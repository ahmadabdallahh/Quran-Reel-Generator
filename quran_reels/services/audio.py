"""Audio helpers: download, caching, duration probing, ayah text fetch.

Extracted from ``main.py`` STEP 11/12 to make the monolith testable and to
remove the duplicated block that used to live twice in the file.  All
path/id constants (``TEMP_DIR``, ``AUDIO_CACHE_DIR`` etc.) are imported
lazily from ``main`` so this module does not create a circular import at
load time.  Public names are re-exported by ``main`` for backward compat
(``from main import download_audio`` continues to work).
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
import time
from typing import Dict

import requests as http_requests
from urllib3.util.retry import Retry


# ---------------------------------------------------------------------------
# Ayah text cache (in-memory, per-process)
# ---------------------------------------------------------------------------
AYAH_TEXT_CACHE: Dict[str, str] = {}


def get_ayah_text(surah: int, ayah: int) -> str:
    """Fetch Uthmani ayah text from api.alquran.cloud with one retry."""
    cache_key = f"{surah}:{ayah}"
    if cache_key in AYAH_TEXT_CACHE:
        logging.debug(f"Using cached text for {cache_key}")
        return AYAH_TEXT_CACHE[cache_key]

    def _fetch() -> str:
        resp = http_requests.get(
            f"https://api.alquran.cloud/v1/ayah/{surah}:{ayah}/quran-uthmani",
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["data"]["text"].replace("\ufeff", "").replace("\u200b", "").strip()
        if not text or len(text) < 5:
            raise ValueError(f"Ayah text too short: {text!r}")
        return text

    try:
        text = _fetch()
    except Exception as e:
        logging.debug(f"Text fetch failed, retrying once: {e}")
        text = _fetch()
    AYAH_TEXT_CACHE[cache_key] = text
    return text


# ---------------------------------------------------------------------------
# ffprobe helper
# ---------------------------------------------------------------------------

def get_audio_duration_ffprobe(audio_path: str) -> float:
    """Return duration in seconds via ffprobe."""
    from main import FFPROBE_EXE  # lazy

    exe = FFPROBE_EXE or "ffprobe"
    cmd = [
        exe, "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", audio_path,
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=True)
    return float(out.stdout.strip())


# ---------------------------------------------------------------------------
# Circuit breaker for audio downloads
# ---------------------------------------------------------------------------
_circuit_breaker_failures = 0
_circuit_breaker_last_failure = 0.0
_circuit_breaker_threshold = 5
_circuit_breaker_timeout = 60  # seconds
_circuit_lock = threading.Lock()


def is_circuit_breaker_open() -> bool:
    with _circuit_lock:
        if _circuit_breaker_failures >= _circuit_breaker_threshold:
            if time.time() - _circuit_breaker_last_failure > _circuit_breaker_timeout:
                return False
            return True
        return False


def record_download_success() -> None:
    global _circuit_breaker_failures
    with _circuit_lock:
        _circuit_breaker_failures = 0


def record_download_failure() -> None:
    global _circuit_breaker_failures, _circuit_breaker_last_failure
    with _circuit_lock:
        _circuit_breaker_failures += 1
        _circuit_breaker_last_failure = time.time()


def reset_circuit_breaker() -> None:
    global _circuit_breaker_failures, _circuit_breaker_last_failure
    with _circuit_lock:
        _circuit_breaker_failures = 0
        _circuit_breaker_last_failure = 0.0


# ---------------------------------------------------------------------------
# Paths / cache
# ---------------------------------------------------------------------------

def get_cached_audio_path(reciter_id: str, surah: int, ayah: int) -> str:
    """Return (and ensure) the on-disk path for a cached ayah mp3."""
    from main import AUDIO_CACHE_DIR  # lazy

    fn = f"{surah:03d}{ayah:03d}.mp3"
    reciter_dir = os.path.join(AUDIO_CACHE_DIR, str(reciter_id))
    os.makedirs(reciter_dir, exist_ok=True)
    return os.path.join(reciter_dir, fn)


def _job_audio_path(idx: int) -> str:
    """Job-scoped temp audio path; falls back to legacy TEMP_DIR path."""
    try:
        from main import current_job, TEMP_DIR  # lazy
        return current_job().audio_path(idx)
    except Exception:
        from main import TEMP_DIR  # type: ignore
        return os.path.join(TEMP_DIR, f"audio_{idx:03d}.mp3")


def cleanup_audio_cache() -> None:
    """LRU-evict audio cache if it exceeds size/count limits."""
    try:
        from main import AUDIO_CACHE_DIR, AUDIO_CACHE_MAX_SIZE_MB, AUDIO_CACHE_MAX_FILES  # lazy

        audio_files = []
        for root, _, files in os.walk(AUDIO_CACHE_DIR):
            for file in files:
                if file.endswith(".mp3"):
                    fp = os.path.join(root, file)
                    try:
                        stat = os.stat(fp)
                        audio_files.append((fp, stat.st_size, stat.st_mtime))
                    except OSError:
                        continue
        audio_files.sort(key=lambda x: x[2])
        total_size = sum(s for _, s, _ in audio_files) / (1024 * 1024)
        files_to_remove = []
        if total_size > AUDIO_CACHE_MAX_SIZE_MB or len(audio_files) > AUDIO_CACHE_MAX_FILES:
            excess_size = total_size - AUDIO_CACHE_MAX_SIZE_MB
            excess_files = len(audio_files) - AUDIO_CACHE_MAX_FILES
            for fp, size, _ in audio_files:
                if excess_size > 0 or excess_files > 0:
                    files_to_remove.append(fp)
                    excess_size -= size / (1024 * 1024)
                    excess_files -= 1
                else:
                    break
        for fp in files_to_remove:
            try:
                os.remove(fp)
                logging.debug(f"Removed old cache file: {os.path.basename(fp)}")
            except OSError:
                pass
        if files_to_remove:
            logging.info(f"Cleaned {len(files_to_remove)} old audio cache files")
    except Exception as e:
        logging.warning(f"Audio cache cleanup failed: {e}")


_AYAH_DURATION_ESTIMATE_SEC = 5.0


def estimate_ayah_duration(reciter_id: str, surah: int, ayah: int) -> float:
    p = get_cached_audio_path(reciter_id, surah, ayah)
    if os.path.exists(p) and os.path.getsize(p) > 1000:
        try:
            return get_audio_duration_ffprobe(p)
        except Exception:
            pass
    return _AYAH_DURATION_ESTIMATE_SEC


# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------

def download_audio(reciter_id: str, surah: int, ayah: int, idx: int) -> str:
    """Download (or copy from cache) one ayah's recitation mp3.

    The file is written to a job-scoped path so parallel builds do not
    collide.  Retry covers multiple mirrors plus urllib3 retries and
    exponential back-off; the circuit breaker is per-process and reset
    per job by ``main.start_new_job``.
    """
    fn = f"{surah:03d}{ayah:03d}.mp3"

    if is_circuit_breaker_open():
        raise RuntimeError("Circuit breaker is open - too many consecutive failures")

    cached_path = get_cached_audio_path(reciter_id, surah, ayah)
    if os.path.exists(cached_path) and os.path.getsize(cached_path) > 1000:
        logging.debug(f"Using cached audio: {fn}")
        out = _job_audio_path(idx)
        shutil.copy2(cached_path, out)
        return out

    sources = [
        f"https://everyayah.com/data/{reciter_id}/{fn}",
        f"https://download.quranicaudio.com/quran/{reciter_id}/{fn}",
        f"https://www.everyayah.com/data/{reciter_id}/{fn}",
        f"https://mp3.quranicaudio.com/quran/{reciter_id}/{fn}",
    ]
    out = _job_audio_path(idx)

    session = http_requests.Session()
    retry_strategy = Retry(
        total=5,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504, 408],
        allowed_methods=["GET"],
    )
    adapter = http_requests.adapters.HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    for attempt, url in enumerate(sources, 1):
        try:
            logging.debug(f"Downloading audio from source {attempt}: {url}")
            if attempt > 1:
                delay = min(2 ** (attempt - 2), 10)
                time.sleep(delay)
                logging.debug(f"Retry delay: {delay}s")
            r = session.get(url, timeout=30)
            r.raise_for_status()
            with open(out, "wb") as f:
                f.write(r.content)
            if os.path.getsize(out) < 1000:
                raise ValueError(f"Audio file too small: {os.path.getsize(out)} bytes")
            logging.debug(f"Audio downloaded: {fn} ({os.path.getsize(out)} bytes)")
            try:
                os.makedirs(os.path.dirname(cached_path), exist_ok=True)
                shutil.copy2(out, cached_path)
                logging.debug(f"Audio cached: {cached_path}")
            except Exception as e:
                logging.warning(f"Failed to cache audio: {e}")
            record_download_success()
            return out
        except Exception as e:
            logging.warning(f"Source {attempt} failed: {e}")
            record_download_failure()
            if attempt < len(sources):
                continue
            if _circuit_breaker_failures >= _circuit_breaker_threshold:
                logging.error("Circuit breaker opened due to consecutive failures")
            raise RuntimeError(f"Failed to download audio for {surah}:{ayah} from all sources") from e


def download_audio_parallel(reciter_id: str, ayah_list, max_workers: int = 4) -> dict:
    """Parallel batch download with simple rate limiting (0.5 s gap)."""
    import concurrent.futures

    results: dict = {}
    download_lock = threading.Lock()
    last_download_time = 0.0
    min_delay = 0.5

    def download_with_delay(args):
        nonlocal last_download_time
        rid, surah, ayah, idx = args
        with download_lock:
            now = time.time()
            if now - last_download_time < min_delay:
                time.sleep(min_delay - (now - last_download_time))
            last_download_time = time.time()
        try:
            path = download_audio(rid, surah, ayah, idx)
            return (ayah, path, None)
        except Exception as e:
            return (ayah, None, str(e))

    download_args = [(reciter_id, a["surah"], a["ayah"], a["idx"]) for a in ayah_list]
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(download_with_delay, a): a for a in download_args}
        for fut in concurrent.futures.as_completed(futures):
            ayah, path, err = fut.result()
            if err:
                logging.error(f"Failed to download ayah {ayah}: {err}")
                results[ayah] = {"error": err}
            else:
                results[ayah] = {"path": path}
                logging.debug(f"Downloaded ayah {ayah} in parallel")
    return results
