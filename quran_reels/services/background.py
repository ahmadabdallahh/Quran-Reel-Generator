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
import os
import random
from typing import List, Optional, Union


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
            files = [f for f in os.listdir(style_dir) if f.endswith('.mp4')]
            return [os.path.join(style_dir, f) for f in files]
        else:
            # Fallback to pattern-based in main vision folder
            pattern = f"{self.style}_part"
            files = [f for f in os.listdir(VISION_DIR)
                     if f.startswith(pattern) and f.endswith('.mp4')]
            return [os.path.join(VISION_DIR, f) for f in files]

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
