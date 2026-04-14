import sys
import os
import json
from sqlalchemy import select

# Add the project directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "AI-HR")))

from ai_hr.db.session import SessionLocal
from ai_hr.db.models.candidate import Candidate
from ai_hr.db.models.job_candidate import JobCandidate

def diagnose_duplicates_and_metadata():
    session = SessionLocal()
    try:
        print("--- Duplicate Candidates Check ---")
        # Find candidates with the same name (not perfect but a hint)
        stmt = select(Candidate.name, Candidate.id, Candidate.external_candidate_id).order_by(Candidate.name)
        candidates = session.execute(stmt).all()
        
        name_map = {}
        for name, cid, ext_id in candidates:
            if name not in name_map:
                name_map[name] = []
            name_map[name].append({"id": cid, "external_id": ext_id})
        
        duplicates_found = False
        for name, entries in name_map.items():
            if len(entries) > 1:
                print(f"Name '{name}' has {len(entries)} entries:")
                for e in entries:
                    print(f"  - ID: {e['id']}, External ID: {e['external_id']}")
                duplicates_found = True
        
        if not duplicates_found:
            print("No simple name-based duplicates found.")

        print("\n--- Metadata & Raw Profile Check ---")
        # Pick the latest candidate
        stmt = select(Candidate).order_by(Candidate.created_at.desc()).limit(3)
        recent_candidates = session.execute(stmt).scalars().all()
        
        for c in recent_candidates:
            print(f"Candidate: {c.name} (ID: {c.id})")
            print(f"  School: {c.school}")
            print(f"  Degree: {c.degree}")
            print(f"  Experience: {c.work_experience}")
            print(f"  Salary: {c.expected_salary}")
            print(f"  Company: {c.latest_company}")
            print(f"  Raw Profile Keys: {list(c.raw_profile.keys())}")
            # print(f"  Raw Profile (Sample): {json.dumps({k: c.raw_profile[k] for k in list(c.raw_profile.keys())[:10]}, indent=2, ensure_ascii=False)}")
            print("-" * 20)

    finally:
        session.close()

if __name__ == "__main__":
    diagnose_duplicates_and_metadata()
