import sys
import os
import argparse

# 确保项目路径在 sys.path 中
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from ai_hr.connectors.boss import BossConnector, ConnectorCredentials
from ai_hr.core.config import get_settings

def main():
    parser = argparse.ArgumentParser(description="BOSS 独立消息投递工具")
    parser.add_argument("--candidate", required=True, help="候选人的 Security ID (长串)")
    parser.add_argument("--uid", help="候选人的数字 UID (从抓包获取)")
    parser.add_argument("--job", required=True, help="职位的加密 ID (encryptJid)")
    parser.add_argument("--numeric_job", help="职位的数字 ID (jobId)")
    parser.add_argument("--msg", required=True, help="消息内容")
    
    args = parser.parse_args()

    print("="*75)
    print(f"📡 正在投递全字段对齐消息至 BOSS...")
    print(f"👤 目标 UID: {args.uid or 'N/A'}")
    print(f"💼 目标 JobID: {args.numeric_job or 'N/A'}")
    print(f"💬 消息内容: {args.msg}")
    print("="*75)

    settings = get_settings()
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
        # 使用我们已验证成功的 block/v2 协议发送 (现在带入全字段身份)
        result = connector.send_message(
            args.candidate, 
            args.msg, 
            job_id=args.job, 
            numeric_uid=args.uid, 
            numeric_job_id=args.numeric_job
        )
        
        raw = result.get("raw_payload", {})
        if raw.get("code") == 0:
            print("\n✅ 发送成功！")
            print(f"服务器回执: {raw.get('zpData', {}).get('tip', 'OK')}")
        else:
            print(f"\n⚠️ 发送状态异常: {raw.get('message', '未知错误')}")
            
    except Exception as e:
        print(f"\n💥 程序运行异常: {e}")

if __name__ == "__main__":
    main()
