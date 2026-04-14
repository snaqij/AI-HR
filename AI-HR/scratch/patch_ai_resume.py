import sys
import os

path = r'd:\24985\code\boss-cli-main\AI-HR\ai_hr\services\ai_resume.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Target 1: _resolve_candidate_email_from_resume
target1 = """    def _resolve_candidate_email_from_resume(self, *, resume_text: str, raw_profile: dict[str, Any]) -> str | None:
        email = self._extract_email_from_profile(raw_profile)
        if email:
            return email
        return self._extract_email_from_text(resume_text)"""

replacement1 = """    def _resolve_candidate_email_from_resume(self, *, resume_text: str, raw_profile: dict[str, Any]) -> str | None:
        # 1. 优先从三方画像中提取
        email = self._extract_email_from_profile(raw_profile)
        if email:
            return email
            
        # 2. 启发式正则提取 (快速且高频)
        email = self._extract_email_from_text(resume_text)
        if email:
            return email
            
        # 3. LLM 兜底解析 (处理混淆、错位或非标准格式)
        if self._is_llm_enabled() and resume_text.strip():
            # 仅取简历开头和结尾，联系方式通常出现在该位置
            sample = resume_text[:2000] + "\\n...\\n" + resume_text[-1000:] if len(resume_text) > 3000 else resume_text
            try:
                from .llm.prompts import PromptTaskKey, get_prompt_template
                from .llm.client import InvokeContext
                import uuid
                template = get_prompt_template(PromptTaskKey.CONTACT_EXTRACT, "v1")
                prompt = "\\n".join([template.system_prompt, template.render(text_context=sample)])
                result = self._llm_client.invoke_json(
                    InvokeContext(
                        task_key=PromptTaskKey.CONTACT_EXTRACT,
                        trace_id=str(uuid.uuid4()),
                        prompt=prompt,
                    )
                )
                if not result.fallback_used and result.content.get("email"):
                    llm_email = str(result.content["email"]).strip().lower()
                    if self._looks_like_email(llm_email):
                        return llm_email
            except Exception:
                pass

        return None"""

# Target 2: _extract_email_from_profile
# Use a more generic match to avoid encoding issues with 閭
import re
pattern2 = re.compile(r'    def _extract_email_from_profile\(self, raw_profile: dict\[str, Any\]\) -> str \| None:.*?return None', re.DOTALL)
replacement2 = """    def _extract_email_from_profile(self, raw_profile: dict[str, Any]) -> str | None:
        if not isinstance(raw_profile, dict):
            return None
        # 增加对常见中文标签的支持
        for key in ("email", "mail", "contact_email", "邮箱", "电子邮箱"):
            value = raw_profile.get(key)
            if isinstance(value, str):
                parsed = self._extract_email_from_text(value)
                if parsed:
                    return parsed
        return None"""

# Target 3: _extract_email_from_text
target3 = """    def _extract_email_from_text(self, text: str) -> str | None:
        if not text:
            return None
        match = re.search(r"\\b[a-zA-Z0-9._%+\\-]+@[a-zA-Z0-9.\\-]+\\.[A-Za-z]{2,}\\b", text)
        if not match:
            return None
        return match.group(0).strip().lower()"""

replacement3 = """    def _extract_email_from_text(self, text: str) -> str | None:
        if not text:
            return None
        # 优化正则：支持更多后缀，处理某些混淆情况
        pattern = r"\\b[a-zA-Z0-9._%+\\-]+@[a-zA-Z0-9.\\-]+\\.[A-Za-z]{2,6}\\b"
        match = re.search(pattern, text)
        if match:
            return match.group(0).strip().lower()
        
        # 处理 (at) 等混淆格式
        confused = re.search(r"\\b[a-zA-Z0-9._%+\\-]+(?:\\(at\\)|@)[a-zA-Z0-9.\\-]+\\.(?:[A-Za-z]{2,6})\\b", text, re.IGNORECASE)
        if confused:
            return confused.group(0).replace("(at)", "@").strip().lower()

        return None

    def _looks_like_email(self, value: str) -> bool:
        return bool(re.match(r"^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", value.strip()))"""

new_content = content.replace(target1, replacement1)
new_content = pattern2.sub(replacement2, new_content)
new_content = new_content.replace(target3, replacement3)

if new_content != content:
    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("SUCCESS")
else:
    print("FAILURE: No replacement made")
