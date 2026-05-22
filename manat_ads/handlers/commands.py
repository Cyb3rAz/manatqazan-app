"""
ManatAds – Telegram Bot Command Handlers
==========================================
Commands:
  /start [referral_code]  – Register + deep-link referral binding.
  /balance                – Show current MC balance & AZN equivalent.
  /referral               – Show referral link, stats & earnings.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from aiogram import Router, types
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from database import async_session
from models import User

router = Router(name="commands")

# ── Config ──────────────────────────────────────────────────────────────
MC_TO_AZN_RATE = int(os.getenv("MC_TO_AZN_RATE", "21000"))
MC_PER_VIDEO = int(os.getenv("MC_PER_VIDEO", "50"))
DAILY_LIMIT = int(os.getenv("DAILY_VIDEO_LIMIT", "25"))

raw_webhook_url = os.getenv("WEBHOOK_URL", "").strip()
if not raw_webhook_url or "your-domain" in raw_webhook_url:
    WEBHOOK_URL = "https://manatqazan.vercel.app"
else:
    WEBHOOK_URL = raw_webhook_url.rstrip("/")


# ── /start with deep-link referral ─────────────────────────────────────
@router.message(CommandStart(deep_link=True))
async def cmd_start_with_referral(message: types.Message) -> None:
    """Handle /start <referral_code> where code == referrer's telegram_id."""
    tg_user = message.from_user
    if not tg_user:
        return

    referral_code = message.text.split(maxsplit=1)[1] if message.text and " " in message.text else None
    referrer_tg_id: int | None = None

    if referral_code:
        try:
            referrer_tg_id = int(referral_code)
        except (ValueError, TypeError):
            referrer_tg_id = None

    # Don't let users refer themselves
    if referrer_tg_id == tg_user.id:
        referrer_tg_id = None

    async with async_session() as session:
        # Check if user already exists
        stmt = select(User).where(User.telegram_id == tg_user.id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if user:
            await _send_welcome_back(message, user)
            return

        # Validate referrer exists
        if referrer_tg_id:
            ref_stmt = select(User).where(User.telegram_id == referrer_tg_id)
            ref_result = await session.execute(ref_stmt)
            referrer = ref_result.scalar_one_or_none()
            if referrer:
                referrer.referral_count += 1
                session.add(referrer)
            else:
                referrer_tg_id = None

        # Create new user
        new_user = User(
            telegram_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            last_name=tg_user.last_name,
            referrer_id=referrer_tg_id,
        )
        session.add(new_user)
        await session.commit()

    referral_msg = ""
    if referrer_tg_id:
        referral_msg = "\n\n🤝 <b>You were invited by a friend!</b> They'll earn a 10% lifetime bonus on your rewards."

    webapp_url = "https://manatqazan.vercel.app"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Watch & Earn", web_app=types.WebAppInfo(url=webapp_url))],
        [InlineKeyboardButton(text="💰 My Balance", callback_data="balance")],
        [InlineKeyboardButton(text="👥 Referral Program", callback_data="referral")],
    ])

    await message.answer(
        f"🎉 <b>Welcome to ManatAds!</b>\n\n"
        f"Hello, <b>{tg_user.first_name}</b>! 👋\n\n"
        f"📺 Watch short videos and earn <b>{MC_PER_VIDEO} MC</b> per video.\n"
        f"💵 Convert your earnings: <b>{MC_TO_AZN_RATE:,} MC = 1.00 AZN</b>\n"
        f"📊 Daily limit: <b>{DAILY_LIMIT} videos/day</b>\n"
        f"👥 Invite friends for <b>10% lifetime bonus!</b>"
        f"{referral_msg}",
        reply_markup=keyboard,
    )


@router.message(CommandStart())
async def cmd_start(message: types.Message) -> None:
    """Handle plain /start without a referral code."""
    tg_user = message.from_user
    if not tg_user:
        return

    async with async_session() as session:
        stmt = select(User).where(User.telegram_id == tg_user.id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if user:
            await _send_welcome_back(message, user)
            return

        new_user = User(
            telegram_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            last_name=tg_user.last_name,
        )
        session.add(new_user)
        await session.commit()

    webapp_url = "https://manatqazan.vercel.app"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Watch & Earn", web_app=types.WebAppInfo(url=webapp_url))],
        [InlineKeyboardButton(text="💰 My Balance", callback_data="balance")],
        [InlineKeyboardButton(text="👥 Referral Program", callback_data="referral")],
    ])

    await message.answer(
        f"🎉 <b>Welcome to ManatAds!</b>\n\n"
        f"Hello, <b>{tg_user.first_name}</b>! 👋\n\n"
        f"📺 Watch short videos and earn <b>{MC_PER_VIDEO} MC</b> per video.\n"
        f"💵 Convert your earnings: <b>{MC_TO_AZN_RATE:,} MC = 1.00 AZN</b>\n"
        f"📊 Daily limit: <b>{DAILY_LIMIT} videos/day</b>\n"
        f"👥 Invite friends for <b>10% lifetime bonus!</b>",
        reply_markup=keyboard,
    )


# ── /balance ────────────────────────────────────────────────────────────
@router.message(Command("balance"))
async def cmd_balance(message: types.Message) -> None:
    """Show the user's current MC balance and AZN equivalent."""
    tg_user = message.from_user
    if not tg_user:
        return

    async with async_session() as session:
        stmt = select(User).where(User.telegram_id == tg_user.id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

    if not user:
        await message.answer("⚠️ You're not registered yet. Send /start first.")
        return

    azn_value = user.balance_mc / MC_TO_AZN_RATE
    today = datetime.now(timezone.utc).date()
    last_date = user.last_watch_date.date() if user.last_watch_date else None
    videos_remaining = DAILY_LIMIT - (user.videos_today if last_date == today else 0)

    await message.answer(
        f"💰 <b>Your Balance</b>\n\n"
        f"┌─────────────────────────\n"
        f"│ 🪙 <b>Manat Coins:</b>  {user.balance_mc:,.0f} MC\n"
        f"│ 💵 <b>AZN Value:</b>    {azn_value:,.4f} AZN\n"
        f"│ 📈 <b>Total Earned:</b> {user.total_earned_mc:,.0f} MC\n"
        f"│ 🎬 <b>Videos Left:</b>  {videos_remaining}/{DAILY_LIMIT}\n"
        f"└─────────────────────────\n\n"
        f"💡 <i>Conversion rate: {MC_TO_AZN_RATE:,} MC = 1.00 AZN</i>",
    )


# ── /referral ──────────────────────────────────────────────────────────
@router.message(Command("referral"))
async def cmd_referral(message: types.Message) -> None:
    """Show the user's referral link, count, and earnings."""
    tg_user = message.from_user
    if not tg_user:
        return

    async with async_session() as session:
        stmt = select(User).where(User.telegram_id == tg_user.id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

    if not user:
        await message.answer("⚠️ You're not registered yet. Send /start first.")
        return

    bot_info = await message.bot.me()
    bot_username = bot_info.username
    referral_link = f"https://t.me/{bot_username}?start={tg_user.id}"
    ref_azn = user.referral_earnings_mc / MC_TO_AZN_RATE

    await message.answer(
        f"👥 <b>Referral Program</b>\n\n"
        f"Share your link and earn <b>10% lifetime bonus</b> on every video your friends watch!\n\n"
        f"🔗 <b>Your Referral Link:</b>\n"
        f"<code>{referral_link}</code>\n\n"
        f"┌─────────────────────────\n"
        f"│ 👤 <b>Friends Invited:</b>     {user.referral_count}\n"
        f"│ 🪙 <b>Referral Earnings:</b>   {user.referral_earnings_mc:,.0f} MC\n"
        f"│ 💵 <b>Referral AZN:</b>        {ref_azn:,.4f} AZN\n"
        f"└─────────────────────────\n\n"
        f"💡 <i>For each video your referral watches ({MC_PER_VIDEO} MC), "
        f"you automatically receive {MC_PER_VIDEO * 10 // 100} MC!</i>",
    )


# ── Callback-query shortcuts ──────────────────────────────────────────
@router.callback_query(lambda c: c.data == "balance")
async def cb_balance(callback: types.CallbackQuery) -> None:
    """Inline button shortcut for /balance."""
    await callback.answer()
    # Reuse the command handler by faking a Message-like call
    if callback.message and isinstance(callback.message, types.Message):
        callback.message.from_user = callback.from_user
        await cmd_balance(callback.message)


@router.callback_query(lambda c: c.data == "referral")
async def cb_referral(callback: types.CallbackQuery) -> None:
    """Inline button shortcut for /referral."""
    await callback.answer()
    if callback.message and isinstance(callback.message, types.Message):
        callback.message.from_user = callback.from_user
        await cmd_referral(callback.message)


# ── Helpers ─────────────────────────────────────────────────────────────
async def _send_welcome_back(message: types.Message, user: User) -> None:
    """Greet a returning user with their current stats."""
    azn_value = user.balance_mc / MC_TO_AZN_RATE
    webapp_url = "https://manatqazan.vercel.app"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Watch & Earn", web_app=types.WebAppInfo(url=webapp_url))],
        [InlineKeyboardButton(text="💰 My Balance", callback_data="balance")],
        [InlineKeyboardButton(text="👥 Referral Program", callback_data="referral")],
    ])

    await message.answer(
        f"👋 <b>Welcome back, {user.first_name or 'friend'}!</b>\n\n"
        f"🪙 Balance: <b>{user.balance_mc:,.0f} MC</b> ({azn_value:,.4f} AZN)\n"
        f"📈 Total earned: <b>{user.total_earned_mc:,.0f} MC</b>\n\n"
        f"Ready to earn more? Tap the button below! 👇",
        reply_markup=keyboard,
    )
