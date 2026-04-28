import os
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/spreadsheets"
]

def get_calendar_service():
    creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
    return build("calendar", "v3", credentials=creds)

def calendar_add_event(title: str, date_str: str, time_str: str = "09:00", duration: int = 60) -> str:
    try:
        service = get_calendar_service()
        dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        end = dt + timedelta(minutes=duration)
        event = {
            "summary": title,
            "start": {"dateTime": dt.isoformat(), "timeZone": "Asia/Tashkent"},
            "end": {"dateTime": end.isoformat(), "timeZone": "Asia/Tashkent"},
        }
        result = service.events().insert(calendarId="primary", body=event).execute()
        return f"✅ Kalendarga qo'shildi: {title} — {date_str} {time_str}"
    except Exception as e:
        return f"❌ Calendar xatosi: {e}"

def calendar_get_events(days: int = 7) -> str:
    try:
        service = get_calendar_service()
        now = datetime.utcnow().isoformat() + "Z"
        end = (datetime.utcnow() + timedelta(days=days)).isoformat() + "Z"
        result = service.events().list(
            calendarId="primary", timeMin=now, timeMax=end,
            maxResults=10, singleEvents=True, orderBy="startTime"
        ).execute()
        events = result.get("items", [])
        if not events:
            return f"📅 Keyingi {days} kunda voqea yo'q."
        lines = [f"📅 Keyingi {days} kun:\n"]
        for e in events:
            start = e["start"].get("dateTime", e["start"].get("date", ""))[:16].replace("T", " ")
            lines.append(f"• {start} — {e['summary']}")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Calendar xatosi: {e}"
