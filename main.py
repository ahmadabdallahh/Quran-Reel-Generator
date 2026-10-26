# Quran Reels Generator — Flask entry point and backwards-compatible exports.

import os
import sys
import shutil
import logging
import atexit

from flask import Flask
from urllib3 import disable_warnings
disable_warnings()
from quran_reels import __version__ as APP_VERSION

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
    TEMPLATE_LABELS,
    BACKGROUND_VIDEO_EXTENSIONS,
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
from quran_reels.utils.cleanup import cleanup_temp, cleanup_orphaned_temp_files
from quran_reels.utils.progress import (
    current_progress, reset_progress, add_log, update_progress,
    update_ayah_progress,
    request_cancel, run_cancellable, raise_if_cancelled, OperationCancelled,
)

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

# Create runtime directories before services resolve their paths.
TEMP_DIR = _env("QURAN_TEMP_DIR", os.path.join(EXEC_DIR, "temp"))
os.makedirs(TEMP_DIR, exist_ok=True)
logging.info(f"Temp directory: {TEMP_DIR}")

AUDIO_CACHE_DIR = _env("QURAN_AUDIO_CACHE_DIR", os.path.join(EXEC_DIR, "cache", "audio"))
os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)
logging.info(f"Audio cache directory: {AUDIO_CACHE_DIR}")

# Runtime paths
OUT_DIR = _env_path("QURAN_OUT_DIR", "outputs")
VIDEO_DIR = _env_path("QURAN_VIDEO_DIR", os.path.join(OUT_DIR, "video"))
BG_CACHE_DIR = _env_path("QURAN_BG_CACHE_DIR", os.path.join("cache", "backgrounds"))
VISION_DIR = _env_path("QURAN_VISION_DIR", "vision")
UI_PATH = _env_path("QURAN_UI_PATH", "UI.html")

from quran_reels.services.themes import get_available_templates

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

# Stateful job and audio services live outside the Flask entry point.
from quran_reels.utils.job import JobContext, current_job, start_new_job, _job_local
from quran_reels.services.audio import (
    cleanup_audio_cache, download_audio, download_audio_parallel,
    estimate_ayah_duration as _estimate_ayah_duration, get_ayah_text,
    get_audio_duration_ffprobe, get_cached_audio_path,
    is_circuit_breaker_open, record_download_failure,
    record_download_success, reset_circuit_breaker,
)

# Cache management
AUDIO_CACHE_MAX_SIZE_MB = _env("QURAN_AUDIO_CACHE_MAX_SIZE_MB", 500, int)  # Maximum cache size in MB
AUDIO_CACHE_MAX_FILES = _env("QURAN_AUDIO_CACHE_MAX_FILES", 1000, int)    # Maximum number of files

# Cleanup orphaned temp files on startup

atexit.register(cleanup_temp)

# Video composition lives in service modules; re-export names to preserve
# existing callers that import helpers from ``main``.
from quran_reels.services.video_rendering import (
    _compute_xfade_pairs, _split_into_chunks, _premerge_chunks,
    _merge_highlight_boxes, _video_encoding_args, HIGHLIGHT_MAX_LAYERS,
    build_segment_ffmpeg,
    process_single_ayah_ffmpeg,
)
from quran_reels.services.video_builder import build_video

# Background selection and preprocessing live in the background service.
from quran_reels.services.background import (
    BG_CACHE, get_preprocessed_bg, init_bg_cache, pick_bg,
)

# HTTP handlers are implemented in a dedicated module and re-exported here
# to preserve the legacy ``main.<handler>`` import surface.
from quran_reels.routes import (
    _validated_api_payload, serve_ui, serve_css, serve_generated_css, serve_js,
    serve_asset, generate_video, get_progress, preview_video, get_config,
    serve_vision, serve_output, register_routes,
)

register_routes(app)

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

    app.run(
        host=_env("QURAN_FLASK_HOST", "127.0.0.1"),
        port=_env("QURAN_FLASK_PORT", 5000, int),
        debug=_env("QURAN_FLASK_DEBUG", False, lambda s: s.lower() in ("1", "true", "yes", "on")),
        threaded=True,
    )
