# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Primary: Arabic-speaking dawah content creators who publish Quran recitation
reels daily to TikTok, Instagram Reels, and YouTube Shorts. They open the local
page, pick a reciter/surah/ayah range, and expect a finished vertical video in
minutes — then post it and repeat tomorrow.

## Product Purpose

Remove the manual editing between a recitation and a postable reel. The tool
fetches the audio, renders the recited ayah's exact text in sync, and merges
both over background video — fully automatically, running locally, free.
Success = a creator with no editing skill ships a correct, good-looking reel
every day.

## Positioning

A local, free, fully automatic ayah-synced reel builder: exact Uthmani text
timed to the recitation (never a silent textless success), plus optional
word-by-word highlighting — with no account, no editor timeline, no upload
queue. A cloud editor or generic video tool cannot truthfully copy the
one-click recitation-to-synced-reel path.

## Operating Context

Single user on their own machine (`python main.py` → `http://127.0.0.1:5000`).
Inputs: background clips the user drops into `vision/`; everything else
(recitation MP3, ayah text) downloads and caches automatically. Outputs land in
`outputs/video/` as 9:16 MP4s (or 1:1). Progress is polled live; a single-ayah
preview renders first for a fast look-check.

## Capabilities and Constraints

- Surah 1–114 with per-surah ayah validation; 12+ reciters; low/medium/high
  quality; 4 visual themes driving backgrounds and transitions.
- Read-along Uthmani text (default on), lower or middle anchor, experimental
  word highlighting with plain-display fallback.
- No auth, no accounts, wide-open CORS — never expose the port casually.
- No test suite; verification is live endpoint exercise per
  `specs/002-ayah-text-sync/quickstart.md`.
- Undecided: hosted/multi-user operation; monetization; mobile-app packaging.

## Brand Commitments

Name: Quran Reels Generator ("الريلز القرآنية", positioned as ongoing charity /
sadaqah jariyah — "Made for the Ummah"). Voice: Arabic-first RTL interface.
Visual world (user-pinned, 2026-10): warm emerald + honey gold on dark —
emerald owns action, gold owns brand moments.

## Evidence on Hand

- Working app: `main.py` + `UI.html` + `main.js` + `style.css` served by Flask.
- Bundled OFL font: `assets/fonts/ScheherazadeNew-Regular.ttf`.
- Feature truth: `specs/002-ayah-text-sync/` (spec, tasks, API contract).
- Architecture map: `.archify/architecture-quran-reels-20261016-151521/`.
- No testimonials, benchmarks, or usage statistics — do not fabricate any.

## Product Principles

1. One click to a correct reel — automation over control, always.
2. Text is a promise: if the ayah text cannot render, the job fails loudly.
3. Local, free, and Arabic-first — never trade these for power features.
4. Preview before committing — a fast single-ayah check precedes every build.
5. Beginner-proof — every control explains itself; defaults produce the reel.

## Accessibility & Inclusion

No product-specific standard established. Baseline: usable Arabic RTL in a
desktop or mobile browser; computed text contrast meets WCAG AA.
