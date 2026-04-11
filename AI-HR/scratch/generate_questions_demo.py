import sys
import os
import json
import uuid
from pathlib import Path

# Setup path to include project root for imports
project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from ai_hr.core.config import get_settings
from ai_hr.services.llm.client import LLMClient, InvokeContext
from ai_hr.services.llm.router import ModelRouter
from ai_hr.services.llm.guardrails import GuardrailService
from ai_hr.services.llm.prompts import get_prompt_template
from ai_hr.domain.constants import PromptTaskKey

def main():
    # 0. Set environment variable to use the specific env file
    os.environ["AI_HR_ENV"] = "dev"
    
    settings = get_settings()
    router = ModelRouter(settings=settings)
    guardrail = GuardrailService()
    client = LLMClient(router=router, guardrail_service=guardrail)
    
    print("=== 面试题目生成演示 ===")
    
    # 1. Load Resume (测试文本简历)
    resume_path = project_root / "data" / "测试文本简历"
    if not resume_path.exists():
        print(f"错误: 找不到简历文件 {resume_path}")
        return
        
    with open(resume_path, "r", encoding="utf-8") as f:
        resume_text = f.read()
    
    print(f"已加载简历: {resume_path.name}")
        
    # 2. Define JD (Sample Java Backend)
    job_title = "Java 后端开发工程师"
    job_requirements = """
    1. 计算机及相关专业本科以上学历，实习生。
    2. 了解 Java 基础、JVM、多线程编程及常用设计模式。
    3. 了解 Spring Boot, Spring Cloud, MyBatis 等主流框架原理方案。
    4. 了解 MySQL、Redis、RabbitMQ/RocketMQ 等中间件，并有性能调优经验。
    5. 具备分布式系统的设计和开发经验，熟悉分布式事务、限流、熔断等机制。
    6. 具有良好的沟通能力和团队合作精神，能够独立解决复杂技术问题。
    """
    
    print(f"目标岗位: {job_title}")
    
    # 3. Resolve and Render Prompt Template (v4)
    try:
        template = get_prompt_template(PromptTaskKey.INTERVIEW_QUESTION_SET, "v4")
        rendered = template.render(
            language="zh",
            job_title=job_title,
            job_requirements=job_requirements,
            resume_text=resume_text[:3000],
            skills=["Java", "Spring Cloud", "MySQL", "Redis", "RabbitMQ", "Netty", "Seata"],
            question_count=14,
        )
    except Exception as e:
        print(f"渲染模板失败: {e}")
        return
        
    prompt = f"{template.system_prompt}\n{rendered}"
    
    # 4. Invoke LLM
    print(f"正在使用模型 [{settings.llm_model}] 生成题目 (基于 v4 Prompt)...")
    
    context = InvokeContext(
        task_key=PromptTaskKey.INTERVIEW_QUESTION_SET,
        trace_id=f"demo-gen-{uuid.uuid4().hex[:6]}",
        prompt=prompt,
        entity_type="demo_candidate",
        entity_id="酒敬哲",
    )
    
    import time
    start_time = time.time()
    try:
        # We use invoke instead of invoke_json to bypass the restrictive InterviewQuestionSetLLMOutput validator
        # as the v4 prompt produces more fields than the contract currently supports.
        result = client.invoke(context)
        raw_text = result.content.get("text", "")
    except Exception as e:
        print(f"调用 LLM 失败: {e}")
        return
    
    # 5. Process and Display Results
    try:
        # Manually parse JSON from the raw text
        # The LLM output usually contains the JSON block
        import re
        json_match = re.search(r"\{[\s\S]*\}", raw_text)
        if json_match:
            data = json.loads(json_match.group(0))
        else:
            data = json.loads(raw_text)
            
        questions = data.get("questions", [])
        print(f"\n生成成功! 耗时: {time.time() - start_time:.2f}s")
        print(f"总计生成题目: {len(questions)} 道")
        
        # Save to data directory for preview
        output_path = project_root / "data" / "generated_questions_demo.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"详细题目已保存至: {output_path}")
        print("\n--- 题目预览 ---")
        for i, q in enumerate(questions, 1):
            bucket = q.get('bucket', 'Unknown')
            stage = q.get('stage', 'Unknown')
            module = q.get('module', '')
            question_text = q.get('question', '')
            print(f"{i:2d}. [{stage}] [{bucket:10s}] {module + ': ' if module else ''}{question_text}")
    except Exception as e:
        print(f"\n解析生成的题目失败: {e}")
        print("未加工的输出内容:")
        print(raw_text)

if __name__ == "__main__":
    main()
