"""
Ko'p akkaunt boshqaruvi
Har bir akkaunt uchun alohida sessiya fayli
"""
import os
import json
import asyncio
from telethon import TelegramClient
from telethon.tl.functions.contacts import ImportContactsRequest
from telethon.tl.types import InputPhoneContact
from dotenv import load_dotenv

load_dotenv()

API_ID   = int(os.getenv("TG_API_ID"))
API_HASH = os.getenv("TG_API_HASH")

ACCOUNTS_FILE = "accounts.json"

def load_accounts() -> list:
    """Akkauntlar ro'yxatini yuklash"""
    if os.path.exists(ACCOUNTS_FILE):
        with open(ACCOUNTS_FILE) as f:
            return json.load(f)
    return []

def save_accounts(accounts: list):
    """Akkauntlarni saqlash"""
    with open(ACCOUNTS_FILE, "w") as f:
        json.dump(accounts, f, ensure_ascii=False, indent=2)

def get_account_list() -> str:
    """Akkauntlar ro'yxatini matn shaklida"""
    accounts = load_accounts()
    if not accounts:
        return "📭 Akkauntlar yo'q.\n/addaccount +998901234567 Ism"
    lines = [f"👥 Akkauntlar ({len(accounts)} ta):\n"]
    for i, acc in enumerate(accounts, 1):
        status = "✅" if acc.get("active") else "⭕"
        lines.append(f"{i}. {status} {acc['name']} ({acc['phone']})")
    return "\n".join(lines)

async def add_account(phone: str, name: str) -> str:
    """Yangi akkaunt qo'shish va sessiya yaratish"""
    accounts = load_accounts()
    
    # Allaqachon bormi?
    for acc in accounts:
        if acc["phone"] == phone:
            return f"⚠️ {phone} allaqachon qo'shilgan."
    
    session_name = f"session_{phone.replace('+', '').replace(' ', '')}"
    
    try:
        client = TelegramClient(session_name, API_ID, API_HASH)
        await client.connect()
        
        if not await client.is_user_authorized():
            await client.send_code_request(phone)
            return f"📱 {phone} ga kod yuborildi.\n/confirmcode {phone} KOD"
        
        me = await client.get_me()
        await client.disconnect()
        
        accounts.append({
            "phone": phone,
            "name": name,
            "session": session_name,
            "active": True,
            "tg_name": f"{me.first_name or ''} {me.last_name or ''}".strip()
        })
        save_accounts(accounts)
        return f"✅ {name} ({phone}) qo'shildi!"
        
    except Exception as e:
        return f"❌ Xato: {e}"

async def confirm_code(phone: str, code: str, name: str = "") -> str:
    """Tasdiqlash kodi kiritish"""
    accounts = load_accounts()
    session_name = f"session_{phone.replace('+', '').replace(' ', '')}"
    
    try:
        client = TelegramClient(session_name, API_ID, API_HASH)
        await client.connect()
        await client.sign_in(phone, code)
        me = await client.get_me()
        await client.disconnect()
        
        # Akkaunt bormi? Yangilaymiz
        for acc in accounts:
            if acc["phone"] == phone:
                acc["active"] = True
                save_accounts(accounts)
                return f"✅ {me.first_name} ulandi!"
        
        # Yangi qo'shamiz
        display_name = name or me.first_name or phone
        accounts.append({
            "phone": phone,
            "name": display_name,
            "session": session_name,
            "active": True,
            "tg_name": f"{me.first_name or ''} {me.last_name or ''}".strip()
        })
        save_accounts(accounts)
        return f"✅ {display_name} muvaffaqiyatli ulandi!"
        
    except Exception as e:
        return f"❌ Kod xato yoki muddati o'tgan: {e}"

async def send_voice_from_account(account_idx: int, phone_to: str, audio_bytes: bytes, name: str = "") -> str:
    """Tanlangan akkauntdan ovozli xabar yuborish"""
    accounts = load_accounts()
    if account_idx < 1 or account_idx > len(accounts):
        return "❌ Akkaunt topilmadi."
    
    acc = accounts[account_idx - 1]
    session_name = acc["session"]
    
    try:
        client = TelegramClient(session_name, API_ID, API_HASH)
        await client.connect()
        
        if not await client.is_user_authorized():
            await client.disconnect()
            return f"❌ {acc['name']} sessiyasi tugagan. Qayta ulang."
        
        # Kontaktni topish
        contact = InputPhoneContact(client_id=0, phone=phone_to, first_name=name, last_name="")
        result = await client(ImportContactsRequest([contact]))
        
        if not result.users:
            await client.disconnect()
            return f"❌ {phone_to} Telegram da topilmadi."
        
        user = result.users[0]
        
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        
        await client.send_file(user.id, tmp_path, voice_note=True)
        os.unlink(tmp_path)
        await client.disconnect()
        
        return f"✅ {acc['name']} akkauntidan {name} ga yuborildi!"
        
    except Exception as e:
        return f"❌ {acc['name']} xatosi: {e}"

async def send_text_from_account(account_idx: int, phone_to: str, text: str, name: str = "") -> str:
    """Tanlangan akkauntdan matnli xabar yuborish"""
    accounts = load_accounts()
    if account_idx < 1 or account_idx > len(accounts):
        return "❌ Akkaunt topilmadi."
    
    acc = accounts[account_idx - 1]
    
    try:
        client = TelegramClient(acc["session"], API_ID, API_HASH)
        await client.connect()
        
        if not await client.is_user_authorized():
            await client.disconnect()
            return f"❌ {acc['name']} sessiyasi tugagan."
        
        contact = InputPhoneContact(client_id=0, phone=phone_to, first_name=name, last_name="")
        result = await client(ImportContactsRequest([contact]))
        
        if not result.users:
            await client.disconnect()
            return f"❌ {phone_to} topilmadi."
        
        await client.send_message(result.users[0].id, text)
        await client.disconnect()
        return f"✅ {acc['name']} akkauntidan {name} ga yuborildi!"
        
    except Exception as e:
        return f"❌ Xato: {e}"

async def send_video_from_account(account_idx: int, phone_to: str, video_bytes: bytes, name: str = "", caption: str = "") -> str:
    """Tanlangan akkauntdan video yuborish"""
    accounts = load_accounts()
    if account_idx < 1 or account_idx > len(accounts):
        return "❌ Akkaunt topilmadi."
    
    acc = accounts[account_idx - 1]
    
    try:
        client = TelegramClient(acc["session"], API_ID, API_HASH)
        await client.connect()
        
        contact = InputPhoneContact(client_id=0, phone=phone_to, first_name=name, last_name="")
        result = await client(ImportContactsRequest([contact]))
        
        if not result.users:
            await client.disconnect()
            return f"❌ {phone_to} topilmadi."
        
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp.write(video_bytes)
            tmp_path = tmp.name
        
        await client.send_file(result.users[0].id, tmp_path, caption=caption)
        os.unlink(tmp_path)
        await client.disconnect()
        return f"✅ {acc['name']} akkauntidan video yuborildi!"
        
    except Exception as e:
        return f"❌ Xato: {e}"
