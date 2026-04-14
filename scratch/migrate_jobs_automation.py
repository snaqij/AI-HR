import sys
import os
from sqlalchemy import text

# Add the project directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "AI-HR")))

from ai_hr.db.session import engine

def migrate_jobs_table():
    print("Running database migration: adding automation settings to jobs table...")
    
    columns_to_add = [
        ("auto_request_resume", "BOOLEAN DEFAULT FALSE"),
        ("min_degree", "VARCHAR(64) NULL"),
        ("min_experience_years", "INT NULL"),
        ("max_daily_resume_requests", "INT DEFAULT 10")
    ]
    
    with engine.connect() as connection:
        for col_name, col_def in columns_to_add:
            try:
                # Check if column exists
                result = connection.execute(text(f"SHOW COLUMNS FROM jobs LIKE '{col_name}'"))
                if result.fetchone():
                    print(f"Column '{col_name}' already exists.")
                else:
                    connection.execute(text(f"ALTER TABLE jobs ADD COLUMN {col_name} {col_def}"))
                    connection.commit()
                    print(f"Successfully added column '{col_name}'.")
            except Exception as e:
                print(f"Failed to add column '{col_name}': {e}")

if __name__ == "__main__":
    migrate_jobs_table()
