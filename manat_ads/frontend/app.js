/**
 * VibeCash – Mini App Frontend Logic (i18n: AZ, TR, EN, RU)
 * ===========================================================
 * Integrates with:
 *   • Telegram Web App SDK (istifadəçi kimliyi + tema)
 *   • Onclicka TMA SDK (video reklamlar – Zone ID: 443591)
 *   • VibeCash Backend API (istifadəçi məlumatı + mükafat callback)
 */

// ── Konfiqurasiya ─────────────────────────────────────────────────────
const API_BASE = window.location.origin;
// ── 2-Level Ad Pool Configuration ───────────────────────────────────────
let LEVEL_LIMIT = 25;             // Ads per level — overridden dynamically from API (25 free / 22 PRO / 20 ELITE)
let LEVEL_2_LIMIT = 25;           // Ads for level 2 — daily_limit - LEVEL_LIMIT
const MAX_LEVELS  = 2;            // Total levels
const COOLDOWN_MS = 3 * 60 * 60 * 1000; // 3 hours in milliseconds

// ── Adsgram TMA SDK Bootstrap ──────────────────────────────────────────
let AdController = null;
let globalConfig = null;

async function fetchConfigAndInitAdsgram() {
    try {
        const resp = await fetch(`${API_BASE}/api/config`);
        if (resp.ok) {
            globalConfig = await resp.json();
            
            // Dynamic maintenance mode check
            if (globalConfig.maintenance_mode === true) {
                document.body.innerHTML = `
                <div style="
                    background-color: #0f172a;
                    color: #f8fafc;
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    justify-content: center;
                    height: 100vh;
                    margin: 0;
                    text-align: center;
                    padding: 20px;
                    box-sizing: border-box;
                    position: fixed;
                    top: 0;
                    left: 0;
                    width: 100vw;
                    z-index: 999999;
                ">
                    <div style="
                        max-width: 400px;
                        padding: 30px;
                        background: rgba(30, 41, 59, 0.7);
                        border-radius: 16px;
                        box-shadow: 0 10px 30px rgba(0,0,0,0.5);
                        border: 1px solid rgba(255,255,255,0.1);
                        backdrop-filter: blur(10px);
                    ">
                        <div style="
                            font-size: 48px;
                            margin-bottom: 20px;
                            animation: spin 3s linear infinite;
                            display: inline-block;
                        ">⚙️</div>
                        <h1 style="color: #38bdf8; margin-top: 0; font-size: 24px;">Texniki İşlər Gedir</h1>
                        <p style="color: #94a3b8; line-height: 1.6; font-size: 16px;">Sistemdə optimallaşdırma və təmir işləri aparılır. Tezliklə yenidən xidmətinizdə olacağıq. Anlayışınız üçün təşəkkür edirik!</p>
                    </div>
                    <style>
                        @keyframes spin {
                            0% { transform: rotate(0deg); }
                            100% { transform: rotate(360deg); }
                        }
                    </style>
                </div>`;
                return;
            }

            if (window.Adsgram && globalConfig.adsgram_block_id) {
                AdController = window.Adsgram.init({ blockId: globalConfig.adsgram_block_id.toString() });
            }
        }
    } catch(e) {
        console.error("Failed to fetch global config:", e);
    }
}
fetchConfigAndInitAdsgram();

// ── 2-Level Ad Pool State ─────────────────────────────────────────────
// These are loaded from / persisted to localStorage so state survives refreshes.
let currentLevel    = 1;    // 1 or 2
let levelClicks     = 0;    // 0 to LEVEL_LIMIT
let cooldownEndTime = 0;    // Unix ms timestamp; 0 = no cooldown

function loadAdState() {
    currentLevel    = parseInt(localStorage.getItem('ad_currentLevel')    || '1', 10);
    levelClicks     = parseInt(localStorage.getItem('ad_levelClicks')     || '0', 10);
    cooldownEndTime = parseInt(localStorage.getItem('ad_cooldownEndTime') || '0', 10);
    // Validate
    if (![1, 2].includes(currentLevel)) currentLevel = 1;
    if (isNaN(levelClicks) || levelClicks < 0) levelClicks = 0;
    if (isNaN(cooldownEndTime) || cooldownEndTime < 0) cooldownEndTime = 0;
}

function saveAdState() {
    localStorage.setItem('ad_currentLevel',    currentLevel);
    localStorage.setItem('ad_levelClicks',     levelClicks);
    localStorage.setItem('ad_cooldownEndTime', cooldownEndTime);
}

/** Evaluate and advance cooldown state — called on boot and each render. */
function evaluateAdState() {
    const now = Date.now();
    // If Level 1 filled and we're waiting for cooldown to expire → switch to Level 2
    if (currentLevel === 1 && levelClicks >= LEVEL_LIMIT && cooldownEndTime > 0) {
        if (now >= cooldownEndTime) {
            // Cooldown expired → unlock Level 2
            currentLevel    = 2;
            levelClicks     = 0;
            cooldownEndTime = 0;
            saveAdState();
        }
        // else: still waiting
    }
}


// ── i18n Dil Dəstəyi ─────────────────────────────────────────────────
const SUPPORTED_LANGS = ['az', 'tr', 'en', 'ru'];
let currentLang = 'en'; // Changed default from 'az' to 'en'

const LOCALES = {
    az: {
        wbTitle: "Uğurlu Qeydiyyat! ✅",
        wbBody: "Yeni istifadəçilərə özəl olaraq hesabınıza 4 AZN bonus köçürüldü! Çıxarış limitinə çatmaq üçün sadəcə qısa bir yolunuz qaldı. Şansınızı qaçırmayın, indi qazanmağa başlayın!",
        wbBtn: "Təsdiqlə",
        subtitle: "İzlə • Qazan • Çevir",
        onboardingTitle: "Xoş gəldiniz! Zəhmət olmasa bölgənizi və valyutanızı seçin:",
        onboardingBtn: "Davam et 🚀",
        greeting: "Xoş gəldiniz,",
        balanceLabel: "BALANSINIZ",
        withdrawalTarget: "Çıxarış: 10 AZN - 100 AZN",
        totalEarned: "ÜMUMİ QAZANC",
        dailyVideos: "BUGÜNKÜ VİDEOLAR",
        invitedLabel: "DƏVƏT OLUNANLAR",
        refEarnings: "REFERAL QAZANCI",
        session1Title: "🔆 Mərhələ 1",
        session2Title: "🌙 Mərhələ 2",
        videoUnit: "video",
        watchBtn: "<svg class=\"btn-inline-icon\" style=\"fill: #0a1a22; stroke: #0a1a22;\" xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 24 24\"><polygon points=\"6 4 20 12 6 20 6 4\"></polygon></svg> Video İzlə &",
        watchBtnSuffix: "VC Qazan",
        completedS1: "<svg class=\"btn-inline-icon\" style=\"stroke: #06b6d4;\" xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2.5\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M22 11.08V12a10 10 0 1 1-5.93-9.14\"></path><polyline points=\"22 4 12 14.01 9 11.01\"></polyline></svg> Tamamlandı",
        completedS2: "<svg class=\"btn-inline-icon\" style=\"stroke: #06b6d4;\" xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2.5\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M22 11.08V12a10 10 0 1 1-5.93-9.14\"></path><polyline points=\"22 4 12 14.01 9 11.01\"></polyline></svg> Tamamlandı",
        locked: "🔒 Mərhələ 2 Kilidlidir",
        finishFirst: "⏳ Əvvəlcə Mərhələ 1-i bitirin",
        cooldownHint: "Kilid açılmasına:",
        lock_countdown: "Kilid açılmasına: ",
        adLoading: "⏳ Reklam yüklənir...",
        rewardCalc: "✅ Mükafat hesablanır...",
        waitSec: "⏳ Gözləyin",
        referralTitle: "👥 Referal Proqramı",
        refFriends: "Dostlar",
        refEarnedLabel: "VC Qazanc",
        refBonusPct: "Bonus Faizi",
        refLinkLoading: "Referal linki yüklənir...",
        copyBtn: "📋 Linki Kopyala",
        copied: "✅ Kopyalandı!",
        toastEarned: "🎉 +{amount} VC qazandınız!",
        rewardSuccess: "🎉 +{amount} VC qazandınız!",
        toastCopied: "📋 Referal linki kopyalandı!",
        toastCopyFail: "⚠️ Kopyalana bilmədi. Linki əl ilə kopyalayın.",
        toastAdNotAvail: "⚠️ Reklam xidməti mövcud deyil. Sonra cəhd edin.",
        toastAdFailed: "⚠️ Reklam yüklənmədi. Yenidən cəhd edin.",
        toastWatchFull: "⏭️ Mükafat almaq üçün videonu tam izləyin.",
        toastS1Done: "🌅 Mərhələ 1 tamamlanıb!",
        toastS2Locked: "🔒 Mərhələ 2 hələ kilidlidir!",
        toastS2Done: "🌌 Mərhələ 2 tamamlanıb!",
        toastLoadFail: "⚠️ Məlumatlar yüklənə bilmədi. Yenidən cəhd edin.",
        spamTooOften: "Upps! Reklamlara çox tez-tez baxmağa çalışırsınız. Zəhmət olmasa, bir neçə saniyə gözləyin 🙏",
        spamNoAd: "Hazırda göstəriləcək reklam tapılmadı. Bir az sonra təkrar yoxlayın.",
        spamLongSession: "Sessiyanız çox uzun çəkdi. Zəhmət olmasa, səhifəni yeniləyin.",
        leagueBronze: "Bürünc Liqa",
        leagueSilver: "Gümüş Liqa",
        leagueGold: "Qızıl Liqa",
        leaguePlatinum: "Platin Liqa",
        leagueDiamond: "Almaz Liqa",
        upgradeSilverTitle: "🎉 TƏBRİKLƏR! 🎉",
        upgradeSilverText: "Sən rəsmən ⚪ Gümüş Liqasına yüksəldin! Sürətin mükəmməldir, belə də davam et! 🚀",
        upgradeGoldTitle: "🔥 MÖHTƏŞƏM! 🔥",
        upgradeGoldText: "Sən artıq 🟡 Qızıl Liqasındasan! Kassan getdikcə böyüyür, çıxarışa az qaldı! 💎",
        upgradePlatTitle: "👑 SENSASİYA! 👑",
        upgradePlatText: "Böyük oyunçu! Rəsmən 🔵 Platin Liqa statusunu aldın! Səni dayandırmaq qeyri-mümkündür! 😎",
        upgradeDiamondTitle: "🌌 ƏFSANƏVİ! 🌌",
        upgradeDiamondText: "Vəssalam! Sən 💎 Almaz Liqasındasan! Çıxarış qapısı sənin üçün açıldı, son addımı at! 💰",
        upgradeBtn: "Uğurlar! 🚀",
        nav_main: "Əsas",
        nav_home: "Əsas",
        splashTagline: "İzlə • Qazan • Çevir",
        nav_tasks: "Tapşırıqlar",
        nav_leaderboard: "Liderlər",
        task_sub: "Kanallara abunə ol və qazan",
        btn_verify: "Yoxla 🔄",
        btn_join: "Abunə Ol 🚀",
        tasks_empty_msg: "Hazırda aktiv tapşırıq yoxdur.",
        nav_store: "Mağaza",
        store_soon: "Mağaza tezliklə...",
        store_subtitle_soon: "VIP Statuslar tezliklə aktiv olacaq!",
        vip_free_label: "Standart Sürət",
        vip_free_price: "Pulsuz",
        vip_free_perk: "Hər video +200 VC",
        vip_pro_title: "PRO Nitro",
        vip_elite_title: "ELITE Ultra",
        Pro_Price: "2.50 AZN / 1 Həftə",
        Elite_Price: "3.50 AZN / 1 Həftə",
        Pro_Line_1: "Gündəlik: 45 video (Daha az yorucu)",
        Pro_Line_2: "Hər gün +11,700 VC-yə qədər böyük qazanc",
        Pro_Line_3: "🚀 130% Turbo Sürətli qazanc gücü",
        Pro_Line_4: "+310 VC hər tapşırıq üçün",
        Elite_Line_1: "Gündəlik: 40 video (Maksimum qənaət)",
        Elite_Line_2: "Hər gün +14,000 VC-yə qədər rekord qazanc",
        Elite_Line_3: "🔥 175% Ultra Sürət və 0% komissiyalı çıxarış",
        Elite_Line_4: "+400 VC hər tapşırıq üçün",
        vip_buy_btn: "Satın Al",
        Modal_Confirm_Text: "Siz bu paketi almaq istədiyinizi təsdiqləyirsiniz?", 
        Modal_Btn_Cancel: "İmtina", 
        Modal_Btn_Confirm: "Təsdiqlə",
        Modal_Order_Msg: "Salam! Mən {package} paketi almaq istəyirəm. Mənim İD-m: {id}",
        Withdraw_Range_Notice: "Birdəfəlik Çıxarış Limiti: 10 AZN - 100 AZN",
        Dashboard_Range: "Çıxarış: 10 AZN - 100 AZN",
        menu_leaderboard: "🏆 Liderlər",
        leaderboard_title: "Ən Çox Qazanan Top 25",
        user_label: "İstifadəçi",
        balance_label: "Qazanc",
        global_users: "istifadəçi",
        videoPreparing: "Yeni video hazırlanır...",
    },
    tr: {
        wbTitle: "Başarılı Kayıt! ✅",
        wbBody: "Yeni kullanıcılara özel olarak hesabınıza 110 TRY bonus tanımlandı! Çekim limitine ulaşmak için sadece kısa bir yolunuz kaldı. Şansınızı kaçırmayın, şimdi kazanmaya başlayın!",
        wbBtn: "Onayla",
        subtitle: "İzle • Kazan • Çevir",
        onboardingTitle: "Hoş geldiniz! Lütfen bölgenizi ve para biriminizi seçin:",
        onboardingBtn: "Devam et 🚀",
        greeting: "Hoş geldiniz,",
        balanceLabel: "BAKİYENİZ",
        withdrawalTarget: "Çekim: 275 TRY - 2750 TRY",
        totalEarned: "TOPLAM KAZANÇ",
        dailyVideos: "BUGÜNKÜ VİDEOLAR",
        invitedLabel: "DAVET EDİLENLER",
        refEarnings: "REFERANS KAZANCI",
        session1Title: "🔆 Aşama 1",
        session2Title: "🌙 Aşama 2",
        videoUnit: "video",
        watchBtn: "<svg class=\"btn-inline-icon\" style=\"fill: #0a1a22; stroke: #0a1a22;\" xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 24 24\"><polygon points=\"6 4 20 12 6 20 6 4\"></polygon></svg> Video İzle &",
        watchBtnSuffix: "VC Kazan",
        completedS1: "<svg class=\"btn-inline-icon\" style=\"stroke: #06b6d4;\" xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2.5\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M22 11.08V12a10 10 0 1 1-5.93-9.14\"></path><polyline points=\"22 4 12 14.01 9 11.01\"></polyline></svg> Tamamlandı",
        completedS2: "<svg class=\"btn-inline-icon\" style=\"stroke: #06b6d4;\" xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2.5\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M22 11.08V12a10 10 0 1 1-5.93-9.14\"></path><polyline points=\"22 4 12 14.01 9 11.01\"></polyline></svg> Tamamlandı",
        locked: "🔒 Aşama 2 Kilitli",
        finishFirst: "⏳ Önce Aşama 1'i bitirin",
        cooldownHint: "Kilit açılmasına:",
        lock_countdown: "Kilidin açılmasına: ",
        adLoading: "⏳ Reklam yükleniyor...",
        rewardCalc: "✅ Ödül hesaplanıyor...",
        waitSec: "⏳ Bekleyin",
        referralTitle: "👥 Referans Programı",
        refFriends: "Arkadaşlar",
        refEarnedLabel: "VC Kazanç",
        refBonusPct: "Bonus Yüzdesi",
        refLinkLoading: "Referans linki yükleniyor...",
        copyBtn: "📋 Linki Kopyala",
        copied: "✅ Kopyalandı!",
        toastEarned: "🎉 +{amount} VC kazandınız!",
        rewardSuccess: "🎉 +{amount} VC kazandınız!",
        toastCopied: "📋 Referans linki kopyalandı!",
        toastCopyFail: "⚠️ Kopyalanamadı. Linki elle kopyalayın.",
        toastAdNotAvail: "⚠️ Reklam servisi mevcut değil. Daha sonra deneyin.",
        toastAdFailed: "⚠️ Reklam yüklenemedi. Tekrar deneyin.",
        toastWatchFull: "⏭️ Ödül almak için videoyu tamamen izleyin.",
        toastS1Done: "🌅 Aşama 1 tamamlandı!",
        toastS2Locked: "🔒 Aşama 2 henüz kilitli!",
        toastS2Done: "🌌 Aşama 2 tamamlandı!",
        toastLoadFail: "⚠️ Veriler yüklenemedi. Tekrar deneyin.",
        spamTooOften: "Oops! Reklamları çok sık izlemeye çalışıyorsunuz. Lütfen birkaç saniye bekleyin 🙏",
        spamNoAd: "Şu anda gösterilecek reklam bulunamadı. Biraz sonra tekrar deneyin.",
        spamLongSession: "Oturumunuz çok uzun sürdü. Lütfen sayfayı yenileyin.",
        leagueBronze: "Bronz Lig",
        leagueSilver: "Gümüş Lig",
        leagueGold: "Altın Lig",
        leaguePlatinum: "Platin Lig",
        leagueDiamond: "Elmas Lig",
        upgradeSilverTitle: "🎉 TEBRİKLER! 🎉",
        upgradeSilverText: "Resmen ⚪ Gümüş Lig'e yükseldin! Hızın mükemmel, böyle devam et! 🚀",
        upgradeGoldTitle: "🔥 MUHTEŞEM! 🔥",
        upgradeGoldText: "Artık 🟡 Altın Lig'desin! Kasan büyüyor, çekime az kaldı! 💎",
        upgradePlatTitle: "👑 SANSASYONEL! 👑",
        upgradePlatText: "Büyük oyuncu! Resmen 🔵 Platin Lig statüsünü aldın! Seni durdurmak imkansız! 😎",
        upgradeDiamondTitle: "🌌 EFSANEVİ! 🌌",
        upgradeDiamondText: "İşte bu! 💎 Elmas Lig'desin! Çekim kapısı senin için açıldı, son adımı at! 💰",
        upgradeBtn: "Başarılar! 🚀",
        nav_main: "Ana Sayfa",
        nav_home: "Anasayfa",
        splashTagline: "İzle • Kazan • Dönüştür",
        nav_tasks: "Görevler",
        nav_leaderboard: "Liderler",
        task_sub: "Kanallara abone ol ve kazan",
        btn_verify: "Kontrol Et 🔄",
        btn_join: "Abone Ol 🚀",
        tasks_empty_msg: "Şu anda aktif görev bulunmamaktadır.",
        nav_store: "Mağaza",
        store_soon: "Mağaza yakında...",
        store_subtitle_soon: "VIP Statüler yakında aktif olacak!",
        vip_free_label: "Standart Hız",
        vip_free_price: "Ücretsiz",
        vip_free_perk: "Her video +200 VC",
        vip_pro_title: "PRO Nitro",
        vip_elite_title: "ELITE Ultra",
        Pro_Price: "70 TRY / 1 Hafta",
        Elite_Price: "95 TRY / 1 Hafta",
        Pro_Line_1: "Günlük: 45 video (Daha az yorucu)",
        Pro_Line_2: "Her gün +11.700 VC'ye varan büyük kazanç",
        Pro_Line_3: "🚀 130% Turbo Hızlı kazanç gücü",
        Pro_Line_4: "+310 VC her görev için",
        Elite_Line_1: "Günlük: 40 video (Maksimum tasarruf)",
        Elite_Line_2: "Her gün +14.000 VC'ye varan rekor kazanç",
        Elite_Line_3: "🔥 175% Ultra Hız ve 0% komisyonlu çekim",
        Elite_Line_4: "+400 VC her görev için",
        vip_buy_btn: "Satın Al",
        Modal_Confirm_Text: "Bu paketi almak istediğinizi onaylıyor musunuz?", 
        Modal_Btn_Cancel: "İptal", 
        Modal_Btn_Confirm: "Onayla",
        Modal_Order_Msg: "Merhaba! Ben {package} paketi almak istiyorum. Benim ID'm: {id}",
        Withdraw_Range_Notice: "Tek Seferlik Çekim Limiti: 275 TRY - 2750 TRY",
        Dashboard_Range: "Çekim: 275 TRY - 2750 TRY",
        menu_leaderboard: "🏆 Liderler",
        leaderboard_title: "En Çok Kazanan Top 25",
        user_label: "Kullanıcı",
        balance_label: "Kazanç",
        global_users: "kullanıcı",
        videoPreparing: "Yeni video hazırlanıyor...",
    },
    en: {
        wbTitle: "Successful Registration! ✅",
        wbBody: "An exclusive 2.40 USDT bonus has been credited to your account as a new user! You have only a short way left to reach the withdrawal limit. Don't miss your chance, start earning now!",
        wbBtn: "Confirm",
        subtitle: "Watch • Earn • Convert",
        onboardingTitle: "Welcome! Please select your region and currency:",
        onboardingBtn: "Continue 🚀",
        greeting: "Welcome,",
        balanceLabel: "YOUR BALANCE",
        withdrawalTarget: "Withdrawal: 6 USDT - 60 USDT",
        totalEarned: "TOTAL EARNED",
        dailyVideos: "TODAY'S VIDEOS",
        invitedLabel: "INVITED",
        refEarnings: "REFERRAL EARNINGS",
        session1Title: "🔆 Level 1",
        session2Title: "🌙 Level 2",
        videoUnit: "videos",
        watchBtn: "<svg class=\"btn-inline-icon\" style=\"fill: #0a1a22; stroke: #0a1a22;\" xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 24 24\"><polygon points=\"6 4 20 12 6 20 6 4\"></polygon></svg> Watch Video &",
        watchBtnSuffix: "VC Earn",
        completedS1: "<svg class=\"btn-inline-icon\" style=\"stroke: #06b6d4;\" xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2.5\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M22 11.08V12a10 10 0 1 1-5.93-9.14\"></path><polyline points=\"22 4 12 14.01 9 11.01\"></polyline></svg> Completed",
        completedS2: "<svg class=\"btn-inline-icon\" style=\"stroke: #06b6d4;\" xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2.5\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M22 11.08V12a10 10 0 1 1-5.93-9.14\"></path><polyline points=\"22 4 12 14.01 9 11.01\"></polyline></svg> Completed",
        locked: "🔒 Level 2 Locked",
        finishFirst: "⏳ Complete Level 1 first",
        cooldownHint: "Unlocks in:",
        lock_countdown: "Unlocks in: ",
        adLoading: "⏳ Loading ad...",
        rewardCalc: "✅ Calculating reward...",
        waitSec: "⏳ Wait",
        referralTitle: "👥 Referral Program",
        refFriends: "Friends",
        refEarnedLabel: "VC Earned",
        refBonusPct: "Bonus Rate",
        refLinkLoading: "Loading referral link...",
        copyBtn: "📋 Copy Link",
        copied: "✅ Copied!",
        toastEarned: "🎉 +{amount} VC earned!",
        rewardSuccess: "🎉 You earned +{amount} VC!",
        toastCopied: "📋 Referral link copied!",
        toastCopyFail: "⚠️ Could not copy. Copy the link manually.",
        toastAdNotAvail: "⚠️ Ad service unavailable. Try later.",
        toastAdFailed: "⚠️ Ad failed to load. Try again.",
        toastWatchFull: "⏭️ Watch the full video to earn rewards.",
        toastS1Done: "🌅 Level 1 completed!",
        toastS2Locked: "🔒 Level 2 is still locked!",
        toastS2Done: "🌌 Level 2 completed!",
        toastLoadFail: "⚠️ Failed to load data. Please try again.",
        spamTooOften: "Oops! You're watching ads too often. Please wait a few seconds 🙏",
        spamNoAd: "No ads available right now. Please try again later.",
        spamLongSession: "Your session took too long. Please refresh the page.",
        leagueBronze: "Bronze League",
        leagueSilver: "Silver League",
        leagueGold: "Gold League",
        leaguePlatinum: "Platinum League",
        leagueDiamond: "Diamond League",
        upgradeSilverTitle: "🎉 CONGRATULATIONS! 🎉",
        upgradeSilverText: "You've been promoted to ⚪ Silver League! Your pace is amazing, keep going! 🚀",
        upgradeGoldTitle: "🔥 AMAZING! 🔥",
        upgradeGoldText: "You're now in 🟡 Gold League! Your balance is growing, withdrawal is near! 💎",
        upgradePlatTitle: "👑 SENSATION! 👑",
        upgradePlatText: "Big player! You've earned 🔵 Platinum League status! Nothing can stop you! 😎",
        upgradeDiamondTitle: "🌌 LEGENDARY! 🌌",
        upgradeDiamondText: "That's it! You're in 💎 Diamond League! The withdrawal gate is open for you! 💰",
        upgradeBtn: "Let's Go! 🚀",
        nav_main: "Home",
        nav_home: "Home",
        splashTagline: "Watch • Earn • Convert",
        nav_tasks: "Tasks",
        nav_leaderboard: "Leaderboard",
        task_sub: "Subscribe to channels and earn",
        btn_verify: "Verify 🔄",
        btn_join: "Join 🚀",
        tasks_empty_msg: "There are currently no active tasks.",
        nav_store: "Store",
        store_soon: "Store coming soon...",
        store_subtitle_soon: "VIP Statuses will be active soon!",
        vip_free_label: "Standard Speed",
        vip_free_price: "Free",
        vip_free_perk: "+200 VC per video",
        vip_pro_title: "PRO Nitro",
        vip_elite_title: "ELITE Ultra",
        Pro_Price: "1.60 USDT / 1 Week",
        Elite_Price: "2.10 USDT / 1 Week",
        Pro_Line_1: "Daily: 45 videos (Less exhausting)",
        Pro_Line_2: "Earn up to +11,700 VC massive daily drop",
        Pro_Line_3: "🚀 130% Turbo Earnings velocity multiplier",
        Pro_Line_4: "+310 VC per task",
        Elite_Line_1: "Daily: 40 videos (Maximum savings)",
        Elite_Line_2: "Earn up to +14,000 VC record daily drop",
        Elite_Line_3: "🔥 175% Ultra Speed & 0% withdrawal commission",
        Elite_Line_4: "+400 VC per task",
        vip_buy_btn: "Buy Now",
        Modal_Confirm_Text: "Do you confirm buying this package?", 
        Modal_Btn_Cancel: "Cancel", 
        Modal_Btn_Confirm: "Confirm",
        Modal_Order_Msg: "Hello! I want to buy the {package} package. My ID: {id}",
        Withdraw_Range_Notice: "Single Withdrawal Limit: 6 USDT - 60 USDT",
        Dashboard_Range: "Withdrawal: 6 USDT - 60 USDT",
        menu_leaderboard: "🏆 Leaderboard",
        leaderboard_title: "Top 25 Earners",
        user_label: "User",
        balance_label: "Earnings",
        global_users: "users",
        videoPreparing: "Preparing new video...",
    },
    ru: {
        wbTitle: "Успешная Регистрация! ✅",
        wbBody: "Эксклюзивно для новых пользователей на ваш счет начислен бонус 2.40 USDT! До лимита вывода остался всего один короткий шаг. Не упустите свой шанс, начните зарабатывать прямо сейчас!",
        wbBtn: "Подтвердить",
        subtitle: "Смотри • Зарабатывай • Конвертируй",
        onboardingTitle: "Добро пожаловать! Пожалуйста, выберите ваш регион и валюту:",
        onboardingBtn: "Продолжить 🚀",
        greeting: "Добро пожаловать,",
        balanceLabel: "ВАШ БАЛАНС",
        withdrawalTarget: "Вывод: 6 USDT - 60 USDT",
        totalEarned: "ОБЩИЙ ЗАРАБОТОК",
        dailyVideos: "ВИДЕО СЕГОДНЯ",
        invitedLabel: "ПРИГЛАШЁННЫЕ",
        refEarnings: "РЕФЕРАЛЬНЫЙ ДОХОД",
        session1Title: "🔆 Уровень 1",
        session2Title: "🌙 Уровень 2",
        videoUnit: "видео",
        watchBtn: "<svg class=\"btn-inline-icon\" style=\"fill: #0a1a22; stroke: #0a1a22;\" xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 24 24\"><polygon points=\"6 4 20 12 6 20 6 4\"></polygon></svg> Смотреть видео &",
        watchBtnSuffix: "VC Заработать",
        completedS1: "<svg class=\"btn-inline-icon\" style=\"stroke: #06b6d4;\" xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2.5\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M22 11.08V12a10 10 0 1 1-5.93-9.14\"></path><polyline points=\"22 4 12 14.01 9 11.01\"></polyline></svg> Завершено",
        completedS2: "<svg class=\"btn-inline-icon\" style=\"stroke: #06b6d4;\" xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2.5\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M22 11.08V12a10 10 0 1 1-5.93-9.14\"></path><polyline points=\"22 4 12 14.01 9 11.01\"></polyline></svg> Завершено",
        locked: "🔒 Уровень 2 заблокирован",
        finishFirst: "⏳ Сначала завершите Уровень 1",
        cooldownHint: "Разблокировка через:",
        lock_countdown: "До разблокировки: ",
        adLoading: "⏳ Загрузка рекламы...",
        rewardCalc: "✅ Расчёт награды...",
        waitSec: "⏳ Подождите",
        referralTitle: "👥 Реферальная программа",
        refFriends: "Друзья",
        refEarnedLabel: "VC Заработок",
        refBonusPct: "Бонус %",
        refLinkLoading: "Загрузка реферальной ссылки...",
        copyBtn: "📋 Копировать ссылку",
        copied: "✅ Скопировано!",
        toastEarned: "🎉 +{amount} VC заработано!",
        rewardSuccess: "🎉 Вы заработали +{amount} VC!",
        toastCopied: "📋 Реферальная ссылка скопирована!",
        toastCopyFail: "⚠️ Не удалось скопировать. Скопируйте ссылку вручную.",
        toastAdNotAvail: "⚠️ Рекламный сервис недоступен. Попробуйте позже.",
        toastAdFailed: "⚠️ Не удалось загрузить рекламу. Попробуйте ещё раз.",
        toastWatchFull: "⏭️ Посмотрите видео полностью, чтобы получить награду.",
        toastS1Done: "🌅 Уровень 1 завершен!",
        toastS2Locked: "🔒 Уровень 2 ещё заблокирован!",
        toastS2Done: "🌌 Уровень 2 завершен!",
        toastLoadFail: "⚠️ Не удалось загрузить данные. Попробуйте ещё раз.",
        spamTooOften: "Упс! Вы слишком часто смотрите рекламу. Пожалуйста, подождите несколько секунд 🙏",
        spamNoAd: "Сейчас нет доступной рекламы. Попробуйте позже.",
        spamLongSession: "Ваша сессия слишком долгая. Пожалуйста, обновите страницу.",
        leagueBronze: "Бронзовая Лига",
        leagueSilver: "Серебряная Лига",
        leagueGold: "Золотая Лига",
        leaguePlatinum: "Платиновая Лига",
        leagueDiamond: "Алмазная Лига",
        upgradeSilverTitle: "🎉 ПОЗДРАВЛЯЕМ! 🎉",
        upgradeSilverText: "Вы перешли в ⚪ Серебряную Лигу! Ваш темп превосходен, продолжайте! 🚀",
        upgradeGoldTitle: "🔥 ПОТРЯСАЮЩЕ! 🔥",
        upgradeGoldText: "Теперь вы в 🟡 Золотой Лиге! Ваш баланс растёт, до вывода совсем немного! 💎",
        upgradePlatTitle: "👑 СЕНСАЦИЯ! 👑",
        upgradePlatText: "Крупный игрок! Вы получили статус 🔵 Платиновой Лиги! Вас невозможно остановить! 😎",
        upgradeDiamondTitle: "🌌 ЛЕГЕНДАРНО! 🌌",
        upgradeDiamondText: "Вот это да! Вы в 💎 Алмазной Лиге! Ворота вывода открыты для вас! 💰",
        upgradeBtn: "Вперёд! 🚀",
        nav_main: "Главная",
        nav_home: "Главная",
        splashTagline: "Смотри • Зарабатывай • Обменивай",
        nav_tasks: "Задания",
        nav_leaderboard: "Лидеры",
        task_sub: "Подписывайся на каналы и зарабатывай",
        btn_verify: "Проверить 🔄",
        btn_join: "Подписаться 🚀",
        tasks_empty_msg: "На данный момент активных заданий нет.",
        nav_store: "Магазин",
        store_soon: "Магазин скоро...",
        store_subtitle_soon: "VIP Статусы будут активны скоро!",
        vip_free_label: "Стандартная скорость",
        vip_free_price: "Бесплатно",
        vip_free_perk: "+200 VC за видео",
        vip_pro_title: "PRO Nitro",
        vip_elite_title: "ELITE Ultra",
        Pro_Price: "1.60 USDT / 1 Неделя",
        Elite_Price: "2.10 USDT / 1 Неделя",
        Pro_Line_1: "Ежедневно: 45 видео (Меньше усталости)",
        Pro_Line_2: "До +11 700 VC крупного заработка каждый день",
        Pro_Line_3: "🚀 130% Турбо Скорость генерации прибыли",
        Pro_Line_4: "+310 VC за задание",
        Elite_Line_1: "Ежедневно: 40 видео (Максимальная экономия)",
        Elite_Line_2: "До +14 000 VC рекордного заработка каждый день",
        Elite_Line_3: "🔥 175% Ультра Скорость и 0% комиссия на вывод",
        Elite_Line_4: "+400 VC за задание",
        vip_buy_btn: "Купить",
        Modal_Confirm_Text: "Вы подтверждаете покупку этого пакета?", 
        Modal_Btn_Cancel: "Отмена", 
        Modal_Btn_Confirm: "Подтвердить",
        Modal_Order_Msg: "Здравствуйте! Я хочу купить пакет {package}. Мой ID: {id}",
        Withdraw_Range_Notice: "Лимит разового вывода: 6 USDT - 60 USDT",
        Dashboard_Range: "Вывод: 6 USDT - 60 USDT",
        menu_leaderboard: "🏆 Лидеры",
        leaderboard_title: "Топ 25 по заработку",
        user_label: "Пользователь",
        balance_label: "Заработок",
        global_users: "пользователей",
        videoPreparing: "Подготовка нового видео...",
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
    localStorage.setItem('user_lang', currentLang);


    // Update all static elements with data-i18n attribute
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        const val = t(key);
        if (val) {
            if (val.includes('<svg')) {
                el.innerHTML = val;
            } else {
                el.textContent = val;
            }
        }
    });

    const proPriceEl = document.getElementById('pro-price-tag');
    if (proPriceEl) proPriceEl.innerText = LOCALES[currentLang].Pro_Price;
    
    const elitePriceEl = document.getElementById('elite-price-tag');
    if (elitePriceEl) elitePriceEl.innerText = LOCALES[currentLang].Elite_Price;

    const withdrawNoticeEl = document.getElementById('store-withdraw-notice');
    if (withdrawNoticeEl) withdrawNoticeEl.innerText = LOCALES[currentLang].Withdraw_Range_Notice;

    // Minimalist Withdrawal Range on dashboard card
    document.getElementById('dashboard-target-text').innerText = LOCALES[currentLang].withdrawalTarget;

    // Manually translate tasks-empty-msg if present in DOM
    const emptyMsgEl = document.getElementById('tasks-empty-msg');
    if (emptyMsgEl) {
        emptyMsgEl.textContent = t('tasks_empty_msg');
    }

    // Re-render dashboard with new language
    if (userData) {
        renderDashboard();
        
        // If Tasks tab is active, re-fetch and translate task elements
        const tasksTab = document.getElementById("tab-tasks-content");
        if (tasksTab && tasksTab.style.display === "block") {
            fetchTasks();
        }
    }

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
            checkWelcomeBonus(); // Check for welcome bonus after onboarding closes
        }, 400);
    }
}

function checkWelcomeBonus() {
    if (userData && userData.is_eligible_for_welcome_bonus) {
        const wbModal = document.getElementById("welcome-bonus-modal");
        if (wbModal) {
            wbModal.style.display = "flex";
            setTimeout(() => wbModal.classList.add("active"), 100);
        }
    }
}

async function closeWelcomeBonusModal() {
    const wbModal = document.getElementById("welcome-bonus-modal");
    if (wbModal) {
        wbModal.classList.remove("active");
        setTimeout(() => {
            wbModal.style.display = "none";
        }, 400);
    }
    if (currentUser && currentUser.id) {
        try {
            await fetch(`/api/user/${currentUser.id}/claim_welcome_bonus`, { method: "POST" });
            if (userData) userData.is_eligible_for_welcome_bonus = false;
        } catch (e) {
            console.error("Failed to mark welcome bonus as claimed", e);
        }
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

    // Watch button event listeners to handle clicking programmatically
    const s1Btn = document.getElementById("session-1-btn");
    const s2Btn = document.getElementById("session-2-btn");
    if (s1Btn) {
        s1Btn.onclick = null; // Explicitly unbind
        s1Btn.onclick = () => watchAd(1);
    }
    if (s2Btn) {
        s2Btn.onclick = null; // Explicitly unbind
        s2Btn.onclick = () => watchAd(2);
    }

    initApp();
});

function getImmediateBootLanguage() {
    // Priority 1: Explicitly saved user override from previous sessions
    const localSaved = localStorage.getItem('user_lang');
    if (localSaved && ['az', 'tr', 'en', 'ru'].includes(localSaved)) {
        return localSaved;
    }
    // Priority 2: Telegram Client Language Code
    if (window.Telegram?.WebApp?.initDataUnsafe?.user?.language_code) {
        const tgLang = window.Telegram.WebApp.initDataUnsafe.user.language_code.toLowerCase();
        if (['az', 'tr', 'en', 'ru'].includes(tgLang)) return tgLang;
    }
    // Priority 3: Global Application Default
    return 'az';
}

async function initApp() {
    // ── Load & evaluate 2-level ad state from localStorage ──────────────
    loadAdState();
    evaluateAdState();

    try {
        const urlParams = new URLSearchParams(window.location.search);

        // Telegram Web App-dan istifadəçini al
        if (tg?.initDataUnsafe?.user) {
            currentUser = tg.initDataUnsafe.user;
        } else {
            console.warn("Telegram daxilində deyil – test istifadəçi istifadə olunur.");
            currentUser = { id: 123456789, first_name: "TestUser" };
        }

        // Phase 1 (Instant Pre-Network Injection)
        const bootLang = getImmediateBootLanguage();
        currentLang = bootLang;
        localStorage.setItem('saved_language', currentLang);

        const taglineEl = document.querySelector('.splash-tagline');
        if (taglineEl) {
            taglineEl.textContent = t('splashTagline'); 
        }

        // Backend-dən istifadəçi məlumatlarını çək
        await fetchUserData();

        // Phase 2 (Post-Network Hydration Sync)
        let finalLang = bootLang;
        if (userData && userData.language && SUPPORTED_LANGS.includes(userData.language)) {
            finalLang = userData.language;
            localStorage.setItem('saved_language', finalLang);
            localStorage.setItem('user_lang', finalLang);
            localStorage.setItem('onboarding_completed', 'true');
        }

        if (finalLang !== bootLang) {
            console.log(`[LangDebug] Dual-phase sync: User language updated from ${bootLang} to ${finalLang}`);
            currentLang = finalLang;
            if (taglineEl) {
                taglineEl.textContent = t('splashTagline');
            }
        }

        // UI-ı yenilə
        renderDashboard();

        // Apply language to all static elements
        setLanguage(currentLang);

        // ── Sınaq / Reset Mexanizmi ──────────────────────────────────────────
        if (urlParams.get('reset') === 'true') {
            console.log(`[LangDebug] ?reset=true parametri tapıldı. Onboarding sıfırlanır...`);
            localStorage.removeItem('onboarding_completed');
        }

        // Check if onboarding is completed (set above if userData.language was present)
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
            // Ensure the modal stays hidden / is not rendered when onboarding is complete
            const obModal = document.getElementById("onboarding-modal");
            if (obModal) {
                obModal.style.display = "none";
                obModal.classList.remove("active");
            }
            console.log(`[LangDebug] Onboarding already completed, skipping modal.`);
            checkWelcomeBonus(); // Since onboarding is skipped, check for welcome bonus right away
        }

        // Əsas kontenti göstər, splash screen-i fade-out ilə gizlə
        document.getElementById("main-content").style.display = "block";
        const splashSuccess = document.getElementById("loader");
        if (splashSuccess) {
            splashSuccess.style.opacity = '0';
            splashSuccess.style.visibility = 'hidden';
            setTimeout(() => splashSuccess.remove(), 400);
        }

        // Start global user counter polling
        startGlobalStatsPolling();

    } catch (err) {
        console.error("Başlanğıc xətası:", err);
        document.getElementById("main-content").style.display = "block";
        const splashError = document.getElementById("loader");
        if (splashError) {
            splashError.style.opacity = '0';
            splashError.style.visibility = 'hidden';
            setTimeout(() => splashError.remove(), 400);
        }
        renderDashboard();
        setLanguage(currentLang);
        showToast(t('toastLoadFail'), "error");
    }
}

// ── İstifadəçi Məlumatlarını Çək (cache-busting ilə) ─────────────────
async function fetchUserData() {
    const currentFetchId = ++lastFetchId;
    const cacheBuster = Date.now();
    const url = `${API_BASE}/api/user/${currentUser.id}?_t=${cacheBuster}`;
    console.log(`[fetchUserData] Sorgu #${currentFetchId} göndərilir: ${url}`);

    try {
        const resp = await fetch(url, {
            method: "GET",
            headers: {
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "ngrok-skip-browser-warning": "true"
            }
        });

        console.log(`[fetchUserData] Cavab #${currentFetchId} alındı: status=${resp.status}`);

        if (!resp.ok) {
            if (resp.status === 404) {
                console.warn(`[fetchUserData] 404 - İstifadəçi ID=${currentUser.id} tapılmadı.`);
                if (currentFetchId === lastFetchId && !userData) {
                    userData = createDefaultUserData();
                }
                return null;
            }
            const errText = await resp.text();
            console.error(`[fetchUserData] API xətası: ${resp.status} | ${errText}`);
            if (currentFetchId === lastFetchId && !userData) {
                userData = createDefaultUserData();
            }
            return null;
        }

        const newData = await resp.json();
        console.log(`[fetchUserData] Backend data #${currentFetchId}: balance_mc=${newData.balance_mc}, videos_today=${newData.videos_today}`);

        if (currentFetchId !== lastFetchId) {
            console.log(`[fetchUserData] Sorgu #${currentFetchId} köhnəldiyi üçün imtina edildi (cari=${lastFetchId}).`);
            return newData;
        }

        if (newData && typeof newData.session_1_count === 'number' && typeof newData.session_2_count === 'number') {
            if (isRewardSyncing) {
                console.log(`[fetchUserData-GUARD] Stale server data ignored during active reward sync.`);
                if (userData) {
                    userData.referral_count = newData.referral_count;
                    userData.referral_earnings_mc = newData.referral_earnings_mc;
                }
                return newData;
            }

            userData = newData;
            syncAdStateFromUserData();
        } else {
            userData = newData;
        }
        return newData;

    } catch (err) {
        console.error("[fetchUserData] Şəbəkə xətası:", err);
        if (currentFetchId === lastFetchId && !userData) {
            userData = createDefaultUserData();
        }
        return null;
    }
}

function syncAdStateFromUserData() {
    if (!userData) return;
    const s1Count = userData.session_1_count || 0;
    const s2Count = userData.session_2_count || 0;
    const s2Locked = userData.session_2_locked ?? true;
    const unlockAtStr = userData.unlock_at;

    // Update LEVEL_LIMIT dynamically from API (Free=25, PRO=22, ELITE=20)
    if (userData.session_limit && userData.session_limit > 0) {
        LEVEL_LIMIT = userData.session_limit;
    }
    // Update LEVEL_2_LIMIT dynamically as remainder logic: daily_limit - session_limit
    const dailyLimit = userData.daily_limit || (LEVEL_LIMIT * MAX_LEVELS);
    LEVEL_2_LIMIT = dailyLimit - LEVEL_LIMIT;

    if (s1Count < LEVEL_LIMIT) {
        currentLevel = 1;
        levelClicks = s1Count;
        cooldownEndTime = 0;
    } else {
        if (s2Locked) {
            currentLevel = 1;
            levelClicks = LEVEL_LIMIT;
            if (unlockAtStr) {
                let tStr = unlockAtStr;
                if (typeof tStr === 'string' && !tStr.endsWith('Z') && !tStr.includes('+')) {
                    tStr += 'Z';
                }
                cooldownEndTime = new Date(tStr).getTime();
            } else {
                if (cooldownEndTime <= 0) {
                    cooldownEndTime = Date.now() + COOLDOWN_MS;
                }
            }
        } else {
            currentLevel = 2;
            levelClicks = s2Count;
            cooldownEndTime = 0;
        }
    }
    saveAdState();
}

function createDefaultUserData() {
    return {
        telegram_id: currentUser.id,
        first_name: currentUser.first_name || "İstifadəçi",
        balance_mc: 0,
        balance_azn: 0,
        total_earned_mc: 0,
        videos_today: 0,
        daily_limit: 24,
        referral_count: 0,
        referral_earnings_mc: 0,
        mc_per_video: 200,
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

    let unlockAtStr = unlockAt;
    if (typeof unlockAtStr === 'string' && !unlockAtStr.endsWith('Z') && !unlockAtStr.includes('+')) {
        unlockAtStr += 'Z';
    }
    const targetTime = new Date(unlockAtStr).getTime();

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
    balanceMcEl.textContent = formatNumber(userData.balance_vc !== undefined ? userData.balance_vc : 0);

    // Çıxarış Progress Bar -> Natively calculated against 10 AZN target
    const currentMc = userData.balance_mc || 0;
    
    // Natively compute progress percentage against the 10 AZN target
    let progressPct = Math.min(100, Math.max(0, (currentMc / 10) * 100));
    
    // Assign a league based on the progress (5 tiers, 20% each)
    let newLeagueIndex = 0;
    if (progressPct < 20) newLeagueIndex = 0;
    else if (progressPct < 40) newLeagueIndex = 1;
    else if (progressPct < 60) newLeagueIndex = 2;
    else if (progressPct < 80) newLeagueIndex = 3;
    else newLeagueIndex = 4;

    const LEAGUE_NAMES = [
        t('leagueBronze'), t('leagueSilver'), t('leagueGold'),
        t('leaguePlatinum'), t('leagueDiamond')
    ];

    let leagueName = LEAGUE_NAMES[newLeagueIndex];

    // Check for league upgrade
    if (currentLeagueIndex !== -1 && newLeagueIndex > currentLeagueIndex) {
        showUpgradeModal(newLeagueIndex);
    }
    currentLeagueIndex = newLeagueIndex;

    const pctStr = progressPct.toFixed(1);

    // Configuration map for high-tech minimalist shield/medal SVG vectors for each tier
    const LEAGUE_SVGS = {
        bronze: `<svg viewBox="0 0 24 24" width="100%" height="100%" fill="none" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="bronze-grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#f59e0b" stop-opacity="0.8" />
      <stop offset="50%" stop-color="#b45309" />
      <stop offset="100%" stop-color="#78350f" />
    </linearGradient>
    <filter id="bronze-glow" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="1.5" result="blur" />
      <feComposite in="SourceGraphic" in2="blur" operator="over" />
    </filter>
  </defs>
  <path d="M12 2L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-3z" fill="url(#bronze-grad)" filter="url(#bronze-glow)" stroke="#f59e0b" stroke-width="1" />
  <path d="M12 5l6 2v4c0 3.9-2.5 7.5-6 8.5-3.5-1-6-4.6-6-8.5V7l6-2z" fill="#78350f" opacity="0.3" />
  <circle cx="12" cy="12" r="3" fill="#f59e0b" opacity="0.9" />
</svg>`,
        silver: `<svg viewBox="0 0 24 24" width="100%" height="100%" fill="none" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="silver-grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#f3f4f6" />
      <stop offset="50%" stop-color="#9ca3af" />
      <stop offset="100%" stop-color="#4b5563" />
    </linearGradient>
    <filter id="silver-glow" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="1.5" result="blur" />
      <feComposite in="SourceGraphic" in2="blur" operator="over" />
    </filter>
  </defs>
  <path d="M12 2L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-3z" fill="url(#silver-grad)" filter="url(#silver-glow)" stroke="#e5e7eb" stroke-width="1" />
  <path d="M12 5l6 2v4c0 3.9-2.5 7.5-6 8.5-3.5-1-6-4.6-6-8.5V7l6-2z" fill="#4b5563" opacity="0.3" />
  <circle cx="12" cy="12" r="3" fill="#f3f4f6" opacity="0.9" />
</svg>`,
        gold: `<svg viewBox="0 0 24 24" width="100%" height="100%" fill="none" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="gold-grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#fef08a" />
      <stop offset="50%" stop-color="#eab308" />
      <stop offset="100%" stop-color="#854d0e" />
    </linearGradient>
    <filter id="gold-glow" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="1.5" result="blur" />
      <feComposite in="SourceGraphic" in2="blur" operator="over" />
    </filter>
  </defs>
  <path d="M12 2L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-3z" fill="url(#gold-grad)" filter="url(#gold-glow)" stroke="#facc15" stroke-width="1" />
  <path d="M12 5l6 2v4c0 3.9-2.5 7.5-6 8.5-3.5-1-6-4.6-6-8.5V7l6-2z" fill="#854d0e" opacity="0.3" />
  <polygon points="12,8 14,12 18,12 15,14 16,18 12,16 8,18 9,14 6,12 10,12" fill="#fff" opacity="0.95" />
</svg>`,
        platinum: `<svg viewBox="0 0 24 24" width="100%" height="100%" fill="none" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="plat-grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#a5f3fc" />
      <stop offset="50%" stop-color="#06b6d4" />
      <stop offset="100%" stop-color="#083344" />
    </linearGradient>
    <filter id="plat-glow" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="2" result="blur" />
      <feComposite in="SourceGraphic" in2="blur" operator="over" />
    </filter>
  </defs>
  <path d="M12 2L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-3z" fill="url(#plat-grad)" filter="url(#plat-glow)" stroke="#22d3ee" stroke-width="1.5" />
  <path d="M12 5l6 2v4c0 3.9-2.5 7.5-6 8.5-3.5-1-6-4.6-6-8.5V7l6-2z" fill="#083344" opacity="0.4" />
  <path d="M9 11l2 2 4-4" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
</svg>`,
        diamond: `<svg viewBox="0 0 24 24" width="100%" height="100%" fill="none" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="diamond-grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#e0f2fe" />
      <stop offset="30%" stop-color="#38bdf8" />
      <stop offset="70%" stop-color="#0284c7" />
      <stop offset="100%" stop-color="#0f172a" />
    </linearGradient>
    <filter id="diamond-glow" x="-30%" y="-30%" width="160%" height="160%">
      <feGaussianBlur stdDeviation="2" result="blur" />
      <feComposite in="SourceGraphic" in2="blur" operator="over" />
    </filter>
  </defs>
  <path d="M12 2L2 12l10 10 10-10L12 2z" fill="url(#diamond-grad)" filter="url(#diamond-glow)" stroke="#34d399" stroke-width="1.5" />
  <path d="M12 6L6 12l6 6 6-6-6-6z" fill="#0f172a" opacity="0.4" stroke="#38bdf8" stroke-width="0.5" />
  <polygon points="12,9 13.5,12 12,15 10.5,12" fill="#fff" />
</svg>`,
        default: `<svg viewBox="0 0 24 24" width="100%" height="100%" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M12 2L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-3z" fill="#4b5563" stroke="#9ca3af" stroke-width="1" />
</svg>`
    };

    const LEAGUE_KEYS = ['bronze', 'silver', 'gold', 'platinum', 'diamond'];
    const currentLeagueKey = LEAGUE_KEYS[newLeagueIndex] || 'bronze';

    const leagueNameEl = document.getElementById("league-name-label");
    const leagueIconContainer = document.getElementById("league-icon-container");
    if (leagueNameEl) leagueNameEl.textContent = leagueName;
    if (leagueIconContainer) {
        leagueIconContainer.innerHTML = LEAGUE_SVGS[currentLeagueKey] || LEAGUE_SVGS['default'];
    }


    const withdrawalPctEl = document.getElementById("withdrawal-pct");
    if (withdrawalPctEl) withdrawalPctEl.textContent = pctStr;

    const withdrawalFillEl = document.getElementById("withdrawal-progress-fill");
    if (withdrawalFillEl) withdrawalFillEl.style.width = `${progressPct}%`;

    // Withdrawal target label
    const dashboardTargetEl = document.getElementById("dashboard-target-text");
    if (dashboardTargetEl) dashboardTargetEl.innerText = LOCALES[currentLang].withdrawalTarget;

    // Statistika
    document.getElementById("total-earned").textContent = formatNumber(userData.total_earned_vc !== undefined ? userData.total_earned_vc : 0);
    const dynDailyLimit = userData.daily_limit || (LEVEL_LIMIT * MAX_LEVELS);
    document.getElementById("videos-count").textContent = `${(userData.session_1_count || 0) + (userData.session_2_count || 0)}/${dynDailyLimit}`;
    document.getElementById("referral-count").textContent = userData.referral_count;
    document.getElementById("referral-earnings").textContent = formatNumber(userData.referral_earnings_mc);

    // ── 2-Level Ad System Rendering ──────────────────────────────────
    evaluateAdState();

    const s1Count = userData.session_1_count || 0;
    const s2Count = userData.session_2_count || 0;
    const now = Date.now();
    const isCooling = currentLevel === 1 && levelClicks >= LEVEL_LIMIT && cooldownEndTime > 0 && now < cooldownEndTime;

    // ── Session 1 / Mərhələ 1 Card ───────────────────────────────────
    document.getElementById("session-1-progress-text").textContent = `${Math.min(s1Count, LEVEL_LIMIT)} / ${LEVEL_LIMIT} Video`;
    document.getElementById("session-1-progress-fill").style.width = `${Math.min((s1Count / LEVEL_LIMIT) * 100, 100)}%`;
    const s1Btn = document.getElementById("session-1-btn");

    if (s1Count >= LEVEL_LIMIT) {
        // Level 1 complete
        s1Btn.disabled = true;
        s1Btn.innerHTML = t('completedS1');
        s1Btn.classList.add("completed");
        s1Btn.style.cssText = '';
    } else if (isBtnCooldownActive) {
        s1Btn.disabled = true;
        s1Btn.style.background = '#1f293d';
        s1Btn.style.boxShadow = 'none';
        s1Btn.style.color = '#6b7280';
        s1Btn.style.opacity = '1';
        s1Btn.style.pointerEvents = 'none';
        s1Btn.style.transform = 'none';
        s1Btn.style.filter = 'none';
        s1Btn.style.textShadow = 'none';
    } else {
        s1Btn.disabled = false;
        s1Btn.innerHTML = `${t('watchBtn')} ${userData.mc_per_video || 200} ${t('watchBtnSuffix')}`;
        s1Btn.classList.remove("completed");
        s1Btn.style.cssText = '';
    }

    // ── Session 2 / Mərhələ 2 Card ───────────────────────────────────
    const s2Btn  = document.getElementById("session-2-btn");
    const s2Hint = document.getElementById("session-2-cooldown-hint");

    if (isCooling) {
        // 3-hour inter-level cooldown is active
        s2Btn.disabled = true;
        s2Btn.classList.remove("completed");
        s2Btn.style.background = '#1f293d';
        s2Btn.style.boxShadow = 'none';
        s2Btn.style.color = '#6b7280';
        s2Btn.style.opacity = '1';
        s2Btn.style.pointerEvents = 'none';
        s2Btn.style.transform = 'none';
        s2Btn.style.filter = 'none';
        s2Btn.style.textShadow = 'none';

        // Show ticking countdown inside the Level 2 button area
        const remaining = cooldownEndTime - now;
        const hh = Math.floor(remaining / 3600000);
        const mm = Math.floor((remaining % 3600000) / 60000);
        const ss = Math.floor((remaining % 60000) / 1000);
        const pad = n => String(n).padStart(2, '0');
        document.getElementById("session-2-progress-text").textContent = `0 / ${LEVEL_2_LIMIT} Video`;
        document.getElementById("session-2-progress-fill").style.width = '0%';
        s2Btn.textContent = `⏳ ${t('lock_countdown') || 'Növbəti mərhələ:'} ${pad(hh)}:${pad(mm)}:${pad(ss)}`;
        s2Hint.style.display = 'none';

        // Start the live countdown ticker
        startLevel2CooldownTicker();
    } else if (currentLevel === 2 || (s1Count >= LEVEL_LIMIT && cooldownEndTime === 0)) {
        // Level 2 is active (cooldown cleared)
        stopLevel2CooldownTicker();
        document.getElementById("session-2-progress-text").textContent = `${Math.min(s2Count, LEVEL_2_LIMIT)} / ${LEVEL_2_LIMIT} Video`;
        document.getElementById("session-2-progress-fill").style.width = `${Math.min((s2Count / LEVEL_2_LIMIT) * 100, 100)}%`;
        s2Hint.style.display = 'none';

        if (s2Count >= LEVEL_2_LIMIT) {
            // All done for the day
            s2Btn.disabled = true;
            s2Btn.innerHTML = '<svg class="btn-inline-icon" style="stroke: #06b6d4;" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg> Gündəlik limit bitdi! Sabah gəl.';
            s2Btn.classList.add("completed");
            s2Btn.style.cssText = '';
        } else if (isBtnCooldownActive) {
            s2Btn.disabled = true;
            s2Btn.style.background = '#1f293d';
            s2Btn.style.boxShadow = 'none';
            s2Btn.style.color = '#6b7280';
            s2Btn.style.opacity = '1';
            s2Btn.style.pointerEvents = 'none';
            s2Btn.style.transform = 'none';
            s2Btn.style.filter = 'none';
            s2Btn.style.textShadow = 'none';
        } else {
            s2Btn.disabled = false;
            s2Btn.innerHTML = `${t('watchBtn')} ${userData.mc_per_video || 200} ${t('watchBtnSuffix')}`;
            s2Btn.classList.remove("completed");
            s2Btn.style.cssText = '';
        }
    } else {
        // Level 2 locked — Level 1 not yet complete
        stopLevel2CooldownTicker();
        document.getElementById("session-2-progress-text").textContent = `0 / ${LEVEL_2_LIMIT} Video`;
        document.getElementById("session-2-progress-fill").style.width = '0%';
        s2Btn.disabled = true;
        s2Btn.innerHTML = t('finishFirst');
        s2Btn.classList.remove("completed");
        s2Btn.style.cssText = '';
        s2Hint.style.display = 'none';
        stopCooldownTimer();
    }

    // Referal bölməsi
    const botUsername = "QazanAz_bot";
    const refLink = `https://t.me/${botUsername}?start=${currentUser.id}`;
    document.getElementById("referral-link").textContent = refLink;
    document.getElementById("ref-friends").textContent = userData.referral_count;
    document.getElementById("ref-earned").textContent = formatNumber(userData.referral_earnings_mc);
}

// ── Level 2 Countdown Ticker ─────────────────────────────────────────
let _level2TickerInterval = null;

function startLevel2CooldownTicker() {
    if (_level2TickerInterval) return; // already running
    _level2TickerInterval = setInterval(() => {
        evaluateAdState();
        renderDashboard();
    }, 1000);
}

function stopLevel2CooldownTicker() {
    if (_level2TickerInterval) {
        clearInterval(_level2TickerInterval);
        _level2TickerInterval = null;
    }
}

// ── Onclicka TMA Ad Engine ────────────────────────────────────────────
/**
 * Dispaly a rewarded ad via the Onclicka TMA SDK.
 * sessionNum: 1 → Mərhələ 1, 2 → Mərhələ 2
 */
let currentWatchingSession = 1;

// Mutex: prevents re-entry during the post-ad cooldown
let isBtnCooldownActive = false;
let isRewardSyncing = false;
let lastFetchId = 0;
let cooldownRemaining = 0;
let _btnCooldownTimerId = null;

let isAdRunning = false;

async function watchAd(sessionNum = 1) {
    if (isAdRunning) return;
    isAdRunning = true;
    
    const watchBtn = document.getElementById(`session-${sessionNum}-btn`);
    if (watchBtn) watchBtn.disabled = true; // Immediately disable

    try {
        await _watchAdImpl(sessionNum);
    } finally {
        isAdRunning = false;
        // Allow button to be active again if not in cooldown
        if (!isBtnCooldownActive && watchBtn) {
            watchBtn.disabled = false;
        }
    }
}

async function _watchAdImpl(sessionNum = 1) {
    // Guard: mutex cooldown
    if (isBtnCooldownActive) return;

    // Guard: Adsgram SDK not yet ready
    if (!AdController) {
        showToast(t('toastAdNotAvail'), "error");
        return;
    }

    if (!userData) return;
    currentWatchingSession = sessionNum;

    // Evaluate & validate state
    evaluateAdState();

    const s1Count = userData.session_1_count || 0;
    const s2Count = userData.session_2_count || 0;
    const now = Date.now();
    const isCooling = currentLevel === 1 && levelClicks >= LEVEL_LIMIT && cooldownEndTime > 0 && now < cooldownEndTime;

    if (sessionNum === 1) {
        if (s1Count >= LEVEL_LIMIT) {
            showToast(t('toastS1Done'), "error");
            return;
        }
    } else if (sessionNum === 2) {
        if (isCooling) {
            showToast(t('toastS2Locked'), "error");
            return;
        }
        if (currentLevel < 2 && s1Count < LEVEL_LIMIT) {
            showToast(t('toastS2Locked'), "error");
            return;
        }
        if (s2Count >= LEVEL_2_LIMIT) {
            showToast(t('toastS2Done'), "error");
            return;
        }
    }

    const watchBtn = document.getElementById(`session-${sessionNum}-btn`);
    const otherBtn = document.getElementById(`session-${sessionNum === 1 ? 2 : 1}-btn`);

    watchBtn.disabled = true;
    watchBtn.textContent = t('adLoading');
    if (otherBtn) otherBtn.disabled = true;

    try {
        const result = await AdController.show();
        console.log('[Adsgram] Ad completed successfully:', result);
        
        watchBtn.textContent = t('rewardCalc');
        await executeAdSuccessReward(sessionNum);
        spawnCoinBurst();
        showToast(t('rewardSuccess').replace('{amount}', userData.mc_per_video || 200), "success");
    } catch (error) {
        console.error('[Adsgram] Ad playback tracking state failed/skipped:', error);
        
        // Handle gracefully based on whether user skipped or script failed to load
        if (error && (error.userExit || error.done === false)) {
            showToast(t('toastWatchFull'), "error");
        } else {
            showToast(t('toastAdFailed'), "error");
        }
    } finally {
        renderDashboard();
        startButtonCooldown(sessionNum);
    }
}

// ── Button post-ad cooldown (7-10 seconds jitter, Premium Progress Bar) ─────────
function startButtonCooldown(sessionNum, seconds = null) {
    const btn      = document.getElementById(`session-${sessionNum}-btn`);
    const otherBtn = document.getElementById(`session-${sessionNum === 1 ? 2 : 1}-btn`);

    isBtnCooldownActive = true;

    // Generate jitter cooldown between 7 and 10 seconds inclusive
    if (seconds === null) {
        seconds = Math.floor(Math.random() * (10 - 7 + 1)) + 7;
    }

    if (_btnCooldownTimerId !== null) {
        clearTimeout(_btnCooldownTimerId);
        _btnCooldownTimerId = null;
    }

    function applyDisabledStyles(el, isMainBtn) {
        if (!el) return;
        el.disabled = true;
        el.style.background    = '#1f293d';
        el.style.boxShadow     = 'none';
        el.style.color         = isMainBtn ? '#ffffff' : '#6b7280';
        el.style.opacity       = '1';
        el.style.pointerEvents = 'none';
        el.style.transform     = 'none';
        el.style.filter        = 'none';
        el.style.textShadow    = 'none';
        
        if (isMainBtn) {
            el.style.position = 'relative';
            el.style.overflow = 'hidden';
            el.style.border = '1px solid rgba(6, 182, 212, 0.3)';
        }
    }

    function clearDisabledStyles(el) {
        if (!el) return;
        el.disabled            = false;
        el.style.background    = '';
        el.style.boxShadow     = '';
        el.style.color         = '';
        el.style.opacity       = '';
        el.style.pointerEvents = '';
        el.style.transform     = '';
        el.style.filter        = '';
        el.style.textShadow    = '';
        el.style.position      = '';
        el.style.overflow      = '';
        el.style.border        = '';
    }

    applyDisabledStyles(btn, true);
    applyDisabledStyles(otherBtn, false);

    cooldownRemaining = seconds;

    if (btn) {
        btn.innerHTML = `
            <div id="cooldown-progress-bar" style="
                position: absolute;
                top: 0;
                left: 0;
                height: 100%;
                width: 0%;
                background: linear-gradient(135deg, #06b6d4, #00ffcc);
                transition: width ${seconds}s linear;
                z-index: 1;
                opacity: 0.85;
            "></div>
            <span style="position: relative; z-index: 2; font-weight: 700; color: #ffffff; text-shadow: 0 1px 3px rgba(0,0,0,0.6); letter-spacing: 0.5px;">${t('videoPreparing')}</span>
        `;
        
        // Trigger reflow to apply the CSS transition smoothly
        void btn.offsetHeight;
        
        // Start animation
        setTimeout(() => {
            const bar = document.getElementById('cooldown-progress-bar');
            if (bar) bar.style.width = '100%';
        }, 50);
    }
    
    if (otherBtn) {
        otherBtn.textContent = `${t('waitSec')}...`;
    }

    // Set a timeout to clear the state once the exact random duration has finished animating
    _btnCooldownTimerId = setTimeout(() => {
        _btnCooldownTimerId = null;
        clearDisabledStyles(btn);
        if (otherBtn) clearDisabledStyles(otherBtn);
        isBtnCooldownActive = false;
        cooldownRemaining = 0;
        renderDashboard(); // Restore original UI structure via the render loop
    }, seconds * 1000);
}

// ── Reward Lifecycle Engine ───────────────────────────────────────────
/**
 * Called immediately after a successful ad completion.
 * Applies optimistic local state update, then fires backend sync.
 */
async function executeAdSuccessReward(sessionNum) {
    if (!userData) return;

    // Set reward syncing flag to true
    isRewardSyncing = true;

    const reward = userData.mc_per_video || 200;

    // ── 1. Optimistic UI update ────────────────────────────────────────
    userData.balance_mc      += reward; // Keep internal AZN float updated if needed
    userData.balance_vc      = (userData.balance_vc || 0) + (userData.mc_per_video || 200);
    userData.total_earned_mc += reward;
    userData.total_earned_vc = (userData.total_earned_vc || 0) + (userData.mc_per_video || 200);
    userData.videos_today    = (userData.videos_today || 0) + 1;

    if (sessionNum === 1) {
        userData.session_1_count = (userData.session_1_count || 0) + 1;
        levelClicks = userData.session_1_count;

        // Level 1 just completed → start 3-hour cooldown
        if (userData.session_1_count >= LEVEL_LIMIT && currentLevel === 1) {
            cooldownEndTime = Date.now() + COOLDOWN_MS;
            saveAdState();
        } else {
            saveAdState();
        }
    } else if (sessionNum === 2) {
        userData.session_2_count = (userData.session_2_count || 0) + 1;
        levelClicks = userData.session_2_count;
        saveAdState();
    }

    // ── 2. Animate balance ────────────────────────────────────────────
    const balEl = document.getElementById('balance-mc');
    if (balEl) {
        balEl.style.transition = 'transform 0.3s cubic-bezier(0.34,1.56,0.64,1), color 0.3s';
        balEl.style.transform = 'scale(1.12)';
        balEl.style.color = '#00ffcc';
        setTimeout(() => {
            balEl.style.transform = 'scale(1)';
            balEl.style.color = '';
        }, 400);
    }

    renderDashboard();

    // ── 3. Fire backend sync (non-blocking) ───────────────────────────
    try {
        // Explicitly trigger the reward on the backend (Adsgram backend configuration uses event_id uniquely)
        await fetch(`${API_BASE}/api/reward?userId=${currentUser.id}&event_id=adsgram_${Date.now()}_${Math.random()}`);
    } catch (err) {
        console.error("[Reward] Backend trigger error:", err);
    }

    scheduleServerSync(4, 2500);
}


/**
 * Server ilə sinxronlaşdırma
 */
function scheduleServerSync(maxRetries, delayMs) {
    let attempt = 0;
    const targetBalance = userData ? userData.balance_mc : 0;

    function trySync() {
        attempt++;
        console.log(`[SYNC] Cəhd ${attempt}/${maxRetries} — ${delayMs * attempt}ms sonra...`);

        setTimeout(async () => {
            try {
                const newData = await fetchUserData();
                renderDashboard();

                const currentServerBalance = newData ? newData.balance_mc : 0;
                console.log(`[SYNC] Cəhd ${attempt} tamamlandı: server_balans=${currentServerBalance} | hedef=${targetBalance}`);

                if (currentServerBalance < targetBalance && attempt < maxRetries) {
                    trySync();
                } else {
                    isRewardSyncing = false;
                    // Trigger a final fetch to apply the server data and remove the sync guard
                    await fetchUserData();
                    renderDashboard();
                }
            } catch (err) {
                console.error(`[SYNC] Cəhd ${attempt} xətası:`, err);
                if (attempt < maxRetries) {
                    trySync();
                } else {
                    isRewardSyncing = false;
                }
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
    }, 2500);
}

// ── Yardımçı (Format) ────────────────────────────────────────────────
function formatNumber(num) {
    if (num === undefined || num === null) return "0";
    return Math.floor(num).toLocaleString("az-AZ");
}

// ── Tabs Navigation ──────────────────────────────────────────────────
function switchTab(tabId) {
    const mainTab = document.getElementById("tab-main-content");
    const tasksTab = document.getElementById("tab-tasks-content");
    const storeTab = document.getElementById("tab-store-content");
    const leaderboardTab = document.getElementById("tab-leaderboard-content");
    
    const navMain = document.getElementById("nav-main");
    const navTasks = document.getElementById("nav-tasks");
    const navStore = document.getElementById("nav-store");
    const navLeaderboard = document.getElementById("nav-leaderboard");

    if (!mainTab || !tasksTab || !storeTab || !leaderboardTab) return;

    if (tabId === 'main') {
        mainTab.style.display = "block";
        tasksTab.style.display = "none";
        storeTab.style.display = "none";
        leaderboardTab.style.display = "none";
        
        if (navMain) navMain.classList.add("active");
        if (navTasks) navTasks.classList.remove("active");
        if (navStore) navStore.classList.remove("active");
        if (navLeaderboard) navLeaderboard.classList.remove("active");
    } else if (tabId === 'tasks') {
        mainTab.style.display = "none";
        tasksTab.style.display = "block";
        storeTab.style.display = "none";
        leaderboardTab.style.display = "none";
        
        if (navTasks) navTasks.classList.add("active");
        if (navMain) navMain.classList.remove("active");
        if (navStore) navStore.classList.remove("active");
        if (navLeaderboard) navLeaderboard.classList.remove("active");
        fetchTasks();
        
        // Auto-trigger AdsGram Task Wall on tab switch
        if (window.Adsgram) {
            try {
                const taskBlock = window.Adsgram.initTask({ blockId: "task-34381" });
                taskBlock.show().then((result) => {
                    let calcAmount = 250;
                    if (userData && userData.vip_status) {
                        if (userData.vip_status === "pro") calcAmount = 310;
                        else if (userData.vip_status === "elite") calcAmount = 400;
                    }
                    showToast(t('rewardSuccess').replace('{amount}', calcAmount), "success");
                }).catch((result) => {
                    console.log("AdsGram task failed or closed", result);
                });
            } catch (e) {
                console.error("AdsGram init error:", e);
            }
        }
    } else if (tabId === 'store') {
        mainTab.style.display = "none";
        tasksTab.style.display = "none";
        storeTab.style.display = "block";
        leaderboardTab.style.display = "none";
        
        if (navStore) navStore.classList.add("active");
        if (navMain) navMain.classList.remove("active");
        if (navTasks) navTasks.classList.remove("active");
        if (navLeaderboard) navLeaderboard.classList.remove("active");
    } else if (tabId === 'leaderboard') {
        mainTab.style.display = "none";
        tasksTab.style.display = "none";
        storeTab.style.display = "none";
        leaderboardTab.style.display = "block";
        
        if (navLeaderboard) navLeaderboard.classList.add("active");
        if (navMain) navMain.classList.remove("active");
        if (navTasks) navTasks.classList.remove("active");
        if (navStore) navStore.classList.remove("active");
        fetchLeaderboard();
    }
}

// ── Leaderboard Logic ────────────────────────────────────────────────
async function fetchLeaderboard() {
    const container = document.getElementById("leaderboard-list");
    if (!container) return;
    
    container.innerHTML = `<div style="text-align:center; padding: 20px; color: var(--text-muted);">Yüklənir...</div>`;
    
    try {
        const resp = await fetch(`${API_BASE}/api/leaderboard`);
        if (!resp.ok) throw new Error("Failed to load leaderboard");
        const data = await resp.json();
        
        if (!data.leaderboard || data.leaderboard.length === 0) {
            container.innerHTML = `<div style="text-align:center; padding: 20px; color: var(--text-muted);">No users found.</div>`;
            return;
        }
        
        container.innerHTML = "";
        data.leaderboard.forEach((user, index) => {
            const row = document.createElement("div");
            row.className = "leaderboard-row";
            
            // Gold, Silver, Bronze classes
            let rankClass = "";
            let rankDisplay = `${index + 1}`;
            if (index === 0) {
                rankClass = "rank-gold";
                rankDisplay = `<svg viewBox="0 0 24 24" width="20" height="20" fill="#FFD700" style="display:inline-block;vertical-align:middle;"><circle cx="12" cy="9" r="6"/><path d="M9 14.2L5 22l4-2 4 2-2.3-4.5"/><path d="M15 14.2l4 7.8-4-2-4 2 2.3-4.5"/></svg>`;
            } else if (index === 1) {
                rankClass = "rank-silver";
                rankDisplay = `<svg viewBox="0 0 24 24" width="20" height="20" fill="#E2E8F0" style="display:inline-block;vertical-align:middle;"><circle cx="12" cy="9" r="6"/><path d="M9 14.2L5 22l4-2 4 2-2.3-4.5"/><path d="M15 14.2l4 7.8-4-2-4 2 2.3-4.5"/></svg>`;
            } else if (index === 2) {
                rankClass = "rank-bronze";
                rankDisplay = `<svg viewBox="0 0 24 24" width="20" height="20" fill="#FF7F50" style="display:inline-block;vertical-align:middle;"><circle cx="12" cy="9" r="6"/><path d="M9 14.2L5 22l4-2 4 2-2.3-4.5"/><path d="M15 14.2l4 7.8-4-2-4 2 2.3-4.5"/></svg>`;
            }
            
            if (rankClass) {
                row.classList.add(rankClass);
            }
            
            // VIP SVGs
            let vipSvg = "";
            if (user.vip_status === "elite") {
                vipSvg = `<svg class="vip-icon elite-glow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:16px;height:16px;margin-left:5px;vertical-align:middle;color:#00ffcc;"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon></svg>`;
            } else if (user.vip_status === "pro") {
                vipSvg = `<svg class="vip-icon pro-glow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:16px;height:16px;margin-left:5px;vertical-align:middle;color:#ff00ff;"><path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2l.5-.5m10-10l-10 10-3-3 10-10c2.76-2.76 7.24-2.76 7.24-2.76s0 4.48-2.76 7.24z"></path></svg>`;
            }

            row.innerHTML = `
                <span class="rank">${rankDisplay}</span>
                <span class="username">${user.first_name}${vipSvg}</span>
                <span class="balance">${Number(user.balance_mc).toLocaleString()} VC</span>
            `;
            container.appendChild(row);
        });
        
    } catch (err) {
        console.error("Leaderboard fetch error:", err);
        container.innerHTML = `<div style="text-align:center; padding: 20px; color: var(--text-muted);">Xəta baş verdi.</div>`;
    }
}

// ── Tasks Logic ──────────────────────────────────────────────────────
async function fetchTasks() {
    const container = document.getElementById("tasks-list-container");
    if (!container) return;
    
    container.innerHTML = `<div style="text-align:center; padding: 20px; color: var(--text-muted);">Yüklənir...</div>`;
    
    if (!currentUser) return;
    
    try {
        const resp = await fetch(`${API_BASE}/api/tasks?telegram_id=${currentUser.id}&initData=${encodeURIComponent(tg.initData || '')}`);
        if (!resp.ok) throw new Error("Failed to load tasks");
        const data = await resp.json();
        
        const adminBtn = document.getElementById("admin-add-task-btn");
        if (adminBtn) {
            adminBtn.style.display = data.is_admin ? "block" : "none";
        }
        
        if (!data.tasks || data.tasks.length === 0) {
            container.innerHTML = `<div id="tasks-empty-msg" style="text-align:center; padding: 20px; color: var(--text-muted);" data-i18n="tasks_empty_msg">${t('tasks_empty_msg')}</div>`;
            return;
        }
        
        container.innerHTML = "";
        data.tasks.forEach(task => {
            const card = document.createElement("div");
            card.className = "task-card";
            card.innerHTML = `
                <div class="task-info">
                    <div class="task-title">${task.title}</div>
                    <div class="task-reward">+${task.reward_amount} VC</div>
                </div>
                <div class="task-actions">
                    <a href="${task.channel_url}" target="_blank" class="task-btn task-btn-join">${t('btn_join')}</a>
                    <button class="task-btn task-btn-verify" onclick="verifyTask(${task.id})">${t('btn_verify')}</button>
                </div>
            `;
            container.appendChild(card);
        });
    } catch (err) {
        console.error("fetchTasks error:", err);
        container.innerHTML = `<div style="text-align:center; padding: 20px; color: var(--accent-rose);">Tapşırıqlar yüklənə bilmədi.</div>`;
    }
}

async function verifyTask(taskId) {
    if (!tg || !tg.initData) {
        showToast("Təhlükəsizlik xətası: Telegram mühiti tapılmadı", "error");
        return;
    }
    
    try {
        const resp = await fetch(`${API_BASE}/api/tasks/verify`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                task_id: taskId,
                initData: tg.initData
            })
        });
        
        const data = await resp.json();
        
        if (resp.ok && data.ok) {
            showToast(t('rewardSuccess').replace('{amount}', data.reward), "success");
            spawnCoinBurst();
            
            // Update local balance
            if (userData) {
                userData.balance_mc = data.new_balance;
                if (data.new_balance_vc !== undefined) {
                    userData.balance_vc = data.new_balance_vc;
                }
                renderDashboard();
            }
            
            // Remove task from list or refresh
            fetchTasks();
        } else {
            showToast(data.message || "Uğursuz yoxlama.", "error");
        }
    } catch (err) {
        console.error("verifyTask error:", err);
        showToast("Xəta baş verdi. Yenidən cəhd edin.", "error");
    }
}
// ── Admin Modal Handlers ─────────────────────────────────────────────
function openAdminTaskModal() {
    const modal = document.getElementById("admin-task-modal");
    if (modal) modal.classList.add("open");
}

function closeAdminTaskModal() {
    const modal = document.getElementById("admin-task-modal");
    if (modal) {
        modal.classList.remove("open");
        // Clear inputs
        document.getElementById("admin-task-title").value = "";
        document.getElementById("admin-task-channel-id").value = "";
        document.getElementById("admin-task-channel-url").value = "";
        document.getElementById("admin-task-reward").value = "";
    }
}

async function submitAdminTask() {
    const title = document.getElementById("admin-task-title").value.trim();
    const channelId = document.getElementById("admin-task-channel-id").value.trim();
    const channelUrl = document.getElementById("admin-task-channel-url").value.trim();
    const rewardVal = document.getElementById("admin-task-reward").value.trim();
    
    if (!title || !channelId || !channelUrl || !rewardVal) {
        showToast("Zəhmət olmasa bütün xanaları doldurun", "error");
        return;
    }
    
    const rewardAmount = parseFloat(rewardVal);
    if (isNaN(rewardAmount) || rewardAmount <= 0) {
        showToast("Mükafat düzgün məbləğ olmalıdır", "error");
        return;
    }
    
    if (!tg || !tg.initData) {
        showToast("Təhlükəsizlik xətası: Telegram initData tapılmadı", "error");
        return;
    }
    
    try {
        const resp = await fetch(`${API_BASE}/api/admin/add-task`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                initData: tg.initData,
                title: title,
                channel_id: channelId,
                channel_url: channelUrl,
                reward_amount: rewardAmount
            })
        });
        
        const data = await resp.json();
        if (resp.ok && data.ok) {
            showToast("🎉 Tapşırıq uğurla yaradıldı!", "success");
            closeAdminTaskModal();
            fetchTasks(); // Reload task list
        } else {
            showToast(data.message || "Xəta baş verdi", "error");
        }
    } catch (err) {
        console.error("submitAdminTask error:", err);
        showToast("Şəbəkə xətası, yenidən cəhd edin", "error");
    }
}

// ── VIP Purchase Handler ─────────────────────────────────────────────
function handleVipPurchase(tier) {
    selectedVipPackage = tier;
    
    document.getElementById('vip-modal-text').textContent = t('Modal_Confirm_Text');
    document.getElementById('vip-cancel-btn').textContent = t('Modal_Btn_Cancel');
    document.getElementById('vip-confirm-btn').textContent = t('Modal_Btn_Confirm');
    
    document.getElementById('vip-modal').style.display = 'flex';
}

let selectedVipPackage = "";

function closeVipModal() {
    document.getElementById('vip-modal').style.display = 'none';
    selectedVipPackage = "";
}

function confirmVipPurchase() {
    const tierName = selectedVipPackage === 'pro' ? t('vip_pro_title') : t('vip_elite_title');
    const priceStr = selectedVipPackage === 'pro' ? LOCALES[currentLang].Pro_Price : LOCALES[currentLang].Elite_Price;
    const packageInfo = `${tierName} (${priceStr})`;
    
    const msgTemplate = t('Modal_Order_Msg');
    const formattedMsg = msgTemplate.replace('{package}', packageInfo).replace('{id}', userData?.telegram_id || currentUser?.id || "Unknown");
    const msg = encodeURIComponent(formattedMsg);
    const tgUrl = "https://t.me/NoYouOkk?text=" + msg;
    
    if (window.Telegram && window.Telegram.WebApp) {
        window.Telegram.WebApp.openTelegramLink(tgUrl);
    } else {
        window.open(tgUrl, "_blank");
    }
    closeVipModal();
}

// Bind modal buttons when DOM is loaded
document.addEventListener("DOMContentLoaded", () => {
    const cancelBtn = document.getElementById('vip-cancel-btn');
    const confirmBtn = document.getElementById('vip-confirm-btn');
    if (cancelBtn) cancelBtn.addEventListener('click', closeVipModal);
    if (confirmBtn) confirmBtn.addEventListener('click', confirmVipPurchase);
});

// ── Global User Stats Counter ──────────────────────────────────────────
let globalUserCount = 0;
let statsFetchIntervalId = null;

async function fetchGlobalStats() {
    try {
        const resp = await fetch(`${API_BASE}/api/global-stats`, {
            method: "GET",
            headers: {
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "ngrok-skip-browser-warning": "true"
            }
        });
        if (resp.ok) {
            const data = await resp.json();
            if (data && typeof data.total_users === 'number') {
                // To completely guarantee the counter never jumps backwards
                globalUserCount = Math.max(globalUserCount, data.total_users);
                updateGlobalUserCountUI(globalUserCount);
            }
        }
    } catch (err) {
        console.error("Error fetching global stats:", err);
    }
}

function updateGlobalUserCountUI(count) {
    const el = document.getElementById("global-user-count");
    if (el) {
        el.textContent = count.toLocaleString('en-US');
    }
}

function startGlobalStatsPolling() {
    // Fetch immediately
    fetchGlobalStats();

    // Poll strictly once every 60 seconds (60000 ms)
    if (!statsFetchIntervalId) {
        statsFetchIntervalId = setInterval(fetchGlobalStats, 60000);
    }
}

