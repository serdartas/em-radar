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

- Signals are authored in **YAML** (declarative, reviewable, shareable).
- They are **imported into a local database** on install/update.
- **Export** writes them back out in the **same YAML format**. Round-trippable, no lock-in.
- A set of **built-in, non-negotiable default signals** ships with the tool. Sensible defaults nobody should have to argue about (e.g. "MR open > N days with no review activity").

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

- **Open source:** core signal engine, generic connectors (Jira, GitLab, …), default built-in signals, CLI, GUI shell, marketplace client.
- **Private / proprietary (optional):** company-specific adapters, internal signal packs, internal deployment glue.

This lets companies adopt EM Radar without giving up internal customizations, and lets the community grow the open core without being gated by any single org.

---

## Guiding Principles

- **Local-first, private by default.** The EM owns their data.
- **Signals as shareable content, not hard-coded logic.** YAML in, YAML out.
- **Open core, private edges.** Anyone can extend; companies can keep their extensions internal.
- **Two equal surfaces.** GUI and CLI are both first-class.
- **Sensible defaults.** Built-in signals exist so the tool is useful on day one with zero configuration.
- **No lock-in.** Everything imported can be exported in the same format.
