import sys
import os
import time

# 确保项目路径在 sys.path 中
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from ai_hr.connectors.boss import BossConnector, ConnectorCredentials
from ai_hr.core.config import get_settings

def deep_search(target_name, max_pages=20):
    settings = get_settings()
    credentials = ConnectorCredentials(
        account=settings.boss_account,
        secret=settings.boss_secret or "",
        mode="live",
        base_url=settings.boss_base_url,
        cookie_header=settings.boss_cookie_header,
        applicants_path="/wapi/zprelation/friend/getBossFriendListV2.json"
    )
    
    connector = BossConnector(credentials)
    
    print(f"\n📡 正在为您执行深度侦察 (目标: {target_name}, 最大深度: {max_pages} 页)...")
    
    for page in range(1, max_pages + 1):
        print(f"   - 扫描第 {page} 页...")
        try:
            # 搜索好友列表
            payload = {"page": page, "pageSize": 50, "type": 0}
            response = connector._send_live_request(
                connector._build_live_url(credentials.applicants_path),
                payload,
                method="POST",
                is_json=False
            )
            
            friends = response.get("zpData", {}).get("friendList", [])
            for f in friends:
                name = f.get("name", "")
                if target_name in name:
                    print(f"\n🎯 锁定！在第 {page} 页找到 {name}:")
                    print(f"   - UID: {f.get('uid')}")
                    print(f"   - securityId: {f.get('securityId')}")
                    print(f"   - jobId: {f.get('jobId')}")
                    return f.get('uid'), f.get('securityId'), f.get('jobId')
            
            if not friends:
                print("   - 该页无数据，停止。")
                break
            
            time.sleep(0.5) # 友好的频率限制
        except Exception as e:
            print(f"   - 翻页异常: {e}")
            break
            
    print("\n❌ 深度侦察结束，未能在前 20 页找到该候选人。")
    return None, None, None

if __name__ == "__main__":
    deep_search("杜潇楠")
