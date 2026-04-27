import asyncio
import contextlib
import json
import logging
import os
import re
import time
import sys
import uuid
from urllib import error as urllib_error
from urllib import request as urllib_request

from ten_runtime import AsyncExtension, AsyncTenEnv, Cmd, CmdResult, Data, StatusCode

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "../../../../../apps/backend"))
if project_root not in sys.path:
    sys.path.append(project_root)

from ai_hr.core.config import get_settings
from ai_hr.content.interview_zh import (
    AUDIO_ISSUE_PHRASES,
    AUDIO_RETRY_MESSAGE,
    DEFAULT_CANDIDATE_NAME,
    EXPERT_BRIDGES,
    EXPERT_FILLERS,
    HANDSHAKE_KEYWORDS,
    HANDSHAKE_TEMPLATE,
    INTERVIEW_BRIDGES,
    LLM_EMPTY_FALLBACK_REPLY,
    REENGAGEMENT_MARKERS,
    SKIP_PHRASES,
    TTS_BLACKLIST,
    TTS_META_PREFIXES,
)
from ai_hr.domain.constants import (
    AgentState,
    InterviewEventType,
    InterviewStage,
    PromptTaskKey,
    RuntimeCommand,
    RuntimeDataChannel,
)
from ai_hr.services.interview_runtime.question_flow import InterviewQuestionFlowEngine
from ai_hr.services.interview_runtime.question_schema import normalize_question_pack
from ai_hr.services.interview_runtime.question_seed_builder import build_stage_seed_questions
from ai_hr.services.interview_runtime.realtime_policy import get_stage_realtime_policy
from ai_hr.services.interview_runtime.runtime_engine import InterviewRuntimeEngine
from ai_hr.services.interview_runtime.stage_progress import StageProgressEngine
from ai_hr.services.llm.client import InvokeContext, LLMClient
from ai_hr.services.llm.guardrails import GuardrailService
from ai_hr.services.llm.prompts import (
    INTERVIEW_SYSTEM_PROMPT,
    build_interview_company_intro,
)
from ai_hr.services.llm.router import ModelRouter
from ai_hr.services.orchestrator.conversation_arbiter import ConversationArbiter
from ai_hr.services.orchestrator.streaming_utils import split_sentences, split_sentences_async
from ai_hr.services.orchestrator.turn_completion import TurnCompletionJudge

try:
    from .prompt_builder import InterviewPromptBuilder, PromptBuildInput
    from .session_context import Role, SessionContext
except ImportError:  # pragma: no cover
    from prompt_builder import InterviewPromptBuilder, PromptBuildInput
    from session_context import Role, SessionContext


logger = logging.getLogger(__name__)


class RealtimeEventBridge:
    def __init__(
        self,
        *,
        session_id: str,
        base_url: str,
        api_key: str = "",
        flush_interval_ms: int = 80,
        batch_max_events: int = 20,
        critical_queue_size: int = 512,
        volatile_queue_size: int = 1024,
        request_timeout_s: float = 3.0,
    ):
        self.session_id = str(session_id or "").strip()
        self.base_url = str(base_url or "").rstrip("/")
        self.api_key = str(api_key or "").strip()
        self.flush_interval_ms = max(20, int(flush_interval_ms or 80))
        self.batch_max_events = max(1, int(batch_max_events or 20))
        self.request_timeout_s = max(0.1, float(request_timeout_s or 3.0))
        self.critical_queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=max(8, critical_queue_size))
        self.volatile_queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=max(16, volatile_queue_size))
        self._worker_task: asyncio.Task | None = None
        self._drop_counters = {"critical": 0, "volatile": 0}
        self._circuit_open_until = 0.0

    @property
    def enabled(self) -> bool:
        return bool(self.session_id and self.base_url)

    def start(self) -> None:
        if not self.enabled or self._worker_task is not None:
            return
        self._worker_task = asyncio.create_task(self._run(), name=f"ten-event-bridge-{self.session_id}")

    async def stop(self) -> None:
        if self._worker_task is None:
            return
        self._worker_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._worker_task
        self._worker_task = None

    def emit(self, *, event_type: str, payload: dict, critical: bool = False) -> None:
        if not self.enabled:
            return
        event = {
            "event_id": f"{self.session_id}:{event_type}:{int(time.time() * 1000)}:{uuid.uuid4().hex[:8]}",
            "event_type": event_type,
            "session_id": self.session_id,
            "ts": int(time.time() * 1000),
            "source": "ten_agent",
            "payload": payload,
            "__critical": bool(critical),
        }
        queue = self.critical_queue if critical else self.volatile_queue
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            if critical:
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
                with contextlib.suppress(asyncio.QueueFull):
                    queue.put_nowait(event)
                self._drop_counters["critical"] += 1
                logger.error(
                    "event_bridge.critical_queue_full session_id=%s event_type=%s "
                    "queue_size=%s drop_count=%s text_preview=%s",
                    self.session_id,
                    event_type,
                    queue.qsize(),
                    self._drop_counters["critical"],
                    str(payload.get("text", ""))[:50],
                )
            else:
                self._drop_counters["volatile"] += 1
                if self._drop_counters["volatile"] % 10 == 1:  # Log every 10th drop
                    logger.warning(
                        "event_bridge.volatile_queue_full session_id=%s event_type=%s "
                        "queue_size=%s drop_count=%s",
                        self.session_id,
                        event_type,
                        queue.qsize(),
                        self._drop_counters["volatile"],
                    )

    async def _run(self) -> None:
        try:
            while True:
                if time.monotonic() < self._circuit_open_until:
                    await asyncio.sleep(0.2)
                    continue
                batch = await self._collect_batch()
                if not batch:
                    continue
                ok = await asyncio.to_thread(self._post_batch, batch)
                if not ok:
                    self._requeue_failed_batch(batch)
                    self._circuit_open_until = time.monotonic() + 5.0
        except asyncio.CancelledError:
            return

    def _requeue_failed_batch(self, events: list[dict]) -> None:
        """Best-effort retry by returning failed events back to in-memory queues."""
        if not events:
            return
        requeued = 0
        dropped = 0
        for event in events:
            is_critical = bool(event.get("__critical"))
            queue = self.critical_queue if is_critical else self.volatile_queue
            try:
                queue.put_nowait(event)
                requeued += 1
            except asyncio.QueueFull:
                dropped += 1
                if is_critical:
                    self._drop_counters["critical"] += 1
                else:
                    self._drop_counters["volatile"] += 1
        logger.warning(
            "orchestrator.event_bridge_requeue session_id=%s requeued=%s dropped=%s",
            self.session_id,
            requeued,
            dropped,
        )

    async def _collect_batch(self) -> list[dict]:
        events: list[dict] = []
        first = await self._get_next_event()
        if first is None:
            return events
        events.append(first)
        deadline = time.monotonic() + (self.flush_interval_ms / 1000.0)
        while len(events) < self.batch_max_events and time.monotonic() < deadline:
            event = self._drain_nowait()
            if event is None:
                await asyncio.sleep(0.01)
                continue
            events.append(event)
        return events

    async def _get_next_event(self) -> dict | None:
        event = self._drain_nowait()
        if event is not None:
            return event
        critical_task = asyncio.create_task(self.critical_queue.get())
        volatile_task = asyncio.create_task(self.volatile_queue.get())
        done, pending = await asyncio.wait(
            {critical_task, volatile_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        for task in done:
            with contextlib.suppress(asyncio.CancelledError):
                return task.result()
        return None

    def _drain_nowait(self) -> dict | None:
        for queue in (self.critical_queue, self.volatile_queue):
            with contextlib.suppress(asyncio.QueueEmpty):
                return queue.get_nowait()
        return None

    def _post_batch(self, events: list[dict]) -> bool:
        target_url = f"{self.base_url}/ai/interviews/sessions/{self.session_id}/bridge/events"
        body = json.dumps({"events": events}, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        req = urllib_request.Request(target_url, data=body, headers=headers, method="POST")
        try:
            with urllib_request.urlopen(req, timeout=self.request_timeout_s) as resp:
                return 200 <= int(resp.status) < 300
        except (urllib_error.URLError, TimeoutError, OSError) as exc:
            logger.warning(
                "orchestrator.event_bridge_send_failed session_id=%s error=%s",
                self.session_id,
                exc,
            )
            return False


class InterviewOrchestratorExtension(AsyncExtension):
    def __init__(self, name: str):
        super().__init__(name)
        self.trace_id = ""
        self.task_key = PromptTaskKey.INTERVIEW_FOLLOWUP
        self.max_followup = 2
        self.resume_summary = ""
        self.job_requirements = ""
        self.logged_first_final_input = False
        self.state = None
        self.llm_client = None
        self.flow_engine = None
        self.llm_task = None
        self.system_prompt_built = ""
        self.last_final_transcript = ""
        self.last_finalized_transcript = ""
        self.last_finalized_ts = 0
        self.speculative_task = None
        self.pending_finalize_task = None
        self.pending_finalize_token = 0
        self.pending_payload = None
        self.arbiter = ConversationArbiter()
        self.turn_completion_judge = TurnCompletionJudge()
        self.stage_progress_engine = StageProgressEngine()
        self.runtime_engine = InterviewRuntimeEngine(
            question_flow_engine=self.flow_engine,
            stage_progress_engine=self.stage_progress_engine,
        ) if self.flow_engine is not None else None
        self.playback_sequence = 0
        self.current_turn_start_ms = 0
        self.current_turn_segment_start_ms = 0
        self.current_turn_accumulated_ms = 0
        self.last_asr_activity_ms = 0
        self.pending_finalize_wait_logged = False
        self.turn_triggered = False  # 标记当前回合是否已触发处理
        self.last_triggered_text = ""  # 记录本回合触发时的文本
        
        self.candidate_name = "候选人"
        self.company_info = ""
        self.company_info_source = ""
        self.company_info_version = ""
        self.question_pack_source = ""
        self.question_pack_version = ""
        self.candidate_name = DEFAULT_CANDIDATE_NAME
        self.BRIDGES = [
            "明白了，那我们继续聊聊。",
            "好的，关于这块，我想再听听你的看法。",
            "原来如此，那我们针对你的项目场景再深入一点。",
            "理解了，那我们进入下一个环节。"
        ]
        self.EXPERT_BRIDGES = [
            "简历背景我大概了解了，我们直接进入技术交流。",
            "明白，那我们深挖一下你这个项目的底层实现。",
            "好的，我们先从系统实战角度开始聊。",
            "理解了，我想针对你提到的核心模块继续问一下。"
        ]
        self.EXPERT_FILLERS = [
            "好的。",
            "OK。",
            "明白了。",
            "懂你的意思了。",
            "我听懂了。",
            "了解。",
            "关于这一点，",
            "原来是这样。"
        ]
        self.BRIDGES = list(INTERVIEW_BRIDGES)
        self.EXPERT_BRIDGES = list(EXPERT_BRIDGES)
        self.EXPERT_FILLERS = list(EXPERT_FILLERS)
        self.last_filler = ""
        self.system_prompt = INTERVIEW_SYSTEM_PROMPT
        self.event_bridge: RealtimeEventBridge | None = None
        self.current_question_trace_id = ""
        self.current_question_buffer = ""
        self.opening_topic_id = ""
        self.active_topic_id = ""
        self.active_parent_topic_id = ""
        self.active_is_followup = False
        self.active_phase = "opening"
        self.active_question_seq: int | None = None
        self.active_question_id = ""
        self.session_context = SessionContext(session_id="")
        self.prompt_builder = InterviewPromptBuilder()
        self._bg_tasks: set[asyncio.Task] = set()


    def _create_task(self, coro, name=None) -> asyncio.Task:
        task = asyncio.create_task(coro, name=name)
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)
        return task


    def _build_company_intro(self) -> str:
        return build_interview_company_intro(self.company_info)

    @staticmethod
    def _summarize_question_pack_ids(question_pack: dict) -> str:
        questions = question_pack.get("questions", []) if isinstance(question_pack, dict) else []
        pack_ids: list[str] = []
        if isinstance(questions, list):
            for item in questions[:16]:
                if not isinstance(item, dict):
                    continue
                identifier = str(item.get("idx") or item.get("question_id") or item.get("id") or "").strip()
                if identifier:
                    pack_ids.append(identifier)
        return ",".join(pack_ids)

    def _load_runtime_question_pack(self, config: dict) -> tuple[dict, str, str]:
        raw_pack = config.get("question_pack")
        if isinstance(raw_pack, str):
            raw_text = raw_pack.strip()
            if raw_text:
                with contextlib.suppress(json.JSONDecodeError):
                    raw_pack = json.loads(raw_text)
        if isinstance(raw_pack, list):
            raw_pack = {"questions": raw_pack}
        if not isinstance(raw_pack, dict):
            self._log(
                logging.WARNING,
                "orchestrator.runtime_question_pack_missing",
                raw_pack_type=type(raw_pack).__name__,
                configured_source=str(config.get("question_pack_source") or ""),
                configured_version=str(config.get("question_pack_version") or ""),
            )
            return {"questions": []}, "", ""

        normalized_pack = normalize_question_pack(raw_pack)
        if not normalized_pack.get("questions"):
            self._log(
                logging.WARNING,
                "orchestrator.runtime_question_pack_empty",
                configured_source=str(config.get("question_pack_source") or ""),
                configured_version=str(config.get("question_pack_version") or ""),
            )
            return {"questions": []}, "", ""

        source = str(
            config.get("question_pack_source")
            or normalized_pack.get("source")
            or "runtime"
        ).strip()
        version = str(
            config.get("question_pack_version")
            or normalized_pack.get("version")
            or ""
        ).strip()
        return normalized_pack, source, version

    def _load_local_question_pack(self) -> tuple[dict, str, str]:
        data_dir = os.path.join(project_root, "data")
        q_file = os.path.join(data_dir, "interview_questions.json")
        if not os.path.exists(q_file):
            return {"questions": []}, "", ""

        with open(q_file, "r", encoding="utf-8") as f:
            loaded_questions = json.load(f)
        normalized_pack = normalize_question_pack({"questions": loaded_questions})
        if not normalized_pack.get("questions"):
            return {"questions": []}, "", ""
        return normalized_pack, "local_file", ""

    def _build_seed_question_pack(self) -> tuple[dict, str, str]:
        normalized_pack = normalize_question_pack(
            {
                "questions": build_stage_seed_questions(
                    job_requirements=self.job_requirements,
                    skills=[],
                    language="zh-CN",
                )
            }
        )
        return normalized_pack, "seed_fallback", ""

    def _set_stage(self, stage_code: str, *, reason: str = "") -> None:
        self.state = self.flow_engine.transition_stage(
            state=self.state,
            stage_code=stage_code,
            transition_reason=reason,
        )

    def _detect_candidate_move_on(self, transcript: str) -> bool:
        move_on_phrases = [
            "继续吧",
            "不清楚",
            "没考虑过",
            "换个话题",
            "先过",
            "跳过",
            "继续",
        ]
        return any(phrase in transcript for phrase in move_on_phrases)

    def _is_company_question(self, transcript: str) -> bool:
        text = str(transcript or "").strip()
        if not text or len(text) > 30: # 长度保护：过长的输入通常是候选人的回答，而非询问
            return False
            
        # 强匹配模式：明确的询问意图
        patterns = [
            r"介绍(一下|下)?(你们?|贵)的?(公司|业务|团队)",
            r"(你们?|贵)的?(公司|业务|团队)?的?(业务|方向|是|主营|做什么).*(做)?什么",
            r"(你们?|贵)的?公司的?名称是?",
            r"岗位(职责|要求)是什么",
            r"面试最后(会有)?(公司介绍|介绍(一下|下)?公司)[吗呢]?",
            r"能(再)?讲讲(你们?|贵)的?公司吗",
        ]
        
        if any(re.search(p, text) for p in patterns):
            return True
            
        # 排除模式：候选人描述自己背景时常带的词（防止将描述经历误判为询问）
        negative_patterns = [
            r"我(在|之前|那家)公司",
            r"在这个公司",
            r"公司里边",
            r"负责",
            r"项目",
            r"这段实习",
            r"之前的",
            r"上家",
            r"工作过",
        ]
        if any(re.search(p, text) for p in negative_patterns):
            return False
            
        # 弱匹配兜底（保留之前的核心关键词，但更谨慎）
        weak_keywords = ("你们公司叫什么", "你们公司主营", "你们是做什么的")
        return any(wk in text for wk in weak_keywords)

    async def _emit_company_qa_defer_reply(self, ten_env: AsyncTenEnv) -> None:
        reply = "公司和岗位相关信息我会在面试最后统一介绍，我们先继续当前面试流程。"
        await self._send_to_tts(ten_env, reply, is_final=False)
        await self._send_to_tts(ten_env, "", is_final=True)

    async def _emit_scripted_question(
        self,
        ten_env: AsyncTenEnv,
        *,
        question: dict[str, object] | None,
        trace_id: str = "",
    ) -> None:
        target_question = question if isinstance(question, dict) else {}
        text = str(target_question.get("question") or "").strip()
        if not text:
            return

        self.state["current_question_id"] = str(
            target_question.get("question_id")
            or target_question.get("id")
            or self.state.get("current_question_id")
            or ""
        ).strip()
        self.state["current_question_status"] = "scripted_asked"
        self.state["current_question_asked"] = True
        self.state["current_output_mode"] = "scripted_question"
        self.state["question_completion_reason"] = ""
        self.state["transition_reason"] = "scripted_question_emitted"

        self._log(
            logging.INFO,
            "orchestrator.scripted_question_emitted",
            question_id=self.state.get("current_question_id"),
            question_text=text,
            active_question_index=self.state.get("active_question_index"),
        )
        await self._send_to_tts(ten_env, text, is_final=False, trace_id=trace_id)
        await self._send_to_tts(ten_env, "", is_final=True, trace_id=trace_id)

    def _build_next_question_preview(
        self,
        *,
        decision,
        current_question: dict | None,
    ) -> str:
        if (
            decision
            and getattr(decision, "output_mode", "") == "scripted_question"
            and isinstance(getattr(decision, "target_question", None), dict)
        ):
            preview_question = decision.target_question or {}
        elif decision and decision.must_transition:
            preview_question = current_question or {}
        else:
            preview_question = self.flow_engine.current_question(
                state={
                    "active_question_index": self.state["active_question_index"] + 1,
                    "interview_stage": (self.state or {}).get("interview_stage", InterviewStage.OPENING),
                    "question_statuses": (self.state or {}).get("question_statuses", []),
                    "question_stage_sequence": (self.state or {}).get("question_stage_sequence", []),
                },
                question_pack=self.question_pack,
            ) or {}
        return str(preview_question.get("question") or "请继续围绕岗位核心能力深入作答。")

    def _get_active_question_context(self) -> dict:
        question = self.flow_engine.current_question(
            state=self.state,
            question_pack=self.question_pack,
        ) or {}
        raw_seq = question.get("idx")
        try:
            question_seq = int(raw_seq) if raw_seq is not None else None
        except (TypeError, ValueError):
            question_seq = None
        if question_seq is None:
            try:
                question_seq = int((self.state or {}).get("active_question_index") or 0) + 1
            except (TypeError, ValueError):
                question_seq = None
        return {
            "question": question,
            "question_id": str(question.get("question_id") or question.get("id") or ""),
            "question_seq": question_seq,
            "topic_name": str(question.get("topic_name") or ""),
            "topic_aliases": question.get("topic_aliases") if isinstance(question.get("topic_aliases"), list) else [],
        }

    def _resolve_phase_from_stage(self, stage: str) -> str:
        normalized = str(stage or "").strip()
        if normalized in {InterviewStage.OPENING, InterviewStage.SELF_INTRO}:
            return "opening"
        return "formal"

    def _ensure_opening_topic_id(self) -> str:
        if not self.opening_topic_id:
            self.opening_topic_id = f"opening-{uuid.uuid4().hex[:12]}"
        return self.opening_topic_id

    def _now_ms(self) -> int:
        return int(time.perf_counter() * 1000)

    def _get_realtime_policy(self, stage_code: str | None = None):
        active_stage = stage_code or (self.state or {}).get("interview_stage", InterviewStage.OPENING)
        return get_stage_realtime_policy(active_stage)

    def _cancel_pending_finalize(self, *, clear_payload: bool = True) -> None:
        if clear_payload:
            self.pending_payload = None
        self.pending_finalize_token += 1
        if self.pending_finalize_task and not self.pending_finalize_task.done():
            self.pending_finalize_task.cancel()
        self.pending_finalize_task = None
        self.pending_finalize_wait_logged = False

    def _invalidate_active_response(self) -> None:
        self.arbiter.invalidate_generation()
        if self.llm_task and not self.llm_task.done():
            self.llm_task.cancel()

    def _reset_turn_capture(self) -> None:
        self.current_turn_start_ms = 0
        self.current_turn_segment_start_ms = 0
        self.current_turn_accumulated_ms = 0
        self.last_asr_activity_ms = 0
        self.pending_finalize_wait_logged = False

    def _has_active_response_pipeline(self) -> bool:
        if self.pending_payload:
            return True
        if self.pending_finalize_task and not self.pending_finalize_task.done():
            return True
        if self.llm_task and not self.llm_task.done():
            return True
        if self.arbiter.active_generation_id:
            return True
        return False

    def _is_reengagement_transcript(self, transcript: str) -> bool:
        text = str(transcript or "").strip().lower()
        if not text:
            return False
        return any(marker in text for marker in REENGAGEMENT_MARKERS)
        reengagement_markers = (
            "你在听吗",
            "我们继续面试",
            "继续面试",
            "你怎么不说话",
            "怎么不说话",
            "再给我",
            "hello hello",
            "hello",
            "喂",
        )
        return any(marker in text for marker in reengagement_markers)

    def _is_duplicate_like_transcript(self, current: str, previous: str) -> bool:
        """Conservative duplicate check to avoid dropping semantically different turns."""
        cur = str(current or "").strip()
        prev = str(previous or "").strip()
        if not cur or not prev:
            return False
        if cur == prev:
            return True
        if cur in prev or prev in cur:
            min_len = max(1, min(len(cur), len(prev)))
            return abs(len(cur) - len(prev)) <= max(4, int(min_len * 0.4))
        prefix_len = len(os.path.commonprefix([cur, prev]))
        min_len = max(1, min(len(cur), len(prev)))
        return min_len >= 6 and prefix_len >= max(6, int(min_len * 0.8))

    def _new_turn_id(self) -> str:
        return f"turn-{uuid.uuid4().hex[:8]}"

    def _log(self, level: int, event: str, **fields) -> None:
        payload = {
            "event": event,
            "session_id": self.session_context.session_id or "",
            "trace_id": self.trace_id or "",
            "stage": (self.state or {}).get("interview_stage", ""),
        }
        for key, value in fields.items():
            if value is not None:
                payload[key] = value
        logger.log(level, json.dumps(payload, ensure_ascii=False, sort_keys=True))

    def _append_context_turn(
        self,
        *,
        role: Role,
        text: str,
        stage: str = "",
        trace_id: str = "",
        question_id: str = "",
        topic_name: str = "",
    ) -> None:
        self.session_context.append_turn(
            turn_id=self._new_turn_id(),
            role=role,
            text=text,
            now_ms=self._now_ms(),
            stage=stage,
            trace_id=trace_id,
            question_id=question_id,
            topic_name=topic_name,
        )

    def _start_pending_question(
        self,
        *,
        question_text: str,
        stage: str,
        trace_id: str = "",
        question_id: str = "",
        topic_name: str = "",
    ) -> None:
        self.session_context.start_pending_question(
            turn_id=self._new_turn_id(),
            question_text=question_text,
            now_ms=self._now_ms(),
            stage=stage,
            trace_id=trace_id,
            question_id=question_id,
            topic_name=topic_name,
        )

    def _finalize_candidate_answer(self, *, answer_text: str) -> None:
        self.session_context.append_candidate_answer(
            turn_id=self._new_turn_id(),
            answer_text=answer_text,
            now_ms=self._now_ms(),
        )

    def _build_recent_history_text(self) -> str:
        return self.session_context.build_recent_history_text()

    def _sanitize_tts_text(self, text: str) -> str:
        cleaned = str(text or "").strip()
        if not cleaned:
            return ""

        # Remove common internal-control wrappers before any TTS playback.
        cleaned = re.sub(r"（[^）]*）", "", cleaned)
        cleaned = re.sub(r"\([^)]*\)", "", cleaned)
        cleaned = re.sub(r"\[[^\]]*\]", "", cleaned)

        meta_prefixes = (
            "听起来",
            "需要引导",
            "需要继续追问",
            "候选人",
            "说明",
            "看起来他",
            "我应该",
            "这里需要",
            "先不要",
            "回到自己的项目经验",
            "具体实现细节不太清晰",
            "内部",
            "策略",
            "满意",
            "fallback",
        )
        lowered = cleaned.lower()
        if any(token in lowered for token in ("need to", "internal note", "meta", "fallback")):
            return ""

        for prefix in meta_prefixes:
            idx = cleaned.find(prefix)
            if idx != -1 and idx <= 4:
                sentence_start = max(cleaned.find("你"), cleaned.find("那"), cleaned.find("关"), cleaned.find("我"))
                if sentence_start > idx:
                    cleaned = cleaned[sentence_start:]
                else:
                    return ""

        cleaned = re.sub(r"^[,，。！？:：\]\[]+", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def _is_tts_speakable(self, text: str) -> bool:
        candidate = str(text or "").strip()
        if not candidate:
            return False
        if len(candidate) < 4:
            return False
        blacklist = (
            "需要引导",
            "具体实现细节不太清晰",
            "候选人",
            "回到自己的项目经验",
            "内部",
            "策略",
            "满意",
            "fallback",
        )
        if any(term in candidate for term in blacklist):
            return False
        if candidate[0] in ",，。！？:：)]":
            return False
        return True

    def _remaining_finalize_delay_ms(self, *, stage: str, asr_final_ts: float, asr_physical_stop_ts: float) -> int:
        policy = self._get_realtime_policy(stage)
        elapsed_ms = 0
        if asr_final_ts > 0 and asr_physical_stop_ts > 0:
            elapsed_ms = max(0, int((asr_final_ts - asr_physical_stop_ts) * 1000))
        likely_done_remaining = max(0, policy.likely_done_ms - elapsed_ms)
        return likely_done_remaining + policy.resume_grace_ms

    def _schedule_finalize(
        self,
        ten_env: AsyncTenEnv,
        *,
        transcript: str,
        asr_final_ts: float,
        asr_sentence_start_ts: float,
        asr_physical_stop_ts: float,
        orch_receive_ts: float,
    ) -> None:
        stage = self.state.get("interview_stage", InterviewStage.OPENING)
        delay_ms = self._remaining_finalize_delay_ms(
            stage=stage,
            asr_final_ts=asr_final_ts,
            asr_physical_stop_ts=asr_physical_stop_ts,
        )
        merged_transcript = transcript
        if self.pending_payload and str(self.pending_payload.get("transcript") or "").strip():
            prior_transcript = str(self.pending_payload.get("transcript") or "").strip()
            if transcript not in prior_transcript:
                merged_transcript = f"{prior_transcript} {transcript}".strip()
            else:
                merged_transcript = prior_transcript
            self._log(
                logging.INFO,
                "orchestrator.pending_transcript_merged",
                merged_chars=len(merged_transcript),
                turn_accumulated_ms=self.current_turn_accumulated_ms,
            )
        self._cancel_pending_finalize(clear_payload=False)
        self.pending_payload = {
            "transcript": merged_transcript,
            "asr_final_ts": asr_final_ts,
            "asr_sentence_start_ts": asr_sentence_start_ts,
            "asr_physical_stop_ts": asr_physical_stop_ts,
            "orch_receive_ts": orch_receive_ts,
            "turn_start_ms": self.current_turn_start_ms,
            "turn_accumulated_ms": self.current_turn_accumulated_ms,
        }
        self.last_asr_activity_ms = self._now_ms()
        
        # Turn stitching: if we are within 2.5s of the last finalized turn, 
        # it is likely the user is continuing their previous thought after a premature finalization.
        now = time.perf_counter()
        stitch_window = 2.5 
        if not self.pending_payload and self.last_finalized_ts and (now - self.last_finalized_ts) < stitch_window:
             if self.last_finalized_transcript and transcript not in self.last_finalized_transcript:
                 transcript = f"{self.last_finalized_transcript} {transcript}".strip()
                 self._log(
                     logging.INFO, 
                     "orchestrator.turn_stitched", 
                     diff_ms=int((now - self.last_finalized_ts) * 1000),
                     new_transcript_len=len(transcript)
                 )
             # Consume the finalized state so we don't stitch again for the same turn fragment
             self.last_finalized_ts = 0

        token = self.pending_finalize_token
        self.pending_finalize_task = self._create_task(
            self._finalize_after_delay(ten_env, delay_ms=delay_ms, token=token),
            name="vad-finalize-after-delay"
        )

    async def _finalize_after_delay(self, ten_env: AsyncTenEnv, *, delay_ms: int, token: int) -> None:
        try:
            if delay_ms > 0:
                await asyncio.sleep(delay_ms / 1000.0)
            while True:
                if token != self.pending_finalize_token:
                    return
                now_ms = self._now_ms()
                if not self.pending_payload:
                    return
                if self.is_user_speaking:
                    stage = (self.state or {}).get("interview_stage", InterviewStage.OPENING)
                    policy = self._get_realtime_policy(stage)
                    idle_since_asr_ms = (
                        now_ms - self.last_asr_activity_ms if self.last_asr_activity_ms else 0
                    )
                    stale_speaking_guard_ms = max(policy.hard_done_ms, 1800)
                    if idle_since_asr_ms >= stale_speaking_guard_ms:
                        self._log(
                            logging.WARNING,
                            "orchestrator.stale_speaking_state_cleared",
                            idle_since_asr_ms=idle_since_asr_ms,
                        )
                        self.is_user_speaking = False
                        self.current_turn_segment_start_ms = 0
                        self.pending_finalize_wait_logged = False
                        continue
                    if not self.pending_finalize_wait_logged:
                        self._log(logging.INFO, "orchestrator.pending_finalize_waiting")
                        self.pending_finalize_wait_logged = True
                    await asyncio.sleep(0.2)
                    continue
                if self.pending_finalize_wait_logged:
                    self._log(logging.INFO, "orchestrator.pending_finalize_resumed")
                    self.pending_finalize_wait_logged = False

                payload = dict(self.pending_payload)
                stage = (self.state or {}).get("interview_stage", InterviewStage.OPENING)
                policy = self._get_realtime_policy(stage)
                speaking_elapsed_ms = int(payload.get("turn_accumulated_ms") or 0)

                # ── Dual-Reference Silence Calculation ────────────────────────────────
                # BUG GUARD: When VAD fires END_OF_SENTENCE mid-utterance, the forced ASR
                # emit may carry asr_physical_stop_ts=0.0 (NLS on_sentence_end hasn't fired).
                # This makes silence_ms = now_ms = process uptime ms (hundreds of thousands),
                # instantly exceeding max_force_finalize_ms → user gets rudely interrupted.
                #
                # Fix: use BOTH references and take the MINIMUM (most conservative).
                # activity_silence_ms: time since last ASR event in orchestrator (always valid)
                # ts_silence_ms:       time since NLS sentence-end ts (can be stale or zero)
                asr_physical_stop_ts = float(payload.get("asr_physical_stop_ts") or 0.0)
                activity_silence_ms = (
                    max(0, now_ms - self.last_asr_activity_ms)
                    if self.last_asr_activity_ms > 0 else 0
                )
                if asr_physical_stop_ts > 0:
                    ts_silence_ms = max(0, now_ms - int(asr_physical_stop_ts * 1000))
                    silence_ms = min(activity_silence_ms, ts_silence_ms)
                else:
                    silence_ms = activity_silence_ms  # ts is invalid, use activity only

                # ── Inter-Sentence Holdoff ────────────────────────────────────────────
                # Do not evaluate turn completion if we haven't reached soft_pause_ms yet.
                # Prevents cutting off users mid-sentence during natural Chinese speech pauses.
                if silence_ms < policy.soft_pause_ms:
                    await asyncio.sleep(0.1)
                    continue
                # ─────────────────────────────────────────────────────────────────────

                resumed_recently = bool(
                    self.arbiter.last_user_resume_ms
                    and (now_ms - self.arbiter.last_user_resume_ms) < policy.resume_grace_ms
                )
                decision = self.turn_completion_judge.judge(
                    transcript=str(payload.get("transcript") or ""),
                    stage=stage,
                    policy=policy,
                    speaking_elapsed_ms=speaking_elapsed_ms,
                    silence_ms=silence_ms,
                    resumed_recently=resumed_recently,
                )
                self._log(
                    logging.INFO,
                    "orchestrator.finalize_decision",
                    decision_stage=stage,
                    should_finalize=decision.should_finalize,
                    reason=decision.reason,
                    silence_ms=silence_ms,
                    activity_silence_ms=activity_silence_ms,
                    asr_stop_ts_valid=asr_physical_stop_ts > 0,
                    speaking_elapsed_ms=speaking_elapsed_ms,
                    semantic_completion_score=round(decision.semantic_completion_score, 2),
                )
                if decision.should_finalize:
                    if decision.reason == "max_silence_force_finalize":
                        self._log(
                            logging.WARNING,
                            "orchestrator.force_finalize_after_long_silence",
                            transcript_chars=len(str(payload.get("transcript") or "")),
                        )
                    self.pending_payload = None
                    await self._handle_interaction(ten_env, **payload)
                    self._reset_turn_capture()
                    return

                await asyncio.sleep(max(100, decision.need_more_wait_ms) / 1000.0)
        except asyncio.CancelledError:
            return

    async def on_init(self, ten_env: AsyncTenEnv) -> None:
        self._ten_env = ten_env
        self._log(logging.INFO, "orchestrator.init_started")
        settings = get_settings()
        router = ModelRouter(settings=settings)
        guardrail = GuardrailService()

        self.llm_client = LLMClient(router=router, guardrail_service=guardrail)
        self.flow_engine = InterviewQuestionFlowEngine()
        self.runtime_engine = InterviewRuntimeEngine(
            question_flow_engine=self.flow_engine,
            stage_progress_engine=self.stage_progress_engine,
        )
        self.question_pack = {"questions": []}

        config_json, _ = await ten_env.get_property_to_json("")
        config = json.loads(config_json) if config_json else {}

        self.task_key = config.get("task_key", PromptTaskKey.INTERVIEW_FOLLOWUP)
        self.max_followup = int(config.get("max_followup", 2)) or 2
        
        # 核心状态初始化
        self.is_user_speaking = False
        self.session_id = str(config.get("session_id") or uuid.uuid4())
        bridge_base_url = (
            str(config.get("bridge_api_base_url") or "").strip()
            or str(os.getenv("AI_HR_REALTIME_BRIDGE_BASE_URL") or "").strip()
            or "http://127.0.0.1:8000/api/v1"
        )
        bridge_api_key = (
            str(config.get("bridge_api_key") or "").strip()
            or str(os.getenv("AI_HR_AI_INTERVIEW_API_KEY") or "").strip()
        )
        self.event_bridge = RealtimeEventBridge(
            session_id=self.session_id,
            base_url=bridge_base_url,
            api_key=bridge_api_key,
        )
        self.event_bridge.start()
        
        # Start background listener for event bus
        
        self.session_context = SessionContext(session_id=self.session_id, max_turns=8)
        
        # 捕获职位要求
        self.job_requirements = config.get("job_requirements", "精通分布式系统和高可用架构")
        
        # 智能提取候选人姓名与简历内容逻辑
        def extract_name(text: str) -> str:
            if not text:
                return "同学"
            # 1. 尝试匹配常见姓名格式关键字
            patterns = [
                r"姓名[:：]\s*([^\s\d]{2,10})",
                r"Candidate[:：]\s*([^\s\d]{2,10})",
                r"Name[:：]\s*([^\s\d]{2,10})",
            ]
            for p in patterns:
                m = re.search(p, text)
                if m:
                    res = m.group(1).strip()
                    if res: return res
            
            # 2. 如果没找到关键字，取前几行中第一个看起来像名字的（非空且不含“简历”或太长的行）
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            for line in lines[:5]:
                # 排除明显的标题行
                if any(x in line for x in ("简历", "Resume", "手机", "电话", "邮箱", "@")):
                    continue
                # 简单正则：2-4个中文字符
                if re.match(r"^[\u4e00-\u9fa5]{2,4}$", line):
                    return line
            return "同学"

        def abbreviate_name(name: str) -> str:
            cleaned = name.strip()
            if not cleaned or cleaned == "同学":
                return "同学"
            # 如果是两三位中文名，取后两位
            if re.match(r"^[\u4e00-\u9fa5]{2,4}$", cleaned):
                if len(cleaned) <= 2:
                    return cleaned
                return cleaned[-2:]
            # 英文名取前 10 位
            return cleaned[:10]

        # 优先从 config 获取简历全文
        raw_resume = config.get("resume_summary", "").strip()
        
        # 如果 config 为空，尝试从本地文件回退（仅限调试）
        if not raw_resume:
            resume_file_path = os.path.join(project_root, "data", "测试文本简历.txt")
            if os.path.exists(resume_file_path):
                try:
                    with open(resume_file_path, "r", encoding="utf-8") as f:
                        raw_resume = f.read().strip()
                except Exception as e:
                    logger.warning(f"Failed to read fallback resume file: {e}")

        # 最终确认简历内容
        self.resume_summary = raw_resume or "一名资深开发工程师"
        
        # 提取并缩写姓名
        full_name = extract_name(self.resume_summary)
        self.candidate_name = abbreviate_name(full_name)
        
        self._log(
            logging.INFO, 
            "orchestrator.candidate_context_resolved", 
            candidate_name=self.candidate_name,
            full_name=full_name,
            resume_chars=len(self.resume_summary)
        )

        self.trace_id = "ten_trace_" + uuid.uuid4().hex[:8]

        # 尝试加载预生成的面试题库
        runtime_pack, runtime_source, runtime_version = self._load_runtime_question_pack(config)
        if runtime_pack.get("questions"):
            self.question_pack = runtime_pack
            self.question_pack_source = runtime_source or "runtime"
            self.question_pack_version = runtime_version
        else:
            try:
                local_pack, local_source, local_version = self._load_local_question_pack()
            except Exception as exc:
                logger.exception(
                    json.dumps(
                        {
                            "event": "orchestrator.local_question_pack_load_failed",
                            "error": str(exc),
                        },
                        ensure_ascii=False,
                    )
                )
                local_pack, local_source, local_version = {"questions": []}, "", ""

            if local_pack.get("questions"):
                self.question_pack = local_pack
                self.question_pack_source = local_source
                self.question_pack_version = local_version
                self._log(
                    logging.WARNING,
                    "orchestrator.question_pack_fallback_local",
                    question_pack_source=self.question_pack_source or "local_file",
                    question_pack_version=self.question_pack_version or "",
                    question_count=len(self.question_pack.get("questions", [])),
                    question_ids=self._summarize_question_pack_ids(self.question_pack),
                )
            else:
                seed_pack, seed_source, seed_version = self._build_seed_question_pack()
                self.question_pack = seed_pack
                self.question_pack_source = seed_source
                self.question_pack_version = seed_version
                self._log(
                    logging.WARNING,
                    "orchestrator.question_pack_fallback_seed",
                    warning="runtime_question_pack_missing_or_empty",
                    question_pack_source=self.question_pack_source or "seed_fallback",
                    question_pack_version=self.question_pack_version or "",
                    question_count=len(self.question_pack.get("questions", [])),
                    question_ids=self._summarize_question_pack_ids(self.question_pack),
                )

        self._log(
            logging.INFO,
            "orchestrator.question_pack_ready",
            question_pack_source=self.question_pack_source or "unknown",
            question_pack_version=self.question_pack_version or "",
            question_count=len(self.question_pack.get("questions", [])),
            question_ids=self._summarize_question_pack_ids(self.question_pack),
        )

        self.state = self.flow_engine.init_state(question_pack=self.question_pack)
        self.stage_progress_engine = StageProgressEngine()
        self.prompt_builder = InterviewPromptBuilder()
        self.arbiter = ConversationArbiter()
        self.turn_completion_judge = TurnCompletionJudge()

        # 预加载公司与系统级 Prompts
        self.company_info = str(
            config.get("company_info")
            or config.get("company_profile")
            or config.get("company_intro")
            or ""
        ).strip()
        self.company_info_source = str(config.get("company_info_source") or "").strip()
        self.company_info_version = str(config.get("company_info_version") or "").strip()
        self._log(
            logging.INFO,
            "orchestrator.company_info_ready",
            company_info_loaded=bool(self.company_info),
            company_info_source=self.company_info_source or "unknown",
            company_info_version=self.company_info_version or "",
            company_info_chars=len(self.company_info),
        )
        self.system_prompt_built = INTERVIEW_SYSTEM_PROMPT

        # 运行时变量重置
        self.last_filler = ""
        self.pending_payload = None
        self.turn_triggered = False
        self.last_asr_activity_ms = 0
        self.current_turn_segment_start_ms = 0
        self.current_turn_accumulated_ms = 0
        self.current_turn_start_ms = 0
        self.pending_finalize_task = None
        self.pending_finalize_token = 0
        self.pending_finalize_wait_logged = False
        self.llm_task = None
        self.opening_topic_id = ""
        self.active_topic_id = ""
        self.active_parent_topic_id = ""
        self.active_is_followup = False
        self.active_phase = "opening"
        self.active_question_seq = None
        self.active_question_id = ""

    async def _handle_interaction(
        self,
        ten_env: AsyncTenEnv,
        transcript: str,
        asr_final_ts: float,
        asr_sentence_start_ts: float,
        asr_physical_stop_ts: float,
        orch_receive_ts: float,
        turn_start_ms: int | None = None,
        turn_accumulated_ms: int | None = None,
    ) -> None:
        try:
            if turn_accumulated_ms is not None:
                self.current_turn_accumulated_ms = max(0, int(turn_accumulated_ms))
            if turn_start_ms is not None:
                self.current_turn_start_ms = max(0, int(turn_start_ms))

            # Speaking Guard: Do not trigger interaction if candidate is actively speaking.
            # This prevents interruptions when a VAD timer expires but the user resumes speech.
            if self.arbiter.is_candidate_speaking:
                self._log(
                    logging.INFO,
                    "orchestrator.interaction_suppressed_candidate_speaking",
                    transcript=transcript[:200],
                )
                return

            self.last_finalized_transcript = transcript
            self.last_finalized_ts = time.perf_counter()

            stage = self.state.get("interview_stage", InterviewStage.OPENING)
            original_index = self.state.get("active_question_index", 0)
            current_q = self.flow_engine.current_question(
                state=self.state,
                question_pack=self.question_pack,
            ) or {}

            self._log(
                logging.INFO,
                "orchestrator.interaction_triggered",
                interaction_stage=stage,
                active_question_index=self.state.get("active_question_index"),
                original_index=original_index,
            )

            if stage == InterviewStage.OPENING:
                if not self.state["context_flags"]["connectivity_confirmed"]:
                    self.state["context_flags"]["connectivity_confirmed"] = True
                    self._set_stage(InterviewStage.SELF_INTRO, reason="connectivity_confirmed")
                    formal_welcome = "好的，那我们正式开始。你可以先做一个 1 到 2 分钟的自我介绍。"
                    self._log(logging.INFO, "orchestrator.handshake_confirmed", transcript=transcript[:200])
                    await self._send_to_tts(ten_env, formal_welcome, is_final=False)
                    await self._send_to_tts(ten_env, "", is_final=True)
                    return
                self._set_stage(InterviewStage.SELF_INTRO, reason="opening_completed")
                stage = self.state.get("interview_stage", InterviewStage.SELF_INTRO)

            if stage == InterviewStage.COMPANY_QA:
                if not self.state["context_flags"]["company_info_shared"]:
                    self.state["context_flags"]["company_info_shared"] = True
                    reply_msg = self._build_company_intro()
                    await self._send_to_tts(ten_env, reply_msg, is_final=False)
                    await self._send_to_tts(ten_env, "", is_final=True)
                    return
                if any(p in transcript for p in ["没问题", "没有了", "大概了解", "谢谢", "再见"]):
                    self._set_stage(InterviewStage.CLOSING, reason="candidate_has_no_more_questions")
                    stage = self.state.get("interview_stage", InterviewStage.CLOSING)

            if stage == InterviewStage.CLOSING:
                if not self.state["context_flags"]["closing_started"]:
                    self.state["context_flags"]["closing_started"] = True
                    closing_msg = "那今天先聊到这里，后续安排 HR 会再和你同步。回头见。"
                    await self._send_to_tts(ten_env, closing_msg, is_final=False)
                    await self._send_to_tts(ten_env, "", is_final=True)
                return

            if stage != InterviewStage.COMPANY_QA and self._is_company_question(transcript):
                self._log(
                    logging.INFO,
                    "orchestrator.company_question_deferred",
                    transcript=transcript[:200],
                )
                await self._emit_company_qa_defer_reply(ten_env)
                return

            candidate_requested_move_on = self._detect_candidate_move_on(transcript)
            decision = self.runtime_engine.process_candidate_turn(
                state=self.state,
                question_pack=self.question_pack,
                transcript=transcript,
                confidence=0.95,
                candidate_requested_move_on=candidate_requested_move_on,
            )
            stage_progress_snapshot = decision.stage_progress_snapshot
            self.state = dict(decision.updated_state)

            if stage_progress_snapshot is not None:
                self._log(
                    logging.INFO,
                    "orchestrator.stage_progress_updated",
                    progress_stage=stage,
                    completed=stage_progress_snapshot.completed,
                    collected_signals=stage_progress_snapshot.collected_signals,
                    missing_signals=stage_progress_snapshot.missing_signals,
                )

            self._log(
                logging.INFO,
                "orchestrator.runtime_decision_applied",
                next_action=decision.next_action,
                must_transition=decision.must_transition,
                output_mode=getattr(decision, "output_mode", ""),
                flow_reason=decision.flow_reason,
                next_stage=decision.next_stage,
                target_question_id=str((decision.target_question or {}).get("question_id") or ""),
                followup_budget_remaining=getattr(decision, "followup_budget_remaining", 0),
            )

            stage = self.state.get("interview_stage", stage)
            current_q = decision.current_question or current_q
            if isinstance(getattr(decision, "target_question", None), dict):
                current_q = decision.target_question or current_q
            elif decision.must_transition:
                current_q = self.flow_engine.current_question(
                    state=self.state,
                    question_pack=self.question_pack,
                ) or current_q

            if getattr(decision, "output_mode", "") == "scripted_question":
                await self._emit_scripted_question(
                    ten_env,
                    question=current_q,
                    trace_id=self.trace_id,
                )
                return

            # CRITICAL: Enforce followup budget limit at code level
            followup_budget = int(getattr(decision, "followup_budget_remaining", 0) or 0)
            if followup_budget <= 0 and decision.must_transition:
                self._log(
                    logging.WARNING,
                    "orchestrator.followup_budget_exhausted_force_transition",
                    followup_budget_remaining=followup_budget,
                    followup_count_current=int(self.state.get("followup_count_current", 0)),
                    current_question_id=str(current_q.get("question_id") or ""),
                )
                # Force transition to next question instead of generating followup
                await self._emit_scripted_question(
                    ten_env,
                    question=current_q,
                    trace_id=self.trace_id,
                )
                return

            self.session_context.sync_runtime_state(
                focus_experience=str(self.state.get("focus_experience") or ""),
                focus_module=str(self.state.get("focus_module") or ""),
                active_topic_name=str(self.state.get("active_topic_name") or current_q.get("topic_name") or ""),
                active_topic_rounds=int(self.state.get("active_topic_rounds") or 0),
                topic_aliases=current_q.get("topic_aliases") if isinstance(current_q.get("topic_aliases"), list) else [],
            )

            next_q_text = self._build_next_question_preview(
                decision=decision,
                current_question=current_q,
            )
            raw_success_signals = current_q.get("success_signals") or current_q.get("expected_signal") or []
            if isinstance(raw_success_signals, str):
                success_signals = raw_success_signals
            else:
                success_signals = ", ".join(str(item) for item in raw_success_signals)

            transition_hint = "[MUST_TRANSITION]: close the current topic and move to the next question." if decision.must_transition else ""
            next_question_prompt = f"Next question preview: {next_q_text}\n{transition_hint}"

            build_result = self.prompt_builder.build(
                PromptBuildInput(
                    stage=stage,
                    output_mode=str(getattr(decision, "output_mode", "llm_followup") or "llm_followup"),
                    candidate_name=self.candidate_name,
                    transcript=transcript,
                    current_question=str(current_q.get("question") or ""),
                    target_question_id=str(current_q.get("question_id") or current_q.get("id") or ""),
                    next_question=next_question_prompt,
                    success_signals=success_signals,
                    is_last_followup=bool(decision.must_transition),
                    followup_budget_remaining=int(getattr(decision, "followup_budget_remaining", 0) or 0),
                    company_info=self.company_info,
                    stage_goal=str(self.state.get("stage_goal") or ""),
                    missing_evidence=self.state.get("missing_evidence"),
                    difficulty_level=str(current_q.get("difficulty_level") or current_q.get("difficulty") or "normal"),
                    transition_reason=str(getattr(decision, "transition_brief", "") or ""),
                    question_type=str(current_q.get("question_type") or current_q.get("type") or "followup"),
                    focus_experience=str(self.state.get("focus_experience") or ""),
                    focus_module=str(self.state.get("focus_module") or ""),
                    active_topic_name=str(self.state.get("active_topic_name") or current_q.get("topic_name") or ""),
                    active_topic_rounds=int(self.state.get("active_topic_rounds") or 0),
                    must_transition=bool(decision.must_transition),
                    candidate_requested_move_on=bool(candidate_requested_move_on),
                    flow_reason=str(decision.flow_reason or ""),
                    system_prompt_prefix=str(self.system_prompt),
                    session_context=self.session_context,
                )
            )

            llm_start_ts = time.perf_counter()
            self.llm_task = self._create_task(
                self._llm_streaming_worker(
                    ten_env,
                    context=InvokeContext(
                        task_key=self.task_key,
                        trace_id=self.trace_id,
                        prompt=build_result.prompt,
                        system_prompt=build_result.system_prompt,
                    ),
                    asr_final_ts=asr_final_ts,
                    asr_sentence_start_ts=asr_sentence_start_ts,
                    asr_physical_stop_ts=asr_physical_stop_ts,
                    orch_receive_ts=orch_receive_ts,
                    llm_start_ts=llm_start_ts,
                    transcript=transcript,
                ),
                name="llm-streaming-worker"
            )
        except Exception as exc:
            self._log(logging.ERROR, "orchestrator.interaction_handling_failed", error=str(exc))

    async def on_cmd(self, ten_env: AsyncTenEnv, cmd: Cmd) -> None:
        cmd_name = cmd.get_name()

        if cmd_name == RuntimeCommand.START_OF_SENTENCE:
            self.is_user_speaking = True
            now_ms = self._now_ms()
            if not self.current_turn_start_ms:
                self.current_turn_start_ms = now_ms
            self.current_turn_segment_start_ms = now_ms
            policy = self._get_realtime_policy()
            self.arbiter.on_candidate_speaking(
                now_ms=now_ms,
                commit_guard_ms=policy.commit_guard_ms,
            )
            self._cancel_pending_finalize(clear_payload=False)
            self._invalidate_active_response()
            self.turn_triggered = False
            self._emit_agent_state(AgentState.LISTENING)
            self._log(logging.INFO, "orchestrator.user_speaking_started")
            await ten_env.send_cmd(Cmd.create(RuntimeCommand.INTERRUPT))

        elif cmd_name == RuntimeCommand.END_OF_SENTENCE:
            self.is_user_speaking = False
            now_ms = self._now_ms()
            if self.current_turn_segment_start_ms:
                self.current_turn_accumulated_ms += max(0, now_ms - self.current_turn_segment_start_ms)
                self.current_turn_segment_start_ms = 0
            policy = self._get_realtime_policy()
            self.arbiter.on_candidate_pause(
                now_ms=now_ms,
                commit_guard_ms=policy.commit_guard_ms,
            )
            self._emit_agent_state(AgentState.THINKING)
            self._log(logging.INFO, "orchestrator.user_speaking_stopped")

        elif cmd_name == RuntimeCommand.ON_CONNECTED:
            if self.state and self.state.get("interview_stage", InterviewStage.OPENING) == InterviewStage.OPENING and not self.state["context_flags"].get("greeted", False):
                self._log(logging.INFO, "orchestrator.handshake_started")
                handshake_msg = HANDSHAKE_TEMPLATE.format(candidate_name=self.candidate_name)
                await self._send_to_tts(ten_env, handshake_msg, is_final=False)
                await self._send_to_tts(ten_env, "", is_final=True)
                self._set_stage(InterviewStage.OPENING, reason="connectivity_handshake_sent")
                self.state["context_flags"]["greeted"] = True
            else:
                self._log(
                    logging.INFO,
                    "orchestrator.reconnection_detected",
                    current_stage=self.state.get("interview_stage"),
                )
        elif cmd_name == RuntimeCommand.ON_CONNECTION_ERROR:
            error_code, _ = cmd.get_property_int("error")
            error_msg, _ = cmd.get_property_string("msg")
            self._emit_agent_state(AgentState.ERROR)
            self._log(
                logging.ERROR,
                "orchestrator.rtc_connection_error",
                error_code=error_code,
                error_msg=error_msg or "",
            )
        elif cmd_name == RuntimeCommand.ON_CONNECTION_FAILURE:
            reason_type, _ = cmd.get_property_int("reason_type")
            channel, _ = cmd.get_property_string("channel")
            user_id, _ = cmd.get_property_string("user_id")
            self._emit_agent_state(AgentState.ERROR)
            self._log(
                logging.ERROR,
                "orchestrator.rtc_connection_failure",
                reason_type=reason_type,
                channel=channel or "",
                user_id=user_id or "",
            )
        elif cmd_name == RuntimeCommand.ON_TOKEN_EXPIRED:
            channel, _ = cmd.get_property_string("channel")
            user_id, _ = cmd.get_property_string("user_id")
            self._emit_agent_state(AgentState.ERROR)
            self._log(
                logging.ERROR,
                "orchestrator.rtc_token_expired",
                channel=channel or "",
                user_id=user_id or "",
            )

        await ten_env.return_result(CmdResult.create(StatusCode.OK, cmd))

    async def on_data(self, ten_env: AsyncTenEnv, data: Data) -> None:
        transcript, _ = data.get_property_string("text")
        is_final, _ = data.get_property_bool("is_final")
        stage = self.state.get("interview_stage", InterviewStage.OPENING)

        transcript = (transcript or "").strip()
        if not transcript:
            return
        self.last_asr_activity_ms = self._now_ms()

        asr_final_ts, _ = data.get_property_float("asr_final_ts")
        asr_sentence_start_ts, _ = data.get_property_float("asr_sentence_start_ts")
        asr_physical_stop_ts, _ = data.get_property_float("asr_physical_stop_ts")

        skip_phrases = SKIP_PHRASES
        legacy_skip_phrases = {
            "啊",
            "嗯",
            "额",
            "那个",
            "就是",
            "其实",
            "你看",
            "这个",
            "那",
            "这种",
            "那样",
            "这么说",
        }
        handshake_keywords = HANDSHAKE_KEYWORDS
        legacy_handshake_keywords = {
            "在的",
            "听到",
            "你好",
            "hello",
            "hi",
            "可以",
            "行",
            "好",
            "好的",
            "没问题",
            "对",
            "明白",
        }
        audio_issue_phrases = AUDIO_ISSUE_PHRASES
        legacy_audio_issue_phrases = {
            "听不到",
            "没声音",
            "听不清",
            "卡",
            "断断续续",
            "没有声音",
            "你那边没声",
        }

        if not is_final:
            return

        if transcript == self.last_final_transcript:
            return
        self.last_final_transcript = transcript

        clean_text = transcript.strip("銆傦紝鈥溾€濓紝锛侊紵!?, ")
        if clean_text in skip_phrases or len(clean_text) < 2:
            self._log(logging.INFO, "orchestrator.final_ignored_noise", transcript=transcript[:200])
            return
        if len(clean_text) <= 2 and stage in {InterviewStage.OPENING, InterviewStage.SELF_INTRO} and clean_text not in handshake_keywords:
            self._log(logging.INFO, "orchestrator.final_ignored_short", transcript=transcript[:200], short_stage=stage)
            return

        # Emit every accepted ASR-final sentence for transcript visibility.
        # Downstream duplicate suppression should only gate orchestration actions, not transcript capture.
        self._emit_candidate_final(transcript)

        if stage == InterviewStage.OPENING and any(phrase in transcript for phrase in audio_issue_phrases):
            self._log(logging.WARNING, "orchestrator.handshake_audio_issue", transcript=transcript[:200])
            self._cancel_pending_finalize()
            self._invalidate_active_response()
            await self._send_to_tts(ten_env, "我这边再确认一下，现在能听到吗？", is_final=False)
            await self._send_to_tts(ten_env, "", is_final=True)
            return

        if self.turn_triggered and len(transcript) > 0:
            if self.last_triggered_text and self._is_duplicate_like_transcript(transcript, self.last_triggered_text):
                if self._is_reengagement_transcript(transcript):
                    self._log(logging.INFO, "orchestrator.reengagement_allowed", transcript=transcript[:200])
                elif self._has_active_response_pipeline():
                    self._log(
                        logging.INFO,
                        "orchestrator.final_skipped_duplicate",
                        transcript=transcript[:200],
                        last_triggered_text=self.last_triggered_text[:200],
                    )
                    return
                else:
                    self._log(
                        logging.INFO,
                        "orchestrator.duplicate_like_final_allowed",
                        transcript=transcript[:200],
                    )

        self._log(logging.INFO, "orchestrator.final_buffered", transcript=transcript[:200])
        self.turn_triggered = True
        self.last_triggered_text = transcript
        self._finalize_candidate_answer(answer_text=transcript)
        self._emit_agent_state(AgentState.THINKING)
        orch_receive_ts = time.perf_counter()
        self._schedule_finalize(
            ten_env,
            transcript=transcript,
            asr_final_ts=asr_final_ts,
            asr_sentence_start_ts=asr_sentence_start_ts,
            asr_physical_stop_ts=asr_physical_stop_ts,
            orch_receive_ts=orch_receive_ts,
        )

    async def _llm_streaming_worker(
        self,
        ten_env: AsyncTenEnv,
        context: InvokeContext,
        asr_final_ts: float,
        asr_sentence_start_ts: float,
        asr_physical_stop_ts: float,
        orch_receive_ts: float,
        llm_start_ts: float,
        transcript: str,
    ) -> str:
        generation_id = self.arbiter.begin_generation(turn_id=self.arbiter.begin_turn())
        try:
            content_iter = self.llm_client.async_stream_invoke(context=context)
            emitted = False
            first_sentence_sent = False
            llm_ttfb_ts = 0.0
            llm_ttfs_ts = 0.0
            full_reply_content = []

            async def _raw_chunk_interceptor(inner_iter):
                nonlocal llm_ttfb_ts
                async for chunk in inner_iter:
                    if not llm_ttfb_ts:
                        llm_ttfb_ts = time.perf_counter()
                    yield chunk

            async for sentence in split_sentences_async(_raw_chunk_interceptor(content_iter)):
                if not self.arbiter.is_generation_active(generation_id):
                    self._log(logging.INFO, "orchestrator.generation_stale_before_emit")
                    return " ".join(full_reply_content)

                sentence = (sentence or "").strip()
                if not sentence:
                    continue
                full_reply_content.append(sentence)

                if not first_sentence_sent:
                    first_sentence_sent = True
                    llm_ttfs_ts = time.perf_counter()

                    asr_recognition_delay = (asr_final_ts - asr_sentence_start_ts) * 1000 if asr_sentence_start_ts > 0 else 0
                    vad_wait_delay = (asr_final_ts - asr_physical_stop_ts) * 1000 if asr_physical_stop_ts > 0 else 0
                    trigger_delay = (llm_start_ts - asr_physical_stop_ts) * 1000 if asr_physical_stop_ts > 0 else 0
                    orch_overhead = (orch_receive_ts - asr_final_ts) * 1000
                    llm_start_delay = (llm_start_ts - orch_receive_ts) * 1000
                    llm_ttfb_delay = (llm_ttfb_ts - llm_start_ts) * 1000 if llm_ttfb_ts > 0 else 0
                    llm_ttfs_delay = (llm_ttfs_ts - llm_ttfb_ts) * 1000 if llm_ttfb_ts > 0 else 0
                    total_p95_offset = (llm_ttfs_ts - asr_final_ts) * 1000

                    self._log(
                        logging.INFO,
                        "orchestrator.latency_stats",
                        asr_recognition_delay_ms=round(asr_recognition_delay, 2),
                        vad_wait_delay_ms=round(vad_wait_delay, 2),
                        trigger_delay_ms=round(trigger_delay, 2),
                        orchestrator_overhead_ms=round(orch_overhead, 2),
                        llm_prep_delay_ms=round(llm_start_delay, 2),
                        llm_ttfb_delay_ms=round(llm_ttfb_delay, 2),
                        llm_ttfs_delay_ms=round(llm_ttfs_delay, 2),
                        total_asr_to_tts_ms=round(total_p95_offset, 2),
                    )

                emitted = True

                self._log(logging.DEBUG, "orchestrator.llm_raw_sentence", sentence=sentence[:200])
                clean_sentence = self._sanitize_tts_text(sentence)
                if not clean_sentence:
                    self._log(logging.DEBUG, "orchestrator.llm_sentence_dropped")
                    continue
                if not self._is_tts_speakable(clean_sentence):
                    self._log(logging.DEBUG, "orchestrator.llm_sentence_blocked", sentence=clean_sentence[:200])
                    continue
                self._log(logging.DEBUG, "orchestrator.llm_clean_sentence", sentence=clean_sentence[:200])

                while not self.arbiter.can_commit_tts(
                    generation_id=generation_id,
                    now_ms=self._now_ms(),
                ):
                    if not self.arbiter.is_generation_active(generation_id):
                        self._log(logging.INFO, "orchestrator.generation_cancelled_during_commit_wait")
                        return " ".join(full_reply_content)
                    await asyncio.sleep(0.05)

                await self._send_to_tts(
                    ten_env,
                    clean_sentence,
                    is_final=False,
                    asr_physical_stop_ts=asr_physical_stop_ts,
                    trace_id=context.trace_id,
                    generation_id=generation_id,
                )

            if not emitted:
                error_msg = LLM_EMPTY_FALLBACK_REPLY
                await self._send_to_tts(ten_env, error_msg, is_final=False, generation_id=generation_id)
                full_reply_content.append(error_msg)

            if self.arbiter.is_generation_active(generation_id):
                await self._send_to_tts(ten_env, "", is_final=True, generation_id=generation_id)
            return " ".join(full_reply_content)
        except asyncio.CancelledError:
            self._log(logging.INFO, "orchestrator.llm_stream_cancelled")
            return ""
        except Exception as exc:
            logger.exception(
                json.dumps(
                    {
                        "event": "orchestrator.llm_stream_failed",
                        "session_id": self.session_context.session_id or "",
                        "trace_id": context.trace_id,
                        "error": str(exc),
                    },
                    ensure_ascii=False,
                )
            )
            return ""

    async def _send_to_tts(
        self,
        ten_env: AsyncTenEnv,
        text: str,
        is_final: bool = True,
        asr_physical_stop_ts: float = 0.0,
        trace_id: str = "",
        generation_id: str | None = None,
    ) -> None:
        if text and generation_id:
            while not self.arbiter.can_commit_tts(
                generation_id=generation_id,
                now_ms=self._now_ms(),
            ):
                if not self.arbiter.is_generation_active(generation_id):
                    return
                await asyncio.sleep(0.05)

        if text and self.is_user_speaking:
            return

        if text:
            self._emit_question_update(text=text, trace_id=trace_id)
            self._emit_agent_state(AgentState.SPEAKING)

        tts_data = Data.create(RuntimeDataChannel.TEXT_DATA)
        tts_data.set_property_string("text", text)
        tts_data.set_property_bool("is_final", is_final)
        if asr_physical_stop_ts > 0:
            tts_data.set_property_float("asr_physical_stop_ts", asr_physical_stop_ts)
            tts_data.set_property_string("trace_id", trace_id)
        if text and generation_id:
            self.playback_sequence += 1
            playback_id = f"pb-{self.playback_sequence}"
            if not self.arbiter.register_playback(generation_id=generation_id, playback_id=playback_id):
                return
            tts_data.set_property_string("playback_id", playback_id)
        elif is_final:
            self._emit_question_final(trace_id=trace_id)
            self.arbiter.clear_playback()
        await ten_env.send_data(tts_data)

    async def _listen_for_events(self) -> None:
        return
        """监听 Event Bus 上的外部事件，如手动强制结算。"""
        try:
            async for event in DEFAULT_INTERVIEW_EVENT_BUS.subscribe():
                if not isinstance(event, dict):
                    continue
                
                event_type = event.get("event_type")
                session_id = event.get("session_id")
                
                # 仅处理匹配当前会话的事件
                if session_id != self.session_id:
                    continue
                
                if event_type == InterviewEventType.CANDIDATE_FORCE_FINALIZE:
                    self._log(logging.INFO, "orchestrator.force_finalize_received", event=event)
                    # 触发手动交互处理，跳过 VAD 等待
                    payload = event.get("payload") or {}
                    transcript = payload.get("text") or self.last_final_transcript
                    
                    if transcript:
                        # 使用 _create_task 确保并发执行
                        self._create_task(
                            self._handle_interaction(
                                ten_env=self._ten_env,
                                transcript=transcript,
                                asr_final_ts=time.perf_counter(),
                                asr_sentence_start_ts=0,
                                asr_physical_stop_ts=0,
                                orch_receive_ts=time.perf_counter(),
                            ),
                            name="manual-force-finalize"
                        )
        except asyncio.CancelledError:
            self._log(logging.INFO, "orchestrator.event_bus_listener_cancelled")
        except Exception as exc:
            self._log(logging.ERROR, "orchestrator.event_bus_listener_failed", error=str(exc))

    async def on_stop(self, ten_env: AsyncTenEnv) -> None:
        self._cancel_pending_finalize()
        self._invalidate_active_response()
        
        # 取消并等待所有后台任务
        if self._bg_tasks:
            self._log(logging.INFO, "orchestrator.stopping_tasks", count=len(self._bg_tasks))
            for task in list(self._bg_tasks):
                if not task.done():
                    task.cancel()
            
            # 使用 wait 确保所有任务都已清理完成，防止 rwlock 冲突
            if self._bg_tasks:
                import asyncio
                # We are already in an async method, so we can await.
                # However, on_stop might be called from a context where we want to be brief.
                # But to avoid rwlock issues, we must await here.
                done, pending = await asyncio.wait(list(self._bg_tasks), timeout=2.0)
                for t in pending:
                    # If still not done, we just log it and move on (not ideal but avoids hanging)
                    pass
            self._bg_tasks.clear()

        if self.event_bridge is not None:
            await self.event_bridge.stop()
        with contextlib.suppress(Exception):
            await ten_env.send_cmd(Cmd.create(RuntimeCommand.INTERRUPT))
        self._log(logging.INFO, "orchestrator.stopped")


    def _emit_agent_state(self, state: str) -> None:
        if self.event_bridge is None:
            return
        self.event_bridge.emit(
            event_type=InterviewEventType.AGENT_STATE,
            critical=False,
            payload={"state": str(state or "").strip() or AgentState.IDLE},
        )

    def _emit_candidate_final(self, transcript: str) -> None:
        text = str(transcript or "").strip()
        if not text or self.event_bridge is None:
            return
        question_ctx = self._get_active_question_context()
        stage = str((self.state or {}).get("interview_stage") or "")
        phase = self._resolve_phase_from_stage(stage)
        trace_id = str(self.trace_id or "").strip()
        question_seq = question_ctx.get("question_seq")
        question_id = str(question_ctx.get("question_id") or "")
        topic_id = str(self.active_topic_id or "").strip()
        parent_topic_id = str(self.active_parent_topic_id or "").strip()
        is_followup = bool(self.active_is_followup)
        if phase == "opening":
            topic_id = self._ensure_opening_topic_id()
            parent_topic_id = ""
            is_followup = False
            question_seq = None
        elif not topic_id:
            topic_id = f"formal-{uuid.uuid4().hex[:12]}"
            self.active_topic_id = topic_id
            self.active_phase = "formal"
            self.active_question_seq = int(question_seq) if isinstance(question_seq, int) else None
            self.active_question_id = question_id
        self.event_bridge.emit(
            event_type=InterviewEventType.CANDIDATE_FINAL,
            critical=True,
            payload={
                "text": text,
                "trace_id": trace_id,
                "stage": stage,
                "phase": phase,
                "question_id": question_id,
                "question_seq": question_seq,
                "topic_id": topic_id,
                "parent_topic_id": parent_topic_id,
                "is_followup": is_followup,
                "topic_name": str(question_ctx.get("topic_name") or ""),
            },
        )

    def _normalize_question_chunk(self, text: str) -> str:
        clean_text = str(text or "").strip()
        if not clean_text:
            return ""
        if not self.current_question_buffer:
            return clean_text
        if self.current_question_buffer.endswith(("。", "，", "、", ".", "?", "!", "？", "！")):
            return clean_text
        if clean_text.startswith(("，", "。", "、", ",", ".", "?", "!", "？", "！", "：", ":")):
            return clean_text
        return f" {clean_text}"

    def _emit_question_update(self, *, text: str, trace_id: str = "") -> None:
        clean_text = str(text or "").strip()
        if not clean_text or self.event_bridge is None:
            return
        trace = str(trace_id or "").strip() or "default"
        question_ctx = self._get_active_question_context()
        stage = str((self.state or {}).get("interview_stage") or "")
        phase = self._resolve_phase_from_stage(stage)
        question_seq = question_ctx.get("question_seq")
        topic_id = str(self.active_topic_id or "").strip()
        parent_topic_id = str(self.active_parent_topic_id or "").strip()
        is_followup = bool(self.active_is_followup)
        if phase == "opening":
            topic_id = self._ensure_opening_topic_id()
            parent_topic_id = ""
            is_followup = False
            question_seq = None
        if trace != self.current_question_trace_id:
            self.current_question_trace_id = trace
            self.current_question_buffer = ""
        self.current_question_buffer = f"{self.current_question_buffer}{self._normalize_question_chunk(clean_text)}".strip()
        if not self.current_question_buffer:
            return
        self.event_bridge.emit(
            event_type=InterviewEventType.QUESTION_UPDATE,
            critical=True,
            payload={
                "text": self.current_question_buffer,
                "spoken_text": self.current_question_buffer,
                "trace_id": trace,
                "stage": stage,
                "phase": phase,
                "question_id": str(question_ctx.get("question_id") or ""),
                "question_seq": question_seq,
                "topic_id": topic_id,
                "parent_topic_id": parent_topic_id,
                "is_followup": is_followup,
                "topic_name": str(question_ctx.get("topic_name") or ""),
            },
        )

    def _emit_question_final(self, *, trace_id: str = "") -> None:
        if self.event_bridge is None or not self.current_question_buffer:
            return
        trace = str(trace_id or "").strip() or self.current_question_trace_id or "default"
        stage = str((self.state or {}).get("interview_stage") or "")
        phase = self._resolve_phase_from_stage(stage)
        question_ctx = self._get_active_question_context()
        question_id = str(question_ctx.get("question_id") or "").strip()
        question_seq = question_ctx.get("question_seq")
        parent_topic_id = ""
        topic_id = ""
        is_followup = False
        if phase == "opening":
            topic_id = self._ensure_opening_topic_id()
            is_followup = bool(self.active_phase == "opening" and bool(self.active_topic_id))
            if is_followup:
                parent_topic_id = topic_id
            question_seq = None
            self.active_topic_id = topic_id
            self.active_parent_topic_id = parent_topic_id
            self.active_is_followup = is_followup
            self.active_phase = "opening"
            self.active_question_seq = None
            self.active_question_id = question_id
        else:
            normalized_seq = int(question_seq) if isinstance(question_seq, int) else None
            same_topic = bool(
                self.active_phase == "formal"
                and self.active_topic_id
                and (
                    (normalized_seq is not None and self.active_question_seq == normalized_seq)
                    or (question_id and self.active_question_id and self.active_question_id == question_id)
                )
            )
            if same_topic:
                topic_id = self.active_topic_id
                is_followup = True
                parent_topic_id = topic_id
            else:
                topic_id = f"formal-{uuid.uuid4().hex[:12]}"
                is_followup = False
                parent_topic_id = ""
            self.active_topic_id = topic_id
            self.active_parent_topic_id = parent_topic_id
            self.active_is_followup = is_followup
            self.active_phase = "formal"
            self.active_question_seq = normalized_seq
            self.active_question_id = question_id
        self._start_pending_question(
            question_text=self.current_question_buffer,
            stage=stage,
            trace_id=trace,
            question_id=question_id,
            topic_name=str(question_ctx.get("topic_name") or ""),
        )
        self.event_bridge.emit(
            event_type=InterviewEventType.QUESTION_FINAL,
            critical=True,
            payload={
                "text": self.current_question_buffer,
                "spoken_text": self.current_question_buffer,
                "trace_id": trace,
                "stage": stage,
                "phase": phase,
                "question_id": question_id,
                "question_seq": question_seq,
                "topic_id": topic_id,
                "parent_topic_id": parent_topic_id,
                "is_followup": is_followup,
                "topic_name": str(question_ctx.get("topic_name") or ""),
            },
        )
        self.current_question_trace_id = ""
        self.current_question_buffer = ""
