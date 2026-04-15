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
    job_title="Python Engineer",
    job_requirements="Know python well, good at FastAPI",
    resume_text="Experienced Python Developer for 5 years.",
    skills=["Python", "FastAPI"],
    question_count=14,
)

context = InvokeContext(
    task_key=PromptTaskKey.INTERVIEW_QUESTION_SET,
    trace_id="test-trace",
    prompt=f"{template.system_prompt}\n{rendered}",
    entity_type="session",
    entity_id="test-session",
)

response = llm_client.invoke(context)
raw_text = response.content.get("text", "") if response.content else ""
print("==== RAW OUTPUT ====")
print(raw_text)

# simulate _parse_questions_from_llm_text
import re, json
text = str(raw_text or "").strip()
candidates = [text]
fence_matches = re.findall(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE)
for block in fence_matches:
    candidates.append(block.strip())

first_obj = text.find("{")
last_obj = text.rfind("}")
if first_obj >= 0 and last_obj > first_obj:
    candidates.append(text[first_obj : last_obj + 1])

first_arr = text.find("[")
last_arr = text.rfind("]")
if first_arr >= 0 and last_arr > first_arr:
    candidates.append(text[first_arr : last_arr + 1])

found = False
for candidate in candidates:
    payload = candidate.strip()
    if not payload: continue
    try:
        parsed = json.loads(payload)
        if isinstance(parsed, dict):
            questions = parsed.get("questions", [])
            if isinstance(questions, list):
                print(f"Parsed dict questions: {len(questions)}")
                found = True
        elif isinstance(parsed, list):
            if parsed and all(isinstance(item, dict) for item in parsed):
                print(f"Parsed list questions: {len(parsed)}")
                found = True
    except:
        pass

if not found:
    print("FAILED TO PARSE QUESTIONS!")

