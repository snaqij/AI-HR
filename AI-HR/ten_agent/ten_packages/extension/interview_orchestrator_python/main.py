import asyncio
import json
import os
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
from ai_hr.services.llm.client import InvokeContext, LLMClient
from ai_hr.services.llm.guardrails import GuardrailService
from ai_hr.services.llm.router import ModelRouter
from ai_hr.services.orchestrator.streaming_utils import split_sentences, split_sentences_async
from ai_hr.services.interview_runtime.interview_questions import (
    get_random_p1, get_random_p5, get_random_p6
)


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
        self.system_prompt = (
            "你是一名资深、冷静且敏锐的大厂技术面试专家（P8+）。你的目标是通过深维度追问评估候选人的真实实力。\n\n"
            "## 核心人格 ##\n"
            "- 专业且克制：严禁废话，不进行无意义的赞美（禁止‘太棒了’、‘原来如此’、‘非常有参考价值’等）。\n"
            "- 敏锐：如果候选人回答模糊（如‘听说过’、‘好像是’），立刻针对具体实现进行压力追问。\n"
            "- 引导者：如果候选人跑题，请立刻使用干练的衔接语将其拉回当前技术考点。\n"
            "- 禁止透露 AI 身份。\n\n"
            "## 交互控制 ##\n"
            "- 限制：说话干脆利落，单次回复严控在 50 字以内，严禁 Markdown。\n"
            "- DDA 动态难度：如果候选人对高难度问题理解困难（如连续回答‘不清楚’、‘没做过’），请在回复中包含‘[FALLBACK]’标记，并降低难度转而提问基础原理或应用场景。"
        )

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
                self.state["interview_stage"] = "S1"
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

    async def _handle_interaction(self, ten_env: AsyncTenEnv, transcript: str, asr_final_ts: float, asr_sentence_start_ts: float, asr_physical_stop_ts: float, orch_receive_ts: float) -> None:
        try:
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
                    self.state["interview_stage"] = stage

            evaluation = self.flow_engine.evaluate_answer(
                transcript=transcript,
                confidence=0.95,
            )
                
            print(f"[orchestrator] Interaction Triggered. Stage: {stage} (Index: {self.state.get('active_question_index')})", flush=True)

            # --- 状态机流转与干练衔接逻辑 (S1-S3, S7-S8) ---
            
            # S1 (Greeting Handshake) -> S2 (正式开场与自我介绍提示)
            if stage == "S1":
                 if not self.state["context_flags"]["connectivity_confirmed"]:
                      # 此时已经通过了上面的 Noise 过滤，说明是正常的 2 字以上有效输入
                      self.state["context_flags"]["connectivity_confirmed"] = True
                      self.state["interview_stage"] = "S2"
                      
                      formal_welcome = (
                          "好的，没问题。那咱们就正式开始了。我是今天的面试官，很高兴能和你交流。"
                          "咱们今天的面试预计 40 分钟左右，分为：背景介绍、项目深挖、以及最后的公司介绍和答疑三个环节。"
                          "那咱们先从一个简短的自我介绍开始吧，你可以重点讲讲最近的项目心得。"
                      )
                      print(f"[orchestrator] Handshake confirmed. Starting session. Input: {transcript}", flush=True)
                      await self._send_to_tts(ten_env, formal_welcome, is_final=False)
                      await self._send_to_tts(ten_env, "", is_final=True)
                      return
                 
                 self.state["interview_stage"] = "S2"

            # S2/S3 的硬编码在前置环节已移除，改为依靠 LLM [SATISFIED] 信号在 turn 结束时触发。
            # 这可以有效防止类似 "Come on" 等杂音由于被 ASR 误读而意外跳过自我介绍环节。

            # P5 (Company QA 环节)
            if stage == "S7":
                 if not self.state["context_flags"]["company_info_shared"]:
                      self.state["context_flags"]["company_info_shared"] = True
                      reply_msg = f"刚才的技术环节我们聊得很深入，我也对你的背景有了更清晰的认识。接下来，我为你简单介绍一下我们公司的情况。\n\n{self.company_info}\n\n那么，关于我们团队或者这个岗位，你有什么想了解的吗？"
                      await self._send_to_tts(ten_env, reply_msg, is_final=False)
                      await self._send_to_tts(ten_env, "", is_final=True)
                      return
                 
                 # 如果用户已经问完了
                 if any(p in transcript for p in ["没问题", "没有了", "大概了解", "谢谢", "再见"]):
                      self.state["interview_stage"] = "S8"
                      # 下面会进入 P6 逻辑

            if stage == "S8":
                 if not self.state["context_flags"]["closing_started"]:
                      self.state["context_flags"]["closing_started"] = True
                      closing_msg = f"好的，那今天的交流就先到这里。后续的安排 HR 会在 3 个工作日内告知你。非常感谢你的支持，回见！"
                      await self._send_to_tts(ten_env, closing_msg, is_final=False)
                      await self._send_to_tts(ten_env, "", is_final=True)
                 return

            # --- LLM 业务逻辑 (S2-S6) ---
            
            # 获取下一题预览，用于支持 LLM 主动转场
            next_q = self.flow_engine.current_question(
                state={"active_question_index": self.state["active_question_index"] + 1},
                question_pack=self.question_pack
            )
            next_q_text = next_q.get("question", "面试结束，进入 QA 环节") if next_q else "没有更多技术题了，准备进入 QA 环节"

            # 构造面试指令 (结合 DDA、锚点信息与预览题目)
            if stage == "S7":
                 instruction = f"你现在是答疑时间。请根据公司信息简短回答。公司信息：{self.company_info}。限制 50 字以内，不准说废话。"
            else:
                 is_last_followup = (self.state["followup_count_current"] >= current_q.get("max_followups", 2) - 1)
                 success_signals = ", ".join(current_q.get("success_signals", []))
                 tech_context = current_q.get("technical_context", "")

                 # 针对不同阶段的动态指令
                 # 针对不同阶段的动态指令
                 if stage in ["S1", "S2", "S3"]:
                     instruction = (
                         f"当前环节：{stage}。核心引导：请继续深度引导候选人介绍项目背景及个人职责。\n"
                         f"## 重要流转指令 ##\n"
                         f"1. 这是一个引导环节。当确认背景完整时，请务必输出 [SATISFIED] 标记推进到技术环节。\n"
                         f"2. 限制 50 字以内。资深面试官语气。禁止复读。"
                     )
                 else:
                     instruction = (
                         f"当前环节：{stage}。核心锚点题：{current_q.get('question')}。\n"
                         f"技术背景：{tech_context}\n"
                         f"期望成功信号：{success_signals}\n"
                         f"## 重要流转指令 ##\n"
                         f"1. 答透或说“跳过”即输出 [SATISFIED] 跳转。\n"
                         f"2. 下一题预览：{next_q_text}\n"
                         f"3. 限制 50 字。严禁复读问题。"
                     )
                 
                 if is_last_followup:
                     instruction += "\n注意：这是本题最后一次追问机会，无论回答如何，结束后请准备切题。"

            # --- 核心改进：针对 DeepSeek V3 的 Context Caching 优化 ---
            # 这里的顺序极其重要：System Prompt -> Instructions -> History -> Latest Context
            # 通过将 instruction 放在 history 之前，我们可以保证即使 history 变长，指令部分的缓存依然有效。
            
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

            if was_satisfied:
                if stage == "S2":
                    self.state["interview_stage"] = "S3"
                elif stage == "S3":
                    self.state["interview_stage"] = "S4"
            else:
                # 兜底：如果在 S2/S3 阶段且已回答了实质性内容 (或者回答较长)，也执行转场，防止卡死
                if stage in ["S2", "S3"] and (not evaluation.get("need_followup", True) or len(transcript) > 15):
                    next_stage = "S3" if stage == "S2" else "S4"
                    print(f"[orchestrator] Heuristic transition: {stage} -> {next_stage} (input length/quality)", flush=True)
                    self.state["interview_stage"] = next_stage
                    print("[orchestrator] Transitioning S2 -> S3", flush=True)
                elif stage == "S3":
                    self.state["interview_stage"] = "S4"
                    print("[orchestrator] Transitioning S3 -> S4", flush=True)

            if was_satisfied or self.state["followup_count_current"] == 0:
                print(f"[orchestrator] Terminating topic. was_satisfied={was_satisfied}", flush=True)
                
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
                 self.state["interview_stage"] = "S7"
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
