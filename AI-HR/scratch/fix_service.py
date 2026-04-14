import os

file_path = r'd:\24985\code\boss-cli-main\AI-HR\ai_hr\services\ai_interviews.py'

with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

# 1. Fix the try: block missing contents and following prompt line
# We look for the 'try:' followed by 'prompt = ...'
corrupted_try = '''        try:
        prompt = f"{template.system_prompt}\\n{rendered}"'''

# Note: template.render needs to be inside try
fixed_try = '''        try:
            rendered = template.render(**prompt_ctx)
        except KeyError:
            logger.warning("Invalid runtime prompt placeholders for task=interview_followup, fallback to bundled v3")
            template = get_prompt_template(PromptTaskKey.INTERVIEW_FOLLOWUP, "v3")
            rendered = template.render(**prompt_ctx)
        prompt = f"{template.system_prompt}\\n{rendered}"'''

if corrupted_try in text:
    text = text.replace(corrupted_try, fixed_try)
    print("REPAIRED corrupted_try")
else:
    # If not found exactly, try a more flexible approach
    print("COULD NOT FIND corrupted_try EXACTLY, checking alternatives")
    if '        try:\n        prompt =' in text:
         text = text.replace('        try:\n        prompt =', '        try:\n            rendered = template.render(**prompt_ctx)\n        except KeyError:\n            logger.warning("Invalid runtime prompt placeholders")\n            template = get_prompt_template(PromptTaskKey.INTERVIEW_FOLLOWUP, "v3")\n            rendered = template.render(**prompt_ctx)\n        prompt =')
         print("REPAIRED with fallback search")

# 2. Ensure AIInterviewInvitationRepository is imported if not present
if 'AIInterviewInvitationRepository' not in text:
    text = text.replace('AIInterviewSessionRepository,', 'AIInterviewInvitationRepository,\n    AIInterviewSessionRepository,')
    print("ADDED AIInterviewInvitationRepository import")

# 3. Final check on the return block in get_ai_interview_service
old_return = '''    return AIInterviewService(
        session_repository=AIInterviewSessionRepository(session),
        runtime_repository=runtime_repository,'''
new_return = '''    return AIInterviewService(
        session_repository=AIInterviewSessionRepository(session),
        invitation_repository=AIInterviewInvitationRepository(session),
        runtime_repository=runtime_repository,'''

if old_return in text:
    text = text.replace(old_return, new_return)
    print("REPAIRED factory return")

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(text)

print("FIX VERSION 2 COMPLETED")
