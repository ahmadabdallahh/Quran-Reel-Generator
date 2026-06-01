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
import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFont, ImageFilter

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
# STEP 2b: FEATURE FLAGS  (animations.md §12)
# =============================================================================
# Gates each phase of the animations plan so behavior changes are opt-in.
#   - font_polish:     Phase 1 (always on, already shipped)
#   - text_animations: Phase 2 (intro/outro fades, slide/zoom on text)
#   - kinetic_text:    Phase 3 (per-word reveal — opt-in, not yet implemented)
#   - forced_alignment: Phase 3 v3 (per-word word-by-word forced alignment)
# =============================================================================

FEATURE_FLAGS = {
    'font_polish':        True,
    'text_animations':    True,
    'kinetic_text':       False,
    'forced_alignment':   False,
}

# =============================================================================
# STEP 3: TEMPORARY DIRECTORY MANAGEMENT (NEW: replaces static audio folder)
# =============================================================================

# Create temp directory inside project structure that auto-cleans on exit
TEMP_DIR = os.path.join(EXEC_DIR, "temp")
os.makedirs(TEMP_DIR, exist_ok=True)
logging.info(f"Temp directory: {TEMP_DIR}")

# Create persistent audio cache directory
AUDIO_CACHE_DIR = os.path.join(EXEC_DIR, "cache", "audio")
os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)
logging.info(f"Audio cache directory: {AUDIO_CACHE_DIR}")

# Cache management
AUDIO_CACHE_MAX_SIZE_MB = 500  # Maximum cache size in MB
AUDIO_CACHE_MAX_FILES = 1000   # Maximum number of files

def get_cached_audio_path(reciter_id, surah, ayah):
    """Get cached audio file path"""
    fn = f'{surah:03d}{ayah:03d}.mp3'
    reciter_dir = os.path.join(AUDIO_CACHE_DIR, str(reciter_id))
    os.makedirs(reciter_dir, exist_ok=True)
    return os.path.join(reciter_dir, fn)

def cleanup_audio_cache():
    """Clean audio cache if it exceeds limits"""
    try:
        # Get all audio files
        audio_files = []
        for root, dirs, files in os.walk(AUDIO_CACHE_DIR):
            for file in files:
                if file.endswith('.mp3'):
                    file_path = os.path.join(root, file)
                    stat = os.stat(file_path)
                    audio_files.append((file_path, stat.st_size, stat.st_mtime))

        # Sort by last accessed time (LRU)
        audio_files.sort(key=lambda x: x[2])

        # Check size limit
        total_size = sum(size for _, size, _ in audio_files) / (1024 * 1024)  # MB

        # Remove oldest files if limits exceeded
        files_to_remove = []
        if total_size > AUDIO_CACHE_MAX_SIZE_MB or len(audio_files) > AUDIO_CACHE_MAX_FILES:
            excess_size = total_size - AUDIO_CACHE_MAX_SIZE_MB
            excess_files = len(audio_files) - AUDIO_CACHE_MAX_FILES

            for file_path, size, _ in audio_files:
                if excess_size > 0 or excess_files > 0:
                    files_to_remove.append(file_path)
                    excess_size -= size / (1024 * 1024)
                    excess_files -= 1
                else:
                    break

        # Remove files
        for file_path in files_to_remove:
            try:
                os.remove(file_path)
                logging.debug(f"Removed old cache file: {os.path.basename(file_path)}")
            except:
                pass

        if files_to_remove:
            logging.info(f"Cleaned {len(files_to_remove)} old audio cache files")

    except Exception as e:
        logging.warning(f"Audio cache cleanup failed: {e}")

def cleanup_temp():
    """Cleanup temp directory on exit"""
    try:
        if os.path.exists(TEMP_DIR):
            shutil.rmtree(TEMP_DIR, ignore_errors=True)
            logging.info("Temp directory cleaned up")
    except:
        pass

# Also cleanup after each video generation
def cleanup_after_video():
    """Clean temp files after video completion"""
    try:
        if os.path.exists(TEMP_DIR):
            # Keep directory but remove contents
            for item in os.listdir(TEMP_DIR):
                item_path = os.path.join(TEMP_DIR, item)
                if os.path.isfile(item_path):
                    os.remove(item_path)
                elif os.path.isdir(item_path):
                    shutil.rmtree(item_path, ignore_errors=True)
            logging.debug("Temp files cleaned after video")
    except Exception as e:
        logging.warning(f"Failed to cleanup temp files: {e}")

# Cleanup orphaned temp files on startup
def cleanup_orphaned_temp_files():
    """Clean temp files that might be left from previous crashes"""
    try:
        if os.path.exists(TEMP_DIR):
            # Remove files older than 1 hour
            current_time = time.time()
            for item in os.listdir(TEMP_DIR):
                item_path = os.path.join(TEMP_DIR, item)
                try:
                    stat = os.stat(item_path)
                    if current_time - stat.st_mtime > 3600:  # 1 hour
                        if os.path.isfile(item_path):
                            os.remove(item_path)
                        elif os.path.isdir(item_path):
                            shutil.rmtree(item_path, ignore_errors=True)
                        logging.debug(f"Removed orphaned temp file: {item}")
                except:
                    pass
            logging.info("Orphaned temp files cleanup completed")
    except Exception as e:
        logging.warning(f"Orphaned temp cleanup failed: {e}")

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

FFPROBE_EXE = find_binary(os.path.join(BUNDLE_DIR, "bin", "ffmpeg", "ffprobe.exe"), "ffprobe")
if not FFPROBE_EXE and FFMPEG_EXE:
    prob_path = os.path.join(os.path.dirname(FFMPEG_EXE), "ffprobe.exe")
    if os.path.isfile(prob_path): FFPROBE_EXE = prob_path
    else: FFPROBE_EXE = shutil.which("ffprobe")

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
    """Enhanced test if a font can render Arabic text with tashkeel and complex ligatures"""
    try:
        font = ImageFont.truetype(font_path, 30)

        # Simple test case - just check if font loads and can render basic Arabic
        test_text = "بسم الله"

        try:
            reshaped = ARABIC_RESHAPER.reshape(test_text)
            bidi_text = get_display(reshaped)

            # Create test image
            img = Image.new('RGB', (400, 60), color='white')
            draw = ImageDraw.Draw(img)
            draw.text((20, 20), bidi_text, font=font, fill='black')

            # Verify text was rendered (check if image changed)
            img_array = np.array(img)
            if not np.array_equal(img_array, np.ones_like(img_array) * 255):
                logging.debug(f"✅ Font {os.path.basename(font_path)} can render Arabic")
                return True

        except Exception as e:
            logging.debug(f"Font rendering test failed: {e}")
            # Even if reshaping fails, if font loads it might work for simple text
            return True

    except Exception as e:
        logging.warning(f"Font test failed for {os.path.basename(font_path)}: {e}")
        return False

def validate_arabic_rendering_pipeline():
    """Validate the entire Arabic text rendering pipeline"""
    try:
        # Test the full pipeline with simple text
        test_text = "بسم الله"

        # Step 1: Process text
        processed_text, num_lines, word_count = process_arabic_text(test_text, words_per_line=4)

        # Step 2: Render to image
        img = render_arabic_to_pil_image(test_text, fontsize=80)

        # Step 3: Verify image is not empty
        img_array = np.array(img)
        if img_array.size == 0 or np.all(img_array == 0):
            raise ValueError("Rendered image is empty")

        logging.info("✅ Arabic rendering pipeline validation passed")
        return True

    except Exception as e:
        logging.warning(f"Arabic rendering pipeline validation failed: {e}")
        return False

def init_font_system():
    """Initialize font system once at startup - find best working Arabic font"""
    global WORKING_FONT

    logging.info("🔍 Initializing Arabic font system...")

    # Priority order for Arabic fonts (best first)
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

                # Validate the entire pipeline (optional)
                validate_arabic_rendering_pipeline()
                return

    # Try any available font as fallback
    if os.path.exists(FONT_DIR):
        logging.info("Trying fallback fonts...")
        for file in os.listdir(FONT_DIR):
            if file.lower().endswith(('.ttf', '.otf')):
                font_path = os.path.join(FONT_DIR, file)
                try:
                    # Just try to load the font
                    ImageFont.truetype(font_path, 30)
                    WORKING_FONT = _safe_font_path_for_imagemagick(font_path)
                    logging.info(f"✅ Working font selected (fallback): {file}")

                    # Validate pipeline (optional)
                    validate_arabic_rendering_pipeline()
                    return
                except:
                    continue

    # Last resort - try system fonts
    try:
        # Try common system fonts that might support Arabic
        system_fonts = [
            "Arial", "Times New Roman", "Tahoma",
            "Microsoft Sans Serif", "Calibri"
        ]

        for font_name in system_fonts:
            try:
                font = ImageFont.truetype(font_name, 30)
                WORKING_FONT = font_name  # Use system font name directly
                logging.info(f"✅ Using system font: {font_name}")
                validate_arabic_rendering_pipeline()
                return
            except:
                continue
    except:
        pass

    logging.warning("⚠️ No Arabic fonts found - text rendering may not work properly")
    logging.warning("Please install Arabic fonts like Amiri, Dubai, or Lateef for best results")

    # Don't raise error - let the system start with a default font
    WORKING_FONT = "Arial"  # Fallback to system default
    return

# Fonts that PIL can render Arabic with (have presentation forms in cmap).
# The other 13 fonts in fonts/ require OpenType GSUB contextual substitution
# which PIL doesn't apply, so they render as boxes. See skills.md §8.3.
PIL_COMPATIBLE_ARABIC_FONTS = ['Amiri-Bold.ttf', 'Amiri-Regular.ttf']


def get_random_font():
    """Get a random working font from the PIL-compatible subset.

    NOTE: we cannot pick from the full fonts/ directory because most fonts
    there (Lateef, ElMessiri, Dubai, Tajawal, ...) lack presentation forms
    and PIL does not apply OpenType GSUB.  See PIL_COMPATIBLE_ARABIC_FONTS.
    """
    if not os.path.exists(FONT_DIR):
        return WORKING_FONT
    # Restrict to PIL-compatible fonts only
    fonts = [f for f in PIL_COMPATIBLE_ARABIC_FONTS
             if os.path.exists(os.path.join(FONT_DIR, f))]
    if not fonts:
        return WORKING_FONT
    return os.path.join(FONT_DIR, random.choice(fonts))

def get_specific_font(name):
    """Get a specific font by name, or fallback to working font"""
    if not name or name == 'random':
        return get_random_font()
    path = os.path.join(FONT_DIR, name)
    if os.path.exists(path):
        return path
    return WORKING_FONT

# NOTE: init_font_system() is called inside the __main__ block (bottom of file)
# because it depends on process_arabic_text (defined further down) for its
# pipeline validation. Calling it at module import time raises NameError.

# =============================================================================
# STEP 6: UNIFIED ARABIC TEXT PROCESSING (NEW: single function)
# =============================================================================

# Arabic reshaper configured to preserve tashkeel (harakat)
ARABIC_RESHAPER = arabic_reshaper.ArabicReshaper({
    'delete_harakat': False,
    'support_ligatures': True,
})

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

    # Step 2: Apply Arabic reshaping to FULL text first (preserves tashkeel + ligatures)
    reshaped_full = ARABIC_RESHAPER.reshape(cleaned)

    # Step 3: Apply BiDi to FULL text (ensures correct RTL)
    visual_full = get_display(reshaped_full)

    # Step 4: Split into LOGICAL words (from original cleaned text) and wrap
    logical_words = cleaned.split()
    total_words = len(logical_words)
    if total_words == 0:
        return visual_full, 1, 0

    # Wrap logical words into lines
    logical_lines = []
    for i in range(0, total_words, max(1, int(words_per_line))):
        logical_lines.append(' '.join(logical_words[i:i + words_per_line]))

    # Step 5: Apply reshape+bidi to each logical line to preserve tashkeel
    visual_lines = []
    for ln in logical_lines:
        reshaped_ln = ARABIC_RESHAPER.reshape(ln)
        visual_ln = get_display(reshaped_ln)
        visual_lines.append(visual_ln)

    wrapped = '\n'.join(visual_lines)
    logging.info(f"📊 Text processed: {total_words} words -> {len(visual_lines)} lines")
    return wrapped, len(visual_lines), total_words

# =============================================================================
# STEP 7: UNIFIED TEXT RENDERING (NEW: single function using WORKING_FONT)
# =============================================================================

def render_arabic_to_pil_image(text, fontsize=80, color='#FFFFFF',
                                stroke_color='#000000', stroke_width=3,
                                words_per_line=4, target_width=920, font_path=None,
                                supersample=2,
                                shadow=True, shadow_offset=4, shadow_color='#00000080',
                                glow_color=None, glow_radius=6):
    """
    Render Arabic text to a PIL RGBA Image with broadcast-grade quality.

    Pipeline:
      1.  Reshape + BiDi the input text.
      2.  Render at `supersample` x resolution (default 2x) into a transparent canvas
          using Pillow's native anti-aliased `stroke_width` / `stroke_fill`.
      3.  (Optional) Drop shadow — draw a black copy at (+offset, +offset) below the
          main layer.
      4.  (Optional) Soft glow — Gaussian-blur a colorized copy of the text and
          composite it underneath (used by the `ramadan` template).
      5.  Downsample to the target size with `Image.LANCZOS`.

    Args:
        text:            Raw Arabic text (Uthmani or plain).
        fontsize:        Target font size in pixels (post-downsample).
        color:           Fill color (hex, e.g. '#FFFFFF').
        stroke_color:    Outline color (hex).
        stroke_width:    Outline thickness in pixels (post-downsample). Default 3
                         (was 2 — bumped for 1080p legibility).
        words_per_line:  Words-per-line wrap hint.
        target_width:    Output image width in pixels.
        font_path:       Override font; defaults to WORKING_FONT.
        supersample:     Render-scale multiplier (1, 2, 4). 1 disables AA boost;
                         2 is the default; 4 is recommended for `high` quality.
        shadow:          If True, draw a soft drop shadow.
        shadow_offset:   Shadow offset in pixels (post-downsample).
        shadow_color:    Shadow color (hex with alpha, e.g. '#00000080').
        glow_color:      If set, apply a colored Gaussian-blur glow (e.g. '#FFD700').
        glow_radius:     Glow blur radius.

    Returns:
        PIL Image object (RGBA).
    """
    # Step 1 — process Arabic text
    processed_text, num_lines, word_count = process_arabic_text(text, words_per_line)

    if not processed_text:
        return Image.new('RGBA', (target_width, 100), (0, 0, 0, 0))

    # Step 2 — load font
    f_path = font_path or WORKING_FONT
    try:
        font = ImageFont.truetype(f_path, fontsize * supersample)
    except Exception:
        font = ImageFont.truetype(WORKING_FONT, fontsize * supersample)

    # Parse colors
    def hex_to_rgba(hex_color):
        s = (hex_color or '#FFFFFF').strip().lstrip('#')
        if len(s) == 3:
            s = ''.join([c * 2 for c in s])
        if len(s) == 6:
            return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), 255)
        if len(s) == 8:
            return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), int(s[6:8], 16))
        return (255, 255, 255, 255)

    fill_rgba = hex_to_rgba(color)
    stroke_rgba = hex_to_rgba(stroke_color)
    shadow_rgba = hex_to_rgba(shadow_color)

    # Step 3 — calculate image dimensions
    line_height = int(fontsize * 1.6)
    padding = 50
    img_height = max(300, num_lines * line_height + 2 * padding)
    img_width = target_width + 2 * padding

    # Step 4 — render at supersample resolution
    ss = max(1, int(supersample))
    big_w, big_h = img_width * ss, img_height * ss
    big = Image.new('RGBA', (big_w, big_h), (0, 0, 0, 0))
    big_draw = ImageDraw.Draw(big)

    big_y = (padding + line_height // 2) * ss
    big_x_center = big_w // 2

    for line in processed_text.split('\n'):
        if not line.strip():
            big_y += line_height * ss
            continue

        # Pillow's native anti-aliased stroke (single C call, no jaggies).
        big_draw.text(
            (big_x_center, big_y), line,
            font=font, fill=fill_rgba, anchor='mm',
            stroke_width=max(0, stroke_width) * ss,
            stroke_fill=stroke_rgba,
        )
        big_y += line_height * ss

    # Step 5 — drop shadow (rendered at supersample, then composited before downsample)
    if shadow and shadow_color:
        shadow_layer = Image.new('RGBA', (big_w, big_h), (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow_layer)
        big_y2 = (padding + line_height // 2) * ss
        for line in processed_text.split('\n'):
            if not line.strip():
                big_y2 += line_height * ss
                continue
            shadow_draw.text(
                (big_x_center + shadow_offset * ss, big_y2 + shadow_offset * ss), line,
                font=font, fill=shadow_rgba, anchor='mm',
                stroke_width=max(0, stroke_width) * ss,
                stroke_fill=shadow_rgba,
            )
            big_y2 += line_height * ss
        # Composite shadow BEHIND the main text
        big = Image.alpha_composite(shadow_layer, big)

    # Step 6 — soft glow (gold halo for the ramadan template)
    if glow_color:
        glow_layer = Image.new('RGBA', (big_w, big_h), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow_layer)
        big_y3 = (padding + line_height // 2) * ss
        for line in processed_text.split('\n'):
            if not line.strip():
                big_y3 += line_height * ss
                continue
            glow_draw.text(
                (big_x_center, big_y3), line,
                font=font, fill=hex_to_rgba(glow_color), anchor='mm',
                stroke_width=max(0, stroke_width) * ss,
                stroke_fill=hex_to_rgba(glow_color),
            )
            big_y3 += line_height * ss
        # Heavy blur for a halo
        glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=glow_radius * ss))
        big = Image.alpha_composite(glow_layer, big)

    # Step 7 — downsample to target resolution
    if ss > 1:
        img = big.resize((img_width, img_height), Image.LANCZOS)
    else:
        img = big

    logging.info(
        f"✅ Image rendered: {img_width}x{img_height}px, {num_lines} lines, "
        f"supersample={ss}, shadow={bool(shadow)}, glow={bool(glow_color)}"
    )
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
    'reels': {'size': (1080, 1920), 'duration': 600}, # 10 mins
    'story': {'size': (1080, 1920), 'duration': 60},  # 1 min
    'post': {'size': (1080, 1080), 'duration': 600}  # 10 mins
}

TEMPLATES = {
    'ramadan': {
        'bg_style': 'night', 'text_color': '#FFD700', 'font_size_mult': 1.20,
        'text_animation': 'fade_in', 'transition': 'fade',
        'font': 'Amiri-Bold.ttf', 'glow_color': '#FFD700', 'glow_radius': 8,
    },
    'normal':  {
        'bg_style': 'nature', 'text_color': '#FFFFFF', 'font_size_mult': 1.00,
        'text_animation': 'slide_up', 'transition': 'dissolve',
        'font': 'Amiri-Regular.ttf',
    },
    'masjid':  {
        # Soft white halo evokes moonlit calligraphy on the mosque wall.
        # Note: must use Amiri — Lateef/ElMessiri lack presentation forms and
        # PIL does not apply OpenType GSUB contextual substitution.
        'bg_style': 'masjid', 'text_color': '#FFFFFF', 'font_size_mult': 1.10,
        'text_animation': 'fade_in', 'transition': 'fade',
        'font': 'Amiri-Bold.ttf', 'glow_color': '#FFFFFF80', 'glow_radius': 4,
    },
    'islamic': {
        # Heavier drop shadow gives the calligraphic depth of manuscript art.
        'bg_style': 'islamic', 'text_color': '#FFFFFF', 'font_size_mult': 1.10,
        'text_animation': 'zoom_in', 'transition': 'wipe',
        'font': 'Amiri-Bold.ttf',
    },
}

# Animation & Transitions Configuration
TEXT_ANIMATIONS = {
    'fade_in': {'type': 'fade', 'duration': 0.5, 'direction': 'in', 'frames': 15},
    'slide_up': {'type': 'slide', 'duration': 0.5, 'direction': 'up', 'distance': 50},
    'slide_down': {'type': 'slide', 'duration': 0.5, 'direction': 'down', 'distance': 50},
    'slide_left': {'type': 'slide', 'duration': 0.5, 'direction': 'left', 'distance': 50},
    'slide_right': {'type': 'slide', 'duration': 0.5, 'direction': 'right', 'distance': 50},
    'zoom_in': {'type': 'zoom', 'duration': 0.5, 'start_scale': 0.8, 'end_scale': 1.0},
    'typewriter': {'type': 'typewriter', 'duration': 0.03, 'char_delay': 1},  # per character
    'reveal': {'type': 'reveal', 'duration': 0.5, 'direction': 'left'},
    'glow': {'type': 'glow', 'duration': 0.5, 'glow_intensity': 1.5},
    'bounce': {'type': 'bounce', 'duration': 0.6, 'bounces': 3},
}

VIDEO_TRANSITIONS = {
    'fade': {'type': 'fade', 'duration': 0.5, 'ffmpeg_filter': 'fade=out:st={duration}:d={duration}'},
    'dissolve': {'type': 'dissolve', 'duration': 0.5, 'ffmpeg_filter': 'xfade=transition=fade:duration={duration}'},
    'wipe': {'type': 'wipe', 'duration': 0.5, 'direction': 'right', 'ffmpeg_filter': 'xfade=transition=wipeleft:duration={duration}'},
    'slide': {'type': 'slide', 'duration': 0.5, 'direction': 'left', 'ffmpeg_filter': 'xfade=transition=slideleft:duration={duration}'},
    'cross_zoom': {'type': 'zoom', 'duration': 0.5, 'ffmpeg_filter': 'xfade=transition=zoomin:duration={duration}'},
    'pixelate': {'type': 'pixelate', 'duration': 0.5, 'ffmpeg_filter': 'xfade=transition=pixelize:duration={duration}'},
}

# Background Rotation Manager - Prevents video repetition
class BackgroundRotator:
    """Manages background video rotation to prevent repetition per video generation"""
    def __init__(self, style='nature'):
        self.style = style
        self.used_backgrounds = set()
        self.available = self._load_backgrounds()
        self.current_index = 0
        self.usage_history = []  # Track usage across sessions
        self.min_distance = 3    # Minimum distance between repeats

    def _load_backgrounds(self):
        """Load available backgrounds for the style"""
        style_dir = os.path.join(VISION_DIR, self.style)
        if os.path.isdir(style_dir):
            files = [f for f in os.listdir(style_dir) if f.endswith('.mp4')]
            return [os.path.join(style_dir, f) for f in files]
        else:
            # Fallback to pattern-based in main vision folder
            pattern = f"{self.style}_part"
            files = [f for f in os.listdir(VISION_DIR)
                    if f.startswith(pattern) and f.endswith('.mp4')]
            return [os.path.join(VISION_DIR, f) for f in files]

    def get_next(self, count=1):
        """Get next background(s) ensuring variety with smart rotation"""
        if not self.available:
            raise ValueError(f"No backgrounds found for style: {self.style}")

        if count == 1:
            # Smart selection with minimum distance
            candidates = []

            # First, try unused backgrounds
            unused = [b for b in self.available if b not in self.used_backgrounds]
            if unused:
                candidates = unused
            else:
                # If all used, reset and prioritize least recently used
                self.used_backgrounds.clear()
                # Sort by last usage time
                candidates = sorted(self.available,
                                 key=lambda x: self._get_last_usage_time(x))

            if candidates:
                # Weighted random selection - prefer less used backgrounds
                weights = []
                for bg in candidates:
                    usage_count = self._get_usage_count(bg)
                    # Lower usage count = higher weight
                    weight = 1.0 / (usage_count + 1)
                    weights.append(weight)

                # Normalize weights
                total_weight = sum(weights)
                if total_weight > 0:
                    weights = [w / total_weight for w in weights]
                    selected = random.choices(candidates, weights=weights)[0]
                else:
                    selected = random.choice(candidates)

                self.used_backgrounds.add(selected)
                self._record_usage(selected)
                return selected
            else:
                # Fallback to random if no candidates
                selected = random.choice(self.available)
                self.used_backgrounds.add(selected)
                self._record_usage(selected)
                return selected

        else:
            # Get multiple unique backgrounds
            selected = []
            available_copy = self.available.copy()

            for _ in range(min(count, len(self.available))):
                if not available_copy:
                    break

                # Similar logic for multiple selection
                unused = [b for b in available_copy if b not in self.used_backgrounds]
                if unused:
                    candidates = unused
                else:
                    candidates = sorted(available_copy,
                                     key=lambda x: self._get_last_usage_time(x))

                if candidates:
                    bg = candidates[0]  # Take the best candidate
                    selected.append(bg)
                    self.used_backgrounds.add(bg)
                    self._record_usage(bg)
                    available_copy.remove(bg)
                else:
                    break

            return selected

    def _get_usage_count(self, bg_path):
        """Get how many times this background was used"""
        return sum(1 for entry in self.usage_history if entry == bg_path)

    def _get_last_usage_time(self, bg_path):
        """Get last usage time (0 if never used)"""
        for i in reversed(range(len(self.usage_history))):
            if self.usage_history[i] == bg_path:
                return i
        return 0

    def _record_usage(self, bg_path):
        """Record background usage"""
        self.usage_history.append(bg_path)
        # Keep history manageable
        if len(self.usage_history) > 100:
            self.usage_history = self.usage_history[-50:]

    def reset(self):
        """Reset rotation for new video generation"""
        self.used_backgrounds.clear()
        self.current_index = 0

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
    'الشيخ محمد صديق المنشاوي (مجود)': 'Minshawy_Mujawwad_64kbps',
    'الشيخ سعود الشريم': 'Saood_ash-Shuraym_64kbps',
    'الشيخ محمود خليل الحصري': 'Husary_64kbps',
    'الشيخ محمود علي البنا': 'mahmoud_ali_al_banna_32kbps',
    'الشيخ عبدالباسط عبدالصمد (مجود)': 'Abdul_Basit_Mujawwad_128kbps',
    'الشيخ أحمد نعينع': 'Ahmed_Neana_128kbps',
    'الشيخ علي جابر': 'Ali_Jaber_64kbps',
    'الشيخ محمد الطبلاوي': 'Mohammad_al_Tablaway_128kbps',
    'الشيخ مصطفى إسماعيل': 'Mustafa_Ismail_48kbps',
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
from urllib3.util.retry import Retry
from urllib3 import disable_warnings
disable_warnings()  # Disable SSL warnings
from pydub import AudioSegment
import shutil

if FFMPEG_EXE:
    logging.info(f"Using FFmpeg: {FFMPEG_EXE}")
    os.environ["FFMPEG_BINARY"] = FFMPEG_EXE
    os.environ["IMAGEIO_FFMPEG_EXE"] = FFMPEG_EXE
    AudioSegment.converter = FFMPEG_EXE
    AudioSegment.ffmpeg = FFMPEG_EXE
    AudioSegment.ffprobe = FFPROBE_EXE or "ffprobe"
else:
    raise RuntimeError("FFmpeg not found - video processing requires FFmpeg")

# MoviePy imports removed - using direct FFmpeg for performance

# =============================================================================
# STEP 10: GLOBAL PROGRESS TRACKING & FLASK APP
# =============================================================================
# Enhanced Progress Tracking System
current_progress = {
    'percent': 0,
    'status': 'جاري التحضير...',
    'log': [],
    'is_running': False,
    'is_complete': False,
    'output_path': None,
    'error': None,
    'current_ayah': 0,
    'total_ayat': 0,
    'stage': 'preparing',  # preparing, downloading, processing, concatenating, complete
    'eta_seconds': None,
    'start_time': None
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
        'error': None,
        'current_ayah': 0,
        'total_ayat': 0,
        'stage': 'preparing',
        'eta_seconds': None,
        'start_time': time.time()
    }

def add_log(message):
    current_progress['log'].append(message)
    logging.info(f"PROGRESS: {message}")

def update_progress(percent, status, stage=None, current_ayah=None, total_ayat=None):
    current_progress['percent'] = percent
    current_progress['status'] = status

    if stage:
        current_progress['stage'] = stage

    if current_ayah is not None:
        current_progress['current_ayah'] = current_ayah

    if total_ayat is not None:
        current_progress['total_ayat'] = total_ayat

    # Calculate ETA if we have progress and start time
    if current_progress['start_time'] and percent > 0:
        elapsed = time.time() - current_progress['start_time']
        if percent < 100:
            estimated_total = elapsed * 100 / percent
            current_progress['eta_seconds'] = max(0, estimated_total - elapsed)
        else:
            current_progress['eta_seconds'] = 0

    logging.info(f"STATUS ({percent}%): {status}")

def update_ayah_progress(current, total, stage='processing'):
    """Update progress for ayah processing with detailed info"""
    percent = int(10 + (70 * current / total)) if total > 0 else 10
    status = f'معالجة الآية {current} من {total}...'

    update_progress(
        percent=percent,
        status=status,
        stage=stage,
        current_ayah=current,
        total_ayat=total
    )

# =============================================================================
# STEP 11: UTILITY FUNCTIONS
# =============================================================================

# Cache for ayah texts (avoid duplicate API calls)
AYAH_TEXT_CACHE = {}

def get_audio_duration_ffprobe(audio_path):
    """Get audio duration using ffprobe"""
    exe = FFPROBE_EXE or "ffprobe"

    cmd = [
        exe, "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", audio_path
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=True)
    return float(out.stdout.strip())

# =============================================================================
# STEP 12: DATA FETCHING (ENHANCED WITH RETRY & CIRCUIT BREAKER)
# =============================================================================

# Circuit breaker state
_circuit_breaker_failures = 0
_circuit_breaker_last_failure = 0
_circuit_breaker_threshold = 5
_circuit_breaker_timeout = 60  # seconds

def is_circuit_breaker_open():
    """Check if circuit breaker is open"""
    global _circuit_breaker_failures, _circuit_breaker_last_failure

    if _circuit_breaker_failures >= _circuit_breaker_threshold:
        # Check if timeout has passed
        if time.time() - _circuit_breaker_last_failure > _circuit_breaker_timeout:
            _circuit_breaker_failures = 0  # Reset
            return False
        return True
    return False

def record_download_success():
    """Record successful download"""
    global _circuit_breaker_failures
    _circuit_breaker_failures = 0

def record_download_failure():
    """Record download failure"""
    global _circuit_breaker_failures, _circuit_breaker_last_failure
    _circuit_breaker_failures += 1
    _circuit_breaker_last_failure = time.time()

def download_audio(reciter_id, surah, ayah, idx):
    """Download audio for one ayah with enhanced retry logic and circuit breaker"""
    fn = f'{surah:03d}{ayah:03d}.mp3'

    # Check circuit breaker first
    if is_circuit_breaker_open():
        raise RuntimeError("Circuit breaker is open - too many consecutive failures")

    # Check cache first
    cached_path = get_cached_audio_path(reciter_id, surah, ayah)

    if os.path.exists(cached_path) and os.path.getsize(cached_path) > 1000:
        logging.debug(f"Using cached audio: {fn}")
        # Copy to temp directory for processing
        out = os.path.join(TEMP_DIR, f'audio_{idx:03d}.mp3')
        shutil.copy2(cached_path, out)
        return out

    # Try multiple sources with different domains
    sources = [
        f'https://everyayah.com/data/{reciter_id}/{fn}',
        f'https://download.quranicaudio.com/quran/{reciter_id}/{fn}',
        f'https://www.everyayah.com/data/{reciter_id}/{fn}',
        f'https://mp3.quranicaudio.com/quran/{reciter_id}/{fn}'
    ]

    out = os.path.join(TEMP_DIR, f'audio_{idx:03d}.mp3')

    # Enhanced session with better retry strategy
    session = http_requests.Session()
    retry_strategy = Retry(
        total=5,  # Increased retries
        backoff_factor=2,  # Exponential backoff
        status_forcelist=[429, 500, 502, 503, 504, 408],  # Include timeout
        allowed_methods=["GET"]
    )
    adapter = http_requests.adapters.HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    for attempt, url in enumerate(sources, 1):
        try:
            logging.debug(f"Downloading audio from source {attempt}: {url}")

            # Add exponential delay between attempts
            if attempt > 1:
                delay = min(2 ** (attempt - 2), 10)  # Max 10 seconds
                time.sleep(delay)
                logging.debug(f"Retry delay: {delay}s")

            r = session.get(url, timeout=30)  # Longer timeout
            r.raise_for_status()

            with open(out, 'wb') as f:
                f.write(r.content)

            # Verify file has content
            if os.path.getsize(out) < 1000:
                raise ValueError(f"Audio file too small: {os.path.getsize(out)} bytes")

            logging.debug(f"Audio downloaded: {fn} ({os.path.getsize(out)} bytes)")

            # Save to cache (the downloaded file as-is)
            try:
                os.makedirs(os.path.dirname(cached_path), exist_ok=True)
                shutil.copy2(out, cached_path)
                logging.debug(f"Audio cached: {cached_path}")
            except Exception as e:
                logging.warning(f"Failed to cache audio: {e}")

            # ✅ NO TRIMMING AT ALL - Keep original Quran recitation intact
            record_download_success()
            return out

        except Exception as e:
            logging.warning(f"Source {attempt} failed: {e}")
            record_download_failure()

            if attempt < len(sources):
                continue
            else:
                # All sources failed - check if circuit breaker should open
                if _circuit_breaker_failures >= _circuit_breaker_threshold:
                    logging.error("Circuit breaker opened due to consecutive failures")

                raise RuntimeError(f"Failed to download audio for {surah}:{ayah} from all sources")

def download_audio_parallel(reciter_id, ayah_list, max_workers=4):
    """Download multiple audio files in parallel with rate limiting"""
    import concurrent.futures
    import threading

    results = {}
    download_lock = threading.Lock()
    last_download_time = 0
    min_delay = 0.5  # Minimum delay between downloads to respect rate limits

    def download_with_delay(args):
        nonlocal last_download_time

        reciter_id, surah, ayah, idx = args

        # Rate limiting
        with download_lock:
            nonlocal last_download_time
            current_time = time.time()
            if current_time - last_download_time < min_delay:
                time.sleep(min_delay - (current_time - last_download_time))
            last_download_time = time.time()

        try:
            audio_path = download_audio(reciter_id, surah, ayah, idx)
            return (ayah, audio_path, None)
        except Exception as e:
            return (ayah, None, str(e))

    # Prepare arguments
    download_args = [(reciter_id, ayah['surah'], ayah['ayah'], ayah['idx'])
                     for ayah in ayah_list]

    # Download in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_ayah = {executor.submit(download_with_delay, args): args for args in download_args}

        for future in concurrent.futures.as_completed(future_to_ayah):
            ayah, audio_path, error = future.result()
            if error:
                logging.error(f"Failed to download ayah {ayah}: {error}")
                results[ayah] = {'error': error}
            else:
                results[ayah] = {'path': audio_path}
                logging.debug(f"Downloaded ayah {ayah} in parallel")

    return results

def get_ayah_text(surah, ayah):
    """Fetch ayah text from API with cache"""
    cache_key = f"{surah}:{ayah}"

    # Check cache first
    if cache_key in AYAH_TEXT_CACHE:
        logging.debug(f"Using cached text for {cache_key}")
        return AYAH_TEXT_CACHE[cache_key]

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

        # Cache the result
        AYAH_TEXT_CACHE[cache_key] = text
        return text
    except Exception as e:
        logging.debug(f"Text fetch failed, retrying once: {e}")
        # One retry
        resp = http_requests.get(
            f'https://api.alquran.cloud/v1/ayah/{surah}:{ayah}/quran-uthmani',
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        text = data['data']['text'].replace('\ufeff', '').replace('\u200b', '').strip()
        AYAH_TEXT_CACHE[cache_key] = text
        return text

# =============================================================================
# STEP 13: BACKGROUND HANDLING (CACHED)
# =============================================================================

BG_CACHE = {}

def init_bg_cache():
    """Scan background folders once at startup"""
    global BG_CACHE
    styles = ['nature', 'islamic', 'masjid', 'night']  # Removed 'colorful'

    for style in styles:
        style_dir = os.path.join(VISION_DIR, style)
        files = []

        # Check if style folder exists
        if os.path.isdir(style_dir):
            files = [f for f in os.listdir(style_dir) if f.endswith('.mp4')]
            logging.debug(f"Found {len(files)} files in {style_dir}/")
        else:
            # Fallback: try old pattern-based naming in main vision folder
            pattern = f"{style}_part"
            space_pattern = pattern.replace('_', ' ')
            files = [f for f in os.listdir(VISION_DIR)
                     if (f.startswith(pattern) or f.startswith(space_pattern))
                     and f.endswith('.mp4')]
            if files:
                logging.debug(f"Fallback: Found {len(files)} files with pattern '{pattern}' in main folder")

        BG_CACHE[style] = files
        BG_CACHE[f"{style}_part"] = files  # Also store by pattern for fallback

    logging.debug(f"BG cache initialized: {len(BG_CACHE)} styles")

# NOTE: init_bg_cache() is called inside the __main__ block (bottom of file)
# so it runs after all other definitions are in place.

def pick_bg(style='nature', count=1):
    """Select background video(s) from style-specific folders"""
    init_bg_cache() # Refresh list of available files

    files = BG_CACHE.get(style, [])

    # Fallback to nature if style has no files
    if not files:
        files = BG_CACHE.get('nature', [])

    if not files:
        raise ValueError(f"No background videos found for style '{style}' or 'nature'")

    if count == 1:
        # Return full path to the selected file
        selected_file = random.choice(files)
        style_dir = os.path.join(VISION_DIR, style)

        # Check if style folder exists, fallback to main vision folder
        if os.path.isdir(style_dir):
            return os.path.join(style_dir, selected_file)
        else:
            return os.path.join(VISION_DIR, selected_file)
    else:
        selected = random.sample(files, min(count, len(files)))
        style_dir = os.path.join(VISION_DIR, style)

        if os.path.isdir(style_dir):
            return [os.path.join(style_dir, f) for f in selected]
        else:
            return [os.path.join(VISION_DIR, f) for f in selected]

def get_preprocessed_bg(bg_path, target_w=TARGET_W, target_h=TARGET_H):
    """Get or create preprocessed background video (cached)"""
    os.makedirs(BG_CACHE_DIR, exist_ok=True)
    base = os.path.splitext(os.path.basename(bg_path))[0]
    cached_path = os.path.join(BG_CACHE_DIR, f"{base}_{target_w}x{target_h}.mp4")

    if os.path.isfile(cached_path):
        # Check if file is valid (not 0 or too small, which indicates corruption)
        if os.path.getsize(cached_path) > 5000:  # At least 5KB
            # Additional validation: try to read the file with FFprobe
            try:
                result = subprocess.run([
                    FFPROBE_EXE,
                    '-v', 'error',
                    '-show_format',
                    '-show_streams',
                    cached_path
                ], capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    logging.debug(f"Using cached background: {os.path.basename(cached_path)}")
                    return cached_path
                else:
                    logging.warning(f"Corrupted cache file (FFprobe failed): {cached_path}")
            except Exception as e:
                logging.warning(f"Cache validation failed: {e}")

            # Remove corrupted file
            try:
                os.remove(cached_path)
                logging.info(f"Removed corrupted cache file: {cached_path}")
            except:
                pass
        else:
            logging.warning(f"Cache file too small: {cached_path}")
            try:
                os.remove(cached_path)
            except:
                pass

    # Normalize BG to avoid FFmpeg concat/filter issues (fps/pix_fmt/scale)
    logging.info(f"Preprocessing background: {os.path.basename(bg_path)}")
    vf = f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase,crop={target_w}:{target_h},fps=30,format=yuv420p"
    cmd = [
        FFMPEG_EXE, "-y", "-i", bg_path,
        "-vf", vf, "-an",
        "-r", "30",
        "-c:v", "libx264",
        "-preset", "ultrafast", "-crf", "32", "-threads", "4",
        "-pix_fmt", "yuv420p",
        cached_path
    ]

    try:
        logging.info(f"Running FFmpeg preprocessing: {' '.join(cmd[:8])}...")
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=120)

        # Verify the output file was created successfully
        if os.path.exists(cached_path) and os.path.getsize(cached_path) > 5000:
            logging.info(f"Background cached successfully: {os.path.basename(cached_path)}")
            return cached_path
        else:
            logging.error(f"FFmpeg output file invalid: {cached_path}")
            return bg_path  # Fallback to original

    except subprocess.TimeoutExpired:
        logging.warning(f"Background preprocessing timeout, using original: {os.path.basename(bg_path)}")
        return bg_path  # Fallback to original
    except subprocess.CalledProcessError as e:
        logging.error(f"Background preprocessing failed: {e.stderr}")
        return bg_path  # Fallback to original
    except Exception as e:
        logging.error(f"Unexpected error in preprocessing: {e}")
        return bg_path  # Fallback to original

# =============================================================================
# STEP 13.5: DYNAMIC TEXT COLOR ANALYZER
# =============================================================================

def analyze_background_brightness(bg_path, sample_seconds=1):
    """
    Analyze background video brightness to determine optimal text color.
    Returns brightness value 0.0 (dark) to 1.0 (bright)
    """
    try:
        # Use FFmpeg to extract a frame and calculate average brightness
        cmd = [
            FFMPEG_EXE, '-i', bg_path,
            '-ss', str(sample_seconds),
            '-vframes', '1',
            '-vf', 'format=gray,scale=1:1',
            '-f', 'rawvideo', '-pix_fmt', 'gray',
            'pipe:1'
        ]

        result = subprocess.run(cmd, capture_output=True, timeout=10)
        if result.returncode == 0 and result.stdout:
            # Get the pixel value (0-255)
            pixel_value = result.stdout[0] if result.stdout else 128
            brightness = pixel_value / 255.0
            return brightness
    except Exception as e:
        logging.warning(f"Could not analyze background brightness: {e}")

    # Default to medium brightness if analysis fails
    return 0.5

def get_contrasting_text_color(bg_path, template_color='white', auto_detect=True):
    """
    Determine optimal text color based on background brightness.

    Args:
        bg_path: Path to background video
        template_color: Default color from template
        auto_detect: If True, analyze background; if False, use template color

    Returns:
        tuple: (text_color, stroke_color) as PIL color strings
    """
    if not auto_detect:
        # Use template color with dark stroke
        if template_color.lower() == 'gold':
            return ('#FFD700', 'black')
        elif template_color.lower() == 'white':
            return ('white', 'black')
        else:
            return (template_color, 'black')

    # Analyze background brightness
    brightness = analyze_background_brightness(bg_path)

    # Choose colors based on brightness
    if brightness > 0.6:
        # Bright background - use dark text with lighter stroke
        return ('#1a1a1a', '#ffffff')  # Dark gray with white stroke
    elif brightness < 0.4:
        # Dark background - use light text with dark stroke
        return ('#ffffff', '#000000')  # White with black stroke
    else:
        # Medium brightness - use template color
        if template_color.lower() == 'gold':
            return ('#FFD700', '#000000')
        else:
            return ('#ffffff', '#000000')

def get_ffmpeg_text_animation_filter(animation_name, duration=5.0, fps=30):
    """
    Generate FFmpeg filter for text intro animations.
    Phase 2 (T2.1) — returns a real filter expression to be applied to the
    text PNG before the overlay, OR None to fall back to static overlay.

    All durations are derived from the ayah audio length so they adapt
    naturally to short/long recitations.  `fade_d` is the animation window
    (0.5 s) — we cap it to duration/2 to avoid negative offsets on tiny clips.

    Supported animations:
      fade_in, fade_out, slide_up, slide_down, slide_left, slide_right,
      zoom_in, zoom_out.  Everything else (typewriter, bounce, glow, reveal)
      returns None and is deferred to Phase 3 / kinetic_text.
    """
    if not FEATURE_FLAGS.get('text_animations', False):
        return None

    # Cap the animation window so a 0.4 s ayah isn't asked to fade for 0.5 s.
    fade_d = min(0.5, max(0.1, duration / 2))

    if animation_name == 'fade_in':
        return f'fade=t=in:st=0:d={fade_d:.3f}:alpha=1'

    if animation_name == 'fade_out':
        st = max(0.0, duration - fade_d)
        return f'fade=t=out:st={st:.3f}:d={fade_d:.3f}:alpha=1'

    if animation_name == 'slide_up':
        dist = 50
        # pad bottom by `dist` and shift the visible region up over fade_d
        return (
            f'pad=iw:ih+{dist}:0:{dist}:black@0,'
            f'fade=t=in:st=0:d={fade_d:.3f}:alpha=1,'
            f'crop=iw:ih-{dist}:0:0'
        )

    if animation_name == 'slide_down':
        dist = 50
        return (
            f'pad=iw:ih+{dist}:0:0:black@0,'
            f'fade=t=in:st=0:d={fade_d:.3f}:alpha=1,'
            f'crop=iw:ih-{dist}:0:{dist}'
        )

    if animation_name == 'slide_left':
        # A true horizontal slide needs an animated `overlay` (per-frame t-eval
        # on a second input) which doesn't compose with the static PNG input
        # we have here.  Use a fade as the visual stand-in; full per-frame
        # slide is a Phase 3 / kinetic_text feature.
        return f'fade=t=in:st=0:d={fade_d:.3f}:alpha=1'

    if animation_name == 'slide_right':
        return f'fade=t=in:st=0:d={fade_d:.3f}:alpha=1'

    if animation_name == 'zoom_in':
        # Per-frame scale requires the `t` expression variable, which Pillow's
        # PNG doesn't expose — use fade_in as a stand-in until Phase 3 wires
        # up a properly-scaled second pass.
        return f'fade=t=in:st=0:d={fade_d:.3f}:alpha=1'

    if animation_name == 'zoom_out':
        return f'fade=t=out:st={max(0.0, duration - fade_d):.3f}:d={fade_d:.3f}:alpha=1'

    # typewriter / bounce / glow / reveal: defer to kinetic_text (Phase 3)
    return None

# Global background rotator instance
bg_rotator = None

def init_background_rotator(style='nature'):
    """Initialize or reset the background rotator for a new video"""
    global bg_rotator
    bg_rotator = BackgroundRotator(style)
    logging.info(f"Background rotator initialized for style: {style}")
    return bg_rotator

def get_next_background(style='nature', count=1):
    """Get next background(s) using rotator to prevent repetition"""
    global bg_rotator

    # Initialize if needed or style changed
    if bg_rotator is None or bg_rotator.style != style:
        init_background_rotator(style)

    try:
        return bg_rotator.get_next(count)
    except ValueError:
        # Fallback to random selection if rotator fails
        logging.warning(f"Rotator failed, falling back to random selection")
        return pick_bg(style, count)

# =============================================================================
# STEP 14: TEXT RENDERING TO PNG (NEW UNIFIED FUNCTION)
# =============================================================================

def _resolve_template_font(template_config, selected_font):
    """
    Pick the right font for a render. Order of precedence:
      1. `selected_font` if explicitly given (UI dropdown).
      2. `template_config['font']` (per-template default).
      3. WORKING_FONT global fallback.
    Logs a warning if the chosen font file is missing on disk.
    """
    chosen_name = None
    chosen_path = None

    if selected_font:
        chosen_path = get_specific_font(selected_font)
        chosen_name = os.path.basename(chosen_path) if chosen_path else None
    if not chosen_path or not os.path.exists(chosen_path):
        tpl_font = template_config.get('font')
        if tpl_font:
            candidate = os.path.join(FONT_DIR, tpl_font)
            if os.path.exists(candidate):
                chosen_path = _safe_font_path_for_imagemagick(candidate)
                chosen_name = tpl_font
    if not chosen_path or not os.path.exists(chosen_path):
        logging.warning(
            f"Template font '{template_config.get('font')}' and selected font "
            f"'{selected_font}' not found — falling back to WORKING_FONT "
            f"({os.path.basename(WORKING_FONT) if WORKING_FONT else 'unset'})."
        )
        chosen_path = WORKING_FONT
        chosen_name = os.path.basename(WORKING_FONT) if WORKING_FONT else None
    return chosen_path, chosen_name


def _supersample_for_quality(quality):
    """Map the quality preset to a supersample multiplier (Phase 1, T1.4)."""
    return {'low': 2, 'medium': 2, 'high': 4}.get(quality, 2)


def _fontsize_for_wordcount(word_count, size_mult):
    if word_count > 60:
        return int(50 * size_mult), 7
    if word_count > 40:
        return int(60 * size_mult), 6
    if word_count > 25:
        return int(70 * size_mult), 5
    if word_count > 15:
        return int(80 * size_mult), 4
    return int(95 * size_mult), 3


def render_text_to_png(arabic_text, template, output_png_path, selected_font=None, quality='medium'):
    """
    Render Arabic text to PNG using the unified, broadcast-grade renderer.

    Honours per-template font + glow settings and the quality preset's supersample.
    """
    template_config = TEMPLATES.get(template, TEMPLATES['normal'])

    # Resolve font (selected -> template -> WORKING_FONT)
    font_path, font_name = _resolve_template_font(template_config, selected_font)

    # Word-count aware font sizing
    word_count = len(arabic_text.split())
    size_mult = template_config['font_size_mult']
    fontsize, per_line = _fontsize_for_wordcount(word_count, size_mult)

    # Text color (template can be a hex string or a name like 'gold')
    text_color = template_config['text_color']
    if not text_color.startswith('#'):
        text_color = {'gold': '#FFD700', 'white': '#FFFFFF', 'bright': '#00FFFF'}.get(text_color, '#FFFFFF')

    # Glow (e.g. ramadan template)
    glow_color = template_config.get('glow_color')
    glow_radius = template_config.get('glow_radius', 6)

    # Render
    img = render_arabic_to_pil_image(
        text=arabic_text,
        fontsize=fontsize,
        color=text_color,
        stroke_color='#000000',
        stroke_width=3,
        words_per_line=per_line,
        target_width=TARGET_W - 160,
        font_path=font_path,
        supersample=_supersample_for_quality(quality),
        shadow=True,
        shadow_offset=4,
        shadow_color='#00000080',
        glow_color=glow_color,
        glow_radius=glow_radius,
    )

    # Save to PNG
    os.makedirs(os.path.dirname(output_png_path) or ".", exist_ok=True)
    img.save(output_png_path)
    logging.info(
        f"✅ Text rendered: font={font_name}, template={template}, quality={quality}, "
        f"glow={bool(glow_color)} -> {output_png_path}"
    )
    return output_png_path


def render_text_to_png_with_colors(arabic_text, template, output_png_path,
                                  selected_font=None, text_color='white', stroke_color='black',
                                  quality='medium'):
    """
    Render Arabic text to PNG with custom (auto-detected) colors.
    Used for dynamic text color based on background brightness.
    Per-template font + glow are still respected; only the fill/stroke colors
    are overridden.
    """
    template_config = TEMPLATES.get(template, TEMPLATES['normal'])

    # Resolve font
    font_path, font_name = _resolve_template_font(template_config, selected_font)

    # Word-count aware sizing
    word_count = len(arabic_text.split())
    size_mult = template_config['font_size_mult']
    fontsize, per_line = _fontsize_for_wordcount(word_count, size_mult)

    # Color name -> hex
    color_map = {'white': '#FFFFFF', 'black': '#000000', 'gold': '#FFD700'}
    text_color_hex = color_map.get(text_color.lower(), text_color)
    stroke_color_hex = color_map.get(stroke_color.lower(), stroke_color)

    # Glow comes from the template
    glow_color = template_config.get('glow_color')
    glow_radius = template_config.get('glow_radius', 6)

    img = render_arabic_to_pil_image(
        text=arabic_text,
        fontsize=fontsize,
        color=text_color_hex,
        stroke_color=stroke_color_hex,
        stroke_width=3,
        words_per_line=per_line,
        target_width=TARGET_W - 160,
        font_path=font_path,
        supersample=_supersample_for_quality(quality),
        shadow=True,
        shadow_offset=4,
        shadow_color='#00000080',
        glow_color=glow_color,
        glow_radius=glow_radius,
    )

    os.makedirs(os.path.dirname(output_png_path) or ".", exist_ok=True)
    img.save(output_png_path)
    logging.info(
        f"✅ Text rendered w/ custom colors: font={font_name}, template={template}, "
        f"quality={quality}, text={text_color_hex}, stroke={stroke_color_hex}, "
        f"glow={bool(glow_color)} -> {output_png_path}"
    )
    return output_png_path

# =============================================================================
# STEP 14.5: SEGMENT BUILDER WITH ANIMATIONS
# =============================================================================

def build_segment_ffmpeg(bg_paths, text_png_path, audio_path, duration_sec, output_path,
                        show_text=True, text_animation_filter=None, is_last=True):
    """Build one video segment with FFmpeg, optionally with text animation.

    Phase 2 additions:
      - `text_animation_filter` is now non-None (intro fade/slide/zoom on text)
        when the FEATURE_FLAGS['text_animations'] is on and a template
        animation is set.
      - `is_last=False` appends a 0.4 s outro fade to the final composite
        so the cut to the next segment (or end of video) is soft, not a
        hard jump.  The last segment skips the outro fade to avoid a fade
        to black at the very end of the video.
    """
    # Verify all input files exist and have content
    if show_text:
        if not os.path.exists(text_png_path):
            raise FileNotFoundError(f"Text PNG missing: {text_png_path}")
        if os.path.getsize(text_png_path) < 100:
            raise ValueError(f"Text PNG too small: {os.path.getsize(text_png_path)} bytes")
    else:
        # For no-text mode, just check if file exists (it can be 1x1 placeholder)
        if not os.path.exists(text_png_path):
            raise FileNotFoundError(f"Text PNG placeholder missing: {text_png_path}")

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

    if show_text:
        logging.info(f"Building segment: {n} BGs, duration={duration_sec:.2f}s, part_dur={part_dur:.2f}s, is_last={is_last}")
        logging.info(f"  Text PNG: {text_png_path} ({os.path.getsize(text_png_path)} bytes)")
        logging.info(f"  Audio: {audio_path} ({os.path.getsize(audio_path)} bytes)")
    else:
        logging.info(f"Building segment (no text): {n} BGs, duration={duration_sec:.2f}s, part_dur={part_dur:.2f}s, is_last={is_last}")
        logging.info(f"  Audio: {audio_path} ({os.path.getsize(audio_path)} bytes)")

    # Build FFmpeg command
    common_args = ["-y", "-hide_banner", "-loglevel", "error"]  # Changed to error for more visibility
    inputs = []

    for p in preprocessed:
        inputs.extend(["-stream_loop", "-1", "-i", p])

    if show_text:
        inputs.extend(["-loop", "1", "-i", text_png_path])

    inputs.extend(["-i", audio_path])

    # Phase 2 (T2.5): outro fade.  0.4 s, applied to the final [v] composite
    # so the whole frame (bg + text) eases out before the next segment takes
    # over.  Skipped on the very last segment to avoid a fade-to-black.
    outro_fade_filter = ""
    if FEATURE_FLAGS.get('text_animations', False) and not is_last and show_text:
        outro_d = min(0.4, max(0.1, duration_sec / 2))
        outro_st = max(0.0, duration_sec - outro_d)
        # No leading comma — the label goes on the input side: [vpre]fade=...[v]
        outro_fade_filter = f"fade=t=out:st={outro_st:.3f}:d={outro_d:.3f}:alpha=1[v]"
        # The last filter in the chain will be [v] — chain via the label.
        last_v = "vpre"
    else:
        last_v = "v"

    if n == 1:
        if show_text:
            # Build filter with optional animation
            text_overlay = f"[bg][1:v]overlay=(main_w-overlay_w)/2:(main_h-overlay_h)/2:format=auto"

            # Add animation filter if provided
            if text_animation_filter:
                # Apply animation to text before overlay
                filt = (
                    f"[0:v]trim=duration={duration_sec},setpts=PTS-STARTPTS,fps=30[bg];"
                    f"[1:v]{text_animation_filter}[anim_text];"
                    f"[bg][anim_text]overlay=(main_w-overlay_w)/2:(main_h-overlay_h)/2:format=auto[{last_v}]"
                )
            else:
                filt = (
                    f"[0:v]trim=duration={duration_sec},setpts=PTS-STARTPTS,fps=30[bg];"
                    f"[bg][1:v]overlay=(main_w-overlay_w)/2:(main_h-overlay_h)/2:format=auto[{last_v}]"
                )
            if outro_fade_filter:
                # outro_fade_filter expects [vpre] as the input label
                filt = filt + ";" + f"[{last_v}]{outro_fade_filter}"
                last_v = "v"
            map_args = ["-map", f"[{last_v}]", "-map", "2:a"]
        else:
            filt = f"[0:v]trim=duration={duration_sec},setpts=PTS-STARTPTS,fps=30[{last_v}]"
            if outro_fade_filter:
                filt = filt + ";" + f"[{last_v}]{outro_fade_filter}"
                last_v = "v"
            map_args = ["-map", f"[{last_v}]", "-map", "1:a"]
    else:
        # Multiple BGs
        v_parts = ""
        for i in range(n):
            v_parts += f"[{i}:v]trim=duration={part_dur},setpts=PTS-STARTPTS,fps=30[v{i}];"
        v_parts += "".join([f"[v{i}]" for i in range(n)]) + f"concat=n={n}:v=1:a=0[bg];"

        if show_text:
            # Apply animation to text if provided
            if text_animation_filter:
                filt = v_parts + f"[{n}:v]{text_animation_filter}[anim_text];[bg][anim_text]overlay=(main_w-overlay_w)/2:(main_h-overlay_h)/2:format=auto[{last_v}]"
            else:
                filt = v_parts + f"[bg][{n}:v]overlay=(main_w-overlay_w)/2:(main_h-overlay_h)/2:format=auto[{last_v}]"
            if outro_fade_filter:
                filt = filt + ";" + f"[{last_v}]{outro_fade_filter}"
                last_v = "v"
            map_args = ["-map", f"[{last_v}]", "-map", f"{n+1}:a"]
        else:
            filt = v_parts + f"[bg]null[{last_v}]"
            if outro_fade_filter:
                filt = filt + ";" + f"[{last_v}]{outro_fade_filter}"
                last_v = "v"
            map_args = ["-map", f"[{last_v}]", "-map", f"{n}:a"]

    cmd = [FFMPEG_EXE] + common_args + inputs + [
        "-filter_complex", filt,
    ] + map_args + [
        "-t", str(duration_sec), "-r", "30",
        "-c:v", "libx264", "-preset", "ultrafast", "-threads", "4", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-shortest",
        output_path
    ]

    try:
        logging.info(f"Running FFmpeg command (timeout=300s): {' '.join(cmd[:8])}...")
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300)
        logging.info(f"FFmpeg completed in {result.stderr.count('frame=')} frames")
    except subprocess.TimeoutExpired as e:
        logging.error(f"FFmpeg timeout after 300s - this may be due to large background video")
        # Try with shorter duration as fallback
        try:
            fallback_cmd = cmd.copy()
            fallback_cmd[-1] = output_path.replace('.mp4', '_fallback.mp4')
            # Add or modify quality settings for speed
            if "-preset" in fallback_cmd:
                idx = fallback_cmd.index("-preset")
                fallback_cmd[idx+1] = "ultrafast"
            if "-crf" not in fallback_cmd:
                # Insert CRF before the output path
                fallback_cmd.insert(-1, "-crf")
                fallback_cmd.insert(-1, "35")
            logging.warning("Trying fallback with lower quality...")
            result = subprocess.run(fallback_cmd, check=True, capture_output=True, text=True, timeout=180)
            # Move fallback to original location
            if os.path.exists(fallback_cmd[-1]):
                shutil.move(fallback_cmd[-1], output_path)
        except Exception as fallback_e:
            logging.error(f"Fallback also failed: {fallback_e}")
            raise RuntimeError(f"FFmpeg processing failed - try using shorter ayahs or different background")
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
    Process one ayah using FFmpeg with animations and dynamic features.
    Uses BackgroundRotator to prevent video repetition.
    """
    (reciter_id, surah, ayah, idx, template, bg_style, selected_font,
     show_text, text_animation, auto_text_color, quality, is_last) = args

    try:
        # Download audio (no trimming, faster)
        audio_path = download_audio(reciter_id, surah, ayah, idx)
        duration = get_audio_duration_ffprobe(audio_path)
        logging.debug(f"Segment {idx}: Audio duration = {duration:.2f}s")

        # Fetch text (with cache)
        arabic_text = get_ayah_text(surah, ayah)

        # Select background using rotator to prevent repetition
        bg_path = get_next_background(bg_style, count=1)
        bg_paths = bg_path if isinstance(bg_path, list) else [bg_path]
        logging.debug(f"Segment {idx}: Using background {os.path.basename(bg_paths[0])}")

        # Render text to PNG
        text_png = os.path.join(TEMP_DIR, f"text_{idx:03d}.png")
        segment_out = os.path.join(TEMP_DIR, f"segment_{idx:03d}.mp4")

        if show_text:
            # Get dynamic text color based on background
            template_config = TEMPLATES.get(template, TEMPLATES['normal'])
            template_color = template_config.get('text_color', 'white')

            # Analyze background and get contrasting colors
            text_color, stroke_color = get_contrasting_text_color(
                bg_paths[0], template_color, auto_detect=auto_text_color
            )
            logging.debug(f"Segment {idx}: Text color={text_color}, stroke={stroke_color}")

            # Render with custom colors (Phase 1: quality -> supersample, template font + glow)
            render_text_to_png_with_colors(arabic_text, template, text_png,
                                          selected_font, text_color, stroke_color,
                                          quality=quality)
        else:
            # Create a transparent 1x1 pixel PNG for no-text mode
            from PIL import Image
            transparent = Image.new('RGBA', (1, 1), (0, 0, 0, 0))
            transparent.save(text_png)
            logging.debug(f"Created transparent placeholder: {text_png}")

        # Build segment with animation filter (Phase 2: text animation + outro fade)
        animation_filter = get_ffmpeg_text_animation_filter(text_animation, duration)
        build_segment_ffmpeg(bg_paths, text_png, audio_path, duration, segment_out,
                           show_text=show_text, text_animation_filter=animation_filter,
                           is_last=is_last)

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
                person_name='', selected_font='random', target_duration_seconds=None,
                show_text=True):
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

        # No strict duration cap on ayahs anymore, but keep a safety limit (e.g. 50 ayahs)
        total = last_ayah - start_ayah + 1
        if total > 50:
             last_ayah = start_ayah + 49
             total = 50

        add_log(f'Building {total} ayat from {start_ayah} to {last_ayah}')
        update_progress(10, f'جاري تحضير {total} آيات...')

        # Initialize background rotator to prevent repetition
        init_background_rotator(bg_style)
        logging.info(f"Background rotator initialized for style: {bg_style}")

        # OPTIMIZED: max_workers = total if <=3, else 4
        max_workers = total if total <= 3 else 4
        logging.info(f"Using {max_workers} workers ({total} ayat total)")

        # Get animation and transition config from template
        text_animation = template_config.get('text_animation', 'fade_in')
        video_transition = template_config.get('transition', 'fade')
        auto_text_color = template_config.get('auto_text_color', True)

        logging.info(f"Using text animation: {text_animation}, transition: {video_transition}")

        # Prepare args - now includes rotation index for variety + quality preset
        # + is_last flag (Phase 2 T2.5) so the last segment skips the outro fade.
        total_ayahs = last_ayah - start_ayah + 1
        ayah_args = [
            (reciter_id, surah, ayah, idx, template, bg_style, selected_font, show_text,
             text_animation, auto_text_color, quality, idx == total_ayahs)
            for idx, ayah in enumerate(range(start_ayah, last_ayah + 1), start=1)
        ]

        # Output filename - use ASCII to avoid FFmpeg issues
        surah_name = SURAH_NAMES[surah - 1] if 1 <= surah <= len(SURAH_NAMES) else f"Surah{surah}"
        clean_name = person_name.replace(" ", "_").replace("/", "_").replace("\\", "_") if person_name else "User"
        # Remove Arabic characters for temp filename
        ascii_name = f"{clean_name}_Surah{surah}_Ayah{start_ayah}-{last_ayah}_{quality}_{template}"
        temp_filename = f"{ascii_name}.mp4"
        temp_output_path = os.path.join(TEMP_DIR, temp_filename)

        # Final output with user-friendly filename
        # Format: "Quran_Surah[Number]_[Name]_Ayah[Start-End]_[Name]_[Quality].mp4"
        surah_number = f"{surah:03d}"  # 3-digit format (001, 002, etc.)
        ayah_range = f"{start_ayah}-{last_ayah}"
        user_part = f"_{clean_name}" if clean_name else ""

        # Get Arabic surah name
        surah_name_ar = SURAH_NAMES[surah - 1] if 1 <= surah <= len(SURAH_NAMES) else f"Surah{surah}"
        surah_name_clean = surah_name_ar.replace(" ", "_").replace("/", "_").replace("\\", "_")

        filename = f"Quran_Surah{surah_number}_{surah_name_clean}_Ayah{ayah_range}{user_part}_{quality}.mp4"
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

        # Concatenate with professional crossfade transitions
        add_log('Concatenating segments with crossfade transitions...')
        update_progress(85, 'جاري دمج المقاطع مع انتقالات احترافية...')

        # Always build the concat list file up-front so any fallback can reuse it.
        # This avoids UnboundLocalError on 'list_path' if the crossfade path fails
        # before the list is created.
        list_path = os.path.join(TEMP_DIR, f"concat_{int(time.time() * 1000)}.txt")
        with open(list_path, "w", encoding="utf-8") as f:
            for _, seg_path in segment_results:
                abs_path = os.path.abspath(seg_path).replace(os.sep, '/').replace("'", "'\\''")
                f.write(f"file '{abs_path}'\n")

        cmd_concat = None

        if len(segment_results) <= 1:
            # Single segment - simple concat
            cmd_concat = [
                FFMPEG_EXE, "-y", "-f", "concat", "-safe", "0", "-i", list_path,
                "-c:v", "libx264", "-preset", "ultrafast", "-threads", "4",
                "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart",
                temp_output_path
            ]
        else:
            # Multiple segments - use crossfade for professional transitions
            try:
                # Phase 2 (T2.4): Honor the template's `transition` field and use
                # the *actual* per-segment durations (probed via ffprobe) instead
                # of the previous hardcoded 5 s trim and 4.5 s xfade offset.
                # Each segment is trimmed to its real length; the xfade offset
                # is cumulative-duration of preceding segments - xfade_d.
                xfade_d = 0.5

                # Probe each segment's actual duration
                seg_durations = []
                for _, seg_path in segment_results:
                    try:
                        d = get_audio_duration_ffprobe(seg_path)
                    except Exception as e:
                        logging.warning(f"ffprobe failed for {seg_path}: {e}; defaulting to 5.0s")
                        d = 5.0
                    seg_durations.append(d)
                logging.info(f"Segment durations: {[f'{d:.2f}' for d in seg_durations]}")

                # Resolve transition name from template
                trans_name = template_config.get('transition', 'fade')
                trans_spec = VIDEO_TRANSITIONS.get(trans_name, VIDEO_TRANSITIONS.get('fade'))
                # trans_spec['type'] is the xfade transition key, e.g. 'fade', 'wipeleft'
                xfade_name = trans_spec['type']
                logging.info(f"Using crossfade transition: {trans_name!r} (xfade={xfade_name})")

                filter_complex = []
                # Trim each segment to its actual duration
                for i, (_, seg_path) in enumerate(segment_results):
                    seg_d = seg_durations[i]
                    filter_complex.append(
                        f"[{i}:v]trim=duration={seg_d:.3f},setpts=PTS-STARTPTS[v{i}];"
                        f"[{i}:a]atrim=duration={seg_d:.3f},asetpts=PTS-STARTPTS[a{i}]"
                    )

                # Crossfade between consecutive segments using computed offsets.
                # Each ayah overlaps the next by xfade_d, so the offset of the
                # (i+1)-th xfade is:
                #   sum(durations[0:i+1]) - (i+1) * xfade_d
                # i.e. cumulative_duration minus xfade_d for THIS xfade plus
                # xfade_d for every prior xfade (one per prior overlap).
                cumulative = 0.0
                for i in range(len(segment_results) - 1):
                    cumulative += seg_durations[i]
                    offset = max(0.0, cumulative - (i + 1) * xfade_d)
                    filter_complex.append(
                        f"[v{i}][v{i+1}]xfade=transition={xfade_name}:"
                        f"duration={xfade_d}:offset={offset:.3f}[v{i+1}];"
                        f"[a{i}][a{i+1}]acrossfade=d={xfade_d}[a{i+1}]"
                    )

                # Final output — null filters are required so we can map both
                # video and audio streams to the named output labels.
                last_v = f"v{len(segment_results) - 1}"
                last_a = f"a{len(segment_results) - 1}"
                filter_complex.append(
                    f"[{last_v}]null[outv];"
                    f"[{last_a}]anull[outa]"
                )

                filter_complex_str = ';'.join(filter_complex)

                inputs = []
                for _, seg_path in segment_results:
                    inputs.extend(["-i", seg_path])

                cmd_concat = [
                    FFMPEG_EXE, "-y"
                ] + inputs + [
                    "-filter_complex", filter_complex_str,
                    "-map", "[outv]", "-map", "[outa]",
                    "-c:v", "libx264", "-preset", "ultrafast", "-threads", "4",
                    "-c:a", "aac", "-b:a", "192k",
                    "-movflags", "+faststart",
                    temp_output_path
                ]

            except Exception as e:
                logging.warning(f"Crossfade setup failed, using simple concat: {e}")

                # Fallback to simple concat (list_path already exists)
                cmd_concat = [
                    FFMPEG_EXE, "-y", "-f", "concat", "-safe", "0", "-i", list_path,
                    "-c:v", "libx264", "-preset", "ultrafast", "-threads", "4",
                    "-c:a", "aac", "-b:a", "192k",
                    "-af", "acrossfade=d=0.5",  # Simple audio crossfade
                    "-movflags", "+faststart",
                    temp_output_path
                ]

        try:
            if cmd_concat is None:
                raise ValueError("No concat command generated")

            logging.info(f"Running Concat: {' '.join(cmd_concat)}")
            result = subprocess.run(cmd_concat, check=True, capture_output=True, text=True, timeout=600)
        except subprocess.CalledProcessError as e:
            logging.error(f"FFmpeg Concat Failed with crossfade effects!")
            logging.error(f"STDOUT: {e.stdout}")
            logging.error(f"STDERR: {e.stderr}")

            # Fallback: try without fade effects (list_path already exists from the top)
            logging.info("Trying fallback without fade effects...")

            cmd_fallback = [
                FFMPEG_EXE, "-y", "-f", "concat", "-safe", "0", "-i", list_path,
                "-c", "copy",  # Simple stream copy
                "-movflags", "+faststart",
                temp_output_path
            ]

            try:
                logging.info(f"Running Fallback: {' '.join(cmd_fallback)}")
                result = subprocess.run(cmd_fallback, check=True, capture_output=True, text=True, timeout=600)
            except subprocess.CalledProcessError as fallback_e:
                logging.error(f"Fallback also failed!")
                logging.error(f"Fallback STDERR: {fallback_e.stderr}")

                # Last resort: re-encode everything (list_path already exists)
                logging.info("Last resort: re-encoding all segments...")
                cmd_last_resort = [
                    FFMPEG_EXE, "-y", "-f", "concat", "-safe", "0", "-i", list_path,
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                    "-c:a", "aac", "-b:a", "192k",
                    "-movflags", "+faststart",
                    temp_output_path
                ]
                subprocess.run(cmd_last_resort, check=True, capture_output=True, text=True, timeout=600)

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

        # Clean up temp files after successful video
        cleanup_after_video()

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
    selected_font = data.get('selectedFont', 'random')
    target_duration_seconds = data.get('targetDurationSeconds')
    show_text = data.get('showText', True)

    reset_progress()

    thread = threading.Thread(
        target=build_video,
        args=(reciter_id, surah, start_ayah, end_ayah, quality,
              format_type, template, person_name, selected_font, target_duration_seconds,
              show_text),
        daemon=True
    )
    thread.start()

    return jsonify({'success': True, 'message': 'بدأ إنشاء الفيديو'})

@app.route('/api/progress', methods=['GET'])
def get_progress():
    return jsonify(current_progress)

@app.route('/api/preview', methods=['POST'])
def preview_video():
    """Generate a preview of the first ayah (one verse)."""
    global current_progress
    if current_progress['is_running']:
        return jsonify({'error': 'عملية أخرى قيد التنفيذ'}), 400

    data = request.json
    reciter_id = data.get('reciter')
    surah = int(data.get('surah', 1))
    ayah = int(data.get('ayah', data.get('startAyah', 1)))
    template = data.get('template', 'normal')
    show_text = data.get('showText', True)

    reset_progress()
    thread = threading.Thread(
        target=build_video,
        args=(reciter_id, surah, ayah, ayah, 'low', 'reels', template, '', selected_font, None, show_text),
        daemon=True
    )
    thread.start()
    return jsonify({'success': True, 'message': 'بدأ إنشاء المعاينة'})

@app.route('/api/config', methods=['GET'])
def get_config():
    # Expose available fonts in fonts/ for the UI
    available_fonts = []
    try:
        if os.path.isdir(FONT_DIR):
            available_fonts = sorted([
                f for f in os.listdir(FONT_DIR)
                if f.lower().endswith(('.ttf', '.otf'))
            ])
    except Exception as e:
        logging.warning(f"Failed to list fonts: {e}")

    return jsonify({
        'surahs': SURAH_NAMES,
        'verseCounts': VERSE_COUNTS,
        'reciters': RECITERS_MAP,
        'qualityPresets': list(QUALITY_PRESETS.keys()),
        'outputFormats': list(OUTPUT_FORMATS.keys()),
        'templates': list(TEMPLATES.keys()),
        'workingFont': os.path.basename(WORKING_FONT) if WORKING_FONT else None,
        'availableFonts': available_fonts,
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

    # Startup cleanup operations
    logging.info('Performing startup cleanup...')
    cleanup_orphaned_temp_files()
    cleanup_audio_cache()  # Clean cache on startup

    # Initialize font system (after all functions are defined)
    init_font_system()

    # Initialize background cache
    init_bg_cache()

    # webbrowser.open('http://127.0.0.1:5000')
    app.run(host='127.0.0.1', port=5000, debug=False, threaded=True)
