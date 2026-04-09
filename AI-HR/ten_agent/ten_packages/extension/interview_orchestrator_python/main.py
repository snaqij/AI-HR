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
project_root = os.path.abspath(os.path.join(current_dir, "../../../../"))
if project_root not in sys.path:
    sys.path.append(project_root)

from ai_hr.core.config import get_settings
from ai_hr.services.interview_runtime.question_flow import InterviewQuestionFlowEngine
from ai_hr.services.interview_runtime.realtime_policy import get_stage_realtime_policy
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
        critical_queue_size: int = 128,
        volatile_queue_size: int = 512,
        request_timeout_s: float = 0.3,
    ):
        self.session_id = str(session_id or "").strip()
        self.base_url = str(base_url or "").rstrip("/")
        self.api_key = str(api_key or "").strip()
        self.flush_interval_ms = max(20, int(flush_interval_ms or 80))
        self.batch_max_events = max(1, int(batch_max_events or 20))
        self.request_timeout_s = max(0.1, float(request_timeout_s or 0.3))
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
            else:
                self._drop_counters["volatile"] += 1

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
                    self._circuit_open_until = time.monotonic() + 5.0
        except asyncio.CancelledError:
            return

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
        self.task_key = "interview_followup"
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
        self.speculative_task = None
        self.pending_finalize_task = None
        self.pending_finalize_token = 0
        self.pending_payload = None
        self.arbiter = ConversationArbiter()
        self.turn_completion_judge = TurnCompletionJudge()
        self.stage_progress_engine = StageProgressEngine()
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
        self.last_filler = ""
        self.system_prompt = INTERVIEW_SYSTEM_PROMPT
        self.event_bridge: RealtimeEventBridge | None = None
        self.current_question_trace_id = ""
        self.current_question_buffer = ""
        self.session_context = SessionContext(session_id="")
        self.prompt_builder = InterviewPromptBuilder()

    def _build_company_intro(self) -> str:
        return build_interview_company_intro(self.company_info)

    def _set_stage(self, stage_code: str, *, reason: str = "") -> None:
        self.state = self.flow_engine.transition_stage(
            state=self.state,
            stage_code=stage_code,
            transition_reason=reason,
        )

    def _now_ms(self) -> int:
        return int(time.perf_counter() * 1000)

    def _get_realtime_policy(self, stage_code: str | None = None):
        active_stage = stage_code or (self.state or {}).get("interview_stage", "S1")
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
    ) -> None:
        self.session_context.append_turn(
            turn_id=self._new_turn_id(),
            role=role,
            text=text,
            now_ms=self._now_ms(),
            stage=stage,
            trace_id=trace_id,
            question_id=question_id,
        )

    def _start_pending_question(
        self,
        *,
        question_text: str,
        stage: str,
        trace_id: str = "",
        question_id: str = "",
    ) -> None:
        self.session_context.start_pending_question(
            turn_id=self._new_turn_id(),
            question_text=question_text,
            now_ms=self._now_ms(),
            stage=stage,
            trace_id=trace_id,
            question_id=question_id,
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
        stage = self.state.get("interview_stage", "S1")
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
        token = self.pending_finalize_token
        self.pending_finalize_task = asyncio.create_task(
            self._finalize_after_delay(ten_env, delay_ms=delay_ms, token=token)
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
                    stage = (self.state or {}).get("interview_stage", "S1")
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
                stage = (self.state or {}).get("interview_stage", "S1")
                policy = self._get_realtime_policy(stage)
                speaking_elapsed_ms = int(payload.get("turn_accumulated_ms") or 0)
                silence_ms = 0
                asr_physical_stop_ts = float(payload.get("asr_physical_stop_ts") or 0.0)
                if asr_physical_stop_ts > 0:
                    silence_ms = max(0, now_ms - int(asr_physical_stop_ts * 1000))
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
        self._log(logging.INFO, "orchestrator.init_started")
        settings = get_settings()
        router = ModelRouter(settings=settings)
        guardrail = GuardrailService()

        self.llm_client = LLMClient(router=router, guardrail_service=guardrail)
        self.flow_engine = InterviewQuestionFlowEngine()
        self.question_pack = {"questions": []}

        config_json, _ = await ten_env.get_property_to_json("")
        config = json.loads(config_json) if config_json else {}

        self.task_key = config.get("task_key", "interview_followup")
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
        self.session_context = SessionContext(session_id=self.session_id, max_turns=8)
        
        # 捕获简历和职位要求上下文
        self.resume_summary = config.get("resume_summary", "一名资深后端开发工程师")
        self.job_requirements = config.get("job_requirements", "精通分布式系统和高可用架构")
        
        self.trace_id = "ten_trace_" + uuid.uuid4().hex[:8]

        # 尝试加载预生成的面试题库
        data_dir = os.path.join(project_root, "data")
        q_file = os.path.join(data_dir, "interview_questions.json")
        if os.path.exists(q_file):
             try:
                 with open(q_file, "r", encoding="utf-8") as f:
                     self.question_pack["questions"] = json.load(f)
                 self._log(
                     logging.INFO,
                     "orchestrator.prebuilt_questions_loaded",
                     question_count=len(self.question_pack["questions"]),
                 )
             except Exception as e:
                 logger.exception(
                     json.dumps(
                         {
                             "event": "orchestrator.prebuilt_questions_load_failed",
                             "error": str(e),
                         },
                         ensure_ascii=False,
                     )
                 )

        if not self.question_pack["questions"]:
            self.question_pack["questions"] = [
                {"stage": "P2", "question": "你可以先做一个 1 到 2 分钟的自我介绍。"},
                {"stage": "P3", "question": "你最近参与的核心项目里，最有挑战的技术问题是什么？"},
                {"stage": "P4", "question": "如果系统访问量突然增长 10 倍，你认为最先出现瓶颈的会是哪一层？"},
            ]

        self.state = self.flow_engine.init_state(question_pack=self.question_pack)
        # 优先从本地文件加载完整简历内容并提取姓名
        resume_file_path = os.path.join(project_root, "data", "测试文本简历.txt")
        if os.path.exists(resume_file_path):
            try:
                with open(resume_file_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    self.resume_summary = content
                    # 提取第一行作为姓名，并取后两位
                    first_line = content.split('\n')[0].strip()
                    if first_line and len(first_line) >= 2:
                        self.candidate_name = first_line[-2:]
                self._log(logging.INFO, "orchestrator.candidate_name_extracted", candidate_name=self.candidate_name)
            except Exception as e:
                logger.exception(
                    json.dumps(
                        {
                            "event": "orchestrator.resume_load_failed",
                            "error": str(e),
                        },
                        ensure_ascii=False,
                    )
                )

        # 加载公司信息
        company_info_path = os.path.join(project_root, "data", "company_info.txt")
        if os.path.exists(company_info_path):
             try:
                 with open(company_info_path, "r", encoding="utf-8") as f:
                     self.company_info = f.read().strip()
                 self._log(logging.INFO, "orchestrator.company_info_loaded", company_info_chars=len(self.company_info))
             except Exception as e:
                 logger.exception(
                     json.dumps(
                         {
                             "event": "orchestrator.company_info_load_failed",
                             "error": str(e),
                         },
                         ensure_ascii=False,
                     )
                 )

        # 预构建 system prompt，以便利用 LLM caching 的固定前缀
        self.system_prompt_built = (
            f"{self.system_prompt}\n\n"
            f"### 面试背景固化信息 (Cache Target) ###\n"
            f"候选人简历内容：\n{self.resume_summary}\n\n"
            f"岗位要求：\n{self.job_requirements}\n"
        )

        self._log(
            logging.INFO,
            "orchestrator.init_completed",
            task_key=self.task_key,
            trace_id=self.trace_id,
        )

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
            # 获取当前阶段和原始索引
            stage = self.state.get("interview_stage", "S1")
            original_index = self.state.get("active_question_index", 0)
            
            # 获取当前题目
            current_q = self.flow_engine.current_question(
                state=self.state,
                question_pack=self.question_pack,
            ) or {}

            # 同步题目中的阶段标签，但在开场环节（S1-S3）不能被技术题覆盖
            if current_q and current_q.get("stage"):
                q_stage = current_q.get("stage")
                # 只有系统已经进入 S4 及以后，才同步题库 stage
                if stage not in ["S1", "S2", "S3", "S7", "S8"]:
                    stage = q_stage
                    self._set_stage(stage, reason="sync_with_question_pack")

            evaluation = self.flow_engine.evaluate_answer(
                transcript=transcript,
                confidence=0.95,
            )
            stage_progress_snapshot = None
            if stage in ["S2", "S3"]:
                self.state, stage_progress_snapshot = self.stage_progress_engine.update(
                    state=self.state,
                    stage=stage,
                    transcript=transcript,
                )
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
                "orchestrator.interaction_triggered",
                interaction_stage=stage,
                active_question_index=self.state.get("active_question_index"),
                original_index=original_index,
            )

            # 状态机流转与固定桥接逻辑（S1-S3, S7-S8）
            
            # S1（问候握手） -> S2（正式开场与自我介绍提示）
            if stage == "S1":
                 if not self.state["context_flags"]["connectivity_confirmed"]:
                      # 这里已经通过上面的噪声过滤，说明是正常的有效输入
                      self.state["context_flags"]["connectivity_confirmed"] = True
                      self._set_stage("S2", reason="connectivity_confirmed")
                      
                      formal_welcome = "好的，那我们正式开始。你可以先做一个 1 到 2 分钟的自我介绍。"
                      self._log(logging.INFO, "orchestrator.handshake_confirmed", transcript=transcript[:200])
                      await self._send_to_tts(ten_env, formal_welcome, is_final=False)
                      await self._send_to_tts(ten_env, "", is_final=True)
                      return
                 
                 self._set_stage("S2", reason="opening_completed")

            # S2/S3 的阶段推进依赖 LLM 的 [SATISFIED] 或信号收集结果，避免噪声误触发

            # S7 公司介绍与候选人追问环节
            if stage == "S7":
                 if not self.state["context_flags"]["company_info_shared"]:
                      self.state["context_flags"]["company_info_shared"] = True
                      reply_msg = self._build_company_intro()
                      await self._send_to_tts(ten_env, reply_msg, is_final=False)
                      await self._send_to_tts(ten_env, "", is_final=True)
                      return
                 
                 # 如果候选人已经没有更多问题，直接进入结束阶段。
                 if any(p in transcript for p in ["没问题", "没有了", "大概了解", "谢谢", "再见"]):
                      self._set_stage("S8", reason="candidate_has_no_more_questions")
                      # 下面会进入结束逻辑

            if stage == "S8":
                 if not self.state["context_flags"]["closing_started"]:
                      self.state["context_flags"]["closing_started"] = True
                      closing_msg = "那今天先聊到这里，后续安排 HR 会再和你同步。回头见。"
                      await self._send_to_tts(ten_env, closing_msg, is_final=False)
                      await self._send_to_tts(ten_env, "", is_final=True)
                 return
            # --- LLM business flow (S2-S6) ---
            next_q = self.flow_engine.current_question(
                state={"active_question_index": self.state["active_question_index"] + 1},
                question_pack=self.question_pack,
            )
            next_q_text = next_q.get("question", "请继续围绕岗位核心能力深入作答。") if next_q else "请继续围绕岗位核心能力深入作答。"

            is_last_followup = False
            success_signals = ""
            if stage not in ["S1", "S7", "S8"]:
                followup_limit = self.flow_engine.get_followup_limit(
                    stage_code=stage,
                    question=current_q,
                    default=self.max_followup,
                )
                is_last_followup = self.state["followup_count_current"] >= followup_limit - 1
                raw_success_signals = current_q.get("success_signals") or current_q.get("expected_signal") or []
                if isinstance(raw_success_signals, str):
                    success_signals = raw_success_signals
                else:
                    success_signals = ", ".join(str(item) for item in raw_success_signals)

            build_result = self.prompt_builder.build(
                PromptBuildInput(
                    stage=stage,
                    candidate_name=self.candidate_name,
                    transcript=transcript,
                    current_question=str(current_q.get("question") or ""),
                    next_question=next_q_text,
                    success_signals=success_signals if "success_signals" in locals() else "",
                    is_last_followup=is_last_followup if "is_last_followup" in locals() else False,
                    company_info=self.company_info,
                    stage_goal=str(self.state.get("stage_goal") or ""),
                    missing_evidence=self.state.get("missing_evidence"),
                    difficulty_level=str(self.state.get("difficulty_level") or "normal"),
                    transition_reason=str(self.state.get("transition_reason") or ""),
                    system_prompt_prefix=self.system_prompt_built,
                    session_context=self.session_context,
                )
            )

            context = InvokeContext(
                task_key=self.task_key,
                trace_id=self.trace_id,
                system_prompt=build_result.system_prompt,
                prompt=build_result.prompt,
                entity_type="candidate",
                entity_id="test_user_01",
            )

            if get_settings().llm_context_debug_enabled:
                self._log(
                    logging.DEBUG,
                    "orchestrator.llm_context",
                    current_transcript=transcript[:400],
                    debug_context=build_result.debug_context_payload,
                )

            self._log(
                logging.INFO,
                "orchestrator.llm_worker_triggered",
                active_question_index=self.state.get("active_question_index"),
                pending_question=build_result.pending_question,
            )
            
            # 在技术深挖环节注入简短 filler，降低停顿感
            if stage in ["S4", "S5", "S6"]:
                import random
                available_fillers = [f for f in self.EXPERT_FILLERS if f != self.last_filler]
                filler = random.choice(available_fillers)
                self.last_filler = filler
                self._log(logging.INFO, "orchestrator.filler_sent", filler_stage=stage, filler=filler)
                await self._send_to_tts(ten_env, filler, is_final=False)
            
            llm_start_ts = time.perf_counter()
            self.llm_task = asyncio.create_task(self._llm_streaming_worker(ten_env, context, asr_final_ts, asr_sentence_start_ts, asr_physical_stop_ts, orch_receive_ts, llm_start_ts, transcript))
            full_reply_text = await self.llm_task

            # 安全防御：检查 LLM 返回值是否有效
            if full_reply_text is None:
                self._log(logging.WARNING, "orchestrator.llm_task_returned_none")
                return

            # 状态推进与后续追问逻辑
            was_satisfied = "[SATISFIED]" in full_reply_text

            was_fallback = "[FALLBACK]" in full_reply_text

            stage_signals_completed = bool(stage_progress_snapshot and stage_progress_snapshot.completed)

            

            if was_fallback:
                 self._log(logging.WARNING, "orchestrator.llm_triggered_fallback", fallback_stage=stage)
                 was_satisfied = False

                 evaluation["need_followup"] = True


            self.state = self.flow_engine.apply_turn_result(

                state=self.state,

                evaluation=evaluation,

                current_q_max_followups=current_q.get("max_followups", 2),

                force_complete=was_satisfied

            )


            if was_satisfied or stage_signals_completed:

                if stage == "S2":

                    self._set_stage(

                        "S3",

                        reason="self_intro_signals_completed" if stage_signals_completed else "self_intro_satisfied",

                    )

                elif stage == "S3":

                    self._set_stage(

                        "S4",

                        reason="stack_signals_completed" if stage_signals_completed else "stack_verification_satisfied",

                    )

            elif stage in ["S2", "S3"] and stage_progress_snapshot is not None:

                self.state["missing_evidence"] = list(stage_progress_snapshot.missing_signals)

                self.state["transition_reason"] = stage_progress_snapshot.reason


            refreshed_q = self.flow_engine.current_question(state=self.state, question_pack=self.question_pack)
            self.state = self.flow_engine.sync_stage_metadata(
                state=self.state,
                stage_code=self.state.get("interview_stage", "S1"),
                question=refreshed_q,
                transition_reason=str(self.state.get("transition_reason") or ""),
            )
            if was_satisfied or stage_signals_completed or self.state["followup_count_current"] == 0:
                self._log(
                    logging.INFO,
                    "orchestrator.topic_terminated",
                    was_satisfied=was_satisfied,
                    stage_signals_completed=stage_signals_completed,
                )
                
                next_q = self.flow_engine.current_question(state=self.state, question_pack=self.question_pack)
                next_stage = self.state.get("interview_stage")

                # 如果还在技术深挖环节（S4/S5/S6），这里预留平滑过渡逻辑。
                if next_q and next_stage in ["S4", "S5", "S6"]:
                    # 为了保持过渡自然，交给下一轮 LLM 自动处理，这里不做 fast path。
                    pass

            # 题库消耗完毕后切换到公司介绍与追问阶段
            if self.state["active_question_index"] >= len(self.question_pack["questions"]) and stage not in ["S7", "S8"]:
                 self._set_stage("S7", reason="question_pack_exhausted")
        except asyncio.CancelledError:
            self._log(logging.INFO, "orchestrator.interaction_cancelled")
        except Exception as exc:
            logger.exception(
                json.dumps(
                    {
                        "event": "orchestrator.interaction_failed",
                        "session_id": self.session_context.session_id or "",
                        "trace_id": self.trace_id or "",
                        "stage": (self.state or {}).get("interview_stage", ""),
                        "error": str(exc),
                    },
                    ensure_ascii=False,
                )
            )

    async def on_start(self, ten_env: AsyncTenEnv) -> None:
        self._log(logging.INFO, "orchestrator.started")

    async def on_cmd(self, ten_env: AsyncTenEnv, cmd: Cmd) -> None:
        cmd_name = cmd.get_name()

        if cmd_name == "start_of_sentence":
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
            self._emit_agent_state("listening")
            self._log(logging.INFO, "orchestrator.user_speaking_started")
            await ten_env.send_cmd(Cmd.create("interrupt"))

        elif cmd_name == "end_of_sentence":
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
            self._emit_agent_state("thinking")
            self._log(logging.INFO, "orchestrator.user_speaking_stopped")

        elif cmd_name == "on_connected":
            if self.state.get("interview_stage", "S1") == "S1" and not self.state["context_flags"].get("greeted", False):
                self._log(logging.INFO, "orchestrator.handshake_started")
                handshake_msg = f"{self.candidate_name}，你好。喂，听得到我说话吗？"
                await self._send_to_tts(ten_env, handshake_msg, is_final=False)
                await self._send_to_tts(ten_env, "", is_final=True)
                self._set_stage("S1", reason="connectivity_handshake_sent")
                self.state["context_flags"]["greeted"] = True
            else:
                self._log(
                    logging.INFO,
                    "orchestrator.reconnection_detected",
                    current_stage=self.state.get("interview_stage"),
                )

        await ten_env.return_result(CmdResult.create(StatusCode.OK, cmd))

    async def on_data(self, ten_env: AsyncTenEnv, data: Data) -> None:
        transcript, _ = data.get_property_string("text")
        is_final, _ = data.get_property_bool("is_final")
        stage = self.state.get("interview_stage", "S1")

        transcript = (transcript or "").strip()
        if not transcript:
            return
        self.last_asr_activity_ms = self._now_ms()

        asr_final_ts, _ = data.get_property_float("asr_final_ts")
        asr_sentence_start_ts, _ = data.get_property_float("asr_sentence_start_ts")
        asr_physical_stop_ts, _ = data.get_property_float("asr_physical_stop_ts")

        skip_phrases = {
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
        handshake_keywords = {
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
        audio_issue_phrases = {
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
        if len(clean_text) <= 2 and stage in {"S1", "S2"} and clean_text not in handshake_keywords:
            self._log(logging.INFO, "orchestrator.final_ignored_short", transcript=transcript[:200], short_stage=stage)
            return

        if stage == "S1" and any(phrase in transcript for phrase in audio_issue_phrases):
            self._log(logging.WARNING, "orchestrator.handshake_audio_issue", transcript=transcript[:200])
            self._cancel_pending_finalize()
            self._invalidate_active_response()
            await self._send_to_tts(ten_env, "我这边再确认一下，现在能听到吗？", is_final=False)
            await self._send_to_tts(ten_env, "", is_final=True)
            return

        if self.turn_triggered and len(transcript) > 0:
            if self.last_triggered_text and (
                self.last_triggered_text in transcript or transcript[:5] == self.last_triggered_text[:5]
            ):
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
        self._emit_candidate_final(transcript)
        self._emit_agent_state("thinking")
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
                error_msg = "收到，我们继续下一题。"
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
            self._emit_agent_state("speaking")

        tts_data = Data.create("text_data")
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

    async def on_stop(self, ten_env: AsyncTenEnv) -> None:
        self._cancel_pending_finalize()
        self._invalidate_active_response()
        if self.event_bridge is not None:
            await self.event_bridge.stop()
        with contextlib.suppress(Exception):
            await ten_env.send_cmd(Cmd.create("interrupt"))
        self._log(logging.INFO, "orchestrator.stopped")

    def _emit_agent_state(self, state: str) -> None:
        if self.event_bridge is None:
            return
        self.event_bridge.emit(
            event_type="agent.state",
            critical=False,
            payload={"state": str(state or "").strip() or "idle"},
        )

    def _emit_candidate_final(self, transcript: str) -> None:
        text = str(transcript or "").strip()
        if not text or self.event_bridge is None:
            return
        self.event_bridge.emit(
            event_type="candidate.final",
            critical=True,
            payload={"text": text},
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
        if trace != self.current_question_trace_id:
            self.current_question_trace_id = trace
            self.current_question_buffer = ""
        self.current_question_buffer = f"{self.current_question_buffer}{self._normalize_question_chunk(clean_text)}".strip()
        if not self.current_question_buffer:
            return
        self.event_bridge.emit(
            event_type="question.update",
            critical=True,
            payload={
                "text": self.current_question_buffer,
                "spoken_text": self.current_question_buffer,
                "trace_id": trace,
            },
        )

    def _emit_question_final(self, *, trace_id: str = "") -> None:
        if self.event_bridge is None or not self.current_question_buffer:
            return
        trace = str(trace_id or "").strip() or self.current_question_trace_id or "default"
        stage = str((self.state or {}).get("interview_stage") or "")
        self._start_pending_question(
            question_text=self.current_question_buffer,
            stage=stage,
            trace_id=trace,
        )
        self.event_bridge.emit(
            event_type="question.final",
            critical=True,
            payload={
                "text": self.current_question_buffer,
                "spoken_text": self.current_question_buffer,
                "trace_id": trace,
            },
        )
        self.current_question_trace_id = ""
        self.current_question_buffer = ""
