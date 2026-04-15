import re

with open("ai_hr/services/ai_interviews.py", "r", encoding="utf-8") as f:
    text = f.read()

# Fix docstrings ending in ?" or similar missing their third quote
text = re.sub(r'\"\"\"\n', '\"\"\"\n', text)
text = text.replace('?""', '?"""')
text = text.replace('。""', '。"""')
text = text.replace('！""', '！"""')
text = text.replace('？""', '？"""')

# Fix mojibake docstrings that ate quotes
text = text.replace('銆?""', '銆?"""')

with open("ai_hr/services/ai_interviews.py", "w", encoding="utf-8") as f:
    f.write(text)
