import os
import json
import aiohttp
import hashlib
from datetime import datetime

# ── Web qidirish (SerpAPI) ────────────────────────────────────────────────────
async def web_search(query: str) -> str:
    api_key = os.getenv("SERPAPI_KEY")
    if not api_key:
        return "⚠️ SERPAPI_KEY yo'q. serpapi.com dan bepul oling."
    try:
        url = f"https://serpapi.com/search.json?q={query}&api_key={api_key}&hl=uz&num=3"
        async with aiohttp.ClientSession() as s:
            async with s.get(url) as r:
                data = await r.json()
                results = data.get("organic_results", [])
                if not results:
                    return "❌ Hech narsa topilmadi."
                lines = [f"🔍 '{query}' natijalari:\n"]
                for i, res in enumerate(results[:3], 1):
                    lines.append(f"{i}. {res.get('title', '')}\n   {res.get('snippet', '')}\n   🔗 {res.get('link', '')}")
                return "\n\n".join(lines)
    except Exception as e:
        return f"❌ Qidiruv xatosi: {e}"

# ── Yangiliklar (NewsAPI) ─────────────────────────────────────────────────────
async def get_news(topic: str = "uzbekistan", count: int = 5) -> str:
    api_key = os.getenv("NEWS_API_KEY")
    if not api_key:
        return "⚠️ NEWS_API_KEY yo'q. newsapi.org dan bepul oling."
    try:
        url = f"https://newsapi.org/v2/everything?q={topic}&apiKey={api_key}&pageSize={count}&language=en&sortBy=publishedAt"
        async with aiohttp.ClientSession() as s:
            async with s.get(url) as r:
                data = await r.json()
                articles = data.get("articles", [])
                if not articles:
                    return f"❌ '{topic}' bo'yicha yangilik topilmadi."
                lines = [f"📰 So'nggi yangiliklar ({topic}):\n"]
                for i, a in enumerate(articles[:count], 1):
                    title = a.get("title", "")
                    source = a.get("source", {}).get("name", "")
                    pub = a.get("publishedAt", "")[:10]
                    lines.append(f"{i}. [{pub}] {title}\n   📌 {source}")
                return "\n\n".join(lines)
    except Exception as e:
        return f"❌ Yangilik xatosi: {e}"

# ── Spotify ───────────────────────────────────────────────────────────────────
SPOTIFY_TOKEN = None
SPOTIFY_TOKEN_EXPIRY = None

async def get_spotify_token() -> str | None:
    global SPOTIFY_TOKEN, SPOTIFY_TOKEN_EXPIRY
    if SPOTIFY_TOKEN and SPOTIFY_TOKEN_EXPIRY and datetime.now().timestamp() < SPOTIFY_TOKEN_EXPIRY:
        return SPOTIFY_TOKEN
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None
    import base64
    auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    async with aiohttp.ClientSession() as s:
        async with s.post("https://accounts.spotify.com/api/token",
            headers={"Authorization": f"Basic {auth}"},
            data={"grant_type": "client_credentials"}) as r:
            data = await r.json()
            SPOTIFY_TOKEN = data.get("access_token")
            SPOTIFY_TOKEN_EXPIRY = datetime.now().timestamp() + data.get("expires_in", 3600)
            return SPOTIFY_TOKEN

async def spotify_search(query: str) -> str:
    token = await get_spotify_token()
    if not token:
        return "⚠️ SPOTIFY_CLIENT_ID va SPOTIFY_CLIENT_SECRET kerak.\ndeveloper.spotify.com dan oling."
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://api.spotify.com/v1/search?q={query}&type=track&limit=3",
                headers={"Authorization": f"Bearer {token}"}
            ) as r:
                data = await r.json()
                tracks = data.get("tracks", {}).get("items", [])
                if not tracks:
                    return f"❌ '{query}' topilmadi."
                lines = [f"🎵 '{query}' natijalari:\n"]
                for t in tracks:
                    name = t["name"]
                    artist = ", ".join(a["name"] for a in t["artists"])
                    url = t["external_urls"]["spotify"]
                    lines.append(f"🎶 {name} — {artist}\n🔗 {url}")
                return "\n\n".join(lines)
    except Exception as e:
        return f"❌ Spotify xatosi: {e}"

async def spotify_play(track_url: str) -> str:
    return f"🎵 Spotify da oching:\n{track_url}\n\n💡 Avtomatik ijro uchun Spotify Premium va device kerak."

# ── Parol saqlash (shifrlangan) ───────────────────────────────────────────────
PASSWORDS_FILE = "passwords.json"
MASTER_KEY = os.getenv("MASTER_PASSWORD", "jarvis2024")

def _encrypt(text: str) -> str:
    key = hashlib.md5(MASTER_KEY.encode()).hexdigest()
    result = []
    for i, c in enumerate(text):
        result.append(chr(ord(c) ^ ord(key[i % len(key)])))
    import base64
    return base64.b64encode("".join(result).encode()).decode()

def _decrypt(text: str) -> str:
    import base64
    decoded = base64.b64decode(text.encode()).decode()
    key = hashlib.md5(MASTER_KEY.encode()).hexdigest()
    result = []
    for i, c in enumerate(decoded):
        result.append(chr(ord(c) ^ ord(key[i % len(key)])))
    return "".join(result)

def _load_passwords() -> dict:
    if os.path.exists(PASSWORDS_FILE):
        with open(PASSWORDS_FILE, "r") as f:
            return json.load(f)
    return {}

def _save_passwords(data: dict):
    with open(PASSWORDS_FILE, "w") as f:
        json.dump(data, f, indent=2)

def password_save(service: str, username: str, password: str) -> str:
    data = _load_passwords()
    data[service.lower()] = {
        "username": username,
        "password": _encrypt(password),
        "date": datetime.now().strftime("%Y-%m-%d")
    }
    _save_passwords(data)
    return f"🔐 Parol saqlandi: {service} — {username}"

def password_get(service: str) -> str:
    data = _load_passwords()
    key = service.lower()
    if key not in data:
        for k in data:
            if service.lower() in k:
                key = k
                break
        else:
            return f"❌ '{service}' paroli topilmadi."
    entry = data[key]
    pwd = _decrypt(entry["password"])
    return f"🔐 {service.title()}:\n👤 Login: {entry['username']}\n🔑 Parol: {pwd}"

def password_list() -> str:
    data = _load_passwords()
    if not data:
        return "📭 Saqlangan parollar yo'q."
    lines = [f"🔐 Saqlangan parollar ({len(data)} ta):\n"]
    for service, entry in data.items():
        lines.append(f"• {service.title()} — {entry['username']} [{entry['date']}]")
    return "\n".join(lines)

def password_delete(service: str) -> str:
    data = _load_passwords()
    key = service.lower()
    if key in data:
        del data[key]
        _save_passwords(data)
        return f"🗑️ '{service}' paroli o'chirildi."
    return f"❌ '{service}' topilmadi."

# ── Tug'ilgan kun eslatmasi ───────────────────────────────────────────────────
BIRTHDAYS_FILE = "birthdays.json"

def _load_birthdays() -> dict:
    if os.path.exists(BIRTHDAYS_FILE):
        with open(BIRTHDAYS_FILE, "r") as f:
            return json.load(f)
    return {}

def _save_birthdays(data: dict):
    with open(BIRTHDAYS_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def birthday_add(name: str, date_str: str) -> str:
    """date_str: 15.03 yoki 15.03.1995"""
    data = _load_birthdays()
    parts = date_str.split(".")
    month, day = int(parts[1]), int(parts[0])
    year = int(parts[2]) if len(parts) > 2 else None
    data[name.lower()] = {"name": name, "day": day, "month": month, "year": year}
    _save_birthdays(data)
    age_info = f" ({datetime.now().year - year} yosh)" if year else ""
    return f"🎂 Tug'ilgan kun saqlandi: {name} — {day:02d}.{month:02d}{age_info}"

def birthday_list() -> str:
    data = _load_birthdays()
    if not data:
        return "📭 Tug'ilgan kunlar yo'q."
    today = datetime.now()
    lines = [f"🎂 Tug'ilgan kunlar ({len(data)} ta):\n"]
    upcoming = []
    for entry in data.values():
        try:
            this_year = datetime(today.year, entry["month"], entry["day"])
            if this_year < today:
                this_year = datetime(today.year + 1, entry["month"], entry["day"])
            days_left = (this_year - today).days
            age = f" ({today.year - entry['year']} yosh)" if entry.get("year") else ""
            upcoming.append((days_left, f"• {entry['name']}{age} — {entry['day']:02d}.{entry['month']:02d} ({days_left} kun qoldi)"))
        except:
            pass
    upcoming.sort(key=lambda x: x[0])
    lines += [u[1] for u in upcoming]
    return "\n".join(lines)

def check_todays_birthdays() -> list:
    data = _load_birthdays()
    today = datetime.now()
    result = []
    for entry in data.values():
        if entry["day"] == today.day and entry["month"] == today.month:
            age = f" ({today.year - entry['year']} yosh)" if entry.get("year") else ""
            result.append(f"🎂 Bugun {entry['name']} ning tug'ilgan kuni{age}! 🎉")
    return result

# ── Haftalik/oylik hisobot ────────────────────────────────────────────────────
async def generate_report(period: str = "hafta") -> str:
    try:
        from sheets_helper import get_service, SHEET_ID
        service = get_service()

        result = service.values().get(
            spreadsheetId=SHEET_ID,
            range="Xarajatlar!A:D"
        ).execute()
        rows = result.get("values", [])[1:]

        today = datetime.now()
        if period == "hafta":
            from datetime import timedelta
            start = today - timedelta(days=7)
            label = "Haftalik"
        else:
            start = today.replace(day=1)
            label = "Oylik"

        xarajat = 0
        daromad = 0
        xarajat_count = 0
        daromad_count = 0

        for row in rows:
            try:
                date = datetime.strptime(row[0][:10], "%Y-%m-%d")
                if date >= start:
                    amount = float(row[2]) if len(row) > 2 else 0
                    tur = row[3] if len(row) > 3 else "Xarajat"
                    if tur == "Daromad":
                        daromad += amount
                        daromad_count += 1
                    else:
                        xarajat += amount
                        xarajat_count += 1
            except:
                continue

        saldo = daromad - xarajat
        saldo_icon = "📈" if saldo >= 0 else "📉"

        return (
            f"📊 {label} hisobot ({start.strftime('%d.%m')} — {today.strftime('%d.%m')}):\n\n"
            f"💰 Daromad: {daromad:,.0f} so'm ({daromad_count} ta)\n"
            f"💸 Xarajat: {xarajat:,.0f} so'm ({xarajat_count} ta)\n"
            f"{saldo_icon} Saldo: {saldo:,.0f} so'm"
        )
    except Exception as e:
        return f"❌ Hisobot xatosi: {e}"

# ── Gemini AI (zaxira) ────────────────────────────────────────────────────────
async def gemini_response(prompt: str) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return "⚠️ GEMINI_API_KEY yo'q. aistudio.google.com dan bepul oling."
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        async with aiohttp.ClientSession() as s:
            async with s.post(url, json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.6, "maxOutputTokens": 1024}
            }) as r:
                data = await r.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                return f"🤖 Gemini: {text}"
    except Exception as e:
        return f"❌ Gemini xatosi: {e}"
