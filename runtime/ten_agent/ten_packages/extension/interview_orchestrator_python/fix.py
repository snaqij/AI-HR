import sys
path = r'd:\24985\code\AI-HR\AI-HR\ten_agent\ten_packages\extension\interview_orchestrator_python\main.py'
with open(path, 'rb') as f:
    lines = f.readlines()
changed = False
for i, line in enumerate(lines):
    if b'bridge_instr' in line and b'10' in line:
        if b'"' not in line.strip()[1:]:
            lines[i] = line.rstrip() + b'"\r\n'
            changed = True
if changed:
    with open(path, 'wb') as f:
        f.writelines(lines)
    print("Fixed syntax error")
else:
    print("Not found or already fixed")
