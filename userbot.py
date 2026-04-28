import os
import asyncio
from telethon import TelegramClient
from telethon.tl.functions.contacts import ImportContactsRequest, DeleteContactsRequest
from telethon.tl.types import InputPhoneContact
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv("TG_API_ID"))
API_HASH = os.getenv("TG_API_HASH")
PHONE = os.getenv("TG_PHONE")  # +998901234567

client = TelegramClient("jarvis_session", API_ID, API_HASH)

async def get_client():
    if not client.is_connected():
        await client.connect()
    return client

client = TelegramClient("jarvis_session", API_ID, API_HASH,
    connection_retries=1,
    timeout=10
)

async def send_voice_to_phone(phone: str, audio_bytes: bytes, name: str = "Contact") -> bool:
    """Telefon raqam bo'yicha ovozli xabar yuborish"""
    try:
        c = await get_client()

        # Kontaktni vaqtincha qo'shish
        contact = InputPhoneContact(
            client_id=0,
            phone=phone,
            first_name=name,
            last_name=""
        )
        result = await c(ImportContactsRequest([contact]))

        if not result.users:
            return False  # Telegram da ro'yxatdan o'tmagan

        user = result.users[0]

        # Ovozli xabar yuborish
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        await c.send_file(
            user.id,
            tmp_path,
            voice_note=True
        )

        os.unlink(tmp_path)

        # Vaqtincha qo'shilgan kontaktni o'chirish (ixtiyoriy)
        # await c(DeleteContactsRequest([user]))

        return True

    except Exception as e:
        print(f"Userbot xatosi: {e}")
        return False

async def send_text_to_phone(phone: str, text: str, name: str = "Contact") -> bool:
    """Telefon raqam bo'yicha matnli xabar yuborish"""
    try:
        c = await get_client()

        contact = InputPhoneContact(
            client_id=0,
            phone=phone,
            first_name=name,
            last_name=""
        )
        result = await c(ImportContactsRequest([contact]))

        if not result.users:
            return False

        user = result.users[0]
        await c.send_message(user.id, text)
        return True

    except Exception as e:
        print(f"Userbot xatosi: {e}")
        return False

async def start_userbot():
    """Userbotni ishga tushirish va sessiyani saqlash"""
    await client.start(phone=PHONE)
    print("✅ Userbot ulandi!")
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(start_userbot())

async def send_video_to_phone(phone: str, video_bytes: bytes, name: str = "Contact", caption: str = "") -> bool:
    """Telefon raqam bo'yicha video xabar yuborish"""
    try:
        c = await get_client()
        contact = InputPhoneContact(client_id=0, phone=phone, first_name=name, last_name="")
        result = await c(ImportContactsRequest([contact]))
        if not result.users:
            return False
        user = result.users[0]
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp.write(video_bytes)
            tmp_path = tmp.name
        await c.send_file(user.id, tmp_path, caption=caption, video_note=False)
        os.unlink(tmp_path)
        return True
    except Exception as e:
        print(f"Video yuborish xatosi: {e}")
        return False

async def send_videonote_to_phone(phone: str, video_bytes: bytes, name: str = "Contact") -> bool:
    """Telefon raqam bo'yicha dumaloq video xabar yuborish"""
    try:
        c = await get_client()
        contact = InputPhoneContact(client_id=0, phone=phone, first_name=name, last_name="")
        result = await c(ImportContactsRequest([contact]))
        if not result.users:
            return False
        user = result.users[0]
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp.write(video_bytes)
            tmp_path = tmp.name
        # video_note=True — dumaloq qiladi
        await c.send_file(user.id, tmp_path, video_note=True)
        os.unlink(tmp_path)
        return True
    except Exception as e:
        print(f"Video note xatosi: {e}")
        return False
