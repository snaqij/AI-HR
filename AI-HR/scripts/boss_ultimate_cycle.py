import sys
import os
import time

# 确保项目路径在 sys.path 中
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from ai_hr.connectors.boss import BossConnector, ConnectorCredentials
from ai_hr.core.config import get_settings

def full_cycle_test(candidate_name, msg_text):
    settings = get_settings()
    credentials = ConnectorCredentials(
        account=settings.boss_account,
        secret=settings.boss_secret or "",
        mode="live",
        base_url=settings.boss_base_url,
        cookie_header=settings.boss_cookie_header
    )
    
    connector = BossConnector(credentials)
    
    print("\n" + "="*80)
    print(f"📡 [Phase 1] 正在自动拉取并寻找候选人: {candidate_name}...")
    
    # 1. 动态拉取候选人列表
    payload = {"page": 1, "pageSize": 50}
    # 尝试读取最新的 Java 职位 ID
    java_job_id = "bcdd0ea56ebec9450nZy39q5ElBU" 

    try:
        # 获取好友列表作为冗余搜索源
        discovery_path = "/wapi/zprelation/friend/getBossFriendListV2.json"
        response = connector._send_live_request(
            connector._build_live_url(discovery_path),
            {"page": 1, "pageSize": 100},
            method="POST"
        )
        
        friends = response.get("zpData", {}).get("friendList", [])
        target = next((f for f in friends if candidate_name in f.get("name", "")), None)
        
        if not target:
            print(f"❌ 未在好友列表中发现 {candidate_name}。")
            return

        print(f"✅ 成功锁定: {target['name']} (UID: {target['uid']}, SID: {target['securityId'][:15]}...)")
        
        # 2. 精准投递
        print(f"\n📡 [Phase 2] 正在利用最新 ID 执行两步穿透投递...")
        
        # 使用连接器的 send_message (底层已升级为独立两步走)
        result = connector.send_message(
            target_id=target['securityId'],
            message=msg_text,
            job_id=target.get('encryptJobId') or java_job_id,
            numeric_uid=target['uid'],
            numeric_job_id=target.get('jobId') or "528474224"
        )
        
        print(f"✅ 投递任务已完成！服务器回执: {result.get('raw_payload', {})}")

    except Exception as e:
        print(f"💥 流程运行异常: {e}")

if __name__ == "__main__":
    full_cycle_test("陈坤鲲", "你好，陈坤鲲。这一条消息使用了‘下拉取候选人+全协议对齐’的最终方案发送，请确认收到。")
