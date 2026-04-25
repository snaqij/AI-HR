"""Centralized prompt policy and prompt builders."""

from __future__ import annotations

from dataclasses import dataclass

from ai_hr.domain.constants import InterviewStage, PromptTaskKey
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
    "你是一名真实、专业、简洁的技术面试官。"
    "你的目标是通过连续对话判断候选人的真实性、技术深度、问题解决能力和岗位匹配度。"
    "请使用口语化表达，单轮只问一个清晰问题，不要堆叠子问题。"
)

INTERVIEW_STAGE_GUIDANCE: dict[str, str] = {
    InterviewStage.OPENING: "当前是开场确认阶段，快速确认沟通状态后进入正式面试。",
    InterviewStage.SELF_INTRO: "当前是自我介绍阶段，聚焦最近经历、核心项目与角色定位。",
    InterviewStage.TECH_STACK: "当前是技术栈核验阶段，验证简历中的真实技术使用。",
    InterviewStage.PROJECT_DEEP_DIVE: "当前是项目深挖阶段，追问目标、职责、难点、取舍与结果。",
    InterviewStage.JD_MATCH: "当前是经历与岗位匹配阶段，确认岗位相关能力证据。",
    InterviewStage.GENERAL_PROBE: "当前是综合能力补充阶段，补齐尚未确认的能力证据。",
    InterviewStage.COMPANY_QA: "当前是公司介绍与候选人反问阶段，介绍团队和岗位并回答问题。",
    InterviewStage.CLOSING: "当前是收尾阶段，简短结束并说明后续流程。",
}


def _normalize_text_list(raw: str) -> list[str]:
    parts = raw.replace("；", ",").replace("。", ",").split(",")
    return [item.strip() for item in parts if item.strip()]


def build_interview_company_intro(company_info: str = "") -> str:
    """Convert company profile text into interviewer-style introduction."""

    raw = (company_info or "").strip()
    if not raw:
        return "技术部分先到这里。我简单介绍下团队和岗位，你有问题可以直接问。"
    condensed = " ".join(line.strip() for line in raw.splitlines() if line.strip())
    if len(condensed) > 240:
        condensed = condensed[:240].rstrip("，；。") + "。"
    return f"技术部分先到这里。补充下公司和岗位背景：{condensed}"


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
    question_type: str = "",
    focus_experience: str = "",
    focus_module: str = "",
    active_topic_name: str = "",
    active_topic_rounds: int = 0,
    must_transition: bool = False,
    candidate_requested_move_on: bool = False,
    flow_reason: str = "",
) -> str:
    """Build a stable stage-aware instruction for realtime interviewing."""

    policy = get_stage_policy(stage)
    base = INTERVIEW_STAGE_GUIDANCE.get(policy.code, "Keep interview natural and stage-aware.")
    goal = stage_goal.strip() if stage_goal else policy.goal

    evidence_items: list[str]
    if isinstance(missing_evidence, str):
        evidence_items = _normalize_text_list(missing_evidence)
    elif isinstance(missing_evidence, (list, tuple)):
        evidence_items = [str(item).strip() for item in missing_evidence if str(item).strip()]
    else:
        evidence_items = []
    evidence_text = "; ".join(evidence_items) if evidence_items else "候选人贡献、决策依据、可量化结果"

    if policy.code == InterviewStage.COMPANY_QA:
        return (
            f"{base}\n"
            f"Stage goal: {goal}\n"
            f"Company info: {company_info or 'Introduce team/business/role naturally.'}\n"
            "请口语化介绍团队和岗位，不要照读原文；缺失信息直接说明待确认，不要编造。"
        )

    details = (
        f"{base}\n"
        f"Stage goal: {goal}\n"
        f"Current target question: {current_question or 'Continue on stage objective.'}\n"
        f"Expected evidence: {expected_signal or evidence_text}\n"
        f"Missing evidence: {evidence_text}\n"
        f"Difficulty: {difficulty_level}\n"
        f"Question type: {question_type or 'unknown'}\n"
        f"Focus experience: {focus_experience or 'not_locked'}\n"
        f"Focus module: {focus_module or 'not_locked'}\n"
        f"Active topic: {active_topic_name or 'unnamed'}\n"
        f"Topic round: {max(0, int(active_topic_rounds or 0))}\n"
        f"Next question reference: {next_question or 'Move on when enough evidence is collected.'}\n"
        "单轮只问一个问题，优先短句，避免提示答案和多层追问。"
    )

    if transition_reason:
        details += f"\nTransition context: {transition_reason}"
    if flow_reason:
        details += f"\nFlow reason: {flow_reason}"
    if must_transition:
        details += "\nYou must transition in this turn."
    if candidate_requested_move_on:
        details += "\nCandidate requested to move on; do not insist on current topic."
    if is_last_followup:
        details += "\nThis is the last follow-up chance on this topic."
    if difficulty_level == "fallback":
        details += "\nCandidate is struggling: lower difficulty and anchor to fundamentals."

    return details


DEFAULT_PROMPT_LIBRARY: dict[tuple[str, str], PromptTemplate] = {
    (PromptTaskKey.RESUME_PARSE, "v1"): PromptTemplate(
        task_key=PromptTaskKey.RESUME_PARSE,
        version="v1",
        system_prompt="你是招聘简历解析助手，必须输出严格 JSON。",
        user_template="请解析以下简历文本并提取结构化字段：\n{resume_text}",
    ),
    (PromptTaskKey.CANDIDATE_SCORE, "v1"): PromptTemplate(
        task_key=PromptTaskKey.CANDIDATE_SCORE,
        version="v1",
        system_prompt="你是候选人评分助手，必须输出严格 JSON。",
        user_template="岗位要求：{job_requirements}\n候选人信息：{candidate_profile}",
    ),
    (PromptTaskKey.CANDIDATE_EVALUATION, "v1"): PromptTemplate(
        task_key=PromptTaskKey.CANDIDATE_EVALUATION,
        version="v1",
        system_prompt=(
            "你是一名具备深厚行业洞察力的资深招聘官。由于当前处于人才竞争激烈的市场环境，你的评价必须具有高度的“商业现实感”。\n"
            "你的目标是基于岗位薪资待遇，判断该候选人在当前人才市场中是否具有竞争力。\n"
            "评价准则：\n"
            "1. 实习生/应届生：重点看学历档次、核心基础能力、技术热情、竞赛及学习潜力。评价要客观，不应以社招标准要求。\n"
            "2. 社招候选人：重点看项目深度、业务落地能力、解决复杂问题的证据、量化产出。严厉识别简历中的“关键词堆砌”和“水分”。\n"
            "3. 市场对标：结合薪资水平，思考该候选人是否属于“高性价比”或“溢价”。如果 15k 的岗位招到了 30k 素质的人，应给予极高评价。\n"
            "只输出 JSON，严禁冗长解释。"
        ),
        user_template=(
            "岗位标题：{job_title}\n"
            "薪资范围：{salary_range}\n"
            "岗位要求：{job_requirements}\n"
            "候选人简历文本：{resume_text}\n"
            "候选人画像：{normalized_profile}\n"
            "已识别风险：{resume_risks}\n\n"
            "请评估字段：\n"
            "- match_score (0-100)\n"
            "- market_competitiveness (0-100)\n"
            "- salary_fit_score (针对给定薪资的匹配度, 0-100)\n"
            "- final_score (加权总分)\n"
            "- recommendation (strong_recommend/recommend/review/reject)\n"
            "- dimension_scores (education, experience, projects, skills, potential)\n"
            "- strengths, weaknesses, highlights (List, 中文)\n"
            "- market_benchmark (一句话点评该候选人在目前市场同等薪资下的竞争力水平)\n"
            "- summary (综合评价，必须真实且具备批判性)"
        ),
    ),
    (PromptTaskKey.CONTACT_EXTRACT, "v1"): PromptTemplate(
        task_key=PromptTaskKey.CONTACT_EXTRACT,
        version="v1",
        system_prompt="你是一名简历联系方式提取专家。请从混乱的文本中精准识别邮箱，输出 JSON {'email': '...'}。如果找不到，输出空。解析混淆格式如 (at) [dot] 等。",
        user_template="简历文本片段：\n{text_context}",
    ),
    (PromptTaskKey.ANSWER_EVALUATION, "v1"): PromptTemplate(
        task_key=PromptTaskKey.ANSWER_EVALUATION,
        version="v1",
        system_prompt="你是一个资深的 AI 评估助手，负责对候选人的单道面试题回答进行多维度的量化评估。必须输出严格的 JSON 格式。",
        user_template=(
            "面试要求（JD）：{job_requirements}\n"
            "考察维度：{dimension}\n"
            "面试阶段：{stage}\n"
            "面试问题：{question_text}\n"
            "候选人回答：{answer_text}\n\n"
            "请评估以下维度（0-100分）：\n"
            "- completeness (完整度)\n"
            "- logic (逻辑性)\n"
            "- evidence (证据密度)\n"
            "- communication (表达沟通能力)\n"
            "- domain_fit (结合岗位要求JD的专业契合度)\n"
            "- confidence (模型打分置信度 0-1)\n"
            "- risk_tags (风险标签，如伪造、合规等，字符串列表)\n"
        ),
    ),
    (PromptTaskKey.INTENT_CLASSIFY, "v1"): PromptTemplate(
        task_key=PromptTaskKey.INTENT_CLASSIFY,
        version="v1",
        system_prompt="你是招聘会话意图识别助手，必须输出 JSON。",
        user_template="消息内容：{message}",
    ),
    (PromptTaskKey.REPLY_GENERATE, "v1"): PromptTemplate(
        task_key=PromptTaskKey.REPLY_GENERATE,
        version="v1",
        system_prompt="你是招聘会话回复助手，必须输出 JSON。",
        user_template="候选人消息：{message}\n意图：{intent}",
    ),
    (PromptTaskKey.INTERVIEW_QUESTION_SET, "v1"): PromptTemplate(
        task_key=PromptTaskKey.INTERVIEW_QUESTION_SET,
        version="v1",
        system_prompt="你是结构化面试题生成助手，输出 JSON questions[]。",
        user_template="语言：{language}\n岗位要求：{job_requirements}\n简历：{resume_text}\n技能：{skills}\n题量：{question_count}",
    ),
    (PromptTaskKey.INTERVIEW_QUESTION_SET, "v2"): PromptTemplate(
        task_key=PromptTaskKey.INTERVIEW_QUESTION_SET,
        version="v2",
        system_prompt="你是结构化技术面试题设计助手，输出 JSON questions[]。",
        user_template="语言：{language}\n岗位要求：{job_requirements}\n简历：{resume_text}\n技能：{skills}\n题量：{question_count}",
    ),
    (PromptTaskKey.INTERVIEW_QUESTION_SET, "v3"): PromptTemplate(
        task_key=PromptTaskKey.INTERVIEW_QUESTION_SET,
        version="v3",
        system_prompt="你是技术面试题设计助手，按简历和 JD 生成可执行问题，输出 JSON。",
        user_template="语言：{language}\n岗位要求：{job_requirements}\n简历：{resume_text}\n技能：{skills}\n题量：{question_count}",
    ),
    (PromptTaskKey.INTERVIEW_QUESTION_SET, "v4"): PromptTemplate(
        task_key=PromptTaskKey.INTERVIEW_QUESTION_SET,
        version="v4",
        system_prompt="你是高质量面试题生成助手，要求严格输出包含 'questions' 数组字段的 JSON 对象，问题需贴合项目证据。",
        user_template="语言：{language}\n{role_context}\n岗位要求：{job_requirements}\n简历：{resume_text}\n技能：{skills}\n题量：{question_count}",
    ),
    (PromptTaskKey.INTERVIEW_FOLLOWUP, "v1"): PromptTemplate(
        task_key=PromptTaskKey.INTERVIEW_FOLLOWUP,
        version="v1",
        system_prompt=INTERVIEW_SYSTEM_PROMPT,
        user_template="阶段：{stage}\n上轮问题：{last_question}\n候选人回答：{candidate_answer}\n目标信号：{expected_signal}",
    ),
    (PromptTaskKey.INTERVIEW_FOLLOWUP, "v2"): PromptTemplate(
        task_key=PromptTaskKey.INTERVIEW_FOLLOWUP,
        version="v2",
        system_prompt=INTERVIEW_SYSTEM_PROMPT,
        user_template="阶段：{stage}\n上轮问题：{last_question}\n候选人回答：{candidate_answer}\n目标信号：{expected_signal}\n追问次数：{followup_count}",
    ),
    (PromptTaskKey.INTERVIEW_FOLLOWUP, "v3"): PromptTemplate(
        task_key=PromptTaskKey.INTERVIEW_FOLLOWUP,
        version="v3",
        system_prompt=INTERVIEW_SYSTEM_PROMPT,
        user_template="阶段：{stage}\n上轮问题：{last_question}\n候选人回答：{candidate_answer}\n目标信号：{expected_signal}\n缺失证据：{missing_evidence}",
    ),
    (PromptTaskKey.INTERVIEW_FOLLOWUP, "v4"): PromptTemplate(
        task_key=PromptTaskKey.INTERVIEW_FOLLOWUP,
        version="v4",
        system_prompt=INTERVIEW_SYSTEM_PROMPT,
        user_template=(
            "阶段：{stage}\n当前题目：{current_question}\n候选人回答：{candidate_answer}\n"
            "目标信号：{expected_signal}\n缺失证据：{missing_evidence}\n过渡原因：{transition_reason}"
        ),
    ),
    (PromptTaskKey.INTERVIEW_FOLLOWUP, "v5"): PromptTemplate(
        task_key=PromptTaskKey.INTERVIEW_FOLLOWUP,
        version="v5",
        system_prompt=INTERVIEW_SYSTEM_PROMPT,
        user_template=(
            "阶段：{stage}\n当前题目：{current_question}\n候选人回答：{candidate_answer}\n"
            "目标信号：{expected_signal}\n缺失证据：{missing_evidence}\n"
            "话题：{active_topic_name}\n轮次：{active_topic_rounds}\n候选人是否请求切题：{candidate_requested_move_on}"
        ),
    ),
}


def get_prompt_template(task_key: str, version: str = "v1") -> PromptTemplate:
    """Return prompt template with v1 fallback."""

    template = DEFAULT_PROMPT_LIBRARY.get((task_key, version))
    if template is not None:
        return template

    fallback = DEFAULT_PROMPT_LIBRARY.get((task_key, "v1"))
    if fallback is not None:
        return fallback

    raise KeyError(f"Prompt template not found: task_key={task_key}, version={version}")
