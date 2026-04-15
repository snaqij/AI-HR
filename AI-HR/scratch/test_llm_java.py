import os
import sys

sys.path.insert(0, os.path.abspath('.'))
os.environ["PYTHONUTF8"] = "1"

from ai_hr.core.config import get_settings
settings = get_settings()

from ai_hr.services.llm.client import LLMClient, InvokeContext
from ai_hr.services.llm.router import ModelRouter
from ai_hr.services.llm.guardrails import GuardrailService
from ai_hr.domain.constants import PromptTaskKey
from ai_hr.services.llm.prompts import get_prompt_template

router = ModelRouter(runtime_repository=None, settings=settings)
llm_client = LLMClient(router=router, guardrail_service=GuardrailService(), observability_repository=None)

template = get_prompt_template(
    task_key=PromptTaskKey.INTERVIEW_QUESTION_SET,
    version="v4"
)
rendered = template.render(
    language="zh-CN",
    job_title="Java开发实习生",
    job_requirements=(
        "1. 计算机或相关专业本科及以上学历在读生。\n"
        "2. 热爱编程，具备扎实的Java语言基础，了解JVM、多线程及集合框架。\n"
        "3. 熟悉Spring、Spring Boot、MyBatis等主流应用开发框架优先。\n"
        "4. 熟悉关系型数据库（MySQL）的基本使用，了解常用SQL优化。\n"
        "5. 有较强的逻辑分析能力和系统除错能力，能快速适应新领域和学习新技术。\n"
        "6. 重点考察：基础技术功底、项目实践的真实度、以及遇到 Bug 时真实的解决思路。"
    ),
    resume_text="酒敬哲：酒敬哲 电话：16639783713（微信同号） 教育经历 2023.9-2027.6 河南科技学院... 熟悉Java...",
    skills=["Java", "Spring", "MySQL", "Redis"],
    question_count=14,
)

context = InvokeContext(
    task_key=PromptTaskKey.INTERVIEW_QUESTION_SET,
    trace_id="test-trace",
    prompt=f"{template.system_prompt}\n{rendered}",
    entity_type="session",
    entity_id="test-session",
)
import time
t = time.time()
response = llm_client.invoke(context)
print(f"LLM Response Time: {time.time()-t:.2f}s")
raw_text = response.content.get("text", "") if response.content else ""
print("==== RAW OUTPUT ====")
print(raw_text[:1000]) # only print first 1000 chars

# simulate parsing using the ai_interviews service
from ai_hr.services.ai_interviews import AIInterviewService
# mock the service dependencies since _parse_questions_from_llm_text doesn't use self anyway
questions = AIInterviewService._parse_questions_from_llm_text(None, raw_text=raw_text, session_id="test")
print(f"Parsed {len(questions)} questions")
