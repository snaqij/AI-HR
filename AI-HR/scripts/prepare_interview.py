import json
import sys
from pathlib import Path

import pypdf

# 路径设置
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from ai_hr.core.config import get_settings
from ai_hr.services.llm.client import LLMClient, InvokeContext
from ai_hr.services.llm.router import ModelRouter


def extract_text_from_pdf(pdf_path):
    """从 PDF 中提取文本"""
    text = ""
    try:
        with open(pdf_path, "rb") as f:
            reader = pypdf.PdfReader(f)
            for page in reader.pages:
                text += page.extract_text() + "\n"
    except Exception as e:
        print(f"Error extracting PDF {pdf_path}: {e}")
    return text

def generate_questions(resume_text, settings):
    """使用 LLM 生成面试问题"""
    # 初始化 LLMClient (简单起见，这里不依赖复杂的 DB 路由)
    router = ModelRouter(runtime_repository=None, settings=settings)
    client = LLMClient(router=router)

    system_prompt = (
        "你是一名顶级大厂的技术面试专家。请基于提供的简历文本，生成 12-15 个结构化面试锚点题。\n"
        "这些题目必须严格对应以下三个核心技术考察阶段：\n"
        "S6: 边界与压力测试 (考察复杂场景下的稳定性、性能极限或容灾设计)\n\n"
        "输出格式必须为 JSON 列表，每个对象示例：\n"
        "{\n"
        "  \"stage\": \"S4\",\n"
        "  \"topic\": \"分布式事务\",\n"
        "  \"question\": \"请结合项目阐述 Seata AT 模式原理...\",\n"
        "  \"success_signals\": [\"二阶段提交\", \"行锁\", \"回滚日志\"],\n"
        "  \"difficulty\": 8,\n"
        "  \"technical_context\": \"候选人简历提到使用 Seata 解决跨服务一致性问题\"\n"
        "}\n\n"
        "请确保问题极其硬核，符合专家级面试标准，严禁空泛或通用。"
    )

    user_prompt = (
        "请基于以下简历内容，根据 System Prompt 的定义生成 12-15 个面试锚点题。\n"
        "注意：严禁重复简历正文，直接输出包含 S4/S5/S6 阶段题目的 JSON 列表。\n\n"
        f"--- 简历文本 ---\n{resume_text}"
    )

    context = InvokeContext(
        task_key="interview_question_set",
        trace_id="prepare_interview_script",
        prompt=user_prompt,
        system_prompt=system_prompt
    )

    print("正在调用 LLM 生成题目...")
    result = client.invoke(context) # 使用文本模式
    
    raw_text = result.content.get("text", "")
    print(f"LLM 原始输出长度: {len(raw_text)}")

    # 更鲁棒的 JSON 提取逻辑
    import re
    try:
        # 匹配最外层的 [ ] 或 { }
        match = re.search(r"(\[[\s\S]*\]|\{[\s\S]*\})", raw_text)
        if match:
            json_str = match.group(1)
            # 移除可能的 Markdown 标记
            json_str = re.sub(r"```json\s*", "", json_str)
            json_str = re.sub(r"```\s*", "", json_str)
            data = json.loads(json_str.strip())
            
            if isinstance(data, dict) and "questions" in data:
                return data["questions"]
            if isinstance(data, list):
                return data
        else:
            print("LLM 输出中未发现有效的 JSON 格式。")
    except Exception as e:
        print(f"解析位 JSON 出错: {e}")
        # 如果解析失败，打印前 200 个字方便调试
        print(f"原始输出片段: {raw_text[:200]}...")

    # 如果分析失败，返回一个默认值
    print("使用预设 Mock 问题。")
    return [
        {"stage": "P2", "question": "请介绍一下你简历中提到的核心项目及其业务价值。", "expected_signal": "业务目标、架构图、个人贡献", "followup_suggestion": "追问项目中的技术难点"},
        {"stage": "P3", "question": "在你的 Java 项目中，是如何调优 JVM 参数的？", "expected_signal": "GC算法、内存分代、Dump分析", "followup_suggestion": "追问具体遇到过的 OOM 场景"},
        {"stage": "P3", "question": "Redis 在你的项目中主要解决什么问题？如何保证缓存一致性？", "expected_signal": "延迟双删、监听Binlog、分布式锁", "followup_suggestion": "追问缓存雪崩/击穿的预防方案"},
        {"stage": "P4", "question": "项目中遇到过最难解决的线上 Bug 是什么？你是如何定位和复盘的？", "expected_signal": "排查工具(arthas/jstack)、复盘机制", "followup_suggestion": "追问预防类似问题的自动化手段"}
    ]

def main():
    settings = get_settings()
    data_dir = PROJECT_ROOT / "data"
    output_file = data_dir / "interview_questions.json"

    # 寻找简历 (PDF 或 文本)
    pdfs = list(data_dir.glob("*.pdf"))
    text_files = list(data_dir.glob("测试文本简历*")) or list(data_dir.glob("*.txt"))
    
    resume_text = ""
    if text_files:
        print(f"找到文本简历: {text_files[0].name}")
        with open(text_files[0], "r", encoding="utf-8") as f:
            resume_text = f.read()
    elif pdfs:
        print(f"找到 PDF 简历: {pdfs[0].name}")
        resume_text = extract_text_from_pdf(pdfs[0])
    else:
        print("未在 data 目录下找到任何简历 (PDF 或 TXT)。")
        return
    
    if not resume_text.strip():
        print("未能提取到有效的简历文本。")
        return

    # 截断过长的简历文本
    if len(resume_text) > 8000:
        print(f"检测到简历文本过长 ({len(resume_text)} 字)，正在截断至 8000 字...")
        resume_text = resume_text[:8000]

    questions = generate_questions(resume_text, settings)
    
    # 写入 JSON
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(questions, f, ensure_ascii=False, indent=4)

    print(f"成功生成题库并保存至: {output_file}")

if __name__ == "__main__":
    main()
