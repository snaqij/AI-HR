import re
with open("ai_hr/services/ai_interviews.py", "r", encoding="utf-8") as f:
    text = f.read()

text = re.sub(r'\"{4,}', '\"\"\"', text)

with open("ai_hr/services/ai_interviews.py", "w", encoding="utf-8") as f:
    f.write(text)
