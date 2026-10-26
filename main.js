// Quran Reels Generator - Premium UI Logic
const API_BASE = window.location.origin; // Same origin for Flask

// --- Configuration & Data ---
const SURAH_NAMES = [
    'الفاتحة', 'البقرة', 'آل عمران', 'النساء', 'المائدة', 'الأنعام', 'الأعراف', 'الأنفال', 'التوبة', 'يونس',
    'هود', 'يوسف', 'الرعد', 'إبراهيم', 'الحجر', 'النحل', 'الإسراء', 'الكهف', 'مريم', 'طه',
    'الأنبياء', 'الحج', 'المؤمنون', 'النور', 'الفرقان', 'الشعراء', 'النمل', 'القصص', 'العنكبوت', 'الروم',
    'لقمان', 'السجدة', 'الأحزاب', 'سبأ', 'فاطر', 'يس', 'الصافات', 'ص', 'الزمر', 'غافر',
    'فصلت', 'الشورى', 'الزخرف', 'الدخان', 'الجاثية', 'الأحقاف', 'محمد', 'الفتح', 'الحجرات', 'ق',
    'الذاريات', 'الطور', 'النجم', 'القمر', 'الرحمن', 'الواقعة', 'الحديد', 'المجادلة', 'الحشر', 'الممتحنة',
    'الصف', 'الجمعة', 'المنافقون', 'التغابن', 'الطلاق', 'التحريم', 'الملك', 'القلم', 'الحاقة', 'المعارج',
    'نوح', 'الجن', 'المزمل', 'المدثر', 'القيامة', 'الإنسان', 'المرسلات', 'النبأ', 'النازعات', 'عبس',
    'التكوير', 'الانفطار', 'المطففين', 'الانشقاق', 'البروج', 'الطارق', 'الأعلى', 'الغاشية', 'الفجر', 'البلد',
    'الشمس', 'الليل', 'الضحى', 'الشرح', 'التين', 'العلق', 'القدر', 'البينة', 'الزلزلة', 'العاديات',
    'القارعة', 'التكاثر', 'العصر', 'الهمزة', 'الفيل', 'قريش', 'الماعون', 'الكوثر', 'الكافرون', 'النصر',
    'المسد', 'الإخلاص', 'الفلق', 'الناس'
];

const VERSE_COUNTS = {
    1: 7, 2: 286, 3: 200, 4: 176, 5: 120, 6: 165, 7: 206, 8: 75, 9: 129, 10: 109,
    11: 123, 12: 111, 13: 43, 14: 52, 15: 99, 16: 128, 17: 111, 18: 110, 19: 98, 20: 135,
    21: 112, 22: 78, 23: 118, 24: 64, 25: 77, 26: 227, 27: 93, 28: 88, 29: 69, 30: 60,
    31: 34, 32: 30, 33: 73, 34: 54, 35: 45, 36: 83, 37: 182, 38: 88, 39: 75, 40: 85,
    41: 54, 42: 53, 43: 89, 44: 59, 45: 37, 46: 35, 47: 38, 48: 29, 49: 18, 50: 45,
    51: 60, 52: 49, 53: 62, 54: 55, 55: 78, 56: 96, 57: 29, 58: 22, 59: 24, 60: 13,
    61: 14, 62: 11, 63: 11, 64: 18, 65: 12, 66: 12, 67: 30, 68: 52, 69: 52, 70: 44,
    71: 28, 72: 28, 73: 20, 74: 56, 75: 40, 76: 31, 77: 50, 78: 40, 79: 46, 80: 42,
    81: 29, 82: 19, 83: 36, 84: 25, 85: 22, 86: 17, 87: 19, 88: 26, 89: 30, 90: 20,
    91: 15, 92: 21, 93: 11, 94: 8, 95: 8, 96: 19, 97: 5, 98: 8, 99: 8, 100: 11,
    101: 11, 102: 8, 103: 3, 104: 9, 105: 5, 106: 4, 107: 7, 108: 3, 109: 6, 110: 3,
    111: 5, 112: 4, 113: 5, 114: 6
};

// --- DOM Elements ---
const surahSelect = document.getElementById('surahSelect');
const surahSearch = document.getElementById('surahSearch');
const startAyahInput = document.getElementById('startAyah');
const endAyahInput = document.getElementById('endAyah');
const reciterSelect = document.getElementById('reciterSelect');
const qualitySelect = document.getElementById('qualitySelect');
const formatSelect = document.getElementById('formatSelect');
const templateGrid = document.getElementById('templateGrid');
const previewSkeleton = document.getElementById('previewSkeleton');
const playerFrame = document.getElementById('playerFrame');
const personNameInput = document.getElementById('personName');
const backgroundIntervalInput = document.getElementById('backgroundInterval');
const backgroundIntervalUnit = document.getElementById('backgroundIntervalUnit');

function syncBackgroundIntervalLimit() {
    const byAyah = backgroundIntervalUnit.value === 'ayahs';
    backgroundIntervalInput.max = byAyah ? '12' : '120';
    if (Number(backgroundIntervalInput.value) > Number(backgroundIntervalInput.max)) {
        backgroundIntervalInput.value = backgroundIntervalInput.max;
    }
}

backgroundIntervalUnit.addEventListener('change', syncBackgroundIntervalLimit);
syncBackgroundIntervalLimit();

function syncPreviewAspect() {
    const ratios = { reels: '9 / 16', story: '9 / 16', post: '1 / 1', youtube: '16 / 9' };
    const ratio = ratios[formatSelect.value] || ratios.reels;
    const maxWidth = formatSelect.value === 'youtube' ? '560px' : '350px';
    [previewSkeleton, playerFrame].forEach((frame) => {
        frame.style.aspectRatio = ratio;
        frame.style.maxWidth = maxWidth;
    });
}

formatSelect.addEventListener('change', syncPreviewAspect);
syncPreviewAspect();



const generateBtn = document.getElementById('generateBtn');
const previewBtn = document.getElementById('previewBtn');
const generatorForm = document.getElementById('generatorForm');

const statusCard = document.getElementById('statusCard');
const progressFill = document.getElementById('progressFill');
const progressPercent = document.getElementById('progressPercent');
const progressTrack = document.getElementById('progressTrack');
const statusText = document.getElementById('statusText');
const logTerminal = document.getElementById('logTerminal');
const formError = document.getElementById('formError');
const renderEta = document.getElementById('renderEta');
const retryBtn = document.getElementById('retryBtn');
const cancelBtn = document.getElementById('cancelBtn');

const videoPreviewWrapper = document.getElementById('videoPreviewWrapper');
const previewVideo = document.getElementById('previewVideo');

// Button labels carry drawn SVG icons now, so restore the captured markup
// instead of a text-only string when a job ends.
let generateBtnDefaultLabel = '';

// --- Initialization ---
document.addEventListener('DOMContentLoaded', () => {
    initSurahs();
    initCounters();

    // Check for existing progress
    pollProgress();

    // Load available fonts & reciters
    loadConfig();
});


function initSurahs() {
    SURAH_NAMES.forEach((name, index) => {
        const option = document.createElement('option');
        option.value = index + 1;
        option.textContent = `${index + 1}. ${name}`;
        surahSelect.appendChild(option);
    });

    // Add search functionality
    surahSearch.addEventListener('input', (e) => {
        const searchTerm = e.target.value.toLowerCase();
        const options = surahSelect.querySelectorAll('option');

        options.forEach(option => {
            const text = option.textContent.toLowerCase();
            const matches = text.includes(searchTerm);
            option.style.display = matches ? 'block' : 'none';
        });

        // Show first matching option
        const firstVisible = Array.from(options).find(opt => opt.style.display !== 'none');
        if (firstVisible && searchTerm.length > 0) {
            surahSelect.value = firstVisible.value;
            surahSelect.dispatchEvent(new Event('change'));
        }
    });

    const updateMax = () => {
        const count = VERSE_COUNTS[surahSelect.value] || 7;
        startAyahInput.max = count;
        endAyahInput.max = count;

        // Ensure current values don't exceed new max
        if (parseInt(startAyahInput.value) > count) startAyahInput.value = count;
        if (parseInt(endAyahInput.value) > count) endAyahInput.value = count;
    };

    surahSelect.addEventListener('change', () => {
        const count = VERSE_COUNTS[surahSelect.value];
        updateMax();
        startAyahInput.value = 1;
        endAyahInput.value = Math.min(5, count);
    });

    // Run once on init to set correct max for the first surah
    updateMax();

    // Prevent manual entry exceeding max
    [startAyahInput, endAyahInput].forEach(input => {
        input.addEventListener('input', () => {
            const max = parseInt(input.max);
            if (parseInt(input.value) > max) input.value = max;
            if (parseInt(input.value) < 1) input.value = 1;
        });
    });

    // Prevent cross-over (start > end or end < start)
    startAyahInput.addEventListener('change', () => {
        const start = parseInt(startAyahInput.value);
        const end = parseInt(endAyahInput.value);
        if (start > end) endAyahInput.value = start;
    });

    endAyahInput.addEventListener('change', () => {
        const start = parseInt(startAyahInput.value);
        const end = parseInt(endAyahInput.value);
        if (end < start) startAyahInput.value = end;
    });
}

function initCounters() {
    // Decrease buttons
    document.querySelectorAll('.counter-btn[data-type="minus"]').forEach(btn => {
        btn.addEventListener('click', () => {
            const target = document.getElementById(btn.dataset.target);
            const val = parseInt(target.value);
            if (val > 1) {
                target.value = val - 1;
                target.dispatchEvent(new Event('change'));
            }
        });
    });

    // Increase buttons
    document.querySelectorAll('.counter-btn[data-type="plus"]').forEach(btn => {
        btn.addEventListener('click', () => {
            const target = document.getElementById(btn.dataset.target);
            const val = parseInt(target.value);
            const max = parseInt(target.max);
            if (val < max) {
                target.value = val + 1;
                target.dispatchEvent(new Event('change'));
            }
        });
    });

    // Live-update the reciter-speed label as the user drags the slider and
    // paint the emerald fill from the RTL minimum (right) to the thumb.
    const reciterSpeedInput = document.getElementById('reciterSpeedInput');
    const reciterSpeedValue = document.getElementById('reciterSpeedValue');
    if (reciterSpeedInput && reciterSpeedValue) {
        const paintFill = () => {
            const min = parseFloat(reciterSpeedInput.min) || 0;
            const max = parseFloat(reciterSpeedInput.max) || 100;
            const pct = ((parseFloat(reciterSpeedInput.value) - min) / (max - min)) * 100;
            reciterSpeedInput.style.setProperty('--range-fill', `${pct}%`);
        };
        reciterSpeedInput.addEventListener('input', () => {
            reciterSpeedValue.textContent = parseFloat(reciterSpeedInput.value).toFixed(2);
            paintFill();
        });
        paintFill();
    }
}

async function loadConfig() {
    try {
        const response = await fetch(`${API_BASE}/api/config`);
        const data = await response.json();
        if (data.version) {
            document.getElementById('appVersion').textContent = data.version;
        }

        // Load Reciters (Synchronize with RECITERS_MAP from backend)
        if (data.reciters) {
            reciterSelect.innerHTML = '';
            Object.entries(data.reciters).forEach(([displayName, internalValue]) => {
                const option = document.createElement('option');
                option.value = internalValue;
                option.textContent = displayName;
                reciterSelect.appendChild(option);
            });
        }
        if (Array.isArray(data.themes) && data.themes.length) {
            renderThemeOptions(data.themes);
        }
    } catch (error) {
        console.error('Failed to load config:', error);
    }
}

function renderThemeOptions(themes) {
    const currentTheme = templateGrid.querySelector('input[name="template"]:checked')?.value || 'normal';
    const numberFormat = new Intl.NumberFormat('ar');
    const fragment = document.createDocumentFragment();

    themes.forEach((theme, index) => {
        const label = document.createElement('label');
        label.className = 'template-option';
        label.style.setProperty('--theme-index', index);

        const input = document.createElement('input');
        input.type = 'radio';
        input.name = 'template';
        input.value = theme.key;
        input.checked = theme.key === currentTheme || (!themes.some(item => item.key === currentTheme) && index === 0);

        const video = document.createElement('video');
        video.className = 'theme-preview';
        video.muted = true;
        video.loop = !(theme.previewUrls?.length > 1);
        video.playsInline = true;
        video.preload = 'metadata';
        video.setAttribute('aria-hidden', 'true');

        const previewUrls = Array.isArray(theme.previewUrls) && theme.previewUrls.length
            ? theme.previewUrls
            : [theme.previewUrl].filter(Boolean);
        if (previewUrls.length) video.src = previewUrls[0];
        let previewIndex = 0;
        let previewTimer = null;
        let previewActive = false;

        const playThemePreview = async () => {
            if (!previewActive || !previewUrls.length) return;
            video.src = previewUrls[previewIndex];
            video.classList.remove('theme-preview-change');
            requestAnimationFrame(() => video.classList.add('theme-preview-change'));
            try {
                await video.play();
            } catch (_) {
                return;
            }
            if (previewUrls.length > 1 && previewActive) {
                previewTimer = window.setTimeout(() => {
                    previewIndex = (previewIndex + 1) % previewUrls.length;
                    playThemePreview();
                }, 2800);
            }
        };

        const title = document.createElement('span');
        title.textContent = theme.label;

        const count = document.createElement('small');
        count.className = 'theme-count';
        count.textContent = `${numberFormat.format(theme.videoCount)} مقطع`;

        const previewOnIntent = () => {
            if (previewActive || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
            previewActive = true;
            playThemePreview();
        };
        const pauseOnExit = () => {
            previewActive = false;
            window.clearTimeout(previewTimer);
            previewTimer = null;
            video.pause();
        };
        label.addEventListener('pointerenter', previewOnIntent);
        label.addEventListener('pointerleave', pauseOnExit);
        label.addEventListener('focusin', previewOnIntent);
        label.addEventListener('focusout', pauseOnExit);

        label.append(input, video, title, count);
        fragment.appendChild(label);
    });

    templateGrid.replaceChildren(fragment);
}

// Global alias for compatibility
const loadAvailableFonts = loadConfig;


// --- Logic Functions ---
let displayedLogs = 0;
let progressInterval = null;

const WORKING_LABEL = '<span>جاري العمل</span><span class="loading-dots" aria-hidden="true"><span>.</span><span>.</span><span>.</span></span>';

async function pollProgress() {
    try {
        const res = await fetch(`${API_BASE}/api/progress`);
        const data = await res.json();

        if (data.is_running || data.is_complete || data.is_cancelled || data.error) {
            statusCard.classList.add('active');
            updateUI(data);
        }

        if (data.is_running && !progressInterval) {
            progressInterval = setInterval(pollProgress, 1000);
            generateBtn.disabled = true;
            generateBtn.innerHTML = WORKING_LABEL;
            previewBtn.disabled = true;
        } else if (!data.is_running && progressInterval) {
            clearInterval(progressInterval);
            progressInterval = null;
            generateBtn.disabled = false;
            generateBtn.innerHTML = generateBtnDefaultLabel;
            previewBtn.disabled = false;
            previewBtn.innerHTML = previewBtnDefaultLabel;
        }
    } catch (e) {
        console.error('Polling error:', e);
    }
}

function appendLog(msg) {
    const line = document.createElement('div');
    line.className = 'log-line';
    line.textContent = `> ${msg}`;
    logTerminal.appendChild(line);
    logTerminal.scrollTop = logTerminal.scrollHeight;
}

function setPlayerState(state) {
    // state: 'idle' | 'building' | 'ready'
    videoPreviewWrapper.classList.toggle('active', state !== 'idle');
    videoPreviewWrapper.classList.toggle('has-video', state === 'ready');
    previewSkeleton.hidden = state !== 'building';
}

function resetPlayer() {
    displayedLogs = 0;
    logTerminal.innerHTML = '<div class="log-line">&gt; <span>بانتظار بدء المهمة...</span></div>';
    statusCard.classList.remove('done');
    statusText.textContent = 'جاري التحضير...';
    progressFill.style.width = '0%';
    progressPercent.textContent = '0%';
    progressTrack.setAttribute('aria-valuenow', '0');
    setPlayerState('idle');
    previewVideo.pause();
    previewVideo.removeAttribute('src');
    previewVideo.load();
}

function updateUI(data) {
    progressFill.style.width = `${data.percent}%`;
    progressPercent.textContent = `${data.percent}%`;
    progressTrack.setAttribute('aria-valuenow', String(data.percent));
    statusText.textContent = data.error || data.status;
    if (data.is_running && Number.isFinite(data.eta_seconds) && data.eta_seconds > 0) {
        const seconds = Math.ceil(data.eta_seconds);
        const estimate = seconds >= 60 ? `${Math.ceil(seconds / 60)} دقيقة تقريباً` : `${seconds} ثانية تقريباً`;
        renderEta.textContent = `المرحلة: ${data.stage || 'جاري المعالجة'} · الوقت المتبقي ${estimate}`;
    } else {
        renderEta.textContent = data.is_running ? `المرحلة: ${data.stage || 'جاري المعالجة'}` : '';
    }
    retryBtn.hidden = !data.error;
    cancelBtn.hidden = !data.is_running;
    cancelBtn.disabled = Boolean(data.cancel_requested);
    cancelBtn.querySelector('.cancel-label').textContent = data.cancel_requested
        ? 'جارٍ الإلغاء...'
        : 'إلغاء العملية';

    if (data.is_running) {
        setPlayerState('building');
    }

    // Logs (textContent: build log text is never parsed as markup)
    while (displayedLogs < data.log.length) {
        appendLog(data.log[displayedLogs]);
        displayedLogs++;
    }

    if (data.is_complete && data.output_path) {
        // Video filename is the last part of path
        const filename = data.output_path.split(/[\\\/]/).pop();
        const videoUrl = `${API_BASE}/outputs/video/${filename}`;

        // Set video source and show preview/download immediately
        if (!previewVideo.src || !previewVideo.src.endsWith(filename)) {
            previewVideo.src = videoUrl;
            previewVideo.load();
        }

        setPlayerState('ready');

        // Update download link - ensure it's always visible
        const downloadLink = document.getElementById('downloadLink');
        if (downloadLink) {
            downloadLink.href = videoUrl;
            downloadLink.textContent = 'تحميل الفيديو';
        }

        statusCard.classList.add('done');

        // Bring the player into view and start playback (autoplay policies
        // may block it — native controls let the user press play instead).
        videoPreviewWrapper.scrollIntoView({
            behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
            block: 'nearest'
        });
        previewVideo.play().catch(() => {});
    }

    if (data.error) {
        previewBtn.disabled = false;
        previewBtn.innerHTML = previewBtnDefaultLabel;
        setPlayerState(previewVideo.src ? 'ready' : 'idle');
    }
}

cancelBtn.addEventListener('click', async () => {
    cancelBtn.disabled = true;
    cancelBtn.querySelector('.cancel-label').textContent = 'جارٍ الإلغاء...';
    try {
        const res = await fetch(`${API_BASE}/api/cancel`, { method: 'POST' });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.error || 'تعذر إلغاء العملية.');
        pollProgress();
    } catch (e) {
        cancelBtn.disabled = false;
        cancelBtn.querySelector('.cancel-label').textContent = 'إلغاء العملية';
        formError.textContent = e.message;
        formError.hidden = false;
    }
});

// --- Event Handlers ---

generateBtn.addEventListener('click', async (e) => {
    e.preventDefault();

    const payload = {
        reciter: reciterSelect.value,
        surah: parseInt(surahSelect.value),
        startAyah: parseInt(startAyahInput.value),
        endAyah: parseInt(endAyahInput.value),
        quality: qualitySelect.value,
        template: document.querySelector('input[name="template"]:checked')?.value || 'normal',
        personName: personNameInput.value,
        format: formatSelect.value,
        includeBismillah: document.getElementById('bismillahCheckbox').checked,
        showText: document.getElementById('showTextCheckbox').checked,
        highlightWords: document.getElementById('highlightWordsCheckbox').checked,
        textPosition: document.getElementById('textPositionSelect').value,
        targetDurationSeconds: (() => {
            const v = document.getElementById('targetDurationInput').value;
            const n = parseInt(v, 10);
            return Number.isFinite(n) && n > 0 ? n : null;
        })(),
        reciterSpeed: parseFloat(document.getElementById('reciterSpeedInput').value) || 1.0,
        transitionStyle: document.querySelector('input[name="transitionStyle"]:checked')?.value || 'crossfade',
        backgroundMotion: document.querySelector('input[name="backgroundMotion"]:checked')?.value || 'still',
        backgroundInterval: parseInt(document.getElementById('backgroundInterval').value, 10) || 15,
        backgroundIntervalUnit: document.getElementById('backgroundIntervalUnit').value
    };

    if (!Number.isInteger(payload.surah) || !Number.isInteger(payload.startAyah) ||
        !Number.isInteger(payload.endAyah) || payload.startAyah < 1 ||
        payload.endAyah < payload.startAyah || payload.endAyah > (VERSE_COUNTS[payload.surah] || 0)) {
        formError.textContent = 'تحقق من السورة وآيات البداية والنهاية قبل إنشاء الفيديو.';
        formError.hidden = false;
        return;
    }

    try {
        formError.hidden = true;
        resetPlayer();
        generateBtn.disabled = true;
        generateBtn.innerHTML = WORKING_LABEL;

        const res = await fetch(`${API_BASE}/api/generate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const data = await res.json().catch(() => ({}));
        if (res.ok && data.success) {
            if (!progressInterval) {
                progressInterval = setInterval(pollProgress, 1000);
            }
            pollProgress();
        } else {
            generateBtn.disabled = false;
            generateBtn.innerHTML = generateBtnDefaultLabel;
            formError.textContent = data.error || 'تعذر بدء إنشاء الفيديو. تحقق من المدخلات ثم حاول مجدداً.';
            formError.hidden = false;
        }
    } catch (e) {
        generateBtn.disabled = false;
        generateBtn.innerHTML = generateBtnDefaultLabel;
        formError.textContent = `تعذر الاتصال بالخادم: ${e.message}`;
        formError.hidden = false;
    }
});

// Enter inside a field submits the form: run the same build once and never
// reload the page. When the browser already fired the button click, the
// disabled guard stops a second request.
generatorForm.addEventListener('submit', (e) => {
    e.preventDefault();
    if (!generateBtn.disabled) generateBtn.click();
});

previewBtn.addEventListener('click', async () => {
    const payload = {
        reciter: reciterSelect.value,
        surah: parseInt(surahSelect.value),
        ayah: parseInt(startAyahInput.value),
        template: document.querySelector('input[name="template"]:checked')?.value || 'normal',
        showText: document.getElementById('showTextCheckbox').checked,
        highlightWords: document.getElementById('highlightWordsCheckbox').checked,
        textPosition: document.getElementById('textPositionSelect').value,
        backgroundMotion: document.querySelector('input[name="backgroundMotion"]:checked')?.value || 'still',
        backgroundInterval: parseInt(document.getElementById('backgroundInterval').value, 10) || 15,
        backgroundIntervalUnit: document.getElementById('backgroundIntervalUnit').value
    };

    previewBtn.disabled = true;
    previewBtn.innerHTML = '<span>جاري إنشاء المعاينة</span><span class="loading-dots" aria-hidden="true"><span>.</span><span>.</span><span>.</span></span>';

    try {
        resetPlayer();

        const res = await fetch(`${API_BASE}/api/preview`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const data = await res.json().catch(() => ({}));
        if (res.ok && (data.success !== false)) {
            if (!progressInterval) {
                progressInterval = setInterval(pollProgress, 1000);
            }
            pollProgress();
        } else {
            formError.textContent = data.error || 'تعذر إنشاء المعاينة. تحقق من الاتصال وحاول مجدداً.';
            formError.hidden = false;
            previewBtn.disabled = false;
            previewBtn.innerHTML = previewBtnDefaultLabel;
        }
    } catch (e) {
        console.error('Preview error:', e);
        formError.textContent = `تعذر الاتصال بالخادم: ${e.message}`;
        formError.hidden = false;
        previewBtn.disabled = false;
        previewBtn.innerHTML = previewBtnDefaultLabel;
    }
});

retryBtn.addEventListener('click', () => {
    retryBtn.hidden = true;
    formError.hidden = true;
    generateBtn.click();
});

// Word highlighting uses the renderer's best-effort character-weighted
// timing estimate; its UI label makes that limitation explicit.
const showTextCheckbox = document.getElementById('showTextCheckbox');
const highlightWordsCheckbox = document.getElementById('highlightWordsCheckbox');
const textPositionSelect = document.getElementById('textPositionSelect');

function syncHighlightToggle() {
    highlightWordsCheckbox.disabled = !showTextCheckbox.checked;
    textPositionSelect.disabled = !showTextCheckbox.checked;
    const status = document.getElementById('highlightWordsStatus');
    status.textContent = !showTextCheckbox.checked
        ? 'يتطلب نص الآية'
        : (highlightWordsCheckbox.checked ? 'مفعّل' : 'متوقف');
}

showTextCheckbox.addEventListener('change', syncHighlightToggle);
highlightWordsCheckbox.addEventListener('change', syncHighlightToggle);
syncHighlightToggle();

// --- Custom dropdowns (native <select> lists paint OS-blue; the proxy
// below renders the same value through design tokens while the hidden
// native select keeps every existing reader/writer working untouched) ---
function enhanceSelect(select) {
    if (select.dataset.enhanced) return;
    select.dataset.enhanced = '1';

    const wrap = document.createElement('div');
    wrap.className = 'relative';
    select.parentElement.insertBefore(wrap, select);
    wrap.appendChild(select);
    select.classList.add('hidden');

    const label = select.closest('div').parentElement.querySelector('label');
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'ds-btn w-full rounded-2xl border-2 border-gold/25 bg-white px-4 py-3.5 text-ink outline-none transition cursor-pointer hover:border-action/40 focus-visible:border-action focus-visible:ring-4 focus-visible:ring-action/20 focus-visible:outline-none disabled:opacity-45 disabled:cursor-not-allowed flex items-center justify-between gap-3 text-right';
    btn.setAttribute('aria-haspopup', 'listbox');
    btn.setAttribute('aria-expanded', 'false');
    if (label) {
        const name = (label.textContent || '').replace(/\s+/g, ' ').trim();
        btn.setAttribute('aria-label', name || select.id);
    } else if (select.title) btn.setAttribute('aria-label', select.title);
    else if (select.id) btn.setAttribute('aria-label', select.id);
    const btnLabel = document.createElement('span');
    btnLabel.className = 'flex-1 truncate';
    const chev = document.createElement('span');
    chev.className = 'shrink-0 text-action';
    chev.innerHTML = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="6 9 12 15 18 9"/></svg>';
    btn.appendChild(btnLabel);
    btn.appendChild(chev);

    const list = document.createElement('ul');
    list.setAttribute('role', 'listbox');
    list.hidden = true;
    list.className = 'absolute z-50 mt-2 w-full max-h-[min(60vh,22rem)] overflow-y-auto rounded-2xl border-2 border-gold/25 bg-white p-2 shadow-[0_20px_50px_rgba(74,60,25,0.25)]';

    wrap.appendChild(btn);
    wrap.appendChild(list);

    let items = [];
    let activeIdx = -1;

    function paint() {
        list.innerHTML = '';
        items = [];
        const opts = Array.from(select.options);
        opts.forEach((opt) => {
            if (opt.style.display === 'none') return;
            const li = document.createElement('li');
            li.setAttribute('role', 'option');
            li.setAttribute('tabindex', '-1');
            li.id = `${select.id}-opt-${items.length}`;
            const selected = opt.selected;
            li.setAttribute('aria-selected', selected ? 'true' : 'false');
            li.textContent = opt.textContent;
            li.className = 'flex items-center justify-between gap-3 rounded-xl px-4 py-2.5 cursor-pointer transition ' +
                (selected ? 'bg-action font-bold text-foam' : 'text-ink hover:bg-tint');
            if (selected) {
                const tick = document.createElement('span');
                tick.className = 'shrink-0 text-foam/80';
                tick.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m5 13 4 4L19 7"/></svg>';
                li.appendChild(tick);
            }
            li.addEventListener('click', () => choose(items.indexOf(li)));
            li.addEventListener('mousemove', () => setActive(items.indexOf(li), false));
            list.appendChild(li);
            items.push(li);
        });
        const current = opts.find((o) => o.selected) || opts[0];
        btnLabel.textContent = current ? current.textContent : '';
        btn.disabled = select.disabled;
        activeIdx = items.findIndex((li) => li.getAttribute('aria-selected') === 'true');
    }

    function setActive(idx, focusIt = true) {
        if (!items.length) return;
        activeIdx = (idx + items.length) % items.length;
        items.forEach((li, i) => {
            const on = i === activeIdx;
            li.classList.toggle('bg-tint-strong', on && li.getAttribute('aria-selected') !== 'true');
            if (on) {
                list.setAttribute('aria-activedescendant', li.id);
                const listBox = list.getBoundingClientRect();
                const rowBox = li.getBoundingClientRect();
                if (rowBox.top < listBox.top) list.scrollTop -= listBox.top - rowBox.top;
                else if (rowBox.bottom > listBox.bottom) list.scrollTop += rowBox.bottom - listBox.bottom;
                if (focusIt) li.focus();
            }
        });
    }

    // The grid cells carry a load-in transform, which makes every cell its own
    // stacking context. Raise the open cell so the list paints over the fields
    // that follow it in the DOM.
    function raiseCell(on) {
        const cell = wrap.parentElement;
        cell.style.position = 'relative';
        cell.style.zIndex = on ? '40' : '';
    }

    function open() {
        if (btn.disabled) return;
        paint();
        raiseCell(true);
        list.hidden = false;
        btn.setAttribute('aria-expanded', 'true');
        // Flip above the button when the list would run past the viewport.
        const room = window.innerHeight - btn.getBoundingClientRect().bottom;
        const flip = room < 300 && btn.getBoundingClientRect().top > 300;
        list.style.top = flip ? 'auto' : '';
        list.style.bottom = flip ? 'calc(100% + 0.5rem)' : '';
        list.classList.toggle('mt-2', !flip);
        setActive(Math.max(activeIdx, 0));
    }

    function close(returnFocus = true) {
        list.hidden = true;
        btn.setAttribute('aria-expanded', 'false');
        list.style.top = '';
        list.style.bottom = '';
        list.classList.add('mt-2');
        raiseCell(false);
        if (returnFocus) btn.focus();
    }

    function choose(idx) {
        if (idx < 0 || idx >= items.length) return;
        const visible = Array.from(select.options).filter((o) => o.style.display !== 'none');
        select.selectedIndex = Array.from(select.options).indexOf(visible[idx]);
        select.dispatchEvent(new Event('change', { bubbles: true }));
        paint();
        close();
    }

    btn.addEventListener('click', () => (list.hidden ? open() : close(false)));
    btn.addEventListener('keydown', (e) => {
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            open();
        }
    });
    list.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            e.preventDefault();
            close();
        } else if (e.key === 'ArrowDown') {
            e.preventDefault();
            setActive(activeIdx + 1);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            setActive(activeIdx - 1);
        } else if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            choose(activeIdx);
        } else if (e.key === 'Tab') {
            close(false);
        }
    });
    document.addEventListener('click', (e) => {
        if (!wrap.contains(e.target) && !list.hidden) close(false);
    });

    // Keep the proxy honest: any native mutation (options loaded, search
    // filter, disabled sync) repaints it.
    new MutationObserver(paint).observe(select, {
        childList: true,
        attributes: true,
        subtree: true,
        attributeFilter: ['disabled', 'style'],
    });
    select.addEventListener('change', () => {
        if (list.hidden) paint();
    });

    paint();
}

document.querySelectorAll('select').forEach(enhanceSelect);

// --- Video player: native controls are the single playback surface ---
const previewBtnDefaultLabel = previewBtn.innerHTML;
generateBtnDefaultLabel = generateBtn.innerHTML;
