# AGENTS.md

## What this is

Flask web app that generates Quran recitation reels (recitation audio synced over background video). Synchronized ayah text display is implemented behind toggles: `showText` (default on) composites each ayah's exact Uthmani text onto its segment, and `highlightWords` (default on) adds best-effort karaoke-style word highlighting using character-weighted timing estimates — see `specs/002-ayah-text-sync/`.

- Backend: `main.py` is the Flask startup and compatibility entry point (~260 lines); rendering, routes, audio, backgrounds, progress, and job state live in `quran_reels/`
- Frontend: static `UI.html` + `main.js` + `style.css`, served by Flask (no build step)
- External deps at runtime: FFmpeg + FFprobe (env var, portable binary, or PATH); APIs `api.alquran.cloud` (text) and everyayah.com / quranicaudio.com (audio)

## Commands

```bash
python -m venv .venv && source .venv/bin/activate   # NOTE: committed .venv is a Windows venv — recreate it on Linux/macOS
pip install -r requirements.txt
python main.py            # serves http://127.0.0.1:5000
```

There are **no tests, lint, or typecheck configs**. Verification = run the server and exercise endpoints (`GET /api/config` for a cheap smoke test, `POST /api/preview` for a single-ayah render).

## Configuration

All config via `QURAN_*` env vars loaded from `.env` (see `.env.example`). Defaults: loopback-only host, port 5000, 1080x1920. The server has **no auth** and wide-open CORS — never set `QURAN_FLASK_HOST=0.0.0.0` casually.

FFmpeg and FFprobe resolution supports `QURAN_FFMPEG_EXE` / `QURAN_FFPROBE_EXE`, portable `bin/ffmpeg/` paths, then PATH fallback.

## Architecture notes

- `quran_reels/config.py` owns constants (themes, quality presets, reciters, surah tables) and is re-exported through `main.py` for legacy `from main import X` callers.
- `quran_reels/services/video_builder.py` orchestrates renders; `video_rendering.py` builds per-ayah segments and transitions; `audio.py`, `background.py`, and `themes.py` own their respective asset workflows.
- `quran_reels/routes.py` defines the HTTP handlers. `main.py` registers them with their existing endpoint names so `url_for('serve_vision')` and legacy imports continue to work.
- Some service helpers lazily import runtime paths and FFmpeg settings from `main.py` to avoid import cycles. Keep those imports inside functions.
- Generation runs in a daemon thread; progress state is polled by the UI at `/api/progress`.
- Data dirs (gitignored): `vision/` (background mp4 packs per style), `cache/audio` (LRU audio cache), `cache/backgrounds`, `outputs/video`, `temp/` (auto-cleaned), `runlog.txt`.

## Known traps

- Runtime behavior belongs in the service modules; keep `main.py` focused on startup, runtime configuration, and compatibility exports.
- `old_main.py` (216 KB) is legacy reference code from the removed text-rendering era. Don't edit it or use it as a guide for current behavior.
- `extract.py` and `patch.py` are one-off migration scripts, not part of the app.
- Docs drift: `docs/skills.md` may list dependencies that are no longer imported. Trust the code over that guide.
- `audioop_patch.py` is an unused Python 3.13 shim (nothing imports it).
