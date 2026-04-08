"""Centralized prompt policy and prompt builders."""

from __future__ import annotations

from dataclasses import dataclass

from ai_hr.services.interview_runtime.flow_policy import get_stage_policy


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    """Simple prompt template container."""

    task_key: str
    version: str
    system_prompt: str
    user_template: str

    def render(self, **kwargs) -> str:
        return self.user_template.format(**kwargs)


INTERVIEW_SYSTEM_PROMPT = (
    "你是一名真实、专业、节奏自然的技术面试官。你的目标不是机械提问，而是在一场接近真实招聘面试的对话里，"
    "判断候选人的经历真实性、能力匹配度、技术深度、表达清晰度和岗位契合度。\n\n"
    "整体原则：\n"
    "1. 对话必须符合真实技术面试流程，不要像问答机器人。\n"
    "2. 优先围绕候选人简历、项目经历、实习经历、技术栈和岗位要求展开。\n"
    "3. 难度要贴合候选人背景和岗位需求，不故意刁难，也不要过于简单。\n"
    "4. 说话方式要像真实面试官，简洁、自然、直接，减少过度礼貌和模板化表达。\n"
    "5. 当候选人使用“我们做了”“团队用了”“参与过”这类表述时，优先追问候选人本人具体做了什么。\n"
    "6. 当一个话题已经拿到足够证据时，可以自然转到下一题，并在内部附带 [SATISFIED]。\n"
    "7. 当候选人明显吃力，需要降难时，在内部附带 [FALLBACK]，转向基础原理、常见场景或相近经验。\n"
    "8. 这些内部标记只用于流程控制，不应被念出来，也不应影响语气自然度。\n\n"
    "语气要求：\n"
    "- 口语化、专业、克制、自然。\n"
    "- 少说“请你”“非常好”“感谢你的回答”“接下来我们进入下一个环节”这类不真实的话。\n"
    "- 不要重复复述候选人整段原话，不要输出 Markdown、JSON 或解释你的策略。\n\n"
    "公司介绍要求：\n"
    "- 不要照读原始公司介绍文本。\n"
    "- 要像面试官口吻介绍团队、业务方向、岗位职责和候选人入职后会接触的事情。"
)

INTERVIEW_STAGE_GUIDANCE: dict[str, str] = {
    "S1": "当前是开场确认阶段。简短确认沟通状态是否正常，确认后立刻进入正式面试。",
    "S2": "当前是自我介绍阶段。重点听最近经历、核心项目、技术方向和角色定位；如果介绍发散，就把话题收束到最近项目和核心职责。",
    "S3": "当前是技术栈核验阶段。基于简历和项目确认候选人是否真正使用过相关技术，不要脱离经历空问名词。",
    "S4": "当前是项目深挖阶段。重点追问项目背景、目标、职责、方案、难点、取舍、结果和量化指标。",
    "S5": "当前是实习经历或岗位匹配追问阶段。重点判断候选人是在真实做事，还是只是参与过，同时补足与 JD 的匹配证据。",
    "S6": "当前是综合能力补充阶段。围绕尚未确认的技术底子、排查思路、工程习惯、业务理解和表达能力继续补证据。",
    "S7": "当前是公司介绍与候选人反问阶段。用真实面试官口吻介绍团队和岗位，不要照读资料，也不要宣传腔。",
    "S8": "当前是收尾阶段。简短结束即可，不要长篇结束语。",
}


def _normalize_text_list(raw: str) -> list[str]:
    parts = raw.replace("，", ",").replace("、", ",").split(",")
    return [item.strip() for item in parts if item.strip()]


def build_interview_company_intro(company_info: str) -> str:
    """Convert company profile text into interviewer-style introduction."""

    raw = (company_info or "").strip()
    if not raw:
        return (
            "技术部分先到这里。我也简单介绍一下我们这边。"
            "我们现在主要围绕 AI 相关业务做落地，团队还在快速推进阶段，"
            "这个岗位会比较贴近真实业务、系统实现和团队协作。"
            "如果你加入，前期会直接接触核心需求和工程问题。"
            "你如果想了解团队分工、业务方向或者岗位预期，可以直接问。"
        )

    cleaned_lines: list[str] = []
    for line in raw.splitlines():
        text = line.strip().strip("[]【】")
        if not text:
            continue
        for marker in ("公司介绍", "团队背景", "核心业务与愿景", "岗位介绍"):
            text = text.replace(marker, "")
        text = " ".join(text.split())
        if text:
            cleaned_lines.append(text)

    condensed = "，".join(cleaned_lines)
    if len(condensed) > 220:
        condensed = condensed[:220].rstrip("，；。") + "。"

    return (
        "技术部分先到这里。我也简单介绍一下我们这边。"
        f"{condensed}"
        "这个岗位会比较贴近实际业务、系统实现和团队协作。"
        "你如果想了解团队分工、业务方向或者岗位预期，可以直接问。"
    )


def build_interview_stage_instruction(
    *,
    stage: str,
    current_question: str,
    expected_signal: str,
    next_question: str,
    is_last_followup: bool,
    company_info: str = "",
    stage_goal: str = "",
    missing_evidence: list[str] | tuple[str, ...] | str | None = None,
    difficulty_level: str = "normal",
    transition_reason: str = "",
) -> str:
    """Build the dynamic stage instruction for realtime interviewing."""

    policy = get_stage_policy(stage)
    base = INTERVIEW_STAGE_GUIDANCE.get(policy.code, "请保持真实、自然、专业的面试官口吻推进当前环节。")
    goal = stage_goal.strip() if stage_goal else policy.goal

    evidence_items: list[str]
    if isinstance(missing_evidence, str):
        evidence_items = _normalize_text_list(missing_evidence)
    elif isinstance(missing_evidence, (list, tuple)):
        evidence_items = [str(item).strip() for item in missing_evidence if str(item).strip()]
    else:
        evidence_items = []
    evidence_text = "、".join(evidence_items) if evidence_items else "候选人的真实职责、技术判断、结果证据"

    if policy.code == "S7":
        return (
            f"{base}\n"
            f"当前阶段目标：{goal}\n"
            f"公司信息：{company_info or '结合现有上下文，自然介绍团队、业务和岗位。'}\n"
            "介绍时重点放在我们现在做什么、团队状态、岗位职责、入职后会接触什么，口语化、简洁，不要照读资料。"
        )

    details = (
        f"{base}\n"
        f"当前阶段目标：{goal}\n"
        f"当前重点问题：{current_question or '请围绕当前简历重点继续提问。'}\n"
        f"期望获取的信息：{expected_signal or evidence_text}\n"
        f"当前缺失证据：{evidence_text}\n"
        f"当前难度档位：{difficulty_level}\n"
        f"下一题参考：{next_question or '如果当前话题已经拿到足够证据，就自然切到下一题。'}\n"
        "每次只推进一个明确话题。如果候选人回答模糊，优先补场景、职责、做法、原因、结果和指标。"
    )

    if transition_reason:
        details += f"\n当前转场背景：{transition_reason}"
    if is_last_followup and policy.code in {"S4", "S5", "S6"}:
        details += "\n这已经是当前问题最后一次追问机会，拿到关键信息后就准备转场。"
    if difficulty_level == "fallback":
        details += "\n候选人当前有吃力迹象，优先从基础原理、常见场景或相近经验切入。"

    return details


DEFAULT_PROMPT_LIBRARY: dict[tuple[str, str], PromptTemplate] = {
    ("resume_parse", "v1"): PromptTemplate(
        task_key="resume_parse",
        version="v1",
        system_prompt="你是招聘简历解析助手，必须输出严格 JSON，不输出多余文本。",
        user_template="请解析以下简历文本并提取结构化字段：\n{resume_text}",
    ),
    ("candidate_score", "v1"): PromptTemplate(
        task_key="candidate_score",
        version="v1",
        system_prompt="你是候选人评估助手，必须输出严格 JSON。",
        user_template="岗位要求：{job_requirements}\n候选人信息：{candidate_profile}",
    ),
    ("intent_classify", "v1"): PromptTemplate(
        task_key="intent_classify",
        version="v1",
        system_prompt="你是招聘会话意图识别助手，必须输出 JSON。",
        user_template="消息内容：{message}",
    ),
    ("reply_generate", "v1"): PromptTemplate(
        task_key="reply_generate",
        version="v1",
        system_prompt="你是招聘会话回复助手，必须输出 JSON。",
        user_template="候选人消息：{message}\n意图：{intent}",
    ),
    ("interview_question_set", "v1"): PromptTemplate(
        task_key="interview_question_set",
        version="v1",
        system_prompt="你是结构化面试题生成助手。必须输出 JSON，字段为 questions[{question,dimension,expected_signal,followup_condition}]。",
        user_template="语言：{language}\n岗位要求：{job_requirements}\n简历文本：{resume_text}\n技能：{skills}\n题目数：{question_count}",
    ),
    ("interview_question_set", "v2"): PromptTemplate(
        task_key="interview_question_set",
        version="v2",
        system_prompt=(
            "你是结构化技术面试设计助手。请基于候选人简历和岗位要求，设计一组贴近真实面试场景的问题。\n\n"
            "生成原则：\n"
            "1. 严格贴合简历和 JD，不要生成泛泛而谈的通用题。\n"
            "2. 面试流程要自然，优先覆盖：自我介绍切入、技术栈核验、项目深挖、实习职责追问、岗位匹配追问。\n"
            "3. 简历明确写过的项目、技术和职责可以深挖；简历没体现的冷门点不要生硬拔高。\n"
            "4. 难度保持真实中等偏上，重点评估真实性、理解深度、解决问题能力和岗位匹配度，不以问倒人为目标。\n"
            "5. 问题要像真实面试官会问的话，避免书面化、教材化。\n"
            "6. 题目长度要有变化，不要全部一样短，也不要连续出现很多长题。整体上以自然口语为准。\n"
            "7. 中文题目优先控制在 18 到 45 个字之间；允许少量题目更短，少量题目稍长，但最长尽量不要超过 60 个字。\n"
            "8. 不要在一个题目里塞入太多背景、限制条件和子问题，不要出现“先说A，再说B，再分析C”这种明显过载的长题干。\n"
            "9. 短题也必须是完整有效的问题，不能写成“你会X？”“你了解Y？”这种发问残句；短题也要能直接用于真实面试。\n"
            "10. 如果需要追问，把追问内容放到 followup_condition，不要堆到 question 正文里。\n"
            "11. 阶段配额必须严格遵守，不能把 S2/S4/S5/S6/S7 的题目都堆到 S3。\n"
            "12. 默认 14 道题时，按以下阶段配额输出：S2=1，S3=8，S4=2，S5=1，S6=1，S7=1。\n"
            "13. 技术栈核验阶段必须比普通面试更充分，S3 需要重点生成 8 到 9 道题，并按以下结构分配："
            "2 道围绕候选人简历里最核心的主技术栈，"
            "2 道围绕项目里真实用过的中间件、数据库或缓存，"
            "1 到 2 道围绕系统设计、性能优化、故障排查，"
            "3 道围绕岗位 JD 的关键要求补齐。"
            "这些题必须都贴着简历经历和岗位要求来问，不能写成通用八股题。\n"
            "14. 如果总题量不足以完整覆盖上述结构，优先保留 S3 的结构完整性，但仍要保留 S2/S4/S5/S6/S7 的最小覆盖。\n"
            "15. 输出严格 JSON，字段为 questions[{stage,question,dimension,expected_signal,max_followups,success_signals,followup_condition}]。"
        ),
        user_template=(
            "语言：{language}\n"
            "岗位要求：{job_requirements}\n"
            "简历文本：{resume_text}\n"
            "技能：{skills}\n"
            "题目数：{question_count}\n"
            "建议总题量不少于 14，道数不足时优先保证技术栈核验阶段的 8 到 9 道结构化问题。"
        ),
    ),
    ("interview_followup", "v1"): PromptTemplate(
        task_key="interview_followup",
        version="v1",
        system_prompt="你是实时面试追问助手。必须输出 JSON，字段为 followup_question,reason,policy_flags,confidence。",
        user_template=(
            "语言：{language}\n"
            "阶段：{stage}\n"
            "候选人回答：{answer}\n"
            "置信度：{confidence}\n"
            "追问目标：补齐证据、量化结果、澄清风险。"
        ),
    ),
    ("interview_followup", "v2"): PromptTemplate(
        task_key="interview_followup",
        version="v2",
        system_prompt="你是实时面试追问助手。请直接输出针对候选人回答的简短追问，不要包含 JSON 或任何标签。",
        user_template=(
            "语言：{language}\n"
            "阶段：{stage}\n"
            "候选人回答：{answer}\n"
            "反馈：{confidence}"
        ),
    ),
    ("interview_followup", "v3"): PromptTemplate(
        task_key="interview_followup",
        version="v3",
        system_prompt=(
            "你是实时面试追问助手。请直接输出一句简短追问，不要输出 JSON。"
            "你必须围绕当前题目目标追问证据、指标、个人贡献和风险澄清。"
        ),
        user_template=(
            "语言：{language}\n"
            "阶段：{stage}\n"
            "当前题目：{current_question}\n"
            "期望信号：{expected_signal}\n"
            "候选人回答：{answer}\n"
            "最近上下文：{last_turns_summary}\n"
            "置信度：{confidence}"
        ),
    ),
    ("interview_followup", "v4"): PromptTemplate(
        task_key="interview_followup",
        version="v4",
        system_prompt=(
            "你是一位专业、自然、有亲和力的 AI 面试官。"
            "你的任务是根据候选人最新的一句话，给出下一句最合适的自然回应。"
            "如果回答已经完整，就自然切到下一题；如果回答模糊，就追问具体细节、结果或个人贡献。"
            "直接输出你说的话，不要输出 JSON，不要加任何前缀标签，长度控制在 1 到 2 句话。"
        ),
        user_template=(
            "语言：{language}\n"
            "当前面试阶段：{stage}\n"
            "当前提问方向：{current_question}\n"
            "期望信号：{expected_signal}\n"
            "最近对话历史（最新在下）：\n{last_turns_summary}\n"
            "候选人刚说：{answer}\n"
            "{next_question_section}\n"
            "请做出自然的面试官回应："
        ),
    ),
    ("interview_followup", "v5"): PromptTemplate(
        task_key="interview_followup",
        version="v5",
        system_prompt=INTERVIEW_SYSTEM_PROMPT,
        user_template=(
            "语言：{language}\n"
            "当前阶段：{stage}\n"
            "当前问题：{current_question}\n"
            "期望信号：{expected_signal}\n"
            "最近对话：\n{last_turns_summary}\n"
            "候选人刚刚说：{answer}\n"
            "{next_question_section}\n"
            "请给出此刻最自然的面试官回应："
        ),
    ),
}


def get_prompt_template(task_key: str, version: str) -> PromptTemplate:
    """Return prompt template with v1 fallback."""

    template = DEFAULT_PROMPT_LIBRARY.get((task_key, version))
    if template:
        return template
    fallback = DEFAULT_PROMPT_LIBRARY.get((task_key, "v1"))
    if fallback:
        return fallback
    raise KeyError(f"Prompt template not found for task={task_key}")
