"""Arabic text shaping via HarfBuzz + glyph rasterisation via FreeType.

PIL's ``ImageDraw.text()`` does **not** apply OpenType ``GSUB`` contextual
substitution, so any Arabic font that relies on HarfBuzz composition
(Lateef, ElMessiri, Dubai, Scheherazade, Tajawal, Zain, etc.) renders as
disconnected base letters.  This module replaces the PIL text call with:

  1.  **HarfBuzz** (``uharfbuzz``) — proper Arabic script shaping: ligatures,
      tashkeel placement, kashida, mark stacking, and RTL positioning.
  2.  **FreeType** (``freetype-py``) — rasterise each shaped glyph to an
      8-bit alpha bitmap at the requested size.

The output is a :class:`ShapedLine` of :class:`ShapedGlyph` records that
the caller composites onto an RGBA ``PIL.Image`` via
:func:`render_shaped_to_canvas`.  Stroke and glow are applied on top of
the composited image (whole-text drop shadow, per-glyph ``FT_Stroker``
outline, or Gaussian halo).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional, Tuple

import freetype
import numpy as np
import uharfbuzz as hb
from PIL import Image


# Characters that are *almost* universally present in Arabic fonts but
# that some modern Naskh/Sans fonts (Tajawal, Uthman TN1, RanaKufi,
# Dubai) omit from their cmap.  Quranic Uthmani text uses alef wasla
# (U+0671) and the small Quranic annotation marks (U+06D6-06DE) at the
# start of many nouns and after aayah endings; rendering these as
# ``.notdef`` (an empty rectangle) looks broken.
#
# Two layers of defence are used together:
#
#   1.  ``select_rendering_font()`` (see below) checks the *whole* text
#       for coverage at the chosen font, and if any required codepoint
#       is missing, transparently switches to a full-coverage Quranic
#       font (Amiri-Bold by default).  This is the *primary* fix — it
#       keeps the entire line in a single font so GSUB ligatures like
#       ﷲ and ﷽ form correctly.
#
#   2.  The per-cluster fallback below is a *safety net* for the rare
#       case where the user really did pick a partial-coverage font and
#       we couldn't find any full-coverage replacement.  It re-shapes
#       only the missing codepoints with Amiri, so the rest of the line
#       keeps the user's chosen style.  Note: this *will* break
#       ligatures that span the missing char, but it is strictly better
#       than rendering a tofu box.
_FALLBACK_FONT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "fonts", "Amiri-Bold.ttf"
)

# Fonts known to ship the full Quranic Uthmani character set (alef
# wasla, the small Quranic marks U+06D6-06DE, the ﷲ / ﷽ ligatures,
# etc.).  ``select_rendering_font`` consults this list when the
# user-chosen font is missing required codepoints; the first one found
# on disk wins.
#
# Ordered so that visually-similar styles are tried first: Quranic
# Uthmani fonts come before Naskh, Naskh before Kufi.  This matters
# because when the user picks a Uthmani-style font (Almadinah,
# Uthman TN1, etc.) and we have to fall back, falling back to
# DigitalKhatt (also Uthmani) keeps the *visual style* close to the
# original choice — much less jarring than jumping all the way to
# Amiri's Naskh.
_FULL_COVERAGE_FONTS = [
    # Uthmani / Quranic madinah style (same style as Almadinah, Uthman TN1)
    "DigitalKhatt-OldMadina.otf",
    "DigitalMadina-NON V1.ttf",
    "Elgharib-KFGQPCHafs.V10.ttf",
    # Naskh classic (used by Lateef, Amiri)
    "Lateef-Bold.ttf",
    "Amiri-Bold.ttf",
    "Amiri-Regular.ttf",
]

# Set of font paths we have already warned about during this process.
# ``select_rendering_font`` pushes into this set after logging so a
# single batch that calls the renderer many times only produces one
# warning per overridden font (otherwise the log gets spammed).
_warned_fallbacks: "set[str]" = set()


# -----------------------------------------------------------------------------
# Public dataclasses
# -----------------------------------------------------------------------------


@dataclass
class ShapedGlyph:
    """A single shaped glyph ready to composite.

    Attributes:
        bitmap:      RGBA ``PIL.Image`` (alpha = glyph coverage).  May be
                     zero-sized for whitespace / ZWJ.
        bearing_x:   Pixel x-offset of the bitmap's left edge from the
                     current pen position (FreeType's ``bitmap_left``).
        bearing_y:   Pixel y-offset of the bitmap's top edge *above* the
                     baseline (FreeType's ``bitmap_top``).
        x_advance:   Pixels to advance the pen after drawing (HarfBuzz
                     ``x_advance``, in font design px).
        y_advance:   Vertical pen advance (always 0 for horizontal text).
        cluster:     Index of the source Unicode codepoint this glyph
                     originated from.
        glyph_id:    HarfBuzz-assigned glyph index.  ``0`` means the font
                     has no glyph for this cluster (``.notdef`` / tofu);
                     the renderer uses this to trigger per-cluster font
                     fallback.
        codepoint:   The original Unicode codepoint of the source
                     character (before any GSUB substitutions).  This
                     lets the renderer look the character up in a
                     fallback font when ``glyph_id == 0``.
    """

    bitmap: Image.Image
    bearing_x: int
    bearing_y: int
    x_advance: float
    y_advance: float
    cluster: int
    glyph_id: int = 0
    codepoint: int = 0


@dataclass
class ShapedLine:
    """A complete shaped line ready to render.

    Attributes:
        glyphs:    Ordered list of shaped glyphs (left-to-right in pen
                   order; for RTL text, the *first* glyph in the list is
                   the rightmost on screen).
        width:     Total horizontal advance of the line in pixels.
        ascent:    Distance from the baseline to the top of the line
                   (font ascender scaled to px).
        descent:   Distance from the baseline to the bottom of the line
                   (font descender magnitude, positive number).
    """

    glyphs: List[ShapedGlyph]
    width: float
    ascent: float
    descent: float


# -----------------------------------------------------------------------------
# Shaping
# -----------------------------------------------------------------------------


def _read_font_data(font_path: str) -> bytes:
    with open(font_path, "rb") as f:
        return f.read()


def _cluster_to_codepoint(text: str, cluster: int) -> int:
    """Map a HarfBuzz ``cluster`` value (a char index into ``text``)
    back to the source Unicode codepoint.

    HarfBuzz's ``cluster`` field for a ``Buffer`` built via
    ``buf.add_str(text)`` is the index of the source *character* in
    the Python string (Python's str is char-indexed, not byte-indexed,
    so this works for any Unicode text).  Falls back to ``0`` if the
    cluster is out of range — the caller treats ``0`` as unknown.
    """
    if 0 <= cluster < len(text):
        return ord(text[cluster])
    return 0


def _shape_to_glyphs(
    text: str,
    font_path: str,
    font_size_px: float,
    direction: str = "rtl",
    script: Optional[str] = "arab",
    language: Optional[str] = "ar",
) -> Tuple[List[ShapedGlyph], freetype.Face, hb.Font]:
    """Run HarfBuzz over ``text`` and rasterise each shaped glyph.

    Returns the glyph list, the loaded FreeType face, and the HarfBuzz
    font (the latter two are kept for callers that need ascender/
    descender metrics).
    """
    if not text:
        return [], _make_face(font_path, font_size_px), None  # type: ignore[return-value]

    font_data = _read_font_data(font_path)
    hb_face = hb.Face(font_data)
    hb_font = hb.Font(hb_face)
    # uharfbuzz >= 0.40 returns positions as floats already scaled by
    # ``font.scale`` (in design px, not 26.6 fixed point).
    hb_font.scale = (int(round(font_size_px)), int(round(font_size_px)))

    buf = hb.Buffer()
    buf.add_str(text)
    buf.direction = direction
    if script:
        buf.script = script
    if language:
        buf.language = language
    # Keep cluster level 0 (default) so cluster indices are char indices.
    buf.guess_segment_properties()
    hb.shape(hb_font, buf)

    ft_face = _make_face(font_path, font_size_px)

    glyphs: List[ShapedGlyph] = []
    load_flags = freetype.FT_LOAD_RENDER | freetype.FT_LOAD_TARGET_NORMAL
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        glyph_id = int(info.codepoint)
        ft_face.load_glyph(glyph_id, load_flags)
        g = ft_face.glyph
        bitmap = _ft_bitmap_to_pil(g.bitmap)
        glyphs.append(
            ShapedGlyph(
                bitmap=bitmap,
                bearing_x=int(g.bitmap_left),
                bearing_y=int(g.bitmap_top),
                x_advance=float(pos.x_advance),
                y_advance=float(pos.y_advance),
                cluster=int(info.cluster),
                glyph_id=glyph_id,
                codepoint=_cluster_to_codepoint(text, int(info.cluster)),
            )
        )

    # HarfBuzz returns glyphs in **logical** order (matching the source
    # string's character order), not visual order.  For RTL text this
    # means the *first* glyph in the list is the LEFTMOST on screen
    # and the *last* is the RIGHTMOST — the exact opposite of what a
    # left-to-right renderer expects.  Reverse the list when the buffer
    # direction is RTL so downstream code can iterate the glyphs in
    # visual order (rightmost first, leftmost last).
    if direction == "rtl":
        glyphs = list(reversed(glyphs))

    return glyphs, ft_face, hb_font


def _make_face(font_path: str, font_size_px: float) -> freetype.Face:
    """Create a FreeType face and set its char size in 26.6 fixed point."""
    face = freetype.Face(font_path)
    face.set_char_size(int(round(font_size_px * 64)))
    return face


def _apply_codepoint_fallbacks(text: str, font_path: str) -> str:
    """Legacy simple-substitution path.  No longer used — kept for
    reference.  Replaced by per-cluster font fallback which preserves
    Quranic ligatures (e.g. ﷲ) that get broken by this pre-substitution.
    """
    return text


def _fallback_missing_glyphs(
    text, glyphs, ft_face, primary_font_path, font_size_px,
    direction, script, language,
):
    """Replace any .notdef glyphs (glyph_id 0) in ``glyphs`` with the
    equivalent glyphs shaped by ``_FALLBACK_FONT_PATH``.

    This walks the primary font's shaped output cluster-by-cluster,
    identifies clusters whose leading glyph came back as .notdef, and
    re-shapes just the source character(s) of those clusters with the
    fallback font.  The fallback glyph inherits the *primary* font's
    x_advance (so the line still flows at the primary font's metric)
    but uses the fallback's bitmap and bearing for the missing char.

    Trade-off: when a ligature spans the missing char, we lose the
    ligature (e.g. "ٱللَّه" becomes "ٱ" + "ل" + "ل" + "َّ" + "ه" with
    "ٱ" rendered in the fallback font).  This is still strictly better
    than rendering a tofu box.
    """
    if not os.path.isfile(_FALLBACK_FONT_PATH):
        return glyphs
    if _FALLBACK_FONT_PATH == primary_font_path:
        return glyphs  # No point falling back to the same font

    # Find clusters whose primary glyph is .notdef.  We trigger on
    # ``glyph_id == 0`` (the HarfBuzz glyph index), not on the bitmap
    # being empty: some fonts (Tajawal, Uthman TN1) ship a *visible*
    # .notdef glyph (a hollow rectangle) with a non-empty bitmap but
    # glyph_id 0.
    missing_clusters: set = set()
    for g in glyphs:
        if g.glyph_id == 0 and g.codepoint > 0:
            missing_clusters.add(g.cluster)

    if not missing_clusters:
        return glyphs

    # For each missing cluster, extract the source char and shape it
    # with the fallback font, at the same font size.  We re-shape
    # *only* the missing character, not the surrounding text, so we
    # don't disturb the primary font's ligatures.
    fallback_glyphs: dict = {}  # cluster -> ShapedGlyph from fallback
    for cluster in missing_clusters:
        if cluster >= len(text):
            continue
        sub = text[cluster]
        if not sub:
            continue
        sub_glyphs, _, _ = _shape_to_glyphs(
            sub, _FALLBACK_FONT_PATH, font_size_px, direction, script, language
        )
        if sub_glyphs:
            fallback_glyphs[cluster] = sub_glyphs[0]

    if not fallback_glyphs:
        return glyphs

    # Splice in the fallback glyphs.  We rebuild the glyphs list with
    # the fallback glyphs replacing the .notdef entries.  The
    # x_advance of the missing primary glyph is kept (so the line
    # width doesn't change); the fallback glyph is positioned within
    # that advance.  The fallback bitmap's bearing is preserved.
    new_glyphs = []
    for g in glyphs:
        if g.cluster in fallback_glyphs:
            fg = fallback_glyphs[g.cluster]
            new_glyphs.append(
                ShapedGlyph(
                    bitmap=fg.bitmap,
                    bearing_x=fg.bearing_x,
                    bearing_y=fg.bearing_y,
                    x_advance=g.x_advance,  # keep primary's advance
                    y_advance=g.y_advance,
                    cluster=g.cluster,
                    glyph_id=fg.glyph_id or 1,  # not 0
                    codepoint=g.codepoint,
                )
            )
        else:
            new_glyphs.append(g)
    return new_glyphs


# -----------------------------------------------------------------------------
# Font coverage check + safe-font selection
# -----------------------------------------------------------------------------


def check_font_coverage(font_path: str, text: str) -> Tuple[int, int, List[int], str]:
    """Return the codepoint coverage of ``font_path`` against ``text``.

    Counts every *distinct* Unicode codepoint that appears in ``text``
    and reports how many of them the font can render (i.e. the font's
    cmap has a non-zero glyph index for that codepoint).  Ligatures
    and presentation forms are *not* re-resolved — we only check the
    literal source codepoints, which is what users expect when they
    see "the font can't render this character".

    Args:
        font_path: Absolute path to a TTF/OTF file.
        text:      The text the user wants to render.

    Returns:
        A 4-tuple ``(covered, total, missing_codepoints, missing_chars_repr)``:

        * ``covered``  — number of distinct codepoints the font has.
        * ``total``    — total distinct codepoints in the text.
        * ``missing_codepoints`` — sorted list of codepoints the font
          is missing (only those present in the input text).
        * ``missing_chars_repr`` — a short, human-readable string like
          ``"U+0671 (ٱ) U+06DD (۝)"`` suitable for log lines.  Empty
          when coverage is 100%.

    Example::

        >>> check_font_coverage("fonts/Tajawal-Bold.ttf", "ٱلله")
        (3, 4, [0x0671], 'U+0671 (\u0671)')

    Note: This walks the text character by character and is O(n) in the
    text length.  The cost is a FreeType ``Face`` open + ``get_char_index``
    lookup per unique codepoint; for typical Quranic text (a few hundred
    characters) this completes in well under a millisecond.
    """
    if not text:
        return 0, 0, [], ""

    # Build the set of distinct codepoints the text actually uses.
    # Skip whitespace and control characters (newlines from word-wrap,
    # ZWSP, bidi marks, etc.) — these are structural, not renderable,
    # and no font's cmap contains U+000A.  Including them would make
    # every word-wrapped line look "incomplete" to the coverage check
    # and trigger spurious fallbacks.
    def _is_renderable(cp: int) -> bool:
        # C0 controls (U+0000..U+001F), space (U+0020), DEL (U+007F),
        # and the C1 range (U+0080..U+009F) are all non-renderable.
        if cp < 0x20 or cp == 0x7F or (0x80 <= cp <= 0x9F):
            return False
        # BiDi / formatting marks that the renderer ignores anyway.
        if cp in (0x200B, 0x200C, 0x200D, 0x200E, 0x200F,
                  0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
                  0x2066, 0x2067, 0x2068, 0x2069, 0xFEFF):
            return False
        return True

    distinct = sorted({ord(c) for c in text if _is_renderable(ord(c))})
    if not distinct:
        return 0, 0, [], ""

    # FreeType raises on corrupted fonts.  Treat that as "no coverage
    # at all" so the caller falls back to a known-good font instead of
    # crashing the entire render pipeline.
    try:
        face = freetype.Face(font_path)
    except Exception:
        return 0, len(distinct), distinct, "font_unreadable"

    missing: List[int] = []
    for cp in distinct:
        try:
            if face.get_char_index(cp) == 0:
                missing.append(cp)
        except Exception:
            # Per-codepoint errors are non-fatal; treat as missing.
            missing.append(cp)

    covered = len(distinct) - len(missing)
    if missing:
        repr_parts = []
        for cp in missing[:8]:  # cap log noise at 8 chars
            try:
                ch = chr(cp)
            except ValueError:
                ch = "?"
            repr_parts.append(f"U+{cp:04X} ({ch})")
        if len(missing) > 8:
            repr_parts.append(f"...+{len(missing) - 8} more")
        missing_repr = " ".join(repr_parts)
    else:
        missing_repr = ""

    return covered, len(distinct), missing, missing_repr


def select_rendering_font(
    preferred_path: Optional[str],
    text: str,
    fallbacks: Optional[List[str]] = None,
) -> Tuple[str, bool, float, str]:
    """Pick the best font path to render ``text`` with.

    Strategy:

      1. If ``preferred_path`` is missing or doesn't exist, fall back to
         the first available full-coverage font on disk.
      2. Otherwise check the preferred font's coverage against ``text``.
         If 100%, use it.
      3. Otherwise try each font in ``fallbacks`` (default: the
         ``_FULL_COVERAGE_FONTS`` list) and use the first one with 100%
         coverage.  The warning is logged **once per overridden font**
         per process (``_warned_fallbacks`` set), so a batch render
         doesn't spam the log.
      4. If no font has full coverage, return the preferred font and
         let the per-cluster fallback catch the missing characters.

    The return value is a 4-tuple ``(chosen_path, was_fallback, coverage_pct, missing_repr)``:

    * ``chosen_path``  — absolute path to the font to use.
    * ``was_fallback`` — ``True`` if ``chosen_path != preferred_path``.
    * ``coverage_pct`` — coverage of ``chosen_path`` against ``text``
      (0.0–1.0).
    * ``missing_repr`` — human-readable missing-char string for the
      chosen font (empty when coverage is 100%).

    Note: the caller's preferred font is **never silently dropped**;
    if no full-coverage replacement can be found, we render with the
    preferred font and accept any per-cluster fallback artefacts.  This
    means a niche font with no available backup still works, just not
    perfectly.
    """
    preferred = preferred_path or ""
    full_cov_list = list(fallbacks) if fallbacks else list(_FULL_COVERAGE_FONTS)

    # Case 1: no preferred font — find any full-coverage font on disk.
    if not preferred or not os.path.isfile(preferred):
        for cand in full_cov_list:
            # If fallbacks were given as basenames, resolve them next
            # to the preferred font's directory; otherwise treat them
            # as absolute paths.
            cand_path = cand
            if preferred and not os.path.isabs(cand):
                cand_path = os.path.join(os.path.dirname(preferred), cand)
            if not os.path.isfile(cand_path) and os.path.isfile(cand):
                cand_path = cand
            if os.path.isfile(cand_path):
                covered, total, missing, missing_repr = check_font_coverage(cand_path, text)
                if total > 0 and covered == total:
                    _maybe_warn(preferred, cand_path, covered, total, missing_repr)
                    return cand_path, True, 1.0, ""
        # Last-ditch: try the fallback font next to this module even
        # if the caller didn't pass a preferred path.
        if os.path.isfile(_FALLBACK_FONT_PATH):
            covered, total, _, _ = check_font_coverage(_FALLBACK_FONT_PATH, text)
            if total > 0 and covered == total:
                return _FALLBACK_FONT_PATH, True, 1.0, ""
        # Nothing full-coverage available; return preferred as-is.
        if preferred and os.path.isfile(preferred):
            covered, total, missing, missing_repr = check_font_coverage(preferred, text)
            return preferred, False, (covered / total) if total else 1.0, missing_repr
        return _FALLBACK_FONT_PATH, True, 0.0, ""

    # Case 2: preferred font exists; check its coverage.
    covered, total, missing, missing_repr = check_font_coverage(preferred, text)
    if total == 0 or covered == total:
        return preferred, False, 1.0, ""

    # Case 3: preferred is partial-coverage — try the fallback list.
    for cand in full_cov_list:
        cand_path = cand
        if not os.path.isabs(cand):
            cand_path = os.path.join(os.path.dirname(preferred), cand)
        if not os.path.isfile(cand_path) and os.path.isfile(cand):
            cand_path = cand
        if not os.path.isfile(cand_path):
            continue
        if os.path.abspath(cand_path) == os.path.abspath(preferred):
            continue  # don't "fall back" to the same font
        c_covered, c_total, c_missing, c_repr = check_font_coverage(cand_path, text)
        if c_total > 0 and c_covered == c_total:
            _maybe_warn(preferred, cand_path, covered, total, missing_repr)
            return cand_path, True, 1.0, ""

    # Case 4: no replacement found.  Use the preferred font and accept
    # the partial coverage (per-cluster fallback will patch the holes).
    return preferred, False, (covered / total) if total else 1.0, missing_repr


def _maybe_warn(
    preferred: str,
    chosen: str,
    covered: int,
    total: int,
    missing_repr: str,
) -> None:
    """Log a single warning when a font override happens.

    Uses the module-level ``_warned_fallbacks`` set to de-duplicate:
    once we've warned that ``preferred -> chosen`` is happening, we
    don't warn again for the same pair.  This is what stops a 200-clip
    batch from filling the log with 200 identical warnings.
    """
    key = f"{preferred}->{chosen}"
    if key in _warned_fallbacks:
        return
    _warned_fallbacks.add(key)
    try:
        import logging
        logging.warning(
            "Font override: %s lacks coverage for %d/%d codepoints "
            "(missing %s); falling back to %s for consistent Quranic "
            "ligatures (e.g. \ufdf2).",
            os.path.basename(preferred) if preferred else "<none>",
            total - covered, total, missing_repr,
            os.path.basename(chosen),
        )
    except Exception:
        # Logging shouldn't break rendering.
        pass


def reset_font_warnings() -> None:
    """Clear the warned-fallbacks set.  Useful in tests."""
    _warned_fallbacks.clear()


def _ft_bitmap_to_pil(ft_bitmap) -> Image.Image:
    """Convert a FreeType bitmap (grayscale or mono) to a PIL RGBA image.

    White-on-transparent: R/G/B are forced to white so the caller can
    colourise by ``Image.ImageEval`` or by overlying a flat colour layer
    (see ``render_shaped_to_canvas``).  Alpha = glyph coverage.
    """
    w, h = int(ft_bitmap.width), int(ft_bitmap.rows)
    if w == 0 or h == 0:
        return Image.new("RGBA", (0, 0), (0, 0, 0, 0))

    if ft_bitmap.pixel_mode == freetype.FT_PIXEL_MODE_MONO:
        # 1-bit packed bitmap.  FreeType already pads each row to a byte
        # boundary (``pitch``); we lift each bit to a full byte.
        buf = bytes(ft_bitmap.buffer)
        rows = []
        bytes_per_row = (w + 7) // 8
        for y in range(h):
            row_bytes = buf[y * ft_bitmap.pitch : y * ft_bitmap.pitch + bytes_per_row]
            bits = np.unpackbits(np.frombuffer(row_bytes, dtype=np.uint8))[:w]
            rows.append(bits * 255)
        arr = np.stack(rows).astype(np.uint8)
    else:
        # 8-bit grayscale (FT_PIXEL_MODE_GRAY).
        arr = np.frombuffer(bytes(ft_bitmap.buffer), dtype=np.uint8)
        arr = arr.reshape(h, w)

    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    rgba[..., 0] = 255
    rgba[..., 1] = 255
    rgba[..., 2] = 255
    rgba[..., 3] = arr
    return Image.fromarray(rgba, "RGBA")


# -----------------------------------------------------------------------------
# Public shaping API
# -----------------------------------------------------------------------------


def shape_text(
    text: str,
    font_path: str,
    font_size_px: float,
    direction: str = "rtl",
    script: Optional[str] = "arab",
    language: Optional[str] = "ar",
) -> ShapedLine:
    """Shape ``text`` with HarfBuzz and rasterise with FreeType.

    Returns a :class:`ShapedLine` containing every glyph's bitmap and
    positioning info.  The caller is expected to pass the line to
    :func:`render_shaped_to_canvas` to composite it.

    Args:
        text:         Logical-order text (no reshape, no bidi).  HarfBuzz
                      handles both internally based on the script tags.
        font_path:    Absolute path to a TTF/OTF font.
        font_size_px: Target font size in pixels (post-supersample, if
                      the caller is rendering at 2x/4x and will downscale
                      later).
        direction:    ``'rtl'`` (default for Arabic), ``'ltr'``, or
                      ``'ttb'`` (top-to-bottom).
        script:       OpenType script tag.  ``'arab'`` by default; pass
                      ``None`` to skip and let HarfBuzz guess.
        language:     BCP-47 language tag.  ``'ar'`` by default.

    Returns:
        A :class:`ShapedLine`.
    """
    glyphs, ft_face, _ = _shape_to_glyphs(
        text, font_path, font_size_px, direction, script, language
    )

    # Per-cluster fallback: if any glyph came back as glyph_id 0
    # (``.notdef`` / tofu), re-shape the corresponding source
    # character(s) with a fallback font that has the codepoint.  This
    # fixes fonts like Tajawal, Uthman TN1, RanaKufi, and Dubai that
    # drop U+0671 and other Quranic diacritics from their cmap.  See
    # BUG 2.
    #
    # We trigger on ``glyph_id == 0`` rather than ``bitmap.size ==
    # (0, 0)`` because some fonts (Tajawal, Uthman TN1) ship a
    # *visible* .notdef glyph — a hollow rectangle — and the bitmap is
    # non-empty even though the character is missing.  HarfBuzz still
    # reports ``glyph_id == 0`` for these.
    if _FALLBACK_FONT_PATH and any(
        g.glyph_id == 0 and g.codepoint > 0 for g in glyphs
    ):
        glyphs = _fallback_missing_glyphs(
            text, glyphs, ft_face, font_path, font_size_px,
            direction, script, language,
        )
    if not glyphs:
        return ShapedLine(glyphs=[], width=0.0, ascent=0.0, descent=0.0)

    upem = ft_face.units_per_EM
    ascent = ft_face.ascender * (font_size_px / upem)
    descent = -ft_face.descender * (font_size_px / upem)
    width = sum(g.x_advance for g in glyphs)
    return ShapedLine(
        glyphs=glyphs,
        width=width,
        ascent=ascent,
        descent=descent,
    )


def measure_text(text: str, font_path: str, font_size_px: float) -> Tuple[float, float]:
    """Cheap width/height measurement without rasterising glyphs.

    Useful for word-wrap decisions.  We call FreeType ``load_glyph`` with
    ``FT_LOAD_NO_HINTING | FT_LOAD_NO_BITMAP`` (no rasterisation) to read
    the horizontal advance per codepoint and sum them.  HarfBuzz is still
    used for shaping so the measurement reflects ligatures.
    """
    if not text:
        return 0.0, 0.0

    font_data = _read_font_data(font_path)
    hb_face = hb.Face(font_data)
    hb_font = hb.Font(hb_face)
    hb_font.scale = (int(round(font_size_px)), int(round(font_size_px)))

    buf = hb.Buffer()
    buf.add_str(text)
    buf.direction = "rtl"
    buf.script = "arab"
    buf.language = "ar"
    buf.guess_segment_properties()
    hb.shape(hb_font, buf)

    width = sum(float(p.x_advance) for p in buf.glyph_positions)

    ft_face = _make_face(font_path, font_size_px)
    upem = ft_face.units_per_EM
    ascent = ft_face.ascender * (font_size_px / upem)
    descent = -ft_face.descender * (font_size_px / upem)
    return width, ascent + descent


# -----------------------------------------------------------------------------
# Compositing
# -----------------------------------------------------------------------------


def render_shaped_to_canvas(
    shaped: ShapedLine,
    canvas: Image.Image,
    pen_xy: Tuple[float, float],
    fill_rgb: Tuple[int, int, int, int] = (255, 255, 255, 255),
    baseline_y: Optional[float] = None,
) -> float:
    """Composite a shaped line onto an RGBA canvas.

    For RTL text the line is drawn right-to-left starting at
    ``pen_xy[0]``; ``pen_xy[1]`` is the *baseline* y-coordinate.  Glyph
    bitmaps are pasted at ``(pen_x + bearing_x, baseline_y - bearing_y)``
    and tinted by compositing a flat-colour layer over their white
    pixels.

    Args:
        shaped:       The :class:`ShapedLine` to draw.
        canvas:       Target RGBA ``PIL.Image`` (modified in place).
        pen_xy:       ``(x, baseline_y)`` for the line's rightmost edge.
        fill_rgb:     RGBA colour applied to the glyph pixels.
        baseline_y:   Override for the baseline; defaults to ``pen_xy[1]``.

    Returns:
        The new pen x after the last glyph (useful for chaining lines).
    """
    if not shaped.glyphs:
        return pen_xy[0]

    pen_x = float(pen_xy[0])
    base_y = float(baseline_y if baseline_y is not None else pen_xy[1])
    fr, fg_, fb, fa = fill_rgb

    # Build a single colour swatch the size of the canvas, then mask it
    # with the alpha channel of every glyph.  This is faster than
    # iterating per-pixel and lets us reuse one mask.
    # For a typical line (a few hundred px wide, ~120 px tall), this is
    # cheaper than per-glyph blend math.
    for g in shaped.glyphs:
        if g.bitmap.size == (0, 0):
            pen_x -= g.x_advance  # RTL: pen moves left
            continue
        paste_x = int(round(pen_x + g.bearing_x))
        paste_y = int(round(base_y - g.bearing_y))
        # Tint: white pixels become (fr, fg, fb); alpha preserved.
        arr = np.array(g.bitmap)
        if (fr, fg_, fb) != (255, 255, 255):
            arr[..., 0] = fr
            arr[..., 1] = fg_
            arr[..., 2] = fb
        # Respect the requested alpha
        if fa < 255:
            arr[..., 3] = (arr[..., 3].astype(np.uint16) * fa // 255).astype(np.uint8)
        tinted = Image.fromarray(arr, "RGBA")
        canvas.alpha_composite(tinted, (paste_x, paste_y))
        pen_x -= g.x_advance  # RTL: pen moves left
    return pen_x
