# API Contract: show_text extension

**Feature**: 002-ayah-text-sync | **Date**: 2026-08-22

The app's only external interface is its local HTTP API + static UI. This
contract EXTENDS the existing endpoints with one optional field; all other
request/response shapes are unchanged.

## POST /api/generate

Request JSON — one new optional field:

```json
{
  "reciter": "...",
  "surah": 2,
  "startAyah": 255,
  "endAyah": 255,
  "quality": "medium",
  "format": "reels",
  "template": "normal",
  "includeBismillah": true,
  "show_text": true
}
```

| Field | Type | Default | Meaning |
|-------|------|---------|---------|
| `show_text` | boolean | `true` | Render the recited ayah's Arabic text on each segment. `false` reproduces today's audio+background-only output exactly (SC-005). |
| `highlight_words` | boolean | `false` | Experimental karaoke-style word highlighting; requires `show_text`. Falls back to plain display when timings are unavailable (FR-011). |
| `text_position` | string | `"lower"` | Text block anchor: `"lower"` (lower-center) or `"middle"` (vertically centered). Unknown values fall back to `"lower"`. |

Unknown/absent → default applies. `camelCase` aliases (`showText`, `highlightWords`, `textPosition`) are accepted.

Responses: unchanged (`{success, message}` on accept; `{error}` + 4xx when a
job is already running). Progress polling remains `GET /api/progress`.

### Error contract (FR-010 / SC-007)

When `show_text=true` and ayah text cannot be fetched after the existing
retry: the job MUST terminate with `current_progress.status = error` and an
error message visible via `/api/progress` and the run log. The endpoint MUST
NOT report success for a reel that silently omitted required text.

Example progress payload during failure:

```json
{ "is_running": false, "is_complete": false,
  "status": "error", "error": "تعذر جلب نص الآية 2:255 — تحقق من الاتصال" }
```

(Log lines additionally note per-segment outcomes: text fetched/rendered.)

## POST /api/preview

Same single new field:

```json
{ "reciter": "...", "surah": 112, "ayah": 1, "template": "normal", "show_text": true }
```

Response shape unchanged (preview video path); rendered preview MUST contain
the overlay when `show_text=true`.

## UI contract

`UI.html` gains a checkbox ("إظهار نص الآية" / "Show ayah text"), default
checked, included in both generate and preview payloads as `show_text`.
A "موضع نص الآية" select (`lower` أسفل / `middle` وسط, default `lower`)
controls the text anchor and is sent as `textPosition`; it is disabled while
"show text" is off. The preview player is a dependency-free toolbar around
the native `<video>` element (play/pause, 0.5–2× speed, fullscreen,
time label, auto-scroll into view + autoplay attempt on ready).
No other UI behavior changes.

## Non-goals

No auth/CORS changes (Constitution VI). No new endpoints.
