# Changelog

## 0.8.0 — 2026-10-26

### Added

- Desktop toast (`notify-send`) and browser notifications when a render
  finishes or fails, summarising the surah, ayah range, duration, and file
  size in Arabic.
- Event feed on `/api/progress` plus a "finished while you were away" banner,
  so a completion is never lost when the tab was closed and the server runs
  headless.
- `QURAN_NOTIFY_ENABLED` and `QURAN_NOTIFY_URGENCY` to control desktop toasts.

### Changed

- Preview renders stay silent by design: `build_video(..., notify=False)`.

## 0.7.1 — 2026-10-26

### Improved

- Prefer Amiri Quran with RAQM shaping and retain the bundled Scheherazade
  font as a deterministic fallback.
- Add warm ivory, soft gold, and white verse text colors; strengthen the
  rounded black backing and remove the glyph shadow for clearer reading.
- Expand and center only exceptionally long ayahs so all text stays on-frame
  at a readable size.

## 0.7.0 — 2026-10-26

### Added

- Added background scene cadence controls by seconds or ayah count.
- Kept the selected clip and camera movement continuous across ayahs in each
  scene; short clips loop until the scene ends.

## 0.6.0 — 2026-10-26

### Added

- Added optional still, slow zoom-in, slow zoom-out, and alternating drift
  movement for background footage.
- Added live motion samples and kept the ayah text fixed above moving footage.

## 0.5.0 — 2026-10-26

### Added

- Theme previews now cycle through the actual background clips in each local
  theme folder, matching the footage pool used across ayahs in generated videos.
- Added a brief, reduced-motion-aware dissolve when preview clips change.

## 0.4.0 — 2026-10-26

### Added

- Added animated transition previews and four calm scene-transition choices.
- Added spaced dissolves to reduce visual changes during longer recitations.
- Honored reduced-motion preferences in the transition previews.

## 0.3.0 — 2026-10-26

### Added

- Added a styled cancel button for active video generation and previews.
- Added cooperative cancellation that terminates active FFmpeg work and reports a cancelled state.

## 0.2.0 — 2026-10-26

### Added

- Added crossfade, fade-through-black, and direct-cut transitions between ayahs.

### Fixed

- Prevented render workers from reading or deleting an incomplete background cache file.

## 0.1.2 — 2026-10-26

### Maintenance

- Documented the proposed hand-picked background sequence workflow.
- Consolidated project planning documents and added a local run helper.

## 0.1.1 — 2026-10-25

### Maintenance

- Split the Flask monolith into focused modules while preserving the `main.py`
  entry point and its compatibility exports.

## 0.1.0 — 2026-10-25

### Added

- Folder-discovered background themes with live video previews and clip counts.
- A visible transition-style selector with reduced-motion-aware previews.
- Word-by-word ayah highlighting, enabled by default, using the existing
  character-weighted timing estimate and Honey Gold from the visual theme.
- An app version shown in the UI and returned by `/api/config`.

### Fixed

- Re-enabled the existing word-highlight rendering path in the UI and renderer.
- Offset word highlights correctly when a Bismillah visual lead-in is enabled.
- Included `.mov` files in background discovery and rendering selection.
