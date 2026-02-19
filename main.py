# Quran Reels Generator - Backend Server
# This script provides the video generation API for the HTML UI

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
import psutil
import concurrent.futures
import shelve
import hashlib
import re

from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS

# --- Step: Path Resolution Functions ---
def app_dir():
    """Returns the directory of the executable (or script) - Use for external files (fonts, outputs, logs)"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def bundled_dir():
    """Returns the bundled temp directory or script dir - Use for internal assets (bin, vision, UI)"""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

# --- Step: Define Base Directories ---
EXEC_DIR = app_dir()
BUNDLE_DIR = bundled_dir()

# --- Step: Setup Logging ---
log_path = os.path.join(EXEC_DIR, "runlog.txt")
logging.basicConfig(filename=log_path, level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s', force=True)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
logging.getLogger().addHandler(console_handler)

logging.info("--- Starting Quran Reels Generator ---")
logging.info(f"Execution Directory: {EXEC_DIR}")
logging.info(f"Bundled Directory: {BUNDLE_DIR}")

# --- Step: Define Paths and Find Binaries ---
def is_image_magick(path):
    """Verifies that the found 'magick' or 'convert' is actually ImageMagick."""
    if not path or not os.path.isfile(path):
        return False
    # Explicitly ignore Windows system convert.exe
    if "System32" in path and "convert.exe" in path.lower():
        return False
    try:
        import subprocess
        # Try both -version and --version as ImageMagick supports them
        res = subprocess.run([path, "-version"], capture_output=True, text=True, timeout=2)
        return "ImageMagick" in res.stdout or "ImageMagick" in res.stderr
    except:
        return False

def find_binary(portable_path, system_name):
    """Checks for portable binary first, then system PATH."""
    if os.path.isfile(portable_path):
        if system_name in ["magick", "convert"] and not is_image_magick(portable_path):
            pass # Continue to search if portable is invalid (unlikely)
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
if not IM_MAGICK_EXE: # Try older name
    IM_MAGICK_EXE = find_binary(os.path.join(BUNDLE_DIR, "bin", "imagemagick", "convert.exe"), "convert")

IM_HOME = os.path.join(BUNDLE_DIR, "bin", "imagemagick")

VISION_DIR = os.path.join(BUNDLE_DIR, "vision")
UI_PATH = os.path.join(BUNDLE_DIR, "UI.html")

OUT_DIR = os.path.join(EXEC_DIR, "outputs")
AUDIO_DIR = os.path.join(OUT_DIR, "audio")
VIDEO_DIR = os.path.join(OUT_DIR, "video")
BG_CACHE_DIR = os.path.join(OUT_DIR, "bg_cache")

FONT_DIR = os.path.join(EXEC_DIR, "fonts")

# Cache for fonts that have problematic filenames (non-ascii) or locations.
# ImageMagick on Windows can fail to load such font paths.
FONT_CACHE_DIR = os.path.join(FONT_DIR, "_cache")


def _is_ascii(s):
    try:
        s.encode("ascii")
        return True
    except Exception:
        return False


def _safe_font_path_for_imagemagick(font_path):
    """Return a font path that ImageMagick is more likely to read on Windows.

    If the font path contains non-ASCII characters, copy it to an ASCII-only
    cache filename under fonts/_cache and return the cached path.
    """
    try:
        if not font_path:
            return font_path

        # MoviePy/TextClip passes this path down to ImageMagick.
        # ImageMagick on Windows often fails for non-ascii paths.
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
            logging.info(f"Cached font for ImageMagick: '{os.path.basename(font_path)}' -> '{cached_name}'")

        # Ensure the file is not empty
        if os.path.getsize(cached_path) == 0:
            logging.error(f"Cached font file is empty! {cached_path}")
            return font_path

        return cached_path
    except Exception as e:
        logging.warning(f"Failed to create safe font cache path for '{font_path}': {e}")
        return font_path


def _normalize_font_request(font_name):
    if not font_name:
        return ""
    # Normalize whitespace and quotes (users can paste weird strings)
    font_name = str(font_name).strip().strip('"').strip("'")
    font_name = re.sub(r"\s+", " ", font_name)
    return font_name

# Auto-detect available fonts
def get_available_fonts():
    """Get all .ttf and .otf fonts from the fonts directory"""
    fonts = []
    if os.path.exists(FONT_DIR):
        for file in os.listdir(FONT_DIR):
            if file.lower().endswith(('.ttf', '.otf')):
                # Prioritize known good Arabic fonts
                if any(arabic_font in file.lower() for arabic_font in [
                    'amiri', 'tajawal', 'lateef', 'elmessiri', 'cairo', 'zain',
                    'dubai', 'scheherazade', 'reemkufi', 'sultan',
                    'ghalam', 'ka books', 'hj yad', 'babalrayhan', 'al-rifai',
                    'elgharib', 'alfont_com'
                ]):
                    fonts.insert(0, os.path.join(FONT_DIR, file))  # Add to front
                else:
                    fonts.append(os.path.join(FONT_DIR, file))

    # Fallback to default fonts if no fonts found
    if not fonts:
        FONT_PATH = os.path.join(FONT_DIR, "DUBAI-MEDIUM.TTF")
        FONT_PATH_ARABIC = os.path.join(FONT_DIR, "DUBAI-BOLD.TTF")
        FONT_PATH_ENGLISH = os.path.join(FONT_DIR, "DUBAI-REGULAR.TTF")
        return FONT_PATH, FONT_PATH_ARABIC, FONT_PATH_ENGLISH, fonts

    # Use first available font as primary, second as Arabic fallback
    FONT_PATH = fonts[0] if fonts else os.path.join(FONT_DIR, "DUBAI-MEDIUM.TTF")
    FONT_PATH_ARABIC = fonts[0] if len(fonts) > 0 else os.path.join(FONT_DIR, "DUBAI-BOLD.TTF")
    FONT_PATH_ENGLISH = fonts[1] if len(fonts) > 1 else fonts[0]

    logging.info(f"Found {len(fonts)} fonts in directory")
    for font in fonts:
        logging.info(f"  - {os.path.basename(font)}")
    logging.info(f"Using fonts: Primary={os.path.basename(FONT_PATH)}, Arabic={os.path.basename(FONT_PATH_ARABIC)}")
    return FONT_PATH, FONT_PATH_ARABIC, FONT_PATH_ENGLISH, fonts

def test_font_arabic_support(font_path):
    """Test if a font can properly render Arabic text"""
    try:
        from PIL import Image, ImageDraw, ImageFont
        import arabic_reshaper

        # Create a test image
        img = Image.new('RGB', (200, 50), color='white')
        draw = ImageDraw.Draw(img)

        # Try to load the font
        font = ImageFont.truetype(font_path, 20)

        # Test Arabic text
        test_text = "بسم الله"
        reshaped_text = arabic_reshaper.reshape(test_text)
        bidi_text = get_display(reshaped_text)

        # Try to draw text
        draw.text((10, 10), bidi_text, font=font, fill='black')

        return True
    except Exception as e:
        logging.warning(f"Font {os.path.basename(font_path)} failed Arabic test: {e}")
        return False

def get_specific_font(font_name):
    """Get a specific font by name - with better matching and clear confirmation"""
    try:
        font_name = _normalize_font_request(font_name)
        font_name_lower = font_name.lower()

        logging.info(f"🔤 USER REQUESTED FONT: '{font_name}'")

        if os.path.exists(FONT_DIR):
            fonts_in_dir = [f for f in os.listdir(FONT_DIR) if f.lower().endswith(('.ttf', '.otf'))]

            # Try exact match first
            for file in fonts_in_dir:
                if file == font_name or os.path.splitext(file)[0] == font_name:
                    font_path = os.path.join(FONT_DIR, file)
                    safe_path = _safe_font_path_for_imagemagick(font_path)
                    logging.info(f"✅ EXACT MATCH: Using font '{file}' -> {os.path.basename(safe_path)}")
                    return safe_path

            # Try case-insensitive match
            for file in fonts_in_dir:
                file_lower = file.lower()
                name_lower = os.path.splitext(file)[0].lower()
                if file_lower == font_name_lower or name_lower == font_name_lower:
                    font_path = os.path.join(FONT_DIR, file)
                    safe_path = _safe_font_path_for_imagemagick(font_path)
                    logging.info(f"✅ CASE-INSENSITIVE MATCH: Using font '{file}' -> {os.path.basename(safe_path)}")
                    return safe_path

            # Try partial match (user typed "Dubai" -> matches "DUBAI-BOLD.TTF")
            for file in fonts_in_dir:
                file_lower = file.lower()
                if font_name_lower in file_lower or font_name_lower.replace(' ', '') in file_lower:
                    font_path = os.path.join(FONT_DIR, file)
                    safe_path = _safe_font_path_for_imagemagick(font_path)
                    logging.info(f"✅ PARTIAL MATCH: '{font_name}' matched to '{file}' -> {os.path.basename(safe_path)}")
                    return safe_path

            # Log available fonts for debugging
            logging.warning(f"❌ Font '{font_name}' not found in directory")
            logging.info(f"📋 Available fonts: {fonts_in_dir[:10]}...")  # Show first 10

        # Fallback to random
        fallback = get_random_font()
        logging.warning(f"⚠️  FALLBACK: Using random font instead of '{font_name}'")
        return fallback

    except Exception as e:
        logging.error(f"Error selecting specific font: {e}")
        return get_random_font()

def get_random_font():
    """Get a random font from available fonts, prioritizing Arabic fonts"""
    try:
        fonts = []
        arabic_fonts = []
        if os.path.exists(FONT_DIR):
            for file in os.listdir(FONT_DIR):
                if file.lower().endswith(('.ttf', '.otf')):
                    font_path = os.path.join(FONT_DIR, file)
                    fonts.append(font_path)

                    # Identify Arabic fonts by name
                    if any(arabic_font in file.lower() for arabic_font in [
                        'dubai', 'lateef', 'scheherazade', 'reemkufi', 'sultan',
                        'ghalam', 'ka books', 'hj yad', 'babalrayhan', 'al-rifai',
                        'elgharib', 'alfont_com', 'omartype', 'qahiri', 'ranakufi'
                    ]):
                        arabic_fonts.append(font_path)

        # Prefer Arabic fonts, use all fonts if no Arabic fonts found
        font_pool = arabic_fonts if arabic_fonts else fonts

        # Try up to 5 times to find a working font
        for _ in range(min(5, len(font_pool))):
            selected_font = random.choice(font_pool)

            # Test the font (optional - can be disabled for performance)
            # if test_font_arabic_support(selected_font):
            safe_path = _safe_font_path_for_imagemagick(selected_font)
            logging.info(f"Randomly selected font: {os.path.basename(safe_path)}")
            return safe_path
            # else:
            #     font_pool.remove(selected_font)

        # If all tests failed, return first available font
        if fonts:
            safe_path = _safe_font_path_for_imagemagick(fonts[0])
            logging.info(f"Using first available font: {os.path.basename(safe_path)}")
            return safe_path
        else:
            # Fallback to default
            return _safe_font_path_for_imagemagick(os.path.join(FONT_DIR, "DUBAI-BOLD.TTF"))
    except Exception as e:
        logging.error(f"Error selecting random font: {e}")
        return _safe_font_path_for_imagemagick(os.path.join(FONT_DIR, "DUBAI-BOLD.TTF"))

def refresh_fonts():
    """Refresh font list - call this when new fonts are added"""
    global FONT_PATH, FONT_PATH_ARABIC, FONT_PATH_ENGLISH, AVAILABLE_FONTS
    FONT_PATH, FONT_PATH_ARABIC, FONT_PATH_ENGLISH, AVAILABLE_FONTS = get_available_fonts()
    logging.info("Font list refreshed successfully")
    return len(AVAILABLE_FONTS)

# Initialize font paths
FONT_PATH, FONT_PATH_ARABIC, FONT_PATH_ENGLISH, AVAILABLE_FONTS = get_available_fonts()

# Create folders on startup
try:
    os.makedirs(AUDIO_DIR, exist_ok=True)
    os.makedirs(VIDEO_DIR, exist_ok=True)
    os.makedirs(BG_CACHE_DIR, exist_ok=True)
    os.makedirs(FONT_DIR, exist_ok=True)
    logging.info("Output and Font directories verified.")
except Exception as e:
    logging.error(f"Failed to create directories: {e}")

# Validate Requirements and Configure Environment
if FFMPEG_EXE:
    logging.info(f"Using FFmpeg at: {FFMPEG_EXE}")
    os.environ["FFMPEG_BINARY"] = FFMPEG_EXE
    os.environ["IMAGEIO_FFMPEG_EXE"] = FFMPEG_EXE
else:
    logging.error("FFmpeg not found in portable bin or system PATH!")
    logging.error("Please download FFmpeg and place ffmpeg.exe in bin/ffmpeg/ folder")
    logging.error("Or install FFmpeg system-wide and add to PATH")
    raise RuntimeError("FFmpeg not found - video processing requires FFmpeg")

if IM_MAGICK_EXE:
    logging.info(f"Using ImageMagick at: {IM_MAGICK_EXE}")
    os.environ["IMAGEMAGICK_BINARY"] = IM_MAGICK_EXE
    os.environ["MAGICK_HOME"] = os.path.dirname(IM_MAGICK_EXE)

    # Prepend PATH for DLL discovery if portable
    if BUNDLE_DIR in IM_MAGICK_EXE:
        os.environ["PATH"] = os.pathsep.join([
            os.path.dirname(FFMPEG_EXE) if FFMPEG_EXE else "",
            os.path.dirname(IM_MAGICK_EXE),
            os.environ.get("PATH", "")
        ])
else:
    logging.warning("ImageMagick not found in portable bin or system PATH! Text creation will fail.")

if not os.path.isdir(VISION_DIR): logging.error(f"Missing vision folder at {VISION_DIR}")
if not os.path.isfile(UI_PATH): logging.error(f"Missing UI.html at {UI_PATH}")

logging.info("Environment configuration completed.")

# Python 3.13 compatibility patch for missing audioop module
if sys.version_info >= (3, 13):
    try:
        import audioop
    except ImportError:
        import audioop_patch
        sys.modules['audioop'] = audioop_patch
        sys.modules['pyaudioop'] = audioop_patch
        logging.info("Applied Python 3.13 audioop compatibility patch")

import numpy as np
import requests as http_requests
from pydub import AudioSegment
import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFont


TARGET_W = 1080
TARGET_H = 1920

# Professional pipeline: Pillow -> PNG, FFmpeg overlay + concat (no TextClip, no heavy MoviePy)
USE_FFMPEG_PIPELINE = True

# Quality presets - 1080x1920 Reels/Shorts: 30fps, high bitrate for social
num_cores = os.cpu_count() or 4
QUALITY_PRESETS = {
    'low': {'fps': 24, 'codec': 'libx264', 'preset': 'ultrafast', 'threads': num_cores, 'bitrate': '4M'},
    'medium': {'fps': 30, 'codec': 'libx264', 'preset': 'fast', 'threads': num_cores, 'bitrate': '8M'},
    'high': {'fps': 30, 'codec': 'libx264', 'preset': 'fast', 'threads': num_cores, 'bitrate': '12M'}
}

# Output formats
OUTPUT_FORMATS = {
    'reels': {'size': (1080, 1920), 'duration': 30},
    'story': {'size': (1080, 1920), 'duration': 15},
    'post': {'size': (1080, 1080), 'duration': 60}
}

# Visual templates
TEMPLATES = {
    'ramadan': {'bg_style': 'night', 'text_color': 'gold', 'font_size_mult': 1.2},
    'normal': {'bg_style': 'nature', 'text_color': 'white', 'font_size_mult': 1.0},
    'kids': {'bg_style': 'colorful', 'text_color': 'bright', 'font_size_mult': 1.3}
}

# Configure pydub with FFmpeg
if FFMPEG_EXE:
    AudioSegment.converter = FFMPEG_EXE
    AudioSegment.ffmpeg = FFMPEG_EXE
    AudioSegment.ffprobe = os.path.join(os.path.dirname(FFMPEG_EXE), "ffprobe.exe")
    if not os.path.isfile(AudioSegment.ffprobe):
        AudioSegment.ffprobe = shutil.which("ffprobe") or FFMPEG_EXE
    logging.info(f"Using FFmpeg for pydub: {FFMPEG_EXE}")
else:
    logging.warning("FFmpeg not found - audio processing may not work")

# Configure MoviePy with FFmpeg and ImageMagick
logging.info("Importing moviepy.editor...")
try:
    from moviepy.editor import VideoFileClip, AudioFileClip, TextClip, ImageClip, CompositeVideoClip, concatenate_videoclips
    import moviepy.video.fx.all as vfx
    logging.info("MoviePy imported successfully")
except Exception as e:
    logging.error(f"FATAL: MoviePy initialization failed: {e}")
    logging.error(traceback.format_exc())
    # We still need these to exist for the rest of the script to be valid syntax,
    # but we want them to fail with the REAL error.
    raise

# Verse counts for each Surah
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

# Surah names in Arabic
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

# Reciters mapping
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

# Global progress tracking
current_progress = {
    'percent': 0,
    'status': 'جاري التحضير...',
    'log': [],
    'is_running': False,
    'is_complete': False,
    'output_path': None,
    'error': None
}

# Flask App
app = Flask(__name__, static_folder=EXEC_DIR) # Not used directly due to custom route
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
    try:
        print(f'>>> {message}', flush=True)
    except OSError:
        pass

def update_progress(percent, status):
    current_progress['percent'] = percent
    current_progress['status'] = status
    logging.info(f"STATUS ({percent}%): {status}")

def clear_outputs():
    """Robustly clears the audio directory, ignoring locked files if necessary."""
    if not os.path.isdir(AUDIO_DIR):
        return

    logging.info(f"Clearing audio directory: {AUDIO_DIR}")
    for filename in os.listdir(AUDIO_DIR):
        file_path = os.path.join(AUDIO_DIR, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.remove(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path, ignore_errors=True)
        except Exception as e:
            # On Windows, Errno 22 or PermissionError often means the file is busy
            logging.warning(f"Skipping {filename} - likely in use: {e}")
            continue
    logging.info("Audio directory clear-up finished.")

def detect_leading_silence(sound, thresh, chunk=10):
    t = 0
    while t < len(sound) and sound[t:t + chunk].dBFS < thresh:
        t += chunk
    return t

def detect_trailing_silence(sound, thresh, chunk=10):
    return detect_leading_silence(sound.reverse(), thresh, chunk)

def download_audio(reciter_id, surah, ayah, idx):
    os.makedirs(AUDIO_DIR, exist_ok=True)
    fn = f'{surah:03d}{ayah:03d}.mp3'

    # Try multiple sources with timeout
    sources = [
        f'https://everyayah.com/data/{reciter_id}/{fn}',
        f'https://download.quranicaudio.com/quran/{reciter_id}/{fn}',
        f'https://www.everyayah.com/data/{reciter_id}/{fn}'
    ]

    out = os.path.join(AUDIO_DIR, f'part{idx}.mp3')

    for attempt, url in enumerate(sources, 1):
        try:
            logging.info(f"Trying source {attempt}: {url}")
            r = http_requests.get(url, timeout=30)  # Add timeout
            r.raise_for_status()
            with open(out, 'wb') as f:
                f.write(r.content)

            # Verify file has content
            if os.path.getsize(out) < 1000:
                raise ValueError(f"Audio file too small: {os.path.getsize(out)} bytes")

            logging.info(f"✅ Audio downloaded from source {attempt}: {fn}")
            break
        except Exception as e:
            logging.warning(f"Source {attempt} failed: {e}")
            if attempt == len(sources):
                raise RuntimeError(f"Failed to download audio for {surah}:{ayah} from all sources")

    # Trim silence
    snd = AudioSegment.from_file(out, 'mp3')
    start = detect_leading_silence(snd, snd.dBFS - 16)
    end = detect_trailing_silence(snd, snd.dBFS - 16)
    trimmed = snd[start:len(snd) - end]
    trimmed.export(out, format='mp3')
    return out

def get_ayah_text(surah, ayah):
    """Fetch complete ayah text from API with verification"""
    try:
        # Use quran-uthmani for complete Quranic text including tashkeel
        resp = http_requests.get(f'https://api.alquran.cloud/v1/ayah/{surah}:{ayah}/quran-uthmani')
        resp.raise_for_status()
        data = resp.json()

        # Extract text from response
        text = data['data']['text']

        # Remove BOM and normalize whitespace
        text = text.replace('\ufeff', '').replace('\u200b', '').strip()

        # Verify we got meaningful text
        if not text or len(text) < 5:
            logging.error(f"⚠️  Ayah {surah}:{ayah} returned too short text: '{text}'")
            raise ValueError(f"Ayah text too short: {text}")

        logging.info(f"✅ Fetched ayah {surah}:{ayah}: {len(text)} chars - '{text[:50]}...'")
        return text

    except Exception as e:
        logging.error(f"❌ Failed to fetch ayah {surah}:{ayah}: {e}")
        raise


def monitor_resources():
    cpu_percent = psutil.cpu_percent()
    memory_percent = psutil.virtual_memory().percent
    logging.info(f"System Resources - CPU: {cpu_percent}%, Memory: {memory_percent}%")
    return cpu_percent, memory_percent

def retry_on_failure(func, max_retries=3):
    for i in range(max_retries):
        try:
            return func()
        except Exception as e:
            if i == max_retries - 1:
                raise
            wait_time = 2 ** i
            logging.warning(f"Retry {i+1}/{max_retries} after {wait_time}s: {e}")
            time.sleep(wait_time)

def wrap_text(text, per_line):
    """Wrap text into multiple lines based on word count per line - PRESERVES ALL WORDS"""
    words = text.split()
    total_words = len(words)

    if total_words == 0:
        return text

    # Calculate number of lines needed
    num_lines = (total_words + per_line - 1) // per_line  # Ceiling division

    # Build lines ensuring ALL words are included
    lines = []
    for i in range(num_lines):
        start_idx = i * per_line
        end_idx = min(start_idx + per_line, total_words)
        line_words = words[start_idx:end_idx]
        lines.append(' '.join(line_words))

    result = '\n'.join(lines)

    # Verify all words are preserved
    result_word_count = len(result.replace('\n', ' ').split())
    if result_word_count != total_words:
        logging.error(f"⚠️  WORD LOSS DETECTED: {total_words} -> {result_word_count} words")
        # Fallback: return original text as single line
        return text

    logging.info(f"✅ Text wrapped: {total_words} words -> {len(lines)} lines ({per_line} words/line)")
    return result


def get_audio_duration_ffprobe(audio_path):
    """Get duration in seconds using ffprobe (no MoviePy)."""
    if not FFMPEG_EXE:
        raise RuntimeError("FFmpeg not available")
    ffprobe_exe = "ffprobe.exe" if os.name == "nt" else "ffprobe"
    ffprobe = os.path.join(os.path.dirname(FFMPEG_EXE), ffprobe_exe)
    if not os.path.isfile(ffprobe):
        ffprobe = shutil.which("ffprobe") or FFMPEG_EXE
    cmd = [
        ffprobe, "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", audio_path
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=True)
    return float(out.stdout.strip())


def _pil_color_to_rgba(color_str):
    """Convert hex color string to RGBA tuple for PIL."""
    s = color_str.strip()
    if s.startswith('#'):
        s = s[1:]
    if len(s) == 6:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), 255)
    return (255, 255, 255, 255)


def render_arabic_text_to_image(arabic_text, font_path, fontsize, color='white', stroke_color='black', stroke_width=2,
                                width=None, per_line=4):
    """
    Render Arabic text (UTF-8) to an RGBA image using PIL.
    CRITICAL: Forces working font to avoid square boxes.
    """
    if width is None:
        width = TARGET_W - 160

    # CRITICAL: Get complete original text
    original_text = str(arabic_text).replace('\ufeff', '').strip() if arabic_text else " "

    logging.info(f"🔤 INPUT TEXT: '{original_text}' ({len(original_text)} chars)")

    # FORCE a working Arabic font, but pick the *real* filename present in ./fonts (case-insensitive)
    forced_font = None
    try:
        candidates = []
        if os.path.isdir(FONT_DIR):
            candidates = [f for f in os.listdir(FONT_DIR) if f.lower().endswith(('.ttf', '.otf'))]

        def _pick_font(preferred_names):
            for pref in preferred_names:
                for f in candidates:
                    if f.lower() == pref.lower():
                        return os.path.join(FONT_DIR, f)
            return None

        # Prefer Dubai (as you have it): Dubai-Bold.ttf
        forced_font = _pick_font(["Dubai-Bold.ttf", "Dubai-Regular.ttf"]) or _pick_font(["DUBAI-BOLD.TTF", "DUBAI-REGULAR.TTF"])

        # If Dubai not found, prefer a known Arabic-capable font
        if not forced_font:
            forced_font = _pick_font(["Amiri-Bold.ttf", "Amiri-Regular.ttf", "Lateef-Bold.ttf", "Lateef-Medium.ttf", "Lateef-Light.ttf", "ElMessiri-Bold.ttf", "ElMessiri-Regular.ttf", "Tajawal-Bold.ttf", "Tajawal-Regular.ttf", "Zain-Bold.ttf", "Zain-Regular.ttf"])

        # Last resort: any font in folder
        if not forced_font and candidates:
            forced_font = os.path.join(FONT_DIR, candidates[0])

    except Exception as e:
        logging.error(f"❌ Font selection failed: {e}")
        forced_font = None

    try:
        if forced_font and os.path.exists(forced_font):
            font = ImageFont.truetype(forced_font, fontsize)
            logging.info(f"✅ USING FONT: {os.path.basename(forced_font)} at {fontsize}px")
        else:
            raise FileNotFoundError(f"No usable font found in {FONT_DIR}")
    except Exception as e:
        logging.error(f"❌ Font load failed: {e}, trying all Arabic fonts...")
        # CRITICAL: Never use default font for Arabic - it doesn't support Arabic glyphs!
        # Try every available Arabic font as fallback
        arabic_font_names = ["Dubai-Bold.ttf", "Dubai-Regular.ttf", "Amiri-Bold.ttf",
                             "Amiri-Regular.ttf", "Lateef-Bold.ttf", "Lateef-Medium.ttf",
                             "ElMessiri-Bold.ttf", "ElMessiri-Regular.ttf", "Tajawal-Bold.ttf",
                             "Tajawal-Regular.ttf", "Zain-Bold.ttf", "Zain-Regular.ttf"]
        font_loaded = False
        for fallback_font in arabic_font_names:
            fallback_path = os.path.join(FONT_DIR, fallback_font)
            if os.path.exists(fallback_path):
                try:
                    font = ImageFont.truetype(fallback_path, fontsize)
                    logging.info(f"✅ FALLBACK FONT LOADED: {fallback_font}")
                    font_loaded = True
                    break
                except Exception as e2:
                    logging.warning(f"⚠️ Fallback font {fallback_font} failed: {e2}")
                    continue

        if not font_loaded:
            # Last resort: try any .ttf file in fonts folder
            candidates = [f for f in os.listdir(FONT_DIR) if f.lower().endswith(('.ttf', '.otf'))]
            for any_font in candidates:
                try:
                    font = ImageFont.truetype(os.path.join(FONT_DIR, any_font), fontsize)
                    logging.info(f"✅ LAST RESORT FONT: {any_font}")
                    font_loaded = True
                    break
                except:
                    continue

        if not font_loaded:
            raise RuntimeError(f"CRITICAL: No Arabic font could be loaded from {FONT_DIR}. Please install Arabic fonts.")

    # Process text:
    # CRITICAL FIX: Apply reshape + bidi to FULL TEXT first, then wrap into lines.
    # This preserves tashkeel (diacritics) and contextual letter forms.
    try:
        # Step 1: Clean the text
        cleaned_text = original_text.replace('\ufeff', '').replace('\u200b', '').strip()

        # Step 2: Apply Arabic reshaping to the ENTIRE text (preserves contextual forms)
        reshaped_text = arabic_reshaper.reshape(cleaned_text)

        # Step 3: Apply BiDi algorithm to get correct visual order (RTL)
        visual_text = get_display(reshaped_text)

        logging.info(f"🔤 TEXT PROCESSING: Original='{cleaned_text[:50]}...'")
        logging.info(f"🔤 TEXT PROCESSING: Reshaped='{reshaped_text[:50]}...'")
        logging.info(f"🔤 TEXT PROCESSING: Visual='{visual_text[:50]}...'")

        # Step 4: Wrap into lines based on word count (working on visual text)
        words = visual_text.split()
        total_words = len(words)
        logging.info(f"� TOTAL WORDS: {total_words}, per_line={per_line}")

        visual_lines = []
        for i in range(0, total_words, per_line):
            line_words = words[i:i + per_line]
            # Join words back with spaces for each line
            line = ' '.join(line_words)
            visual_lines.append(line)
            logging.info(f"  📄 Line {len(visual_lines)}: '{line[:50]}...'")

        wrapped = '\n'.join(visual_lines) if visual_lines else visual_text

    except Exception as e:
        logging.error(f"❌ Text processing failed: {e}")
        # Fallback: use original text
        wrapped = original_text

    logging.info(f"📝 FINAL TEXT: '{wrapped[:100]}...' ({len(wrapped)} chars)")

    fill_rgba = _pil_color_to_rgba(color if isinstance(color, str) and color.startswith('#') else '#FFFFFF')
    stroke_rgba = _pil_color_to_rgba(stroke_color if isinstance(stroke_color, str) and stroke_color.startswith('#') else '#000000')

    lines = wrapped.split('\n')
    line_height = int(fontsize * 1.5)  # Increased spacing
    padding = 50  # More padding
    img_height = max(300, len(lines) * line_height + 2 * padding)
    img = Image.new('RGBA', (width + 2 * padding, img_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    y = padding + line_height // 2
    for line in lines:
        if not line.strip():
            y += line_height
            continue
        x_center = (width + 2 * padding) // 2

        # Draw stroke/outline first
        if stroke_width > 0:
            for dx in range(-stroke_width, stroke_width + 1):
                for dy in range(-stroke_width, stroke_width + 1):
                    if dx != 0 or dy != 0:
                        draw.text((x_center + dx, y + dy), line, font=font, fill=stroke_rgba, anchor='mm')

        # Draw main text
        draw.text((x_center, y), line, font=font, fill=fill_rgba, anchor='mm')
        y += line_height

    logging.info(f"✅ IMAGE RENDERED: {img.size[0]}x{img.size[1]}px, {len(lines)} lines")
    return np.array(img)


def render_arabic_to_png(arabic, template, selected_font, output_png_path):
    """
    Render Arabic text (UTF-8 + bidi + reshaper) to PNG with Pillow. Stable font, no ImageMagick.
    Saves to output_png_path (RGBA). For use with FFmpeg overlay.
    """
    template_config = TEMPLATES.get(template, TEMPLATES['normal'])
    words = arabic.split()
    word_count = len(words)
    size_mult = template_config['font_size_mult']
    if word_count > 60:
        fontsize = int(50 * size_mult)
        per_line = 7
    elif word_count > 40:
        fontsize = int(60 * size_mult)
        per_line = 6
    elif word_count > 25:
        fontsize = int(70 * size_mult)
        per_line = 5
    elif word_count > 15:
        fontsize = int(80 * size_mult)
        per_line = 4
    else:
        fontsize = int(95 * size_mult)
        per_line = 3
    color = template_config['text_color']
    text_color = '#FFD700' if color == 'gold' else ('#00FFFF' if color == 'bright' else 'white')
    if selected_font == 'random':
        font_path = get_random_font()
    else:
        font_path = get_specific_font(selected_font)

    # DEBUG: Confirm which font is being used
    logging.info(f"🎨 RENDER_ARABIC_TO_PNG: selected_font='{selected_font}' -> using font='{os.path.basename(font_path)}'")

    font_path = _safe_font_path_for_imagemagick(font_path)
    if not os.path.isabs(font_path):
        font_path = os.path.abspath(font_path)
    im_array = render_arabic_text_to_image(
        arabic, font_path, fontsize, color=text_color, stroke_color='black', stroke_width=2,
        width=TARGET_W - 160, per_line=per_line
    )
    os.makedirs(os.path.dirname(output_png_path) or ".", exist_ok=True)
    Image.fromarray(im_array).save(output_png_path)
    logging.info(f"Text rendered to PNG: {output_png_path}")
    return output_png_path


def build_segment_ffmpeg(bg_paths, text_png_path, audio_path, duration_sec, output_path, target_w=TARGET_W, target_h=TARGET_H):
    """
    Build one segment with FFmpeg only: BG (loop/concat) + overlay text PNG + audio.
    CRITICAL: Added file existence checks and better error handling.
    """
    if not FFMPEG_EXE:
        raise RuntimeError("FFmpeg not available")

    # CRITICAL: Check if text PNG exists
    if not os.path.exists(text_png_path):
        logging.error(f"❌ Text PNG not found: {text_png_path}")
        raise FileNotFoundError(f"Text PNG missing: {text_png_path}")

    logging.info(f"✅ Text PNG exists: {text_png_path} ({os.path.getsize(text_png_path)} bytes)")

    # Preprocess BG paths
    preprocessed = []
    for p in (bg_paths if isinstance(bg_paths, (list, tuple)) else [bg_paths]):
        preprocessed.append(get_preprocessed_bg(p, target_w=target_w, target_h=target_h))

    # Verify BG files exist
    for p in preprocessed:
        if not os.path.exists(p):
            logging.error(f"❌ BG video not found: {p}")
            raise FileNotFoundError(f"Background video missing: {p}")
        logging.info(f"✅ BG video exists: {p}")

    n = len(preprocessed)
    part_dur = duration_sec / n

    logging.info(f"📊 Building segment: {n} BG videos, duration={duration_sec}s, part_dur={part_dur}s")

    # Common FFmpeg options - use veryfast instead of ultrafast for stability
    common_args = ["-y", "-hide_banner", "-loglevel", "warning"]

    # Build Input list and Filter
    inputs = []
    for p in preprocessed:
        # Use -stream_loop to loop video backgrounds
        inputs.extend(["-stream_loop", "-1", "-i", p])

    # CRITICAL: -loop 1 for image input to keep it visible!
    inputs.extend(["-loop", "1", "-i", text_png_path])
    inputs.extend(["-i", audio_path])

    if n == 1:
        # One BG: Loop BG, Trim, Overlay text
        filt = f"[0:v]trim=duration={duration_sec},setpts=PTS-STARTPTS[bg];[bg][1:v]overlay=(main_w-overlay_w)/2:(main_h-overlay_h)/2:format=auto[v]"
        map_args = ["-map", "[v]", "-map", "2:a"]
    else:
        # Multiple BGs: Loop/Trim each, Concat, Overlay text
        v_parts = ""
        for i in range(n):
            v_parts += f"[{i}:v]trim=duration={part_dur},setpts=PTS-STARTPTS[v{i}];"
        v_parts += "".join([f"[v{i}]" for i in range(n)]) + f"concat=n={n}:v=1:a=0[bg];"
        filt = v_parts + f"[bg][{n}:v]overlay=(main_w-overlay_w)/2:(main_h-overlay_h)/2:format=auto[v]"
        map_args = ["-map", "[v]", "-map", f"{n+1}:a"]

    cmd = [FFMPEG_EXE] + common_args + inputs + [
        "-filter_complex", filt,
    ] + map_args + [
        "-t", str(duration_sec),
        "-r", "30",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",  # CRITICAL: Stop when shortest input ends
        output_path
    ]

    # Log the command for debugging
    cmd_str = ' '.join(f'"{arg}"' if ' ' in arg else arg for arg in cmd)
    logging.info(f"🎬 FFmpeg command: {cmd_str[:200]}...")

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300)
        logging.info(f"✅ FFmpeg segment created: {output_path}")
    except subprocess.CalledProcessError as e:
        logging.error(f"❌ FFmpeg error (exit {e.returncode}):")
        logging.error(f"   stderr: {e.stderr}")
        logging.error(f"   stdout: {e.stdout}")
        raise RuntimeError(f"FFmpeg failed with exit code {e.returncode}: {e.stderr}")
    except Exception as e:
        logging.error(f"❌ Unexpected FFmpeg error: {e}")
        raise

    # Verify output was created
    if not os.path.exists(output_path):
        raise RuntimeError(f"FFmpeg output not created: {output_path}")

    return output_path


def create_text_clip_pil(arabic, translation="", duration=5, template='normal', video_height=1080, selected_font='random'):
    """
    Create text clip using PIL-rendered image (no ImageMagick). Guarantees font on Windows.
    """
    template_config = TEMPLATES.get(template, TEMPLATES['normal'])
    words = arabic.split()
    word_count = len(words)
    size_mult = template_config['font_size_mult']
    if word_count > 60:
        fontsize = int(50 * size_mult)
        per_line = 7
    elif word_count > 40:
        fontsize = int(60 * size_mult)
        per_line = 6
    elif word_count > 25:
        fontsize = int(70 * size_mult)
        per_line = 5
    elif word_count > 15:
        fontsize = int(80 * size_mult)
        per_line = 4
    else:
        fontsize = int(95 * size_mult)
        per_line = 3

    color = template_config['text_color']
    if color == 'gold':
        text_color = '#FFD700'
    elif color == 'bright':
        text_color = '#00FFFF'
    else:
        text_color = 'white'

    if selected_font == 'random':
        font_path = get_random_font()
    else:
        font_path = get_specific_font(selected_font)
    font_path = _safe_font_path_for_imagemagick(font_path)
    if not os.path.isabs(font_path):
        font_path = os.path.abspath(font_path)

    try:
        im_array = render_arabic_text_to_image(
            arabic, font_path, fontsize, color=text_color, stroke_color='black', stroke_width=2,
            width=TARGET_W - 160, per_line=per_line
        )
        ar_clip = ImageClip(im_array).set_duration(duration).set_position('center')
        ar_clip = ar_clip.fadein(0.3).fadeout(0.3)
        logging.info(f"✅ PIL text clip created successfully: {im_array.shape[1]}x{im_array.shape[0]}, font={os.path.basename(font_path)}")
        return ar_clip
    except Exception as e:
        logging.exception(f"❌ PIL text clip failed with font {font_path}: {e}")
        raise


def create_text_clip(arabic, translation="", duration=5, template='normal', video_height=1080, selected_font='random'):
    """
    Create enhanced text clip with Arabic and optional English translation.
    Includes professional visual effects and template support.
    """
    template_config = TEMPLATES.get(template, TEMPLATES['normal'])
    words = arabic.split()
    word_count = len(words)

    # Dynamic settings based on text length and template - Optimized for readability
    size_mult = template_config['font_size_mult']
    if word_count > 60:
        fontsize = int(50 * size_mult)
        per_line = 7
    elif word_count > 40:
        fontsize = int(60 * size_mult)
        per_line = 6
    elif word_count > 25:
        fontsize = int(70 * size_mult)
        per_line = 5
    elif word_count > 15:
        fontsize = int(80 * size_mult)
        per_line = 4
    else:
        fontsize = int(95 * size_mult)
        per_line = 3

    # Reshape Arabic text and handle BiDi for correct rendering in MoviePy
    try:
        if not arabic or not arabic.strip():
            logging.warning("Arabic text is empty, using placeholder")
            arabic = " "

        # Remove any lingering BOM or control chars
        arabic = arabic.replace('\ufeff', '').strip()

        # Reshape Arabic text and handle BiDi for correct rendering in MoviePy
        reshaped_text = arabic_reshaper.reshape(arabic)
        bidi_text = get_display(reshaped_text)

        # Wrap corrected text
        wrapped_arabic = wrap_text(bidi_text, per_line)
        logging.info(f"Text processing: Original='{arabic[:30]}...' Reshaped='{reshaped_text[:30]}...' BIDI='{bidi_text[:30]}...'")

    except Exception as e:
        logging.error(f"Arabic text processing failed: {e}")
        wrapped_arabic = arabic



    # Create Arabic text with enhanced styling
    color = template_config['text_color']
    if color == 'gold':
        text_color = '#FFD700'
    elif color == 'bright':
        text_color = '#00FFFF'
    else:
        text_color = 'white'

    # Use selected font or random font
    if selected_font == 'random':
        requested_font_path = get_random_font()
    else:
        requested_font_path = get_specific_font(selected_font)

    # Always go through the safe-path helper (handles non-ascii filenames)
    requested_font_path = _safe_font_path_for_imagemagick(requested_font_path)

    # Ensure absolute path with normalized separators for ImageMagick
    requested_font_path = os.path.abspath(requested_font_path).replace("\\", "/")

    # Try creating text clip with fallbacks (fonts can be invalid or unreadable by ImageMagick)
    # We use a mix of the requested font and very safe defaults.
    fallback_fonts = [
        requested_font_path,
        # Fallback 1: Random font from the directory (might also be problematic, so we wrap it)
        os.path.abspath(_safe_font_path_for_imagemagick(get_random_font())).replace("\\", "/"),
        # Fallback 2: Known safe font (Dubai-Bold or similar if it exists)
        os.path.abspath(_safe_font_path_for_imagemagick(os.path.join(FONT_DIR, "DUBAI-BOLD.TTF"))).replace("\\", "/"),
        # Fallback 3: ImageMagick default (empty font string often uses a system font)
        "Arial"
    ]

    last_error = None
    ar_clip = None
    for i, font_path in enumerate(fallback_fonts):
        try:
            logging.info(f"[{i+1}/4] Rendering Text (Fast Mode): {font_path}")

            # Single TextClip with better stroke to avoid the overhead of heavy shadows
            ar_clip = TextClip(
                wrapped_arabic,
                font=font_path,
                fontsize=fontsize,
                color=text_color,
                stroke_color='black',
                stroke_width=2.0, # Thicker stroke instead of shadow for 2x speedup
                method='caption',
                size=(TARGET_W - 160, None),
                align='center',
            ).set_duration(duration).set_position('center')

            if ar_clip.w == 0 or ar_clip.h == 0:
                logging.warning(f"Created clip size is 0x0 with font {font_path}")
                continue

            logging.info(f"TextClip created! Size: {ar_clip.w}x{ar_clip.h}")
            last_error = None
            break


        except Exception as e:
            last_error = e
            logging.warning(f"TextClip failed with font '{font_path}': {e}")
            continue

    if ar_clip is None:
        # Final emergency fallback: use a very simple TextClip
        try:
            logging.error("CRITICAL: All fonts failed, using emergency system font")
            ar_clip = TextClip(
                wrapped_arabic,
                fontsize=fontsize,
                color='white',
                method='caption',
                size=(TARGET_W - 160, None),
                align='center'
            ).set_duration(duration).set_position('center')
        except:
            raise Exception(f"All font attempts failed. Last error: {last_error}")


    # Add professional fade effects
    ar_clip = ar_clip.fadein(0.3).fadeout(0.3)

    return ar_clip


def pick_bg(style='nature', count=1):
    try:
        # Support multiple background styles
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
            logging.warning(f"No {style} backgrounds found, falling back to nature")
            files = [f for f in os.listdir(VISION_DIR)
                    if f.startswith('nature_part') and f.endswith('.mp4')]

        if not files:
            logging.error("No background videos found in vision folder!")
            raise ValueError("No background videos found.")

        if count == 1:
            selected = random.choice(files)
            logging.info(f"Selected background: {selected}")
            return os.path.join(VISION_DIR, selected)
        else:
            # Pick multiple unique BGs if possible
            selected_files = random.sample(files, min(count, len(files)))
            logging.info(f"Selected {len(selected_files)} background(s) for mashup: {selected_files}")
            return [os.path.join(VISION_DIR, f) for f in selected_files]
    except Exception as e:

        logging.error(f"Error picking background: {e}")
        raise

def get_preprocessed_bg(bg_path, target_w=TARGET_W, target_h=TARGET_H):
    if not FFMPEG_EXE:
        return bg_path

    os.makedirs(BG_CACHE_DIR, exist_ok=True)
    base = os.path.splitext(os.path.basename(bg_path))[0]
    cached_path = os.path.join(BG_CACHE_DIR, f"{base}_{target_w}x{target_h}.mp4")
    if os.path.isfile(cached_path):
        return cached_path

    vf = f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase,crop={target_w}:{target_h}"
    cmd = [
        FFMPEG_EXE,
        "-y",
        "-i", bg_path,
        "-vf", vf,
        "-an",
        "-c:v", "libx264",
        "-preset", "ultrafast", # Max speed for preprocessing
        "-crf", "32"            # Lower quality for BG is fine
    ]

    # Only add movflags on non-Windows systems to avoid path issues
    if os.name != 'nt':  # Not Windows
        cmd.extend(["-movflags", "+faststart"])

    cmd.append(cached_path)
    logging.info(f"Preprocessing BG via FFmpeg -> {cached_path}")
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return cached_path

def process_single_ayah(args):
    """Process a single ayah for parallel processing"""
    reciter_id, surah, ayah, idx, template, bg_style, selected_font = args

    try:
        # Monitor resources
        cpu, mem = monitor_resources()
        if mem > 85:
            logging.warning(f"High memory usage: {mem}%, consider reducing quality")

        # Download audio with retry
        def download():
            return download_audio(reciter_id, surah, ayah, idx)

        ap = retry_on_failure(download)

        # Fetch Arabic text with retry
        def fetch_text():
            return get_ayah_text(surah, ayah)

        ar = retry_on_failure(fetch_text)

        # Process audio
        audio = AudioFileClip(ap)
        dur = audio.duration
        audio = audio.audio_fadein(0.2).audio_fadeout(0.2)

        # Create background (Mashup 2 videos per ayah for variety)
        bg_paths = pick_bg(bg_style, count=2)
        seg_bg = prepare_bg_clip(bg_paths, dur)

        # Create text with template (Arabic only) - PIL path guarantees font on Windows
        ar_clip = create_text_clip_pil(ar, "", dur, template, TARGET_H, selected_font)


        # Composite with fade in/out for smooth transitions
        seg = CompositeVideoClip([seg_bg, ar_clip], size=(TARGET_W, TARGET_H)).set_audio(audio)
        seg = seg.crossfadein(0.5).crossfadeout(0.5)

        # CRITICAL: Store ayah number for proper sorting
        seg.ayah_number = ayah

        logging.info(f"Completed ayah {surah}:{ayah} (segment #{idx})")
        return seg

    except Exception as e:
        logging.error(f"Error processing ayah {surah}:{ayah}: {e}")
        raise


def process_single_ayah_ffmpeg(args):
    """
    Process one ayah using FFmpeg only: Pillow -> PNG, FFmpeg overlay + audio.
    Returns (ayah_number, segment_path). No MoviePy clip; low CPU, stable fonts.
    """
    reciter_id, surah, ayah, idx, template, bg_style, selected_font = args
    try:
        logging.info(f"🎬 Starting FFmpeg pipeline for ayah {surah}:{ayah} (idx={idx})")

        def download():
            return download_audio(reciter_id, surah, ayah, idx)
        ap = retry_on_failure(download)
        logging.info(f"✅ Audio downloaded: {ap}")

        dur = get_audio_duration_ffprobe(ap)
        logging.info(f"📊 Audio duration: {dur}s")

        ar = retry_on_failure(lambda: get_ayah_text(surah, ayah))
        logging.info(f"✅ Ayah text fetched: {ar[:50]}...")

        bg_paths = pick_bg(bg_style, count=2)
        logging.info(f"✅ Backgrounds selected: {bg_paths}")

        os.makedirs(AUDIO_DIR, exist_ok=True)
        text_png = os.path.join(AUDIO_DIR, f"text_{idx:03d}.png")
        segment_out = os.path.join(AUDIO_DIR, f"segment_{idx:03d}.mp4")

        # CRITICAL: Create text PNG and verify it exists
        logging.info(f"🎨 Rendering text PNG: {text_png}")
        render_arabic_to_png(ar, template, selected_font, text_png)

        # Verify PNG was created and has content
        if not os.path.exists(text_png):
            raise RuntimeError(f"Text PNG not created: {text_png}")

        png_size = os.path.getsize(text_png)
        if png_size < 1000:
            raise RuntimeError(f"Text PNG too small ({png_size} bytes), likely empty")

        logging.info(f"✅ Text PNG created: {text_png} ({png_size} bytes)")

        # Now build the video segment
        logging.info(f"🎬 Building segment: {segment_out}")
        build_segment_ffmpeg(bg_paths, text_png, ap, dur, segment_out)

        logging.info(f"✅ FFmpeg segment done ayah {surah}:{ayah} -> {segment_out}")
        return (ayah, segment_out)
    except Exception as e:
        logging.error(f"❌ Error processing ayah {surah}:{ayah} (FFmpeg): {e}")
        raise


def prepare_bg_clip(path_or_paths, duration, target_w=TARGET_W, target_h=TARGET_H):
    """
    Prepares a background clip. If a list of paths is provided, merges them with transitions (Mashup).
    """
    if isinstance(path_or_paths, list) and len(path_or_paths) > 1:
        # Mashup Background Mode: equal part durations, no negative padding (sync-safe)
        bg_clips = []
        part_dur = duration / len(path_or_paths)

        for path in path_or_paths:
            path = get_preprocessed_bg(path, target_w=target_w, target_h=target_h)
            clip = VideoFileClip(path, audio=False).set_duration(part_dur)
            clip = clip.fx(vfx.loop, duration=part_dur)
            bg_clips.append(clip)

        bg = concatenate_videoclips(bg_clips, method='compose', padding=0)
        bg = bg.subclip(0, duration)
    else:
        # Single Background Mode
        path = path_or_paths[0] if isinstance(path_or_paths, list) else path_or_paths
        path = get_preprocessed_bg(path, target_w=target_w, target_h=target_h)
        bg = VideoFileClip(path, audio=False)
        bg = bg.fx(vfx.loop, duration=duration).subclip(0, duration)

    if bg.h != target_h:
        bg = bg.resize(height=target_h)

    if bg.w < target_w:
        bg = bg.resize(width=target_w)

    bg = bg.crop(x_center=bg.w / 2, y_center=bg.h / 2, width=target_w, height=target_h)
    return bg

def build_video(reciter_id, surah, start_ayah, end_ayah=None, quality='medium', format_type='reels', template='normal', person_name='', selected_font='random', target_duration_seconds=None):
    """
    Enhanced video builder with quality presets, templates, and parallel processing.
    target_duration_seconds: optional cap (e.g. 15-30) to limit total video length by ayah count.
    """
    global current_progress
    clips = []
    final = None
    try:
        current_progress['is_running'] = True
        current_progress['is_complete'] = False
        current_progress['error'] = None

        # Get configurations
        quality_config = QUALITY_PRESETS.get(quality, QUALITY_PRESETS['medium'])
        format_config = OUTPUT_FORMATS.get(format_type, OUTPUT_FORMATS['reels'])
        template_config = TEMPLATES.get(template, TEMPLATES['normal'])
        bg_style = template_config['bg_style']

        # Validation
        if surah not in VERSE_COUNTS:
            raise ValueError(f"Invalid surah: {surah}")
        max_ayah = VERSE_COUNTS[surah]
        if start_ayah < 1 or start_ayah > max_ayah:
            raise ValueError(f"start_ayah {start_ayah} out of range for surah {surah} (1-{max_ayah})")
        if not reciter_id or not str(reciter_id).strip():
            raise ValueError("reciter_id is required")
        try:
            pick_bg(bg_style, count=1)
        except Exception as e:
            raise ValueError(f"No background videos found for style '{bg_style}'. Check vision folder.") from e

        logging.info(f"build_video: surah={surah} ayahs={start_ayah}-(end) quality={quality} format={format_type} template={template}")

        add_log('[1] Clearing output folders...')
        update_progress(5, 'جاري تنظيف ملفات الإخراج...')
        clear_outputs()
        if end_ayah is None:
            last_ayah = min(start_ayah + 9, max_ayah)
        else:
            last_ayah = min(end_ayah, max_ayah)

        if last_ayah < start_ayah:
            last_ayah = start_ayah

        # Cap ayah count by format max duration or optional target (e.g. ~6s per ayah -> 30s = 5 ayahs)
        max_duration = target_duration_seconds if target_duration_seconds is not None else (format_config.get('duration') or 30)
        avg_ayah_seconds = 6
        max_ayahs_by_duration = max(1, int(max_duration / avg_ayah_seconds))
        last_ayah = min(last_ayah, start_ayah + max_ayahs_by_duration - 1)
        logging.info(f"Format {format_type} target max duration: {max_duration}s, ayah range capped for ~{max_duration}s")

        total = last_ayah - start_ayah + 1

        add_log(f'[2] Preparing {total} آيات (from {start_ayah} to {last_ayah}) with {quality} quality')
        update_progress(10, f'جاري تحضير {total} آيات بجودة {quality}...')

        # Limit workers to avoid CPU thrashing and crashes (leave headroom for system)
        cpu, mem = monitor_resources()
        num_cores = os.cpu_count() or 4
        if mem > 85:
            max_workers = 1
        else:
            max_workers = min(total, max(2, num_cores - 1))
        logging.info(f"Using {max_workers} workers (capped to prevent thrashing)")


        # Prepare arguments for parallel processing
        ayah_args = [(reciter_id, surah, ayah, idx, template, bg_style, selected_font)
                     for idx, ayah in enumerate(range(start_ayah, last_ayah + 1), start=1)]

        surah_name = SURAH_NAMES[surah - 1] if 1 <= surah <= len(SURAH_NAMES) else f"Surah{surah}"
        clean_person_name = person_name.replace(" ", "_").replace("/", "_").replace("\\", "_") if person_name else "User"
        filename = f"{clean_person_name}_{surah_name}_Ayah{start_ayah}-{last_ayah}_{quality}_{template}.mp4"
        out = os.path.join(VIDEO_DIR, filename)
        bitrate = quality_config.get('bitrate', '8M')

        if USE_FFMPEG_PIPELINE:
            # Professional path: Pillow -> PNG, FFmpeg overlay + concat (no TextClip, no heavy MoviePy)
            add_log('[2] Building segments with FFmpeg (Pillow + overlay)...')
            segment_results = []
            if max_workers > 1:
                with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                    future_to_args = {executor.submit(process_single_ayah_ffmpeg, a): a for a in ayah_args}
                    for i, future in enumerate(concurrent.futures.as_completed(future_to_args), 1):
                        ayah_num, seg_path = future.result()
                        segment_results.append((ayah_num, seg_path))
                        update_progress(int(10 + 70 * i / total), f'تم معالجة {i}/{total} آيات...')
            else:
                for i, args in enumerate(ayah_args, 1):
                    ayah_num, seg_path = process_single_ayah_ffmpeg(args)
                    segment_results.append((ayah_num, seg_path))
                    update_progress(int(10 + 70 * i / total), f'تم معالجة الآية {i}/{total}...')
            segment_results.sort(key=lambda x: x[0])
            add_log('[4] Concatenating with FFmpeg...')
            update_progress(85, 'جاري دمج المقاطع...')
            list_path = os.path.join(AUDIO_DIR, "concat_list.txt")
            with open(list_path, "w", encoding="utf-8") as f:
                for _, seg_path in segment_results:
                    f.write(f"file '{seg_path.replace(os.sep, '/')}'\n")
            cmd_concat = [
                FFMPEG_EXE, "-y", "-f", "concat", "-safe", "0", "-i", list_path,
                "-c:v", "libx264", "-preset", quality_config["preset"], "-b:v", bitrate,
                "-r", "30", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k"
            ]
            if os.name != "nt":
                cmd_concat.extend(["-movflags", "+faststart"])
            cmd_concat.append(out)
            subprocess.run(cmd_concat, check=True, capture_output=True, text=True, timeout=600)
            add_log('[6] Done!')
            update_progress(100, 'تم بنجاح!')
            current_progress['is_complete'] = True
            current_progress['output_path'] = out
            if os.path.isfile(out):
                size_mb = os.path.getsize(out) / (1024 * 1024)
                logging.info(f"Output written (FFmpeg): {out} ({size_mb:.2f} MB)")
        else:
            # MoviePy path (fallback)
            if max_workers > 1:
                with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                    future_to_ayah = {executor.submit(process_single_ayah, args): args for args in ayah_args}
                    for i, future in enumerate(concurrent.futures.as_completed(future_to_ayah), 1):
                        clip = future.result()
                        clips.append(clip)
                        update_progress(int(10 + 70 * i / total), f'تم معالجة {i}/{total} آيات...')
            else:
                for idx, args in enumerate(ayah_args, 1):
                    clip = process_single_ayah(args)
                    clips.append(clip)
                    update_progress(int(10 + 70 * (idx) / total), f'تم معالجة الآية {idx}/{total}...')
            add_log('[4] Concatenating segments with transitions...')
            update_progress(85, 'جاري دمج المقاطع مع الانتقالات...')
            clips.sort(key=lambda c: getattr(c, 'ayah_number', 0))
            final = concatenate_videoclips(clips, method='compose', padding=0)
            add_log(f'[5] Writing final video -> {out}')
            update_progress(90, 'جاري كتابة الفيديو النهائي...')
            total_dur = final.duration
            logging.info(f"Final clip duration: {total_dur:.1f}s, writing to {out}")
            ffmpeg_params = ['-pix_fmt', 'yuv420p']
            if os.name != 'nt':
                ffmpeg_params.extend(['-movflags', '+faststart'])
            threads_ff = quality_config.get('threads', num_cores)
            final.write_videofile(
                out, fps=quality_config['fps'], codec=quality_config['codec'],
                audio_codec='aac', audio_bitrate='192k', bitrate=bitrate,
                verbose=False, preset=quality_config['preset'], threads=threads_ff,
                ffmpeg_params=ffmpeg_params, write_logfile=False
            )
            add_log('[6] Done!')
            update_progress(100, 'تم بنجاح!')
            current_progress['is_complete'] = True
            current_progress['output_path'] = out
            if os.path.isfile(out):
                size_mb = os.path.getsize(out) / (1024 * 1024)
                logging.info(f"Output written: {out} ({size_mb:.2f} MB)")

    except Exception as e:
        logging.exception("Error in build_video")
        current_progress['error'] = str(e)
        add_log(f'[ERROR] {str(e)}')
        update_progress(0, f'خطأ: {str(e)}')
    finally:
        # CRITICAL: Close all clip resources to release file locks on Windows
        logging.info("Cleaning up video resources...")
        if final:
            try:
                final.close()
            except:
                pass
        for c in clips:
            try:
                c.close()
            except:
                pass
        current_progress['is_running'] = False

# API Routes
@app.route('/')
def serve_ui():
    # Use robust path for UI.html
    if os.path.exists(UI_PATH):
        return send_file(UI_PATH)
    else:
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

    # Enhanced parameters
    quality = data.get('quality', 'medium')
    format_type = data.get('format', 'reels')
    template = data.get('template', 'normal')
    person_name = data.get('personName', '')  # New parameter for person's name
    selected_font = data.get('selectedFont', 'random')  # New parameter for selected font
    target_duration_seconds = data.get('targetDurationSeconds')  # Optional: cap total duration (e.g. 15-30)

    reset_progress()

    # Start video generation in background thread with enhanced parameters
    thread = threading.Thread(
        target=build_video,
        args=(reciter_id, surah, start_ayah, end_ayah, quality, format_type, template, person_name, selected_font, target_duration_seconds),
        daemon=True
    )
    thread.start()

    return jsonify({'success': True, 'message': 'بدأ إنشاء الفيديو'})

@app.route('/api/progress', methods=['GET'])
def get_progress():
    return jsonify(current_progress)

@app.route('/api/refresh-fonts', methods=['POST'])
def refresh_fonts_api():
    """Refresh font list - call this when new fonts are added"""
    try:
        font_count = refresh_fonts()
        return jsonify({
            'success': True,
            'message': f'Font list refreshed successfully',
            'fontCount': font_count,
            'fonts': [os.path.basename(font) for font in AVAILABLE_FONTS]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/config', methods=['GET'])
def get_config():
    # Get font names for UI display
    font_names = []
    if AVAILABLE_FONTS:
        font_names = [os.path.basename(font) for font in AVAILABLE_FONTS]

    return jsonify({
        'surahs': SURAH_NAMES,
        'verseCounts': VERSE_COUNTS,
        'reciters': RECITERS_MAP,
        'qualityPresets': list(QUALITY_PRESETS.keys()),
        'outputFormats': list(OUTPUT_FORMATS.keys()),
        'templates': list(TEMPLATES.keys()),
        'availableFonts': font_names
    })

@app.route('/api/preview', methods=['POST'])
def preview_video():
    """Generate a preview of the first ayah (one verse)."""
    try:
        data = request.json
        reciter_id = data.get('reciter')
        surah = int(data.get('surah', 1))
        ayah = int(data.get('ayah', 1))
        template = data.get('template', 'normal')
        quality = 'low'  # Always use low quality for preview
        selected_font = data.get('selectedFont', 'random')

        # Generate preview with just one ayah; pass person_name='', selected_font, target_duration_seconds=None
        preview_thread = threading.Thread(
            target=build_video,
            args=(reciter_id, surah, ayah, ayah, quality, 'reels', template, '', selected_font, None),
            daemon=True
        )
        preview_thread.start()

        return jsonify({'success': True, 'message': 'Preview generation started'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/vision/<path:filename>')
def serve_vision(filename):
    return send_from_directory(VISION_DIR, filename)

@app.route('/outputs/<path:filename>')
def serve_output(filename):
    return send_from_directory(OUT_DIR, filename)

@app.route('/final_video.mp4')
def serve_final_video():
    return send_from_directory(EXEC_DIR, 'final_video.mp4')

if __name__ == '__main__':
    logging.info('Server Starting...')
    print('=' * 50)
    print('  One-Click Quran Reels Generator')
    print('  Running in Portable Mode')
    print('=' * 50)

    # Open browser automatically
    webbrowser.open('http://127.0.0.1:5000')

    # Start Flask server
    # Important: host='127.0.0.1' as requested
    app.run(host='127.0.0.1', port=5000, debug=False, threaded=True)
