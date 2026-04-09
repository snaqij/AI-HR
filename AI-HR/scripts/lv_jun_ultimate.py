import urllib.request
import urllib.parse
import time
import json

# --- 吕军 终极实战数据集 ---
UID = "73352932"
SID = "AHremp7o5WleB5D2w7gTD5x5wcIRs_9tcKINzpjKStoVWq0Gkl3Q3wrutFi-NpNzA_QZ3KxNNmC9drV7A97ylvPBKJ-j1yvvpbwiuTf_vE_3f92qZf6sV1L-q1fIHWpYvirmPcCau4xsfMyPlzDjzBfaLI3M2ECXNlOBA"
JOB_NUM = "528474224"
JOB_ENC = "bcdd0ea56ebec9450nZy39q5ElBU"
COOKIE = "lastCity=101180300; ab_guid=2babf9e3-2d2f-4a1e-adaa-3949042fbc59; __zp_seo_uuid__=77790b22-b96a-4ae0-95a2-0b8ddbd8ba66; __l=r=https%3A%2F%2Fwww.google.com%2F&l=%2F&s=1; __g=-; Hm_lvt_194df3105ad7148dcf2b98a91b5e727a=1773837546,1775050827; Hm_lpvt_194df3105ad7148dcf2b98a91b5e727a=1775050827; HMACCOUNT=7729392ABFE0F672; wt2=DGbcbwSjyjhgmRQchl0i_j8erDU4r7_1Xtjdbj3GnE29XacMkVSrm8bozhCPdncxuN4I4UuvcQ8QxiOBV1KlszA~~; wbg=1; zp_at=c86PnXGQGbJfn1zEqLEIFdtQWnxgywiws-4C_1b23os~; bst=V2R94iEuz901djVtRuyBgRKi-w7Drexys~|R94iEuz901djVtRuyBgRKi-w7DrXxSo~; __c=1775050826; __a=85352538.1746838988.1773837546.1775050826.354.28.3.9"

MSG = "你好，吕军，我是面试官。我已经看过了你的简历，你的 Java 基础非常扎实。你有空参加一次线上语音面试吗？"

def ultimate_strike():
    print(f"\n🚀 吕军 (UID: {UID}) 终极全链路投递启动...")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        "Cookie": COOKIE,
        "Referer": "https://www.zhipin.com/web/boss/index",
        "X-Requested-With": "XMLHttpRequest"
    }

    # Step 1: Unlock (block/v2)
    print("\n[Action 1/3] 正在执行业务解锁 (Unlock)...")
    p1 = urllib.parse.urlencode({"securityId": SID, "encryptJid": JOB_ENC, "autoRelease": 1, "bgSource": 1}).encode("utf-8")
    try:
        req1 = urllib.request.Request("https://www.zhipin.com/wapi/zpblock/chat/reply/block/v2", data=p1, headers=headers)
        with urllib.request.urlopen(req1, timeout=8) as r1:
            print(f"   - Result: {r1.read().decode('utf-8')[:100]}")
    except Exception as e: print(f"   - Error (Ignored): {e}")

    time.sleep(1.5)

    # Step 2: Greet (greet/send.json)
    print("\n[Action 2/3] 正在发起首发招呼 (Greet)...")
    p2 = urllib.parse.urlencode({"toId": UID, "jobId": JOB_NUM, "securityId": SID}).encode("utf-8")
    try:
        req2 = urllib.request.Request("https://www.zhipin.com/wapi/zpchat/greet/send.json", data=p2, headers=headers)
        with urllib.request.urlopen(req2, timeout=8) as r2:
            print(f"   - Result: {r2.read().decode('utf-8')[:100]}")
    except Exception as e: print(f"   - Error (Ignored): {e}")

    time.sleep(1.5)

    # Step 3: Message (send.json)
    print("\n[Action 3/3] 正在注入面试邀请文字 (Message)...")
    p3 = urllib.parse.urlencode({"toId": UID, "msg": MSG, "jobId": JOB_NUM, "securityId": SID}).encode("utf-8")
    try:
        req3 = urllib.request.Request("https://www.zhipin.com/wapi/zpchat/conversation/send.json", data=p3, headers=headers)
        with urllib.request.urlopen(req3, timeout=8) as r3:
            resp3 = r3.read().decode("utf-8")
            print(f"   - Result: {resp3}")
            if '"code":0' in resp3:
                print("\n✅ 终极必达！吕军 窗口现在应该已经完美显示面试邀请。")
            else:
                print("\n⚠️ 吕军 已激活，但自定义文字由于频率或策略限制未能显现。")
    except Exception as e: print(f"   - Error: {e}")

if __name__ == "__main__":
    ultimate_strike()
