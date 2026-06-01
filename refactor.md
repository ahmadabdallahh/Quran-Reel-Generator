# Quran Reels Generator — Refactor Plan

> **Mission:** take the project from "works for one user on one machine" to a production-quality, maintainable, performant application. All items below are evidence-based, traced to a file:line and (where possible) to a `runlog.txt` occurrence.

**Total estimated effort:** ~6 weeks for one developer (P0 → P3, tests, docs).
**Performance target:** **3-5× faster** generation for a typical 7-ayah surah.
**Usability target:** Zero crashes on bad input, live progress <200 ms, no dead UI elements.

---

## Table of Contents

1. [Critical Bugs (P0)](#p0--critical-bugs-must-fix-first)
2. [High-Impact Refactor (P1)](#p1--high-impact-refactor)
3. [Architecture Improvements (P2)](#p2--architecture-improvements)
4. [Polish (P3)](#p3--polish)
5. [Performance Playbook](#performance-playbook)
6. [Usability Playbook](#usability-playbook)
7. [Testing Strategy](#testing-strategy)
8. [CI/CD & Tooling](#cicd--tooling)
9. [Migration Order](#migration-order)

---

## P0 — Critical Bugs (must fix first)

These cause **runtime failures, 404s, or wasted work**. They are observable in `runlog.txt` and on every fresh run.

### P0-1 · Function-order bug in font init — `Arabic rendering pipeline validation failed`

**Where:** `main.py:351` calls `validate_arabic_rendering_pipeline()` from `init_font_system()`. The function at `main.py:302-324` calls `process_arabic_text()` (defined at `main.py:430`). At module-import time, `process_arabic_text` does not exist yet → `NameError`.

**Evidence:** `runlog.txt:918, 1286, 1868, 2181`.

**Fix:**
```python
# main.py:418 — remove the module-level init_font_system() call.
# Move the call to the bottom of the module, after all function definitions.
if __name__ == '__main__':
    init_font_system()
    init_bg_cache()
    ...
```

**Effort:** 5 min · **Risk:** None (the validation has no side effects).

---

### P0-2 · Wrong FFprobe path — `[WinError 2]` on every background cache validation

**Where:** `main.py:1289-1296`
```python
ffprobe_exe = FFMPEG_EXE.replace('ffmpeg', 'ffprobe')   # BUG
subprocess.run([ffprobe_exe, '-v', 'error', '-show_entries', ...])
```
On Windows, `bin/ffmpeg/ffmpeg.exe` → `bin/ffprobe/ffprobe.exe` (does not exist).

**Evidence:** 30+ occurrences in `runlog.txt` (`runlog.txt:68, 73, 181, 213, 415, 416, 421, 507, 706, 711, 721, 823, 968, 989, 990, 1117, 1122, 1155, 1196, 1208, 1460, 1468, 1474, 1683, 1690, 1909, 1917, 1918, 2092, 2102`).

**Fix:**
```python
subprocess.run([FFPROBE_EXE, '-v', 'error', '-show_entries', ...], ...)
```

**Effort:** 1 min · **Risk:** None. `FFPROBE_EXE` is already defined at `main.py:218`.

---

### P0-3 · `normalize_audio` always fails — `Invalid audio stream`

**Where:** `main.py:980-989`
```python
cmd = [FFMPEG_EXE, '-y', '-i', input_path, '-c:a', 'libmp3lame', output_path]
subprocess.run(cmd, ...)
```
The input is mp3 but FFmpeg is told it's raw stream → error. The fix: add `-f mp3` or use the proper demuxer auto-detection (which is the default if you pass a file path). The bug is in the *normalization pipeline* being invoked when the audio is already mp3.

**Evidence:** `runlog.txt:945-948, 1083-1093, 1126, 1183-1194, 1313, 1346, 1379, 1412, 1521, 1571, 1604, 1637, 1707, 1764`.

**Fix (option A — remove normalize, it's optional):**
```python
# main.py:946-1013 — comment out or remove normalize_audio entirely.
# Callers (main.py:1117, 1107) already gracefully handle missing normalized path.
```

**Fix (option B — fix the command):**
```python
cmd = [FFMPEG_EXE, '-y',
       '-f', 'mp3', '-i', input_path,
       '-af', 'loudnorm=I=-14:TP=-1.5:LRA=11',
       '-ar', '48000', '-ac', '2',
       '-c:a', 'libmp3lame', '-q:a', '2',
       output_path]
```

**Recommendation:** option A. Normalization is a "nice-to-have" that's currently broken and adds a full re-encode pass for every ayah (huge perf cost).

**Effort:** 5 min (option A) / 30 min (option B).

---

### P0-4 · `UnboundLocalError` on crossfade fallback — `list_path`

**Where:** `main.py:1890-1977`
```python
list_path = os.path.join(TEMP_DIR, "concat_list.txt")   # line 1890
try:
    if len(segment_results) <= 1:
        list_path = os.path.join(TEMP_DIR, "single.txt")  # line 1895
        ...
    else:
        # happy path — does NOT set list_path
        subprocess.run(cmd_concat, check=True, timeout=600)
except subprocess.CalledProcessError:
    # line 1973 references list_path
    subprocess.run([FFMPEG_EXE, '-y', '-f', 'concat', '-safe', '0', '-i', list_path, ...])
```
If the happy-path `cmd_concat` raises (rare but happens), the except branch sees `list_path` as local-but-unset → `UnboundLocalError`.

**Evidence:** `runlog.txt:1260-1276`.

**Fix:**
```python
# main.py — restructure to always build the concat list before calling FFmpeg.
list_path = os.path.join(TEMP_DIR, f"concat_{int(time.time()*1000)}.txt")
with open(list_path, 'w', encoding='utf-8') as f:
    for seg in segment_results:
        f.write(f"file '{seg['path'].replace(os.sep, '/')}'\n")
        if seg.get('duration'):
            f.write(f"duration {seg['duration']}\n")
    f.write(f"file '{segment_results[-1]['path'].replace(os.sep, '/')}'\n")  # repeat last

cmd_concat = [FFMPEG_EXE, '-y', '-f', 'concat', '-safe', '0', '-i', list_path,
              '-c', 'copy', final_tmp]
try:
    subprocess.run(cmd_concat, check=True, timeout=600, capture_output=True)
except subprocess.CalledProcessError:
    # Fallback: re-encode
    ...
```

**Effort:** 30 min · **Risk:** Low.

---

### P0-5 · `bg_paths` typo in per-ayah worker

**Where:** `main.py:1732`
```python
bg_paths = [bg_path] if isinstance(bg_path, str) else bg_paths
```
`bg_paths` is undefined when reached; the right-hand side `bg_paths` is the same undefined name. This is dead code today only because `BackgroundRotator.get_next()` returns a string when `count=1`, so `bg_path` is always a string and the `else` branch never runs. But the typo will bite any future refactor that returns a list.

**Fix:**
```python
bg_paths = bg_path if isinstance(bg_path, list) else [bg_path]
```

**Effort:** 1 min · **Risk:** None (same observable behavior today).

---

### P0-6 · Incomplete `requirements.txt` — fresh `pip install` fails

**Missing:** `arabic-reshaper`, `python-bidi`, `Pillow`, `numpy`, `urllib3`.

**Fix:** see `skills.md` §3.3 for the recommended file.

**Effort:** 5 min · **Risk:** None.

---

### P0-7 · `last version/main.py` in repo

**Where:** `last version/main.py` (1,703 lines).

The `.gitignore` already excludes it but the file is on disk. Causes:
- Bloated repo size
- Confusion for new contributors
- Potential accidental `import` if someone has the wrong CWD

**Fix:** `git rm -r "last version/" && git commit` (after verifying nothing imports from it).

**Effort:** 1 min · **Risk:** None.

---

## P1 — High-Impact Refactor

### P1-1 · Split `main.py` (2,166 lines) into focused modules

**Current state:** one file mixes routing, business logic, FFmpeg command building, image processing, text rendering, caching, and concurrency. The file is divided into 19 "STEP" comment blocks; this is a code-smell signal, not a structure.

**Target structure:**
```
quran_reels/
├── __init__.py
├── app.py                    # Flask app factory + route registration
├── config.py                 # TEMPLATES, QUALITY_PRESETS, RECITERS_MAP, VERSE_COUNTS, SURAH_NAMES
│
├── routes/
│   ├── __init__.py
│   ├── ui.py                 # GET /, /style.css, /main.js, /vision/<path>, /outputs/<path>
│   ├── api.py                # /api/generate, /api/preview, /api/progress, /api/config
│
├── services/
│   ├── __init__.py
│   ├── audio.py              # download_audio, get_cached_audio_path, cleanup_audio_cache
│   ├── text.py               # process_arabic_text, render_arabic_to_pil_image
│   ├── background.py         # BackgroundRotator, get_preprocessed_bg, init_bg_cache
│   ├── video.py              # build_segment_ffmpeg, build_video, process_single_ayah_ffmpeg
│   ├── contrast.py           # analyze_background_brightness, get_contrasting_text_color
│
├── utils/
│   ├── __init__.py
│   ├── paths.py              # app_dir, bundled_dir, FFMPEG_EXE, FFPROBE_EXE
│   ├── logging_setup.py      # rotating file handler
│   ├── progress.py           # current_progress, ProgressState class (thread-safe)
│   └── shell.py              # run_subprocess_safe() with logging
│
└── legacy/
    └── main.py               # thin shim: from quran_reels import app; app.run(...)
```

**Step-by-step:**
1. Create the package skeleton.
2. Move `STEP 1-2` (paths, logging) → `utils/paths.py`, `utils/logging_setup.py`.
3. Move `STEP 3-4` (cache, binaries) → `utils/` + module-level constants.
4. Move `STEP 5-7` (font, text, PNG) → `services/text.py`, `services/fonts.py`.
5. Move `STEP 8` (constants, rotator) → `config.py`, `services/background.py`.
6. Move `STEP 11-13.5` (fetching, contrast) → `services/audio.py`, `services/contrast.py`.
7. Move `STEP 14-17` (rendering, segment, build) → `services/video.py`.
8. Move `STEP 18-19` (routes, entry) → `app.py`, `routes/`.
9. Replace `main.py` with a 5-line shim that imports and runs.

**Effort:** 4-6 hours (1 day).
**Risk:** Medium. Mitigate with: keep `main.py` as a façade during migration, run end-to-end test after each module move.

---

### P1-2 · Consolidate `render_text_to_png` and `render_text_to_png_with_colors`

**Where:** `main.py:1460-1511` and `main.py:1513-1567`.

Both functions duplicate:
- The word-count-to-font-size lookup table
- The font loading and fallback logic
- The line-wrapping algorithm
- The `WORKING_FONT` global handling
- The hex→RGBA conversion
- The stroke outline drawing

The only difference is whether the color comes from a `template['text_color']` or from a runtime parameter.

**Fix:**
```python
def render_text_to_png(
    text: str,
    font_path: Optional[str] = None,
    text_color: Union[str, Tuple[int, int, int, int]] = "white",
    stroke_color: Union[str, Tuple[int, int, int, int]] = (0, 0, 0, 200),
    stroke_width: int = 2,
    max_width: int = TARGET_W - 100,
) -> bytes:
    """Render Arabic text to RGBA PNG bytes. Single source of truth."""
    font_path = font_path or WORKING_FONT
    # ... all the logic, single copy ...
    return png_bytes

# Caller side:
def render_for_template(text: str, template: Dict) -> bytes:
    color = template['text_color']
    return render_text_to_png(text, text_color=color, stroke_width=2)
```

**Effort:** 2 hours · **Risk:** Low (covered by visual regression test).

---

### P1-3 · Replace `pydub` entirely

**Where:** `main.py:800-810`.

`pydub` is in `requirements.txt:4` but only used to set `AudioSegment.converter = FFMPEG_EXE` (which is never read because `AudioSegment` is never instantiated). The `pydub` package adds ~50 MB of install size and a hard dep on the system `audioop` module (which is why `audioop_patch.py` exists).

**Fix:** remove the import, the line, and the `requirements.txt` entry.

**Effort:** 5 min · **Risk:** None.

---

### P1-4 · Remove dead code

| Item | Where | Action |
|---|---|---|
| `TEXT_ANIMATIONS` dict | `main.py:588-599` | Delete (no caller; the function `get_ffmpeg_text_animation_filter` always returns `None`) |
| `VIDEO_TRANSITIONS` dict | `main.py:601-608` | Delete (the strings in `ffmpeg_filter` are never used) |
| `USE_FFMPEG_PIPELINE` constant | `main.py:566` | Delete (never read) |
| `IM_MAGICK_EXE`, `IM_HOME` | `main.py:214, 224` | Delete (referenced but never used) |
| `bin/imagemagick/` | filesystem | Delete (1.5 GB of unused binaries) |
| `downloadLink` `<a>` element | `UI.html:842` | Delete (never wired up — see P3-1 instead) |
| `cleanup_after_video` | `main.py:147-156` | Delete (redundant with `cleanup_temp` at exit) |
| `os.makedirs(FONT_CACHE_DIR)` at `main.py:68` | `main.py:68` | Delete (duplicated at `main.py:255`) |
| `dark Mode` CSS | `UI.html:327-333` | Delete (no-op) |
| `moviepy==1.0.3` from requirements | `requirements.txt:5` | Delete |

**Effort:** 30 min · **Risk:** None.

---

### P1-5 · Use `concurrent.futures` properly — remove the serializing lock

**Where:** `main.py:1124-1170` (`download_audio_parallel`).

The `global` `_download_lock` plus `min_delay=0.5` makes audio downloads effectively serial, defeating the ThreadPoolExecutor.

**Fix:**
- Drop the global lock.
- Use per-host connection pools (`requests.Session` with `HTTPAdapter(pool_connections=4, pool_maxsize=4)`).
- The 0.5 s "politeness delay" is a holdover from the EveryAyah.com free-tier guidelines; convert to a token-bucket rate limiter per host (`threading.Semaphore(2) + time.sleep(0.1)`).
- Use `urllib3.Retry` for backoff (already configured at `main.py:797-799`).

```python
class HostRateLimiter:
    def __init__(self, max_per_second: float = 2.0):
        self._interval = 1.0 / max_per_second
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self):
        with self._lock:
            now = time.monotonic()
            delay = self._interval - (now - self._last)
            if delay > 0:
                time.sleep(delay)
            self._last = time.monotonic()

everyayah_limiter = HostRateLimiter(max_per_second=2.0)
quranicaudio_limiter = HostRateLimiter(max_per_second=2.0)
```

**Effect:** **2-3× faster** audio download phase for 7+ ayahs.

**Effort:** 2 hours · **Risk:** Low.

---

### P1-6 · Centralize FFmpeg argument constants

**Currently scattered across:** `main.py:1573-1707` (segment), `main.py:1890-2007` (concat), `main.py:1709-1770` (per-ayah), `main.py:1356-1382` (brightness analysis). The strings `-threads 4`, `-preset ultrafast`, `-c:v libx264`, `-pix_fmt yuv420p`, `-c:a aac -b:a 192k` appear 4-5 times each.

**Fix:** one `services/ffmpeg_args.py` module:
```python
# ffmpeg_args.py
PIX_FMT = "yuv420p"
VCODEC = "libx264"
PRESET_FAST = "fast"
PRESET_ULTRAFAST = "ultrafast"
THREADS = "2"  # see P2-1
ACODEC = "aac"
ABITRATE = "192k"

COMMON_INPUT = ["-hide_banner", "-loglevel", "error"]
COMMON_OUTPUT = ["-pix_fmt", PIX_FMT, "-c:v", VCODEC, "-preset", PRESET_ULTRAFAST, "-threads", THREADS]
COMMON_AUDIO = ["-c:a", ACODEC, "-b:a", ABITRATE, "-ar", "48000", "-ac", "2"]
```

**Effort:** 2 hours · **Risk:** None.

---

### P1-7 · Replace `current_progress` global dict with a thread-safe class

**Where:** `main.py:819-832` and 30+ reads/writes across the codebase.

**Current issues:**
- No type safety.
- Concurrent reads from the polling thread + writes from worker thread = data race (Python GIL saves you most of the time, but list/dict mutations are not atomic).
- Hard to test.

**Fix:**
```python
# utils/progress.py
from threading import RLock
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class ProgressState:
    percent: int = 0
    status: str = ""
    is_running: bool = False
    is_complete: bool = False
    log: List[str] = field(default_factory=list)
    output_path: Optional[str] = None
    error: Optional[str] = None
    _lock: RLock = field(default_factory=RLock, repr=False)

    def update(self, **kwargs):
        with self._lock:
            for k, v in kwargs.items():
                setattr(self, k, v)

    def append_log(self, msg: str):
        with self._lock:
            self.log.append(msg)
            if len(self.log) > 500:
                self.log = self.log[-500:]

    def to_dict(self) -> dict:
        with self._lock:
            return {
                'percent': self.percent, 'status': self.status,
                'is_running': self.is_running, 'is_complete': self.is_complete,
                'log': list(self.log), 'output_path': self.output_path,
                'error': self.error,
            }

    def reset(self):
        with self._lock:
            self.percent = 0
            self.status = ""
            self.is_running = False
            self.is_complete = False
            self.log = []
            self.output_path = None
            self.error = None

current_progress = ProgressState()
```

**Effort:** 1 hour · **Risk:** Low.

---

### P1-8 · Add type hints everywhere

**Why:** enables `mypy` catching bugs at lint time. Currently 0 type hints in `main.py` despite the file being 2,166 lines.

**Targets:** all public function signatures + return types. Use `from __future__ import annotations` for forward refs.

**Effort:** 4 hours (boring but mechanical) · **Risk:** None.

---

### P1-9 · Add `python-dotenv` + a `.env.example`

**Why:** `.gitignore:63-65` already mentions `.env` support but no code reads it. Allows operators to override: `FLASK_PORT`, `LOG_LEVEL`, `AUDIO_CACHE_MAX_MB`, `FFMPEG_PATH`, `FFPROBE_PATH`, `MAX_WORKERS`.

**Fix:**
```python
# main.py:1
from dotenv import load_dotenv
load_dotenv()  # before anything else
```
And add `.env.example`:
```bash
FLASK_PORT=5000
FLASK_HOST=127.0.0.1
LOG_LEVEL=INFO
AUDIO_CACHE_MAX_MB=500
AUDIO_CACHE_MAX_FILES=1000
FFMPEG_PATH=           # leave blank to use bundled bin/ffmpeg
FFPROBE_PATH=
MAX_WORKERS=4
```

**Effort:** 30 min · **Risk:** None.

---

## P2 — Architecture Improvements

### P2-1 · Reduce FFmpeg thread oversubscription

**Where:** `main.py:1666, 1902, 1934, 1951, 1966` (all pass `-threads 4`).

With `ThreadPoolExecutor(max_workers=4)` × `-threads 4` = 16 worker threads per ayah. On a 4-core/8-thread machine this destroys performance due to context switching.

**Fix:** `THREADS = max(1, (os.cpu_count() or 4) // max_workers)`. Default: 2 threads per FFmpeg, 4 workers = 8 threads total = matches a typical 8-thread CPU.

**Effect:** **2× faster** end-to-end on most machines.

**Effort:** 15 min · **Risk:** None.

---

### P2-2 · Pre-warm font and background cache at startup

**Where:** `main.py:418` (init_font_system), `main.py:1244` (init_bg_cache).

Currently these are called at module import (with the bug from P0-1) and on first use. The first ayah pays 100% of the cache-miss cost.

**Fix:** add a `prewarm_caches()` step in `if __name__ == '__main__':` that:
1. Pre-renders the title card text into a single PNG (catches font fallback issues).
2. Pre-runs `get_preprocessed_bg` on the first 3 backgrounds in each style (warm-up the FFmpeg cache).
3. Runs in a background thread so the server starts accepting requests immediately.

**Effort:** 2 hours · **Risk:** None.

---

### P2-3 · Cache `analyze_background_brightness` results

**Where:** `main.py:1356-1382`.

Per-ayah FFmpeg invocation is **expensive** (200-500 ms × 4 parallel × 7 ayahs = 5-10 s of waiting on a 4-core box). Plus the 10 s timeout causes failures under load (`runlog.txt:714, 716, 978, 979, 1143`).

**Fix:** cache the brightness by `bg_path` since it doesn't change:
```python
_BRIGHTNESS_CACHE: Dict[str, float] = {}

def analyze_background_brightness(bg_path: str) -> float:
    if bg_path in _BRIGHTNESS_CACHE:
        return _BRIGHTNESS_CACHE[bg_path]
    # ... existing FFmpeg call ...
    _BRIGHTNESS_CACHE[bg_path] = brightness
    return brightness
```

**Effect:** **3-5 s saved** per generation.

**Effort:** 30 min · **Risk:** None.

---

### P2-4 · Persist `AYAH_TEXT_CACHE` across restarts

**Where:** `main.py:900`.

Currently a global dict that resets on every server restart. 22,800 possible entries × ~50 bytes = ~1 MB if serialized.

**Fix:** use `shelve` (stdlib) or a tiny SQLite DB:
```python
import shelve
_AYAH_CACHE_DB = os.path.join(EXEC_DIR, 'cache', 'ayah_text.db')

def get_ayah_text(surah: int, ayah: int) -> Optional[str]:
    key = f"{surah}:{ayah}"
    with shelve.open(_AYAH_CACHE_DB) as db:
        if key in db:
            return db[key]
    text = _fetch_from_api(surah, ayah)
    if text:
        with shelve.open(_AYAH_CACHE_DB) as db:
            db[key] = text
    return text
```

**Effort:** 1 hour · **Risk:** Low.

---

### P2-5 · Replace 1 Hz polling with Server-Sent Events (SSE)

**Where:** `main.js:234-260` polls every 1 s; backend has `current_progress` already.

**SSE flow:**
1. New route `GET /api/progress/stream` returns `text/event-stream`.
2. Backend pushes `data: <json>\n\n` on every `update_progress()` call.
3. Frontend uses native `EventSource`.

**Effect:** sub-200 ms latency for progress; **eliminates 100% of polling requests**.

**Effort:** 3 hours · **Risk:** Medium (Flask's dev server handles SSE OK, but behind any reverse proxy you need `X-Accel-Buffering: no`).

---

### P2-6 · Use Flask Blueprints

**Why:** prepare for `app.py` split (P1-1) and enable per-route auth (P2-7).

```python
# routes/api.py
from flask import Blueprint
api_bp = Blueprint('api', __name__, url_prefix='/api')

@api_bp.route('/generate', methods=['POST'])
def generate_video():
    ...
```
```python
# app.py
app.register_blueprint(api_bp)
app.register_blueprint(ui_bp)
```

**Effort:** 1 hour · **Risk:** None.

---

### P2-7 · Add minimal auth token to `/api/generate` and `/api/preview`

**Why:** anyone with access to `http://localhost:5000` can submit infinite heavy jobs. Local DoS.

**Fix:**
1. On startup, generate a random token, log it to console and `runlog.txt`.
2. Set a cookie with the token.
3. `@require_token` decorator on the heavy routes.
4. Optional env var `QRG_API_KEY` overrides the auto-generated token.

**Effort:** 1 hour · **Risk:** None for the local case; document the cookie behavior for the UI.

---

### P2-8 · Move i18n strings out of code

**Where:** `main.py:822, 841, 885, 1818, 1886, 2010, 2025, 2052, 2092, 2108` + many more.

**Fix:** create `i18n/ar.json` + `i18n/en.json`:
```json
{
  "errors": {
    "already_running": "عملية إنشاء فيديو قيد التنفيذ بالفعل",
    "invalid_surah": "رقم السورة غير صالح",
    "ayah_out_of_range": "رقم الآية خارج النطاق"
  },
  "status": {
    "downloading_audio": "جاري تحميل الصوت...",
    "rendering_segment": "جاري تجهيز المقطع {current}/{total}",
    "concatenating": "جاري دمج المقاطع..."
  }
}
```

**Effort:** 2 hours · **Risk:** None.

---

### P2-9 · Add structured logging + rotation

**Where:** `main.py:51-56`.

**Fix:** `RotatingFileHandler` with 10 MB × 5 backups, plus a JSON formatter for production:
```python
from logging.handlers import RotatingFileHandler
file_handler = RotatingFileHandler('logs/runlog.txt', maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
file_handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)-7s | %(name)s | %(message)s'))
```
Move `runlog.txt` → `logs/runlog.txt` (and update `.gitignore`).

**Effort:** 30 min · **Risk:** None.

---

### P2-10 · Add graceful shutdown

**Where:** `main.py:2166` (`app.run`).

Currently Ctrl-C during a generation kills the worker mid-FFmpeg, leaving partial files.

**Fix:** register a `signal.SIGINT` handler that sets a `threading.Event()`; the worker checks the event between ayahs and bails out cleanly, finalizing the partial video if at least one segment is complete.

**Effort:** 2 hours · **Risk:** Low.

---

## P3 — Polish

### P3-1 · Wire up the download link

**Where:** `UI.html:842`, `main.js:280-282`.

**Fix:**
```javascript
// main.js:280
function updateUI(data) {
    ...
    if (data.output_path) {
        const filename = data.output_path.split(/[\\/]/).pop();
        const link = document.getElementById('downloadLink');
        link.href = `/outputs/video/${encodeURIComponent(filename)}`;
        link.download = filename;
        link.classList.remove('disabled');
    }
}
```

**Effort:** 15 min.

---

### P3-2 · Fix video poster path

**Where:** `UI.html:838` → `poster="vision/nature_part1.mp4"` (404).

**Fix:** `poster="vision/nature/nature_part1.mp4"`.

**Effort:** 1 min.

---

### P3-3 · Display errors in the UI

**Where:** `main.js:262-284` (updateUI doesn't render `data.error`).

**Fix:** add a red banner above the log when `data.error` is set.

**Effort:** 30 min.

---

### P3-4 · Add a Cancel button

**Where:** new `POST /api/cancel` route + `main.js`.

**Fix:** set a `threading.Event()`; the worker checks it between ayahs; returns immediately.

**Effort:** 2 hours.

---

### P3-5 · Implement the `quality` preset

**Where:** `build_segment_ffmpeg` (`main.py:1573-1707`) hardcodes `-preset ultrafast` regardless of `quality`.

**Fix:** read `QUALITY_PRESETS[quality]` and apply `preset` and `bitrate` (via `-b:v`).

**Effort:** 30 min.

---

### P3-6 · Two-way surah search filter

**Where:** `main.js:84-100` hides non-matching options but doesn't restore on clear.

**Fix:** keep a reference to all options; on empty input, show all.

```javascript
function filterSurahs(query) {
    const options = document.querySelectorAll('#surahSelect option');
    const q = query.trim().toLowerCase();
    options.forEach(opt => {
        opt.hidden = q && !opt.textContent.toLowerCase().includes(q);
    });
}
```

**Effort:** 15 min.

---

### P3-7 · Add keyboard shortcuts

**Where:** `UI.html` form (Enter to generate, Esc to cancel).

**Effort:** 30 min.

---

### P3-8 · Persist form state across page refresh

**Where:** `UI.html` form.

**Fix:** save the form to `localStorage` on every change; restore on load.

**Effort:** 1 hour.

---

### P3-9 · Add `prefers-reduced-motion` support

**Where:** `UI.html:172-186` (particles).

**Fix:**
```css
@media (prefers-reduced-motion: reduce) {
    .particle { animation: none; }
}
```

**Effort:** 5 min.

---

### P3-10 · Add `aria-label` to all form controls

**Effort:** 1 hour.

---

### P3-11 · Remove `audioop_patch.py` (or gate it strictly)

**Where:** `main.py:786-789`, `audioop_patch.py:1-188`.

Pydub is unused (P1-3) → audioop is unused → the patch is unused. Once P1-3 lands, `audioop_patch.py` can be deleted.

**Effort:** 0 min (rolled into P1-3).

---

### P3-12 · Move inline styles to a real `style.css`

**Where:** scattered inline `style="..."` in `UI.html`.

**Fix:** extract to `style.css` (the route `/style.css` already exists at `main.py:2039` but the file does not — it's a 404).

**Effort:** 2 hours.

---

## Performance Playbook

The combined effect of P1-5, P1-6, P2-1, P2-2, P2-3, P2-4 should be:

| Phase | Before (7-ayah surah) | After | Speedup |
|---|---|---|---|
| Audio download (4 workers, serialized) | 12 s | 3 s | **4×** |
| Text fetch (cold cache) | 1.5 s | 0.1 s (SQLite) | 15× |
| Background pre-processing (first ayah only) | 8 s | 1 s (pre-warmed) | 8× |
| Brightness analysis (per ayah) | 3 s | 0.1 s (cached) | 30× |
| Segment encoding (4× oversubscribed) | 45 s | 18 s | 2.5× |
| Concatenation | 4 s | 4 s | 1× |
| **Total** | **~73 s** | **~26 s** | **~3×** |

With P2-1 + P2-2 the "tail" (worst-case cold start) drops from ~120 s to ~35 s.

---

## Usability Playbook

| P0/P3 item | Impact | Effort |
|---|---|---|
| P0-1..P0-6 (bug fixes) | App actually works on a fresh install | 1 hour total |
| P0-7 (remove backup) | Cleaner repo | 1 min |
| P3-1 (download link) | Users can save their work | 15 min |
| P3-2 (poster path) | No more 404 in console | 1 min |
| P3-3 (error display) | Users see what went wrong | 30 min |
| P3-4 (cancel button) | Users can abort | 2 h |
| P3-5 (quality preset) | "High" quality is actually higher | 30 min |
| P3-6 (search filter) | Less frustration | 15 min |
| P3-7 (shortcuts) | Power users happy | 30 min |
| P3-8 (form persistence) | Refresh-safe | 1 h |
| P3-9 (reduced motion) | Accessibility | 5 min |
| P3-10 (aria labels) | Screen-reader friendly | 1 h |
| P3-12 (real style.css) | Cleaner dev workflow | 2 h |

---

## Testing Strategy

### Unit tests (pytest)

```
tests/
├── conftest.py                  # shared fixtures (mocked FFmpeg, mock Cache)
├── unit/
│   ├── test_arabic_text.py      # reshape, bidi, line-wrap edge cases
│   ├── test_contrast.py         # brightness thresholds, color choice
│   ├── test_background_rotator.py # no-repetition, weighted RNG
│   ├── test_audio_cache.py      # LRU eviction, size limit
│   ├── test_paths.py            # app_dir, bundled_dir
│   └── test_progress.py         # thread-safe update / reset / serialize
├── integration/
│   ├── test_download_audio.py   # mocked HTTP, 3 sources, circuit breaker
│   ├── test_build_segment.py    # subprocess mock, filter graph
│   └── test_full_pipeline.py    # mock everything, verify call sequence
└── fixtures/
    ├── sample_uthmani.txt
    └── sample_surah_1.json
```

**Targets:**
- `process_arabic_text` — 100% coverage
- `BackgroundRotator` — 100% coverage
- `analyze_background_brightness` + `get_contrasting_text_color` — 100% coverage
- `download_audio` retry / circuit-breaker logic — 90% coverage
- `build_video` happy path + 1 fallback — 60% coverage

**Effort:** 1 day.

### Smoke test (manual / CI)

```bash
# In CI:
python -m venv .venv-test
source .venv-test/bin/activate
pip install -r requirements.txt
python main.py &
SERVER_PID=$!
sleep 3
curl -X POST http://127.0.0.1:5000/api/preview \
     -H 'Content-Type: application/json' \
     -d '{"reciter":"Abdul_Basit_Murattal_64kbps","surah":1,"ayah":1,"template":"normal"}'
sleep 15
curl http://127.0.0.1:5000/api/progress
test -f outputs/video/*.mp4 && echo OK
kill $SERVER_PID
```

**Effort:** 2 hours (must mock or stub the external HTTP services for CI to be hermetic).

---

## CI/CD & Tooling

### Pre-commit (`pre-commit`, `ruff`, `black`, `mypy`)

`.pre-commit-config.yaml`:
```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.0
    hooks: [{id: ruff, args: [--fix]}, {id: ruff-format}]
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.10.0
    hooks: [{id: mypy, additional_dependencies: [types-requests, types-Pillow]}]
```

### GitHub Actions

`.github/workflows/test.yml`:
```yaml
name: test
on: [push, pull_request]
jobs:
  test:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest]
        python: ['3.11', '3.12', '3.13']
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: ${{ matrix.python }}}
      - run: pip install -r requirements.txt -r requirements-dev.txt
      - run: pip install pytest pytest-cov
      - run: pytest --cov=quran_reels --cov-report=xml
      - uses: codecov/codecov-action@v4
```

### `requirements-dev.txt`

```text
-r requirements.txt
pytest==8.2.0
pytest-cov==5.0.0
pytest-mock==3.14.0
ruff==0.4.0
mypy==1.10.0
types-requests
types-Pillow
pre-commit==3.7.0
```

### Dockerfile (optional, for reproducible deployment)

```dockerfile
FROM python:3.12-slim
RUN apt-get update && apt-get install -y ffmpeg fonts-noto-core && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["python", "main.py"]
```

**Effort:** 1 day for all of the above.

---

## Migration Order

Suggested sequence to minimize risk and maximize early feedback.

| Sprint | Items | Goal |
|---|---|---|
| **Sprint 0 (½ day)** | P0-1 .. P0-7 | Server actually works on a fresh install; no more startup errors |
| **Sprint 1 (1 day)** | P1-3, P1-4, P1-6, P1-7, P1-9 | Clean dead code, centralize FFmpeg args, thread-safe progress, env vars |
| **Sprint 2 (1 day)** | P1-1 (full split), P1-8 | Modular code, type hints |
| **Sprint 3 (½ day)** | P1-2, P1-5 | Remove render duplication, parallelize audio |
| **Sprint 4 (½ day)** | P2-1 .. P2-4 | Performance wins: 3× faster |
| **Sprint 5 (1 day)** | P2-5, P2-6, P2-7, P2-9, P2-10 | SSE, blueprints, auth, logging, graceful shutdown |
| **Sprint 6 (1 day)** | P3-1 .. P3-12, P2-8 | Polish + i18n |
| **Sprint 7 (1 day)** | Tests, CI, pre-commit, Dockerfile | Quality gate |

**Total: ~6 working days for one developer.**

---

## Appendix · Quantified evidence from `runlog.txt`

Top recurring log patterns (frequency in 2,196 lines of runlog):

| Pattern | Count | Maps to |
|---|---|---|
| `Cache validation failed: [WinError 2]` | 30 | P0-2 |
| `Invalid audio stream. Exactly one MP3 audio stream is required` | 18 | P0-3 |
| `Arabic rendering pipeline validation failed` | 4 | P0-1 |
| `UnboundLocalError: local variable 'list_path'` | 3 | P0-4 |
| `ffmpeg timed out` (brightness analysis) | 5 | P2-3 |
| `GET /vision/nature_part1.mp4 HTTP/1.1" 404` | 3 | P3-2 |

Fixing the top 4 patterns will eliminate ~55 of the ~70 error-level log lines — i.e., the log becomes a real diagnostic tool instead of a noise generator.
