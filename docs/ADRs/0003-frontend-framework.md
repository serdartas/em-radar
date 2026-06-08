# ADR-0003: Frontend framework — React + Vite

- **Status:** Accepted
- **Date:** 2026-06-01
- **Deciders:** Serdar Tas
- **Related:** [04-tech-stack.md](../04-tech-stack.md), [ADR-0004](./0004-ui-component-library.md)

## Context

EM Radar needs a browser UI for ~6 MVP pages (setup, source connections, signal settings, report runner, report results, settings/privacy). The UI is served locally from the same Docker container as the backend.

Constraints:

- **Open-source contribution magnet.** We want the broadest possible contributor pool.
- **Non-coding EM friendly.** The UI exists so EMs don't have to edit YAML in containers (REQ-NF-050).
- **Low maintenance.** Minimal toolchain churn, fewest moving parts that still feel current.
- **Free, modern but not hype.** No framework that will look dated or abandoned in two years.

## Decision

Use **React** as the UI library and **Vite** as the build tool / dev server.

## Alternatives considered

### HTMX + Jinja2 (server-rendered)
- **Strengths:** Dramatically less to maintain. No Node toolchain, no JS bundler, no npm audit churn. Single backend stack. Faster initial page loads. Lower bundle size.
- **Weaknesses:** Much smaller contributor pool (most frontend devs work in React/Vue). Less "modern" feel for EMs evaluating the project on the README screenshot. Interactive features (drag-to-reorder signals, complex form state, real-time refresh) become harder.
- **Verdict:** Genuinely tempting for maintenance reasons, but loses on contributor reach and first-impression polish, both of which matter for an OSS project trying to build a community.

### Vue + Vite
- **Strengths:** Cleaner API than React for many cases, very capable, Vite is its native build tool.
- **Weaknesses:** Smaller contributor pool than React. Less ubiquitous in EM tooling.
- **Verdict:** Fine technically, weaker community-fit.

### SvelteKit
- **Strengths:** Excellent DX, smaller bundles, less boilerplate.
- **Weaknesses:** Smaller community again. More opinionated framework (SvelteKit). Risk of "where did this tool go in five years?" higher than React.
- **Verdict:** Too far from the safe path.

### Next.js
- **Strengths:** Best-in-class React framework.
- **Weaknesses:** SSR, file-system routing, server components, all overkill for a local single-user app. Adds Node runtime constraints to a backend that's Python.
- **Verdict:** Wrong tool. Built for production server-rendered web apps, not local-first SPAs.

### React + Vite
- **Strengths:** Largest contributor pool of any UI tech. Vite gives modern HMR and tiny build config. No SSR overhead. Plays cleanly with a separate Python backend. Industry default. Feels neither dated nor experimental.
- **Weaknesses:** Node toolchain to maintain (npm audit churn, periodic major upgrades). Bundle ships JS the user must download.

## Consequences

### Positive
- Maximum contributor reach.
- Mature ecosystem for everything we need (forms, tables, charts, query state).
- Vite gives near-instant dev feedback and zero-config TS.
- Pairs naturally with Tailwind + shadcn/ui (see [ADR-0004](./0004-ui-component-library.md)) and a generated TS client from FastAPI's OpenAPI.

### Negative
- Node toolchain in addition to Python. Two ecosystems to upgrade.
- npm dependency surface area requires periodic security audits.
- React rendering quirks (effects, strict mode, suspense) are a learning curve for newer contributors.

## Revisit when

- The maintenance cost of the JS dependency surface becomes outsized vs. the UI's complexity.
- We ship a desktop wrapper (Tauri/Electron) where server-rendered HTML would be lighter.
- React itself stops being the safe default (no realistic horizon for that).
