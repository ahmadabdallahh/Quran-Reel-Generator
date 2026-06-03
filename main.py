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
# STEP 0: ENVIRONMENT LOADING  (refactor P1-9)
# =============================================================================
# Reads ``.env`` from the current working directory (or any parent) into
# ``os.environ`` BEFORE any of the path / port / size constants below are
# resolved.  ``load_dotenv()`` does NOT clobber values that are already set
# in the real environment, so production shells still win over ``.env``.

from dotenv import load_dotenv
load_dotenv()

def _env(key, default=None, cast=str):
    """Read an env var, falling back to ``default`` if unset/empty.
    The default is type-coerced via ``cast`` so numeric / bool flags work
    without the caller having to do ``int(os.environ.get(...))`` boilerplate.
    Invalid values fall back to the default and log a warning.
    """
    raw = os.environ.get(key)
    if raw is None or raw == "":
        return cast(default) if default is not None else default
    try:
        return cast(raw)
    except (TypeError, ValueError):
        logging.warning(f"Invalid value for {key}={raw!r}; using default {default!r}")
        return cast(default) if default is not None else default


def _env_path(key, default, base_dir=None):
    """Read a filesystem path env var with EXEC_DIR-relative resolution.

    - If the env var is set AND the value is an absolute path, it's returned as-is.
    - If the env var is set AND the value is relative, it's resolved against ``base_dir``.
    - If the env var is unset/empty, ``default`` is used (resolved against ``base_dir``
      when ``default`` is also relative).

    Defaults ``base_dir`` to ``EXEC_DIR`` so the common case of project-relative
    layout doesn't need to spell it out at every call site.
    """
    if base_dir is None:
        base_dir = EXEC_DIR
    raw = os.environ.get(key)
    if raw is None or raw == "":
        rel = default
    else:
        rel = raw
    if os.path.isabs(rel):
        return rel
    return os.path.join(base_dir, rel)

# =============================================================================
# Refactor P1-1 (scoped split): leaf modules extracted from this file.
# Re-exported at module level below so existing ``import main; main.X``
# callers and ``from main import X`` keep working unchanged.
# =============================================================================
from quran_reels.config import (
    FEATURE_FLAGS,
    QUALITY_PRESETS,
    OUTPUT_FORMATS,
    TEMPLATES,
    VIDEO_TRANSITIONS,
    VERSE_COUNTS,
    SURAH_NAMES,
    RECITERS_MAP,
    BISMILLAH_TEXT,
    BISMILLAH_DURATION_SEC,
    BISMILLAH_SKIP_SURAHS,
)
from quran_reels.services.contrast import (
    analyze_background_brightness,
    get_contrasting_text_color,
)
from quran_reels.services.animation import get_ffmpeg_text_animation_filter
from quran_reels.services.background import (
    BackgroundRotator,
    bg_rotator,
    init_background_rotator,
    get_next_background,
)
from quran_reels.utils.progress import current_progress

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

log_path = _env_path("QURAN_LOG_PATH", "runlog.txt")
logging.basicConfig(filename=log_path, level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s', force=True)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
logging.getLogger().addHandler(console_handler)

logging.info("--- Quran Reels Generator (Refactored) ---")
logging.info(f"Exec Dir: {EXEC_DIR}")
logging.info(f"Bundle Dir: {BUNDLE_DIR}")
logging.info(f"Log path: {log_path}")

# =============================================================================
# STEP 3: TEMPORARY DIRECTORY MANAGEMENT (NEW: replaces static audio folder)
# =============================================================================

# Create temp directory inside project structure that auto-cleans on exit
TEMP_DIR = _env("QURAN_TEMP_DIR", os.path.join(EXEC_DIR, "temp"))
os.makedirs(TEMP_DIR, exist_ok=True)
logging.info(f"Temp directory: {TEMP_DIR}")

# Create persistent audio cache directory
AUDIO_CACHE_DIR = _env("QURAN_AUDIO_CACHE_DIR", os.path.join(EXEC_DIR, "cache", "audio"))
os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)
logging.info(f"Audio cache directory: {AUDIO_CACHE_DIR}")

# Cache management
AUDIO_CACHE_MAX_SIZE_MB = _env("QURAN_AUDIO_CACHE_MAX_SIZE_MB", 500, int)  # Maximum cache size in MB
AUDIO_CACHE_MAX_FILES = _env("QURAN_AUDIO_CACHE_MAX_FILES", 1000, int)    # Maximum number of files

def get_cached_audio_path(reciter_id, surah, ayah):
    """Get cached audio file path"""
    fn = f'{surah:03d}{ayah:03d}.mp3'
    reciter_dir = os.path.join(AUDIO_CACHE_DIR, str(reciter_id))
    os.makedirs(reciter_dir, exist_ok=True)
    return os.path.join(reciter_dir, fn)


# =============================================================================
# STEP 3.5: JOB CONTEXT — PER-VIDEO UNIQUE FILENAMES (BUG FIX)
# =============================================================================
# Every video build gets a unique ``job_id`` (8-char hex) so its temp files
# (audio, text PNG, segment, concat list, chunk) cannot collide with any
# other build, including:
#
#   * a previous build's leftovers in ``TEMP_DIR`` (the temp dir is
#     auto-cleaned on exit, but two consecutive builds in the same
#     process were reusing ``audio_001.mp3`` etc. and silently
#     cross-pollinating),
#   * a parallel build started in the same process (preview vs. main
#     generate, or any future concurrent job),
#   * a build that crashed mid-run and left files behind.
#
# The :class:`JobContext` holds the id and provides per-resource
# path builders.  The active context is stored in ``_current_job``;
# :func:`start_new_job` is called at the top of every build (and on
# the API entry points) to refresh it.

import uuid


class JobContext:
    """Holds the unique ``job_id`` for one video build and builds
    per-resource temp paths.

    All paths are absolute, normalised through :func:`os.path.join`
    against :data:`TEMP_DIR`, and include the job_id so they can never
    collide with another build.
    """

    __slots__ = ("job_id", "created_at")

    def __init__(self, job_id: str | None = None):
        # 8 hex chars = 32 bits = 4 billion possible ids; more than
        # enough to make accidental collisions astronomically unlikely
        # within a single process lifetime.
        self.job_id = job_id or uuid.uuid4().hex[:8]
        self.created_at = time.time()

    # ---- per-ayah paths ----

    def audio_path(self, idx: int) -> str:
        """Per-ayah downloaded/reciter-speed-not-applied audio."""
        return os.path.join(TEMP_DIR, f"{self.job_id}_audio_{idx:03d}.mp3")

    def sped_path(self, idx: int) -> str:
        """Per-ayah audio after the reciter_speed atempo pre-pass."""
        return os.path.join(TEMP_DIR, f"{self.job_id}_audio_{idx:03d}_sped.mp3")

    def text_png_path(self, idx: int) -> str:
        """Per-ayah rendered Arabic text PNG."""
        return os.path.join(TEMP_DIR, f"{self.job_id}_text_{idx:03d}.png")

    def segment_path(self, idx: int) -> str:
        """Per-ayah muxed video segment (bg + text + audio)."""
        return os.path.join(TEMP_DIR, f"{self.job_id}_segment_{idx:03d}.mp4")

    # ---- Bismillah (single segment, ayah_num=0) ----

    def bismillah_text_png(self) -> str:
        return os.path.join(TEMP_DIR, f"{self.job_id}_text_000_bismillah.png")

    def bismillah_audio(self) -> str:
        return os.path.join(TEMP_DIR, f"{self.job_id}_audio_000_bismillah.mp3")

    def bismillah_segment(self) -> str:
        return os.path.join(TEMP_DIR, f"{self.job_id}_segment_000_bismillah.mp4")

    # ---- concat / chunk / final-output paths ----

    def concat_list_path(self) -> str:
        """Concat demuxer list for the final crossfade/merge step."""
        # 8-char job_id + millisecond timestamp = effectively unique.
        return os.path.join(TEMP_DIR, f"{self.job_id}_concat_{int(time.time() * 1000)}.txt")

    def chunk_list_path(self, ci: int) -> str:
        return os.path.join(TEMP_DIR, f"{self.job_id}_chunk_{ci:03d}_{int(time.time() * 1000)}.txt")

    def chunk_video_path(self, ci: int) -> str:
        return os.path.join(TEMP_DIR, f"{self.job_id}_chunk_{ci:03d}_{int(time.time() * 1000)}.mp4")

    def temp_output_path(self, ascii_name: str) -> str:
        """In-progress final mp4 in TEMP_DIR (gets renamed/moved to
        ``outputs/video/`` after the crossfade/merge step)."""
        return os.path.join(TEMP_DIR, f"{self.job_id}_{ascii_name}")

    def final_output_path(self, ascii_name: str) -> str:
        """Final user-facing mp4 in ``outputs/video/``.  Includes the
        job_id suffix so two consecutive builds of the exact same
        surah+ayahs+quality+template+user-name do NOT overwrite each
        other — see ``bug.md`` Issue 2 P0 #7."""
        base, ext = os.path.splitext(ascii_name)
        # Defensive: ensure the output directory exists even if the
        # caller didn't call ``os.makedirs(VIDEO_DIR)`` explicitly.
        try:
            os.makedirs(VIDEO_DIR, exist_ok=True)
        except Exception:
            pass
        return os.path.join(VIDEO_DIR, f"{base}_{self.job_id}{ext}")


_current_job: "JobContext | None" = None
_current_job_lock = threading.Lock()

# Per-thread job context.  ``start_new_job`` is called from the API
# entry point's worker thread; it sets the value for *that* thread.
# Any code that runs in a child thread (ThreadPoolExecutor worker,
# asyncio task) needs its own value — otherwise the workers from two
# parallel builds would all see whichever job_id was written last
# and collide on temp filenames (see ``bug.md`` Issue 2 P0 #5
# "ThreadPool race conditions").
_job_local = threading.local()


def start_new_job() -> JobContext:
    """Start a fresh job context for one video build.

    Each calling thread gets its own :class:`JobContext` — the context
    is stored in a :class:`threading.local` so two parallel builds
    (e.g. a preview while the main build is still running) cannot
    trample each other's temp filenames.

    Also resets per-build mutable state that must NOT leak across
    builds (circuit-breaker counters, etc.).  See ``bug.md`` Issue 2
    P0 #2 ("Global mutable state").  The circuit-breaker reset is
    guarded by a global lock so two threads can't race to reset it
    mid-build.
    """
    global _circuit_breaker_failures, _circuit_breaker_last_failure
    ctx = JobContext()
    _job_local.ctx = ctx
    with _current_job_lock:
        # Mirror to module-level so legacy / non-threaded code that
        # reads ``_current_job`` still works.
        global _current_job
        _current_job = ctx
        # Reset the per-build circuit breaker.  Without this, a long
        # stretch of download failures on a previous build leaves the
        # breaker in "open" state and the next build is rejected for
        # the next 60 s even though it may target a different reciter
        # / network / etc.
        _circuit_breaker_failures = 0
        _circuit_breaker_last_failure = 0
    logging.info(f"Started new job: job_id={ctx.job_id}")
    return ctx


def current_job() -> JobContext:
    """Return the active :class:`JobContext` for the current thread,
    creating a default one if none exists.  Always safe to call.

    Resolution order:
      1. This thread's ``_job_local.ctx`` (set by ``start_new_job``
         when the API entry point launched the build), or
      2. A lazily-created default context (used by tests / smoke
         scripts / anything that didn't go through the API).
    """
    ctx = getattr(_job_local, "ctx", None)
    if ctx is not None:
        return ctx
    # Lazy fallback: create a context in a NEW thread slot so we
    # don't pollute the parent's thread-local.
    return start_new_job()


def _compute_xfade_pairs(transition_style, n, xfade_d):
    """Return a list of booleans of length ``n-1`` marking which consecutive
    segment pairs get a real xfade (True) vs a hard cut with xfade_d=0 (False).

    transition_style:
      - cinematic : False * (n-1)  -- no xfade, rely on per-segment fade in/out
      - cut       : False * (n-1)  -- hard cuts only
      - dynamic   : True  * (n-1)  -- xfade every consecutive pair
      - smooth    : True every 3rd pair (n//3); hard cut the rest
      - unknown   : treated as dynamic
    """
    if n <= 1:
        return []
    if transition_style in ('cinematic', 'cut'):
        return [False] * (n - 1)
    if transition_style == 'dynamic':
        return [True] * (n - 1)
    if transition_style == 'smooth':
        every = max(1, n // 3)
        return [((i + 1) % every == 0) for i in range(n - 1)]
    # Unknown / future styles default to dynamic for visual continuity
    return [True] * (n - 1)


def _split_into_chunks(is_xfade_pair):
    """Group consecutive segment indices into "chunks" separated by xfade
    boundaries.  Each chunk is a list of indices that should be hard-cut
    together (via the concat demuxer) before being xfaded with the next
    chunk.

    Example: is_xfade_pair = [F, T, F, T, F, T] for n=7 segments
             => chunks = [[0, 1], [2, 3], [4, 5], [6]]
    """
    n = len(is_xfade_pair) + 1
    chunks = []
    current = [0]
    for i, is_xfade in enumerate(is_xfade_pair):
        if is_xfade:
            chunks.append(current)
            current = [i + 1]
        else:
            current.append(i + 1)
    chunks.append(current)
    return chunks


def _premerge_chunks(chunk_groups, segment_results, seg_durations):
    """For each chunk of 1 segment, return the original segment path as-is.
    For each chunk of 2+ segments, pre-merge them via the ffmpeg concat
    demuxer into a single mp4 in TEMP_DIR.  Returns:
        (chunk_paths, chunk_durations) where chunk_paths[i] is a string
        file path and chunk_durations[i] is the summed duration.
    """
    chunk_paths = []
    chunk_durations = []
    for ci, chunk in enumerate(chunk_groups):
        chunk_dur = sum(seg_durations[idx] for idx in chunk)
        if len(chunk) == 1:
            # Single-segment chunk — use the original segment file
            chunk_paths.append(segment_results[chunk[0]][1])
            chunk_durations.append(chunk_dur)
            continue
        # Multi-segment chunk: pre-merge via concat demuxer
        list_path = current_job().chunk_list_path(ci)
        with open(list_path, 'w', encoding='utf-8') as f:
            for idx in chunk:
                _, seg_path = segment_results[idx]
                abs_path = os.path.abspath(seg_path).replace(os.sep, '/').replace("'", "'\\''")
                f.write(f"file '{abs_path}'\n")
        out_path = current_job().chunk_video_path(ci)
        cmd = [
            FFMPEG_EXE, '-y', '-f', 'concat', '-safe', '0', '-i', list_path,
            '-c:v', 'libx264', '-preset', 'ultrafast', '-threads', '4',
            '-c:a', 'aac', '-b:a', '192k',
            '-movflags', '+faststart',
            out_path,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0 or not os.path.exists(out_path):
            raise RuntimeError(
                f"Chunk pre-merge failed for chunk {ci}: {res.stderr.strip()}"
            )
        chunk_paths.append(out_path)
        chunk_durations.append(chunk_dur)
        logging.info(f"Pre-merged chunk {ci} ({len(chunk)} segments, {chunk_dur:.2f}s) -> {out_path}")
    return chunk_paths, chunk_durations


# Default audio length used when an ayah is not yet in the cache and the
# target_duration_seconds cap is being estimated.  Conservative — actual
# recitation is usually shorter.
_AYAH_DURATION_ESTIMATE_SEC = 5.0


def _estimate_ayah_duration(reciter_id, surah, ayah):
    """Return the cached audio duration of one ayah, or a default if
    not yet cached.  Used to pre-compute the target_duration_seconds cap
    before the parallel download pool opens.
    """
    p = get_cached_audio_path(reciter_id, surah, ayah)
    if os.path.exists(p) and os.path.getsize(p) > 1000:
        try:
            return get_audio_duration_ffprobe(p)
        except Exception:
            pass
    return _AYAH_DURATION_ESTIMATE_SEC

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
# STEP 4: FIND BINARIES (FFMPEG, FFprobe)
# =============================================================================
# ImageMagick was previously probed here (is_image_magick, IM_MAGICK_EXE,
# IM_HOME) but every consumer of those names was removed in earlier
# refactors.  The pure-FFmpeg pipeline doesn't need ImageMagick.

def find_binary(portable_path, system_name):
    if os.path.isfile(portable_path):
        return portable_path
    return shutil.which(system_name)

FFMPEG_EXE = _env("QURAN_FFMPEG_EXE") or find_binary(os.path.join(BUNDLE_DIR, "bin", "ffmpeg", "ffmpeg.exe"), "ffmpeg")
FFPROBE_EXE = _env("QURAN_FFPROBE_EXE") or find_binary(os.path.join(BUNDLE_DIR, "bin", "ffmpeg", "ffprobe.exe"), "ffprobe")
if not FFPROBE_EXE and FFMPEG_EXE:
    prob_path = os.path.join(os.path.dirname(FFMPEG_EXE), "ffprobe.exe")
    if os.path.isfile(prob_path): FFPROBE_EXE = prob_path
    else: FFPROBE_EXE = shutil.which("ffprobe")

VISION_DIR = _env("QURAN_VISION_DIR", os.path.join(BUNDLE_DIR, "vision"))
UI_PATH = _env("QURAN_UI_PATH", os.path.join(BUNDLE_DIR, "UI.html"))

OUT_DIR = _env("QURAN_OUT_DIR", os.path.join(EXEC_DIR, "outputs"))
VIDEO_DIR = os.path.join(OUT_DIR, "video")
BG_CACHE_DIR = os.path.join(OUT_DIR, "bg_cache")
FONT_DIR = _env("QURAN_FONT_DIR", os.path.join(EXEC_DIR, "fonts"))
FONT_CACHE_DIR = os.path.join(FONT_DIR, "_cache")

# =============================================================================
# STEP 5: UNIFIED FONT SYSTEM (NEW: scan once, store WORKING_FONT)
# =============================================================================

WORKING_FONT = None  # Global variable - best Arabic font found


# Per-font rendering tuning.  Different fonts ship with different design
# metrics: Uthman TN1 is laid out for print (~18pt) and looks tiny at
# 80px; Tajawal Bold has very thick strokes that need a thinner outline
# to stay legible; Kufi fonts have square corners that look harsh with
# the default stroke.  Each entry adjusts the rendered fontsize and
# stroke width relative to the caller's values so the *visual* weight
# is consistent regardless of which font is active.
#
# Keys are font basenames (case-sensitive).  Values are dicts of
# multipliers applied at render time:
#   * ``size_mult``   - multiplier on the requested fontsize.
#   * ``stroke_mult`` - multiplier on the requested stroke_width.
#   * ``shadow_mult`` - multiplier on the requested shadow_offset.
#
# Fonts not in the table are rendered with the requested values
# unchanged.  This is intentionally a *small* set — the goal is to
# fix the worst offenders, not to perfectly tune every font.
_FONT_RENDER_TUNING: dict = {
    # Uthman TN1 is designed for ~18pt Quran print; bump the size
    # so it reads well on 1080p video, and reduce stroke so the
    # delicate hooks don't get muddied.
    "UthmanTN1-Ver10.otf":          {"size_mult": 1.25, "stroke_mult": 0.85, "shadow_mult": 1.0},
    # DigitalMadina & DigitalKhatt are Uthmani-madinah; they look
    # similar to Uthman TN1 but ship at different scales.
    "DigitalKhatt-OldMadina.otf":   {"size_mult": 1.05, "stroke_mult": 0.95, "shadow_mult": 1.0},
    "DigitalMadina-NON V1.ttf":     {"size_mult": 1.05, "stroke_mult": 0.95, "shadow_mult": 1.0},
    "Elgharib-KFGQPCHafs.V10.ttf":  {"size_mult": 1.10, "stroke_mult": 0.90, "shadow_mult": 1.0},
    "Almadinah1.otf":               {"size_mult": 1.10, "stroke_mult": 0.90, "shadow_mult": 1.0},
    "Almadinah2.otf":               {"size_mult": 1.10, "stroke_mult": 0.90, "shadow_mult": 1.0},
    # Tajawal Bold has heavy strokes; thin the outline so the text
    # doesn't look "doubled".
    "Tajawal-Bold.ttf":             {"size_mult": 1.00, "stroke_mult": 0.75, "shadow_mult": 1.0},
    "Tajawal-Medium.ttf":           {"size_mult": 1.00, "stroke_mult": 0.80, "shadow_mult": 1.0},
    "Tajawal-Regular.ttf":          {"size_mult": 1.00, "stroke_mult": 0.85, "shadow_mult": 1.0},
    # Kufi / square fonts: their corners look harsh with thick
    # strokes; thin the outline to keep the geometry crisp.
    "RanaKufi.otf":                 {"size_mult": 1.05, "stroke_mult": 0.70, "shadow_mult": 1.1},
    "Letellka-Bold.otf":            {"size_mult": 1.05, "stroke_mult": 0.75, "shadow_mult": 1.0},
    "Letellka-Light.otf":           {"size_mult": 1.05, "stroke_mult": 0.80, "shadow_mult": 1.0},
}


def _get_font_tuning(font_path: str) -> dict:
    """Return the tuning dict for ``font_path``, or empty dict if none.

    Looks up by basename so callers can pass any absolute path.
    Unknown fonts get an empty dict and the caller multiplies by 1.0
    (i.e. applies the caller's requested values unchanged).
    """
    if not font_path:
        return {}
    base = os.path.basename(font_path)
    return _FONT_RENDER_TUNING.get(base, {})


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

    # Priority order for Arabic fonts (best first).  All of these are
    # now supported via the HarfBuzz + FreeType pipeline — see
    # ``quran_reels.services.shaping`` and the new
    # ``PIL_COMPATIBLE_ARABIC_FONTS`` list.
    preferred_fonts = [
        "Amiri-Bold.ttf", "Amiri-Regular.ttf",
        "Lateef-Bold.ttf",
        "Dubai-Bold.ttf", "Dubai-Regular.ttf",
        "Tajawal-Bold.ttf", "Tajawal-Medium.ttf", "Tajawal-Regular.ttf",
        "Zain-Bold.ttf", "Zain-Light.ttf", "Zain-Regular.ttf",
        "DigitalKhatt-OldMadina.otf", "DigitalMadina-NON V1.ttf",
        "UthmanTN1-Ver10.otf",
        "Letellka-Bold.otf", "Letellka-Light.otf",
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

def _list_arabic_fonts():
    """Return every .ttf/.otf file in ``fonts/`` that FreeType can open.

    Previously this was a hard-coded list of two Amiri files (PIL's
    ``ImageDraw.text()`` could only render those because they bake
    presentation forms into their cmap).  With the HarfBuzz + FreeType
    pipeline in ``quran_reels.services.shaping`` that constraint is gone
    — every Arabic font in the project is now supported, so we just
    enumerate the directory.

    If a font file fails FreeType loading (e.g. it is a non-Arabic
    fallback), it is silently dropped.
    """
    if not os.path.isdir(FONT_DIR):
        return []
    try:
        import freetype as _ft
    except ImportError:
        # freetype-py not installed — fall back to extension-only filter
        _ft = None
    fonts = []
    for name in sorted(os.listdir(FONT_DIR)):
        if not name.lower().endswith(('.ttf', '.otf')):
            continue
        path = os.path.join(FONT_DIR, name)
        if _ft is not None:
            try:
                _ft.Face(path).num_glyphs
            except Exception:
                logging.debug(f"Skipping non-loadable font: {name}")
                continue
        fonts.append(name)
    return fonts


# Backward-compatible alias for any code that imports the old constant.
# ``PIL_COMPATIBLE_ARABIC_FONTS`` used to be a hard-coded list of the
# two Amiri files that PIL could render directly; it is now the same
# dynamic list as ``_list_arabic_fonts()`` so external callers see every
# supported font.
def PIL_COMPATIBLE_ARABIC_FONTS():
    return _list_arabic_fonts()


def get_random_font():
    """Get a random Arabic font from the full ``fonts/`` directory.

    Any font in ``fonts/`` is supported via the HarfBuzz + FreeType
    shaping pipeline (``quran_reels.services.shaping``).  This used to
    be restricted to the two Amiri files because PIL's ``text()`` does
    not apply OpenType GSUB.
    """
    fonts = _list_arabic_fonts()
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

def process_arabic_text(text, words_per_line=4, mode='visual'):
    """
    Unified Arabic text processing function.

    Args:
        text: Raw Arabic text (with or without tashkeel)
        words_per_line: Word-wrap target.
        mode: ``'visual'`` (default — legacy) returns the reshape+bidi
              presentation forms so the old PIL ``ImageDraw.text()`` path
              still works.  ``'logical'`` returns the original Arabic in
              logical order, ready to feed to HarfBuzz (which handles
              both reshape and bidi internally based on the script tag).

    Returns:
        Tuple of (processed_text, num_lines, word_count).
    """
    if not text or not text.strip():
        return "", 0, 0

    # Step 1: Clean text
    cleaned = text.replace('\ufeff', '').replace('\u200b', '').strip()

    # Step 2: Split into LOGICAL words and wrap
    logical_words = cleaned.split()
    total_words = len(logical_words)
    if total_words == 0:
        return cleaned, 1, 0

    logical_lines = []
    for i in range(0, total_words, max(1, int(words_per_line))):
        logical_lines.append(' '.join(logical_words[i:i + words_per_line]))

    if mode == 'logical':
        # For HarfBuzz shaping — keep the original logical text; the
        # shaper applies the presentation forms and RTL positioning
        # itself.
        wrapped = '\n'.join(logical_lines)
        logging.info(f"📊 Text processed (logical): {total_words} words -> {len(logical_lines)} lines")
        return wrapped, len(logical_lines), total_words

    # 'visual' mode — apply arabic-reshaper + python-bidi per line so
    # PIL's text() can render the result.
    visual_lines = []
    for ln in logical_lines:
        reshaped_ln = ARABIC_RESHAPER.reshape(ln)
        visual_ln = get_display(reshaped_ln)
        visual_lines.append(visual_ln)
    wrapped = '\n'.join(visual_lines)
    logging.info(f"📊 Text processed (visual): {total_words} words -> {len(visual_lines)} lines")
    return wrapped, len(visual_lines), total_words

# =============================================================================
# STEP 7: UNIFIED TEXT RENDERING (NEW: single function using WORKING_FONT)
# =============================================================================


def _hex_to_rgba(hex_color, default=(255, 255, 255, 255)):
    s = (hex_color or '').strip().lstrip('#')
    if len(s) == 3:
        s = ''.join([c * 2 for c in s])
    if len(s) == 6:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), 255)
    if len(s) == 8:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), int(s[6:8], 16))
    return default


def _apply_glow_to_layer(layer_rgba, glow_color, glow_radius):
    """Return a *halo-only* RGBA image: the original layer's alpha tinted
    with ``glow_color`` and Gaussian-blurred.  The caller composites
    this *underneath* the original text layer so the main text stays
    sharp on top.
    """
    arr = np.array(layer_rgba)
    gr, gg, gb, _ = _hex_to_rgba(glow_color, default=(255, 215, 0, 255))
    alpha = arr[..., 3].astype(np.float32) / 255.0
    halo = np.zeros_like(arr)
    halo[..., 0] = gr
    halo[..., 1] = gg
    halo[..., 2] = gb
    halo[..., 3] = (alpha * 255).astype(np.uint8)
    halo_img = Image.fromarray(halo, 'RGBA')
    halo_img = halo_img.filter(ImageFilter.GaussianBlur(radius=glow_radius))
    return halo_img


def _dilate_alpha_for_stroke(text_layer_rgba, stroke_radius):
    """Return a new RGBA layer where the text's alpha is dilated by
    ``stroke_radius`` pixels (MaxFilter) and re-tinted black/transparent
    depending on the existing alpha values.
    """
    alpha = text_layer_rgba.split()[3]
    dilated = alpha.filter(ImageFilter.MaxFilter(2 * int(stroke_radius) + 1))
    dilated_rgba = Image.new('RGBA', text_layer_rgba.size, (0, 0, 0, 0))
    dilated_rgba.putalpha(dilated)
    # Black-fill the dilated shape; alpha=255 where dilated, 0 elsewhere.
    arr = np.array(dilated_rgba)
    arr[..., 0] = 0
    arr[..., 1] = 0
    arr[..., 2] = 0
    arr[..., 3] = dilated
    return Image.fromarray(arr, 'RGBA')


def _render_with_shaping(
    processed_text, num_lines, fontsize, color, stroke_color, stroke_width,
    target_width, font_path, supersample, shadow, shadow_offset, shadow_color,
    glow_color, glow_radius, shape_text, render_shaped_to_canvas,
):
    """Render ``processed_text`` (logical order) using HarfBuzz+FreeType.

    The output matches the legacy PIL renderer in dimensions and
    effects (drop shadow, soft glow, stroke), but works for any Arabic
    font.
    """
    from quran_reels.services.shaping import ShapedLine  # type: ignore

    ss = max(1, int(supersample))
    fill_rgba = _hex_to_rgba(color)
    stroke_rgba = _hex_to_rgba(stroke_color)
    shadow_rgba = _hex_to_rgba(shadow_color, default=(0, 0, 0, 128))

    line_height = int(fontsize * 1.6)
    padding = 50
    img_height = max(300, num_lines * line_height + 2 * padding)
    img_width = target_width + 2 * padding
    big_w, big_h = img_width * ss, img_height * ss

    # Shape every line at the supersample resolution
    big_fontsize_px = fontsize * ss
    lines = processed_text.split('\n')
    shaped_lines: list = []
    for ln in lines:
        if not ln.strip():
            shaped_lines.append(None)
            continue
        try:
            shaped_lines.append(shape_text(ln, font_path, big_fontsize_px))
        except Exception as e:
            logging.warning(f"Shaping failed for line ({ln!r}): {e}")
            shaped_lines.append(None)

    def _compose(fill_rgb, line_offset_x=0, line_offset_y=0):
        """Render all shaped lines onto a fresh transparent canvas."""
        canvas = Image.new('RGBA', (big_w, big_h), (0, 0, 0, 0))
        pen_y = (padding + line_height // 2) * ss
        for sl in shaped_lines:
            if sl is None or not sl.glyphs:
                pen_y += line_height * ss
                continue
            # RTL: pen starts at the right edge, less the line width / 2
            # to center the line within the image.
            pen_x = big_w // 2 + sl.width / 2 + line_offset_x
            baseline = pen_y + line_offset_y
            render_shaped_to_canvas(
                sl, canvas, (pen_x, baseline), fill_rgb=fill_rgb
            )
            pen_y += line_height * ss
        return canvas

    # ---- Build layers from bottom to top ----
    #   shadow  →  glow  →  stroke  →  main text
    # Each ``alpha_composite(top, over=bottom)`` puts ``top`` above.
    layers_bottom_up = []

    # 1) Shadow (lowest)
    if shadow and shadow_color:
        layers_bottom_up.append(
            _compose(shadow_rgba, line_offset_x=shadow_offset * ss,
                     line_offset_y=shadow_offset * ss)
        )

    # 2) Glow
    main_canvas = _compose(fill_rgba)
    if glow_color:
        glow_layer = _apply_glow_to_layer(main_canvas, glow_color,
                                           glow_radius * ss)
        layers_bottom_up.append(glow_layer)

    # 3) Stroke (dilated alpha of the main text, tinted with stroke_color)
    if stroke_width and stroke_width > 0 and stroke_rgba[3] > 0:
        stroke_layer = _dilate_alpha_for_stroke(main_canvas, stroke_width * ss)
        sr, sg, sb, sa = stroke_rgba
        s_arr = np.array(stroke_layer)
        s_arr[..., 0] = sr
        s_arr[..., 1] = sg
        s_arr[..., 2] = sb
        s_arr[..., 3] = (s_arr[..., 3].astype(np.uint16) * sa // 255).astype(np.uint8)
        layers_bottom_up.append(Image.fromarray(s_arr, 'RGBA'))

    # 4) Main text (top)
    layers_bottom_up.append(main_canvas)

    # Composite bottom-up
    big = layers_bottom_up[0]
    for layer in layers_bottom_up[1:]:
        big = Image.alpha_composite(big, layer)

    # Downsample
    if ss > 1:
        img = big.resize((img_width, img_height), Image.LANCZOS)
    else:
        img = big

    logging.info(
        f"✅ Shaped image rendered: {img_width}x{img_height}px, {num_lines} lines, "
        f"font={os.path.basename(font_path)}, ss={ss}, "
        f"shadow={bool(shadow)}, glow={bool(glow_color)}, stroke={stroke_width}"
    )
    return img


def render_arabic_to_pil_image(text, fontsize=80, color='#FFFFFF',
                                stroke_color='#000000', stroke_width=3,
                                words_per_line=4, target_width=920, font_path=None,
                                supersample=2,
                                shadow=True, shadow_offset=4, shadow_color='#00000080',
                                glow_color=None, glow_radius=6,
                                use_shaping=True):
    """
    Render Arabic text to a PIL RGBA Image with broadcast-grade quality.

    Pipeline (HarfBuzz + FreeType shaping, default ``use_shaping=True``):
      1.  Word-wrap the input (logical order).
      2.  For each line, run HarfBuzz (``uharfbuzz``) over the *logical*
          text — it applies presentation-form substitution (GSUB) and
          GPOS positioning using the font's own tables, so any Arabic
          font renders correctly (not just Amiri).
      3.  Rasterise each shaped glyph with FreeType and composite onto
          a transparent canvas.
      4.  Apply per-glyph stroke (FreeType's ``FT_Stroker``) and the
          drop-shadow / glow post-passes at the supersample resolution.
      5.  Downsample to the target size with ``Image.LANCZOS``.

    The legacy ``use_shaping=False`` path falls back to PIL's
    ``ImageDraw.text()`` with the arabic-reshaper / python-bidi
    pipeline.  This only works for fonts that bake presentation forms
    into their cmap (e.g. Amiri); other fonts will render as boxes.

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
        use_shaping:     ``True`` (default) → HarfBuzz + FreeType path.
                         ``False`` → legacy PIL path (Amiri only).

    Returns:
        PIL Image object (RGBA).
    """
    # Step 1 — process Arabic text
    if use_shaping:
        processed_text, num_lines, word_count = process_arabic_text(
            text, words_per_line, mode='logical'
        )
    else:
        processed_text, num_lines, word_count = process_arabic_text(
            text, words_per_line, mode='visual'
        )

    if not processed_text:
        return Image.new('RGBA', (target_width, 100), (0, 0, 0, 0))

    # Step 2 — load font
    f_path = font_path or WORKING_FONT
    if use_shaping and f_path and os.path.exists(f_path):
        # Lazy import: shaping service depends on uharfbuzz + freetype-py,
        # which are optional.  Fall through to the legacy path if either
        # import fails.
        try:
            from quran_reels.services.shaping import (
                shape_text, render_shaped_to_canvas, select_rendering_font,
            )
            # Font coverage guard.  The user may have picked a popular
            # Arabic font (Tajawal, Uthman TN1, Dubai, Zain, Letellka,
            # RanaKufi, Almadinah) that does NOT contain the full Quranic
            # Uthmani character set.  Rendering with it produces a
            # visually broken word — the alef wasla (U+0671) and the ﷲ
            # ligature come out as disconnected letters or tofu boxes.
            #
            # ``select_rendering_font`` checks the actual text against
            # the chosen font; if anything is missing it transparently
            # switches to Amiri-Bold (which has 100% Quranic coverage)
            # and logs a one-time, de-duplicated warning.  This keeps
            # the entire line in a single font so GSUB ligatures like
            # ﷲ / ﷽ form correctly.  See BUG 2 / "good appearance".
            chosen_path, was_fallback, coverage_pct, missing_repr = (
                select_rendering_font(f_path, processed_text)
            )
            if was_fallback:
                logging.debug(
                    "Font override: %s -> %s (coverage=%.0f%%, missing %s)",
                    os.path.basename(f_path), os.path.basename(chosen_path),
                    coverage_pct * 100, missing_repr,
                )
            f_path = chosen_path
            # Per-font tuning.  Different fonts ship with different
            # design metrics: Uthman TN1 looks tiny at 80px, Tajawal
            # has very thick strokes that need thinning, Kufi fonts
            # have harsh corners.  Apply per-font multipliers so the
            # visual weight stays consistent across font choices.
            tuning = _get_font_tuning(f_path)
            eff_fontsize = max(8, int(round(fontsize * tuning.get("size_mult", 1.0))))
            eff_stroke = max(0, int(round(stroke_width * tuning.get("stroke_mult", 1.0))))
            eff_shadow_off = max(0, int(round(shadow_offset * tuning.get("shadow_mult", 1.0))))
            if eff_fontsize != fontsize or eff_stroke != stroke_width:
                logging.debug(
                    "Font tuning applied: %s size %d->%d, stroke %d->%d, shadow %d->%d",
                    os.path.basename(f_path),
                    fontsize, eff_fontsize,
                    stroke_width, eff_stroke,
                    shadow_offset, eff_shadow_off,
                )
            return _render_with_shaping(
                processed_text=processed_text,
                num_lines=num_lines,
                fontsize=eff_fontsize,
                color=color,
                stroke_color=stroke_color,
                stroke_width=eff_stroke,
                target_width=target_width,
                font_path=f_path,
                supersample=supersample,
                shadow=shadow,
                shadow_offset=eff_shadow_off,
                shadow_color=shadow_color,
                glow_color=glow_color,
                glow_radius=glow_radius,
                shape_text=shape_text,
                render_shaped_to_canvas=render_shaped_to_canvas,
            )
        except ImportError as e:
            logging.warning(
                f"HarfBuzz/FreeType shaping unavailable ({e}); falling back "
                f"to legacy PIL path.  Install uharfbuzz + freetype-py to "
                f"unlock all Arabic fonts."
            )

    # ---- Legacy path (PIL ImageDraw.text) ----
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
# STEP 8: CONSTANTS & CONFIGURATION  (refactored — see quran_reels.config)
# =============================================================================
# TEMPLATES, QUALITY_PRESETS, OUTPUT_FORMATS, RECITERS_MAP, VERSE_COUNTS,
# SURAH_NAMES, VIDEO_TRANSITIONS, FEATURE_FLAGS, and the BackgroundRotator
# class are all imported from quran_reels.* at the top of this file.
TARGET_W = _env("QURAN_TARGET_W", 1080, int)
TARGET_H = _env("QURAN_TARGET_H", 1920, int)

# =============================================================================
# STEP 10: IMPORTS FOR VIDEO PROCESSING
# =============================================================================
# (STEP 9 — Python 3.13 audioop compatibility patch — was deleted with
# the pydub removal in refactor P1-3.  Pydub was the only consumer of the
# ``audioop`` shim; without pydub the patch is dead.  ``audioop_patch.py``
# is left on disk in case a future dependency reintroduces the need.)

import numpy as np
import requests as http_requests
from urllib3.util.retry import Retry
from urllib3 import disable_warnings
disable_warnings()  # Disable SSL warnings
import shutil

if FFMPEG_EXE:
    logging.info(f"Using FFmpeg: {FFMPEG_EXE}")
    os.environ["FFMPEG_BINARY"] = FFMPEG_EXE
    os.environ["IMAGEIO_FFMPEG_EXE"] = FFMPEG_EXE
else:
    raise RuntimeError("FFmpeg not found - video processing requires FFmpeg")

# =============================================================================
# STEP 10: GLOBAL PROGRESS TRACKING & FLASK APP
# =============================================================================
# Enhanced Progress Tracking System — see quran_reels.utils.progress
# for the thread-safe ProgressState implementation.  ``current_progress``
# is the module-level singleton imported at the top of this file.

app = Flask(__name__, static_folder=EXEC_DIR)
CORS(app)

def reset_progress():
    """Reset the shared progress state to a fresh-build snapshot."""
    current_progress.reset()

def add_log(message):
    """Append a log line to the shared progress state (thread-safe)."""
    current_progress.append_log(message)
    logging.info(f"PROGRESS: {message}")

def update_progress(percent, status, stage=None, current_ayah=None, total_ayat=None):
    """Update the shared progress state atomically (percent, ETA, etc.)."""
    # Build the kwargs we want to write; filter out None so we don't
    # clobber an existing value with ``None`` when the caller didn't
    # pass an explicit stage/ayah/count.
    updates = {'percent': percent, 'status': status}
    if stage is not None:
        updates['stage'] = stage
    if current_ayah is not None:
        updates['current_ayah'] = current_ayah
    if total_ayat is not None:
        updates['total_ayat'] = total_ayat

    # The set() and calculate_eta() must happen under the same lock so
    # readers never see a percent bump without a matching ETA.
    with current_progress._lock:
        current_progress.set(**updates)
        current_progress.calculate_eta()

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
        # Copy to temp directory for processing (job-scoped filename)
        out = current_job().audio_path(idx)
        shutil.copy2(cached_path, out)
        return out

    # Try multiple sources with different domains
    sources = [
        f'https://everyayah.com/data/{reciter_id}/{fn}',
        f'https://download.quranicaudio.com/quran/{reciter_id}/{fn}',
        f'https://www.everyayah.com/data/{reciter_id}/{fn}',
        f'https://mp3.quranicaudio.com/quran/{reciter_id}/{fn}'
    ]

    out = current_job().audio_path(idx)

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
# STEP 13.5: DYNAMIC TEXT COLOR ANALYZER  (refactored — see quran_reels.services.contrast)
# =============================================================================
# analyze_background_brightness and get_contrasting_text_color are imported
# from quran_reels.services.contrast at the top of this file.

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


def render_text_to_png(arabic_text, template, output_png_path, selected_font=None,
                       quality='medium', text_color=None, stroke_color=None):
    """
    Render Arabic text to PNG using the unified, broadcast-grade renderer.

    Honours per-template font + glow settings and the quality preset's supersample.
    Pass `text_color` / `stroke_color` to override the template's defaults
    (used for dynamic contrast-based coloring from get_contrasting_text_color).
    """
    template_config = TEMPLATES.get(template, TEMPLATES['normal'])

    # Resolve font (selected -> template -> WORKING_FONT)
    font_path, font_name = _resolve_template_font(template_config, selected_font)

    # Word-count aware font sizing
    word_count = len(arabic_text.split())
    size_mult = template_config['font_size_mult']
    fontsize, per_line = _fontsize_for_wordcount(word_count, size_mult)

    # Fill color: override -> template's text_color (hex or name like 'gold')
    if text_color is None:
        text_color = template_config['text_color']
        if not text_color.startswith('#'):
            text_color = {'gold': '#FFD700', 'white': '#FFFFFF', 'bright': '#00FFFF'}.get(text_color, '#FFFFFF')

    # Stroke color: override -> hardcoded black for readability
    if stroke_color is None:
        stroke_color = '#000000'

    # Glow (e.g. ramadan template)
    glow_color = template_config.get('glow_color')
    glow_radius = template_config.get('glow_radius', 6)

    # Render
    img = render_arabic_to_pil_image(
        text=arabic_text,
        fontsize=fontsize,
        color=text_color,
        stroke_color=stroke_color,
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
        f"text={text_color}, stroke={stroke_color}, glow={bool(glow_color)} -> {output_png_path}"
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

    The first element of ``args`` is the :class:`JobContext` for the
    build — passed explicitly so the worker thread (which has its own
    thread-local storage) uses the *parent* build's job_id, not a
    racey global.  See ``bug.md`` Issue 2 P0 #5
    ("ThreadPool race conditions").
    """
    (job, reciter_id, surah, ayah, idx, template, bg_style, selected_font,
     show_text, text_animation, auto_text_color, quality, reciter_speed,
     is_last) = args

    # Bind the parent build's JobContext to this worker thread so any
    # nested call to ``current_job()`` (e.g. inside ``download_audio``)
    # returns the same job — otherwise the ThreadPoolExecutor's worker
    # thread would have its own (empty) thread-local and
    # ``current_job()`` would lazily start a *third* job mid-build,
    # splitting the build's files across two job_ids.
    _job_local.ctx = job

    try:
        # Download audio (no trimming, faster)
        audio_path = download_audio(reciter_id, surah, ayah, idx)
        # Feature: reciter_speed — apply ffmpeg atempo to speed up / slow
        # down the recitation without changing pitch.  Done as a separate
        # pre-pass so the rest of the pipeline sees a normal mp3 file and
        # doesn't need to know about tempo.  atempo is limited to [0.5,
        # 2.0] per pass, so values outside that range are clamped.
        if reciter_speed and reciter_speed != 1.0:
            atempo = max(0.5, min(2.0, float(reciter_speed)))
            sped_path = current_job().sped_path(idx)
            cmd = [
                FFMPEG_EXE, '-y', '-hide_banner', '-loglevel', 'error',
                '-i', audio_path,
                '-af', f'atempo={atempo:.3f}',
                '-c:a', 'libmp3lame', '-b:a', '192k',
                sped_path,
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0 and os.path.exists(sped_path):
                audio_path = sped_path
                logging.debug(f"Segment {idx}: reciter_speed={reciter_speed} (atempo={atempo:.3f})")
            else:
                logging.warning(f"Segment {idx}: atempo pre-pass failed, using original audio: {res.stderr.strip()}")
        duration = get_audio_duration_ffprobe(audio_path)
        logging.debug(f"Segment {idx}: Audio duration = {duration:.2f}s")

        # Fetch text (with cache)
        arabic_text = get_ayah_text(surah, ayah)

        # Select background using rotator to prevent repetition
        bg_path = get_next_background(bg_style, count=1)
        bg_paths = bg_path if isinstance(bg_path, list) else [bg_path]
        logging.debug(f"Segment {idx}: Using background {os.path.basename(bg_paths[0])}")

        # Render text to PNG (job-scoped filenames so they cannot
        # collide with another build running in the same process).
        text_png = current_job().text_png_path(idx)
        segment_out = current_job().segment_path(idx)

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
            render_text_to_png(arabic_text, template, text_png,
                              selected_font=selected_font, quality=quality,
                              text_color=text_color, stroke_color=stroke_color)
        else:
            # Create a transparent 1x1 pixel PNG for no-text mode
            from PIL import Image
            transparent = Image.new('RGBA', (1, 1), (0, 0, 0, 0))
            transparent.save(text_png)
            logging.debug(f"Created transparent placeholder: {text_png}")

        # Build segment with animation filter (Phase 2: text animation + outro fade)
        # Pass text PNG dimensions so zoom_in/zoom_out can pad the scaled text
        # back to the original canvas size, centered.  Slides don't need this.
        text_size = None
        if show_text and os.path.exists(text_png):
            try:
                from PIL import Image as _PILImage
                with _PILImage.open(text_png) as _img:
                    text_size = _img.size
            except Exception:
                text_size = None
        animation_filter = get_ffmpeg_text_animation_filter(
            text_animation, duration, text_size=text_size)
        build_segment_ffmpeg(bg_paths, text_png, audio_path, duration, segment_out,
                           show_text=show_text, text_animation_filter=animation_filter,
                           is_last=is_last)

        logging.info(f"✅ Segment {idx} complete: ayah {surah}:{ayah}")
        return (ayah, segment_out)

    except Exception as e:
        logging.error(f"❌ Error processing ayah {surah}:{ayah}: {e}")
        raise

# =============================================================================
# STEP 16.5: BISMILLAH TITLE-CARD HELPERS
# =============================================================================
# Feature: prepend a 1.8s "Bismillah ar-Rahman ar-Raheem" card before ayah 1
# of any surah.  Skipped for surahs in BISMILLAH_SKIP_SURAHS (Al-Fatihah,
# At-Tawbah) per the standard recitation tradition.

def _generate_silence_mp3(output_path, duration_sec, sample_rate=44100):
    """Render ``duration_sec`` of stereo silence to an mp3 file.

    Uses ffmpeg's ``anullsrc`` so no external asset is needed.  Matches the
    sample rate / channel layout of the downloaded recitation mp3s
    (44.1 kHz, stereo) so it can drop in next to them without re-encoding.
    """
    cmd = [
        FFMPEG_EXE, '-y', '-hide_banner', '-loglevel', 'error',
        '-f', 'lavfi',
        '-i', f'anullsrc=channel_layout=stereo:sample_rate={sample_rate}',
        '-t', f'{duration_sec:.3f}',
        '-c:a', 'libmp3lame', '-b:a', '128k',
        output_path,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0 or not os.path.exists(output_path):
        raise RuntimeError(f"Silence mp3 generation failed: {res.stderr.strip()}")
    return output_path


def _build_bismillah_segment(template, selected_font, quality, bg_paths):
    """Build a 1.8s title-card segment for Bismillah ar-Rahman ar-Raheem.

    Returns ``(ayah_num, segment_path)`` with ``ayah_num=0`` so the existing
    sort-by-ayah-number logic places it before ayah 1.
    """
    job = current_job()
    bismillah_png = job.bismillah_text_png()
    bismillah_audio = job.bismillah_audio()
    bismillah_segment = job.bismillah_segment()

    # 1) Render the Bismillah text using the same template-driven renderer
    #    the regular ayahs use, so font / glow / color stay consistent.
    template_config = TEMPLATES.get(template, TEMPLATES['normal'])
    template_color = template_config.get('text_color', 'white')
    # Bismillah is a title card: use the FIRST background we were handed so
    # it visually leads into ayah 1 (which would otherwise pick a new bg).
    if bg_paths:
        first_bg = bg_paths[0]
    else:
        bg = get_next_background(template_config['bg_style'], count=1)
        # get_next_background returns a string for count=1 and a list for count>1
        first_bg = bg if isinstance(bg, str) else bg[0]
    text_color, stroke_color = get_contrasting_text_color(
        first_bg, template_color, auto_detect=template_config.get('auto_text_color', True)
    )
    render_text_to_png(BISMILLAH_TEXT, template, bismillah_png,
                       selected_font=selected_font, quality=quality,
                       text_color=text_color, stroke_color=stroke_color)

    # 2) Generate the silence audio track.
    _generate_silence_mp3(bismillah_audio, BISMILLAH_DURATION_SEC)

    # 3) Build the segment with a simple fade-in (no slide/zoom on a static
    #    title card) and an outro fade (is_last=False) so the crossfade
    #    into ayah 1 lands smoothly.
    text_size = None
    try:
        from PIL import Image as _PILImage
        with _PILImage.open(bismillah_png) as _img:
            text_size = _img.size
    except Exception:
        text_size = None
    animation_filter = get_ffmpeg_text_animation_filter(
        'fade_in', BISMILLAH_DURATION_SEC, text_size=text_size)
    build_segment_ffmpeg(
        [first_bg], bismillah_png, bismillah_audio, BISMILLAH_DURATION_SEC,
        bismillah_segment, show_text=True,
        text_animation_filter=animation_filter, is_last=False,
    )
    logging.info(f"✅ Bismillah title card built: {bismillah_segment}")
    return (0, bismillah_segment)


# =============================================================================
# STEP 17: MAIN VIDEO BUILDER
# =============================================================================

def build_video(reciter_id, surah, start_ayah, end_ayah=None,
                quality='medium', format_type='reels', template='normal',
                person_name='', selected_font='random', target_duration_seconds=None,
                show_text=True, include_bismillah=False, reciter_speed=1.0,
                transition_style_override=None):
    """
    Main video builder - optimized and refactored.
    No clear_outputs() needed - uses temp directory.

    Returns:
        str | None: Absolute ``output_path`` of the final mp4 on success,
        or ``None`` on failure.  The return value is purely informational —
        progress and errors are also reported via the ``current_progress``
        global so the existing ``threading.Thread(target=build_video, ...)``
        callers in the API routes continue to work unchanged.
    """
    try:
        # Start a fresh job context: gives every temp file a unique
        # ``job_id`` so this build cannot collide with any previous
        # build's leftovers or a parallel build's running files (see
        # ``bug.md`` Issue 2 P0 #1 and #2).  Also resets the
        # per-build circuit-breaker counters that may have tripped on
        # a previous run.
        start_new_job()
        current_progress.set(is_running=True, is_complete=False, error=None)

        # Get config
        quality_config = QUALITY_PRESETS.get(quality, QUALITY_PRESETS['medium'])
        format_config = OUTPUT_FORMATS.get(format_type, OUTPUT_FORMATS['reels'])
        template_config = TEMPLATES.get(template, TEMPLATES['normal'])
        if transition_style_override:
            # Caller (UI/API) picked an explicit style; shallow-copy so we
            # don't mutate the shared TEMPLATES dict.
            template_config = {**template_config, 'transition_style': transition_style_override}
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

        add_log(f'Building {total} ayat from {start_ayah} to {last_ayah} (job_id={current_job().job_id})')
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

        # Feature: target_duration_seconds — cap the number of ayahs so the
        # final video won't exceed the user's requested length.  Iterates
        # through candidate ayahs in order, summing their (cached) audio
        # durations, and stops just before the running total would exceed
        # the cap.  Always keeps at least the first ayah.  Uncached files
        # fall back to a conservative 5 s estimate so the cap isn't
        # over-strict on the first run.
        if target_duration_seconds and target_duration_seconds > 0:
            cumulative = 0.0
            new_last = start_ayah - 1
            for ayah in range(start_ayah, last_ayah + 1):
                d = _estimate_ayah_duration(reciter_id, surah, ayah)
                if new_last >= start_ayah and cumulative + d > target_duration_seconds:
                    break
                cumulative += d
                new_last = ayah
            if new_last < start_ayah:
                new_last = start_ayah
            if new_last < last_ayah:
                trimmed = last_ayah - new_last
                add_log(
                    f"target_duration_seconds={target_duration_seconds}s capped last_ayah "
                    f"({last_ayah} -> {new_last}, dropped {trimmed} ayahs, "
                    f"~{cumulative:.1f}s)"
                )
                last_ayah = new_last
                total = last_ayah - start_ayah + 1

        # Prepare args - now includes rotation index for variety + quality preset
        # + is_last flag (Phase 2 T2.5) so the last segment skips the outro fade.
        # The leading ``job`` element is the per-build :class:`JobContext`
        # captured at the top of ``build_video`` — passed explicitly so
        # the worker threads (which have their own thread-local storage)
        # cannot race on a global job_id.  See ``bug.md`` Issue 2 P0 #5.
        total_ayahs = last_ayah - start_ayah + 1
        job = current_job()
        ayah_args = [
            (job, reciter_id, surah, ayah, idx, template, bg_style, selected_font, show_text,
             text_animation, auto_text_color, quality, reciter_speed, idx == total_ayahs)
            for idx, ayah in enumerate(range(start_ayah, last_ayah + 1), start=1)
        ]

        # Output filename - use ASCII to avoid FFmpeg issues
        surah_name = SURAH_NAMES[surah - 1] if 1 <= surah <= len(SURAH_NAMES) else f"Surah{surah}"
        clean_name = person_name.replace(" ", "_").replace("/", "_").replace("\\", "_") if person_name else "User"
        # Remove Arabic characters for temp filename
        ascii_name = f"{clean_name}_Surah{surah}_Ayah{start_ayah}-{last_ayah}_{quality}_{template}"
        temp_filename = f"{ascii_name}.mp4"
        # In-progress final mp4 lives in TEMP_DIR under a job-scoped
        # name so two concurrent/sequential builds cannot trample each
        # other.
        temp_output_path = current_job().temp_output_path(temp_filename)

        # Final output with user-friendly filename
        # Format: "Quran_Surah[Number]_[Name]_Ayah[Start-End]_[Name]_[Quality]_<job_id>.mp4"
        # The ``<job_id>`` suffix prevents silent overwrites when the
        # user re-runs the exact same surah+ayahs+quality back-to-back
        # — see ``bug.md`` Issue 2 P0 #7.
        surah_number = f"{surah:03d}"  # 3-digit format (001, 002, etc.)
        ayah_range = f"{start_ayah}-{last_ayah}"
        user_part = f"_{clean_name}" if clean_name else ""

        # Get Arabic surah name
        surah_name_ar = SURAH_NAMES[surah - 1] if 1 <= surah <= len(SURAH_NAMES) else f"Surah{surah}"
        surah_name_clean = surah_name_ar.replace(" ", "_").replace("/", "_").replace("\\", "_")

        filename = f"Quran_Surah{surah_number}_{surah_name_clean}_Ayah{ayah_range}{user_part}_{quality}.mp4"
        output_path = current_job().final_output_path(filename)

        os.makedirs(VIDEO_DIR, exist_ok=True)

        # Process in parallel
        add_log('Processing ayat in parallel...')

        # Feature: Bismillah title card.  Built sequentially (it's just one
        # short 1.8s render) so the parallel pool doesn't waste a worker on
        # it and the xfade chain at the end naturally crossfades Bismillah
        # into ayah 1.  Skipped for surahs in BISMILLAH_SKIP_SURAHS.
        segment_results = []
        if (include_bismillah
                and start_ayah == 1
                and surah not in BISMILLAH_SKIP_SURAHS):
            update_progress(11, 'جاري تحضير البسملة...')
            add_log('Building Bismillah title card...')
            bismillah_result = _build_bismillah_segment(
                template, selected_font, quality, bg_paths=None)
            segment_results.append(bismillah_result)
        elif include_bismillah and surah in BISMILLAH_SKIP_SURAHS:
            add_log(f"Skipping Bismillah for surah {surah} (in BISMILLAH_SKIP_SURAHS)")

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
        # before the list is created.  Job-scoped so a previous build's
        # leftover list cannot be picked up by mistake — see ``bug.md``
        # Issue 2 P0 #4.
        list_path = current_job().concat_list_path()
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
            # Multiple segments - decide whether to xfade any pair, and which
            try:
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
                xfade_d = trans_spec.get('duration', 0.5)

                # Resolve transition_style (Feature 3: smart transitions)
                # - cinematic : no xfade between segments; rely on the per-
                #               segment fade-in/out for the cinematic look
                # - cut       : hard cuts only, no xfade at all
                # - dynamic   : xfade between every consecutive pair (default)
                # - smooth    : xfade every Nth pair, hard cut the rest
                trans_style = template_config.get('transition_style', 'cinematic')
                n = len(segment_results)
                is_xfade_pair = _compute_xfade_pairs(trans_style, n, xfade_d)
                any_xfade = any(is_xfade_pair)
                logging.info(
                    f"Using transition style: {trans_style!r} "
                    f"({sum(is_xfade_pair)}/{n-1} pairs will xfade with {xfade_name})"
                )

                if not any_xfade:
                    # No xfade anywhere — fall back to the simple concat demuxer
                    # (hard cuts).  This path is identical to the single-segment
                    # branch above, just with more inputs.
                    cmd_concat = [
                        FFMPEG_EXE, "-y", "-f", "concat", "-safe", "0", "-i", list_path,
                        "-c:v", "libx264", "-preset", "ultrafast", "-threads", "4",
                        "-c:a", "aac", "-b:a", "192k",
                        "-movflags", "+faststart",
                        temp_output_path
                    ]
                else:
                    # xfade d=0 produces invalid output, so the "smooth" style
                    # pre-merges hard-cut runs into single files via the
                    # concat demuxer, then runs the xfade chain on the
                    # resulting list of chunks.  Single-segment chunks are
                    # used as-is, multi-segment chunks get a fresh merged mp4.
                    chunk_groups = _split_into_chunks(is_xfade_pair)
                    chunk_paths, chunk_durations = _premerge_chunks(
                        chunk_groups, segment_results, seg_durations
                    )
                    # Rebuild the in-flight lists as chunk-shaped and force
                    # every pair to be an xfade (chunks are the units now).
                    segment_results = [(i, p) for i, p in enumerate(chunk_paths)]
                    seg_durations = chunk_durations
                    is_xfade_pair = [True] * (len(segment_results) - 1)

                    filter_complex = []
                    # Trim each segment to its actual duration
                    for i, (_, seg_path) in enumerate(segment_results):
                        seg_d = seg_durations[i]
                        filter_complex.append(
                            f"[{i}:v]trim=duration={seg_d:.3f},setpts=PTS-STARTPTS[v{i}];"
                            f"[{i}:a]atrim=duration={seg_d:.3f},asetpts=PTS-STARTPTS[a{i}]"
                        )

                    # Crossfade between consecutive chunks using computed offsets.
                    # Each chunk overlaps the next by xfade_d, so the offset of
                    # the (i+1)-th xfade is:
                    #   sum(durations[0:i+1]) - (i+1) * xfade_d
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
        current_progress.set(is_complete=True, output_path=output_path)

        if os.path.isfile(output_path):
            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            logging.info(f"Output: {output_path} ({size_mb:.2f} MB)")

        return output_path

    except Exception as e:
        logging.exception("Error in build_video")
        current_progress.set(error=str(e))
        add_log(f'[ERROR] {str(e)}')
        update_progress(0, f'خطأ: {str(e)}')
        return None
    finally:
        current_progress.set(is_running=False)

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
    if current_progress.is_running:
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
    include_bismillah = data.get('includeBismillah', False)
    reciter_speed = data.get('reciterSpeed', 1.0)
    try:
        reciter_speed = float(reciter_speed)
    except (TypeError, ValueError):
        reciter_speed = 1.0
    transition_style_override = data.get('transitionStyle') or None

    reset_progress()

    thread = threading.Thread(
        target=build_video,
        args=(reciter_id, surah, start_ayah, end_ayah, quality,
              format_type, template, person_name, selected_font, target_duration_seconds,
              show_text, include_bismillah, reciter_speed, transition_style_override),
        daemon=True
    )
    thread.start()

    return jsonify({'success': True, 'message': 'بدأ إنشاء الفيديو'})

@app.route('/api/progress', methods=['GET'])
def get_progress():
    return jsonify(current_progress.to_dict())

@app.route('/api/preview', methods=['POST'])
def preview_video():
    """Generate a preview of the first ayah (one verse)."""
    if current_progress.is_running:
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
    app.run(
        host=_env("QURAN_FLASK_HOST", "127.0.0.1"),
        port=_env("QURAN_FLASK_PORT", 5000, int),
        debug=_env("QURAN_FLASK_DEBUG", False, lambda s: s.lower() in ("1", "true", "yes", "on")),
        threaded=True,
    )
