<!--
SYNC IMPACT REPORT
==================
Version change: 1.0.0 → 2.0.0 (MAJOR)
Bump rationale: Principle I redefined incompatibly — the "Audio-First
Output" prohibition on on-screen text is replaced by "Synchronized Ayah
Text Rendering", which makes recitation-synced text display a supported,
first-class capability.
Modified principles:
  - I. Audio-First Output (NON-NEGOTIABLE) → I. Synchronized Ayah Text Rendering
Added sections: none
Removed sections: none
Amended collateral:
  - Additional Constraints: old_main.py status updated from "frozen legacy"
    to historical reference for the restored text-rendering path
  - Governance: versioning example referencing "re-adding text rendering"
    removed (no longer a violation)
Templates requiring updates:
  ✅ .specify/templates/plan-template.md — generic gate, no edit required
  ✅ .specify/templates/spec-template.md — no constitution-coupled sections
  ✅ .specify/templates/tasks-template.md — no principle-driven task categories
  ✅ .opencode/commands/speckit.*.md — no outdated references
Follow-up TODOs: none
Amendment history:
  - 1.0.0 (2026-08-22): initial ratification (6 core principles)
  - 2.0.0 (2026-08-22): Principle I redefined to permit/require synced
    ayah text rendering (feature specs/002-ayah-text-sync)
-->

# Quran Reels Generator Constitution

## Core Principles

### I. Synchronized Ayah Text Rendering

Every reel MUST pair recitation audio with background video. When text
display is enabled (a first-class product capability), the system MUST render
the exact text of the ayah currently being recited:

- Displayed text MUST correspond frame-accurately (within bounded drift) to
  the audio segment playing; text of one ayah MUST NOT bleed into another's
  segment beyond a small tolerance.
- Text rendering MUST NOT degrade or replace the audio+background pipeline;
  users MUST be able to disable text and obtain pure audio+video output.
- Word-level highlighting/animations are optional enhancements built on top
  of correct full-ayah display; they MUST NOT sacrifice timing accuracy.

**Rationale**: Viewers expect to read along with the recitation; the earlier
removal was about implementation fragility, not product intent. Restoring it
as a principle guarantees it is engineered deliberately against Principles II
and IV rather than bolted on.

### II. Sacred Content Integrity

Quranic content MUST pass through the pipeline unaltered:

- Ayah text and recitation audio MUST come from vetted sources only:
  `api.alquran.cloud` (text), everyayah.com / quranicaudio.com (audio).
- Ayat MUST NOT be truncated, reordered, paraphrased, or re-spoken with
  synthetic speech.
- A failed fetch MUST fail the affected segment audibly/loudly (error surfaced
  to progress state) — the generator MUST NOT silently substitute placeholder
  or partial content.

**Rationale**: This tool handles revealed scripture; correctness of source,
order, and completeness is a domain requirement, not a nice-to-have.

### III. Simplicity & Monolith-First

The application MUST remain a single Flask process (`main.py` + `quran_reels/`
package) serving a static frontend (`UI.html`, `main.js`, `style.css`) with no
build step. New frameworks, task queues, databases, ORMs, microservices, or
bundlers MUST NOT be adopted without a documented plan that justifies why the
existing pattern is insufficient. Generation runs in one daemon thread polled
via `/api/progress`; preserve this model unless complexity is justified.

**Rationale**: A ~2k-line monolith plus static assets is the deliberate
architecture; accidental infrastructure growth is the primary maintenance risk.

### IV. External Dependency Resilience

FFmpeg and FFprobe MUST be present on PATH (verify with `shutil.which`);
their absence is a hard startup failure. Remote Quran text/audio services MUST
be treated as unreliable:

- All audio downloads flow through the LRU cache (`cache/audio`).
- Network calls MUST have timeouts and bounded retries.
- Large media MUST NOT be vendored into git; background packs live in
  gitignored `vision/`.

Note: `QURAN_FFMPEG_EXE` / portable `bin/ffmpeg/` lookup is NOT implemented
(`main.py` uses `shutil.which("ffmpeg")` only) — do not document or rely on it.

**Rationale**: The pipeline is only as reliable as its flakiest upstream;
caching and loud failure keep renders reproducible offline-first where
possible.

### V. Verification by Live Exercise

There are no test, lint, or typecheck configurations and none may be assumed.
Verification standard for any change touching generation behavior:

1. Run the server (`python main.py`).
2. Smoke test: `GET /api/config` returns 200 with expected shape.
3. Render check: `POST /api/preview` produces a single-ayah output without
   errors in `runlog.txt`.

Changes to audio sync, ffmpeg argument construction, or caching MUST be
exercised end-to-end (step 3) before being considered complete.

**Rationale**: Endpoint exercise is the project's only executable proof of
correctness today; skipping it leaves regressions undetected until real
renders fail.

### VI. Secure Defaults & Loopback Isolation

The server has NO authentication and wide-open CORS. Therefore:

- Default binding MUST remain loopback-only (127.0.0.1) via `QURAN_FLASK_HOST`.
- Non-loopback binding MUST be an explicit, conscious operator decision —
  never a casual default in config, docs, or examples.
- Secrets MUST NOT be committed; `.env` stays gitignored (`.env.example` is the
  template).

**Rationale**: With auth absent and CORS open, any non-loopback bind exposes
the host's filesystem-backed routes (`/vision/<path>`, `/outputs/<path>`).

## Additional Constraints

- **Environment parity**: the committed `.venv` is a Windows venv; on
  Linux/macOS recreate it (`python -m venv .venv`) and install from
  `requirements.txt`. Python 3.11+, Flask 3.0+, FFmpeg 6.0+.
- **Data-dir hygiene**: `vision/`, `cache/`, `outputs/`, `temp/`,
  `runlog.txt` are runtime artifacts and MUST stay gitignored; `temp/` is
  auto-cleaned and must not be used for durable data.
- **Known traps (must respect when editing)**:
  - `main.py` contains duplicated function definitions (`reset_progress`,
    `add_log`, `download_audio`, `get_ayah_text`, etc.) left over from the
    `patch.py` migration; Python keeps the LAST definition. Always search for
    duplicates before editing any of these functions or you will edit dead code.
  - `old_main.py` is frozen legacy code from the removed text-rendering era.
    It MUST NOT be edited or imported, but it MAY be consulted as a historical
    reference when re-implementing text rendering (spec
    `specs/002-ayah-text-sync`); do not treat it as a behavioral guide.
  - `README.md` and `docs/skills.md` contain drift (removed features, missing
    deps). The code is the source of truth; AGENTS.md is the trusted summary.
  - `extract.py`, `patch.py`, `audioop_patch.py` are one-off/unwired scripts,
    not part of the application surface.

## Development Workflow

- **Edit discipline**: before modifying a function in `main.py`, grep for
  duplicate definitions of the same name; edit the surviving (last) definition
  or de-duplicate explicitly as part of the change.
- **Verification gates**: every functional change passes Principle V steps 1–3;
  pipeline-affecting changes additionally verify a multi-ayah `/api/generate`.
- **Config changes**: new options go through `quran_reels/config.py` +
  `QURAN_*` env vars loaded from `.env`, documented in `.env.example`;
  defaults MUST be safe (loopback, port 5000, 1080x1920).
- **Docs policy**: when architecture, routes, or data flow change, update
  AGENTS.md; do not treat README.md as authoritative.
- **Circular imports**: `quran_reels/services/background.py` lazy-imports
  `main` inside functions — keep that pattern; do not convert to top-level
  imports.

## Governance

This constitution supersedes all other practices, docs, and ad-hoc decisions.
Conflicts are resolved in favor of this document.

- **Amendment procedure**: propose the change (with rationale), update this
  file, bump the version per semver rules below, record the amendment date,
  and propagate impacts to dependent templates/specs in the same change.
- **Versioning policy**:
  - MAJOR: principle removal, incompatible redefinition, or removal of a
    governance guarantee.
  - MINOR: new principle, materially expanded guidance, or a new mandatory
    section.
  - PATCH: clarifications, wording, typo fixes, non-semantic refinements.
- **Compliance review**: plans must pass their "Constitution Check" gate
  before Phase 0 research; implementations must demonstrate the Principle V
  verification steps; reviewers MUST reject changes violating Principles I,
  II, or VI regardless of scope or convenience.
- **Runtime guidance**: use `AGENTS.md` for day-to-day development guidance;
  this document defines what may not be violated.

**Version**: 2.0.0 | **Ratified**: 2026-08-22 | **Last Amended**: 2026-08-22
