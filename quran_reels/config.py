"""Static configuration for the Quran Reels Generator.

This module holds the constants that used to live in ``main.py`` STEP 2b
(feature flags) and STEP 8 (templates / presets / reciters / verse
counts / surah names).  Splitting them out removes ~200 lines from
``main.py`` and gives a single, importable home for any caller that
needs to read the project's configuration without spinning up the
Flask app.

Nothing in this module imports from ``main`` — it's a leaf — so the
order in which it is loaded does not matter.
"""

import os

# =============================================================================
# Ayah text rendering (feature 002-ayah-text-sync, Constitution v2.0.0
# Principle I).  Consumed by quran_reels/services/text_overlay.py.
# =============================================================================

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ASSETS_DIR = os.path.join(_REPO_ROOT, "assets")

# Font fallback chain: bundled Quranic-grade font first (deterministic
# rendering across machines), then system families resolved via fontconfig.
TEXT_FONT_CANDIDATES = [
    ("file", os.path.join(_ASSETS_DIR, "fonts", "ScheherazadeNew-Regular.ttf")),
    ("family", "Amiri"),
    ("family", "Noto Kufi Arabic"),
    ("family", "DejaVu Sans"),
]

# Text placement zone — lower-center block on the vertical frame.
TEXT_ZONE_MAX_WIDTH_FRAC = 0.86    # block width cap vs frame width
TEXT_ZONE_BOTTOM_MARGIN_FRAC = 0.08  # gap between block bottom and frame bottom
TEXT_ZONE_MAX_HEIGHT_FRAC = 0.34   # block height cap vs frame height
TEXT_MAX_LINES = 6                 # hard wrap budget inside the zone

# Glyph size bounds (fractions of frame width; 1080-wide reference design).
TEXT_SIZE_MIN_FRAC = 0.042         # ≈45 px @1080 → legibility floor (SC-003)
TEXT_SIZE_MAX_FRAC = 0.085         # ≈92 px @1080

# Backing box behind the glyphs (contrast treatment, FR-004/SC-003).
BACKING_COLOR_RGB = (17, 17, 17)   # near-black rounded box fill
BACKING_OPACITY = 0.60             # alpha of the backing fill
BACKING_PADDING_PX = 28            # padding around text at 1080-wide design
TEXT_MIN_CONTRAST = 4.5            # WCAG-ish contrast floor vs backdrop

# Feature defaults (request fields may override per call).
SHOW_TEXT_DEFAULT = True
HIGHLIGHT_WORDS_DEFAULT = True     # estimated word timing, enabled by default
HIGHLIGHT_COLOR_RGBA = (232, 182, 76, 140)  # Honey Gold from the visual theme
TEXT_POSITION_DEFAULT = "lower"    # ayah-text block anchor: "lower" | "middle"
TEXT_POSITIONS = ("lower", "middle")

# Per-template styling profiles (keys match TEMPLATES below).
# 'accent' drives the glyph color; backing opacity varies slightly so each
# theme reads distinctly while staying within the contrast guard.
TEXT_STYLE_PROFILES = {
    "ramadan": {"accent": "#FFD98A", "backing_opacity": 0.62},
    "normal":  {"accent": "#FFFFFF", "backing_opacity": 0.58},
    "masjid":  {"accent": "#F2FBF4", "backing_opacity": 0.60},
    "islamic": {"accent": "#FFF7E6", "backing_opacity": 0.60},
}


# =============================================================================
# Feature flags
# =============================================================================
# ``FEATURE_FLAGS`` remains an empty compatibility mapping. Quran text and
# estimated word highlighting are controlled by their explicit request flags.

FEATURE_FLAGS = {}

# =============================================================================
# Output dimensions / format
# =============================================================================

TARGET_W = 1080
TARGET_H = 1920

QUALITY_PRESETS = {
    'low': {'fps': 24, 'codec': 'libx264', 'preset': 'ultrafast', 'bitrate': '4M'},
    'medium': {'fps': 30, 'codec': 'libx264', 'preset': 'fast', 'bitrate': '8M'},
    'high': {'fps': 30, 'codec': 'libx264', 'preset': 'fast', 'bitrate': '12M'},
}

OUTPUT_FORMATS = {
    'reels': {'size': (1080, 1920), 'duration': 600},  # 10 mins
    'story': {'size': (1080, 1920), 'duration': 60},   # 1 min
    'post':  {'size': (1080, 1080), 'duration': 600},  # 10 mins
    'youtube': {'size': (1920, 1080), 'duration': 600},  # 16:9 landscape
}

# =============================================================================
# Visual templates
# =============================================================================
# Each template now drives only the background style and transition between
# ayahs. Text-rendering fields (text_color, font,
# font_size_mult, glow_color, glow_radius, text_animation) have been
# removed along with the rest of the text-on-video feature.

TEMPLATES = {
    'ramadan': {
        'bg_style': 'night',
        'transition': 'crossfade',
        'transition_style': 'crossfade',
    },
    'normal':  {
        'bg_style': 'nature',
        'transition': 'crossfade',
        'transition_style': 'crossfade',
    },
    'masjid':  {
        'bg_style': 'masjid',
        'transition': 'crossfade',
        'transition_style': 'crossfade',
    },
    'islamic': {
        'bg_style': 'islamic',
        'transition': 'crossfade',
        'transition_style': 'crossfade',
    },
    'forest': {
        'bg_style': 'forest',
        'transition': 'crossfade',
        'transition_style': 'crossfade',
    },
    'trees': {
        'bg_style': 'trees',
        'transition': 'crossfade',
        'transition_style': 'crossfade',
    },
}

TEMPLATE_LABELS = {
    'normal': 'طبيعة',
    'ramadan': 'ليل',
    'masjid': 'المسجد',
    'islamic': 'فن إسلامي',
    'forest': 'الغابة',
    'trees': 'الأشجار',
    'rain': 'أجواء المطر',
    'nature_vision': 'مشاهد الطبيعة',
}

BACKGROUND_VIDEO_EXTENSIONS = ('.mp4', '.mov')

# Optional camera movement applied to the background layer of each ayah.
BACKGROUND_MOTIONS = ('still', 'zoom_in', 'zoom_out', 'drift')

# =============================================================================
# Video transitions between ayahs. These affect video only; the recitation
# audio remains concatenated at its original duration.
# =============================================================================

VIDEO_TRANSITIONS = {
    'crossfade': {'type': 'fade', 'duration': 0.45},
    'fadeblack': {'type': 'fadeblack', 'duration': 0.45},
    'smooth': {'type': 'fade', 'duration': 0.45},
}

# =============================================================================
# Quran / reciter metadata
# =============================================================================

VERSE_COUNTS = {
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
    111: 5, 112: 4, 113: 5, 114: 6,
}

SURAH_NAMES = [
    'الفاتحة', 'البقرة', 'آل عمران', 'النساء', 'المائدة', 'الأنعام', 'الأعراف', 'الأنفال', 'التوبة', 'يونس',
    'هود', 'يوسف', 'الرعد', 'إبراهيم', 'الحجر', 'النحل', 'الإسراء', 'الكهف', 'مريم', 'طه',
    'الأنبياء', 'الحج', 'المؤمنون', 'النور', 'الفرقان', 'الشعراء', 'النمل', 'القصص', 'العنكبوت', 'الروم',
    'لقمان', 'السجدة', 'الأحزاب', 'سبأ', 'فاطر', 'يس', 'الصافات', 'ص', 'الزمر', 'غافر',
    'فصلت', 'الشورى', 'الزخرف', 'الدخان', 'الجاثية', 'الأحقاف', 'محمد', 'الفتح', 'الحجرات', 'ق',
    'الذاريات', 'الطور', 'النجم', 'القمر', 'الرحمن', 'الواقعة', 'الحديد', 'المجادلة', 'الحشر', 'الممتحنة',
    'الصف', 'الجمعة', 'المنافقون', 'التغابن', 'الطلاق', 'التحريم', 'الملك', 'القلم', 'الحاقة', 'المعارج',
    'نوح', 'الجن', 'المزمل', 'المدثر', 'القيامة', 'الإنسان', 'المرسلات', 'النبأ', 'النازعات', 'عبس',
    'التكوير', 'الانفطار', 'المطففين', 'الانشقاق', 'البروج', 'الطارئ', 'الأعلى', 'الغاشية', 'الفجر', 'البلد',
    'الشمس', 'الليل', 'الضحى', 'الشرح', 'التين', 'العلق', 'القدر', 'البينة', 'الزلزلة', 'العاديات',
    'القارعة', 'التكاثر', 'العصر', 'الهمزة', 'الفيل', 'قريش', 'الماعون', 'الكوثر', 'الكافرون', 'النصر',
    'المسد', 'الإخلاص', 'الفلق', 'الناس',
]

RECITERS_MAP = {
    'الشيخ عبدالباسط عبدالصمد':              'AbdulSamad_64kbps_QuranExplorer.Com',
    'الشيخ عبدالباسط عبدالصمد (مرتل)':       'Abdul_Basit_Murattal_64kbps',
    'الشيخ عبدالرحمن السديس':                'Abdurrahmaan_As-Sudais_64kbps',
    'الشيخ محمد صديق المنشاوي (مجود)':       'Minshawy_Mujawwad_64kbps',
    'الشيخ سعود الشريم':                      'Saood_ash-Shuraym_64kbps',
    'الشيخ محمود خليل الحصري':                'Husary_64kbps',
    'الشيخ محمود علي البنا':                  'mahmoud_ali_al_banna_32kbps',
    'الشيخ عبدالباسط عبدالصمد (مجود)':       'Abdul_Basit_Mujawwad_128kbps',
    'الشيخ أحمد نعينع':                        'Ahmed_Neana_128kbps',
    'الشيخ علي جابر':                          'Ali_Jaber_64kbps',
    'الشيخ محمد الطبلاوي':                     'Mohammad_al_Tablaway_128kbps',
    'الشيخ مصطفى إسماعيل':                    'Mustafa_Ismail_48kbps',
}

# =============================================================================
# Bismillah (Surah-opening invocation)
# =============================================================================
# The optional unsynchronized visual lead-in is skipped for At-Tawbah, which
# has no opening Bismillah, and Al-Fatihah, whose first ayah contains it.

BISMILLAH_DURATION_SEC = 1.8  # visual-only lead-in over ayah audio
BISMILLAH_SKIP_SURAHS = {1, 9}  # Al-Fatihah already includes it; At-Tawbah omits it


def should_show_bismillah_visual(include_bismillah: bool, surah: int,
                                  ayah: int) -> bool:
    """Return whether an explicit visual-only opening applies to this ayah."""
    return bool(include_bismillah and ayah == 1
                and surah not in BISMILLAH_SKIP_SURAHS)
