/**
 * ManatAds – Mini App Frontend Logic (i18n: AZ, TR, EN, RU)
 * ===========================================================
 * Integrates with:
 *   • Telegram Web App SDK (istifadəçi kimliyi + tema)
 *   • Adsgram SDK (video reklamlar – .show(), .then(), .catch())
 *   • ManatAds Backend API (istifadəçi məlumatı + mükafat callback)
 */

// ── Konfiqurasiya ─────────────────────────────────────────────────────
const API_BASE = "";
const ADSGRAM_BLOCK_ID = "31923";

// ── i18n Dil Dəstəyi ─────────────────────────────────────────────────
const SUPPORTED_LANGS = ['az', 'tr', 'en', 'ru'];
let currentLang = 'en'; // Changed default from 'az' to 'en'

const LOCALES = {
    az: {
        subtitle: "İzlə • Qazan • Çevir",
        onboardingTitle: "Xoş gəldiniz! Zəhmət olmasa bölgənizi və valyutanızı seçin:",
        onboardingBtn: "Davam et 🚀",
        greeting: "Xoş gəldiniz,",
        balanceLabel: "BALANSINIZ",
        withdrawalTarget: "Çıxarış Hədəfi: 5.00 AZN",
        totalEarned: "ÜMUMİ QAZANC",
        dailyVideos: "BUGÜNKÜ VİDEOLAR",
        invitedLabel: "DƏVƏT OLUNANLAR",
        refEarnings: "REFERAL QAZANCI",
        session1Title: "🌅 1️⃣ Səans 1",
        session2Title: "🌌 2️⃣ Səans 2",
        videoUnit: "video",
        watchBtn: "🎬 Video İzlə &",
        watchBtnSuffix: "MC Qazan",
        completedS1: "🌅 Tamamlandı",
        completedS2: "🌌 Tamamlandı",
        locked: "🔒 Səans 2 Kilidlidir",
        finishFirst: "⏳ Əvvəlcə Səans 1-i bitirin",
        cooldownHint: "Kilid açılmasına:",
        lock_countdown: "Kilid açılmasına: ",
        adLoading: "⏳ Reklam yüklənir...",
        rewardCalc: "✅ Mükafat hesablanır...",
        waitSec: "⏳ Gözləyin",
        referralTitle: "👥 Referal Proqramı",
        refFriends: "Dostlar",
        refEarnedLabel: "MC Qazanc",
        refBonusPct: "Bonus Faizi",
        refLinkLoading: "Referal linki yüklənir...",
        copyBtn: "📋 Linki Kopyala",
        copied: "✅ Kopyalandı!",
        toastEarned: "🎉 +{amount} MC qazandınız!",
        toastCopied: "📋 Referal linki kopyalandı!",
        toastCopyFail: "⚠️ Kopyalana bilmədi. Linki əl ilə kopyalayın.",
        toastAdNotAvail: "⚠️ Reklam xidməti mövcud deyil. Sonra cəhd edin.",
        toastAdFailed: "⚠️ Reklam yüklənmədi. Yenidən cəhd edin.",
        toastWatchFull: "⏭️ Mükafat almaq üçün videonu tam izləyin.",
        toastS1Done: "🌅 Səans 1 tamamlanıb!",
        toastS2Locked: "🔒 Səans 2 hələ kilidlidir!",
        toastS2Done: "🌌 Səans 2 tamamlanıb!",
        toastLoadFail: "⚠️ Məlumatlar yüklənə bilmədi. Yenidən cəhd edin.",
        spamTooOften: "Upps! Reklamlara çox tez-tez baxmağa çalışırsınız. Zəhmət olmasa, bir neçə saniyə gözləyin 🙏",
        spamNoAd: "Hazırda göstəriləcək reklam tapılmadı. Bir az sonra təkrar yoxlayın.",
        spamLongSession: "Sessiyanız çox uzun çəkdi. Zəhmət olmasa, səhifəni yeniləyin.",
        leagueBronze: "🟤 Bürünc Liqa",
        leagueSilver: "⚪ Gümüş Liqa",
        leagueGold: "🟡 Qızıl Liqa",
        leaguePlatinum: "🔵 Platin Liqa",
        leagueDiamond: "💎 Almaz Liqa",
        upgradeSilverTitle: "🎉 TƏBRİKLƏR! 🎉",
        upgradeSilverText: "Sən rəsmən ⚪ Gümüş Liqasına yüksəldin! Sürətin mükəmməldir, belə də davam et! 🚀",
        upgradeGoldTitle: "🔥 MÖHTƏŞƏM! 🔥",
        upgradeGoldText: "Sən artıq 🟡 Qızıl Liqasındasan! Kassan getdikcə böyüyür, çıxarışa az qaldı! 💎",
        upgradePlatTitle: "👑 SENSASİYA! 👑",
        upgradePlatText: "Böyük oyunçu! Rəsmən 🔵 Platin Liqa statusunu aldın! Səni dayandırmaq qeyri-mümkündür! 😎",
        upgradeDiamondTitle: "🌌 ƏFSANƏVİ! 🌌",
        upgradeDiamondText: "Vəssalam! Sən 💎 Almaz Liqasındasan! Çıxarış qapısı sənin üçün açıldı, son addımı at! 💰",
        upgradeBtn: "Uğurlar! 🚀",
    },
    tr: {
        subtitle: "İzle • Kazan • Çevir",
        onboardingTitle: "Hoş geldiniz! Lütfen bölgenizi ve para biriminizi seçin:",
        onboardingBtn: "Devam et 🚀",
        greeting: "Hoş geldiniz,",
        balanceLabel: "BAKİYENİZ",
        withdrawalTarget: "Çekim Hedefi: 100.00 TRY",
        totalEarned: "TOPLAM KAZANÇ",
        dailyVideos: "BUGÜNKÜ VİDEOLAR",
        invitedLabel: "DAVET EDİLENLER",
        refEarnings: "REFERANS KAZANCI",
        session1Title: "🌅 1️⃣ Oturum 1",
        session2Title: "🌌 2️⃣ Oturum 2",
        videoUnit: "video",
        watchBtn: "🎬 Video İzle &",
        watchBtnSuffix: "MC Kazan",
        completedS1: "🌅 Tamamlandı",
        completedS2: "🌌 Tamamlandı",
        locked: "🔒 Oturum 2 Kilitli",
        finishFirst: "⏳ Önce Oturum 1'i bitirin",
        cooldownHint: "Kilit açılmasına:",
        lock_countdown: "Kilidin açılmasına: ",
        adLoading: "⏳ Reklam yükleniyor...",
        rewardCalc: "✅ Ödül hesaplanıyor...",
        waitSec: "⏳ Bekleyin",
        referralTitle: "👥 Referans Programı",
        refFriends: "Arkadaşlar",
        refEarnedLabel: "MC Kazanç",
        refBonusPct: "Bonus Yüzdesi",
        refLinkLoading: "Referans linki yükleniyor...",
        copyBtn: "📋 Linki Kopyala",
        copied: "✅ Kopyalandı!",
        toastEarned: "🎉 +{amount} MC kazandınız!",
        toastCopied: "📋 Referans linki kopyalandı!",
        toastCopyFail: "⚠️ Kopyalanamadı. Linki elle kopyalayın.",
        toastAdNotAvail: "⚠️ Reklam servisi mevcut değil. Daha sonra deneyin.",
        toastAdFailed: "⚠️ Reklam yüklenemedi. Tekrar deneyin.",
        toastWatchFull: "⏭️ Ödül almak için videoyu tamamen izleyin.",
        toastS1Done: "🌅 Oturum 1 tamamlandı!",
        toastS2Locked: "🔒 Oturum 2 henüz kilitli!",
        toastS2Done: "🌌 Oturum 2 tamamlandı!",
        toastLoadFail: "⚠️ Veriler yüklenemedi. Tekrar deneyin.",
        spamTooOften: "Oops! Reklamları çok sık izlemeye çalışıyorsunuz. Lütfen birkaç saniye bekleyin 🙏",
        spamNoAd: "Şu anda gösterilecek reklam bulunamadı. Biraz sonra tekrar deneyin.",
        spamLongSession: "Oturumunuz çok uzun sürdü. Lütfen sayfayı yenileyin.",
        leagueBronze: "🟤 Bronz Lig",
        leagueSilver: "⚪ Gümüş Lig",
        leagueGold: "🟡 Altın Lig",
        leaguePlatinum: "🔵 Platin Lig",
        leagueDiamond: "💎 Elmas Lig",
        upgradeSilverTitle: "🎉 TEBRİKLER! 🎉",
        upgradeSilverText: "Resmen ⚪ Gümüş Lig'e yükseldin! Hızın mükemmel, böyle devam et! 🚀",
        upgradeGoldTitle: "🔥 MUHTEŞEM! 🔥",
        upgradeGoldText: "Artık 🟡 Altın Lig'desin! Kasan büyüyor, çekime az kaldı! 💎",
        upgradePlatTitle: "👑 SANSASYONEL! 👑",
        upgradePlatText: "Büyük oyuncu! Resmen 🔵 Platin Lig statüsünü aldın! Seni durdurmak imkansız! 😎",
        upgradeDiamondTitle: "🌌 EFSANEVİ! 🌌",
        upgradeDiamondText: "İşte bu! 💎 Elmas Lig'desin! Çekim kapısı senin için açıldı, son adımı at! 💰",
        upgradeBtn: "Başarılar! 🚀",
    },
    en: {
        subtitle: "Watch • Earn • Convert",
        onboardingTitle: "Welcome! Please select your region and currency:",
        onboardingBtn: "Continue 🚀",
        greeting: "Welcome,",
        balanceLabel: "YOUR BALANCE",
        withdrawalTarget: "Withdrawal Target: 3.00 USDT",
        totalEarned: "TOTAL EARNED",
        dailyVideos: "TODAY'S VIDEOS",
        invitedLabel: "INVITED",
        refEarnings: "REFERRAL EARNINGS",
        session1Title: "🌅 1️⃣ Session 1",
        session2Title: "🌌 2️⃣ Session 2",
        videoUnit: "videos",
        watchBtn: "🎬 Watch Video &",
        watchBtnSuffix: "MC Earn",
        completedS1: "🌅 Completed",
        completedS2: "🌌 Completed",
        locked: "🔒 Session 2 Locked",
        finishFirst: "⏳ Complete Session 1 first",
        cooldownHint: "Unlocks in:",
        lock_countdown: "Unlocks in: ",
        adLoading: "⏳ Loading ad...",
        rewardCalc: "✅ Calculating reward...",
        waitSec: "⏳ Wait",
        referralTitle: "👥 Referral Program",
        refFriends: "Friends",
        refEarnedLabel: "MC Earned",
        refBonusPct: "Bonus Rate",
        refLinkLoading: "Loading referral link...",
        copyBtn: "📋 Copy Link",
        copied: "✅ Copied!",
        toastEarned: "🎉 +{amount} MC earned!",
        toastCopied: "📋 Referral link copied!",
        toastCopyFail: "⚠️ Could not copy. Copy the link manually.",
        toastAdNotAvail: "⚠️ Ad service unavailable. Try later.",
        toastAdFailed: "⚠️ Ad failed to load. Try again.",
        toastWatchFull: "⏭️ Watch the full video to earn rewards.",
        toastS1Done: "🌅 Session 1 completed!",
        toastS2Locked: "🔒 Session 2 is still locked!",
        toastS2Done: "🌌 Session 2 completed!",
        toastLoadFail: "⚠️ Failed to load data. Please try again.",
        spamTooOften: "Oops! You're watching ads too often. Please wait a few seconds 🙏",
        spamNoAd: "No ads available right now. Please try again later.",
        spamLongSession: "Your session took too long. Please refresh the page.",
        leagueBronze: "🟤 Bronze League",
        leagueSilver: "⚪ Silver League",
        leagueGold: "🟡 Gold League",
        leaguePlatinum: "🔵 Platinum League",
        leagueDiamond: "💎 Diamond League",
        upgradeSilverTitle: "🎉 CONGRATULATIONS! 🎉",
        upgradeSilverText: "You've been promoted to ⚪ Silver League! Your pace is amazing, keep going! 🚀",
        upgradeGoldTitle: "🔥 AMAZING! 🔥",
        upgradeGoldText: "You're now in 🟡 Gold League! Your balance is growing, withdrawal is near! 💎",
        upgradePlatTitle: "👑 SENSATION! 👑",
        upgradePlatText: "Big player! You've earned 🔵 Platinum League status! Nothing can stop you! 😎",
        upgradeDiamondTitle: "🌌 LEGENDARY! 🌌",
        upgradeDiamondText: "That's it! You're in 💎 Diamond League! The withdrawal gate is open for you! 💰",
        upgradeBtn: "Let's Go! 🚀",
    },
    ru: {
        subtitle: "Смотри • Зарабатывай • Конвертируй",
        onboardingTitle: "Добро пожаловать! Пожалуйста, выберите ваш регион и валюту:",
        onboardingBtn: "Продолжить 🚀",
        greeting: "Добро пожаловать,",
        balanceLabel: "ВАШ БАЛАНС",
        withdrawalTarget: "Цель вывода: 3.00 USDT",
        totalEarned: "ОБЩИЙ ЗАРАБОТОК",
        dailyVideos: "ВИДЕО СЕГОДНЯ",
        invitedLabel: "ПРИГЛАШЁННЫЕ",
        refEarnings: "РЕФЕРАЛЬНЫЙ ДОХОД",
        session1Title: "🌅 1️⃣ Сессия 1",
        session2Title: "🌌 2️⃣ Сессия 2",
        videoUnit: "видео",
        watchBtn: "🎬 Смотреть видео &",
        watchBtnSuffix: "MC Заработать",
        completedS1: "🌅 Завершено",
        completedS2: "🌌 Завершено",
        locked: "🔒 Сессия 2 заблокирована",
        finishFirst: "⏳ Сначала завершите Сессию 1",
        cooldownHint: "Разблокировка через:",
        lock_countdown: "До разблокировки: ",
        adLoading: "⏳ Загрузка рекламы...",
        rewardCalc: "✅ Расчёт награды...",
        waitSec: "⏳ Подождите",
        referralTitle: "👥 Реферальная программа",
        refFriends: "Друзья",
        refEarnedLabel: "MC Заработок",
        refBonusPct: "Бонус %",
        refLinkLoading: "Загрузка реферальной ссылки...",
        copyBtn: "📋 Копировать ссылку",
        copied: "✅ Скопировано!",
        toastEarned: "🎉 +{amount} MC заработано!",
        toastCopied: "📋 Реферальная ссылка скопирована!",
        toastCopyFail: "⚠️ Не удалось скопировать. Скопируйте ссылку вручную.",
        toastAdNotAvail: "⚠️ Рекламный сервис недоступен. Попробуйте позже.",
        toastAdFailed: "⚠️ Не удалось загрузить рекламу. Попробуйте ещё раз.",
        toastWatchFull: "⏭️ Посмотрите видео полностью, чтобы получить награду.",
        toastS1Done: "🌅 Сессия 1 завершена!",
        toastS2Locked: "🔒 Сессия 2 ещё заблокирована!",
        toastS2Done: "🌌 Сессия 2 завершена!",
        toastLoadFail: "⚠️ Не удалось загрузить данные. Попробуйте ещё раз.",
        spamTooOften: "Упс! Вы слишком часто смотрите рекламу. Пожалуйста, подождите несколько секунд 🙏",
        spamNoAd: "Сейчас нет доступной рекламы. Попробуйте позже.",
        spamLongSession: "Ваша сессия слишком долгая. Пожалуйста, обновите страницу.",
        leagueBronze: "🟤 Бронзовая Лига",
        leagueSilver: "⚪ Серебряная Лига",
        leagueGold: "🟡 Золотая Лига",
        leaguePlatinum: "🔵 Платиновая Лига",
        leagueDiamond: "💎 Алмазная Лига",
        upgradeSilverTitle: "🎉 ПОЗДРАВЛЯЕМ! 🎉",
        upgradeSilverText: "Вы перешли в ⚪ Серебряную Лигу! Ваш темп превосходен, продолжайте! 🚀",
        upgradeGoldTitle: "🔥 ПОТРЯСАЮЩЕ! 🔥",
        upgradeGoldText: "Теперь вы в 🟡 Золотой Лиге! Ваш баланс растёт, до вывода совсем немного! 💎",
        upgradePlatTitle: "👑 СЕНСАЦИЯ! 👑",
        upgradePlatText: "Крупный игрок! Вы получили статус 🔵 Платиновой Лиги! Вас невозможно остановить! 😎",
        upgradeDiamondTitle: "🌌 ЛЕГЕНДАРНО! 🌌",
        upgradeDiamondText: "Вот это да! Вы в 💎 Алмазной Лиге! Ворота вывода открыты для вас! 💰",
        upgradeBtn: "Вперёд! 🚀",
    }
};

function t(key) {
    return (LOCALES[currentLang] && LOCALES[currentLang][key]) || (LOCALES['az'] && LOCALES['az'][key]) || key;
}

// ── i18n Dil Dəyişmə ─────────────────────────────────────────────────
function setLanguage(lang) {
    if (lang && typeof lang === 'string') {
        lang = lang.toLowerCase().trim();
        if (lang.startsWith('az')) lang = 'az';
        else if (lang.startsWith('tr')) lang = 'tr';
        else if (lang.startsWith('ru')) lang = 'ru';
        else if (lang.startsWith('en')) lang = 'en';
        else lang = 'en';
    } else {
        lang = 'en';
    }
    currentLang = lang;
    localStorage.setItem('saved_language', currentLang);


    // Update all static elements with data-i18n attribute
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        const val = t(key);
        if (val) el.textContent = val;
    });

    // Re-render dashboard with new language
    if (userData) renderDashboard();

    // Update active language indicator
    document.querySelectorAll('.lang-option').forEach(opt => {
        opt.classList.toggle('active', opt.dataset.lang === currentLang);
    });

    // Update current lang display button text (dynamic flag and code)
    const langDisplayMap = {
        'az': '🇦🇿 AZ ▾',
        'tr': '🇹🇷 TR ▾',
        'en': '🇬🇧 EN ▾',
        'ru': '🇷🇺 RU ▾'
    };
    const currentLangEl = document.getElementById('current-lang');
    if (currentLangEl) {
        currentLangEl.textContent = langDisplayMap[lang] || '🇬🇧 EN ▾';
    }

    // Persist to backend silently
    if (currentUser) {
        fetch(`${API_BASE}/api/user/${currentUser.id}/language`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ language: currentLang })
        }).catch(err => console.warn('[i18n] Failed to save language:', err));
    }
}

function toggleLangDropdown() {
    const dropdown = document.getElementById('lang-dropdown');
    if (dropdown) dropdown.classList.toggle('open');
}

// Close dropdown when clicking outside
document.addEventListener('click', (e) => {
    const dropdown = document.getElementById('lang-dropdown');
    const langBtn = document.getElementById('lang-btn');
    if (dropdown && langBtn && !langBtn.contains(e.target) && !dropdown.contains(e.target)) {
        dropdown.classList.remove('open');
    }
});

// ── Onboarding Modal Logic ───────────────────────────────────────────
let onboardingSelectedLang = 'az';

function selectOnboardingLang(lang) {
    if (lang && typeof lang === 'string') {
        lang = lang.toLowerCase().trim();
        if (lang.startsWith('az')) lang = 'az';
        else if (lang.startsWith('tr')) lang = 'tr';
        else if (lang.startsWith('ru')) lang = 'ru';
        else if (lang.startsWith('en')) lang = 'en';
        else lang = 'en';
    } else {
        lang = 'en';
    }
    onboardingSelectedLang = lang;
    
    // Update active visual state of cards
    document.querySelectorAll('.onboarding-option-card').forEach(card => {
        card.classList.toggle('active', card.dataset.lang === lang);
    });

    // Dynamically update onboarding title and confirm button text instantly
    const obTitle = document.getElementById("onboarding-title");
    if (obTitle) {
        obTitle.textContent = LOCALES[lang]?.onboardingTitle || LOCALES['az'].onboardingTitle;
    }
    const obConfirmBtn = document.getElementById("onboarding-confirm-btn");
    if (obConfirmBtn) {
        obConfirmBtn.textContent = LOCALES[lang]?.onboardingBtn || LOCALES['az'].onboardingBtn;
    }
}

function completeOnboarding() {
    // Set active app language
    setLanguage(onboardingSelectedLang);
    
    // Save state to localStorage
    localStorage.setItem('onboarding_completed', 'true');
    
    // Hide modal with elegant transition
    const obModal = document.getElementById("onboarding-modal");
    if (obModal) {
        obModal.classList.remove("active");
        setTimeout(() => {
            obModal.style.display = "none";
        }, 400);
    }
}

// ── Telegram Web App ──────────────────────────────────────────────────
const tg = window.Telegram?.WebApp;
let currentUser = null;
let userData = null;

// ── Başlanğıc ─────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
    if (tg) {
        tg.ready();
        tg.expand();
        try { tg.enableClosingConfirmation(); } catch (_) { /* SDK v6 uyğunluğu */ }

        // Telegram tema rənglərini tətbiq et
        if (tg.themeParams) {
            document.documentElement.style.setProperty(
                "--tg-bg", tg.themeParams.bg_color || "#0a0e1a"
            );
        }
    }

    // Mini App arxa plandan qayıtdıqda balansı yenilə
    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible" && currentUser) {
            console.log("[VISIBILITY] Mini App yenidən görünür — balans yenilənir...");
            fetchUserData().then(() => renderDashboard());
        }
    });

    initApp();
});

// ── Tətbiqin Başlanğıcı ──────────────────────────────────────────────
async function initApp() {
    try {
        // Telegram Web App-dan istifadəçini al
        if (tg?.initDataUnsafe?.user) {
            currentUser = tg.initDataUnsafe.user;
        } else {
            console.warn("Telegram daxilində deyil – test istifadəçi istifadə olunur.");
            currentUser = { id: 123456789, first_name: "TestUser" };
        }

        // Təhlükəsiz dil yoxlanışı funksiyası
        function getValidLang(langStr, source) {
            console.log(`[LangDebug] Checking source (${source}):`, langStr);
            if (langStr && typeof langStr === 'string') {
                const lower = langStr.toLowerCase().trim();
                if (lower.startsWith('az')) return 'az';
                if (lower.startsWith('tr')) return 'tr';
                if (lower.startsWith('en')) return 'en';
                if (lower.startsWith('ru')) return 'ru';
            }
            return null;
        }

        // Ciddi dil prioriteti hiyerarxiyası
        let detectedLang = null;

        // a) Priority 1: Telegram initData
        const tgLang = tg?.initDataUnsafe?.user?.language_code;
        detectedLang = getValidLang(tgLang, 'Telegram initDataUnsafe');
        if (detectedLang) console.log(`[LangDebug] Picked Priority 1 (TG): ${detectedLang}`);

        // b) Priority 2: URL parametri
        if (!detectedLang) {
            const urlParams = new URLSearchParams(window.location.search);
            const urlLang = urlParams.get('lang');
            detectedLang = getValidLang(urlLang, 'URL ?lang=');
            if (detectedLang) console.log(`[LangDebug] Picked Priority 2 (URL): ${detectedLang}`);
        }

        // c) Priority 3: localStorage
        if (!detectedLang) {
            const lsLang = localStorage.getItem('saved_language');
            detectedLang = getValidLang(lsLang, 'localStorage saved_language');
            if (detectedLang) console.log(`[LangDebug] Picked Priority 3 (Storage): ${detectedLang}`);
        }

        // d) Priority 4: Default
        currentLang = detectedLang || 'en';
        console.log(`[LangDebug] Final initialized language: ${currentLang}`);
        localStorage.setItem('saved_language', currentLang); // Yadda saxla

        // Backend-dən istifadəçi məlumatlarını çək
        await fetchUserData();

        // UI-ı yenilə
        renderDashboard();

        // Apply language to all static elements
        setLanguage(currentLang);

        // ── Sınaq / Reset Mexanizmi ──────────────────────────────────────────
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.get('reset') === 'true') {
            console.log(`[LangDebug] ?reset=true parametri tapıldı. Onboarding sıfırlanır...`);
            localStorage.removeItem('onboarding_completed');
        }

        // Check if onboarding is completed
        const onboardingCompleted = localStorage.getItem('onboarding_completed');
        console.log(`[LangDebug] onboardingCompleted flag:`, onboardingCompleted);
        
        if (onboardingCompleted !== 'true') {
            console.log(`[LangDebug] Showing onboarding modal for lang: ${currentLang}`);
            // Preset the onboarding selection according to initial currentLang
            onboardingSelectedLang = currentLang;
            selectOnboardingLang(currentLang);
            
            // Force dynamic localization updates for onboarding title & button
            const obTitle = document.getElementById("onboarding-title");
            if (obTitle) {
                obTitle.textContent = LOCALES[currentLang]?.onboardingTitle || LOCALES['en'].onboardingTitle;
            }
            const obConfirmBtn = document.getElementById("onboarding-confirm-btn");
            if (obConfirmBtn) {
                obConfirmBtn.textContent = LOCALES[currentLang]?.onboardingBtn || LOCALES['en'].onboardingBtn;
            }

            // Show the modal
            const obModal = document.getElementById("onboarding-modal");
            if (obModal) {
                obModal.style.display = "flex";
                // If user meant 'display: block', we could use block, but 'flex' is what style.css uses to center it. 
                setTimeout(() => obModal.classList.add("active"), 10);
            }
        } else {
            console.log(`[LangDebug] Onboarding already completed, skipping modal.`);
        }

        // Əsas kontenti göstər, loaderi gizlə
        document.getElementById("loader").style.display = "none";
        document.getElementById("main-content").style.display = "block";

    } catch (err) {
        console.error("Başlanğıc xətası:", err);
        document.getElementById("loader").style.display = "none";
        document.getElementById("main-content").style.display = "block";
        renderDashboard();
        setLanguage(currentLang);
        showToast(t('toastLoadFail'), "error");
    }
}

// ── İstifadəçi Məlumatlarını Çək (cache-busting ilə) ─────────────────
async function fetchUserData() {
    const cacheBuster = Date.now();
    const url = `${API_BASE}/api/user/${currentUser.id}?_t=${cacheBuster}`;
    console.log(`[fetchUserData] Sorgu göndərilir: ${url}`);

    try {
        const resp = await fetch(url, {
            method: "GET",
            headers: {
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "ngrok-skip-browser-warning": "true"
            }
        });

        console.log(`[fetchUserData] Cavab alındı: status=${resp.status}`);

        if (!resp.ok) {
            if (resp.status === 404) {
                console.warn(`[fetchUserData] 404 - İstifadəçi ID=${currentUser.id} tapılmadı.`);
                if (!userData) userData = createDefaultUserData();
                return;
            }
            const errText = await resp.text();
            console.error(`[fetchUserData] API xətası: ${resp.status} | ${errText}`);
            if (!userData) userData = createDefaultUserData();
            return;
        }

        const newData = await resp.json();
        console.log(`[fetchUserData] Backend data: balance_mc=${newData.balance_mc}, videos_today=${newData.videos_today}`);

        if (userData && userData.balance_mc > newData.balance_mc) {
            console.log(`[fetchUserData] Lokal balans > Server. Lokal saxlanılır.`);
            userData.referral_count = newData.referral_count;
            userData.referral_earnings_mc = newData.referral_earnings_mc;
            return;
        }

        userData = newData;

    } catch (err) {
        console.error("[fetchUserData] Şəbəkə xətası:", err);
        if (!userData) userData = createDefaultUserData();
    }
}

function createDefaultUserData() {
    return {
        telegram_id: currentUser.id,
        first_name: currentUser.first_name || "İstifadəçi",
        balance_mc: 0,
        balance_azn: 0,
        total_earned_mc: 0,
        videos_today: 0,
        daily_limit: 25,
        referral_count: 0,
        referral_earnings_mc: 0,
        mc_per_video: 50,
    };
}

// ── Cooldown Timer State ──────────────────────────────────────────────
let cooldownInterval = null;

function startCooldownTimer(unlockAt) {
    const hintEl = document.getElementById("session-2-cooldown-hint");
    if (!unlockAt) {
        if (hintEl) hintEl.style.display = "none";
        return;
    }
    stopCooldownTimer();

    const targetTime = new Date(unlockAt).getTime();

    function updateTimer() {
        const now = new Date().getTime();
        const difference = targetTime - now;

        if (difference <= 0) {
            stopCooldownTimer();
            if (hintEl) hintEl.style.display = "none";
            if (userData) {
                userData.session_2_locked = false;
                userData.unlock_at = null;
                renderDashboard();
            }
            return;
        }

        const hours = Math.floor(difference / (1000 * 60 * 60));
        const minutes = Math.floor((difference % (1000 * 60 * 60)) / (1000 * 60));
        const seconds = Math.floor((difference % (1000 * 60)) / 1000);

        const pad = (n) => n.toString().padStart(2, '0');
        const prefix = LOCALES[currentLang]?.lock_countdown || LOCALES['az'].lock_countdown;
        if (hintEl) {
            hintEl.textContent = prefix + `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
            hintEl.style.display = "block";
        }
    }

    updateTimer();
    cooldownInterval = setInterval(updateTimer, 1000);
}

function stopCooldownTimer() {
    if (cooldownInterval) {
        clearInterval(cooldownInterval);
        cooldownInterval = null;
    }
}

// ── Dashboard Render ─────────────────────────────────────────────────
let currentLeagueIndex = -1;

function showUpgradeModal(leagueIndex) {
    const modal = document.getElementById("upgrade-modal");
    const titleEl = document.getElementById("upgrade-modal-title");
    const textEl = document.getElementById("upgrade-modal-text");
    const cardEl = document.getElementById("upgrade-modal-card");
    const btnEl = document.querySelector(".upgrade-modal-btn");

    if (!modal || !titleEl || !textEl || !cardEl) return;

    let title = "";
    let text = "";
    let borderColor = "";
    let shadowColor = "";

    switch (leagueIndex) {
        case 1:
            title = t('upgradeSilverTitle');
            text = t('upgradeSilverText');
            borderColor = "#e2e8f0";
            shadowColor = "rgba(226, 232, 240, 0.25)";
            break;
        case 2:
            title = t('upgradeGoldTitle');
            text = t('upgradeGoldText');
            borderColor = "#f59e0b";
            shadowColor = "rgba(245, 158, 11, 0.25)";
            break;
        case 3:
            title = t('upgradePlatTitle');
            text = t('upgradePlatText');
            borderColor = "#3b82f6";
            shadowColor = "rgba(59, 130, 246, 0.25)";
            break;
        case 4:
            title = t('upgradeDiamondTitle');
            text = t('upgradeDiamondText');
            borderColor = "#06b6d4";
            shadowColor = "rgba(6, 182, 212, 0.25)";
            break;
        default:
            return;
    }

    titleEl.textContent = title;
    textEl.textContent = text;
    if (btnEl) btnEl.textContent = t('upgradeBtn');

    cardEl.style.borderColor = borderColor;
    cardEl.style.boxShadow = `0 0 40px ${shadowColor}, inset 0 0 20px ${shadowColor}`;

    modal.classList.add("active");

    // Confetti!
    if (window.confetti) {
        const duration = 3000;
        const end = Date.now() + duration;

        (function frame() {
            confetti({
                particleCount: 5,
                angle: 60,
                spread: 55,
                origin: { x: 0 },
                colors: ['#f59e0b', '#3b82f6', '#06b6d4', '#e2e8f0']
            });
            confetti({
                particleCount: 5,
                angle: 120,
                spread: 55,
                origin: { x: 1 },
                colors: ['#f59e0b', '#3b82f6', '#06b6d4', '#e2e8f0']
            });

            if (Date.now() < end) {
                requestAnimationFrame(frame);
            }
        }());
    }
}

function closeUpgradeModal() {
    const modal = document.getElementById("upgrade-modal");
    if (modal) modal.classList.remove("active");
}

function renderDashboard() {
    if (!userData) return;

    // Başlıq
    document.getElementById("user-name").textContent = userData.first_name || currentUser.first_name || "İstifadəçi";

    // Balans
    const balanceMcEl = document.getElementById("balance-mc");
    balanceMcEl.textContent = formatNumber(userData.balance_mc);

    // Çıxarış Progress Bar -> Liqa Sistemi
    const currentMc = userData.balance_mc || 0;
    let leagueName = "";
    let progressPct = 0;
    let newLeagueIndex = 0;

    if (currentMc <= 10000) {
        leagueName = t('leagueBronze');
        progressPct = (currentMc / 10000) * 100;
        newLeagueIndex = 0;
    } else if (currentMc <= 50000) {
        leagueName = t('leagueSilver');
        progressPct = ((currentMc - 10000) / 40000) * 100;
        newLeagueIndex = 1;
    } else if (currentMc <= 150000) {
        leagueName = t('leagueGold');
        progressPct = ((currentMc - 50000) / 100000) * 100;
        newLeagueIndex = 2;
    } else if (currentMc <= 350000) {
        leagueName = t('leaguePlatinum');
        progressPct = ((currentMc - 150000) / 200000) * 100;
        newLeagueIndex = 3;
    } else if (currentMc < 625000) {
        leagueName = t('leagueDiamond');
        progressPct = ((currentMc - 350000) / 275000) * 100;
        newLeagueIndex = 4;
    } else {
        leagueName = t('leagueDiamond');
        progressPct = 100;
        newLeagueIndex = 4;
    }

    // Check for league upgrade
    if (currentLeagueIndex !== -1 && newLeagueIndex > currentLeagueIndex) {
        showUpgradeModal(newLeagueIndex);
    }
    currentLeagueIndex = newLeagueIndex;

    const pctStr = progressPct.toFixed(1);

    const leagueNameEl = document.getElementById("league-name-text");
    if (leagueNameEl) leagueNameEl.textContent = leagueName;

    const withdrawalPctEl = document.getElementById("withdrawal-pct");
    if (withdrawalPctEl) withdrawalPctEl.textContent = pctStr;

    const withdrawalFillEl = document.getElementById("withdrawal-progress-fill");
    if (withdrawalFillEl) withdrawalFillEl.style.width = `${progressPct}%`;

    // Withdrawal target label
    const withdrawalTargetEl = document.getElementById("withdrawal-target-text");
    if (withdrawalTargetEl) withdrawalTargetEl.textContent = t('withdrawalTarget');

    // Statistika
    document.getElementById("total-earned").textContent = formatNumber(userData.total_earned_mc);
    document.getElementById("videos-count").textContent = `${userData.videos_today}/${userData.daily_limit || 50}`;
    document.getElementById("referral-count").textContent = userData.referral_count;
    document.getElementById("referral-earnings").textContent = formatNumber(userData.referral_earnings_mc);

    // Səans 1 Card
    const s1Count = userData.session_1_count || 0;
    document.getElementById("session-1-progress-text").textContent = `${s1Count}/25 ${t('videoUnit')}`;
    document.getElementById("session-1-progress-fill").style.width = `${(s1Count / 25) * 100}%`;
    const s1Btn = document.getElementById("session-1-btn");

    if (s1Count >= 25) {
        s1Btn.disabled = true;
        s1Btn.textContent = t('completedS1');
    } else {
        s1Btn.disabled = false;
        s1Btn.textContent = `${t('watchBtn')} ${userData.mc_per_video || 50} ${t('watchBtnSuffix')}`;
    }

    // Səans 2 Card
    const s2Count = userData.session_2_count || 0;
    document.getElementById("session-2-progress-text").textContent = `${s2Count}/25 ${t('videoUnit')}`;
    document.getElementById("session-2-progress-fill").style.width = `${(s2Count / 25) * 100}%`;
    const s2Btn = document.getElementById("session-2-btn");
    const s2Hint = document.getElementById("session-2-cooldown-hint");

    if (userData.session_2_locked) {
        s2Btn.disabled = true;
        if (userData.unlock_at) {
            s2Btn.textContent = t('locked');
            s2Hint.style.display = "block";
            startCooldownTimer(userData.unlock_at);
        } else {
            s2Btn.textContent = t('finishFirst');
            s2Hint.style.display = "none";
            stopCooldownTimer();
        }
    } else {
        s2Hint.style.display = "none";
        stopCooldownTimer();
        if (s2Count >= 25) {
            s2Btn.disabled = true;
            s2Btn.textContent = t('completedS2');
        } else {
            if (s1Count < 25) {
                s2Btn.disabled = true;
                s2Btn.textContent = t('finishFirst');
            } else {
                s2Btn.disabled = false;
                s2Btn.textContent = `${t('watchBtn')} ${userData.mc_per_video || 50} ${t('watchBtnSuffix')}`;
            }
        }
    }

    // Referal bölməsi
    const botUsername = "QazanAz_bot";
    const refLink = `https://t.me/${botUsername}?start=${currentUser.id}`;
    document.getElementById("referral-link").textContent = refLink;
    document.getElementById("ref-friends").textContent = userData.referral_count;
    document.getElementById("ref-earned").textContent = formatNumber(userData.referral_earnings_mc);
}

// ── Adsgram İnteqrasiyası ────────────────────────────────────────────
let adController = null;

function initAdsgram() {
    if (window.Adsgram) {
        adController = window.Adsgram.init({ blockId: ADSGRAM_BLOCK_ID });

        adController.addEventListener("onNonStopShow", () => {
            showToast(t('spamTooOften'), "error");
        });

        adController.addEventListener("onBannerNotFound", () => {
            showToast(t('spamNoAd'), "error");
        });

        adController.addEventListener("onTooLongSession", () => {
            showToast(t('spamLongSession'), "error");
        });

        return true;
    }
    console.warn("Adsgram SDK yüklənmədi.");
    return false;
}

/**
 * Adsgram vasitəsilə mükafatlı video reklamı göstər.
 */
let currentWatchingSession = 1;

async function watchAd(sessionNum = 1) {
    currentWatchingSession = sessionNum;
    const watchBtn = document.getElementById(`session-${sessionNum}-btn`);
    const otherBtn = document.getElementById(`session-${sessionNum === 1 ? 2 : 1}-btn`);

    if (!userData) return;

    if (sessionNum === 1 && userData.session_1_count >= 25) {
        showToast(t('toastS1Done'), "error");
        return;
    }
    if (sessionNum === 2) {
        if (userData.session_2_locked) {
            showToast(t('toastS2Locked'), "error");
            return;
        }
        if (userData.session_2_count >= 25) {
            showToast(t('toastS2Done'), "error");
            return;
        }
    }

    if (!adController) {
        if (!initAdsgram()) {
            showToast(t('toastAdNotAvail'), "error");
            return;
        }
    }

    watchBtn.disabled = true;
    const oldText = watchBtn.textContent;
    watchBtn.textContent = t('adLoading');
    if (otherBtn) otherBtn.disabled = true;

    try {
        const result = await adController.show();

        if (result.done) {
            watchBtn.textContent = t('rewardCalc');

            await creditReward(sessionNum);

            spawnCoinBurst();

            showToast(t('toastEarned').replace('{amount}', userData.mc_per_video), "success");
        }

    } catch (result) {
        if (result.error) {
            console.error("Adsgram xətası:", result.description);
            showToast(t('toastAdFailed'), "error");
        } else {
            showToast(t('toastWatchFull'), "error");
        }
    } finally {
        renderDashboard();
        startButtonCooldown(sessionNum);
    }
}

// ── Düymə Cooldown ────────────────────────────────────────────────────
function startButtonCooldown(sessionNum, seconds = 5) {
    const btn = document.getElementById(`session-${sessionNum}-btn`);
    const otherBtn = document.getElementById(`session-${sessionNum === 1 ? 2 : 1}-btn`);

    btn.disabled = true;
    if (otherBtn) otherBtn.disabled = true;

    let remaining = seconds;
    btn.textContent = `${t('waitSec')} (${remaining}s)...`;

    const interval = setInterval(() => {
        remaining--;
        if (remaining > 0) {
            btn.textContent = `${t('waitSec')} (${remaining}s)...`;
        } else {
            clearInterval(interval);
            renderDashboard();
        }
    }, 1000);
}

// ── Mükafat Kreditləmə ───────────────────────────────────────────────
async function creditReward(sessionNum) {
    if (userData) {
        userData.balance_mc += userData.mc_per_video;
        userData.total_earned_mc += userData.mc_per_video;
        userData.videos_today += 1;

        if (sessionNum === 1) {
            userData.session_1_count += 1;
            if (userData.session_1_count === 25) {
                userData.session_2_locked = true;
                const unlockDate = new Date();
                unlockDate.setHours(unlockDate.getHours() + 4);
                userData.unlock_at = unlockDate.toISOString();
            }
        } else if (sessionNum === 2) {
            userData.session_2_count += 1;
        }

        renderDashboard();
    }

    scheduleServerSync(4, 2500);
}

/**
 * Server ilə sinxronlaşdırma
 */
function scheduleServerSync(maxRetries, delayMs) {
    let attempt = 0;

    function trySync() {
        attempt++;
        console.log(`[SYNC] Cəhd ${attempt}/${maxRetries} — ${delayMs * attempt}ms sonra...`);

        setTimeout(async () => {
            try {
                const prevBalance = userData ? userData.balance_mc : 0;
                await fetchUserData();
                renderDashboard();

                const newBalance = userData ? userData.balance_mc : 0;
                console.log(`[SYNC] Cəhd ${attempt} tamamlandı: balans=${newBalance} (əvvəlki=${prevBalance})`);

                if (newBalance < prevBalance && attempt < maxRetries) {
                    trySync();
                }
            } catch (err) {
                console.error(`[SYNC] Cəhd ${attempt} xətası:`, err);
                if (attempt < maxRetries) trySync();
            }
        }, delayMs * attempt);
    }

    trySync();
}

// ── Referal Linkini Kopyala ──────────────────────────────────────────
async function copyReferralLink() {
    const linkEl = document.getElementById("referral-link");
    const link = linkEl.textContent;
    const btn = document.getElementById("copy-btn");

    let copied = false;

    if (tg && typeof tg.openLink === "function") {
        try {
            if (typeof tg.shareUrl === "function") {
                tg.shareUrl(link);
                copied = true;
            }
        } catch (_) { }
    }

    if (!copied && navigator.clipboard && navigator.clipboard.writeText) {
        try {
            await navigator.clipboard.writeText(link);
            copied = true;
        } catch (_) { }
    }

    if (!copied) {
        try {
            const textArea = document.createElement("textarea");
            textArea.value = link;
            textArea.style.position = "fixed";
            textArea.style.left = "-9999px";
            textArea.style.top = "-9999px";
            textArea.style.opacity = "0";
            document.body.appendChild(textArea);
            textArea.focus();
            textArea.select();
            copied = document.execCommand("copy");
            document.body.removeChild(textArea);
        } catch (_) { copied = false; }
    }

    if (copied) {
        showToast(t('toastCopied'), "success");
        btn.textContent = t('copied');
        setTimeout(() => {
            btn.textContent = t('copyBtn');
        }, 2000);
    } else {
        showToast(t('toastCopyFail'), "error");
    }
}

// ── Coin Partlayış Animasiyası ───────────────────────────────────────
function spawnCoinBurst() {
    const emojis = ["🪙", "✨", "💰", "⭐"];
    const count = 8;

    for (let i = 0; i < count; i++) {
        const coin = document.createElement("div");
        coin.className = "coin-burst";
        coin.textContent = emojis[Math.floor(Math.random() * emojis.length)];
        coin.style.left = `${30 + Math.random() * 40}%`;
        coin.style.top = `${40 + Math.random() * 20}%`;
        coin.style.animationDelay = `${i * 0.08}s`;
        document.body.appendChild(coin);
        setTimeout(() => coin.remove(), 1500);
    }
}

// ── Toast Notifications ──────────────────────────────────────────────
let toastTimer = null;

function showToast(message, toastType = "success") {
    const toast = document.getElementById("toast");
    toast.textContent = message;
    toast.className = `toast ${toastType} visible`;

    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
        toast.classList.remove("visible");
    }, 3000);
}

// ── Yardımçı (Format) ────────────────────────────────────────────────
function formatNumber(num) {
    if (num === undefined || num === null) return "0";
    return Math.floor(num).toLocaleString("az-AZ");
}
