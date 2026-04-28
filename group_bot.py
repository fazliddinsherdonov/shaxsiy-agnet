"""
Guruh uchun userbot - kim yozsa AI javob beradi
"""
import os
import asyncio
import json
from datetime import datetime
from dotenv import load_dotenv
from groq import Groq
from telethon import TelegramClient, events

load_dotenv()

API_ID   = int(os.getenv("TG_API_ID"))
API_HASH = os.getenv("TG_API_HASH")
PHONE    = os.getenv("TG_PHONE")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

client = TelegramClient("jarvis_session", API_ID, API_HASH)
groq   = Groq(api_key=GROQ_API_KEY)

# Sozlamalar fayli
SETTINGS_FILE = "group_settings.json"

def load_settings() -> dict:
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE) as f:
            return json.load(f)
    return {
        "active_groups": {},   # {group_id: {"name": "...", "mode": "smart"}}
        "group_histories": {}  # {group_id: [messages]}
    }

def save_settings(data: dict):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

settings = load_settings()

GROUP_SYSTEM_PROMPT = """
Sen Jarvis — aqlli guruh yordamchisan.
Qoidalar:
1. FAQAT O'ZBEK TILIDA javob ber.
2. Guruh a'zolariga do'stona va qisqa javob ber.
3. Savollarga aniq javob ber.
4. Agar savol bo'lmasa yoki oddiy suhbat bo'lsa — qo'shilma.
5. Haqorat yoki noto'g'ri so'zlarga munosabat bildirma.
6. Har doim foydali bo'lishga harakat qil.
"""

def get_group_ai_response(group_id: str, user_name: str, user_message: str) -> str:
    if "group_histories" not in settings:
        settings["group_histories"] = {}
    
    gid = str(group_id)
    if gid not in settings["group_histories"]:
        settings["group_histories"][gid] = []
    
    history = settings["group_histories"][gid]
    history.append({"role": "user", "content": f"{user_name}: {user_message}"})
    
    # Tarixni 20 xabar bilan cheklash
    if len(history) > 20:
        history = history[-20:]
        settings["group_histories"][gid] = history

    MODELS = ["llama-3.1-8b-instant", "llama-3.3-70b-versatile"]
    
    for model in MODELS:
        try:
            completion = groq.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": GROUP_SYSTEM_PROMPT},
                    *history
                ],
                temperature=0.7,
                max_tokens=512,
            )
            response = completion.choices[0].message.content
            history.append({"role": "assistant", "content": response})
            save_settings(settings)
            return response
        except Exception as e:
            if "429" in str(e): continue
            raise e
    
    return None

def should_respond(message_text: str, bot_name: str = "Jarvis") -> bool:
    """Javob berish kerakmi?"""
    text_lower = message_text.lower()
    triggers = [
        "jarvis", "ботга", "botga", "?", "нима", "nima",
        "қандай", "qanday", "қаерда", "qaerda", "қачон", "qachon",
        "нега", "nega", "ким", "kim", "qancha", "қанча",
        "yordam", "ёрдам", "bilasanmi", "биласанми"
    ]
    return any(t in text_lower for t in triggers)

@client.on(events.NewMessage)
async def handle_group_message(event):
    # Faqat guruhlar
    if not event.is_group:
        return
    
    group_id = str(event.chat_id)
    
    # Faol guruhlar ro'yxatida bormi?
    if group_id not in settings.get("active_groups", {}):
        return
    
    # O'z xabarlariga javob bermasin
    if event.out:
        return
    
    message_text = event.message.text or ""
    if not message_text.strip():
        return
    
    group_info = settings["active_groups"][group_id]
    mode = group_info.get("mode", "smart")
    
    sender = await event.get_sender()
    sender_name = getattr(sender, 'first_name', 'Foydalanuvchi') or 'Foydalanuvchi'
    
    # Smart mode: faqat savol/trigger bo'lsa javob bersin
    if mode == "smart" and not should_respond(message_text):
        return
    
    # Javob tayyorlash
    response = get_group_ai_response(group_id, sender_name, message_text)
    
    if response:
        await asyncio.sleep(1)  # Tabiiy ko'rinish uchun
        await event.reply(response)

async def main():
    await client.start(phone=PHONE)
    print("🤖 Guruh bot ishga tushdi!")
    print(f"Faol guruhlar: {list(settings.get('active_groups', {}).values())}")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
