import sys
import os
import json

# 确保项目路径在 sys.path 中
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from ai_hr.connectors.boss import BossConnector, ConnectorCredentials
from ai_hr.core.config import get_settings

def discovery():
    settings = get_settings()
    credentials = ConnectorCredentials(
        account=settings.boss_account,
        secret=settings.boss_secret or "",
        mode="live",
        base_url=settings.boss_base_url,
        cookie_header=settings.boss_cookie_header,
        # 使用您提供的候选人/好友列表路径
        applicants_path="/wapi/zprelation/friend/getBossFriendListV2.json"
    )
    
    connector = BossConnector(credentials)
    
    print("\n" + "="*80)
    print("📡 正在全量扫描 BOSS 好友列表 (Discovery Mode)...")
    print("="*80)

    try:
        # 获取好友列表
        payload = {"page": 1, "pageSize": 100, "type": 0}
        response = connector._send_live_request(
            connector._build_live_url(credentials.applicants_path),
            payload,
            method="POST"
        )
        
        friends = response.get("zpData", {}).get("friendList", [])
        if not friends:
            print("⚠️ 未发现任何好友数据。")
            return

        found = False
        for f in friends:
            name = f.get("name", "未知")
            uid = f.get("uid", "N/A")
            securityId = f.get("securityId", "N/A")
            jobId = f.get("jobId", "N/A")
            encryptJobId = f.get("encryptJobId", "N/A")
            
            if "陈坤鲲" in name:
                print(f"\n🎯 锁定目标 [陈坤鲲]:")
                print(f"   - 数字 UID (toId): {uid}")
                print(f"   - 令牌 SecurityId: {securityId}")
                print(f"   - 数字 JobID: {jobId}")
                print(f"   - 加密 JobID: {encryptJobId}")
                found = True
            else:
                print(f"[-] 扫描中: {name} (UID: {uid})")
        
        if not found:
            print("\n❌ 在前 100 名好友中未发现陈坤鲲，请确认其是否已在沟通列表中。")

    except Exception as e:
        print(f"\n💥 侦察失败: {e}")

if __name__ == "__main__":
    discovery()
