
import os
import sys
from sqlalchemy import create_engine, text

# Add the project root to sys.path
sys.path.append(os.path.join(os.getcwd(), "AI-HR"))

from ai_hr.core.config import get_settings

def check_progress():
    settings = get_settings()
    engine = create_engine(settings.database_url)
    
    with engine.connect() as conn:
        # Check metadata enrichment progress
        enriched = conn.execute(text("SELECT COUNT(*) FROM candidates WHERE metadata_synced_at IS NOT NULL")).scalar()
        total = conn.execute(text("SELECT COUNT(*) FROM candidates")).scalar()
        print(f"Metadata Enrichment: {enriched}/{total} candidates processed.")
        
        # Check pipeline status
        pipeline_status = conn.execute(text("SELECT resume_request_status, COUNT(*) FROM candidate_job_pipeline GROUP BY resume_request_status")).all()
        print("\nPipeline Status (Resume Requests):")
        for row in pipeline_status:
            print(f"- {row[0]}: {row[1]}")
            
        # Check evaluation status
        eval_status = conn.execute(text("SELECT evaluation_status, COUNT(*) FROM candidate_job_pipeline GROUP BY evaluation_status")).all()
        print("\nPipeline Status (Evaluations):")
        for row in eval_status:
            print(f"- {row[0]}: {row[1]}")

if __name__ == "__main__":
    check_progress()
