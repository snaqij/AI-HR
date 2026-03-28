"""Prompt 模板与渲染。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    """Prompt 模板定义。"""

    task_key: str
    version: str
    system_prompt: str
    user_template: str

    def render(self, **kwargs) -> str:
        """渲染用户输入部分。"""
        return self.user_template.format(**kwargs)


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
        system_prompt="你是实时面试追问助手。请直接输出针对候选人回答的简短追问，不要包含 JSON 或任何标签。目标：补齐证据、量化结果。",
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
            "你是一位专业、自然、有亲和力的AI面试官。"
            "你的任务是根据候选人最新的一句话，做出最恰当的自然语言回应。"
            "回应规则：\n"
            "- 如果候选人在打招呼或寒暄，请自然回应并简短引导进入面试\n"
            "- 如果候选人在做自我介绍，请适当鼓励并追问感兴趣的细节\n"
            "- 如果候选人在陈述项目经历，请追问具体细节、成果或个人贡献\n"
            "- 如果候选人的回答已经完整，则直接提出下一个问题（使用 next_question）\n"
            "直接输出你说的话，不要输出JSON，不要加任何前缀标签，长度1-2句话。"
        ),
        user_template=(
            "语言：{language}\n"
            "当前面试阶段：{stage}\n"
            "当前提问方向：{current_question}\n"
            "期望信号：{expected_signal}\n"
            "最近对话历史（最新在下）：\n{last_turns_summary}\n"
            "候选人刚说：{answer}\n"
            "{next_question_section}"
            "请做出自然的面试官回应："
        ),
    ),
}


def get_prompt_template(task_key: str, version: str) -> PromptTemplate:
    """获取 Prompt 模板，缺省回退到 v1。"""
    template = DEFAULT_PROMPT_LIBRARY.get((task_key, version))
    if template:
        return template
    fallback = DEFAULT_PROMPT_LIBRARY.get((task_key, "v1"))
    if fallback:
        return fallback
    raise KeyError(f"Prompt template not found for task={task_key}")
