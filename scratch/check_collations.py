
import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Add the project root to sys.path to import config
sys.path.append(os.path.join(os.getcwd(), "AI-HR"))

from ai_hr.core.config import get_settings

def diagnose_collations():
    settings = get_settings()
    engine = create_engine(settings.database_url)
    
    with engine.connect() as conn:
        print("Checking collations for candidate_job_pipeline and job_candidates...")
        
        query = text("""
            SELECT TABLE_NAME, COLUMN_NAME, COLLATION_NAME 
            FROM information_schema.COLUMNS 
            WHERE TABLE_SCHEMA = DATABASE() 
            AND TABLE_NAME IN ('candidate_job_pipeline', 'job_candidates')
            AND COLUMN_NAME IN ('candidate_id', 'job_id');
        """)
        
        results = conn.execute(query)
        for row in results:
            print(f"Table: {row[0]}, Column: {row[1]}, Collation: {row[2]}")

if __name__ == "__main__":
    diagnose_collations()
