"""Background brightness sampling and template-aware text colour picking.

The functions here used to live in ``main.py`` STEP 13.5.  They are
extracted so the contrast logic can be tested and reasoned about in
isolation, and so future "smart colour" work (e.g. caching brightness
results, region sampling) can be added without touching ``main.py``.

Lazy imports from ``main`` keep the new module decoupled at module-load
time and avoid the circular import that would otherwise occur between
``main`` and ``quran_reels.services.contrast``.
"""
from __future__ import annotations

import subprocess
from typing import Tuple


def analyze_background_brightness(bg_path: str, sample_seconds: int = 1) -> float:
    """
    Analyze background video brightness to determine optimal text color.

    Returns:
        Brightness value 0.0 (dark) to 1.0 (bright).
    """
    # Lazy import — FFMPEG_EXE/logging are defined in main.py and bringing
    # them in at module top would create a circular import.
    from main import FFMPEG_EXE, logging

    try:
        # Use FFmpeg to extract a frame and calculate average brightness
        cmd = [
            FFMPEG_EXE, '-i', bg_path,
            '-ss', str(sample_seconds),
            '-vframes', '1',
            '-vf', 'format=gray,scale=1:1',
            '-f', 'rawvideo', '-pix_fmt', 'gray',
            'pipe:1',
        ]

        result = subprocess.run(cmd, capture_output=True, timeout=10)
        if result.returncode == 0 and result.stdout:
            # Get the pixel value (0-255)
            pixel_value = result.stdout[0] if result.stdout else 128
            brightness = pixel_value / 255.0
            return brightness
    except Exception as e:
        logging.warning(f"Could not analyze background brightness: {e}")

    # Default to medium brightness if analysis fails
    return 0.5


def get_contrasting_text_color(
    bg_path: str,
    template_color: str = 'white',
    auto_detect: bool = True,
) -> Tuple[str, str]:
    """
    Determine optimal text color based on background brightness.

    The template_color is treated as a *hint* — it is kept whenever it has
    enough contrast against the background.  When the background's
    brightness disagrees with the template (e.g. the ramadan template's
    gold on a bright frame, or a white template on a dark frame), the
    result is overridden to a default that maximises readability.

    Args:
        bg_path: Path to background video.
        template_color: Default color from template (name or hex).
        auto_detect: If True, analyze background; if False, use template color.

    Returns:
        Tuple ``(text_color, stroke_color)`` of PIL color strings.
    """
    if not auto_detect:
        # Use template color with dark stroke
        if template_color.lower() == 'gold':
            return ('#FFD700', 'black')
        elif template_color.lower() == 'white':
            return ('white', 'black')
        else:
            return (template_color, 'black')

    # Normalize template_color to a lowercase hex string so we can compute
    # luminance and so the return values match the historical
    # ``#ffffff``-style spelling callers expect.
    name_map = {'gold': '#ffd700', 'white': '#ffffff', 'bright': '#00ffff'}
    t_lower = (template_color or 'white').lower()
    template_hex = name_map.get(t_lower)
    if template_hex is None:
        candidate = template_color if template_color else '#ffffff'
        template_hex = candidate.lower() if candidate.startswith('#') else '#ffffff'

    def _hex_luminance(hex_str):
        if not (hex_str and len(hex_str) == 7 and hex_str[0] == '#'):
            return 128.0
        try:
            r = int(hex_str[1:3], 16)
            g = int(hex_str[3:5], 16)
            b = int(hex_str[5:7], 16)
        except ValueError:
            return 128.0
        return 0.299 * r + 0.587 * g + 0.114 * b

    template_lum = _hex_luminance(template_hex)

    # Analyze background brightness
    brightness = analyze_background_brightness(bg_path)

    # Choose colors based on brightness, preserving the template hint when
    # it already has enough contrast.
    if brightness > 0.6:
        # Bright background — prefer dark text.  Keep the template only if
        # it is itself dark; otherwise fall back to a dark default.
        if template_lum < 128:
            return (template_hex, 'white')
        return ('#1a1a1a', '#ffffff')
    elif brightness < 0.4:
        # Dark background — prefer light text.  Keep the template only if
        # it is itself light; otherwise fall back to a white default.
        if template_lum > 128:
            return (template_hex, '#000000')
        return ('#ffffff', '#000000')
    else:
        # Medium brightness — the template hint dominates.  Gold stays
        # gold, white stays white, anything else is best-effort.
        if t_lower == 'gold':
            return ('#ffd700', '#000000')
        return ('#ffffff', '#000000')
