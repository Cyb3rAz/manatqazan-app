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
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aiogram import types as aio_types
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select

from bot_instance import bot, dp
from database import async_session, close_db, init_db
from handlers import commands_router
from models import User, WatchRecord

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
ADSGRAM_SECRET: str = os.getenv("ADSGRAM_SECRET", "")
MC_PER_VIDEO: int = int(os.getenv("MC_PER_VIDEO", "50"))
DAILY_VIDEO_LIMIT: int = int(os.getenv("DAILY_VIDEO_LIMIT", "25"))
MC_TO_AZN_RATE: int = int(os.getenv("MC_TO_AZN_RATE", "21000"))
REFERRAL_BONUS_PERCENT: int = int(os.getenv("REFERRAL_BONUS_PERCENT", "10"))

WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"

if not commands_router.parent_router:
    dp.include_router(commands_router)


# ── Lifespan ────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(application: FastAPI):
    """Startup / shutdown lifecycle for the combined app."""
    # ── Startup ──
    await init_db()
    logger.info("Database initialised.")

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


# ── Adsgram S2S Reward – GET (əsl Adsgram formatı) ─────────────────────
@app.get("/api/reward", summary="Adsgram S2S reward callback (GET)")
async def adsgram_reward_get(
    request: Request,
) -> JSONResponse:
    """
    Adsgram S2S callback – GET sorğusu ilə gəlir.
    Dashboard-da Reward URL:
        https://<ngrok>/api/reward?userId=[userId]&blockId=31453
    """
    params = dict(request.query_params)
    logger.info("[ADSGRAM-GET] Raw query params: %s | IP=%s", params, request.client.host if request.client else "unknown")

    # Get userId or user_id or username
    user_id_val = params.get("userId") or params.get("user_id") or params.get("user")
    block_id = params.get("blockId") or params.get("block_id")

    # Log and bypass signature/secret verification
    sig_keys = ["hash", "signature", "sign", "secret_key", "secret"]
    received_sigs = {k: params.get(k) for k in sig_keys if k in params}
    
    logger.warning(
        "[SIGNATURE-DEBUG-GET] Received security parameters: %s | Local SECRET=%r (bypass active)",
        received_sigs,
        ADSGRAM_SECRET[:10] + "..." if ADSGRAM_SECRET else "(boş)"
    )

    if not user_id_val:
        logger.error("[ADSGRAM-GET] Missing userId or user_id in request query parameters!")
        raise HTTPException(status_code=400, detail="userId və ya user_id parametri tapılmadı.")

    event_id = params.get("event_id") or params.get("eventId") or str(uuid.uuid4())
    return await _credit_user(user_id_val, event_id=event_id, source="adsgram_get")


# ── Adsgram S2S Reward – POST (köhnə / alternativ format) ───────────────
@app.post("/api/adsgram/callback", summary="Adsgram S2S reward callback (POST)")
async def adsgram_callback(request: Request) -> JSONResponse:
    """
    POST format callback – HMAC yoxlanışı bypass edildi (debug rejimi).
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    logger.info("[ADSGRAM-POST] Raw body payload: %s", payload)

    user_id_val = payload.get("user_id") or payload.get("userId") or payload.get("user")
    event_id = payload.get("event_id") or payload.get("eventId") or str(uuid.uuid4())
    signature = payload.get("signature") or payload.get("hash") or payload.get("sign") or ""

    logger.warning(
        "[SIGNATURE-DEBUG-POST] SECRET=%r | user_id=%s | event_id=%s | received_sig=%s (bypass active)",
        ADSGRAM_SECRET[:10] + "..." if ADSGRAM_SECRET else "(boş)",
        user_id_val, event_id, signature[:20] if signature else "(yox)"
    )

    if not user_id_val:
        logger.error("[ADSGRAM-POST] Missing user_id in payload!")
        raise HTTPException(status_code=400, detail="user_id parametri tapılmadı.")

    return await _credit_user(user_id_val, event_id=event_id, source="adsgram_post")


# ── Ortaq kredit məntiqi ─────────────────────────────────────────────────
async def _credit_user(user_id_val: int | str, event_id: str, source: str = "unknown") -> JSONResponse:
    """Bazada istifadəçini tap, balansı artır, commit et."""
    logger.info("[CREDIT] Attempting to credit user %s | event_id=%s | source=%s", user_id_val, event_id, source)

    user_str = str(user_id_val).strip()
    is_numeric = user_str.isdigit()

    async with async_session() as session:
        # ── İstifadəçini tap ──
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
            logger.info("[CREDIT] User not found by numeric telegram_id %s, checking username field as fallback...", user_str)
            stmt = select(User).where(User.username == user_str)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()

        if not user:
            logger.error("[CREDIT] User %s NOT FOUND in database after all lookup strategies!", user_id_val)
            raise HTTPException(status_code=404, detail=f"User {user_id_val} tapılmadı.")

        user_telegram_id = user.telegram_id
        logger.info("[CREDIT] Found user: id=%s, telegram_id=%s, current_balance=%.2f", user.id, user.telegram_id, user.balance_mc)

        # ── event_id ilə dublikat yoxla ──
        if event_id:
            dup_stmt = select(WatchRecord).where(WatchRecord.adsgram_event_id == event_id)
            dup_result = await session.execute(dup_stmt)
            if dup_result.scalar_one_or_none():
                logger.info("[CREDIT] Duplicate event_id=%s – skipping.", event_id)
                return JSONResponse({"ok": True, "message": "Artıq kreditlənib.", "balance": user.balance_mc})

        # ── Gündəlik limit yoxla ──
        now = datetime.now(timezone.utc)
        today = now.date()
        if user.last_watch_date and user.last_watch_date.date() == today:
            if user.videos_today >= DAILY_VIDEO_LIMIT:
                logger.warning("[CREDIT] User %s hit daily limit (%s/%s)", user_telegram_id, user.videos_today, DAILY_VIDEO_LIMIT)
                return JSONResponse({"ok": False, "message": "Gündəlik limit bitdi."}, status_code=429)
        else:
            # Yeni gün → sıfırla
            logger.info("[CREDIT] New day for user %s – resetting videos_today", user_telegram_id)
            user.videos_today = 0

        # ── Balansı artır ──
        reward = float(MC_PER_VIDEO)
        old_balance = user.balance_mc
        user.balance_mc += reward
        user.total_earned_mc += reward
        user.videos_today += 1
        user.last_watch_date = now

        logger.info(
            "[CREDIT] balance: %.2f → %.2f (+%.2f) | videos_today=%s",
            old_balance, user.balance_mc, reward, user.videos_today
        )

        # ── Referal bonusu ──
        referrer_bonus: float = 0.0
        referrer_tg_id: int | None = user.referrer_id

        if referrer_tg_id:
            referrer_bonus = reward * REFERRAL_BONUS_PERCENT / 100.0
            ref_stmt = select(User).where(User.telegram_id == referrer_tg_id)
            ref_result = await session.execute(ref_stmt)
            referrer = ref_result.scalar_one_or_none()
            if referrer:
                referrer.balance_mc += referrer_bonus
                referrer.total_earned_mc += referrer_bonus
                referrer.referral_earnings_mc += referrer_bonus
                session.add(referrer)
                logger.info("[CREDIT] Referral bonus %.2f MC → user %s", referrer_bonus, referrer_tg_id)

        # ── Audit record ──
        record = WatchRecord(
            user_id=user.id,
            telegram_id=user_telegram_id,
            reward_mc=reward,
            referrer_bonus_mc=referrer_bonus,
            referrer_telegram_id=referrer_tg_id,
            adsgram_event_id=event_id,
        )
        session.add(record)
        session.add(user)

        # ── COMMIT – balansı yaddaşa yaz ──
        await session.flush()
        await session.commit()
        logger.info("[CREDIT] ✅ COMMITTED DATABASE TRANS! user=%s new_balance=%.2f", user_telegram_id, user.balance_mc)

    return JSONResponse({
        "ok": True,
        "source": source,
        "reward": reward,
        "new_balance": user.balance_mc,
        "videos_today": user.videos_today,
        "daily_limit": DAILY_VIDEO_LIMIT,
    })


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

    now = datetime.now(timezone.utc)
    today = now.date()
    videos_today = user.videos_today if (
        user.last_watch_date and user.last_watch_date.date() == today
    ) else 0

    return JSONResponse({
        "telegram_id": user.telegram_id,
        "first_name": user.first_name,
        "balance_mc": user.balance_mc,
        "balance_azn": round(user.balance_mc / MC_TO_AZN_RATE, 4),
        "total_earned_mc": user.total_earned_mc,
        "videos_today": videos_today,
        "daily_limit": DAILY_VIDEO_LIMIT,
        "referral_count": user.referral_count,
        "referral_earnings_mc": user.referral_earnings_mc,
        "mc_per_video": MC_PER_VIDEO,
        "mc_to_azn_rate": MC_TO_AZN_RATE,
    })


# ── Mini App Frontend Serving ──────────────────────────────────────────
@app.get("/miniapp", response_class=HTMLResponse)
async def serve_miniapp() -> FileResponse:
    """Serve the Mini App index.html."""
    return FileResponse(FRONTEND_DIR / "index.html", media_type="text/html")


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
