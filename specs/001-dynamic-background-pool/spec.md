# Feature Specification: Dynamic Background Pool

**Feature Branch**: `001-dynamic-background-pool`

**Created**: 2026-08-22

**Status**: Draft

**Input**: User description: "Dynamic background pool — curate high-quality vertical background videos from an external stock catalog, organized by visual style, with automatic rotation, local caching, and offline fallback (P1 item from future-steps.md)"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Style-matched fresh backgrounds for every reel (Priority: P1)

A content creator generating a Quran recitation reel selects a template/style
(e.g., Nature, Islamic, Masjid, Night) as they do today. Instead of cycling
through the small built-in background library, the system enriches that style
with suitable vertical videos drawn from a large external curated catalog and
uses them as the backdrop for the recitation. The creator gets visibly more
varied, higher-quality reels without hunting for or downloading videos
manually.

**Why this priority**: This is the core value of the feature — variety is the
primary motivation in the roadmap ("limited local library lacks variety").
Without this story the feature does not exist.

**Independent Test**: Can be fully tested by enabling the pool, generating one
multi-ayah reel per style, and verifying each segment uses an appropriate,
style-consistent vertical background sourced beyond the local library.

**Acceptance Scenarios**:

1. **Given** the external catalog is reachable and credentials are configured,
   **When** the user generates a 5-ayah reel with the "Nature" style,
   **Then** every video segment uses a portrait-orientation background
   matching the nature theme, and no two segments repeat the same video.
2. **Given** the same setup, **When** the user generates separate reels with
   each of the four styles (Nature, Islamic, Masjid, Night),
   **Then** each reel's backgrounds visually match its selected style.
3. **Given** any generation using pooled backgrounds, **When** the output
   video is inspected, **Then** all backgrounds are at least standard HD
   quality in the vertical format and contain no watermarks or embedded text.

---

### User Story 2 - Downloaded backgrounds are reused across generations (Priority: P2)

A creator who generates several reels over days should not wait for the same
videos to be fetched repeatedly, nor hit provider usage limits unnecessarily.
Once a suitable video has been acquired for a style, it is stored locally and
subsequent generations reuse it first, fetching new material only when the
stored set cannot provide enough unique options for a given reel.

**Why this priority**: Reuse protects against rate limits and cost growth and
keeps later generations fast, but the feature already delivers value without
it (Story 1).

**Independent Test**: Can be tested by generating the same styled reel twice
and confirming the second run completes with little to no waiting for new
downloads while still producing non-repeating backgrounds within the reel.

**Acceptance Scenarios**:

1. **Given** a previous generation downloaded backgrounds for the "Masjid"
   style, **When** the user generates another "Masjid" reel of equal length,
   **Then** the system reuses stored videos before acquiring new ones and the
   reel contains no repeated background.
2. **Given** stored assets exist for a style, **When** the user regenerates
   with the same settings, **Then** total generation time is noticeably lower
   than a cold first run with an empty store.

---

### User Story 3 - Generation survives catalog outages (Priority: P3)

If the external catalog is unreachable, credentials are missing/invalid, or
usage limits are exhausted mid-generation, the system must not fail the reel.
It falls back to the existing local background library for the affected
segments (or the whole reel), clearly noting the fallback in progress logs so
the creator understands why variety was reduced.

**Why this priority**: Reliability matters but only becomes relevant once
fetching exists; it is a safety net rather than new user value.

**Independent Test**: Can be tested by disabling network access or removing
credentials, then generating a reel: generation must complete successfully
using local backgrounds with a visible fallback notice.

**Acceptance Scenarios**:

1. **Given** the external catalog cannot be reached, **When** the user starts
   a generation with pooling enabled, **Then** the reel completes using local
   library backgrounds and the log records that fallback occurred.
2. **Given** usage limits are exceeded partway through a multi-segment reel,
   **When** remaining segments request new backgrounds, **Then** those
   segments use already-stored or local assets and generation finishes
   without error.

---

### Edge Cases

- What happens when the catalog returns zero acceptable results for a style?
  The affected segments fall back to stored or local backgrounds for that
  style; the reel still completes.
- How does the system handle a downloaded file that is corrupt, too short, or
  wrongly oriented? The asset is rejected before use, never appears in
  output, and is discarded/re-fetched.
- What if two segments would otherwise select the same video? Selection must
  guarantee uniqueness within a single reel while enough distinct assets
  exist.
- What happens when credentials are invalid? Treated like an outage:
  fallback path with a clear log message, no crash, no silent degradation.
- What if a very long reel needs more unique backgrounds than are available
  (stored + fetchable)? The system repeats the least-recently-used assets
  rather than failing, prioritizing completion.
- What if the operator's storage fills up? Old, least-recently-used cached
  assets may be evicted to stay within a configurable cap; eviction must
  never delete the original local library.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST acquire additional vertical background videos from
  a configured external stock-video catalog when generating reels, in
  addition to the existing local library.
- **FR-002**: System MUST only accept candidate videos that match the output
  orientation (portrait/vertical) and meet a minimum quality bar (at least
  standard HD resolution).
- **FR-003**: System MUST map each supported visual style (Nature, Islamic,
  Masjid, Night) to curated search criteria so fetched content matches the
  chosen theme.
- **FR-004**: System MUST NOT use the same background video more than once
  within a single generated reel while sufficient distinct assets exist.
- **FR-005**: System MUST store accepted downloads locally and reuse them in
  preference to re-downloading identical assets across runs.
- **FR-006**: System MUST bound its requests to the external catalog (request
  limits, timeouts, bounded retries) so a slow or erroring catalog cannot
  stall generation indefinitely.
- **FR-007**: System MUST fall back to the existing local background library
  whenever external acquisition fails, is disabled, or yields nothing usable;
  generation MUST NOT fail because of catalog problems.
- **FR-008**: System MUST record in the visible progress log whether
  segments used newly fetched, previously stored, or fallback local
  backgrounds.
- **FR-009**: System MUST obtain catalog credentials exclusively from
  operator-provided configuration outside version control; absence of
  credentials disables remote fetching without breaking generation.
- **FR-010**: System MUST reject and discard any downloaded asset that fails
  integrity/orientation/duration checks before it can appear in output.
- **FR-011**: Users MUST be able to disable remote background acquisition via
  configuration, reverting to local-library-only behavior.
- **FR-012**: System MUST limit the size of the downloaded-asset store (e.g.,
  count or disk-size cap) evicting least-recently-used assets beyond the cap,
  while never modifying the original local library.

### Key Entities *(include if feature involves data)*

- **BackgroundAsset**: One acquired background video — identified by its
  catalog reference; carries its assigned style tag, technical attributes
  (orientation, resolution, duration), acquisition date, and last-used date;
  stored on local disk outside version control.
- **StyleProfile**: The mapping between a user-facing style (Nature, Islamic,
  Masjid, Night) and the search criteria used to find matching catalog
  content.
- **AcquisitionAttempt**: A record of one fetch cycle — what was requested,
  outcome (fetched / reused / rejected / fell back), and why — feeding the
  progress log and reuse decisions.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For each of the four styles, the pool makes available at least
  five times more usable distinct backgrounds than the current local library
  provides for that style.
- **SC-002**: In any generated multi-segment reel where the pool holds enough
  distinct assets, 100% of segments use unique backgrounds (zero repeats).
- **SC-003**: With the network deliberately unavailable or credentials
  removed, 100% of generation attempts still produce a finished reel via the
  fallback path, with the fallback noted in the log.
- **SC-004**: Regenerating an already-produced styled reel with a warm asset
  store adds no perceptible acquisition wait compared with a cold run
  (target: warm-run wall-clock time within ~10% of local-library-only runs).
- **SC-005**: 100% of backgrounds appearing in final outputs pass the
  orientation and minimum-quality checks — zero landscape or sub-HD assets
  reach rendered output.
- **SC-006**: Creators reviewing progress logs can correctly tell whether a
  reel used fetched, reused, or fallback backgrounds without inspecting the
  video itself.

## Assumptions

- Default catalog provider is Pexels (per future-steps.md); the spec treats
  the provider as replaceable — requirements reference "the external
  catalog", not a specific service.
- The operator supplies their own free-tier catalog credential via the
  project's environment configuration; the app ships without embedded keys.
- Portrait means vertical format matching current reel outputs (9:16);
  minimum quality is 720p-class resolution or better.
- The existing local background packs remain untouched and continue to serve
  as both fallback source and default behavior when remote acquisition is
  disabled.
- Search queries are expressed in English and rely on the catalog's own
  categorization; human curation of individual results is out of scope for
  v1 (theme matching is query-driven).
- v1 is automatic-only: no UI for browsing, previewing, or hand-picking
  catalog videos; creators influence results solely through style selection.
- Downloaded assets live alongside other runtime media in gitignored cache
  storage, consistent with existing data-dir hygiene rules.
