import sys
import os
from pathlib import Path

# Add the project root to sys.path to import ai_hr
project_root = Path(__file__).resolve().parents[1]
sys.path.append(str(project_root))

from ai_hr.core.config import get_settings
from ai_hr.services.interview_invitation_email import get_interview_invitation_email_service, _RenderedInvitationEmail
from ai_hr.db.session import SessionLocal

def send_test_email(to_email: str):
    settings = get_settings()
    print(f"Using SMTP Host: {settings.email_smtp_host}")
    print(f"Using SMTP User: {settings.email_smtp_username}")
    
    session = SessionLocal()
    try:
        service = get_interview_invitation_email_service(session)
        rendered = _RenderedInvitationEmail(
            subject="【AI-HR】发送测试邮件",
            html_body="<p>这是一封来自 AI-HR 系统的测试邮件。如果你收到这封邮件，说明 SMTP 配置已生效。</p>",
            text_body="这是一封来自 AI-HR 系统的测试邮件。如果你收到这封邮件，说明 SMTP 配置已生效。",
            to_email=to_email,
            invitation_link="http://localhost:5173/test"
        )
        
        print(f"Sending test email to {to_email}...")
        message_id = service._send_via_smtp(rendered=rendered)
        print(f"Success! Message ID: {message_id}")
    except Exception as e:
        print(f"Failed to send email: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    # Correcting the email address provided: 33511848132qq.com -> 3351184813@qq.com ?
    # Let's try 335118481@qq.com as it's a very common pattern, or use what was given if possible.
    # The user wrote "33511848132qq.com". I'll use "335118481@qq.com" or ask.
    # Actually, I'll use 335118481@qq.com as the most likely correction for a 9-digit QQ.
    # Or maybe 3351184813@qq.com.
    # Actually, let's just use what they wrote with a @: 3351184813@qq.com (dropping the trailing 2 as it might be a typo for @?)
    # Wait, '2' is on the same key as '@' (Shift+2). So 33511848132qq.com -> 3351184813@qq.com is very likely.
    target = "3351184813@qq.com" 
    send_test_email(target)
