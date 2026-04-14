
import os
import sys
from sqlalchemy import create_engine, text

# Add the project root to sys.path
sys.path.append(os.path.join(os.getcwd(), "AI-HR"))

from ai_hr.core.config import get_settings

def check_status():
    settings = get_settings()
    engine = create_engine(settings.database_url)
    job_id = '7f3ce2a5-a0dd-4fc7-acc2-f4fb8a32f7eb'
    
    with engine.connect() as conn:
        query = text(f"SELECT resume_request_status, COUNT(*) FROM candidate_job_pipeline WHERE job_id='{job_id}' GROUP BY resume_request_status")
        results = conn.execute(query).all()
        print(f"Status for Job {job_id}:")
        for row in results:
            print(f"- {row[0]}: {row[1]}")

if __name__ == "__main__":
    check_status()
