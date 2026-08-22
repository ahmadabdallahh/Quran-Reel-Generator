# Data Model: Ayah Text Sync

**Feature**: 002-ayah-text-sync | **Date**: 2026-08-22

Entities from spec §Key Entities, refined for the existing pipeline. All
persistence is filesystem/in-memory; no database (Constitution III).

## Entities

### AyahText

The authoritative Arabic text of one ayah, as displayed.

| Field | Type | Source | Notes |
|-------|------|--------|-------|
| surah | int 1–114 | request | validated by existing range checks |
| ayah | int 1..surah_count | request | validated against SURAH_AYAH_COUNTS |
| text | str (Uthmani, full tashkeel) | `get_ayah_text()` → api.alquran.cloud `quran-uthmani` | BOM/ZWSP stripped (existing); length ≥ 5 enforced |
| cache_key | `"surah:ayah"` | derived | key into in-memory AYAH_TEXT_CACHE |

**Validation rules** (from FR-002/FR-010):
- Text MUST be used verbatim — no truncation/reordering at any layer.
- Fetch failure after retry MUST raise → job error state (loud), never
  empty-string substitution.
- Cache hit MUST return identical bytes to first fetch within a process.

### TextStyleProfile

Per-template visual definition of ayah text presentation.

| Field | Type | Notes |
|-------|------|-------|
| template_key | enum: ramadan / normal / masjid / islamic | one profile per TEMPLATES entry |
| accent_color | RGB hex | theme-matched glyph color (e.g., gold accents for ramadan) |
| backing_color / backing_opacity | RGBA | dark rounded box behind text (~0.6 alpha default) |
| shadow | {offset, blur, color} | subtle, aids contrast on busy bg |
| zone | {max_width_frac≈0.86, anchor_y_frac} | lower-center placement geometry |
| font_size_range | {min_px, max_px} relative to 1080×1920 frame | auto-fit clamps here |
| max_lines | int | wrap limit inside frame; overflow → smaller size step, never clip |

**Validation rules** (from FR-004/FR-006/SC-003): rendered contrast vs
backing ≥ 4.5:1; final glyph height ≥ legibility minimum (~5% of frame
width); wrapping must keep all lines fully inside safe area.

### SegmentTimingMap

Mapping of each output segment to its ayah and audio window.

| Field | Type | Notes |
|-------|------|-------|
| segment_path | file path | temp segment mp4 |
| surah, ayah | int | identity of displayed text |
| audio_duration_sec | float | measured from downloaded audio |
| is_last / is_bismillah | bool | bismillah intro → no body text overlay |

**Validation rules** (from FR-003/FR-007): exactly one AyahText per
non-intro segment; intro segments carry none; text lifetime == segment
lifetime (structural).

### RenderedTextArtifact *(implementation entity)*

Transparent PNG per rendered ayah, written to gitignored `temp/`.

| Field | Type | Notes |
|-------|------|-------|
| path | temp/{job}_text_{surah}_{ayah}.png | auto-cleaned with existing temp cleanup |
| pixel_size | (w,h) ≤ frame bounds | measured wrap output |
| profile_key | template used | consistency within a job |

## State Transitions

Per-segment text lifecycle (within existing job progress model):

```
(none, show_text=false)                       # toggle-off path: current behavior
pending → fetched (AyahText cached) 
        → rendered (PNG artifact exists)
        → composited (segment mp4 contains overlay)
fetched ─✗ raise → job status=error + message (progress/log)   # FR-010 loud failure
```

Job-level states (`current_progress`) are unchanged; only new log lines and
the error path are added.

## Relationships

- Job 1—N Segments; Segment 1—1 AyahText (non-intro); AyahText N—1
  TextStyleProfile per job (profile fixed by chosen template).
- RenderedTextArtifact derives from (AyahText × TextStyleProfile).
