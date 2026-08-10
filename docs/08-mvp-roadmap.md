# EM Radar — MVP Roadmap and Milestones

- **Status:** Draft v0.1
- **Date:** 2026-06-01
- **Owner:** Serdar Tas
- **Related:** [01-vision-and-scope.md](./01-vision-and-scope.md) §7, [02-requirements.md](./02-requirements.md) §2 and §10

## 1. Purpose

This document sequences the MVP work into milestones. It is the single source of truth for "what's in v0.1" and "what's deferred", so that marketplace, enterprise, AI, and any other future-phase work cannot creep into the first release.

The milestones are ordered for **value-first delivery**: each milestone ends in a working slice the project owner can demo, even if narrow. Nothing is built that does not connect to a demo on the same milestone.

## 2. MVP Definition (Recap)

> An Engineering Manager can run EM Radar locally, connect to Jira and GitLab using personal access tokens, select a sprint or date range, run configurable deterministic signals, view an actionable report, and export it as Markdown.

The MVP must be useful without AI, cloud hosting, enterprise deployment, Slack/Teams, Kubernetes, multi-user support, SSO, GitHub support, or marketplace.

Reference: [requirements §10 MVP Acceptance Checklist](./02-requirements.md#10-mvp-acceptance-checklist).

## 3. Milestone Map

| # | Name | Goal | Demoable Outcome |
|---|---|---|---|
| M0 | Foundations | Empty but runnable repo. | `uv sync && docker compose up` returns a hello-world page. |
| M1 | Canonical model + demo path end-to-end | One signal evaluated against fake data, rendered in the UI. | Demo connector → 1 signal → 1 finding visible. |
| M2 | Storage, config, UI shell | Persistence and the real UI skeleton. | Signal config editable in UI, survives restart. |
| M3 | Jira connector | Real Jira data flowing into canonical model. | Real Jira sprint produces real findings for the 8 Jira signals. |
| M3.1 | Jira signal engine revision | Revised post-UAT signal model applied before GitLab work. | Jira signals use capability-aware entity types and fields, preview, and group-based import/export; teams own project/board selection. |
| M4 | GitLab connector | Real GitLab data flowing into canonical model. | Real GitLab repo produces real findings for the 5 MR signals. |
| M5 | Signal engine (full MVP set) | All 13 signals operational with one work-tracking or code-repository entity type per definition. | All MVP signals firing correctly through the constrained rule engine against team-owned sources. |
| M6 | Report runner + Markdown export | Sprint and date-range reports, exportable. | Generated report copies cleanly into a doc. |
| M7 | Privacy and polish | REQ-NF security/privacy hardening, docs, onboarding. | Fresh-machine setup in under 15 minutes following the README. |
| v0.1.0 | Release | All [§10 acceptance checklist](./02-requirements.md#10-mvp-acceptance-checklist) items pass. | Public-ready repo + release. |

## 4. Milestone Details

### M0 — Foundations

**Goal.** A runnable empty shell.

**Scope.**
- Monorepo layout per [architecture §19](./03-architecture-overview.md#19-suggested-repository-structure).
- Backend Python project with `uv`, `ruff`, `pytest`, FastAPI scaffold.
- Frontend project with `npm`, Vite, React, Tailwind, shadcn/ui.
- `Dockerfile` and `docker-compose.yml` building one image serving the API and the built frontend.
- Single `/health` endpoint and one blank UI page.
- GitHub Actions CI: lint + test + build on every PR.
- LICENSE (Apache-2.0) and README stub.

**Deliverables.** Working `docker compose up`. CI green on `main`.

**Out of scope.** Database, signals, connectors.

**Acceptance.**
- `curl http://localhost:8080/health` returns `{"status": "ok"}`.
- `http://localhost:8080/` serves the React shell.
- CI passes on a fresh PR.

---

### M1 — Canonical model + demo path end-to-end

**Goal.** Prove the end-to-end shape: connector → normalizer → engine → report → UI. One signal is enough.

**Scope.**
- Canonical models per [data model §5](./05-data-model.md), as SQLModel classes (no migrations yet, in-memory SQLite is fine).
- Connector interface protocol per [connector spec §6](./07-connector-interface.md).
- **Demo connector** producing a deterministic fixture company (3 projects, 1 sprint, 30 work items, 10 MRs).
- One signal implemented: `stale-in-progress-work-item`.
- A `/reports/run` API endpoint that runs the demo connector + the one signal + returns findings JSON.
- A UI page rendering the findings.

**Deliverables.** Running the demo from the UI produces visible findings.

**Out of scope.** Persistence between restarts, configuration, real connectors.

**Acceptance.**
- Clicking "Run demo report" in the UI shows N findings from `stale-in-progress-work-item`.
- The same demo run produces the same findings every time (determinism).

---

### M2 — Storage, config, UI shell

**Goal.** Make EM Radar persistent and configurable through the UI.

**Scope.**
- Switch SQLite from in-memory to file-backed (`/data/em-radar.db` in the Docker volume).
- Alembic migrations.
- Persist: connections, signal config, generated reports, findings, normalized data cache.
- Default signal pack seeding on first startup.
- UI pages: setup, source connections (UI only; no real connectors yet), signal settings, report runner, report results, settings/privacy.
- Signal settings page can enable/disable signals and override parameters for all 13 catalog entries (even if only one signal is implemented).
- YAML import/export endpoints + UI.

**Deliverables.** Configuration changes persist across container restart. Demo connector + one signal still works.

**Out of scope.** Real connectors.

**Acceptance.**
- Restart the container; previous report and config are still there.
- Edit a threshold in the UI; re-run the demo; new threshold takes effect.
- Export YAML; re-import on a fresh database; previous overrides restored.

---

### M3 — Jira connector

**Goal.** Real Jira data flowing through the canonical pipeline.

**Scope.**
- Jira connector implementing `ConnectorBase`, `WorkItemProvider`, `TransitionProvider`.
- Config schema (URL, auth email, token).
- `test_connection`, `list_projects`, `list_boards`, `list_sprints`, `fetch_workitems`, `fetch_transitions`.
- Default field mapping (story points, epic link, acceptance criteria, blocked label).
- UI: create and test a Jira connection; configure a team's project/board source; run a sprint
  report.
- Implement the remaining 7 Jira signals (catalog 10.2–10.8).

**Deliverables.** A real Jira sprint produces findings for all 8 work-item signals.

**Out of scope.** GitLab.

**Acceptance.**
- Connect to a real Jira instance with a personal access token.
- Pick a sprint; report runs without errors.
- All 8 Jira signals fire correctly against fixture data (verified with contract tests).
- Token is masked in UI, absent from logs, absent from YAML export.

---

### M3.1 — Jira signal engine revision

**Goal.** Align the app with the post-UAT signal model before extending it to GitLab.

**Scope.**
- Rework signal persistence from built-in id + params into structured signal definitions for one
  signal entity type, with expression trees, report settings, and origin metadata.
- Add reusable signal config groups (many-to-many with signals and teams) and attach one
  project/board scope to each team; team source selections are resolved at report time and never
  stored on signals.
- Add a Jira capability schema for issue fields, supported operators, value providers, and
  sprint-only availability constraints.
- Update the signal settings UI into a constrained builder: create, duplicate, edit, disable, delete
  user-created signals, bundle them into signal config groups, and preview results before saving.
- Represent the 8 default-pack Jira signals as declarative templates that can be instantiated,
  duplicated, and recreated from scratch (no hardcoded signal logic).
- Update YAML import/export to support private backup and public template modes.

**Deliverables.** Real Jira UAT workflows can express team-specific rules such as Scrum stale-work
checks, Kanban aging checks, and support ticket SLA checks without applying every signal globally to
every Jira project or board.

**Out of scope.** GitLab-specific fields and MR signal templates.

**Acceptance.**
- A Jira connector exposes searchable project/board options for team configuration; one board
  `ScopeDefinition` stores both selected identities.
- A default-pack Jira template can be duplicated, edited into a custom work-tracking rule, previewed,
  saved, and evaluated without selecting a connection, project, or board.
- Signal-group exports contain definitions and report settings without connections, team source
  selections, or secrets.
- Public templates strip organization-specific values and import without connector or scope mapping.

---

### M4 — GitLab connector (connector only, no signal creation)

**Goal.** Real GitLab data flowing through the canonical pipeline. No signals are authored in this
milestone — per the no-hardcoded-signals principle, code-source signals are declared as data in M5
after the engine can evaluate merge requests.

**Scope.**
- GitLab connector implementing `ConnectorBase`, `MergeRequestProvider`, `ReviewProvider`.
- GitLab capability schema for the `merge_request` entity type, fields, operators, and value
  providers, following the M3.1 signal-builder contract.
- Config schema (URL, token).
- `test_connection`, `list_repositories`, `fetch_mergerequests`, `fetch_reviews`.
- Workitem-key extraction from MR title, description, source branch.
- MR-to-WorkItem linking when matching key exists in cached Jira data.
- First-run onboarding wizard.

**Deliverables.** A real GitLab project's merge-request data flows through the canonical pipeline;
linked WorkItem evidence resolves. The 5 code-source signals are deferred to M5-14 (declarative).

**Out of scope.** GitHub. Any merge-request signal logic (declared as default-pack data in M5-14,
after M5-10 adds MR evaluation).

**Acceptance.**
- Connect to a real GitLab instance with a personal access token.
- Attach the whole GitLab connection to a team; all accessible repositories are included and the
  report runs without errors.
- MRs normalize correctly and key-extraction/linking passes contract + normalization tests.

---

### M5 — Signal engine (full MVP set): generic, de-hardcoded, multi-entity

**Goal.** Complete the generic declarative engine and remove every hardcoded signal, then declare the
remaining signals as data. This milestone is where "the signal engine is built" — no signal exists in
code form after it.

**Scope.**
- Expression evaluation per [signal spec §10](./06-signal-yaml-spec.md#10-rule-expressions) across
  Jira and GitLab entity types, including **merge-request (code) entity evaluation** so code signals
  run through the same generic evaluator.
- **Remove the per-signal hardcoding** still on the live path (the `sprint-scope-churn` delegation to
  a Python class and per-template evidence) and **delete the dead hardcoded `Signal`-class stack**
  left from M1/M3; evidence becomes expression-derived.
- **Declarative default pack + single seeding path**; seed the 5 merge-request signals as declarative
  default-pack definitions (the replacement for the removed M4 signal work).
- Signal builder UI gains the `merge_request` entity type, so every code signal is recreatable in the
  UI.
- Each team's signals are the union of its attached signal config groups; each signal evaluates one
  MVP entity type against the team's project/board scope or whole code connection.
- Connector capability validation; expression-derived evidence conformance across all 13 signals.
- Performance: meet [REQ-NF-020](./02-requirements.md#req-nf-020-local-mvp-performance) (60s for 500 work items + 300 MRs on a modern laptop).

**Deliverables.** A single generic engine interpreting declarative signal definitions only — no
hardcoded signals ([REQ-F-036](./02-requirements.md#req-f-036--no-hardcoded-signals)). All 13 signals
ship as default-pack data, each recreatable from the Signal Settings page. Performance budget met.

**Acceptance.**
- All 13 signals enabled, default pack, target data size, report completes in under 60 seconds.
- No `template_key`-keyed evaluation/evidence branch and no `Signal`-subclass registry remain in the
  codebase; the full default report is unchanged by their removal.
- Expression, source-type compatibility, capability, and evidence conformance tests pass for every
  seeded signal.

---

### M6 — Report runner + Markdown export

**Goal.** Reports are usable artifacts, not just JSON.

**Scope.**
- Report sections per [requirements REQ-F-052](./02-requirements.md#req-f-052-report-sections): summary, top risks, planning hygiene, delivery flow, MR flow, detailed findings, suggested actions.
- Ordering by severity within each section.
- Markdown export per [REQ-F-053](./02-requirements.md#req-f-053-markdown-export).
- Source links rendered in every finding.
- Date-range reports in addition to sprint reports.
- Report history page; offline viewing of past reports.

**Deliverables.** Generated Markdown opens cleanly in any Markdown editor and pastes into Confluence/Notion intact.

**Acceptance.**
- Markdown round-trips through Confluence and GitHub README preview without broken links.
- Past reports remain viewable in the UI even with the source disconnected.

---

### M7 — Privacy and polish

**Goal.** Make the experience trustworthy and onboarding-friendly.

**Scope.**
- Token masking everywhere (`****` + last 4).
- Log scrubbing tests (REQ-NF-003).
- YAML export credential exclusion tests.
- Telemetry-off-by-default verified end to end (REQ-NF-002).
- "Delete connection and cached data" action in UI.
- Localhost-only binding by default in Docker (REQ-NF-010).
- README quickstart: from zero to a demo report in under 5 minutes.
- README real-data path: from zero to a real Jira/GitLab report in under 15 minutes.
- `CONTRIBUTING.md`, issue templates, PR template.
- License headers in source files.

**Deliverables.** A fresh-machine user can follow the README and produce a meaningful report.

**Acceptance.**
- An EM unfamiliar with the project can reach a successful report within 15 minutes using only the README.
- Automated tests prove tokens never appear in logs or exports for the bundled connectors.

---

### v0.1.0 — Release

**Release criteria.**
- All [requirements §10](./02-requirements.md#10-mvp-acceptance-checklist) checkboxes pass.
- All contract tests green for Jira, GitLab, and demo connectors.
- Performance target met for the documented data size.
- Documentation complete: README, [01-vision-and-scope](./01-vision-and-scope.md), [02-requirements](./02-requirements.md), [03-architecture-overview](./03-architecture-overview.md), [04-tech-stack](./04-tech-stack.md), [05-data-model](./05-data-model.md), [06-signal-yaml-spec](./06-signal-yaml-spec.md), [07-connector-interface](./07-connector-interface.md), this roadmap.
- CHANGELOG.md initialized.
- Public GitHub repo published with Apache-2.0 LICENSE.
- Tagged release `v0.1.0` with built Docker image.

## 5. Out-of-MVP Backlog (Phase 2+)

Carried as the explicit "do not pull into MVP" list. Reorder as priorities sharpen.

- **Marketplace.** Public signal-pack catalog (Phase 2).
- **GitHub connector** (Phase 3).
- **AI-optional features.** Claude connector, DoR check, weak-AC detection (Phase 4).
- **Destination connectors.** Slack, Teams, email, Confluence (Phase 5).
- **Enterprise edition.** PostgreSQL, OIDC, RBAC, audit logs, Helm chart (Phase 6).
- **Deep arbitrary signal expression nesting** beyond one nested group.
- **Desktop wrapper** (Tauri/Electron) for non-Docker distribution.
- **CLI** (`em-radar` binary). Architecture-ready in MVP; full implementation later.
- **JSON and PDF report exports.**
- **Offline report generation from cache** (MVP only supports offline *viewing*).

## 6. Risk Register

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| Jira custom-field variability breaks default mappings | Reports look wrong for some users | High | UI-driven field mapping, demo data, contract tests |
| GitLab Cloud API rate limits | Long fetches fail | Medium | Pagination + retry in connector; surface partial-data state |
| Signal pack YAML schema drift | Imports fail or silently change behavior | Medium | `apiVersion` discipline, validation tests, in-app migration |
| Token leak in logs | Trust collapse | Low (with controls) | Default redaction in shared httpx client, automated log-scrub tests |
| Performance miss on realistic data | Frustrating UX | Medium | Per-milestone perf check, async fetches, incremental cache |
| SQLite single-writer contention if user opens two report runs | Cryptic errors | Low | Serialize report runs; show queue state in UI |
| Scope creep (marketplace, AI, GitHub) | Slips v0.1 | High | This document is the gate; defer ruthlessly |

## 7. Tracking

- **GitHub issues** mapped to milestones M0–M7.
- **GitHub milestones** named exactly as in §3 to ease project board filtering.
- Each milestone's "Acceptance" bullets become a closing checklist on a milestone-summary issue.
- A milestone is closed only when its acceptance bullets all pass on `main`.
- No work item is "done" without a test, unless explicitly marked as documentation or scaffolding.

## 8. Out of Scope for This Document

- Specific calendar dates. This is a personal-cadence project; sequencing matters more than dates.
- Resource allocation. Single owner.
- Funding, marketing, branding.
