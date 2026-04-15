for i, line in enumerate(open('ai_hr/services/ai_interviews.py', encoding='utf-8')):
    if 'join_url = f"/ai-interview/session' in line:
        print(f"Match at Line {i+1}: {line.strip()}")
