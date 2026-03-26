from sqlalchemy import text
from ai_hr.db.session import engine
from pathlib import Path

print('STEP1_CONNECT_START')
with engine.connect() as conn:
    v = conn.execute(text('SELECT VERSION()')).scalar_one()
    db = conn.execute(text('SELECT DATABASE()')).scalar_one()
    print('STEP1_CONNECT_OK', v, db)

print('STEP2_INIT_SQL_START')
sql_path = Path(r'D:\24985\code\boss-cli-main\AI-HR\sql\init_mysql.sql')
raw = sql_path.read_text(encoding='utf-8')
statements = [s.strip() for s in raw.split(';') if s.strip()]
with engine.begin() as conn:
    for stmt in statements:
        conn.execute(text(stmt))
print('STEP2_INIT_SQL_OK', len(statements))

print('STEP3_QUERY_TABLES_START')
with engine.connect() as conn:
    targets = [
        'events',
        'ai_interview_sessions',
        'ai_interview_question_sets',
        'ai_interview_turns',
        'ai_interview_reports',
        'ai_interview_handoffs',
    ]
    for t in targets:
        c = conn.execute(text(f'SELECT COUNT(1) FROM `{t}`')).scalar_one()
        print('TABLE_COUNT', t, c)
print('STEP3_QUERY_TABLES_OK')
