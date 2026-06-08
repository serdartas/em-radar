# ADR-0004: UI component library — Tailwind CSS + shadcn/ui

- **Status:** Accepted
- **Date:** 2026-06-01
- **Deciders:** Serdar Tas
- **Related:** [04-tech-stack.md](../04-tech-stack.md), [ADR-0003](./0003-frontend-framework.md)

## Context

EM Radar's UI should look consistent and modern without us designing components from scratch. We want:

- **Accessibility out of the box.** EMs and their orgs will judge an OSS tool by basic a11y signals.
- **No vendor lock-in.** We should own the component code, not rent it.
- **Low CSS maintenance.** No bespoke CSS architecture.
- **Free, open source, modern but not hype.**

## Decision

Use **Tailwind CSS** for styling and **shadcn/ui** for components.

shadcn/ui is not a traditional npm component library. It's a CLI that copies accessible React components (built on Radix UI primitives + Tailwind) directly into our repository. We own and edit the code.

## Alternatives considered

### Material UI (MUI)
- **Strengths:** Comprehensive, mature, well-known.
- **Weaknesses:** Opinionated Google Material visual style we'd fight with. Runtime CSS-in-JS overhead (Emotion). Heavy bundle. Component customization is verbose. Vendor coupling. If MUI changes direction, we change with it.
- **Verdict:** Wrong aesthetic, heavyweight, locks us in.

### Chakra UI
- **Strengths:** Pleasant API, good DX.
- **Weaknesses:** Core team has slowed development; uncertain future. Runtime style system overhead.
- **Verdict:** Risk too high for an OSS project with a long horizon.

### Mantine
- **Strengths:** Comprehensive, actively developed, nice DX.
- **Weaknesses:** Smaller community than MUI or shadcn/ui. Vendor coupling like MUI.
- **Verdict:** Solid but smaller orbit.

### Bootstrap / Bootstrap-React
- **Strengths:** Universally known.
- **Weaknesses:** Visually dated; opinionated CSS.
- **Verdict:** No.

### Tailwind CSS + shadcn/ui
- **Strengths:**
  - Components copied into our repo. We own the code, no upgrade-induced breakage.
  - Built on Radix UI primitives → accessibility baked in (keyboard nav, ARIA, focus management).
  - No runtime CSS-in-JS. Just Tailwind utility classes, smaller bundles.
  - Industry standard combo as of 2026. Broad contributor familiarity.
  - Easy to customize. It's our code.
- **Weaknesses:**
  - Components are not auto-updated; we must consciously sync when shadcn/ui ships an improvement.
  - Tailwind utility-class style takes a moment for new contributors to learn (well-documented).

## Consequences

### Positive
- No "the library changed and broke our UI" surprises. We own the components.
- Accessibility primitives (Radix) we don't have to re-implement.
- Small bundles, no CSS-in-JS runtime.
- Easy to brand/theme later (Tailwind tokens).

### Negative
- We're responsible for keeping our copied components reasonably up to date with upstream improvements.
- A non-trivial component (data table with sort/filter/pagination) is still work. shadcn/ui gives primitives, not pre-built apps.

## Revisit when

- We need a full enterprise dashboard kit with charts/tables/forms out of the box (revisit with a chart-specific library like Recharts/Tremor, not by abandoning shadcn).
- Radix UI is abandoned (no signs of this).
