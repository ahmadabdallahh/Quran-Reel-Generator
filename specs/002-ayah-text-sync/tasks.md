---
description: "Task list template for feature implementation"
---

# Tasks: Ayah Text Sync

**Input**: Design documents from `/specs/002-ayah-text-sync/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅

**Tests**: No test framework exists in this project (Constitution Principle V).
Verification = live endpoint exercise per `quickstart.md`; checkpoint tasks below
reference its scenarios instead of automated test suites.

**Organization**: Grouped by user story (US1 read-along display P1 · US2
legibility & theming P2 · US3 word-level highlighting P3).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

Single-project Flask monolith (per plan.md): `main.py` + `quran_reels/`
package at repo root; static frontend files at root; new assets under
`assets/fonts/`.

⚠️ **Standing trap (research.md D10)**: before editing ANY function in
`main.py` (`build_segment_ffmpeg`, `get_ayah_text`, `add_log`,
`update_progress`, …), grep for duplicate definitions of that name and edit
ONLY the surviving (last) definition.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Font asset + environment confirmation needed by every story.

- [ ] T001 [P] Create `assets/fonts/`, bundle one Quranic-grade OFL font
      (Amiri or Scheherazade New regular, <1 MB) plus its `LICENSE-OFL.txt`;
      record chosen filename for config constants
- [ ] T002 [P] Confirm runtime text-shaping capability on the dev machine:
      run `python3 -c "from PIL import features; print(features.check('raqm'))"`
      and verify it prints `True`; if False, stop and record blocker in
      `specs/002-ayah-text-sync/research.md` D1 before any further work

**Checkpoint**: Font file present; raqm confirmed.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Config surface + standalone renderer that ALL user stories depend on.

**⚠️ CRITICAL**: No user story work begins until this phase is complete.

- [ ] T003 Add text-rendering constants to `quran_reels/config.py`:
      `TEXT_FONT_CANDIDATES` (bundled font first, system Noto Kufi Arabic
      fallback), `TEXT_ZONE` geometry (max_width_frac=0.86, lower-center
      anchor), `TEXT_SIZE_MIN_PX`/`TEXT_SIZE_MAX_PX` clamps,
      `BACKING_COLOR`/`BACKING_OPACITY` (dark, ~0.6),
      `SHOW_TEXT_DEFAULT=True`, `HIGHLIGHT_WORDS_DEFAULT=False`
- [ ] T004 Create leaf renderer module `quran_reels/services/text_overlay.py`
      (zero imports of `main`): `load_font()` walking the candidate chain;
      `render_ayah_text_png(text, profile, frame_w, frame_h)` returning the
      written PNG path — RAQM text layout, greedy line wrap, rounded
      semi-transparent backing box, transparent RGBA output sized ≤ frame
- [ ] T005 Sanity-render Al-Ikhlas 1:1 standalone with a one-off
      `python -c` invocation of `render_ayah_text_png()` from
      `quran_reels/services/text_overlay.py`; open the PNG and visually
      verify right-to-left connected letterforms and correctly positioned
      tashkeel BEFORE any server wiring

**Checkpoint**: Renderer proven in isolation — Arabic shaping correct.

---

## Phase 3: User Story 1 — Read Along With the Recitation (Priority: P1) 🎯 MVP

**Goal**: Every generated reel displays the complete text of the ayah whose
audio is playing, entering/exiting exactly at segment boundaries; toggle
reproduces today's output.

**Independent Test**: quickstart.md Scenarios 2–4 — single-ayah preview shows
correct synced text; multi-ayah reel has clean boundary transitions;
`show_text:false` output matches the pre-feature pipeline.

### Implementation for User Story 1

- [ ] T006 [US1] In `main.py`: FIRST grep for duplicate
      `def build_segment_ffmpeg` and edit ONLY the surviving definition —
      add optional `text_png_path=None` parameter; when set, append the PNG
      as an extra `-i` input and insert an `overlay` filter node after the
      background chain (both `n==1` and `n>1` filter branches) before the
      outro fade mapping
- [ ] T007 [US1] In `main.py` `process_single_ayah_ffmpeg()`: accept
      `show_text` flag; when enabled call `get_ayah_text(surah, ayah)` and
      `render_ayah_text_png(...)` to `temp/{job}_text_{surah}_{ayah}.png`,
      passing the path into `build_segment_ffmpeg()`; when disabled pass
      nothing (exact current behavior)
- [ ] T008 [US1] In `main.py`: wrap the T007 fetch/render calls so a text
      failure raises a contextual error (`تعذر جلب نص الآية {surah}:{ayah}`)
      that reaches `current_progress.error` and `runlog.txt` and aborts the
      job — never a silent textless "success" (FR-010/SC-007)
- [ ] T009 [US1] In `main.py` route handlers `generate_video()` and
      `preview_video()`: parse `show_text` from request JSON (default
      `SHOW_TEXT_DEFAULT`) and thread it through the `build_video(...)`
      worker arguments and preview flow per
      `specs/002-ayah-text-sync/contracts/generate-api.md`
- [ ] T010 [US1] In `main.py` Bismillah title-card builder: force NO body
      text overlay on the intro segment regardless of `show_text`; first
      ayah text appears only with its own audio (FR-007)
- [ ] T011 [US1] In `main.py`: emit one progress/log line per segment via the
      surviving `update_progress()`/`add_log()` —
      `text: fetched|rendered|skipped ({surah}:{ayah})` (SC-006 log visibility)
- [ ] T012 [US1] Frontend: add a default-checked "Show ayah text /
      إظهار نص الآية" checkbox to `UI.html`; send `show_text` in both the
      generate and preview request payloads in `main.js`

**Checkpoint**: Run quickstart Scenarios 2, 3, 4, and 6 — US1 complete and
independently demonstrable (this alone is the MVP).

---

## Phase 4: User Story 2 — Text That Is Always Readable (Priority: P2)

**Goal**: Guaranteed legibility across bright/dark/busy backgrounds and all
four template themes, with consistent styling within each reel.

**Independent Test**: quickstart.md Scenario 5 (long-ayah wrap) plus one
render per template theme — readable everywhere, style constant within a
reel.

### Implementation for User Story 2

- [ ] T013 [US2] In `quran_reels/services/text_overlay.py`: replace fixed
      size with measured auto-fit — binary-search font size between
      `TEXT_SIZE_MIN_PX`/`MAX` until wrapped block fits `TEXT_ZONE` width and
      max-lines budget; never clip, never drop below the legibility floor
      (FR-006/SC-004 extremes e.g. surah 2 ayah 255)
- [ ] T014 [US2] Populate per-theme values in `TEXT_STYLE_PROFILES` inside
      `quran_reels/config.py` for keys `ramadan`, `normal`, `masjid`,
      `islamic` (accent colors, backing opacity variants) matching existing
      `TEMPLATES` entries
- [ ] T015 [US2] In `quran_reels/services/text_overlay.py`: compute effective
      glyph-vs-backing contrast and automatically thicken shadow/backing
      until ≥4.5:1 (SC-003) instead of trusting static opacity
- [ ] T016 [US2] In `main.py` `build_video()`: resolve the active
      TextStyleProfile ONCE from the chosen template and pass that single
      instance to every segment's render call — no per-segment re-derivation
      (FR-009 consistency)

**Checkpoint**: Scenario 5 passes; four themed renders reviewed; styling
constant across segments within each reel.

---

## Phase 5: User Story 3 — Word-Level Read-Along Highlighting (Priority: P3)

**Goal**: Karaoke-style emphasis advancing word-by-word with the recitation,
strictly forward, falling back to plain display when timings are unreliable.

**Independent Test**: One single-ayah reel with highlighting enabled —
emphasis progresses forward in rough sync; with the feature off, output is
identical to US1/US2 behavior.

### Implementation for User Story 3

- [ ] T017 [US3] Extend `quran_reels/services/text_overlay.py`: export word
      bounding boxes (index, x/y/w/h) from the RAQM layout alongside the PNG
      so overlays can target exact word positions
- [ ] T018 [US3] In `quran_reels/services/text_overlay.py`: implement
      proportional word-window estimation — split audio duration by
      cumulative character length per word producing strictly increasing
      `[start, end]` windows (research.md D9)
- [ ] T019 [US3] In `main.py` surviving `build_segment_ffmpeg()`: when
      highlighting is active, generate/composite ONE reusable gold radial
      highlight image positioned per word with
      `enable='between(t,start,end)'` overlay expressions driven by the
      exported boxes/windows — a single moving highlight layer, not one
      input per word
- [ ] T020 [US3] Plumb `highlight_words` (default `HIGHLIGHT_WORDS_DEFAULT`)
      through `generate_video()`/`preview_video()` routes in `main.py`, the
      worker args, and a `UI.html`/`main.js` toggle; when timings are
      unavailable or the flag is off, fall back cleanly to plain full-ayah
      display (FR-011)

**Checkpoint**: Highlighted sample reviewed for forward-only progression;
disabled state byte-comparable to US2 output.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Docs truthfulness, hygiene, and full-suite verification.

- [ ] T021 [P] Flip the status note in `AGENTS.md` from "planned, not yet
      implemented" to implemented-behind-toggle for ayah text rendering,
      referencing `specs/002-ayah-text-sync/`
- [ ] T022 In `main.py` `cleanup_temp()`/atexit path: confirm generated
      `{job}_text_*.png` artifacts match the existing temp-cleanup patterns
      and are removed after jobs (data-dir hygiene)
- [ ] T023 Execute the FULL `specs/002-ayah-text-sync/quickstart.md` suite
      including Scenario 7 performance budget (≤20% overhead) and Scenario 1
      smoke; paste the results summary into the PR description
- [ ] T024 Final trap audit: `grep -n "^def "` over `main.py`, confirm every
      function this feature touched had exactly one surviving definition
      edited (no dead-code edits), per research.md D10

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies — T001/T002 start immediately
- **Foundational (Phase 2)**: requires T001+T002 — BLOCKS all stories
- **US1 (Phase 3)**: requires Phase 2 — delivers MVP alone
- **US2 (Phase 4)**: builds on US1's wired pipeline (T007) but changes only
  renderer/config internals — start after Phase 3 checkpoint
- **US3 (Phase 5)**: requires US1 overlay plumbing (T006/T007) and benefits
  from US2 measurement work — start after Phase 4 checkpoint
- **Polish (Phase 6)**: after all desired stories complete

### User Story Dependencies

- **US1**: independent of US2/US3 — fully testable after Phase 2
- **US2**: hardens presentation; does not change US1 behavior contracts
- **US3**: additive flag; OFF state must equal US2 state exactly

### Within Each Story

Renderer/config changes precede `main.py` integration; integration precedes
route/UI plumbing; every story ends at its quickstart checkpoint.

### Parallel Opportunities

- T001 ∥ T002 (unrelated files/actions)
- T013–T015 are all inside `text_overlay.py`/`config.py` but touch disjoint
  functions — serial recommended to avoid merge friction; T016 touches
  `main.py` only
- T021 is independent of code paths — anytime after Phase 5
- Different stories CAN proceed in parallel once Phase 2 done, but share
  `main.py` — sequential execution (P1→P2→P3) is the low-risk default for a
  solo developer

---

## Parallel Example: User Story 1

```bash
# After Phase 2 checkpoint, US1 runs largely serially through main.py
# (shared file), but these two can be prepared concurrently by the same
# developer in separate working copies:
Task T006: "Overlay input in build_segment_ffmpeg() — main.py"
Task T012: "UI checkbox + payload wiring — UI.html / main.js"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 → Phase 2 (foundation)
2. Phase 3 (US1) → STOP → validate via quickstart Scenarios 2/3/4/6
3. Demo-ready: reels now show synced ayah text with a working toggle

### Incremental Delivery

- +US2: legibility guaranteed on all templates/long ayahs → re-run
  Scenarios 5 + themed renders
- +US3: opt-in word highlighting → targeted single-ayah validation
- Each increment leaves the previous one's behavior intact (toggle/fallbacks)

### Solo-Developer Strategy

Single `main.py` owner ⇒ execute phases strictly sequentially
(P1 → P2 → P3); commit after each checkpoint; keep each commit green against
its checkpoint scenarios.

---

## Notes

- No automated tests exist or are introduced (Constitution V) — checkpoints
  ARE the verification gates; commit only after a checkpoint passes
- All `main.py` edits: duplicate-definition grep FIRST (T006 pattern)
- Never let a text-fetch failure produce a "successful" textless reel
  (T008 is a correctness gate, not polish)
