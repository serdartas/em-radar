# EM Radar — Functional Flows

- **Status:** Draft v0.1
- **Date:** 2026-06-07
- **Owner:** Serdar Tas
- **Related:** [01-vision-and-scope.md](./01-vision-and-scope.md) §6, [02-requirements.md](./02-requirements.md) §4, [03-architecture-overview.md](./03-architecture-overview.md) §18, [05-data-model.md](./05-data-model.md), [07-connector-interface.md](./07-connector-interface.md)

## 1. Purpose

This document describes the **end-to-end functional flows** an Engineering Manager (EM) walks
through when using EM Radar: first-run onboarding, connecting sources, scoping teams, the
initial data sync, the dashboard, running reports, and reconfiguration.

The earlier specs define *what the system is made of* (entities, connectors, signals). This
document defines *how a person moves through it*. Where a flow implies a change to an existing
spec, that change is called out in §12 (Model & Backlog Impact) rather than silently assumed.

The four shaping decisions behind these flows:

1. **Connections are created once and named; the team owns its sources; signals live in reusable
   groups.** Source credentials are entered once as a reusable, **named** *Connection* on a
   connection-management page (the name lets one instance be told from another — e.g. a contractor
   with two Jira instances). A *Team* then attaches up to two sources: a **task-board source** (one
   Jira project/board pair in one board scope, 0..1) and a **code source** (a whole GitLab/GitHub
   connection, 0..1). Signals are bundled into reusable *Signal Config Groups* that the EM attaches
   to teams. Each MVP signal declares one work-tracking or code-repository entity type; a team's
   sources are resolved at report time.
2. **Latest-report landing dashboard.** After setup, the landing page shows each team's most
   recent report (severity counts + top risks) with a refresh action. It reuses the report
   view; it is not a separate analytics product.
3. **Working mode derived from Jira, confirmed by the user.** Scrum vs Kanban and sprint
   length are inferred from the selected Jira board and recent sprints, then shown for
   confirm/override.
4. **First-class multi-team in MVP.** Onboarding supports creating several named teams; teams
   are manageable after setup.

MVP source support is **Jira + GitLab**. GitHub and others are later phases
([requirements REQ-F-015/016](./02-requirements.md#req-f-015--github-connector)); the flows
below are written source-agnostically so adding a source does not reshape them.

---

## 2. Actors and Key Entities

| Concept | What it is | Storage | Notes |
|---|---|---|---|
| **EM (user)** | The single local user. | — | No multi-user/auth in MVP. |
| **Connection** | One **named** source instance with connector-defined access configuration (for example Jira Cloud URL + email + token, or GitLab URL + token). | `SourceConnection` ([architecture §8.1](./03-architecture-overview.md#81-stored-data), M2-03) | Reusable across teams. Managed independently of teams. `name` is required and unique per workspace; the connection stores no discovered project, board, or repository data. |
| **Team** | A named unit of work the EM manages. Carries up to two sources + working mode. | `TeamProfile` ([data model §5.12](./05-data-model.md#512-teamprofile)) | First-class; multiple per install. Created with just a name; **saveable with no sources**. See §12 for fields added by this doc. |
| **Task-board source** | The team's workflow project and board (later, other trackers). | One `ScopeDefinition` (`scope_type = board`, [requirements REQ-F-041A](./02-requirements.md#req-f-041a--team-owned-sources)) | Owned by the **team** (0..1 in MVP), chosen via a searchable project → board picker. Its `external_ref` contains both project and board identity. |
| **Code source** | The team's code repository host: a whole GitLab/GitHub connection (all its repos in scope). | `TeamProfile.code_connection_id` ([data model §5.12](./05-data-model.md#512-teamprofile)) | Owned by the **team** (0..1 in MVP). Per-repository scoping is a later phase. |
| **Signal** | A structured rule expression carrying its own configuration for one signal entity type. | `SignalDefinition` ([signal spec §9](./06-signal-yaml-spec.md#9-signal-definitions)) | In MVP, either work tracking (`issue`) or code repository (`merge_request`). It contains no connection or project/board/repository selection. |
| **Signal Config Group** | A reusable, named bundle of signals (e.g. "Scrum signals"). | `SignalConfigGroup` ([data model §5.12C](./05-data-model.md#512c-signalconfiggroup)) | Many-to-many with teams and with signals. Attach a group to as many teams as you like. |
| **Working mode** | `scrum` or `kanban`, plus sprint length for scrum. | On `TeamProfile` (`working_mode`, `sprint_length_days`) | Derived from the board; user-confirmable. |
| **Report** | Result of evaluating signals for a team over a window. | `Report` + `SignalFinding` ([data model §5.14–5.15](./05-data-model.md#514-signalfinding)) | One per run; persisted; viewable offline. |
| **Dashboard** | Landing view: latest report per team. | Derived (reads latest `Report` per team) | Not a new stored entity. |

**Relationship shape:**

```mermaid
flowchart LR
    ConnJira["Connection: Jira<br/>(url + token)"]
    ConnGitLab["Connection: GitLab<br/>(url + token)"]
    ScopeA["Board scope: Fraud / Delivery<br/>(project + board identity)"]
    ScopeB["Board scope: Search / Operations<br/>(project + board identity)"]
    TeamA["Team: Payments<br/>mode=scrum, 2w"]
    TeamB["Team: Search<br/>mode=kanban"]
    RepA["Report (latest)"]
    RepB["Report (latest)"]

    ConnJira --> ScopeA
    ConnJira --> ScopeB
    ScopeA --> TeamA
    ScopeB --> TeamB
    ConnGitLab --> TeamA
    ConnGitLab --> TeamB
    TeamA --> RepA
    TeamB --> RepB
    RepA --> Dashboard
    RepB --> Dashboard
```

---

## 3. Flow A — First-run Onboarding Wizard

**Goal.** Take a fresh user from an empty install to a populated dashboard, guiding them through
connections and one or more teams.

**Entry condition.** No `TeamProfile` rows exist (first run). The wizard is the expanded form
of the Setup page ([requirements REQ-F-002](./02-requirements.md#req-f-002--local-web-ui)).

**Steps.**

1. **Welcome & privacy.** Plain-language local-first explainer (data/tokens/reports stay local,
   no telemetry, read-only access). One "Get started" CTA.
2. **Add ticketing connection (Jira).** See [Flow B](#4-flow-b--connection-setup--token-guidance).
   Give it a **name**, enter credentials, test, and save. Required to run work-item signals.
3. **Add code connection (GitLab).** See [Flow B](#4-flow-b--connection-setup--token-guidance).
   Name it, test, save. Optional but recommended; merge-request signals need it.
4. **Create team.** Ask for a **team name**. Creates a `TeamProfile` (which may be saved with no
   sources yet).
5. **Attach the team's sources.** See [Flow C](#5-flow-c--team-scope--working-mode-detection): choose
   the **task-board source** (pick a Jira connection, then a project and board via searchable pickers)
   and confirm the detected working mode/cadence, then choose the **code source** (attach a whole
   GitLab/GitHub connection). Either may be left unset, but a report needs at least one.
6. **Add another team?** If **yes**, return to step 4. Existing connections are **reused** (no
   token re-entry); the user may add a new connection if a team lives on a different instance.
   If **no**, continue.
7. **Finish → initial sync.** See [Flow D](#6-flow-d--initial-sync--dashboard).

**Connection phase.** Connections are tested and persisted before any team source is selected.

```mermaid
sequenceDiagram
    participant U as User
    participant W as Onboarding Wizard
    participant API
    participant C as Connector
    participant DB as Storage

    U->>W: Get started
    W->>U: Privacy explainer
    U->>W: Add Jira connection (name, url, email, token)
    W->>API: test_connection (Jira)
    API->>C: test_connection()
    C-->>API: ok (user, permissions)
    API->>DB: save Connection (name unique; token stored locally, masked on read)
    U->>W: Add GitLab connection (name, url, token)
    W->>API: test_connection (GitLab)
    API-->>W: ok
    W->>API: save Connection
    API->>DB: save Connection (name + access configuration)
    Note over W,DB: Connections contain access configuration only
```

**Team phase.** Project/board selection begins only after a team exists and is persisted on that
team's board scope.

```mermaid
sequenceDiagram
    participant U as User
    participant W as Onboarding Wizard
    participant API
    participant C as Connector
    participant DB as Storage

    loop For each team
        U->>W: Team name
        W->>API: create TeamProfile (no sources yet)
        W->>API: list_projects (selected Jira connection)
        API->>C: list_projects()
        U->>W: select project
        W->>API: list_boards(project)
        API->>C: list_boards(project)
        U->>W: select board
        W->>API: save one board scope (project + board identity)
        API->>DB: save ScopeDefinition and attach it to TeamProfile
        W->>API: list_sprints(board)
        API-->>W: detected mode + cadence
        W->>U: Confirm "Scrum, 2 weeks" (or override)
        U->>W: attach code source (whole GitLab connection)
        W->>API: save code_connection_id + working_mode
        API->>DB: update TeamProfile
        W->>U: Add another team?
    end
    U->>W: Finish
    W->>API: start initial sync (all teams)
```

**Resumability.** Each completed step is persisted immediately, so closing the browser
mid-wizard does not lose entered connections/teams; reopening resumes at the first incomplete
step.

---

## 4. Flow B — Connection Setup & Token Guidance

**Goal.** Establish a verified, reusable, **named** connection to a source, with safe token handling.
The Connections page manages connection access only: it creates, edits, tests, and deletes
connections, but never picks projects, boards, or repositories and never runs a report (those
belong to the Team, Flow C).

**Steps.**

1. **Pick a source and name it.** Choose the source type, then give the connection a **name**
   (required, unique per workspace — so two instances of the same source, e.g. two Jira tenants, are
   distinguishable). The rest of the form is rendered from the connector's `config_schema`
   ([connector spec §4](./07-connector-interface.md#4-configuration)) via the connector
   registry (`GET /api/connectors`). Secret fields render as write-only password inputs.
2. **Inline access guidance.** Per source, link to the minimum read-only scopes and how to
   create the token ([requirements REQ-NF-011](./02-requirements.md#req-nf-011--read-only-source-access),
   M7-09). Jira Cloud uses email + API token; GitLab uses a `PRIVATE-TOKEN`.
3. **Test connection.** Calls `test_connection()`; on success show the authenticated user and
   detected permissions ([connector spec §6.1](./07-connector-interface.md#61-connectorbase-always-required)).
   On failure, show a structured, token-free error
   ([requirements REQ-NF-070](./02-requirements.md#req-nf-070--graceful-source-failure)).
4. **Save.** Token stored locally; **masked on every read** (`****` + last 4), never logged,
   never exported ([ADR-0006](./ADRs/0006-token-storage.md),
   [requirements REQ-NF-003](./02-requirements.md#req-nf-003--credential-safety)).

**Reuse.** When scoping a later team, existing connections are offered first; the user only
adds a new connection if the team uses a different instance.

**Error handling.** `ConnectorAuthError` → "credentials rejected"; `ConnectorNotFoundError` →
"URL/instance not found"; `ConnectorRateLimitedError`/`ConnectorTransientError` → "source busy,
retry" — all from the typed hierarchy ([connector spec §10](./07-connector-interface.md#10-errors)),
never a stack trace, never the token.

---

## 5. Flow C — Team Scope & Working-Mode Detection

**Goal.** Give a team its two sources and establish how it works, with minimal questions. A team may
be created and **saved with no sources**; sources are attached here on the Teams page. A **report run
requires at least one source** (see [Flow E](#7-flow-e--generate--refresh-a-report)).

**Steps.**

1. **Attach the task-board source.** Pick one of the team's ticketing connections (by name), then a
   **project** and a **board** from **searchable** lists — `list_projects` then
   `list_boards(project)`
   ([connector spec §6.2](./07-connector-interface.md#62-workitemprovider-jira-linear-github-issues)).
   Stored as the team's `0..1` board scope (`ScopeDefinition`, `scope_type = board`). That single
   scope's `external_ref` contains both the selected project identity and selected board identity.
2. **Detect working mode + cadence.** On board selection, read `Board.type`
   (`scrum`/`kanban`/`other`, [data model §5.3](./05-data-model.md#53-board)) and the most
   recent closed/active sprints via `list_sprints` to infer **sprint length** from
   `start_date`/`end_date` medians.
   - **Scrum detected:** show "Scrum · sprint length 2 weeks" pre-filled; default report window
     = **active sprint**.
   - **Kanban detected (or no sprints):** show "Kanban"; default report window = **date range**
     (last `N` days, default 14).
   - User can **confirm or override** either field.
3. **Attach the code source.** Pick one of the team's code connections (GitLab/GitHub) by name. The
   **whole connection** is attached (`TeamProfile.code_connection_id`) — every repository the token
   can access is in scope; there is no per-repository picker in MVP. `list_repositories`
   ([connector spec §6.3](./07-connector-interface.md#63-mergerequestprovider-gitlab-github-prs-bitbucket))
   is resolved at report time.
4. **Field mappings (defaults, advanced deferred).** Default Jira mappings are applied
   silently ([data model §8.1](./05-data-model.md#81-jira--workitem-defaults)); an "advanced
   field mapping" affordance exists but is optional (M3-05).
5. **Persist** the board scope, `code_connection_id`, and working mode on the `TeamProfile`. The
   board scope belongs to the team and references the Jira connection; the connection itself is
   unchanged. Any source may be left unset and saved.

```mermaid
flowchart TD
    A["Pick task-board connection + project<br/>(searchable)"] --> B["Pick board (searchable)"]
    B --> C{"Board.type + sprints?"}
    C -->|scrum + sprints| D["Mode=Scrum<br/>sprint_length from dates<br/>default window = active sprint"]
    C -->|kanban / no sprints| E["Mode=Kanban<br/>default window = date range (N days)"]
    D --> F["Confirm / override"]
    E --> F
    F --> G["Attach code source<br/>(whole GitLab/GitHub connection)"]
    G --> H["Save team sources + mode<br/>(connection records unchanged)"]
```

**Why mode matters downstream.** Working mode sets the team's **default report window**, which
in turn determines **which signals can fire**: sprint-only signals
(`repeated-carry-over`, `sprint-scope-churn`) require a sprint window and are **skipped with a
note** for date-range/Kanban runs, mirroring connector-capability skipping
([connector spec §6.5](./07-connector-interface.md#65-transitionprovider-optional)). Which signals
run is decided by the signal config groups attached to the team — see §10.

---

## 6. Flow D — Initial Sync & Dashboard

**Goal.** On finishing setup, fetch each team's data and present something useful with no
further clicks.

**Steps.**

1. **Build the window per team.** Scrum → `EvaluationWindow(window_type=sprint, sprint_id=active)`;
   Kanban → `EvaluationWindow(window_type=date_range, start=now-N days, end=now)`
   ([data model §5.13](./05-data-model.md#513-evaluationwindow)), with `team_profile_id` set.
   `EvaluationContext.now` = the report's start time (determinism rule,
   [README §4](./backlog/README.md#4-conventions-paths-names-ports)).
2. **Fetch concurrently.** Jira (work items + transitions) and GitLab (merge requests +
   reviews) fetched in parallel ([architecture §18.2](./03-architecture-overview.md#182-report-generation-flow)).
   Progress is shown per source; **partial-source failure is non-fatal** and surfaced as a
   partial-data note ([requirements REQ-NF-070](./02-requirements.md#req-nf-070--graceful-source-failure)).
3. **Normalize, persist, resolve identity.** Normalized entities are upserted by
   `(source, external_id)` to stable internal IDs, and cross-entity links (assignee, parent,
   sprint, MR↔WorkItem) are resolved ([data model §2, §7](./05-data-model.md#2-design-principles)).
4. **Evaluate the team's signals** — the union of enabled signals across the team's attached signal
   config groups, against the team's sources (its board scope and/or its code connection) — and
   persist a `Report` per team with `findings_count_by_severity`. Signals whose source is not attached
   are **skipped with a note** (window-/capability-gating, §10).
5. **Land on the dashboard.**

**Dashboard contents (MVP).** A card per team:

- team name + working mode,
- severity counts (`critical` / `warning` / `info`),
- the top N highest-severity findings (the "top risks" slice),
- **Refresh** (re-run the team's default window) and **Open report** (full sectioned view),
- last-run timestamp and any partial-data warning.

```mermaid
sequenceDiagram
    participant W as Wizard/Finish
    participant R as Report Runner
    participant J as Jira Connector
    participant G as GitLab Connector
    participant N as Normalize+Persist (identity)
    participant E as Signal Engine
    participant DB as Storage
    participant D as Dashboard

    W->>R: initial sync (all teams)
    loop per team
        par
            R->>J: fetch work items + transitions
        and
            R->>G: fetch merge requests + reviews
        end
        J-->>N: WorkItems
        G-->>N: MergeRequests
        N->>DB: upsert by (source, external_id), resolve FKs
        R->>E: evaluate enabled signals (window)
        E->>DB: persist Report + findings
    end
    R-->>D: show latest report per team
```

The dashboard is **derived**: it reads the latest `Report` per team. No new time-series storage
in MVP (trends/charts are a later phase, §11).

---

## 7. Flow E — Generate / Refresh a Report

**Goal.** Produce a fresh report on demand, from the dashboard or the Report Runner.

**Precondition.** The team must have **at least one source** attached (task-board scope or code
connection). A team with no sources can be selected but its run is blocked with a clear message
pointing to Flow C; signals whose source is absent are skipped rather than failing the run.

**Triggers.**

- **Dashboard → Refresh:** re-runs the team's **default** window (active sprint or rolling
  date range).
- **Report Runner:** choose team, then window — a **sprint picker** (Scrum) or **date-range
  picker** (Kanban, or either mode when the EM wants an ad-hoc range)
  ([requirements REQ-F-050/051](./02-requirements.md#req-f-050--sprint-report)).

**Output.** The sectioned report ([requirements REQ-F-052](./02-requirements.md#req-f-052--report-sections)):
summary, top risks, planning hygiene, delivery flow, sprint health, merge request flow, source
linking, detailed findings, suggested actions — severity-ordered, every finding linking back to
its source item, exportable to Markdown ([requirements REQ-F-053](./02-requirements.md#req-f-053--markdown-export)).

Each run **persists a new `Report`**; the latest becomes the team's dashboard card. Past reports
remain viewable (Flow H).

---

## 8. Flow F — Reconfiguration

The wizard is first-run; these are the steady-state management flows.

| Action | Where | Effect |
|---|---|---|
| **Add a team** | Teams page → "Add team" | Re-enters the team loop (Flow A steps 4–6), reusing connections. |
| **Edit a team's sources/mode** | Team detail | Change the task-board scope or the code connection, or override working mode; next run uses it. |
| **Add / edit / re-test a connection** | Connections page | Update name or connector-defined access configuration; `test_connection` re-verifies; token stays masked. No scope or report actions here. |
| **Re-sync** | Dashboard/Team | Refetch + re-evaluate without changing config. |
| **Delete a connection** | Connections page | Removes the connection **and its cached normalized data**; warns about teams that depend on it ([requirements REQ-NF-004](./02-requirements.md#req-nf-004--data-deletion), M7-05). |
| **Delete a team** | Teams page | Removes the team, its scope, and its reports. |
| **Delete cached data / report history** | Settings / Privacy | Clears caches/reports; documented manual volume deletion for a full wipe. |

All destructive actions require confirmation and never touch the source systems (read-only,
[requirements REQ-NF-011](./02-requirements.md#req-nf-011--read-only-source-access)).

---

## 9. Flow G — Signal Config Groups & Import/Export

Steady-state signal configuration is organized around reusable **signal config groups**:

- **Build signals.** View built-in signal templates and existing signals. Create a signal from
  scratch, duplicate a template or existing signal, edit conditions, preview matches, save, disable,
  or delete user-created signals
  ([requirements REQ-F-031/041](./02-requirements.md#req-f-031--default-pack-signals-as-editable-definitions)).
  Each MVP signal selects one signal entity type: work tracking (`issue`) or code repository
  (`merge_request`). There is no connection, project, board, or repository picker in the builder.
- **Group signals.** Create a signal config group (e.g. "Scrum signals", "Kanban signals") and add
  signals to it. A signal can belong to many groups.
- **Attach groups to teams.** From a team, attach one or more groups. A group attached to two teams
  is shared state: editing the group changes both teams' runs.
- The builder is generated from connector capability schemas: the entity type decides available
  fields, operators, values, and sprint-only conditions.
- Export a group's YAML as either a private backup/migration file or a public template file; import
  creates a new group, with validation before applying
  ([signal spec §15–§16](./06-signal-yaml-spec.md#15-export-behavior)).

**Signal applicability.** A team runs the union of signals across its attached groups. Work-tracking
signals evaluate against the team's project/board source; code-repository signals evaluate against
the team's whole code connection. A signal is skipped when the team lacks the source for its entity
type. To give two teams different rules, attach different groups; to run the same check with
different thresholds, create two signals (config is global per signal) and place each in the relevant
group. A single cross-domain signal is deferred until after MVP.

---

## 10. How Working Mode Shapes Signal Availability

Working mode and scope capabilities shape which fields and signals are available:

1. **Window-gating.** Sprint-only signals require a sprint window. A Kanban/date-range run skips
   them and records a one-line note in the report ("skipped: requires a sprint window"). This
   reuses the capability-skip pattern from
   [connector spec §6.5](./07-connector-interface.md#65-transitionprovider-optional).
2. **Scope capabilities.** Sprint fields such as `sprint_day` and `sprint_phase` evaluate only when
   the team's board scope supplies sprint data (scrum boards). Kanban scopes still use aging and
   status conditions.
3. **Entity type plus team sources.** Different teams get different rules by attaching different
   signal config groups. This is how a support team can run a 3-day open-ticket group while a Scrum
   team runs a stale-work group: both signals operate on the work-tracking entity type, while each
   team supplies its own project/board source.

---

## 11. Deferred / Out of Scope for These Flows

- **Aggregated analytics dashboard** (cross-team rollups, trends, charts, time-series storage).
  MVP dashboard is latest-report-per-team only.
- **Scheduled / background auto-refresh.** MVP sync is triggered by finishing setup or by an
  explicit refresh; cron-style refresh is later
  ([roadmap §5](./08-mvp-roadmap.md#5-out-of-mvp-backlog-phase-2)).
- **GitHub and other sources** in onboarding (Phase 3).
- **Deep arbitrary signal expression nesting.** MVP supports AND/OR and one nested group.
- **Multi-source-per-capability teams** (e.g. two Jira instances feeding one team) beyond the
  basic "team may draw from more than one connection" already covered.
- **Cross-source user identity resolution** beyond `member_user_keys`
  ([data model §7](./05-data-model.md#7-identity-linking-and-cross-source-resolution)).

---

## 12. Model & Backlog Impact

These flows imply the following deltas to the existing specs and backlog. They are recorded here
for traceability; applying them is a separate step.

**Data model ([05-data-model.md](./05-data-model.md)).**

- Extend `TeamProfile` (§5.12) with: a single Jira board scope (0..1, via `scope_ids`),
  `signal_config_group_ids: UUID[]` (attached groups), `working_mode: enum {scrum, kanban}`,
  `sprint_length_days: int | null`, and explicit links to the connections it uses (or derive via
  the contained project/repo ids).
- Add the `SignalConfigGroup` entity (§5.12C). A `SignalDefinition` selects one canonical entity
  type in MVP and stores no connection, project, board, or repository references.
- Confirm `TeamProfile` is first-class and created during onboarding (supersedes the earlier
  "auto-seeded Default team" simplification).
- Add a required, workspace-unique `name` to `SourceConnection`, and remove all connection-level
  discovered selections: the Connections page manages access configuration only and the
  project/board selection lives in one team-owned board scope.
- Add `TeamProfile.code_connection_id: UUID | null` (§5.12) for the team's whole-connection code
  source; keep the board scope on `scope_ids`. A team may be saved with no sources; a report run
  requires at least one.

**UI pages ([architecture §12.1](./03-architecture-overview.md#121-mvp-ui-pages), backlog M2).**

- Add a **Dashboard** landing page (latest report per team).
- Add a **Teams** management page.
- The **Setup** page becomes the **Onboarding wizard** (Flow A).

**Backlog (GitHub Issues).**

- The pending change set already adds **M2-17** (normalized persistence + identity resolution),
  **M2-18** (team profiles), **M2-19** (connector registry + `GET /api/connectors`). These flows
  expand **M2-18** from "default team" to "multi-team onboarding wizard + Teams page", and add a
  **Dashboard** ticket.
- Milestone **M3.4** (connection & team source model) revises the already-implemented Connections and
  Teams screens to this flow: named access-only connections, a project/board scope +
  `code_connection_id` on the team, and the save-without-source / report-requires-source rule. It
  supersedes the connection-level scope introduced by the earlier M3 UI.
- Report-runner tickets (M1-08, M3-06, M4-06, M6-02) pass a real `team_profile_id` and derive
  the default window from the team's working mode; **M6-02** additionally blocks a run when the team
  has no sources.
- **M4-06** (GitLab connection UI) becomes create-and-test only (no repository picker, no run), and
  **M4-12** (onboarding wizard) follows the two-source team model.
- Engine gains **window-gating** of sprint-only signals (M5 area).

**Requirements ([02-requirements.md](./02-requirements.md)).**

- The added report sections (sprint health, source linking) align with the 9-section report
  decision; onboarding/dashboard behavior should be reflected in REQ-F-002 and the MVP
  acceptance checklist.
