# Feature Specification: Ayah Text Sync

**Feature Branch**: `002-ayah-text-sync`

**Created**: 2026-08-22

**Status**: Draft

**Input**: User description: "Render the text of the ayah currently being recited, synchronized with the recitation audio over the background video (read-along display)."

## Clarifications

### Session 2026-08-22

- Q: Should segments display an ayah reference label (e.g., "Surah Name S:A") alongside the verse text? → A: No — v1 renders verse text only; a reference sticker remains a separate future increment.
- Q: How is Bismillah-as-ayah-1 handled when generating Al-Fatihah from ayah 1? → A: Rendered like any other ayah (full segment text); the intro card stays suppressed via the existing skip list for such surahs.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Read along with the recitation (Priority: P1)

A viewer watching a generated reel sees the complete Arabic text of the ayah
currently being recited displayed on screen for the full duration of that
ayah's audio. As each new ayah begins, its text replaces the previous one in
sync with the audio — the viewer can read along without guessing which verse
is playing.

**Why this priority**: This is the core product intent ("render the ayah
text while the person speaks"). Without correct synced full-ayah display,
nothing else in this feature has value.

**Independent Test**: Can be fully tested by generating a multi-ayah reel
with text enabled and verifying each segment shows exactly the text of the
ayah whose audio is playing, entering/exiting at segment boundaries.

**Acceptance Scenarios**:

1. **Given** a 5-ayah reel is generated with text display enabled,
   **When** any segment plays, **Then** the on-screen text shows the
   complete Arabic text of that segment's ayah and nothing else.
2. **Given** a segment boundary between ayah N and N+1, **When** ayah N+1's
   audio starts, **Then** its text is visible within a short tolerance of the
   audio start and the previous ayah's text is gone.
3. **Given** the reel is paused on any frame mid-segment, **When** the frame
   is inspected, **Then** the visible words belong to that segment's ayah
   only (no mixing of two verses' text).

---

### User Story 2 - Text that is always readable (Priority: P2)

A viewer on a phone, watching against bright or busy backgrounds (sky,
water, architecture), can comfortably read the ayah text. The text uses a
legible size, a contrast treatment behind or around it, and an appearance
that follows the reel's selected template theme so it feels designed rather
than pasted on. Appearance stays consistent across all segments of one reel.

**Why this priority**: Correct but unreadable text fails the user; styling
is what makes the feature usable across all four template styles and varied
backgrounds.

**Independent Test**: Can be tested by generating reels per template style
over bright/dark/busy backgrounds and confirming readability and consistent
themed appearance throughout each reel.

**Acceptance Scenarios**:

1. **Given** a reel with a bright daylight nature background, **When** text
   is displayed, **Then** a contrast treatment ensures the glyphs remain
   clearly distinguishable from the background.
2. **Given** reels generated with each template theme, **When** compared,
   **Then** each reel's text appearance matches its theme and does not
   change style between segments within the same reel.
3. **Given** the output viewed at phone size, **When** text is displayed,
   **Then** it is large enough to read without zooming.

---

### User Story 3 - Word-level read-along highlighting (Priority: P3)

As the reciter pronounces each word, the corresponding word in the displayed
text is visually emphasized (e.g., highlighted), progressing through the
verse. This gives a guided, karaoke-like reading experience.

**Why this priority**: High perceived value but dependent on word-timing
information that may not be authoritatively available; it must never
compromise the correctness guarantees of Stories 1–2, so it ships after them
and may use best-effort timing.

**Independent Test**: Can be tested by playing a single-ayah reel with
highlighting enabled and observing emphasis progress through the words in
rough correspondence with the audio.

**Acceptance Scenarios**:

1. **Given** highlighting enabled, **When** an ayah's audio plays,
   **Then** emphasis advances through the verse's words in order without
   ever skipping backwards or jumping ahead grossly out of sync.
2. **Given** no reliable timing information exists for a reciter/track,
   **When** the reel is generated, **Then** the system degrades gracefully
   to plain full-ayah display (Story 1 behavior) rather than showing wrong
   emphasis.

---

### Edge Cases

- What happens when the ayah text cannot be fetched? Generation MUST fail
  loudly for that reel (clear error surfaced in progress/log) when text is
  enabled — silent textless output MUST NOT be produced under the guise of
  success. Only an explicit user toggle produces text-free reels.
- How are very long ayahs handled (e.g., the longest verses)? The complete
  text wraps across multiple lines within the frame; nothing is truncated,
  shrunk into illegibility, or pushed off-screen.
- What is displayed during the Bismillah intro card? No rendered verse text
  — existing intro visuals only; the first ayah's text must not appear
  before its audio starts. Where the recited ayah IS the Bismillah
  (Al-Fatihah ayah 1, with the intro already suppressed for such surahs),
  it renders as normal segment text (see Clarifications).
- What about diacritics and letter shaping across unusual verses? All 114
  surahs' orthography renders correctly (connected script, marks positioned)
  — sampled verification across surah variety is part of validation.
- What if the user disables text? Output must match today's audio +
  background-only pipeline exactly; the toggle is intentional, not a failure
  path.
- What if backgrounds are extremely dark or extremely bright? The contrast
  treatment adapts (or is guaranteed by design) so text remains readable on
  both extremes.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST display the complete Arabic text of the ayah
  currently being recited, for the full duration of that ayah's audio
  segment, when text display is enabled. Display is limited to the verse
  text itself — no reference label or sticker in v1 (see Clarifications).
- **FR-002**: Displayed text MUST exactly match authoritative Quranic text
  obtained from the project's vetted text source — no paraphrasing,
  abbreviation, or reordering of words.
- **FR-003**: Text transitions MUST align with segment boundaries: each
  ayah's text appears at (or within a small bounded tolerance of) its audio
  start and disappears at its end; adjacent verses' text MUST NOT overlap
  on screen beyond that tolerance.
- **FR-004**: Rendered text MUST be legible: sufficient contrast against the
  background (via treatment such as backing, shadow, or adaptive styling)
  and a minimum readable size on vertical mobile-format output.
- **FR-005**: Arabic script MUST render correctly: right-to-left order,
  connected letterforms, and diacritical marks positioned accurately for
  every ayah.
- **FR-006**: Long ayahs MUST wrap across multiple lines inside the frame;
  no truncation, clipping, or shrinking below the legibility minimum.
- **FR-007**: The Bismillah/intro segment MUST carry no rendered verse text
  (existing intro visuals unchanged); the first ayah's text MUST NOT appear
  before its audio starts. Where the recited ayah IS the Bismillah
  (Al-Fatihah ayah 1), it is treated like any other ayah — full segment
  text — while the intro card remains suppressed by the existing skip list
  for such surahs.
- **FR-008**: Users MUST be able to disable text display via configuration;
  disabled mode MUST reproduce the existing audio + background-only output.
- **FR-009**: Text appearance (position, colors, treatment) MUST follow the
  selected template theme and remain consistent across all segments of a
  single reel.
- **FR-010**: When text is enabled, a failed text fetch MUST surface a clear
  error through the progress/log channel and fail the affected generation —
  the system MUST NOT silently deliver a textless reel as if successful.
- **FR-011**: Word-level highlighting (when enabled) MUST advance strictly
  forward through the verse's words in recitation order; where reliable
  timings are unavailable, the system MUST fall back to plain full-ayah
  display instead of incorrect emphasis.
- **FR-012**: Text rendering MUST NOT unreasonably slow generation compared
  with the current textless pipeline.

### Key Entities *(include if feature involves data)*

- **AyahText**: The authoritative Arabic text of one ayah — referenced by
  surah and ayah number; includes full orthography with diacritics; may
  include optional word-boundary/timing hints for Story 3.
- **TextStyleProfile**: Per-template visual definition of how ayah text is
  presented — placement zone, sizing rules relative to frame, colors and
  contrast treatment, line-wrap limits.
- **SegmentTimingMap**: The mapping of each output segment to its ayah and
  audio window, used to guarantee text/audio alignment at boundaries.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In generated reels with text enabled, 100% of segments display
  the correct complete text of their recited ayah (verified against the
  source text).
- **SC-002**: Text appears within half a second of its segment's audio start
  and zero cross-segment text overlap is detectable in sampled reels.
- **SC-003**: Text passes a readability bar in all samples: contrast ratio of
  at least 4.5:1 against its immediate backdrop and height of at least ~5%
  of frame width, readable on a phone at arm's length.
- **SC-004**: Across sampled reels spanning many surahs, zero instances of
  broken letter shaping, misplaced diacritics, or truncated/wrapped-off
  text.
- **SC-005**: With text disabled, output is indistinguishable from the
  pre-feature audio + background pipeline for identical settings.
- **SC-006**: Enabling text increases total generation time by no more than
  20% versus the same settings without text.
- **SC-007**: A deliberate text-fetch failure produces a visible error state
  (progress log) in 100% of forced-failure tests — never a "successful"
  textless reel.

## Assumptions

- Arabic-only display for v1; translations/transliterations are explicitly
  out of scope.
- Full-ayah display is the v1 baseline; word-level highlighting is a
  progressive enhancement (Story 3) permitted to use best-effort proportional
  timing when authoritative word timings are unavailable.
- The project continues to obtain Quranic text from its existing vetted text
  source; no new content sources are introduced by this feature.
- Fonts/typography capable of full Quranic orthography (with tashkeel) will
  be made available to the rendering path; exact font selection is a planning
  decision, not a spec constraint.
- The existing per-segment build model (one ayah = one timed segment)
  remains the foundation; this feature layers text onto it rather than
  restructuring timing.
- Historical implementations exist in legacy reference code and design notes
  (`old_main.py`, docs/animations.md); they inform feasibility but do not
  constrain the new implementation.
