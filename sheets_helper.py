import os
from datetime import datetime
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

def get_service():
    creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
    return build("sheets", "v4", credentials=creds).spreadsheets()

def ensure_sheets():
    """Kerakli sheet nomlarini yaratish"""
    service = get_service()
    meta = service.get(spreadsheetId=SHEET_ID).execute()
    existing = [s["properties"]["title"] for s in meta["sheets"]]
    needed = ["Xarajatlar", "Kontaktlar", "Vazifalar", "Qaydlar"]
    
    requests = []
    for name in needed:
        if name not in existing:
            requests.append({"addSheet": {"properties": {"title": name}}})
    
    if requests:
        service.batchUpdate(spreadsheetId=SHEET_ID, body={"requests": requests}).execute()
    
    # Header qo'shish
    headers = {
        "Xarajatlar": [["Sana", "Nom", "Miqdor", "Tur"]],
        "Kontaktlar": [["Sana", "Ism", "Telefon"]],
        "Vazifalar":  [["Sana", "Vazifa", "Status"]],
        "Qaydlar":    [["Sana", "Matn"]],
    }
    for sheet, header in headers.items():
        if sheet not in existing:
            service.values().update(
                spreadsheetId=SHEET_ID,
                range=f"{sheet}!A1",
                valueInputOption="RAW",
                body={"values": header}
            ).execute()

# ── Xarajat qo'shish ──────────────────────────────────────────────────────────
def sheets_add_expense(name: str, amount: float, exp_type: str = "Xarajat") -> str:
    try:
        service = get_service()
        row = [datetime.now().strftime("%Y-%m-%d %H:%M"), name, amount, exp_type]
        service.values().append(
            spreadsheetId=SHEET_ID,
            range="Xarajatlar!A:D",
            valueInputOption="RAW",
            body={"values": [row]}
        ).execute()
        return f"✅ Sheets ga yozildi: {name} — {amount:,.0f} ({exp_type})"
    except Exception as e:
        return f"❌ Sheets xatosi: {e}"

# ── Xarajatlarni o'qish ───────────────────────────────────────────────────────
def sheets_get_expenses(limit: int = 10) -> str:
    try:
        service = get_service()
        result = service.values().get(
            spreadsheetId=SHEET_ID,
            range="Xarajatlar!A:D"
        ).execute()
        rows = result.get("values", [])[1:]  # header ni o'tkazib yuborish
        if not rows:
            return "📭 Xarajatlar jadvali bo'sh."
        lines = [f"💰 Google Sheets xarajatlar (so'nggi {limit} ta):\n"]
        total = 0
        for row in rows[-limit:]:
            sana = row[0] if len(row) > 0 else ""
            nom = row[1] if len(row) > 1 else ""
            miqdor = float(row[2]) if len(row) > 2 else 0
            tur = row[3] if len(row) > 3 else ""
            total += miqdor
            lines.append(f"• [{sana[:10]}] {nom}: {miqdor:,.0f} {f'({tur})' if tur else ''}")
        lines.append(f"\n💵 Ko'rsatilgan jami: {total:,.0f}")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Sheets xatosi: {e}"

# ── Kontakt qo'shish ──────────────────────────────────────────────────────────
def sheets_add_contact(name: str, phone: str) -> str:
    try:
        service = get_service()
        row = [datetime.now().strftime("%Y-%m-%d"), name, phone]
        service.values().append(
            spreadsheetId=SHEET_ID,
            range="Kontaktlar!A:C",
            valueInputOption="RAW",
            body={"values": [row]}
        ).execute()
        return f"✅ Sheets ga kontakt saqlandi: {name} — {phone}"
    except Exception as e:
        return f"❌ Sheets xatosi: {e}"

# ── Kontaktlarni o'qish ───────────────────────────────────────────────────────
def sheets_get_contacts() -> str:
    try:
        service = get_service()
        result = service.values().get(
            spreadsheetId=SHEET_ID,
            range="Kontaktlar!A:C"
        ).execute()
        rows = result.get("values", [])[1:]
        if not rows:
            return "📭 Kontaktlar jadvali bo'sh."
        lines = [f"👥 Google Sheets kontaktlar ({len(rows)} ta):\n"]
        for row in rows:
            ism = row[1] if len(row) > 1 else ""
            tel = row[2] if len(row) > 2 else ""
            lines.append(f"• {ism}: {tel}")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Sheets xatosi: {e}"

# ── Vazifa qo'shish ───────────────────────────────────────────────────────────
def sheets_add_todo(text: str) -> str:
    try:
        service = get_service()
        row = [datetime.now().strftime("%Y-%m-%d %H:%M"), text, "Bajarilmagan"]
        service.values().append(
            spreadsheetId=SHEET_ID,
            range="Vazifalar!A:C",
            valueInputOption="RAW",
            body={"values": [row]}
        ).execute()
        return f"✅ Sheets ga vazifa saqlandi: {text[:50]}"
    except Exception as e:
        return f"❌ Sheets xatosi: {e}"

# ── Vazifalarni o'qish ────────────────────────────────────────────────────────
def sheets_get_todos() -> str:
    try:
        service = get_service()
        result = service.values().get(
            spreadsheetId=SHEET_ID,
            range="Vazifalar!A:C"
        ).execute()
        rows = result.get("values", [])[1:]
        if not rows:
            return "📭 Vazifalar jadvali bo'sh."
        active = [r for r in rows if len(r) < 3 or r[2] != "Bajarilgan"]
        done = [r for r in rows if len(r) >= 3 and r[2] == "Bajarilgan"]
        lines = ["📋 Google Sheets vazifalar:\n"]
        if active:
            lines.append("⬜ Bajarilmagan:")
            for r in active:
                lines.append(f"  • {r[1] if len(r) > 1 else ''}")
        if done:
            lines.append("\n✅ Bajarilgan:")
            for r in done:
                lines.append(f"  • {r[1] if len(r) > 1 else ''}")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Sheets xatosi: {e}"

# ── Qayd qo'shish ─────────────────────────────────────────────────────────────
def sheets_add_note(text: str) -> str:
    try:
        service = get_service()
        row = [datetime.now().strftime("%Y-%m-%d %H:%M"), text]
        service.values().append(
            spreadsheetId=SHEET_ID,
            range="Qaydlar!A:B",
            valueInputOption="RAW",
            body={"values": [row]}
        ).execute()
        return f"✅ Sheets ga qayd saqlandi: {text[:50]}"
    except Exception as e:
        return f"❌ Sheets xatosi: {e}"

# ── Qaydlarni o'qish ──────────────────────────────────────────────────────────
def sheets_get_notes(limit: int = 10) -> str:
    try:
        service = get_service()
        result = service.values().get(
            spreadsheetId=SHEET_ID,
            range="Qaydlar!A:B"
        ).execute()
        rows = result.get("values", [])[1:]
        if not rows:
            return "📭 Qaydlar jadvali bo'sh."
        lines = [f"📝 Google Sheets qaydlar (so'nggi {limit} ta):\n"]
        for row in rows[-limit:]:
            sana = row[0][:10] if row else ""
            matn = row[1] if len(row) > 1 else ""
            lines.append(f"• [{sana}] {matn}")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Sheets xatosi: {e}"
