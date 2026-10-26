"""Background video rotation.

The ``BackgroundRotator`` class and its module-level helpers
(``init_background_rotator``, ``get_next_background``, ``bg_rotator``)
used to live in two places in ``main.py``:

  - The class itself in STEP 8 (alongside the other config dicts).
  - The init/get_next helpers in the post-STEP 13 region.

They are co-located here so a future caller can reason about the
"pick a non-repeating background" responsibility in one place.

The module also keeps the module-level ``bg_rotator`` singleton so the
``global bg_rotator`` rewrite in ``main.py`` is mechanical.

Lazy imports from ``main`` keep the new module decoupled at module-load
time and avoid the circular import that would otherwise occur between
``main`` and ``quran_reels.services.background``.
"""
from __future__ import annotations

import logging
import json
import os
import subprocess
import tempfile
import threading
from typing import List, Optional, Union

from quran_reels.config import (
    BACKGROUND_VIDEO_EXTENSIONS, TARGET_H, TARGET_W,
)


class BackgroundRotator:
    """Manages background video rotation to prevent repetition per video generation."""

    def __init__(self, style: str = 'nature'):
        self.style = style
        self.used_backgrounds = set()
        self.available = self._load_backgrounds()
        self.current_index = 0
        self.usage_history: List[str] = []  # Track usage across sessions
        self.min_distance = 3                # Minimum distance between repeats

    def _load_backgrounds(self) -> List[str]:
        """Load available backgrounds for the style."""
        # Lazy import — VISION_DIR is defined in main.py.
        from main import VISION_DIR

        style_dir = os.path.join(VISION_DIR, self.style)
        if os.path.isdir(style_dir):
            files = [f for f in os.listdir(style_dir)
                     if f.lower().endswith(BACKGROUND_VIDEO_EXTENSIONS)]
            paths = [os.path.join(style_dir, f) for f in files]
        else:
            # Fallback to pattern-based in main vision folder
            pattern = f"{self.style}_part"
            files = [f for f in os.listdir(VISION_DIR)
                     if f.startswith(pattern)
                     and f.lower().endswith(BACKGROUND_VIDEO_EXTENSIONS)]
            paths = [os.path.join(VISION_DIR, f) for f in files]

        # The per-asset score is curated in the manifest after visual review.
        # Unlisted legacy footage stays eligible, with a neutral score.
        project_dir = os.path.abspath(os.path.join(VISION_DIR, os.pardir))
        manifest_path = os.path.join(
            project_dir, "assets", "manifests", "background-videos.json",
        )
        try:
            with open(manifest_path, encoding="utf-8") as manifest_file:
                records = json.load(manifest_file).get("assets", [])
            self.visual_scores = {
                os.path.normcase(os.path.normpath(os.path.join(
                    project_dir, item["path"]
                ))): float(item.get("text_readability_score", 0.5))
                for item in records if item.get("path")
            }
        except (OSError, ValueError, TypeError, KeyError):
            self.visual_scores = {}
        return sorted(paths, key=lambda path: (
            -self.visual_scores.get(os.path.normcase(os.path.normpath(path)), 0.5),
            os.path.basename(path).casefold(),
        ))

    def get_next(self, count: int = 1) -> Union[str, List[str]]:
        """Get next background(s) ensuring variety with smart rotation.

        Selection rules (in order):
          1. Prefer unused backgrounds.
          2. If all are used, fall back to least-recently-used.
          3. Within the candidates, drop any that were used within the last
             ``min_distance`` picks so a background (or, by tie-breaking on
             LRU, a near-recent one) cannot repeat too soon.
          4. If every candidate is filtered out, accept the violation rather
             than starve — the alternative is failing the call.
        """
        if not self.available:
            raise ValueError(f"No backgrounds found for style: {self.style}")

        def _filter_min_distance(candidates):
            """Drop candidates that violate the min_distance rule."""
            if self.min_distance <= 0 or not candidates:
                return candidates
            allowed = [b for b in candidates if not self._violates_min_distance(b)]
            return allowed if allowed else candidates

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
                candidates = _filter_min_distance(candidates)
                # Prefer curated text-safe compositions, then the least
                # recently used eligible clip for predictable variety.
                selected = min(candidates, key=lambda bg: (
                    -self.visual_scores.get(os.path.normcase(os.path.normpath(bg)), 0.5),
                    self._get_last_usage_time(bg),
                    os.path.basename(bg).casefold(),
                ))

                self.used_backgrounds.add(selected)
                self._record_usage(selected)
                return selected
            else:
                # If the recent-use filter excludes every clip, choose the
                # next highest-ranked item instead of randomizing the scene.
                selected = min(self.available, key=lambda bg: (
                    -self.visual_scores.get(os.path.normcase(os.path.normpath(bg)), 0.5),
                    self._get_last_usage_time(bg),
                    os.path.basename(bg).casefold(),
                ))
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
                    candidates = _filter_min_distance(candidates)
                    bg = candidates[0]  # Take the best candidate
                    selected.append(bg)
                    self.used_backgrounds.add(bg)
                    self._record_usage(bg)
                    available_copy.remove(bg)
                else:
                    break

            return selected

    def _get_usage_count(self, bg_path: str) -> int:
        """Get how many times this background was used."""
        return sum(1 for entry in self.usage_history if entry == bg_path)

    def _get_last_usage_time(self, bg_path: str) -> int:
        """Get last usage time (0 if never used)."""
        for i in reversed(range(len(self.usage_history))):
            if self.usage_history[i] == bg_path:
                return i
        return 0

    def _record_usage(self, bg_path: str) -> None:
        """Record background usage."""
        self.usage_history.append(bg_path)
        # Keep history manageable
        if len(self.usage_history) > 100:
            self.usage_history = self.usage_history[-50:]

    def _violates_min_distance(self, bg_path: str) -> bool:
        """Return True if bg_path was used within the last min_distance picks.

        ``min_distance`` is the minimum number of picks between repeats of
        the same background.  When ``min_distance <= 0`` the rule is off.
        """
        if self.min_distance <= 0:
            return False
        recent = self.usage_history[-self.min_distance:] if self.usage_history else []
        return bg_path in recent

    def reset(self) -> None:
        """Reset rotation for new video generation."""
        self.used_backgrounds.clear()
        self.current_index = 0


# Module-level singleton — keep the same shape as the original main.py
# ``bg_rotator = None`` so any ``global bg_rotator`` rewrite in main.py
# is purely a rename.
bg_rotator: Optional[BackgroundRotator] = None


def init_background_rotator(style: str = 'nature') -> BackgroundRotator:
    """Initialize or reset the background rotator for a new video."""
    global bg_rotator
    bg_rotator = BackgroundRotator(style)
    logging.info(f"Background rotator initialized for style: {style}")
    return bg_rotator


def get_next_background(
    style: str = 'nature',
    count: int = 1,
) -> Union[str, List[str]]:
    """Get next background(s) using rotator to prevent repetition."""
    global bg_rotator

    # Lazy import — pick_bg is defined later in main.py (STEP 13).
    from main import pick_bg

    # Initialize if needed or style changed
    if bg_rotator is None or bg_rotator.style != style:
        init_background_rotator(style)

    try:
        return bg_rotator.get_next(count)
    except ValueError:
        # Fallback to random selection if rotator fails
        logging.warning("Rotator failed, falling back to random selection")
        return pick_bg(style, count)


# Legacy background cache helpers remain available through this service.
BG_CACHE = {}
_BG_CACHE_LOCKS = {}
_BG_CACHE_LOCKS_GUARD = threading.Lock()


def _cache_lock(path):
    """Return the shared in-process lock for one preprocessed cache path."""
    with _BG_CACHE_LOCKS_GUARD:
        return _BG_CACHE_LOCKS.setdefault(path, threading.Lock())


def init_bg_cache():
    """Scan background folders once at startup"""
    from main import BACKGROUND_VIDEO_EXTENSIONS, VISION_DIR, get_available_templates
    global BG_CACHE
    styles = sorted({config['bg_style'] for config in get_available_templates().values()})

    for style in styles:
        style_dir = os.path.join(VISION_DIR, style)
        files = []

        # Check if style folder exists
        if os.path.isdir(style_dir):
            files = [f for f in os.listdir(style_dir)
                     if f.lower().endswith(BACKGROUND_VIDEO_EXTENSIONS)]
            logging.debug(f"Found {len(files)} files in {style_dir}/")
        else:
            # Fallback: try old pattern-based naming in main vision folder
            pattern = f"{style}_part"
            space_pattern = pattern.replace('_', ' ')
            files = [f for f in os.listdir(VISION_DIR)
                     if (f.startswith(pattern) or f.startswith(space_pattern))
                     and f.lower().endswith(BACKGROUND_VIDEO_EXTENSIONS)]
            if files:
                logging.debug(f"Fallback: Found {len(files)} files with pattern '{pattern}' in main folder")

        BG_CACHE[style] = files
        BG_CACHE[f"{style}_part"] = files  # Also store by pattern for fallback

    logging.debug(f"BG cache initialized: {len(BG_CACHE)} styles")
def pick_bg(style='nature', count=1):
    """Select background video(s) from style-specific folders"""
    from main import VISION_DIR
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
    """Get or create a validated, atomically published background cache."""
    from main import BG_CACHE_DIR, FFMPEG_EXE, FFPROBE_EXE
    os.makedirs(BG_CACHE_DIR, exist_ok=True)
    base = os.path.splitext(os.path.basename(bg_path))[0]
    cached_path = os.path.join(BG_CACHE_DIR, f"{base}_{target_w}x{target_h}.mp4")

    # Multiple ayah workers can request the same background at once. Serialize
    # cache validation/builds in-process, and publish only complete MP4s so
    # render workers never open a file while FFmpeg is still writing it.
    with _cache_lock(os.path.abspath(cached_path)):
        if os.path.isfile(cached_path):
            if os.path.getsize(cached_path) > 5000:
                try:
                    result = subprocess.run([
                        FFPROBE_EXE, '-v', 'error', '-show_format',
                        '-show_streams', cached_path,
                    ], capture_output=True, text=True, timeout=10)
                    if result.returncode == 0 and "codec_type=video" in result.stdout:
                        logging.debug(
                            f"Using cached background: {os.path.basename(cached_path)}"
                        )
                        return cached_path
                    logging.warning(
                        f"Corrupted cache file (FFprobe failed): {cached_path}"
                    )
                except Exception as exc:
                    logging.warning(f"Cache validation failed: {exc}")
            else:
                logging.warning(f"Cache file too small: {cached_path}")

            try:
                os.remove(cached_path)
                logging.info(f"Removed corrupted cache file: {cached_path}")
            except FileNotFoundError:
                pass
            except OSError as exc:
                logging.warning(f"Could not remove invalid cache file: {exc}")

        # FFmpeg writes to a unique sibling file. os.replace publishes it in a
        # single filesystem operation only after FFprobe accepts the result.
        fd, temp_path = tempfile.mkstemp(
            prefix=f".{base}_{target_w}x{target_h}.",
            suffix=".tmp.mp4",
            dir=BG_CACHE_DIR,
        )
        os.close(fd)
        vf = (
            f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
            f"crop={target_w}:{target_h},fps=30,format=yuv420p"
        )
        cmd = [
            FFMPEG_EXE, "-y", "-i", bg_path,
            "-vf", vf, "-an", "-r", "30",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "32",
            "-threads", "4", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", temp_path,
        ]

        try:
            logging.info(f"Preprocessing background: {os.path.basename(bg_path)}")
            subprocess.run(
                cmd, check=True, capture_output=True, text=True, timeout=120,
            )
            if not os.path.isfile(temp_path) or os.path.getsize(temp_path) <= 5000:
                raise RuntimeError("FFmpeg produced an empty or undersized cache file")
            probe = subprocess.run(
                [FFPROBE_EXE, '-v', 'error', '-show_format', '-show_streams', temp_path],
                capture_output=True, text=True, timeout=10,
            )
            if probe.returncode != 0 or "codec_type=video" not in probe.stdout:
                raise RuntimeError(f"FFprobe rejected preprocessed video: {probe.stderr.strip()}")

            os.replace(temp_path, cached_path)
            logging.info(f"Background cached successfully: {os.path.basename(cached_path)}")
            return cached_path
        except subprocess.TimeoutExpired:
            logging.warning(
                f"Background preprocessing timeout, using original: {os.path.basename(bg_path)}"
            )
            return bg_path
        except subprocess.CalledProcessError as exc:
            logging.error(f"Background preprocessing failed: {exc.stderr}")
            return bg_path
        except Exception as exc:
            logging.error(f"Unexpected error in preprocessing: {exc}")
            return bg_path
        finally:
            try:
                os.remove(temp_path)
            except FileNotFoundError:
                pass
            except OSError as exc:
                logging.warning(f"Could not remove temporary background cache: {exc}")
