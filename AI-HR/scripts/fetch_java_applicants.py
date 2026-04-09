import sys
import os

# 确保项目路径在 sys.path 中
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from ai_hr.connectors.boss import BossConnector, ConnectorCredentials
from ai_hr.core.config import get_settings

def fetch_java_applicants():
    print("="*75)
    print("📡 BOSS 生产环境：正在拉取 [Java] 职位的投递人数据...")
    print("="*75)

    settings = get_settings()
    # 使用 Java 职位的真实 ID
    job_id = "bcdd0ea56ebec9450nZy39q5ElBU" 

    credentials = ConnectorCredentials(
        account=settings.boss_account,
        secret=settings.boss_secret or "",
        mode="live",
        base_url=settings.boss_base_url,
        # 已经在 .env.dev 中更新为 /wapi/zprelation/friend/getBossFriendListV2.json
        applicants_path=settings.boss_applicants_path,
        cookie_header=settings.boss_cookie_header
    )
    
    connector = BossConnector(credentials)

    try:
        # 实时拉取
        result = connector.list_applicants(job_id)
        found_data = result.get("items", [])
        raw_payload = result.get("raw_payload", {})
        
        if not found_data:
            print(f"⚠️ 未在该岗位下匹配到候选人。")
            print(f"原始响应状态码: {raw_payload.get('code')}")
            # 打印前 500 个字符进行调试
            print(f"原始数据预览: {str(raw_payload)[:500]}...")
            
            # 尝试全量搜索：如果不传 job_id 看看能拉到什么
            print("\n正在尝试全量检索所有候选人...")
            all_result = connector.list_applicants(None)
            all_items = all_result.get("items", [])
            print(f"全量列表返回了 {len(all_items)} 个候选人。")
            if all_items:
                print("列表中的前 3 个候选人及其对应的职位 ID：")
                for item in all_items[:3]:
                    print(f"- {item.get('name')}: JobID={item.get('raw_profile', {}).get('encryptJobId')}")
        else:
            print(f"✅ 成功获取到 {len(found_data)} 名真实候选人：\n")
            print(f"{'姓名':<10} | {'Security ID (用于聊天)':<45} | {'职位'}")
            print("-" * 95)
            for cand in found_data:
                name = cand.get("name", "Unknown")
                sid = cand.get("external_candidate_id", "N/A")
                job_name = cand.get("raw_profile", {}).get("jobName", "N/A")
                
                print(f"{name:<10} | {sid:<45} | {job_name}")
            
    except Exception as e:
        print(f"💥 数据获取失败: {e}")

    print("\n" + "="*75)

if __name__ == "__main__":
    fetch_java_applicants()
