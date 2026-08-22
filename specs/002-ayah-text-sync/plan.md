# Implementation Plan: Ayah Text Sync

**Branch**: `002-ayah-text-sync` | **Date**: 2026-08-22 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-ayah-text-sync/spec.md`

## Summary

Render the complete Arabic text of the ayah currently being recited on each
video segment, synchronized with the recitation audio, with per-template
styling, guaranteed legibility, and a user toggle that reproduces today's
audio+background-only output when disabled. Technical approach: pre-render
each ayah's text to a transparent PNG using Pillow with native RAQM layout
(verified available — proper RTL shaping + tashkeel positioning without
extra dependencies), then composite it in the existing per-segment FFmpeg
filter graph as an overlay input. Because each output segment already maps
1:1 to one ayah's audio window, boundary-accurate sync is structural, not
computed. Text comes from the existing vetted `quran-uthmani` fetch path
with its cache/timeout/retry behavior; fetch failure fails the job loudly.

## Technical Context

**Language/Version**: Python 3.11+ (Flask 3.0+, Pillow 10.4.0 already in requirements.txt)

**Primary Dependencies**: Flask (existing server), Pillow w/ libraqm (text
rendering — `PIL.features.check('raqm') == True` on this machine), FFmpeg +
FFprobe on PATH (segment building), requests (existing text fetch)

**Storage**: filesystem only — text PNGs in gitignored `temp/` (auto-cleaned),
outputs in `outputs/video`; in-memory `AYAH_TEXT_CACHE` reused for API text

**Testing**: no test framework configured (Constitution Principle V) —
verification by live exercise: `GET /api/config` smoke, `POST /api/preview`
single-ayah render, multi-ayah `POST /api/generate`, frame extraction checks
defined in quickstart.md

**Target Platform**: local single-process web app bound to loopback;
1080x1920 (9:16) vertical output; Linux/macOS dev machines

**Project Type**: web-service (Flask monolith + static frontend, no build step)

**Performance Goals**: text rendering adds ≤20% to total generation time
(SC-006); per-segment PNG render is milliseconds-scale vs seconds-scale x264
encode

**Constraints**: exact `quran-uthmani` text fidelity (no paraphrase/truncation,
FR-002); ≥4.5:1 contrast treatment (SC-003); ≤0.5s boundary tolerance
(structurally satisfied); loud failure on text-fetch error when enabled
(FR-010); bundled Quranic font kept small (<1 MB asset, not "large media")

**Scale/Scope**: 6,236 ayahs addressable; single-user local tool; scope =
full-ayah display (P1) + theming/legibility (P2); word-level highlighting
(P3) behind an off-by-default flag using proportional timing fallback

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design — all gates still PASS.*

| # | Principle | Status | Evidence |
|---|-----------|--------|----------|
| I | Synchronized Ayah Text Rendering | ✅ PASS | This feature implements it (v2.0.0 amendment). Disable toggle preserved → pure audio+bg output (FR-008/SC-005). Boundary sync structural via segment-scoped overlay. |
| II | Sacred Content Integrity | ✅ PASS | Text from existing `get_ayah_text()` → api.alquran.cloud `quran-uthmani`, unmodified; fetch failure raises → job fails loudly (FR-010), never silent textless success. |
| III | Simplicity & Monolith-First | ✅ PASS | One new leaf module (`quran_reels/services/text_overlay.py`) + overlay input in existing `build_segment_ffmpeg()`. No new frameworks, queues, DBs. No new pip deps (raqm-capable Pillow already required). |
| IV | External Dependency Resilience | ✅ PASS | Reuses AYAH_TEXT_CACHE + 10s timeout + retry. Font bundled locally (<1 MB OFL asset — justified: not media, removes system-font nondeterminism). |
| V | Verification by Live Exercise | ✅ PASS | quickstart.md defines endpoint-driven validation incl. frame-extraction checks. |
| VI | Secure Defaults & Loopback Isolation | ✅ PASS | No route/auth/CORS surface changes. |

## Project Structure

### Documentation (this feature)

```text
specs/002-ayah-text-sync/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
│   └── generate-api.md  # /api/generate + /api/preview show_text contract
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
quran_reels/
├── config.py                  # EDIT: add TEXT_STYLE_PROFILES per template,
│                              #   SHOW_TEXT default, font paths, text-zone constants
└── services/
    ├── background.py          # unchanged (lazy-import pattern untouched)
    └── text_overlay.py        # NEW leaf renderer: ayah text -> transparent PNG
assets/
└── fonts/                     # NEW: bundled Quranic-grade font (OFL) + fallback chain
main.py                        # EDIT: thread show_text through build_video ->
                               #   process_single_ayah_ffmpeg -> build_segment_ffmpeg
                               #   (overlay input); bismillah intro shows no body text
UI.html, main.js, style.css    # EDIT: "Show ayah text" checkbox -> payload field
```

**Structure Decision**: Single-project layout retained (Constitution III).
The renderer lives as a leaf service module taking explicit parameters —
no imports of `main`, so the circular-import trap does not apply. Legacy
`old_main.py` consulted as historical reference only (constitution allows).

## Complexity Tracking

> No constitution violations — table intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |
