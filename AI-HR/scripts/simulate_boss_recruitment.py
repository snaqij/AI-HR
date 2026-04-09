import sys
import os
import json
from datetime import datetime
from unittest.mock import MagicMock

# 确保项目路径在 sys.path 中
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from ai_hr.connectors.boss import BossConnector, ConnectorCredentials
from ai_hr.services.ai_reply_llm import AIReplyLLMService
from ai_hr.schemas.ai_reply import AIIntentClassifyResult

def run_boss_simulation():
    print("="*60)
    print("🚀 BOSS 平台自动化招聘流 - 功能模拟测试开始")
    print("="*60)

    # 1. 初始化连接器 (Mock 模式)
    credentials = ConnectorCredentials(
        account="test-hr-id",
        secret="test-secret",
        mode="mock"
    )
    connector = BossConnector(credentials)

    # --- Step 1: 发岗位 (Publish Job) ---
    print("\n[Step 1] 正在向 BOSS 发布新岗位...")
    job_payload = {
        "title": "高级后端工程师 (AI 方向)",
        "requirements": "精通 Python, 熟悉分布式架构和 LLM 集成。",
        "city": "北京",
        "salary_range": "30k-50k"
    }
    publish_result = connector.publish_job(job_payload)
    external_job_id = publish_result.external_job_id
    print(f"✅ 岗位发布成功! 平台 ID: {external_job_id}")

    # --- Step 2: 收简历 (Get Applicants) ---
    print("\n[Step 2] 正在拉取该岗位的最新投递简历...")
    applicants = connector.list_applicants(external_job_id)
    items = applicants.get("items", [])
    print(f"✅ 成功抓取到 {len(items)} 份简历:")
    for cand in items:
        print(f"   - 候选人: {cand['name']} | 核心技能: {cand['resume_text']}")

    # --- Step 3: 自动回复 (Auto-Reply Simulation) ---
    target_candidate = items[0]
    cand_id = target_candidate["external_candidate_id"]
    conv_id = f"conv-{cand_id}"
    
    print(f"\n[Step 3] 模拟候选人 {target_candidate['name']} 发来消息...")
    user_message = "你好，请问你们公司对 Python 异步编程要求高吗？"
    print(f"💬 候选人: \"{user_message}\"")

    # 准备 AI 回复服务 (使用 Mock Session 绕过数据库)
    mock_session = MagicMock()
    # 模拟 LLM 行为 (因为 llm_provider 目前也是 mock)
    reply_service = AIReplyLLMService(mock_session)
    
    print("\n[AI 思考中] 正在进行意图分类与回复生成...")
    # 在 mock 模式下，LLM 可能会返回 fallback。我们这里演示逻辑闭环。
    reply_result = reply_service.generate_reply_result(
        conversation_id=conv_id,
        message=user_message
    )

    print(f"💡 AI 判定意图: {reply_result.intent} (置信度: {reply_result.confidence})")
    print(f"🤖 AI 生成回复: \"{reply_result.reply_text or '收到，我会反馈给技术负责人。'}\"")

    # --- Step 4: 发送消息 (Send Message) ---
    print("\n[Step 4] 正在将回复同步至 BOSS 聊天窗口...")
    send_result = connector.send_message(conv_id, reply_result.reply_text or "收到。")
    print(f"✅ 消息发送成功! 消息 ID: {send_result['message_id']}")

    print("\n" + "="*60)
    print("🎉 BOSS 平台全链路功能模拟测试完成!")
    print("="*60)

if __name__ == "__main__":
    run_boss_simulation()
