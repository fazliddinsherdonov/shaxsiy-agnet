import os
import asyncio
import tempfile
import aiohttp
from datetime import datetime
from dotenv import load_dotenv
from groq import Groq
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, BufferedInputFile, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.filters import CommandStart, Command
from aiogram.fsm.storage.memory import MemoryStorage

from userbot import send_voice_to_phone, send_text_to_phone, send_video_to_phone, send_videonote_to_phone, client as userbot_client
import multi_account as ma
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram import F as AiogramF
from videonote_maker import text_to_videonote, make_avatar_videonote
import json
from video_converter import convert_to_videonote, is_ffmpeg_installed
import notion_helper as notion
import sheets_helper as sheets
import calendar_helper as cal
import gmail_helper as gmail
import extra_helpers as extra

load_dotenv()

BOT_TOKEN       = os.getenv("BOT_TOKEN")
GROQ_API_KEY    = os.getenv("GROQ_API_KEY")
MY_ID           = int(os.getenv("MY_TELEGRAM_ID"))
TG_PHONE        = os.getenv("TG_PHONE")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")

bot    = Bot(token=BOT_TOKEN)
dp     = Dispatcher(storage=MemoryStorage())
client = Groq(api_key=GROQ_API_KEY)

MODELS = ["llama-3.1-8b-instant", "llama-3.3-70b-versatile", "gemma2-9b-it"]

SYSTEM_PROMPT = """
Sening isming Jarvis. Sen o'ta aqlli, professional va tartibli shaxsiy yordamchisan.
QOIDALAR:
1. FAQAT O'ZBEK TILIDA javob ber.
2. Qisqa va lo'nda javob ber.
3. Agar foydalanuvchi "qaydla", "saqla", "eslab qol", "yozib qo'y" desa:
   SAVE_NOTE:matn
4. Agar foydalanuvchi "vazifa", "qilish kerak", "eslatma qo'y" desa:
   SAVE_TODO:matn
5. Agar kimdir yozgan xabarni qaytarish kerak bo'lsa:
   REPLY_TO:username_yoki_id|matn

BUYRUQLAR FORMATI (faqat kerak bo'lganda ishlat):
SEND_VOICE:ism:matn
SEND_TEXT:ism:matn
SEND_VIDEO:ism:izoh
SEND_VIDEONOTE:ism (foydalanuvchi yuborgan dumaloq video)
MAKE_VIDEONOTE:ism:matn (AI o'zi dumaloq video tayyorlaydi)
WEATHER:shahar
CURRENCY:USD
SEARCH:qidiruv matni
NEWS:mavzu
SPOTIFY:qo'shiq nomi
GEMINI:savol
CALENDAR_ADD:sarlavha|YYYY-MM-DD|HH:MM
CALENDAR_GET:7
EMAIL:email@gmail.com|mavzu|matn
NOTION_ADD_NOTE:matn
NOTION_ADD_TODO:matn
NOTION_DONE_TODO:matn
NOTION_ADD_EXPENSE:nom|miqdor|tur
SHEETS_ADD_NOTE:matn
SHEETS_ADD_TODO:matn
SHEETS_ADD_EXPENSE:nom|miqdor|tur
REPORT:hafta
NOT_FOUND:ism
"""

conversation_histories = {}
pending_videos = {}  # user_id: video_bytes
AUTO_REPLY = {"enabled": True}  # Avtomatik javob holati
contacts  = {}
notes     = []
todos     = []
reminders = []
stats = {"messages_sent":0,"voice_sent":0,"text_sent":0,"today":datetime.now().strftime("%Y-%m-%d")}


CUSTOM_BUTTONS = []  # Foydalanuvchi qo'shadigan tugmalar
user_state = {}      # {user_id: "waiting_note" | ...}
pending_sends = {}   # {user_id: {"type":..., "contact":..., "data":...}}

def update_stats(t="message"):
    today = datetime.now().strftime("%Y-%m-%d")
    if stats["today"] != today:
        stats.update({"messages_sent":0,"voice_sent":0,"text_sent":0,"today":today})
    stats["messages_sent"] += 1
    if t=="voice": stats["voice_sent"]+=1
    elif t=="text": stats["text_sent"]+=1


def account_keyboard(action: str) -> InlineKeyboardMarkup:
    accounts = ma.load_accounts()
    buttons = []
    for i, acc in enumerate(accounts, 1):
        status = "✅" if acc.get("active") else "⭕"
        buttons.append([InlineKeyboardButton(
            text=f"{status} {acc['name']} ({acc['phone']})",
            callback_data=f"acc_{action}_{i}"
        )])
    buttons.append([InlineKeyboardButton(text="1️⃣ Asosiy akkaunt", callback_data=f"acc_{action}_0")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def main_menu():
    base = [
        [KeyboardButton(text="📝 Qaydlar"),       KeyboardButton(text="✅ Vazifalar")],
        [KeyboardButton(text="👥 Kontaktlar"),    KeyboardButton(text="💰 Moliya")],
        [KeyboardButton(text="⏰ Eslatmalar"),    KeyboardButton(text="📅 Kalendar")],
        [KeyboardButton(text="📰 Yangiliklar"),   KeyboardButton(text="🔍 Qidirish")],
        [KeyboardButton(text="👥 Guruhlar"),      KeyboardButton(text="📊 Hisobot")],
        [KeyboardButton(text="🔐 Parollar"),      KeyboardButton(text="🎂 Tug'ilgan kun")],
        [KeyboardButton(text="📨 Xabar yuborish"),KeyboardButton(text="📧 Email")],
        [KeyboardButton(text="⚙️ Sozlamalar"),    KeyboardButton(text="❓ Yordam")],
        [KeyboardButton(text="👤 Akkauntlar")],
    ]
    if CUSTOM_BUTTONS:
        row = []
        for btn in CUSTOM_BUTTONS:
            row.append(KeyboardButton(text=btn["label"]))
            if len(row) == 2:
                base.insert(-1, row)
                row = []
        if row:
            base.insert(-1, row)
    base.append([KeyboardButton(text="➕ Tugma qo'shish"), KeyboardButton(text="🗑️ Tugma o'chirish")])
    return ReplyKeyboardMarkup(keyboard=base, resize_keyboard=True)

def notes_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ Qayd qo'shish")],
        [KeyboardButton(text="📋 Barcha qaydlar"), KeyboardButton(text="📒 Notion qaydlar")],
        [KeyboardButton(text="📊 Sheets qaydlar")],
        [KeyboardButton(text="🔙 Asosiy menyu")],
    ], resize_keyboard=True)

def todos_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ Vazifa qo'shish")],
        [KeyboardButton(text="📋 Barcha vazifalar"), KeyboardButton(text="✅ Bajarildi belgilash")],
        [KeyboardButton(text="📒 Notion vazifalar"), KeyboardButton(text="📊 Sheets vazifalar")],
        [KeyboardButton(text="🔙 Asosiy menyu")],
    ], resize_keyboard=True)

def contacts_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ Kontakt qo'shish")],
        [KeyboardButton(text="📋 Kontaktlar ro'yxati")],
        [KeyboardButton(text="🗑️ Kontakt o'chirish")],
        [KeyboardButton(text="🔙 Asosiy menyu")],
    ], resize_keyboard=True)

def finance_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="💸 Xarajat qo'shish"), KeyboardButton(text="💰 Daromad qo'shish")],
        [KeyboardButton(text="📊 Xarajatlar ro'yxati")],
        [KeyboardButton(text="📈 Haftalik hisobot"), KeyboardButton(text="📉 Oylik hisobot")],
        [KeyboardButton(text="🔙 Asosiy menyu")],
    ], resize_keyboard=True)

def reminders_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ Eslatma qo'shish"), KeyboardButton(text="🔔 Kunlik eslatma")],
        [KeyboardButton(text="📋 Eslatmalar ro'yxati")],
        [KeyboardButton(text="🗑️ Eslatma o'chirish")],
        [KeyboardButton(text="🔙 Asosiy menyu")],
    ], resize_keyboard=True)

def calendar_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ Voqea qo'shish")],
        [KeyboardButton(text="📅 7 kunlik voqealar"), KeyboardButton(text="📅 30 kunlik voqealar")],
        [KeyboardButton(text="🔙 Asosiy menyu")],
    ], resize_keyboard=True)

def groups_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ Guruh qo'shish")],
        [KeyboardButton(text="📋 Guruhlar ro'yxati")],
        [KeyboardButton(text="🗑️ Guruh o'chirish")],
        [KeyboardButton(text="🔙 Asosiy menyu")],
    ], resize_keyboard=True)

def passwords_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔐 Parol saqlash")],
        [KeyboardButton(text="🔍 Parol olish"), KeyboardButton(text="📋 Parollar ro'yxati")],
        [KeyboardButton(text="🗑️ Parol o'chirish")],
        [KeyboardButton(text="🔙 Asosiy menyu")],
    ], resize_keyboard=True)

def birthdays_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ Tug'ilgan kun qo'shish")],
        [KeyboardButton(text="📋 Tug'ilgan kunlar ro'yxati")],
        [KeyboardButton(text="🔙 Asosiy menyu")],
    ], resize_keyboard=True)

def send_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🎙️ Ovozli xabar yuborish")],
        [KeyboardButton(text="📝 Matnli xabar yuborish")],
        [KeyboardButton(text="🎬 Video xabar yuborish")],
        [KeyboardButton(text="🔙 Asosiy menyu")],
    ], resize_keyboard=True)

def settings_menu():
    auto_status = "✅ Yoqiq" if AUTO_REPLY["enabled"] else "❌ O'chiq"
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📊 Statistika")],
        [KeyboardButton(text="🧹 Suhbatni tozalash")],
        [KeyboardButton(text="📊 Hozir hisobot")],
        [KeyboardButton(text=f"🤖 Avtomatik javob: {auto_status}")],
        [KeyboardButton(text="🔙 Asosiy menyu")],
    ], resize_keyboard=True)

async def is_owner(m: Message) -> bool:
    if m.from_user.id != MY_ID:
        await m.answer("⛔ Bu bot shaxsiy.")
        return False
    return True

def decode_qp(text):
    import quopri
    try: return quopri.decodestring(text.encode()).decode("utf-8",errors="ignore")
    except: return text

def parse_vcf(content):
    result,cur_name,cur_phone={},None,None
    for line in content.splitlines():
        line=line.strip()
        if line.startswith("FN:"): cur_name=line[3:]
        elif "FN;" in line and "QUOTED-PRINTABLE" in line: cur_name=decode_qp(line.split(":",1)[-1])
        elif line.startswith("TEL"):
            p="".join(c for c in line.split(":")[-1] if c.isdigit() or c=="+")
            if len(p)>=7: cur_phone=p if p.startswith("+") else "+"+p
        elif line=="END:VCARD":
            if cur_name and cur_phone:
                result[cur_name.lower().strip()]={"name":cur_name.strip(),"phone":cur_phone}
            cur_name=cur_phone=None
    return result

def find_contact(name):
    n=name.lower().strip()
    if n in contacts: return contacts[n]
    for k,v in contacts.items():
        if n in k or k.startswith(n): return v
    return None


async def _sheets_note(text):
    try: sheets.sheets_add_note(text)
    except: pass

async def _sheets_todo(text):
    try: sheets.sheets_add_todo(text)
    except: pass

async def text_to_voice(text):
    try:
        r=client.audio.speech.create(model="canopylabs/orpheus-v1-english",voice="sarah",input=text,response_format="wav")
        return r.content
    except Exception as e:
        print(f"TTS xatosi: {e}"); return None

async def get_weather(city):
    if not WEATHER_API_KEY: return "⚠️ WEATHER_API_KEY kerak."
    try:
        url=f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric&lang=ru"
        async with aiohttp.ClientSession() as s:
            async with s.get(url) as r:
                d=await r.json()
                if d.get("cod")!=200: return f"❌ '{city}' topilmadi"
                return(f"🌤️ {city.title()}:\n🌡️ {d['main']['temp']:.0f}°C\n"
                       f"☁️ {d['weather'][0]['description']}\n"
                       f"💧 {d['main']['humidity']}%  💨 {d['wind']['speed']}m/s")
    except Exception as e: return f"❌ {e}"

async def get_currency(code):
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get("https://cbu.uz/uz/arkhiv-kursov-valyut/json/") as r:
                data=await r.json(content_type=None)
                for item in data:
                    if item["Ccy"]==code.upper():
                        return f"💱 1 {code.upper()} = {item['Rate']} so'm\n📅 {item['Date']}"
                return f"❌ '{code}' topilmadi"
    except Exception as e: return f"❌ {e}"

def get_ai_response(user_id, user_message):
    if user_id not in conversation_histories: conversation_histories[user_id]=[]
    contacts_info=", ".join(f"{v['name']} ({v['phone']})" for v in contacts.values()) or "yo'q"
    system=SYSTEM_PROMPT+f"\nKontaktlar: {contacts_info}\nSana: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    conversation_histories[user_id].append({"role":"user","content":user_message})
    for model in MODELS:
        try:
            c=client.chat.completions.create(
                model=model,
                messages=[{"role":"system","content":system},*conversation_histories[user_id]],
                temperature=0.6,max_tokens=1024)
            resp=c.choices[0].message.content
            conversation_histories[user_id].append({"role":"assistant","content":resp})
            return resp
        except Exception as e:
            if "429" in str(e) or "rate_limit" in str(e).lower(): continue
            raise e
    conversation_histories[user_id].pop()
    return "⚠️ Modellar band. 10 daqiqadan so'ng urinib ko'ring."

async def process_ai_response(message: Message, ai_response: str):
    lines=ai_response.strip().splitlines()
    out=[]
    for line in lines:
        line=line.strip()
        if not line: continue

        if line.startswith("SEND_VOICE:") or line.startswith("SEND_TEXT:"):
            is_voice=line.startswith("SEND_VOICE:")
            parts=line.split(":",2)
            if len(parts)==3:
                names=[n.strip() for n in parts[1].split(",")]
                msg_text=parts[2].strip()
                audio=await text_to_voice(msg_text) if is_voice else None
                for name in names:
                    contact=find_contact(name)
                    if contact:
                        accounts = ma.load_accounts()
                        if accounts:
                            # Akkaunt tanlash
                            msg_type = "voice" if (is_voice and audio) else "text"
                            pending_sends[message.from_user.id] = {
                                "type": msg_type,
                                "contact": contact,
                                "data": audio if (is_voice and audio) else msg_text,
                                "account_name": "Asosiy"
                            }
                            kb = account_keyboard(msg_type)
                            await message.answer(
                                f"👤 {contact['name']} ga qaysi akkauntdan yuboramiz?",
                                reply_markup=kb
                            )
                        else:
                            # Faqat asosiy akkaunt
                            await message.answer(f"📤 {contact['name']} ga yuborilmoqda...")
                            if is_voice and audio:
                                ok=await send_voice_to_phone(contact["phone"],audio,contact["name"])
                                update_stats("voice")
                                out.append(f"✅ {contact['name']} ga ovozli xabar" if ok else f"❌ {contact['name']} — topilmadi")
                            else:
                                ok=await send_text_to_phone(contact["phone"],msg_text,contact["name"])
                                update_stats("text")
                                out.append(f"✅ {contact['name']} ga matnli xabar" if ok else f"❌ {contact['name']} — topilmadi")
                    else:
                        out.append(f"❓ '{name}' kontaktlarda topilmadi")

        elif line.startswith("SEND_VIDEO:"):
            parts = line.split(":", 2)
            if len(parts) >= 2:
                names = [n.strip() for n in parts[1].split(",")]
                caption = parts[2].strip() if len(parts) > 2 else ""
                if hasattr(message, '_pending_video') and message._pending_video:
                    video_bytes = message._pending_video
                    for name in names:
                        contact = find_contact(name)
                        if contact:
                            await message.answer(f"📤 {contact['name']} ga video yuborilmoqda...")
                            ok = await send_video_to_phone(contact["phone"], video_bytes, contact["name"], caption)
                            out.append(f"✅ {contact['name']} ga video yuborildi" if ok else f"❌ {contact['name']} — topilmadi")
                        else:
                            out.append(f"❓ '{name}' kontaktlarda topilmadi")
                else:
                    out.append("⚠️ Avval video fayl yuboring, keyin kimga yuborishni ayting.")

        elif line.startswith("MAKE_VIDEONOTE:"):
            parts = line.split(":", 2)
            if len(parts) == 3:
                names = [n.strip() for n in parts[1].split(",")]
                vn_text = parts[2].strip()
                await message.answer("🎬 Dumaloq video tayyorlanmoqda...")
                avatar = "avatar.jpg" if os.path.exists("avatar.jpg") else None
                video_bytes = await make_avatar_videonote(vn_text, client, avatar)
                if video_bytes:
                    for name in names:
                        contact = find_contact(name)
                        if contact:
                            ok = await send_videonote_to_phone(contact["phone"], video_bytes, contact["name"])
                            out.append(f"✅ {contact['name']} ga AI dumaloq video yuborildi" if ok else f"❌ {contact['name']} — topilmadi")
                        else:
                            out.append(f"❓ '{name}' topilmadi")
                else:
                    out.append("❌ Video tayyorlashda xato. ffmpeg o'rnatilganmi?")

        elif line.startswith("SEND_VIDEONOTE:"):
            parts = line.split(":", 1)
            if len(parts) >= 2:
                names = [n.strip() for n in parts[1].split(",")]
                if hasattr(message, '_pending_video') and message._pending_video:
                    await message.answer("⚙️ Video dumaloq formatga o'tkazilmoqda...")
                    loop = asyncio.get_event_loop()
                    note_bytes = await loop.run_in_executor(
                        None, convert_to_videonote, message._pending_video
                    )
                    if not note_bytes:
                        out.append("❌ Video o'tkazishda xato. ffmpeg o'rnatilganmi?")
                    else:
                        for name in names:
                            contact = find_contact(name)
                            if contact:
                                await message.answer(f"📤 {contact['name']} ga dumaloq video yuborilmoqda...")
                                ok = await send_videonote_to_phone(contact["phone"], note_bytes, contact["name"])
                                out.append(f"✅ {contact['name']} ga ⭕ dumaloq video yuborildi" if ok else f"❌ {contact['name']} — topilmadi")
                            else:
                                out.append(f"❓ '{name}' kontaktlarda topilmadi")
                else:
                    out.append("⚠️ Avval video yuboring, keyin kimga yuborishni ayting.")

        elif line.startswith("SAVE_NOTE:"):
            note_text = line.split(":",1)[1].strip()
            note = {"id": len(notes)+1, "text": note_text, "date": datetime.now().strftime("%d.%m %H:%M")}
            notes.append(note)
            asyncio.create_task(notion.notion_add_note(note_text))
            asyncio.create_task(_sheets_note(note_text))
            out.append(f"📝 Qayd saqlandi: {note_text[:50]}")

        elif line.startswith("SAVE_TODO:"):
            todo_text = line.split(":",1)[1].strip()
            todo = {"id": len(todos)+1, "text": todo_text, "done": False, "date": datetime.now().strftime("%d.%m")}
            todos.append(todo)
            asyncio.create_task(notion.notion_add_todo(todo_text))
            asyncio.create_task(_sheets_todo(todo_text))
            out.append(f"✅ Vazifa saqlandi: {todo_text[:50]}")

        elif line.startswith("REPLY_TO:"):
            parts = line.split(":",1)[1].split("|",1)
            if len(parts)==2:
                target, reply_text = parts[0].strip(), parts[1].strip()
                try:
                    ok = await send_text_to_phone(target, reply_text, target)
                    out.append(f"✅ Javob yuborildi: {reply_text[:40]}" if ok else f"❌ Yuborib bo'lmadi")
                except Exception as e:
                    out.append(f"❌ Xato: {e}")

        elif line.startswith("NOT_FOUND:"):
            out.append(f"❓ '{line.split(chr(58),1)[1]}' topilmadi")
        elif line.startswith("WEATHER:"): out.append(await get_weather(line.split(":",1)[1].strip()))
        elif line.startswith("CURRENCY:"): out.append(await get_currency(line.split(":",1)[1].strip()))
        elif line.startswith("SEARCH:"): out.append(await extra.web_search(line.split(":",1)[1].strip()))
        elif line.startswith("NEWS:"): out.append(await extra.get_news(line.split(":",1)[1].strip()))
        elif line.startswith("SPOTIFY:"): out.append(await extra.spotify_search(line.split(":",1)[1].strip()))
        elif line.startswith("GEMINI:"): out.append(await extra.gemini_response(line.split(":",1)[1].strip()))
        elif line.startswith("REPORT:"): out.append(await extra.generate_report(line.split(":",1)[1].strip()))
        elif line.startswith("CALENDAR_ADD:"):
            p=line.split(":",1)[1].split("|")
            out.append(cal.calendar_add_event(p[0],p[1],p[2] if len(p)>2 else "09:00"))
        elif line.startswith("CALENDAR_GET:"):
            out.append(cal.calendar_get_events(int(line.split(":",1)[1])))
        elif line.startswith("EMAIL:"):
            p=line.split(":",1)[1].split("|")
            out.append(gmail.send_email_smtp(p[0],p[1],p[2]))
        elif line.startswith("NOTION_ADD_NOTE:"): out.append(await notion.notion_add_note(line.split(":",1)[1].strip()))
        elif line.startswith("NOTION_ADD_TODO:"): out.append(await notion.notion_add_todo(line.split(":",1)[1].strip()))
        elif line.startswith("NOTION_DONE_TODO:"): out.append(await notion.notion_done_todo(line.split(":",1)[1].strip()))
        elif line.startswith("NOTION_ADD_EXPENSE:"):
            p=line.split(":",1)[1].split("|")
            out.append(await notion.notion_add_expense(p[0],float(p[1]),p[2] if len(p)>2 else "Xarajat"))
        elif line.startswith("SHEETS_ADD_NOTE:"): out.append(sheets.sheets_add_note(line.split(":",1)[1].strip()))
        elif line.startswith("SHEETS_ADD_TODO:"): out.append(sheets.sheets_add_todo(line.split(":",1)[1].strip()))
        elif line.startswith("SHEETS_ADD_EXPENSE:"):
            p=line.split(":",1)[1].split("|")
            out.append(sheets.sheets_add_expense(p[0],float(p[1]),p[2] if len(p)>2 else "Xarajat"))
        else:
            if line.strip(): out.append(line)

    if out: await message.answer("\n".join(out))

# ══════════════════════════════════════════════════════════════════════════════
@dp.message(CommandStart())
async def start(m: Message):
    if not await is_owner(m): return
    await m.answer(
        "👋 Salom! Men Jarvis — shaxsiy AI yordamchingizman!\n\n"
        "Quyidagi menyudan foydalaning 👇",
        reply_markup=main_menu()
    )

@dp.message(Command("help"))
async def help_cmd(m: Message):
    if not await is_owner(m): return
    await m.answer(
        "📚 BARCHA BUYRUQLAR:\n\n"
        "👤 KONTAKTLAR:\n"
        "/contacts /addcontact /delcontact\n\n"
        "📝 QAYDLAR:\n"
        "/note /notes /notionnotes /sheetsnotes /delnote\n\n"
        "✅ VAZIFALAR:\n"
        "/todo /todos /notiontodos /sheetstodos /done /deltodo\n\n"
        "💰 MOLIYA:\n"
        "/expense /income /expenses\n"
        "/report hafta — haftalik\n"
        "/report oy — oylik\n\n"
        "📅 KALENDAR:\n"
        "/caladd 2026-05-01 10:00 Uchrashuv\n"
        "/calget 7 — 7 kunlik\n\n"
        "📧 EMAIL:\n"
        "/email email@gmail.com|Mavzu|Matn\n\n"
        "🔐 PAROLLAR:\n"
        "/passsave Gmail user@gmail.com parol123\n"
        "/passget Gmail\n"
        "/passlist\n"
        "/passdel Gmail\n\n"
        "🎂 TUG'ILGAN KUN:\n"
        "/bdadd Ism 15.03.1995\n"
        "/bdlist\n\n"
        "🔍 QIDIRISH:\n"
        "/search qidiruv matni\n\n"
        "📰 YANGILIKLAR:\n"
        "/news mavzu\n\n"
        "🎵 SPOTIFY:\n"
        "/spotify qo'shiq nomi\n\n"
        "⏰ ESLATMALAR:\n"
        "/remind 10:30 Matn\n"
        "/repeatremind 09:00 Matn\n"
        "/reminders /delremind\n\n"
        "🌤️ /weather Toshkent\n"
        "💱 /currency USD\n"
        "📊 /stats\n"
        "/clear\n\n"
        "👥 GURUHLAR:\n"
        "/groupadd -100123 Guruh nomi\n"
        "/groupdel -100123\n"
        "/grouplist\n"
        "/groupmode -100123 smart/all\n\n"
        "🎬 DUMALOQ VIDEO:\n"
        "/makevn Ism Matn — AI dumaloq video\n"
        "Video yuboring → kimga yuborishni ayting"
    )

@dp.message(Command("contacts"))
async def show_contacts(m: Message):
    if not await is_owner(m): return
    if not contacts: await m.answer("📭 Kontaktlar yo'q."); return
    lines=[f"📋 ({len(contacts)} ta):\n"]
    for i,v in enumerate(list(contacts.values())[:50],1):
        lines.append(f"{i}. {v['name']}: {v['phone']}")
    await m.answer("\n".join(lines))

@dp.message(Command("addcontact"))
async def add_contact(m: Message):
    if not await is_owner(m): return
    try:
        parts=m.text.split(" ",2); name,phone=parts[1],parts[2]
        phone="".join(c for c in phone if c.isdigit() or c=="+")
        if not phone.startswith("+"): phone="+"+phone
        contacts[name.lower()]={"name":name,"phone":phone}
        n_res=await notion.notion_add_contact(name,phone)
        s_res=sheets.sheets_add_contact(name,phone)
        await m.answer(f"✅ {name} — {phone}\n{n_res}\n{s_res}")
    except: await m.answer("⚠️ /addcontact Ism +998901234567")

@dp.message(Command("delcontact"))
async def del_contact(m: Message):
    if not await is_owner(m): return
    try:
        name=m.text.split(" ",1)[1].strip().lower()
        if name in contacts: contacts.pop(name); await m.answer("🗑️ O'chirildi.")
        else: await m.answer("❓ Topilmadi.")
    except: await m.answer("⚠️ /delcontact Ism")

@dp.message(Command("note"))
async def add_note(m: Message):
    if not await is_owner(m): return
    try:
        text=m.text.split(" ",1)[1].strip()
        note={"id":len(notes)+1,"text":text,"date":datetime.now().strftime("%d.%m %H:%M")}
        notes.append(note)
        n_res=await notion.notion_add_note(text)
        s_res=sheets.sheets_add_note(text)
        await m.answer(f"📝 #{note['id']} saqlandi\n{n_res}\n{s_res}")
    except: await m.answer("⚠️ /note Matn")

@dp.message(Command("notes"))
async def show_notes(m: Message):
    if not await is_owner(m): return
    if not notes: await m.answer("📭 Qaydlar yo'q."); return
    lines=[f"📝 ({len(notes)} ta):\n"]
    for n in notes: lines.append(f"{n['id']}. [{n['date']}] {n['text']}")
    await m.answer("\n".join(lines))

@dp.message(Command("notionnotes"))
async def notion_notes(m: Message):
    if not await is_owner(m): return
    await m.answer(await notion.notion_get_notes())

@dp.message(Command("sheetsnotes"))
async def sheets_notes_cmd(m: Message):
    if not await is_owner(m): return
    await m.answer(sheets.sheets_get_notes())

@dp.message(Command("delnote"))
async def del_note(m: Message):
    if not await is_owner(m): return
    try:
        nid=int(m.text.split()[1])
        for i,n in enumerate(notes):
            if n["id"]==nid: notes.pop(i); await m.answer(f"🗑️ #{nid} o'chirildi."); return
        await m.answer(f"❓ #{nid} topilmadi.")
    except: await m.answer("⚠️ /delnote 1")

@dp.message(Command("todo"))
async def add_todo(m: Message):
    if not await is_owner(m): return
    try:
        text=m.text.split(" ",1)[1].strip()
        todo={"id":len(todos)+1,"text":text,"done":False,"date":datetime.now().strftime("%d.%m")}
        todos.append(todo)
        n_res=await notion.notion_add_todo(text)
        s_res=sheets.sheets_add_todo(text)
        await m.answer(f"✅ #{todo['id']}: {text}\n{n_res}\n{s_res}")
    except: await m.answer("⚠️ /todo Matn")

@dp.message(Command("todos"))
async def show_todos(m: Message):
    if not await is_owner(m): return
    if not todos: await m.answer("📭 Vazifalar yo'q."); return
    active=[t for t in todos if not t["done"]]
    done_l=[t for t in todos if t["done"]]
    lines=["📋 Vazifalar:\n"]
    if active: lines.append("⬜ Bajarilmagan:"); lines+=[f"  {t['id']}. {t['text']}" for t in active]
    if done_l: lines.append("\n✅ Bajarilgan:"); lines+=[f"  {t['id']}. {t['text']}" for t in done_l]
    await m.answer("\n".join(lines))

@dp.message(Command("notiontodos"))
async def notion_todos_cmd(m: Message):
    if not await is_owner(m): return
    await m.answer(await notion.notion_get_todos())

@dp.message(Command("sheetstodos"))
async def sheets_todos_cmd(m: Message):
    if not await is_owner(m): return
    await m.answer(sheets.sheets_get_todos())

@dp.message(Command("done"))
async def mark_done(m: Message):
    if not await is_owner(m): return
    try:
        tid=int(m.text.split()[1])
        for t in todos:
            if t["id"]==tid:
                t["done"]=True
                n_res=await notion.notion_done_todo(t["text"])
                await m.answer(f"✅ {t['text']}\n{n_res}"); return
        await m.answer(f"❓ #{tid} topilmadi.")
    except: await m.answer("⚠️ /done 1")

@dp.message(Command("deltodo"))
async def del_todo(m: Message):
    if not await is_owner(m): return
    try:
        tid=int(m.text.split()[1])
        for i,t in enumerate(todos):
            if t["id"]==tid: todos.pop(i); await m.answer(f"🗑️ #{tid} o'chirildi."); return
        await m.answer(f"❓ #{tid} topilmadi.")
    except: await m.answer("⚠️ /deltodo 1")

@dp.message(Command("expense"))
async def add_expense(m: Message):
    if not await is_owner(m): return
    try:
        parts=m.text.split(" ",2); amount,name=float(parts[1]),parts[2]
        n_res=await notion.notion_add_expense(name,amount,"Xarajat")
        s_res=sheets.sheets_add_expense(name,amount,"Xarajat")
        await m.answer(f"💸 {name} — {amount:,.0f} so'm\n{n_res}\n{s_res}")
    except: await m.answer("⚠️ /expense 50000 Tushlik")

@dp.message(Command("income"))
async def add_income(m: Message):
    if not await is_owner(m): return
    try:
        parts=m.text.split(" ",2); amount,name=float(parts[1]),parts[2]
        n_res=await notion.notion_add_expense(name,amount,"Daromad")
        s_res=sheets.sheets_add_expense(name,amount,"Daromad")
        await m.answer(f"💰 {name} — {amount:,.0f} so'm\n{n_res}\n{s_res}")
    except: await m.answer("⚠️ /income 1000000 Maosh")

@dp.message(Command("expenses"))
async def show_expenses(m: Message):
    if not await is_owner(m): return
    await m.answer(await notion.notion_get_expenses())


@dp.message(Command("reportnow"))
async def report_now(m: Message):
    """Hozir hisobot yuborish"""
    if not await is_owner(m): return
    from extra_helpers import generate_report
    weekly = await generate_report("hafta")
    monthly = await generate_report("oy")
    active_todos = [t for t in todos if not t["done"]]
    report_text = (
        f"📊 HISOBOT\n"
        f"━━━━━━━━━━━━━━━\n"
        f"{weekly}\n\n"
        f"{monthly}\n\n"
        f"✅ Bajarilmagan vazifalar: {len(active_todos)} ta\n"
        f"⏰ Eslatmalar: {len(reminders)} ta\n"
        f"👤 Kontaktlar: {len(contacts)} ta"
    )
    await m.answer(report_text)

@dp.message(Command("setreport"))
async def set_report(m: Message):
    """Hisobot kunini o'zgartirish"""
    if not await is_owner(m): return
    await m.answer(
        "📊 Avtomatik hisobot hozir:\n"
        "🗓️ Har dushanba 09:00\n\n"
        "Hozir ko'rish uchun: /reportnow\n"
        "Haftalik: /report hafta\n"
        "Oylik: /report oy"
    )

@dp.message(Command("report"))
async def report_cmd(m: Message):
    if not await is_owner(m): return
    try:
        period=m.text.split(" ",1)[1].strip()
    except:
        period="hafta"
    await m.answer(await extra.generate_report(period))

@dp.message(Command("caladd"))
async def cal_add(m: Message):
    if not await is_owner(m): return
    try:
        parts=m.text.split(" ",3)
        date_str,time_str,title=parts[1],parts[2],parts[3]
        await m.answer(cal.calendar_add_event(title,date_str,time_str))
    except: await m.answer("⚠️ /caladd 2026-05-01 10:00 Uchrashuv nomi")

@dp.message(Command("calget"))
async def cal_get(m: Message):
    if not await is_owner(m): return
    try:
        days=int(m.text.split()[1])
    except:
        days=7
    await m.answer(cal.calendar_get_events(days))

@dp.message(Command("email"))
async def email_cmd(m: Message):
    if not await is_owner(m): return
    try:
        data=m.text.split(" ",1)[1].strip()
        parts=data.split("|",2)
        await m.answer(gmail.send_email_smtp(parts[0],parts[1],parts[2]))
    except: await m.answer("⚠️ /email email@gmail.com|Mavzu|Matn")

@dp.message(Command("passsave"))
async def pass_save(m: Message):
    if not await is_owner(m): return
    try:
        parts=m.text.split(" ",3)
        await m.answer(extra.password_save(parts[1],parts[2],parts[3]))
    except: await m.answer("⚠️ /passsave Gmail user@gmail.com parol123")

@dp.message(Command("passget"))
async def pass_get(m: Message):
    if not await is_owner(m): return
    try:
        service=m.text.split(" ",1)[1].strip()
        await m.answer(extra.password_get(service))
    except: await m.answer("⚠️ /passget Gmail")

@dp.message(Command("passlist"))
async def pass_list(m: Message):
    if not await is_owner(m): return
    await m.answer(extra.password_list())

@dp.message(Command("passdel"))
async def pass_del(m: Message):
    if not await is_owner(m): return
    try:
        service=m.text.split(" ",1)[1].strip()
        await m.answer(extra.password_delete(service))
    except: await m.answer("⚠️ /passdel Gmail")

@dp.message(Command("bdadd"))
async def bd_add(m: Message):
    if not await is_owner(m): return
    try:
        parts=m.text.split(" ",2)
        await m.answer(extra.birthday_add(parts[1],parts[2]))
    except: await m.answer("⚠️ /bdadd Ism 15.03.1995")

@dp.message(Command("bdlist"))
async def bd_list(m: Message):
    if not await is_owner(m): return
    await m.answer(extra.birthday_list())

@dp.message(Command("search"))
async def search_cmd(m: Message):
    if not await is_owner(m): return
    try:
        query=m.text.split(" ",1)[1].strip()
        await m.answer(await extra.web_search(query))
    except: await m.answer("⚠️ /search qidiruv matni")

@dp.message(Command("news"))
async def news_cmd(m: Message):
    if not await is_owner(m): return
    try:
        topic=m.text.split(" ",1)[1].strip()
    except:
        topic="uzbekistan"
    await m.answer(await extra.get_news(topic))

@dp.message(Command("spotify"))
async def spotify_cmd(m: Message):
    if not await is_owner(m): return
    try:
        query=m.text.split(" ",1)[1].strip()
        await m.answer(await extra.spotify_search(query))
    except: await m.answer("⚠️ /spotify qo'shiq nomi")

@dp.message(Command("remind"))
async def remind(m: Message):
    if not await is_owner(m): return
    try:
        parts=m.text.split(" ",2); time_str,text=parts[1],parts[2]
        hour,minute=map(int,time_str.split(":"))
        rid=len(reminders)+1
        reminders.append({"id":rid,"time":time_str,"text":text,"repeat":False})
        async def once():
            delta=(datetime.now().replace(hour=hour,minute=minute,second=0)-datetime.now()).total_seconds()
            if delta<0: delta+=86400
            await asyncio.sleep(delta)
            await bot.send_message(MY_ID,f"⏰ {text}")
            for r in reminders:
                if r["id"]==rid: reminders.remove(r); break
        asyncio.create_task(once())
        await m.answer(f"⏰ #{rid}: {time_str} — {text}")
    except: await m.answer("⚠️ /remind 10:30 Matn")

@dp.message(Command("repeatremind"))
async def repeat_remind(m: Message):
    if not await is_owner(m): return
    try:
        parts=m.text.split(" ",2); time_str,text=parts[1],parts[2]
        hour,minute=map(int,time_str.split(":"))
        rid=len(reminders)+1
        reminders.append({"id":rid,"time":time_str,"text":text,"repeat":True})
        async def daily():
            while any(r["id"]==rid for r in reminders):
                delta=(datetime.now().replace(hour=hour,minute=minute,second=0)-datetime.now()).total_seconds()
                if delta<0: delta+=86400
                await asyncio.sleep(delta)
                if any(r["id"]==rid for r in reminders):
                    await bot.send_message(MY_ID,f"🔔 {text}")
                await asyncio.sleep(61)
        asyncio.create_task(daily())
        await m.answer(f"🔔 Kunlik #{rid}: {time_str} — {text}")
    except: await m.answer("⚠️ /repeatremind 09:00 Matn")

@dp.message(Command("reminders"))
async def show_reminders(m: Message):
    if not await is_owner(m): return
    if not reminders: await m.answer("📭 Eslatmalar yo'q."); return
    lines=[f"⏰ ({len(reminders)} ta):\n"]
    for r in reminders:
        lines.append(f"{r['id']}. {'🔔' if r['repeat'] else '⏰'} {r['time']} — {r['text']}")
    await m.answer("\n".join(lines))

@dp.message(Command("delremind"))
async def del_remind(m: Message):
    if not await is_owner(m): return
    try:
        rid=int(m.text.split()[1])
        for i,r in enumerate(reminders):
            if r["id"]==rid: reminders.pop(i); await m.answer(f"🗑️ #{rid} o'chirildi."); return
        await m.answer(f"❓ #{rid} topilmadi.")
    except: await m.answer("⚠️ /delremind 1")

@dp.message(Command("weather"))
async def weather_cmd(m: Message):
    if not await is_owner(m): return
    try: await m.answer(await get_weather(m.text.split(" ",1)[1].strip()))
    except: await m.answer("⚠️ /weather Toshkent")

@dp.message(Command("currency"))
async def currency_cmd(m: Message):
    if not await is_owner(m): return
    try: await m.answer(await get_currency(m.text.split(" ",1)[1].strip()))
    except: await m.answer("⚠️ /currency USD")

@dp.message(Command("stats"))
async def show_stats(m: Message):
    if not await is_owner(m): return
    await m.answer(
        f"📊 Statistika ({stats['today']}):\n"
        f"💬 Xabarlar: {stats['messages_sent']}\n"
        f"🎙️ Ovozli: {stats['voice_sent']}\n"
        f"📨 Matnli: {stats['text_sent']}\n"
        f"👤 Kontaktlar: {len(contacts)}\n"
        f"📝 Qaydlar: {len(notes)}\n"
        f"✅ Vazifalar: {len(todos)}\n"
        f"⏰ Eslatmalar: {len(reminders)}"
    )

@dp.message(Command("clear"))
async def clear(m: Message):
    if not await is_owner(m): return
    conversation_histories[m.from_user.id]=[]
    await m.answer("🧹 Tozalandi.")


@dp.message(Command("groupadd"))
async def group_add(m: Message):
    if not await is_owner(m): return
    try:
        parts = m.text.split(" ", 2)
        group_id = parts[1].strip()
        group_name = parts[2].strip() if len(parts) > 2 else group_id
        import json
        settings_file = "group_settings.json"
        if os.path.exists(settings_file):
            with open(settings_file) as f:
                settings = json.load(f)
        else:
            settings = {"active_groups": {}, "group_histories": {}}
        settings["active_groups"][group_id] = {
            "name": group_name,
            "mode": "smart",
            "added": str(datetime.now())[:10]
        }
        with open(settings_file, "w") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        await m.answer(
            f"✅ Guruh qo'shildi: {group_name}\n"
            f"ID: {group_id}\n"
            f"Mode: Smart (savollarga javob beradi)\n\n"
            f"Mode o'zgartirish:\n"
            f"/groupmode {group_id} all — hammaga javob\n"
            f"/groupmode {group_id} smart — faqat savollarga"
        )
    except:
        await m.answer(
            "⚠️ Format: /groupadd -1001234567890 Guruh nomi\n\n"
            "Guruh ID ni qanday topish:\n"
            "1. Guruhga @getidsbot ni qo'shing\n"
            "2. Yoki grup ichida /id yuboring"
        )

@dp.message(Command("groupdel"))
async def group_del(m: Message):
    if not await is_owner(m): return
    try:
        group_id = m.text.split(" ", 1)[1].strip()
        settings_file = "group_settings.json"
        if os.path.exists(settings_file):
            with open(settings_file) as f:
                settings = json.load(f)
            if group_id in settings.get("active_groups", {}):
                name = settings["active_groups"][group_id]["name"]
                del settings["active_groups"][group_id]
                with open(settings_file, "w") as f:
                    json.dump(settings, f, ensure_ascii=False, indent=2)
                await m.answer(f"🗑️ {name} guruhi o'chirildi.")
            else:
                await m.answer("❓ Guruh topilmadi.")
    except:
        await m.answer("⚠️ /groupdel -1001234567890")

@dp.message(Command("grouplist"))
async def group_list(m: Message):
    if not await is_owner(m): return
    settings_file = "group_settings.json"
    if not os.path.exists(settings_file):
        await m.answer("📭 Hech qanday guruh yo'q.\n/groupadd bilan qo'shing.")
        return
    with open(settings_file) as f:
        settings = json.load(f)
    groups = settings.get("active_groups", {})
    if not groups:
        await m.answer("📭 Faol guruhlar yo'q.")
        return
    lines = [f"👥 Faol guruhlar ({len(groups)} ta):\n"]
    for gid, info in groups.items():
        lines.append(f"• {info['name']}\n  ID: {gid} | Mode: {info.get('mode','smart')}")
    await m.answer("\n".join(lines))

@dp.message(Command("groupmode"))
async def group_mode(m: Message):
    if not await is_owner(m): return
    try:
        parts = m.text.split(" ", 2)
        group_id, mode = parts[1].strip(), parts[2].strip()
        settings_file = "group_settings.json"
        with open(settings_file) as f:
            settings = json.load(f)
        if group_id in settings["active_groups"]:
            settings["active_groups"][group_id]["mode"] = mode
            with open(settings_file, "w") as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
            mode_text = "Hammaga javob beradi" if mode=="all" else "Faqat savollarga javob beradi"
            await m.answer(f"✅ Mode o'zgartirildi: {mode_text}")
        else:
            await m.answer("❓ Guruh topilmadi.")
    except:
        await m.answer("⚠️ /groupmode -1001234567890 smart")

@dp.message(Command("makevn"))
async def make_videonote_cmd(m: Message):
    """AI dumaloq video tayyorlab yuborish"""
    if not await is_owner(m): return
    try:
        parts = m.text.split(" ", 2)
        contact_name = parts[1].strip()
        text = parts[2].strip()
        contact = find_contact(contact_name)
        if not contact:
            await m.answer(f"❓ '{contact_name}' kontaktlarda topilmadi.")
            return
        await m.answer(f"🎬 Dumaloq video tayyorlanmoqda...\n📝 Matn: {text[:50]}")
        avatar = "avatar.jpg" if os.path.exists("avatar.jpg") else None
        video_bytes = await make_avatar_videonote(text, client, avatar)
        if video_bytes:
            ok = await send_videonote_to_phone(contact["phone"], video_bytes, contact["name"])
            await m.answer(f"✅ {contact['name']} ga dumaloq video yuborildi!" if ok else f"❌ {contact['name']} — topilmadi")
        else:
            await m.answer("❌ ffmpeg o'rnatilmagan. CMD da: winget install ffmpeg")
    except:
        await m.answer("⚠️ /makevn Ism Yuborilajak matn")


@dp.message(F.text == "🔙 Asosiy menyu")
async def back_to_main(m: Message):
    if not await is_owner(m): return
    user_state.pop(m.from_user.id, None)
    await m.answer("🏠 Asosiy menyu:", reply_markup=main_menu())


# ══════════════════════════════════════════════════════════════════════════════
# AKKAUNT BOSHQARUVI
# ══════════════════════════════════════════════════════════════════════════════


# ── Guruhga avtomatik javob sozlamalari ───────────────────────────────────────
@dp.message(Command("replygroup"))
async def reply_group_add(m: Message):
    if not await is_owner(m): return
    try:
        parts = m.text.split(" ", 2)
        group_id = parts[1].strip()
        action = parts[2].strip().lower() if len(parts) > 2 else "on"
        if action in ["on", "yoq", "1"]:
            AUTO_REPLY_GROUPS[group_id] = True
            await m.answer(f"✅ {group_id} guruhiga avtomatik javob yoqildi!")
        else:
            AUTO_REPLY_GROUPS[group_id] = False
            await m.answer(f"❌ {group_id} guruhiga avtomatik javob o'chirildi!")
    except:
        await m.answer(
            "⚠️ Format:\n"
            "/replygroup -1001234567890 on — yoqish\n"
            "/replygroup -1001234567890 off — o'chirish\n\n"
            "Guruh ID ni @getidsbot dan oling"
        )

@dp.message(Command("replygroups"))
async def reply_groups_list(m: Message):
    if not await is_owner(m): return
    if not AUTO_REPLY_GROUPS:
        await m.answer(
            "📭 Hech qanday guruh sozlanmagan.\n\n"
            "Guruh qo'shish:\n"
            "/replygroup -1001234567890 on"
        )
        return
    lines = ["📋 Guruh javob sozlamalari:\n"]
    for gid, status in AUTO_REPLY_GROUPS.items():
        icon = "✅" if status else "❌"
        lines.append(f"{icon} {gid}")
    await m.answer("\n".join(lines))

@dp.message(Command("accounts"))
async def show_accounts(m: Message):
    if not await is_owner(m): return
    await m.answer(ma.get_account_list(), reply_markup=main_menu())

@dp.message(Command("addaccount"))
async def add_account_cmd(m: Message):
    if not await is_owner(m): return
    try:
        parts = m.text.split(" ", 2)
        phone = parts[1].strip()
        name = parts[2].strip() if len(parts) > 2 else phone
        result = await ma.add_account(phone, name)
        await m.answer(result)
    except:
        await m.answer(
            "⚠️ Format: /addaccount +998901234567 Ism\n\n"
            "Keyin kod kelganda:\n"
            "/confirmcode +998901234567 12345"
        )

@dp.message(Command("confirmcode"))
async def confirm_code_cmd(m: Message):
    if not await is_owner(m): return
    try:
        parts = m.text.split(" ", 3)
        phone = parts[1].strip()
        code = parts[2].strip()
        name = parts[3].strip() if len(parts) > 3 else ""
        result = await ma.confirm_code(phone, code, name)
        await m.answer(result)
    except:
        await m.answer("⚠️ Format: /confirmcode +998901234567 12345")

@dp.message(Command("delacc"))
async def del_account_cmd(m: Message):
    if not await is_owner(m): return
    try:
        idx = int(m.text.split()[1]) - 1
        accounts = ma.load_accounts()
        if 0 <= idx < len(accounts):
            removed = accounts.pop(idx)
            ma.save_accounts(accounts)
            await m.answer(f"🗑️ {removed['name']} o'chirildi.")
        else:
            await m.answer("❓ Topilmadi.")
    except:
        await m.answer("⚠️ /delacc 1")

# ── Callback: akkaunt tanlanganda ────────────────────────────────────────────
from aiogram.types import CallbackQuery

@dp.callback_query(AiogramF.data.startswith("acc_"))
async def account_selected(callback: CallbackQuery):
    if callback.from_user.id != MY_ID: return
    parts = callback.data.split("_")
    action = parts[1]
    acc_idx = int(parts[2])
    
    pending = pending_sends.get(callback.from_user.id)
    if not pending:
        await callback.answer("⚠️ Xabar topilmadi.")
        return
    
    contact = pending["contact"]
    msg_type = pending["type"]
    
    await callback.message.edit_text(f"📤 Yuborilmoqda... ({pending['account_name'] if acc_idx == 0 else ''})")
    
    if acc_idx == 0:
        # Asosiy akkaunt
        if msg_type == "voice":
            ok = await send_voice_to_phone(contact["phone"], pending["data"], contact["name"])
        elif msg_type == "text":
            ok = await send_text_to_phone(contact["phone"], pending["data"], contact["name"])
        elif msg_type == "video":
            ok = await send_video_to_phone(contact["phone"], pending["data"], contact["name"])
        result = f"✅ Asosiy akkauntdan {contact['name']} ga yuborildi!" if ok else "❌ Xato"
    else:
        # Tanlangan akkaunt
        if msg_type == "voice":
            result = await ma.send_voice_from_account(acc_idx, contact["phone"], pending["data"], contact["name"])
        elif msg_type == "text":
            result = await ma.send_text_from_account(acc_idx, contact["phone"], pending["data"], contact["name"])
        elif msg_type == "video":
            result = await ma.send_video_from_account(acc_idx, contact["phone"], pending["data"], contact["name"], pending.get("caption",""))
        else:
            result = "❌ Noma'lum tur"
    
    pending_sends.pop(callback.from_user.id, None)
    await callback.message.edit_text(result)
    await callback.answer()

# ── Menyu bo'limlari ──────────────────────────────────────────────────────────
@dp.message(F.text == "📝 Qaydlar")
async def menu_notes(m: Message):
    if not await is_owner(m): return
    await m.answer("📝 Qaydlar bo'limi:", reply_markup=notes_menu())

@dp.message(F.text == "✅ Vazifalar")
async def menu_todos(m: Message):
    if not await is_owner(m): return
    await m.answer("✅ Vazifalar bo'limi:", reply_markup=todos_menu())

@dp.message(F.text == "👥 Kontaktlar")
async def menu_contacts(m: Message):
    if not await is_owner(m): return
    await m.answer("👥 Kontaktlar bo'limi:", reply_markup=contacts_menu())

@dp.message(F.text == "💰 Moliya")
async def menu_finance(m: Message):
    if not await is_owner(m): return
    await m.answer("💰 Moliya bo'limi:", reply_markup=finance_menu())

@dp.message(F.text == "⏰ Eslatmalar")
async def menu_reminders(m: Message):
    if not await is_owner(m): return
    await m.answer("⏰ Eslatmalar bo'limi:", reply_markup=reminders_menu())

@dp.message(F.text == "📅 Kalendar")
async def menu_calendar(m: Message):
    if not await is_owner(m): return
    await m.answer("📅 Kalendar bo'limi:", reply_markup=calendar_menu())

@dp.message(F.text == "👥 Guruhlar")
async def menu_groups(m: Message):
    if not await is_owner(m): return
    await m.answer("👥 Guruhlar bo'limi:", reply_markup=groups_menu())

@dp.message(F.text == "🔐 Parollar")
async def menu_passwords(m: Message):
    if not await is_owner(m): return
    await m.answer("🔐 Parollar bo'limi:", reply_markup=passwords_menu())

@dp.message(F.text == "🎂 Tug'ilgan kun")
async def menu_birthdays(m: Message):
    if not await is_owner(m): return
    await m.answer("🎂 Tug'ilgan kunlar:", reply_markup=birthdays_menu())

@dp.message(F.text == "📨 Xabar yuborish")
async def menu_send(m: Message):
    if not await is_owner(m): return
    await m.answer("📨 Xabar yuborish:", reply_markup=send_menu())

@dp.message(F.text == "⚙️ Sozlamalar")
async def menu_settings(m: Message):
    if not await is_owner(m): return
    await m.answer("⚙️ Sozlamalar:", reply_markup=settings_menu())

@dp.message(F.text == "❓ Yordam")
async def menu_help(m: Message):
    if not await is_owner(m): return
    await m.answer(
        "📚 ASOSIY BUYRUQLAR:\n\n"
        "📝 /note Matn — qayd\n"
        "✅ /todo Matn — vazifa\n"
        "💸 /expense 50000 Tushlik\n"
        "💰 /income 1000000 Maosh\n"
        "⏰ /remind 10:30 Matn\n"
        "🔔 /repeatremind 09:00 Matn\n"
        "📅 /caladd 2026-05-01 10:00 Uchrashuv\n"
        "🔐 /passsave Gmail user parol\n"
        "🎂 /bdadd Ism 15.03.1995\n"
        "🔍 /search qidiruv\n"
        "🎵 /spotify qo'shiq\n"
        "📰 /news mavzu\n"
        "🌤️ /weather Toshkent\n"
        "💱 /currency USD\n"
        "👥 /groupadd -100123 Guruh\n"
        "🎬 /makevn Ism Matn\n"
        "📊 /reportnow",
        reply_markup=main_menu()
    )

# ── Tugma bosilganda amallar ──────────────────────────────────────────────────

# Qaydlar
@dp.message(F.text == "➕ Qayd qo'shish")
async def btn_add_note(m: Message):
    if not await is_owner(m): return
    user_state[m.from_user.id] = "waiting_note"
    await m.answer("📝 Qayd matnini yozing:", reply_markup=ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 Asosiy menyu")]], resize_keyboard=True))

@dp.message(F.text == "📋 Barcha qaydlar")
async def btn_notes(m: Message):
    if not await is_owner(m): return
    if not notes: await m.answer("📭 Qaydlar yo'q.", reply_markup=notes_menu()); return
    lines = [f"📝 ({len(notes)} ta):\n"]
    for n in notes: lines.append(f"{n['id']}. [{n['date']}] {n['text']}")
    await m.answer("\n".join(lines), reply_markup=notes_menu())

@dp.message(F.text == "📒 Notion qaydlar")
async def btn_notion_notes(m: Message):
    if not await is_owner(m): return
    await m.answer(await notion.notion_get_notes(), reply_markup=notes_menu())

@dp.message(F.text == "📊 Sheets qaydlar")
async def btn_sheets_notes(m: Message):
    if not await is_owner(m): return
    await m.answer(sheets.sheets_get_notes(), reply_markup=notes_menu())

# Vazifalar
@dp.message(F.text == "➕ Vazifa qo'shish")
async def btn_add_todo(m: Message):
    if not await is_owner(m): return
    user_state[m.from_user.id] = "waiting_todo"
    await m.answer("✅ Vazifa matnini yozing:", reply_markup=ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 Asosiy menyu")]], resize_keyboard=True))

@dp.message(F.text == "📋 Barcha vazifalar")
async def btn_todos(m: Message):
    if not await is_owner(m): return
    if not todos: await m.answer("📭 Vazifalar yo'q.", reply_markup=todos_menu()); return
    active = [t for t in todos if not t["done"]]
    done_l = [t for t in todos if t["done"]]
    lines = ["📋 Vazifalar:\n"]
    if active: lines.append("⬜ Bajarilmagan:"); lines += [f"  {t['id']}. {t['text']}" for t in active]
    if done_l: lines.append("\n✅ Bajarilgan:"); lines += [f"  {t['id']}. {t['text']}" for t in done_l]
    await m.answer("\n".join(lines), reply_markup=todos_menu())

@dp.message(F.text == "✅ Bajarildi belgilash")
async def btn_done_todo(m: Message):
    if not await is_owner(m): return
    user_state[m.from_user.id] = "waiting_done"
    await m.answer("Vazifa raqamini yozing (masalan: 1):", reply_markup=ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 Asosiy menyu")]], resize_keyboard=True))

@dp.message(F.text == "📒 Notion vazifalar")
async def btn_notion_todos(m: Message):
    if not await is_owner(m): return
    await m.answer(await notion.notion_get_todos(), reply_markup=todos_menu())

@dp.message(F.text == "📊 Sheets vazifalar")
async def btn_sheets_todos(m: Message):
    if not await is_owner(m): return
    await m.answer(sheets.sheets_get_todos(), reply_markup=todos_menu())

# Kontaktlar
@dp.message(F.text == "📋 Kontaktlar ro'yxati")
async def btn_contacts(m: Message):
    if not await is_owner(m): return
    if not contacts: await m.answer("📭 Kontaktlar yo'q.", reply_markup=contacts_menu()); return
    lines = [f"📋 ({len(contacts)} ta):\n"]
    for i, v in enumerate(list(contacts.values())[:30], 1):
        lines.append(f"{i}. {v['name']}: {v['phone']}")
    await m.answer("\n".join(lines), reply_markup=contacts_menu())

@dp.message(F.text == "➕ Kontakt qo'shish")
async def btn_add_contact(m: Message):
    if not await is_owner(m): return
    user_state[m.from_user.id] = "waiting_contact"
    await m.answer("👤 Format: Ism +998901234567", reply_markup=ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 Asosiy menyu")]], resize_keyboard=True))

@dp.message(F.text == "🗑️ Kontakt o'chirish")
async def btn_del_contact(m: Message):
    if not await is_owner(m): return
    user_state[m.from_user.id] = "waiting_delcontact"
    await m.answer("O'chirmoqchi bo'lgan kontakt ismini yozing:", reply_markup=ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 Asosiy menyu")]], resize_keyboard=True))

# Moliya
@dp.message(F.text == "💸 Xarajat qo'shish")
async def btn_add_expense(m: Message):
    if not await is_owner(m): return
    user_state[m.from_user.id] = "waiting_expense"
    await m.answer("💸 Format: 50000 Tushlik", reply_markup=ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 Asosiy menyu")]], resize_keyboard=True))

@dp.message(F.text == "💰 Daromad qo'shish")
async def btn_add_income(m: Message):
    if not await is_owner(m): return
    user_state[m.from_user.id] = "waiting_income"
    await m.answer("💰 Format: 1000000 Maosh", reply_markup=ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 Asosiy menyu")]], resize_keyboard=True))

@dp.message(F.text == "📊 Xarajatlar ro'yxati")
async def btn_expenses(m: Message):
    if not await is_owner(m): return
    await m.answer(await notion.notion_get_expenses(), reply_markup=finance_menu())

@dp.message(F.text == "📈 Haftalik hisobot")
async def btn_weekly(m: Message):
    if not await is_owner(m): return
    from extra_helpers import generate_report
    await m.answer(await generate_report("hafta"), reply_markup=finance_menu())

@dp.message(F.text == "📉 Oylik hisobot")
async def btn_monthly(m: Message):
    if not await is_owner(m): return
    from extra_helpers import generate_report
    await m.answer(await generate_report("oy"), reply_markup=finance_menu())

# Eslatmalar
@dp.message(F.text == "➕ Eslatma qo'shish")
async def btn_add_remind(m: Message):
    if not await is_owner(m): return
    user_state[m.from_user.id] = "waiting_remind"
    await m.answer("⏰ Format: 10:30 Uchrashuv matni", reply_markup=ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 Asosiy menyu")]], resize_keyboard=True))

@dp.message(F.text == "🔔 Kunlik eslatma")
async def btn_add_repeat(m: Message):
    if not await is_owner(m): return
    user_state[m.from_user.id] = "waiting_repeatremind"
    await m.answer("🔔 Format: 09:00 Har kunlik eslatma matni", reply_markup=ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 Asosiy menyu")]], resize_keyboard=True))

@dp.message(F.text == "📋 Eslatmalar ro'yxati")
async def btn_reminders(m: Message):
    if not await is_owner(m): return
    if not reminders: await m.answer("📭 Eslatmalar yo'q.", reply_markup=reminders_menu()); return
    lines = [f"⏰ ({len(reminders)} ta):\n"]
    for r in reminders:
        lines.append(f"{r['id']}. {'🔔' if r['repeat'] else '⏰'} {r['time']} — {r['text']}")
    await m.answer("\n".join(lines), reply_markup=reminders_menu())

@dp.message(F.text == "🗑️ Eslatma o'chirish")
async def btn_del_remind(m: Message):
    if not await is_owner(m): return
    user_state[m.from_user.id] = "waiting_delremind"
    await m.answer("O'chirmoqchi bo'lgan eslatma raqamini yozing:", reply_markup=ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 Asosiy menyu")]], resize_keyboard=True))

# Kalendar
@dp.message(F.text == "➕ Voqea qo'shish")
async def btn_add_event(m: Message):
    if not await is_owner(m): return
    user_state[m.from_user.id] = "waiting_caladd"
    await m.answer("📅 Format: 2026-05-01 10:00 Uchrashuv nomi", reply_markup=ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 Asosiy menyu")]], resize_keyboard=True))

@dp.message(F.text == "📅 7 kunlik voqealar")
async def btn_cal7(m: Message):
    if not await is_owner(m): return
    await m.answer(cal.calendar_get_events(7), reply_markup=calendar_menu())

@dp.message(F.text == "📅 30 kunlik voqealar")
async def btn_cal30(m: Message):
    if not await is_owner(m): return
    await m.answer(cal.calendar_get_events(30), reply_markup=calendar_menu())

# Guruhlar
@dp.message(F.text == "➕ Guruh qo'shish")
async def btn_add_group(m: Message):
    if not await is_owner(m): return
    user_state[m.from_user.id] = "waiting_group"
    await m.answer("👥 Format: -1001234567890 Guruh nomi\n\nGuruh ID: @getidsbot", 
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🔙 Asosiy menyu")]], resize_keyboard=True))

@dp.message(F.text == "📋 Guruhlar ro'yxati")
async def btn_groups(m: Message):
    if not await is_owner(m): return
    settings_file = "group_settings.json"
    if not os.path.exists(settings_file):
        await m.answer("📭 Guruhlar yo'q.", reply_markup=groups_menu()); return
    with open(settings_file) as f: gs = json.load(f)
    groups = gs.get("active_groups", {})
    if not groups: await m.answer("📭 Guruhlar yo'q.", reply_markup=groups_menu()); return
    lines = [f"👥 ({len(groups)} ta):\n"]
    for gid, info in groups.items():
        lines.append(f"• {info['name']} ({info.get('mode','smart')})")
    await m.answer("\n".join(lines), reply_markup=groups_menu())

@dp.message(F.text == "🗑️ Guruh o'chirish")
async def btn_del_group(m: Message):
    if not await is_owner(m): return
    user_state[m.from_user.id] = "waiting_delgroup"
    await m.answer("O'chirmoqchi guruh ID sini yozing:", reply_markup=ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 Asosiy menyu")]], resize_keyboard=True))

# Parollar
@dp.message(F.text == "🔐 Parol saqlash")
async def btn_save_pass(m: Message):
    if not await is_owner(m): return
    user_state[m.from_user.id] = "waiting_passsave"
    await m.answer("🔐 Format: Gmail user@gmail.com parol123", reply_markup=ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 Asosiy menyu")]], resize_keyboard=True))

@dp.message(F.text == "🔍 Parol olish")
async def btn_get_pass(m: Message):
    if not await is_owner(m): return
    user_state[m.from_user.id] = "waiting_passget"
    await m.answer("Qaysi servis parolini olmoqchisiz? (masalan: Gmail)", reply_markup=ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 Asosiy menyu")]], resize_keyboard=True))

@dp.message(F.text == "📋 Parollar ro'yxati")
async def btn_pass_list(m: Message):
    if not await is_owner(m): return
    await m.answer(extra.password_list(), reply_markup=passwords_menu())

@dp.message(F.text == "🗑️ Parol o'chirish")
async def btn_del_pass(m: Message):
    if not await is_owner(m): return
    user_state[m.from_user.id] = "waiting_passdel"
    await m.answer("O'chirmoqchi servis nomini yozing:", reply_markup=ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 Asosiy menyu")]], resize_keyboard=True))

# Tug'ilgan kun
@dp.message(F.text == "➕ Tug'ilgan kun qo'shish")
async def btn_add_birthday(m: Message):
    if not await is_owner(m): return
    user_state[m.from_user.id] = "waiting_birthday"
    await m.answer("🎂 Format: Ism 15.03.1995", reply_markup=ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 Asosiy menyu")]], resize_keyboard=True))

@dp.message(F.text == "📋 Tug'ilgan kunlar ro'yxati")
async def btn_birthdays(m: Message):
    if not await is_owner(m): return
    await m.answer(extra.birthday_list(), reply_markup=birthdays_menu())

# Xabar yuborish
@dp.message(F.text == "🎙️ Ovozli xabar yuborish")
async def btn_send_voice(m: Message):
    if not await is_owner(m): return
    user_state[m.from_user.id] = "waiting_sendvoice"
    await m.answer("🎙️ Format: Ism|Yuborilajak matn\nMasalan: Shohrux|Ertaga 10da kelgin", 
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🔙 Asosiy menyu")]], resize_keyboard=True))

@dp.message(F.text == "📝 Matnli xabar yuborish")
async def btn_send_text(m: Message):
    if not await is_owner(m): return
    user_state[m.from_user.id] = "waiting_sendtext"
    await m.answer("📝 Format: Ism|Yuborilajak matn", 
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🔙 Asosiy menyu")]], resize_keyboard=True))

@dp.message(F.text == "🤖 AI dumaloq video")
async def btn_make_vn(m: Message):
    if not await is_owner(m): return
    user_state[m.from_user.id] = "waiting_makevn"
    await m.answer("🤖 Format: Ism|Yuborilajak matn\nMasalan: Shohrux|Ertaga uchrashuv bor", 
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🔙 Asosiy menyu")]], resize_keyboard=True))

@dp.message(F.text == "🎬 Video xabar yuborish")
async def btn_send_video(m: Message):
    if not await is_owner(m): return
    await m.answer("🎬 Avval video faylni yuboring, keyin kimga yuborishni ayting.", reply_markup=send_menu())

@dp.message(F.text == "⭕ Dumaloq video yuborish")
async def btn_send_videonote(m: Message):
    if not await is_owner(m): return
    await m.answer("⭕ Avval dumaloq video yuboring, keyin kimga yuborishni ayting.", reply_markup=send_menu())

# Qidirish
@dp.message(F.text == "🔍 Qidirish")
async def btn_search(m: Message):
    if not await is_owner(m): return
    user_state[m.from_user.id] = "waiting_search"
    await m.answer("🔍 Qidirmoqchi bo'lgan narsani yozing:", reply_markup=ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 Asosiy menyu")]], resize_keyboard=True))

# Ob-havo va Valyuta
@dp.message(F.text == "🌤️ Ob-havo")
async def btn_weather(m: Message):
    if not await is_owner(m): return
    user_state[m.from_user.id] = "waiting_weather"
    await m.answer("🌤️ Shahar nomini yozing:", reply_markup=ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Toshkent"), KeyboardButton(text="Samarqand")],
            [KeyboardButton(text="Buxoro"), KeyboardButton(text="Namangan")],
            [KeyboardButton(text="🔙 Asosiy menyu")]
        ], resize_keyboard=True))

@dp.message(F.text == "💱 Valyuta")
async def btn_currency(m: Message):
    if not await is_owner(m): return
    user_state[m.from_user.id] = "waiting_currency"
    await m.answer("💱 Valyuta kodini tanlang:", reply_markup=ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="USD"), KeyboardButton(text="EUR"), KeyboardButton(text="RUB")],
            [KeyboardButton(text="GBP"), KeyboardButton(text="CNY"), KeyboardButton(text="JPY")],
            [KeyboardButton(text="🔙 Asosiy menyu")]
        ], resize_keyboard=True))

# Spotify va Yangiliklar
@dp.message(F.text == "🎵 Spotify")
async def btn_spotify(m: Message):
    if not await is_owner(m): return
    user_state[m.from_user.id] = "waiting_spotify"
    await m.answer("🎵 Qo'shiq nomini yozing:", reply_markup=ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 Asosiy menyu")]], resize_keyboard=True))

@dp.message(F.text == "📰 Yangiliklar")
async def btn_news(m: Message):
    if not await is_owner(m): return
    user_state[m.from_user.id] = "waiting_news"
    await m.answer("📰 Mavzuni tanlang yoki yozing:", reply_markup=ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="uzbekistan"), KeyboardButton(text="technology")],
            [KeyboardButton(text="sports"), KeyboardButton(text="business")],
            [KeyboardButton(text="🔙 Asosiy menyu")]
        ], resize_keyboard=True))

# Hisobot
@dp.message(F.text == "📊 Hisobot")
async def btn_report(m: Message):
    if not await is_owner(m): return
    from extra_helpers import generate_report
    weekly = await generate_report("hafta")
    await m.answer(weekly, reply_markup=finance_menu())

# Sozlamalar
@dp.message(F.text == "📊 Statistika")
async def btn_stats(m: Message):
    if not await is_owner(m): return
    await m.answer(
        f"📊 Statistika ({stats['today']}):\n"
        f"💬 Xabarlar: {stats['messages_sent']}\n"
        f"🎙️ Ovozli: {stats['voice_sent']}\n"
        f"📨 Matnli: {stats['text_sent']}\n"
        f"👤 Kontaktlar: {len(contacts)}\n"
        f"📝 Qaydlar: {len(notes)}\n"
        f"✅ Vazifalar: {len(todos)}\n"
        f"⏰ Eslatmalar: {len(reminders)}",
        reply_markup=settings_menu()
    )

@dp.message(F.text == "🧹 Suhbatni tozalash")
async def btn_clear(m: Message):
    if not await is_owner(m): return
    conversation_histories[m.from_user.id] = []
    await m.answer("🧹 Suhbat tarixi tozalandi.", reply_markup=settings_menu())

@dp.message(F.text == "📊 Hozir hisobot")
async def btn_report_now(m: Message):
    if not await is_owner(m): return
    from extra_helpers import generate_report
    weekly = await generate_report("hafta")
    monthly = await generate_report("oy")
    await m.answer(f"{weekly}\n\n{monthly}", reply_markup=settings_menu())


# ── Maxsus tugmalar ───────────────────────────────────────────────────────────
@dp.message(F.text == "➕ Tugma qo'shish")
async def btn_add_custom(m: Message):
    if not await is_owner(m): return
    user_state[m.from_user.id] = "waiting_custom_btn"
    await m.answer(
        "➕ Yangi tugma qo'shish\n\n"
        "Format: emoji Nom|buyruq\n\n"
        "Masallar:\n"
        "🏋️ Sport|Bugun sport qildim, qayd et\n"
        "💊 Dori|Eslatma: dori vaqti\n"
        "🚗 Mashina|Mashinaga benzin solish kerakmi\n\n"
        "Tugma bosilganda o'ng tomondagi matn Jarvisga yuboriladi.",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="🔙 Asosiy menyu")]],
            resize_keyboard=True
        )
    )

@dp.message(F.text == "🗑️ Tugma o'chirish")
async def btn_del_custom(m: Message):
    if not await is_owner(m): return
    if not CUSTOM_BUTTONS:
        await m.answer("📭 Maxsus tugmalar yo'q.", reply_markup=main_menu())
        return
    lines = ["🗑️ Qaysi tugmani o'chirmoqchisiz? Raqam yozing:\n"]
    for i, btn in enumerate(CUSTOM_BUTTONS, 1):
        lines.append(f"{i}. {btn['label']}")
    user_state[m.from_user.id] = "waiting_del_custom_btn"
    await m.answer("\n".join(lines), reply_markup=ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 Asosiy menyu")]], resize_keyboard=True))



@dp.message(F.text == "👥 Guruh javob sozlash")
async def btn_group_reply(m: Message):
    if not await is_owner(m): return
    lines = [
        "👥 Guruhga avtomatik javob sozlash:\n",
        "Yoqish: /replygroup -1001234567890 on",
        "O'chirish: /replygroup -1001234567890 off",
        "Ro'yxat: /replygroups\n",
        "Guruh ID ni @getidsbot dan oling"
    ]
    if AUTO_REPLY_GROUPS:
        lines.append("\nHozirgi sozlamalar:")
        for gid, status in AUTO_REPLY_GROUPS.items():
            lines.append(f"{'✅' if status else '❌'} {gid}")
    await m.answer("\n".join(lines), reply_markup=settings_menu())

@dp.message(F.text.startswith("🤖 Avtomatik javob:"))
async def toggle_auto_reply(m: Message):
    if not await is_owner(m): return
    AUTO_REPLY["enabled"] = not AUTO_REPLY["enabled"]
    status = "✅ Yoqildi" if AUTO_REPLY["enabled"] else "❌ O'chirildi"
    await m.answer(f"🤖 Avtomatik javob: {status}", reply_markup=settings_menu())


@dp.message(F.text == "👤 Akkauntlar")
async def menu_accounts(m: Message):
    if not await is_owner(m): return
    accounts = ma.load_accounts()
    text = ma.get_account_list()
    text += (
        "\n\n📌 Buyruqlar:\n"
        "/addaccount +998901234567 Ism\n"
        "/confirmcode +998901234567 12345\n"
        "/delacc 1 — o'chirish\n\n"
        "Xabar yuborayotganda akkaunt tanlash taklif qilinadi!"
    )
    await m.answer(text, reply_markup=main_menu())

@dp.message(F.text == "📧 Email")
async def btn_email(m: Message):
    if not await is_owner(m): return
    user_state[m.from_user.id] = "waiting_email"
    await m.answer("📧 Format: email@gmail.com|Mavzu|Matn", reply_markup=ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 Asosiy menyu")]], resize_keyboard=True))

@dp.message(F.document)
async def handle_doc(m: Message):
    if not await is_owner(m): return
    if not m.document.file_name.lower().endswith(".vcf"):
        await m.answer("⚠️ Faqat .vcf fayl."); return
    await m.answer("⏳ Yuklanmoqda...")
    file=await bot.get_file(m.document.file_id)
    with tempfile.NamedTemporaryFile(suffix=".vcf",delete=False) as tmp:
        await bot.download_file(file.file_path,tmp.name); tmp_path=tmp.name
    try:
        with open(tmp_path,"r",encoding="utf-8",errors="ignore") as f:
            new_contacts=parse_vcf(f.read())
        contacts.update(new_contacts)
        await m.answer(f"✅ {len(new_contacts)} ta kontakt yuklandi!\nJami: {len(contacts)} ta")
    finally: os.unlink(tmp_path)

@dp.message(F.text)
async def handle_text(m: Message):
    if not await is_owner(m): return
    update_stats()
    await bot.send_chat_action(m.chat.id,"typing")
    if m.from_user.id in pending_videos:
        m._pending_video = pending_videos[m.from_user.id]
    else:
        m._pending_video = None
    response = get_ai_response(m.from_user.id, m.text)
    await process_ai_response(m, response)
    # Video yuborilgandan keyin tozalash
    if m._pending_video and any("✅" in str(o) for o in []):
        pending_videos.pop(m.from_user.id, None)



@dp.message(F.video_note)
async def handle_videonote(m: Message):
    if not await is_owner(m): return
    await bot.send_chat_action(m.chat.id, "typing")
    file = await bot.get_file(m.video_note.file_id)
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        await bot.download_file(file.file_path, tmp.name)
        tmp_path = tmp.name
    try:
        with open(tmp_path, "rb") as f:
            video_bytes = f.read()
        pending_videos[m.from_user.id] = video_bytes
        await m.answer(
            f"⭕ Dumaloq video qabul qilindi ({len(video_bytes)//1024} KB)\n"
            "Kimga yuborishni ayting:\n"
            "Masalan: 'Shohruxga yubor'"
        )
    finally:
        os.unlink(tmp_path)

@dp.message(F.video)
async def handle_video(m: Message):
    if not await is_owner(m): return
    await bot.send_chat_action(m.chat.id, "typing")
    file = await bot.get_file(m.video.file_id)
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        await bot.download_file(file.file_path, tmp.name)
        tmp_path = tmp.name
    try:
        with open(tmp_path, "rb") as f:
            video_bytes = f.read()
        pending_videos[m.from_user.id] = video_bytes
        ffmpeg_ok = is_ffmpeg_installed()
        ffmpeg_status = "✅ ffmpeg bor" if ffmpeg_ok else "⚠️ ffmpeg yo'q (faqat oddiy video)"
        await m.answer(
            f"🎬 Video qabul qilindi ({len(video_bytes)//1024} KB)\n"
            f"{ffmpeg_status}\n\n"
            "Qanday yuborish?\n"
            "• 'Shohruxga yubor' — oddiy video 🎬\n"
            "• 'Shohruxga dumaloq yubor' — ⭕ dumaloq (Jarvis o'zi o'zgartiradi)"
        )
    finally:
        os.unlink(tmp_path)

@dp.message(F.voice)
async def handle_voice(m: Message):
    if not await is_owner(m): return
    update_stats()
    await bot.send_chat_action(m.chat.id,"typing")
    file=await bot.get_file(m.voice.file_id)
    with tempfile.NamedTemporaryFile(suffix=".ogg",delete=False) as tmp:
        await bot.download_file(file.file_path,tmp.name); tmp_path=tmp.name
    try:
        with open(tmp_path,"rb") as f:
            tr=client.audio.transcriptions.create(file=("audio.ogg",f.read()),model="whisper-large-v3",language="uz")
        text=tr.text.strip()
        await m.answer(f"🎙️ *Siz:* {text}",parse_mode="Markdown")
        # Qayd/vazifa so'zlari bo'lsa avtomatik saqlash
        keywords_note = ["qaydla","yozib qo'y","saqla","eslab qol"]
        keywords_todo = ["vazifa","qilish kerak","bajarish kerak"]
        tl = text.lower()
        if any(k in tl for k in keywords_note):
            note = {"id":len(notes)+1,"text":text,"date":datetime.now().strftime("%d.%m %H:%M")}
            notes.append(note)
            asyncio.create_task(notion.notion_add_note(text))
            asyncio.create_task(_sheets_note(text))
            await m.answer("📝 Qaydga saqlandi!")
        elif any(k in tl for k in keywords_todo):
            todo = {"id":len(todos)+1,"text":text,"done":False,"date":datetime.now().strftime("%d.%m")}
            todos.append(todo)
            asyncio.create_task(notion.notion_add_todo(text))
            asyncio.create_task(_sheets_todo(text))
            await m.answer("✅ Vazifaga saqlandi!")
        await process_ai_response(m,get_ai_response(m.from_user.id,text))
    finally: os.unlink(tmp_path)


async def auto_report():
    """Har dushanba 09:00 da haftalik hisobot yuborish"""
    while True:
        now = datetime.now()
        # Keyingi dushanbani topish
        days_ahead = 0 - now.weekday()  # 0 = dushanba
        if days_ahead <= 0:
            days_ahead += 7
        next_monday = now.replace(hour=9, minute=0, second=0) 
        import datetime as dt
        next_monday = now + dt.timedelta(days=days_ahead)
        next_monday = next_monday.replace(hour=9, minute=0, second=0)
        delta = (next_monday - now).total_seconds()
        print(f"📊 Keyingi hisobot: {next_monday.strftime('%d.%m.%Y %H:%M')}")
        await asyncio.sleep(delta)
        try:
            # Haftalik hisobot
            from extra_helpers import generate_report
            weekly = await generate_report("hafta")
            
            # Bugungi tug'ilgan kunlar
            from extra_helpers import check_todays_birthdays
            birthdays = check_todays_birthdays()
            
            # Vazifalar holati
            active_todos = [t for t in todos if not t["done"]]
            done_todos = [t for t in todos if t["done"]]
            
            # Eslatmalar
            reminder_count = len(reminders)
            
            report_text = (
                f"📊 HAFTALIK HISOBOT\n"
                f"━━━━━━━━━━━━━━━━━\n"
                f"{weekly}\n\n"
                f"✅ Vazifalar:\n"
                f"  Bajarilmagan: {len(active_todos)} ta\n"
                f"  Bajarilgan: {len(done_todos)} ta\n\n"
                f"⏰ Faol eslatmalar: {reminder_count} ta\n"
                f"👤 Kontaktlar: {len(contacts)} ta\n"
                f"━━━━━━━━━━━━━━━━━\n"
                f"🗓️ {datetime.now().strftime('%d.%m.%Y')}"
            )
            
            await bot.send_message(MY_ID, report_text)
            
            if birthdays:
                await bot.send_message(MY_ID, "\n".join(birthdays))
                
            print("📊 Haftalik hisobot yuborildi!")
        except Exception as e:
            print(f"⚠️ Hisobot xatosi: {e}")
        
        await asyncio.sleep(60)  # Qayta ishlamasin

async def birthday_checker():
    """Har kuni ertalab tug'ilgan kunlarni tekshirish"""
    while True:
        now=datetime.now()
        next_check=now.replace(hour=9,minute=0,second=0)
        if next_check<=now:
            from datetime import timedelta
            next_check+=timedelta(days=1)
        await asyncio.sleep((next_check-now).total_seconds())
        birthdays=extra.check_todays_birthdays()
        for msg in birthdays:
            await bot.send_message(MY_ID,msg)

# Guruh sozlamalari: {chat_id: True/False}
AUTO_REPLY_GROUPS = {}  # True = javob bersin, False = bermasin

async def watch_incoming_messages():
    """Shaxsiy va guruh xabarlariga Jarvis javob beradi"""
    from telethon import events as tel_events
    import time

    me = await userbot_client.get_me()
    my_id = me.id
    last_replied = {}  # spam himoya

    @userbot_client.on(tel_events.NewMessage())
    async def on_incoming(event):
        try:
            # O'z yozgan xabarlariga javob bermasin
            if event.out:
                return

            sender = await event.get_sender()
            if sender is None:
                return
            if getattr(sender, "bot", False):
                return
            if sender.id == my_id:
                return

            msg_text = event.message.text or ""
            if not msg_text.strip():
                return

            # Avtomatik javob o'chiq bo'lsa
            if not AUTO_REPLY.get("enabled", True):
                sender_name = getattr(sender, "first_name", "") or "Noma'lum"
                await bot.send_message(MY_ID, f"📩 {sender_name}: {msg_text}")
                return

            chat_id = str(event.chat_id)

            # Guruh xabari
            if event.is_group or event.is_channel:
                # Guruh ro'yxatda bormi va yozish ruxsati bormi?
                if AUTO_REPLY_GROUPS.get(chat_id) is not True:
                    return
            
            # Spam himoya - bir odamga 10 sekundda bir marta
            now = time.time()
            key = f"{sender.id}_{chat_id}"
            if key in last_replied and now - last_replied[key] < 10:
                return
            last_replied[key] = now

            sender_name = getattr(sender, "first_name", "") or "Noma'lum"
            sender_phone = getattr(sender, "phone", "") or ""

            # Guruhmi yoki lichkami
            if event.is_group:
                chat = await event.get_chat()
                chat_name = getattr(chat, "title", "Guruh")
                location = f"'{chat_name}' guruhida"
            else:
                location = "shaxsiy lichkada"

            # Botga bildirish
            await bot.send_message(
                MY_ID,
                f"📩 {location}:\n"
                f"👤 {sender_name} ({sender_phone}):\n"
                f"💬 {msg_text}"
            )

            # 2 sekund kutish (tabiiy ko'rinish)
            await asyncio.sleep(2)

            # AI javob
            if event.is_group:
                context = (
                    f"'{chat_name}' guruhida '{sender_name}' shunday yozdi: '{msg_text}'. "
                    f"Guruh a'zosiga qisqa, do'stona o'zbekcha javob yoz. 1-2 jumla."
                )
            else:
                context = (
                    f"'{sender_name}' shaxsiy lichkada yozdi: '{msg_text}'. "
                    f"Unga qisqa, do'stona o'zbekcha javob yoz. 1-2 jumla."
                )

            ai_reply = get_ai_response(MY_ID, context)

            # Javob yuborish
            await event.reply(ai_reply)

            # Botga nima yozilganini bildirish
            await bot.send_message(MY_ID, f"✅ Javob: {ai_reply[:80]}")

        except Exception as e:
            print(f"Incoming watcher xatosi: {e}")

    await userbot_client.run_until_disconnected()


async def run_group_bot():
    """group_bot.py ni bot bilan parallel ishlatish"""
    try:
        from telethon import TelegramClient, events
        import json

        API_ID   = int(os.getenv("TG_API_ID"))
        API_HASH = os.getenv("TG_API_HASH")
        GROQ_API_KEY = os.getenv("GROQ_API_KEY")

        group_client = TelegramClient("jarvis_group_session", API_ID, API_HASH)
        group_groq   = Groq(api_key=GROQ_API_KEY)

        SETTINGS_FILE = "group_settings.json"
        MODELS = ["llama-3.1-8b-instant", "llama-3.3-70b-versatile"]

        GROUP_PROMPT = """Sen Jarvis — aqlli guruh yordamchisan.
1. FAQAT O'ZBEK TILIDA javob ber.
2. Qisqa va foydali javob ber.
3. Do'stona bo'l.
4. Savol bo'lmasa — aralashma."""

        def load_gs():
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE) as f: return json.load(f)
            return {"active_groups": {}, "group_histories": {}}

        def save_gs(d):
            with open(SETTINGS_FILE, "w") as f: json.dump(d, f, ensure_ascii=False, indent=2)

        def should_respond(text):
            triggers = ["jarvis","?","nima","qanday","qaerda","qachon",
                       "nega","kim","qancha","yordam","bilasanmi","нима","қандай"]
            return any(t in text.lower() for t in triggers)

        def get_response(group_id, sender_name, text):
            gs = load_gs()
            gid = str(group_id)
            if gid not in gs.get("group_histories", {}):
                gs.setdefault("group_histories", {})[gid] = []
            hist = gs["group_histories"][gid]
            hist.append({"role": "user", "content": f"{sender_name}: {text}"})
            if len(hist) > 20: hist = hist[-20:]
            gs["group_histories"][gid] = hist
            for model in MODELS:
                try:
                    c = group_groq.chat.completions.create(
                        model=model,
                        messages=[{"role":"system","content":GROUP_PROMPT},*hist],
                        temperature=0.7, max_tokens=512
                    )
                    resp = c.choices[0].message.content
                    hist.append({"role":"assistant","content":resp})
                    save_gs(gs)
                    return resp
                except Exception as e:
                    if "429" in str(e): continue
            return None

        @group_client.on(events.NewMessage)
        async def on_group_msg(event):
            if not event.is_group or event.out: return
            gs = load_gs()
            group_id = str(event.chat_id)
            if group_id not in gs.get("active_groups", {}): return
            text = event.message.text or ""
            if not text.strip(): return
            mode = gs["active_groups"][group_id].get("mode", "smart")
            if mode == "smart" and not should_respond(text): return
            sender = await event.get_sender()
            name = getattr(sender, "first_name", "Foydalanuvchi") or "Foydalanuvchi"
            response = get_response(group_id, name, text)
            if response:
                await asyncio.sleep(1)
                await event.reply(response)

        await group_client.start(phone=os.getenv("TG_PHONE"))
        print("👥 Guruh bot ishga tushdi!")
        await group_client.run_until_disconnected()

    except Exception as e:
        print(f"⚠️ Guruh bot xatosi: {e}")

async def main():
    print("🤖 Jarvis Bot v14 ishga tushdi!")
    try:
        sheets.ensure_sheets()
        print("📊 Google Sheets tayyor!")
    except Exception as e:
        print(f"⚠️ Sheets: {e}")
    await userbot_client.start(phone=TG_PHONE)
    print("👤 Userbot ulandi!")
    asyncio.create_task(birthday_checker())
    asyncio.create_task(auto_report())
    asyncio.create_task(run_group_bot())
    asyncio.create_task(watch_incoming_messages())
    await dp.start_polling(bot)

if __name__=="__main__":
    asyncio.run(main())

# ── Guruh botni alohida thread da ishga tushirish ─────────────────────────────