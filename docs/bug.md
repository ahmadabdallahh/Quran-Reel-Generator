# Bug Report - Arabic Text Rendering & Multi-Generation Audio Sync Issues

## Project

Quran Reels Generator v2.0

---

# Issue 1: Arabic Text Rendering Problems

## Description

Arabic text is not always rendered correctly inside generated videos.

Observed symptoms:

* Words appear with incorrect spacing.
* Some words are not visually connected.
* Tashkeel placement may look incorrect.
* Line wrapping sometimes breaks the visual appearance of the ayah.
* Certain fonts produce inconsistent rendering compared to others.

Example:

Expected:

بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ

Possible output:

بِسْمِ اللَّهِ      الرَّحْمَٰنِ      الرَّحِيمِ

or

ا ل ر ح م ن

---

## Suspected Causes

### 1. Incorrect line wrapping order

Current pipeline:

text
→ reshape
→ bidi
→ wrap
→ render

Wrapping may be occurring at an incorrect stage.

Need to verify:

* process_arabic_text()
* render_text_to_png()
* render_text_to_png_with_colors()
* render_arabic_to_pil_image()

---

### 2. Font compatibility issues

Project supports many fonts:

* Amiri
* Dubai
* Lateef
* Tajawal
* Uthman
* DigitalMadina
* Others

Not all fonts correctly support:

* Uthmani script
* OpenType Arabic shaping
* HarfBuzz positioning
* Tashkeel placement

Recommended testing:

Amiri-Regular.ttf

Amiri-Bold.ttf

as baseline fonts.

---

### 3. HarfBuzz fallback

Documentation mentions:

* HarfBuzz
* FreeType

Need to verify that rendering is always using the HarfBuzz pipeline and never silently falling back to a PIL-only rendering path.

---

### 4. Text centering

Need to verify:

* anchor='mm'
* textbbox()
* manual centering logic

Incorrect centering may create visual spacing artifacts.

---

# Issue 2: Audio/Text Mismatch After Multiple Generations

## Description

First generated video works correctly.

After generating another video without restarting the application:

* Audio may belong to the wrong ayah.
* Text may belong to a previous generation.
* Audio and text become unsynchronized.
* Previous generation data appears to leak into the next generation.

---

## Expected Behavior

Every generation must be completely isolated.

Generation #2 should never reuse:

* Ayah text
* Audio files
* Segment files
* Temporary PNG files
* FFmpeg concat lists
* Progress state

from Generation #1.

---

## Suspected Causes

### 1. Temporary file collisions

Need to inspect:

temp/

Possible issue:

audio_001.mp3
segment_001.mp4
text_001.png

being reused across generations.

Recommended:

Use UUID-based filenames.

Example:

audio_7a9f3c.mp3
segment_b4f2e1.mp4
text_4fd88a.png

---

### 2. Global mutable state

Project contains many globals:

WORKING_FONT

BG_CACHE

AYAH_TEXT_CACHE

current_progress

bg_rotator

Circuit breaker counters

Need to verify these are reset between jobs.

---

### 3. AYAH_TEXT_CACHE contamination

Need to verify cache keys.

Expected:

(surah, ayah)

Not:

ayah only

Otherwise incorrect text may be returned.

---

### 4. Concat list reuse

Need to inspect:

build_video()

Possible issue:

list.txt

concat.txt

being overwritten or reused between runs.

Recommended:

Generate unique concat files per job.

Example:

concat_a81f.txt

---

### 5. ThreadPool race conditions

Project uses:

ThreadPoolExecutor(max_workers=4)

Need to verify:

* shared state is thread-safe
* no concurrent writes to temp files
* no shared filenames

---

### 6. Progress state not reset

Verify:

reset_progress()

is called before every generation.

Need to ensure:

status

logs

output_path

error

percent

are cleared.

---

### 7. FFmpeg output reuse

Need to verify old outputs are not reused accidentally due to filename collisions.

Use timestamp or UUID-based output names.

---

# Recommended Investigation Priority

P0 - Critical

1. Temporary file naming collisions
2. Concat list reuse
3. Global mutable state leakage
4. ThreadPool race conditions

P1 - High

5. HarfBuzz rendering verification
6. Font compatibility testing
7. Wrapping order validation

P2 - Medium

8. Text alignment review
9. Cache optimization
10. Additional rendering tests

---

# Reproduction Steps

## Rendering Bug

1. Open application.
2. Generate any ayah with text enabled.
3. Observe spacing and word connections.
4. Repeat using multiple fonts.
5. Compare rendered output.

## Audio/Text Sync Bug

1. Generate Video A.
2. Without restarting application.
3. Generate Video B.
4. Compare:

   * Ayah text
   * Audio recitation
   * Segment ordering
5. Observe if previous generation assets appear in current output.

---

# Expected Outcome

* Arabic text renders correctly with proper shaping and spacing.
* Every generation is isolated.
* No audio/text contamination between runs.
* No stale temp files are reused.
* No race conditions when processing multiple ayahs.
