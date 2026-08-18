# EM Radar — Requirements

## 1. Purpose

This document defines the functional and non-functional requirements for **EM Radar**.

EM Radar is a local-first engineering management signal engine that helps Engineering Managers detect planning, delivery, and code-review risks from tools such as Jira and GitLab.

This document separates:

* **MVP requirements**: required for the first useful release
* **Later requirements**: intentionally out of scope for MVP
* **Non-goals**: things the product should not do

---

## 2. MVP Definition

The MVP is complete when:

> An Engineering Manager can run EM Radar locally, connect to Jira and GitLab using personal access tokens, select a sprint or date range, run configurable deterministic signals, view an actionable report, and export it as Markdown.

The MVP must be useful without:

* AI
* cloud hosting
* enterprise deployment
* Slack/Teams integration
* Kubernetes
* multi-user support
* SSO
* GitHub support

---

## 3. User Roles

### 3.1 Engineering Manager

Primary user.

The Engineering Manager can:

* run EM Radar locally
* connect Jira and GitLab
* configure deterministic signals for work-tracking or code-repository entities
* run reports
* inspect findings
* export reports

### 3.2 Advanced User / Contributor

Secondary user.

The advanced user can:

* inspect configuration files
* import/export signal packs
* author and contribute signal definitions for the default pack (declarative, not code)
* develop additional connectors later

### 3.3 Enterprise Administrator

Future user, not part of MVP.

The enterprise administrator may later:

* deploy EM Radar centrally
* configure SSO
* manage users and permissions
* manage organization-wide connector settings
* manage approved signal packs

---

## 4. Functional Requirements

## 4.1 Local Application

### REQ-F-001 — Local Docker Deployment

**MVP**

The system shall be runnable locally using Docker.

Acceptance criteria:

* user can start the application with Docker Compose
* application exposes a local web UI
* application persists data across restarts using a local volume
* no external hosting account is required

---

### REQ-F-002 — Local Web UI

**MVP**

The system shall provide a browser-based UI.

The UI shall include at minimum:

* onboarding/setup wizard (guides connection setup and team creation; see [09-functional-flows §3](./09-functional-flows.md#3-flow-a--first-run-onboarding-wizard))
* dashboard (landing view showing the latest report per team)
* source connections page (connection management only: named access configuration; no scope or
  report actions)
* teams page (create/manage teams and their two sources: task-board scope + code connection)
* signal settings page
* report runner page
* report results page
* settings/privacy page

Acceptance criteria:

* user can complete MVP workflow through the UI
* user does not need to edit files manually for normal usage

---

### REQ-F-003 — Local Persistence

**MVP**

The system shall store local application data in SQLite by default.

Stored data includes:

* connector configuration
* team profiles, including each team's task-board scope, code connection, and attached signal config groups
* scope definitions for selected project/board pairs (the code source is a whole connection, not a
  repository scope, in MVP)
* signal definitions and signal config groups
* report history
* cached normalized source data
* local user preferences

Acceptance criteria:

* data survives container restart
* database file is stored in a mounted local volume
* PostgreSQL is not required for MVP

---

### REQ-F-004 — Optional PostgreSQL Support

**Later**

The system should support PostgreSQL for advanced or enterprise deployments.

This is not required for MVP.

---

## 4.2 Source Connections

### REQ-F-010 — Source Connector Framework

**MVP**

The system shall provide a connector framework that separates source-specific integrations from the core signal engine.

Acceptance criteria:

* signal engine does not directly call Jira or GitLab APIs
* connectors normalize source data into canonical EM Radar models
* fake/demo connector exists for testing and demonstration
* connector interfaces are documented

---

### REQ-F-011 — Jira Connector

**MVP**

The system shall provide a Jira connector.

The Jira connector shall support:

* Jira base URL configuration
* personal access token or API token configuration
* connection test
* project listing for team source selection
* board listing for team source selection where available
* sprint listing where available
* issue fetching
* epic/story relationship mapping
* configurable field mappings

Acceptance criteria:

* user can connect to Jira
* user can select a Jira project and board while configuring a team
* user can fetch issues for a sprint
* user can fetch issues for a custom date range
* fetched Jira issues are normalized into WorkItem objects

---

### REQ-F-012 — Jira Field Mapping

**MVP**

The system shall allow users to configure basic Jira field mappings.

Field mappings may include:

* epic link or parent
* sprint field
* story points
* acceptance criteria
* team field
* blocked status or blocked label

Acceptance criteria:

* user can configure field mappings through the UI
* field mapping changes persist across restarts
* missing optional fields do not break report generation

---

### REQ-F-013 — GitLab Connector

**MVP**

The system shall provide a GitLab connector.

The GitLab connector shall support:

* GitLab base URL configuration
* personal access token configuration
* connection test
* group or project selection
* merge request fetching
* reviewer and approval metadata
* pipeline status
* changed file count
* additions/deletions
* merge request state

Acceptance criteria:

* user can connect to GitLab
* user can select a group or project
* user can fetch merge requests for a date range
* fetched GitLab merge requests are normalized into MergeRequest objects

---

### REQ-F-014 — Jira Key Detection in Merge Requests

**MVP**

The system shall detect linked work item keys from GitLab merge requests.

The system shall inspect:

* merge request title
* merge request description
* source branch name

Acceptance criteria:

* user can configure the ticket key pattern
* default pattern supports common Jira keys such as `ABC-123`
* merge requests with detected keys are linked to matching WorkItems when available
* merge requests without detected keys can be reported as findings

---

### REQ-F-017 — Named Source Access Connections

**MVP**

The system shall let users create multiple named source connections, and the Source Connections page
shall create/manage connections only.

Each connection carries a user-provided **name** that is required and unique per workspace, so that
multiple connections of the same source type (for example two Jira instances, or a contractor working
across companies) are distinguishable. The Source Connections page creates, edits, tests, and deletes
connections. A connection stores its name, connector type, and connector-defined access
configuration only (for example URL, authentication fields, and TLS settings). It does not select
or store projects, boards, repositories, or other discovered source data, and it does not run
reports — those are team concerns (REQ-F-041A, REQ-F-050).

Acceptance criteria:

* a connection has a required name that is unique within the workspace
* a user can create several connections of the same source type with different names and credentials
* the connection form tests the connection and saves only its name, connector type, and
  connector-defined access configuration
* the Source Connections page has no project/board/repository picker and no run-report action
* connections are reusable across teams

---

### REQ-F-015 — GitHub Connector

**Later**

The system should support GitHub pull requests and issues.

This is not required for MVP.

---

### REQ-F-016 — Linear Connector

**Later**

The system may support Linear issues.

This is not required for MVP.

---

## 4.3 Canonical Data Model

### REQ-F-020 — WorkItem Model

**MVP**

The system shall define a source-agnostic WorkItem model.

The model shall support at minimum:

* ID
* source
* external ID
* key
* URL
* type
* title
* description
* status
* status category
* assignee
* reporter
* labels
* components
* created date
* updated date
* resolved date
* parent ID
* sprint IDs
* team ID
* project ID
* acceptance criteria
* story points

Acceptance criteria:

* Jira issues can be mapped to WorkItem
* signal engine only depends on WorkItem, not raw Jira issue objects

---

### REQ-F-021 — Sprint Model

**MVP**

The system shall define a source-agnostic Sprint model.

The model shall support at minimum:

* ID
* source
* external ID
* name
* state
* start date
* end date
* complete date
* board ID

Acceptance criteria:

* Jira sprints can be mapped to Sprint
* reports can be run for a selected Sprint

---

### REQ-F-022 — MergeRequest Model

**MVP**

The system shall define a source-agnostic MergeRequest model.

The model shall support at minimum:

* ID
* source
* external ID
* URL
* title
* description
* state
* author
* reviewers
* approvers
* created date
* updated date
* merged date
* closed date
* target branch
* source branch
* repository ID
* linked work item keys
* changed files count
* additions
* deletions
* pipeline status
* approval count
* comment count

Acceptance criteria:

* GitLab merge requests can be mapped to MergeRequest
* signal engine only depends on MergeRequest, not raw GitLab API responses

---

### REQ-F-023 — Evaluation Window Model

**MVP**

The system shall support evaluation windows.

Supported window types:

* sprint
* custom date range

Acceptance criteria:

* user can run a report for a sprint
* user can run a report for a custom date range
* signals receive a consistent EvaluationWindow object

---

### REQ-F-024 — SignalFinding Model

**MVP**

The system shall define a SignalFinding model.

A finding shall include:

* signal ID
* signal name
* severity
* confidence
* entity type
* entity ID
* title
* reason
* recommendation
* evidence
* created date
* source link where available

Acceptance criteria:

* every signal result produces structured evidence
* UI can display findings consistently
* reports can export findings to Markdown

---

## 4.4 Signal Engine

### REQ-F-030 — Deterministic Signal Evaluation

**MVP**

The system shall evaluate deterministic, rule-based signals.

Acceptance criteria:

* signal engine can run without AI
* signal engine can run against demo data
* signal engine can run against Jira/GitLab data
* signal output is stable and explainable

---

### REQ-F-031 — Default Pack Signals as Editable Definitions

**MVP**

The signals the system ships with are the contents of a **default signal pack**: ordinary
declarative signal definitions (structured field/operator/value rule expressions), seeded on first
run. They are not hard-coded engine features — see [REQ-F-036](#req-f-036--no-hardcoded-signals).

Users shall be able to:

* add shipped signals (or copies of them) to signal config groups
* duplicate signals
* edit signal conditions, thresholds, logical grouping, severity, and report category
* delete any signal, including a shipped default
* recreate any shipped signal from scratch using the same rule builder
* reset signal settings to defaults

Signals do not select connections, projects, boards, or repositories. In MVP each signal declares
one signal entity type: `issue` for the work-tracking domain or `merge_request` for the
code-repository domain. The team supplies the compatible source at report time — one
project/board pair for work tracking and/or one whole code connection — and runs the signals from
its attached signal config groups (see REQ-F-041C). Signal configuration is global per signal; to
run the same check with different thresholds, create two signals. A single signal combining both
domains is deferred until after MVP.

Acceptance criteria:

* signal settings can be changed through the UI
* changes persist after restart
* built-in templates can be duplicated and edited without changing the system default template
* validation rejects duplicate signal names in the local workspace
* validation requires exactly one supported entity type per MVP signal

---

### REQ-F-032 — Initial Jira Signals

**MVP**

The default signal pack shall include the following task-board (work-item) signal definitions. These
are declarative definitions seeded on first run, not engine-hardcoded checks; each can be edited,
deleted, or recreated in the UI:

1. stale in-progress work item
2. blocked item without recent update
3. story without acceptance criteria
4. story without parent epic
5. epic too broad
6. epic without measurable description
7. repeated carry-over
8. sprint scope churn

Acceptance criteria:

* each signal produces findings with reason, evidence, and recommendation
* each signal has configurable thresholds where relevant

---

### REQ-F-033 — Initial GitLab Signals

**MVP**

The default signal pack shall include the following code-source (merge-request) signal definitions.
As with the task-board signals, these are declarative definitions seeded on first run, not
engine-hardcoded checks; each can be edited, deleted, or recreated in the UI:

1. merge request waiting too long
2. merge request without linked work item
3. large merge request risk
4. failing pipeline too long
5. merged without enough approval

Acceptance criteria:

* each signal produces findings with reason, evidence, and recommendation
* each signal has configurable thresholds where relevant

---

### REQ-F-034 — User-defined Declarative Signals

**MVP**

The system shall allow users to create custom declarative signals through a constrained rule
builder.

Custom signals must be structured data, not executable code. The MVP builder shall support:

* field/operator/value conditions
* AND/OR logical groups
* one level of nested grouping
* date and duration comparisons
* sprint-aware conditions, evaluated only when the team's board scope supplies sprint data

Acceptance criteria:

* the UI only shows fields and operators available for the signal's selected entity type
* custom signal definitions are persisted and evaluated deterministically
* custom signal definitions can be exported and imported
* arbitrary scripting or expression-language execution is rejected

---

### REQ-F-035 — LLM-based Signals

**Later**

The system may support optional LLM-based signals.

Possible use cases:

* Definition of Ready checks
* vague ticket detection
* weak acceptance criteria detection
* epic split suggestions
* report summarization

This is not required for MVP.

---

### REQ-F-036 — No Hardcoded Signals

**MVP**

No signal shall be hard-coded into the engine. Every signal — including every signal in the default
pack — shall be a declarative definition the signal engine interprets, and shall be fully
reproducible through the Signal Settings page.

Acceptance criteria:

* the signal engine contains no per-signal code path; it evaluates rule expressions generically
* the default signal pack ships as declarative signal definitions (the same shape a user authors),
  seeded into the local database on first run
* every default-pack signal can be recreated from scratch in the rule builder using only fields,
  operators, values, logical grouping, severity, and category available in the UI
* the rule grammar and connector capability schemas are the single source of truth for what a signal
  can express; a shipped signal has no capability a user-authored signal lacks
* removing or editing a default-pack signal does not require a code change

---

## 4.5 Signal Configuration

### REQ-F-040 — Default Signal Config Group

**MVP**

The system shall include a default signal config group, seeded from the bundled default signal pack.
The group combines task-board and code-source signal definitions. Its signals are ordinary editable
definitions, not fixed engine features (see [REQ-F-036](#req-f-036--no-hardcoded-signals)).

Acceptance criteria:

* the default group is loaded on first startup by seeding the default signal pack
* the default group contains enough signals to produce useful reports
* default thresholds are documented
* every signal in the default group is editable, deletable, and recreatable from the UI

---

### REQ-F-041 — UI-based Signal Configuration

**MVP**

The system shall allow users to configure signals and signal config groups through the UI.

Acceptance criteria:

* user can see available signals
* user can create, duplicate, edit, and delete user-created signals
* user can edit conditions with field/operator/value controls
* user can preview a signal before saving it
* user can reset to defaults
* the signal builder has no connection, project, board, or repository picker
* each MVP signal is built for one entity type in either the work-tracking or code-repository domain

---

### REQ-F-041A — Team-owned Sources

**MVP**

The system shall store sources separately from connectors and signals, and attach them to a team. A
team carries up to two sources: a **task-board source** (a Jira board, 0..1, stored as a
`ScopeDefinition`) and a **code source** (a whole GitLab/GitHub connection, 0..1, stored as
`TeamProfile.code_connection_id`). Both are resolved from the team at report time; signals never
reference sources.

The task-board source is chosen via a searchable project → board picker from connector-provided
options. One board `ScopeDefinition` persists both selections in `external_ref`: the selected
project identity and the selected board identity. Neither selection is stored on the
`SourceConnection`. The code source attaches the whole connection — every repository the token can
access is in scope; per-repository selection is a later phase. A team may be **saved with no
sources**, but a **report run requires at least one source** (see REQ-F-050); signals whose source is
absent are skipped with a note.

Acceptance criteria:

* connectors represent access to external systems, not signal applicability
* users can select a team's board scope from connector-provided options (searchable project + board)
* the team's board scope stores both project and board identity in one `ScopeDefinition.external_ref`
* users can attach a whole GitLab/GitHub connection as the team's code source
* a team can be saved with no sources; a report run is blocked when the team has no sources
* a team's report runs against the team's attached sources
* reports include the scope name for each finding

---

### REQ-F-041C — Reusable Signal Config Groups

**MVP**

The system shall provide reusable signal config groups: named bundles of signals that the user
attaches to teams.

A signal config group is many-to-many with both teams (one group may be attached to many teams) and
signals (one signal may belong to many groups). A group carries no connector, scope, or credential.

Acceptance criteria:

* users can create, rename, and delete signal config groups
* users can add and remove signals from a group; a signal may live in several groups
* users can attach and detach groups from a team
* a team's evaluated signals are the union of signals across its attached groups
* editing a group propagates to every team it is attached to

---

### REQ-F-041B — Connector Capability Schema

**MVP**

Each connector shall expose a capability schema used by the signal builder and importer.

The schema shall describe:

* supported entity types
* supported fields
* valid operators per field
* static or dynamic value providers
* field availability constraints, such as sprint-only fields

Scope discovery for team configuration is provided separately by connector `list_*` methods; it is
not part of signal applicability.

Acceptance criteria:

* the signal builder is generated from connector capabilities instead of hardcoding Jira-specific
  behavior
* invalid field/operator combinations are blocked before save
* imported public templates are validated against the available capability schemas for their
  declared entity type

---

### REQ-F-042 — YAML Export

**MVP**

The system shall allow users to export a signal config group as YAML in two modes:

* private backup or migration export
* public template export

Acceptance criteria:

* a YAML export contains the group's signals and their report settings — no connectors, scopes, or teams
* private backup export keeps organization-specific condition values (e.g. concrete label or status names)
* public template export prompts the user to review and scrub organization-specific condition values
* exported YAML contains no credentials
* public template exports can be stored in version control if the user chooses

---

### REQ-F-043 — YAML Import

**MVP**

The system shall allow users to import private backup YAML and public template YAML.

Acceptance criteria:

* importing a YAML pack creates a new signal config group (name suffixed on collision)
* the user attaches the new group to teams after import; no connector or scope mapping step is required
* imports validate field/operator/value compatibility against connector capability schemas
* invalid YAML is rejected with a clear error
* credentials cannot be imported through signal config
* user can review or confirm import before applying, if feasible

---

### REQ-F-044 — Community Signal Packs

**Later**

The system should support community signal packs.

Potential capabilities:

* import from URL
* preview pack contents
* view author and version
* star or rate packs
* browse official and community packs

This is not required for MVP.

---

## 4.6 Report Runner

### REQ-F-050 — Sprint Report

**MVP**

The system shall allow users to run a sprint report for one or more selected teams.

Acceptance criteria:

* user can select one or more teams
* for each team, the system uses the team's attached sources — board scope + code connection — with no separate board picker
* a team with no sources attached cannot run a report (the run is blocked with a clear message)
* user can select a sprint (scrum teams default to the active sprint)
* system fetches relevant Jira and GitLab data
* system evaluates each team's signals (the union across its attached signal config groups); signals whose source is absent are skipped
* system displays report results per team

---

### REQ-F-051 — Date-range Report

**MVP**

The system shall allow users to run a date-range report for one or more selected teams.

Acceptance criteria:

* user can select one or more teams and a start and end date
* for each team, the system uses the team's attached sources (board scope + code connection)
* a team with no sources attached cannot run a report
* system fetches relevant Jira and GitLab data for that range
* system evaluates each team's signals (the union across its attached signal config groups)
* system displays report results per team

---

### REQ-F-052 — Report Sections

**MVP**

The generated report shall group findings into sections.

Initial sections:

* summary
* top risks
* planning hygiene
* delivery flow
* sprint health
* merge request flow
* source linking
* detailed findings
* suggested actions

These nine sections map 1:1 to the five signal categories plus the cross-cutting
summary/top-risks/detailed/suggested-actions sections (planning hygiene, delivery flow, sprint
health, merge request flow, source linking — see [architecture §10.3](./03-architecture-overview.md#103-mvp-signal-categories)).

Acceptance criteria:

* findings are grouped in a readable way
* severe findings are easy to identify
* report links back to source items where available

---

### REQ-F-053 — Markdown Export

**MVP**

The system shall allow users to export a report as Markdown.

Acceptance criteria:

* exported Markdown includes report metadata
* exported Markdown includes grouped findings
* exported Markdown includes source links where available
* exported Markdown can be copied into notes, Confluence, or documents

---

### REQ-F-054 — JSON Export

**Later**

The system may allow users to export report data as JSON.

This is not required for MVP.

---

### REQ-F-055 — PDF Export

**Later**

The system may allow users to export reports as PDF.

This is not required for MVP.

---

## 4.7 Destination Connectors

### REQ-F-060 — Slack Connector

**Later**

The system may send reports or summaries to Slack.

This is not required for MVP.

---

### REQ-F-061 — Microsoft Teams Connector

**Later**

The system may send reports or summaries to Microsoft Teams.

This is not required for MVP.

---

### REQ-F-062 — Email Connector

**Later**

The system may send reports by email.

This is not required for MVP.

---

### REQ-F-063 — Confluence Connector

**Later**

The system may publish reports to Confluence.

This is not required for MVP.

---

## 4.8 AI Connector

### REQ-F-070 — Optional AI Provider Framework

**Later**

The system should support optional AI providers through an external connector interface.

This is not required for MVP.

---

### REQ-F-071 — Claude Connector

**Later**

The first AI connector should support Claude API.

This is not required for MVP.

---

### REQ-F-072 — AI Disabled by Default

**Later**

When AI features are introduced, they must be disabled by default.

Acceptance criteria:

* user must explicitly enable AI
* UI explains what data may be sent
* user can disable AI at any time

---

## 5. Non-functional Requirements

## 5.1 Privacy & Data Protection

### REQ-NF-001 — Local-first Data Storage

**MVP**

The system shall store data locally by default.

Acceptance criteria:

* Jira/GitLab data is stored on the user’s machine
* reports are stored on the user’s machine
* credentials are stored on the user’s machine
* no external service is required for MVP

---

### REQ-NF-002 — No Telemetry by Default

**MVP**

The system shall not send telemetry by default.

Acceptance criteria:

* telemetry is disabled unless explicitly enabled
* no source data is sent to project maintainers
* no usage data is sent without consent

---

### REQ-NF-003 — Credential Safety

**MVP**

The system shall handle credentials safely.

Acceptance criteria:

* tokens are masked in UI
* tokens are never logged
* tokens are excluded from config exports
* logs do not contain Authorization headers
* documentation recommends read-only tokens where possible

---

### REQ-NF-004 — Data Deletion

**MVP**

The system shall allow users to delete local data.

Acceptance criteria:

* user can delete source connection
* user can delete cached source data
* user can delete report history
* user can remove local database volume manually using documented steps

---

### REQ-NF-005 — AI Data Protection

**Later**

When AI features are introduced, the system shall clearly disclose what data may be sent to configured AI providers.

This is not required for MVP.

---

## 5.2 Security

### REQ-NF-010 — Local-only Default Exposure

**MVP**

The application shall bind to localhost by default where feasible.

Acceptance criteria:

* default configuration is suitable for local personal use
* documentation warns users before exposing the app on a network
* production/enterprise exposure requires explicit configuration

---

### REQ-NF-011 — Read-only Source Access

**MVP**

The MVP shall only read from Jira and GitLab.

Acceptance criteria:

* system does not create, update, or delete Jira issues
* system does not comment on or modify GitLab merge requests
* documentation lists minimum required permissions

---

### REQ-NF-012 — No Arbitrary Code Execution in Config

**MVP**

Signal configuration shall not execute arbitrary user code.

Acceptance criteria:

* YAML import cannot execute code
* community configs, when introduced, must be declarative only

---

### REQ-NF-013 — Basic Input Validation

**MVP**

The system shall validate user inputs.

Acceptance criteria:

* invalid URLs are rejected
* invalid tokens fail connection tests clearly
* invalid date ranges are rejected
* invalid YAML config is rejected
* API returns structured errors

---

## 5.3 Performance

### REQ-NF-020 — Local MVP Performance

**MVP**

The system shall perform acceptably for a typical EM team scope.

Target MVP data size:

* up to 3 Jira projects
* up to 10 repositories
* up to 500 work items in an evaluation window
* up to 300 merge requests in an evaluation window

Acceptance criteria:

* report generation completes within 60 seconds for target MVP data size on a modern laptop
* UI remains responsive during report generation
* long-running fetch/evaluation shows progress or clear loading state

---

### REQ-NF-021 — Caching

**MVP**

The system should cache fetched source data locally.

Acceptance criteria:

* repeated reports do not always require full refetch
* user can refresh data manually
* user can delete cached data

---

### REQ-NF-022 — Larger Scale Performance

**Later**

The system should support larger organization-level usage.

Possible future target:

* dozens of teams
* hundreds of repositories
* tens of thousands of work items
* scheduled report generation

This is not required for MVP.

---

## 5.4 Offline Behavior

### REQ-NF-030 — Offline Report Viewing

**MVP**

The system shall allow users to view previously generated reports offline.

Acceptance criteria:

* existing reports are available without Jira/GitLab connectivity
* cached findings can be viewed locally

---

### REQ-NF-031 — Offline Report Generation from Cache

**Later**

The system may allow users to generate new reports from cached data while offline.

This is not required for MVP.

---

### REQ-NF-032 — Source Connectivity Required for Fresh Data

**MVP**

The system shall require connectivity to Jira/GitLab to fetch fresh data.

Acceptance criteria:

* user receives clear error if source system is unavailable
* user can still view previous reports

---

## 5.5 Cross-platform Support

### REQ-NF-040 — Docker-based Cross-platform Support

**MVP**

The system shall support local execution through Docker on common operating systems.

Target platforms:

* macOS
* Windows
* Linux

Acceptance criteria:

* documented Docker Compose setup works on macOS
* documented Docker Compose setup works on Windows with Docker Desktop
* documented Docker Compose setup works on Linux with Docker Engine

---

### REQ-NF-041 — Browser Compatibility

**MVP**

The UI shall support modern browsers.

Target browsers:

* Chrome
* Edge
* Firefox
* Safari

Acceptance criteria:

* core workflow works in latest stable versions of target browsers

---

### REQ-NF-042 — Native Desktop Application

**Later**

The system may provide a native desktop wrapper.

This is not required for MVP.

---

## 5.6 Usability

### REQ-NF-050 — Non-coding EM Usability

**MVP**

The system shall be usable by an Engineering Manager who is comfortable with Docker but does not actively code.

Acceptance criteria:

* setup is documented step-by-step
* normal usage does not require editing YAML
* token setup is explained clearly
* source connection errors are understandable
* signal settings use plain language

---

### REQ-NF-051 — Clear Findings

**MVP**

Findings shall be understandable without reading source code.

Acceptance criteria:

* every finding includes a human-readable reason
* every finding includes evidence
* every finding includes a recommended action
* every finding links to the source item where available

---

### REQ-NF-052 — Avoid Surveillance Framing

**MVP**

The product shall avoid individual productivity scoring.

Acceptance criteria:

* reports focus on work, flow, planning, and risk
* product language avoids ranking developers
* no “developer score” feature exists
* no leaderboard exists

---

## 5.7 Maintainability

### REQ-NF-060 — Modular Architecture

**MVP**

The system shall keep core engine, connectors, configuration, reporting, and UI concerns separated.

Acceptance criteria:

* signal engine can run against demo data without Jira/GitLab
* connectors can be developed independently
* new signals can be added without changing connector code
* new connectors can be added without changing signal logic

---

### REQ-NF-061 — Documented Extension Points

**MVP**

The project shall document how to extend the system.

Acceptance criteria:

* connector interface is documented
* signal structure is documented
* configuration format is documented
* contribution guide exists

---

### REQ-NF-062 — Automated Tests

**MVP**

The system shall include automated tests for core logic.

Minimum tests:

* canonical model validation
* signal evaluation
* configuration import/export
* Jira normalization
* GitLab normalization

Acceptance criteria:

* core signal engine has meaningful unit tests
* connector normalizers have tests using fixture data
* tests can run locally

---

## 5.8 Reliability

### REQ-NF-070 — Graceful Source Failure

**MVP**

The system shall handle source-system failures gracefully.

Acceptance criteria:

* Jira connection failure does not crash the app
* GitLab connection failure does not crash the app
* partial data errors are shown clearly
* report generation can fail with a useful error message

---

### REQ-NF-071 — Safe Defaults

**MVP**

The system shall ship with safe defaults.

Acceptance criteria:

* no telemetry
* no write access
* no external AI
* no public network exposure by default
* no credentials in exports

---

## 6. MVP Signal Requirements

## 6.1 Stale In-progress Work Item

**MVP**

Detect work items that are in progress and have not been updated for a configurable number of days.

Default threshold:

* 7 days

Finding should include:

* work item key
* title
* status
* assignee
* last updated date
* threshold
* source link

---

## 6.2 Blocked Item Without Recent Update

**MVP**

Detect blocked work items that have not been updated for a configurable number of days.

Default threshold:

* 3 days

Finding should include:

* work item key
* title
* blocked status or label
* assignee
* last updated date
* source link

---

## 6.3 Story Without Acceptance Criteria

**MVP**

Detect story-type work items missing acceptance criteria.

Finding should include:

* work item key
* title
* issue type
* source link

---

## 6.4 Story Without Parent Epic

**MVP**

Detect story-type work items without a parent epic.

Finding should include:

* work item key
* title
* sprint
* source link

---

## 6.5 Epic Too Broad

**MVP**

Detect epics with more than a configurable number of child items.

Default threshold:

* 15 child items

Finding should include:

* epic key
* title
* child count
* threshold
* source link

---

## 6.6 Epic Without Measurable Description

**MVP**

Detect epics with missing or too-short descriptions.

Default threshold:

* fewer than 100 characters

Finding should include:

* epic key
* title
* description length
* threshold
* source link

---

## 6.7 Repeated Carry-over

**MVP**

Detect work items that have appeared in multiple sprints without completion.

Default threshold:

* 2 or more sprints

Finding should include:

* work item key
* title
* sprint count
* current status
* source link

---

## 6.8 Sprint Scope Churn

**MVP**

Detect significant scope changes after sprint start.

Default threshold:

* warning: 20% added after sprint start

The default pack ships this as a single signal with a fixed severity, so it stays expressible in the
standard rule grammar (no self-escalating severity). An EM who wants a stricter tier simply creates a
second signal (e.g. 35% → critical) in the builder — exactly as any user would.

Finding should include:

* sprint name
* original item count
* added item count
* churn percentage

---

## 6.9 Merge Request Waiting Too Long

**MVP**

Detect open merge requests older than a configurable number of days.

Default threshold:

* 3 days

Finding should include:

* MR title
* author
* reviewers
* age
* source link

---

## 6.10 Merge Request Without Linked Work Item

**MVP**

Detect merge requests without a detectable work item key.

Finding should include:

* MR title
* source branch
* author
* source link

---

## 6.11 Large Merge Request Risk

**MVP**

Detect merge requests that exceed configurable size thresholds.

Default thresholds:

* more than 20 changed files
* or more than 500 total line changes

Finding should include:

* MR title
* changed file count
* additions
* deletions
* source link

---

## 6.12 Failing Pipeline Too Long

**MVP**

Detect merge requests with failing pipelines for longer than a configurable threshold.

Default threshold:

* 1 day

Finding should include:

* MR title
* pipeline status
* last updated date
* source link

---

## 6.13 Merged Without Enough Approval

**MVP**

Detect merge requests merged with fewer approvals than configured.

Default threshold:

* fewer than 1 approval

Finding should include:

* MR title
* approval count
* merged date
* source link

---

## 7. Later-stage Requirements

The following are explicitly out of scope for MVP.

### 7.1 Community Config Marketplace

Later capability for:

* publishing signal packs
* browsing packs
* starring packs
* importing packs from URL
* official/verified pack distinction

---

### 7.2 AI-assisted Analysis

Later capability for:

* Definition of Ready checks
* description clarity checks
* acceptance criteria quality checks
* report summarization
* suggested epic splits

---

### 7.3 Destination Connectors

Later capability for:

* Slack
* Microsoft Teams
* email
* Confluence

---

### 7.4 Enterprise Deployment

Later capability for:

* central server deployment
* PostgreSQL
* SSO/OIDC
* RBAC
* audit logging
* private config registry
* Helm chart

---

### 7.5 Additional Source Systems

Later capability for:

* GitHub
* Linear
* Azure DevOps
* Bitbucket
* Shortcut

---

## 8. Non-goals

EM Radar shall not:

* rank individual developers
* create developer productivity scores
* create leaderboards
* replace Engineering Manager judgment
* replace team conversations
* become a generic BI tool
* require cloud hosting
* require Kubernetes for personal use
* send data to AI providers by default
* require enterprise approval for local personal usage
* write back to Jira or GitLab in MVP

---

## 9. Open Questions

The following questions remain open and should be resolved before or during Phase 1 implementation.

### 9.1 Credential Storage

Should MVP store tokens:

* directly in SQLite
* encrypted in SQLite
* in environment variables
* in local OS keychain where available
* using Docker secrets

Initial recommendation:

> Store tokens locally, mask them everywhere, exclude them from export, and design for stronger encryption later.

---

### 9.2 UI and Backend Packaging

Should MVP run as:

* one container with backend serving frontend
* two containers: backend and frontend
* desktop wrapper later

Initial recommendation:

> Use one container for MVP simplicity.

---

### 9.3 Report History Retention

How long should reports and cached data be retained?

Initial recommendation:

> Keep indefinitely by default, but allow manual deletion.

---

### 9.4 Jira Field Mapping Complexity

How much field mapping should be UI-driven in MVP?

Initial recommendation:

> Support basic UI mapping for common fields, and allow advanced mapping later.

---

### 9.5 Community Config Format

Should the config format be optimized for human readability, strict validation, or future marketplace compatibility?

Initial recommendation:

> Use readable YAML with strict schema validation.

---

## 10. MVP Acceptance Checklist

The MVP is ready when all of the following are true:

* [ ] Application runs locally with Docker Compose
* [ ] SQLite persistence works
* [ ] Onboarding wizard guides connection + team setup; user can create one or more teams
* [ ] Dashboard shows the latest report per team
* [ ] UI supports setup, connections, teams, signal settings, and reports
* [ ] Jira connector works
* [ ] GitLab connector works
* [ ] Canonical model is implemented
* [ ] Signal engine runs without source-specific dependencies and has no per-signal hardcoded logic
* [ ] Default pack ships at least 8 task-board (Jira/work-item) signal definitions
* [ ] Default pack ships at least 5 code-source (GitLab/merge-request) signal definitions
* [ ] Signals are configurable from UI
* [ ] Every default-pack signal can be recreated from scratch in the UI rule builder
* [ ] Sprint report works
* [ ] Date-range report works
* [ ] Markdown export works
* [ ] Tokens are masked
* [ ] Tokens are excluded from config export
* [ ] No telemetry is sent by default
* [ ] Documentation explains local-first privacy model
* [ ] Setup is usable by an EM comfortable with Docker
