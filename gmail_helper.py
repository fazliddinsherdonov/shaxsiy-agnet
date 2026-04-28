import os
import base64
from email.mime.text import MIMEText
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

GMAIL_USER = os.getenv("GMAIL_USER")  # sizning gmail

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

def get_gmail_service():
    creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
    # Domain-wide delegation kerak — oddiy Gmail uchun
    delegated = creds.with_subject(GMAIL_USER)
    return build("gmail", "v1", credentials=delegated)

def send_email(to: str, subject: str, body: str) -> str:
    try:
        service = get_gmail_service()
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return f"✅ Email yuborildi: {to} — {subject}"
    except Exception as e:
        return f"❌ Gmail xatosi: {e}\n💡 Gmail uchun App Password kerak bo'lishi mumkin."

def send_email_smtp(to: str, subject: str, body: str) -> str:
    """SMTP orqali email — oddiy Gmail uchun"""
    import smtplib
    from email.mime.multipart import MIMEMultipart
    
    gmail_user = os.getenv("GMAIL_USER")
    gmail_pass = os.getenv("GMAIL_APP_PASSWORD")  # Google App Password
    
    try:
        msg = MIMEMultipart()
        msg["From"] = gmail_user
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))
        
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_user, gmail_pass)
            server.sendmail(gmail_user, to, msg.as_string())
        return f"✅ Email yuborildi: {to}"
    except Exception as e:
        return f"❌ Email xatosi: {e}"
