"""Flask application factory.

Keeps ``main.py`` as the legacy entry point (``python main.py``) while
providing ``create_app()`` for tools / tests / future ASGI embedding.
The factory intentionally does NOT run ``init_bg_cache`` or ``cleanup``
— those remain the responsibility of the ``__main__`` block in
``main.py`` so importing this module is side-effect free.
"""

from __future__ import annotations

import os
from flask import Flask
from flask_cors import CORS


def create_app(exec_dir: str | None = None) -> Flask:
    """Build and return a Flask app with all routes registered.

    Importing routes must happen AFTER the app is created so
    ``main.app`` already exists (routes use ``@app.route``).
    To avoid that coupling here, this factory imports ``main``
    lazily and returns ``main.app`` which already has the routes.
    For a future fully-decoupled factory the routes would live in
    ``quran_reels.routes`` — this shim keeps the refactor reversible.
    """
    # Lazy import — ``main`` creates the global ``app`` on import.
    import main  # noqa: F401

    # Ensure CORS is applied (main does it at import time, but be defensive)
    try:
        CORS(main.app)
    except Exception:
        pass
    return main.app
