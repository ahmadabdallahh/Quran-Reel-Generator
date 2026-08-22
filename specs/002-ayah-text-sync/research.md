# Research: Ayah Text Sync

**Feature**: 002-ayah-text-sync | **Date**: 2026-08-22
All NEEDS CLARIFICATION items from Technical Context: none were left open —
every decision below was resolved by direct inspection of this repository and
runtime environment.

## D1: Text rendering mechanism

**Decision**: Pre-render each ayah's text to a transparent RGBA PNG with
Pillow (RAQM layout), composite via an FFmpeg overlay input inside the
existing per-segment filter graph.

**Rationale**:
- Verified `PIL.features.check('raqm') == True` on this machine → native
  HarfBuzz shaping: correct RTL order, connected letterforms, and tashkeel
  positioning without arabic_reshaper/python-bidi (deps that were dropped
  from the project).
- Full styling control (wrap measurement, backing box, per-template colors)
  computed in Python where layout is testable; FFmpeg only composites.
- Legacy-proven path: `old_main.py` used exactly PNG→overlay successfully.
- Alternative — ffmpeg `drawtext`: rejected. Relies on the ffmpeg build's
  freetype/harfbuzz flags (nondeterministic across machines), poor multi-line
  wrap control, no reliable tashkeel positioning guarantees.
- Alternative — burned ASS/SRT subtitles via libass: rejected. Styling of a
  centered verse block is awkward, adds font-config surface, and gives no
  better sync than segment-scoped overlay.

## D2: Sync model

**Decision**: Bake text into each ayah's own segment during its build; no
global timeline or cross-segment timing computation.

**Rationale**: The pipeline already maps one segment = one ayah audio window
(`process_single_ayah_ffmpeg` → `build_segment_ffmpeg`). Segment-scoped
overlay makes FR-003 (boundary alignment) structural: text physically cannot
appear outside its segment. Tolerance ≤0.5s (SC-002) is trivially met.
Word-level highlighting (spec Story 3) later becomes per-word timed overlays
within the same segment — out of scope for P1/P2.

## D3: Arabic font

**Decision**: Bundle one compact Quranic-grade font in `assets/fonts/`
(candidate: Amiri or Scheherazade New, OFL license, <1 MB), with fallback
chain → system Noto Kufi Arabic (verified present on this machine).

**Rationale**: Rendering must be deterministic across dev machines
(Constitution IV resilience); system-font-only setups vary. A sub-megabyte
OFL font is an asset, not "large media", so git-vendoring it does not
violate data-dir hygiene. Kufi-style system fonts alone render vocalized
Quranic text acceptably but are not designed for full tashkeel density.

## D4: Text source & failure behavior

**Decision**: Reuse existing `get_ayah_text(surah, ayah)` (main.py:1431) —
api.alquran.cloud `/v1/ayah/{surah}:{ayah}/quran-uthmani`, 10s timeout, one
retry, in-memory cache. On final failure: raise → job fails with clear error
in progress state/log when show_text=true.

**Rationale**: Constitution II (vetted sources only, loud failure, no silent
placeholder). No new providers introduced. Uthmani script carries full
tashkeel as required by SC-004. Cache already prevents duplicate fetches for
repeated ayahs across jobs.

## D5: Legibility treatment

**Decision**: Text zone = lower-center block (above bottom safe margin,
~86% max frame width); rounded semi-transparent dark backing box behind
glyphs (~60% opacity) + subtle shadow; auto-fit font size within min/max
bounds; long ayahs wrap to multiple lines inside the zone (never shrink
below legibility minimum).

**Rationale**: Meets SC-003 (≥4.5:1 contrast) deterministically regardless
of background brightness (bright skies, dark night styles) without runtime
background analysis — simpler than luminance-adaptive styling and robust for
all four template styles.

## D6: Template theming & config surface

**Decision**: Add `TEXT_STYLE_PROFILES` to `quran_reels/config.py` keyed by
existing templates (`ramadan`, `normal`, `masjid`, `islamic`) varying accent
colors/backing opacity within the same placement geometry; new
`show_text` request flag on `/api/generate` + `/api/preview` (default true);
UI checkbox "Show ayah text".

**Rationale**: Consistent appearance within a reel (FR-009/FR-011) comes
from profile-per-template selected once per job. Toggle default ON matches
product intent (this feature is the point of v2.0.0); OFF reproduces current
pipeline bit-for-bit (SC-005) since the overlay input simply isn't added.

## D7: Bismillah intro card

**Decision**: Intro card renders with NO ayah body text (existing visuals
unchanged); first ayah's text appears only when its audio starts.

**Rationale**: Spec FR-007. Simplest compliant behavior; decorative Bismillah
calligraphy already exists in intro visuals.

## D8: Performance impact

**Decision**: Accept measured overhead; target ≤20% (SC-006).

**Rationale**: One extra image input + overlay chain node per segment;
PNG render is milliseconds vs seconds-scale x264 ultrafast encode. Expected
overhead well under budget; verified in quickstart timing check.

## D9: Word-level highlighting (P3 scope guard)

**Decision**: Implement behind `highlight_words` flag, OFF by default at
delivery of P3; uses proportional word-timing (word i starts at
`duration * prefix_len_i / total_len`) — character-length proportional split;
falls back to plain display automatically if flag off/unavailable timings.

**Rationale**: Authoritative word timestamps aren't available from current
audio sources; spec FR-011 requires strict forward progression and graceful
fallback. Proportional timing satisfies "rough correspondence" acceptance
without new dependencies; flagged experimental until validated against real
reciters.

## D10: Duplicate-definition trap mitigation

**Decision**: Implementation tasks MUST grep for duplicate function
definitions before editing `main.py` functions (`build_segment_ffmpeg`,
`get_ayah_text`, etc.) and edit the surviving definition only.

**Rationale**: AGENTS.md documents duplicated defs from the patch.py
migration; editing dead code silently loses changes. (Post-plan note:
current main.py is post-dedup refactor f84594e lineage — verify at edit time.)
