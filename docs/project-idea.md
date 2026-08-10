# EM Radar — Project Idea

## Summary

**EM Radar** is an open-source, local-first **Engineering Management Radar** for individual Engineering Managers (EMs), with an optional path to company/enterprise deployment.

It runs inside a company's own environment (no data leaves the org), connects to engineering tools like **Jira** and **GitLab**, normalizes the data into a common model, evaluates **configurable management signals**, and produces **sprint and date-range reports** focused on:

- **Delivery risks** (slipping work, scope churn, bottlenecks)
- **Planning hygiene** (estimates, refinement quality, sprint shape)
- **Code review flow** (review latency, reviewer load, stale MRs/PRs)

The tool ships with both a **graphical UI** and a **CLI**, so EMs can use whichever fits the moment.

---

## Goals

1. Give every EM a personal, private radar that surfaces management signals without depending on a central data team.
2. Keep the **core engine and generic connectors fully open source**, so the community can extend, audit, and trust them.
3. Allow **company-specific adapters** (proprietary workflows, custom fields, internal tools) to be developed and kept **private**, layered on top of the open core.
4. Treat **signals as content**, not code: signal definitions are shareable YAML files, distributed through a community **marketplace**.
5. Default to **local-first**: a single EM should be able to install, configure, and get value within minutes, without any backend or infra.
6. Provide a clean upgrade path to **team or enterprise deployment** for organizations that want shared dashboards.

---

## Non-Goals (for now)

- Replacing project management tools (Jira, Linear, etc.). EM Radar **reads** from them; it does not become a source of truth for work items.
- Performance management of individual engineers. Signals describe **systems and flows**, not people-ranking metrics.
- Building a SaaS product as the primary distribution model. SaaS is not the target; local-first is.

---

## Target Users

- **Primary:** Individual Engineering Managers running 1–3 teams, who want their own lens on delivery and planning health.
- **Secondary:** Directors / Heads of Engineering who want to roll up multiple EM radars into a department view (enterprise mode).
- **Tertiary:** Open-source contributors and signal authors who want to publish reusable signal packs.

---

## Core Concepts

### 1. Connectors
Pluggable adapters that pull raw data from external systems.

- **Generic, open-source connectors:** Jira, GitLab (more to follow: GitHub, Azure DevOps, etc.).
- **Custom adapters:** companies can write private adapters for internal tools or non-standard workflows, kept in their own repos.

### 2. Normalized Data Model
A common internal schema (issues, sprints, merge/pull requests, reviews, comments, transitions) so signals don't need to know which tool the data came from.

### 3. Signals
The heart of the product. A signal is a **configurable rule** that inspects the normalized data and emits an observation (e.g. "3 MRs open > 5 days without review", "sprint scope grew 30% mid-sprint").

- Signals are **declarative structured data**, not code. A signal is a rule expression
  (field / operator / value conditions combined with AND/OR groups) over one source domain.
- **No signal is hard-coded.** Every signal — including the ones the app ships with — is a
  definition the user can view, edit, disable, delete, or **recreate from scratch on the Signal
  Settings page**. The engine has no privileged, code-backed signals; it only interprets these
  definitions. There is nothing a shipped signal can do that a user-created one cannot.
- Signals filter **canonical, connector-independent fields**. The two source domains — the
  **task-board source** (work items) and the **code source** (merge/pull requests) — each expose a
  fixed field set that a signal can filter on **regardless of which connector supplied the data**
  (a `status_category` or "age in current status" condition means the same thing whether the source
  is Jira, GitHub, or Linear).
- Signals are authored in the UI and **round-trip through YAML** (declarative, reviewable,
  shareable). They are **imported into a local database** on install/update, and **export** writes
  them back out in the **same YAML format**. No lock-in.
- The app ships with a **default signal pack**: a bundle of ready-made signal definitions —
  combining task-board and code-source rules — seeded on first run so the tool is useful on day one.
  These are sensible defaults, not fixed features: the same pack could be rebuilt by a user from the
  Signal Settings page.

### 4. Signal Marketplace
A public website acting as a catalog of community-contributed signal configurations.

- EMs can **browse, download, and install** signal packs.
- Contributors can **publish** their own signals (with versioning, descriptions, examples).
- The marketplace is open; the tool can also load signals from any local file or private URL.

### 5. Reports
Sprint and date-range views that aggregate signal output into actionable summaries:

- Delivery risk view
- Planning hygiene view
- Code review flow view
- Custom views composed from selected signals

### 6. Local-First Storage
All data (raw, normalized, and signal output) lives in a local database on the EM's machine by default. No telemetry, no upload, no shared backend required.

---

## User Experience

- **GUI:** Primary surface for most EMs. Browse reports, configure connectors, manage signals, drill into specific findings.
- **CLI:** First-class alternative for terminal-native users and automation (cron-driven refreshes, scripted exports, CI checks).
- Both surfaces operate on the same local engine and database. Feature parity is a design goal where it makes sense.

---

## Distribution & Deployment Modes

1. **Single-EM local install** (default): one binary / package, local DB, runs on the EM's laptop.
2. **Team deployment** (optional): shared instance for a small group of EMs, shared signal config, shared reports.
3. **Enterprise deployment** (optional, later): multi-team, SSO, role-based access, departmental rollups.

The same core engine powers all three modes; deployment shape changes, the product does not fork.

---

## Openness Model

- **Open source:** core signal engine, generic connectors (Jira, GitLab, …), the default signal pack, CLI, GUI shell, marketplace client.
- **Private / proprietary (optional):** company-specific adapters, internal signal packs, internal deployment glue.

This lets companies adopt EM Radar without giving up internal customizations, and lets the community grow the open core without being gated by any single org.

---

## Guiding Principles

- **Local-first, private by default.** The EM owns their data.
- **Signals as shareable content, not hard-coded logic.** YAML in, YAML out. No signal is baked into
  the engine; every signal is a declarative definition the user can recreate from the UI.
- **Open core, private edges.** Anyone can extend; companies can keep their extensions internal.
- **Two equal surfaces.** GUI and CLI are both first-class.
- **Sensible defaults.** A default signal pack is seeded on first run so the tool is useful on day
  one with zero configuration — and every signal in it is editable and recreatable, not fixed.
- **No lock-in.** Everything imported can be exported in the same format.
