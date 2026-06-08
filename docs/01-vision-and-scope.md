# EM Radar — Vision & Scope

## 1. Vision

**EM Radar** is a local-first engineering management signal engine that helps Engineering Managers detect planning, delivery, and code-review risks from tools like Jira, GitLab, and GitHub.

The goal is not to create another generic dashboard. The goal is to help EMs answer a practical question:

> What should I pay attention to before this becomes a delivery, quality, or team-health problem?

EM Radar runs locally by default, connects to the tools an EM already uses, evaluates configurable signals, and produces actionable reports for sprint reviews, planning, one-on-ones, leadership updates, and team health checks.

The long-term ambition is to become an open-source standard for Engineering Management signals: a tool and community where EMs can share, improve, and reuse practical signal configurations.

---

## 2. Problem Statement

Engineering Managers are surrounded by operational data, but most of it is scattered across systems:

* Jira tickets
* GitLab/GitHub merge requests
* sprint boards
* epics and initiatives
* code review activity
* delivery status updates
* team rituals and planning processes

Existing engineering analytics tools often focus on executive dashboards, productivity metrics, or developer activity tracking. They are frequently too broad, too expensive, too company-controlled, or too disconnected from the day-to-day decisions an EM needs to make.

Many EMs still manually inspect Jira boards, sprint reports, stale tickets, merge requests, carry-over items, and vague epics before meetings. This is repetitive, inconsistent, and easy to miss.

EM Radar exists to turn this operational noise into useful signals.

---

## 3. Product Principles

### 3.1 Local-first

The default usage model is local.

An EM should be able to run EM Radar on their own machine using Docker or a similar local runtime.

By default:

* data stays local
* tokens stay local
* reports stay local
* telemetry is disabled
* no company data is sent to an external SaaS

This lowers adoption friction and increases trust.

---

### 3.2 Rules-first, AI-optional

The first version of EM Radar is deterministic and rule-based.

Most useful EM signals do not require an LLM:

* stale work
* missing acceptance criteria
* broad epics
* repeated sprint carry-over
* scope churn
* merge requests waiting too long
* failing pipelines
* unlinked merge requests

AI may become useful later for text-heavy analysis, such as comparing ticket descriptions against a Definition of Ready. However, AI must remain optional and external to the core engine.

---

### 3.3 Source-agnostic core

The core signal engine must not depend directly on Jira, GitLab, GitHub, Linear, or any specific company setup.

Source systems are accessed through connectors. Connectors normalize external data into EM Radar’s canonical model.

This enables the same engine to work with multiple tools and allows companies to create private internal adapters without changing the core.

---

### 3.4 Configurable signals

EMs should be able to:

* enable or disable signals
* modify thresholds
* tune severity
* import/export signal configurations
* eventually share reusable signal packs with the community

Configuration should be editable through the UI, not only through files.

---

### 3.5 Actionable over analytical

EM Radar should avoid vanity metrics.

A finding is useful only if it helps an EM decide what to inspect, discuss, challenge, or improve.

Every signal should aim to provide:

* what was detected
* why it matters
* supporting evidence
* suggested action
* link to the original source item

---

### 3.6 Community-configurable

The long-term value of EM Radar is not only the software. It is also the shared knowledge of how EMs detect risk.

The project should support reusable configuration packs, such as:

* Scrum Team Health Pack
* Kanban Flow Pack
* Platform Team Pack
* Jira Hygiene Pack
* Tech Debt Radar Pack
* AI Coding Readiness Pack
* Quarterly Planning Readiness Pack

Community signal packs should be declarative and safe to import.

---

## 4. Target Users

### 4.1 Primary User

The primary user is a hands-on Engineering Manager who:

* works with Jira, GitLab, GitHub, or similar tools
* wants better visibility into delivery and planning risks
* is comfortable running a local Docker container
* may not have coded actively for years
* does not want to wait for enterprise tooling approval
* values practical reports over dashboards full of metrics

---

### 4.2 Secondary Users

Secondary users may include:

* Lead Engineers
* Group Product Managers
* Heads of Engineering
* Delivery Managers
* Platform teams
* Engineering Operations teams

However, the first version should optimize for the individual EM, not enterprise leadership.

---

## 5. Positioning

### Short Positioning

> Local-first engineering management signals from Jira, GitLab, and GitHub.

### Expanded Positioning

> EM Radar helps Engineering Managers detect delivery, planning, and code-review risks by analyzing data from tools like Jira and GitLab. It runs locally, keeps data under the user’s control, and produces actionable reports for sprint reviews, planning, and leadership conversations.

### What EM Radar Is

EM Radar is:

* a local-first EM support tool
* a signal engine
* a reporting tool
* a configurable rule engine
* a connector-based integration platform
* an open-source project
* a future community for EM signal packs

### What EM Radar Is Not

EM Radar is not:

* a developer surveillance tool
* a productivity scoring system
* a replacement for human judgment
* an enterprise BI dashboard
* an AI-first product
* a generic Jira reporting tool
* a system that tells EMs what to do without evidence

---

## 6. Core Use Cases

### 6.1 Sprint Health Report

An EM selects a Jira sprint and generates a report showing:

* stale in-progress work
* blocked items without recent updates
* stories missing acceptance criteria
* repeated carry-over
* scope churn
* epics that are too broad
* merge requests waiting too long
* failing pipelines
* unlinked merge requests

---

### 6.2 Custom Date Range Report

An EM selects a date range and generates a report independent of a sprint.

This is useful for:

* Kanban teams
* monthly reviews
* quarterly planning
* leadership updates
* personal team health checks
* retrospective preparation

---

### 6.3 Jira Hygiene Review

An EM generates a report focused on planning quality:

* stories without acceptance criteria
* stories without parent epics
* stale epics
* overly broad epics
* unclear descriptions
* items stuck in progress
* blocked items without ownership

---

### 6.4 Merge Request Flow Review

An EM generates a report focused on code-review flow:

* merge requests open too long
* merge requests without linked work items
* large merge requests
* failing pipelines
* merged items with insufficient review
* stale review activity

---

### 6.5 Weekly EM Radar Report

An EM generates a weekly summary that answers:

> What are the top risks I should look at this week?

The output should be usable for:

* weekly team check-ins
* EM/PM/LE syncs
* leadership updates
* one-on-one preparation
* retro preparation

---

## 7. Phase 1 Scope

Phase 1 is the first coded MVP.

The goal of Phase 1 is:

> An EM can run EM Radar locally, connect to Jira and GitLab, configure basic signals, run a sprint or date-range report, and export the result.

---

### 7.1 Included in Phase 1

Phase 1 includes:

* local Docker-based deployment
* database local persistence
* backend API
* frontend UI shell
* canonical data model
* configuration store
* Jira connector MVP
* GitLab connector MVP
* source connector framework
* deterministic signal engine
* configurable built-in signals
* sprint report
* date-range report
* Markdown export
* basic privacy and token-safety handling

---

### 7.2 Excluded from Phase 1

Phase 1 excludes:

* LLM-based analysis
* Claude/OpenAI/Ollama connectors
* Slack/Teams/Confluence destination connectors
* scheduled reports
* hosted SaaS
* enterprise SSO
* RBAC
* multi-user support
* Kubernetes Helm chart
* marketplace website
* GitHub connector
* Linear connector
* predictive analytics
* automated ticket creation
* write-back to Jira or GitLab

---

## 8. Phase 1 Epics

### Epic 1 — Local App Foundation

Create the runnable local application foundation.

Scope:

* FastAPI backend
* React/Vite frontend
* Database persistence
* Dockerfile
* Docker Compose
* `/data` volume
* health check endpoint
* basic UI navigation

Outcome:

> User can run the app locally and open the UI in a browser.

---

### Epic 2 — Canonical Data Model

Define the normalized internal model used by the signal engine.

Core entities:

* WorkItem
* Sprint
* MergeRequest
* Repository
* TeamProfile
* EvaluationWindow
* SignalFinding
* Report

Outcome:

> Jira and GitLab data can be transformed into consistent internal objects.

---

### Epic 3 — Configuration Store & Signal Settings

Store signal configuration in the local database and allow users to edit it through the UI.

Scope:

* default signal pack seeding
* enable/disable signals
* threshold editing
* severity configuration
* YAML import/export
* reset to defaults
* credentials excluded from exports

Outcome:

> EMs can configure signals without editing files inside containers.

---

### Epic 4 — Source Connector Framework

Create provider interfaces and connector abstractions.

Scope:

* WorkItemProvider
* SprintProvider
* MergeRequestProvider
* RepositoryProvider
* connector registry
* fake/demo connector
* connector documentation

Outcome:

> The signal engine can use normalized data without knowing which source system it came from.

---

### Epic 5 — Jira Connector MVP

Connect to Jira and fetch work items, boards, sprints, and issue relationships.

Scope:

* Jira base URL
* personal access token
* connection test
* project/board selection
* sprint listing
* issue fetching
* epic/story relationship mapping
* configurable field mappings
* normalization into WorkItem and Sprint models

Outcome:

> EMs can run planning and delivery signals against Jira data.

---

### Epic 6 — GitLab Connector MVP

Connect to GitLab and fetch merge request activity.

Scope:

* GitLab base URL
* personal access token
* connection test
* group/project selection
* merge request fetching
* approval/reviewer metadata
* pipeline status
* changed file and line counts
* Jira key extraction from title, branch, and description
* normalization into MergeRequest model

Outcome:

> EMs can run code-review and merge-flow signals against GitLab data.

---

### Epic 7 — Signal Engine MVP

Implement the first deterministic signals.

Initial Jira signals:

* stale in-progress work item
* blocked item without recent update
* story without acceptance criteria
* story without parent epic
* epic too broad
* epic without measurable description
* repeated carry-over
* sprint scope churn

Initial GitLab signals:

* merge request waiting too long
* merge request without linked work item
* large merge request risk
* failing pipeline too long
* merged without enough approval

Outcome:

> EM Radar can produce actionable findings from normalized Jira and GitLab data.

---

### Epic 8 — Report Runner & UI Reports

Allow users to run and view reports.

Scope:

* team/profile selection
* sprint selection
* custom date range selection
* report execution
* report persistence
* grouped findings
* links to source items
* Markdown export

Outcome:

> EMs can generate and use a practical EM Radar report.

---

### Epic 9 — Basic Security & Privacy Hardening

Make local-first usage trustworthy.

Scope:

* mask tokens in UI
* never log tokens
* exclude credentials from exports
* recommend read-only tokens
* document required permissions
* allow deleting connections and cached data
* telemetry disabled by default

Outcome:

> EMs can safely use EM Radar locally with personal access tokens.

---

## 9. Canonical Concepts

### 9.1 WorkItem

A normalized representation of an item from a planning or ticketing system.

Examples:

* Jira story
* Jira task
* Jira bug
* Jira epic
* GitHub issue
* Linear issue

---

### 9.2 MergeRequest

A normalized representation of a code-change request.

Examples:

* GitLab merge request
* GitHub pull request
* Bitbucket pull request

---

### 9.3 Signal

A rule or detector that identifies a possible risk, smell, or condition worth attention.

Examples:

* stale work item
* story without acceptance criteria
* large merge request
* sprint scope churn

---

### 9.4 Finding

A specific result produced by a signal.

A finding should include:

* signal ID
* severity
* confidence
* affected entity
* reason
* evidence
* recommendation
* source link

---

### 9.5 Evaluation Window

The period or scope over which signals are evaluated.

Supported windows:

* sprint
* custom date range

---

### 9.6 Signal Pack

A reusable configuration bundle containing enabled signals, thresholds, views, and assumptions.

Examples:

* Scrum Team Health Pack
* Kanban Flow Pack
* Jira Hygiene Pack

---

## 10. Configuration Strategy

EM Radar should use a hybrid configuration model.

### Default Configuration

Default signals and thresholds are bundled with the app.

On first startup, the app seeds the local database with default configuration.

---

### User Configuration

User changes are stored in the local database.

This allows configuration through the UI and avoids forcing users to edit files inside Docker containers.

---

### Import/Export

Users can export and import configuration as YAML.

Credentials must never be included in exported configuration.

---

### Community Configuration

In a later phase, users should be able to discover, download, rate, and share signal packs.

Community configuration must be declarative only.

No executable code should be allowed inside community configuration packs.

---

## 11. Data & Privacy Model

EM Radar is local-first.

By default:

* data is stored locally
* credentials are stored locally
* reports are stored locally
* telemetry is disabled
* no data is sent to external services
* no data is sent to AI providers

Users may optionally configure external connectors later, such as Slack, Teams, Confluence, or AI providers. These must be explicit opt-in choices.

---

## 12. AI Strategy

AI is not part of the Phase 1 MVP.

Future AI use cases may include:

* comparing tickets against Definition of Ready
* identifying vague descriptions
* detecting weak acceptance criteria
* summarizing large epics
* suggesting epic splits
* generating weekly report summaries
* drafting action recommendations

AI should be implemented through optional external connectors.

Initial AI connector candidate:

* Claude API

Future candidates:

* OpenAI
* local Ollama
* Gemini
* company-hosted LLM gateways

AI features must be disabled by default.

When enabled, the UI must clearly explain what data may be sent to the configured provider.

---

## 13. Future Scope

### Phase 2 — Community Signal Packs

Potential scope:

* public config pack format
* import signal pack from URL
* signal pack preview
* official packs
* community packs
* pack metadata
* GitHub-backed sharing model
* website or registry

---

### Phase 3 — GitHub Support

Potential scope:

* GitHub pull requests
* GitHub issues
* GitHub Projects support
* GitHub Marketplace packaging

---

### Phase 4 — AI-Optional Features

Potential scope:

* Claude connector
* Definition of Ready checker
* ticket clarity checker
* weak acceptance criteria detector
* AI-generated report summary
* optional local LLM support

---

### Phase 5 — Destination Connectors

Potential scope:

* Slack report delivery
* Microsoft Teams delivery
* email delivery
* Confluence publishing
* Markdown-to-page export

---

### Phase 6 — Enterprise Self-Hosted Edition

Potential scope:

* PostgreSQL-first deployment
* OIDC/SSO
* RBAC
* team-level permissions
* audit logs
* private config registry
* organization-wide deployment
* Helm chart
* enterprise support model

---

## 14. Success Criteria

### Phase 1 Success

Phase 1 is successful when:

* an EM can run EM Radar locally
* Jira connection works
* GitLab connection works
* sprint report works
* date-range report works
* at least 10 useful deterministic signals exist
* signal thresholds can be configured from UI
* report output is actionable
* Markdown export works
* credentials are handled safely
* setup is simple enough for a non-coding EM

---

### Product Success

The project is successful when EMs say:

> This helped me notice something I would otherwise have missed.

Or:

> This saved me time before planning, retro, or leadership updates.

Or:

> This gives me a better operating picture of my team without becoming a surveillance tool.

---

## 15. Non-Goals

EM Radar will not try to:

* rank individual developers
* calculate developer productivity scores
* replace EM judgment
* replace team conversations
* become a generic BI platform
* become a Jira clone
* become an AI-first management assistant from day one
* require company-wide deployment for basic usage
* require cloud hosting
* require Kubernetes for personal use

---

## 16. Guiding Product Philosophy

EM Radar should be built for practical Engineering Managers.

It should help them:

* inspect the right things sooner
* prepare better conversations
* detect delivery risk earlier
* improve planning hygiene
* understand code-review flow
* reduce manual board inspection
* share useful management practices with other EMs

The product should remain simple, transparent, and trustworthy.

The core promise is:

> Keep your data local. Make your risks visible. Help EMs lead with better signals.
