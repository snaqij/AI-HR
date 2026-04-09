import sys
import os

# 确保项目路径在 sys.path 中
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from ai_hr.connectors.boss import BossConnector, ConnectorCredentials
from ai_hr.core.config import get_settings

def probe_boss_endpoints():
    print("="*70)
    print("🛰 BOSS 接口雷达：正在为您探测真实职位列表路径...")
    print("="*70)

    settings = get_settings()
    # 尝试切换到企业端专用域名
    credentials = ConnectorCredentials(
        account=settings.boss_account,
        secret=settings.boss_secret or "",
        mode="live",
        base_url="https://employer.zhipin.com",
        cookie_header=settings.boss_cookie_header
    )
    
    connector = BossConnector(credentials)

    # 企业端核心备选路径
    candidates = [
        "/wapi/zpjob/job/post/list.json",
        "/wapi/zpjob/post/queryList.json",
        "/wapi/zpjob/job/queryList.json"
    ]

    found_path = None

    for path in candidates:
        print(f"检测路径: {path} ...", end=" ", flush=True)
        try:
            # 使用 GET 探测
            resp = connector._send_live_request(
                connector._build_live_url(path),
                {"page": 1, "pageSize": 10},
                method="GET"
            )
            code = resp.get("code")
            if code == 0:
                print("✅ 匹配成功!")
                found_path = path
                break
            else:
                print(f"❌ 失败 (Code={code}, Msg={resp.get('message')})")
        except Exception as e:
            if "404" in str(e):
                print("🚫 路径不存在 (404)")
            else:
                print(f"⚠️ 响应错误: {str(e)[:50]}")

    print("\n" + "="*70)
    if found_path:
        print(f"🎉 探测完成！您的真实路径为: {found_path}")
        print("我将自动为您更新配置文件并拉取数据。")
    else:
        print("❌ 遗憾: 所有预设路径均未能匹配。")
        print("建议: 请在浏览器 F12 网络面板中，搜索 'json' 并寻找包含职位名称的请求，查看其具体 URL。")
    print("="*70)

if __name__ == "__main__":
    probe_boss_endpoints()
