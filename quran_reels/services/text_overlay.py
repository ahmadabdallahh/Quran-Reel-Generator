"""Ayah text renderer — leaf service module (feature 002-ayah-text-sync).

Renders the complete Uthmani text of one ayah onto a transparent,
full-frame RGBA PNG that the segment builder composites with a single
FFmpeg overlay input (overlay=0:0 — geometry is baked into the PNG).

Responsibilities (Constitution v2.0.0 Principle I):
- exact text passthrough (no truncation/reordering — ever),
- RTL shaping via Pillow/libraqm (connected letterforms + tashkeel),
- measured auto-fit inside the lower-center zone (FR-004/FR-006),
- deterministic contrast treatment ≥ TEXT_MIN_CONTRAST (SC-003),
- word bounding boxes + proportional timing windows for the optional
  word-level highlighting story (FR-011).

This module is a LEAF: stdlib + Pillow + ``quran_reels.config`` only.
It MUST NOT import ``main`` (circular-import trap — see AGENTS.md).
"""

from __future__ import annotations

import logging
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from quran_reels.config import (
    BACKING_COLOR_RGB,
    BACKING_OPACITY,
    BACKING_PADDING_PX,
    SHOW_TEXT_DEFAULT,  # noqa: F401  (re-exported convenience)
    TEXT_FONT_CANDIDATES,
    TEXT_MIN_CONTRAST,
    TEXT_SIZE_MAX_FRAC,
    TEXT_SIZE_MIN_FRAC,
    TEXT_STYLE_PROFILES,
    TEXT_ZONE_BOTTOM_MARGIN_FRAC,
    TEXT_ZONE_MAX_HEIGHT_FRAC,
    TEXT_ZONE_MAX_WIDTH_FRAC,
)

_FONT_CACHE: dict[int, ImageFont.FreeTypeFont] = {}

_LINE_LEADING = 1.28   # Scheherazade metrics already carry tashkeel headroom


# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------

def _load_font(size_px: int) -> ImageFont.FreeTypeFont:
    """First-available candidate font at ``size_px``, RAQM layout required."""
    cached = _FONT_CACHE.get(size_px)
    if cached is not None:
        return cached
    font = None
    for kind, value in TEXT_FONT_CANDIDATES:
        try:
            if kind == "file":
                if os.path.exists(value):
                    font = ImageFont.truetype(
                        value, size_px, layout_engine=ImageFont.Layout.RAQM)
            else:  # family name → resolve through fontconfig
                import subprocess
                try:
                    out = subprocess.run(
                        ["fc-match", "-f", "%{file}", value],
                        capture_output=True, text=True, timeout=5)
                    path = out.stdout.strip()
                except Exception:
                    path = ""
                if path and os.path.exists(path):
                    font = ImageFont.truetype(
                        path, size_px, layout_engine=ImageFont.Layout.RAQM)
            if font is not None:
                break
        except Exception as exc:  # noqa: BLE001 — try every candidate
            logging.debug("Font candidate failed (%s %s): %s", kind, value, exc)
    if font is None:
        raise RuntimeError(
            "No usable Arabic-capable font found — check assets/fonts/ "
            "and TEXT_FONT_CANDIDATES")
    _FONT_CACHE[size_px] = font
    return font


# ---------------------------------------------------------------------------
# Color helpers
# ---------------------------------------------------------------------------

def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    def chan(c: int) -> float:
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (chan(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast_ratio(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    la, lb = _relative_luminance(a), _relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _blend_over(rgb: tuple[int, int, int], alpha: float,
                backdrop: tuple[int, int, int]) -> tuple[int, int, int]:
    return tuple(int(round(alpha * c + (1 - alpha) * bg))
                 for c, bg in zip(rgb, backdrop))  # type: ignore[return-value]


def resolve_profile(template: str) -> dict:
    """Single source of truth for a job's text styling (FR-009)."""
    return dict(TEXT_STYLE_PROFILES.get(template, TEXT_STYLE_PROFILES["normal"]))


def _guard_contrast(accent_rgb, backing_rgb, opacity) -> tuple[tuple, tuple, float]:
    """Thicken/darken the backing until accent-on-backing clears the floor.

    Worst-case backdrop is pure white video behind the translucent box —
    if contrast holds there, it holds everywhere (deterministic, no
    background luminance probing).
    """
    eff = _blend_over(backing_rgb, opacity, (255, 255, 255))
    while (_contrast_ratio(accent_rgb, eff) < TEXT_MIN_CONTRAST
           and opacity < 0.92):
        opacity = min(0.92, opacity + 0.04)
        backing_rgb = tuple(max(0, c - 6) for c in backing_rgb)  # type: ignore[assignment]
        eff = _blend_over(backing_rgb, opacity, (255, 255, 255))
    return backing_rgb, eff, opacity


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

class _Measurer:
    """Thin wrapper measuring shaped Arabic strings with RAQM."""

    def __init__(self, font: ImageFont.FreeTypeFont):
        self.font = font
        self._img = Image.new("RGBA", (8, 8))
        self._draw = ImageDraw.Draw(self._img)

    def width(self, text: str) -> float:
        return self._draw.textlength(text, font=self.font,
                                     direction="rtl", language="ar")

    @property
    def space_width(self) -> float:
        return self.width(" ")

    def metrics(self) -> tuple[int, int]:
        return self.font.getmetrics()


def _wrap_rtl(measurer: _Measurer, words: list[str], max_width: float):
    """Greedy wrap preserving word order; returns list of lines (each a
    list of ``(word, width)`` pairs) plus each rendered line width."""
    lines: list[list[tuple[str, float]]] = []
    current: list[tuple[str, float]] = []
    current_w = 0.0
    for word in words:
        w_w = measurer.width(word)
        addition = w_w if not current else measurer.space_width + w_w
        if current and current_w + addition > max_width:
            lines.append(current)
            current, current_w = [(word, w_w)], w_w
        else:
            current.append((word, w_w))
            current_w += addition
    if current:
        lines.append(current)
    widths = [sum(w for _, w in ln) + measurer.space_width * (len(ln) - 1)
              for ln in lines]
    return lines, widths


def _fit_layout(text: str, frame_w: int, frame_h: int, padding: int):
    """Largest font whose wrapped block fits the zone (height governs;
    the line-count cap is derived from the zone, never clips — FR-006)."""
    max_block_w = frame_w * TEXT_ZONE_MAX_WIDTH_FRAC - 2 * padding
    max_block_h = frame_h * TEXT_ZONE_MAX_HEIGHT_FRAC - 2 * padding
    words = text.split()
    if not words:  # defensive — callers validate upstream
        raise ValueError("Empty ayah text")
    size_min = max(12, int(round(frame_w * TEXT_SIZE_MIN_FRAC)))
    size_max = max(size_min + 2, int(round(frame_w * TEXT_SIZE_MAX_FRAC)))
    chosen = None
    for size in range(size_max, size_min - 1, -2):
        measurer = _Measurer(_load_font(size))
        asc, desc = measurer.metrics()
        line_h = int(round((asc + desc) * _LINE_LEADING))
        lines, widths = _wrap_rtl(measurer, words, max_block_w)
        total_h = len(lines) * line_h
        if total_h <= max_block_h:
            chosen = (size, measurer, lines, widths, line_h)
            break
    if chosen is None:  # legibility floor wins over zone overflow
        measurer = _Measurer(_load_font(size_min))
        asc, desc = measurer.metrics()
        line_h = int(round((asc + desc) * _LINE_LEADING))
        lines, widths = _wrap_rtl(measurer, words, max_block_w)
        chosen = (size_min, measurer, lines, widths, line_h)
    return chosen


# ---------------------------------------------------------------------------
# Highlight sprite (word-level read-along, US3)
# ---------------------------------------------------------------------------

def get_highlight_png(out_path: str, w: int, h: int,
                      color=(255, 205, 92, 120)) -> str:
    """Soft radial-ish glow blob reused behind the active word.

    Always (re)writes ``out_path`` — callers scope the filename per
    job/ayah so parallel workers can never read each other's sprite
    mid-write (no module-global cache on purpose).
    """
    margin = max(6, min(w, h) // 6)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([margin, margin, w - margin, h - margin], fill=color)
    img = img.filter(ImageFilter.GaussianBlur(radius=margin))
    img.save(out_path)
    return out_path


def word_windows(words: list[str], duration_sec: float | None):
    """Proportional char-length timing windows, strictly forward (D9).

    Returns ``[(t0, t1), ...]`` aligned with ``words`` or ``None`` when no
    duration is available (graceful plain-display fallback, FR-011).
    """
    if not duration_sec or duration_sec <= 0:
        return None
    weights = [max(len(w), 1) for w in words]
    total = sum(weights)
    windows = []
    t0 = 0.0
    for i, weight in enumerate(weights):
        raw_end = t0 + duration_sec * weight / total
        end = duration_sec if i == len(words) - 1 else min(raw_end, duration_sec)
        if end <= t0:
            end = t0 + 0.02
        windows.append((round(t0, 2), round(end, 2)))
        t0 = end
    return windows


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render_ayah_text_png(text: str, out_path: str, template: str = "normal",
                         frame_w: int = 1080, frame_h: int = 1920,
                         duration_sec: float | None = None,
                         with_highlight: bool = False,
                         highlight_path: str | None = None) -> dict:
    """Render ``text`` (verbatim!) to a transparent full-frame PNG.

    Returns metadata::

        {"png": out_path, "width": ..., "height": ...,
         "words": [{"i": 0, "x": .., "y": .., "w": .., "h": ..}, ...],
         "windows": [(t0, t1), ...] | None}
    """
    profile = resolve_profile(template)
    accent = _hex_to_rgb(profile["accent"])
    backing_rgb = BACKING_COLOR_RGB
    opacity = float(profile.get("backing_opacity", BACKING_OPACITY))
    backing_rgb, _, opacity = _guard_contrast(accent, backing_rgb, opacity)

    scale = frame_w / 1080
    padding = max(10, int(BACKING_PADDING_PX * scale))

    size, measurer, lines, widths, line_h = _fit_layout(
        text, frame_w, frame_h, padding)
    font = measurer.font
    asc, desc = measurer.metrics()
    glyph_band = asc + desc

    block_w = max(widths)
    block_h = len(lines) * line_h
    bottom = frame_h * (1.0 - TEXT_ZONE_BOTTOM_MARGIN_FRAC)
    top = bottom - block_h
    left = (frame_w - block_w) / 2.0

    canvas = Image.new("RGBA", (frame_w, frame_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    # Backing rounded rectangle (contrast treatment).
    bx0, by0 = left - padding, top - padding
    bx1, by1 = left + block_w + padding, bottom + padding
    radius = int(padding * 0.9)
    draw.rounded_rectangle([bx0, by0, bx1, by1], radius=radius,
                           fill=backing_rgb + (int(opacity * 255),))

    # Soft shadow layer under glyphs (extra separation from busy video).
    shadow = Image.new("RGBA", (frame_w, frame_h), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)

    boxes: list[dict] = []
    y_line = top
    for line, line_w in zip(lines, widths):
        line_left = left + (block_w - line_w) / 2.0
        y_glyph = y_line + (line_h - glyph_band) // 2
        x_right = line_left + line_w  # RTL: start at the right edge
        for order, (word, w_w) in enumerate(line):
            x_word = x_right - w_w
            sdraw.text((x_word + 2 * scale, y_glyph + 3 * scale), word,
                       font=font, fill=(0, 0, 0, 140),
                       direction="rtl", language="ar")
            draw.text((x_word, y_glyph), word, font=font,
                      fill=accent + (255,), direction="rtl", language="ar")
            boxes.append({"i": len(boxes), "x": int(x_word),
                          "y": int(y_line), "w": int(w_w),
                          "h": int(line_h)})
            x_right -= (w_w + measurer.space_width)
        y_line += line_h

    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=3 * scale))
    canvas = Image.alpha_composite(shadow, canvas)
    canvas.save(out_path, "PNG")

    windows = word_windows(text.split(), duration_sec)
    meta = {"png": out_path, "width": frame_w, "height": frame_h,
            "words": boxes, "windows": windows}
    logging.debug("text_overlay: rendered '%s…' (%d words, font %dpx) → %s",
                  text[:16], len(boxes), size, out_path)
    if with_highlight:
        hb = max(b["h"] for b in boxes) if boxes else line_h
        wb = max(b["w"] for b in boxes) if boxes else int(6 * scale)
        hw, hh = int(wb * 1.25), int(hb * 0.95)
        sprite_path = highlight_path or os.path.join(
            os.path.dirname(out_path), f"highlight_{hw}x{hh}.png")
        meta["highlight"] = {
            "png": get_highlight_png(sprite_path, hw, hh),
            "w": hw, "h": hh,
        }
    return meta
