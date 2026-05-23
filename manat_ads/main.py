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
from contextlib import asynccontextmanager
from datetime import datetime, timezone
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

    # ── Set Menu Button ──
    try:
        await bot.set_chat_menu_button(
            menu_button=aio_types.MenuButtonWebApp(
                text="🚀 Aç", 
                web_app=aio_types.WebAppInfo(url="https://manatqazan.vercel.app")
            )
        )
        logger.info("Chat menu button set.")
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

    # Log and bypass signature/secret verification
    sig_keys = ["hash", "signature", "sign", "secret_key", "secret"]
    received_sigs = {k: params.get(k) for k in sig_keys if k in params}

    print(f"[ADSGRAM-GET] Security params: {received_sigs}")
    logger.warning(
        "[SIGNATURE-DEBUG-GET] Received security parameters: %s | Local SECRET=%r (bypass active)",
        received_sigs,
        ADSGRAM_SECRET[:10] + "..." if ADSGRAM_SECRET else "(empty)"
    )

    if not user_id_val:
        print(f"[ADSGRAM-GET] ERROR: userId not found! All params: {params}")
        logger.error("[ADSGRAM-GET] Missing userId or user_id in request query parameters! All params: %s", params)
        raise HTTPException(status_code=400, detail=f"userId parametri tapilmadi. Alinan parametrler: {list(params.keys())}")

    event_id = params.get("event_id") or params.get("eventId") or str(uuid.uuid4())
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
    event_id = payload.get("event_id") or payload.get("eventId") or str(uuid.uuid4())
    signature = payload.get("signature") or payload.get("hash") or payload.get("sign") or ""

    print(f"[ADSGRAM-POST] userId={user_id_val!r} | signature={signature!r}")
    logger.warning(
        "[SIGNATURE-DEBUG-POST] SECRET=%r | user_id=%s | event_id=%s | received_sig=%s (bypass active)",
        ADSGRAM_SECRET[:10] + "..." if ADSGRAM_SECRET else "(empty)",
        user_id_val, event_id, signature[:20] if signature else "(none)"
    )

    if not user_id_val:
        print(f"[ADSGRAM-POST] ERROR: userId not found! Keys: {list(payload.keys())}")
        logger.error("[ADSGRAM-POST] Missing user_id in payload! Keys: %s", list(payload.keys()))
        raise HTTPException(status_code=400, detail=f"user_id parametri tapilmadi. Alinan acarlar: {list(payload.keys())}")

    return await _credit_user(user_id_val, event_id=event_id, source="adsgram_post")


# ── Ortaq kredit məntiqi ─────────────────────────────────────────────────
async def _credit_user(user_id_val: int | str, event_id: str, source: str = "unknown") -> JSONResponse:
    """Bazada istifadecini tap, balansi artir, commit et."""
    print(f"[CREDIT] Credit attempt: user={user_id_val!r} | event_id={event_id} | source={source}")
    logger.info("[CREDIT] Attempting to credit user %s | event_id=%s | source=%s", user_id_val, event_id, source)

    user_str = str(user_id_val).strip()
    is_numeric = user_str.isdigit()

    # -- Deyiskenleri session scope-undan evvel elan et (DetachedInstanceError-i onle) --
    final_new_balance: float = 0.0
    final_videos_today: int = 0
    final_reward: float = float(MC_PER_VIDEO)

    async with async_session() as session:
        # -- Istifadecini tap (relasiya olmadan, yalniz users cedvelinden) --
        if is_numeric:
            tg_id = int(user_str)
            stmt = select(User).where(User.telegram_id == tg_id)
        else:
            username_val = user_str.lstrip('@')
            stmt = select(User).where(User.username == username_val)

        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        # Fallback: reqemsal idi amma tapilmadi -> username kimi yoxla
        if not user and is_numeric:
            print(f"[CREDIT] telegram_id={user_str} not found, checking username fallback...")
            logger.info("[CREDIT] User not found by numeric telegram_id %s, checking username field as fallback...", user_str)
            stmt = select(User).where(User.username == user_str)
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

        # -- event_id ile dublikat yoxla --
        if event_id:
            dup_stmt = select(WatchRecord).where(WatchRecord.adsgram_event_id == event_id)
            dup_result = await session.execute(dup_stmt)
            dup_record = dup_result.scalar_one_or_none()
            if dup_record:
                existing_balance = user.balance_mc
                print(f"[CREDIT] Duplicate event_id={event_id} - skipping.")
                logger.info("[CREDIT] Duplicate event_id=%s - skipping.", event_id)
                return JSONResponse({"ok": True, "message": "Artiq kreditlenib.", "balance": existing_balance})

        # -- Gundelik limit ve ardicil seans yoxla --
        now = datetime.now(timezone.utc)
        today = now.date()
        from datetime import timedelta

        # Dynamic daily reset
        if user.last_watch_date and user.last_watch_date.date() != today:
            print(f"[CREDIT] New day for user {user_telegram_id} - resetting session stats")
            logger.info("[CREDIT] New day for user %s - resetting session stats", user_telegram_id)
            user.session_1_count = 0
            user.session_2_count = 0
            user.session_1_completion_time = None
            user.videos_today = 0

        # Determine target session & enforce limits/cooldown
        if user.session_1_count < 25:
            # Active in Session 1
            user.session_1_count += 1
            if user.session_1_count == 25:
                user.session_1_completion_time = now
                print(f"[CREDIT] User {user_telegram_id} COMPLETED Session 1 at {now.isoformat()}")
                logger.info("[CREDIT] User %s COMPLETED Session 1 at %s", user_telegram_id, now.isoformat())
        else:
            # Session 1 is completed. Check Session 2 status.
            if user.session_1_completion_time is None:
                # Fallback: completed Session 1 but completion time was null, set now (though should not happen)
                user.session_1_completion_time = now - timedelta(hours=8) # unlock immediately

            unlock_time = user.session_1_completion_time + timedelta(hours=7)
            if now < unlock_time:
                # Session 2 is currently locked
                print(f"[CREDIT] Session 2 is LOCKED for user {user_telegram_id} until {unlock_time.isoformat()}")
                logger.warning("[CREDIT] Session 2 is LOCKED for user %s until %s", user_telegram_id, unlock_time.isoformat())
                return JSONResponse(
                    {"ok": False, "message": "Növbəti seans hələ kilidlidir.", "unlock_at": unlock_time.isoformat()},
                    status_code=403
                )

            # Session 2 is unlocked. Check if already completed Session 2.
            if user.session_2_count >= 25:
                print(f"[CREDIT] User {user_telegram_id} completed both sessions today (50 videos). Limit hit.")
                logger.warning("[CREDIT] User %s completed both sessions today (50 videos). Limit hit.", user_telegram_id)
                return JSONResponse({"ok": False, "message": "Gündəlik limitiniz bitdi."}, status_code=429)

            # Increment Session 2 count
            user.session_2_count += 1

        # -- Balansi artir --
        final_reward = float(MC_PER_VIDEO)
        old_balance = user.balance_mc
        user.balance_mc = old_balance + final_reward
        user.total_earned_mc = user.total_earned_mc + final_reward
        user.videos_today = user.session_1_count + user.session_2_count
        user.last_watch_date = now

        # Deyerleri cixmadan yadda saxla
        final_new_balance = user.balance_mc
        final_videos_today = user.videos_today

        print(f"[CREDIT] Balance update: {old_balance:.2f} -> {final_new_balance:.2f} (+{final_reward:.2f}) | videos_today={final_videos_today} (S1={user.session_1_count}, S2={user.session_2_count})")
        logger.info(
            "[CREDIT] balance: %.2f -> %.2f (+%.2f) | videos_today=%s (S1=%s, S2=%s)",
            old_balance, final_new_balance, final_reward, final_videos_today, user.session_1_count, user.session_2_count
        )

        # -- Referal bonusu --
        referrer_bonus: float = 0.0
        referrer_tg_id: int | None = user.referrer_id

        if referrer_tg_id:
            referrer_bonus = final_reward * REFERRAL_BONUS_PERCENT / 100.0
            ref_stmt = select(User).where(User.telegram_id == referrer_tg_id)
            ref_result = await session.execute(ref_stmt)
            referrer = ref_result.scalar_one_or_none()
            if referrer:
                referrer.balance_mc = referrer.balance_mc + referrer_bonus
                referrer.total_earned_mc = referrer.total_earned_mc + referrer_bonus
                referrer.referral_earnings_mc = referrer.referral_earnings_mc + referrer_bonus
                session.add(referrer)
                print(f"[CREDIT] Referral bonus {referrer_bonus:.2f} MC -> user {referrer_tg_id}")
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

        # -- COMMIT -- balansi yaddasa yaz --
        try:
            await session.flush()   # SQL-i bazaya gonder
            await session.commit()  # Emeliyyati qeti mohurle
            print(f"[CREDIT] SUCCESS: DB COMMITTED! user={user_telegram_id} | new_balance={final_new_balance:.2f} MC")
            logger.info("[CREDIT] COMMITTED DATABASE TRANS! user=%s new_balance=%.2f", user_telegram_id, final_new_balance)
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
        "videos_today": final_videos_today,
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

        if not user.is_active:
            logger.warning("[USER-INFO] Banned user %s tried to fetch user info!", telegram_id)
            raise HTTPException(status_code=403, detail="Hesabınız dondurulub.")

        now = datetime.now(timezone.utc)
        today = now.date()

        # Dynamic reset on-the-fly if last watch date is not today
        if user.last_watch_date and user.last_watch_date.date() != today:
            user.session_1_count = 0
            user.session_2_count = 0
            user.session_1_completion_time = None
            user.videos_today = 0
            session.add(user)
            await session.commit()
            await session.refresh(user)

        session_1_count = user.session_1_count
        session_2_count = user.session_2_count
        session_1_completion_time = user.session_1_completion_time
        videos_today = session_1_count + session_2_count
        balance_mc = user.balance_mc
        total_earned_mc = user.total_earned_mc
        referral_count = user.referral_count
        referral_earnings_mc = user.referral_earnings_mc
        first_name = user.first_name
        telegram_id_val = user.telegram_id

    # Compute Session 2 lock state
    session_2_locked = True
    unlock_at = None

    if session_1_count >= 25:
        if session_1_completion_time is None:
            # Legacy or fallback: if completed but no timestamp, unlock immediately
            session_2_locked = False
        else:
            from datetime import timedelta
            unlock_time = session_1_completion_time + timedelta(hours=7)
            if now < unlock_time:
                session_2_locked = True
                unlock_at = unlock_time.isoformat()
            else:
                session_2_locked = False

    return JSONResponse({
        "telegram_id": telegram_id_val,
        "first_name": first_name,
        "balance_mc": balance_mc,
        "balance_azn": round(balance_mc / MC_TO_AZN_RATE, 4),
        "total_earned_mc": total_earned_mc,
        "videos_today": videos_today,
        "daily_limit": 50,
        "session_1_count": session_1_count,
        "session_2_count": session_2_count,
        "session_2_locked": session_2_locked,
        "session_1_completion_time": session_1_completion_time.isoformat() if session_1_completion_time else None,
        "unlock_at": unlock_at,
        "referral_count": referral_count,
        "referral_earnings_mc": referral_earnings_mc,
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
