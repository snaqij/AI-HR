import sys
import os
import json

# Add the project directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "AI-HR")))

from ai_hr.core.config import get_settings
from ai_hr.connectors.boss import BossConnector
from ai_hr.connectors.base import ConnectorCredentials

def inspect_geek_detail_keys():
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
    raw_profile = {"uid": 748227681}
    
    try:
        detail = connector._fetch_boss_geek_detail(raw_profile)
        print("Candidate Detail Keys:")
        # Common keys for school/degree/experience in detailed view
        interesting_keys = [
            "school", "schoolName", "university", 
            "degree", "degreeName", "education",
            "experience", "workExperience", "workYears",
            "salary", "expectSalary", "salaryDesc",
            "latestCompany", "companyName", "company",
            "primarySchool", "primaryEducation",
            "graduateSchool", "major"
        ]
        
        found = {}
        for k in interesting_keys:
            if k in detail:
                found[k] = detail[k]
        
        # Also check for common nested patterns
        for k, v in detail.items():
            if isinstance(v, dict):
                for sub_k in interesting_keys:
                    if sub_k in v:
                        found[f"{k}.{sub_k}"] = v[sub_k]
        
        print(json.dumps(found, indent=2, ensure_ascii=False))
        
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    inspect_geek_detail_keys()
