
import os
import sys
from sqlalchemy import create_engine, text

# Add the project root to sys.path
sys.path.append(os.path.join(os.getcwd(), "AI-HR"))

from ai_hr.core.config import get_settings

def fix_collations():
    settings = get_settings()
    engine = create_engine(settings.database_url)
    
    with engine.connect() as conn:
        print("Starting collation unification process...")
        
        # 0. Disable FK checks
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        
        # 1. Get database name
        db_name = conn.execute(text("SELECT DATABASE()")).scalar()
        print(f"Target Database: {db_name}")
        
        # 2. Alter database default
        print(f"Altering database {db_name} defaults...")
        conn.execute(text(f"ALTER DATABASE `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
        
        # 3. Get all tables
        tables = conn.execute(text("SHOW TABLES")).scalars().all()
        
        # 4. Alter each table
        for table in tables:
            print(f"Converting table: {table} ...")
            try:
                # CONVERT TO performs the change on all columns as well
                conn.execute(text(f"ALTER TABLE `{table}` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
                # conn.commit() - if needed, but usually autocommit or handled by context
            except Exception as e:
                print(f"Error converting table {table}: {e}")
        
        # 5. Enable FK checks
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        conn.commit()
        
        print("\nCollation unification complete!")

if __name__ == "__main__":
    fix_collations()
