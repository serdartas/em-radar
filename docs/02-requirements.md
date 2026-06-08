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
* configure signal thresholds
* run reports
* inspect findings
* export reports

### 3.2 Advanced User / Contributor

Secondary user.

The advanced user can:

* inspect configuration files
* import/export signal packs
* contribute new built-in signals
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
* source connections page
* teams page (create/manage teams and their scope)
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
* selected projects/boards/repositories
* signal settings
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
* project selection
* board selection where available
* sprint listing where available
* issue fetching
* epic/story relationship mapping
* configurable field mappings

Acceptance criteria:

* user can connect to Jira
* user can select a Jira project or board
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

### REQ-F-031 — Configurable Built-in Signals

**MVP**

The system shall provide built-in signals with configurable thresholds.

Users shall be able to:

* enable signals
* disable signals
* modify thresholds
* modify severity where supported
* reset signal settings to defaults

Acceptance criteria:

* signal settings can be changed through the UI
* changes persist after restart
* disabled signals are not evaluated

---

### REQ-F-032 — Initial Jira Signals

**MVP**

The system shall include the following Jira/work-item signals:

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
* each signal can be enabled or disabled
* each signal has configurable thresholds where relevant

---

### REQ-F-033 — Initial GitLab Signals

**MVP**

The system shall include the following GitLab/merge-request signals:

1. merge request waiting too long
2. merge request without linked work item
3. large merge request risk
4. failing pipeline too long
5. merged without enough approval

Acceptance criteria:

* each signal produces findings with reason, evidence, and recommendation
* each signal can be enabled or disabled
* each signal has configurable thresholds where relevant

---

### REQ-F-034 — User-defined Declarative Signals

**Later**

The system should allow users to define custom declarative signals using configuration.

This is not required for MVP.

When implemented, custom signals must be declarative and must not execute arbitrary code.

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

## 4.5 Signal Configuration

### REQ-F-040 — Default Signal Pack

**MVP**

The system shall include a default signal pack.

Acceptance criteria:

* default pack is loaded on first startup
* default pack enables enough signals to produce useful reports
* default thresholds are documented

---

### REQ-F-041 — UI-based Signal Configuration

**MVP**

The system shall allow users to configure signals through the UI.

Acceptance criteria:

* user can see available signals
* user can enable or disable signals
* user can edit thresholds
* user can reset to defaults

---

### REQ-F-042 — YAML Export

**MVP**

The system shall allow users to export signal configuration as YAML.

Acceptance criteria:

* exported YAML contains signal settings
* exported YAML contains no credentials
* exported YAML can be stored in version control if the user chooses

---

### REQ-F-043 — YAML Import

**MVP**

The system shall allow users to import signal configuration from YAML.

Acceptance criteria:

* imported YAML updates signal settings
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

The system shall allow users to run a report for a selected sprint.

Acceptance criteria:

* user can select a configured Jira board/project
* user can select a sprint
* system fetches relevant Jira and GitLab data
* system evaluates enabled signals
* system displays report results

---

### REQ-F-051 — Date-range Report

**MVP**

The system shall allow users to run a report for a custom date range.

Acceptance criteria:

* user can select start and end date
* system fetches relevant Jira and GitLab data for that range
* system evaluates enabled signals
* system displays report results

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

Default thresholds:

* warning: 20% added after sprint start
* critical: 35% added after sprint start

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
* [ ] Signal engine runs without source-specific dependencies
* [ ] At least 8 Jira/work-item signals exist
* [ ] At least 5 GitLab/merge-request signals exist
* [ ] Signals are configurable from UI
* [ ] Sprint report works
* [ ] Date-range report works
* [ ] Markdown export works
* [ ] Tokens are masked
* [ ] Tokens are excluded from config export
* [ ] No telemetry is sent by default
* [ ] Documentation explains local-first privacy model
* [ ] Setup is usable by an EM comfortable with Docker
