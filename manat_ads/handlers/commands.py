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
        referral_msg = "\n\n🤝 <b>Sizi dostunuz dəvət edib!</b> Onlar sizin qazancınızdan ömürlük 10% bonus qazanacaqlar."

    webapp_url = "https://manatqazan.vercel.app"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Video İzlə & Qazan", web_app=types.WebAppInfo(url=webapp_url))],
        [
            InlineKeyboardButton(text="💰 Balansım", callback_data="balance"),
            InlineKeyboardButton(text="👥 Referal Proqramı", callback_data="referral")
        ],
        [
            InlineKeyboardButton(text="ℹ️ Necə İşləyir?", callback_data="how_it_works"),
            InlineKeyboardButton(text="💰 Çıxarış", callback_data="withdraw")
        ]
    ])

    await message.answer(
        f"🎉 <b>ManatAds-a xoş gəlmisiniz!</b>\n\n"
        f"Salam, <b>{tg_user.first_name}</b>! 👋\n\n"
        f"📺 Qısa videolar izləyin və hər video üçün <b>{MC_PER_VIDEO} MC</b> qazanın.\n"
        f"💵 Qazancınızı konvertasiya edin: <b>{MC_TO_AZN_RATE:,} MC = 1.00 AZN</b>\n"
        f"📊 Gündəlik limit: <b>{DAILY_LIMIT} video/gün</b>\n"
        f"👥 Dostlarınızı dəvət edin və <b>ömürlük 10% bonus</b> qazanın!"
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
        [InlineKeyboardButton(text="🎬 Video İzlə & Qazan", web_app=types.WebAppInfo(url=webapp_url))],
        [
            InlineKeyboardButton(text="💰 Balansım", callback_data="balance"),
            InlineKeyboardButton(text="👥 Referal Proqramı", callback_data="referral")
        ],
        [
            InlineKeyboardButton(text="ℹ️ Necə İşləyir?", callback_data="how_it_works"),
            InlineKeyboardButton(text="💰 Çıxarış", callback_data="withdraw")
        ]
    ])

    await message.answer(
        f"🎉 <b>ManatAds-a xoş gəlmisiniz!</b>\n\n"
        f"Salam, <b>{tg_user.first_name}</b>! 👋\n\n"
        f"📺 Qısa videolar izləyin və hər video üçün <b>{MC_PER_VIDEO} MC</b> qazanın.\n"
        f"💵 Qazancınızı konvertasiya edin: <b>{MC_TO_AZN_RATE:,} MC = 1.00 AZN</b>\n"
        f"📊 Gündəlik limit: <b>{DAILY_LIMIT} video/gün</b>\n"
        f"👥 Dostlarınızı dəvət edin və <b>ömürlük 10% bonus</b> qazanın!",
        reply_markup=keyboard,
    )


# ── /balance ────────────────────────────────────────────────────────────
@router.message(Command("balance"))
async def cmd_balance(message: types.Message) -> None:
    """Show the user's current MC balance and AZN equivalent."""
    tg_user = message.from_user
    if not tg_user:
        return
    await _show_balance(tg_user, message)


async def _show_balance(tg_user: types.User, message: types.Message) -> None:
    async with async_session() as session:
        stmt = select(User).where(User.telegram_id == tg_user.id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

    if not user:
        await message.answer("⚠️ Siz hələ qeydiyyatdan keçməmisiniz. Zəhmət olmasa əvvəlcə /start göndərin.")
        return

    azn_value = user.balance_mc / MC_TO_AZN_RATE
    today = datetime.now(timezone.utc).date()
    last_date = user.last_watch_date.date() if user.last_watch_date else None
    videos_remaining = DAILY_LIMIT - (user.videos_today if last_date == today else 0)

    await message.answer(
        f"💰 <b>Balansınız</b>\n\n"
        f"┌─────────────────────────\n"
        f"│ 🪙 <b>Manat Coins:</b>  {user.balance_mc:,.0f} MC\n"
        f"│ 💵 <b>AZN Dəyəri:</b>    {azn_value:,.4f} AZN\n"
        f"│ 📈 <b>Ümumi Qazanc:</b> {user.total_earned_mc:,.0f} MC\n"
        f"│ 🎬 <b>Qalan Videolar:</b>  {videos_remaining}/{DAILY_LIMIT}\n"
        f"└─────────────────────────\n\n"
        f"💡 <i>Məzənnə: {MC_TO_AZN_RATE:,} MC = 1.00 AZN</i>",
    )


# ── /referral ──────────────────────────────────────────────────────────
@router.message(Command("referral"))
async def cmd_referral(message: types.Message) -> None:
    """Show the user's referral link, count, and earnings."""
    tg_user = message.from_user
    if not tg_user:
        return
    await _show_referral(tg_user, message)


async def _show_referral(tg_user: types.User, message: types.Message) -> None:
    async with async_session() as session:
        stmt = select(User).where(User.telegram_id == tg_user.id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

    if not user:
        await message.answer("⚠️ Siz hələ qeydiyyatdan keçməmisiniz. Zəhmət olmasa əvvəlcə /start göndərin.")
        return

    bot_info = await message.bot.me()
    bot_username = bot_info.username
    referral_link = f"https://t.me/{bot_username}?start={tg_user.id}"
    ref_azn = user.referral_earnings_mc / MC_TO_AZN_RATE

    await message.answer(
        f"👥 <b>Referal Proqramı</b>\n\n"
        f"Dəvət linkinizi paylaşın və dostlarınızın izlədiyi hər videodan <b>ömürlük 10% bonus</b> qazanın!\n\n"
        f"🔗 <b>Sizin Referal Linkiniz:</b>\n"
        f"<code>{referral_link}</code>\n\n"
        f"┌─────────────────────────\n"
        f"│ 👤 <b>Dəvət Olunanlar:</b>   {user.referral_count}\n"
        f"│ 🪙 <b>Referal Qazancı:</b>   {user.referral_earnings_mc:,.0f} MC\n"
        f"│ 💵 <b>Referal AZN:</b>      {ref_azn:,.4f} AZN\n"
        f"└─────────────────────────\n\n"
        f"💡 <i>Dəvət etdiyiniz hər bir şəxsin izlədiyi video üçün ({MC_PER_VIDEO} MC), "
        f"siz avtomatik olaraq {MC_PER_VIDEO * 10 // 100} MC əldə edirsiniz!</i>",
    )


# ── Callback-query shortcuts ──────────────────────────────────────────
@router.callback_query(lambda c: c.data == "balance")
async def cb_balance(callback: types.CallbackQuery) -> None:
    """Inline button shortcut for /balance."""
    await callback.answer()
    if callback.message and isinstance(callback.message, types.Message):
        await _show_balance(callback.from_user, callback.message)


@router.callback_query(lambda c: c.data == "referral")
async def cb_referral(callback: types.CallbackQuery) -> None:
    """Inline button shortcut for /referral."""
    await callback.answer()
    if callback.message and isinstance(callback.message, types.Message):
        await _show_referral(callback.from_user, callback.message)


@router.callback_query(lambda c: c.data == "how_it_works")
async def cb_how_it_works(callback: types.CallbackQuery) -> None:
    """Inline button shortcut for /how_it_works."""
    await callback.answer()
    if callback.message and isinstance(callback.message, types.Message):
        await _show_how_it_works(callback.message)


@router.callback_query(lambda c: c.data == "withdraw")
async def cb_withdraw(callback: types.CallbackQuery) -> None:
    """Inline button shortcut for withdrawal."""
    await callback.answer()
    if callback.message and isinstance(callback.message, types.Message):
        await _handle_withdraw(callback.from_user, callback.message)


# ── Helpers ─────────────────────────────────────────────────────────────
async def _send_welcome_back(message: types.Message, user: User) -> None:
    """Greet a returning user with their current stats."""
    azn_value = user.balance_mc / MC_TO_AZN_RATE
    webapp_url = "https://manatqazan.vercel.app"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Video İzlə & Qazan", web_app=types.WebAppInfo(url=webapp_url))],
        [
            InlineKeyboardButton(text="💰 Balansım", callback_data="balance"),
            InlineKeyboardButton(text="👥 Referal Proqramı", callback_data="referral")
        ],
        [
            InlineKeyboardButton(text="ℹ️ Necə İşləyir?", callback_data="how_it_works"),
            InlineKeyboardButton(text="💰 Çıxarış", callback_data="withdraw")
        ]
    ])

    await message.answer(
        f"👋 <b>Yenidən xoş gəldiniz, {user.first_name or 'dost'}!</b>\n\n"
        f"🪙 Balans: <b>{user.balance_mc:,.0f} MC</b> ({azn_value:,.4f} AZN)\n"
        f"📈 Ümumi qazanc: <b>{user.total_earned_mc:,.0f} MC</b>\n\n"
        f"Daha çox qazanmağa hazırsınız? Aşağıdakı düyməyə toxunun! 👇",
        reply_markup=keyboard,
    )


async def _show_how_it_works(message: types.Message) -> None:
    """Show how it works info message to the user."""
    text = (
        "ℹ️ <b>ManatAds Layihəsi Haqqında Məlumat</b>\n\n"
        "Platformamızın işləmə məntiqi çox bəsitdir:\n"
        "1️⃣ '<b>🎬 Video İzlə & Qazan</b>' düyməsinə toxunaraq qısa video reklamlar izləyirsiniz.\n"
        "2️⃣ Hər uğurlu izləmə üçün balansınıza anında <b>50 MC</b> (Manat Coin) əlavə olunur.\n"
        "3️⃣ Dostlarınızı dəvət edərək onların qazancından da əlavə bonuslar əldə edirsiniz.\n\n"
        "💰 <b>Çıxarış və Balans Mexanizmi:</b>\n"
        "Yığılan MC xalları sistem daxilində real Azərbaycan Manatına (AZN) konvertasiya olunur. "
        "Minimum çıxarış limiti 7 AZN-dir. Bu limitə çatdıqdan sonra qazancınızı rahatlıqla şəxsi elektron pul kisələrinə (məsələn, m10) "
        "və ya bank kartınıza nağdlaşdıra bilərsiniz!\n\n"
        "Hər hansı bir sualınız yaranarsa, dəstək komandası ilə əlaqə saxlaya bilərsiniz. "
        "İndi ilk videonuzu izləyin və qazanmağa başlayın! 🚀"
    )
    await message.answer(text)


async def _handle_withdraw(tg_user: types.User, message: types.Message) -> None:
    async with async_session() as session:
        stmt = select(User).where(User.telegram_id == tg_user.id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

    if not user:
        await message.answer("⚠️ Siz hələ qeydiyyatdan keçməmisiniz. Zəhmət olmasa əvvəlcə /start göndərin.")
        return

    azn_value = user.balance_mc / MC_TO_AZN_RATE
    
    if azn_value < 7:
        await message.answer(
            f"❌ Çıxarış uğursuz oldu. Minimum çıxarış limiti 7 AZN-dir. "
            f"Sizin hazırkı balansınız: {azn_value:,.4f} AZN. "
            f"Daha çox video izləyərək limiti tamamlaya bilərsiniz! 🚀"
        )
    else:
        await message.answer(
            "✅ Təbriklər! Çıxarış limitini keçmisiniz. Zəhmət olmasa pulu köçürmək "
            "istədiyiniz m10 nömrənizi və ya Bank Kartı məlumatlarınızı (Ad, Soyad, 16 rəqəmli kod) bura yazın:"
        )
