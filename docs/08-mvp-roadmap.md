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
| M4 | GitLab connector | Real GitLab data flowing into canonical model. | Real GitLab repo produces real findings for the 5 MR signals. |
| M5 | Signal engine (full MVP set) | All 13 signals operational with parameter overrides and scope. | All MVP signals firing correctly with overrideable thresholds. |
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
- UI: connect Jira, pick projects/boards, run a sprint report.
- Implement the remaining 7 Jira signals (catalog 10.2–10.8).

**Deliverables.** A real Jira sprint produces findings for all 8 work-item signals.

**Out of scope.** GitLab.

**Acceptance.**
- Connect to a real Jira instance with a personal access token.
- Pick a sprint; report runs without errors.
- All 8 Jira signals fire correctly against fixture data (verified with contract tests).
- Token is masked in UI, absent from logs, absent from YAML export.

---

### M4 — GitLab connector

**Goal.** Real GitLab data flowing through the canonical pipeline.

**Scope.**
- GitLab connector implementing `ConnectorBase`, `MergeRequestProvider`, `ReviewProvider`.
- Config schema (URL, token).
- `test_connection`, `list_repositories`, `fetch_mergerequests`, `fetch_reviews`.
- Workitem-key extraction from MR title, description, source branch.
- MR-to-WorkItem linking when matching key exists in cached Jira data.
- Implement the 5 GitLab signals (catalog 10.9–10.13).

**Deliverables.** A real GitLab project produces findings for all 5 MR signals. Linked WorkItem evidence appears in MR findings.

**Out of scope.** GitHub.

**Acceptance.**
- Connect to a real GitLab instance with a personal access token.
- Pick repositories; report runs without errors.
- All 5 MR signals fire correctly against fixture data.
- MR without `[A-Z]+-\d+` in any of (title, description, branch) is flagged by `mergerequest-without-linked-workitem`.

---

### M5 — Signal engine (full MVP set)

**Goal.** Solidify the engine: scope filters, severity resolution, evidence structure, performance.

**Scope.**
- Scope filters per [signal spec §7.4](./06-signal-yaml-spec.md#74-scope-optional-object) wired into every signal.
- Pack-level defaults (`severity_override`, default scope) applied correctly.
- Severity resolution order per [signal spec §8](./06-signal-yaml-spec.md#8-severity-resolution-order).
- Evidence payloads conform to the shapes documented in [signal spec §10](./06-signal-yaml-spec.md#10-built-in-signal-catalog-mvp).
- Performance: meet [REQ-NF-020](./02-requirements.md#req-nf-020-local-mvp-performance) (60s for 500 work items + 300 MRs on a modern laptop).

**Deliverables.** Engine satisfies the full signal catalog with overrideable parameters and scope. Performance budget met.

**Acceptance.**
- All 13 signals enabled, default pack, target data size, report completes in under 60 seconds.
- Scope filter unit tests pass for every filterable signal.

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
- **Custom user-defined declarative signals** (post-MVP, schema reserved per [signal spec §16](./06-signal-yaml-spec.md#16-forward-compatibility-later)).
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
