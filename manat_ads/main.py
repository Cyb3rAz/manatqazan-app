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
    allow_origins=[
        "https://manatqazan.vercel.app",
        "https://8157-212-47-146-163.ngrok-free.app",
        "http://localhost",
        "http://localhost:8000",
        "http://127.0.0.1",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Telegram Webhook Endpoint ──────────────────────────────────────────
@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request) -> JSONResponse:
    """Receive Telegram updates and feed them to Aiogram."""
    update_data: dict[str, Any] = await request.json()
    update = aio_types.Update.model_validate(update_data, context={"bot": bot})
    await dp.feed_update(bot=bot, update=update)
    return JSONResponse({"ok": True})


# ── HMAC-SHA256 Verification Helper ────────────────────────────────────
def _verify_adsgram_signature(
    user_id: str,
    event_id: str,
    received_signature: str,
) -> bool:
    """
    Verify Adsgram S2S callback authenticity.
    The signature is HMAC-SHA256( secret, "user_id:event_id" ).
    """
    if not ADSGRAM_SECRET:
        logger.warning("ADSGRAM_SECRET is not set — skipping HMAC verification.")
        return True  # Dev-mode passthrough

    message = f"{user_id}:{event_id}".encode("utf-8")
    expected = hmac.new(
        ADSGRAM_SECRET.encode("utf-8"),
        message,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, received_signature)


# ── Adsgram S2S Reward Callback ────────────────────────────────────────
class AdsgramCallbackPayload(BaseModel):
    """Pydantic model for the Adsgram S2S callback body."""
    user_id: int
    event_id: str
    signature: str
    reward: float | None = None


@app.post("/api/adsgram/callback", summary="Adsgram S2S reward callback")
async def adsgram_callback(payload: AdsgramCallbackPayload) -> JSONResponse:
    """
    Called by Adsgram's servers after a user completes a video.
    1. Verify HMAC-SHA256 signature.
    2. Credit user with MC_PER_VIDEO.
    3. Credit referrer with 10% bonus.
    """
    # ── Signature verification ──
    if not _verify_adsgram_signature(
        str(payload.user_id), payload.event_id, payload.signature
    ):
        logger.warning("Invalid HMAC signature for user %s", payload.user_id)
        raise HTTPException(status_code=403, detail="Invalid signature.")

    async with async_session() as session:
        # ── Find user ──
        stmt = select(User).where(User.telegram_id == payload.user_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=404, detail="User not found.")

        # ── Deduplicate by event_id ──
        dup_stmt = select(WatchRecord).where(WatchRecord.adsgram_event_id == payload.event_id)
        dup_result = await session.execute(dup_stmt)
        if dup_result.scalar_one_or_none():
            return JSONResponse({"ok": True, "message": "Already credited."})

        # ── Daily limit check ──
        now = datetime.now(timezone.utc)
        today = now.date()
        if user.last_watch_date and user.last_watch_date.date() == today:
            if user.videos_today >= DAILY_VIDEO_LIMIT:
                return JSONResponse(
                    {"ok": False, "message": "Daily limit reached."},
                    status_code=429,
                )
        else:
            # New day → reset counter
            user.videos_today = 0

        # ── Credit user ──
        reward = float(MC_PER_VIDEO)
        user.balance_mc += reward
        user.total_earned_mc += reward
        user.videos_today += 1
        user.last_watch_date = now

        # ── Referral bonus ──
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

        # ── Audit record ──
        record = WatchRecord(
            user_id=user.id,
            telegram_id=payload.user_id,
            reward_mc=reward,
            referrer_bonus_mc=referrer_bonus,
            referrer_telegram_id=referrer_tg_id,
            adsgram_event_id=payload.event_id,
        )
        session.add(record)
        session.add(user)
        await session.commit()

        logger.info(
            "Credited %s MC to user %s (referrer bonus: %s MC to %s)",
            reward, payload.user_id, referrer_bonus, referrer_tg_id,
        )

    return JSONResponse({
        "ok": True,
        "reward": reward,
        "new_balance": user.balance_mc,
        "videos_today": user.videos_today,
        "daily_limit": DAILY_VIDEO_LIMIT,
    })


# ── User Info API (for Mini App) ───────────────────────────────────────
@app.get("/api/user/{telegram_id}", summary="Get user info for Mini App")
async def get_user_info(telegram_id: int) -> JSONResponse:
    """Return user balance & stats for the Mini App frontend."""
    async with async_session() as session:
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

    if not user:
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
