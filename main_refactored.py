# Quran Reels Generator - Refactored Backend Server
# Major refactoring: unified text processing, simplified font system, optimized performance

import os
import sys
import shutil
import random
import threading
import webbrowser
import json
import datetime
import logging
import traceback
import subprocess
import time
import concurrent.futures
import hashlib
import re
import tempfile
import atexit

from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS

# =============================================================================
# STEP 1: PATH RESOLUTION & DIRECTORY SETUP
# =============================================================================

def app_dir():
    """Returns the directory of the executable (or script)"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def bundled_dir():
    """Returns the bundled temp directory or script dir"""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

EXEC_DIR = app_dir()
BUNDLE_DIR = bundled_dir()

# =============================================================================
# STEP 2: LOGGING SETUP
# =============================================================================

log_path = os.path.join(EXEC_DIR, "runlog.txt")
logging.basicConfig(filename=log_path, level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s', force=True)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
logging.getLogger().addHandler(console_handler)

logging.info("--- Quran Reels Generator (Refactored) ---")
logging.info(f"Exec Dir: {EXEC_DIR}")
logging.info(f"Bundle Dir: {BUNDLE_DIR}")

# =============================================================================
# STEP 3: TEMPORARY DIRECTORY MANAGEMENT (NEW: replaces static audio folder)
# =============================================================================

# Create temp directory that auto-cleans on exit
TEMP_DIR = tempfile.mkdtemp(prefix="quran_reels_")
logging.info(f"Temp directory: {TEMP_DIR}")

def cleanup_temp():
    """Cleanup temp directory on exit"""
    try:
        if os.path.exists(TEMP_DIR):
            shutil.rmtree(TEMP_DIR, ignore_errors=True)
            logging.info("Temp directory cleaned up")
    except:
        pass

atexit.register(cleanup_temp)

# =============================================================================
# STEP 4: FIND BINARIES (FFMPEG, ImageMagick)
# =============================================================================

def is_image_magick(path):
    if not path or not os.path.isfile(path):
        return False
    if "System32" in path and "convert.exe" in path.lower():
        return False
    try:
        res = subprocess.run([path, "-version"], capture_output=True, text=True, timeout=2)
        return "ImageMagick" in res.stdout or "ImageMagick" in res.stderr
    except:
        return False

def find_binary(portable_path, system_name):
    if os.path.isfile(portable_path):
        if system_name in ["magick", "convert"] and not is_image_magick(portable_path):
            pass
        else:
            return portable_path
    system_path = shutil.which(system_name)
    if system_path:
        if system_name in ["magick", "convert"]:
            if is_image_magick(system_path):
                return system_path
        else:
            return system_path
    return None

FFMPEG_EXE = find_binary(os.path.join(BUNDLE_DIR, "bin", "ffmpeg", "ffmpeg.exe"), "ffmpeg")
IM_MAGICK_EXE = find_binary(os.path.join(BUNDLE_DIR, "bin", "imagemagick", "magick.exe"), "magick")
if not IM_MAGICK_EXE:
    IM_MAGICK_EXE = find_binary(os.path.join(BUNDLE_DIR, "bin", "imagemagick", "convert.exe"), "convert")

IM_HOME = os.path.join(BUNDLE_DIR, "bin", "imagemagick")

VISION_DIR = os.path.join(BUNDLE_DIR, "vision")
UI_PATH = os.path.join(BUNDLE_DIR, "UI.html")

OUT_DIR = os.path.join(EXEC_DIR, "outputs")
VIDEO_DIR = os.path.join(OUT_DIR, "video")
BG_CACHE_DIR = os.path.join(OUT_DIR, "bg_cache")
FONT_DIR = os.path.join(EXEC_DIR, "fonts")
FONT_CACHE_DIR = os.path.join(FONT_DIR, "_cache")

# =============================================================================
# STEP 5: UNIFIED FONT SYSTEM (NEW: scan once, store WORKING_FONT)
# =============================================================================

WORKING_FONT = None  # Global variable - best Arabic font found

def _is_ascii(s):
    try:
        s.encode("ascii")
        return True
    except:
        return False

def _safe_font_path_for_imagemagick(font_path):
    """Return a font path that ImageMagick is more likely to read on Windows."""
    if not font_path:
        return font_path
    if _is_ascii(font_path) and _is_ascii(os.path.basename(font_path)):
        return font_path

    os.makedirs(FONT_CACHE_DIR, exist_ok=True)
    ext = os.path.splitext(font_path)[1].lower()
    if ext not in [".ttf", ".otf"]:
        ext = ".ttf"

    digest = hashlib.md5(font_path.encode("utf-8", errors="ignore")).hexdigest()[:12]
    cached_name = f"font_{digest}{ext}"
    cached_path = os.path.join(FONT_CACHE_DIR, cached_name)

    if not os.path.exists(cached_path):
        shutil.copy2(font_path, cached_path)
        logging.info(f"Cached font: {os.path.basename(font_path)} -> {cached_name}")

    return cached_path if os.path.getsize(cached_path) > 0 else font_path

def test_font_arabic(font_path):
    """Test if a font can render Arabic text with tashkeel"""
    try:
        from PIL import Image, ImageDraw, ImageFont
        import arabic_reshaper
        from bidi.algorithm import get_display

        font = ImageFont.truetype(font_path, 30)
        # Test with tashkeel to ensure diacritics work
        test_text = "بِسْمِ اللَّهِ الرَّحْمَنِ الرَّحِيمِ"
        reshaped = arabic_reshaper.reshape(test_text)
        bidi_text = get_display(reshaped)

        img = Image.new('RGB', (400, 60), color='white')
        draw = ImageDraw.Draw(img)
        draw.text((20, 20), bidi_text, font=font, fill='black')

        return True
    except Exception as e:
        logging.warning(f"Font test failed for {os.path.basename(font_path)}: {e}")
        return False

def init_font_system():
    """Initialize font system once at startup - find best working Arabic font"""
    global WORKING_FONT

    # Priority order for Arabic fonts
    preferred_fonts = [
        "Amiri-Bold.ttf", "Amiri-Regular.ttf",
        "Dubai-Bold.ttf", "Dubai-Regular.ttf",
        "Lateef-Bold.ttf", "Lateef-Medium.ttf",
        "ElMessiri-Bold.ttf", "ElMessiri-Regular.ttf",
        "Tajawal-Bold.ttf", "Tajawal-Regular.ttf",
        "Zain-Bold.ttf", "Zain-Regular.ttf"
    ]

    # Try preferred fonts first
    for font_name in preferred_fonts:
        font_path = os.path.join(FONT_DIR, font_name)
        if os.path.exists(font_path):
            if test_font_arabic(font_path):
                WORKING_FONT = _safe_font_path_for_imagemagick(font_path)
                logging.info(f"✅ Working font selected: {font_name}")
                return

    # Try any available font
    if os.path.exists(FONT_DIR):
        for file in os.listdir(FONT_DIR):
            if file.lower().endswith(('.ttf', '.otf')):
                font_path = os.path.join(FONT_DIR, file)
                if test_font_arabic(font_path):
                    WORKING_FONT = _safe_font_path_for_imagemagick(font_path)
                    logging.info(f"✅ Working font selected (fallback): {file}")
                    return

    raise RuntimeError("No working Arabic font found! Please install Arabic fonts.")

# Initialize fonts at startup
init_font_system()

# =============================================================================
# STEP 6: UNIFIED ARABIC TEXT PROCESSING (NEW: single function)
# =============================================================================

import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFont

def process_arabic_text(text, words_per_line=4):
    """
    Unified Arabic text processing function.

    Args:
        text: Raw Arabic text (with or without tashkeel)
        words_per_line: Number of words per line for wrapping

    Returns:
        Tuple of (processed_text_for_display, num_lines, word_count)
    """
    if not text or not text.strip():
        return "", 0, 0

    # Step 1: Clean text
    cleaned = text.replace('\ufeff', '').replace('\u200b', '').strip()

    # Step 2: Apply Arabic reshaping to FULL text (preserves contextual forms)
    reshaped = arabic_reshaper.reshape(cleaned)

    # Step 3: Apply BiDi for RTL display
    visual = get_display(reshaped)

    # Step 4: Calculate word count and wrap
    words = visual.split()
    total_words = len(words)

    if total_words == 0:
        return visual, 1, 0

    # Wrap into lines
    lines = []
    for i in range(0, total_words, words_per_line):
        line_words = words[i:i + words_per_line]
        lines.append(' '.join(line_words))

    wrapped = '\n'.join(lines)

    logging.info(f"📊 Text processed: {total_words} words -> {len(lines)} lines")
    return wrapped, len(lines), total_words

# =============================================================================
# STEP 7: UNIFIED TEXT RENDERING (NEW: single function using WORKING_FONT)
# =============================================================================

def render_arabic_to_pil_image(text, fontsize=80, color='#FFFFFF',
                                stroke_color='#000000', stroke_width=2,
                                words_per_line=4, target_width=920):
    """
    Unified function to render Arabic text to PIL Image.
    Uses WORKING_FONT globally - no more font selection per call.

    Args:
        text: Raw Arabic text
        fontsize: Font size in pixels
        color: Text color (hex)
        stroke_color: Outline color (hex)
        stroke_width: Outline thickness
        words_per_line: Words per line
        target_width: Target image width

    Returns:
        PIL Image object (RGBA)
    """
    # Process Arabic text (reshape + bidi + wrap)
    processed_text, num_lines, word_count = process_arabic_text(text, words_per_line)

    if not processed_text:
        # Return empty image
        return Image.new('RGBA', (target_width, 100), (0, 0, 0, 0))

    # Load font (using global WORKING_FONT)
    font = ImageFont.truetype(WORKING_FONT, fontsize)

    # Parse colors
    def hex_to_rgba(hex_color):
        s = hex_color.strip().lstrip('#')
        if len(s) == 6:
            return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), 255)
        return (255, 255, 255, 255)

    fill_rgba = hex_to_rgba(color)
    stroke_rgba = hex_to_rgba(stroke_color)

    # Calculate image dimensions
    line_height = int(fontsize * 1.6)
    padding = 50
    img_height = max(300, num_lines * line_height + 2 * padding)
    img_width = target_width + 2 * padding

    # Create image
    img = Image.new('RGBA', (img_width, img_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw each line
    y = padding + line_height // 2
    x_center = img_width // 2

    for line in processed_text.split('\n'):
        if not line.strip():
            y += line_height
            continue

        # Draw stroke/outline
        if stroke_width > 0:
            for dx in range(-stroke_width, stroke_width + 1):
                for dy in range(-stroke_width, stroke_width + 1):
                    if dx != 0 or dy != 0:
                        draw.text((x_center + dx, y + dy), line,
                                 font=font, fill=stroke_rgba, anchor='mm')

        # Draw main text
        draw.text((x_center, y), line, font=font, fill=fill_rgba, anchor='mm')
        y += line_height

    logging.info(f"✅ Image rendered: {img_width}x{img_height}px, {num_lines} lines")
    return img

# =============================================================================
# STEP 8: CONSTANTS & CONFIGURATION
# =============================================================================

TARGET_W = 1080
TARGET_H = 1920
USE_FFMPEG_PIPELINE = True

QUALITY_PRESETS = {
    'low': {'fps': 24, 'codec': 'libx264', 'preset': 'ultrafast', 'bitrate': '4M'},
    'medium': {'fps': 30, 'codec': 'libx264', 'preset': 'fast', 'bitrate': '8M'},
    'high': {'fps': 30, 'codec': 'libx264', 'preset': 'fast', 'bitrate': '12M'}
}

OUTPUT_FORMATS = {
    'reels': {'size': (1080, 1920), 'duration': 30},
    'story': {'size': (1080, 1920), 'duration': 15},
    'post': {'size': (1080, 1080), 'duration': 60}
}

TEMPLATES = {
    'ramadan': {'bg_style': 'night', 'text_color': 'gold', 'font_size_mult': 1.2},
    'normal': {'bg_style': 'nature', 'text_color': 'white', 'font_size_mult': 1.0},
    'kids': {'bg_style': 'colorful', 'text_color': 'bright', 'font_size_mult': 1.3}
}

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
    111: 5, 112: 4, 113: 5, 114: 6
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
    'التكوير', 'الانفطار', 'المطففين', 'الانشقاق', 'البروج', 'الطارق', 'الأعلى', 'الغاشية', 'الفجر', 'البلد',
    'الشمس', 'الليل', 'الضحى', 'الشرح', 'التين', 'العلق', 'القدر', 'البينة', 'الزلزلة', 'العاديات',
    'القارعة', 'التكاثر', 'العصر', 'الهمزة', 'الفيل', 'قريش', 'الماعون', 'الكوثر', 'الكافرون', 'النصر',
    'المسد', 'الإخلاص', 'الفلق', 'الناس'
]

RECITERS_MAP = {
    'الشيخ عبدالباسط عبدالصمد': 'AbdulSamad_64kbps_QuranExplorer.Com',
    'الشيخ عبدالباسط عبدالصمد (مرتل)': 'Abdul_Basit_Murattal_64kbps',
    'الشيخ عبدالرحمن السديس': 'Abdurrahmaan_As-Sudais_64kbps',
    'الشيخ ماهر المعيقلي': 'Maher_AlMuaiqly_64kbps',
    'الشيخ محمد صديق المنشاوي (مجود)': 'Minshawy_Mujawwad_64kbps',
    'الشيخ سعود الشريم': 'Saood_ash-Shuraym_64kbps',
    'الشيخ مشاري العفاسي': 'Alafasy_64kbps',
    'الشيخ محمود خليل الحصري': 'Husary_64kbps',
    'الشيخ عبدالله الحذيفي': 'Hudhaify_64kbps',
    'الشيخ أبو بكر الشاطري': 'Abu_Bakr_Ash-Shaatree_128kbps',
    'الشيخ محمود علي البنا': 'mahmoud_ali_al_banna_32kbps'
}

# =============================================================================
# STEP 9: PYTHON 3.13 COMPATIBILITY (MUST BE BEFORE PYDUB IMPORT)
# =============================================================================

if sys.version_info >= (3, 13):
    try:
        import audioop
    except ImportError:
        # Apply patch before importing pydub
        import audioop_patch
        sys.modules['audioop'] = audioop_patch
        sys.modules['pyaudioop'] = audioop_patch
        logging.info("Applied Python 3.13 audioop compatibility patch")

# =============================================================================
# STEP 10: IMPORTS FOR VIDEO PROCESSING
# =============================================================================

import numpy as np
import requests as http_requests
from pydub import AudioSegment

if FFMPEG_EXE:
    logging.info(f"Using FFmpeg: {FFMPEG_EXE}")
    os.environ["FFMPEG_BINARY"] = FFMPEG_EXE
    os.environ["IMAGEIO_FFMPEG_EXE"] = FFMPEG_EXE
    AudioSegment.converter = FFMPEG_EXE
    AudioSegment.ffmpeg = FFMPEG_EXE
    AudioSegment.ffprobe = os.path.join(os.path.dirname(FFMPEG_EXE), "ffprobe.exe")
else:
    raise RuntimeError("FFmpeg not found - video processing requires FFmpeg")

from moviepy.editor import VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip, concatenate_videoclips
import moviepy.video.fx.all as vfx

# =============================================================================
# STEP 10: GLOBAL PROGRESS TRACKING & FLASK APP
# =============================================================================

current_progress = {
    'percent': 0,
    'status': 'جاري التحضير...',
    'log': [],
    'is_running': False,
    'is_complete': False,
    'output_path': None,
    'error': None
}

app = Flask(__name__, static_folder=EXEC_DIR)
CORS(app)

def reset_progress():
    global current_progress
    current_progress = {
        'percent': 0,
        'status': 'جاري التحضير...',
        'log': [],
        'is_running': False,
        'is_complete': False,
        'output_path': None,
        'error': None
    }

def add_log(message):
    current_progress['log'].append(message)
    logging.info(f"PROGRESS: {message}")

def update_progress(percent, status):
    current_progress['percent'] = percent
    current_progress['status'] = status
    logging.info(f"STATUS ({percent}%): {status}")

# =============================================================================
# STEP 11: UTILITY FUNCTIONS
# =============================================================================

def detect_leading_silence(sound, thresh, chunk=10):
    t = 0
    while t < len(sound) and sound[t:t + chunk].dBFS < thresh:
        t += chunk
    return t

def detect_trailing_silence(sound, thresh, chunk=10):
    return detect_leading_silence(sound.reverse(), thresh, chunk)

def get_audio_duration_ffprobe(audio_path):
    """Get audio duration using ffprobe"""
    ffprobe = os.path.join(os.path.dirname(FFMPEG_EXE), "ffprobe.exe")
    if not os.path.isfile(ffprobe):
        ffprobe = shutil.which("ffprobe") or FFMPEG_EXE

    cmd = [
        ffprobe, "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", audio_path
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=True)
    return float(out.stdout.strip())

# STEP 12: DATA FETCHING (SIMPLIFIED)
# =============================================================================

def download_audio(reciter_id, surah, ayah, idx):
    """Download audio for one ayah with multiple sources and retries"""
    fn = f'{surah:03d}{ayah:03d}.mp3'

    # Try multiple sources
    sources = [
        f'https://everyayah.com/data/{reciter_id}/{fn}',
        f'https://download.quranicaudio.com/quran/{reciter_id}/{fn}',
        f'https://www.everyayah.com/data/{reciter_id}/{fn}'
    ]

    out = os.path.join(TEMP_DIR, f'audio_{idx:03d}.mp3')

    for attempt, url in enumerate(sources, 1):
        try:
            logging.info(f"Downloading audio from source {attempt}: {url}")
            r = http_requests.get(url, timeout=15)  # Reduced timeout
            r.raise_for_status()

            with open(out, 'wb') as f:
                f.write(r.content)

            # Verify file has content
            if os.path.getsize(out) < 1000:
                raise ValueError(f"Audio file too small: {os.path.getsize(out)} bytes")

            # Trim silence
            snd = AudioSegment.from_file(out, 'mp3')
            start = detect_leading_silence(snd, snd.dBFS - 16)
            end = detect_trailing_silence(snd, snd.dBFS - 16)
            trimmed = snd[start:len(snd) - end]
            trimmed.export(out, format='mp3')

            logging.info(f"✅ Audio downloaded: {fn} ({os.path.getsize(out)} bytes)")
            return out

        except Exception as e:
            logging.warning(f"Source {attempt} failed: {e}")
            if attempt < len(sources):
                continue
            else:
                # All sources failed - create silent audio as fallback
                logging.error(f"All audio sources failed for {surah}:{ayah}, creating silent audio")
                silent = AudioSegment.silent(duration=3000)  # 3 seconds silent
                silent.export(out, format='mp3')
                return out

def get_ayah_text(surah, ayah):
    """Fetch ayah text from API with single retry"""
    try:
        resp = http_requests.get(
            f'https://api.alquran.cloud/v1/ayah/{surah}:{ayah}/quran-uthmani',
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        text = data['data']['text'].replace('\ufeff', '').replace('\u200b', '').strip()

        if not text or len(text) < 5:
            raise ValueError(f"Ayah text too short: {text}")

        return text
    except Exception as e:
        logging.warning(f"Text fetch failed, retrying once: {e}")
        # One retry
        resp = http_requests.get(
            f'https://api.alquran.cloud/v1/ayah/{surah}:{ayah}/quran-uthmani',
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        return data['data']['text'].replace('\ufeff', '').replace('\u200b', '').strip()

# =============================================================================
# STEP 13: BACKGROUND HANDLING (CACHED)
# =============================================================================

def pick_bg(style='nature', count=1):
    """Select background video(s)"""
    bg_patterns = {
        'nature': 'nature_part',
        'islamic': 'islamic_part',
        'masjid': 'masjid_part',
        'night': 'night_part',
        'colorful': 'colorful_part'
    }

    pattern = bg_patterns.get(style, 'nature_part')
    files = [f for f in os.listdir(VISION_DIR)
             if f.startswith(pattern) and f.endswith('.mp4')]

    if not files:
        files = [f for f in os.listdir(VISION_DIR)
                if f.startswith('nature_part') and f.endswith('.mp4')]

    if not files:
        raise ValueError("No background videos found")

    if count == 1:
        return os.path.join(VISION_DIR, random.choice(files))
    else:
        selected = random.sample(files, min(count, len(files)))
        return [os.path.join(VISION_DIR, f) for f in selected]

def get_preprocessed_bg(bg_path, target_w=TARGET_W, target_h=TARGET_H):
    """Get or create preprocessed background video (cached)"""
    os.makedirs(BG_CACHE_DIR, exist_ok=True)
    base = os.path.splitext(os.path.basename(bg_path))[0]
    cached_path = os.path.join(BG_CACHE_DIR, f"{base}_{target_w}x{target_h}.mp4")

    if os.path.isfile(cached_path):
        return cached_path

    vf = f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase,crop={target_w}:{target_h}"
    cmd = [
        FFMPEG_EXE, "-y", "-i", bg_path,
        "-vf", vf, "-an", "-c:v", "libx264",
        "-preset", "ultrafast", "-crf", "32",
        cached_path
    ]

    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return cached_path

# =============================================================================
# STEP 14: TEXT RENDERING TO PNG (NEW UNIFIED FUNCTION)
# =============================================================================

def render_text_to_png(arabic_text, template, output_png_path):
    """
    Render Arabic text to PNG using unified rendering system.
    Uses global WORKING_FONT - no font selection needed.
    """
    template_config = TEMPLATES.get(template, TEMPLATES['normal'])

    # Calculate font size based on word count
    word_count = len(arabic_text.split())
    size_mult = template_config['font_size_mult']

    if word_count > 60:
        fontsize, per_line = int(50 * size_mult), 7
    elif word_count > 40:
        fontsize, per_line = int(60 * size_mult), 6
    elif word_count > 25:
        fontsize, per_line = int(70 * size_mult), 5
    elif word_count > 15:
        fontsize, per_line = int(80 * size_mult), 4
    else:
        fontsize, per_line = int(95 * size_mult), 3

    # Determine color
    color = template_config['text_color']
    if color == 'gold':
        text_color = '#FFD700'
    elif color == 'bright':
        text_color = '#00FFFF'
    else:
        text_color = '#FFFFFF'

    # Render using unified function (uses WORKING_FONT)
    img = render_arabic_to_pil_image(
        text=arabic_text,
        fontsize=fontsize,
        color=text_color,
        stroke_color='#000000',
        stroke_width=2,
        words_per_line=per_line,
        target_width=TARGET_W - 160
    )

    # Save to PNG
    os.makedirs(os.path.dirname(output_png_path) or ".", exist_ok=True)
    img.save(output_png_path)
    logging.info(f"✅ Text rendered to PNG: {output_png_path}")
    return output_png_path

# =============================================================================
# =============================================================================

def build_segment_ffmpeg(bg_paths, text_png_path, audio_path, duration_sec, output_path):
    """Build one video segment with FFmpeg"""
    # Verify all input files exist and have content
    if not os.path.exists(text_png_path):
        raise FileNotFoundError(f"Text PNG missing: {text_png_path}")
    if os.path.getsize(text_png_path) < 100:
        raise ValueError(f"Text PNG too small: {os.path.getsize(text_png_path)} bytes")

    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio missing: {audio_path}")
    if os.path.getsize(audio_path) < 1000:
        raise ValueError(f"Audio too small: {os.path.getsize(audio_path)} bytes")

    # Preprocess backgrounds
    preprocessed = []
    for p in (bg_paths if isinstance(bg_paths, (list, tuple)) else [bg_paths]):
        if not os.path.exists(p):
            raise FileNotFoundError(f"Background missing: {p}")
        preprocessed.append(get_preprocessed_bg(p))

    n = len(preprocessed)
    part_dur = duration_sec / n

    logging.info(f"Building segment: {n} BGs, duration={duration_sec:.2f}s, part_dur={part_dur:.2f}s")
    logging.info(f"  Text PNG: {text_png_path} ({os.path.getsize(text_png_path)} bytes)")
    logging.info(f"  Audio: {audio_path} ({os.path.getsize(audio_path)} bytes)")

    # Build FFmpeg command
    common_args = ["-y", "-hide_banner", "-loglevel", "error"]  # Changed to error for more visibility
    inputs = []

    for p in preprocessed:
        inputs.extend(["-stream_loop", "-1", "-i", p])

    inputs.extend(["-loop", "1", "-i", text_png_path])
    inputs.extend(["-i", audio_path])

    if n == 1:
        filt = (f"[0:v]trim=duration={duration_sec},setpts=PTS-STARTPTS[bg];"
                f"[bg][1:v]overlay=(main_w-overlay_w)/2:(main_h-overlay_h)/2:format=auto[v]")
        map_args = ["-map", "[v]", "-map", "2:a"]
    else:
        v_parts = ""
        for i in range(n):
            v_parts += f"[{i}:v]trim=duration={part_dur},setpts=PTS-STARTPTS[v{i}];"
        v_parts += "".join([f"[v{i}]" for i in range(n)]) + f"concat=n={n}:v=1:a=0[bg];"
        filt = v_parts + f"[bg][{n}:v]overlay=(main_w-overlay_w)/2:(main_h-overlay_h)/2:format=auto[v]"
        map_args = ["-map", "[v]", "-map", f"{n+1}:a"]

    cmd = [FFMPEG_EXE] + common_args + inputs + [
        "-filter_complex", filt,
    ] + map_args + [
        "-t", str(duration_sec), "-r", "30",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-shortest",
        output_path
    ]

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=120)
    except subprocess.CalledProcessError as e:
        logging.error(f"FFmpeg failed with exit code {e.returncode}")
        logging.error(f"FFmpeg stderr: {e.stderr}")
        logging.error(f"FFmpeg stdout: {e.stdout}")
        raise RuntimeError(f"FFmpeg failed: {e.stderr}")

    if not os.path.exists(output_path):
        raise RuntimeError(f"FFmpeg output not created: {output_path}")

    logging.info(f"✅ Segment created: {output_path} ({os.path.getsize(output_path)} bytes)")
    return output_path

# =============================================================================
# STEP 16: PARALLEL PROCESSING (OPTIMIZED)
# =============================================================================

def process_single_ayah_ffmpeg(args):
    """
    Process one ayah using FFmpeg.
    Optimized: uses temp dir, single font, no resource monitoring.
    """
    reciter_id, surah, ayah, idx, template, bg_style = args

    try:
        # Download audio (with single retry built-in)
        audio_path = download_audio(reciter_id, surah, ayah, idx)
        duration = get_audio_duration_ffprobe(audio_path)
        logging.info(f"Segment {idx}: Audio duration = {duration:.2f}s")

        # Fetch text (with single retry built-in)
        arabic_text = get_ayah_text(surah, ayah)

        # Select SINGLE background (avoid concat issues)
        bg_path = pick_bg(bg_style, count=1)

        # Render text to PNG
        text_png = os.path.join(TEMP_DIR, f"text_{idx:03d}.png")
        segment_out = os.path.join(TEMP_DIR, f"segment_{idx:03d}.mp4")

        render_text_to_png(arabic_text, template, text_png)

        # Build segment
        build_segment_ffmpeg(bg_path, text_png, audio_path, duration, segment_out)

        logging.info(f"✅ Segment {idx} complete: ayah {surah}:{ayah}")
        return (ayah, segment_out)

    except Exception as e:
        logging.error(f"❌ Error processing ayah {surah}:{ayah}: {e}")
        raise

# =============================================================================
# STEP 17: MAIN VIDEO BUILDER
# =============================================================================

def build_video(reciter_id, surah, start_ayah, end_ayah=None,
                quality='medium', format_type='reels', template='normal',
                person_name='', target_duration_seconds=None):
    """
    Main video builder - optimized and refactored.
    No clear_outputs() needed - uses temp directory.
    """
    global current_progress

    try:
        current_progress['is_running'] = True
        current_progress['is_complete'] = False
        current_progress['error'] = None

        # Get config
        quality_config = QUALITY_PRESETS.get(quality, QUALITY_PRESETS['medium'])
        format_config = OUTPUT_FORMATS.get(format_type, OUTPUT_FORMATS['reels'])
        template_config = TEMPLATES.get(template, TEMPLATES['normal'])
        bg_style = template_config['bg_style']

        # Validation
        if surah not in VERSE_COUNTS:
            raise ValueError(f"Invalid surah: {surah}")
        max_ayah = VERSE_COUNTS[surah]
        start_ayah = max(1, min(start_ayah, max_ayah))

        if end_ayah is None:
            last_ayah = min(start_ayah + 9, max_ayah)
        else:
            last_ayah = min(end_ayah, max_ayah)

        if last_ayah < start_ayah:
            last_ayah = start_ayah

        # Duration cap
        max_duration = target_duration_seconds or format_config.get('duration', 30)
        max_ayahs = max(1, int(max_duration / 6))
        last_ayah = min(last_ayah, start_ayah + max_ayahs - 1)

        total = last_ayah - start_ayah + 1

        add_log(f'Building {total} ayat from {start_ayah} to {last_ayah}')
        update_progress(10, f'جاري تحضير {total} آيات...')

        # OPTIMIZED: max_workers = min(total, 3) - prevent overloading
        max_workers = min(total, 3)
        logging.info(f"Using {max_workers} workers (capped at 3)")

        # Prepare args
        ayah_args = [
            (reciter_id, surah, ayah, idx, template, bg_style)
            for idx, ayah in enumerate(range(start_ayah, last_ayah + 1), start=1)
        ]

        # Output filename - use ASCII to avoid FFmpeg issues
        surah_name = SURAH_NAMES[surah - 1] if 1 <= surah <= len(SURAH_NAMES) else f"Surah{surah}"
        clean_name = person_name.replace(" ", "_").replace("/", "_").replace("\\", "_") if person_name else "User"
        # Remove Arabic characters for temp filename
        ascii_name = f"{clean_name}_Surah{surah}_Ayah{start_ayah}-{last_ayah}_{quality}_{template}"
        temp_filename = f"{ascii_name}.mp4"
        temp_output_path = os.path.join(TEMP_DIR, temp_filename)

        # Final output with proper Arabic name
        filename = f"{clean_name}_{surah_name}_Ayah{start_ayah}-{last_ayah}_{quality}_{template}.mp4"
        output_path = os.path.join(VIDEO_DIR, filename)

        os.makedirs(VIDEO_DIR, exist_ok=True)

        # Process in parallel
        add_log('Processing ayat in parallel...')
        segment_results = []

        if max_workers > 1:
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(process_single_ayah_ffmpeg, a): a for a in ayah_args}
                for i, future in enumerate(concurrent.futures.as_completed(futures), 1):
                    ayah_num, seg_path = future.result()
                    segment_results.append((ayah_num, seg_path))
                    update_progress(int(10 + 70 * i / total), f'تم معالجة {i}/{total} آيات...')
        else:
            for i, args in enumerate(ayah_args, 1):
                ayah_num, seg_path = process_single_ayah_ffmpeg(args)
                segment_results.append((ayah_num, seg_path))
                update_progress(int(10 + 70 * i / total), f'تم معالجة {i}/{total} آيات...')

        # Sort by ayah number
        segment_results.sort(key=lambda x: x[0])

        # Concatenate
        add_log('Concatenating segments...')
        update_progress(85, 'جاري دمج المقاطع...')

        list_path = os.path.join(TEMP_DIR, "concat_list.txt")
        with open(list_path, "w", encoding="utf-8") as f:
            for _, seg_path in segment_results:
                f.write(f"file '{seg_path.replace(os.sep, '/')}'\n")

        cmd_concat = [
            FFMPEG_EXE, "-y", "-f", "concat", "-safe", "0", "-i", list_path,
            "-c:v", "libx264", "-preset", quality_config["preset"],
            "-b:v", quality_config.get("bitrate", "8M"),
            "-r", "30", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k"
        ]

        # Use temp ASCII path for FFmpeg
        cmd_concat.append(temp_output_path)
        subprocess.run(cmd_concat, check=True, capture_output=True, text=True, timeout=600)

        # Move to final location with Arabic name
        if os.path.exists(temp_output_path):
            shutil.move(temp_output_path, output_path)

        # Success
        add_log('Done!')
        update_progress(100, 'تم بنجاح!')
        current_progress['is_complete'] = True
        current_progress['output_path'] = output_path

        if os.path.isfile(output_path):
            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            logging.info(f"Output: {output_path} ({size_mb:.2f} MB)")

    except Exception as e:
        logging.exception("Error in build_video")
        current_progress['error'] = str(e)
        add_log(f'[ERROR] {str(e)}')
        update_progress(0, f'خطأ: {str(e)}')
    finally:
        current_progress['is_running'] = False

# =============================================================================
# STEP 18: API ROUTES (SIMPLIFIED)
# =============================================================================

@app.route('/')
def serve_ui():
    if os.path.exists(UI_PATH):
        return send_file(UI_PATH)
    return f"Error: UI.html not found at {UI_PATH}", 404

@app.route('/style.css')
def serve_css():
    return send_from_directory(BUNDLE_DIR, 'style.css')

@app.route('/main.js')
def serve_js():
    return send_from_directory(BUNDLE_DIR, 'main.js')

@app.route('/api/generate', methods=['POST'])
def generate_video():
    global current_progress

    if current_progress['is_running']:
        return jsonify({'error': 'عملية إنشاء فيديو قيد التنفيذ بالفعل'}), 400

    data = request.json
    reciter_id = data.get('reciter')
    surah = int(data.get('surah', 1))
    start_ayah = int(data.get('startAyah', 1))
    end_ayah = data.get('endAyah')
    if end_ayah is not None:
        end_ayah = int(end_ayah)

    quality = data.get('quality', 'medium')
    format_type = data.get('format', 'reels')
    template = data.get('template', 'normal')
    person_name = data.get('personName', '')
    target_duration_seconds = data.get('targetDurationSeconds')

    reset_progress()

    thread = threading.Thread(
        target=build_video,
        args=(reciter_id, surah, start_ayah, end_ayah, quality,
              format_type, template, person_name, target_duration_seconds),
        daemon=True
    )
    thread.start()

    return jsonify({'success': True, 'message': 'بدأ إنشاء الفيديو'})

@app.route('/api/progress', methods=['GET'])
def get_progress():
    return jsonify(current_progress)

@app.route('/api/config', methods=['GET'])
def get_config():
    return jsonify({
        'surahs': SURAH_NAMES,
        'verseCounts': VERSE_COUNTS,
        'reciters': RECITERS_MAP,
        'qualityPresets': list(QUALITY_PRESETS.keys()),
        'outputFormats': list(OUTPUT_FORMATS.keys()),
        'templates': list(TEMPLATES.keys()),
        'workingFont': os.path.basename(WORKING_FONT) if WORKING_FONT else None
    })

@app.route('/vision/<path:filename>')
def serve_vision(filename):
    return send_from_directory(VISION_DIR, filename)

@app.route('/outputs/<path:filename>')
def serve_output(filename):
    return send_from_directory(OUT_DIR, filename)

# =============================================================================
# STEP 19: MAIN ENTRY POINT
# =============================================================================

if __name__ == '__main__':
    logging.info('Server Starting...')
    print('=' * 50)
    print('  Quran Reels Generator (Refactored)')
    print('  Running in Portable Mode')
    print('=' * 50)

    # Create output directory
    os.makedirs(VIDEO_DIR, exist_ok=True)
    os.makedirs(BG_CACHE_DIR, exist_ok=True)

    webbrowser.open('http://127.0.0.1:5000')
    app.run(host='127.0.0.1', port=5000, debug=False, threaded=True)
