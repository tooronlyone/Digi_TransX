---
name: Digi_TransX Driver Portal
description: A light mobility-concourse system for fast, trustworthy driver operations.
colors:
  concourse-bg: "#f4f7fb"
  surface: "#ffffff"
  surface-soft: "#f8faff"
  surface-blue: "#eef4ff"
  ink: "#10213b"
  copy: "#465a76"
  muted: "#556981"
  line: "#dce5f0"
  line-strong: "#c9d6e6"
  cobalt: "#235ed7"
  cobalt-dark: "#1848ac"
  cobalt-soft: "#dce9ff"
  amber: "#d97706"
  amber-soft: "#fff5dc"
  green: "#14815b"
  green-soft: "#e8f7f0"
  red: "#c53d4a"
  red-soft: "#fff0f1"
typography:
  display:
    fontFamily: "Inter, Segoe UI, sans-serif"
    fontSize: "2.05rem"
    fontWeight: 790
    lineHeight: 1.14
    letterSpacing: "-0.025em"
  title:
    fontFamily: "Inter, Segoe UI, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 770
    lineHeight: 1.2
    letterSpacing: "-0.015em"
  body:
    fontFamily: "Inter, Segoe UI, sans-serif"
    fontSize: "0.86rem"
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontFamily: "Inter, Segoe UI, sans-serif"
    fontSize: "0.68rem"
    fontWeight: 750
    lineHeight: 1.2
    letterSpacing: "0.1em"
rounded:
  control: "11px"
  compact: "12px"
  panel: "14px"
  card: "16px"
  pill: "999px"
spacing:
  xs: "5px"
  sm: "8px"
  md: "12px"
  control: "16px"
  section: "20px"
  card: "24px"
  gutter: "34px"
components:
  button-primary:
    backgroundColor: "{colors.cobalt}"
    textColor: "{colors.surface}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "0 16px"
    height: "42px"
  button-primary-hover:
    backgroundColor: "{colors.cobalt-dark}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.cobalt-dark}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "0 16px"
    height: "42px"
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.card}"
    padding: "24px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "10px 12px"
    height: "44px"
---

# Design System: Digi_TransX Driver Portal

## Overview

**Creative North Star: "The Mobility Concourse"**

The driver portal is a cool-white operational workspace shaped by transport wayfinding: fixed navigation, clear destinations, route lines, durable status colour, and a strong next-action hierarchy. It feels refined but never ornamental; the driver's current assignment and recovery path outrank decoration.

The system is flat and factual. It uses borders, tonal surfaces, restrained shadows, and a faint highway image only in the welcome context. It does not use gradients, glass panels, neon effects, or dark-theme styling.

**Key Characteristics:**
- Cool-white surfaces over a pale blue-grey concourse.
- Cobalt wayfinding with amber attention, green success, and red failure states.
- Route pins and a continuous dashed path as the signature journey motif.
- Priority-weighted metrics, compact labels, tabular numerals, and explicit fallbacks.
- Desktop and mobile are equally complete operating environments.

## Colors

The palette separates navigation, attention, success, and failure without turning every surface into a status card.

### Primary
- **Wayfinding Cobalt:** Primary actions, active navigation, links, focus, route origins, and in-progress states.
- **Deep Cobalt:** Hovered actions and high-emphasis cobalt text.

### Secondary
- **Safety Amber:** Assigned, pending, offered, reserve, rating, and attention states; never a general decoration colour.
- **Verified Green:** Completed, accepted, active, safe, and verified states.
- **Incident Red:** Failed, rejected, cancelled, destructive, and recovery states.

### Neutral
- **Concourse Background:** The page field behind operational surfaces.
- **Cool White:** Primary panels, cards, controls, and the sticky header.
- **Freight Ink:** Primary copy and numeric values.
- **Operational Copy / Muted:** Explanations, metadata, and secondary labels.
- **Cool Line / Strong Line:** Structure panels, tables, controls, and grouped metrics.

**The Semantic Signal Rule.** Amber, green, and red always communicate operational meaning and retain a text label; colour never carries status alone.

**The No Atmospheric Effects Rule.** Do not introduce gradients or translucent glass surfaces. Tonal fills and borders provide structure.

## Typography

**Display Font:** Inter (with Segoe UI and sans-serif fallback)  
**Body Font:** Inter (with Segoe UI and sans-serif fallback)

**Character:** A compact, modern sans-serif hierarchy optimised for scanning under time pressure. Weight, size, and spacing establish order without a decorative display face.

### Hierarchy
- **Display** (790, 2.05rem, 1.14): Welcome and high-level operational context; scales to 1.55rem on mobile.
- **Title** (770, 1.25rem, 1.2): Page and card titles.
- **Section title** (760, 0.96rem): Dispatch, quick-access, and grouped controls.
- **Body** (400, 0.86rem, 1.6): Explanations; keep long supporting copy near 74ch or less.
- **Metric** (790, 1.5rem): Values use tabular numerals; wallet and reputation totals may scale to 2–2.2rem.
- **Label** (750, 0.68rem, 0.1em): Short uppercase navigation and credential labels only.

**The Scan-First Rule.** Keep operational nouns and values visually dominant; explanations are smaller and quieter, never vague substitutes for missing data.

## Layout

Desktop uses a fixed 272px navigation rail, a sticky 76px header, and a centered workspace capped at 1540px with 34px gutters. The dashboard leads with one contextual welcome panel, then a grouped metric strip, then a 1.6:0.7 dispatch/quick-action grid. This unequal weighting makes assignment and dispatch information visibly primary.

Spacing follows a compact 4–5px-derived rhythm: 5–12px inside labels and icon groups, 14–16px in controls and rows, 20px between modules, and 24–34px for card and page padding. Avoid grids of equally prominent cards when a strip, list, or master/detail hierarchy communicates priority better.

At 1180px the rail narrows to 238px, gutters become 24px, and metrics form two columns. At 900px navigation becomes a 286px off-canvas drawer and operational grids collapse. At 680px gutters become 15–16px, the route illustration is removed, actions become full width, metrics stack, dispatch values wrap below their row label, and tables become bordered record blocks with hidden headers.

## Elevation & Depth

The system is flat by default. Cool borders and tonal blue surfaces carry most grouping; shadows are reserved for active cobalt icons, primary actions, route pins, and the mobile drawer.

### Shadow Vocabulary
- **Cobalt action:** `0 9px 20px rgba(35, 94, 215, 0.2)` for the primary button.
- **Cobalt marker:** `0 9px 18px rgba(35, 94, 215, 0.2)` for identity and active-navigation markers.
- **Route pin:** `0 12px 28px rgba(40, 73, 119, 0.14)` for map-like stops.
- **Drawer:** `18px 0 50px rgba(18, 41, 73, 0.14)` only while mobile navigation is open.

**The Flat-by-Default Rule.** Resting cards and data surfaces use a 1px cool border, not a shadow. Elevation indicates action, wayfinding, or temporary overlay state.

## Shapes

Controls use gently curved 10–12px corners; compact panels use 13–15px; major cards and grouped strips use 16px. Pills are reserved for IDs, roles, and statuses. Icon tiles are compact rounded squares, while circular dots mark live journey state. Borders remain thin and cool; route geometry is the only deliberately directional shape.

## Components

### Buttons
- **Primary:** Cobalt fill, white text, 42px minimum height, 11px radius, and restrained cobalt shadow.
- **Secondary:** Cool-white fill, cobalt text, and a visible cool border.
- **Hover / Focus / Disabled:** Hover lifts 1px and deepens the fill; focus uses a visible 3px cobalt ring with 3px offset; disabled controls preserve their label at reduced opacity and use the correct wait or not-allowed cursor.

### Status Chips
- **Style:** Compact pill with semantic soft fill, dark readable text, and a written status label.
- **Mapping:** Green = accepted/completed/active; amber = requested/pending/offered; cobalt = in progress; red = rejected/cancelled/failed; neutral = unknown.

### Cards / Containers
- **Corner Style:** 16px for major cards; 14px for nested groups.
- **Background:** Cool white or a documented soft semantic surface.
- **Border / Padding:** 1px cool border and 20–24px internal padding; flush list cards keep headings and rows separated by lines.
- **Hierarchy:** Prefer grouped metric strips and list rows to repeated floating cards.

### Inputs / Fields
- **Style:** White, 44px minimum height, 11px radius, strong cool border, inherited type.
- **Focus:** Cobalt border with a 3px low-opacity cobalt ring.
- **Error / Disabled:** Pair semantic colour with explicit text; never clear or replace the user's factual input silently.

### Navigation
- **Desktop:** Fixed light rail with 48px links, rounded icon tiles, and a cobalt active state marked by `aria-current`.
- **Mobile:** Off-canvas drawer with labeled open/close controls and a dismissible scrim; the page returns to full-width content.

### Journey Route
- **Style:** White start/end pins connected by a dashed cobalt path and amber progress marker.
- **Data:** Prefer active-trip pickup and destination; otherwise show the saved base city and the literal fallback “Awaiting assignment.” Hide the decorative route on narrow mobile screens, but retain textual assignment context.

### Loading, Empty, and Error States
- **Loading:** Skeleton surfaces mirror the hero and metric structure and expose `aria-busy`.
- **Empty:** Explain what is absent and the next real action, including the factual driver ID when available.
- **Error:** Use a red semantic state, a plain-language recovery message, `role="alert"`, and an explicit retry action.

## Do's and Don'ts

### Do:
- **Do** put current assignment, route, status, money, and the next driver action before supporting content.
- **Do** preserve factual fallbacks: `0` for verified counts, an em dash plus “Awaiting first review” for unrated trust, “Base city not set” or “not available” for missing profile facts, and “Ready for dispatch” / “Awaiting assignment” when no trip exists.
- **Do** keep status meaning in both colour and text, numeric columns tabular, focus visible, and reduced-motion support enabled.
- **Do** use real driver, trip, vehicle, transporter, wallet, and reputation data; keep currency and local transport language faithful to the product.

### Don't:
- **Don't** invent assignments, ratings, reviews, locations, credentials, vehicles, earnings, testimonials, or performance claims to fill an empty state.
- **Don't** use gradients, glass panels, dark themes, neon accents, flashing status animation, or imagery behind dense data and controls.
- **Don't** give every metric equal visual weight or replace an operational list with decorative cards.
- **Don't** hide primary actions on mobile or rely on hover, motion, icons, or colour as the only source of meaning.
