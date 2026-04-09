import urllib.request
import urllib.parse
import json
import time

TARGET_UID = "73352932"
TARGET_SID = "AHremp7o5WleB5D2w7gTD5x5wcIRs_9tcKINzpjKStoVWq0Gkl3Q3wrutFi-NpNzA_QZ3KxNNmC9drV7A97ylvPBKJ-j1yvvpbwiuTf_vE_3f92qZf6sV1L-q1fIHWpYvirmPcCau4xsfMyPlzDjzBfaLI3M2ECXNlOBA"
JOB_NUMERIC_ID = "528474224"
JOB_ENCRYPT_ID = "bcdd0ea56ebec9450nZy39q5ElBU"
COOKIE = "lastCity=101180300; ab_guid=2babf9e3-2d2f-4a1e-adaa-3949042fbc59; __zp_seo_uuid__=77790b22-b96a-4ae0-95a2-0b8ddbd8ba66; __l=r=https%3A%2F%2Fwww.google.com%2F&l=%2F&s=1; __g=-; Hm_lvt_194df3105ad7148dcf2b98a91b5e727a=1773837546,1775050827; Hm_lpvt_194df3105ad7148dcf2b98a91b5e727a=1775050827; HMACCOUNT=7729392ABFE0F672; wt2=DGbcbwSjyjhgmRQchl0i_j8erDU4r7_1Xtjdbj3GnE29XacMkVSrm8bozhCPdncxuN4I4UuvcQ8QxiOBV1KlszA~~; wbg=1; zp_at=c86PnXGQGbJfn1zEqLEIFdtQWnxgywiws-4C_1b23os~; bst=V2R94iEuz901djVtRuyBgRKi-w7Drexys~|R94iEuz901djVtRuyBgRKi-w7DrXxSo~; __c=1775050826; __a=85352538.1746838988.1773837546.1775050826.354.28.3.9"

MSG = "你好，吕军，我是面试官。我已经看过了你的简历，你的 Java 基础非常扎实。你有空参加一次线上语音面试吗？"

def sync_strike():
    print("\n🚀 吕军 同步原生投递启动 (Phase 1: Unlock)...")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        "Cookie": COOKIE,
        "Referer": "https://www.zhipin.com/web/boss/index",
        "X-Requested-With": "XMLHttpRequest"
    }

    # --- Step 1: block/v2 (Form) ---
    unblock_payload = urllib.parse.urlencode({
        "securityId": TARGET_SID,
        "encryptJid": JOB_ENCRYPT_ID,
        "autoRelease": 1,
        "bgSource": 1,
        "msg": MSG
    }).encode("utf-8")

    try:
        req1 = urllib.request.Request("https://www.zhipin.com/wapi/zpblock/chat/reply/block/v2", data=unblock_payload, headers=headers)
        with urllib.request.urlopen(req1, timeout=8) as r1:
            resp1 = r1.read().decode("utf-8")
            print(f"   - Phase 1 Res: {resp1[:150]}")
    except Exception as e:
        print(f"   - Phase 1 异常 (跳过): {e}")

    time.sleep(2)

    # --- Step 2: send.json (Form) ---
    print("\n🚀 Phase 2: Final Delivery (send.json)...")
    send_payload = urllib.parse.urlencode({
        "toId": TARGET_UID,
        "msg": MSG,
        "jobId": JOB_NUMERIC_ID,
        "securityId": TARGET_SID
    }).encode("utf-8")

    try:
        req2 = urllib.request.Request("https://www.zhipin.com/wapi/zpchat/conversation/send.json", data=send_payload, headers=headers)
        with urllib.request.urlopen(req2, timeout=8) as r2:
            resp2 = r2.read().decode("utf-8")
            print(f"   - Phase 2 Res: {resp2}")
            if '"code":0' in resp2:
                print("\n✅ 投递圆满成功！吕军 窗口应该已经显示。")
            else:
                print("\n⚠️ 吕军 已解锁但消息发送受限。")
    except Exception as e:
        print(f"   - Phase 2 致命崩溃: {e}")

if __name__ == "__main__":
    sync_strike()
