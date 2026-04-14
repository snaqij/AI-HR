
import os
import sys
import json
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

# 将项目根目录加入路径
sys.path.append(os.path.join(os.getcwd(), "AI-HR"))

from ai_hr.core.config import get_settings
from ai_hr.db.models import Candidate

def wash_candidate_data():
    settings = get_settings()
    engine = create_engine(settings.database_url)
    
    with Session(engine) as session:
        # 查找学历或学校缺失的候选人
        candidates = session.query(Candidate).filter(
            (Candidate.degree.is_(None)) | (Candidate.school.is_(None))
        ).all()
        
        print(f"Found {len(candidates)} candidates needing data washing.")
        
        updated_count = 0
        for c in candidates:
            raw = c.raw_profile or {}
            if not raw:
                continue
                
            needs_update = False
            
            # 1. 提取学历 (degree)
            # 优先级: raw['edu'] -> raw['eduExpList'][0]['degree']
            degree = raw.get("edu")
            if not degree and "eduExpList" in raw and raw["eduExpList"]:
                degree = raw["eduExpList"][0].get("degree")
            
            if degree and not c.degree:
                c.degree = degree
                needs_update = True
            
            # 2. 提取学校 (school)
            school = raw.get("school")
            if not school and "eduExpList" in raw and raw["eduExpList"]:
                school = raw["eduExpList"][0].get("school")
                
            if school and not c.school:
                c.school = school
                needs_update = True
            
            # 3. 提取工作经验描述 (work_experience)
            work_exp = raw.get("year") or raw.get("salaryDesc")
            if work_exp and not c.work_experience:
                c.work_experience = work_exp
                needs_update = True

            if needs_update:
                updated_count += 1
                if updated_count % 10 == 0:
                    print(f"Progress: Updated {updated_count} candidates...")

        session.commit()
        print(f"Success: Washed and updated {updated_count} candidates.")

if __name__ == "__main__":
    wash_candidate_data()
