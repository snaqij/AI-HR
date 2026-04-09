import requests
import json
import os

# --- 杜潇楠 实战数据集 ---
TARGET_UID = "738548141"
TARGET_SID = "NNF8rT61vL0rT-u1rhVl-SRXVw7EId7kt1vOw17_a3DVRaEl7Jw54WaRTQrk0JNfRrVypeyWSdVWjnnF9BcvYtqaC_2dQ-qbhbgYsPEADZQnxMN4MDve4GGAxm9FlK7Ano_PL8gmk-pLvEFDhYYcZjeflLVnzoMNMs0U2lX51x6Q3xmcTc-jrDzVOU8hUzPpIdVKcwuAezlKowCNLuw8Chdj6AKstUDuvJPfobrQSGFCDz8qR0Rx20j1LdUarbRCnWh58AbWyk3DSKMnZLoPDqUILc92Y5UD9kIYiqrRxNFJoXJlx4itPkE4T9ngI_LV479ye4fuLy-VWwCwSth1wLZVbwJ0QvdFmn9usEqZmMo9v5tqiilrBPaqDaHEQk1laLxD6saf18KkfMiaXBFfLOTAFBinivSoM-YiBIOsWnijkgWiTc-NA2-bBkgyGr_rLojjrvLoxLXSlO9DMQmNt2RFQJTTX2ijp97A1WKf2-uyc8AdZjHnHBpiop_QrMEyLFBnJKkM2jSVi3FAkIrypduIN9Bu_PW4ge2m5cHhWpjI_Zw~"
JOB_ENCRYPT_ID = "bcdd0ea56ebec9450nZy39q5ElBU"
JOB_NUMERIC_ID = "528474224"
COOKIE = "lastCity=101180300; ab_guid=2babf9e3-2d2f-4a1e-adaa-3949042fbc59; __zp_seo_uuid__=77790b22-b96a-4ae0-95a2-0b8ddbd8ba66; __l=r=https%3A%2F%2Fwww.google.com%2F&l=%2F&s=1; __g=-; Hm_lvt_194df3105ad7148dcf2b98a91b5e727a=1773837546,1775050827; Hm_lpvt_194df3105ad7148dcf2b98a91b5e727a=1775050827; HMACCOUNT=7729392ABFE0F672; wt2=DGbcbwSjyjhgmRQchl0i_j8erDU4r7_1Xtjdbj3GnE29XacMkVSrm8bozhCPdncxuN4I4UuvcQ8QxiOBV1KlszA~~; wbg=1; zp_at=c86PnXGQGbJfn1zEqLEIFdtQWnxgywiws-4C_1b23os~; bst=V2R94iEuz901djVtRuyBgRKi-w7Drexys~|R94iEuz901djVtRuyBgRKi-w7DrXxSo~; __c=1775050826; __a=85352538.1746838988.1773837546.1775050826.354.28.3.9"

MSG = "你好，杜潇楠，我是面试官。我已经看过了你的简历，你的 Java 基础非常扎实。你有空参加一次线上语音面试吗？"

def final_strike():
    print("\n🚀 杜潇楠 终极定点投递启动...")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Content-Type": "application/json; charset=UTF-8",
        "Accept": "application/json, text/plain, */*",
        "Cookie": COOKIE,
        "Referer": "https://www.zhipin.com/web/boss/index",
        "Origin": "https://www.zhipin.com"
    }

    # --- Step 1: block/v2 (Unblock/Accept) ---
    print("\n[Phase 1] 正在执行业务解锁 (block/v2)...")
    unblock_url = "https://www.zhipin.com/wapi/zpblock/chat/reply/block/v2"
    payload1 = {
        "securityId": TARGET_SID,
        "encryptJid": JOB_ENCRYPT_ID,
        "autoRelease": 1,
        "bgSource": 1
    }
    
    try:
        r1 = requests.post(unblock_url, json=payload1, headers=headers, timeout=10)
        print(f"   - 回执状态码: {r1.status_code}")
        print(f"   - 服务器响应: {r1.text[:200]}")
    except Exception as e:
        print(f"   - 解锁步骤报错 (忽略): {e}")

    # --- Step 2: send.json (Real Chat Message) ---
    print("\n[Phase 2] 正在强制注入对话内容 (send.json)...")
    send_url = "https://www.zhipin.com/wapi/zpchat/conversation/send.json"
    payload2 = {
        "toId": TARGET_UID,
        "msg": MSG,
        "jobId": JOB_NUMERIC_ID,
        "securityId": TARGET_SID
    }

    try:
        r2 = requests.post(send_url, json=payload2, headers=headers, timeout=10)
        print(f"   - 回执状态码: {r2.status_code}")
        print(f"   - 服务器响应: {r2.text}")
        
        if r2.status_code == 200 and '"code":0' in r2.text:
            print("\n✅ 发送成功！杜潇楠 应该已在聊天窗口收到消息。")
        else:
            print("\n⚠️ 发送状态异常，请检查 Cookie 是否过期。")
    except Exception as e:
        print(f"\n💥 最终步骤崩溃: {e}")

if __name__ == "__main__":
    final_strike()
