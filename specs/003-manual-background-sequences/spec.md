# Feature Brief: Hand-Picked Visual Sequences for Quran Reels

**Status:** Proposed — review before implementation  
**Feature:** `003-manual-background-sequences`  
**Project:** Quran Reels Generator  
**Audience:** The project owner and the AI assistant implementing the approved feature

## The idea

Let the creator choose between the existing automatic background selection and a hand-built sequence from their own images and videos in a designated local folder. In manual mode, they choose the exact background files, order them, and set how long each should appear—for example, a rain clip for 20 seconds followed by a still image for 10 seconds. Optionally, they can add a separate ambient sound such as rain.

The Quran recitation determines the final reel length. The selected visual sequence is fitted to that duration: a short sequence repeats and a long one is trimmed at the end. Optional ambience is mixed quietly beneath the recitation. The creator can preview the sequence and see its repeat/trim behavior before rendering. Backgrounds are never picked at random while manual mode is selected.

## What success looks like

A creator can keep automatic selection or choose a particular rain scene or other background, set each scene's duration, place scenes in order, and preview how they cover the complete recitation. They can optionally add a separate ambient track. The generated reel preserves the Quran audio duration and clarity.

## Current project context

- The app is a Flask application with a static HTML/CSS/JavaScript interface.
- FFmpeg renders each segment and combines video with recitation audio.
- Existing visual templates select from local style folders and use an automatic background rotator.
- Ayah text and Basmala rendering already exist; word-level highlighting remains unavailable without verified timestamps.
- The existing automatic background mode should remain available and keep working as it does today.

## Proposed user flow

1. The creator places image and video files in the managed visuals folder, and optionally ambient audio files in a separate ambience folder.
2. In the generator, they choose **Automatic backgrounds** or **Choose backgrounds**.
3. In manual mode, the app shows eligible files as a gallery with a thumbnail, filename, and media type.
4. The creator adds the desired files to a sequence, orders them, and sets each scene duration in seconds.
5. The creator previews the visual sequence, its total duration and estimated repeat/trim behavior. They may optionally select an ambient track and set its volume.
6. The app renders the sequence under the selected recitation, reports progress, and provides the finished video.

## Proposed product decisions

These defaults keep the feature simple and protect the existing workflow. Please review them before implementation.

- **Managed folders:** use `vision/custom/visuals/` and `vision/custom/ambience/` under the configured vision directory. This avoids exposing arbitrary server filesystem paths in the UI. Nested subfolders may be supported if useful for organizing collections.
- **Supported files:** common still-image formats (`.jpg`, `.jpeg`, `.png`, `.webp`) and FFmpeg-readable video formats (`.mp4`, `.mov`, `.m4v`, `.webm`). Unsupported, unreadable, or zero-byte files are not selectable.
- **Selection:** manual mode uses only the files and order selected by the creator. Reordering must be explicit and repeatable.
- **Per-scene duration:** the creator sets a duration for every selected item. A still image remains visible for that duration. A video is trimmed or looped to cover that scene duration.
- **Sequence shorter than recitation:** repeat the selected sequence from its beginning until the recitation ends. Trim the final scene at the end of the recitation. Never shorten, stretch, or insert silence into the recitation to fit the visuals.
- **Sequence longer than recitation:** stop at the end of the recitation and trim the last scene to match.
- **Sequence preview:** before rendering, show the total selected-scene duration and an estimate of how many times the sequence will repeat or how much will be trimmed to match the recitation.
- **Background video audio:** always mute audio tracks embedded in selected background videos.
- **Optional ambience:** allow the creator to explicitly select a separate local ambient audio file such as rain. Default to off. Make its volume adjustable and restrained, apply gentle fades, and loop or trim it to the full recitation duration. Keep the Quran recitation clear and primary. Do not automatically select ambience.
- **Transitions:** use a restrained dissolve between visual scenes. Transitions affect the video only and must not move the recitation timeline.
- **Existing behavior:** automatic background selection remains available and unchanged unless the creator switches to manual mode.
- **Text and Quran accuracy:** preserve the existing exact ayah text, Arabic font rendering, Basmala rules, and current behavior for unavailable word timestamps.

## Scope

### Included

- A managed folder for creator-supplied background images and videos.
- A gallery that previews eligible local files and distinguishes images from videos.
- Explicit asset selection, sequence ordering, and per-scene duration controls.
- A preview of the selected visual sequence before rendering.
- FFmpeg composition that fits the visual sequence to the recitation duration.
- Clear validation and progress messages for missing, unsupported, or unreadable files.
- Validation that submitted paths resolve only inside the managed custom-background folder.
- Preservation of the existing automatic background mode and output formats.

### Not included in the first version

- Downloading stock footage or requiring a Pexels/Pixabay API key.
- Uploading media to a cloud service.
- Automatic ambience selection or extracting audio from background videos.
- AI-generated scene selection or random selection in manual mode.
- A full multi-track video editor or per-word timing editor.
- Deleting, overwriting, or moving the creator's source files.

## Functional requirements

- **FR-001:** The app must provide an automatic mode and a manual visual-sequence mode.
- **FR-002:** Manual mode must list supported files found inside the managed custom-background folder.
- **FR-003:** The creator must be able to select exact files and set their display order.
- **FR-004:** Each selected visual must have an editable duration in seconds and a clear duration range.
- **FR-005:** The preview must show the selected order and approximate timing before rendering.
- **FR-006:** Still images must fill the output frame using a consistent crop or fit rule for portrait, square, and landscape outputs.
- **FR-007:** Video scenes must be trimmed or looped to their assigned duration, with their source audio removed.
- **FR-008:** The video sequence must cover the complete Quran audio duration. If needed, repeat the selected sequence and trim the final scene. The preview must disclose the estimated repeat count or trim amount.
- **FR-009:** Visual transitions must not shift, shorten, duplicate, or add silence to the Quran recitation.
- **FR-010:** File paths supplied by the browser must be validated against the managed folder. Directory traversal and external paths must be rejected.
- **FR-011:** Missing or invalid selections must produce a clear error before a long render starts.
- **FR-012:** The app must preserve the existing automatic background selection and existing Quran text behavior.
- **FR-013:** Rendering progress must identify the selected visual currently being processed.
- **FR-014:** The creator may optionally choose a separate supported ambient audio file; ambience is off by default and its volume is adjustable.
- **FR-015:** Ambient audio must loop or trim to the recitation duration, use gentle fades, and remain quiet enough for the Quran recitation to stay clear and primary.
- **FR-016:** Audio embedded in selected background videos must be removed even when a separate ambient track is enabled.

## Acceptance criteria

1. Given 20 supported files in the custom folder, the gallery lists those files and allows the creator to preview them.
2. Given a chosen image and rain video, the creator can place them in a specified order and assign different durations, such as 10 and 20 seconds.
3. Given manual mode, the output uses only the chosen files in the chosen order; it does not substitute a random background.
4. Given a visual sequence shorter than the recitation, the sequence repeats or loops to cover the remaining audio, and the video has no unintended black gap.
5. Given a visual sequence longer than the recitation, the output ends with the recitation and trims the final visual scene.
6. Before rendering, the preview displays the selected sequence's total time and estimated repeat count or trim amount.
7. With ambience off, only the Quran recitation is audible. With ambience enabled, the selected ambient track is quiet, fades gently, and spans the recitation without changing its timing.
8. Comparing the source recitation with the rendered output confirms the recitation is not time-stretched, cut, duplicated, or replaced by source-video audio.
9. Portrait, square, and landscape outputs render without stretching the source image or exposing empty borders.
10. Missing, unsupported, corrupt, and out-of-folder selections are rejected with a useful message.
11. Existing automatic mode still produces output without requiring any custom files.
12. A rendered sample is inspected at scene boundaries and at bright/dark backgrounds for crop quality, legibility, black frames, and audio continuity.

## Project constraints

- Keep the current Flask, HTML/CSS/JavaScript, and FFmpeg architecture; do not introduce Remotion or a cloud renderer for this feature.
- Keep creator assets local and outside version control unless the creator explicitly chooses otherwise.
- Do not delete or overwrite existing background files.
- Do not invent ayah timing. Use the existing recitation/ayah synchronization behavior.
- No test, lint, or type-check configuration currently exists. Verification should use the project's available Python/JavaScript checks and representative FFmpeg renders.

## Suggested implementation boundaries

Treat this as one user-facing capability with clear internal boundaries:

| Area | Responsibility |
|---|---|
| Local media library | Find, validate, and preview files under the managed folder |
| Sequence editor | Select exact files, order them, and assign durations |
| Render timeline | Convert the chosen sequence into video scenes that cover the recitation duration |
| Quran audio protection | Keep the original recitation timing and discard background-video audio |
| Optional ambience | Mix only an explicitly selected, low-volume ambient track beneath the recitation |

Recommended build order: local media listing and validation → sequence selection and duration UI → render timeline integration → preview and representative render review.

## AI implementation instructions

Before changing code:

1. Review this brief and the existing `specs/001-dynamic-background-pool/` and `specs/002-ayah-text-sync/` documents.
2. Confirm the proposed decisions, especially the managed folders, sequence-repeat behavior, and optional separate ambience track.
3. Inspect the current render pipeline and identify the narrowest integration points. Do not replace the existing renderer.
4. Present an implementation plan and acceptance-test plan for review.
5. Implement only after this brief and plan are approved.

During implementation, preserve user files, keep custom assets out of Git, validate local paths, and verify a short reel with at least one still image and one video scene in each supported output orientation.

## Review questions

- Are `vision/custom/visuals/` and `vision/custom/ambience/` good folders for the creator's media?
- Should a short sequence repeat until the recitation ends, as proposed, or should the creator choose a separate fallback scene?
- Should the separate ambience track be included in the first version, off by default and mixed quietly beneath the recitation?
- Is a modest dissolve between scenes the desired default transition?

## Review status

**Awaiting creator review.** No implementation is authorized by this brief alone; update the proposed decisions here before the implementation plan is approved.
