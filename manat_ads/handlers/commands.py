"""
VibeCash – Telegram Bot Command Handlers
==========================================
Commands:
  /start [referral_code]  – Register + deep-link referral binding.
  /balance                – Show current VC balance & AZN equivalent.
  /referral               – Show referral link, stats & earnings.
"""

from __future__ import annotations

import os
import asyncio
import logging
from datetime import date, datetime, timezone, timedelta
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

def _get_utc_date(dt: datetime | None) -> date | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc).date()
    return dt.astimezone(timezone.utc).date()

# ── Admin Config ──
ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "1970477419")
ADMIN_IDS = [int(x.strip()) for x in ADMIN_IDS_RAW.split(",") if x.strip().isdigit()]
# ADMIN_ID is the primary notification target (falls back to the first entry in ADMIN_IDS)
_admin_id_env = os.getenv("ADMIN_ID", "").strip()
ADMIN_ID: int | None = int(_admin_id_env) if _admin_id_env.isdigit() else (ADMIN_IDS[0] if ADMIN_IDS else None)

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
MC_TO_AZN_RATE = int(os.getenv("MC_TO_AZN_RATE", "140000"))
MIN_WITHDRAWAL_TRY = float(os.getenv("MIN_WITHDRAWAL_TRY", "275.00"))
MC_PER_VIDEO = int(os.getenv("MC_PER_VIDEO", "300"))
DAILY_LIMIT = int(os.getenv("DAILY_VIDEO_LIMIT", "24"))
# Withdrawal threshold = 10 AZN
_WITHDRAWAL_THRESHOLD_MC: float = 10.0


def _get_mc_for_tier(vip_status: str | None) -> int:
    """Return the VC-per-video reward for a given VIP tier string.

    Mirrors _get_vip_params() in main.py but is self-contained so
    command handlers need no cross-module import.
    MC_TO_AZN_RATE=140,000 | Withdrawal threshold=700,000 VC = 5 AZN:
      free  -> 200 VC  (50 clicks/day → 70 days to withdraw)
      pro   -> 260 VC  (45 clicks/day → ~60 days to withdraw)
      elite -> 350 VC  (40 clicks/day → 50 days to withdraw)
    """
    tier = (vip_status or "free").lower().strip()
    if tier == "pro":
        return 311
    if tier == "elite":
        return 420
    return 240  # free / fallback

raw_webhook_url = os.getenv("WEBHOOK_URL", "").strip()
if not raw_webhook_url or "your-domain" in raw_webhook_url:
    WEBHOOK_URL = "https://manatqazan.vercel.app"
else:
    WEBHOOK_URL = raw_webhook_url.rstrip("/")


# ── Safe UPSERT helper ─────────────────────────────────────────────────
SUPPORTED_LANGS = ['az', 'tr', 'en', 'ru']

def _detect_language(tg_user) -> str:
    """Detect user language from Telegram language_code using prefix matching."""
    lang_code = getattr(tg_user, 'language_code', None) or ''
    lang_code = lang_code.lower().strip()
    if lang_code.startswith('az'):
        return 'az'
    elif lang_code.startswith('tr'):
        return 'tr'
    elif lang_code.startswith('ru'):
        return 'ru'
    elif lang_code.startswith('en'):
        return 'en'
    return 'en'


# ── Bot Locales (Çat Dili Lüğəti) ─────────────────────────────────────
BOT_LOCALES = {
    'az': {
        'choose_lang':    "🌐 <b>Xoş gəldiniz!</b>\n\nZəhmət olmasa bot dilini seçin:",
        'lang_set':       "✅ Dil Azərbaycan dilinə təyin edildi!",
        'welcome_new':    (
            "🎉 <b>VibeCash-a xoş gəlmisiniz!</b>\n\n"
            "Salam, <b>{name}</b>! 👋\n\n"
            "📺 Qısa videolar izləyin və hər video üçün <b>{mc} VC</b> qazanın.\n"
            "📊 Gündəlik limit: <b>50 video klik</b> (hər mərhələ 25 video klik)\n"
            "👥 Dostlarınızı dəvət edin və <b>ömürlük 10% bonus</b> qazanın!"
            "\n\n💡 İpucu: Sistemi yeniləmək üçün /start yaza bilərsiniz!"
        ),
        'welcome_back':   "👋 <b>Yenidən xoş gəldiniz, {name}!</b>\n\n🪙 Balans: <b>{balance} VC</b>\n📈 Ümumi qazanc: <b>{total} VC</b>\n\nDaha çox qazanmağa hazırsınız? Aşağıdakı düyməyə toxunun! 👇\n\n💡 İpucu: Sistemi yeniləmək üçün /start yaza bilərsiniz!",
        'referral_msg':   "\n\n🤝 <b>Sizi dostunuz dəvət edib!</b> Onlar sizin qazancınızdan ömürlük 10% bonus qazanacaqlar.",
        'btn_video':      "🎬 Video İzlə & {mc} VC Qazan",
        'btn_balance':    "💰 Balansım",
        'btn_referral':   "👥 Referal Proqramı",
        'btn_how':        "ℹ️ Necə İşləyir?",
        'btn_withdraw':   "💰 Çıxarış",
        'btn_start':      "🚀 Başlat",
        'btn_lang_settings': "🌐 Dil Seçimi / Language ⚙️",
        # ── Balance screen ──
        'balance_title':    "💰 <b>Balansınız</b>",
        'balance_mc_row':   "🪙 <b>Vibe Coins:</b>",
        'balance_earn_row': "📈 <b>Ümumi Qazanc:</b>",
        'balance_s1_row':   "1️⃣ <b>Mərhələ 1:</b>",
        'balance_s2_row':   "2️⃣ <b>Mərhələ 2:</b>",
        'balance_locked':   "Kilidli 🔒",
        'balance_active':   "Aktiv 🟢",
        'balance_lock_rem': "🔒 Kilidli ({h:02d}s {m:02d}d qalıb)",
        # ── Referral screen ──
        'referral_title':   "👥 <b>Referal Proqramı</b>",
        'referral_desc':    "Dəvət linkinizi paylaşın və dostlarınızın izlədiyi hər videodan <b>ömürlük 10% bonus</b> qazanın!",
        'referral_link_lbl':"🔗 <b>Referal Linkiniiz:</b>",
        'referral_invited': "👤 <b>Dəvət Edilənlər:</b>",
        'referral_earned':  "🪙 <b>Referal Qazancı:</b>",
        'referral_azn':     "💵 <b>Referal AZN:</b>     {amount:,.4f} AZN",
        'referral_tip':     "💡 <i>Dəvət etdiyiniz hər şəxsin qazandığı VC-dən avtomatik 10% bonus qazanırsınız!</i>",
        # ── How it works ──
        'how_title':        "ℹ️ <b>VibeCash Layihəsi Haqqında Məlumat</b>",
        'how_body':         (
            "Platformamızın işləmə məntiqi çox bəsitdir:\n"
            "1️⃣ '<b>🎬 Video İzlə & {mc} VC Qazan</b>' düyməsinə toxunaraq qısa video reklamlar izliyirsiniz.\n"
            "2️⃣ Hər uğurlu izləmə üçün balansınıza anında <b>{mc} VC</b> (Vibe Coin) əlavə olunur.\n"
            "3️⃣ Dostlarınızı dəvət edərək onların qazancından da əlavə bonuslar əldə edirsiniz.\n\n"
            "💰 <b>Çıxarış və Balans Mexanizmi:</b>\n"
            "Yığılan VC xalları sistem daxilində real Azərbaycan Manatına (AZN) konvertasiya olunur. "
            "Minimum çıxarış limiti 10 AZN - 100 AZN təşkil edir. Bu limitə çatdıqdan sonra qazancınızı rahatlıqla "
            "şəxsi elektron pul kisələrinə (məsələn, m10) və ya bank kartınıza nağdlaşdıra bilərsiniz!\n\n"
            "Hər hansı bir sualınız yaranarsa, dəstək komandası ilə əlaqə saxlaya bilərsiniz. "
            "İndi ilk videonuzu izləyin və qazanmağa başlayın! 🚀"
        ),
        # ── Withdraw ──
        'withdraw_below_limit': (
            "❌ Çıxarış uğursuz oldu. Minimum çıxarış limiti 10 AZN - 100 AZN təşkil edir.\n\n"
            "💰 Sizin hazırkı balansınız: <b>{amount:.4f} AZN</b>\n\n"
            "🚀 <b>Limiti necə daha sürətli tamamlamaq olar?</b>\n"
            "Daha çox video izləməklə yanaşı, <b>dostlarınızı dəvət edərək</b> daha böyük məbləğlər qazana bilərsiniz! "
            "Dəvət etdiyiniz hər dostunuzun izlədiyi reklamlardan sizə avtomatik <b>ömürlük 10% bonus</b> gələcək. "
            "Linkinizi paylaşın və hədəfə sürətlə çatın! 👥💸\n\n"
            "Gözləmək sənlik deyil? ⚡ Mağaza (Store) bölməsindən PRO və ya ELITE paketlərinə keç, VC qazancını uçur! Gündəlik limiti saniyələr daxilində vur, Liderlər siyahısında zirvəyə yüksəl və qazancını gözləmədən anında nağdlaşdır! 🚀"
        ),
        'withdraw_ok': (
            "✅ Təbriklər! Çıxarış limitini keçmisiniz. Zəhmət olmasa pulu köçürmək "
            "istədiyiniz m10 nömrənizi və ya Bank Kartı məlumatlarınızı (Ad, Soyad, 16 rəqəmli kod) bura yazın:"
        ),
        # ── Error / not registered ──
        'not_registered': "⚠️ Siz hələ qeydiyyatdan keçməmisiniz. Zəhmət olmasa əvvəlcə /start göndərin.",
    },
    'tr': {
        'choose_lang':    "🌐 <b>Hoş geldiniz!</b>\n\nLütfen bot dilini seçin:",
        'lang_set':       "✅ Dil Türkçe olarak ayarlandı!",
        'welcome_new':    (
            "🎉 <b>VibeCash'a hoş geldiniz!</b>\n\n"
            "Merhaba, <b>{name}</b>! 👋\n\n"
            "📺 Kısa videolar izleyin ve her video için <b>{mc} VC</b> kazanın.\n"
            "📊 Günlük limit: <b>50 video klik</b> (her aşama 25 video klik)\n"
            "👥 Arkadaşlarınızı davet edin ve <b>ömür boyu %10 bonus</b> kazanın!"
            "\n\n💡 İpucu: Sistemi yenilemek için /start yazabilirsiniz!"
        ),
        'welcome_back':   "👋 <b>Tekrar hoş geldiniz, {name}!</b>\n\n🪙 Bakiye: <b>{balance} VC</b>\n📈 Toplam kazanç: <b>{total} VC</b>\n\nDaha fazla kazanmaya hazır mısınız? Aşağıdaki butona dokunun! 👇\n\n💡 İpucu: Sistemi yenilemek için /start yazabilirsiniz!",
        'referral_msg':   "\n\n🤝 <b>Sizi bir arkadaşınız davet etti!</b> Kazancınızdan ömür boyu %10 bonus alacaklar.",
        'btn_video':      "🎬 Video İzle & {mc} VC Kazan",
        'btn_balance':    "💰 Bakiyem",
        'btn_referral':   "👥 Referans Programı",
        'btn_how':        "ℹ️ Nasıl Çalışır?",
        'btn_withdraw':   "💰 Çekim",
        'btn_start':      "🚀 Başlat",
        'btn_lang_settings': "🌐 Dil Seçimi / Language ⚙️",
        # ── Balance screen ──
        'balance_title':    "💰 <b>Bakiyeniz</b>",
        'balance_mc_row':   "🪙 <b>Vibe Coins:</b>",
        'balance_earn_row': "📈 <b>Toplam Kazanç:</b>",
        'balance_s1_row':   "1️⃣ <b>Aşama 1:</b>",
        'balance_s2_row':   "2️⃣ <b>Aşama 2:</b>",
        'balance_locked':   "Kilitli 🔒",
        'balance_active':   "Aktif 🟢",
        'balance_lock_rem': "🔒 Kilitli ({h:02d}s {m:02d}d kaldı)",
        # ── Referral screen ──
        'referral_title':   "👥 <b>Referans Programı</b>",
        'referral_desc':    "Davet bağlantınızı paylaşın ve arkadaşınızın izlediği her videodan <b>ömür boyu %10 bonus</b> kazanın!",
        'referral_link_lbl':"🔗 <b>Referans Bağlantınız:</b>",
        'referral_invited': "👤 <b>Davet Edilenler:</b>",
        'referral_earned':  "🪙 <b>Referans Kazancı:</b>",
        'referral_azn':     "💵 <b>Referans TRY:</b>     {amount:,.4f} TRY",
        'referral_tip':     "💡 <i>Davet ettiğiniz her kişinin kazandığı VC'den otomatik %10 bonus kazanırsınız!</i>",
        # ── How it works ──
        'how_title':        "ℹ️ <b>VibeCash Projesi Hakkında Bilgi</b>",
        'how_body':         (
            "Platformamızın çalışma mantığı çok basittir:\n"
            "1️⃣ '<b>🎬 Video İzle & {mc} VC Kazan</b>' butonuna dokunarak kısa video reklamlar izliyorsunuz.\n"
            "2️⃣ Her başarılı izleme için bakiyenize anında <b>{mc} VC</b> (Vibe Coin) ekleniyor.\n"
            "3️⃣ Arkadaşlarınızı davet ederek onun kazançlarından da ek bonuslar elde ediyorsunuz.\n\n"
            "💰 <b>Çekim ve Bakiye Mekanizması:</b>\n"
            "Biriktirilen VC puanları sistem içinde gerçek Türk Lirası (TRY) para birimine dönüştürülür. "
            "Minimum çekim limiti 275 TRY - 2750 TRY olarak belirlenmiştir. Bu limite ulaştıktan sonra kazancınızı kolayca "
            "Papara, İninal numaranıza veya Yerel Banka kartınıza çekebilirsiniz!\n\n"
            "Herhangi bir sorunuz olursa destek ekibiyle iletişime geçebilirsiniz. "
            "Şimdi ilk videonuzu izleyin ve kazanmaya başlayın! 🚀"
        ),
        # ── Withdraw ──
        'withdraw_below_limit': (
            "❌ Çekim başarısız oldu. Minimum çekim limiti 275 TRY - 2750 TRY olarak belirlenmiştir.\n\n"
            "💰 Mevcut bakiyeniz: <b>{amount:.4f} TRY</b>\n\n"
            "🚀 <b>Limiti nasıl daha hızlı tamamlarsınız?</b>\n"
            "Daha fazla video izlemenin yanı sıra, <b>arkadaşlarınızı davet ederek</b> daha büyük miktarlar kazanabilirsiniz! "
            "Davet ettiğiniz her arkadaşınızın izlediği reklamlardan size otomatik <b>ömür boyu %10 bonus</b> gelecek. "
            "Bağlantınızı paylaşın ve hedefe hızla ulaşın! 👥💸\n\n"
            "Beklemek sana göre değil mi? ⚡ Mağaza (Store) bölümünden PRO veya ELITE paketlerine geç, VC kazancını uçur! Günlük limiti saniyeler içinde erit, Liderler listesinde zirveye tırman ve kazancını beklemeden anında nakde çevir! 🚀"
        ),
        'withdraw_ok': (
            "✅ Tebrikler! Çekim limitini aştınız. Lütfen parayı transfer etmek "
            "istediğiniz Papara, İninal numaranızı veya Yerel Banka kartı bilgilerinizi (Ad, Soyad, 16 haneli kod) buraya yazın:"
        ),
        # ── Error / not registered ──
        'not_registered': "⚠️ Henüz kayıt olmadınız. Lütfen önce /start gönderin.",
    },
    'en': {
        'choose_lang':    "🌐 <b>Welcome!</b>\n\nPlease choose the bot language:",
        'lang_set':       "✅ Language set to English!",
        'welcome_new':    (
            "🎉 <b>Welcome to VibeCash!</b>\n\n"
            "Hello, <b>{name}</b>! 👋\n\n"
            "📺 Watch short videos and earn <b>{mc} VC</b> per video.\n"
            "📊 Daily limit: <b>50 video clicks</b> (25 video clicks per level)\n"
            "👥 Invite your friends and earn a <b>lifetime 10% bonus</b>!"
            "\n\n💡 Tip: You can type /start at any time to refresh the system!"
        ),
        'welcome_back':   "👋 <b>Welcome back, {name}!</b>\n\n🪙 Balance: <b>{balance} VC</b>\n📈 Total earned: <b>{total} VC</b>\n\nReady to earn more? Tap the button below! 👇\n\n💡 Tip: You can type /start at any time to refresh the system!",
        'referral_msg':   "\n\n🤝 <b>You were invited by a friend!</b> They will earn a lifetime 10% bonus from your earnings.",
        'btn_video':      "🎬 Watch Videos & Earn {mc} VC",
        'btn_balance':    "💰 My Balance",
        'btn_referral':   "👥 Referral Program",
        'btn_how':        "ℹ️ How It Works?",
        'btn_withdraw':   "💰 Withdraw",
        'btn_start':      "🚀 Start",
        'btn_lang_settings': "🌐 Change Language / Dil Seçimi ⚙️",
        # ── Balance screen ──
        'balance_title':    "💰 <b>Your Balance</b>",
        'balance_mc_row':   "🪙 <b>Vibe Coins:</b>",
        'balance_earn_row': "📈 <b>Total Earned:</b>",
        'balance_s1_row':   "1️⃣ <b>Level 1:</b>",
        'balance_s2_row':   "2️⃣ <b>Level 2:</b>",
        'balance_locked':   "Locked 🔒",
        'balance_active':   "Active 🟢",
        'balance_lock_rem': "🔒 Locked ({h:02d}h {m:02d}m remaining)",
        # ── Referral screen ──
        'referral_title':   "👥 <b>Referral Program</b>",
        'referral_desc':    "Share your invite link and earn a <b>lifetime 10% bonus</b> from every video your friends watch!",
        'referral_link_lbl':"🔗 <b>Your Referral Link:</b>",
        'referral_invited': "👤 <b>People Invited:</b>",
        'referral_earned':  "🪙 <b>Referral Earnings:</b>",
        'referral_azn':     "💵 <b>Referral USDT:</b>     {amount:,.4f} USDT",
        'referral_tip':     "💡 <i>You automatically earn a 10% bonus from the VC earned by everyone you invite!</i>",
        # ── How it works ──
        'how_title':        "ℹ️ <b>About VibeCash</b>",
        'how_body':         (
            "Our platform's logic is very simple:\n"
            "1️⃣ Tap the '<b>🎬 Watch Videos & Earn {mc} VC</b>' button to watch short video ads.\n"
            "2️⃣ For each successful watch, <b>{mc} VC</b> (Vibe Coin) is instantly added to your balance.\n"
            "3️⃣ Invite your friends and earn extra bonuses from their activity too.\n\n"
            "💰 <b>Withdrawal & Balance Mechanism:</b>\n"
            "Accumulated VC points are converted to USDT (Crypto) within the system. "
            "The withdrawal limit is 6 USDT - 60 USDT. Once you reach this limit, you can easily "
            "cash out to your crypto wallets (e.g., TRC-20, BEP-20) or global payment systems!\n\n"
            "If you have any questions, feel free to contact the support team. "
            "Watch your first video now and start earning! 🚀"
        ),
        # ── Withdraw ──
        'withdraw_below_limit': (
            "❌ Withdrawal failed. The withdrawal limit is 6 USDT - 60 USDT.\n\n"
            "💰 Your current balance: <b>{amount:.4f} USDT</b>\n\n"
            "🚀 <b>How to reach the limit faster?</b>\n"
            "Watch more videos and <b>invite your friends</b> to earn larger amounts! "
            "You'll automatically earn a <b>lifetime 10% bonus</b> from every ad your referrals watch. "
            "Share your link and reach your goal faster! 👥💸\n\n"
            "Hate waiting? ⚡ Head over to the Store and upgrade to PRO or ELITE to skyrocket your VC earnings! Smash through the daily limits in seconds, climb the leaderboard to the very top, and cash out instantly without waiting! 🚀"
        ),
        'withdraw_ok': (
            "✅ Congratulations! You've reached the withdrawal limit. Please provide your "
            "crypto wallet address (e.g., TRC-20, BEP-20) or global payment details to process the transfer:"
        ),
        # ── Error / not registered ──
        'not_registered': "⚠️ You are not registered yet. Please send /start first.",
    },
    'ru': {
        'choose_lang':    "🌐 <b>Добро пожаловать!</b>\n\nПожалуйста, выберите язык бота:",
        'lang_set':       "✅ Язык установлен на Русский!",
        'welcome_new':    (
            "🎉 <b>Добро пожаловать в VibeCash!</b>\n\n"
            "Привет, <b>{name}</b>! 👋\n\n"
            "📺 Смотрите короткие видео и зарабатывайте <b>{mc} VC</b> за каждое видео.\n"
            "📊 Ежедневный лимит: <b>50 video klik</b> (25 video klik за уровень)\n"
            "👥 Приглашайте друзей и зарабатывайте <b>пожизненный бонус 10%</b>!"
            "\n\n💡 Подсказка: Вы можете написать /start в любое время, чтобы обновить систему!"
        ),
        'welcome_back':   "👋 <b>С возвращением, {name}!</b>\n\n🪙 Баланс: <b>{balance} VC</b>\n📈 Всего заработано: <b>{total} VC</b>\n\nГотовы зарабатывать больше? Нажмите на кнопку ниже! 👇\n\n💡 Подсказка: Вы можете написать /start в любое время, чтобы обновить систему!",
        'referral_msg':   "\n\n🤝 <b>Вас пригласил друг!</b> Они будут получать пожизненный бонус 10% с ваших заработков.",
        'btn_video':      "🎬 Смотреть видео & Заработать {mc} VC",
        'btn_balance':    "💰 Мой баланс",
        'btn_referral':   "👥 Реферальная программа",
        'btn_how':        "ℹ️ Как это работает?",
        'btn_withdraw':   "💰 Вывод",
        'btn_start':      "🚀 Запустить",
        'btn_lang_settings': "🌐 Смена языка / Language ⚙️",
        # ── Balance screen ──
        'balance_title':    "💰 <b>Ваш баланс</b>",
        'balance_mc_row':   "🪙 <b>Vibe Coins:</b>",
        'balance_earn_row': "📈 <b>Всего заработано:</b>",
        'balance_s1_row':   "1️⃣ <b>Уровень 1:</b>",
        'balance_s2_row':   "2️⃣ <b>Уровень 2:</b>",
        'balance_locked':   "Заблокировано 🔒",
        'balance_active':   "Активно 🟢",
        'balance_lock_rem': "🔒 Заблок. ({h:02d}ч {m:02d}м осталось)",
        # ── Referral screen ──
        'referral_title':   "👥 <b>Реферальная программа</b>",
        'referral_desc':    "Поделитесь своей реферальной ссылкой и зарабатывайте <b>пожизненный бонус 10%</b> с каждого видео, просмотренного вашими друзьями!",
        'referral_link_lbl':"🔗 <b>Ваша реферальная ссылка:</b>",
        'referral_invited': "👤 <b>Приглашено:</b>",
        'referral_earned':  "🪙 <b>Реферальный заработок:</b>",
        'referral_azn':     "💵 <b>Реферальные USDT:</b> {amount:,.4f} USDT",
        'referral_tip':     "💡 <i>Вы автоматически получаете 10% бонус от VC, заработанных каждым приглашенным вами пользователем!</i>",
        # ── How it works ──
        'how_title':        "ℹ️ <b>О проекте VibeCash</b>",
        'how_body':         (
            "Логика работы нашей платформы очень проста:\n"
            "1️⃣ Нажмите на кнопку '<b>🎬 Смотреть видео & Заработать {mc} VC</b>', чтобы смотреть короткую видеорекламу.\n"
            "2️⃣ За каждый успешный просмотр на ваш баланс мгновенно зачисляется <b>{mc} VC</b> (Vibe Coin).\n"
            "3️⃣ Приглашайте друзей и получайте дополнительные бонусы с их активности.\n\n"
            "💰 <b>Механизм вывода и баланса:</b>\n"
            "Накопленные VC-баллы конвертируются в USDT (Крипто) внутри системы. "
            "Лимит на вывод составляет 6 USDT - 60 USDT. Достигнув этого лимита, вы легко можете "
            "вывести средства на свои криптокошельки (например, TRC-20, BEP-20) или глобальные платежные системы!\n\n"
            "Если у вас возникнут вопросы, вы можете обратиться в службу поддержки. "
            "Смотрите первое видео прямо сейчас и начинайте зарабатывать! 🚀"
        ),
        # ── Withdraw ──
        'withdraw_below_limit': (
            "❌ Вывод не удался. Лимит на вывод составляет 6 USDT - 60 USDT.\n\n"
            "💰 Ваш текущий баланс: <b>{amount:.4f} USDT</b>\n\n"
            "🚀 <b>Как быстрее достичь лимита?</b>\n"
            "Смотрите больше видео и <b>приглашайте друзей</b>, чтобы зарабатывать больше! "
            "Вы автоматически получите <b>пожизненный бонус 10%</b> с каждой рекламы, просмотренной вашими рефералами. "
            "Поделитесь ссылкой и быстрее достигните цели! 👥💸\n\n"
            "Не любишь ждать? ⚡ Залетай в Магазин (Store), хватай PRO или ELITE и разгоняй свой заработок VC до небес! Закрывай дневные лимиты за секунды, взлетай на вершину Топа лидеров и выводи кэш моментально без ожидания! 🚀"
        ),
        'withdraw_ok': (
            "✅ Поздравляем! Вы достигли лимита вывода. Пожалуйста, укажите адрес своего "
            "криптокошелька (например, TRC-20, BEP-20) или реквизиты глобальной платежной системы для перевода:"
        ),
        # ── Error / not registered ──
        'not_registered': "⚠️ Вы ещё не зарегистрированы. Пожалуйста, сначала отправьте /start.",
    },
}

# ── Localized system-refresh hint (appended to every menu screen) ──────
# Defined once here; referenced by _show_balance, _show_referral,
# _show_how_it_works, and _handle_withdraw so the hint is always in sync.
SYSTEM_REFRESH_HINT: dict[str, str] = {
    'az': "\n\n💡 <b>İpucu:</b> Sistemi yeniləmək üçün /start yaza bilərsiniz!",
    'tr': "\n\n💡 <b>İpucu:</b> Sistemi yenilemek için /start yazabilirsiniz!",
    'ru': "\n\n💡 <b>Подсказка:</b> Для обновления системы вы можете написать /start!",
    'en': "\n\n💡 <b>Tip:</b> You can write /start to refresh the system!",
}


def get_lang_select_keyboard() -> InlineKeyboardMarkup:
    """Returns 4-button language selection InlineKeyboard for new users."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇦🇿 Azərbaycan dili", callback_data="set_bot_lang:az"),
        ],
        [
            InlineKeyboardButton(text="🇹🇷 Türkçe", callback_data="set_bot_lang:tr"),
        ],
        [
            InlineKeyboardButton(text="🇬🇧 English", callback_data="set_bot_lang:en"),
        ],
        [
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="set_bot_lang:ru"),
        ],
    ])


def get_main_keyboard(lang: str, vip_status: str | None = None) -> InlineKeyboardMarkup:
    """Returns the main InlineKeyboard in the specified language."""
    loc = BOT_LOCALES.get(lang, BOT_LOCALES['en'])
    tier_mc = _get_mc_for_tier(vip_status)
    btn_video_text = loc['btn_video'].format(mc=tier_mc)
    webapp_url = f"https://manatqazan.vercel.app/?lang={lang}&v={int(datetime.now().timestamp())}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=btn_video_text, web_app=types.WebAppInfo(url=webapp_url))],
        [
            InlineKeyboardButton(text=loc['btn_balance'], callback_data="balance"),
            InlineKeyboardButton(text=loc['btn_referral'], callback_data="referral"),
        ],
        [
            InlineKeyboardButton(text=loc['btn_how'], callback_data="how_it_works"),
            InlineKeyboardButton(text=loc['btn_withdraw'], callback_data="withdraw"),
        ],
        [
            InlineKeyboardButton(text=loc['btn_lang_settings'], callback_data="show_lang_menu"),
        ],
    ])


# ── LanguageUpdateMiddleware (DB dilini oxuyur, əzmür) ─────────────────
class LanguageUpdateMiddleware(BaseMiddleware):
    """
    Reads the user's language from the DB and attaches it to handler data.
    Does NOT override language chosen by the user via set_bot_lang.
    """
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        tg_user = getattr(event, 'from_user', None)
        user_lang = 'en'
        if tg_user:
            async with async_session() as session:
                stmt = select(User).where(User.telegram_id == tg_user.id)
                res = await session.execute(stmt)
                user = res.scalar_one_or_none()
            
            if user and user.language in BOT_LOCALES:
                user_lang = user.language
            else:
                user_lang = _detect_language(tg_user)
        
        data['user_lang'] = user_lang
        return await handler(event, data)

router.message.outer_middleware(LanguageUpdateMiddleware())
router.callback_query.outer_middleware(LanguageUpdateMiddleware())


async def _upsert_user(
    session,
    telegram_id: int,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
    referrer_id: int | None = None,
    language: str = 'az',
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
        language=language,
    )
    if referrer_id is not None:
        values["referrer_id"] = referrer_id

    # Fields to refresh on conflict (user reopened bot / changed profile)
    update_on_conflict = dict(
        username=username,
        first_name=first_name,
        last_name=last_name,
        language=language,
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


# ── Admin new-user notification ────────────────────────────────────────
async def _notify_admin_new_user(bot, user_id: int, first_name: str | None, username: str | None, referrer_text: str = "Doğrudan Keçid (Yoxdur)") -> None:
    """
    Send a real-time notification to ADMIN_ID about a brand-new user registration.
    Runs as a fire-and-forget background task — NEVER raises; registration flow must not be affected.
    """
    if ADMIN_ID is None:
        return
    try:
        uname_display = f"@{username}" if username else "Yoxdur"
        text = (
            "\U0001f680 <b>Yeni Istifadeci Qosuldu!</b>\n"
            f"\U0001f464 <b>Ad:</b> {first_name or 'Namelum'}\n"
            f"\U0001f194 <b>ID:</b> <code>{user_id}</code>\n"
            f"\U0001f3f7 <b>Username:</b> {uname_display}\n"
            f"👥 <b>Dəvət Edən:</b> {referrer_text}"
        )
        await bot.send_message(chat_id=ADMIN_ID, text=text, parse_mode="HTML")
    except Exception as notify_err:
        logger.warning("[ADMIN NOTIFY] Failed to send new-user notification: %s", notify_err)


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

    referrer_text = "Doğrudan Keçid (Yoxdur)"

    async with async_session() as session:
        try:
            # Check if user already exists
            existing_stmt = select(User).where(User.telegram_id == tg_user.id)
            existing_result = await session.execute(existing_stmt)
            existing_user = existing_result.scalar_one_or_none()

            if existing_user:
                # Returning user – update profile fields, keep their chosen language
                existing_user.username = tg_user.username
                existing_user.first_name = tg_user.first_name
                existing_user.last_name = tg_user.last_name
                await session.commit()
                await _send_welcome_back(message, existing_user)
                return

            # NEW USER: Register with NULL language first, show lang selection
            # Validate referrer exists
            if referrer_tg_id:
                ref_stmt = select(User).where(User.telegram_id == referrer_tg_id)
                ref_result = await session.execute(ref_stmt)
                referrer = ref_result.scalar_one_or_none()
                if referrer:
                    referrer.referral_count += 1
                    session.add(referrer)
                    ref_uname = f"@{referrer.username}" if referrer.username else "Namelum"
                    referrer_text = f"{ref_uname} (ID: {referrer.telegram_id})"
                else:
                    referrer_tg_id = None
                    if referral_code:
                        referrer_text = f"Kampaniya: {referral_code}"
            elif referral_code:
                if referral_code.lower() == "tiktok_bio":
                    referrer_text = "TikTok Bio Kampaniyası 🚀"
                else:
                    referrer_text = f"Kampaniya: {referral_code}"

            # Register with detected fallback lang; user will override via callback
            tg_detected = _detect_language(tg_user)
            await _upsert_user(
                session,
                telegram_id=tg_user.id,
                username=tg_user.username,
                first_name=tg_user.first_name,
                last_name=tg_user.last_name,
                referrer_id=referrer_tg_id,
                language=tg_detected,
            )
            await session.commit()
            logger.info("[UPSERT] New user %s (referrer=%s) registered.", tg_user.id, referrer_tg_id)

        except Exception as e:
            await session.rollback()
            logger.exception("[UPSERT] Failed to upsert user %s: %s", tg_user.id, e)
            await message.answer("\u26a0\ufe0f Xata bas verdi. Zahmat olmasa bir az sonra yenidan cahd edin.")
            return

    # Fire-and-forget: admin notification runs concurrently, does not delay user response
    asyncio.create_task(_notify_admin_new_user(
        bot=message.bot,
        user_id=tg_user.id,
        first_name=tg_user.first_name,
        username=tg_user.username,
        referrer_text=referrer_text,
    ))

    # Show language selection to new user – greeting localized to their native Telegram language
    _tg_lang = _detect_language(tg_user)
    _lang_greetings = {
        'az': "🌐 <b>Xoş gəldiniz!</b>\n\nZəhmət olmasa ölkənizi seçin:",
        'tr': "🌐 <b>Hoş geldiniz!</b>\n\nLütfen ülkenizi seçin:",
        'ru': "🌐 <b>Добро пожаловать!</b>\n\nПожалуйста, выберите вашу страну:",
        'en': "🌐 <b>Welcome!</b>\n\nPlease select your country:",
    }
    await message.answer(
        _lang_greetings.get(_tg_lang, _lang_greetings['en']),
        reply_markup=get_lang_select_keyboard(),
    )


@router.message(CommandStart())
async def cmd_start(message: types.Message) -> None:
    """Handle plain /start without a referral code."""
    tg_user = message.from_user
    if not tg_user:
        return

    async with async_session() as session:
        try:
            # Check if user already exists
            existing_stmt = select(User).where(User.telegram_id == tg_user.id)
            existing_result = await session.execute(existing_stmt)
            existing_user = existing_result.scalar_one_or_none()

            if existing_user:
                # Returning user – update profile fields, keep their chosen language
                existing_user.username = tg_user.username
                existing_user.first_name = tg_user.first_name
                existing_user.last_name = tg_user.last_name
                await session.commit()
                await _send_welcome_back(message, existing_user)
                return

            # NEW USER: Register with TG-detected lang, then show lang selection
            tg_detected = _detect_language(tg_user)
            await _upsert_user(
                session,
                telegram_id=tg_user.id,
                username=tg_user.username,
                first_name=tg_user.first_name,
                last_name=tg_user.last_name,
                language=tg_detected,
            )
            await session.commit()
            logger.info("[UPSERT] New user %s registered.", tg_user.id)

        except Exception as e:
            await session.rollback()
            logger.exception("[UPSERT] Failed to upsert user %s: %s", tg_user.id, e)
            await message.answer("\u26a0\ufe0f Xata bas verdi. Zahmat olmasa bir az sonra yenidan cahd edin.")
            return

    # Fire-and-forget: admin notification runs concurrently, does not delay user response
    asyncio.create_task(_notify_admin_new_user(
        bot=message.bot,
        user_id=tg_user.id,
        first_name=tg_user.first_name,
        username=tg_user.username,
    ))

    # Show language selection to new user – greeting localized to their native Telegram language
    _tg_lang = _detect_language(tg_user)
    _lang_greetings = {
        'az': "🌐 <b>Xoş gəldiniz!</b>\n\nZəhmət olmasa ölkənizi seçin:",
        'tr': "🌐 <b>Hoş geldiniz!</b>\n\nLütfen ülkenizi seçin:",
        'ru': "🌐 <b>Добро пожаловать!</b>\n\nПожалуйста, выберите вашу страну:",
        'en': "🌐 <b>Welcome!</b>\n\nPlease select your country:",
    }
    await message.answer(
        _lang_greetings.get(_tg_lang, _lang_greetings['en']),
        reply_markup=get_lang_select_keyboard(),
    )

@router.message(Command("lang"))
async def cmd_lang(message: types.Message) -> None:
    """Allow users to change their language at any time."""
    await message.answer(
        "🌐 <b>Welcome / Xoş gəldiniz / Hoş geldiniz / Добро пожаловать!</b>\n\n"
        "Please choose your language / Dil seçin:",
        reply_markup=get_lang_select_keyboard(),
    )


# ── set_bot_lang Callback Handler ───────────────────────────────────────
@router.callback_query(lambda c: c.data and c.data.startswith("set_bot_lang:"))
async def cb_set_bot_lang(callback: types.CallbackQuery) -> None:
    """Handle language selection button for new users."""
    tg_user = callback.from_user
    chosen_lang = callback.data.split(":", 1)[1]
    if chosen_lang not in SUPPORTED_LANGS:
        chosen_lang = 'en'

    loc = BOT_LOCALES[chosen_lang]

    # Save chosen language to DB
    async with async_session() as session:
        stmt = select(User).where(User.telegram_id == tg_user.id)
        res = await session.execute(stmt)
        db_user = res.scalar_one_or_none()
        if db_user:
            db_user.language = chosen_lang
            await session.commit()
        else:
            # Edge case: user not in DB yet — register now
            tg_detected = _detect_language(tg_user)
            await _upsert_user(
                session,
                telegram_id=tg_user.id,
                username=tg_user.username,
                first_name=tg_user.first_name,
                last_name=tg_user.last_name,
                language=chosen_lang,
            )
            await session.commit()
            # Re-fetch
            res2 = await session.execute(select(User).where(User.telegram_id == tg_user.id))
            db_user = res2.scalar_one_or_none()

    logger.info("[LANG] User %s chose language: %s", tg_user.id, chosen_lang)
    await callback.answer(loc['lang_set'], show_alert=False)

    # Set menu button WebApp URL with chosen lang
    webapp_url = f"https://manatqazan.vercel.app/?lang={chosen_lang}&v={int(datetime.now().timestamp())}"
    try:
        await callback.bot.set_chat_menu_button(
            chat_id=tg_user.id,
            menu_button=MenuButtonWebApp(
                text=loc['btn_start'],
                web_app=types.WebAppInfo(url=webapp_url)
            )
        )
    except Exception:
        pass

    # Build welcome message — use tier-aware VC for new users (always free at first pick)
    name = tg_user.first_name or "friend"
    tier_mc = _get_mc_for_tier(getattr(db_user, 'vip_status', 'free') if db_user else 'free')
    welcome_text = loc['welcome_new'].format(
        name=name, mc=tier_mc, limit=DAILY_LIMIT
    )

    # Edit the language selection message → welcome + main keyboard
    if callback.message and isinstance(callback.message, types.Message):
        vip_status = getattr(db_user, 'vip_status', 'free') if db_user else 'free'
        await callback.message.edit_text(
            welcome_text,
            reply_markup=get_main_keyboard(chosen_lang, vip_status=vip_status),
        )


# ── /balance ────────────────────────────────────────────────────────────
@router.message(Command("balance"))
async def cmd_balance(message: types.Message) -> None:
    """Show the user's current VC balance and AZN equivalent."""
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
        await message.answer(BOT_LOCALES['az']['not_registered'])
        return

    lang = user.language if user.language in BOT_LOCALES else 'en'
    loc = BOT_LOCALES[lang]

    now = datetime.now(timezone.utc)
    today = now.date()

    # Dynamic daily reset
    if user.last_watch_date and _get_utc_date(user.last_watch_date) != today:
        async with async_session() as reset_session:
            stmt = select(User).where(User.telegram_id == tg_user.id)
            res = await reset_session.execute(stmt)
            db_user = res.scalar_one()
            db_user.session_1_count = 0
            db_user.session_2_count = 0
            db_user.videos_today = 0
            if db_user.session_1_completion_time is not None:
                from datetime import timedelta
                if db_user.session_1_completion_time.tzinfo is None:
                    db_user.session_1_completion_time = db_user.session_1_completion_time.replace(tzinfo=timezone.utc)
                crossday_unlock = db_user.session_1_completion_time + timedelta(hours=3)
                if now >= crossday_unlock:
                    db_user.session_1_completion_time = None
            await reset_session.commit()
            user = db_user

    from main import _get_vip_params
    session_limit, daily_limit, _ = _get_vip_params(user.vip_status, now)
    session_2_limit = daily_limit - session_limit

    session_1_count = user.session_1_count
    session_2_count = user.session_2_count
    session_1_completion_time = user.session_1_completion_time
    if session_1_completion_time is not None and session_1_completion_time.tzinfo is None:
        session_1_completion_time = session_1_completion_time.replace(tzinfo=timezone.utc)
        
    balance_mc = user.balance_mc
    total_earned_mc = user.total_earned_mc

    # Calculate lock text using localized strings
    s2_status = loc['balance_locked']
    if session_1_count >= session_limit:
        if session_1_completion_time is None:
            s2_status = loc['balance_active']
        else:
            from datetime import timedelta
            unlock_time = session_1_completion_time + timedelta(hours=3)
            if now < unlock_time:
                remaining = unlock_time - now
                h, remainder = divmod(int(remaining.total_seconds()), 3600)
                m, _ = divmod(remainder, 60)
                s2_status = loc['balance_lock_rem'].format(h=h, m=m)
            else:
                s2_status = loc['balance_active']

    hint = SYSTEM_REFRESH_HINT.get(lang, SYSTEM_REFRESH_HINT['en'])
    await message.answer(
        f"{loc['balance_title']}\n\n"
        f"┌─────────────────────────\n"
        f"│ {loc['balance_mc_row']}  {balance_mc:,.0f} VC\n"
        f"│ {loc['balance_earn_row']} {total_earned_mc:,.0f} VC\n"
        f"├─────────────────────────\n"
        f"│ {loc['balance_s1_row']}  {session_1_count}/{session_limit} klik\n"
        f"│ {loc['balance_s2_row']}  {session_2_count}/{session_2_limit} klik ({s2_status})\n"
        f"└─────────────────────────"
        + hint,
        parse_mode="HTML",
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
        await message.answer(BOT_LOCALES['az']['not_registered'])
        return

    lang = user.language if user.language in BOT_LOCALES else 'en'
    loc = BOT_LOCALES[lang]

    bot_info = await message.bot.me()
    bot_username = bot_info.username
    referral_link = f"https://t.me/{bot_username}?start={tg_user.id}"
    
    # Dynamic fiat calculation according to selected language
    if lang == 'az':
        ref_fiat = user.referral_earnings_mc
    elif lang == 'tr':
        ref_fiat = user.referral_earnings_mc / (_WITHDRAWAL_THRESHOLD_MC / MIN_WITHDRAWAL_TRY)
    else:  # en, ru — USDT
        ref_fiat = user.referral_earnings_mc / (_WITHDRAWAL_THRESHOLD_MC / 6.0)

    bonus_per_video = MC_PER_VIDEO * 10 // 100

    hint = SYSTEM_REFRESH_HINT.get(lang, SYSTEM_REFRESH_HINT['en'])
    await message.answer(
        f"{loc['referral_title']}\n\n"
        f"{loc['referral_desc']}\n\n"
        f"{loc['referral_link_lbl']}\n"
        f"<code>{referral_link}</code>\n\n"
        f"┌─────────────────────────\n"
        f"│ {loc['referral_invited']}   {user.referral_count}\n"
        f"│ {loc['referral_earned']}   {user.referral_earnings_mc:,.0f} VC\n"
        f"│ {loc['referral_azn'].format(amount=ref_fiat)}\n"
        f"└─────────────────────────\n\n"
        + loc['referral_tip'].format(mc=MC_PER_VIDEO, bonus=bonus_per_video)
        + hint,
        parse_mode="HTML",
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
        await _show_how_it_works(callback.from_user, callback.message)


@router.callback_query(lambda c: c.data == "withdraw")
async def cb_withdraw(callback: types.CallbackQuery) -> None:
    """Inline button shortcut for withdrawal."""
    await callback.answer()
    if callback.message and isinstance(callback.message, types.Message):
        await _handle_withdraw(callback.from_user, callback.message)


@router.callback_query(lambda c: c.data == "show_lang_menu")
async def cb_show_lang_menu(callback: types.CallbackQuery) -> None:
    """Inline button shortcut to show language selection menu."""
    await callback.answer()
    if callback.message and isinstance(callback.message, types.Message):
        await callback.message.answer(
            "🌐 <b>Welcome / Xoş gəldiniz / Hoş geldiniz / Добро пожаловать!</b>\n\n"
            "Please choose your language / Dil seçin:",
            reply_markup=get_lang_select_keyboard(),
        )


# ── Text Message Handlers (Reply Keyboard — all 4 languages) ───────────
_BALANCE_TEXTS   = {loc['btn_balance']  for loc in BOT_LOCALES.values()}
_REFERRAL_TEXTS  = {loc['btn_referral'] for loc in BOT_LOCALES.values()}
_HOW_TEXTS       = {loc['btn_how']      for loc in BOT_LOCALES.values()}
_WITHDRAW_TEXTS  = {loc['btn_withdraw'] for loc in BOT_LOCALES.values()}

@router.message(lambda m: m.text in _BALANCE_TEXTS)
async def txt_balance(message: types.Message) -> None:
    if message.from_user:
        await _show_balance(message.from_user, message)

@router.message(lambda m: m.text in _REFERRAL_TEXTS)
async def txt_referral(message: types.Message) -> None:
    if message.from_user:
        await _show_referral(message.from_user, message)

@router.message(lambda m: m.text in _HOW_TEXTS)
async def txt_how_it_works(message: types.Message) -> None:
    if message.from_user:
        await _show_how_it_works(message.from_user, message)

@router.message(lambda m: m.text in _WITHDRAW_TEXTS)
async def txt_withdraw(message: types.Message) -> None:
    if message.from_user:
        await _handle_withdraw(message.from_user, message)


@router.message(lambda m: m.text and not m.text.startswith("/"))
async def handle_user_text_message(message: types.Message) -> None:
    # Ignore if it matches main keyboard button texts
    if message.text in _BALANCE_TEXTS or message.text in _REFERRAL_TEXTS or message.text in _HOW_TEXTS or message.text in _WITHDRAW_TEXTS:
        return
        
    tg_user = message.from_user
    if not tg_user:
        return
        
    async with async_session() as session:
        stmt = select(User).where(User.telegram_id == tg_user.id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
    if not user:
        return
        
    # If the user has enough balance to withdraw, we forward the message to admin
    if user.balance_mc >= _WITHDRAWAL_THRESHOLD_MC:
        if ADMIN_ID:
            uname_display = f"@{user.username}" if user.username else "Yoxdur"
            name_display = user.first_name or "Namelum"
            admin_text = (
                "📥 <b>Yeni Çıxarış Sorğusu!</b>\n\n"
                f"👤 <b>İstifadəçi:</b> {name_display} ({uname_display})\n"
                f"🆔 <b>Telegram ID:</b> <code>{user.telegram_id}</code>\n"
                f"🪙 <b>Balans:</b> {user.balance_mc:,.0f} VC\n"
                f"💬 <b>Kart/Məhsul Məlumatları:</b>\n"
                f"<code>{message.text}</code>"
            )
            try:
                await message.bot.send_message(chat_id=ADMIN_ID, text=admin_text, parse_mode="HTML")
                # Send confirmation in user's language
                lang = user.language if user.language in BOT_LOCALES else 'en'
                # Simple localized messages
                confirm_msgs = {
                    'az': "✅ <b>Çıxarış sorğunuz qəbul edildi!</b>\nMəlumatlarınız adminlərə göndərildi. Tezliklə ödənişiniz icra olunacaq.",
                    'tr': "✅ <b>Çekim talebiniz alındı!</b>\nBilgileriniz yöneticilere iletildi. En kısa sürede ödemeniz yapılacaktır.",
                    'en': "✅ <b>Your withdrawal request has been received!</b>\nYour details have been forwarded to the admins. Your payment will be processed shortly.",
                    'ru': "✅ <b>Ваш запрос на вывод средств принят!</b>\nВаши данные отправлены администраторам. Ваша выплата будет произведена в ближайшее время."
                }
                user_msg = confirm_msgs.get(lang, confirm_msgs['en'])
                await message.answer(user_msg, parse_mode="HTML")
                logger.info("[WITHDRAW] Request from user %s forwarded to admin %s", user.telegram_id, ADMIN_ID)
            except Exception as e:
                logger.exception("Failed to forward withdrawal request to admin: %s", e)
                err_msgs = {
                    'az': "⚠️ Xəta baş verdi. Zəhmət olmasa bir az sonra yenidən cəhd edin.",
                    'tr': "⚠️ Bir hata oluştu. Lütfen daha sonra tekrar deneyin.",
                    'en': "⚠️ An error occurred. Please try again later.",
                    'ru': "⚠️ Произошла ошибка. Пожалуйста, попробуйте позже."
                }
                await message.answer(err_msgs.get(lang, err_msgs['en']))


# ── Helpers ─────────────────────────────────────────────────────────────
async def _send_welcome_back(message: types.Message, user: User) -> None:
    """Greet a returning user with their current stats in their chosen language."""
    lang = user.language if user.language in BOT_LOCALES else 'en'
    loc = BOT_LOCALES[lang]
    webapp_url = f"https://manatqazan.vercel.app/?lang={lang}&v={int(datetime.now().timestamp())}"

    # Update menu button to match user's language
    try:
        await message.bot.set_chat_menu_button(
            chat_id=user.telegram_id,
            menu_button=MenuButtonWebApp(
                text=loc['btn_start'],
                web_app=types.WebAppInfo(url=webapp_url)
            )
        )
    except Exception:
        pass

    name = user.first_name or "friend"
    welcome_text = loc['welcome_back'].format(
        name=name,
        balance=f"{user.balance_mc:,.0f}",
        total=f"{user.total_earned_mc:,.0f}",
    )

    await message.answer(
        welcome_text,
        reply_markup=get_main_keyboard(lang, vip_status=user.vip_status),
    )


async def _show_how_it_works(tg_user: types.User, message: types.Message) -> None:
    """Show how it works info message to the user in their language."""
    async with async_session() as session:
        stmt = select(User).where(User.telegram_id == tg_user.id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

    lang = (user.language if user and user.language in BOT_LOCALES else 'en')
    loc = BOT_LOCALES[lang]

    hint = SYSTEM_REFRESH_HINT.get(lang, SYSTEM_REFRESH_HINT['en'])

    tier_mc = _get_mc_for_tier(getattr(user, 'vip_status', 'free') if user else 'free')
    text = loc['how_title'] + "\n\n" + loc['how_body'].format(mc=tier_mc) + hint
    await message.answer(text, parse_mode="HTML")


async def _handle_withdraw(tg_user: types.User, message: types.Message) -> None:
    async with async_session() as session:
        stmt = select(User).where(User.telegram_id == tg_user.id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

    if not user:
        await message.answer(BOT_LOCALES['az']['not_registered'])
        return

    lang = user.language if user.language in BOT_LOCALES else 'en'
    loc = BOT_LOCALES[lang]

    hint = SYSTEM_REFRESH_HINT.get(lang, SYSTEM_REFRESH_HINT['en'])

    # Global hardcoded minimum threshold
    if user.balance_mc < _WITHDRAWAL_THRESHOLD_MC:
        if lang == 'az':
            fiat_value = user.balance_mc
        elif lang == 'tr':
            fiat_value = user.balance_mc / (_WITHDRAWAL_THRESHOLD_MC / MIN_WITHDRAWAL_TRY)
        else:  # en, ru — USDT
            fiat_value = user.balance_mc / (_WITHDRAWAL_THRESHOLD_MC / 6.0)
        await message.answer(
            loc['withdraw_below_limit'].format(amount=fiat_value) + hint,
            parse_mode="HTML",
        )
    else:
        await message.answer(loc['withdraw_ok'] + hint, parse_mode="HTML")


# ── Admin Commands ──────────────────────────────────────────────────────

async def _get_admin_stats_text() -> str:
    """Build the admin stats text including last 5 joined users."""
    async with async_session() as session:
        # ── Ümumi istifadəçi sayı ──
        total_users_res = await session.execute(select(func.count(User.id)))
        total_users = total_users_res.scalar() or 0

        # ── Dövriyyədəki ümumi VC (Yalnız aktiv istifadəçilər) ──
        total_mc_res = await session.execute(select(func.sum(User.balance_mc)).where(User.is_active == True))
        total_mc = total_mc_res.scalar() or 0.0

        # ── Ümumi qazanılan VC (Bütün tarixi qazanc) ──
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
        f"📊 <b>VIBECASH — ADMİN PANELİ</b>\n"
        f"{'─' * 30}\n\n"
        f"👤 <b>Ümumi İstifadəçi Sayı:</b> {total_users} nəfər\n"
        f"🪙 <b>Dövriyyədəki Cəmi VC:</b> {total_mc:,.0f} VC\n"
        f"📈 <b>Ümumi Qazanılan VC:</b> {total_earned:,.0f} VC\n\n"
        f"🕒 <b>Son Qoşulan 5 İstifadəçi:</b>\n"
        f"{last5_block}"
    )


ADMIN_HELP_TEXT = (
    "🛠️ <b>VibeCash — Aktiv Admin Əmrləri:</b>\n\n"
    "• /admin — Ümumi sistem statistikası və idarəetmə paneli.\n"
    "• /users — Bota son qoşulan 20 istifadəçi və balansları.\n"
    "• /info [ID/Username] — İstifadəçinin bütün detallı profili (Məs: /info CVb3rAz).\n"
    "• /give [ID/Username] [Miqdar] — Balansa manual VC əlavə edir/silir (Məs: /give CVb3rAz 500).\n"
    "• /ban [ID] — Şübhəli şəxsi dondurur, botu və Mini App-i onun üçün bağlayır.\n"
    "• /unban [ID] — Ban olunmuş şəxsin blokunu qaldırır.\n"
    "• /broadcast [Mesaj] — Bazardakı BÜTÜN istifadəçilərə kütləvi bildiriş göndərir.\n"
    "• /setvip [ID] [pro/elite] — 7 Günlük VIP təyin edər."
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
        lines.append(f"{i}. ID: {u.telegram_id} | {username_str} | Balans: {u.balance_mc:,.0f} VC")
        
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
    last_date = _get_utc_date(user.last_watch_date) if user.last_watch_date else None
    
    from main import _get_vip_params
    session_limit, daily_limit, _ = _get_vip_params(user.vip_status, datetime.now(timezone.utc))
    
    session_1 = user.session_1_count if last_date == today else 0
    session_2 = user.session_2_count if last_date == today else 0
    total_videos = session_1 + session_2
    
    await message.answer(
        f"ℹ️ <b>İstifadəçi Məlumatı:</b>\n"
        f"• <b>Telegram ID:</b> <code>{user.telegram_id}</code>\n"
        f"• <b>Username:</b> {username_display}\n"
        f"• <b>Hazırkı Balans:</b> {user.balance_mc:,.0f} VC\n"
        f"• <b>Ümumi Qazanc:</b> {user.total_earned_mc:,.0f} VC\n"
        f"• <b>Bugünkü Videolar:</b> {total_videos}/{daily_limit} (S1: {session_1}/{session_limit} | S2: {session_2}/{session_limit})\n"
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
            f"🪙 Əvvəlki balans: {old_bal:,.0f} VC\n"
            f"➕ Dəyişiklik: {amount:+,.0f} VC\n"
            f"💰 Yeni balans: {user.balance_mc:,.0f} VC"
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


@router.message(Command("setvip"))
async def cmd_setvip(message: types.Message) -> None:
    if not message.from_user or message.from_user.id != 1970477419:
        return
        
    parts = message.text.split()
    if len(parts) < 3:
        await message.answer("⚠️ Format: <code>/setvip &lt;telegram_id&gt; &lt;pro/elite&gt;</code>", parse_mode="HTML")
        return
        
    target = parts[1].strip()
    status = parts[2].strip().lower()
    
    if status not in ['pro', 'elite']:
        await message.answer("⚠️ Format: <code>/setvip &lt;telegram_id&gt; &lt;pro/elite&gt;</code>", parse_mode="HTML")
        return
        
    if not target.isdigit():
        await message.answer("⚠️ Telegram ID rəqəm olmalıdır.")
        return
        
    tg_id = int(target)
    
    async with async_session() as session:
        stmt = select(User).where(User.telegram_id == tg_id)
        res = await session.execute(stmt)
        user = res.scalar_one_or_none()
        
        if not user:
            await message.answer("❌ İstifadəçi tapılmadı!")
            return
            
        user.vip_status = status
        user.vip_expires_at = datetime.utcnow() + timedelta(days=7)
        user_lang = user.language if user.language in ['az', 'tr', 'en', 'ru'] else 'en'
        await session.commit()
        
        VIP_NOTIFS = {
            "pro": {
                "az": "Sənə bomba bir xəbərim var! Hesabın PRO Nitro-ya qaldırıldı! 🚀\n\nQazanc sürətin artıq **130% Turbo** gücündə uçur! ⚡ Videoların hazırdır, gir dərhal pulunu yığmağa başla!",
                "tr": "Sana bomba gibi bir haberim var! Hesabın PRO Nitro seviyesine uçuruldu! 🚀\n\nKazanç hızın artık **130% Turbo** güçte! ⚡ Görevlerin hazır, hemen gir ve toplamaya başla!",
                "en": "Got some hype news for you! Your account is now PRO Nitro! 🚀\n\nYour earnings velocity is zooming at **130% Turbo Power**! ⚡ Daily tasks are ready, jump in and start stacking!",
                "ru": "Есть бомбическая новость! Твой аккаунт прокачан до PRO Nitro! 🚀\n\nСкорость заработка взлетает на **130% Турбо**! ⚡ Видосы готовы, залетай и начинай рубить кэш!"
            },
            "elite": {
                "az": "Vəssalam, sən artıq ən zirvədəsən! Hesabın ELITE Ultra-ya uçuruldu! 🔥\n\nSürətiniz maksimumda: **175% Ultra Sürət** və **0% komissiya**! Sənin üçün bütün qapılar açıldı, daxil ol və rekordları darmadağın elə!",
                "tr": "Ve bitti! Artık zirvedesin! Hesabın ELITE Ultra statüsüne yükseltildi! 🔥\n\nKazanç hızın maksimumda: **175% Ultra Hız** ve **%0 komisyon**! Tüm kapılar açıldı, gir ve rekorları darmadağın et!",
                "en": "Boom! You are at the absolute top now! Account upgraded to ELITE Ultra! 🔥\n\nMax velocity engaged: **175% Ultra Speed** & **0% commission**! All gateways unlocked, go smash some records!",
                "ru": "Изи! Ты теперь на самом пике! Твой аккаунт взлетел до ELITE Ultra! 🔥\n\nСкорость на максимуме: **175% Ультра** и **0% комиссия**! Все шлюзы открыты, залетай и разноси рекорды в щепки!"
            }
        }
        
        try:
            notif_text = VIP_NOTIFS[status][user_lang]
            await message.bot.send_message(chat_id=tg_id, text=notif_text, parse_mode="Markdown")
        except Exception as e:
            logger.error("Failed to notify user %s of VIP upgrade: %s", tg_id, e)
        
        await message.answer(
            f"✅ <b>VIP Uğurla Təyin Edildi!</b>\n"
            f"İstifadəçi: <code>{tg_id}</code>\n"
            f"Status: <b>{status.upper()}</b>\n"
            f"Müddət: 7 Gün"
        )
