---
name: Quran Reels Generator
description: Warm emerald and honey gold glass over a deep green night — a calm daily tool for building synced Quran reels.
colors:
  action: "#34d399"
  action-ink: "#052e1f"
  action-deep: "#0a3d27"
  gold: "#e8b64c"
  gold-light: "#f6d47e"
  gold-dark: "#a97e2e"
  canvas: "#0a0f0c"
  surface: "#111915"
  ink: "#f7f4ea"
  ink-secondary: "rgba(247, 244, 234, 0.78)"
  ink-muted: "rgba(247, 244, 234, 0.55)"
  line-glow: "rgba(232, 182, 76, 0.22)"
  line-action: "rgba(52, 211, 153, 0.35)"
  error: "#ff6b6b"
typography:
  display:
    fontFamily: "Amiri, serif"
    fontSize: "3rem"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "1px"
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
    fontSize: "1rem"
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
    textColor: "{colors.action-ink}"
    rounded: "{rounded.md}"
    padding: "16px 20px"
  button-primary-hover:
    backgroundColor: "{colors.action}"
    textColor: "{colors.action-ink}"
    rounded: "{rounded.md}"
    padding: "16px 20px"
  button-secondary:
    backgroundColor: "rgba(52, 211, 153, 0.05)"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "16px 20px"
  input-field:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "15px 20px"
  glass-card:
    backgroundColor: "rgba(17, 25, 21, 0.72)"
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
accents speak: emerald acts, gold glows. Glass surfaces float over a deep
green night with ambient light borrowed from both accents; nothing is sharp,
nothing shouts, and the primary action is always the easiest thing to find.
The old stark gold-on-black coldness is retired and must never return.

**Key Characteristics:**
- Warm emerald action + honey gold brand light on a deep green night
- Frosted glass cards with ambient glow, never flat panels
- Amiri display serif over Cairo body — Quranic voice, everyday readability
- Generous radii (16–32px); pills reserved for small round controls

## Colors

Emerald acts and gold glows; rarity is the point of both.

### Primary
- **Oasis Emerald** (#34d399): the action color — primary buttons, progress,
  counters, checkboxes, focus borders, log highlights, wayfinding icons. Deep
  green ink (#052e1f) sits on it (7.7:1).

### Secondary
- **Honey Gold** (#e8b64c, light #f6d47e, dark #a97e2e): brand light only —
  logo tile and titles, card borders, glows, scrollbar, focus rings. Never
  spends itself on actions anymore.

### Neutral
- **Green Night** (#0a0f0c): canvas; gradients deepen toward #14211a.
- **Palm Surface** (#111915): inputs, counters, card glass base.
- **Warm White** (#f7f4ea): primary text (17.6:1 on canvas).
- **Warm Secondary** (rgba white .78) and **Warm Muted** (rgba white .55):
  labels and hints, both passing AA on the canvas.
- **Glow Line** (rgba gold .22) and **Action Line** (rgba emerald .35): borders.

### Named Rules
**The Two Lights Rule.** Emerald moves things forward; gold marks what matters.
No element wears both jobs, and neither appears where it has no role.

### Token Source
One source: Tailwind `@theme` tokens in `UI.html` (`paper, card, ink, action,
mint, gold, honey, term, foam, sand, golddeep`). `style.css` holds no color
of its own — every value reads `var(--color-*)`, except data-URI literals
(select chevron, dot pattern) which are commented with the token they match.

### Focus System
One indicator: the emerald `focus-visible` ring. Native states stay inside the
system too — checked dropdown options get emerald with white text, autofill
keeps paper fill and ink text, and the video keeps a scoped gold outline.

### Light Theme
Warm paper is the default and only theme: paper canvas (#f4f1e8),
ink text (#1d2b23), deepened action emerald (#0c6e47) and honey gold (#8a5f16)
so every pair still passes AA. Fills keep the bright emerald gradient with
deep-green ink. The build log stays a dark terminal. Implemented with
Tailwind utilities over shared `@theme` tokens; `style.css` keeps only what
utilities cannot express (ambient background, select chevron, keyframes,
state classes, scrollbars).

## Typography

**Display Font:** Amiri (serif fallback)
**Body Font:** Cairo (sans-serif fallback)
**Label/Mono Font:** Cairo semibold for labels; Consolas for the build log

**Character:** Quranic voice up top, plainspoken helper below — Amiri carries
identity in two places only (logo, card title); Cairo does all the work.

### Hierarchy
- **Display** (700, 3rem, 1.2): product name in the header, solid Honey Light.
- **Headline** (700, 2rem, 1.3): card titles, centered, with a short gold rule.
- **Title** (600, 1.1rem): section labels inside the progress card.
- **Body** (400, 1rem, 1.6): form text, hints, buttons; measure stays narrow
  (single centered column, max 900px).
- **Label** (600, 1rem): field labels with a 20px emerald glyph icon.
- **Mono** (400, 0.9rem): build log lines only.

### Named Rules
**The Two Voices Rule.** Amiri names things; Cairo explains them. No third
typeface, no display face outside the header and card titles.

## Layout

One centered column (max 900px), one card per concern: the setup form, then
the status/progress card, then the 9:16 player stage (max 350px wide) with its
toolbar and download. Form fields sit in a two-up grid collapsing to one
column under 768px; groups breathe at 20–30px rhythm with 40px card padding.
RTL throughout: hints and labels right-aligned, select chevrons on the left.

## Elevation & Depth

Layered glass with purposeful glow — depth comes from frosted surfaces lifting
off the night plus a wash of accent light, never from gray steps.

### Shadow Vocabulary (if applicable)
- **Brand glow** (`box-shadow: 0 8px 28px rgba(232, 182, 76, 0.22)`): logo tile,
  gold-focus moments.
- **Action glow** (`box-shadow: 0 10px 30px rgba(52, 211, 153, 0.28)`,
  deepening to 0.45 on hover): primary buttons only.
- **Premium lift** (`box-shadow: 0 20px 50px rgba(0, 0, 0, 0.5)`): glass cards.
- **Inset wash** (`box-shadow: inset 0 2px 5px rgba(0,0,0,0.5)`): progress track.

### Named Rules
**The Light Means Something Rule.** Every glow traces to emerald action or gold
brand light; decorative halos with no role are removed, not toned down.

## Shapes

Softly architectural: cards swell to a generous curve (32px), the player stage
holds 24px, buttons steady at 18px, fields at 16px, the log at 12px. True
pills (999px) belong only to small round tool buttons (play, fullscreen).
Borders are hairlines of glow color, never gray; glass carries an inner top
refraction line (1px warm-white at 9%) so frosted surfaces read as physical.
The logo tile is a rotated square (24px radius) that spins upright on
hover — the single authored motion moment, joined only by the form's
staggered load-in cascade and the progress sheen.

## Components

Warm and confident: soft glass, clear actions, nothing sharp.

### Buttons
- **Shape:** steady curve (18px radius), 16px × 20px padding, bold Cairo.
- **Primary:** emerald gradient fill, deep-green ink text, action glow; lifts
  on hover with a deeper glow.
- **Hover / Focus:** translate up slightly; gold focus ring
  (`outline: 2px solid gold, offset 2px`) for keyboard users.
- **Secondary:** translucent emerald wash with glow border; hover deepens the
  wash and swaps the border to emerald. Disabled buttons fade and wait
  (`cursor: wait`).

### Cards / Containers
- **Corner Style:** generous curve (32px radius).
- **Background:** frosted deep-green glass (`blur(25px)`) with a faint gold
  wash from the top.
- **Shadow Strategy:** premium lift; see Elevation.
- **Border:** 1px glow line.
- **Internal Padding:** 40px (form card), 30px (status card).

### Inputs / Fields
- **Style:** deep-green fill, 16px radius, 2px translucent gold border.
- **Focus:** border turns emerald with a soft emerald halo ring.
- **Error / Disabled:** disabled fields fade to 45% with `not-allowed` cursor;
  errors use the rose banner (translucent red fill, #ff6b6b text).
- **Selects** render through token-styled proxy menus (button + listbox):
  hovered rows take an emerald wash, the chosen row is solid emerald with
  foam text; full keyboard support (arrows/enter/escape). The native select
  stays hidden in the DOM as the value source.
- **Counters** pair emerald steppers with a bold centered value;
  **checkboxes** tint emerald when checked.

### Progress + Player (signature components)
- **Progress:** dark inset track, emerald gradient fill with a traveling sheen
  while building, emerald percentage in extrabold numerals. A pulsing emerald
  dot marks "working" and rests steady on done — motion with a resolved end.
- **Loading:** while a job runs, the player stage shows a 9:16 skeleton with a
  slow emerald shimmer, never a bare spinner.
- **Player stage:** 9:16 framed card (24px radius, glow border) with native
  video; below it a centered toolbar — round tool buttons, speed select, live
  time label — then the download link.
- **Icons:** small glyphs are drawn inline SVG in one stroke family, never
  unicode symbols or emoji.

## Do's and Don'ts

### Do:
- **Do** let emerald own every action and gold own every brand moment
  (The Two Lights Rule).
- **Do** keep Amiri to the logo and card titles; everything else is Cairo.
- **Do** give keyboard focus the gold ring on every interactive element.
- **Do** pair every color-coded state with text or an icon, never color alone.
- **Do** keep body text at 4.5:1 or better — verify computed pairs, not intent.

### Don't:
- **Don't** bring back stark gold-on-black coldness or generic SaaS blue.
- **Don't** use gradient text; emphasis comes from weight or size.
- **Don't** spend the primary emerald on decoration or the gold on buttons.
- **Don't** add a third typeface, a modal, or a nested card to solve a layout.
- **Don't** use unicode glyphs or emoji as icons; draw one SVG stroke family.
- **Don't** ship a new screen that the live panel cannot render from these
  tokens — extend the system instead.
