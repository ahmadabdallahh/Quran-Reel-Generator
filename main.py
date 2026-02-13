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

# Auto-detect available fonts
def get_available_fonts():
    """Get all .ttf fonts from the fonts directory"""
    fonts = []
    if os.path.exists(FONT_DIR):
        for file in os.listdir(FONT_DIR):
            if file.lower().endswith('.ttf'):
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

def get_random_font():
    """Get a random font from available fonts"""
    try:
        fonts = []
        if os.path.exists(FONT_DIR):
            for file in os.listdir(FONT_DIR):
                if file.lower().endswith('.ttf'):
                    fonts.append(os.path.join(FONT_DIR, file))

        if fonts:
            selected_font = random.choice(fonts)
            logging.info(f"Randomly selected font: {os.path.basename(selected_font)}")
            return selected_font
        else:
            # Fallback to default
            return os.path.join(FONT_DIR, "DUBAI-BOLD.TTF")
    except Exception as e:
        logging.error(f"Error selecting random font: {e}")
        return os.path.join(FONT_DIR, "DUBAI-BOLD.TTF")

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

import requests as http_requests
from pydub import AudioSegment

TARGET_W = 1080
TARGET_H = 1920

# Quality presets
QUALITY_PRESETS = {
    'low': {'fps': 15, 'codec': 'libx264', 'preset': 'ultrafast', 'threads': 2},
    'medium': {'fps': 24, 'codec': 'libx264', 'preset': 'fast', 'threads': 4},
    'high': {'fps': 30, 'codec': 'libx264', 'preset': 'medium', 'threads': 6}
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
    from moviepy.editor import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip, concatenate_videoclips
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
    print(f'>>> {message}', flush=True)

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
    url = f'https://everyayah.com/data/{reciter_id}/{fn}'
    out = os.path.join(AUDIO_DIR, f'part{idx}.mp3')
    r = http_requests.get(url)
    r.raise_for_status()
    with open(out, 'wb') as f:
        f.write(r.content)
    snd = AudioSegment.from_file(out, 'mp3')
    start = detect_leading_silence(snd, snd.dBFS - 16)
    end = detect_trailing_silence(snd, snd.dBFS - 16)
    trimmed = snd[start:len(snd) - end]
    trimmed.export(out, format='mp3')
    return out

def get_ayah_text(surah, ayah):
    try:
        resp = http_requests.get(f'https://api.alquran.cloud/v1/ayah/{surah}:{ayah}/quran-uthmani')
        resp.raise_for_status()
        return resp.json()['data']['text']
    except Exception as e:
        logging.error(f"Failed to fetch ayah text: {e}")
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
    """Wrap text into multiple lines based on word count per line"""
    words = text.split()
    lines = [' '.join(words[i:i + per_line]) for i in range(0, len(words), per_line)]
    return '\n'.join(lines)

def create_text_clip(arabic, translation="", duration=5, template='normal', video_height=1080):
    """
    Create enhanced text clip with Arabic and optional English translation.
    Includes professional visual effects and template support.
    """
    template_config = TEMPLATES.get(template, TEMPLATES['normal'])
    words = arabic.split()
    word_count = len(words)

    # Dynamic settings based on text length and template
    size_mult = template_config['font_size_mult']
    if word_count > 60:
        fontsize = int(45 * size_mult)
        per_line = 7
    elif word_count > 40:
        fontsize = int(55 * size_mult)
        per_line = 6
    elif word_count > 25:
        fontsize = int(65 * size_mult)
        per_line = 5
    elif word_count > 15:
        fontsize = int(75 * size_mult)
        per_line = 4
    else:
        fontsize = int(90 * size_mult)
        per_line = 3

    wrapped_arabic = wrap_text(arabic, per_line)

    # Create Arabic text with enhanced styling
    color = template_config['text_color']
    if color == 'gold':
        text_color = '#FFD700'
    elif color == 'bright':
        text_color = '#00FFFF'
    else:
        text_color = 'white'

    # Use random font from available fonts for variety
    selected_font = get_random_font()

    ar_clip = TextClip(
        wrapped_arabic,
        font=selected_font,
        fontsize=fontsize,
        color=text_color,
        stroke_color='black',
        stroke_width=2,
        method='caption',
        size=(TARGET_W - 100, None),
        align='center',
    ).set_duration(duration).set_position('center')

    # Add professional fade effects
    ar_clip = ar_clip.fadein(0.3).fadeout(0.3)

    return ar_clip


def pick_bg(style='nature'):
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

        selected = random.choice(files)
        logging.info(f"Selected background: {selected}")
        return os.path.join(VISION_DIR, selected)
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
        "-preset", "veryfast",
        "-crf", "23"
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
    reciter_id, surah, ayah, idx, template, bg_style = args

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

        # Create background
        seg_bg = prepare_bg_clip(pick_bg(bg_style), dur)

        # Create text with template (Arabic only)
        ar_clip = create_text_clip(ar, "", dur, template)

        # Composite
        seg = CompositeVideoClip([seg_bg, ar_clip], size=(TARGET_W, TARGET_H)).set_audio(audio)

        logging.info(f"Completed ayah {surah}:{ayah}")
        return seg

    except Exception as e:
        logging.error(f"Error processing ayah {surah}:{ayah}: {e}")
        raise

def prepare_bg_clip(path, duration, target_w=TARGET_W, target_h=TARGET_H):
    path = get_preprocessed_bg(path, target_w=target_w, target_h=target_h)
    bg = VideoFileClip(path, audio=False)
    logging.info(f"BG source: {path} size={bg.w}x{bg.h}")
    bg = bg.fx(vfx.loop, duration=duration).subclip(0, duration)

    if bg.h != target_h:
        bg = bg.resize(height=target_h)

    if bg.w < target_w:
        bg = bg.resize(width=target_w)

    bg = bg.crop(x_center=bg.w / 2, y_center=bg.h / 2, width=target_w, height=target_h)
    logging.info(f"BG prepared size={bg.w}x{bg.h} target={target_w}x{target_h}")
    return bg

def build_video(reciter_id, surah, start_ayah, end_ayah=None, quality='medium', format_type='reels', template='normal', person_name=''):
    """
    Enhanced video builder with quality presets, templates, and parallel processing.
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

        add_log('[1] Clearing output folders...')
        update_progress(5, 'جاري تنظيف ملفات الإخراج...')
        clear_outputs()
        max_ayah = VERSE_COUNTS[surah]
        if end_ayah is None:
            last_ayah = min(start_ayah + 9, max_ayah)
        else:
            last_ayah = min(end_ayah, max_ayah)

        if last_ayah < start_ayah:
            last_ayah = start_ayah

        total = last_ayah - start_ayah + 1

        # Check duration limits for format
        if format_config.get('duration'):
            max_duration = format_config['duration']
            logging.info(f"Format {format_type} max duration: {max_duration}s")

        add_log(f'[2] Preparing {total} آيات (from {start_ayah} to {last_ayah}) with {quality} quality')
        update_progress(10, f'جاري تحضير {total} آيات بجودة {quality}...')

        # Parallel processing with resource monitoring
        cpu, mem = monitor_resources()
        max_workers = 1 if mem > 75 else (2 if mem > 50 else 3)
        logging.info(f"Using {max_workers} parallel workers (CPU: {cpu}%, MEM: {mem}%)")

        # Prepare arguments for parallel processing
        ayah_args = [(reciter_id, surah, ayah, idx, template, bg_style)
                     for idx, ayah in enumerate(range(start_ayah, last_ayah + 1), start=1)]

        if max_workers > 1:
            # Parallel processing
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_ayah = {executor.submit(process_single_ayah, args): args for args in ayah_args}

                for i, future in enumerate(concurrent.futures.as_completed(future_to_ayah), 1):
                    try:
                        clip = future.result()
                        clips.append(clip)
                        progress = 10 + (70 * i / total)
                        update_progress(int(progress), f'تم معالجة {i}/{total} آيات...')
                    except Exception as e:
                        logging.error(f"Ayah processing failed: {e}")
                        raise
        else:
            # Sequential processing (fallback)
            for idx, args in enumerate(ayah_args, 1):
                progress_per_ayah = 70 / total
                base_progress = 10 + (idx - 1) * progress_per_ayah

                clip = process_single_ayah(args)
                clips.append(clip)

                update_progress(int(base_progress + progress_per_ayah), f'تم معالجة الآية {idx}/{total}...')

        add_log('[4] Concatenating segments...')
        update_progress(85, 'جاري دمج المقاطع...')
        final = concatenate_videoclips(clips, method='chain')

        # Generate filename with person name, date, and surah name
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        date_str = datetime.datetime.now().strftime("%d-%m-%Y")

        # Get surah name
        surah_name = SURAH_NAMES[surah - 1] if 1 <= surah <= len(SURAH_NAMES) else f"Surah{surah}"

        # Clean person name for filename (remove special characters)
        clean_person_name = person_name.replace(" ", "_").replace("/", "_").replace("\\", "_") if person_name else "User"

        # Create new filename format: PersonName_Date_SurahName_Ayahs_Quality_Template
        filename = f"{clean_person_name}_{date_str}_{surah_name}_Ayah{start_ayah}-{end_ayah}_{quality}_{template}.mp4"
        out = os.path.join(VIDEO_DIR, filename)

        add_log(f'[5] Writing final video -> {out}')
        update_progress(90, 'جاري كتابة الفيديو النهائي...')

        # Enhanced video writing with quality presets
        ffmpeg_params = []
        if os.name != 'nt':  # Not Windows
            ffmpeg_params.append('-movflags')
            ffmpeg_params.append('+faststart')

        final.write_videofile(
            out,
            fps=quality_config['fps'],
            codec=quality_config['codec'],
            audio_codec='aac',
            audio_bitrate='192k',
            verbose=False,
            preset=quality_config['preset'],
            threads=quality_config['threads'],
            ffmpeg_params=ffmpeg_params
        )

        add_log('[6] Done!')
        update_progress(100, 'تم بنجاح!')
        current_progress['is_complete'] = True
        current_progress['output_path'] = out

    except Exception as e:
        logger_error_msg = f"Error in build_video: {str(e)}\n{traceback.format_exc()}"
        logging.error(logger_error_msg)
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

    reset_progress()

    # Start video generation in background thread with enhanced parameters
    thread = threading.Thread(
        target=build_video,
        args=(reciter_id, surah, start_ayah, end_ayah, quality, format_type, template, person_name),
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
    """Generate a 5-second preview of the first ayah"""
    try:
        data = request.json
        reciter_id = data.get('reciter')
        surah = int(data.get('surah', 1))
        ayah = int(data.get('ayah', 1))
        template = data.get('template', 'normal')
        quality = 'low'  # Always use low quality for preview

        # Generate preview with just one ayah
        preview_thread = threading.Thread(
            target=build_video,
            args=(reciter_id, surah, ayah, ayah, quality, 'reels', template),
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
