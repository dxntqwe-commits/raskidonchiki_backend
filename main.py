import json
import os
import logging
import uuid
from typing import List, Optional

import aiohttp
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    WebAppInfo, MenuButtonWebApp, Update,
)
from aiogram.enums import ChatMemberStatus, ParseMode
from aiogram.client.default import DefaultBotProperties

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========== CONFIG ==========
BOT_TOKEN = os.getenv("BOT_TOKEN", "8893552048:AAHdsPXbFtPPMRalW8oaa-DjLyRwirL_n_Q")
CHANNEL_USERNAME = "raskidonchiki"
CHANNEL_ID = -1002417376378
ADMIN_IDS = {661340242, 281387611}
MINI_APP_URL = os.getenv("MINI_APP_URL", "https://phenomenal-douhua-f7bcf1.netlify.app")
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "https://raskidonchiki-api.onrender.com")

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://xlqdomjssggkapovljpo.supabase.co").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

MAPS = ["mirage", "dust2", "inferno", "nuke", "ancient", "anubis", "cache"]
GRENADE_TYPES = ["smoke", "flash", "molotov", "he", "insta_smoke_ct", "insta_smoke_t"]

class MarkerCreate(BaseModel):
    map: str
    grenade_type: str
    x: float
    y: float
    title: str = ""
    link: str
    side: Optional[str] = None
    from_x: Optional[float] = None
    from_y: Optional[float] = None

# ========== SUPABASE HELPERS ==========
def _headers(extra=None):
    h = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    if extra:
        h.update(extra)
    return h

async def sb_get_markers(map_name: Optional[str] = None, grenade_type: Optional[str] = None) -> List[dict]:
    if not SUPABASE_KEY:
        return []
    params = []
    if map_name:
        params.append(f"map=eq.{map_name}")
    if grenade_type:
        params.append(f"grenade_type=eq.{grenade_type}")
    q = ("&".join(params)) if params else ""
    url = f"{SUPABASE_URL}/rest/v1/markers?select=*{'&' + q if q else ''}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=_headers()) as resp:
            if resp.status != 200:
                text = await resp.text()
                logger.error(f"Supabase GET error {resp.status}: {text}")
                return []
            return await resp.json()

async def sb_insert_marker(data: dict) -> dict:
    url = f"{SUPABASE_URL}/rest/v1/markers"
    async with aiohttp.ClientSession() as session:
        async with session.post(
            url,
            headers=_headers({"Prefer": "return=representation"}),
            json=data,
        ) as resp:
            text = await resp.text()
            if resp.status not in (200, 201):
                logger.error(f"Supabase INSERT error {resp.status}: {text}")
                raise HTTPException(status_code=500, detail=f"DB error: {text}")
            rows = json.loads(text) if text else []
            return rows[0] if isinstance(rows, list) and rows else data

async def sb_delete_marker(marker_id: str) -> bool:
    url = f"{SUPABASE_URL}/rest/v1/markers?id=eq.{marker_id}"
    async with aiohttp.ClientSession() as session:
        async with session.delete(url, headers=_headers()) as resp:
            return resp.status in (200, 204)

# ========== BOT ==========
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

async def is_subscribed(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in (
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.CREATOR,
        )
    except Exception as e:
        logger.error(f"Sub check error: {e}")
        return False

def get_subscribe_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Підписатися на канал", url=f"https://t.me/{CHANNEL_USERNAME}")],
        [InlineKeyboardButton(text="✅ Я підписався — перевірити", callback_data="check_sub")],
    ])

def get_main_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="🗺️ Відкрити розкидки", web_app=WebAppInfo(url=MINI_APP_URL))],
        [InlineKeyboardButton(text="💡 Запропонувати смоук", callback_data="propose_smoke")],
    ]
    if is_admin:
        buttons.append([InlineKeyboardButton(
            text="⚙️ Адмін-панель",
            web_app=WebAppInfo(url=f"{MINI_APP_URL}?admin=1"),
        )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@dp.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    is_admin = user_id in ADMIN_IDS
    if await is_subscribed(user_id):
        await message.answer(
            "🔥 <b>Вітаю в Raskidonchiki Lineups!</b>\n\n"
            "Натискай кнопку нижче, щоб відкрити карти:",
            reply_markup=get_main_keyboard(is_admin),
        )
    else:
        await message.answer(
            "👋 Привіт!\n\n"
            f"Підпишись на канал <b>@{CHANNEL_USERNAME}</b>, потім натисни «Я підписався».",
            reply_markup=get_subscribe_keyboard(),
        )

@dp.callback_query(F.data == "check_sub")
async def check_subscription(callback: CallbackQuery):
    user_id = callback.from_user.id
    is_admin = user_id in ADMIN_IDS
    if await is_subscribed(user_id):
        await callback.message.edit_text(
            "🔥 <b>Дякуємо за підписку!</b>",
            reply_markup=get_main_keyboard(is_admin),
        )
    else:
        await callback.answer("❌ Ти ще не підписаний.", show_alert=True)

@dp.callback_query(F.data == "propose_smoke")
async def propose_smoke(callback: CallbackQuery):
    await callback.message.answer(
        "💡 <b>Запропонувати смоук</b>\n\n"
        "Напиши: карта, тип гранати, опис, посилання."
    )
    await callback.answer()

@dp.message(F.text & ~F.text.startswith("/"))
async def handle_proposal(message: Message):
    if message.from_user.id in ADMIN_IDS:
        return
    text = (
        f"💡 <b>Нова пропозиція</b>\n\n"
        f"Від: @{message.from_user.username or 'no_username'} "
        f"(<code>{message.from_user.id}</code>)\n\n{message.text}"
    )
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text)
        except Exception as e:
            logger.error(e)
    await message.answer("✅ Надіслано адмінам.")

@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer(
        "⚙️ Адмін-панель",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="⚙️ Відкрити",
                web_app=WebAppInfo(url=f"{MINI_APP_URL}?admin=1"),
            )
        ]]),
    )

# ========== FASTAPI ==========
app = FastAPI(title="Raskidonchiki API + Bot")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def on_startup():
    if not SUPABASE_KEY:
        logger.warning("SUPABASE_KEY is empty — markers will not persist!")
    webhook_url = RENDER_EXTERNAL_URL.rstrip("/") + WEBHOOK_PATH
    try:
        await bot.set_webhook(webhook_url, drop_pending_updates=True)
        logger.info(f"Webhook set: {webhook_url}")
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text="🗺️ Розкидки", web_app=WebAppInfo(url=MINI_APP_URL))
        )
    except Exception as e:
        logger.error(f"Startup error: {e}")

@app.on_event("shutdown")
async def on_shutdown():
    await bot.session.close()

@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.model_validate(data, context={"bot": bot})
    await dp.feed_update(bot, update)
    return {"ok": True}

@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "mini_app": MINI_APP_URL,
        "supabase": bool(SUPABASE_KEY),
    }

@app.get("/api/maps")
async def get_maps():
    return {"maps": MAPS, "grenade_types": GRENADE_TYPES}

@app.get("/api/markers")
async def get_markers(map: Optional[str] = None, grenade_type: Optional[str] = None):
    markers = await sb_get_markers(map, grenade_type)
    return {"markers": markers}

@app.post("/api/markers")
async def create_marker(marker: MarkerCreate, x_telegram_user_id: Optional[int] = Header(None)):
    if x_telegram_user_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Admin access required")
    if marker.map not in MAPS:
        raise HTTPException(status_code=400, detail="Invalid map")
    if marker.grenade_type not in GRENADE_TYPES:
        raise HTTPException(status_code=400, detail="Invalid grenade type")
    data = {
        "id": str(uuid.uuid4()),
        "map": marker.map,
        "grenade_type": marker.grenade_type,
        "x": marker.x,
        "y": marker.y,
        "title": marker.title or marker.grenade_type,
        "link": marker.link,
        "side": marker.side,
        "from_x": marker.from_x,
        "from_y": marker.from_y,
    }
    saved = await sb_insert_marker(data)
    return {"marker": saved}

@app.delete("/api/markers/{marker_id}")
async def delete_marker(marker_id: str, x_telegram_user_id: Optional[int] = Header(None)):
    if x_telegram_user_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Admin access required")
    ok = await sb_delete_marker(marker_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Marker not found")
    return {"ok": True}
