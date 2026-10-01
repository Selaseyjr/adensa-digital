# Adensa Visual Identity / Design System v1

Status: **v1 — implemented** (this phase). Applies to the Next.js client (`web/`).

Adensa Digital is the digital operations layer for supply-chain managers.
The experience metaphor is **cockpit + mission control**: the manager should
feel informed, clear-headed, supported, in control — never overwhelmed.
AI is advisory; the human manager remains responsible for decisions.

The identity territory follows the name (Akan: *continuous daylight, "it's
never night"*):

> Light → Visibility → Awareness → Readiness → Action → Resilience

Established as a product concept in 2026.

---

## 1. Design principles

1. **Information before decoration.** No visual element exists without a
   functional reason.
2. **Operational state before generic metrics.** Surfaces answer "what does
   the operation need from me now", not "look at these numbers".
3. **Clarity before density.** Density is earned through typography and
   rhythm, never through compression.
4. **Evidence before recommendation.** Rationale is promoted; scores are
   context.
5. **Human decision-making remains visible.** Approvals, rejections and
   manual interventions are first-class, styled surfaces.
6. **Motion communicates meaning.** Two durations, no decoration.
7. **Critical information gets visual priority.** Rails, chips and the
   attention signal — always subtle, never a flash.
8. **Brand colour does not replace semantic status colour.** The Adensa
   blues identify the product; success/warning/critical report state.
9. **Every major visual element has a functional reason.** If a rail, tint
   or gradient cannot explain itself, it is removed.
10. **Continuously aware, never noisy.** The interface feels alive through
    truthful data and restraint, not through animation.

## 2. Colour system

Tokens live in `web/app/globals.css` (`:root`), consumed nowhere else as
literals. Brand hues are named once and aliased to the functional tokens
components actually use.

### Brand palette

| Token | Value | Role |
| --- | --- | --- |
| `--adensa-navy` | `#0b1f33` | Deep Adensa navy — the command ground |
| `--adensa-navy-raised` | `#0e2740` | Raised navy surface (deck tiles) |
| `--adensa-blue` | `#0f4c81` | Primary Adensa blue (accent) |
| `--adensa-blue-strong` | `#1d6fb8` | Strong accent (non-text emphasis, primary series) |
| `--adensa-blue-deep` | `#0b3a63` | Deep accent (emphasis on light) |
| `--adensa-blue-soft` | `#85b8e8` | The accent on dark chrome |
| `--adensa-cyan` | `#2ea8c9` | Secondary technology accent — data-viz secondary series only |
| `--adensa-day` | `#f2f6fa` | The light accent on navy |

### Neutral system (light workspace)

`--bg` (application ground) · `--surface` (primary/elevated) ·
`--surface-subtle` (secondary) · `--surface-sunken` (sunken) ·
`--border` / `--border-strong` (dividers) · `--text` / `--text-secondary` /
`--text-tertiary` / `--text-muted` (ramp) · `--text-metadata` (metadata).

### Semantic system (deliberately separate from the brand)

`--semantic-success` / `--semantic-warning` / `--semantic-critical` /
`--semantic-neutral` / `--semantic-info` (+ `--semantic-info-tint`),
aliasing the audited `--ok` / `--warning` / `--critical` values. Semantic
colour communicates operational state only — never decoration, never brand
identity. Chip text remains the accessible semantic carrier; dots and rails
are reinforcement.

### Light and Dark Command Centre

Two expressions of one brand — never an inversion. Light is the calm
operational workspace; dark re-lights the same navy/blue family on deep
navy ground (`--bg #0b1f33`, surfaces `#12293f`/`#0e2238`, borders
`#1e3a52`/`#2d4e6b`, lifted accent family, on-dark semantic hues,
`--row-hover #16324b`). The P12.2 shell tokens (`--shell-*`) alias the same
values, so header, footer, command deck and the dark theme are one system.

Activation: `[data-theme="dark"]` on `<html>`, set before first paint by
the init script in `app/layout.tsx`; the toggle is
`web/components/ThemeToggle.tsx`; persistence is `localStorage["adensa-theme"]`
(falls back to light; no `prefers-color-scheme` inference). Components need
no dark variants — they style from tokens; only light-native *property
choices* (solid halos, `#ffffff` inks, gradient starts) are re-expressed in
the `[data-theme="dark"]` remap block of `globals.css`.

## 3. Typography

Inter via `next/font` (`--font-inter`), exposed as `--font-ui`. Weights
stay within 400/600/700 — the system never needs more; page titles are 24px
and never larger in normal flow (the deck title steps to its clamped size
once, as the Control Tower's identity moment).

| Role | Token / class | Notes |
| --- | --- | --- |
| Product identity | `.app-brand-name` | Header lockup beside the mark |
| Page title | `--text-page` (24px) / `.page-title` | −0.01em |
| Section title | `--text-section` (17px) / `.section-title` | |
| Body | `--text-body` (15px) | |
| Metadata | `--text-metadata` (13px) / `.text-metadata` | Timestamps, intro lines |
| Fine print | `--text-note` (11.5px) / `.text-note` | |
| KPI values | `--text-metric` / `.metric-value`, `.deck-metric-value` | Tabular, −0.01em |
| **Operational identifiers** | `.op-id` primitive; `.queue-link`, `.data-table td:first-child`, `.workspace-header-meta` | `tabular-nums` + `--tracking-op-id` (0.02em), weight 600. EXC-/SHP-/OPT- read as technical data |
| Timestamps | `.history-timestamp`, `.text-metadata` | Tabular |
| Status labels | `.chip` family | Text is the semantic source |
| Analytical values | `.text-value`, `.chart-axis-label` (tabular) | |

## 4. Spacing, layout, control tokens

| Token | Value |
| --- | --- |
| `--space-1..8` (+`--space-10/12`) | 4px base scale |
| `--radius-sm` / `--radius` / `--radius-full` | 6 / 8 / 999px — full is for chips, dots and the mark only, never cards |
| `--control-height` | 36px |
| `--pad-panel-x` / `--pad-panel-y` | 24 / 20px — one panel padding |
| `--section-gap` | 20px |
| `--layout-max` | 1180px content column |
| Breakpoints | 1024 / 900 / 720 / 640 / 560px — restrained enterprise tiers |

Shadows stop at `--shadow-2`; dark mode carries depth with borders instead
(`--shadow-1: none`). Nothing is more rounded than `--radius` on cards.

## 5. Iconography

One inline-SVG system, stroke-based: 1.5px weight, round caps/joins,
`currentColor`, 24px optical grid scaled by `em`. The `.icon` primitive in
`globals.css` defines the style; `aria-hidden` unless the icon is the only
content. No decorative logistics icons (truck/globe/package/container/
arrow/sparkle). Current vocabulary: the brand mark and its horizon
geometry; add future icons as stroke paths in the same style, never as
fill glyphs from icon packs.

## 6. Logo / brand mark

`web/components/brand/BrandMark.tsx` is the single home of the mark:

- Concept: **A + light + continuity** — an open triangular apex (daylight
  breaking, the A) over three horizon lines of descending weight
  (continuous day; equally readable as flow lines / a network pathway).
- `BrandMark` inherits `currentColor` for header/footer lockups;
  `AdensaMarkIcon` is the self-contained navy-tile compact form.
- The mark is **replaceable by design**: all geometry lives inside the two
  `<svg>` blocks of that one component; no SVG is scattered through the app.
- Favicon: `web/app/icon.svg` is the tracked source of truth;
  `web/app/favicon.ico` (16+32) is generated from the same geometry via
  `data/gen_favicon.py` (Pillow; `data/` is gitignored).

## 7. Data visualization identity

Charts are hand-built SVG (`control-tower/LineChart.tsx`, `BarChart.tsx`,
`QueueCompositionBand.tsx`) and remain dependency-free; v1 binds them to
the data-viz token row:

`--chart-bg` / `--chart-plot-bg` (panel ground) · `--chart-grid` (dotted)
/ `--chart-grid-base` (solid baseline) · `--chart-axis` ·
`--chart-series-primary` (Adensa accent) · `--chart-series-secondary`
(the cyan tech accent — the one place it appears) ·
`--chart-series-critical` / `--chart-series-positive` (semantic) ·
`--chart-tooltip-bg/text` (navy plate, day text) · `--chart-empty`.

Rules: no gradients, no 3D, no decorative elements; gridlines recede, the
baseline reads as an axis; values are tabular; every chart keeps its
visually-hidden data-table fallback; empty and loading states reuse the
calm `state-panel` language with the metadata voice.

## 8. Motion

Two durations, two easings — nothing else ships:

- `--dur-fast` 150ms `--ease-standard`: state changes, hover/focus.
- `--dur-reveal` 200ms `--ease-departure`: one-shot reveals (charts, bands).

`prefers-reduced-motion` remains the global guard (skeletons degrade to
static blocks; the chart readout snaps). v1 adds the explicit
`[data-motion="reduced"]` attribute hook with identical neutralization for
testing and future in-app opt-out. `.attention-critical` is the one
attention signal — a quiet 2s/2-iteration critical halo for genuinely
critical events; numbers may animate on viewport entry in future phases
within the same tokens.

## 9. Voice / UI copy

Calm, informed, concise, evidence-based, human. Lead with the observation,
then the evidence, then the options — e.g. "I noticed a problem with
SHP-001529. I've checked the available recovery options and found three
possible ways forward." Never: "Oops!", "AI magic", "Let's fix this!",
exclamation-mark hype, or personified urgency. The audit found the existing
copy already conforms (state panels read "Operational data unavailable",
not errors thrown at the user); this section codifies it as a standard for
future UI work. Theme vocabulary follows the same rule: the toggle offers
the "Command Centre", never "dark mode".

## 10. Maintenance rules

- New UI consumes tokens; no literal colour/spacing/motion values in
  components.
- The mark's SVG lives only in `BrandMark.tsx`; the favicon geometry only
  in `icon.svg`/`gen_favicon.py`.
- Preserve the shell contracts: `app-brand-name`/`app-brand-sub` text, the
  P12.5 severity rails/stages, `.inbox-result-count`,
  `.history-list .history-entry`.
- Both themes and reduced motion are part of "done" for any visual change.
