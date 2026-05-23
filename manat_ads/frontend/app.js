/**
 * ManatAds – Mini App Frontend Logic (AZ)
 * =========================================
 * Integrates with:
 *   • Telegram Web App SDK (istifadəçi kimliyi + tema)
 *   • Adsgram SDK (video reklamlar – .show(), .then(), .catch())
 *   • ManatAds Backend API (istifadəçi məlumatı + mükafat callback)
 */

// ── Konfiqurasiya ─────────────────────────────────────────────────────
const API_BASE = ""; // Vercel vasitəsilə proxy
const ADSGRAM_BLOCK_ID = "31453";

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

    initApp();
});

// ── Tətbiqin Başlanğıcı ──────────────────────────────────────────────
async function initApp() {
    try {
        // Telegram Web App-dan istifadəçini al
        if (tg?.initDataUnsafe?.user) {
            currentUser = tg.initDataUnsafe.user;
        } else {
            // Telegram xaricində inkişaf / test üçün
            console.warn("Telegram daxilində deyil – test istifadəçi istifadə olunur.");
            currentUser = { id: 123456789, first_name: "TestUser" };
        }

        // Backend-dən istifadəçi məlumatlarını çək
        await fetchUserData();

        // Əsas kontenti göstər
        document.getElementById("loader").style.display = "none";
        document.getElementById("main-content").style.display = "block";

        // UI-ı yenilə
        renderDashboard();

    } catch (err) {
        console.error("Başlanğıc xətası:", err);
        showToast("Tətbiq yüklənmədi. Yenidən cəhd edin.", "error");
    }
}

// ── İstifadəçi Məlumatlarını Çək ─────────────────────────────
async function fetchUserData() {
    const url = `${API_BASE}/api/user/${currentUser.id}`;
    console.log(`[fetchUserData] Sorgu göndərilir: ${url} | currentUser.id=${currentUser.id}`);

    try {
        const resp = await fetch(url, {
            headers: { "ngrok-skip-browser-warning": "true" }
        });

        console.log(`[fetchUserData] Cavab alındı: status=${resp.status}`);

        if (!resp.ok) {
            if (resp.status === 404) {
                console.warn(`[fetchUserData] 404 - İstifadəçi ID=${currentUser.id} tapilmadı. Bot-da /start göndərin.`);
                // Mövcud userData-nı sıfırlamadan qoru, yoxdursa default yarat
                if (!userData) {
                    userData = createDefaultUserData();
                }
                return;
            }
            const errText = await resp.text();
            console.error(`[fetchUserData] API xətası: ${resp.status} | ${errText}`);
            // Xəta halinda da mövcud userData-nı qoru
            if (!userData) {
                userData = createDefaultUserData();
            }
            return;
        }

        const newData = await resp.json();
        console.log(`[fetchUserData] Yeni data alındı: balance_mc=${newData.balance_mc}, videos_today=${newData.videos_today}`);
        userData = newData;

    } catch (err) {
        console.error("[İstifadəçi məlumatları çəkilmədi]:", err);
        // Tormöz halinda mövcud userData-nı qoru
        if (!userData) {
            userData = createDefaultUserData();
        }
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
        mc_to_azn_rate: 21000,
    };
}

// ── Dashboard Render ─────────────────────────────────────────────────
function renderDashboard() {
    if (!userData) return;

    // Başlıq
    document.getElementById("user-name").textContent = userData.first_name || currentUser.first_name || "İstifadəçi";

    // Balans – birbaşa DOM yeniləmə
    const balanceMcEl = document.getElementById("balance-mc");
    const balanceAznEl = document.getElementById("balance-azn");
    balanceMcEl.textContent = formatNumber(userData.balance_mc);
    balanceAznEl.textContent = (userData.balance_mc / userData.mc_to_azn_rate).toFixed(4);

    // Statistika
    document.getElementById("total-earned").textContent = formatNumber(userData.total_earned_mc);
    document.getElementById("videos-count").textContent = `${userData.videos_today}/${userData.daily_limit}`;
    document.getElementById("referral-count").textContent = userData.referral_count;
    document.getElementById("referral-earnings").textContent = formatNumber(userData.referral_earnings_mc);

    // Tərəqqi
    const progress = (userData.videos_today / userData.daily_limit) * 100;
    document.getElementById("progress-fill").style.width = `${Math.min(progress, 100)}%`;
    document.getElementById("progress-text").textContent = `${userData.videos_today}/${userData.daily_limit} video`;

    // İzlə düyməsinin vəziyyəti
    const watchBtn = document.getElementById("watch-btn");
    if (userData.videos_today >= userData.daily_limit) {
        watchBtn.disabled = true;
        watchBtn.textContent = "📛 Gündəlik limit bitdi";
    } else {
        watchBtn.disabled = false;
        watchBtn.textContent = `🎬 Video İzlə & ${userData.mc_per_video} MC Qazan`;
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
        return true;
    }
    console.warn("Adsgram SDK yüklənmədi.");
    return false;
}

/**
 * Adsgram vasitəsilə mükafatlı video reklamı göstər.
 * Axın:
 *   1. adController.show()   → reklamı təqdim edir
 *   2. .then(result)         → reklam tamamlandı → mükafatı kreditlə
 *   3. .catch(result)        → reklam atlandı / xəta → müvafiq mesaj göstər
 */
async function watchAd() {
    const watchBtn = document.getElementById("watch-btn");

    // Client tərəfdə gündəlik limit yoxla
    if (userData && userData.videos_today >= userData.daily_limit) {
        showToast("📛 Gündəlik limit bitdi! Sabah yenidən gəlin.", "error");
        return;
    }

    // Lazım olduqda Adsgram-ı başlat
    if (!adController) {
        if (!initAdsgram()) {
            showToast("⚠️ Reklam xidməti mövcud deyil. Sonra cəhd edin.", "error");
            return;
        }
    }

    // Reklam zamanı düyməni söndür
    watchBtn.disabled = true;
    watchBtn.textContent = "⏳ Reklam yüklənir...";

    try {
        // Reklamı göstər və tamamlanmasını gözlə
        const result = await adController.show();

        // Reklam uğurla tamamlandı
        if (result.done) {
            watchBtn.textContent = "✅ Mükafat hesablanır...";

            // Mükafatı kreditlə və balansı yenilə
            await creditReward();

            // Coin partlayış animasiyası
            spawnCoinBurst();

            showToast(`🎉 +${userData.mc_per_video} MC qazandınız!`, "success");
        }

    } catch (result) {
        // Reklam atlandı, erkən bağlandı və ya xəta baş verdi
        if (result.error) {
            console.error("Adsgram xətası:", result.description);
            showToast("⚠️ Reklam yüklənmədi. Yenidən cəhd edin.", "error");
        } else {
            // İstifadəçi əl ilə bağladı / atladı
            showToast("⏭️ Mükafat almaq üçün videonu tam izləyin.", "error");
        }
    } finally {
        // Düyməni yenidən aktiv et
        if (userData && userData.videos_today < userData.daily_limit) {
            watchBtn.disabled = false;
            watchBtn.textContent = `🎬 Video İzlə & ${userData.mc_per_video} MC Qazan`;
        } else {
            watchBtn.disabled = true;
            watchBtn.textContent = "📛 Gündəlik limit bitdi";
        }
    }
}

// ── Mükafat Kreditləmə (balans yeniləmə ilə) ───────────────────────
async function creditReward() {
    // Optimistik lokal yeniləmə – dərhal UI-da göstərmək üçün
    if (userData) {
        userData.balance_mc += userData.mc_per_video;
        userData.total_earned_mc += userData.mc_per_video;
        userData.videos_today += 1;
        renderDashboard(); // Dərhal ekranda göstər
    }

    // Qeyd: Serverdən (fetchUserData) dərhal yeniləməni ləğv etdik,
    // çünki Adsgram S2S (Server-to-Server) callback-i 2-5 saniyə gecikə bilər.
    // Əgər dərhal serverdən məlumat çəksək, hələ bazaya yazılmadığı üçün köhnə balansı qaytarır 
    // və UI-da balans geri qayıdır. Optimistik yeniləmə sessiya üçün kifayətdir.
}

// ── Referal Linkini Kopyala (Telegram SDK uyğunluğu ilə) ────────────
async function copyReferralLink() {
    const linkEl = document.getElementById("referral-link");
    const link = linkEl.textContent;
    const btn = document.getElementById("copy-btn");

    let copied = false;

    // Üsul 1: Telegram WebApp SDK – ən etibarlı yol Telegram daxilində
    if (tg && typeof tg.openLink === "function") {
        try {
            // Telegram daxilində clipboard birbaşa çalışmaya bilər,
            // ona görə shareUrl ilə paylaşmağı təklif edirik
            if (typeof tg.shareUrl === "function") {
                tg.shareUrl(link);
                copied = true;
            }
        } catch (_) { /* növbəti üsula keç */ }
    }

    // Üsul 2: Modern Clipboard API
    if (!copied && navigator.clipboard && navigator.clipboard.writeText) {
        try {
            await navigator.clipboard.writeText(link);
            copied = true;
        } catch (_) { /* növbəti üsula keç */ }
    }

    // Üsul 3: Köhnə execCommand fallback
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

    // Nəticə göstər
    if (copied) {
        showToast("📋 Referal linki kopyalandı!", "success");
        btn.textContent = "✅ Kopyalandı!";
        setTimeout(() => {
            btn.textContent = "📋 Linki Kopyala";
        }, 2000);
    } else {
        showToast("⚠️ Kopyalana bilmədi. Linki əl ilə kopyalayın.", "error");
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

        // Animasiyadan sonra təmizlə
        setTimeout(() => coin.remove(), 1500);
    }
}

// ── Toast Bildirişlər ────────────────────────────────────────────────
let toastTimer = null;

function showToast(message, type = "success") {
    const toast = document.getElementById("toast");
    toast.textContent = message;
    toast.className = `toast ${type} visible`;

    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
        toast.classList.remove("visible");
    }, 3000);
}

// ── Yardımçı ─────────────────────────────────────────────────────────
function formatNumber(num) {
    if (num === undefined || num === null) return "0";
    return Math.floor(num).toLocaleString("az-AZ");
}
