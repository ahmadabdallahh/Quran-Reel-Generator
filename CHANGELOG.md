# Changelog

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
