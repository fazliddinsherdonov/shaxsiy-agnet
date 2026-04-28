import os
import aiohttp
from datetime import datetime

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_NOTES_DB = os.getenv("NOTION_NOTES_DB")
NOTION_TODOS_DB = os.getenv("NOTION_TODOS_DB")
NOTION_EXPENSES_DB = os.getenv("NOTION_EXPENSES_DB")
NOTION_CONTACTS_DB = os.getenv("NOTION_CONTACTS_DB")

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

BASE = "https://api.notion.com/v1"

# ── Qayd qo'shish ─────────────────────────────────────────────────────────────
async def notion_add_note(text: str) -> str:
    async with aiohttp.ClientSession() as s:
        r = await s.post(f"{BASE}/pages", headers=HEADERS, json={
            "parent": {"database_id": NOTION_NOTES_DB},
            "properties": {
                "Name": {"title": [{"text": {"content": text}}]},
                "Date": {"date": {"start": datetime.now().isoformat()}}
            }
        })
        data = await r.json()
        if r.status == 200:
            return f"✅ Notion ga qayd saqlandi: {text[:50]}"
        return f"❌ Notion xatosi: {data.get('message', 'nomalum')}"

# ── Qaydlarni olish ───────────────────────────────────────────────────────────
async def notion_get_notes(limit: int = 10) -> str:
    async with aiohttp.ClientSession() as s:
        r = await s.post(f"{BASE}/databases/{NOTION_NOTES_DB}/query", headers=HEADERS, json={
            "sorts": [{"property": "Date", "direction": "descending"}],
            "page_size": limit
        })
        data = await r.json()
        if r.status != 200:
            return f"❌ Notion xatosi: {data.get('message')}"
        results = data.get("results", [])
        if not results:
            return "📭 Notion da qaydlar yo'q."
        lines = [f"📝 Notion qaydlar ({len(results)} ta):\n"]
        for i, page in enumerate(results, 1):
            props = page["properties"]
            name = props["Name"]["title"][0]["text"]["content"] if props["Name"]["title"] else "—"
            date = props.get("Date", {}).get("date", {})
            date_str = date.get("start", "")[:10] if date else ""
            lines.append(f"{i}. [{date_str}] {name}")
        return "\n".join(lines)

# ── Vazifa qo'shish ───────────────────────────────────────────────────────────
async def notion_add_todo(text: str) -> str:
    async with aiohttp.ClientSession() as s:
        r = await s.post(f"{BASE}/pages", headers=HEADERS, json={
            "parent": {"database_id": NOTION_TODOS_DB},
            "properties": {
                "Name": {"title": [{"text": {"content": text}}]},
                "Done": {"checkbox": False},
                "Date": {"date": {"start": datetime.now().isoformat()}}
            }
        })
        data = await r.json()
        if r.status == 200:
            return f"✅ Notion ga vazifa saqlandi: {text[:50]}"
        return f"❌ Notion xatosi: {data.get('message')}"

# ── Vazifalarni olish ─────────────────────────────────────────────────────────
async def notion_get_todos() -> str:
    async with aiohttp.ClientSession() as s:
        r = await s.post(f"{BASE}/databases/{NOTION_TODOS_DB}/query", headers=HEADERS, json={
            "sorts": [{"property": "Date", "direction": "descending"}],
            "page_size": 20
        })
        data = await r.json()
        if r.status != 200:
            return f"❌ Notion xatosi: {data.get('message')}"
        results = data.get("results", [])
        if not results:
            return "📭 Notion da vazifalar yo'q."
        active = []
        done_list = []
        for page in results:
            props = page["properties"]
            name = props["Name"]["title"][0]["text"]["content"] if props["Name"]["title"] else "—"
            done = props.get("Done", {}).get("checkbox", False)
            pid = page["id"]
            if done:
                done_list.append(f"  ✅ {name}")
            else:
                active.append((pid, f"  ⬜ {name}"))
        lines = ["📋 Notion vazifalar:\n"]
        if active:
            lines.append("Bajarilmagan:")
            lines += [a[1] for a in active]
        if done_list:
            lines.append("\nBajarilgan:")
            lines += done_list
        return "\n".join(lines)

# ── Vazifani bajarildi deb belgilash ─────────────────────────────────────────
async def notion_done_todo(text: str) -> str:
    async with aiohttp.ClientSession() as s:
        # Avval qidirish
        r = await s.post(f"{BASE}/databases/{NOTION_TODOS_DB}/query", headers=HEADERS, json={
            "filter": {"property": "Name", "title": {"contains": text}}
        })
        data = await r.json()
        results = data.get("results", [])
        if not results:
            return f"❌ '{text}' vazifasi topilmadi"
        page_id = results[0]["id"]
        r2 = await s.patch(f"{BASE}/pages/{page_id}", headers=HEADERS, json={
            "properties": {"Done": {"checkbox": True}}
        })
        if r2.status == 200:
            return f"✅ Bajarildi: {text}"
        return "❌ Yangilashda xato"

# ── Xarajat qo'shish ──────────────────────────────────────────────────────────
async def notion_add_expense(name: str, amount: float, exp_type: str = "Xarajat") -> str:
    async with aiohttp.ClientSession() as s:
        r = await s.post(f"{BASE}/pages", headers=HEADERS, json={
            "parent": {"database_id": NOTION_EXPENSES_DB},
            "properties": {
                "Name": {"title": [{"text": {"content": name}}]},
                "Amount": {"number": amount},
                "Type": {"select": {"name": exp_type}},
                "Date": {"date": {"start": datetime.now().isoformat()}}
            }
        })
        data = await r.json()
        if r.status == 200:
            return f"✅ Notion ga yozildi: {name} — {amount:,.0f} so'm ({exp_type})"
        return f"❌ Notion xatosi: {data.get('message')}"

# ── Xarajatlarni olish ────────────────────────────────────────────────────────
async def notion_get_expenses() -> str:
    async with aiohttp.ClientSession() as s:
        r = await s.post(f"{BASE}/databases/{NOTION_EXPENSES_DB}/query", headers=HEADERS, json={
            "sorts": [{"property": "Date", "direction": "descending"}],
            "page_size": 15
        })
        data = await r.json()
        if r.status != 200:
            return f"❌ Notion xatosi: {data.get('message')}"
        results = data.get("results", [])
        if not results:
            return "📭 Xarajatlar yo'q."
        lines = ["💰 Notion xarajatlar:\n"]
        total = 0
        for page in results:
            props = page["properties"]
            name = props["Name"]["title"][0]["text"]["content"] if props["Name"]["title"] else "—"
            amount = props.get("Amount", {}).get("number", 0) or 0
            exp_type = props.get("Type", {}).get("select", {})
            type_name = exp_type.get("name", "") if exp_type else ""
            date = props.get("Date", {}).get("date", {})
            date_str = date.get("start", "")[:10] if date else ""
            total += amount
            lines.append(f"• [{date_str}] {name}: {amount:,.0f} so'm {f'({type_name})' if type_name else ''}")
        lines.append(f"\n💵 Jami: {total:,.0f} so'm")
        return "\n".join(lines)

# ── Kontakt qo'shish ──────────────────────────────────────────────────────────
async def notion_add_contact(name: str, phone: str) -> str:
    async with aiohttp.ClientSession() as s:
        r = await s.post(f"{BASE}/pages", headers=HEADERS, json={
            "parent": {"database_id": NOTION_CONTACTS_DB},
            "properties": {
                "Name": {"title": [{"text": {"content": name}}]},
                "Phone": {"phone_number": phone},
                "Date": {"date": {"start": datetime.now().isoformat()}}
            }
        })
        data = await r.json()
        if r.status == 200:
            return f"✅ Notion ga kontakt saqlandi: {name} — {phone}"
        return f"❌ Notion xatosi: {data.get('message')}"
