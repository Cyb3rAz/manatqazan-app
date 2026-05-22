/**
 * ManatAds – Mini App Frontend Logic
 * ====================================
 * Integrates with:
 *   • Telegram Web App SDK (user identity + theme)
 *   • Adsgram SDK (video ads – .show(), .then(), .catch())
 *   • ManatAds Backend API (user info + reward callback)
 */

// ── Configuration ─────────────────────────────────────────────────────
const API_BASE = window.location.origin;
const ADSGRAM_BLOCK_ID = "your_adsgram_block_id_here"; // Replace with .env value in production

// ── Telegram Web App ──────────────────────────────────────────────────
const tg = window.Telegram?.WebApp;
let currentUser = null;
let userData = null;

// ── Initialise ────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
    if (tg) {
        tg.ready();
        tg.expand();
        tg.enableClosingConfirmation();

        // Apply Telegram theme colors if available
        if (tg.themeParams) {
            document.documentElement.style.setProperty(
                "--tg-bg", tg.themeParams.bg_color || "#0a0e1a"
            );
        }
    }

    initApp();
});

// ── App Initialisation ───────────────────────────────────────────────
async function initApp() {
    try {
        // Get user from Telegram Web App
        if (tg?.initDataUnsafe?.user) {
            currentUser = tg.initDataUnsafe.user;
        } else {
            // Fallback for development / testing outside Telegram
            console.warn("Not running inside Telegram – using test user.");
            currentUser = { id: 123456789, first_name: "TestUser" };
        }

        // Fetch user data from backend
        await fetchUserData();

        // Show main content
        document.getElementById("loader").style.display = "none";
        document.getElementById("main-content").style.display = "block";

        // Update UI
        renderDashboard();

    } catch (err) {
        console.error("Init error:", err);
        showToast("Failed to load app. Please try again.", "error");
    }
}

// ── Fetch User Data ──────────────────────────────────────────────────
async function fetchUserData() {
    try {
        const resp = await fetch(`${API_BASE}/api/user/${currentUser.id}`);
        if (!resp.ok) {
            if (resp.status === 404) {
                console.warn("User not found – they may need to /start the bot first.");
                userData = createDefaultUserData();
                return;
            }
            throw new Error(`API error: ${resp.status}`);
        }
        userData = await resp.json();
    } catch (err) {
        console.error("Failed to fetch user data:", err);
        userData = createDefaultUserData();
    }
}

function createDefaultUserData() {
    return {
        telegram_id: currentUser.id,
        first_name: currentUser.first_name || "User",
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

// ── Render Dashboard ─────────────────────────────────────────────────
function renderDashboard() {
    if (!userData) return;

    // Header
    document.getElementById("user-name").textContent = userData.first_name || currentUser.first_name || "User";

    // Balance
    document.getElementById("balance-mc").textContent = formatNumber(userData.balance_mc);
    document.getElementById("balance-azn").textContent = (userData.balance_mc / userData.mc_to_azn_rate).toFixed(4);

    // Stats
    document.getElementById("total-earned").textContent = formatNumber(userData.total_earned_mc);
    document.getElementById("videos-count").textContent = `${userData.videos_today}/${userData.daily_limit}`;
    document.getElementById("referral-count").textContent = userData.referral_count;
    document.getElementById("referral-earnings").textContent = formatNumber(userData.referral_earnings_mc);

    // Progress
    const progress = (userData.videos_today / userData.daily_limit) * 100;
    document.getElementById("progress-fill").style.width = `${Math.min(progress, 100)}%`;
    document.getElementById("progress-text").textContent = `${userData.videos_today}/${userData.daily_limit} videos`;

    // Watch button state
    const watchBtn = document.getElementById("watch-btn");
    if (userData.videos_today >= userData.daily_limit) {
        watchBtn.disabled = true;
        watchBtn.textContent = "📛 Daily Limit Reached";
    } else {
        watchBtn.disabled = false;
        watchBtn.textContent = `🎬 Watch Video & Earn ${userData.mc_per_video} MC`;
    }

    // Referral section
    const botUsername = "ManatAdsBot"; // Replace with actual bot username
    const refLink = `https://t.me/${botUsername}?start=${currentUser.id}`;
    document.getElementById("referral-link").textContent = refLink;
    document.getElementById("ref-friends").textContent = userData.referral_count;
    document.getElementById("ref-earned").textContent = formatNumber(userData.referral_earnings_mc);
}

// ── Adsgram Integration ──────────────────────────────────────────────
let adController = null;

function initAdsgram() {
    if (window.Adsgram) {
        adController = window.Adsgram.init({ blockId: ADSGRAM_BLOCK_ID });
        return true;
    }
    console.warn("Adsgram SDK not loaded.");
    return false;
}

/**
 * Show a rewarded video ad via Adsgram.
 * Flow:
 *   1. adController.show()   → presents the ad
 *   2. .then(result)         → ad completed → call backend to credit reward
 *   3. .catch(result)        → ad skipped / errored → show appropriate message
 */
async function watchAd() {
    const watchBtn = document.getElementById("watch-btn");

    // Check daily limit client-side
    if (userData && userData.videos_today >= userData.daily_limit) {
        showToast("📛 Daily limit reached! Come back tomorrow.", "error");
        return;
    }

    // Initialise Adsgram if needed
    if (!adController) {
        if (!initAdsgram()) {
            showToast("⚠️ Ad service unavailable. Try again later.", "error");
            return;
        }
    }

    // Disable button during ad
    watchBtn.disabled = true;
    watchBtn.textContent = "⏳ Loading ad...";

    try {
        // Show the ad and wait for completion
        const result = await adController.show();

        // Ad completed successfully
        if (result.done) {
            watchBtn.textContent = "✅ Crediting reward...";

            // The backend will be called by Adsgram's S2S callback automatically.
            // We also call our own endpoint for immediate UI feedback.
            await creditReward();

            // Coin burst animation
            spawnCoinBurst();

            showToast(`🎉 +${userData.mc_per_video} MC earned!`, "success");
        }

    } catch (result) {
        // Ad was skipped, closed early, or errored
        if (result.error) {
            console.error("Adsgram error:", result.description);
            showToast("⚠️ Ad failed to load. Please try again.", "error");
        } else {
            // User manually closed / skipped
            showToast("⏭️ Watch the full video to earn your reward.", "error");
        }
    } finally {
        // Re-enable button
        if (userData && userData.videos_today < userData.daily_limit) {
            watchBtn.disabled = false;
            watchBtn.textContent = `🎬 Watch Video & Earn ${userData.mc_per_video} MC`;
        } else {
            watchBtn.disabled = true;
            watchBtn.textContent = "📛 Daily Limit Reached";
        }
    }
}

// ── Credit Reward (client-side update) ───────────────────────────────
async function creditReward() {
    // Optimistic local update for instant UI feedback
    if (userData) {
        userData.balance_mc += userData.mc_per_video;
        userData.total_earned_mc += userData.mc_per_video;
        userData.videos_today += 1;
        renderDashboard();
    }

    // Refresh from server to get authoritative data
    try {
        await fetchUserData();
        renderDashboard();
    } catch (err) {
        console.error("Failed to refresh user data:", err);
    }
}

// ── Copy Referral Link ───────────────────────────────────────────────
async function copyReferralLink() {
    const linkEl = document.getElementById("referral-link");
    const link = linkEl.textContent;

    try {
        await navigator.clipboard.writeText(link);
        showToast("📋 Referral link copied!", "success");

        const btn = document.getElementById("copy-btn");
        btn.textContent = "✅ Copied!";
        setTimeout(() => {
            btn.textContent = "📋 Copy Referral Link";
        }, 2000);
    } catch {
        // Fallback for environments without clipboard API
        const textArea = document.createElement("textarea");
        textArea.value = link;
        textArea.style.position = "fixed";
        textArea.style.left = "-9999px";
        document.body.appendChild(textArea);
        textArea.select();
        document.execCommand("copy");
        document.body.removeChild(textArea);

        showToast("📋 Referral link copied!", "success");
    }
}

// ── Coin Burst Animation ─────────────────────────────────────────────
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

        // Clean up after animation
        setTimeout(() => coin.remove(), 1500);
    }
}

// ── Toast Notifications ──────────────────────────────────────────────
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

// ── Utility ──────────────────────────────────────────────────────────
function formatNumber(num) {
    if (num === undefined || num === null) return "0";
    return Math.floor(num).toLocaleString("en-US");
}
