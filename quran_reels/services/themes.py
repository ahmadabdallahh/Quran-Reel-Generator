"""Discovery of folder-backed video themes."""
from __future__ import annotations

import os
import re


def get_available_templates() -> dict:
    """Return configured themes and valid video-backed folders in VISION_DIR."""
    from main import VISION_DIR
    from quran_reels.config import (
        BACKGROUND_VIDEO_EXTENSIONS,
        TEMPLATES,
    )

    available = {}
    configured_styles = {item['bg_style'].casefold() for item in TEMPLATES.values()}

    for key, config in TEMPLATES.items():
        style_dir = os.path.join(VISION_DIR, config['bg_style'])
        if not os.path.isdir(style_dir):
            continue
        if any(
            os.path.isfile(os.path.join(style_dir, name))
            and name.lower().endswith(BACKGROUND_VIDEO_EXTENSIONS)
            for name in os.listdir(style_dir)
        ):
            available[key] = config

    if not os.path.isdir(VISION_DIR):
        return available

    for name in sorted(os.listdir(VISION_DIR), key=str.casefold):
        folder = os.path.join(VISION_DIR, name)
        key = name.casefold()
        if (not os.path.isdir(folder) or key in configured_styles
                or not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', key)):
            continue
        if any(
            os.path.isfile(os.path.join(folder, file_name))
            and file_name.lower().endswith(BACKGROUND_VIDEO_EXTENSIONS)
            for file_name in os.listdir(folder)
        ):
            available[key] = {
                'bg_style': name,
                'transition': 'fade',
                'transition_style': 'cinematic',
            }
    return available
