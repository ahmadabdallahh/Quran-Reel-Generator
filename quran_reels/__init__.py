"""Quran Reels Generator — modular package.

This package is the result of refactor.md P1-1 (scoped split).  Only
the leaf modules have been extracted from ``main.py``:

  * :mod:`quran_reels.config`     — static configuration (templates,
    quality presets, reciters, verse counts, surah names, feature flags).
  * :mod:`quran_reels.services.contrast`   — background-brightness
    sampling and template-aware text colour picking.
  * :mod:`quran_reels.services.animation`  — Phase 2 per-ayah text
    animation filter expressions.
  * :mod:`quran_reels.services.background` — ``BackgroundRotator`` and
    its module-level helpers.

``main.py`` continues to be the entry point and re-exports the public
names that used to live there, so existing callers
(``import main; main.build_video(...)``) keep working unchanged.
"""

__all__ = [
    "config",
    "services",
]
