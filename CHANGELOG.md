# Changelog

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
