# EM Radar — Entity-Relationship Diagram

- **Status:** Draft v0.1
- **Date:** 2026-06-07
- **Owner:** Serdar Tas
- **Related:** [05-data-model.md](./05-data-model.md) (authoritative field-level spec), [09-functional-flows.md](./09-functional-flows.md), [03-architecture-overview.md](./03-architecture-overview.md)

## 1. Purpose

This document is a **visual reference** for the EM Radar schema. The authoritative,
field-by-field definitions (types, nullability, invariants, enums) live in
[05-data-model.md](./05-data-model.md); this file shows the entities and how they relate, at
attribute altitude, so the shape is easy to grasp at a glance.

The schema splits into two domains that meet at `TeamProfile`:

1. **Canonical / source domain** — normalized data pulled from Jira/GitLab (§3).
2. **Scoping, evaluation & configuration domain** — teams, connections, windows, reports,
   findings, and local config (§4).

Attribute lists below are a meaningful subset (keys + load-bearing fields). For the complete
column set of any entity, see the matching section in [05-data-model.md §5](./05-data-model.md#5-entities).

**Cardinality legend (Mermaid crow's-foot):**

| Notation | Meaning |
|---|---|
| `\|\|--\|\|` | exactly one ↔ exactly one |
| `\|\|--o{` | one ↔ zero or many |
| `}o--\|\|` | zero or many ↔ exactly one |
| `}o--o\|` | zero or many ↔ zero or one |
| `}o--o{` | many ↔ many (in MVP, materialized as UUID-array fields, not join tables) |

> **Note on array relationships.** Several links (`sprint_ids`, `project_ids`, `board_ids`,
> `repository_ids`, `connection_ids`, `linked_workitem_ids`) are stored as **UUID arrays** on the
> owning row (SQLite JSON columns), not as separate join tables. They are drawn as many-to-many
> for clarity but carry no association entity in MVP.

---

## 2. High-Level Map

```mermaid
flowchart LR
    subgraph Source["Canonical / source domain (§3)"]
        PROJECT --> BOARD --> SPRINT
        PROJECT --> WORKITEM
        REPOSITORY --> MERGEREQUEST
        USER
    end
    subgraph Eval["Scoping, evaluation & config (§4)"]
        TEAMPROFILE --> EVALUATIONWINDOW --> REPORT --> SIGNALFINDING
        SOURCECONNECTION
        SIGNALCONFIG
        SIGNALPACKHISTORY
    end
    TEAMPROFILE -. scopes .-> PROJECT
    TEAMPROFILE -. scopes .-> BOARD
    TEAMPROFILE -. scopes .-> REPOSITORY
    TEAMPROFILE -. uses .-> SOURCECONNECTION
    WORKITEM -. evaluated by .-> REPORT
    MERGEREQUEST -. evaluated by .-> REPORT
```

---

## 3. Canonical / Source Domain

Normalized entities produced by connectors. Every row carries the common fields from
[data model §4](./05-data-model.md#4-common-field-patterns) (`id`, `source`, `external_id`,
`source_url`, `source_metadata`, `fetched_at`, `created_at`, `updated_at`); only distinguishing
fields are repeated below.

```mermaid
erDiagram
    USER {
        uuid id PK
        string source
        string external_id
        string display_name
        string email
        string username
        bool is_bot
    }
    PROJECT {
        uuid id PK
        string source
        string external_id
        string key
        string name
    }
    BOARD {
        uuid id PK
        uuid project_id FK
        string name
        enum type "scrum|kanban|other"
    }
    SPRINT {
        uuid id PK
        uuid board_id FK
        string name
        enum state "future|active|closed"
        datetime start_date
        datetime end_date
        datetime complete_date
        string goal
    }
    WORKITEM {
        uuid id PK
        uuid project_id FK
        string key
        enum type "epic|story|task|bug|subtask|spike|other"
        string title
        text description
        string status
        enum status_category "todo|in_progress|done|blocked"
        uuid assignee_id FK
        uuid reporter_id FK
        uuid parent_id FK
        number story_points
        text acceptance_criteria
        bool is_blocked
        datetime resolved_at
        array sprint_ids
        uuid current_sprint_id
    }
    WORKITEMLINK {
        uuid id PK
        uuid source_workitem_id FK
        uuid target_workitem_id FK
        enum link_type "blocks|is_blocked_by|relates_to|duplicates|is_duplicated_by"
    }
    REPOSITORY {
        uuid id PK
        string source
        string external_id
        string name
        string full_path
        string default_branch
        bool is_archived
    }
    MERGEREQUEST {
        uuid id PK
        uuid repository_id FK
        int iid
        string title
        enum state "open|draft|merged|closed"
        bool is_draft
        uuid author_id FK
        string target_branch
        string source_branch
        datetime merged_at
        datetime closed_at
        int changed_files_count
        int additions
        int deletions
        enum pipeline_status "success|failed|running|canceled|skipped|none"
        datetime pipeline_updated_at
        int approval_count
        int comment_count
        array linked_workitem_keys
        array linked_workitem_ids
    }
    REVIEW {
        uuid id PK
        uuid mergerequest_id FK
        uuid reviewer_id FK
        enum decision "approved|changes_requested|commented|dismissed|requested"
        datetime submitted_at
    }
    COMMENT {
        uuid id PK
        enum entity_type "workitem|mergerequest"
        uuid entity_id FK
        uuid author_id FK
        text body
        bool is_system
    }
    TRANSITION {
        uuid id PK
        enum entity_type "workitem|mergerequest"
        uuid entity_id FK
        string from_status
        string to_status
        enum from_status_category
        enum to_status_category
        uuid actor_id FK
        datetime occurred_at
    }

    PROJECT  ||--o{ BOARD        : "contains"
    BOARD    ||--o{ SPRINT       : "contains"
    PROJECT  ||--o{ WORKITEM     : "contains"
    WORKITEM }o--o{ SPRINT       : "appears in (sprint_ids)"
    WORKITEM }o--o| WORKITEM     : "parent (epic)"
    WORKITEM ||--o{ WORKITEMLINK : "as source"
    WORKITEM ||--o{ WORKITEMLINK : "as target"
    USER     ||--o{ WORKITEM     : "assignee"
    USER     ||--o{ WORKITEM     : "reporter"
    REPOSITORY ||--o{ MERGEREQUEST : "contains"
    USER     ||--o{ MERGEREQUEST : "author"
    MERGEREQUEST ||--o{ REVIEW   : "has"
    USER     ||--o{ REVIEW       : "reviewer"
    MERGEREQUEST }o--o{ WORKITEM : "linked (keys/ids)"
    WORKITEM ||--o{ COMMENT      : "has"
    MERGEREQUEST ||--o{ COMMENT  : "has"
    USER     ||--o{ COMMENT      : "author"
    WORKITEM ||--o{ TRANSITION   : "has"
    MERGEREQUEST ||--o{ TRANSITION : "has"
    USER     ||--o{ TRANSITION   : "actor"
```

**Notes.**
- `COMMENT` and `TRANSITION` are **polymorphic** (`entity_type` + `entity_id`): a row belongs to
  either a `WorkItem` or a `MergeRequest`, never both.
- `WORKITEMLINK` is an edge with two FKs into `WORKITEM` (`source`/`target`); asymmetric link
  types are stored as canonical pairs ([data model §5.6](./05-data-model.md#56-workitemlink)).
- `MERGEREQUEST ↔ WORKITEM` linking is by extracted key (`linked_workitem_keys`) resolved to
  `linked_workitem_ids` when a matching item exists ([data model §7](./05-data-model.md#7-identity-linking-and-cross-source-resolution)).

---

## 4. Scoping, Evaluation & Configuration Domain

Teams scope what a report sees; a report is the result of evaluating signals over an
evaluation window. `SourceConnection`, `SignalConfig`, and `SignalPackHistory` are local
application tables ([backlog M2-03/M2-18/M2-19](./backlog/M2-storage-config-ui.md)), not pulled
from a source.

```mermaid
erDiagram
    SOURCECONNECTION {
        uuid id PK
        string connector_name "demo|jira|gitlab"
        json config "credentials masked on read"
        array selected_project_ids
        array selected_board_ids
        array selected_repository_ids
        datetime created_at
    }
    TEAMPROFILE {
        uuid id PK
        string name
        text description
        array connection_ids
        array project_ids
        array board_ids
        array repository_ids
        enum working_mode "scrum|kanban"
        int sprint_length_days
        array member_user_keys
        datetime created_at
        datetime updated_at
    }
    EVALUATIONWINDOW {
        uuid id PK
        enum window_type "sprint|date_range"
        uuid sprint_id FK "when window_type=sprint"
        datetime start "when window_type=date_range"
        datetime end "when window_type=date_range"
        uuid team_profile_id FK
    }
    REPORT {
        uuid id PK
        uuid evaluation_window_id FK
        json signal_pack_snapshot
        enum status "pending|running|succeeded|failed"
        datetime started_at
        datetime finished_at
        text error
        json findings_count_by_severity
    }
    SIGNALFINDING {
        uuid id PK
        uuid report_id FK
        string signal_id
        string signal_name
        enum severity "info|warning|critical"
        enum confidence "high|medium|low"
        enum entity_type "workitem|mergerequest|sprint|repository"
        uuid entity_id FK
        string title
        text reason
        text recommendation
        json evidence
        string source_link
        datetime created_at
    }
    SIGNALCONFIG {
        uuid id PK
        string signal_id "catalog id"
        bool enabled
        enum severity_override
        json params
        json scope
    }
    SIGNALPACKHISTORY {
        uuid id PK
        string pack_name
        text raw_yaml "round-trip source"
        datetime imported_at
    }

    TEAMPROFILE }o--o{ SOURCECONNECTION : "uses (connection_ids)"
    TEAMPROFILE }o--o{ PROJECT          : "scope (project_ids)"
    TEAMPROFILE }o--o{ BOARD            : "scope (board_ids)"
    TEAMPROFILE }o--o{ REPOSITORY       : "scope (repository_ids)"
    TEAMPROFILE ||--o{ EVALUATIONWINDOW : "scopes"
    EVALUATIONWINDOW }o--o| SPRINT      : "sprint window"
    EVALUATIONWINDOW ||--|| REPORT      : "produces"
    REPORT ||--o{ SIGNALFINDING         : "contains"
    SIGNALFINDING }o--|| WORKITEM       : "about (when entity_type=workitem)"
    SIGNALFINDING }o--|| MERGEREQUEST   : "about (when entity_type=mergerequest)"
    SIGNALFINDING }o--|| SPRINT         : "about (when entity_type=sprint)"
    SIGNALFINDING }o--|| REPOSITORY     : "about (when entity_type=repository)"
```

**Notes.**
- `TeamProfile.working_mode` drives the default window type: **scrum → sprint**, **kanban →
  date_range**. Sprint-only signals are skipped on date-range runs (window-gating,
  [09-functional-flows §10](./09-functional-flows.md#10-how-working-mode-shapes-signals-no-per-team-config)).
- `EvaluationWindow` requires `sprint_id` **xor** (`start`,`end`) per `window_type`
  ([data model §5.13](./05-data-model.md#513-evaluationwindow)).
- `SignalFinding.entity_id` is **polymorphic** over `entity_type` (work item, MR, sprint, or
  repository); the four "about" relationships above are mutually exclusive per row.
- `SourceConnection.config` holds credentials at rest (SQLite, masked on read,
  [ADR-0006](./ADRs/0006-token-storage.md)); it is the only place tokens live and is never
  exported.
- `Dashboard` is **not** an entity — it is derived by reading the latest `Report` per
  `TeamProfile` ([09-functional-flows §6](./09-functional-flows.md#6-flow-d--initial-sync--dashboard)).

---

## 5. Identity & Persistence

Internal `id` UUIDs are **stable across fetches**, keyed by `(source, external_id)`; the
persistence/identity layer ([backlog M2-17](./backlog/M2-storage-config-ui.md)) upserts on each
fetch and resolves cross-entity references (assignee, parent, sprint membership, MR↔WorkItem)
from external ids to internal UUIDs. See [data model §2 and §7](./05-data-model.md#2-design-principles).

Cross-**source** user identity (the same human in Jira and GitLab) is **not** auto-resolved in
MVP; a `TeamProfile.member_user_keys` list may declare it, but the engine does not infer it.
