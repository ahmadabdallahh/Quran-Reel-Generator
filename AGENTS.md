# AGENTS.md

## What this is

Flask web app that generates Quran recitation reels (recitation audio synced over background video). Current code renders audio + background video only — but text-overlay rendering is being reintroduced: Constitution v2.0.0 (2026-08-22) redefined Principle I to permit/require synchronized ayah text display; see `specs/002-ayah-text-sync/spec.md` (planned, not yet implemented).

- Backend: single `main.py` (~2,100 lines) + small `quran_reels/` package
- Frontend: static `UI.html` + `main.js` + `style.css`, served by Flask (no build step)
- External deps at runtime: FFmpeg + FFprobe on PATH; APIs `api.alquran.cloud` (text) and everyayah.com / quranicaudio.com (audio)

## Commands

```bash
python -m venv .venv && source .venv/bin/activate   # NOTE: committed .venv is a Windows venv — recreate it on Linux/macOS
pip install -r requirements.txt
python main.py            # serves http://127.0.0.1:5000
```

There are **no tests, lint, or typecheck configs**. Verification = run the server and exercise endpoints (`GET /api/config` for a cheap smoke test, `POST /api/preview` for a single-ayah render).

## Configuration

All config via `QURAN_*` env vars loaded from `.env` (see `.env.example`). Defaults: loopback-only host, port 5000, 1080x1920. The server has **no auth** and wide-open CORS — never set `QURAN_FLASK_HOST=0.0.0.0` casually.

Gotcha: `.env.example` documents `QURAN_FFMPEG_EXE` / portable `bin/ffmpeg/` lookup, but current `main.py:165` only does `shutil.which("ffmpeg")` — the env var is not implemented. Ensure ffmpeg is on PATH.

## Architecture notes

- `quran_reels/config.py` is a leaf module with all constants (templates, quality presets, reciters, surah tables). It's re-exported at module level in `main.py` so `from main import X` keeps working.
- `quran_reels/services/background.py` uses **lazy imports of `main`** inside functions to avoid circular imports — don't convert these to top-level imports.
- Flask routes live at the bottom of `main.py` (~line 2027+): `/`, `/style.css`, `/main.js`, `/api/generate`, `/api/progress`, `/api/preview`, `/api/config`, `/vision/<path>`, `/outputs/<path>`.
- Generation runs in a daemon thread; progress state is polled by the UI at `/api/progress`.
- Data dirs (gitignored): `vision/` (background mp4 packs per style), `cache/audio` (LRU audio cache), `cache/backgrounds`, `outputs/video`, `temp/` (auto-cleaned), `runlog.txt`.

## Known traps

- **`main.py` contains duplicated function definitions** (`reset_progress`, `add_log`, `update_progress`, `download_audio`, `get_ayah_text`, `init_bg_cache`, `pick_bg`, etc. each appear twice) — an accident from the one-off `patch.py` migration script. Python keeps the *last* definition. When editing any of these, search for duplicates first or you may edit dead code.
- `old_main.py` (216 KB) is legacy reference code from the removed text-rendering era. Don't edit it or use it as a guide for current behavior.
- `extract.py` and `patch.py` are one-off migration scripts, not part of the app.
- Docs drift: `README.md` still documents text overlays/fonts/animations that were removed; `docs/skills.md` lists deps missing from requirements.txt that current code no longer imports. Trust the code over both.
- `audioop_patch.py` is an unused Python 3.13 shim (nothing imports it).
