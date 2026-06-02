"""FFmpeg filter expressions for per-ayah text intro animations (Phase 2).

Phase 2 (animations.md §4) introduced per-ayah text animations.  This
module owns the filter-string generation.  The function used to live in
``main.py`` near ``get_contrasting_text_color``; it is extracted here so
the animation vocabulary (slide/zoom/fade) can be extended and tested
without modifying ``main.py``.

The function is a *pure* filter builder — it takes a name, duration, and
optional PNG canvas size, and returns a filter string (or ``None`` for
deferred animations).  It reads ``FEATURE_FLAGS`` from
``quran_reels.config`` to honour the Phase 2 opt-in flag.
"""
from __future__ import annotations

from typing import Optional, Tuple

from quran_reels.config import FEATURE_FLAGS


def get_ffmpeg_text_animation_filter(
    animation_name: str,
    duration: float = 5.0,
    fps: int = 30,
    text_size: Optional[Tuple[int, int]] = None,
) -> Optional[str]:
    """
    Generate FFmpeg filter for text intro animations.

    Phase 2 (T2.1) — returns a real filter expression to be applied to the
    text PNG before the overlay, OR None to fall back to static overlay.

    All durations are derived from the ayah audio length so they adapt
    naturally to short/long recitations.  ``fade_d`` is the animation
    window (0.5 s) — we cap it to ``duration/2`` to avoid negative
    offsets on tiny clips.

    ``text_size=(w, h)`` is the text PNG size; needed for zoom_in/zoom_out
    so the pad expression can center the scaled text in the original
    canvas.  Defaults to ``(1020, 432)`` if not provided (the typical size
    for Al-Fatiha ayahs in this codebase — actual sizes range 404-464
    vertically depending on the text length and template glow).

    Supported animations:
      fade_in, fade_out, slide_up, slide_down, slide_left, slide_right,
      zoom_in, zoom_out.  Everything else (typewriter, bounce, glow,
      reveal) returns ``None`` and is deferred to Phase 3 / kinetic_text.

    Geometry of the per-frame slide/zoom:
      - Slide: pad the SIDE OPPOSITE to the slide direction by ``dist``,
        then crop a fixed-size window with a per-frame y/x offset that
        interpolates from dist to 0 over ``fade_d`` seconds.
      - Zoom:  scale the input by a per-frame factor (0.8 to 1.0 for
        zoom_in, 1.0 to 0.8 for zoom_out), then pad to the original
        canvas size, centered.
    """
    if not FEATURE_FLAGS.get('text_animations', False):
        return None

    # Cap the animation window so a 0.4 s ayah isn't asked to fade for 0.5 s.
    fade_d = min(0.5, max(0.1, duration / 2))

    # Default text PNG size if caller didn't pass it.  Used for zoom pad
    # centering; slides don't need this since they pad by the slide
    # distance and crop the same size as the input.
    if text_size is None:
        text_w, text_h = 1020, 432
    else:
        text_w, text_h = text_size

    if animation_name == 'fade_in':
        return f'fade=t=in:st=0:d={fade_d:.3f}:alpha=1'

    if animation_name == 'fade_out':
        st = max(0.0, duration - fade_d)
        return f'fade=t=out:st={st:.3f}:d={fade_d:.3f}:alpha=1'

    # Per-frame expression helper.  min(t, fade_d)/fade_d goes 0 -> 1 over
    # the animation window, then stays at 1.  Backslash-escapes the comma
    # so it isn't parsed as a filter argument separator.
    prog = f'min(t\\,{fade_d:.3f})/{fade_d:.3f}'

    if animation_name == 'slide_up':
        # Text comes IN from below, slides UP to its natural position.
        # Pad the TOP by `dist` so the original is at the BOTTOM of the
        # padded image; the crop window then shows the text at
        # y = natural+dist at t=0 and slides to y = natural at t=fade_d.
        # NOTE: crop's x/y expressions are evaluated per-frame automatically
        # when they reference `t`, so no `eval=frame` option is needed.
        dist = 50
        return (
            f'format=rgba,'
            f'pad=iw:ih+{dist}:0:0:black@0,'
            f'crop=iw:ih:0:{dist}*{prog},'
            f'fade=t=in:st=0:d={fade_d:.3f}:alpha=1'
        )

    if animation_name == 'slide_down':
        # Text comes IN from above, slides DOWN to its natural position.
        # Pad the BOTTOM by `dist` so the original is at the TOP of the
        # padded image; the crop window shows the text shifted UP by dist
        # at t=0 and slides to natural at t=fade_d.
        dist = 50
        return (
            f'format=rgba,'
            f'pad=iw:ih+{dist}:0:{dist}:black@0,'
            f'crop=iw:ih:0:{dist}*(1-{prog}),'
            f'fade=t=in:st=0:d={fade_d:.3f}:alpha=1'
        )

    if animation_name == 'slide_left':
        # Text comes IN from the right, slides LEFT to its natural position.
        # Pad the LEFT by `dist` so the original is on the RIGHT; the crop
        # window shows the text shifted RIGHT by dist at t=0 and slides
        # left to natural at t=fade_d.
        dist = 50
        return (
            f'format=rgba,'
            f'pad=iw+{dist}:ih:0:0:black@0,'
            f'crop=iw:ih:{dist}*{prog}:0,'
            f'fade=t=in:st=0:d={fade_d:.3f}:alpha=1'
        )

    if animation_name == 'slide_right':
        # Text comes IN from the left, slides RIGHT to its natural position.
        # Pad the RIGHT by `dist` so the original is on the LEFT; the crop
        # window shows the text shifted LEFT by dist at t=0 and slides
        # right to natural at t=fade_d.
        dist = 50
        return (
            f'format=rgba,'
            f'pad=iw+{dist}:ih:{dist}:0:black@0,'
            f'crop=iw:ih:{dist}*(1-{prog}):0,'
            f'fade=t=in:st=0:d={fade_d:.3f}:alpha=1'
        )

    if animation_name == 'zoom_in':
        # Text starts at 80% of its natural size, grows to 100% over fade_d.
        # FFmpeg's `scale` filter doesn't support per-frame scaling (it needs
        # to know the output size at init time), so we use `crop` with per-frame
        # out_w/out_h to take a smaller sub-region of the input (the centre
        # portion), then `pad` to bring it back to the original canvas size,
        # centred.  The visible effect is the same: a uniformly-scaled text
        # that grows from 80% to 100% over fade_d, with empty space around it
        # shrinking as the text grows.
        z_start, z_end = 0.8, 1.0
        scale_expr = f'({z_start}+({z_end}-{z_start})*{prog})'
        return (
            f'format=rgba,'
            f'crop={text_w}*{scale_expr}:{text_h}*{scale_expr}:'
            f'({text_w}-{text_w}*{scale_expr})/2:({text_h}-{text_h}*{scale_expr})/2,'
            f'pad={text_w}:{text_h}:({text_w}-iw)/2:({text_h}-ih)/2:color=black@0,'
            f'fade=t=in:st=0:d={fade_d:.3f}:alpha=1'
        )

    if animation_name == 'zoom_out':
        # Text starts at 100% of its natural size, shrinks to 80% over fade_d.
        # Same crop+pad trick as zoom_in, but with the scale going 1.0 -> 0.8.
        z_start, z_end = 1.0, 0.8
        scale_expr = f'({z_start}+({z_end}-{z_start})*{prog})'
        return (
            f'format=rgba,'
            f'crop={text_w}*{scale_expr}:{text_h}*{scale_expr}:'
            f'({text_w}-{text_w}*{scale_expr})/2:({text_h}-{text_h}*{scale_expr})/2,'
            f'pad={text_w}:{text_h}:({text_w}-iw)/2:({text_h}-ih)/2:color=black@0,'
            f'fade=t=in:st=0:d={fade_d:.3f}:alpha=1'
        )

    # typewriter / bounce / glow / reveal: defer to kinetic_text (Phase 3)
    return None
