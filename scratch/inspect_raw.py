import sys
import os
import json
from sqlalchemy import select

# Add the project directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "AI-HR")))

from ai_hr.db.session import SessionLocal
from ai_hr.db.models.candidate import Candidate

def inspect_full_raw_profile():
    session = SessionLocal()
    try:
        stmt = select(Candidate).order_by(Candidate.created_at.desc()).limit(1)
        c = session.execute(stmt).scalar_one_or_none()
        if c:
            print(f"Candidate: {c.name}")
            print(json.dumps(c.raw_profile, indent=2, ensure_ascii=False))
        else:
            print("No candidates found.")
    finally:
        session.close()

if __name__ == "__main__":
    inspect_full_raw_profile()
