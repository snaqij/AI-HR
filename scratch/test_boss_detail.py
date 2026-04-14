import sys
import os
import json

# Add the project directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "AI-HR")))

from ai_hr.core.config import get_settings
from ai_hr.connectors.boss import BossConnector
from ai_hr.connectors.base import ConnectorCredentials

def test_geek_detail():
    print("Testing BOSS Geek Detail API...")
    
    # Needs valid cookies/config from environment or settings
    # I'll try to use the ones already configured in the app if they exist
    settings = get_settings()
    creds = ConnectorCredentials(
        account="dummy",
        secret="dummy",
        mode="live",
        base_url="https://www.zhipin.com",
        publish_path="/wapi/zpboss/job/publish.json",
        status_path="/wapi/zpboss/job/status.json",
        applicants_path="/wapi/zprelation/friend/list.json",
        cookie_header=settings.boss_cookie_header
    )
    
    connector = BossConnector(creds)
    
    # Candidate info from user's dump
    # uid: 748227681
    raw_profile = {"uid": 748227681}
    
    try:
        detail = connector._fetch_boss_geek_detail(raw_profile)
        print("Success! Detail keys found:")
        print(list(detail.keys()))
        print("\nFull Detail (Sample):")
        print(json.dumps(detail, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"Failed to fetch detail: {e}")

if __name__ == "__main__":
    test_geek_detail()
