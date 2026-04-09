import sys
import os

# 确保项目路径在 sys.path 中
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from ai_hr.connectors.boss import BossConnector, ConnectorCredentials
from ai_hr.core.config import get_settings

def fetch_real_jobs():
    print("="*70)
    print("📡 BOSS 平台：正在拉取您的真实职位列表...")
    print("="*70)

    # 1. 加载配置
    settings = get_settings()
    
    # 2. 初始化连接器
    credentials = ConnectorCredentials(
        account=settings.boss_account,
        secret=settings.boss_secret or "",
        mode="live",
        base_url=settings.boss_base_url,
        publish_path=settings.boss_publish_path,
        status_path=settings.boss_status_path,
        list_jobs_path=settings.boss_list_jobs_path,
        applicants_path=settings.boss_applicants_path,
        cookie_header=settings.boss_cookie_header
    )
    
    connector = BossConnector(credentials)

    # 3. 执行拉取
    try:
        result = connector.list_jobs(page=1, page_size=30)
        items = result.get("items", [])
        
        if not items:
            print("⚠️ 未发现任何在线职位。请确认您的账号后台是否有已发布的岗位。")
            print(f"原始响应摘要: {str(result.get('raw_payload'))[:200]}...")
        else:
            print(f"✅ 成功找到 {len(items)} 个职位：\n")
            print(f"{'职位名称':<25} | {'薪资':<15} | {'城市':<10} | {'外部 ID'}")
            print("-" * 75)
            for job in items:
                title = job.get("title", "Unknown")
                salary = job.get("salary", "N/A")
                city = job.get("city", "N/A")
                job_id = job.get("external_job_id", "N/A")
                print(f"{title:<25} | {salary:<15} | {city:<10} | {job_id}")
            
    except Exception as e:
        print(f"💥 拉取失败: {e}")

    print("\n" + "="*70)

if __name__ == "__main__":
    fetch_real_jobs()
