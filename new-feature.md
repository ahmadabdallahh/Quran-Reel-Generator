# Feature Proposal: Hand-Picked Backgrounds and Ambient Audio

**Status:** Proposed — review before implementation  
**Project:** Quran Reels Generator

## The idea

Add manual background selection alongside the existing automatic selection. The creator can choose specific images or videos, arrange several scenes, and set how long each scene appears. They can optionally pair a scene with a matching ambient sound, such as rain audio for a rainy scene.

The Quran recitation remains the primary and clearest audio in the video. Ambient audio is optional, stays quieter than the recitation, and plays only during the scene it is assigned to. Scene durations and ambient sounds must not change the recitation's length or timing.

## Proposed user flow

1. The creator chooses the existing automatic background mode or manual selection mode.
2. In manual mode, the creator browses available images and videos, selects the assets to use, arranges them, and sets each scene's duration.
3. For each scene, the creator may select an optional ambient audio file, such as rain or wind, or leave it without additional sound.
4. The creator previews the scene order, durations, and assigned sounds before generating the video.
5. The app renders the video to the recitation's duration: it repeats the visual sequence if it ends early, or trims the final scene if the sequence runs long.

## Proposed decisions

- Keep the existing automatic mode available and working as it does today.
- In manual mode, use only the files selected by the creator, in the order they specified.
- Allow an optional, separate ambient audio file for each scene. Do not automatically extract audio from background videos.
- Keep ambient audio quieter than the recitation, with a restrained default level and a user-adjustable volume. Use the Quran recitation as the mixing reference and lower the ambience further when needed to keep the words clear.
- Sync each scene's ambient sound to that scene's duration and use gentle fades at its start and end. Repeat the sound when its scene repeats.
- If no ambient audio is selected for a scene, play only the recitation during that scene.
- Make the final video as long as the recitation. Do not cut or slow the recitation or add silence to make it fit the backgrounds.
- This proposal does not change ayah display, Basmala rules, or any related behavior.

## Scope

### Included

- A choice between automatic backgrounds and manual selection.
- Browsing local images and videos and explicitly selecting files for manual mode.
- Ordering scenes and setting each scene's duration.
- Optionally selecting and adjusting the volume of ambient audio for each scene.
- Previewing the sequence, its duration, its repeats or trims, and the sounds assigned to scenes.
- Mixing ambient audio quietly while preserving recitation clarity.

### Out of scope for this version

- AI-driven automatic selection of backgrounds or ambient sounds.
- Downloading images, videos, or audio from the internet.
- A full multitrack video editor or word-level timing controls.
- Changes to ayah display or Basmala behavior.

## Acceptance criteria

1. The creator can continue using the existing automatic background selection.
2. In manual mode, the output uses the creator's selected files and order without substituting random backgrounds.
3. The creator can set a different duration for each scene and preview the sequence before rendering.
4. The creator can assign ambient audio to a specific scene and leave other scenes without additional audio.
5. Ambient audio stays in sync with its scene, repeats with that scene when needed, and fades smoothly.
6. The Quran recitation remains clear and louder than ambient sounds in the rendered output.
7. The video duration matches the recitation: short visual sequences repeat, and long sequences are trimmed at the final scene.
8. Audio embedded in background videos does not enter the mix; only ambient audio explicitly selected by the creator is used.
9. Missing, unsupported, or corrupt files produce a clear message before rendering begins.

## Implementation constraints

- Keep the current Flask, HTML/CSS/JavaScript, and FFmpeg architecture.
- Keep creator files local and validate that paths stay inside the allowed media folders.
- Do not delete or overwrite creator files.
- Inspect the current render pipeline before deciding how to build the timeline and mix audio.

## Questions for review

- Should creators choose a separate ambient sound for each scene, as proposed, or one ambient sound for the entire video?
- Should ambient audio be off until the creator selects it, as proposed?
- Should short visual sequences repeat until the recitation ends, or would you prefer another behavior when the sequence ends?

## Instructions for the implementing assistant

This document is for review only. Do not modify the application until the feature and its decisions above are approved. After approval, inspect the current render pipeline and present a concise implementation and verification plan, then implement the feature while preserving automatic mode.
