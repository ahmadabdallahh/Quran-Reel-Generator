"""Render-finished notifications.

Three delivery paths cover the ways a render can finish while you are
looking somewhere else:

  1. **Desktop toast** — ``notify-send`` (libnotify).  Fires from a
     daemon thread so a slow or missing notification daemon can never
     delay the render thread or leave ``current_progress.is_running``
     stuck.  Silently skipped when the process has no desktop session
     (headless server, systemd unit, SSH), which is common for this app.
  2. **Browser notification** — driven by the UI from the event feed
     this module keeps (``recent_events``).  Works whenever the tab is
     open, even in the background.
  3. **Event history** — the last :data:`HISTORY_LIMIT` events are kept
     in memory and shipped with ``/api/progress``.  The UI uses them to
     raise a "finished while you were away" banner on the next page
     load, covering the case where both live channels were unavailable.

Nothing in here raises: a failed notification must never turn a
successful render into an error.  Every path is guarded, and every
failure is logged once at ``info`` level.

Configuration (read lazily from the environment so ``.env`` and tests
work without importing ``main``):

  * ``QURAN_NOTIFY_ENABLED``  — ``1``/``0``, default ``1``.
  * ``QURAN_NOTIFY_URGENCY``  — ``low`` | ``normal`` | ``critical``,
    default ``normal``.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, List, Optional

HISTORY_LIMIT = 20
APP_NAME = 'Quran Reels'
TOAST_TIMEOUT_SECONDS = 6
_ERROR_BODY_LIMIT = 140

_enabled_warned = False
_desktop_missing_logged = False


@dataclass(frozen=True)
class RenderEvent:
    """One finished render — success or failure."""

    id: int
    ts: float
    ok: bool
    title: str
    body: str
    output_path: Optional[str] = None
    error: Optional[str] = None
    filename: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        return {
            'id': self.id,
            'ts': self.ts,
            'ok': self.ok,
            'title': self.title,
            'body': self.body,
            'output_path': self.output_path,
            'error': self.error,
            'filename': self.filename,
        }


_events: Deque[RenderEvent] = deque(maxlen=HISTORY_LIMIT)
_events_lock = threading.Lock()
_next_id = 0


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

def _env_bool(key: str, default: bool) -> bool:
    raw = os.environ.get(key)
    if raw is None or raw == '':
        return default
    return raw.strip().lower() in ('1', 'true', 'yes', 'on')


def _enabled() -> bool:
    return _env_bool('QURAN_NOTIFY_ENABLED', True)


def _urgency() -> str:
    raw = (os.environ.get('QURAN_NOTIFY_URGENCY') or 'normal').strip().lower()
    return raw if raw in ('low', 'normal', 'critical') else 'normal'


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def _sanitise(text: str, *, single_line: bool) -> str:
    """Strip control characters that would corrupt a toast body."""
    cleaned = ''.join(
        ch for ch in str(text)
        if (ch == '\n' and not single_line) or ord(ch) >= 0x20
    )
    if single_line:
        cleaned = cleaned.replace('\r', ' ').replace('\n', ' ')
    return cleaned.strip()


def _format_duration(seconds: Optional[float]) -> Optional[str]:
    if not seconds or seconds <= 0:
        return None
    total = int(round(seconds))
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f'{hours}:{minutes:02d}:{secs:02d}'
    return f'{minutes}:{secs:02d}'


def _format_size(size_bytes: Optional[int]) -> Optional[str]:
    if not size_bytes or size_bytes <= 0:
        return None
    megabytes = size_bytes / (1024 * 1024)
    if megabytes >= 1024:
        return f'{megabytes / 1024:.1f} غ.ب'
    return f'{megabytes:.1f} م.ب'


def _surah_name(surah: int) -> str:
    try:
        from quran_reels.config import SURAH_NAMES  # lazy: keeps import cheap
        if 1 <= int(surah) <= len(SURAH_NAMES):
            return f'سورة {SURAH_NAMES[int(surah) - 1]}'
    except Exception:
        pass
    return f'سورة {surah}'


def _describe(surah: int, start_ayah: int, end_ayah: int) -> str:
    """`سورة الكهف · الآيات 10–20` (single ayah collapses to one number)."""
    try:
        start = int(start_ayah)
        end = int(end_ayah or start_ayah)
    except (TypeError, ValueError):
        return _surah_name(surah)
    span = f'الآية {start}' if end == start else f'الآيات {start}–{end}'
    return f'{_surah_name(surah)} · {span}'


# ---------------------------------------------------------------------------
# Desktop toast
# ---------------------------------------------------------------------------

def _has_desktop_session() -> bool:
    return bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))


def _send_desktop_toast(title: str, body: str) -> None:
    """Run ``notify-send`` once.  Never raises, never blocks the caller."""
    global _desktop_missing_logged

    if not _has_desktop_session():
        if not _desktop_missing_logged:
            logging.info(
                'Notify: no DISPLAY/WAYLAND_DISPLAY; desktop toast disabled. '
                'Browser notification + event history still cover this render.'
            )
            _desktop_missing_logged = True
        return

    exe = shutil.which('notify-send')
    if not exe:
        if not _desktop_missing_logged:
            logging.info(
                'Notify: notify-send not found on PATH; desktop toast disabled.'
            )
            _desktop_missing_logged = True
        return

    command = [
        exe,
        '--app-name', APP_NAME,
        '--urgency', _urgency(),
        '--icon', 'video-x-generic',
        '--', _sanitise(title, single_line=True), _sanitise(body, single_line=False),
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=TOAST_TIMEOUT_SECONDS,
        )
        if result.returncode != 0:
            logging.info(
                'Notify: notify-send exited %s: %s',
                result.returncode, (result.stderr or '').strip()[:200],
            )
    except subprocess.TimeoutExpired:
        logging.info('Notify: notify-send timed out after %ss', TOAST_TIMEOUT_SECONDS)
    except Exception as exc:  # noqa: BLE001 - notifications must never raise
        logging.info('Notify: desktop toast failed: %s', exc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def recent_events(limit: int = HISTORY_LIMIT) -> List[Dict[str, object]]:
    """Return the newest events in ascending ``id`` order (oldest first)."""
    with _events_lock:
        items = list(_events)
    if limit and limit > 0:
        items = items[-limit:]
    return [event.to_dict() for event in items]


def notify_render_finished(*, surah: int, start_ayah: int, end_ayah: int,
                           output_path: Optional[str] = None,
                           error: Optional[str] = None,
                           size_bytes: Optional[int] = None,
                           duration_seconds: Optional[float] = None) -> Optional[RenderEvent]:
    """Record a finished render and fire the desktop toast.

    A render is treated as successful when ``error`` is empty.  Returns
    the recorded :class:`RenderEvent`, or ``None`` if even recording
    failed (the caller keeps going either way).
    """
    global _next_id, _enabled_warned

    try:
        ok = not error
        where = _describe(surah, start_ayah, end_ayah)
        if ok:
            title = 'اكتمل إنشاء الفيديو'
            parts = [where]
            duration = _format_duration(duration_seconds)
            size = _format_size(size_bytes)
            if duration:
                parts.append(duration)
            if size:
                parts.append(size)
            body = ' · '.join(parts)
        else:
            title = 'فشل إنشاء الفيديو'
            reason = _sanitise(error, single_line=True)[:_ERROR_BODY_LIMIT]
            body = f'{where} · {reason}' if reason else where

        filename = os.path.basename(output_path) if output_path else None

        with _events_lock:
            _next_id += 1
            event = RenderEvent(
                id=_next_id,
                ts=time.time(),
                ok=ok,
                title=title,
                body=body,
                output_path=output_path,
                error=error,
                filename=filename,
            )
            _events.append(event)
    except Exception as exc:  # noqa: BLE001
        logging.info('Notify: could not record render event: %s', exc)
        return None

    if not _enabled():
        if not _enabled_warned:
            logging.info('Notify: QURAN_NOTIFY_ENABLED=0; desktop toast skipped.')
            _enabled_warned = True
        return event

    try:
        threading.Thread(
            target=_send_desktop_toast,
            args=(event.title, event.body),
            name='render-notify',
            daemon=True,
        ).start()
    except Exception as exc:  # noqa: BLE001
        logging.info('Notify: could not start toast thread: %s', exc)

    return event
