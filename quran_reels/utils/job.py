"""Per-build job context — unique temp file isolation.

Extracted from ``main.py`` STEP 3.5.  Kept as a standalone module so
services can import ``current_job`` / ``start_new_job`` without pulling
in the whole Flask app.  All filesystem roots (``TEMP_DIR``,
``VIDEO_DIR``) are resolved lazily from ``main`` to avoid circular
imports at load time.
"""

from __future__ import annotations

import os
import threading
import time
import uuid


class JobContext:
    """Holds the unique ``job_id`` for one video build and builds per-resource paths."""

    __slots__ = ("job_id", "created_at")

    def __init__(self, job_id: str | None = None):
        self.job_id = job_id or uuid.uuid4().hex[:8]
        self.created_at = time.time()

    # ---- per-ayah paths ----
    def audio_path(self, idx: int) -> str:
        from main import TEMP_DIR  # lazy
        return os.path.join(TEMP_DIR, f"{self.job_id}_audio_{idx:03d}.mp3")

    def sped_path(self, idx: int) -> str:
        from main import TEMP_DIR
        return os.path.join(TEMP_DIR, f"{self.job_id}_audio_{idx:03d}_sped.mp3")

    def segment_path(self, idx: int) -> str:
        from main import TEMP_DIR
        return os.path.join(TEMP_DIR, f"{self.job_id}_segment_{idx:03d}.mp4")

    def text_png_path(self, idx: int) -> str:
        from main import TEMP_DIR
        return os.path.join(TEMP_DIR, f"{self.job_id}_text_{idx:03d}.png")

    def highlight_png(self, idx: int) -> str:
        from main import TEMP_DIR
        return os.path.join(TEMP_DIR, f"{self.job_id}_highlight_{idx:03d}.png")

    # ---- concat / chunk / final-output paths ----
    def concat_list_path(self) -> str:
        from main import TEMP_DIR
        return os.path.join(TEMP_DIR, f"{self.job_id}_concat_{int(time.time() * 1000)}.txt")

    def chunk_list_path(self, ci: int) -> str:
        from main import TEMP_DIR
        return os.path.join(TEMP_DIR, f"{self.job_id}_chunk_{ci:03d}_{int(time.time() * 1000)}.txt")

    def chunk_video_path(self, ci: int) -> str:
        from main import TEMP_DIR
        return os.path.join(TEMP_DIR, f"{self.job_id}_chunk_{ci:03d}_{int(time.time() * 1000)}.mp4")

    def temp_output_path(self, ascii_name: str) -> str:
        from main import TEMP_DIR
        return os.path.join(TEMP_DIR, f"{self.job_id}_{ascii_name}")

    def final_output_path(self, ascii_name: str) -> str:
        from main import VIDEO_DIR  # lazy
        base, ext = os.path.splitext(ascii_name)
        try:
            os.makedirs(VIDEO_DIR, exist_ok=True)
        except Exception:
            pass
        return os.path.join(VIDEO_DIR, f"{base}_{self.job_id}{ext}")


_current_job: JobContext | None = None
_current_job_lock = threading.Lock()
_job_local = threading.local()


def start_new_job() -> JobContext:
    """Start a fresh job context for the calling thread + reset breaker."""
    try:
        from quran_reels.services.audio import reset_circuit_breaker  # lazy
    except Exception:
        reset_circuit_breaker = None  # type: ignore

    ctx = JobContext()
    _job_local.ctx = ctx
    with _current_job_lock:
        global _current_job
        _current_job = ctx
        if reset_circuit_breaker is not None:
            try:
                reset_circuit_breaker()
            except Exception:
                pass
    import logging
    logging.info(f"Started new job: job_id={ctx.job_id}")
    return ctx


def current_job() -> JobContext:
    """Return active JobContext for this thread, creating one lazily if needed."""
    ctx = getattr(_job_local, "ctx", None)
    if ctx is not None:
        return ctx
    return start_new_job()
