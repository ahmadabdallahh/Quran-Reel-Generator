"""Thread-safe progress tracking for long-running video builds.

This module replaces the legacy ``current_progress`` global dict in
``main.py``.  The dict had three issues:

  1. No type safety.
  2. ``log.append(message)`` was a non-atomic list mutation that could
     race with the Flask polling thread reading ``log``.
  3. ``reset_progress()`` reassigned a brand-new dict, momentarily
     leaving the name ``current_progress`` pointing at a fresh object
     while readers held a reference to the old one.

``ProgressState`` is a dataclass with an internal ``RLock`` that guards
the only operations which need atomicity (log mutation, snapshot
serialisation, and reset).  Plain attribute reads are intentionally
NOT locked — Python's GIL guarantees atomic single-attribute reads,
and the polling endpoint is allowed to see a slightly stale value.

Migration in ``main.py``:

  * ``current_progress = {...}``           -> ``current_progress = ProgressState()``
  * ``current_progress['percent'] = 70``  -> ``current_progress.percent = 70``
  * ``current_progress['log'].append(x)``  -> ``current_progress.append_log(x)``
  * ``jsonify(current_progress)``          -> ``jsonify(current_progress.to_dict())``
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import RLock
from typing import List, Optional


# A "preparing" sentinel status so a freshly-constructed ProgressState
# (e.g. imported before any work has started) shows a friendly message
# on the first poll rather than an empty string.
DEFAULT_STATUS_AR = 'جاري التحضير...'


@dataclass
class ProgressState:
    """Thread-safe progress state for one video build."""

    # --- User-visible fields (read freely, write via set() / append_log()) ---
    percent:      int                = 0
    status:       str                = DEFAULT_STATUS_AR
    is_running:   bool               = False
    is_complete:  bool               = False
    output_path:  Optional[str]      = None
    error:        Optional[str]      = None
    current_ayah: int                = 0
    total_ayat:   int                = 0
    stage:        str                = 'preparing'  # preparing | downloading | processing | concatenating | complete
    eta_seconds:  Optional[float]    = None
    start_time:   Optional[float]    = None

    # --- Internal ---
    log:   List[str] = field(default_factory=list)
    _lock: RLock     = field(default_factory=RLock, repr=False)

    # --- Atomic mutators ---

    def set(self, **kwargs) -> None:
        """Update any subset of the public fields under the lock.

        Unknown keyword names are silently ignored so callers can pass
        optional updates without branching.
        """
        with self._lock:
            for k, v in kwargs.items():
                if k.startswith('_'):
                    continue
                if hasattr(self, k):
                    setattr(self, k, v)

    def append_log(self, message: str) -> None:
        """Append a log line and keep the history bounded to 500 entries."""
        with self._lock:
            self.log.append(message)
            if len(self.log) > 500:
                # Drop the oldest entries in one slice; assigning to
                # ``self.log`` keeps the snapshot consistent.
                self.log = self.log[-500:]

    def calculate_eta(self) -> None:
        """Recompute ``eta_seconds`` from ``percent`` and ``start_time``.

        Intended to be called from inside a locked section (e.g.
        ``update_progress``) so the percent/status writes and the ETA
        derivation are atomic with respect to readers.
        """
        if self.start_time and self.percent > 0:
            elapsed = time.time() - self.start_time
            if self.percent < 100:
                estimated_total = elapsed * 100 / self.percent
                self.eta_seconds = max(0.0, estimated_total - elapsed)
            else:
                self.eta_seconds = 0

    def to_dict(self) -> dict:
        """Return a JSON-serialisable snapshot of the public state.

        Acquires the lock so the snapshot is consistent even if other
        writers are mutating fields concurrently.
        """
        with self._lock:
            return {
                'percent':      self.percent,
                'status':       self.status,
                'is_running':   self.is_running,
                'is_complete':  self.is_complete,
                'output_path':  self.output_path,
                'error':        self.error,
                'current_ayah': self.current_ayah,
                'total_ayat':   self.total_ayat,
                'stage':        self.stage,
                'eta_seconds':  self.eta_seconds,
                'start_time':   self.start_time,
                'log':          list(self.log),
            }

    def reset(self) -> None:
        """Reset to a fresh-build state and stamp the new start time."""
        with self._lock:
            self.percent      = 0
            self.status       = DEFAULT_STATUS_AR
            self.log          = []
            self.is_running   = False
            self.is_complete  = False
            self.output_path  = None
            self.error        = None
            self.current_ayah = 0
            self.total_ayat   = 0
            self.stage        = 'preparing'
            self.eta_seconds  = None
            self.start_time   = time.time()


# Module-level singleton — the Flask polling endpoint and the worker
# thread started by /api/generate and /api/preview both reach for this
# single instance.  Importing it gives every caller the same object.
current_progress = ProgressState()
