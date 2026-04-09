import sys
import os

# 确保项目路径在 sys.path 中
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from ai_hr.connectors.boss import BossConnector, ConnectorCredentials
from ai_hr.core.config import get_settings

def send_block_message():
    print("="*75)
    print("🚀 BOSS 生产实战：使用 [block/v2] 协议发送邀约...")
    print("="*75)

    settings = get_settings()
    
    # 候选人: 陈坤鲲 的最新 Security ID
    security_id = "yXFTF5FK24SCh-G15mMs1WRuqZONqNvi2V5KvOBjwwabhDn5pXgvEeky1cu4hxjU8OMYkQePbLpJGHNeXoj5zfanj2jvkPfPMOaNY5Ltj1JvT879Pa0cWJZajbIR4gnF-a8viZi4UgwL0FLrAi1HoHsIzI3Glqi-y9cWx9t9bofnKr57KLreKXB1lV57-cq-M42Ag8hEzM8Zpcn0iFLQ5bg~"
    # 职位: Java 的加密 ID
    job_id = "bcdd0ea56ebec9450nZy39q5ElBU"
    
    # 话术内容
    message_content = "你好，陈坤鲲，我是您的 AI 招聘助手。很高兴收到您的简历，我们会尽快评估并安排面试。"

    credentials = ConnectorCredentials(
        account=settings.boss_account,
        secret=settings.boss_secret or "",
        mode="live",
        base_url=settings.boss_base_url,
        cookie_header=settings.boss_cookie_header,
        send_message_path=settings.boss_send_message_path
    )
    
    connector = BossConnector(credentials)

    try:
        print(f"发送动作: 开启对话并回复 [Java] 岗位邀约")
        print(f"目标 SecurityId: {security_id[:30]}...")
        print(f"关联 JobId: {job_id}")
        
        # 现在 send_message 已经支持 job_id 参数
        result = connector.send_message(security_id, message_content, job_id=job_id)
        
        if result.get("status") == "sent":
            print("\n✅ 成功！消息协议已接受。")
            print(f"响应数据: {result.get('raw_payload')}")
        else:
            print("\n⚠️ 协议响应异常。")
            print(f"Raw Response: {result.get('raw_payload')}")
            
    except Exception as e:
        print(f"\n💥 发送异常: {e}")

    print("\n" + "="*75)

if __name__ == "__main__":
    send_block_message()
