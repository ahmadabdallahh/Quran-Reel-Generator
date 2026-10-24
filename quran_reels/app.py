"""Flask application factory.

Keeps ``main.py`` as the legacy startup entry point (``python main.py``)
while providing ``create_app()`` as a compatibility shim. Runtime setup,
route registration, cache initialization, and cleanup remain owned by
``main.py``; importing this module does not initialize the application.
"""

from __future__ import annotations

from flask import Flask


def create_app(exec_dir: str | None = None) -> Flask:
    """Return the configured app with handlers from ``quran_reels.routes``.

    Import ``main`` lazily to retain its global configuration and
    ``python main.py`` startup behavior.
    """
    # Lazy import — ``main`` creates the global ``app`` on import.
    import main  # noqa: F401

    return main.app
