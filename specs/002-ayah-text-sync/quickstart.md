# Quickstart: Ayah Text Sync Validation

**Feature**: 002-ayah-text-sync | **Date**: 2026-08-22
Verification style per Constitution Principle V — live endpoint exercise,
no test framework. Run from repo root with the venv active and ffmpeg on
PATH.

## Prerequisites

```bash
source .venv/bin/activate        # recreated per-platform (see AGENTS.md)
python main.py                   # serves http://127.0.0.1:5000
```

Confirm in startup log: text renderer initialized and bundled font found
(`assets/fonts/`), overlay path enabled.

## Scenario 1 — Smoke

```bash
curl -s http://127.0.0.1:5000/api/config | head -c 400
```

Expected: HTTP 200, JSON containing reciters/surahs/templates. Unchanged
from pre-feature.

## Scenario 2 — Single-ayah render with text (P1 core)

```bash
curl -s -X POST http://127.0.0.1:5000/api/preview \
  -H 'Content-Type: application/json' \
  -d '{"reciter":"ar.abdulbasitmurattal","surah":112,"ayah":1,"template":"normal","show_text":true}'
```

Then inspect the returned preview video's mid-frame:

```bash
ffmpeg -y -i outputs/video/<preview>.mp4 -vf "select=eq(n\,45)" -vframes 1 /tmp/opencode/frame.png
```

Check frame:
- Complete Uthmani text of Al-Ikhlas 1:1 visible, lower-center.
- Correct RTL connected script + tashkeel (compare against source text).
- Backing box gives clear contrast; nothing clipped.

## Scenario 3 — Boundary sync across ayahs

Generate surah 112, ayahs 1–4 (`show_text:true`). Extract frames ±0.25s
around each segment boundary:

- Text of ayah N+1 appears within ≤0.5s of its audio start; ayah N's text
  is gone; no frame shows two verses' text mixed.

## Scenario 4 — Toggle-off equivalence

Repeat Scenario 2 with `"show_text":false`. Expected: output visually
identical to the pre-feature pipeline (backgrounds differ only by random
rotation); no text anywhere. This is SC-005.

## Scenario 5 — Long-ayah wrap

Render surah 2, ayah 255 (Ayat al-Kursi). Expected: full text wrapped on
multiple lines inside the safe area — no truncation, no off-frame lines,
still ≥ legibility minimum size. This exercises FR-006/SC-004 extremes.

## Scenario 6 — Loud failure drill (FR-010)

Temporarily block the text API (e.g., add `127.0.0.1 api.alquran.cloud` to
/etc/hosts or disconnect network) and run Scenario 2 with `show_text:true`.

Expected: job ends with `status:"error"` and a clear message via
`GET /api/progress`; NO "successful" textless reel is produced. Restore
connectivity afterwards.

## Scenario 7 — Performance budget (SC-006)

Time a fixed multi-ayah generation twice (same reciter/surah/template):

```bash
time curl -s -X POST .../api/generate -d '{...,"show_text":true}'   # poll /api/progress to completion
time curl -s -X POST .../api/generate -d '{...,"show_text":false}'
```

Expected: text-enabled run ≤ 1.20× the textless run (background rotation
variance tolerated).

## Pass criteria

All scenarios pass → feature verified for this change set. Record results
(runlog excerpt) in the PR description. Any failure → fix and re-run the
failed scenario plus Scenario 2 before merge.
