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
const templateSelect = document.getElementById('templateSelect');
const formatSelect = document.getElementById('formatSelect');
const personNameInput = document.getElementById('personName');
const fontSelect = document.getElementById('fontSelect');



const generateBtn = document.getElementById('generateBtn');
const previewBtn = document.getElementById('previewBtn');

const statusCard = document.getElementById('statusCard');
const progressFill = document.getElementById('progressFill');
const progressPercent = document.getElementById('progressPercent');
const statusText = document.getElementById('statusText');
const logTerminal = document.getElementById('logTerminal');

const videoPreviewWrapper = document.getElementById('videoPreviewWrapper');
const previewVideo = document.getElementById('previewVideo');

// --- Initialization ---
document.addEventListener('DOMContentLoaded', () => {
    initSurahs();
    initParticles();
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
}

function initParticles() {
    const container = document.getElementById('particles');
    for (let i = 0; i < 30; i++) {
        const p = document.createElement('div');
        p.className = 'particle';
        const size = Math.random() * 4 + 2;
        p.style.width = `${size}px`;
        p.style.height = `${size}px`;
        p.style.left = `${Math.random() * 100}%`;
        p.style.bottom = `-20px`;
        p.style.animationDuration = `${Math.random() * 10 + 10}s`;
        p.style.animationDelay = `${Math.random() * 5}s`;
        container.appendChild(p);
    }
}

const refreshFontsBtn = document.getElementById('refreshFontsBtn');

async function loadConfig() {
    try {
        const response = await fetch(`${API_BASE}/api/config`);
        const data = await response.json();

        // 1. Load Fonts
        if (data.availableFonts && data.availableFonts.length > 0) {
            fontSelect.innerHTML = '<option value="random">عشوائي (تلقائي)</option>';
            data.availableFonts.forEach(font => {
                const option = document.createElement('option');
                option.value = font;
                option.textContent = font.replace(/\.(ttf|otf)$/i, '');
                fontSelect.appendChild(option);
            });
        }

        // 2. Load Reciters (Synchronize with RECITERS_MAP from backend)
        if (data.reciters) {
            reciterSelect.innerHTML = '';
            Object.entries(data.reciters).forEach(([displayName, internalValue]) => {
                const option = document.createElement('option');
                option.value = internalValue;
                option.textContent = displayName;
                reciterSelect.appendChild(option);
            });
        }
    } catch (error) {
        console.error('Failed to load config:', error);
    }
}

// Global alias for compatibility
const loadAvailableFonts = loadConfig;

if (refreshFontsBtn) {
    refreshFontsBtn.addEventListener('click', () => {
        refreshFontsBtn.classList.add('spinning');
        loadConfig();
        setTimeout(() => refreshFontsBtn.classList.remove('spinning'), 1000);
    });
}


// --- Logic Functions ---
let displayedLogs = 0;
let progressInterval = null;

async function pollProgress() {
    try {
        const res = await fetch(`${API_BASE}/api/progress`);
        const data = await res.json();

        if (data.is_running || data.is_complete || data.error) {
            statusCard.classList.add('active');
            updateUI(data);
        }

        if (data.is_running && !progressInterval) {
            progressInterval = setInterval(pollProgress, 1000);
            generateBtn.disabled = true;
            generateBtn.innerHTML = '<span>جاري العمل...</span> <div class="loading-dots"><span>.</span><span>.</span><span>.</span></div>';
        } else if (!data.is_running && progressInterval) {
            clearInterval(progressInterval);
            progressInterval = null;
            generateBtn.disabled = false;
            generateBtn.innerHTML = '<span>إنشاء الفيديو</span>';
        }
    } catch (e) {
        console.error('Polling error:', e);
    }
}

function updateUI(data) {
    progressFill.style.width = `${data.percent}%`;
    progressPercent.textContent = `${data.percent}%`;
    statusText.textContent = data.status;

    // Logs
    while (displayedLogs < data.log.length) {
        const msg = data.log[displayedLogs];
        const line = document.createElement('div');
        line.className = 'log-line';
        line.innerHTML = `> <span>${msg}</span>`;
        logTerminal.appendChild(line);
        logTerminal.scrollTop = logTerminal.scrollHeight;
        displayedLogs++;
    }

    if (data.is_complete && data.output_path) {
        // Video filename is the last part of path
        const filename = data.output_path.split(/[\\\/]/).pop();
        previewVideo.src = `${API_BASE}/outputs/video/${filename}`;
        videoPreviewWrapper.classList.add('active');
    }
}

// --- Event Handlers ---

generateBtn.addEventListener('click', async (e) => {
    e.preventDefault();

    const payload = {
        reciter: reciterSelect.value,
        surah: parseInt(surahSelect.value),
        startAyah: parseInt(startAyahInput.value),
        endAyah: parseInt(endAyahInput.value),
        quality: qualitySelect.value,
        template: templateSelect.value,
        personName: personNameInput.value,
        format: formatSelect.value,
        selectedFont: document.getElementById('fontSelect').value,
        showText: document.getElementById('showTextSelect').value === 'yes'
    };

    if (payload.endAyah < payload.startAyah) {
        alert('حدث خطأ: يجب أن تكون آية النهاية أكبر من آية البداية');
        return;
    }

    try {
        displayedLogs = 0;
        logTerminal.innerHTML = '';
        videoPreviewWrapper.classList.remove('active');

        const res = await fetch(`${API_BASE}/api/generate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const data = await res.json();
        if (data.success) {
            pollProgress();
        } else {
            alert(data.error || 'حدث خطأ في بدء العملية');
        }
    } catch (e) {
        alert('فشل الاتصال بالخادم: ' + e.message);
    }
});

previewBtn.addEventListener('click', async () => {
    const payload = {
        reciter: reciterSelect.value,
        surah: parseInt(surahSelect.value),
        ayah: parseInt(startAyahInput.value),
        template: templateSelect.value,
        showText: document.getElementById('showTextSelect').value === 'yes'
    };

    try {
        displayedLogs = 0;
        logTerminal.innerHTML = '';
        videoPreviewWrapper.classList.remove('active');

        const res = await fetch(`${API_BASE}/api/preview`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (res.ok) {
            pollProgress();
        }
    } catch (e) {
        console.error('Preview error:', e);
    }
});
