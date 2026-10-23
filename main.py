# Quran Reels Generator - Refactored Backend Server
# Major refactoring: unified text processing, simplified font system, optimized performance

import os
import sys
import shutil
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
import requests as http_requests
from urllib3.util.retry import Retry
from urllib3 import disable_warnings
disable_warnings()

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
    TARGET_W,
    TARGET_H,
    FEATURE_FLAGS,
    QUALITY_PRESETS,
    OUTPUT_FORMATS,
    TEMPLATES,
    VIDEO_TRANSITIONS,
    VERSE_COUNTS,
    SURAH_NAMES,
    RECITERS_MAP,
    BISMILLAH_DURATION_SEC,
    BISMILLAH_SKIP_SURAHS,
    should_show_bismillah_visual,
    SHOW_TEXT_DEFAULT,
    HIGHLIGHT_WORDS_DEFAULT,
    TEXT_POSITION_DEFAULT,
    TEXT_POSITIONS,
)
from quran_reels.services.text_overlay import render_ayah_text_png, resolve_profile
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

# Create the Flask app once all the path constants are resolved.
app = Flask(__name__, static_folder=EXEC_DIR)

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

# Constants missing from refactor
OUT_DIR = _env_path("QURAN_OUT_DIR", "outputs")
VIDEO_DIR = _env_path("QURAN_VIDEO_DIR", os.path.join(OUT_DIR, "video"))
BG_CACHE_DIR = _env_path("QURAN_BG_CACHE_DIR", os.path.join("cache", "backgrounds"))
VISION_DIR = _env_path("QURAN_VISION_DIR", "vision")
UI_PATH = _env_path("QURAN_UI_PATH", "UI.html")

def _resolve_ffmpeg_bin(name: str) -> str:
    """Resolve ffmpeg/ffprobe with env var > portable bin > PATH fallback."""
    # 1. Explicit env var
    env_key = f"QURAN_{name.upper()}_EXE"
    env_val = os.environ.get(env_key)
    if env_val:
        # Allow relative paths too (resolve against EXEC_DIR)
        if not os.path.isabs(env_val):
            env_val = os.path.join(EXEC_DIR, env_val)
        if os.path.isfile(env_val):
            return env_val
        # If env points to non-existent file, still honour it (let subprocess fail with clear error)
        return env_val
    # 2. Portable bin/ffmpeg lookup (documented in .env.example)
    portable = os.path.join(EXEC_DIR, "bin", "ffmpeg", f"{name}.exe" if os.name == "nt" else name)
    if os.path.isfile(portable):
        return portable
    portable2 = os.path.join(EXEC_DIR, "bin", "ffmpeg", name)
    if os.path.isfile(portable2):
        return portable2
    # 3. PATH
    return shutil.which(name) or name


FFMPEG_EXE = _resolve_ffmpeg_bin("ffmpeg")
FFPROBE_EXE = _resolve_ffmpeg_bin("ffprobe")

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

    def segment_path(self, idx: int) -> str:
        """Per-ayah muxed video segment (bg + audio)."""
        return os.path.join(TEMP_DIR, f"{self.job_id}_segment_{idx:03d}.mp4")

    def text_png_path(self, idx: int) -> str:
        """Per-ayah rendered ayah-text overlay PNG (feature 002)."""
        return os.path.join(TEMP_DIR, f"{self.job_id}_text_{idx:03d}.png")

    def highlight_png(self, idx: int) -> str:
        """Per-ayah word-highlight sprite for this build (feature 002 US3).

        Scoped per ayah (not per job) because parallel workers each
        render their own sprite at their own ayah's word-box size — a
        single job-wide file would race between the PIL write and the
        FFmpeg read.
        """
        return os.path.join(TEMP_DIR, f"{self.job_id}_highlight_{idx:03d}.png")

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
# Feature 002-ayah-text-sync: Arabic text overlay rendering lives in
# quran_reels/services/text_overlay.py (Pillow + RAQM); the PNG it returns
# is composited in build_segment_ffmpeg() below via an extra overlay input.
# =============================================================================

# Feature 002 US3: hard cap on per-segment word-highlight overlay nodes so a
# very long ayah (e.g. 2:255) can't blow up the filter_complex graph.
HIGHLIGHT_MAX_LAYERS = 60


def _merge_highlight_boxes(boxes, windows):
    """Pair word boxes with timing windows, capping layer count at
    ``HIGHLIGHT_MAX_LAYERS`` by repeatedly merging adjacent entries
    (union bounding box, union time span).  Keeps the FFmpeg graph
    bounded for extreme ayahs; short ayahs pass through untouched."""
    pairs = list(zip(boxes, windows))
    while len(pairs) > HIGHLIGHT_MAX_LAYERS:
        merged = []
        for i in range(0, len(pairs) - 1, 2):
            (b1, w1), (b2, w2) = pairs[i], pairs[i + 1]
            x0 = min(b1["x"], b2["x"])
            y0 = min(b1["y"], b2["y"])
            x1 = max(b1["x"] + b1["w"], b2["x"] + b2["w"])
            y1 = max(b1["y"] + b1["h"], b2["y"] + b2["h"])
            merged.append((
                {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0},
                (min(w1[0], w2[0]), max(w1[1], w2[1])),
            ))
        if len(pairs) % 2:
            merged.append(pairs[-1])
        pairs = merged
    return pairs


def _video_encoding_args(quality_config):
    return [
        "-c:v", quality_config['codec'],
        "-preset", quality_config['preset'],
        "-b:v", quality_config['bitrate'],
        "-r", str(quality_config['fps']),
        "-threads", "4",
    ]


def build_segment_ffmpeg(bg_paths, audio_path, duration_sec, output_path, is_last=True, ayah_num=None, surah_name=None, text_png_path=None, highlight=None, frame_size=(TARGET_W, TARGET_H), quality='medium'):
    """Build one video segment with FFmpeg — background + audio, with optional ayah number watermark.

    Args:
      bg_paths: Single path or list of background video paths.
      audio_path: Path to the audio file to mux onto the video.
      duration_sec: Target segment duration (matches the audio length).
      output_path: Where to write the final segment .mp4.
      is_last: When False, append a 0.4 s outro fade so the cut to the
        next segment is soft, not a hard jump.  The last segment skips
        the outro fade to avoid a fade-to-black at the very end of the
        video.
      ayah_num: Optional ayah number to display (e.g., "1:2" for Surah 1, ayah 2)
      surah_name: Optional surah name for display (e.g., "Al-Baqarah")
      text_png_path: Optional full-frame transparent PNG (from
        ``quran_reels.services.text_overlay``) composited above the
        background chain and below the outro fade.  Feature 002-ayah-text-sync.
      highlight: Optional dict ``{png, w, h, words, windows}`` enabling
        word-level read-along highlighting (feature 002 US3).  ONE glow
        sprite input is repositioned per word via
        ``enable='between(t,start,end)'`` — never one input per word.
        Requires ``text_png_path``; silently skipped (plain display
        fallback, FR-011) when boxes/windows are missing or mismatched.
    """
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio missing: {audio_path}")
    if os.path.getsize(audio_path) < 1000:
        raise ValueError(f"Audio too small: {os.path.getsize(audio_path)} bytes")

    quality_config = QUALITY_PRESETS.get(quality, QUALITY_PRESETS['medium'])

    # Preprocess backgrounds
    preprocessed = []
    frame_w, frame_h = frame_size
    for p in (bg_paths if isinstance(bg_paths, (list, tuple)) else [bg_paths]):
        if not os.path.exists(p):
            raise FileNotFoundError(f"Background missing: {p}")
        preprocessed.append(get_preprocessed_bg(p, frame_w, frame_h))

    n = len(preprocessed)
    part_dur = duration_sec / n

    logging.info(
        f"Building segment: {n} BGs, duration={duration_sec:.2f}s, "
        f"part_dur={part_dur:.2f}s, is_last={is_last}"
    )
    logging.info(f"  Audio: {audio_path} ({os.path.getsize(audio_path)} bytes)")

    # Build FFmpeg command
    common_args = ["-y", "-hide_banner", "-loglevel", "error"]
    inputs = []

    for p in preprocessed:
        inputs.extend(["-stream_loop", "-1", "-i", p])

    inputs.extend(["-i", audio_path])

    # Ayah text overlay (feature 002-ayah-text-sync): full-frame transparent
    # PNG — geometry baked in, so a single overlay=0:0 node composites it.
    # Input index is n+1 (after n backgrounds + audio at index n).
    text_idx = None
    text_overlays = []
    if text_png_path:
        text_overlays = (text_png_path if isinstance(text_png_path, list)
                         else [(text_png_path, 0.0, duration_sec)])
        text_idx = n + 1
        for overlay_path, _, _ in text_overlays:
            if not os.path.exists(overlay_path):
                raise FileNotFoundError(f"Text PNG missing: {overlay_path}")
            inputs.extend(["-loop", "1", "-framerate", "30", "-i", overlay_path])

    # Word-level read-along highlight (feature 002 US3): the glow sprite
    # is split into one branch per word; each branch fades in/out around
    # its own timing window (smooth spotlight, no hard pops), then all
    # branches composite ABOVE the text and BEFORE the outro fade.
    # Any inconsistency in meta → plain display (FR-011).
    hl_chain = ""
    hl_final = None
    if text_idx is not None and highlight:
        hl_png = highlight.get("png")
        hl_boxes = highlight.get("words") or []
        hl_windows = highlight.get("windows")
        if (hl_png and os.path.exists(hl_png) and hl_boxes and hl_windows
                and len(hl_windows) == len(hl_boxes)):
            pairs = _merge_highlight_boxes(hl_boxes, hl_windows)
            hl_w, hl_h = int(highlight["w"]), int(highlight["h"])
            hl_idx = text_idx + len(text_overlays)
            # -loop 1: the sprite must be a real timed stream, not a
            # single held frame — time-based fade st/d never advances on
            # a one-frame input (overlay's repeatlast would freeze the
            # fade's initial transparent frame forever).
            inputs.extend(["-loop", "1", "-framerate", "30", "-i", hl_png])
            n_words = len(pairs)
            fades = []
            if n_words == 1:
                fades.append(f"[{hl_idx}:v]format=rgba[hs0]")
            else:
                outs = "".join(f"[hs{i}]" for i in range(n_words))
                fades.append(f"[{hl_idx}:v]split={n_words}{outs}")
            parts = []
            src = "txtv"
            for i, (box, (t0, t1)) in enumerate(pairs):
                span = max(0.0, t1 - t0)
                fade_d = min(0.15, span * 0.25)
                if fade_d >= 0.03:
                    fades.append(
                        f"[hs{i}]format=rgba,"
                        f"fade=t=in:st={t0:.2f}:d={fade_d:.2f}:alpha=1,"
                        f"fade=t=out:st={t1 - fade_d:.2f}:d={fade_d:.2f}:alpha=1"
                        f"[hf{i}]"
                    )
                else:
                    fades.append(f"[hs{i}]format=rgba[hf{i}]")
                out_lbl = f"hl{i}"
                cx = int(box["x"] + (box["w"] - hl_w) / 2)
                cy = int(box["y"] + (box["h"] - hl_h) / 2)
                parts.append(
                    f"[{src}][hf{i}]overlay=x={cx}:y={cy}:"
                    f"enable='between(t,{t0:.2f},{t1:.2f})'[{out_lbl}]"
                )
                src = out_lbl
            if parts:
                hl_chain = ";" + ";".join(fades + parts)
                hl_final = src

    # Outro fade — applied to the final composite so the segment eases
    # out before the next one takes over.  Skipped on the very last
    # segment to avoid a fade-to-black at the very end of the video.
    outro_fade_filter = ""
    last_v = "v"
    if not is_last:
        outro_d = min(0.4, max(0.1, duration_sec / 2))
        outro_st = max(0.0, duration_sec - outro_d)
        outro_fade_filter = f"fade=t=out:st={outro_st:.3f}:d={outro_d:.3f}:alpha=1[v]"
        last_v = "vpre"

    if n == 1:
        filt = f"[0:v]trim=duration={duration_sec},setpts=PTS-STARTPTS,fps={quality_config['fps']}[{last_v}]"
        if text_idx is not None:
            # Text above background, below outro fade — fade eases the
            # composite so text and video leave together.
            for overlay_i, (_, start, end) in enumerate(text_overlays):
                label = ("txtv" if overlay_i == len(text_overlays) - 1
                         else f"txtv{overlay_i}")
                filt += (f";[{last_v}][{text_idx + overlay_i}:v]"
                         f"overlay=0:0:enable='between(t,{start:.3f},{end:.3f})'"
                         f"[{label}]")
                last_v = label
            if hl_chain:
                filt += hl_chain
                last_v = hl_final
        if outro_fade_filter:
            filt = filt + ";" + f"[{last_v}]{outro_fade_filter}"
            last_v = "v"
        map_args = ["-map", f"[{last_v}]", "-map", "1:a"]
        cmd = [FFMPEG_EXE] + common_args + inputs + [
            "-filter_complex", filt,
        ] + map_args + [
            "-t", str(duration_sec), *_video_encoding_args(quality_config), "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-shortest",
            output_path
        ]
    else:
        v_parts = ""
        for i in range(n):
            v_parts += f"[{i}:v]trim=duration={part_dur},setpts=PTS-STARTPTS,fps={quality_config['fps']}[v{i}];"
        v_parts += "".join([f"[v{i}]" for i in range(n)]) + f"concat=n={n}:v=1:a=0[bg];"
        filt = v_parts + f"[bg]null[{last_v}]"
        if text_idx is not None:
            for overlay_i, (_, start, end) in enumerate(text_overlays):
                label = ("txtv" if overlay_i == len(text_overlays) - 1
                         else f"txtv{overlay_i}")
                filt += (f";[{last_v}][{text_idx + overlay_i}:v]"
                         f"overlay=0:0:enable='between(t,{start:.3f},{end:.3f})'"
                         f"[{label}]")
                last_v = label
            if hl_chain:
                filt += hl_chain
                last_v = hl_final
        if outro_fade_filter:
            filt = filt + ";" + f"[{last_v}]{outro_fade_filter}"
            last_v = "v"
        map_args = ["-map", f"[{last_v}]", "-map", f"{n}:a"]

        cmd = [FFMPEG_EXE] + common_args + inputs + [
            "-filter_complex", filt,
        ] + map_args + [
            "-t", str(duration_sec), *_video_encoding_args(quality_config), "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-shortest",
            output_path
        ]

    try:
        logging.info(f"Running FFmpeg command (timeout=300s): {' '.join(cmd[:8])}...")
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300)
        logging.info(f"FFmpeg completed in {result.stderr.count('frame=')} frames")
    except subprocess.TimeoutExpired:
        logging.error(f"FFmpeg timeout after 300s - this may be due to large background video")
        try:
            fallback_cmd = cmd.copy()
            fallback_cmd[-1] = output_path.replace('.mp4', '_fallback.mp4')
            if "-preset" in fallback_cmd:
                idx = fallback_cmd.index("-preset")
                fallback_cmd[idx+1] = "ultrafast"
            if "-crf" not in fallback_cmd:
                fallback_cmd.insert(-1, "-crf")
                fallback_cmd.insert(-1, "35")
            logging.warning("Trying fallback with lower quality...")
            result = subprocess.run(fallback_cmd, check=True, capture_output=True, text=True, timeout=180)
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
    """Process one ayah: download audio, fetch background, build a video
    segment with the audio muxed onto the background.

    Uses ``BackgroundRotator`` to prevent video repetition.  The first
    element of ``args`` is the :class:`JobContext` for the build —
    passed explicitly so the worker thread (which has its own
    thread-local storage) uses the *parent* build's job_id, not a
    racey global.  See ``bug.md`` Issue 2 P0 #5
    ("ThreadPool race conditions").
    """
    (job, reciter_id, surah, ayah, idx, template, bg_style, quality,
     reciter_speed, is_last, show_text, highlight_words,
     text_position, frame_size, include_bismillah) = args

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

        # Feature 002-ayah-text-sync: render the ayah's exact text onto a
        # transparent full-frame PNG.  Fetch failure = loud job failure
        # (Constitution II / FR-010) — never a silent textless success.
        text_png_path = None
        timed_text_overlays = []
        highlight = None
        # Word timing is not provided by the audio sources. The existing
        # proportional estimate is not authoritative recitation timing, so
        # keep exports at accurate ayah-level sync until timestamps exist.
        use_highlight = False
        bismillah_lead = should_show_bismillah_visual(
            include_bismillah, surah, ayah)
        lead_end = min(BISMILLAH_DURATION_SEC, duration)
        if bismillah_lead:
            bismillah_path = current_job().text_png_path(0)
            render_ayah_text_png(
                "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ",
                bismillah_path, template=template, frame_w=frame_size[0],
                frame_h=frame_size[1], position=text_position)
            timed_text_overlays.append((bismillah_path, 0.0, lead_end))
            add_log("Bismillah: visual lead-in over ayah audio; no added silence")
        if show_text and highlight_words:
            add_log(f"highlight: unavailable, no verified word timestamps ({surah}:{ayah})")
        if show_text:
            add_log(f"text: fetching ({surah}:{ayah})")
            try:
                ayah_text_str = get_ayah_text(surah, ayah)
            except Exception as exc:
                raise RuntimeError(
                    f"تعذر جلب نص الآية {surah}:{ayah} — تحقق من الاتصال "
                    f"ومصدر النص"
                ) from exc
            meta = render_ayah_text_png(
                ayah_text_str,
                current_job().text_png_path(idx),
                template=template,
                duration_sec=duration,
                frame_w=frame_size[0],
                frame_h=frame_size[1],
                with_highlight=use_highlight,
                highlight_path=current_job().highlight_png(idx),
                position=text_position,
            )
            if bismillah_lead:
                timed_text_overlays.append((meta["png"], lead_end, duration))
                text_png_path = timed_text_overlays
            else:
                text_png_path = meta["png"]
            add_log(f"text: rendered ({surah}:{ayah})")
            if use_highlight:
                if meta.get("windows") and meta.get("highlight"):
                    highlight = {
                        "png": meta["highlight"]["png"],
                        "w": meta["highlight"]["w"],
                        "h": meta["highlight"]["h"],
                        "words": meta["words"],
                        "windows": meta["windows"],
                    }
                    add_log(f"highlight: on ({surah}:{ayah}, "
                            f"{len(meta['words'])} words)")
                else:
                    # No audio duration → no reliable word timings:
                    # graceful plain-display fallback (FR-011).
                    add_log(f"highlight: unavailable, plain display "
                            f"({surah}:{ayah})")
        elif bismillah_lead:
            text_png_path = timed_text_overlays
        else:
            add_log(f"text: skipped ({surah}:{ayah})")

        # Select background using rotator to prevent repetition
        bg_path = get_next_background(bg_style, count=1)
        bg_paths = bg_path if isinstance(bg_path, list) else [bg_path]
        logging.debug(f"Segment {idx}: Using background {os.path.basename(bg_paths[0])}")

        segment_out = current_job().segment_path(idx)
        ayah_num = f"{surah}:{ayah}"
        build_segment_ffmpeg(bg_paths, audio_path, duration, segment_out, is_last=is_last, ayah_num=ayah_num, surah_name=SURAH_NAMES[surah-1], text_png_path=text_png_path, highlight=highlight, frame_size=frame_size, quality=quality)

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
                person_name='', target_duration_seconds=None,
                include_bismillah=False, reciter_speed=1.0,
                transition_style_override=None,
                show_text=SHOW_TEXT_DEFAULT,
                highlight_words=HIGHLIGHT_WORDS_DEFAULT,
                text_position=TEXT_POSITION_DEFAULT):
    """Main video builder.

    Downloads each ayah's recitation, muxes it onto a background video
    (selected from a rotating pool to avoid repetition), and concatenates
    the segments into a single mp4.  With ``show_text`` (feature
    002-ayah-text-sync) each segment additionally composites the exact
    Uthmani text of its ayah; with it disabled the output is identical
    to the audio + background pipeline.

    Args:
      reciter_id:        Reciter identifier (key of ``RECITERS_MAP``).
      surah:             Surah number (1..114).
      start_ayah:        First ayah to include.
      end_ayah:          Last ayah to include (defaults to ``start_ayah + 9``).
      quality:           One of ``QUALITY_PRESETS`` keys.
      format_type:       One of ``OUTPUT_FORMATS`` keys.
      template:          One of ``TEMPLATES`` keys (drives background style).
      person_name:       Optional string for the output filename.
      target_duration_seconds: Optional cap on the total video length.
      include_bismillah: If True and the surah is not in
                         ``BISMILLAH_SKIP_SURAHS``, show an unsynchronized
                         1.8 s visual lead-in over the first ayah's audio.
      reciter_speed:     0.5..2.0; tempo multiplier applied via ffmpeg atempo.
      transition_style_override: Optional key of ``VIDEO_TRANSITIONS`` to
                                 override the template's default.

    Returns:
        str | None: Absolute ``output_path`` of the final mp4 on success,
        or ``None`` on failure.  Progress and errors are also reported
        via ``current_progress`` so the existing
        ``threading.Thread(target=build_video, ...)`` callers in the API
        routes continue to work unchanged.
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
        video_encode_args = _video_encoding_args(quality_config)
        format_config = OUTPUT_FORMATS.get(format_type, OUTPUT_FORMATS['reels'])
        frame_size = tuple(format_config['size'])
        template_config = TEMPLATES.get(template, TEMPLATES['normal'])
        if transition_style_override:
            # Caller (UI/API) picked an explicit style; shallow-copy so we
            # don't mutate the shared TEMPLATES dict.
            template_config = {**template_config, 'transition_style': transition_style_override}
        bg_style = template_config['bg_style']

        # Feature 002-ayah-text-sync (FR-009): the text style profile is
        # resolved ONCE per job from the template key.  Workers re-derive
        # styling from the same immutable TEXT_STYLE_PROFILES entry via
        # that key, so every segment of a reel shares identical text
        # appearance.
        _text_profile = resolve_profile(template)
        logging.info(f"Text profile for job: {template} → {_text_profile}")

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

        # Get the transition style from the template (no more text animation).
        video_transition = template_config.get('transition', 'fade')
        logging.info(f"Using transition: {video_transition}")

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

        # Prepare args.  The leading ``job`` element is the per-build
        # :class:`JobContext` captured at the top of ``build_video`` —
        # passed explicitly so the worker threads (which have their own
        # thread-local storage) cannot race on a global job_id.  See
        # ``bug.md`` Issue 2 P0 #5.
        total_ayahs = last_ayah - start_ayah + 1
        # Feature 002 text position: normalize once per job; workers reuse
        # the same anchor so every segment agrees.
        if text_position not in TEXT_POSITIONS:
            text_position = TEXT_POSITION_DEFAULT
        job = current_job()
        ayah_args = [
            (job, reciter_id, surah, ayah, idx, template, bg_style, quality,
             reciter_speed, idx == total_ayahs, show_text, highlight_words,
             text_position, frame_size, include_bismillah)
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

        # Bismillah is an opt-in visual lead-in rendered over the first
        # ayah's audio. It does not create a synthetic silent segment.
        segment_results = []
        if include_bismillah and surah in BISMILLAH_SKIP_SURAHS:
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
                *video_encode_args,
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
                        *video_encode_args,
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
                            f"duration={xfade_d}:offset={offset:.3f}[v{i+1}]"
                        )

                # Keep audio contiguous and complete. Video crossfades shorten
                # the visual timeline, so hold the final frame for that lost time.
                    last_v = f"v{len(segment_results) - 1}"
                    audio_inputs = "".join(f"[a{i}]" for i in range(len(segment_results)))
                    video_extension = xfade_d * max(0, len(segment_results) - 1)
                    filter_complex.append(
                        f"[{last_v}]tpad=stop_mode=clone:stop_duration={video_extension:.3f},null[outv];"
                        f"{audio_inputs}concat=n={len(segment_results)}:v=0:a=1[outa]"
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
                    *video_encode_args,
                        "-c:a", "aac", "-b:a", "192k",
                        "-movflags", "+faststart",
                        temp_output_path
                ]

            except Exception as e:
                logging.warning(f"Crossfade setup failed, using simple concat: {e}")

                # Fallback to simple concat (list_path already exists)
                cmd_concat = [
                    FFMPEG_EXE, "-y", "-f", "concat", "-safe", "0", "-i", list_path,
                    *video_encode_args,
                    "-c:a", "aac", "-b:a", "192k",
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
                        *video_encode_args,
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

def _job_audio_path(idx: int) -> str:
    """Return job-scoped temp audio path; falls back to legacy TEMP_DIR path."""
    try:
        return current_job().audio_path(idx)
    except Exception:
        return os.path.join(TEMP_DIR, f'audio_{idx:03d}.mp3')


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
        # Copy to job-scoped temp path so parallel builds don't collide
        out = _job_audio_path(idx)
        shutil.copy2(cached_path, out)
        return out

    # Try multiple sources with different domains
    sources = [
        f'https://everyayah.com/data/{reciter_id}/{fn}',
        f'https://download.quranicaudio.com/quran/{reciter_id}/{fn}',
        f'https://www.everyayah.com/data/{reciter_id}/{fn}',
        f'https://mp3.quranicaudio.com/quran/{reciter_id}/{fn}'
    ]

    out = _job_audio_path(idx)

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

            # ظ£à NO TRIMMING AT ALL - Keep original Quran recitation intact
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
            files = [f for f in os.listdir(style_dir) if f.lower().endswith('.mp4')]
            logging.debug(f"Found {len(files)} files in {style_dir}/")
        else:
            # Fallback: try old pattern-based naming in main vision folder
            pattern = f"{style}_part"
            space_pattern = pattern.replace('_', ' ')
            files = [f for f in os.listdir(VISION_DIR)
                     if (f.startswith(pattern) or f.startswith(space_pattern))
                     and f.lower().endswith('.mp4')]
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
        selected_file = sorted(files, key=str.casefold)[0]
        style_dir = os.path.join(VISION_DIR, style)

        # Check if style folder exists, fallback to main vision folder
        if os.path.isdir(style_dir):
            return os.path.join(style_dir, selected_file)
        else:
            return os.path.join(VISION_DIR, selected_file)
    else:
        selected = sorted(files, key=str.casefold)[:min(count, len(files))]
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




# STEP 18: API ROUTES (SIMPLIFIED)
# =============================================================================

def _validated_api_payload():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, (jsonify({'error': 'الطلب غير صالح؛ أرسل بيانات JSON صحيحة'}), 400)

    try:
        surah = int(data.get('surah', 1))
        start_ayah = int(data.get('startAyah', data.get('ayah', 1)))
        end_value = data.get('endAyah', start_ayah)
        end_ayah = int(end_value) if end_value not in (None, '') else start_ayah
        reciter_id = data.get('reciter')
        speed = float(data.get('reciterSpeed', 1.0))
        raw_duration = data.get('targetDurationSeconds')
        target_duration = (None if raw_duration in (None, '')
                           else int(raw_duration))
    except (TypeError, ValueError):
        return None, (jsonify({'error': 'تحقق من اختيار القارئ والسورة وأرقام الآيات'}), 400)

    if reciter_id not in RECITERS_MAP.values():
        return None, (jsonify({'error': 'اختر قارئاً من القائمة'}), 400)
    if surah not in VERSE_COUNTS:
        return None, (jsonify({'error': 'رقم السورة يجب أن يكون بين 1 و114'}), 400)
    if not 1 <= start_ayah <= VERSE_COUNTS[surah]:
        return None, (jsonify({'error': 'آية البداية خارج نطاق السورة المختارة'}), 400)
    if not start_ayah <= end_ayah <= VERSE_COUNTS[surah]:
        return None, (jsonify({'error': 'آية النهاية يجب أن تساوي آية البداية أو تليها ضمن السورة'}), 400)
    if not 0.5 <= speed <= 2.0:
        return None, (jsonify({'error': 'سرعة التلاوة يجب أن تكون بين 0.5 و2.0'}), 400)
    if target_duration is not None and target_duration < 1:
        return None, (jsonify({'error': 'المدة القصوى يجب أن تكون ثانية واحدة على الأقل'}), 400)

    quality = data.get('quality', 'medium')
    format_type = data.get('format', 'reels')
    template = data.get('template', 'normal')
    transition_style = data.get('transitionStyle') or None
    if quality not in QUALITY_PRESETS:
        return None, (jsonify({'error': 'جودة الفيديو المختارة غير صالحة'}), 400)
    if format_type not in OUTPUT_FORMATS:
        return None, (jsonify({'error': 'تنسيق الفيديو المختار غير صالح'}), 400)
    if template not in TEMPLATES:
        return None, (jsonify({'error': 'القالب المختار غير صالح'}), 400)
    if transition_style not in (None, 'cinematic', 'dynamic', 'smooth', 'cut'):
        return None, (jsonify({'error': 'أسلوب الانتقال المختار غير صالح'}), 400)

    return {
        'data': data,
        'reciter': reciter_id,
        'surah': surah,
        'startAyah': start_ayah,
        'endAyah': end_ayah,
        'speed': speed,
        'targetDurationSeconds': target_duration,
        'quality': quality,
        'format': format_type,
        'template': template,
        'transitionStyle': transition_style,
    }, None

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

@app.route('/assets/<path:filename>')
def serve_asset(filename):
    return send_from_directory(os.path.join(EXEC_DIR, 'assets'), filename)

@app.route('/api/generate', methods=['POST'])
def generate_video():
    if current_progress.is_running:
        return jsonify({'error': 'عملية إنشاء فيديو قيد التنفيذ بالفعل'}), 400

    payload, error = _validated_api_payload()
    if error:
        return error
    data = payload['data']
    reciter_id = payload['reciter']
    surah = payload['surah']
    start_ayah = payload['startAyah']
    end_ayah = payload['endAyah']
    quality = payload['quality']
    format_type = payload['format']
    template = payload['template']
    person_name = data.get('personName', '')
    target_duration_seconds = payload['targetDurationSeconds']
    include_bismillah = data.get('includeBismillah', False)
    reciter_speed = payload['speed']
    transition_style_override = payload['transitionStyle']
    show_text = bool(data.get('showText', data.get('show_text', SHOW_TEXT_DEFAULT)))
    highlight_words = bool(data.get(
        'highlightWords', data.get('highlight_words', HIGHLIGHT_WORDS_DEFAULT)))
    text_position = str(data.get(
        'textPosition', data.get('text_position', TEXT_POSITION_DEFAULT))
        or TEXT_POSITION_DEFAULT).lower()
    if text_position not in TEXT_POSITIONS:
        text_position = TEXT_POSITION_DEFAULT

    reset_progress()
    current_progress.set(is_running=True, is_complete=False, error=None)

    thread = threading.Thread(
        target=build_video,
        args=(reciter_id, surah, start_ayah, end_ayah, quality,
              format_type, template, person_name, target_duration_seconds,
              include_bismillah, reciter_speed, transition_style_override,
              show_text, highlight_words, text_position),
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

    payload, error = _validated_api_payload()
    if error:
        return error
    data = payload['data']
    reciter_id = payload['reciter']
    surah = payload['surah']
    ayah = payload['startAyah']
    template = payload['template']
    show_text = bool(data.get('showText', data.get('show_text', SHOW_TEXT_DEFAULT)))
    highlight_words = bool(data.get(
        'highlightWords', data.get('highlight_words', HIGHLIGHT_WORDS_DEFAULT)))
    text_position = str(data.get(
        'textPosition', data.get('text_position', TEXT_POSITION_DEFAULT))
        or TEXT_POSITION_DEFAULT).lower()
    if text_position not in TEXT_POSITIONS:
        text_position = TEXT_POSITION_DEFAULT

    reset_progress()
    current_progress.set(is_running=True, is_complete=False, error=None)
    thread = threading.Thread(
        target=build_video,
        args=(reciter_id, surah, ayah, ayah, 'low', 'reels', template, '', None,
              False, 1.0, None, show_text, highlight_words, text_position),
        daemon=True
    )
    thread.start()
    return jsonify({'success': True, 'message': 'بدأ إنشاء المعاينة'})

@app.route('/api/config', methods=['GET'])
def get_config():
    return jsonify({
        'surahs': SURAH_NAMES,
        'verseCounts': VERSE_COUNTS,
        'reciters': RECITERS_MAP,
        'qualityPresets': list(QUALITY_PRESETS.keys()),
        'outputFormats': list(OUTPUT_FORMATS.keys()),
        'templates': list(TEMPLATES.keys()),
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

    # Initialize background cache
    init_bg_cache()

    # webbrowser.open('http://127.0.0.1:5000')
    app.run(
        host=_env("QURAN_FLASK_HOST", "127.0.0.1"),
        port=_env("QURAN_FLASK_PORT", 5000, int),
        debug=_env("QURAN_FLASK_DEBUG", False, lambda s: s.lower() in ("1", "true", "yes", "on")),
        threaded=True,
    )
