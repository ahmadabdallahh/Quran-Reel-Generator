# Quran Reels Generator — Technical Skills & Architecture

> **Live documentation of the codebase. If something here disagrees with the code, the code wins — please open an issue.**

**Version:** 2.0 (Refactored)
**Last Updated:** June 2026
**Maintainer:** Ahmad Abdallah
**License:** Apache 2.0

---

## 1. Project Overview

**Quran Reels Generator** is an automated, AI-assisted Python web application that creates professional vertical short-form video content (Instagram Reels / TikTok / YouTube Shorts) by synchronizing Quranic text in **Uthmani script** with high-quality recitations over beautiful animated background videos. The target audience is the Arabic-speaking Muslim community producing Islamic content for social media.

### High-Level Capabilities

| Capability | Description |
|---|---|
| **Automated ingestion** | Fetches Quranic text from `api.alquran.cloud` and recitations from `everyayah.com` / `quranicaudio.com` |
| **Multi-reciter** | 12 famous sheikhs × multiple qualities (32 / 48 / 64 / 128 kbps) |
| **Visual templates** | 4 themes (Ramadan, Normal, Masjid, Islamic) with style-based background selection |
| **Dynamic text color** | Per-ayah brightness analysis → auto contrast (white vs gold) |
| **Background rotation** | Weighted-random picker that never repeats a video back-to-back |
| **Audio cache** | LRU cache, max **500 MB** or **1000 files**, survives restarts |
| **Background cache** | FFmpeg-normalized to 1080×1920, 30 fps, yuv420p on first use |
| **Real-time progress** | 1 Hz polling of `/api/progress` (`main.js:248`) |
| **Preview mode** | Single-ayah quick test at low quality (`/api/preview`) |
| **Glassmorphism UI** | RTL Arabic, dark gold theme, animated particles (`UI.html:13-660`) |

---

## 2. Architecture

### 2.1 Component Diagram

```
┌──────────────────────────────┐    HTTP/JSON    ┌──────────────────────────────────┐
│  UI.html (RTL, glass UI)     │ ◄─────────────► │  Flask app (main.py)            │
│  + main.js (vanilla ES6)     │  POST /api/*    │  5 routes                       │
│  Polls /api/progress @ 1Hz   │  GET  /api/*    │  1 background thread per job    │
│                              │  static files   │  ThreadPoolExecutor(4 workers)  │
└──────────────────────────────┘                 │  LRU caches                     │
                                                  └────────────┬─────────────────────┘
                                                               │
                                                               ▼
                          ┌────────────────────────────────────────────────────┐
                          │  build_video() pipeline (main.py:1776-2027)        │
                          │  1. Validate surah/ayah range (VERSE_COUNTS)       │
                          │  2. ThreadPoolExecutor(4) over each ayah:           │
                          │       - download_audio (3 sources, 4 retries,      │
                          │                       circuit breaker, LRU cache)   │
                          │       - get_ayah_text  (api.alquran.cloud + cache)  │
                          │       - BackgroundRotator.get_next (weighted RNG)  │
                          │       - get_preprocessed_bg (FFmpeg normalize →     │
                          │                                bg_cache/.cache)    │
                          │       - render_arabic_to_pil_image (RGBA PNG)      │
                          │       - get_contrasting_text_color (FFmpeg crop)   │
                          │       - build_segment_ffmpeg (filter_complex)      │
                          │  3. Concat with xfade=transition=fade:0.5          │
                          │     (3-tier fallback: fade → no-fade → re-encode)  │
                          │  4. shutil.move → outputs/video/                   │
                          └────────────┬───────────────────────────────────────┘
                                       │
                                       ▼
                       ┌──────────────────────────────────┐
                       │  External HTTP services          │
                       │  - api.alquran.cloud             │
                       │  - everyayah.com                 │
                       │  - quranicaudio.com              │
                       └──────────────────────────────────┘
```

### 2.2 Process Model

- **Single-process Flask dev server** — `app.run(host='127.0.0.1', port=5000, debug=False, threaded=True)` at `main.py:2166`.
- **One daemon thread per generation job** — `main.py:2072-2079`. Polling on `/api/progress` reads a global dict.
- **ThreadPoolExecutor(4)** for per-ayah parallelism — `main.py:1870`.
- **Global mutable state** — `WORKING_FONT` (`main.py:239`), `BG_CACHE` (`main.py:1213`), `bg_rotator` (`main.py:1432`), `AYAH_TEXT_CACHE` (`main.py:900`), `current_progress` (`main.py:819`), circuit-breaker counters (`main.py:918-921`). All mutated via `global` declarations.

---

## 3. Technology Stack

### 3.1 Runtime

| Component | Version | Where | Notes |
|---|---|---|---|
| **Python** | 3.13.5 | `.venv/pyvenv.cfg:3` | `audioop` was removed; `audioop_patch.py` is required |
| **JavaScript** | ES6+ | `main.js:1` | Vanilla, no framework |
| **HTML / CSS** | HTML5 / CSS3 | `UI.html:1-853` | RTL Arabic, CSS variables, glassmorphism |

### 3.2 Python Dependencies (`requirements.txt:1-6`)

| Package | Version | Status | Purpose |
|---|---|---|---|
| `flask` | 2.3.3 | Used | Web framework & REST API |
| `flask-cors` | 4.0.0 | Used | CORS headers |
| `requests` | 2.31.0 | Used | HTTP downloads |
| `werkzeug` | 2.3.7 | Used | Flask transitive |
| `pydub` | 0.25.1 | **Effectively unused** | Only `AudioSegment.converter = FFMPEG_EXE` is set (`main.py:807-809`); the class is never instantiated. Should be removed. |
| `moviepy` | 1.0.3 | **Unused** | Comment at `main.py:813` confirms removal. |

### 3.3 Imported but **Missing from `requirements.txt`**

These will fail `pip install -r requirements.txt` on a fresh checkout:

| Package | Where imported | Purpose |
|---|---|---|
| `arabic-reshaper` | `main.py:21` | Arabic glyph shaping |
| `python-bidi` | `main.py:22` | BiDi algorithm for RTL display |
| `Pillow` (PIL) | `main.py:23` | PNG rendering, alpha, stroke |
| `numpy` | `main.py:795` | (Reserved for future pixel ops) |
| `urllib3` | `main.py:797-799` | Retry config, disable warnings |
| `pyaudioop` | `audioop_patch.py:1-188` | Python 3.13 compatibility shim |

**Recommended `requirements.txt`:**
```text
flask==2.3.3
flask-cors==4.0.0
requests==2.31.0
arabic-reshaper==3.0.0
python-bidi==0.4.2
Pillow==10.4.0
numpy==1.26.4
urllib3==2.2.3
werkzeug==2.3.7
```

### 3.4 Bundled Binaries

| Tool | Path | Version | Use |
|---|---|---|---|
| **FFmpeg** | `bin/ffmpeg/ffmpeg.exe` | 7.x (gyan.dev, 2026-01-05) | All video & audio encoding (`runlog.txt:1313`) |
| **FFprobe** | `bin/ffmpeg/ffprobe.exe` | 7.x | Duration & cache validation |
| **ImageMagick** | `bin/imagemagick/` | 7.x | **Bundled but unused** — leftover from the pre-refactor MoviePy path |

### 3.5 External Services

| Service | URL Pattern | Purpose |
|---|---|---|
| **alquran.cloud** | `https://api.alquran.cloud/v1/ayah/{surah}:{ayah}/quran-uthmani` | Arabic Uthmani text (`main.py:1172-1207`) |
| **EveryAyah.com** | `https://everyayah.com/data/{reciter}/{SSSAAA}.mp3` | Primary audio source |
| **QuranicAudio.com** | `https://download.quranicaudio.com/quran/{reciter}/...` | Audio fallback 1 |
| **QuranicAudio.com (alt)** | `https://mp3.quranicaudio.com/...` | Audio fallback 2 |

---

## 4. File Structure

```
Quran-Reels-Generator-main/
├── .git/                          # Git history
├── .gitignore                     # 168 lines — excludes cache, outputs, .venv, runlog, "last version/"
├── .venv/                         # Python 3.13.5 virtual environment
├── LICENSE                        # Apache 2.0 (11,357 bytes)
├── README.md                      # Bilingual (EN/AR) user docs
│
├── main.py                        # 2,166 lines — Flask + FFmpeg pipeline (the whole backend)
├── main.js                        # 357 lines — Frontend logic
├── UI.html                        # 30,603 bytes — RTL glassmorphism UI (single page)
├── audioop_patch.py               # 188 lines — Python 3.13 audioop shim (loaded when py>=3.13)
├── requirements.txt               # 6 deps (incomplete — see §3.3)
├── runlog.txt                     # 258,959 bytes of production logs (auto-written)
├── skills.md                      # This file
│
├── bin/
│   ├── ffmpeg/
│   │   ├── ffmpeg.exe
│   │   ├── ffplay.exe
│   │   └── ffprobe.exe
│   └── imagemagick/               # Bundled but NOT used
│
├── cache/
│   └── audio/                     # Persistent LRU audio cache
│       ├── Abdul_Basit_Mujawwad_128kbps/
│       │   └── 001001.mp3, 001002.mp3, ...
│       └── mahmoud_ali_al_banna_32kbps/
│
├── fonts/                         # 15 Arabic fonts (Amiri, Dubai, Lateef, Tajawal, ...)
│   └── test/                      # Empty placeholder
│
├── outputs/
│   ├── audio/                     # Empty
│   ├── bg_cache/                  # 70+ preprocessed backgrounds (1080×1920, 30 fps)
│   └── video/                     # Final rendered videos
│
├── temp/                          # Working files (auto-cleaned at exit via atexit)
│
├── vision/                        # Background video library
│   ├── nature/                    # 150 .mp4 files
│   ├── islamic/                   # empty (placeholder)
│   ├── masjid/                    # ~6 .mp4 files
│   └── night/                     # 9 .mp4 files
│
└── last version/                  # ⚠ Backup of pre-refactor main.py (should be deleted)
    └── main.py                    # 1,703 lines — uses psutil, shelve, MoviePy, ImageMagick
```

---

## 5. Module / File Reference

### 5.1 `main.py` (2,166 lines)

The entire backend lives in one file, divided into 19 "STEP" comment blocks.

| Step | Lines | Responsibility | Key Symbols |
|---|---|---|---|
| Imports | `1-26` | stdlib + arabic_reshaper, bidi, PIL | – |
| **1. Path resolution** | `28-45` | Portable / PyInstaller-aware paths | `app_dir():32-36`, `bundled_dir():38-42` |
| **2. Logging** | `47-60` | `runlog.txt` + console handler | `logging.basicConfig:52` |
| **3. Temp & cache** | `62-181` | `TEMP_DIR`, `AUDIO_CACHE_DIR`, LRU | `get_cached_audio_path:80-85`, `cleanup_audio_cache:87-131`, `atexit.register:181` |
| **4. Find binaries** | `183-233` | Locate FFmpeg / FFprobe / ImageMagick | `find_binary:198-211`, `FFMPEG_EXE:213`, `FFPROBE_EXE:218` |
| **5. Font system** | `235-418` | Discover, validate, cache fonts | `WORKING_FONT:239`, `init_font_system:326-397` |
| **6. Arabic text shaping** | `420-473` | `process_arabic_text()` (reshape + BiDi + wrap) | `process_arabic_text:430-473` |
| **7. PNG rendering** | `475-558` | `render_arabic_to_pil_image()` with stroke | `render_arabic_to_pil_image:479-558` |
| **8. Constants & rotator** | `560-775` | `TEMPLATES`, `QUALITY_PRESETS`, `RECITERS_MAP`, `VERSE_COUNTS`, `SURAH_NAMES`, `BackgroundRotator` | `BackgroundRotator:611-730`, `VERSE_COUNTS:732-745`, `RECITERS_MAP:762-775` |
| **9. Py3.13 shim** | `777-789` | `import audioop_patch` | `audioop_patch:786-789` |
| **10. Imports (deferred)** | `791-811` | numpy, requests, urllib3, pydub, AudioSegment.converter | `AudioSegment.converter = FFMPEG_EXE:807` |
| Flask app | `813-893` | `current_progress`, `app = Flask`, CORS, progress helpers | `current_progress:819-832` |
| **11. Utility** | `895-911` | `AYAH_TEXT_CACHE`, `get_audio_duration_ffprobe` | – |
| **12. Data fetching** | `913-1207` | Circuit breaker, `download_audio` (3 sources, 4 retries), `get_ayah_text` | `_circuit_breaker:918-921`, `download_audio:1015-1122`, `get_ayah_text:1172-1207` |
| **13. Background handling** | `1209-1350` | `init_bg_cache`, `pick_bg`, `get_preprocessed_bg` (FFmpeg) | `get_preprocessed_bg:1278-1350` |
| **13.5. Text color** | `1352-1428` | `analyze_background_brightness` (FFmpeg crop) → contrasting color | `analyze_background_brightness:1356-1382` |
| **14. PNG helpers** | `1456-1567` | `render_text_to_png`, `render_text_to_png_with_colors` (duplicated) | `render_text_to_png:1460-1511` |
| **14.5. Segment builder** | `1569-1707` | `build_segment_ffmpeg()` with `filter_complex` (xfade + overlay + aac) | `build_segment_ffmpeg:1573-1707` |
| **16. Per-ayah worker** | `1709-1770` | `process_single_ayah_ffmpeg()` | `process_single_ayah_ffmpeg:1713-1770` |
| **17. Main pipeline** | `1772-2027` | `build_video()` — orchestrator with 3-tier concat fallback | `build_video:1776-2027` |
| **18. API routes** | `2029-2140` | 9 routes | see §6 |
| **19. Entry point** | `2142-2166` | `if __name__ == '__main__'` | `app.run:2166` |

### 5.2 `main.js` (357 lines)

| Lines | Responsibility |
|---|---|
| `5-33` | `SURAH_NAMES` array + `VERSE_COUNTS` object (**duplicated from Python** — drift risk) |
| `36-59` | DOM element cache |
| `62-72` | `DOMContentLoaded` init |
| `75-143` | `initSurahs()` — populate `<select>` with live search filter |
| `145-170` | `initCounters()` — ± buttons for ayah range |
| `172-186` | `initParticles()` — animated background |
| `188-230` | `loadConfig()` — fetches `/api/config`, populates fonts & reciters |
| `234-260` | `pollProgress()` — 1 Hz polling of `/api/progress` |
| `262-284` | `updateUI()` — applies progress, logs, preview `<video>` src |
| `288-329` | Generate button handler — `POST /api/generate` |
| `331-357` | Preview button handler — `POST /api/preview` |

### 5.3 `UI.html` (853 lines)

| Lines | Responsibility |
|---|---|
| `13-29` | CSS variables (`:root` — gold theme) |
| `31-115` | Scrollbar, body, particles, animations |
| `117-237` | Header + glass-card / form grid (RTL) |
| `239-432` | Form controls (input, select, counter, premium buttons) |
| `437-532` | Status card, progress bar, log terminal |
| `544-579` | Video preview wrapper |
| `663-852` | HTML body: form (name, font, reciter, surah, ayah range, quality, template, show-text, format, action buttons) |
| `837-845` | Preview wrapper with `<a id="downloadLink">` (**never wired up** — see §10 usability issues) |

### 5.4 `audioop_patch.py` (188 lines)

Pure-Python re-implementation of the `audioop` module functions (`findmax`, `getsample`, `max`, `min`, `avg`, `rms`, `cross`, `add`, `mul`, `reverse`, `tomono`, `tostereo`, `lin2lin`, `ratecv`, `bias`). Loaded only when `sys.version_info >= (3, 13)`. **Not actually exercised by the current code path** (Pydub is unused), but kept for forward compatibility.

### 5.5 `requirements.txt` (6 lines)

See §3.2 / §3.3. **Incomplete — `pip install -r requirements.txt` fails on a fresh checkout.**

### 5.6 `last version/main.py` (1,703 lines)

Pre-refactor backup. Uses `psutil`, `shelve`, `MoviePy`, `ImageMagick`, `clean_outputs()`. **Already in `.gitignore`** but still on disk. Should be removed from the repository.

---

## 6. REST API

All endpoints are defined in `main.py:2029-2140`.

| Method | Path | Description | Handler |
|---|---|---|---|
| GET | `/` | Serve `UI.html` | `serve_ui` at `main.py:2033` |
| GET | `/style.css` | Serve `style.css` (file does **not** exist — returns 404) | `serve_css` at `main.py:2039` |
| GET | `/main.js` | Serve `main.js` | `serve_js` at `main.py:2043` |
| POST | `/api/generate` | Start a generation job in a daemon thread | `generate_video` at `main.py:2047` |
| GET | `/api/progress` | Return the global `current_progress` dict | `get_progress` at `main.py:2083` |
| POST | `/api/preview` | Generate a single-ayah preview at `low` quality | `preview_video` at `main.py:2087` |
| GET | `/api/config` | Expose `SURAH_NAMES`, `VERSE_COUNTS`, `RECITERS_MAP`, `QUALITY_PRESETS`, `OUTPUT_FORMATS`, `TEMPLATES`, `availableFonts` | `get_config` at `main.py:2110` |
| GET | `/vision/<path:filename>` | Serve any file from `vision/` | `serve_vision` at `main.py:2134` |
| GET | `/outputs/<path:filename>` | Serve any file from `outputs/` | `serve_output` at `main.py:2138` |

### 6.1 Request/Response Examples

**Generate a video** — `POST /api/generate`
```json
{
  "reciter": "Abdul_Basit_Murattal_64kbps",
  "surah": 1,
  "startAyah": 1,
  "endAyah": 7,
  "quality": "medium",
  "template": "ramadan",
  "personName": "Ahmad",
  "format": "reels",
  "selectedFont": "random",
  "showText": true
}
```
Response:
```json
{ "success": true, "message": "بدأ إنشاء الفيديو" }
```

**Poll progress** — `GET /api/progress`
```json
{
  "percent": 75,
  "status": "Processing ayah 5/7...",
  "is_running": true,
  "is_complete": false,
  "log": ["...", "..."],
  "output_path": null,
  "error": null
}
```

**Discover config** — `GET /api/config`
```json
{
  "surahs": [["الفاتحة", 1], ...],
  "verseCounts": { "1": 7, "2": 286, ... },
  "reciters": { "AbdulBasit AbdulSamad (Murattal)": "Abdul_Basit_Murattal_64kbps", ... },
  "qualityPresets": ["low", "medium", "high"],
  "outputFormats": ["reels", "story", "post"],
  "templates": ["ramadan", "normal", "masjid", "islamic"],
  "workingFont": "Amiri-Bold.ttf",
  "availableFonts": ["Amiri-Bold.ttf", "Dubai-Bold.ttf", ...]
}
```

---

## 7. Processing Pipeline

### 7.1 `build_video()` — main orchestrator (`main.py:1776-2027`)

```
┌──────────────────────────────────────────────────────────────────────────┐
│  POST /api/generate arrives                                              │
│  → reset_progress()                                                      │
│  → daemon thread starts build_video(...)                                 │
│                                                                          │
│  1. Validate surah ∈ [1,114] and startAyah ≤ endAyah ≤ VERSE_COUNTS[surah]│
│  2. ThreadPoolExecutor(max_workers=4).map(process_single_ayah_ffmpeg, …)  │
│       for each ayah in [startAyah..endAyah]:                             │
│         a. audio_path = download_audio(reciter, surah, ayah)             │
│            ↳ check LRU cache → EveryAyah → QuranicAudio (primary)        │
│              → QuranicAudio (alt) → 4 retries with backoff               │
│              → circuit breaker after 5 consecutive failures              │
│         b. text     = get_ayah_text(surah, ayah) (alquran.cloud + cache) │
│         c. bg_path  = bg_rotator.get_next(template.bg_style)              │
│         d. cached_bg = get_preprocessed_bg(bg_path)  (FFmpeg normalize)  │
│         e. text_png  = render_text_to_png_with_colors(text, font, color) │
│         f. color     = get_contrasting_text_color(cached_bg, ayah)        │
│                          (FFmpeg crop → grayscale → mean pixel)          │
│         g. segment   = build_segment_ffmpeg(cached_bg, text_png, audio)  │
│  3. Concatenate all segments:                                            │
│       Try 1: xfade=transition=fade:duration=0.5:offset=4.5 (stream copy)  │
│       Try 2: re-encode with libx264 ultrafast                            │
│       Try 3: no-fade concat demuxer                                      │
│  4. shutil.move → outputs/video/{filename}.mp4                            │
│  5. cleanup_temp() (atexit)                                              │
└──────────────────────────────────────────────────────────────────────────┘
```

### 7.2 Audio Download — `download_audio()` (`main.py:1015-1122`)

1. Check LRU cache (`AUDIO_CACHE_DIR/<reciter>/<surah:03d><ayah:03d>.mp3`).
2. Try **EveryAyah.com** with pattern `{surah:03d}{ayah:03d}.mp3`.
3. Fallback to **QuranicAudio.com** with chapter-based naming.
4. Fallback to **mp3.quranicaudio.com** alternative path.
5. **4 retries** with exponential backoff; **circuit breaker** opens after 5 consecutive failures for 30 s.

### 7.3 Arabic Text Pipeline — `process_arabic_text()` (`main.py:430-473`)

```python
text     = fetch_raw_text(surah, ayah)        # alquran.cloud
reshaped = arabic_reshaper.reshape(text)      # glyph joining for ligatures
display  = get_display(reshaped)              # python-bidi: correct RTL ordering
# Strip BOM and ZWJ; wrap to max width; ensure newline handling
```

### 7.4 Text-to-PNG — `render_arabic_to_pil_image()` (`main.py:479-558`)

- 1080-wide RGBA canvas; word-count → font-size lookup table
- Hex → RGBA; **stroke outline** for readability on busy backgrounds
- Returns PNG bytes; written to `temp/` for FFmpeg overlay

### 7.5 Background Pre-Processing — `get_preprocessed_bg()` (`main.py:1278-1350`)

- Cache key: `{bg_path}.cache` in `outputs/bg_cache/`
- Validation: ffprobe duration > 0 (uses `FFPROBE_EXE`)
- Normalization: `ffmpeg -i <src> -vf scale=1080:1920,fps=30 -c:v libx264 -preset ultrafast -pix_fmt yuv420p <dst>`
- Subsequent ayahs reuse the cached mp4

### 7.6 Segment Builder — `build_segment_ffmpeg()` (`main.py:1573-1707`)

Filter graph (1 background, 1 ayah):
```
[0:v] scale=1080:1920,fps=30,format=yuv420p,
      trim=duration={audio_dur},
      setpts=PTS-STARTPTS                [bg]
[1:v] format=rgba,
      fade=in:0:30:alpha=1,
      fade=out:{audio_dur*30-30}:30:alpha=1  [ovl]
[bg][ovl] overlay=0:0:format=auto         [v]
[2:a] apad=whole_dur={audio_dur},
      atrim=0:{audio_dur},
      asetpts=PTS-STARTPTS                [a]
[v]format=yuv420p[outv]; [a]aformat=sample_rates=48000[outa]
```

### 7.7 Concatenation — `build_video()` (`main.py:1890-2007`)

3-tier fallback ensures robustness:
1. **Stream-copy with xfade transitions** (fastest).
2. **Re-encode** with `libx264 -preset ultrafast`.
3. **Plain concat demuxer** (no transitions).

---

## 8. Configuration & Data Tables

### 8.1 Video Dimensions

| Constant | Value | Where |
|---|---|---|
| `TARGET_W` | 1080 | `main.py:561` |
| `TARGET_H` | 1920 (9:16) | `main.py:562` |

### 8.2 Quality Presets (`main.py:571-578`)

| Preset | fps | codec | preset | bitrate |
|---|---|---|---|---|
| `low` | 24 | libx264 | ultrafast | 4M |
| `medium` | 30 | libx264 | fast | 8M |
| `high` | 30 | libx264 | fast | 12M |

> ⚠ **The `quality` arg is currently ignored** in `build_segment_ffmpeg()` — it always uses `-preset ultrafast`. See `refactor.md` §P3 #25.

### 8.3 Visual Templates (`main.py:648-672`)

| Template | `bg_style` | `text_color` | `font` | `font_size_mult` | Glow | Effect |
|---|---|---|---|---|---|---|
| `ramadan` | night | `#FFD700` (gold) | Amiri-Bold | 1.20 | `#FFD700` r=8 | gold + luminous halo |
| `normal`  | nature | `#FFFFFF` | Amiri-Regular | 1.00 | — | clean white |
| `masjid`  | masjid | `#FFFFFF` | Amiri-Bold | 1.10 | `#FFFFFF80` r=4 | white + soft moonlit halo |
| `islamic` | islamic | `#FFFFFF` | Amiri-Bold | 1.10 | — | white + heavy drop shadow |

> **Fonts (HarfBuzz + FreeType pipeline):** Arabic text rendering now goes through `quran_reels.services.shaping`, which uses **HarfBuzz** (`uharfbuzz`) for OpenType shaping — ligatures, tashkeel placement, kashida, GPOS positioning — and **FreeType** (`freetype-py`) to rasterise each shaped glyph. This unlocks **every font in `fonts/`** (Almadinah, Amiri, DigitalKhatt, DigitalMadina, Dubai, Elgharib, Lateef, Letellka, RanaKufi, Tajawal, Uthman, Zain), not just the two Amiri files that PIL could render directly.
>
> `PIL_COMPATIBLE_ARABIC_FONTS` (`main.py:548`) is now a dynamic list of every .ttf/.otf in `fonts/` that FreeType can open. `get_random_font()` (`main.py:567`) picks from this list. The legacy PIL path (`use_shaping=False`) is kept as a fallback for non-Arabic text or testing but is no longer the default.
>
> Dependencies added in this phase: `uharfbuzz==0.54.1` and `freetype-py==2.5.1` in `requirements.txt`.

### 8.3.1 Phase 2 Animations & Transitions (`main.py:60-67, 1452-1531, 1738-1839, 2104-2140`)

Phase 2 wires the previously-orphaned `text_animation` and `transition` template fields. Gated by `FEATURE_FLAGS['text_animations'] = True` (`main.py:60-67`).

| Template | `text_animation` | Intro filter | `transition` | Crossfade key |
|---|---|---|---|---|
| `ramadan` | `fade_in` | `fade=t=in:st=0:d=0.5:alpha=1` | `fade` | `fade` |
| `normal`  | `slide_up` | `pad=…:0:50:…:black@0,fade=…,[crop]` | `dissolve` | `fade` (same xfade key) |
| `masjid`  | `fade_in` | same as ramadan | `fade` | `fade` |
| `islamic` | `zoom_in` | (fade stand-in; full per-frame zoom is Phase 3) | `wipe` | `wipeleft` |

**Per-segment filters (`build_segment_ffmpeg`, `main.py:1738-1839`):**
- **Intro:** `text_animation_filter` is inserted between the text PNG input and the overlay filter. The fade uses `alpha=1` so only the alpha channel animates (RGB is preserved).
- **Outro:** A 0.4 s `fade=t=out:…:alpha=1` is appended to the final composite when `is_last=False`, so the whole frame eases to the next segment. The last segment skips the outro to avoid a fade-to-black at the video's end.

**Cross-segment filter (`build_video` concat, `main.py:2104-2140`):**
- Each segment's actual duration is **probed via ffprobe** (no more hardcoded 5 s trim — that broke long ayahs like Al-Baqarah).
- `xfade` `offset` is computed as `cumulative_duration - 0.5`, so the crossfade always lands at the actual ayah boundary, not at a guessed 4.5 s.
- The `transition` field is resolved via `VIDEO_TRANSITIONS[template.transition]['type']` — so `islamic` template actually does a `wipeleft` between ayahs (was always `fade` before).
- Final output is mapped to `[outv]`/`[outa]` via explicit `null`/`anull` filters (the previous `[v1][a1]outv[outa]` syntax was malformed and was silently falling back to stream-copy concat).

**Deferred to Phase 3 (kinetic text):** `typewriter`, `bounce`, `glow`, `reveal` — these require per-frame `t` expressions on a second input stream, which doesn't compose with the static-PNG path. The `get_ffmpeg_text_animation_filter` function returns `None` for them so they fall through to a clean overlay.

### 8.4 Reciters (`main.py:762-775`)

12 reciters; quality is implied by the directory name suffix (`_32kbps`, `_64kbps`, `_128kbps`).

| Display | Reciter ID |
|---|---|
| AbdulBasit AbdulSamad | `AbdulSamad_64kbps_QuranExplorer.Com` |
| AbdulBasit (Murattal) | `Abdul_Basit_Murattal_64kbps` |
| AbdulBasit (Mujawwad) | `Abdul_Basit_Mujawwad_128kbps` |
| Abdurrahman As-Sudais | `Abdurrahmaan_As-Sudais_64kbps` |
| Muhammad Siddiq Al-Minshawy (Mujawwad) | `Minshawy_Mujawwad_64kbps` |
| Saud Ash-Shuraym | `Saood_ash-Shuraym_64kbps` |
| Mahmoud Khalil Al-Husary | `Husary_64kbps` |
| Mahmoud Ali Al-Banna | `mahmoud_ali_al_banna_32kbps` |
| Ahmed Neana | `Ahmed_Neana_128kbps` |
| Ali Jaber | `Ali_Jaber_64kbps` |
| Mohammad Al-Tablawi | `Mohammad_al_Tablaway_128kbps` |
| Mustafa Ismail | `Mustafa_Ismail_48kbps` |

### 8.5 Caches

| Cache | Location | Limit | Eviction |
|---|---|---|---|
| **Audio LRU** | `cache/audio/<reciter>/<SSSAAA>.mp3` | 500 MB / 1000 files | LRU by `st_mtime` |
| **Background** | `outputs/bg_cache/<basename>.cache` | Unbounded (one per `vision/` mp4) | Manual |
| **Ayah text** | `AYAH_TEXT_CACHE` dict in RAM | Unbounded | Manual / restart |

---

## 9. Error Handling

### 9.1 Patterns

```python
try:
    result = subprocess.run(cmd, check=True, timeout=120, capture_output=True)
except subprocess.TimeoutExpired:
    logging.warning("Operation timed out, using fallback")
    return fallback_path
except subprocess.CalledProcessError as e:
    logging.error(f"Command failed: {e.stderr}")
    raise
```

### 9.2 Known Issues (from `runlog.txt` analysis)

| Issue | Frequency in log | Where |
|---|---|---|
| `Cache validation failed: [WinError 2]` from `FFMPEG_EXE.replace('ffmpeg','ffprobe')` | 30+ | `main.py:1289-1296` |
| `Invalid audio stream. Exactly one MP3 audio stream is required` (normalize path) | 18+ | `main.py:982-989` |
| `UnboundLocalError: list_path` on crossfade fallback | 5+ | `main.py:1916` |
| `Arabic rendering pipeline validation failed: name 'process_arabic_text' is not defined` | 4+ | `main.py:351` |

See `refactor.md` §P0 for fixes.

---

## 10. Known Usability Issues (frontend)

1. **Download button is dead** — `<a id="downloadLink">` in `UI.html:842` is never wired up in `main.js:262-284`.
2. **404 poster image** — `UI.html:838` references `vision/nature_part1.mp4`; the actual file is at `vision/nature/nature_part1.mp4`.
3. **No error display** — when `data.error` is set on `/api/progress`, the user only sees a status string.
4. **Search filter is one-directional** — clearing the search input doesn't re-show all options (`main.js:84-100`).
5. **"Update Fonts" button is cosmetic** — re-runs `loadConfig()` with a CSS spinner.
6. **Preview vs Generate confusion** — UI doesn't clearly indicate Preview is single-ayah, low quality.
7. **No keyboard shortcuts** (Enter to generate).
8. **No cancel button** for running generations.
9. **Form data lost on page refresh** during a running job.
10. **No loading indicator** during the 1-2 s font/cache scan at startup.

---

## 11. Code Conventions

| Element | Convention | Example |
|---|---|---|
| Functions | `snake_case` | `get_ayah_text`, `process_arabic_text` |
| Constants | `UPPER_CASE` | `TARGET_W`, `WORKING_FONT`, `AUDIO_CACHE_MAX_SIZE_MB` |
| Classes | `PascalCase` | `BackgroundRotator` |
| Globals | `WORKING_*`, `current_*`, or `_circuit_breaker_*` | `WORKING_FONT`, `current_progress` |
| File organization | One file = one concern; ideally | `main.py` violates this (see `refactor.md` §P1) |
| Logging | `logging.info/warning/error`; never `print` for state | (Mostly) followed |
| Error handling | Catch specific exceptions; never bare `except:` | **42 bare `except:`** in `main.py` (see `refactor.md` §P2) |

---

## 12. Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'arabic_reshaper'` | Incomplete `requirements.txt` | Install the missing packages listed in §3.3 |
| `NameError: name 'process_arabic_text' is not defined` on startup | Function-order bug | Already fixed in refactor plan; will be addressed in §P0 of `refactor.md` |
| `[WinError 2]` on background cache validation | Wrong `ffprobe` path | Use `FFPROBE_EXE` constant instead of string replace |
| `Invalid audio stream` from `normalize_audio` | FFmpeg invocation missing `-f mp3` for the input | Add `-f mp3` or remove normalization |
| UnboundLocalError on crossfade fallback | `list_path` may be unset | Initialize at function top |
| Arabic text shows as boxes | Font lacks Arabic presentation forms (PIL can't apply OpenType GSUB) | Use `Amiri-Bold.ttf` or `Amiri-Regular.ttf` only; see §8.3 "Font constraint" |
| Audio download returns 404 for specific ayah | Reciter ID doesn't include that ayah on EveryAyah | Try a different reciter; check `everyayah.com/data/<reciter>/` |
| Out of memory on long surahs | ThreadPool + `-threads 4` oversubscribes | Reduce `max_workers` to 2 in `main.py:1870` |
| `runlog.txt` fills the disk | Unbounded log file | Add `RotatingFileHandler` (10 MB × 5) — see `refactor.md` §P2 |
| Port 5000 already in use (macOS AirPlay) | Hardcoded port | Override via env var or arg — see `refactor.md` §P2 |

---

## 13. License & Attribution

- **License:** Apache 2.0 — see `LICENSE`.
- **Quran text:** api.alquran.cloud (Quran.com Uthmani script).
- **Audio recitations:** everyayah.com, quranicaudio.com (reciter-dependent licensing — verify per-sheikh before commercial use).
- **Fonts & backgrounds:** User-provided — ensure proper licensing.

---

## 14. Future Enhancements

See `refactor.md` for the **prioritized, evidence-based** refactor and enhancement backlog.

**Out-of-scope for refactor.md but worth tracking:**
1. GPU acceleration (NVENC / QSV) — `main.py:1573-1707`.
2. Real crossfade/slide transitions — `VIDEO_TRANSITIONS` constant is defined but unused (`main.py:601-608`).
3. SRT/VTT subtitle export for accessibility.
4. Batch processing queue with concurrent job limits.
5. Direct social-media upload (Instagram, TikTok, YouTube Shorts APIs).
6. Docker image for reproducible builds.
7. Mobile app (React Native / Flutter).
