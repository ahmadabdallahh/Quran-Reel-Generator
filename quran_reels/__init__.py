"""Quran Reels Generator — modular package.

This package is the result of refactor.md P1-1 (scoped split).  Only
the leaf modules have been extracted from ``main.py``:

  * :mod:`quran_reels.config`     — static configuration (templates,
    quality presets, reciters, verse counts, surah names).
  * :mod:`quran_reels.services.background` — ``BackgroundRotator`` and
    its module-level helpers.

Arabic ayah text is rendered as an optional video overlay. Word-level
highlighting uses an estimated timing window based on each word's length.

``main.py`` continues to be the entry point and re-exports the public
names that used to live there, so existing callers
(``import main; main.build_video(...)``) keep working unchanged.
"""

__version__ = "0.5.0"

__all__ = [
    "__version__",
    "config",
    "services",
]
