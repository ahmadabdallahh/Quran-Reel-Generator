---
name: Quran Reels Generator
description: Warm paper and emerald daylight with honey gold brand light — a calm daily tool for building synced Quran reels.
colors:
  action: "#0c6e47"
  action-ink: "#052e1f"
  action-bright: "#34d399"
  action-mint: "#6ee7b7"
  gold: "#8a5f16"
  gold-light: "#e8b64c"
  gold-dark: "#6e4a10"
  canvas: "#f4f1e8"
  canvas-deep: "#e7e1cf"
  surface: "#fffdf6"
  surface-input: "#ffffff"
  track: "#e0d9c2"
  ink: "#1d2b23"
  ink-secondary: "rgba(29, 43, 35, 0.80)"
  ink-muted: "rgba(29, 43, 35, 0.70)"
  line-glow: "rgba(138, 95, 22, 0.30)"
  line-action: "rgba(12, 110, 71, 0.25)"
  terminal: "#060a08"
  foam: "#f7f4ea"
  error: "#a12a1f"
typography:
  display:
    fontFamily: "Amiri, serif"
    fontSize: "3rem"
    fontWeight: 700
    lineHeight: 1.15
    letterSpacing: "0px"
  headline:
    fontFamily: "Amiri, serif"
    fontSize: "2rem"
    fontWeight: 700
    lineHeight: 1.3
  body:
    fontFamily: "Cairo, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontFamily: "Cairo, sans-serif"
    fontSize: "0.95rem"
    fontWeight: 600
    lineHeight: 1.5
  mono:
    fontFamily: "Consolas, monospace"
    fontSize: "0.9rem"
    fontWeight: 400
    lineHeight: 1.5
rounded:
  xs: "12px"
  sm: "16px"
  md: "18px"
  lg: "24px"
  xl: "32px"
  pill: "999px"
spacing:
  xs: "10px"
  sm: "15px"
  md: "20px"
  lg: "30px"
  xl: "40px"
components:
  button-primary:
    backgroundColor: "{colors.action}"
    textColor: "{colors.foam}"
    rounded: "{rounded.md}"
    padding: "16px 20px"
  button-primary-hover:
    backgroundColor: "{colors.action-ink}"
    textColor: "{colors.foam}"
    rounded: "{rounded.md}"
    padding: "16px 20px"
  button-secondary:
    backgroundColor: "rgba(12, 110, 71, 0.05)"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "16px 20px"
  input-field:
    backgroundColor: "{colors.surface-input}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "14px 16px"
  card-surface:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.xl}"
    padding: "40px"
---

# Design System: Quran Reels Generator

## Overview

**Creative North Star: "The Dawn Garden"**

Warm first light over green: a calm, welcoming tool that feels alive rather
than luxurious-cold. The interface is a single-page daily ritual — one form,
one progress card, one player — so the world stays quiet and lets the two
accents speak: emerald acts, gold glows. Warm paper surfaces carry a soft
wash of both accents; nothing is sharp, nothing shouts, and the primary action
is always the easiest thing to find. The old stark gold-on-black coldness is
retired and must never return.

**Key Characteristics:**
- Warm paper daylight with emerald action and honey gold brand light
- Quiet surfaces with hairline gold borders, never gray or glassy panels
- Amiri display serif over Cairo body — Quranic voice, everyday readability
- Generous radii (16–32px); actions stay at 18px
- Grouped form sections, so 15 fields read as three short decisions

## Colors

Emerald acts and gold glows; rarity is the point of both.

### Primary
- **Oasis Emerald** (#0c6e47): the action color — primary button glow, progress,
  counters, checkboxes, focus borders, log highlights, wayfinding icons. The
  primary button is solid emerald with warm foam text (5.7:1), deepening to
  action-ink on hover, so it stays the loudest thing on the page without
  turning into candy.

### Secondary
- **Honey Gold** (#8a5f16, light #e8b64c, dark #6e4a10): brand light only —
  logo tile and titles, card borders, glows, scrollbar. Never spends itself on
  actions.

### Neutral
- **Warm Paper** (#f4f1e8): canvas; gradients deepen toward #e7e1cf.
- **Card Cream** (#fffdf6): cards and the toggle block; inputs sit on white.
- **Ink** (#1d2b23): primary text (13.1:1 on paper).
- **Ink Secondary** (ink at 80%) and **Ink Muted** (ink at 70%): labels and
  hints, both passing AA on paper and card.
- **Glow Line** (gold .30) and **Action Line** (emerald .25): borders.
- **Progress Track** (#e0d9c2) and **Terminal** (#060a08): inert surfaces.

### Named Rules
**The Two Lights Rule.** Emerald moves things forward; gold marks what matters.
No element wears both jobs, and neither appears where it has no role.

### Token Source
One source: Tailwind `@theme static` tokens in `UI.html` (`paper, paperdeep,
card, ink, action, actionink, mint, mintlight, track, gold, honey, term, foam,
sand, golddeep`). `static` matters: Tailwind v4 otherwise emits only the
variables some utility happens to use, and plain-CSS rules such as the slider
rail would resolve `var(--color-sand)` to nothing and drop the declaration.
`style.css` reads tokens for everything utilities cannot express, except for
the two accent aliases (`--accent`, `--accent-ink`) that let range thumbs,
focus halos and scrollbars keep working without depending on theme emission.
Data-URI literals (select chevron, dot pattern) and alpha shadows stay
hardcoded and are commented where they appear.

### Focus System
One indicator: the emerald `focus-visible` ring. Native states stay inside the
system too — checked dropdown options get solid emerald, foam text and a drawn
tick, autofill keeps card fill and ink text, and the video keeps a scoped gold
outline. The custom select proxies use `currentColor` chevrons tied to the
action token and report their state through `aria-expanded`/`aria-selected`.

### Light Theme
Warm paper is the default and only theme: paper canvas (#f4f1e8), cream cards
(#fffdf6), ink text (#1d2b23), action emerald (#0c6e47) and honey gold
(#8a5f16) so every pair passes AA. Primary fills use solid emerald with foam
text; the progress meter is the same solid emerald, with a light sheen while
building. The build log stays a dark terminal. Implemented with Tailwind
utilities over shared `@theme` tokens; `style.css` keeps only what utilities
cannot express (ambient background, logo tile, slider and chevron primitives,
keyframes, player state classes, scrollbars). Large surfaces use near-solid
fills instead of `backdrop-filter`: blur on a scrolling form is a frame-rate
cost with no visual payoff on paper.

## Typography

**Display Font:** Amiri (serif fallback)
**Body Font:** Cairo (sans-serif fallback)
**Label/Mono Font:** Cairo semibold for labels; Consolas for the build log

**Character:** Quranic voice up top, plainspoken helper below — Amiri carries
identity in two places only (logo, card title); Cairo does all the work.

### Hierarchy
- **Display** (700, 3rem, 1.15): product name in the header, solid gold.
- **Headline** (700, 2rem, 1.3): card titles, centered, with a short gold rule.
- **Title** (600, 0.95rem): the four form group titles and the status card title.
- **Body** (400, 1rem, 1.6): form text, hints, buttons; measure stays narrow
  (single centered column, max 900px).
- **Label** (600, 0.95rem): plain Cairo field labels, no per-field glyphs — the
  group title plus the field name is enough orientation.
- **Mono** (400, 0.9rem): build log lines only.

### Named Rules
**The Two Voices Rule.** Amiri names things; Cairo explains them. No third
typeface, no display face outside the header and card titles.

## Layout

One centered column (max 900px), one card per concern: the setup form, then
the status/progress card, then the 9:16 player stage (max 350px wide) with its
native controls and download. The form reads as four labelled groups — content and
recitation, ayah range, visual output, extra options — each introduced by a
small gold title with a hairline rule, so fifteen fields never present as one
wall. Fields sit in a two-up grid collapsing to one column under 768px; groups
breathe at 28px rhythm with 40px card padding. Toggles live in one bordered
block with hairline dividers rather than three floating rows. RTL throughout:
hints and labels right-aligned, select chevrons on the left.

## Elevation & Depth

Layered paper with purposeful glow — depth comes from cream surfaces lifting off
the warm canvas plus a wash of accent light, never from gray steps or dark
shadows.

### Shadow Vocabulary (if applicable)
- **Brand glow** (`box-shadow: 0 10px 26px rgba(138, 95, 22, 0.30)`): logo tile
  and the honey mark.
- **Action glow** (`box-shadow: 0 10px 30px rgba(12, 110, 71, 0.26)`,
  deepening to 0.32 on hover): primary buttons only.
- **Soft lift** (`box-shadow: 0 20px 50px rgba(74, 60, 25, 0.16)`): cards,
  tinted to the warm paper hue, never neutral black.
- **Inset wash** (`box-shadow: inset 0 2px 5px rgba(0, 0, 0, 0.18)`): progress
  track and slider rail.

### Named Rules
**The Light Means Something Rule.** Every glow traces to emerald action or gold
brand light; decorative halos with no role are removed, not toned down.

## Shapes

Softly architectural: cards swell to a generous curve (32px), the player stage
holds 24px, buttons steady at 18px, fields at 16px, the log at 12px. True
pills (999px) are reserved for small round auxiliary controls, never for
primary actions.
Borders are hairlines of glow color, never gray; cards carry an inner top
highlight (1px warm white at 70%) so cream surfaces read as physical. The logo
tile is a rotated square (18px radius, honey-to-gold) that settles upright on
hover — the single authored motion moment, joined only by the form's staggered
load-in cascade and the progress sheen.

## Components

Warm and confident: cream surfaces, one emerald action, nothing sharp.

### Buttons
- **Shape:** steady curve (18px radius), 16px × 20px padding, bold Cairo.
- **Primary:** solid deep emerald fill (#0c6e47), warm foam text, action glow;
  lifts on hover, deepens to action-ink, and presses back on `:active`.
- **Hover / Focus:** translate up slightly; the emerald `focus-visible` ring
  (`ring-4 ring-action/30`) is the only keyboard indicator.
- **Secondary:** translucent emerald wash with an emerald-tinted border; hover
  deepens the wash and the border. Disabled buttons fade and wait
  (`cursor: wait`), and labels keep their drawn icon through a build.

### Cards / Containers
- **Corner Style:** generous curve (32px radius).
- **Background:** near-solid cream (`bg-card/95`) over the ambient paper wash.
  No `backdrop-filter` on scrolling surfaces — blur costs frames and buys
  nothing on an opaque paper canvas.
- **Shadow Strategy:** soft warm lift; see Elevation.
- **Border:** 1px glow line plus a 1px inner warm-white highlight.
- **Internal Padding:** 40px (form card), 30px (status card).

### Inputs / Fields
- **Style:** white fill, 16px radius, 2px translucent gold border; hints sit
  below in ink at 70% (AA on card).
- **Focus:** border turns emerald with a soft emerald halo ring.
- **Error / Disabled:** disabled fields fade to 45% with `not-allowed` cursor;
  failed requests surface as an alert and the button returns to its idle label.
- **Selects** render through token-styled proxy menus (button + listbox):
  the list is opaque white with inset 12px row pills, hovered rows take an
  emerald wash, the chosen row is solid emerald with foam text and a drawn
  tick (state never rests on color alone); full keyboard support
  (arrows/enter/escape), flips above the button when the viewport runs out of
  room, and raises its grid cell so it paints over later fields. The native
  select stays hidden in the DOM as the value source.
- **Counters** pair emerald steppers with a bold centered value and no native
  spinners; **checkboxes** tint emerald when checked and sit in one bordered
  block with hairline dividers.
- **Slider** (reciter speed): 6px rail tinted gold over sand, emerald fill from
  the RTL minimum to the thumb, 22px emerald thumb with a card ring, emerald
  halo on keyboard focus, full-width 28px hit area.

### Progress + Player (signature components)
- **Progress:** sand inset track, solid emerald fill with a traveling sheen
  while building, emerald percentage in extrabold numerals (`aria-hidden`;
  the track carries `role="progressbar"` and live `aria-valuenow`). A pulsing
  emerald dot marks "working" and rests steady on done.
- **Loading:** while a job runs, the player stage shows only a 9:16 skeleton
  with a slow emerald shimmer, never a bare spinner and never a black void.
- **Player stage:** hidden entirely until a real video exists, then a 9:16
  framed card (24px radius, glow border) with native video controls as the one
  playback surface (play, seek, volume, speed, fullscreen) and the download
  button beneath it. No second toolbar duplicating native controls.
- **Icons:** small glyphs are drawn inline SVG in one stroke family, never
  unicode symbols or emoji.

## Do's and Don'ts

### Do:
- **Do** let emerald own every action and gold own every brand moment
  (The Two Lights Rule).
- **Do** keep Amiri to the logo and card titles; everything else is Cairo.
- **Do** give keyboard focus the emerald ring on every interactive element.
- **Do** pair every color-coded state with text or an icon, never color alone.
- **Do** keep body text at 4.5:1 or better — verify computed pairs, not intent.

### Don't:
- **Don't** bring back stark gold-on-black coldness or generic SaaS blue.
- **Don't** use gradient text; emphasis comes from weight or size.
- **Don't** spend the primary emerald on decoration or the gold on buttons.
- **Don't** add a third typeface, a modal, or a nested card to solve a layout.
- **Don't** use unicode glyphs or emoji as icons; draw one SVG stroke family.
- **Don't** animate decoration forever; every motion answers a state change.
- **Don't** ship a new screen that the live panel cannot render from these
  tokens — extend the system instead.
