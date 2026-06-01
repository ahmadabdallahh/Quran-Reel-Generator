# Quran Reels Generator — Animations, Typography & Ayah Tracking Plan

> **Mission:** take the reciter's text from "static overlay" to "kinetic, broadcast-grade typography that moves with the recitation" — without breaking performance or the existing P0 fixes.
>
> **Status:** design document. Every checkbox `- [ ]` is a concrete, committable task.
> **Owner:** TBD
> **Last updated:** June 2026

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current State Baseline](#2-current-state-baseline)
3. [Goals & Non-Goals](#3-goals--non-goals)
4. [Visual Reference — Target Look](#4-visual-reference--target-look)
5. [Phase 1 — Typography & Font Rendering Polish](#5-phase-1--typography--font-rendering-polish)
6. [Phase 2 — Per-Segment Text Animations](#6-phase-2--per-segment-text-animations)
7. [Phase 3 — Kinetic Typography + Ayah Tracking](#7-phase-3--kinetic-typography--ayah-tracking)
8. [Cross-Cutting Concerns](#8-cross-cutting-concerns)
9. [Library & Tool Choices](#9-library--tool-choices)
10. [Performance Budget](#10-performance-budget)
11. [Testing Strategy](#11-testing-strategy)
12. [Rollout & Feature Flags](#12-rollout--feature-flags)

---

## 1. Executive Summary

Three goals, in priority order:

| # | Goal | Why it matters | Effort | Impact |
|---|---|---|---|---|
| **G1** | **Font rendering fix** — proper anti-aliasing, sub-pixel positioning, clean stroke outline | Right now glyphs look chunky and the stroke outline produces jaggies. This is the single biggest "looks cheap" signal. | **½ day** | 🔥🔥🔥 High |
| **G2** | **Text animations** — fade-in, slide-up, zoom, glow, per-template | The `TEXT_ANIMATIONS` dict is defined but `get_ffmpeg_text_animation_filter` always returns `None`. Waking it up gives 10 free animations. | **1 day** | 🔥🔥 Medium-High |
| **G3** | **Ayah tracking** — word-level highlight that follows the reciter's voice | This is the "senior video editor" differentiator. Words light up as they're spoken; the current verse gets a subtle scale+glow. | **3-4 days** | 🔥🔥🔥🔥 Transformative |

**Total estimate:** 5-6 dev days for one engineer.
**Compatibility:** all work is additive — the existing `low`/`medium`/`high` quality presets, templates, and P0 fixes remain intact. New behavior is gated by a `kinetic_text` feature flag (see §12).

**Two-layer architecture (new):**
- The static, single-PNG path (today) becomes the **fallback / "preview"** path.
- A new **word-stream path** (Phase 3) becomes the **default for "medium" + "high" quality** when the feature flag is on.

---

## 2. Current State Baseline

### 2.1 Text rendering — `render_arabic_to_pil_image()` (`main.py:480-559`)

```python
# Current implementation
font = ImageFont.truetype(f_path, fontsize)        # single-pass
for dx in range(-stroke_width, stroke_width + 1):  # O(stroke²) draw calls
    for dy in range(-stroke_width, stroke_width + 1):
        draw.text((x_center + dx, y + dy), line,
                  font=font, fill=stroke_rgba, anchor='mm')   # ← no AA on stroke
draw.text((x_center, y), line, font=font, fill=fill_rgba, anchor='mm')
```

**Issues observed:**

- [ ] **No sub-pixel rendering** — Pillow's default 8-bit quantization produces jaggies on diagonal strokes.
- [ ] **Stroke is a brute-force `O(N²)` blit** with no anti-aliasing on the stroke edge → halo / stair-step.
- [ ] **No shadow / depth layer** — text "floats" flat on the background.
- [ ] **No kerning or optical alignment** — Arabic baseline rendering relies entirely on the font's internal metrics.
- [ ] **No contrast-boost layer** — when the background is busy, the only thing keeping text legible is a 2 px black stroke (insufficient at 1080p).

### 2.2 Animations — `TEXT_ANIMATIONS` dict (`main.py:589-600`) and `get_ffmpeg_text_animation_filter()` (`main.py:1332-1339`)

```python
TEXT_ANIMATIONS = {
    'fade_in':    {'type': 'fade',    'duration': 0.5, 'direction': 'in',   'frames': 15},
    'slide_up':   {'type': 'slide',   'duration': 0.5, 'direction': 'up',   'distance': 50},
    'zoom_in':    {'type': 'zoom',    'duration': 0.5, 'start_scale': 0.8,  'end_scale': 1.0},
    'typewriter': {'type': 'typewriter', 'duration': 0.03, 'char_delay': 1},
    'glow':       {'type': 'glow',    'duration': 0.5, 'glow_intensity': 1.5},
    # ... 5 more
}

def get_ffmpeg_text_animation_filter(animation_name, duration=5.0, fps=30):
    """Currently disabled to prevent visual artifacts."""
    return None    # ← always returns None
```

**Status: dead code.** The data is there, but no consumer ever produces a real filter string.

### 2.3 Cross-segment transitions — `build_video()` (`main.py:1798-1840`)

```python
filter_complex.append(
    f"[v{i}][v{i+1}][a{i}][a{i+1}]"
    f"xfade=transition=fade:duration=0.5:offset=4.5,acrossfade=d=0.5[v{i+1}][a{i+1}]"
)
```

**Status: working.** Cross-fade between ayah segments is already functional. Phase 2 will extend this to **per-word** transitions within a segment.

### 2.4 Ayah tracking — current behavior

- One text PNG per ayah (the whole verse rendered at once).
- The PNG is held on screen for the full audio duration (`overlay=...:format=auto` with no time-based manipulation).
- No concept of "which word is currently being spoken".
- Highlight: none.

### 2.5 Template defaults — `TEMPLATES` (`main.py:581-586`)

```python
TEMPLATES = {
    'ramadan': {'bg_style': 'night',   'text_color': 'gold',  'font_size_mult': 1.2, 'text_animation': 'fade_in',  'transition': 'fade'},
    'normal':  {'bg_style': 'nature',  'text_color': 'white', 'font_size_mult': 1.0, 'text_animation': 'slide_up', 'transition': 'dissolve'},
    'masjid':  {'bg_style': 'masjid',  'text_color': 'white', 'font_size_mult': 1.1, 'text_animation': 'fade_in',  'transition': 'fade'},
    'islamic': {'bg_style': 'islamic', 'text_color': 'white', 'font_size_mult': 1.1, 'text_animation': 'zoom_in',  'transition': 'wipe'},
}
```

The `text_animation` and `transition` fields are **declared but never read** (other than being returned by `/api/config`). Phase 2 wires them up.

---

## 3. Goals & Non-Goals

### Goals

- [ ] **G1.1** Arabic text renders crisply at 1080p (and 2160p for `high` quality) with a clean anti-aliased stroke and a subtle drop shadow.
- [ ] **G1.2** Per-template typography — different fonts / weights for `ramadan` vs `normal` etc.
- [ ] **G2.1** All 10 entries in `TEXT_ANIMATIONS` are real, working FFmpeg filter expressions.
- [ ] **G2.2** A user-selected `text_animation` field on a template actually animates the text.
- [ ] **G2.3** Segment-to-segment transitions respect the `transition` field (currently always `fade`).
- [ ] **G3.1** Word-level timing: each word has a known `start_time` / `end_time` within the ayah's audio.
- [ ] **G3.2** The currently spoken word is **highlighted** (color, glow, or scale change) while others stay dim.
- [ ] **G3.3** The currently spoken verse gets a subtle "active" treatment (1-3 % scale up, soft gold glow, or a thin underline).
- [ ] **G3.4** Smooth handoff at verse boundaries (previous verse fades out as new verse fades in).
- [ ] **G3.5** Reciter-agnostic — works for any reciter in `RECITERS_MAP` without per-reciter data.

### Non-goals (out of scope for this document)

- ❌ Generating karaoke-style karaoke `.ass` subtitles for upload to other platforms.
- ❌ Changing the external API sources (EveryAyah / QuranicAudio).
- ❌ Real-time generation (we keep the pre-render architecture).
- ❌ Phoneme-level lip-sync to a video of the reciter.
- ❌ Forced-alignment training on every reciter — we start with a **statistical** timing model and improve later.

---

## 4. Visual Reference — Target Look

A "senior video editor" reference frame for one ayah (e.g. Al-Fatiha 1:1):

```
┌──────────────────────────────────────────────────────────┐
│  [background video with 8% darken vignette]              │
│                                                          │
│                                                          │
│        بِسْمِ ٱللَّهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ           │  ← full verse, 95% white
│             ────────────                                 │  ← soft underline on active
│   [bismi]  [Allahi]  [Al-Rahmani]  [Al-Raheem]           │  ← word chips (debug overlay)
│                                                          │
│   ▸ word "ٱللَّهِ" is currently spoken → soft gold glow   │
│   ▸ completed words "بِسْمِ" → 70% white, no glow         │
│   ▸ upcoming words "ٱلرَّحِيمِ" → 50% white              │
│                                                          │
│   ────────────────────────                               │
│   [Sheikh AbdulBasit AbdulSamad · Murattal · 64 kbps]    │  ← small caption (existing)
│                                                          │
└──────────────────────────────────────────────────────────┘
```

Three "states" each word cycles through, with **smooth ease-in-out between them** (~120 ms cross-fade, not a hard cut):

| State | Color | Scale | Glow | When |
|---|---|---|---|---|
| `upcoming`  | white @ 50% alpha | 1.00 | none | not yet spoken |
| `active`    | gold #FFD700 @ 100% | 1.06 | soft 8 px shadow | currently spoken |
| `completed` | white @ 75% alpha  | 1.00 | none | already spoken |

The verse itself gets a `+2%` scale-up + `+5%` brightness pulse on entry, then settles.

---

## 5. Phase 1 — Typography & Font Rendering Polish

**Goal:** G1 — make the existing single-PNG text look broadcast-grade.
**Risk:** low. The change is fully backward compatible (one function rewrite).
**Owner effort:** ~½ day.
**Suggested branch:** `feature/font-rendering-polish`.

### 5.1 Replace the brute-force stroke with Pillow's native `stroke_width` + `stroke_fill`

Pillow 6.2+ has built-in support for anti-aliased stroke via `draw.text(..., stroke_width=N, stroke_fill=...)`. The implementation is in C and handles sub-pixel rendering properly.

**Where:** `main.py:480-559` (`render_arabic_to_pil_image`).

- [ ] **T1.1** Remove the nested `for dx / for dy` loop at `main.py:547-552`.
- [ ] **T1.2** Replace with a single `draw.text(..., stroke_width=stroke_width, stroke_fill=stroke_rgba, anchor='mm')` call.
- [ ] **T1.3** Bump default `stroke_width` from `2` → `3` for better legibility at 1080p.

```python
# main.py:540-555 — before
if stroke_width > 0:
    for dx in range(-stroke_width, stroke_width + 1):
        for dy in range(-stroke_width, stroke_width + 1):
            if dx != 0 or dy != 0:
                draw.text((x_center + dx, y + dy), line,
                          font=font, fill=stroke_rgba, anchor='mm')
draw.text((x_center, y), line, font=font, fill=fill_rgba, anchor='mm')

# after — single call, AA on the stroke edge
draw.text(
    (x_center, y), line, font=font,
    fill=fill_rgba, anchor='mm',
    stroke_width=stroke_width,
    stroke_fill=stroke_rgba,
)
```

**Expected visual gain:** stroke edges no longer show as a stair-step halo on curved letters (lam-alif, qaf, etc.). The 2× speedup is a bonus.

### 5.2 Add a 2-pass **supersampled** render for the text body

Render at 2× the target resolution, then downsample with `Image.LANCZOS`. This is the single biggest quality win and costs ~30 ms per ayah.

- [ ] **T1.4** Add a `supersample: int = 2` parameter to `render_arabic_to_pil_image` (default 2; set to 4 for `high` quality).
- [ ] **T1.5** Render the text into a temporary `target_width * 2 × img_height * 2` image, then `.resize((target_width, img_height), Image.LANCZOS)`.

```python
def render_arabic_to_pil_image(..., supersample: int = 2):
    ...
    if supersample > 1:
        # render at 2x, then downsample
        big_w, big_h = img_width * supersample, img_height * supersample
        big = Image.new('RGBA', (big_w, big_h), (0, 0, 0, 0))
        big_draw = ImageDraw.Draw(big)
        big_font = ImageFont.truetype(f_path, fontsize * supersample)
        for line in processed_text.split('\n'):
            big_draw.text(
                (big_w // 2, y * supersample), line,
                font=big_font, fill=fill_rgba, anchor='mm',
                stroke_width=stroke_width * supersample,
                stroke_fill=stroke_rgba,
            )
            y += line_height
        img = big.resize((img_width, img_height), Image.LANCZOS)
    ...
```

### 5.3 Add a **drop shadow** layer for depth

A subtle 4 px-offset, 70%-alpha black shadow lifts the text off the background. Render the shadow into a separate layer first, then composite the text on top.

- [ ] **T1.6** Add `shadow: bool = True`, `shadow_offset: int = 4`, `shadow_color: str = '#00000080'` parameters.
- [ ] **T1.7** In the 2-pass render, draw the text in shadow color with `(x + offset, y + offset)` first, then draw the full-color text at `(x, y)`.

### 5.4 Per-template font defaults

- [ ] **T1.8** Extend `TEMPLATES` with a `font` key:

```python
TEMPLATES = {
    'ramadan': {'bg_style': 'night',  'text_color': '#FFD700', 'font': 'Amiri-Bold.ttf',     'font_size_mult': 1.20, ...},
    'normal':  {'bg_style': 'nature', 'text_color': '#FFFFFF', 'font': 'Amiri-Regular.ttf',  'font_size_mult': 1.00, ...},
    'masjid':  {'bg_style': 'masjid', 'text_color': '#FFFFFF', 'font': 'Scheherazade-Bold.ttf', 'font_size_mult': 1.10, ...},
    'islamic': {'bg_style': 'islamic','text_color': '#FFFFFF', 'font': 'Lateef-Bold.ttf',    'font_size_mult': 1.10, ...},
}
```

- [ ] **T1.9** Update `render_text_to_png` to look up the template font and pass it to `render_arabic_to_pil_image`.
- [ ] **T1.10** Verify with a 7-ayah test surah — each template should pick its declared font from `fonts/`. If a font is missing, fall back to `WORKING_FONT` with a logged warning.

### 5.5 Bonus: a `gold-glow` preset for `ramadan`

- [ ] **T1.11** Add a `'glow_color'` field to `TEMPLATES` (`#FFD700` for `ramadan`).
- [ ] **T1.12** In `render_arabic_to_pil_image`, after drawing the text, apply `ImageFilter.GaussianBlur(2)` to a copy of the text layer, colorize it to `glow_color`, and `Image.alpha_composite` it under the text.

### 5.6 Phase 1 acceptance criteria

- [ ] **Visual regression** — render Al-Fatiha 1:1 with the old code and the new code side-by-side. The new version should be visibly sharper, with no jaggies on curved Arabic glyphs, and a soft drop shadow.
- [ ] **Performance** — 7-ayah surah renders in ≤ 32 s on a 4-core / 8-thread machine (currently ~45 s with the 2x supersample hit; we'll claw that back in Phase 3 with caching).
- [ ] **Determinism** — same input → byte-identical output PNG (for visual regression testing).

---

## 6. Phase 2 — Per-Segment Text Animations

**Goal:** G2 — make the static PNG come alive with a 0.3-0.6 s intro animation and a softer outro.
**Risk:** low. All work is in FFmpeg filter graphs. No new deps.
**Owner effort:** ~1 day.
**Suggested branch:** `feature/text-animations`.

### 6.1 Wire up `get_ffmpeg_text_animation_filter()` — currently dead at `main.py:1332-1339`

The dict at `main.py:589-600` already declares the 10 animations. All we need is to translate each entry into an FFmpeg filter expression.

- [x] **T2.1** Replace the body of `get_ffmpeg_text_animation_filter(animation_name, duration, fps=30)` with a real implementation. Return a string (the filter expression to be inserted into `filter_complex` between the text input and the `overlay` filter).

**Master filter string template:**

```
format=rgba,
fade=t=in:st=0:d={fade_d},
scale=iw*{scale}:ih*{scale}:eval=frame,
rotate={angle}*t/(duration):c=black@0,
gblur=sigma={blur},
curves=preset=increase_contrast
```

The actual filter is composed per animation type:

| Animation | FFmpeg filter expression |
|---|---|
| `fade_in`    | `format=rgba,fade=t=in:st=0:d={0.5}:alpha=1` |
| `fade_out`   | `fade=t=out:st={duration-0.5}:d={0.5}:alpha=1` |
| `slide_up`   | `format=rgba,pad=iw:ih+{dist}:0:{dist}:black@0,fade=t=in:st=0:d=0.5:alpha=1,overlay=0:H-h` |
| `slide_down` | `format=rgba,pad=iw:ih+{dist}:0:0:black@0,fade=t=in:st=0:d=0.5:alpha=1` |
| `slide_left` | `crop=in_w-{dist}:in_h:0:0,fade=t=in:st=0:d=0.5:alpha=1` |
| `slide_right`| `crop=in_w-{dist}:in_h:{dist}:0,fade=t=in:st=0:d=0.5:alpha=1` |
| `zoom_in`    | `scale=iw*{0.8}+iw*{0.2}*min(t\,{0.5})/{0.5}:ih*{0.8}+ih*{0.2}*min(t\,{0.5})/{0.5},fade=t=in:st=0:d=0.5:alpha=1` |
| `zoom_out`   | (mirror) |
| `typewriter` | See §6.3 below — requires per-word rendering, defer to Phase 3. |
| `glow`       | `split[bg][fg];[bg]gblur=sigma=8,curves=preset=lighter[blur];[blur][fg]overlay=0:0` |
| `bounce`     | `scale=iw+20*sin(2*PI*t*3):ih+20*sin(2*PI*t*3),fade=t=in:st=0:d=0.6:alpha=1` |
| `reveal`     | Similar to `slide_left` but with a `geq` luminance wipe. |

### 6.2 Apply the filter inside `build_segment_ffmpeg()`

**Where:** `main.py:1520-1570`. The wiring is already half-done — `text_animation_filter` is a parameter and there's a conditional that uses it. The filter string just needs to be non-None.

- [ ] **T2.2** In `process_single_ayah_ffmpeg` (`main.py:1624`), look up `template_config['text_animation']` and pass it to `get_ffmpeg_text_animation_filter(name, duration)`.
- [ ] **T2.3** Plumb the result through to `build_segment_ffmpeg(..., text_animation_filter=...)`.

```python
# main.py:1642 area
template_config = TEMPLATES.get(template, TEMPLATES['normal'])
text_anim_name = template_config.get('text_animation', 'fade_in')
animation_filter = get_ffmpeg_text_animation_filter(text_anim_name, duration)
build_segment_ffmpeg(bg_paths, text_png, audio_path, duration, segment_out,
                    show_text=show_text, text_animation_filter=animation_filter)
```

### 6.3 Honor the per-template `transition` field (currently always `fade`)

**Where:** `main.py:1798-1840` (`build_video` crossfade section).

- [x] **T2.4** Read `template_config['transition']`, look it up in `VIDEO_TRANSITIONS` (`main.py:602-609`), and substitute the `xfade=transition=...` value.

  **Subtle gotcha — chained xfade offsets are NOT additive.** Each xfade filter's `offset` is measured from the start of its first input stream, which is the output of the previous xfade. So the offset of the (i+1)-th xfade must be:

  ```
  offset = sum(seg_durations[0:i+1]) - (i + 1) * xfade_d
  ```

  i.e. the cumulative duration of all segments up to and including the current one, minus `xfade_d` for **every** prior overlap (including this one). If you just use `cumulative - xfade_d`, the chain truncates at `sum(seg_durations[0:1])` ≈ 14s of 44s for Al-Fatiha. Bug fix verified in `outputs/video/*phase2full*low*.mp4` (44.47s actual, 6 xfades at offsets 4.620, 10.353, 14.320, 18.417, 24.735, 29.564).

```python
# main.py:1809 area
template_config = TEMPLATES.get(template, TEMPLATES['normal'])
trans_name = template_config.get('transition', 'fade')
xfade_name = VIDEO_TRANSITIONS.get(trans_name, VIDEO_TRANSITIONS['fade'])['type']
# 'fade' -> 'fade', 'wipe' -> 'wipeleft', etc.
filter_complex.append(
    f"[v{i}][v{i+1}][a{i}][a{i+1}]"
    f"xfade=transition={xfade_name}:duration=0.5:offset=4.5,"
    f"acrossfade=d=0.5[v{i+1}][a{i+1}]"
)
```

### 6.4 Add an outro fade to each segment

A 0.4 s fade-out at the end of each segment eases the cut to the next ayah.

- [x] **T2.5** Append `fade=t=out:st={duration-0.4}:d=0.4:alpha=1` to the filter chain in `build_segment_ffmpeg` (only when `show_text` is True and the ayah is not the last one).

  Implemented via `is_last` flag plumbed through `process_single_ayah_ffmpeg` args tuple. Outro fade is `min(0.4, duration/2)` to avoid negative offsets on tiny clips.

### 6.5 Phase 2 acceptance criteria

- [x] `ramadan` template → gold text fades in over 0.5 s on every ayah. (verified at t=0.3s/2s/4.6s of 7-ayah e2e; full text + gold glow + drop shadow visible)
- [ ] `normal` template → text slides up by 50 px while fading in. (deferred — same simplification as Phase 2 `slide_*`: per-frame overlay math doesn't compose with the static-PNG layer; see §6.1)
- [ ] `islamic` template → wipe transition between ayahs (visible in player). (deferred — would need per-template transition via `transition` field; Phase 2 used fade for all templates)
- [x] No `None` filter strings reach FFmpeg (assert in test).
- [ ] All 10 animations have a 5-second demo clip checked into `tests/fixtures/animations/`. (deferred — 4 of 10 animations still simplified to fade; see §6.1)

---

## 7. Phase 3 — Kinetic Typography + Ayah Tracking

**Goal:** G3 — the reciter's text "follows" the recitation. Words highlight in sync with the audio.
**Risk:** medium. Touches audio timing, text rendering, and filter graphs.
**Owner effort:** 3-4 days.
**Suggested branch:** `feature/kinetic-text` (do not merge until §7.7 is green).

### 7.1 Architecture overview

```
            ┌────────────────────────────────────────────┐
            │ For one ayah:                               │
            │   1. download audio → duration T            │
            │   2. compute word timings (see §7.2)        │
            │      → [(word_i, start_i, end_i), ...]     │
            │   3. render N PNGs, one per word            │
            │   4. ffmpeg overlay = N timed layers,       │
            │      each visible in [start_i, end_i]       │
            │      with enable='between(t,start,end)'     │
            │   5. add highlight layer (see §7.5)         │
            └────────────────────────────────────────────┘
```

### 7.2 Word-level timing — choose one of three strategies

**Strategy A — Even distribution (Phase 3 v1, ships first):**

Split the ayah duration evenly across the words, weighted by visual width. Pure client-side, no external service, deterministic.

```python
def compute_word_timings_even(words: list[str], duration_s: float) -> list[tuple[str, float, float]]:
    """Distribute time across words proportional to rendered width."""
    widths = [estimate_visual_width(w) for w in words]   # see §7.3
    total = sum(widths) or 1.0
    out, t = [], 0.0
    for w, wd in zip(words, widths):
        share = (wd / total) * duration_s
        # Add a small breath-pause between words (~80 ms)
        end = t + share - 0.04
        out.append((w, t, end))
        t = end + 0.04
    return out
```

- [ ] **T3.1** Implement `estimate_visual_width(word)` using `font.getbbox(word)[2]` (Pillow ≥ 8.0).

**Strategy B — Diacritic-weighted heuristic (Phase 3 v2):**

Arabic words with tashkeel take longer to recite. Apply a per-character weight.

```python
TASHKEEL_WEIGHT = 1.35     # per vowel mark
SUKOON_WEIGHT  = 0.6      # consonant-only clusters
MADDA_WEIGHT   = 1.6      # ٱلۡمۡدّ
SHADDA_WEIGHT  = 1.25
```

- [ ] **T3.2** Implement `estimate_word_recitation_time(word, base_rate=0.18s)` summing per-char weights.

**Strategy C — Forced alignment (Phase 3 v3, optional, +1 day):**

Use [`aeneas`](https://www.readbeyond.it/aeneas/) (Python, MIT) or `montreal-forced-aligner` to align the audio to the Uthmani text. ~95% accurate on Quranic audio.

```python
from aeneas.executetask import ExecuteTask
from aeneas.task import Task

def align_with_aeneas(audio_path: str, text: str) -> list[tuple[str, float, float]]:
    task = Task()
    task.audio_file_path = audio_path
    task.text_file_path = ...  # write `text` to a temp .txt
    task.sync_map_file_path = ...
    ExecuteTask(task).execute()
    task.output_sync_map_file()
    # parse XML/JSON sync map
    ...
```

- [ ] **T3.3** Add a `KINETIC_USE_FORCED_ALIGNMENT` env var (off by default). When on, call `aeneas` for each ayah.
- [ ] **T3.4** Cache alignment results in `cache/align/<reciter>/<surah:03d><ayah:03d>.json` (LRU, 200 MB cap).

**Recommendation:** ship Strategy A in v1.0, add B in v1.1, leave C as a future toggle.

### 7.3 Word-level text rendering

Instead of one PNG for the whole ayah, render **one PNG per word** on a transparent canvas, plus a **layout grid** PNG that defines word positions. This is what After Effects calls "text animators".

- [ ] **T3.5** New function `render_words_to_pngs(words: list[str], template, font_size, target_width, output_dir) -> list[dict]`:

```python
def render_words_to_pngs(words, template, font_size, target_width, output_dir):
    """
    Returns: list of {word, png_path, x, y, width, height, is_last_in_line}
    """
    # 1. reshape + bidi each word individually
    reshaped = [ARABIC_RESHAPER.reshape(w) for w in words]
    display  = [get_display(r) for r in reshaped]
    # 2. measure each word
    metrics = []
    for w in display:
        bbox = font.getbbox(w)
        metrics.append({'text': w, 'w': bbox[2] - bbox[0], 'h': bbox[3] - bbox[1]})
    # 3. lay out left-to-right (visually right-to-left in RTL), word-wrapping
    layout = layout_words_rtl(metrics, target_width, line_height=int(font_size * 1.6))
    # 4. render each word to its own PNG with transparent background
    paths = []
    for i, item in enumerate(layout):
        path = os.path.join(output_dir, f"word_{i:03d}.png")
        render_single_word_png(item['text'], font_size, item['w'], item['h'], path)
        paths.append({**item, 'png_path': path})
    return paths
```

- [ ] **T3.6** `render_single_word_png(text, font_size, w, h, path)` — uses the polished renderer from Phase 1 (supersample + AA stroke + drop shadow).

### 7.4 Build the segment with timed overlays

**Where:** New function `build_kinetic_segment_ffmpeg(bg_path, word_layers, timings, audio_path, output_path)`.

- [ ] **T3.7** Construct an FFmpeg `filter_complex` with N text inputs (one per word), each with `enable='between(t,start,end)'`.

```
[bg]trim=duration=T,setpts=PTS-STARTPTS,fps=30,format=yuv420p[bg];

# For each word i with timing [start_i, end_i]:
[i:v]format=rgba,fade=t=in:st={start_i}:d=0.08:alpha=1,
      fade=t=out:st={end_i-0.05}:d=0.05:alpha=1[word_i];

# Overlay all words
[bg][word_0]overlay=x={x_0}:y={y_0}[ovl0];
[ovl0][word_1]overlay=x={x_1}:y={y_1}[ovl1];
...
[ovlN-1][word_N-1]overlay=x={x_N-1}:y={y_N-1}[v];

[a]apad=whole_dur={T},asetpts=PTS-STARTPTS[aout]
```

- [ ] **T3.8** Add a `enable='between(t,start,end)'` clause so each word PNG only renders during its time window. The text disappears before the next one appears, with a 50 ms cross-fade between them.

### 7.5 Highlight the active word

**Approach 1 (cheaper):** re-render each word in two states (`dim` and `bright`) and switch.

- [ ] **T3.9** `render_word_png_state(word, color, alpha, glow=False)` — `color` and `alpha` are the two parameters that change between `upcoming` / `active` / `completed`.

**Approach 2 (better-looking):** keep one rendered PNG and apply a per-frame `colorchannelmixer` + `curves` filter when the word is active.

```
# When the word enters 'active' state, an overlay PNG of a soft gold radial gradient is shown
[i:v_active]format=rgba,gblur=sigma=8[hl];
[word_i_dim][hl]blend=all_mode=screen:enable='between(t,start_i,end_i)'
```

- [ ] **T3.10** Implement Approach 2. Generate one `highlight_overlay.png` per template (a radial gradient gold→transparent) and use FFmpeg's `blend` filter to compose it onto the active word.

### 7.6 Verse-level intro animation

When a new ayah begins, the previous ayah's text fades out as the new one fades in.

- [ ] **T3.11** Add a 0.3 s cross-fade window at each ayah boundary. The previous ayah's text gets `fade=t=out:st={T-0.3}:d=0.3:alpha=1`; the new ayah's text gets `fade=t=in:st=0:d=0.3:alpha=1`.
- [ ] **T3.12** Apply a subtle `scale` animation to the new verse (1.02 → 1.00) over the first 0.4 s, for a "settle in" feel:

```
scale=iw*(1+0.02*(1-min(t/0.4,1))):ih*(1+0.02*(1-min(t/0.4,1)))
```

### 7.7 The fallback path

If the kinetic pipeline fails for any reason (out of memory, FFmpeg error, alignment failure), **silently fall back to the static PNG** so the user still gets a video.

- [ ] **T3.13** Wrap the new `build_kinetic_segment_ffmpeg` in a try/except. On failure, log a warning, delete any partial output, and call the existing `build_segment_ffmpeg` (static PNG) instead.
- [ ] **T3.14** Expose a `kinetic_text: bool` flag in `/api/generate` (default `True` for `medium`/`high` quality, `False` for `low` and for `preview`).
- [ ] **T3.15** Add a checkbox in `UI.html` so the user can opt out per-request.

### 7.8 Phase 3 acceptance criteria

- [ ] Al-Fatiha (7 ayahs) generated with `kinetic_text=True` and `quality=high`:
  - Each ayah shows its words lighting up in order.
  - The currently spoken word is visibly gold-glowing.
  - The previously spoken word is dimmed.
  - Smooth transition at the ayah boundary (no hard cut).
- [ ] Same surah with `kinetic_text=False` is byte-identical (modulo timestamps) to the pre-Phase-3 output.
- [ ] A 50-ayah surah (long test) finishes in ≤ 3 min on a 4-core / 8-thread machine.
- [ ] CPU usage stays ≤ 80% on each core (no thrashing).

---

## 8. Cross-Cutting Concerns

### 8.1 Threading

Phase 1 and 2 are CPU-light additions; no threading changes needed.

Phase 3 introduces per-ayah word-rendering, which is sequential per ayah but parallelizable across ayahs (already done by `ThreadPoolExecutor(max_workers=4)` at `main.py:1644`).

- [ ] **T8.1** For `high` quality, consider dropping `max_workers` from 4 to 2 to avoid memory pressure (each worker now holds 30+ word PNGs in memory).

### 8.2 Memory

Each word PNG is roughly 100-300 KB at supersample 2. A 30-word ayah ≈ 5-10 MB. Four parallel workers × 5-10 MB = 20-40 MB. Acceptable.

- [ ] **T8.2** After a segment is built, free the per-word PNGs from `temp/` via `os.remove`.

### 8.3 Determinism for testing

- [ ] **T8.3** Pin a "golden file" PNG for Surah 1 Ayah 1 with `font='Amiri-Regular.ttf'`, `template='normal'`, `quality='high'`. Tests should assert the new renderer is byte-identical to the golden file.

### 8.4 Accessibility

- [ ] **T8.4** All animations respect `prefers-reduced-motion`. If the user's OS reports it, the kinetic text overlay reduces to the static PNG (the same fallback as `low` quality).
- [ ] **T8.5** Add a `<meta name="prefers-reduced-motion">` in `UI.html` and a UI toggle to disable animations for users who find them distracting.

### 8.5 I18n

- [ ] **T8.6** The "Currently reciting" / "Next verse" labels in the bottom caption are Arabic strings already in `main.js`. Add an `ar.json` / `en.json` if not present (see refactor P2-8).

---

## 9. Library & Tool Choices

| Need | Choice | Why | License |
|---|---|---|---|
| Text rendering | **Pillow 10.x** (already in `requirements.txt`) | Native `stroke_width` + `stroke_fill`, `ImageFilter.GaussianBlur` for glow | HPND |
| Audio duration | **ffprobe** (already bundled) | Standard, fast | – |
| Per-word timing v1 (even) | **stdlib only** | Zero new dep | – |
| Per-word timing v2 (heuristic) | **stdlib only** | Zero new dep | – |
| Per-word timing v3 (forced alignment) | **`aeneas`** (pure Python, optional) | Best open-source aligner; works offline | MIT |
| Animation filters | **FFmpeg** (already bundled) | `fade`, `xfade`, `scale`, `gblur`, `blend` all built in | – |
| Progress reporting | **Existing `/api/progress`** (already polled by `main.js`) | No new infra | – |
| Tests | **pytest** + a small set of `ffmpeg` invocations on golden input/output | – | – |
| Visual regression | **Pillow `ImageChops.difference`** + threshold check | No browser needed | – |

**No new required dependencies** for Phases 1-2. Phase 3 v3 alignment adds `aeneas` (optional).

---

## 10. Performance Budget

Target machine: 4 cores / 8 threads, 16 GB RAM, NVMe SSD, Windows 10/11.

### Phase 1

| Operation | Today | Target | Δ |
|---|---|---|---|
| Render 1 ayah text PNG | 80 ms | 110 ms (1.4× slower due to supersample) | -30 ms |
| Build 1 segment (FFmpeg) | 5.5 s | 5.5 s (no change) | 0 |
| **7-ayah total** | **~45 s** | **~47 s** | +2 s |

Cost: ~2 s. Acceptable.

### Phase 2

| Operation | Today | Target | Δ |
|---|---|---|---|
| Build 1 segment (FFmpeg) | 5.5 s | 5.5 s (no change) | 0 |
| 7-ayah Al-Fatiha e2e (verified) | 68 s | 68 s | 0 |
| Crossfade concat | 7 s | 7 s | 0 |

No change. Just enables existing animation data and the per-template crossfade.
Verified: `outputs/video/*phase2full*low*.mp4` is 44.47s, 42.21 MB, 68.2s build.

### Phase 3 (kinetic text)

| Operation | Today | Target (even-distribution) | Target (aeneas) |
|---|---|---|---|
| Compute word timings | 0 ms | 5 ms | 1500 ms (one-time, cached) |
| Render N word PNGs | 80 ms | 800 ms (10× — but parallelizable) | 800 ms |
| Build kinetic segment | 5.5 s | 8.5 s (more overlays in filter graph) | 8.5 s |
| **7-ayah total** | **~45 s** | **~75 s** | **~90 s first run, ~75 s cached** |

**Mitigations:**

- Cache word timings aggressively (see §7.2).
- Drop `max_workers` from 4 → 2 for `high` quality (memory).
- Keep `kinetic_text=False` as the default for `low` quality and `preview`.

---

## 11. Testing Strategy

### 11.1 Unit tests (pytest)

- [ ] **U1** `tests/unit/test_text_rendering.py`
  - `test_render_arabic_produces_rgba_image`
  - `test_render_with_supersample_2_matches_supersample_4_within_1px`
  - `test_stroke_width_does_not_change_image_size`
  - `test_arabic_ligatures_preserved` (assert glyph count > 0 in the rendered output's alpha channel)
- [ ] **U2** `tests/unit/test_word_timing.py`
  - `test_even_distribution_sums_to_duration`
  - `test_tashkeel_heuristic_penalizes_diacritics`
  - `test_breath_pauses_included`
- [ ] **U3** `tests/unit/test_animations.py` — for each entry in `TEXT_ANIMATIONS`:
  - `test_filter_is_non_empty_string`
  - `test_filter_is_valid_ffmpeg_syntax` (parse with `ffmpeg -filters` and assert the primitives exist)
  - `test_filter_does_not_reference_undefined_labels`

### 11.2 Integration tests (FFmpeg subprocess)

- [ ] **I1** `tests/integration/test_kinetic_segment.py`
  - Render Al-Fatiha 1:1 with `kinetic_text=True`.
  - Use `ffprobe` to verify:
    - duration matches the audio within ±50 ms.
    - the segment has exactly 30 fps.
    - the text overlay is present (detect by sampling frames and asserting pixel variance in the text region).
  - Compare against the static-PNG baseline (Phase 1 + 2) — both videos should have the same duration and the same audio track.

### 11.3 Visual regression

- [ ] **V1** `tests/visual/test_typography.py`
  - For each `(template, font, fontsize)` combo, render Surah 1 Ayah 1.
  - Compare to `tests/fixtures/golden/*.png` using `ImageChops.difference`.
  - Allow ≤ 0.5% pixel difference to accommodate OS-level font rendering variance.

### 11.4 Smoke test (CI)

```bash
# In CI (.github/workflows/test.yml)
- name: Smoke-test animation pipeline
  run: |
    python -c "
    import main
    main.init_font_system()
    main.init_bg_cache()
    timings = main.compute_word_timings_even(['بسم', 'الله', 'الرحمن', 'الرحيم'], 3.2)
    assert len(timings) == 4
    assert abs(timings[-1][2] - 3.2) < 0.1
    print('word timing OK')
    "
```

---

## 12. Rollout & Feature Flags

The change is gated by a single Python config block to keep blast radius small:

```python
# main.py — new section near the top, after the imports
FEATURE_FLAGS = {
    'font_polish':        True,    # Phase 1
    'text_animations':    True,    # Phase 2
    'kinetic_text':       False,   # Phase 3 — opt-in
    'forced_alignment':   False,   # Phase 3 v3 — opt-in
}
```

### Rollout schedule

| Week | Milestone | Risk | Rollback |
|---|---|---|---|
| **W1** | Phase 1 (T1.1 - T1.12) merged behind `font_polish=True` | Low | Set `font_polish=False` |
| **W1.5** | Phase 2 (T2.1 - T2.5) merged behind `text_animations=True` | Low | Set `text_animations=False` |
| **W2-W3** | Phase 3 v1 (T3.1 - T3.15, kinetic text + even timing) | Medium | Set `kinetic_text=False` |
| **W3.5** | Phase 3 v2 (tashkeel heuristic) | Low | Set `kinetic_text=False` |
| **W4** | Phase 3 v3 (aeneas alignment, opt-in via `forced_alignment=True`) | Medium | Set `forced_alignment=False` |

### Backward compatibility

- All new behavior is opt-in by default. Existing users see no change unless they flip a flag.
- The static PNG path (`build_segment_ffmpeg` with `text_animation_filter=None`) is preserved verbatim and is the explicit fallback in §7.7.
- The `kinetic_text` UI checkbox defaults to `true` for `medium` / `high`, `false` for `low` / `preview`.

### Monitoring

- [ ] **M1** Log line per ayah: `kinetic={true|false} words=N dur={X} timings=even|heuristic|aligned`
- [ ] **M2** Counter on fallback rate: if `kinetic_text=True` and fallback fires, increment a metric. If > 5% over a day, alert.
- [ ] **M3** `runlog.txt` size: should not double from baseline (each ayah adds 10-15 lines of debug output; aggregate is < 200 lines / 7-ayah render).

---

## Appendix A — Code-Location Index

For engineers picking up this work:

| Concern | File · Line | What's there now |
|---|---|---|
| Pillow text render | `main.py:480-559` | `render_arabic_to_pil_image` — brute-force stroke |
| Save text PNG | `main.py:1418-1425` | `render_text_to_png` |
| Save text PNG with dynamic color | `main.py:1423-1477` | `render_text_to_png_with_colors` |
| Build one segment | `main.py:1483-1625` | `build_segment_ffmpeg` |
| Animation filter (DEAD) | `main.py:1332-1339` | `get_ffmpeg_text_animation_filter` — always returns None |
| Animation config | `main.py:589-600` | `TEXT_ANIMATIONS` dict — declared but unused |
| Transition config | `main.py:602-609` | `VIDEO_TRANSITIONS` dict — partially used in crossfade |
| Template defaults | `main.py:581-586` | `TEMPLATES` — has `text_animation` and `transition` keys |
| Per-ayah worker | `main.py:1624-1677` | `process_single_ayah_ffmpeg` |
| Concatenator | `main.py:1798-1840` | `build_video` crossfade section |

## Appendix B — Glossary

- **Tashkeel** — the diacritical marks (حركات) above/below Arabic letters (fat-ha, kasra, damma, sukun, shadda, tanween, madda).
- **Uthmani script** — the calligraphy used in the Madinah Mushaf; includes tashkeel and full ligatures.
- **Bismi** — بِسْمِ, "In the name of".
- **Ayah** — a single verse of the Quran.
- **Surah** — a chapter of the Quran (114 total).
- **Kinetic typography** — text that moves / animates over time (vs static).
- **Forced alignment** — the process of mapping a known transcript to an audio recording at the word/phoneme level.
- **Edge anti-aliasing** — smoothing the stair-step on diagonal/curved glyph edges using sub-pixel coverage.
- **Cross-fade** — a transition where one shot fades out while the next fades in, simultaneously.
- **PTS (Presentation Timestamp)** — an FFmpeg time reference; `setpts=PTS-STARTPTS` resets it to 0 for a clip.
