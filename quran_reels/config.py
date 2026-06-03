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

# =============================================================================
# Feature flags  (animations.md §12)
# =============================================================================
# Gates each phase of the animations plan so behavior changes are opt-in.
#   - font_polish:     Phase 1 (always on, already shipped)
#   - text_animations: Phase 2 (intro/outro fades, slide/zoom on text)
#   - kinetic_text:    Phase 3 (per-word reveal — opt-in, not yet implemented)
#   - forced_alignment: Phase 3 v3 (per-word word-by-word forced alignment)

FEATURE_FLAGS = {
    'font_polish':        True,
    'text_animations':    True,
    'kinetic_text':       False,
    'forced_alignment':   False,
}

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
}

# =============================================================================
# Visual templates
# =============================================================================

TEMPLATES = {
    'ramadan': {
        'bg_style': 'night', 'text_color': '#FFD700', 'font_size_mult': 1.20,
        'text_animation': 'fade_in', 'transition': 'fade',
        'transition_style': 'cinematic',
        'font': 'Amiri-Bold.ttf', 'glow_color': '#FFD700', 'glow_radius': 8,
    },
    'normal':  {
        'bg_style': 'nature', 'text_color': '#FFFFFF', 'font_size_mult': 1.00,
        'text_animation': 'slide_up', 'transition': 'fade',
        'transition_style': 'cinematic',
        'font': 'Amiri-Regular.ttf',
    },
    'masjid':  {
        # Soft white halo evokes moonlit calligraphy on the mosque wall.
        # Note: must use Amiri — Lateef/ElMessiri lack presentation forms and
        # PIL does not apply OpenType GSUB contextual substitution.
        'bg_style': 'masjid', 'text_color': '#FFFFFF', 'font_size_mult': 1.10,
        'text_animation': 'fade_in', 'transition': 'fade',
        'transition_style': 'cinematic',
        'font': 'Amiri-Bold.ttf', 'glow_color': '#FFFFFF80', 'glow_radius': 4,
    },
    'islamic': {
        # Heavier drop shadow gives the calligraphic depth of manuscript art.
        'bg_style': 'islamic', 'text_color': '#FFFFFF', 'font_size_mult': 1.10,
        'text_animation': 'zoom_in', 'transition': 'wipe',
        'transition_style': 'cinematic',
        'font': 'Amiri-Bold.ttf',
    },
}

# =============================================================================
# Animation & transitions
# =============================================================================

VIDEO_TRANSITIONS = {
    'fade':       {'type': 'fade',     'duration': 0.5, 'ffmpeg_filter': 'fade=out:st={duration}:d={duration}'},
    'dissolve':   {'type': 'dissolve', 'duration': 0.5, 'ffmpeg_filter': 'xfade=transition=fade:duration={duration}'},
    'wipe':       {'type': 'wipe',     'duration': 0.5, 'direction': 'right', 'ffmpeg_filter': 'xfade=transition=wipeleft:duration={duration}'},
    'slide':      {'type': 'slide',    'duration': 0.5, 'direction': 'left',  'ffmpeg_filter': 'xfade=transition=slideleft:duration={duration}'},
    'cross_zoom': {'type': 'zoom',     'duration': 0.5, 'ffmpeg_filter': 'xfade=transition=zoomin:duration={duration}'},
    'pixelate':   {'type': 'pixelate', 'duration': 0.5, 'ffmpeg_filter': 'xfade=transition=pixelize:duration={duration}'},
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
# Bismillah is recited at the start of every surah EXCEPT At-Tawbah (surah 9).
# Al-Fatihah (surah 1) is skipped here because "Bismillah ..." is already
# considered the first ayah of Al-Fatihah by most schools — prepending it
# would duplicate.

BISMILLAH_TEXT = "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ"
BISMILLAH_DURATION_SEC = 1.8  # self-contained title card length
BISMILLAH_SKIP_SURAHS = {1, 9}  # Al-Fatihah (Bismillah IS ayah 1) and At-Tawbah
