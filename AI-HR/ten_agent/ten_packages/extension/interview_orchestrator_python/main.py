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
            "好的，我大概了解了。那咱们换个话题，聊聊",
            "明白，那关于这块我们就先聊到这里。下面我想了解一下",
            "嗯，原来是这样。那咱们继续，我想听听你对...的看法。比如",
            "听起来你在这一块确实有很多心得。那咱们深入一下，谈谈",
            "好的，非常有参考价值。那咱们进入下一个环节，关于"
        ]
        self.EXPERT_BRIDGES = [
            "听起来你的项目经验非常扎实，业务逻辑也考虑得很清楚。那咱们正式开始技术交流，",
            "明白，你的背景和我们这个岗位的匹配度确实挺高的。那咱们深入聊聊，",
            "好的，感谢你的分享，我对你的履历有了初步了解。那咱们先从技术底层开始，",
            "很有意思的经历。那咱们进入正题，我想针对你的项目细节问一下，"
        ]
        self.system_prompt = (
            "你是一名亲切且专业的资深技术专家面试官。你的目标是让候选人解压，在大厂面试中遇到了一位非常老练且有人情味的朋友。\n\n"
            "## 核心人格设定 ##\n"
            "- 禁止透露你是 AI 或模型。严禁使用‘你好，我是 AI’或任何机器人的措辞。\n"
            "- 语气要老道、沉稳但亲切。使用‘原来是这样’、‘那咱们聊聊...’、‘刚才你提到点子上去了’。\n"
            "- 说话干脆利落，严禁啰嗦，总字数严控在 50 字左右。\n\n"
            "## 判定逻辑 (重要) ##\n"
            "- **回答相关性**：如果候选人的回答完全无关、过短或纯噪音（如‘去下载’、‘信号不好’），请不要判断为满意。你要温柔地引导候选人回到面试主题上，例如：‘咱们还是回到刚才聊的问题上...’。\n"
            "- **满意判定**：只有当候选人的回答确实涉及了技术核心或项目细节，且比较透彻时，请在回复的最开始加上 [SATISFIED] 标记。\n\n"
            "## 严禁使用的词汇 (禁术词表) ##\n"
            "- ‘AI’、‘大模型’、‘指令’、‘任务’、‘评估’、‘正在处理’、‘明白’、‘收到’、‘收到你的回答’。\n\n"
            "## 交互风格 ##\n"
            "- 如果你判断当前题目已结束（输出 [SATISFIED]），**请不要**自行询问下一道大题，只需完整评价候选人的表现。下一道题目由系统编排器自动衔接。\n"
            "- 严禁输出任何 Markdown 标记、标题或标签。"
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
        print(f"[orchestrator] on_cmd: {cmd_name}", flush=True)

        if cmd_name == "on_connected":
            print("[orchestrator] Sending personalized greeting...", flush=True)
            welcome_msg = (
                f"{self.candidate_name}，你好。我是今天负责跟你交流的面试官。很高兴能有机会一起探讨一下。咱们今天的面试预计大概 35 到 60 分钟，"
                f"会分为自我介绍、核心项目深挖、以及最后的公司介绍和答疑三个环节。准备好了吗？那咱们先从一个简短的自我介绍开始吧！"
            )
            await self._send_to_tts(ten_env, welcome_msg, is_final=False)
            await self._send_to_tts(ten_env, "", is_final=True)
            self.state["interview_stage"] = "P1"
            self.state["context_flags"]["greeted"] = True
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

        transcript = (transcript or "").strip()
        asr_final_ts, _ = data.get_property_float("asr_final_ts")
        asr_sentence_start_ts, _ = data.get_property_float("asr_sentence_start_ts")
        asr_physical_stop_ts, _ = data.get_property_float("asr_physical_stop_ts")
        
        # 扩展噪音/语气词黑名单
        skip_phrases = {"嗯", "喂", "呃", "啊", "那个", "好的", "没关系", "就是", "其实", "对", "好", "行", "明白", "可以"}

        # 逻辑：对于 Final 包，增加过滤逻辑以防噪音误触发
        if is_final:
            if transcript == self.last_final_transcript:
                return # 防止重复
            self.last_final_transcript = transcript
            
            # 过滤短噪音或单字语气词
            if transcript in skip_phrases or len(transcript) < 2:
                print(f"[orchestrator] Final ignored (noise/filler): {transcript}", flush=True)
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
            # 1. 获取当前题目上下文
            current_q = self.flow_engine.current_question(
                state=self.state,
                question_pack=self.question_pack,
            ) or {}
            
            evaluation = self.flow_engine.evaluate_answer(
                transcript=transcript,
                confidence=0.95,
            )
            
            # 2. 基础评价判定 (同步阶段不提前推进状态，仅作为 LLM 判定参考)
            # self.state = self.flow_engine.apply_turn_result(
            #     state=self.state,
            #     evaluation=evaluation,
            #     current_q_max_followups=current_q.get("max_followups", 2),
            #     force_complete=False 
            # )
            # 注：延迟到 LLM 输出后再决定是否推进状态
            
            stage = self.state.get("interview_stage", "P1")
            print(f"[orchestrator] Interaction Triggered. Stage: {stage}", flush=True)

            # --- 特殊阶段直接处理 ---
            
            # P1 (Greeting 结束) -> P2 (自我介绍正在进行)
            if stage == "P1":
                 self.state["interview_stage"] = "P2"
                 # 此处不进入 Fast Path，继续让 LLM 处理自我介绍

            # P2 (自我介绍结束) -> P3 (正式技术环节)
            if stage == "P2" and not self.state["context_flags"]["intro_ready"]:
                 self.state["context_flags"]["intro_ready"] = True
                 self.state["interview_stage"] = "P3"
                 
                 # FAST PATH: 自流转到第一道题
                 import random
                 bridge = random.choice(self.EXPERT_BRIDGES)
                 first_q = self.flow_engine.current_question(state=self.state, question_pack=self.question_pack)
                 if first_q:
                      fast_msg = f"{bridge}{first_q['question']}"
                      print(f"[orchestrator] P2->P3 FAST PATH: {fast_msg}", flush=True)
                      await self._send_to_tts(ten_env, fast_msg, is_final=False)
                      await self._send_to_tts(ten_env, "", is_final=True)
                      
                      # 同步更新历史，确保下一轮上下文一致
                      self.history.append({"q": "自我介绍", "a": transcript})
                      return

            # P5 (Company QA 环节)
            if stage == "P5":
                 if not self.state["context_flags"]["company_info_shared"]:
                      self.state["context_flags"]["company_info_shared"] = True
                      reply_msg = f"刚才的技术环节我们聊得很深入，我也对你的背景有了更清晰的认识。接下来，我为你简单介绍一下我们公司的情况。\n\n{self.company_info}\n\n那么，关于我们团队或者这个岗位，你有什么想了解的吗？"
                      await self._send_to_tts(ten_env, reply_msg, is_final=False)
                      await self._send_to_tts(ten_env, "", is_final=True)
                      return
                 
                 # 如果用户已经问完了
                 if any(p in transcript for p in ["没问题", "没有了", "大概了解", "谢谢", "再见"]):
                      self.state["interview_stage"] = "P6"
                      # 下面会进入 P6 逻辑

            if stage == "P6":
                 if not self.state["context_flags"]["closing_started"]:
                      self.state["context_flags"]["closing_started"] = True
                      closing_msg = f"好的，那今天的交流就先到这里。后续的安排 HR 会在 3 个工作日内告知你。非常感谢你的支持，回见！"
                      await self._send_to_tts(ten_env, closing_msg, is_final=False)
                      await self._send_to_tts(ten_env, "", is_final=True)
                 return

            # --- LLM 业务逻辑 (P2-P4) ---

            # 构造面试指令 (提前计算以维持 Prompt 稳定性)
            if stage == "P5":
                 instruction = f"你现在是答疑时间。请根据公司信息回答候选人的问题。公司信息：{self.company_info}。回答要专业且有吸引力。限制 50 字。"
            else:
                 instruction = (
                     f"当前考察点：{current_q.get('question', '背景了解')}。期待信号：{current_q.get('expected_signal', '清晰表达')}。\n"
                     f"如果回答不足，请进行技术追问。如果回答已经非常透彻，请输出 [SATISFIED] 标记。限制 50 字。"
                 )

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
            llm_start_ts = time.perf_counter()
            self.llm_task = asyncio.create_task(self._llm_streaming_worker(ten_env, context, asr_final_ts, asr_sentence_start_ts, asr_physical_stop_ts, orch_receive_ts, llm_start_ts, transcript))
            full_reply_text = await self.llm_task

            # --- 核心改进：状态推进与接下来逻辑 ---
            # 无论 LLM 是否满意，或者是回答质量本身太差需结束追问
            was_satisfied = "[SATISFIED]" in full_reply_text
            self.state = self.flow_engine.apply_turn_result(
                state=self.state,
                evaluation=evaluation,
                current_q_max_followups=current_q.get("max_followups", 2),
                force_complete=was_satisfied
            )

            if was_satisfied or self.state["followup_count_current"] == 0:
                print(f"[orchestrator] Terminating topic. was_satisfied={was_satisfied}, final_followup={self.state['followup_count_current']==0}", flush=True)
                
                # 获取刷新后的下一题
                next_q = self.flow_engine.current_question(state=self.state, question_pack=self.question_pack)
                next_stage = self.state.get("interview_stage")

                # 如果有下一题且还在技术环节，执行 Fast Path
                if next_q and next_stage in ["P3", "P4"]:
                    import random
                    bridge = random.choice(self.BRIDGES)
                    fast_msg = f"{bridge}{next_q['question']}"
                    print(f"[orchestrator] FAST PATH TRIGGERED: {fast_msg}", flush=True)
                    
                    # 发送 Fast Path 内容
                    await self._send_to_tts(ten_env, fast_msg, is_final=False)
                    await self._send_to_tts(ten_env, "", is_final=True)
                    return

            # 题库消耗完毕后派生阶段更新
            if self.state["active_question_index"] >= len(self.question_pack["questions"]) and stage not in ["P5", "P6"]:
                 self.state["interview_stage"] = "P5"
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
                # 过滤 [SATISFIED] 标记，防止念出内部标签
                clean_sentence = re.sub(r'\[.*?\]', '', sentence).strip()
                if not clean_sentence:
                    continue
                
                print(f"[orchestrator] llm clean sentence: {clean_sentence}", flush=True)
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
