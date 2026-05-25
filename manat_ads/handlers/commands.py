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
import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable, Dict, Any, Awaitable

from aiogram import Router, types, BaseMiddleware
from aiogram.filters import BaseFilter, Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, MenuButtonWebApp, TelegramObject
from aiogram import F
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from database import async_session, DB_IS_POSTGRES
from models import User

logger = logging.getLogger("manatads.commands")

# ── Admin Config ──
ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "1970477419")
ADMIN_IDS = [int(x.strip()) for x in ADMIN_IDS_RAW.split(",") if x.strip().isdigit()]

class IsAdminFilter(BaseFilter):
    async def __call__(self, message: types.Message) -> bool:
        return message.from_user is not None and message.from_user.id in ADMIN_IDS

# ── Ban Check Middleware ──
class BanCheckMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user: types.User = data.get("event_from_user")
        if user:
            async with async_session() as session:
                stmt = select(User).where(User.telegram_id == user.id)
                res = await session.execute(stmt)
                db_user = res.scalar_one_or_none()
                if db_user and not db_user.is_active:
                    if isinstance(event, types.Message):
                        await event.answer("❌ Hesabınız dondurulub (banlanıb). Dəstək komandası ilə əlaqə saxlayın.")
                    elif isinstance(event, types.CallbackQuery):
                        await event.answer("❌ Hesabınız dondurulub.", show_alert=True)
                    return None
        return await handler(event, data)

router = Router(name="commands")
router.message.outer_middleware(BanCheckMiddleware())
router.callback_query.outer_middleware(BanCheckMiddleware())

# ── Config ──────────────────────────────────────────────────────────────
MC_TO_AZN_RATE = int(os.getenv("MC_TO_AZN_RATE", "125000"))
MC_PER_VIDEO = int(os.getenv("MC_PER_VIDEO", "50"))
DAILY_LIMIT = int(os.getenv("DAILY_VIDEO_LIMIT", "25"))

raw_webhook_url = os.getenv("WEBHOOK_URL", "").strip()
if not raw_webhook_url or "your-domain" in raw_webhook_url:
    WEBHOOK_URL = "https://manatqazan.vercel.app"
else:
    WEBHOOK_URL = raw_webhook_url.rstrip("/")


# ── Safe UPSERT helper ─────────────────────────────────────────────────
async def _upsert_user(
    session,
    telegram_id: int,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
    referrer_id: int | None = None,
) -> User:
    """
    Insert a new user or update an existing one (ON CONFLICT DO UPDATE).
    Works on both PostgreSQL (asyncpg) and SQLite (aiosqlite).
    Returns the User ORM object after the upsert.
    """
    values = dict(
        telegram_id=telegram_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
    )
    if referrer_id is not None:
        values["referrer_id"] = referrer_id

    # Fields to refresh on conflict (user reopened bot / changed profile)
    update_on_conflict = dict(
        username=username,
        first_name=first_name,
        last_name=last_name,
        updated_at=func.now(),
    )

    if DB_IS_POSTGRES:
        stmt = (
            pg_insert(User)
            .values(**values)
            .on_conflict_do_update(
                constraint="uq_users_telegram_id",
                set_=update_on_conflict,
            )
            .returning(User)
        )
        result = await session.execute(stmt)
        user = result.scalar_one()
    else:
        # SQLite dialect
        stmt = (
            sqlite_insert(User)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["telegram_id"],
                set_=update_on_conflict,
            )
        )
        await session.execute(stmt)
        await session.flush()
        # Re-fetch the user since SQLite insert doesn't support RETURNING on ORM
        sel = select(User).where(User.telegram_id == telegram_id)
        result = await session.execute(sel)
        user = result.scalar_one()

    return user


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

    is_new_user = False
    async with async_session() as session:
        try:
            # Check if user already exists BEFORE upsert (to detect new vs returning)
            existing_stmt = select(User).where(User.telegram_id == tg_user.id)
            existing_result = await session.execute(existing_stmt)
            existing_user = existing_result.scalar_one_or_none()

            if existing_user:
                # Returning user – just update profile fields
                existing_user.username = tg_user.username
                existing_user.first_name = tg_user.first_name
                existing_user.last_name = tg_user.last_name
                await session.commit()
                await _send_welcome_back(message, existing_user)
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

            # UPSERT: safe insert or update
            user = await _upsert_user(
                session,
                telegram_id=tg_user.id,
                username=tg_user.username,
                first_name=tg_user.first_name,
                last_name=tg_user.last_name,
                referrer_id=referrer_tg_id,
            )
            await session.commit()
            is_new_user = True
            logger.info("[UPSERT] User %s upserted successfully (referrer=%s)", tg_user.id, referrer_tg_id)

        except Exception as e:
            await session.rollback()
            logger.exception("[UPSERT] Failed to upsert user %s: %s", tg_user.id, e)
            await message.answer("⚠️ Xəta baş verdi. Zəhmət olmasa bir az sonra yenidən cəhd edin.")
            return

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

    await message.bot.set_chat_menu_button(
        chat_id=message.chat.id,
        menu_button=MenuButtonWebApp(
            text="🚀 Başlat",
            web_app=types.WebAppInfo(url=webapp_url)
        )
    )

    await message.answer(
        f"🎉 <b>ManatAds-a xoş gəlmisiniz!</b>\n\n"
        f"Salam, <b>{tg_user.first_name}</b>! 👋\n\n"
        f"📺 Qısa videolar izləyin və hər video üçün <b>{MC_PER_VIDEO} MC</b> qazanın.\n"
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

    is_new_user = False
    async with async_session() as session:
        try:
            # Check if user already exists
            existing_stmt = select(User).where(User.telegram_id == tg_user.id)
            existing_result = await session.execute(existing_stmt)
            existing_user = existing_result.scalar_one_or_none()

            if existing_user:
                # Returning user – update profile fields
                existing_user.username = tg_user.username
                existing_user.first_name = tg_user.first_name
                existing_user.last_name = tg_user.last_name
                await session.commit()
                await _send_welcome_back(message, existing_user)
                return

            # UPSERT: safe insert or update
            user = await _upsert_user(
                session,
                telegram_id=tg_user.id,
                username=tg_user.username,
                first_name=tg_user.first_name,
                last_name=tg_user.last_name,
            )
            await session.commit()
            is_new_user = True
            logger.info("[UPSERT] User %s upserted successfully (no referrer)", tg_user.id)

        except Exception as e:
            await session.rollback()
            logger.exception("[UPSERT] Failed to upsert user %s: %s", tg_user.id, e)
            await message.answer("⚠️ Xəta baş verdi. Zəhmət olmasa bir az sonra yenidən cəhd edin.")
            return

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

    await message.bot.set_chat_menu_button(
        chat_id=message.chat.id,
        menu_button=MenuButtonWebApp(
            text="🚀 Başlat",
            web_app=types.WebAppInfo(url=webapp_url)
        )
    )

    await message.answer(
        f"🎉 <b>ManatAds-a xoş gəlmisiniz!</b>\n\n"
        f"Salam, <b>{tg_user.first_name}</b>! 👋\n\n"
        f"📺 Qısa videolar izləyin və hər video üçün <b>{MC_PER_VIDEO} MC</b> qazanın.\n"
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

    now = datetime.now(timezone.utc)
    today = now.date()

    # Dynamic daily reset
    if user.last_watch_date and user.last_watch_date.date() != today:
        async with async_session() as reset_session:
            stmt = select(User).where(User.telegram_id == tg_user.id)
            res = await reset_session.execute(stmt)
            db_user = res.scalar_one()
            db_user.session_1_count = 0
            db_user.session_2_count = 0
            db_user.session_1_completion_time = None
            db_user.videos_today = 0
            await reset_session.commit()
            user = db_user

    session_1_count = user.session_1_count
    session_2_count = user.session_2_count
    session_1_completion_time = user.session_1_completion_time
    balance_mc = user.balance_mc
    total_earned_mc = user.total_earned_mc

    azn_value = balance_mc / MC_TO_AZN_RATE
    
    # Calculate lock text
    s2_status = "Kilidli 🔒"
    if session_1_count >= 25:
        if session_1_completion_time is None:
            s2_status = "Aktiv 🟢"
        else:
            from datetime import timedelta
            unlock_time = session_1_completion_time + timedelta(hours=4)
            if now < unlock_time:
                remaining = unlock_time - now
                hours, remainder = divmod(int(remaining.total_seconds()), 3600)
                minutes, _ = divmod(remainder, 60)
                s2_status = f"🔒 Kilidli ({hours:02d}s {minutes:02d}d qalıb)"
            else:
                s2_status = "Aktiv 🟢"

    await message.answer(
        f"💰 <b>Balansınız</b>\n\n"
        f"┌─────────────────────────\n"
        f"│ 🪙 <b>Manat Coins:</b>  {balance_mc:,.0f} MC\n"
        f"│ 📈 <b>Ümumi Qazanc:</b> {total_earned_mc:,.0f} MC\n"
        f"├─────────────────────────\n"
        f"│ 1️⃣ <b>Səans 1:</b>  {session_1_count}/25 video\n"
        f"│ 2️⃣ <b>Səans 2:</b>  {session_2_count}/25 video ({s2_status})\n"
        f"└─────────────────────────",
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


# ── Text Message Handlers (Reply Keyboard) ──────────────────────────────
@router.message(F.text == "💰 Balansım")
async def txt_balance(message: types.Message) -> None:
    if message.from_user:
        await _show_balance(message.from_user, message)

@router.message(F.text == "👥 Referal Proqramı")
async def txt_referral(message: types.Message) -> None:
    if message.from_user:
        await _show_referral(message.from_user, message)

@router.message(F.text == "ℹ️ Necə İşləyir?")
async def txt_how_it_works(message: types.Message) -> None:
    await _show_how_it_works(message)

@router.message(F.text == "💰 Çıxarış")
async def txt_withdraw(message: types.Message) -> None:
    if message.from_user:
        await _handle_withdraw(message.from_user, message)


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
        f"🪙 Balans: <b>{user.balance_mc:,.0f} MC</b>\n"
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
        "Minimum çıxarış limiti 5 AZN-dir. Bu limitə çatdıqdan sonra qazancınızı rahatlıqla şəxsi elektron pul kisələrinə (məsələn, m10) "
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
    
    if azn_value < 5:
        await message.answer(
            f"❌ Çıxarış uğursuz oldu. Minimum çıxarış limiti 5 AZN-dir.\n\n"
            f"💰 Sizin hazırkı balansınız: <b>{azn_value:,.4f} AZN</b>\n\n"
            f"🚀 <b>Limiti necə daha sürətli tamamlamaq olar?</b>\n"
            f"Daha çox video izləməklə yanaşı, <b>dostlarınızı dəvət edərək</b> daha böyük məbləğlər qazana bilərsiniz! "
            f"Dəvət etdiyiniz hər dostunuzun izlədiyi reklamlardan sizə avtomatik <b>ömürlük 10% bonus</b> gələcək. Linkinizi paylaşın və hədəfə sürətlə çatın! 👥💸"
        )
    else:
        await message.answer(
            "✅ Təbriklər! Çıxarış limitini keçmisiniz. Zəhmət olmasa pulu köçürmək "
            "istədiyiniz m10 nömrənizi və ya Bank Kartı məlumatlarınızı (Ad, Soyad, 16 rəqəmli kod) bura yazın:"
        )


# ── Admin Commands ──────────────────────────────────────────────────────

async def _get_admin_stats_text() -> str:
    """Build the admin stats text including last 5 joined users."""
    async with async_session() as session:
        # ── Ümumi istifadəçi sayı ──
        total_users_res = await session.execute(select(func.count(User.id)))
        total_users = total_users_res.scalar() or 0

        # ── Dövriyyədəki ümumi MC ──
        total_mc_res = await session.execute(select(func.sum(User.balance_mc)))
        total_mc = total_mc_res.scalar() or 0.0

        # ── Ümumi qazanılan MC ──
        total_earned_res = await session.execute(select(func.sum(User.total_earned_mc)))
        total_earned = total_earned_res.scalar() or 0.0

        # ── Son 5 qoşulan istifadəçi ──
        last5_res = await session.execute(
            select(User.telegram_id, User.username, User.first_name, User.created_at)
            .order_by(User.created_at.desc())
            .limit(5)
        )
        last5 = last5_res.all()

    # ── Son 5 istifadəçi sətirləri ──
    if last5:
        user_lines = []
        for row in last5:
            tg_id, uname, fname, created = row
            username_str = f"@{uname}" if uname else (fname or "Adsız")
            date_str = created.strftime("%d.%m.%Y %H:%M") if created else "—"
            user_lines.append(f"  • {username_str} (<code>{tg_id}</code>) — {date_str}")
        last5_block = "\n".join(user_lines)
    else:
        last5_block = "  — Hələ istifadəçi yoxdur."

    return (
        f"📊 <b>MANAT QAZAN — ADMİN PANELİ</b>\n"
        f"{'─' * 30}\n\n"
        f"👤 <b>Ümumi İstifadəçi Sayı:</b> {total_users} nəfər\n"
        f"🪙 <b>Dövriyyədəki Cəmi MC:</b> {total_mc:,.0f} MC\n"
        f"📈 <b>Ümumi Qazanılan MC:</b> {total_earned:,.0f} MC\n\n"
        f"🕒 <b>Son Qoşulan 5 İstifadəçi:</b>\n"
        f"{last5_block}"
    )


ADMIN_HELP_TEXT = (
    "🛠️ <b>ManatAds — Aktiv Admin Əmrləri:</b>\n\n"
    "• /admin — Ümumi sistem statistikası və idarəetmə paneli.\n"
    "• /users — Bota son qoşulan 20 istifadəçi və balansları.\n"
    "• /info [ID/Username] — İstifadəçinin bütün detallı profili (Məs: /info CVb3rAz).\n"
    "• /give [ID/Username] [Miqdar] — Balansa manual MC əlavə edir/silir (Məs: /give CVb3rAz 500).\n"
    "• /ban [ID] — Şübhəli şəxsi dondurur, botu və Mini App-i onun üçün bağlayır.\n"
    "• /unban [ID] — Ban olunmuş şəxsin blokunu qaldırır.\n"
    "• /broadcast [Mesaj] — Bazardakı BÜTÜN istifadəçilərə kütləvi bildiriş göndərir."
)

ADMIN_PANEL_KB = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="📜 Əmrlər və İzahları", callback_data="admin_show_help")]
])

ADMIN_BACK_KB = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="⬅️ İdarəetmə Panelinə Qayıt", callback_data="admin_main_menu")]
])


@router.message(Command("admin"), IsAdminFilter())
async def cmd_admin(message: types.Message) -> None:
    text = await _get_admin_stats_text()
    await message.answer(text, reply_markup=ADMIN_PANEL_KB)


@router.callback_query(lambda c: c.data == "admin_show_help")
async def cb_admin_show_help(callback: types.CallbackQuery) -> None:
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ İcazəniz yoxdur.", show_alert=True)
        return
    await callback.answer()
    if callback.message and isinstance(callback.message, types.Message):
        await callback.message.edit_text(ADMIN_HELP_TEXT, reply_markup=ADMIN_BACK_KB)


@router.callback_query(lambda c: c.data == "admin_main_menu")
async def cb_admin_main_menu(callback: types.CallbackQuery) -> None:
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ İcazəniz yoxdur.", show_alert=True)
        return
    await callback.answer()
    if callback.message and isinstance(callback.message, types.Message):
        text = await _get_admin_stats_text()
        await callback.message.edit_text(text, reply_markup=ADMIN_PANEL_KB)


@router.message(Command("users"), IsAdminFilter())
async def cmd_users(message: types.Message) -> None:
    async with async_session() as session:
        stmt = select(User).order_by(User.id.desc()).limit(20)
        res = await session.execute(stmt)
        users = res.scalars().all()
        
    if not users:
        await message.answer("👥 Heç bir istifadəçi tapılmadı.")
        return
        
    lines = ["👥 Son Aktiv İstifadəçilər:"]
    for i, u in enumerate(users, 1):
        username_str = f"@{u.username}" if u.username else "Yoxdur"
        lines.append(f"{i}. ID: {u.telegram_id} | {username_str} | Balans: {u.balance_mc:,.0f} MC")
        
    await message.answer("\n".join(lines))


@router.message(Command("info"), IsAdminFilter())
async def cmd_info(message: types.Message) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("⚠️ Zəhmət olmasa istifadəçi ID və ya username daxil edin.\nNümunə: <code>/info 1970477419</code> və ya <code>/info CVb3rAz</code>")
        return
        
    target = parts[1].strip()
    target_clean = target.lstrip('@')
    
    async with async_session() as session:
        if target.isdigit():
            tg_id = int(target)
            stmt = select(User).where((User.telegram_id == tg_id) | (User.username == target_clean))
        else:
            stmt = select(User).where(User.username == target_clean)
            
        res = await session.execute(stmt)
        user = res.scalar_one_or_none()
        
    if not user:
        await message.answer("❌ İstifadəçi tapılmadı!")
        return
        
    status_str = "Aktiv" if user.is_active else "Banlı"
    username_display = f"@{user.username}" if user.username else "Yoxdur"
    
    today = datetime.now(timezone.utc).date()
    last_date = user.last_watch_date.date() if user.last_watch_date else None
    
    session_1 = user.session_1_count if last_date == today else 0
    session_2 = user.session_2_count if last_date == today else 0
    total_videos = session_1 + session_2
    
    await message.answer(
        f"ℹ️ <b>İstifadəçi Məlumatı:</b>\n"
        f"• <b>Telegram ID:</b> <code>{user.telegram_id}</code>\n"
        f"• <b>Username:</b> {username_display}\n"
        f"• <b>Hazırkı Balans:</b> {user.balance_mc:,.0f} MC\n"
        f"• <b>Ümumi Qazanc:</b> {user.total_earned_mc:,.0f} MC\n"
        f"• <b>Bugünkü Videolar:</b> {total_videos}/50 (S1: {session_1}/25 | S2: {session_2}/25)\n"
        f"• <b>Dəvət Etdiyi Şəxslər:</b> {user.referral_count} nəfər\n"
        f"• <b>Status:</b> {status_str}"
    )


@router.message(Command("give"), IsAdminFilter())
async def cmd_give(message: types.Message) -> None:
    parts = message.text.split()
    if len(parts) < 3:
        await message.answer("⚠️ Yanlış format. Nümunə: <code>/give 1970477419 500</code> və ya <code>/give CVb3rAz -200</code>")
        return
        
    target = parts[1].strip()
    try:
         amount = float(parts[2])
    except ValueError:
         await message.answer("⚠️ Miqdar rəqəm olmalıdır.")
         return
         
    target_clean = target.lstrip('@')
    
    async with async_session() as session:
        if target.isdigit():
            tg_id = int(target)
            stmt = select(User).where((User.telegram_id == tg_id) | (User.username == target_clean))
        else:
            stmt = select(User).where(User.username == target_clean)
            
        res = await session.execute(stmt)
        user = res.scalar_one_or_none()
        
        if not user:
            await message.answer("❌ İstifadəçi tapılmadı!")
            return
            
        old_bal = user.balance_mc
        user.balance_mc += amount
        if amount > 0:
            user.total_earned_mc += amount
            
        await session.commit()
        
        await message.answer(
            f"✅ <b>Balans yeniləndi!</b>\n\n"
            f"👤 İstifadəçi: <code>{user.telegram_id}</code>\n"
            f"🪙 Əvvəlki balans: {old_bal:,.0f} MC\n"
            f"➕ Dəyişiklik: {amount:+,.0f} MC\n"
            f"💰 Yeni balans: {user.balance_mc:,.0f} MC"
        )


@router.message(Command("ban"), IsAdminFilter())
async def cmd_ban(message: types.Message) -> None:
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("⚠️ Nümunə: <code>/ban 1970477419</code> və ya <code>/ban CVb3rAz</code>")
        return
        
    target = parts[1].strip()
    target_clean = target.lstrip('@')
    
    async with async_session() as session:
        if target.isdigit():
            tg_id = int(target)
            stmt = select(User).where((User.telegram_id == tg_id) | (User.username == target_clean))
        else:
            stmt = select(User).where(User.username == target_clean)
            
        res = await session.execute(stmt)
        user = res.scalar_one_or_none()
        
        if not user:
            await message.answer("❌ İstifadəçi tapılmadı!")
            return
            
        user.is_active = False
        await session.commit()
        
        await message.answer(
            f"🔒 <b>İstifadəçi donduruldu (Banlandı):</b>\n"
            f"ID: <code>{user.telegram_id}</code> | @{user.username or 'Yoxdur'}"
        )


@router.message(Command("unban"), IsAdminFilter())
async def cmd_unban(message: types.Message) -> None:
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("⚠️ Nümunə: <code>/unban 1970477419</code> və ya <code>/unban CVb3rAz</code>")
        return
        
    target = parts[1].strip()
    target_clean = target.lstrip('@')
    
    async with async_session() as session:
        if target.isdigit():
            tg_id = int(target)
            stmt = select(User).where((User.telegram_id == tg_id) | (User.username == target_clean))
        else:
            stmt = select(User).where(User.username == target_clean)
            
        res = await session.execute(stmt)
        user = res.scalar_one_or_none()
        
        if not user:
            await message.answer("❌ İstifadəçi tapılmadı!")
            return
            
        user.is_active = True
        await session.commit()
        
        await message.answer(
            f"🔓 <b>İstifadəçi aktivləşdirildi (Unban):</b>\n"
            f"ID: <code>{user.telegram_id}</code> | @{user.username or 'Yoxdur'}"
        )


@router.message(Command("broadcast"), IsAdminFilter())
async def cmd_broadcast(message: types.Message) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("⚠️ Nümunə: <code>/broadcast Salam, yeni videolar əlavə olundu! 🚀</code>")
        return
        
    broadcast_msg = parts[1].strip()
    
    async with async_session() as session:
        stmt = select(User.telegram_id).where(User.is_active == True)
        res = await session.execute(stmt)
        active_ids = res.scalars().all()
        
    if not active_ids:
        await message.answer("⚠️ Yayım üçün heç bir aktiv istifadəçi tapılmadı.")
        return
        
    await message.answer(f"📢 <b>Yayım başladı...</b>\nHədəf: {len(active_ids)} istifadəçi.")
    
    success_count = 0
    fail_count = 0
    
    for tg_id in active_ids:
        try:
            await message.bot.send_message(chat_id=tg_id, text=broadcast_msg)
            success_count += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            logger.error("Failed to broadcast to %s: %s", tg_id, e)
            fail_count += 1
            
    await message.answer(
        f"📢 <b>Yayım tamamlandı!</b>\n\n"
        f"✅ Uğurlu: {success_count}\n"
        f"❌ Uğursuz: {fail_count}"
    )
