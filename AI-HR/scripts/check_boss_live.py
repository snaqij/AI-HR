import sys
import os
import json
from pathlib import Path

# 确保项目路径在 sys.path 中
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from ai_hr.connectors.boss import BossConnector, ConnectorCredentials
from ai_hr.core.config import get_settings
from ai_hr.core.exceptions import ConnectorOperationError

def check_live_connectivity():
    print("="*60)
    print("🔍 BOSS 平台实战连通性体检")
    print("="*60)

    # 1. 加载最新配置
    settings = get_settings()
    
    if settings.boss_mode != "live":
        print("❌ 错误: 当前系统仍处于 MOCK 模式。请确保 .env.dev 中 AI_HR_BOSS_MODE=live")
        return

    cookie = settings.boss_cookie_header
    if not cookie or len(cookie) < 50:
        print("❌ 警告: 未检测到有效的 Cookie。")
        print("请在 .env.dev 的 AI_HR_BOSS_COOKIE_HEADER 字段中填入您的浏览器 Cookie。")
        return

    print(f"📡 模式: {settings.boss_mode}")
    print(f"👤 账号: {settings.boss_account}")
    print(f"🔐 Cookie 长度: {len(cookie)} 字符 (已检测到)")

    # 2. 初始化连接器
    credentials = ConnectorCredentials(
        account=settings.boss_account,
        secret=settings.boss_secret or "",
        mode="live",
        base_url=settings.boss_base_url,
        publish_path=settings.boss_publish_path,
        status_path=settings.boss_status_path,
        applicants_path=settings.boss_applicants_path,
        greet_path=settings.boss_greet_path,
        fetch_messages_path=settings.boss_fetch_messages_path,
        send_message_path=settings.boss_send_message_path,
        cookie_header=cookie
    )
    
    connector = BossConnector(credentials)

    # 3. 执行只读测试：获取最近的一个岗位状态
    print("\n[Step 1] 尝试访问 BOSS API...")
    try:
        # 我们随机尝试拉取一个列表，验证鉴权是否通过
        # live 下如果没有具体的 jobId，可以尝试 list_applicants 的空请求或者其他探测
        print("正在尝试同步 API 状态...")
        # 这里的 sync_job_status 需要一个 ID，由于是探测，我们抓取异常即可
        # 更好的方法是调用一个不需要 ID 的通用接口（如果存在）
        # 暂且使用报错信息来判断：如果是 403/401 则是 Cookie 失效，如果是 404 则是 Cookie 成功但路径不对
        
        # 尝试拉取候选人列表 (模拟一个不存在的 ID)
        try:
            connector.list_applicants("test-connectivity-id")
        except ConnectorOperationError as e:
            if "HTTP error 403" in str(e) or "HTTP error 401" in str(e):
                print("❌ 鉴权失败! 您的 Cookie 可能已过期或填写不完整。")
                print(f"原始错误: {e}")
            elif "HTTP error 404" in str(e):
                print("✅ 鉴权通过! (收到 404 说明您已成功访问 API，只是指定的资源不存在)")
            else:
                print(f"⚠️ 收到非预期错误，但 API 已响应: {e}")
                print("这通常意味着连接已经建立。")
                
    except Exception as e:
        print(f"💥 网络请求彻底失败: {e}")

    print("\n" + "="*60)
    print("体检结束。请根据上方提示调整您的 .env.dev 文件。")
    print("="*60)

if __name__ == "__main__":
    check_live_connectivity()
