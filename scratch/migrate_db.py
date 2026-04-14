import sys
import os
from sqlalchemy import text

# Add the project directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "AI-HR")))

from ai_hr.db.session import engine

def migrate_database():
    print("Running database migration: adding metadata_synced_at to candidates table...")
    
    with engine.connect() as connection:
        try:
            # Check if column exists first
            result = connection.execute(text("SHOW COLUMNS FROM candidates LIKE 'metadata_synced_at'"))
            if result.fetchone():
                print("Column 'metadata_synced_at' already exists.")
            else:
                connection.execute(text("ALTER TABLE candidates ADD COLUMN metadata_synced_at DATETIME(6) NULL"))
                connection.commit()
                print("Successfully added column 'metadata_synced_at'.")
        except Exception as e:
            print(f"Migration failed: {e}")

if __name__ == "__main__":
    migrate_database()
