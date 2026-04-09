import asyncio
import contextlib
import json
import os
import re
import time
import sys
import uuid

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
    build_interview_stage_instruction,
)
from ai_hr.services.llm.router import ModelRouter
from ai_hr.services.orchestrator.conversation_arbiter import ConversationArbiter
from ai_hr.services.orchestrator.streaming_utils import split_sentences, split_sentences_async
from ai_hr.services.orchestrator.turn_completion import TurnCompletionJudge


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
        self.history = []  # 存储最近 2 轮对话历史
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
        self.turn_triggered = False  # 新增：回合锁定标志
        self.last_triggered_text = "" # 新增：记录本回合触发时的文本
        
        self.candidate_name = "候选人"
        self.company_info = ""
        self.BRIDGES = [
            "明白了。那咱们聊聊",
            "好的。关于这块，我想听听你对...的看法。比如",
            "原来如此。那咱们针对你的项目场景深入一下，谈谈",
            "理解了。那咱们进入下一个环节，关于"
        ]
        self.EXPERT_BRIDGES = [
            "简历背景我大概了解了。保持高效，咱们直接进入技术交流，",
            "明白。那咱们深挖一下你的项目底层，",
            "好的。咱们先从系统实战演练开始聊起，",
            "理解了。我想针对你提到的核心模块问一下，"
        ]
        self.EXPERT_FILLERS = [
            "好的。",
            "OK。",
            "明白了。",
            "懂你的意思了。",
            "嗯，听懂了。",
            "了解。",
            "关于这一点，",
            "原来是这样。"
        ]
        self.last_filler = ""
        self.system_prompt = INTERVIEW_SYSTEM_PROMPT

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
            "你在吗",
            "我们继续面试",
            "继续面试",
            "你咋不说话",
            "怎么不说话",
            "再给我",
            "hello hello",
            "hello",
            "喂",
        )
        return any(marker in text for marker in reengagement_markers)

    def _sanitize_tts_text(self, text: str) -> str:
        cleaned = str(text or "").strip()
        if not cleaned:
            return ""

        # Remove common internal-control wrappers before any TTS playback.
        cleaned = re.sub(r"（[^）]*）", "", cleaned)
        cleaned = re.sub(r"\([^)]*\)", "", cleaned)
        cleaned = re.sub(r"【[^】]*】", "", cleaned)
        cleaned = re.sub(r"\[[^\]]*\]", "", cleaned)

        # Remove common leaked meta prefixes if a sentence still contains them after bracket cleanup.
        meta_prefixes = (
            "听起来",
            "需要引导",
            "需要继续追问",
            "候选人",
            "说明他",
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
                sentence_start = max(cleaned.find("你"), cleaned.find("那"), cleaned.find("先"), cleaned.find("我"))
                if sentence_start > idx:
                    cleaned = cleaned[sentence_start:]
                else:
                    return ""

        cleaned = re.sub(r"^[）)\]】\s，。,；;:：]+", "", cleaned)
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
        if candidate[0] in "）)]】":
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
            print(
                f"[orchestrator] merged pending final transcript chars={len(merged_transcript)} "
                f"turn_accumulated_ms={self.current_turn_accumulated_ms}",
                flush=True,
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
                        print(
                            f"[orchestrator] stale speaking state detected; clearing user-speaking lock "
                            f"idle_since_asr_ms={idle_since_asr_ms}",
                            flush=True,
                        )
                        self.is_user_speaking = False
                        self.current_turn_segment_start_ms = 0
                        self.pending_finalize_wait_logged = False
                        continue
                    if not self.pending_finalize_wait_logged:
                        print("[orchestrator] pending finalize waiting because user still speaking", flush=True)
                        self.pending_finalize_wait_logged = True
                    await asyncio.sleep(0.2)
                    continue
                if self.pending_finalize_wait_logged:
                    print("[orchestrator] pending finalize resumed after speech ended", flush=True)
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
                print(
                    f"[orchestrator] finalize decision stage={stage} should_finalize={decision.should_finalize} "
                    f"reason={decision.reason} silence_ms={silence_ms} speaking_elapsed_ms={speaking_elapsed_ms} "
                    f"semantic={decision.semantic_completion_score:.2f}",
                    flush=True,
                )
                if decision.should_finalize:
                    if decision.reason == "max_silence_force_finalize":
                        print(
                            f"[orchestrator] force finalizing buffered turn after long silence chars={len(str(payload.get('transcript') or ''))}",
                            flush=True,
                        )
                    self.pending_payload = None
                    await self._handle_interaction(ten_env, **payload)
                    self._reset_turn_capture()
                    return

                await asyncio.sleep(max(100, decision.need_more_wait_ms) / 1000.0)
        except asyncio.CancelledError:
            return

    async def on_init(self, ten_env: AsyncTenEnv) -> None:
        print("[orchestrator] on_init starting...", flush=True)
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
        self.session_id = str(uuid.uuid4())
        
        # 捕获简历和职位要求上下文
        self.resume_summary = config.get("resume_summary", "一名资深后端开发工程师")
        self.job_requirements = config.get("job_requirements", "精通分布式系统和高可用架构")
        
        self.trace_id = "ten_trace_" + uuid.uuid4().hex[:8]

        # 尝试加载提前预生成的简历题库
        data_dir = os.path.join(project_root, "data")
        q_file = os.path.join(data_dir, "interview_questions.json")
        if os.path.exists(q_file):
             try:
                 with open(q_file, "r", encoding="utf-8") as f:
                     self.question_pack["questions"] = json.load(f)
                 print(f"[orchestrator] Loaded {len(self.question_pack['questions'])} pre-generated questions.")
             except Exception as e:
                 print(f"[orchestrator] Error loading pre-generated questions: {e}")

        if not self.question_pack["questions"]:
            self.question_pack["questions"] = [
                {"stage": "P2", "question": "请结合你最近参与的那个核心项目，先做一个简短的自我介绍。"},
                {"stage": "P3", "question": "在刚才提到的项目中，你面临过最具挑战性的技术难题是什么？你是如何进行方案选型和落地权衡的？"},
                {"stage": "P4", "question": "如果现在该系统的访问量激增 10 倍，你认为架构中哪一个组件会最先遇到瓶颈？你会采取什么扩容或容灾策略？"},
            ]

        self.state = self.flow_engine.init_state(question_pack=self.question_pack)
        # 优先从本地文件加载全量简历内容并提取姓名
        resume_file_path = os.path.join(project_root, "data", "测试文本简历")
        if os.path.exists(resume_file_path):
            try:
                with open(resume_file_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    self.resume_summary = content
                    # 提取第一行作为姓名，并取后两位
                    first_line = content.split('\n')[0].strip()
                    if first_line and len(first_line) >= 2:
                        self.candidate_name = first_line[-2:]
                print(f"[orchestrator] Extracted name: {self.candidate_name}")
            except Exception as e:
                print(f"[orchestrator] Error loading local resume file: {e}")

        # 加载公司信息
        company_info_path = os.path.join(project_root, "data", "company_info.txt")
        if os.path.exists(company_info_path):
             try:
                 with open(company_info_path, "r", encoding="utf-8") as f:
                     self.company_info = f.read().strip()
                 print(f"[orchestrator] Loaded company info: {len(self.company_info)} chars")
             except Exception as e:
                 print(f"[orchestrator] Error loading company info: {e}")

        # 预构建 System Prompt 以利用 LLM Caching (固定前缀)
        self.system_prompt_built = (
            f"{self.system_prompt}\n\n"
            f"### 面试背景固化信息 (Cache Target) ###\n"
            f"候选人简历内容：\n{self.resume_summary}\n\n"
            f"岗位要求：\n{self.job_requirements}\n"
        )
        
        print(
            f"[orchestrator] on_init done. task_key={self.task_key}, trace_id={self.trace_id}",
            flush=True,
        )

    async def on_start(self, ten_env: AsyncTenEnv) -> None:
        print("[orchestrator] on_start", flush=True)

    async def on_cmd(self, ten_env: AsyncTenEnv, cmd: Cmd) -> None:
        cmd_name = cmd.get_name()
        
        if cmd_name == "start_of_sentence":
            self.is_user_speaking = True
            print("[orchestrator] User started speaking (VAD START)", flush=True)
            # 同时通知 TTS 打断（冗余保护）
            await ten_env.send_cmd(Cmd.create("interrupt"))
            
        elif cmd_name == "end_of_sentence":
            self.is_user_speaking = False
            print("[orchestrator] User stopped speaking (VAD END)", flush=True)

        elif cmd_name == "on_connected":
            # 只有当面试还未开始(处于S1)时，才允许初始化进度。
            # 防止网络波动或音轨切换导致的 on_connected 信号重置面试。
            if self.state.get("interview_stage", "S1") == "S1" and not self.state["context_flags"].get("greeted", False):
                print("[orchestrator] First connection. Sending connectivity check handshake...", flush=True)
                handshake_msg = f"{self.candidate_name}，你好。喂，听得到我说话吗？"
                await self._send_to_tts(ten_env, handshake_msg, is_final=False)
                await self._send_to_tts(ten_env, "", is_final=True)
                self._set_stage("S1", reason="connectivity_handshake_sent")
                self.state["context_flags"]["greeted"] = True
            else:
                print(f"[orchestrator] Reconnection detected in stage {self.state.get('interview_stage')}. Skipping state reset.", flush=True)
        elif cmd_name == "start_of_sentence":
            print("[orchestrator] user interrupted. Resetting turn state.", flush=True)
            self.turn_triggered = False # 关键：用户开口，重置触发权限
            if self.llm_task and not self.llm_task.done():
                self.llm_task.cancel()

        await ten_env.return_result(CmdResult.create(StatusCode.OK, cmd))

    async def on_stop(self, ten_env: AsyncTenEnv) -> None:
        print("[orchestrator] on_stop", flush=True)

    async def on_data(self, ten_env: AsyncTenEnv, data: Data) -> None:
        transcript, _ = data.get_property_string("text")
        is_final, _ = data.get_property_bool("is_final")
        stage = self.state.get("interview_stage", "S1")

        transcript = (transcript or "").strip()
        asr_final_ts, _ = data.get_property_float("asr_final_ts")
        asr_sentence_start_ts, _ = data.get_property_float("asr_sentence_start_ts")
        asr_physical_stop_ts, _ = data.get_property_float("asr_physical_stop_ts")
        
        # 扩展噪音/语气词黑名单与短语判定
        skip_phrases = {"嗯", "呃", "啊", "那个", "就是", "其实", "你看", "这个", "那", "这个那个", "这种", "那样", "这么说"}
        
        # 逻辑：对于 Final 包，增加过滤逻辑以防噪音误触发
        if is_final:
            if transcript == self.last_final_transcript:
                return # 防止重复
            self.last_final_transcript = transcript
            
            # 使用更纯净的文本进行判定
            clean_text = transcript.strip("。，？！ ")
            
            # 过滤短噪音、单字语气词，以及起始阶段的极短杂音 (如 "你看")
            if clean_text in skip_phrases or len(clean_text) < 2:
                print(f"[orchestrator] Final ignored (noise/filler): {transcript}", flush=True)
                return
            
            # 针对 S1/S2 阶段，对 2 个字以内的短语进行更严格的语义拦截（除非是特定的握手词/确认词）
            handshake_keywords = {"在的", "听到", "你好", "哈喽", "hello", "hi", "可以", "行", "好", "好的", "没问题", "对", "明白"}
            if len(clean_text) <= 2 and stage in ["S1", "S2"] and clean_text not in handshake_keywords:
                print(f"[orchestrator] Final ignored (short/potential noise in {stage}): {transcript}", flush=True)
                return

            # 如果本回合已经抢跑过了，我们比对一下文本
            if self.turn_triggered:
                # 简单启发式过滤：如果内容重合度高，就不再重复生成
                if len(transcript) > 0 and (self.last_triggered_text in transcript or transcript[:5] == self.last_triggered_text[:5]):
                    print(f"[orchestrator] skipping Final trigger; already handled by speculative: {self.last_triggered_text}", flush=True)
                    return

            print(f"[orchestrator] final user input: {transcript}", flush=True)
            self.turn_triggered = True
            self.last_triggered_text = transcript
            
            orch_receive_ts = time.perf_counter()
            asyncio.create_task(self._handle_interaction(ten_env, transcript, asr_final_ts, asr_sentence_start_ts, asr_physical_stop_ts, orch_receive_ts))
        else:
            # 逻辑：对于 Partial 包，在“豆包模式”下不再进行抢跑触发，以确保用户说话时 AI 绝对安静。
            # 我们仅记录日志，或者直接忽略。
            pass

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

            # 同步题目中的阶段标签，但严禁在开场环节（S1-S3）被技术题库覆盖
            if current_q and current_q.get("stage"):
                q_stage = current_q.get("stage")
                # 只有当系统已经进入 S4 及以后，或者不在前三个受保护环节时，才同步题库 Stage
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
                    print(
                        f"[orchestrator] Stage progress {stage}: completed={stage_progress_snapshot.completed} "
                        f"collected={stage_progress_snapshot.collected_signals} missing={stage_progress_snapshot.missing_signals}",
                        flush=True,
                    )
                
            print(f"[orchestrator] Interaction Triggered. Stage: {stage} (Index: {self.state.get('active_question_index')})", flush=True)

            # --- 状态机流转与干练衔接逻辑 (S1-S3, S7-S8) ---
            
            # S1 (Greeting Handshake) -> S2 (正式开场与自我介绍提示)
            if stage == "S1":
                 if not self.state["context_flags"]["connectivity_confirmed"]:
                      # 此时已经通过了上面的 Noise 过滤，说明是正常的 2 字以上有效输入
                      self.state["context_flags"]["connectivity_confirmed"] = True
                      self._set_stage("S2", reason="connectivity_confirmed")
                      
                      formal_welcome = (
                          "好的，没问题。那咱们就正式开始了。我是今天的面试官，很高兴能和你交流。"
                          "咱们今天的面试预计 40 分钟左右，分为：背景介绍、项目深挖、以及最后的公司介绍和答疑三个环节。"
                          "那咱们先从一个简短的自我介绍开始吧，你可以重点讲讲最近的项目心得。"
                      )
                      print(f"[orchestrator] Handshake confirmed. Starting session. Input: {transcript}", flush=True)
                      await self._send_to_tts(ten_env, formal_welcome, is_final=False)
                      await self._send_to_tts(ten_env, "", is_final=True)
                      return
                 
                 self._set_stage("S2", reason="opening_completed")

            # S2/S3 的硬编码在前置环节已移除，改为依靠 LLM [SATISFIED] 信号在 turn 结束时触发。
            # 这可以有效防止类似 "Come on" 等杂音由于被 ASR 误读而意外跳过自我介绍环节。

            # P5 (Company QA 环节)
            if stage == "S7":
                 if not self.state["context_flags"]["company_info_shared"]:
                      self.state["context_flags"]["company_info_shared"] = True
                      reply_msg = self._build_company_intro()
                      await self._send_to_tts(ten_env, reply_msg, is_final=False)
                      await self._send_to_tts(ten_env, "", is_final=True)
                      return
                 
                 # 如果用户已经问完了
                 if any(p in transcript for p in ["没问题", "没有了", "大概了解", "谢谢", "再见"]):
                      self._set_stage("S8", reason="candidate_has_no_more_questions")
                      # 下面会进入 P6 逻辑

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
            next_q_text = next_q.get("question", "???????????????") if next_q else "?????????????????"

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

            instruction = build_interview_stage_instruction(
                stage=stage,
                current_question=str(current_q.get("question") or ""),
                expected_signal=success_signals if 'success_signals' in locals() else "",
                next_question=next_q_text,
                is_last_followup=is_last_followup if 'is_last_followup' in locals() else False,
                company_info=self.company_info,
                stage_goal=str(self.state.get("stage_goal") or ""),
                missing_evidence=self.state.get("missing_evidence"),
                difficulty_level=str(self.state.get("difficulty_level") or "normal"),
                transition_reason=str(self.state.get("transition_reason") or ""),
            )

            history_str = ""
            if self.history:
                # 仅保留最近 2-3 轮关键对话，平衡上下文与缓存开销
                history_str = "### 核心对话历史 ###\n" + "\n".join([f"Q: {h['q']}\nA: {h['a']}" for h in self.history[-3:]]) + "\n\n"

            prompt = (
                f"### 面试环境与准则 ###\n"
                f"当前环节：{stage}\n"
                f"候选人：{self.candidate_name}\n\n"
                f"### 当前面试官指令 ###\n"
                f"{instruction}\n\n"
                f"{history_str}"
                f"### 候选人回应 (Volatile Output) ###\n"
                f"\"{transcript}\""
            )

            context = InvokeContext(
                task_key=self.task_key,
                trace_id=self.trace_id,
                system_prompt=self.system_prompt_built, # system_prompt_built 包含了简历和公司背书，由于是固定前缀，DeepSeek 会自动 Cache 这部分 Tokens
                prompt=prompt,
                entity_type="candidate",
                entity_id="test_user_01",
            )

            print(f"[orchestrator] triggering async LLM worker for stage {stage}...", flush=True)
            
            # --- 核心改进：Filler ACK 抢跑 (仅在技术深挖环节开启) ---
            if stage in ["S4", "S5", "S6"]:
                import random
                available_fillers = [f for f in self.EXPERT_FILLERS if f != self.last_filler]
                filler = random.choice(available_fillers)
                self.last_filler = filler
                print(f"[orchestrator] Sending filler for stage {stage}: {filler}", flush=True)
                await self._send_to_tts(ten_env, filler, is_final=False)
            
            llm_start_ts = time.perf_counter()
            self.llm_task = asyncio.create_task(self._llm_streaming_worker(ten_env, context, asr_final_ts, asr_sentence_start_ts, asr_physical_stop_ts, orch_receive_ts, llm_start_ts, transcript))
            full_reply_text = await self.llm_task

            # --- 安全性防御：检查 LLM 返回值是否有效 ---
            if full_reply_text is None:
                print("[orchestrator] LLM Task returned None. Skipping state update.", flush=True)
                return

            # --- 核心改进：状态推进与接下来逻辑 ---
            # 无论 LLM 是否满意，或者是回答质量本身太差需结束追问
            was_satisfied = "[SATISFIED]" in full_reply_text

            was_fallback = "[FALLBACK]" in full_reply_text

            stage_signals_completed = bool(stage_progress_snapshot and stage_progress_snapshot.completed)

            

            if was_fallback:

                 print(f"[orchestrator] LLM triggered FALLBACK for stage {stage}. Consuming one follow-up turn.", flush=True)

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
                print(
                    f"[orchestrator] Terminating topic. was_satisfied={was_satisfied} "
                    f"stage_signals_completed={stage_signals_completed}",
                    flush=True,
                )
                
                next_q = self.flow_engine.current_question(state=self.state, question_pack=self.question_pack)
                next_stage = self.state.get("interview_stage")

                # 如果还在技术环节 (S4/S5/S6)，执行干练衔接
                if next_q and next_stage in ["S4", "S5", "S6"]:
                    bridge_instr = "针对刚聊的内容做一个 10 字以内的专业确认，然后立刻进入下一个考点。"
                    # 实际由下一轮处理，或者在这里预发一个引导。
                    # 为了保证“丝滑”，我们由下一轮 LLM 自动处理，此处不发 Fast Path。
                    pass

            # 题库消耗完毕后派生阶段更新
            if self.state["active_question_index"] >= len(self.question_pack["questions"]) and stage not in ["S7", "S8"]:
                 self._set_stage("S7", reason="question_pack_exhausted")
        except asyncio.CancelledError:
            print("[orchestrator] LLM interaction task cancelled.", flush=True)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            print(f"[orchestrator] interaction failed: {exc}", flush=True)

    async def _llm_streaming_worker(self, ten_env: AsyncTenEnv, context: InvokeContext, asr_final_ts: float, asr_sentence_start_ts: float, asr_physical_stop_ts: float, orch_receive_ts: float, llm_start_ts: float, transcript: str) -> str:
        try:
            content_iter = self.llm_client.async_stream_invoke(context=context)
            emitted = False
            first_sentence_sent = False
            llm_ttfb_ts = 0.0 # Time to First Byte (Chunk)
            llm_ttfs_ts = 0.0 # Time to First Sentence
            full_reply_content = []
            
            async def _raw_chunk_interceptor(inner_iter):
                nonlocal llm_ttfb_ts
                async for chunk in inner_iter:
                    if not llm_ttfb_ts:
                        llm_ttfb_ts = time.perf_counter()
                    yield chunk

            async for sentence in split_sentences_async(_raw_chunk_interceptor(content_iter)):
                sentence = (sentence or "").strip()
                if not sentence:
                    continue
                
                full_reply_content.append(sentence)

                if not first_sentence_sent:
                    first_sentence_sent = True
                    llm_ttfs_ts = time.perf_counter()
                    
                    # 时延计算与打印
                    asr_recognition_delay = (asr_final_ts - asr_sentence_start_ts) * 1000 if asr_sentence_start_ts > 0 else 0
                    vad_wait_delay = (asr_final_ts - asr_physical_stop_ts) * 1000 if asr_physical_stop_ts > 0 else 0
                    trigger_delay = (llm_start_ts - asr_physical_stop_ts) * 1000 if asr_physical_stop_ts > 0 else 0
                    
                    orch_overhead = (orch_receive_ts - asr_final_ts) * 1000
                    llm_start_delay = (llm_start_ts - orch_receive_ts) * 1000
                    
                    llm_ttfb_delay = (llm_ttfb_ts - llm_start_ts) * 1000 if llm_ttfb_ts > 0 else 0
                    llm_ttfs_delay = (llm_ttfs_ts - llm_ttfb_ts) * 1000 if llm_ttfb_ts > 0 else 0
                    total_p95_offset = (llm_ttfs_ts - asr_final_ts) * 1000
                    
                    print(f"\n[LATENCY_STATS] Turn Trace: {context.trace_id}")
                    print(f"  - ASR Recognition (Voice -> Final): {asr_recognition_delay:.2f}ms")
                    print(f"  - VAD Wait (Physical Stop -> Final): {vad_wait_delay:.2f}ms")
                    print(f"  - Trigger Delay (Physical Stop -> LLM): {trigger_delay:.2f}ms")
                    print(f"  - Orchestrator Queue/Bus: {orch_overhead:.2f}ms")
                    print(f"  - LLM Prep/Guardrail: {llm_start_delay:.2f}ms")
                    print(f"  - LLM TTFB (First Chunk): {llm_ttfb_delay:.2f}ms")
                    print(f"  - LLM TTFS (First Sentence): {llm_ttfs_delay:.2f}ms")
                    print(f"  - TOTAL (ASR Final -> TTS Send): {total_p95_offset:.2f}ms\n", flush=True)

                emitted = True
                import re
                print(f"[orchestrator] llm raw sentence: {sentence}", flush=True)
                # 过滤 [SATISFIED] 和 [FALLBACK] 标记，防止念出内部标签
                clean_sentence = re.sub(r'\[.*?\]', '', sentence).strip()
                if not clean_sentence:
                    continue
                
                print(f"[orchestrator] llm clean sentence: {clean_sentence}", flush=True)
                # 核心避让逻辑：在发送给 TTS 之前，检查用户是否正在说话
                while self.is_user_speaking:
                    print(f"[orchestrator] AI Avoidance: Waiting for user to finish speaking before sending: {clean_sentence[:20]}...", flush=True)
                    await asyncio.sleep(0.2) # 每 200ms 检查一次

                # 透传物理闭口时间，用于 TTS 侧计算真实闭环时延
                await self._send_to_tts(ten_env, clean_sentence, is_final=False, asr_physical_stop_ts=asr_physical_stop_ts, trace_id=context.trace_id)

            if not emitted:
                error_msg = "收到，我们继续下一题。"
                await self._send_to_tts(ten_env, error_msg, is_final=False)
                full_reply_content.append(error_msg)
            
            # 记录对话历史（限制 5 轮，平衡上下文与缓存开销）
            self.history.append({"q": transcript, "a": " ".join(full_reply_content)})
            if len(self.history) > 5:
                self.history = self.history[-5:]
            
            # 通知 TTS 底层关闭
            await self._send_to_tts(ten_env, "", is_final=True)
            return " ".join(full_reply_content)
        except asyncio.CancelledError:
            print(f"[orchestrator] LLM streaming cancelled by user.", flush=True)
        except Exception as exc:
            print(f"[orchestrator] LLM streaming failed: {exc}", flush=True)

    async def _send_to_tts(self, ten_env: AsyncTenEnv, text: str, is_final: bool = True, asr_physical_stop_ts: float = 0.0, trace_id: str = "") -> None:
        tts_data = Data.create("text_data")
        tts_data.set_property_string("text", text)
        tts_data.set_property_bool("is_final", is_final)
        if asr_physical_stop_ts > 0:
            tts_data.set_property_float("asr_physical_stop_ts", asr_physical_stop_ts)
            tts_data.set_property_string("trace_id", trace_id)
        await ten_env.send_data(tts_data)

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
            print("[orchestrator] User started speaking (VAD START)", flush=True)
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
            print("[orchestrator] User stopped speaking (VAD END)", flush=True)

        elif cmd_name == "on_connected":
            if self.state.get("interview_stage", "S1") == "S1" and not self.state["context_flags"].get("greeted", False):
                print("[orchestrator] First connection. Sending connectivity check handshake...", flush=True)
                handshake_msg = f"{self.candidate_name}，你好。喂，听得到我说话吗？"
                await self._send_to_tts(ten_env, handshake_msg, is_final=False)
                await self._send_to_tts(ten_env, "", is_final=True)
                self._set_stage("S1", reason="connectivity_handshake_sent")
                self.state["context_flags"]["greeted"] = True
            else:
                print(
                    f"[orchestrator] Reconnection detected in stage {self.state.get('interview_stage')}. Skipping state reset.",
                    flush=True,
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
            "嗯",
            "呃",
            "啊",
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

        clean_text = transcript.strip("。，“”，！？!?, ")
        if clean_text in skip_phrases or len(clean_text) < 2:
            print(f"[orchestrator] Final ignored (noise/filler): {transcript}", flush=True)
            return
        if len(clean_text) <= 2 and stage in {"S1", "S2"} and clean_text not in handshake_keywords:
            print(f"[orchestrator] Final ignored (short/potential noise in {stage}): {transcript}", flush=True)
            return

        if stage == "S1" and any(phrase in transcript for phrase in audio_issue_phrases):
            print(f"[orchestrator] Audio issue detected during handshake: {transcript}", flush=True)
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
                    print(f"[orchestrator] allowing reengagement transcript through dedupe: {transcript}", flush=True)
                elif self._has_active_response_pipeline():
                    print(
                        f"[orchestrator] skipping Final trigger; already handled by speculative: {self.last_triggered_text}",
                        flush=True,
                    )
                    return
                else:
                    print(
                        f"[orchestrator] duplicate-like final allowed because pipeline is idle: {transcript}",
                        flush=True,
                    )

        print(f"[orchestrator] final user input buffered: {transcript}", flush=True)
        self.turn_triggered = True
        self.last_triggered_text = transcript
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
                    print("[orchestrator] generation became stale before sentence emit", flush=True)
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

                    print(f"\n[LATENCY_STATS] Turn Trace: {context.trace_id}")
                    print(f"  - ASR Recognition (Voice -> Final): {asr_recognition_delay:.2f}ms")
                    print(f"  - VAD Wait (Physical Stop -> Final): {vad_wait_delay:.2f}ms")
                    print(f"  - Trigger Delay (Physical Stop -> LLM): {trigger_delay:.2f}ms")
                    print(f"  - Orchestrator Queue/Bus: {orch_overhead:.2f}ms")
                    print(f"  - LLM Prep/Guardrail: {llm_start_delay:.2f}ms")
                    print(f"  - LLM TTFB (First Chunk): {llm_ttfb_delay:.2f}ms")
                    print(f"  - LLM TTFS (First Sentence): {llm_ttfs_delay:.2f}ms")
                    print(f"  - TOTAL (ASR Final -> TTS Send): {total_p95_offset:.2f}ms\n", flush=True)

                emitted = True

                print(f"[orchestrator] llm raw sentence: {sentence}", flush=True)
                clean_sentence = self._sanitize_tts_text(sentence)
                if not clean_sentence:
                    print("[orchestrator] llm sentence dropped after sanitize", flush=True)
                    continue
                if not self._is_tts_speakable(clean_sentence):
                    print(f"[orchestrator] llm sentence blocked for TTS: {clean_sentence}", flush=True)
                    continue
                print(f"[orchestrator] llm clean sentence: {clean_sentence}", flush=True)

                while not self.arbiter.can_commit_tts(
                    generation_id=generation_id,
                    now_ms=self._now_ms(),
                ):
                    if not self.arbiter.is_generation_active(generation_id):
                        print("[orchestrator] generation cancelled during commit wait", flush=True)
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
                self.history.append({"q": transcript, "a": " ".join(full_reply_content)})
                if len(self.history) > 5:
                    self.history = self.history[-5:]
                await self._send_to_tts(ten_env, "", is_final=True, generation_id=generation_id)
            return " ".join(full_reply_content)
        except asyncio.CancelledError:
            print("[orchestrator] LLM streaming cancelled by user.", flush=True)
            return ""
        except Exception as exc:
            print(f"[orchestrator] LLM streaming failed: {exc}", flush=True)
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
            self.arbiter.clear_playback()
        await ten_env.send_data(tts_data)

    async def on_stop(self, ten_env: AsyncTenEnv) -> None:
        self._cancel_pending_finalize()
        self._invalidate_active_response()
        with contextlib.suppress(Exception):
            await ten_env.send_cmd(Cmd.create("interrupt"))
        print("[orchestrator] on_stop", flush=True)
