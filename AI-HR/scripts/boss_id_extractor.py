import sys
import os
import json
import requests

# 确保项目路径在 sys.path 中
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from ai_hr.connectors.boss import BossConnector, ConnectorCredentials
from ai_hr.core.config import get_settings

def id_extraction(security_id):
    settings = get_settings()
    credentials = ConnectorCredentials(
        account=settings.boss_account,
        secret=settings.boss_secret or "",
        mode="live",
        base_url=settings.boss_base_url,
        cookie_header=settings.boss_cookie_header
    )
    
    # 构造简历查看详情接口，反拉 UID
    url = f"{credentials.base_url}/wapi/zpgeek/view/geek/resume/v2.json"
    params = {"securityId": security_id}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Cookie": credentials.cookie_header or "",
        "Referer": f"{credentials.base_url}/web/boss/index"
    }

    print("\n📡 正在执行身份穿透侦察...")
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        data = response.json()
        
        # 寻找 UID
        zpData = data.get("zpData", {})
        geek_user = zpData.get("geekUser", {})
        uid = geek_user.get("uid")
        name = geek_user.get("name")
        
        if uid:
            print(f"🎯 成功穿透！杜潇楠 的数字 UID: {uid}")
            return uid, name
        else:
            print(f"⚠️ 未能从简历接口获取 UID，服务器返回: {data.get('message', '未知错误')}")
            return None, None

    except Exception as e:
        print(f"💥 侦察由于网络或协议崩溃: {e}")
        return None, None

if __name__ == "__main__":
    sid = "NNF8rT61vL0rT-u1rhVl-SRXVw7EId7kt1vOw17_a3DVRaEl7Jw54WaRTQrk0JNfRrVypeyWSdVWjnnF9BcvYtqaC_2dQ-qbhbgYsPEADZQnxMN4MDve4GGAxm9FlK7Ano_PL8gmk-pLvEFDhYYcZjeflLVnzoMNMs0U2lX51x6Q3xmcTc-jrDzVOU8hUzPpIdVKcwuAezlKowCNLuw8Chdj6AKstUDuvJPfobrQSGFCDz8qR0Rx20j1LdUarbRCnWh58AbWyk3DSKMnZLoPDqUILc92Y5UD9kIYiqrRxNFJoXJlx4itPkE4T9ngI_LV479ye4fuLy-VWwCwSth1wLZVbwJ0QvdFmn9usEqZmMo9v5tqiilrBPaqDaHEQk1laLxD6saf18KkfMiaXBFfLOTAFBinivSoM-YiBIOsWnijkgWiTc-NA2-bBkgyGr_rLojjrvLoxLXSlO9DMQmNt2RFQJTTX2ijp97A1WKf2-uyc8AdZjHnHBpiop_QrMEyLFBnJKkM2jSVi3FAkIrypduIN9Bu_PW4ge2m5cHhWpjI_Zw~"
    id_extraction(sid)
