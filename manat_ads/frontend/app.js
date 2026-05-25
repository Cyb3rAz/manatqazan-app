/**
 * ManatAds – Mini App Frontend Logic (AZ)
 * =========================================
 * Integrates with:
 *   • Telegram Web App SDK (istifadəçi kimliyi + tema)
 *   • Adsgram SDK (video reklamlar – .show(), .then(), .catch())
 *   • ManatAds Backend API (istifadəçi məlumatı + mükafat callback)
 */

// ── Konfiqurasiya ─────────────────────────────────────────────────────
// API_BASE boş saxlanılır — Vercel rewrites vasitəsilə /api/* sorğuları
// avtomatik olaraq backend serverinə yönləndirilir.
// VPS-ə köçdükdən sonra vercel.json-da yeni URL-i dəyişmək kifayətdir.
const API_BASE = "";
const ADSGRAM_BLOCK_ID = "31923";

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
            // Telegram xaricində inkişaf / test üçün
            console.warn("Telegram daxilində deyil – test istifadəçi istifadə olunur.");
            currentUser = { id: 123456789, first_name: "TestUser" };
        }

        // Backend-dən istifadəçi məlumatlarını çək (yüklənmə ekranı qalır)
        await fetchUserData();

        // UI-ı yenilə
        renderDashboard();

        // Əsas kontenti göstər, loaderi gizlə
        document.getElementById("loader").style.display = "none";
        document.getElementById("main-content").style.display = "block";

    } catch (err) {
        console.error("Başlanğıc xətası:", err);
        // Xəta olsa belə loaderi gizlə və default göstər
        document.getElementById("loader").style.display = "none";
        document.getElementById("main-content").style.display = "block";
        renderDashboard();
        showToast("⚠️ Məlumatlar yüklənə bilmədi. Yenidən cəhd edin.", "error");
    }
}

// ── İstifadəçi Məlumatlarını Çək (cache-busting ilə) ─────────────────
async function fetchUserData() {
    // Cache-busting: hər sorğuya unikal timestamp əlavə et
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
                console.warn(`[fetchUserData] 404 - İstifadəçi ID=${currentUser.id} tapılmadı. Bot-da /start göndərin.`);
                if (!userData) {
                    userData = createDefaultUserData();
                }
                return;
            }
            const errText = await resp.text();
            console.error(`[fetchUserData] API xətası: ${resp.status} | ${errText}`);
            if (!userData) {
                userData = createDefaultUserData();
            }
            return;
        }

        const newData = await resp.json();
        console.log(`[fetchUserData] Backend-dən gələn data: balance_mc=${newData.balance_mc}, videos_today=${newData.videos_today}, total_earned=${newData.total_earned_mc}`);

        // Yalnız server datası optimistik lokal balansdan KİÇİK olarsa,
        // lokal (optimistik) yenilənmiş versiyasını qoru.
        // Bu, Adsgram S2S callback gecikmə müddətində UI-nın geri sıçramasını qarşısını alır.
        if (userData && userData.balance_mc > newData.balance_mc) {
            console.log(`[fetchUserData] Lokal balans (${userData.balance_mc}) > Server balansi (${newData.balance_mc}). Lokal saxlanılır (S2S gecikmə).`);
            // Ancaq serverin qaytardığı referral məlumatlarını yenilə
            userData.referral_count = newData.referral_count;
            userData.referral_earnings_mc = newData.referral_earnings_mc;
            return;
        }

        userData = newData;

    } catch (err) {
        console.error("[fetchUserData] Şəbəkə xətası:", err);
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
    };
}

// ── Cooldown Timer State ──────────────────────────────────────────────
let cooldownInterval = null;

function startCooldownTimer(unlockAt) {
    if (!unlockAt) return;
    
    // Clear any existing timer
    stopCooldownTimer();
    
    const targetTime = new Date(unlockAt).getTime();
    const hintEl = document.getElementById("session-2-cooldown-hint");
    
    function updateTimer() {
        const now = new Date().getTime();
        const difference = targetTime - now;
        
        if (difference <= 0) {
            stopCooldownTimer();
            hintEl.style.display = "none";
            
            // Set local lock state to false and re-render instantly without refresh!
            if (userData) {
                userData.session_2_locked = false;
                userData.unlock_at = null;
                renderDashboard();
            }
            return;
        }
        
        // Format countdown: HH:MM:SS
        const hours = Math.floor(difference / (1000 * 60 * 60));
        const minutes = Math.floor((difference % (1000 * 60 * 60)) / (1000 * 60));
        const seconds = Math.floor((difference % (1000 * 60)) / 1000);
        
        const pad = (n) => n.toString().padStart(2, '0');
        hintEl.textContent = `Kilid açılmasına: ${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
        hintEl.style.display = "block";
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
function renderDashboard() {
    if (!userData) return;

    // Başlıq
    document.getElementById("user-name").textContent = userData.first_name || currentUser.first_name || "İstifadəçi";

    // Balans – birbaşa DOM yeniləmə
    const balanceMcEl = document.getElementById("balance-mc");
    balanceMcEl.textContent = formatNumber(userData.balance_mc);

    // Çıxarış Progress Bar yeniləmə -> Liqa Sistemi
    const currentMc = userData.balance_mc || 0;
    let leagueName = "";
    let progressPct = 0;

    if (currentMc <= 10000) {
        leagueName = "🟤 Bürünc Liqa";
        progressPct = (currentMc / 10000) * 100;
    } else if (currentMc <= 50000) {
        leagueName = "⚪ Gümüş Liqa";
        progressPct = ((currentMc - 10000) / 40000) * 100;
    } else if (currentMc <= 150000) {
        leagueName = "🟡 Qızıl Liqa";
        progressPct = ((currentMc - 50000) / 100000) * 100;
    } else if (currentMc <= 350000) {
        leagueName = "🔵 Platin Liqa";
        progressPct = ((currentMc - 150000) / 200000) * 100;
    } else if (currentMc < 625000) {
        leagueName = "💎 Almaz Liqa";
        progressPct = ((currentMc - 350000) / 275000) * 100;
    } else {
        leagueName = "💎 Almaz Liqa"; // Maximum hədəfə çatıb
        progressPct = 100;
    }

    const pctStr = progressPct.toFixed(1);
    
    const leagueNameEl = document.getElementById("league-name-text");
    if (leagueNameEl) {
        leagueNameEl.textContent = leagueName;
    }
    
    const withdrawalPctEl = document.getElementById("withdrawal-pct");
    if (withdrawalPctEl) {
        withdrawalPctEl.textContent = pctStr;
    }
    const withdrawalFillEl = document.getElementById("withdrawal-progress-fill");
    if (withdrawalFillEl) {
        withdrawalFillEl.style.width = `${progressPct}%`;
    }

    // Statistika
    document.getElementById("total-earned").textContent = formatNumber(userData.total_earned_mc);
    document.getElementById("videos-count").textContent = `${userData.videos_today}/${userData.daily_limit || 50}`;
    document.getElementById("referral-count").textContent = userData.referral_count;
    document.getElementById("referral-earnings").textContent = formatNumber(userData.referral_earnings_mc);

    // Səans 1 Card Render
    const s1Count = userData.session_1_count || 0;
    document.getElementById("session-1-progress-text").textContent = `${s1Count}/25 video`;
    document.getElementById("session-1-progress-fill").style.width = `${(s1Count / 25) * 100}%`;
    const s1Btn = document.getElementById("session-1-btn");

    if (s1Count >= 25) {
        s1Btn.disabled = true;
        s1Btn.textContent = "🌅 Tamamlandı";
    } else {
        s1Btn.disabled = false;
        s1Btn.textContent = `🎬 Video İzlə & ${userData.mc_per_video || 50} MC Qazan`;
    }

    // Səans 2 Card Render
    const s2Count = userData.session_2_count || 0;
    document.getElementById("session-2-progress-text").textContent = `${s2Count}/25 video`;
    document.getElementById("session-2-progress-fill").style.width = `${(s2Count / 25) * 100}%`;
    const s2Btn = document.getElementById("session-2-btn");
    const s2Hint = document.getElementById("session-2-cooldown-hint");

    if (userData.session_2_locked) {
        s2Btn.disabled = true;
        s2Btn.textContent = "🔒 Səans 2 Kilidlidir";
        s2Hint.style.display = "block";
        startCooldownTimer(userData.unlock_at);
    } else {
        s2Hint.style.display = "none";
        stopCooldownTimer();
        if (s2Count >= 25) {
            s2Btn.disabled = true;
            s2Btn.textContent = "🌌 Tamamlandı";
        } else {
            // Səans 2 is unlocked and can be watched ONLY if Səans 1 is already completed!
            if (s1Count < 25) {
                s2Btn.disabled = true;
                s2Btn.textContent = "⏳ Əvvəlcə Səans 1-i bitirin";
            } else {
                s2Btn.disabled = false;
                s2Btn.textContent = `🎬 Video İzlə & ${userData.mc_per_video || 50} MC Qazan`;
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
        
        // Adsgram standart xəta/xəbərdarlıq pəncərələrini əngəlləmək və öz doğma dilimizdə göstərmək üçün
        adController.addEventListener("onNonStopShow", () => {
            showToast("Upps! Reklamlara çox tez-tez baxmağa çalışırsınız. Zəhmət olmasa, bir neçə saniyə gözləyin 🙏", "error");
        });
        
        adController.addEventListener("onBannerNotFound", () => {
            showToast("Hazırda göstəriləcək reklam tapılmadı. Bir az sonra təkrar yoxlayın.", "error");
        });
        
        adController.addEventListener("onTooLongSession", () => {
            showToast("Sessiyanız çox uzun çəkdi. Zəhmət olmasa, səhifəni yeniləyin.", "error");
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

    // Client-side limits
    if (!userData) return;
    
    if (sessionNum === 1 && userData.session_1_count >= 25) {
        showToast("🌅 Səans 1 tamamlanıb!", "error");
        return;
    }
    if (sessionNum === 2) {
        if (userData.session_2_locked) {
            showToast("🔒 Səans 2 hələ kilidlidir!", "error");
            return;
        }
        if (userData.session_2_count >= 25) {
            showToast("🌌 Səans 2 tamamlanıb!", "error");
            return;
        }
    }

    // Lazım olduqda Adsgram-ı başlat
    if (!adController) {
        if (!initAdsgram()) {
            showToast("⚠️ Reklam xidməti mövcud deyil. Sonra cəhd edin.", "error");
            return;
        }
    }

    // Reklam zamanı düymələri söndür
    watchBtn.disabled = true;
    const oldText = watchBtn.textContent;
    watchBtn.textContent = "⏳ Reklam yüklənir...";
    if (otherBtn) otherBtn.disabled = true;

    try {
        const result = await adController.show();

        if (result.done) {
            watchBtn.textContent = "✅ Mükafat hesablanır...";

            // Mükafatı kreditlə və balansı yenilə
            await creditReward(sessionNum);

            // Coin partlayış animasiyası
            spawnCoinBurst();

            showToast(`🎉 +${userData.mc_per_video} MC qazandınız!`, "success");
        }

    } catch (result) {
        if (result.error) {
            console.error("Adsgram xətası:", result.description);
            showToast("⚠️ Reklam yüklənmədi. Yenidən cəhd edin.", "error");
        } else {
            showToast("⏭️ Mükafat almaq üçün videonu tam izləyin.", "error");
        }
    } finally {
        renderDashboard();
        startButtonCooldown(sessionNum);
    }
}

// ── Düymə Cooldown (reklam bitdikdən sonra 5 saniyəlik bloklanma) ────
function startButtonCooldown(sessionNum, seconds = 5) {
    const btn = document.getElementById(`session-${sessionNum}-btn`);
    const otherBtn = document.getElementById(`session-${sessionNum === 1 ? 2 : 1}-btn`);

    btn.disabled = true;
    if (otherBtn) otherBtn.disabled = true;

    let remaining = seconds;
    btn.textContent = `⏳ Gözləyin (${remaining}s)...`;

    const interval = setInterval(() => {
        remaining--;
        if (remaining > 0) {
            btn.textContent = `⏳ Gözləyin (${remaining}s)...`;
        } else {
            clearInterval(interval);
            renderDashboard(); // Düymənin əsl mətnini bərpa et
        }
    }, 1000);
}

// ── Mükafat Kreditləmə (optimistik + arxa fonda sinxronlaşdırma) ────
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

    // Arxa fonda server ilə sinxronlaşdır
    scheduleServerSync(4, 2500);
}

/**
 * Server ilə sinxronlaşdırma — gecikmə ilə bir neçə cəhd.
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

                // Əgər server balansi hələ köhnədirsə və cəhd qalıbsa, davam et
                if (newBalance < prevBalance && attempt < maxRetries) {
                    trySync();
                }
            } catch (err) {
                console.error(`[SYNC] Cəhd ${attempt} xətası:`, err);
                if (attempt < maxRetries) {
                    trySync();
                }
            }
        }, delayMs * attempt);
    }

    trySync();
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

// -- Toast Notifications --
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
