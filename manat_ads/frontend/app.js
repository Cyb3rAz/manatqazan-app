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
const FALLBACK_ADSGRAM_BLOCK_ID = 35141; // Production block fallback

// Adsgram SDK-sı yüklənənə qədər gözləyib init edir (max 40 dəfə, 500ms interval = 20 saniyə)
function initAdsgramWhenReady(blockId, retries = 40) {
    if (window.Adsgram) {
        AdController = window.Adsgram.init({ blockId: blockId.toString() });
        console.log('[Adsgram] SDK initialized with blockId:', blockId);
    } else if (retries > 0) {
        setTimeout(() => initAdsgramWhenReady(blockId, retries - 1), 500);
    } else {
        console.warn('[Adsgram] SDK yüklənmədi — reklam düyməsi deaktiv qalacaq.');
    }
}

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

            if (globalConfig.adsgram_block_id) {
                // SDK hazır olana qədər gözlə
                initAdsgramWhenReady(globalConfig.adsgram_block_id);
            } else {
                initAdsgramWhenReady(FALLBACK_ADSGRAM_BLOCK_ID);
            }
        } else {
            console.warn("Failed to fetch global config, using fallback Adsgram Block ID.");
            initAdsgramWhenReady(FALLBACK_ADSGRAM_BLOCK_ID);
        }
    } catch(e) {
        console.error("Failed to fetch global config:", e);
        initAdsgramWhenReady(FALLBACK_ADSGRAM_BLOCK_ID);
    }
}
fetchConfigAndInitAdsgram();

// ── 2-Level Ad Pool State ─────────────────────────────────────────────
// These are loaded from / persisted to localStorage so state survives refreshes.
let currentLevel    = 1;    // 1 or 2
let levelClicks     = 0;    // 0 to LEVEL_LIMIT
let cooldownEndTime = 0;    // Unix ms timestamp; 0 = no cooldown

// ── Passive Income Reminder ───────────────────────────────────────────
let consecutiveVideoCount = 0;       // How many videos watched in a row this session
let targetVideos = Math.floor(Math.random() * (10 - 7 + 1)) + 7; // Random target between 7 and 10


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

let LOCALES = {};

async function loadLocale(lang) {
    if (LOCALES[lang]) return;
    try {
        // In local testing, you might need a server to fetch JSON.
        // If fetch fails, it might be due to CORS on file://.
        const response = await fetch(`locales/${lang}.json`);
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        LOCALES[lang] = await response.json();
    } catch (e) {
        console.error(`Failed to load locale: ${lang}`, e);
        // Fallback to empty object to prevent errors
        LOCALES[lang] = {};
    }
}


function getWithdrawalTargetText(lang, hadPassive) {
    if (hadPassive) {
        if (lang === 'az') return "Çıxarış: 15 AZN - 100 AZN";
        if (lang === 'tr') return "Çekim: 412.5 TRY - 2750 TRY";
        if (lang === 'en') return "Withdrawal: 9 USDT - 60 USDT";
        if (lang === 'ru') return "Вывод: 9 USDT - 60 USDT";
    }
    return LOCALES[lang]?.withdrawalTarget || "Çıxarış: 10 AZN - 100 AZN";
}

function getWithdrawNoticeText(lang, hadPassive) {
    if (hadPassive) {
        if (lang === 'az') return "Birdəfəlik Çıxarış Limiti: 15 AZN - 100 AZN";
        if (lang === 'tr') return "Tek Seferlik Çekim Limiti: 412.5 TRY - 2750 TRY";
        if (lang === 'en') return "Single Withdrawal Limit: 9 USDT - 60 USDT";
        if (lang === 'ru') return "Лимит разового вывода: 9 USDT - 60 USDT";
    }
    return LOCALES[lang]?.Withdraw_Range_Notice || "Birdəfəlik Çıxarış Limiti: 10 AZN - 100 AZN";
}

function t(key) {
    return (LOCALES[currentLang] && LOCALES[currentLang][key]) || (LOCALES['az'] && LOCALES['az'][key]) || key;
}

// ── i18n Dil Dəyişmə ─────────────────────────────────────────────────
async function setLanguage(lang) {
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
    
    await loadLocale(currentLang);
    if (!LOCALES['en']) await loadLocale('en');
    if (!LOCALES['az']) await loadLocale('az');
    
    localStorage.setItem('saved_language', currentLang);
    localStorage.setItem('user_lang', currentLang);


    // Update all static elements with data-i18n attribute
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        const val = t(key);
        if (val) {
            if (val.includes('<')) {
                el.innerHTML = val;
            } else {
                el.textContent = val;
            }
        }
    });

    const proPriceEl = document.getElementById('pro-price-tag');
    if (proPriceEl) proPriceEl.innerText = t('Pro_Price');
    
    const elitePriceEl = document.getElementById('elite-price-tag');
    if (elitePriceEl) elitePriceEl.innerText = t('Elite_Price');

    const passivePriceEl = document.getElementById('passive-price-tag');
    if (passivePriceEl) passivePriceEl.innerText = t('passive_price');

    const hadPassive = userData && userData.had_passive_vip;
    const withdrawNoticeEl = document.getElementById('store-withdraw-notice');
    if (withdrawNoticeEl) withdrawNoticeEl.innerText = getWithdrawNoticeText(currentLang, hadPassive);

    // Minimalist Withdrawal Range on dashboard card
    const targetEl = document.getElementById('dashboard-target-text');
    if (targetEl) targetEl.innerText = getWithdrawalTargetText(currentLang, hadPassive);

    // Manually translate tasks-empty-msg if present in DOM
    const emptyMsgEl = document.getElementById('tasks-empty-msg');
    if (emptyMsgEl) {
        emptyMsgEl.textContent = t('tasks_empty_msg');
    }

    const passivePerksList = document.getElementById('passive-perks-list');
    if (passivePerksList && LOCALES[currentLang] && LOCALES[currentLang].passive_features) {
        passivePerksList.innerHTML = LOCALES[currentLang].passive_features.map(f => `
            <li class="vip-perk">
                <svg class="vip-perk-icon passive-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="20 6 9 17 4 12"></polyline>
                </svg>
                <span>${f}</span>
            </li>
        `).join('');
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
            checkLoyaltyBonus(); // Check for loyalty/welcome bonus after onboarding closes
        }, 400);
    }
}

function checkLoyaltyBonus() {
    if (userData && userData.can_claim_loyalty === true) {
        const modal = document.getElementById("loyalty-modal-overlay");
        const titleEl = document.getElementById("loyalty-modal-title");
        const textEl = document.getElementById("loyalty-modal-text");
        
        if (!modal) return;
        
        const loc = LOCALES[currentLang] || LOCALES['en'];
        
        if (userData.user_status === "new") {
            titleEl.textContent = loc.wbTitle || "🎉 Xoş gəldiniz!";
            textEl.textContent = loc.wbBody || "VibeCash-ə qoşulduğunuz üçün sizə 4.0 AZN (560,000 VC) Xoşgəldin Bonusu hədiyyə edildi!";
            const btnEl = document.getElementById("loyalty-claim-btn");
            if (btnEl) btnEl.textContent = loc.wbBtn || "Təsdiqlə";
        } else {
            titleEl.textContent = loc.loyaltyTitle || "🎉 VibeCash Yeniləndi!";
            textEl.textContent = loc.loyaltyBody || "Sadiqliyinizə görə sizə 4.0 AZN (560,000 VC) Sadiqlik Bonusu hədiyyə edildi!";
            const btnEl = document.getElementById("loyalty-claim-btn");
            if (btnEl) btnEl.textContent = loc.loyaltyBtn || "Təsdiqlə və Davam et";
        }
        
        modal.style.display = "flex";
        setTimeout(() => {
            modal.classList.add("active");
        }, 10);
    }
}

document.getElementById("loyalty-claim-btn")?.addEventListener("click", async function() {
    const btn = this;
    const originalText = btn.innerHTML;
    btn.innerHTML = '<div class="cyber-spinner" style="width: 20px; height: 20px; margin: 0 auto;"></div>';
    btn.disabled = true;
    
    try {
        const resp = await fetch(`${API_BASE}/api/user/${currentUser.id}/claim_loyalty`, {
            method: "POST"
        });
        const res = await resp.json();
        
        if (res.ok) {
            // Update userData locally
            userData.can_claim_loyalty = false;
            userData.loyalty_bonus_claimed = true;
            
            // Fade out modal
            const overlay = document.getElementById("loyalty-modal-overlay");
            overlay.classList.remove("active");
            setTimeout(() => {
                overlay.style.display = "none";
            }, 400);
            
            // ANIMATE!
            const startVc = userData.balance_vc || 0;
            const endVc = res.new_balance_vc;
            userData.balance_vc = endVc;
            userData.balance_mc = (userData.balance_mc || 0) + 4.0;
            
            animateLoyaltyClaim(startVc, endVc);
        } else {
            btn.innerHTML = originalText;
            btn.disabled = false;
            showToast("Xəta baş verdi, yenidən cəhd edin.", "error");
        }
    } catch(e) {
        btn.innerHTML = originalText;
        btn.disabled = false;
        showToast("Şəbəkə xətası.", "error");
    }
});

function animateLoyaltyClaim(startVc, endVc) {
    const duration = 2500; // 2.5 seconds
    const startTime = performance.now();
    
    // Play confetti at the end
    setTimeout(() => {
        if (window.confetti) {
            confetti({ particleCount: 120, spread: 80, origin: { y: 0.6 } });
        }
    }, duration);
    
    function updateFrame(currentTime) {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1);
        
        // Easing out cubic
        const easeOut = 1 - Math.pow(1 - progress, 3);
        
        const currentVc = Math.floor(startVc + (endVc - startVc) * easeOut);
        const balanceMcEl = document.getElementById("balance-mc");
        if (balanceMcEl) {
            balanceMcEl.textContent = formatNumber(currentVc);
        }
        
        // Also animate progress bar
        const currentMc = (userData.balance_mc - 4.0) + (4.0 * easeOut);
        const targetAznLimit = (userData && userData.had_passive_vip) ? 15 : 10;
        let progressPct = Math.min(100, Math.max(0, (currentMc / targetAznLimit) * 100));
        
        const withdrawalFillEl = document.getElementById("withdrawal-progress-fill");
        if (withdrawalFillEl) withdrawalFillEl.style.width = `${progressPct}%`;
        
        const withdrawalPctEl = document.getElementById("withdrawal-pct");
        if (withdrawalPctEl) withdrawalPctEl.textContent = progressPct.toFixed(1);
        
        // Flash leagues dynamically
        let newLeagueIndex = 0;
        if (progressPct < 20) newLeagueIndex = 0;
        else if (progressPct < 40) newLeagueIndex = 1;
        else if (progressPct < 60) newLeagueIndex = 2;
        else if (progressPct < 80) newLeagueIndex = 3;
        else newLeagueIndex = 4;
        
        if (newLeagueIndex > currentLeagueIndex) {
            currentLeagueIndex = newLeagueIndex;
            const LEAGUE_NAMES = [
                t('leagueBronze'), t('leagueSilver'), t('leagueGold'),
                t('leaguePlatinum'), t('leagueDiamond')
            ];
            
            const leagueNameEl = document.getElementById("league-name-label");
            if (leagueNameEl) leagueNameEl.textContent = LEAGUE_NAMES[newLeagueIndex];
            
            const ICONS = ['🥉', '🥈', '🥇', '💎', '👑'];
            const badgeEl = document.getElementById("league-badge");
            if (badgeEl) badgeEl.textContent = ICONS[newLeagueIndex];
        }
        
        if (progress < 1) {
            requestAnimationFrame(updateFrame);
        } else {
            // Make sure final render hits
            renderDashboard();
        }
    }
    
    requestAnimationFrame(updateFrame);
}

// ── Telegram Web App ──────────────────────────────────────────────────
const tg = window.Telegram?.WebApp;
let currentUser = null;
let userData = null;
let isMaintenanceActive = false;
let lastWatchTime = 0; // Timestamp of the last ad watch to prevent balance flickering


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

        // Load cached global stats instantly
        const cachedGlobalCount = localStorage.getItem('cached_global_user_count');
        if (cachedGlobalCount) {
            globalUserCount = parseInt(cachedGlobalCount, 10);
            updateGlobalUserCountUI(globalUserCount);
        }

        // Load cached userData if exists
        const onboardingCompleted = localStorage.getItem('onboarding_completed');
        const cachedUserStr = localStorage.getItem('cached_user_data');
        let hasCache = false;
        if (onboardingCompleted === 'true' && cachedUserStr) {
            try {
                userData = JSON.parse(cachedUserStr);
                if (userData && String(userData.telegram_id) === String(currentUser.id)) {
                    syncAdStateFromUserData();
                    renderDashboard();
                    setLanguage(currentLang);
                    hasCache = true;
                    
                    // Show the app content immediately so user doesn't wait
                    document.getElementById("main-content").style.display = "block";
                    const splash = document.getElementById("loader");
                    if (splash) {
                        splash.style.opacity = '0';
                        splash.style.visibility = 'hidden';
                        setTimeout(() => splash.remove(), 400);
                    }
                    console.log("[initApp] Loaded from cache, instant load triggered.");
                } else {
                    userData = null;
                }
            } catch (e) {
                console.error("[initApp] Error parsing cached user data:", e);
                userData = null;
            }
        }

        if (!hasCache) {
            // Backend-dən istifadəçi məlumatlarını çək (Synchronous block for uncached users)
            const freshData = await fetchUserData();
            if (!freshData) {
                showConnectionErrorScreen();
                return;
            }
            
            if (isMaintenanceActive) {
                console.log("Texniki işlər rejimi aktivdir. Yükləmə dayandırıldı.");
                return;
            }

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
        } else {
            // Background fetch for cached users to keep it snappy
            fetchUserData().then((freshData) => {
                if (freshData && isMaintenanceActive) {
                    return;
                }
                if (userData) {
                    renderDashboard();
                    localStorage.setItem('cached_user_data', JSON.stringify(userData));
                    
                    // Check loyalty bonus
                    checkLoyaltyBonus();
                    
                    // Sync Phase 2 language if updated from backend
                    if (userData.language && SUPPORTED_LANGS.includes(userData.language) && userData.language !== currentLang) {
                        setLanguage(userData.language);
                    }
                }
            }).catch(e => console.warn("[initApp] Background hydration failed:", e));
        }

        // ── Sınaq / Reset Mexanizmi ──────────────────────────────────────────
        if (urlParams.get('reset') === 'true') {
            console.log(`[LangDebug] ?reset=true parametri tapıldı. Onboarding sıfırlanır...`);
            localStorage.removeItem('onboarding_completed');
        }

        // Check if onboarding is completed
        const onboardingCompletedCheck = localStorage.getItem('onboarding_completed');
        console.log(`[LangDebug] onboardingCompleted check:`, onboardingCompletedCheck);
        
        if (onboardingCompletedCheck !== 'true') {
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
                setTimeout(() => obModal.classList.add("active"), 10);
            }
        } else {
            // Ensure the modal stays hidden
            const obModal = document.getElementById("onboarding-modal");
            if (obModal) {
                obModal.style.display = "none";
                obModal.classList.remove("active");
            }
            console.log(`[LangDebug] Onboarding already completed, skipping modal.`);
            if (!hasCache) {
                checkLoyaltyBonus(); // Only trigger here if not already handled by background fetch
            }
        }

        // For uncached users: show app content and remove loader
        if (!hasCache) {
            document.getElementById("main-content").style.display = "block";
            const splashSuccess = document.getElementById("loader");
            if (splashSuccess) {
                splashSuccess.style.opacity = '0';
                splashSuccess.style.visibility = 'hidden';
                setTimeout(() => splashSuccess.remove(), 400);
            }
        }

        // Start global user counter polling
        startGlobalStatsPolling();

    } catch (err) {
        console.error("Başlanğıc xətası:", err);
        showConnectionErrorScreen();
    }
}

// ── İstifadəçi Məlumatlarını Çək (cache-busting ilə) ─────────────────
async function fetchUserData() {
    const currentFetchId = ++lastFetchId;
    const cacheBuster = Date.now();
    const url = `${API_BASE}/api/user/${currentUser.id}?_t=${cacheBuster}`;
    console.log(`[fetchUserData] Sorgu #${currentFetchId} göndərilir: ${url}`);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 8000);

    try {
        const resp = await fetch(url, {
            method: "GET",
            signal: controller.signal,
            headers: {
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "ngrok-skip-browser-warning": "true"
            }
        });
        clearTimeout(timeoutId);

        console.log(`[fetchUserData] Cavab #${currentFetchId} alındı: status=${resp.status}`);

        if (!resp.ok) {
            if (resp.status === 503) {
                try {
                    const errData = await resp.clone().json();
                    if (errData && errData.maintenance) {
                        isMaintenanceActive = true;
                        showMaintenanceScreen();
                        return null;
                    }
                } catch(e) {
                    console.error("Failed to parse maintenance JSON error:", e);
                }
            }
            if (resp.status === 404) {
                console.warn(`[fetchUserData] 404 - İstifadəçi ID=${currentUser.id} tapılmadı.`);
                showErrorScreen("Qeydiyyat Tapılmadı", "Hesabınız tapılmadı. Zəhmət olmasa Telegram bota qayıdaraq /start əmrini göndərin.", "👤");
                return null;
            }
            if (resp.status === 403) {
                console.warn(`[fetchUserData] 403 - İstifadəçi bloklanıb.`);
                showErrorScreen("Hesab Dondurulub", "Təhlükəsizlik səbəbindən hesabınız dondurulub. Lütfən dəstək xidməti ilə əlaqə saxlayın.", "🚫");
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

        // Recent Watch Guard: If user recently watched an ad, keep their higher optimistic balance
        if (userData && newData) {
            const timeSinceLastWatch = Date.now() - lastWatchTime;
            const isRecentWatch = timeSinceLastWatch < 45000; // 45 seconds
            
            if (isRecentWatch && typeof newData.balance_vc === 'number' && typeof userData.balance_vc === 'number' && newData.balance_vc < userData.balance_vc) {
                console.log(`[fetchUserData] Server balance (${newData.balance_vc}) is lower than optimistic local balance (${userData.balance_vc}) within recent watch window (${timeSinceLastWatch}ms). Preserving local balance.`);
                
                // Preserve optimistic fields in the new data
                newData.balance_vc = userData.balance_vc;
                newData.balance_mc = userData.balance_mc;
                newData.total_earned_vc = userData.total_earned_vc;
                newData.total_earned_mc = userData.total_earned_mc;
                newData.session_1_count = Math.max(newData.session_1_count || 0, userData.session_1_count || 0);
                newData.session_2_count = Math.max(newData.session_2_count || 0, userData.session_2_count || 0);
                newData.videos_today = Math.max(newData.videos_today || 0, userData.videos_today || 0);
            }
        }

        if (newData && typeof newData.session_1_count === 'number' && typeof newData.session_2_count === 'number') {
            userData = newData;
            syncAdStateFromUserData();
        } else {
            userData = newData;
        }

        // Save to cache
        if (userData) {
            localStorage.setItem('cached_user_data', JSON.stringify(userData));
        }
        return newData;

    } catch (err) {
        clearTimeout(timeoutId);
        if (err.name === 'AbortError') {
            console.warn('[fetchUserData] Timeout 8s - mövcud userData qorunur.');
        } else {
            console.error("[fetchUserData] Şəbəkə xətası:", err);
        }
        if (currentFetchId === lastFetchId && !userData) {
            userData = createDefaultUserData();
        }
        return null;
    }
}

function showErrorScreen(title, message, icon="⚠️") {
    const splash = document.getElementById("loader");
    if (splash) {
        splash.style.opacity = '0';
        splash.style.visibility = 'hidden';
        setTimeout(() => splash.remove(), 400);
    }
    
    const mainContent = document.getElementById("main-content");
    if (mainContent) {
        mainContent.style.display = "none";
    }
    
    if (document.getElementById("error-screen")) return;
    
    const errorOverlay = document.createElement("div");
    errorOverlay.id = "error-screen";
    errorOverlay.style.position = "fixed";
    errorOverlay.style.top = "0";
    errorOverlay.style.left = "0";
    errorOverlay.style.width = "100%";
    errorOverlay.style.height = "100%";
    errorOverlay.style.backgroundColor = "#0f172a";
    errorOverlay.style.color = "#f8fafc";
    errorOverlay.style.fontFamily = "'Segoe UI', Tahoma, Geneva, Verdana, sans-serif";
    errorOverlay.style.display = "flex";
    errorOverlay.style.flexDirection = "column";
    errorOverlay.style.alignItems = "center";
    errorOverlay.style.justifyContent = "center";
    errorOverlay.style.textAlign = "center";
    errorOverlay.style.padding = "20px";
    errorOverlay.style.boxSizing = "border-box";
    errorOverlay.style.zIndex = "99999";
    
    errorOverlay.innerHTML = `
        <div style="
            max-width: 400px;
            padding: 30px;
            background: rgba(30, 41, 59, 0.7);
            border-radius: 16px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5);
            border: 1px solid rgba(255,255,255,0.1);
            backdrop-filter: blur(10px);
        ">
            <div style="font-size: 60px; margin-bottom: 20px;">${icon}</div>
            <h1 style="color: #ef4444; margin-top: 0; font-size: 24px;">${title}</h1>
            <p style="color: #cbd5e1; font-size: 16px; line-height: 1.6; margin-bottom: 25px;">
                ${message}
            </p>
            <button onclick="Telegram.WebApp.close()" style="
                background: linear-gradient(135deg, #ef4444, #b91c1c);
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 8px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
                width: 100%;
                box-shadow: 0 4px 15px rgba(239, 68, 68, 0.3);
                transition: transform 0.2s;
            ">Bağla</button>
        </div>
    `;
    document.body.appendChild(errorOverlay);
}

function showConnectionErrorScreen() {
    const splash = document.getElementById("loader");
    if (splash) {
        splash.style.opacity = '0';
        splash.style.visibility = 'hidden';
        setTimeout(() => splash.remove(), 400);
    }
    
    const mainContent = document.getElementById("main-content");
    if (mainContent) {
        mainContent.style.display = "none";
    }
    
    if (document.getElementById("connection-error-screen")) return;
    
    const errorOverlay = document.createElement("div");
    errorOverlay.id = "connection-error-screen";
    errorOverlay.style.position = "fixed";
    errorOverlay.style.top = "0";
    errorOverlay.style.left = "0";
    errorOverlay.style.width = "100%";
    errorOverlay.style.height = "100%";
    errorOverlay.style.backgroundColor = "#0f172a";
    errorOverlay.style.color = "#f8fafc";
    errorOverlay.style.fontFamily = "'Segoe UI', Tahoma, Geneva, Verdana, sans-serif";
    errorOverlay.style.display = "flex";
    errorOverlay.style.flexDirection = "column";
    errorOverlay.style.alignItems = "center";
    errorOverlay.style.justifyContent = "center";
    errorOverlay.style.textAlign = "center";
    errorOverlay.style.padding = "20px";
    errorOverlay.style.boxSizing = "border-box";
    errorOverlay.style.zIndex = "99999";
    
    errorOverlay.innerHTML = `
        <div style="
            max-width: 400px;
            padding: 30px;
            background: rgba(30, 41, 59, 0.7);
            border-radius: 16px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5);
            border: 1px solid rgba(255,255,255,0.1);
            backdrop-filter: blur(10px);
        ">
            <div style="font-size: 60px; margin-bottom: 20px;">🔌</div>
            <h1 style="color: #38bdf8; margin-top: 0; font-size: 24px;">Bağlantı Xətası</h1>
            <p style="color: #cbd5e1; font-size: 16px; line-height: 1.6; margin-bottom: 25px;">
                Serverlə əlaqə qurulmadı. İnternet bağlantınızı yoxlayın və yenidən cəhd edin.
            </p>
            <button onclick="location.reload()" style="
                background: linear-gradient(135deg, #38bdf8, #0284c7);
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 8px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
                width: 100%;
                box-shadow: 0 4px 15px rgba(56, 189, 248, 0.3);
                transition: transform 0.2s;
            ">Yenidən Cəhd Et</button>
        </div>
    `;
    document.body.appendChild(errorOverlay);
}

function showMaintenanceScreen() {
    // Hide the loader screen
    const splash = document.getElementById("loader");
    if (splash) {
        splash.style.opacity = '0';
        splash.style.visibility = 'hidden';
        setTimeout(() => splash.remove(), 400);
    }
    
    // Hide main content
    const mainContent = document.getElementById("main-content");
    if (mainContent) {
        mainContent.style.display = "none";
    }
    
    // Check if maintenance screen already exists
    if (document.getElementById("maintenance-screen")) return;
    
    // Create maintenance overlay
    const maintenanceOverlay = document.createElement("div");
    maintenanceOverlay.id = "maintenance-screen";
    maintenanceOverlay.style.position = "fixed";
    maintenanceOverlay.style.top = "0";
    maintenanceOverlay.style.left = "0";
    maintenanceOverlay.style.width = "100%";
    maintenanceOverlay.style.height = "100%";
    maintenanceOverlay.style.backgroundColor = "#0f172a";
    maintenanceOverlay.style.color = "#f8fafc";
    maintenanceOverlay.style.fontFamily = "'Segoe UI', Tahoma, Geneva, Verdana, sans-serif";
    maintenanceOverlay.style.display = "flex";
    maintenanceOverlay.style.flexDirection = "column";
    maintenanceOverlay.style.alignItems = "center";
    maintenanceOverlay.style.justifyContent = "center";
    maintenanceOverlay.style.textAlign = "center";
    maintenanceOverlay.style.padding = "20px";
    maintenanceOverlay.style.boxSizing = "border-box";
    maintenanceOverlay.style.zIndex = "99999";
    
    const titleText = t('maint_title') || "Texniki İşlər Gedir";
    const descText = t('maint_desc') || "Sistemdə optimallaşdırma və təmir işləri aparılır. Tezliklə yenidən xidmətinizdə olacağıq. Anlayışınız üçün təşəkkür edirik!";
    
    maintenanceOverlay.innerHTML = `
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
                font-size: 50px;
                margin-bottom: 20px;
                animation: spin 3s linear infinite;
                display: inline-block;
            ">⚙️</div>
            <h1 style="color: #38bdf8; margin-top: 0; font-size: 24px;">${titleText}</h1>
            <p style="color: #94a3b8; line-height: 1.6; font-size: 16px;">${descText}</p>
        </div>
        <style>
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
        </style>
    `;
    
    document.body.appendChild(maintenanceOverlay);
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

    // Çıxarış Progress Bar -> Natively calculated against 10 AZN or 15 AZN (passive) target
    const currentMc = userData.balance_mc || 0;
    const targetAznLimit = userData.had_passive_vip ? 15 : 10;
    
    // Natively compute progress percentage against the target limit
    let progressPct = Math.min(100, Math.max(0, (currentMc / targetAznLimit) * 100));
    
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


    const pctStrFormatted = progressPct.toFixed(1);
    const withdrawalPctEl = document.getElementById("withdrawal-pct");
    if (withdrawalPctEl) withdrawalPctEl.textContent = pctStrFormatted;

    const withdrawalFillEl = document.getElementById("withdrawal-progress-fill");
    if (withdrawalFillEl) withdrawalFillEl.style.width = `${progressPct}%`;

    // Withdrawal target label
    const dashboardTargetEl = document.getElementById("dashboard-target-text");
    if (dashboardTargetEl) {
        dashboardTargetEl.innerText = getWithdrawalTargetText(currentLang, userData.had_passive_vip);
    }

    // Statistika
    document.getElementById("total-earned").textContent = formatNumber(userData.total_earned_vc !== undefined ? userData.total_earned_vc : 0);
    const dynDailyLimit = userData.daily_limit || (LEVEL_LIMIT * MAX_LEVELS);
    document.getElementById("videos-count").textContent = `${(userData.session_1_count || 0) + (userData.session_2_count || 0)}/${dynDailyLimit}`;
    document.getElementById("referral-count").textContent = userData.referral_count;
    document.getElementById("referral-earnings").textContent = formatNumber(userData.referral_earnings_vc || 0);

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
    document.getElementById("ref-earned").textContent = formatNumber(userData.referral_earnings_vc || 0);
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

    // Guard: Adsgram SDK not yet ready (try to initialize late on click)
    if (!AdController) {
        const blockId = (globalConfig && globalConfig.adsgram_block_id) || FALLBACK_ADSGRAM_BLOCK_ID;
        if (window.Adsgram) {
            console.log('[Adsgram] Late initialization of Adsgram SDK on button click.');
            AdController = window.Adsgram.init({ blockId: blockId.toString() });
        }
    }

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
        // Passive reminder: increment counter and trigger popup at threshold
        consecutiveVideoCount++;
        if (consecutiveVideoCount >= targetVideos) {
            consecutiveVideoCount = 0;
            targetVideos = Math.floor(Math.random() * (10 - 7 + 1)) + 7; // New random target
            setTimeout(() => showPassiveReminder(), 1200);
        }
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

    lastWatchTime = Date.now();
    const reward = userData.mc_per_video || 200;
    const rate = userData.mc_to_azn_rate || 140000;
    const aznReward = reward / rate;

    // Yadda saxlayaq ki, əgər xəta olarsa geri qaytara bilək
    const prevBalanceMc = userData.balance_mc;
    const prevBalanceVc = userData.balance_vc;
    const prevTotalMc = userData.total_earned_mc;
    const prevTotalVc = userData.total_earned_vc;
    const prevVideosToday = userData.videos_today;
    const prevS1 = userData.session_1_count;
    const prevS2 = userData.session_2_count;
    const prevCooldown = cooldownEndTime;

    // ── 1. Optimistic UI update ────────────────────────────────────────
    userData.balance_mc      += aznReward;
    userData.balance_vc      = (userData.balance_vc || 0) + reward;
    userData.total_earned_mc += aznReward;
    userData.total_earned_vc = (userData.total_earned_vc || 0) + reward;
    userData.videos_today    = (userData.videos_today || 0) + 1;

    if (sessionNum === 1) {
        userData.session_1_count = (userData.session_1_count || 0) + 1;
        levelClicks = userData.session_1_count;

        // Level 1 just completed → start 3-hour cooldown
        if (userData.session_1_count >= LEVEL_LIMIT && currentLevel === 1) {
            cooldownEndTime = Date.now() + COOLDOWN_MS;
        }
    } else if (sessionNum === 2) {
        userData.session_2_count = (userData.session_2_count || 0) + 1;
        levelClicks = userData.session_2_count;
    }
    saveAdState();

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

    // ── 3. Serverlə Sinxronizasiya ───────────────────────────
    try {
        const resp = await fetch(`${API_BASE}/api/reward/frontend`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Init-Data': window.Telegram.WebApp.initData || ""
            },
            body: JSON.stringify({
                event_id: `adsgram_${Date.now()}_${Math.random()}`
            })
        });

        const data = await resp.json();

        if (resp.ok && data.ok) {
            // Uğurlu olduqda serverin göndərdiyi yeni məlumatları qəbul et
            if (typeof data.new_balance === 'number') {
                userData.balance_mc = data.new_balance;
                userData.balance_vc = data.new_balance * rate;
            }
            if (typeof data.videos_today === 'number') {
                userData.videos_today = data.videos_today;
            }
            localStorage.setItem('cached_user_data', JSON.stringify(userData));
            renderDashboard();

            // Referal və s. yeniləmək üçün asinxron arxa planda istifadəçi məlumatını çək
            setTimeout(() => {
                fetchUserData().then(() => renderDashboard());
            }, 1000);
            
        } else {
            // Əgər server tərəfindən rədd edilsə, geri qaytar
            console.warn("[Reward] Backend rejected reward:", data);
            _revertOptimisticReward(prevBalanceMc, prevBalanceVc, prevTotalMc, prevTotalVc, prevVideosToday, prevS1, prevS2, prevCooldown);
            
            const errMsg = data.message || data.error || data.detail || "Server xətası: qazanc əlavə edilmədi.";
            showToast(errMsg, "error");
        }

    } catch (err) {
        console.error("[Reward] Backend trigger error:", err);
        _revertOptimisticReward(prevBalanceMc, prevBalanceVc, prevTotalMc, prevTotalVc, prevVideosToday, prevS1, prevS2, prevCooldown);
        showToast("İnternet bağlantısı xətası. Qazanc əlavə edilmədi.", "error");
    }
}

function _revertOptimisticReward(pBalMc, pBalVc, pTotMc, pTotVc, pVid, pS1, pS2, pCool) {
    userData.balance_mc = pBalMc;
    userData.balance_vc = pBalVc;
    userData.total_earned_mc = pTotMc;
    userData.total_earned_vc = pTotVc;
    userData.videos_today = pVid;
    userData.session_1_count = pS1;
    userData.session_2_count = pS2;
    cooldownEndTime = pCool;
    levelClicks = currentLevel === 1 ? pS1 : pS2;
    
    saveAdState();
    localStorage.setItem('cached_user_data', JSON.stringify(userData));
    renderDashboard();
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

// ── Passive Income Reminder Popup ─────────────────────────────────────
function showPassiveReminder() {
    const overlay = document.getElementById('passive-reminder-overlay');
    if (!overlay) return;
    overlay.style.display = 'flex';
    const card = document.getElementById('passive-reminder-card');
    if (card) {
        card.style.opacity = '0';
        card.style.transform = 'scale(0.85) translateY(24px)';
        requestAnimationFrame(() => {
            card.style.transition = 'opacity 0.35s ease, transform 0.35s cubic-bezier(0.34,1.56,0.64,1)';
            card.style.opacity = '1';
            card.style.transform = 'scale(1) translateY(0)';
        });
    }
}

function closePassiveReminder() {
    const overlay = document.getElementById('passive-reminder-overlay');
    const card = document.getElementById('passive-reminder-card');
    if (card) {
        card.style.transition = 'opacity 0.22s ease, transform 0.22s ease';
        card.style.opacity = '0';
        card.style.transform = 'scale(0.9) translateY(10px)';
        setTimeout(() => { if (overlay) overlay.style.display = 'none'; }, 230);
    } else if (overlay) {
        overlay.style.display = 'none';
    }
}

function goToPassiveStore() {
    closePassiveReminder();
    setTimeout(() => switchTab('store'), 300);
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
        
        // Auto-trigger removed: moved to manual button trigger below
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

function triggerAdsgramTasks() {
    if (window.Adsgram) {
        try {
            const taskBlock = window.Adsgram.initTask({ blockId: "35451" });
            taskBlock.show().then((result) => {
                let calcAmount = 250;
                if (userData && userData.vip_status) {
                    if (userData.vip_status === "pro") calcAmount = 310;
                    else if (userData.vip_status === "elite") calcAmount = 400;
                }
                showToast(t('rewardSuccess').replace('{amount}', calcAmount), "success");
            }).catch((result) => {
                console.log("AdsGram task failed or closed", result);
                if (result && result.error) {
                    showToast("Task error: " + result.error, "error");
                }
            });
        } catch (e) {
            console.error("AdsGram init error:", e);
            showToast("Adsgram tapşırıqları aktiv deyil.", "error");
        }
    } else {
        showToast("Reklam SDK-sı yüklənməyib.", "error");
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
            
            // VIP Badges
            let vipBadge = "";
            if (user.vip_status === "elite") {
                vipBadge = `<span class="vip-badge elite">ELITE</span>`;
            } else if (user.vip_status === "pro") {
                vipBadge = `<span class="vip-badge pro">PRO</span>`;
            }

            row.innerHTML = `
                <span class="rank">${rankDisplay}</span>
                <span class="username">${user.first_name}${vipBadge}</span>
                <span class="balance">${Math.floor(user.balance_mc).toLocaleString()} VC</span>
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
    let tierName = "";
    let priceStr = "";
    if (selectedVipPackage === 'pro') {
        tierName = t('vip_pro_title');
        priceStr = t('Pro_Price');
    } else if (selectedVipPackage === 'elite') {
        tierName = t('vip_elite_title');
        priceStr = t('Elite_Price');
    } else if (selectedVipPackage === 'passive') {
        tierName = t('vip_passive_title');
        priceStr = t('passive_price');
    }
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
    const ctrl = new AbortController();
    const tid = setTimeout(() => ctrl.abort(), 5000);
    try {
        const resp = await fetch(`${API_BASE}/api/global-stats`, {
            method: "GET",
            signal: ctrl.signal,
            headers: {
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "ngrok-skip-browser-warning": "true"
            }
        });
        clearTimeout(tid);
        if (resp.ok) {
            const data = await resp.json();
            if (data && typeof data.total_users === 'number') {
                // Guarantee counter never jumps backwards
                globalUserCount = Math.max(globalUserCount, data.total_users);
                localStorage.setItem('cached_global_user_count', globalUserCount);
                updateGlobalUserCountUI(globalUserCount);
            }
        }
    } catch (err) {
        clearTimeout(tid);
        if (err.name === 'AbortError') {
            console.warn('[fetchGlobalStats] Timeout 5s - k\u00f6hn\u0259 say qorunur.');
        } else {
            console.error("Error fetching global stats:", err);
        }
        // Do NOT reset counter on error - keep previous value
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

