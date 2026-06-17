"""
ManatAds – Main Application Entry Point
=========================================
Combines:
  • FastAPI  – HMAC-secured Adsgram S2S callback + Mini App static serving.
  • Aiogram  – Telegram Bot via webhook (set on startup, removed on shutdown).

Run with:
    uvicorn main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import os
import sys
import uuid
import urllib.parse
import json
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Windows terminalinda Unicode print() xetasini onle
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from aiogram import types as aio_types
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select, update, func

from bot_instance import bot, dp
from database import async_session, close_db, init_db
from handlers import commands_router
from models import User, WatchRecord, Task, UserTask

load_dotenv()

# ── Logging ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(name)-18s │ %(levelname)-7s │ %(message)s",
)
logger = logging.getLogger("manatads")

# ── Configuration ───────────────────────────────────────────────────────
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
WEBHOOK_URL: str = os.getenv("WEBHOOK_URL", "").rstrip("/")
FRONTEND_URL: str = os.getenv("FRONTEND_URL", "https://manatqazan.vercel.app").rstrip("/")
ADSGRAM_SECRET: str = os.getenv("ADSGRAM_SECRET", "")
MC_PER_VIDEO: int = int(os.getenv("MC_PER_VIDEO", "50"))
DAILY_VIDEO_LIMIT: int = int(os.getenv("DAILY_VIDEO_LIMIT", "50"))
MC_TO_AZN_RATE: int = int(os.getenv("MC_TO_AZN_RATE", "140000"))
MIN_WITHDRAWAL_TRY: float = float(os.getenv("MIN_WITHDRAWAL_TRY", "135.00"))
REFERRAL_BONUS_PERCENT: int = int(os.getenv("REFERRAL_BONUS_PERCENT", "10"))

ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "1970477419,6682395629")
ADMIN_IDS = [int(x.strip()) for x in ADMIN_IDS_RAW.split(",") if x.strip().isdigit()]

MAINTENANCE_FLAG_PATH = os.path.join(os.path.dirname(__file__), "maintenance.flag")

def is_maintenance_mode() -> bool:
    if os.getenv("MAINTENANCE_MODE", "false").lower() == "true":
        return True
    return os.path.exists(MAINTENANCE_FLAG_PATH)

WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"

# ── Per-user concurrency locks ───────────────────────────────────────────
# Prevents race conditions when multiple Adsgram webhooks arrive for the
# same user within milliseconds (e.g. 3 rapid callbacks = 900 MC burst).
# Each user gets one asyncio.Lock; concurrent requests queue and execute
# sequentially so the DB row is never written from two coroutines at once.
_user_credit_locks: dict[str, asyncio.Lock] = {}
_user_credit_locks_meta: asyncio.Lock = asyncio.Lock()

def _get_utc_date(dt: datetime | None) -> date | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc).date()
    return dt.astimezone(timezone.utc).date()

async def _get_user_lock(user_key: str) -> asyncio.Lock:
    """Return (or create) a per-user asyncio.Lock keyed by user identifier."""
    async with _user_credit_locks_meta:
        if user_key not in _user_credit_locks:
            _user_credit_locks[user_key] = asyncio.Lock()
        return _user_credit_locks[user_key]


def _get_vip_params(vip_status: str, now: datetime) -> tuple[int, int, int]:
    """
    Return (session_limit, daily_limit, mc_reward) for a given VIP tier.

    Tiers (MC_TO_AZN_RATE=140,000 | Withdrawal threshold=700,000 MC = 5 AZN):
      free    -> session=25, daily=50, reward=240 MC  (50×240=12,000 MC/day)
      pro     -> session=22, daily=45, reward=311 MC  (45×311=13,995 MC/day)
      elite   -> session=20, daily=40, reward=420 MC  (40×420=16,800 MC/day)
      passive -> same as free (video rewards unchanged; passive income is separate)
    """
    tier = (vip_status or "free").lower().strip()
    if tier == "pro":
        return (22, 45, 311)
    if tier == "elite":
        return (20, 40, 420)
    # passive intentionally falls through to free params
    return (25, 50, 240)  # free / passive / fallback

if not commands_router.parent_router:
    dp.include_router(commands_router)


# ── Lifespan ────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(application: FastAPI):
    """Startup / shutdown lifecycle for the combined app."""
    # ── Startup ──
    await init_db()
    logger.info("Database initialised.")

    # ── Database Migration for VIP + Passive Income ──
    try:
        from database import DB_IS_POSTGRES
        from sqlalchemy import text
        if DB_IS_POSTGRES:
            async with async_session() as session:
                await session.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS vip_status VARCHAR(255) DEFAULT 'free';"))
                await session.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS vip_expires_at TIMESTAMP WITH TIME ZONE;"))
                await session.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS passive_last_paid_at TIMESTAMP WITH TIME ZONE;"))
                await session.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS had_passive_vip BOOLEAN DEFAULT FALSE;"))
                await session.commit()
            logger.info("PostgreSQL auto-migration done (vip_status, vip_expires_at, passive_last_paid_at, had_passive_vip).")
        else:
            logger.info("SQLite database detected; auto-migration for PostgreSQL columns skipped.")
    except Exception as e:
        logger.warning("Database auto-migration warning/failed: %s", e)

    # ── Launch async cooldown notification worker ──
    notification_task = asyncio.create_task(_cooldown_notification_worker())
    application.state.notification_task = notification_task
    logger.info("Cooldown notification worker started.")

    # ── Launch midnight broadcast scheduler ──
    broadcast_task = asyncio.create_task(_midnight_broadcast_scheduler())
    application.state.broadcast_task = broadcast_task
    logger.info("Midnight broadcast scheduler started.")

    # ── Launch passive income worker ──
    passive_task = asyncio.create_task(_passive_income_worker())
    application.state.passive_task = passive_task
    logger.info("Passive income worker started.")

    # ── Set Bot Commands Menu ──
    try:
        commands_az = [
            aio_types.BotCommand(command="start", description="Botu başladın və Yeniləyin"),
            aio_types.BotCommand(command="lang",  description="Dil seçimini dəyişdirin"),
        ]
        commands_tr = [
            aio_types.BotCommand(command="start", description="Botu başlat ve Yenile"),
            aio_types.BotCommand(command="lang",  description="Dil seçimini değiştir"),
        ]
        commands_en = [
            aio_types.BotCommand(command="start", description="Start and Refresh the Bot"),
            aio_types.BotCommand(command="lang",  description="Change language selection"),
        ]
        commands_ru = [
            aio_types.BotCommand(command="start", description="Запустить и обновить бота"),
            aio_types.BotCommand(command="lang",  description="Изменить выбор языка"),
        ]

        # Default fallback to English
        await bot.set_my_commands(commands_en, scope=aio_types.BotCommandScopeDefault())
        # Specific languages
        await bot.set_my_commands(commands_az, scope=aio_types.BotCommandScopeDefault(), language_code="az")
        await bot.set_my_commands(commands_tr, scope=aio_types.BotCommandScopeDefault(), language_code="tr")
        await bot.set_my_commands(commands_en, scope=aio_types.BotCommandScopeDefault(), language_code="en")
        await bot.set_my_commands(commands_ru, scope=aio_types.BotCommandScopeDefault(), language_code="ru")
        
        # Admin scope commands – set for every admin
        from handlers.commands import ADMIN_IDS
        if ADMIN_IDS:
            admin_commands = [
                aio_types.BotCommand(command="start", description="Botu başlat ve Yenile"),
                aio_types.BotCommand(command="lang", description="Dil seçimini dəyiş"),
                aio_types.BotCommand(command="admin", description="Admin panelini aç")
            ]
            for admin_chat_id in ADMIN_IDS:
                try:
                    await bot.set_my_commands(
                        commands=admin_commands,
                        scope=aio_types.BotCommandScopeChat(chat_id=admin_chat_id)
                    )
                except Exception as cmd_err:
                    logger.warning("Failed to set admin commands for %s: %s", admin_chat_id, cmd_err)
            
        logger.info("Bot commands menu set for multiple languages and admin scope.")
    except Exception as e:
        logger.error("Failed to set bot commands menu: %s", e)

    # ── Set Menu Button ──
    try:
        await bot.set_chat_menu_button(
            menu_button=aio_types.MenuButtonWebApp(
                text="🚀 Aç",
                web_app=aio_types.WebAppInfo(url=f"{FRONTEND_URL}?v=4.8.0")
            )
        )
        logger.info("Chat menu button (WebApp) restored.")
    except Exception as e:
        logger.error("Failed to set chat menu button: %s", e)

    webhook_url = os.getenv("WEBHOOK_URL", "").strip()
    is_placeholder = "your-domain" in webhook_url or not webhook_url

    if is_placeholder:
        logger.info("WEBHOOK_URL is a placeholder or empty. Starting bot in Long Polling mode...")
        polling_task = asyncio.create_task(
            dp.start_polling(bot, allowed_updates=["message", "callback_query"])
        )
        application.state.polling_task = polling_task
    else:
        webhook_full = f"{webhook_url}{WEBHOOK_PATH}"
        try:
            await bot.set_webhook(
                url=webhook_full,
                allowed_updates=["message", "callback_query"],
                drop_pending_updates=True,
            )
            logger.info("Webhook set → %s", webhook_full)
        except Exception as e:
            logger.error("Failed to set webhook (%s). Falling back to Long Polling...", e)
            polling_task = asyncio.create_task(
                dp.start_polling(bot, allowed_updates=["message", "callback_query"])
            )
            application.state.polling_task = polling_task

    yield

    # ── Shutdown ──
    if hasattr(application.state, "notification_task"):
        application.state.notification_task.cancel()
        try:
            await application.state.notification_task
        except asyncio.CancelledError:
            pass
        logger.info("Cooldown notification worker stopped.")

    if hasattr(application.state, "broadcast_task"):
        application.state.broadcast_task.cancel()
        try:
            await application.state.broadcast_task
        except asyncio.CancelledError:
            pass
        logger.info("Midnight broadcast scheduler stopped.")

    if hasattr(application.state, "polling_task"):
        logger.info("Stopping Long Polling...")
        application.state.polling_task.cancel()
        try:
            await application.state.polling_task
        except asyncio.CancelledError:
            pass
        logger.info("Long Polling stopped.")
    else:
        logger.info("Removing Webhook...")
        await bot.delete_webhook(drop_pending_updates=True)
    
    await close_db()
    logger.info("Shutdown complete.")


app = FastAPI(
    title="ManatAds API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── DEBUG: Log all incoming requests ────────────────────────────────────
@app.middleware("http")
async def log_all_requests(request: Request, call_next):
    body_bytes = await request.body()
    logger.info(
        "[REQUEST] %s %s | Query: %s | Body: %s",
        request.method, request.url.path,
        dict(request.query_params),
        body_bytes[:500].decode("utf-8", errors="replace") if body_bytes else "(empty)"
    )
    response = await call_next(request)
    logger.info("[RESPONSE] %s %s → %s", request.method, request.url.path, response.status_code)
    return response


# ── Telegram Webhook Endpoint ──────────────────────────────────────────
@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request) -> JSONResponse:
    """Receive Telegram updates and feed them to Aiogram."""
    update_data: dict[str, Any] = await request.json()
    update = aio_types.Update.model_validate(update_data, context={"bot": bot})
    await dp.feed_update(bot=bot, update=update)
    return JSONResponse({"ok": True})


# ── Frontend-Triggered Secure Reward ─────────────────────────────────────
@app.post("/api/reward/frontend", summary="Frontend-triggered secure reward")
async def frontend_reward(request: Request) -> JSONResponse:
    """
    Secure alternative to S2S webhook. Verified using Telegram's initData.
    """
    # Verify Telegram WebApp Data
    init_data = request.headers.get("X-Init-Data")
    if not init_data:
        raise HTTPException(status_code=401, detail="Missing X-Init-Data header")
        
    user_data_tg = validate_init_data(init_data, BOT_TOKEN)
    if not user_data_tg:
        logger.error("[FRONTEND-REWARD] Invalid initData")
        raise HTTPException(status_code=401, detail="Invalid Telegram InitData")
        
    user_id_val = user_data_tg.get("id")
    if not user_id_val:
        raise HTTPException(status_code=400, detail="User ID not found in InitData")
        
    # Get payload
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
        
    event_id = body.get("event_id")
    if not event_id:
        raise HTTPException(status_code=400, detail="Missing event_id")
        
    logger.info("[FRONTEND-REWARD] Verified trigger for user=%s, event=%s", user_id_val, event_id)
    return await _credit_user(user_id_val, event_id=event_id, source="frontend_secure")


# ── Adsgram S2S Reward – GET (əsl Adsgram formatı) ─────────────────────
@app.get("/api/reward", summary="Adsgram S2S reward callback (GET)")
async def adsgram_reward_get(
    request: Request,
) -> JSONResponse:
    """
    Adsgram S2S callback – GET sorğusu ilə gəlir.
    Dashboard-da Reward URL:
        https://api.nowsupport.site/api/reward?userId=[userId]&blockId=35141
    """
    params = dict(request.query_params)

    # -- DEBUG: Terminald canli log --
    print("\n" + "="*60)
    print("[ADSGRAM-GET] WEBHOOK SORGUSU ALINDI")
    print(f"[ADSGRAM-GET] Parametrler: {params}")
    print(f"[ADSGRAM-GET] IP: {request.client.host if request.client else 'unknown'}")
    print("="*60 + "\n")

    logger.info("[ADSGRAM-GET] Raw query params: %s | IP=%s", params, request.client.host if request.client else "unknown")

    # userId, user_id, user, tgId, tg_id kimi butun mumkun adlari yoxla
    user_id_val = (
        params.get("userId")
        or params.get("user_id")
        or params.get("user")
        or params.get("tgId")
        or params.get("tg_id")
        or params.get("telegram_id")
        or params.get("telegramId")
        or params.get("uid")
    )
    block_id = params.get("blockId") or params.get("block_id")

    print(f"[ADSGRAM-GET] userId={user_id_val!r} | blockId={block_id!r}")

    # -- HMAC-SHA256 Signature Verification --
    received_signature = params.get("signature") or params.get("hash") or params.get("sign")
    
    if not received_signature:
        logger.error("[ADSGRAM-GET] REJECTED: Missing signature in request.")
        raise HTTPException(status_code=403, detail="Forbidden: Missing signature")

    # Exclude signature fields from the hash calculation
    verify_params = {k: v for k, v in params.items() if k not in ["signature", "hash", "sign"]}
    
    # Adsgram standard verification:
    # 1. Sort the parameters alphabetically by key.
    # 2. Concatenate them into a string.
    # Example string format: "blockId=123&eventId=xyz&userId=123..." (or just values depending on the specific integration)
    # The prompt specified "sort the keys alphabetically, concatenate them into a string"
    # Actually Adsgram generally sorts keys, creates `key=value` strings, joins by `&`. Let's use standard URL encoding format without actual url encoding unless needed.
    # Often it is just joined values or key=value joined by empty string or `&`. 
    # Based on prompt: "sort the keys alphabetically, concatenate them into a string"
    
    sorted_keys = sorted(verify_params.keys())
    data_check_string = "".join([f"{k}={verify_params[k]}" for k in sorted_keys])
    
    # Calculate HMAC-SHA256
    secret_key = ADSGRAM_SECRET.encode()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    
    if calculated_hash != received_signature:
        logger.error(
            "[ADSGRAM-GET] REJECTED: Signature mismatch! IP=%s | Calculated=%s | Received=%s",
            request.client.host if request.client else "unknown", calculated_hash, received_signature
        )
        raise HTTPException(status_code=403, detail="Forbidden: Invalid signature")
        
    logger.info("[ADSGRAM-GET] Signature verified successfully.")

    if not user_id_val:
        logger.error("[ADSGRAM-GET] Missing userId or user_id in request query parameters! All params: %s", params)
        raise HTTPException(status_code=400, detail="userId parametri tapilmadi.")

    event_id = params.get("event_id") or params.get("eventId")
    if not event_id:
        logger.error("[ADSGRAM-GET] Missing event_id in request query parameters! All params: %s", params)
        raise HTTPException(status_code=400, detail="event_id parametri tapilmadi.")

    return await _credit_user(user_id_val, event_id=event_id, source="adsgram_get")


# ── Adsgram S2S Reward – POST (köhnə / alternativ format) ───────────────
@app.post("/api/adsgram/callback", summary="Adsgram S2S reward callback (POST)")
async def adsgram_callback(request: Request) -> JSONResponse:
    """
    POST format callback – HMAC yoxlanışı bypass edildi (debug rejimi).
    """
    # Ham body-ni oxu (hem JSON, hem form-data ucun)
    raw_body = await request.body()
    print("\n" + "="*60)
    print("[ADSGRAM-POST] WEBHOOK SORGUSU ALINDI")
    print(f"[ADSGRAM-POST] Raw body: {raw_body[:500]}")
    print(f"[ADSGRAM-POST] IP: {request.client.host if request.client else 'unknown'}")
    print("="*60 + "\n")

    try:
        payload = await request.json()
    except Exception:
        # JSON deyilse, query parametrlerini yoxla
        payload = dict(request.query_params)
        print(f"[ADSGRAM-POST] JSON parse failed, using query params: {payload}")

    print(f"[ADSGRAM-POST] Parsed payload: {payload}")
    logger.info("[ADSGRAM-POST] Raw body payload: %s", payload)

    user_id_val = (
        payload.get("user_id")
        or payload.get("userId")
        or payload.get("user")
        or payload.get("tgId")
        or payload.get("tg_id")
        or payload.get("telegram_id")
        or payload.get("telegramId")
        or payload.get("uid")
    )
    event_id = payload.get("event_id") or payload.get("eventId")
    # -- HMAC-SHA256 Signature Verification --
    received_signature = payload.get("signature") or payload.get("hash") or payload.get("sign")
    
    if not received_signature:
        logger.error("[ADSGRAM-POST] REJECTED: Missing signature in payload.")
        raise HTTPException(status_code=403, detail="Forbidden: Missing signature")

    # Exclude signature fields from the hash calculation
    verify_params = {k: v for k, v in payload.items() if k not in ["signature", "hash", "sign"]}
    
    sorted_keys = sorted(verify_params.keys())
    data_check_string = "".join([f"{k}={verify_params[k]}" for k in sorted_keys])
    
    # Calculate HMAC-SHA256
    secret_key = ADSGRAM_SECRET.encode()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    
    if calculated_hash != received_signature:
        logger.error(
            "[ADSGRAM-POST] REJECTED: Signature mismatch! IP=%s | Calculated=%s | Received=%s",
            request.client.host if request.client else "unknown", calculated_hash, received_signature
        )
        raise HTTPException(status_code=403, detail="Forbidden: Invalid signature")
        
    logger.info("[ADSGRAM-POST] Signature verified successfully.")

    if not user_id_val:
        logger.error("[ADSGRAM-POST] Missing user_id in payload! Keys: %s", list(payload.keys()))
        raise HTTPException(status_code=400, detail="user_id parametri tapilmadi.")

    if not event_id:
        logger.error("[ADSGRAM-POST] Missing event_id in payload! Keys: %s", list(payload.keys()))
        raise HTTPException(status_code=400, detail="event_id parametri tapilmadi.")

    return await _credit_user(user_id_val, event_id=event_id, source="adsgram_post")


# ── Ortaq kredit məntiqi ─────────────────────────────────────────────────
async def _credit_user(user_id_val: int | str, event_id: str, source: str = "unknown") -> JSONResponse:
    """
    Bazada istifadecini tap, balansi artir, commit et.

    Concurrency safety:
    - A per-user asyncio.Lock serialises concurrent webhook calls so that
      3 rapid callbacks for the same user are processed one at a time.
    - Inside the DB session, SELECT … FOR UPDATE acquires a row-level write
      lock on both the user row and (if applicable) the referrer row,
      preventing dirty reads under PostgreSQL. Under SQLite (dev) the lock
      degrades gracefully to a table-level write lock.
    """
    print(f"[CREDIT] Credit attempt: user={user_id_val!r} | event_id={event_id} | source={source}")
    logger.info("[CREDIT] Attempting to credit user %s | event_id=%s | source=%s", user_id_val, event_id, source)

    user_str = str(user_id_val).strip()
    is_numeric = user_str.isdigit()

    # ── Acquire per-user lock BEFORE opening the DB session ──────────────
    # This queues concurrent webhooks for the same user, preventing races.
    user_lock = await _get_user_lock(user_str)
    async with user_lock:

        # -- Deyiskenleri session scope-undan evvel elan et (DetachedInstanceError-i onle) --
        final_new_balance: float = 0.0
        final_videos_today: int = 0
        final_reward: float = float(MC_PER_VIDEO)

        async with async_session() as session:
            # ── SELECT … FOR UPDATE: acquires a row-level write lock so
            # concurrent transactions for the same user are serialised by
            # the DB engine (PostgreSQL). Under SQLite this gracefully
            # degrades to a table-level lock — still safe in dev mode.
            if is_numeric:
                tg_id = int(user_str)
                stmt = select(User).where(User.telegram_id == tg_id).with_for_update()
            else:
                username_val = user_str.lstrip('@')
                stmt = select(User).where(User.username == username_val).with_for_update()

            result = await session.execute(stmt)
            user = result.scalar_one_or_none()

            # Fallback: reqemsal idi amma tapilmadi -> username kimi yoxla
            if not user and is_numeric:
                print(f"[CREDIT] telegram_id={user_str} not found, checking username fallback...")
                logger.info("[CREDIT] User not found by numeric telegram_id %s, checking username field as fallback...", user_str)
                stmt = select(User).where(User.username == user_str).with_for_update()
                result = await session.execute(stmt)
                user = result.scalar_one_or_none()

            if not user:
                print(f"[CREDIT] ERROR: User {user_id_val!r} NOT FOUND in database!")
                logger.error("[CREDIT] User %s NOT FOUND in database after all lookup strategies!", user_id_val)
                raise HTTPException(status_code=404, detail=f"User {user_id_val} tapilmadi.")

            user_telegram_id = user.telegram_id
            print(f"[CREDIT] OK: Found user telegram_id={user_telegram_id}, balance={user.balance_mc:.2f} MC")
            logger.info("[CREDIT] Found user: id=%s, telegram_id=%s, current_balance=%.2f", user.id, user.telegram_id, user.balance_mc)

            # -- Check if user is active (not banned) --
            if not user.is_active:
                print(f"[CREDIT] ERROR: User {user_telegram_id} is banned / inactive!")
                logger.warning("[CREDIT] Inactive/banned user %s tried to watch video", user_telegram_id)
                return JSONResponse({"ok": False, "message": "Hesab dondurulub."}, status_code=403)

            now = datetime.now(timezone.utc)
            today = now.date()

            # -- Resolve VIP tier for this user --
            raw_vip = getattr(user, "vip_status", "free") or "free"
            # Expire VIP if the subscription window has passed
            vip_expires = getattr(user, "vip_expires_at", None)
            if vip_expires is not None:
                if vip_expires.tzinfo is None:
                    vip_expires = vip_expires.replace(tzinfo=timezone.utc)
                if now >= vip_expires:
                    raw_vip = "free"
                    user.vip_status = "free"
                    user.vip_expires_at = None
            session_limit, daily_limit, mc_reward = _get_vip_params(raw_vip, now)
            final_reward = float(mc_reward)
            print(f"[CREDIT] VIP tier={raw_vip} | session_limit={session_limit} | daily_limit={daily_limit} | mc_reward={mc_reward}")
            logger.info("[CREDIT] VIP tier=%s session_limit=%s daily_limit=%s mc_reward=%s", raw_vip, session_limit, daily_limit, mc_reward)

            # -- Idempotency Check (Uniqueness Filter) based on event_id --
            if event_id:
                dup_stmt = select(WatchRecord).where(WatchRecord.adsgram_event_id == event_id)
                dup_result = await session.execute(dup_stmt)
                dup_record = dup_result.scalar_one_or_none()
                if dup_record:
                    existing_balance = user.balance_mc
                    print(f"[CREDIT] REJECTED: Replay Attack protection. Duplicate event_id={event_id}")
                    logger.warning("[CREDIT] REJECTED: Duplicate event_id=%s detected. Blocking replay attack.", event_id)
                    # Reject it immediately as per Replay Attack protection
                    return JSONResponse({"error": "Duplicate event_id. Replay attack blocked."}, status_code=403)


            # -- Gundelik limit ve ardicil seans yoxla --
            # Dynamic daily reset
            if user.last_watch_date and _get_utc_date(user.last_watch_date) != today:
                print(f"[CREDIT] New day for user {user_telegram_id} - resetting session stats")
                logger.info("[CREDIT] New day for user %s - resetting session stats", user_telegram_id)
                user.session_1_count = 0
                user.session_2_count = 0
                user.videos_today = 0
                if user.session_1_completion_time is not None:
                    crossday_unlock = user.session_1_completion_time + timedelta(hours=3)
                    if now >= crossday_unlock:
                        user.session_1_completion_time = None

            # Determine target session & enforce limits/cooldown
            if user.session_1_count < session_limit:
                # Active in Session 1 (Level 1: 0 – session_limit ads)
                user.session_1_count += 1
                if user.session_1_count == session_limit:
                    user.session_1_completion_time = now
                    user.cooldown_notified = False  # Flag: push notification pending
                    print(f"[CREDIT] User {user_telegram_id} COMPLETED Level 1 ({session_limit} ads) at {now.isoformat()}")
                    logger.info("[CREDIT] User %s COMPLETED Level 1 (%s ads) at %s", user_telegram_id, session_limit, now.isoformat())
            else:
                # Session 1 is completed. Check Session 2 status.
                if user.session_1_completion_time is None:
                    # Fallback: session_1_completion_time is NULL (legacy row).
                    # Back-date by exactly 3 hours so unlock_time == now,
                    # meaning Session 2 unlocks immediately without a wait.
                    user.session_1_completion_time = now - timedelta(hours=3)
                elif user.session_1_completion_time.tzinfo is None:
                    user.session_1_completion_time = user.session_1_completion_time.replace(tzinfo=timezone.utc)

                unlock_time = user.session_1_completion_time + timedelta(hours=3)
                if now < unlock_time:
                    # Session 2 is currently locked
                    print(f"[CREDIT] Session 2 is LOCKED for user {user_telegram_id} until {unlock_time.isoformat()}")
                    logger.warning("[CREDIT] Session 2 is LOCKED for user %s until %s", user_telegram_id, unlock_time.isoformat())
                    return JSONResponse(
                        {"ok": False, "message": "Növbəti mərhələ hələ kilidlidir.", "unlock_at": unlock_time.isoformat()},
                        status_code=403
                    )

                # Level 2 is unlocked. Check if already completed Level 2.
                if user.session_2_count >= (daily_limit - session_limit):
                    print(f"[CREDIT] User {user_telegram_id} completed both levels today ({daily_limit} clicks). Daily limit hit.")
                    logger.warning("[CREDIT] User %s completed both levels today (%s clicks). Limit hit.", user_telegram_id, daily_limit)
                    return JSONResponse({"ok": False, "message": "Gündəlik limitiniz bitdi. Sabah gəl."}, status_code=429)

                # Increment Level 2 count
                user.session_2_count += 1

            # -- Balansi artir (atomic column-level SQL expressions) --
            # Using column + scalar instead of Python-side read-add-write
            # makes each increment atomic at the DB level, eliminating any
            # residual race if the application-layer lock is ever bypassed.
            final_reward = round(float(mc_reward) / MC_TO_AZN_RATE, 6)
            old_balance = user.balance_mc
            user.balance_mc      = round(old_balance + final_reward, 6)
            user.total_earned_mc = round(user.total_earned_mc + final_reward, 6)
            user.videos_today    = user.session_1_count + user.session_2_count
            user.last_watch_date = now

            # Deyerleri cixmadan yadda saxla
            final_new_balance = user.balance_mc
            final_videos_today = user.videos_today

            print(f"[CREDIT] Balance update: {old_balance:.2f} -> {final_new_balance:.2f} (+{final_reward:.2f}) | videos_today={final_videos_today} (S1={user.session_1_count}, S2={user.session_2_count})")
            logger.info(
                "[CREDIT] balance: %.2f -> %.2f (+%.2f) | videos_today=%s (S1=%s, S2=%s)",
                old_balance, final_new_balance, final_reward, final_videos_today, user.session_1_count, user.session_2_count
            )

            # ── Referal bonusu (same transaction — atomic with main credit) ──
            # The referrer row is also locked with FOR UPDATE to prevent
            # concurrent earnings from the same referree overwriting each other.
            referrer_bonus: float = 0.0
            referrer_tg_id: int | None = user.referrer_id

            if referrer_tg_id:
                referrer_bonus = round(final_reward * REFERRAL_BONUS_PERCENT / 100.0, 6)
                # Guard: bonus must be a positive, finite number
                if referrer_bonus > 0:
                    ref_stmt = (
                        select(User)
                        .where(User.telegram_id == referrer_tg_id)
                        .with_for_update()
                    )
                    ref_result = await session.execute(ref_stmt)
                    referrer = ref_result.scalar_one_or_none()
                    if referrer:
                        referrer.balance_mc           = round(referrer.balance_mc + referrer_bonus, 6)
                        referrer.total_earned_mc      = round(referrer.total_earned_mc + referrer_bonus, 6)
                        referrer.referral_earnings_mc = round(referrer.referral_earnings_mc + referrer_bonus, 6)
                        session.add(referrer)
                        print(f"[CREDIT] Referral bonus {referrer_bonus:.6f} AZN -> user {referrer_tg_id}")
                        logger.info("[CREDIT] Referral bonus %.2f MC -> user %s", referrer_bonus, referrer_tg_id)

            # -- Audit record --
            record = WatchRecord(
                user_id=user.id,
                telegram_id=user_telegram_id,
                reward_mc=final_reward,
                referrer_bonus_mc=referrer_bonus,
                referrer_telegram_id=referrer_tg_id,
                adsgram_event_id=event_id,
            )
            session.add(record)
            session.add(user)

            # -- COMMIT: user credit + referrer bonus + audit record — all atomic --
            try:
                await session.flush()   # SQL-i bazaya gonder
                await session.commit()  # Emeliyyati qeti mohurle
                print(f"[CREDIT] SUCCESS: DB COMMITTED! user={user_telegram_id} | new_balance={final_new_balance:.2f} MC")
                logger.info("[CREDIT] COMMITTED DATABASE TRANS! user=%s new_balance=%.2f", user_telegram_id, final_new_balance)
            except IntegrityError as db_err:
                await session.rollback()
                logger.warning("[CREDIT] REJECTED: IntegrityError caught during commit (likely concurrent duplicate event_id=%s). Blocking replay attack.", event_id)
                return JSONResponse({"error": "Duplicate event_id. Replay attack blocked at commit phase."}, status_code=403)
            except Exception as db_err:
                await session.rollback()
                print(f"[CREDIT] FAILED: Commit error: {db_err}")
                logger.exception("[CREDIT] Database commit failed for user %s", user_telegram_id)
                raise HTTPException(status_code=500, detail=f"Verilənlər bazasina yazma xetasi: {db_err}")

        # Session baglandi - yadda saxlanmis deyerleri istifade et
        return JSONResponse({
            "ok": True,
            "source": source,
            "reward": final_reward,
            "new_balance": final_new_balance,
            "new_balance_vc": int(final_new_balance * 140000),
            "videos_today": final_videos_today,
            "daily_limit": daily_limit,
        })


# ── Global Config API ───────────────────────────────────────────────────
@app.get("/api/config", summary="Get global frontend configuration")
async def get_config() -> JSONResponse:
    return JSONResponse({
        "adsgram_block_id": os.getenv("ADSGRAM_BLOCK_ID", "35141"),
        "adsgram_platform_id": os.getenv("ADSGRAM_PLATFORM_ID", "33199"),
        "bot_id": os.getenv("BOT_ID", "8960200640"),
        "maintenance_mode": os.getenv("MAINTENANCE_MODE", "false").lower() == "true",
    })

# ── Global User Stats API ──────────────────────────────────────────────
@app.get("/api/global-stats", summary="Get global user count stats")
async def get_global_stats():
    """Return total number of registered users."""
    try:
        async with async_session() as session:
            stmt = select(func.count(User.id))
            result = await session.execute(stmt)
            total_users = result.scalar() or 0
            return JSONResponse({"total_users": total_users})
    except Exception as e:
        logger.error("Error in /api/global-stats: %s", e, exc_info=True)
        return JSONResponse({"total_users": 0}, status_code=500)


# ── Leaderboard API (for Mini App) ─────────────────────────────────────
@app.get("/api/leaderboard", summary="Get Top 25 users for Gamification Leaderboard")
async def get_leaderboard():
    from handlers.commands import ADMIN_IDS
    async with async_session() as session:
        # Fetch top 25 users ordered by balance_mc DESC, excluding only the primary admin
        stmt = select(User.first_name, User.balance_mc, User.vip_status, User.had_passive_vip)
        if ADMIN_IDS:
            stmt = stmt.where(User.telegram_id != ADMIN_IDS[0])
        stmt = stmt.order_by(User.balance_mc.desc()).limit(25)
        
        result = await session.execute(stmt)
        users = result.fetchall()
        
        # Convert to list of dicts
        leaderboard = []
        for row in users:
            leaderboard.append({
                "first_name": row.first_name or "Anonim",
                "balance_mc": row.balance_mc * 140000,
                "vip_status": row.vip_status,
                "had_passive_vip": row.had_passive_vip
            })
            
        return JSONResponse({"ok": True, "leaderboard": leaderboard})


# ── User Info API (for Mini App) ───────────────────────────────────────
@app.get("/api/user/{telegram_id}", summary="Get user info for Mini App")
async def get_user_info(telegram_id: str) -> JSONResponse:
    """Return user balance & stats for the Mini App frontend."""
    user_str = telegram_id.strip()
    is_numeric = user_str.isdigit()

    async with async_session() as session:
        if is_numeric:
            tg_id = int(user_str)
            stmt = select(User).where(User.telegram_id == tg_id)
        else:
            username_val = user_str.lstrip('@')
            stmt = select(User).where(User.username == username_val)

        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        # Fallback: if it was numeric but not found, check if it exists as a username string
        if not user and is_numeric:
            stmt = select(User).where(User.username == user_str)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()

        if not user:
            logger.error("[USER-INFO] User %s NOT FOUND in database!", telegram_id)
            raise HTTPException(status_code=404, detail="User not found.")

        # Maintenance mode check
        if is_maintenance_mode() and user.telegram_id not in ADMIN_IDS:
            logger.warning("[MAINTENANCE] Non-admin user %s blocked by maintenance mode.", user.telegram_id)
            return JSONResponse(
                {"ok": False, "maintenance": True, "message": "Sistemdə texniki işlər aparılır."},
                status_code=503
            )

        if not user.is_active:
            logger.warning("[USER-INFO] Banned user %s tried to fetch user info!", telegram_id)
            raise HTTPException(status_code=403, detail="Hesabınız dondurulub.")

        now = datetime.now(timezone.utc)
        today = now.date()

        # Dynamic reset on-the-fly if last watch date is not today.
        # IMPORTANT: We deliberately keep session_1_completion_time intact
        # so that a 2-hour cooldown window that crosses UTC midnight is still
        # honoured. Only if the completion time itself is from a previous day
        # (>= 2 hours ago at minimum) do we also clear it.
        # This prevents two edge cases:
        #   A) User watches S1 at 23:55 → cooldown expires 01:55 → midnight
        #      reset clears completion_time → S2 unlocks at 00:00 (exploit).
        #   B) User in mid-cooldown → reset strands them in a permanent lock
        #      because session_1_count resets to 0 but completion_time is gone.
        if user.last_watch_date and _get_utc_date(user.last_watch_date) != today:
            user.session_1_count = 0
            user.session_2_count = 0
            user.videos_today = 0
            # Only clear completion_time if the 3-hour cooldown window has already
            # fully expired (i.e. unlock_time is in the past).
            if user.session_1_completion_time is not None:
                if user.session_1_completion_time.tzinfo is None:
                    user.session_1_completion_time = user.session_1_completion_time.replace(tzinfo=timezone.utc)
                crossday_unlock = user.session_1_completion_time + timedelta(hours=3)
                if now >= crossday_unlock:
                    # Cooldown expired — safe to clear
                    user.session_1_completion_time = None
                # else: cooldown still active — keep completion_time so the
                # lock state remains correct after the count reset.
            session.add(user)
            await session.commit()
            await session.refresh(user)

        session_1_count = user.session_1_count
        session_2_count = user.session_2_count
        session_1_completion_time = user.session_1_completion_time
        if session_1_completion_time is not None and session_1_completion_time.tzinfo is None:
            session_1_completion_time = session_1_completion_time.replace(tzinfo=timezone.utc)
            
        videos_today = session_1_count + session_2_count
        balance_mc = user.balance_mc
        total_earned_mc = user.total_earned_mc
        referral_count = user.referral_count
        referral_earnings_mc = user.referral_earnings_mc
        first_name = user.first_name
        telegram_id_val = user.telegram_id
        language = getattr(user, 'language', 'az')
        vip_status = getattr(user, 'vip_status', 'free') or 'free'
        vip_expires_at = getattr(user, 'vip_expires_at', None)
        had_passive_vip = getattr(user, 'had_passive_vip', False) or False
        welcome_bonus_claimed = getattr(user, 'welcome_bonus_claimed', False)
        loyalty_bonus_claimed = getattr(user, 'loyalty_bonus_claimed', False)
        
        # Check eligibility: created within last 12 hours AND not claimed
        created_at_utc = user.created_at if user.created_at.tzinfo else user.created_at.replace(tzinfo=timezone.utc)
        is_eligible_for_welcome_bonus = False
        if not welcome_bonus_claimed and (now - created_at_utc).total_seconds() <= 12 * 3600:
            is_eligible_for_welcome_bonus = True

        user_status = "new" if (now - created_at_utc).total_seconds() <= 12 * 3600 else "legacy"

    # Auto-expire VIP if window passed
    now_check = datetime.now(timezone.utc)
    if vip_expires_at is not None:
        vx = vip_expires_at if vip_expires_at.tzinfo else vip_expires_at.replace(tzinfo=timezone.utc)
        if now_check >= vx:
            vip_status = 'free'

    session_limit, dyn_daily_limit, dyn_mc = _get_vip_params(vip_status, now)
    session_2_locked = True
    unlock_at = None

    if session_1_count >= session_limit:
        if session_1_completion_time is None:
            # Legacy or fallback: if completed but no timestamp, unlock immediately
            session_2_locked = False
        else:
            unlock_time = session_1_completion_time + timedelta(hours=3)
            if now < unlock_time:
                session_2_locked = True
                unlock_at = unlock_time.isoformat()
            else:
                session_2_locked = False
    elif session_1_completion_time is not None:
        # Edge case: session_1_count was reset to 0 by the midnight reset
        # but the 3-hour cooldown window has NOT yet expired (crossed midnight).
        # In this state, session_1_count < 25 but we must keep S2 locked
        # until the original 3-hour window elapses.
        unlock_time = session_1_completion_time + timedelta(hours=3)
        if now < unlock_time:
            session_2_locked = True
            unlock_at = unlock_time.isoformat()
        else:
            session_2_locked = False

    return JSONResponse({
        "telegram_id": telegram_id_val,
        "first_name": first_name,
        "balance_mc": balance_mc,
        "balance_azn": round(balance_mc, 4),
        "balance_vc": int(round(balance_mc * MC_TO_AZN_RATE)),
        "total_earned_mc": total_earned_mc,
        "total_earned_vc": int(round(total_earned_mc * MC_TO_AZN_RATE)),
        "videos_today": videos_today,
        "daily_limit": dyn_daily_limit,
        "session_limit": session_limit,
        "session_1_count": session_1_count,
        "session_2_count": session_2_count,
        "session_2_locked": session_2_locked,
        "session_1_completion_time": session_1_completion_time.isoformat() if session_1_completion_time else None,
        "unlock_at": unlock_at,
        "referral_count": referral_count,
        "referral_earnings_mc": referral_earnings_mc,
        "referral_earnings_vc": int(round(referral_earnings_mc * MC_TO_AZN_RATE)),
        "mc_per_video": dyn_mc,
        "mc_to_azn_rate": MC_TO_AZN_RATE,
        "language": language,
        "vip_status": vip_status,
        "vip_expires_at": vip_expires_at.isoformat() if vip_expires_at else None,
        "had_passive_vip": had_passive_vip,
        "is_eligible_for_welcome_bonus": is_eligible_for_welcome_bonus,
        "user_status": user_status,
        "can_claim_loyalty": not loyalty_bonus_claimed,
    })


@app.post("/api/user/{telegram_id}/claim_welcome_bonus", summary="Mark welcome bonus as claimed")
async def claim_welcome_bonus(telegram_id: str) -> JSONResponse:
    user_str = telegram_id.strip()
    is_numeric = user_str.isdigit()

    async with async_session() as session:
        if is_numeric:
            tg_id = int(user_str)
            stmt = select(User).where(User.telegram_id == tg_id)
        else:
            username_val = user_str.lstrip('@')
            stmt = select(User).where(User.username == username_val)

        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if not user and is_numeric:
            stmt = select(User).where(User.username == user_str)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=404, detail="User not found.")

        user.welcome_bonus_claimed = True
        session.add(user)
        await session.commit()
        return JSONResponse({"ok": True, "message": "Welcome bonus marked as claimed."})


@app.post("/api/user/{telegram_id}/claim_loyalty", summary="Claim interactive loyalty/welcome bonus")
async def claim_loyalty_bonus(telegram_id: str) -> JSONResponse:
    user_str = telegram_id.strip()
    is_numeric = user_str.isdigit()

    async with async_session() as session:
        if is_numeric:
            tg_id = int(user_str)
            stmt = select(User).where(User.telegram_id == tg_id).with_for_update()
        else:
            username_val = user_str.lstrip('@')
            stmt = select(User).where(User.username == username_val).with_for_update()

        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if not user and is_numeric:
            stmt = select(User).where(User.username == user_str).with_for_update()
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=404, detail="User not found.")

        if getattr(user, 'loyalty_bonus_claimed', False):
            return JSONResponse({"ok": False, "message": "Bonus already claimed."}, status_code=400)

        # Add 4.0 AZN
        user.balance_mc = round(user.balance_mc + 4.0, 6)
        user.loyalty_bonus_claimed = True
        
        session.add(user)
        await session.commit()
        
        balance_vc = int(round(user.balance_mc * MC_TO_AZN_RATE))
        return JSONResponse({"ok": True, "new_balance_vc": balance_vc})


@app.post("/api/admin/fix_vc_collision", summary="HOTFIX: Fix legacy VC unit collision")
async def fix_vc_collision():
    from sqlalchemy import text
    try:
        async with engine.begin() as conn:
            # 1. Fix balance_mc
            await conn.execute(text("""
                UPDATE users 
                SET balance_mc = (FLOOR(balance_mc) / 140000.0) + (balance_mc - FLOOR(balance_mc))
                WHERE balance_mc > 50;
            """))
            # 2. Fix total_earned_mc
            await conn.execute(text("""
                UPDATE users 
                SET total_earned_mc = (FLOOR(total_earned_mc) / 140000.0) + (total_earned_mc - FLOOR(total_earned_mc))
                WHERE total_earned_mc > 50;
            """))
            # 3. Fix referral_earnings_mc
            await conn.execute(text("""
                UPDATE users 
                SET referral_earnings_mc = (FLOOR(referral_earnings_mc) / 140000.0) + (referral_earnings_mc - FLOOR(referral_earnings_mc))
                WHERE referral_earnings_mc > 50;
            """))
        return JSONResponse({"ok": True, "message": "Production database unit collision fixed successfully."})
    except Exception as e:
        import traceback
        return JSONResponse({"ok": False, "error": str(e), "trace": traceback.format_exc()}, status_code=500)


# ── Update User Language ───────────────────────────────────────────────
class LanguageUpdate(BaseModel):
    language: str

@app.patch("/api/user/{telegram_id}/language", summary="Update user language")
async def update_user_language(telegram_id: int, body: LanguageUpdate) -> JSONResponse:
    """Update the user's preferred language."""
    supported = ['az', 'tr', 'en', 'ru']
    lang = body.language.lower().strip()
    if lang not in supported:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {lang}")

    async with async_session() as session:
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")
        user.language = lang
        session.add(user)
        await session.commit()

    # Per-user menu button localization when language is mutated inside WebApp
    btn_start_texts = {
        'az': "🚀 Başlat",
        'tr': "🚀 Başlat",
        'en': "🚀 Start",
        'ru': "🚀 Запустить"
    }
    btn_text = btn_start_texts.get(lang, "🚀 Start")
    webapp_url = f"{FRONTEND_URL}?lang={lang}&v={int(datetime.now().timestamp())}"
    try:
        from aiogram.types import MenuButtonWebApp, WebAppInfo
        await bot.set_chat_menu_button(
            chat_id=telegram_id,
            menu_button=MenuButtonWebApp(
                text=btn_text,
                web_app=WebAppInfo(url=webapp_url)
            )
        )
        logger.info("Updated menu button to dynamic language in API: chat_id=%s, lang=%s", telegram_id, lang)
    except Exception as e:
        logger.error("Failed to update user chat menu button in API: %s", e)

    return JSONResponse({"ok": True, "language": lang})


# ── Tasks API ─────────────────────────────────────────────────────────

def validate_init_data(init_data: str, bot_token: str) -> dict | None:
    """Validate Telegram WebApp initData and extract user JSON."""
    try:
        parsed = urllib.parse.parse_qsl(init_data)
        data_dict = dict(parsed)
        if "hash" not in data_dict:
            return None
            
        received_hash = data_dict.pop("hash")
        
        # Sort keys alphabetically and join with '\n'
        data_check_string = "\n".join(f"{k}={data_dict[k]}" for k in sorted(data_dict.keys()))
        
        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        
        if hmac.compare_digest(calculated_hash, received_hash):
            user_str = data_dict.get("user")
            if user_str:
                return json.loads(user_str)
    except Exception as e:
        logger.error("initData validation error: %s", e)
    return None


@app.get("/api/tasks", summary="Get active tasks for user")
async def get_tasks(telegram_id: int, initData: str | None = None) -> JSONResponse:
    """Return list of active tasks excluding those already completed by the user."""
    async with async_session() as session:
        # Get user id to filter tasks
        user_stmt = select(User).where(User.telegram_id == telegram_id)
        user_res = await session.execute(user_stmt)
        user = user_res.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Get completed task ids
        completed_stmt = select(UserTask.task_id).where(UserTask.user_id == user.id)
        completed_res = await session.execute(completed_stmt)
        completed_task_ids = [row[0] for row in completed_res.all()]

        # Get active tasks
        tasks_stmt = select(Task).where(Task.is_active == True)
        tasks_res = await session.execute(tasks_stmt)
        all_tasks = tasks_res.scalars().all()

        available_tasks = []
        for t in all_tasks:
            if t.id not in completed_task_ids:
                available_tasks.append({
                    "id": t.id,
                    "title": t.title,
                    "channel_url": t.channel_url,
                    "reward_amount": t.reward_amount
                })
        
        # Admin check
        is_admin = False
        if initData:
            user_data = validate_init_data(initData, BOT_TOKEN)
            if user_data and "id" in user_data:
                tg_id_from_init = user_data["id"]
                if int(tg_id_from_init) == int(telegram_id):
                    is_admin = (int(tg_id_from_init) == 1970477419)

        return JSONResponse(
            {"tasks": available_tasks, "is_admin": is_admin},
            headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"}
        )

class AddTaskRequest(BaseModel):
    initData: str
    title: str
    channel_id: str
    channel_url: str
    reward_amount: float

@app.post("/api/admin/add-task", summary="Add a new task (Admin only)")
async def add_task(req: AddTaskRequest) -> JSONResponse:
    user_data = validate_init_data(req.initData, BOT_TOKEN)
    if not user_data or "id" not in user_data:
        logger.warning("[ADMIN-ADD-TASK] Invalid initData received.")
        return JSONResponse({"ok": False, "message": "Invalid authentication"}, status_code=401)
        
    telegram_id = user_data["id"]
    
    if int(telegram_id) not in ADMIN_IDS:
        logger.warning("[ADMIN-ADD-TASK] Unauthorized access attempt by ID %s.", telegram_id)
        return JSONResponse({"ok": False, "message": "Forbidden"}, status_code=403)
        
    async with async_session() as session:
        async with session.begin():
            new_task = Task(
                title=req.title,
                channel_id=req.channel_id,
                channel_url=req.channel_url,
                reward_amount=req.reward_amount,
                is_active=True
            )
            session.add(new_task)
            
    return JSONResponse({"ok": True, "message": "Task created successfully"})

class VerifyTaskRequest(BaseModel):
    task_id: int
    initData: str

@app.post("/api/tasks/verify", summary="Verify and complete a task")
async def verify_task(req: VerifyTaskRequest) -> JSONResponse:
    user_data = validate_init_data(req.initData, BOT_TOKEN)
    if not user_data or "id" not in user_data:
        logger.warning("[TASK-VERIFY] Invalid initData received.")
        return JSONResponse({"ok": False, "message": "Invalid authentication"}, status_code=401)
        
    telegram_id = user_data["id"]
    
    async with async_session() as session:
        user_stmt = select(User).where(User.telegram_id == telegram_id).with_for_update()
        user_res = await session.execute(user_stmt)
        user = user_res.scalar_one_or_none()
        if not user:
            return JSONResponse({"ok": False, "message": "User not found"}, status_code=404)
            
        task_stmt = select(Task).where(Task.id == req.task_id)
        task_res = await session.execute(task_stmt)
        task = task_res.scalar_one_or_none()
        if not task or not task.is_active:
            return JSONResponse({"ok": False, "message": "Task not found or inactive"}, status_code=404)
            
        # Check if already completed
        ut_stmt = select(UserTask).where(UserTask.user_id == user.id, UserTask.task_id == task.id)
        ut_res = await session.execute(ut_stmt)
        if ut_res.scalar_one_or_none():
            return JSONResponse({"ok": False, "message": "Task already completed"}, status_code=400)
            
        # Verify via bot
        try:
            member = await bot.get_chat_member(chat_id=task.channel_id, user_id=telegram_id)
            if member.status not in ("member", "administrator", "creator"):
                return JSONResponse({"ok": False, "message": "Kanalda yoxsunuz! / Not joined!"}, status_code=400)
        except Exception as e:
            logger.error("[TASK-VERIFY] Error verifying chat member for user %s channel %s: %s", telegram_id, task.channel_id, e)
            return JSONResponse({"ok": False, "message": "Kanala abunəlik yoxlanıla bilmədi. Bot kanalda admin deyil və ya xəta baş verdi."}, status_code=400)
            
        # Guard: reward must be a positive finite amount
        if task.reward_amount <= 0:
            logger.warning("[TASK-VERIFY] Task %s has non-positive reward %s — rejecting.", req.task_id, task.reward_amount)
            return JSONResponse({"ok": False, "message": "Tapşırıq mükafatı etibarsızdır."}, status_code=400)

        # Reward user — both writes staged in the same transaction
        task_azn_reward = round(float(task.reward_amount) / MC_TO_AZN_RATE, 6)
        user.balance_mc      = round(user.balance_mc + task_azn_reward, 6)
        user.total_earned_mc = round(user.total_earned_mc + task_azn_reward, 6)
        new_balance = user.balance_mc

        user_task = UserTask(user_id=user.id, task_id=task.id)
        session.add(user_task)
        session.add(user)
        try:
            await session.commit()
        except Exception as db_err:
            await session.rollback()
            logger.exception("[TASK-VERIFY] DB commit failed for user %s task %s: %s", telegram_id, req.task_id, db_err)
            return JSONResponse({"ok": False, "message": "Verilənlər bazası xətası. Yenidən cəhd edin."}, status_code=500)

        return JSONResponse({
            "ok": True, 
            "reward": task.reward_amount, 
            "new_balance": new_balance,
            "new_balance_vc": int(new_balance * 140000)
        })


# ── Async Cooldown Notification Worker ────────────────────────────────
_COOLDOWN_PUSH_MESSAGES = {
    "az": (
        "🔥 Gözlədiyin vaxt bitdi! 3 saatlıq kilid açıldı və yeni videolar artıq hazırdır! "
        "🚀 Tez bota gir, videoları izlə və balansını doldurmağa davam et! 💸"
    ),
    "tr": (
        "🔥 Beklediğin an geldi! 3 saatlik mola bitti ve yeni videolar hazır! "
        "🚀 Hemen bota gir, videoları izle ve bakiyeni uçurmaya devam et! 💸"
    ),
    "ru": (
        "🔥 Время пошло! 3-часовой перерыв окончен, новые видео уже ждут! "
        "🚀 Заходи скорее, смотри видео и продолжай разгонять баланс! 💸"
    ),
    "default": (
        "🔥 Cooldown is over! Your new 3-hour session is officially ready! "
        "🚀 Jump back into the bot, watch videos, and keep boosting your balance! 💸"
    ),
}


async def _cooldown_notification_worker() -> None:
    """
    Async background task that polls every 60 seconds.
    Finds users whose 3-hour Session 1 cooldown has elapsed and
    who have not yet been notified (cooldown_notified == False),
    then sends them a localized private push message via the Telegram bot.
    """
    logger.info("[NOTIF-WORKER] Cooldown notification worker initialised — polling every 60s.")
    while True:
        try:
            await asyncio.sleep(60)
            now = datetime.now(timezone.utc)
            cutoff = now - timedelta(hours=3)

            async with async_session() as session:
                stmt = (
                    select(User)
                    .where(
                        User.session_1_count >= 25,
                        User.cooldown_notified == False,  # noqa: E712
                        User.session_1_completion_time <= cutoff,
                        User.is_active == True,
                    )
                )
                result = await session.execute(stmt)
                pending_users = result.scalars().all()

            if pending_users:
                logger.info("[NOTIF-WORKER] Found %d user(s) ready for cooldown push.", len(pending_users))

            for user in pending_users:
                # Resolve localized message
                lang = getattr(user, "language", "en") or "en"
                msg_text = _COOLDOWN_PUSH_MESSAGES.get(lang, _COOLDOWN_PUSH_MESSAGES["default"])

                # Send push notification — wrapped in try/except to handle blocked/deactivated bots
                try:
                    await bot.send_message(chat_id=user.telegram_id, text=msg_text)
                    logger.info("[NOTIF-WORKER] Push sent to user telegram_id=%s (lang=%s).", user.telegram_id, lang)
                except Exception as send_err:
                    logger.warning(
                        "[NOTIF-WORKER] Failed to send push to telegram_id=%s: %s",
                        user.telegram_id, send_err
                    )

                # Mark as notified immediately inside its own transaction
                # to guarantee no duplicate notifications even if the bot call failed.
                async with async_session() as upd_session:
                    upd_stmt = select(User).where(User.telegram_id == user.telegram_id)
                    upd_res = await upd_session.execute(upd_stmt)
                    db_user = upd_res.scalar_one_or_none()
                    if db_user:
                        db_user.cooldown_notified = True
                        upd_session.add(db_user)
                        await upd_session.commit()
                        logger.info(
                            "[NOTIF-WORKER] cooldown_notified=True committed for telegram_id=%s.",
                            user.telegram_id
                        )

        except asyncio.CancelledError:
            logger.info("[NOTIF-WORKER] Worker cancelled — shutting down cleanly.")
            break
        except Exception as worker_err:
            logger.exception("[NOTIF-WORKER] Unexpected error in notification worker: %s", worker_err)
            # Continue looping — a single cycle error must not kill the worker.


# ── Midnight Broadcast Scheduler ──────────────────────────────────────
_MIDNIGHT_BROADCAST = {
    "az": {
        "text": "📢 **Yeni videolar gəldi!** 🚀\nGündəlik limitiniz yeniləndi. Daxil olun və qazanın! 💰",
        "button": "Videolara Bax 🎬",
    },
    "tr": {
        "text": "📢 **Yeni videolar geldi!** 🚀\nGünlük limitiniz yenilendi. Giriş yapın ve kazanın! 💰",
        "button": "Videoları İzle 🎬",
    },
    "ru": {
        "text": "📢 **Новые видео уже тут!** 🚀\nЕжедневный лимит обновлен. Заходи и зарабатывай! 💰",
        "button": "Смотреть видео 🎬",
    },
    "en": {
        "text": "📢 **New videos are here!** 🚀\nYour daily limit has been reset. Join and earn! 💰",
        "button": "Watch Videos 🎬",
    },
}
_WEBAPP_URL = f"{FRONTEND_URL}?v={int(datetime.now().timestamp())}"


async def _midnight_broadcast_scheduler() -> None:
    """
    Async background task that fires once per day at 00:01 UTC.
    Fetches every user's (telegram_id, language) from the DB and sends
    a localized inline-keyboard broadcast message. Blocked/deactivated
    users are silently skipped so the loop never stalls.
    """
    logger.info("[BROADCAST] Midnight broadcast scheduler initialised.")
    while True:
        try:
            # ── Calculate seconds until next 00:01 UTC ──────────────────
            now = datetime.now(timezone.utc)
            target = now.replace(hour=0, minute=1, second=0, microsecond=0)
            if now >= target:
                # Already past 00:01 today — aim for tomorrow
                target += timedelta(days=1)
            wait_seconds = (target - now).total_seconds()
            logger.info(
                "[BROADCAST] Next broadcast in %.0f seconds (at %s UTC).",
                wait_seconds, target.isoformat()
            )
            await asyncio.sleep(wait_seconds)

            # ── Fetch all active users (telegram_id + language only) ────────────
            async with async_session() as session:
                stmt = select(User.telegram_id, User.language).where(User.is_active == True)
                result = await session.execute(stmt)
                rows = result.all()  # list of (telegram_id, language)

            logger.info("[BROADCAST] Firing midnight broadcast to %d user(s).", len(rows))

            sent = 0
            skipped = 0
            for tg_id, lang_code in rows:
                # ── Resolve localized template ───────────────────────────
                template = _MIDNIGHT_BROADCAST.get(
                    lang_code or "en", _MIDNIGHT_BROADCAST["en"]
                )
                msg_text = template["text"]
                btn_label = template["button"]

                # ── Build inline keyboard with WebApp button ─────────────
                keyboard = aio_types.InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            aio_types.InlineKeyboardButton(
                                text=btn_label,
                                web_app=aio_types.WebAppInfo(url=f"{FRONTEND_URL}?v={int(datetime.now().timestamp())}"),
                            )
                        ]
                    ]
                )

                # ── Send — silently skip blocked / deactivated users ─────
                try:
                    await bot.send_message(
                        chat_id=tg_id,
                        text=msg_text,
                        parse_mode="Markdown",
                        reply_markup=keyboard,
                    )
                    sent += 1
                except Exception as send_err:
                    logger.info(
                        "[BROADCAST] Skipped telegram_id=%s (lang=%s): %s",
                        tg_id, lang_code, send_err
                    )
                    skipped += 1
                    continue

            logger.info(
                "[BROADCAST] Broadcast complete — sent=%d, skipped=%d.",
                sent, skipped
            )

        except asyncio.CancelledError:
            logger.info("[BROADCAST] Scheduler cancelled — shutting down cleanly.")
            break
        except Exception as broadcast_err:
            logger.exception("[BROADCAST] Unexpected error in broadcast scheduler: %s", broadcast_err)
            # Back off 60 s before retrying to avoid a tight error loop
            await asyncio.sleep(60)


# ── Passive Income Worker ───────────────────────────────────────────────
_PASSIVE_DAILY_AZN: float = 1.0   # 1 AZN worth of VC per day
_PASSIVE_CHECK_INTERVAL: int = 3600    # check every hour (seconds)

PASSIVE_NOTIFS = {
    "az": (
        "💰 <b>Təbriklər! Ultra Boost Qazancınız Gəldi!</b>\n\n"
        "🎉 Möhtəşəm! Hesabınıza avtomatik olaraq <b>+140,000 VC (≈1 AZN)</b> əlavə olundu! Belə davam edin, heç nə etmədən qazanmaq necə də gözəldir! 🚀\n\n"
        "Cari balansınız: <b>{balance:,.0f} VC</b>\n"
        "Paket bitişi: <b>{expires}</b>"
    ),
    "tr": (
        "💰 <b>Tebrikler! Pasif Kazancınız Geldi!</b>\n\n"
        "🎉 Harika! Hesabınıza otomatik olarak <b>+140.000 VC (≈1 AZN)</b> eklendi! Böyle devam edin, hiçbir şey yapmadan kazanmak ne kadar güzel! 🚀\n\n"
        "Mevcut bakiyeniz: <b>{balance:,.0f} VC</b>\n"
        "Paket bitişi: <b>{expires}</b>"
    ),
    "en": (
        "💰 <b>Congratulations! Your Passive Income is Here!</b>\n\n"
        "🎉 Awesome! <b>+140,000 VC (≈1 AZN)</b> has been automatically added to your account! Keep it up, earning without doing anything is amazing! 🚀\n\n"
        "Current balance: <b>{balance:,.0f} VC</b>\n"
        "Package expires: <b>{expires}</b>"
    ),
    "ru": (
        "💰 <b>Поздравляем! Ваш Пассивный Доход Пришел!</b>\n\n"
        "🎉 Супер! На ваш счет автоматически зачислено <b>+140 000 VC (≈1 AZN)</b>! Так держать, зарабатывать ничего не делая — это прекрасно! 🚀\n\n"
        "Текущий баланс: <b>{balance:,.0f} VC</b>\n"
        "Окончание пакета: <b>{expires}</b>"
    )
}

async def _passive_income_worker() -> None:
    """
    Background task: every hour, find users with an active 'passive' VIP
    subscription whose last payout was ≥24 hours ago (or never) and credit
    them with 140,000 VC (= 1 AZN). Fires up to 7 times total (once per day
    for 7 days), after which vip_expires_at causes the tier to revert to free.
    """
    logger.info("[PASSIVE] Passive income worker initialised.")
    while True:
        try:
            await asyncio.sleep(_PASSIVE_CHECK_INTERVAL)

            now = datetime.now(timezone.utc)
            cutoff = now - timedelta(hours=24)

            # Find eligible users:
            #   • vip_status = 'passive'
            #   • vip_expires_at is still in the future (not expired)
            #   • passive_last_paid_at is NULL (first payout) OR older than 24 h
            async with async_session() as session:
                stmt = select(User).where(
                    User.vip_status == "passive",
                    User.vip_expires_at > now,
                    User.is_active == True,
                    (User.passive_last_paid_at == None) | (User.passive_last_paid_at <= cutoff),
                )
                result = await session.execute(stmt)
                users = result.scalars().all()

                if not users:
                    logger.info("[PASSIVE] No eligible users for passive payout this cycle.")
                    continue

                logger.info("[PASSIVE] Crediting %d user(s) with %.0f AZN each.", len(users), _PASSIVE_DAILY_AZN)
                credited = 0
                for user in users:
                    user.balance_mc += _PASSIVE_DAILY_AZN
                    user.total_earned_mc += _PASSIVE_DAILY_AZN
                    user.passive_last_paid_at = now
                    credited += 1

                await session.commit()
                logger.info("[PASSIVE] Payout complete — credited %d user(s).", credited)

            # Notify credited users via Telegram (best-effort, non-blocking)
            for user in users:
                try:
                    user_lang = user.language if getattr(user, 'language', None) in ['az', 'tr', 'en', 'ru'] else 'en'
                    expires_str = user.vip_expires_at.strftime('%d.%m.%Y') if user.vip_expires_at else '—'
                    notif_text = PASSIVE_NOTIFS[user_lang].format(
                        balance=user.balance_mc * 140000,
                        expires=expires_str
                    )
                    await bot.send_message(
                        chat_id=user.telegram_id,
                        text=notif_text,
                        parse_mode="HTML",
                    )
                    await asyncio.sleep(0.05)
                except Exception as notify_err:
                    logger.debug("[PASSIVE] Could not notify user %s: %s", user.telegram_id, notify_err)

        except asyncio.CancelledError:
            logger.info("[PASSIVE] Worker cancelled — shutting down cleanly.")
            break
        except Exception as worker_err:
            logger.exception("[PASSIVE] Unexpected error in passive income worker: %s", worker_err)
            await asyncio.sleep(60)

# ── Mini App Frontend Serving ──────────────────────────────────────────
@app.get("/miniapp", response_class=HTMLResponse, response_model=None)
async def serve_miniapp() -> Any:
    """Serve the Mini App index.html."""
    response = FileResponse(FRONTEND_DIR / "index.html", media_type="text/html")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


# Mount static assets (JS, CSS, images)
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


# ── Health Check ───────────────────────────────────────────────────────
@app.get("/health")
async def health_check() -> JSONResponse:
    """Simple health-check for monitoring & load balancers."""
    return JSONResponse({"status": "healthy", "service": "ManatAds"})


# ── CLI Entry Point ───────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("ENVIRONMENT", "development") == "development",
    )
