# Requirements: Configurable Signal Builder, Scoped Signals, and Import/Export

## 1. Problem

EM Radar currently treats signals as fixed built-in checks with a small number of configurable parameters. For example, the “stale in-progress work item” signal allows users to configure only:

* Days threshold
* Excluded labels

This is too restrictive.

Engineering managers manage different teams, workflows, projects, boards, and operating models. One team may work in Scrum, another in Kanban, another as a support team. The same signal rule should not automatically apply everywhere.

Examples:

* A support team may need every ticket closed within 3 days.
* A product team may allow larger stories to stay open longer.
* A Scrum team may need sprint-relative checks.
* A Kanban team may need aging-in-column checks.
* A platform team may need different thresholds than a customer-facing team.

EM Radar needs a flexible signal model where users can create, edit, export, import, and share signal configurations.

## 2. Goal

Create a configurable signal system where users can:

* Create custom signals from scratch
* Edit existing signals
* Duplicate existing signals
* Disable signals
* Delete user-created signals
* Use built-in signals as editable templates
* Scope signals to specific projects, boards, teams, repositories, or equivalent connector-specific targets
* Export signal configurations
* Import signal configurations
* Export either private backup configurations or public shareable templates
* Share reusable signal packs with other engineering managers

The system should remain safe, structured, explainable, and implementation-friendly. It must not become an unrestricted scripting engine.

## 3. Core Design Principle

EM Radar must separate three concepts:

```text
Connector = how EM Radar connects to a system
Scope = where inside that system the signal applies
Signal = what rule is evaluated
```

Example:

```text
Connector:
  Jira - bol.com

Scopes:
  Fraud Defense Scrum board
  CDD Kanban board
  Support project

Signals:
  Stale in-progress work item
  Ticket open longer than 3 days
  Sprint ending with unresolved critical items
```

A connector should not imply that every signal applies to every project, board, or team available through that connector.

Signals must have explicit target scopes.

## 4. Definitions

### 4.1 Connector

A connector represents a configured integration with an external tool.

Examples:

* Jira instance
* GitHub organization
* GitLab group

A connector contains connection-level details such as:

* Connector type
* Base URL
* Authentication reference
* Display name
* Sync settings

The connector should not directly define which signals apply to which boards or projects.

### 4.2 Scope

A scope represents a subset of data inside a connector.

Examples for Jira:

* Project
* Board
* Sprint board
* Kanban board
* Saved filter
* JQL-defined dataset
* Team-specific work item set

Examples for GitHub:

* Repository
* Organization
* Team
* Label-filtered issue set
* Pull request set

A scope is reusable. Multiple signals may target the same scope.

### 4.3 Signal

A signal is a rule that evaluates entities from one or more selected scopes.

A signal contains:

* Name
* Description
* Entity type
* Target scopes
* Conditions
* Logical groups
* Report settings
* Enabled/disabled state
* Template/export metadata

Examples:

* Stale in-progress work item
* Ticket open longer than 3 days
* Blocked item without update
* High-priority item close to sprint end
* Pull request open longer than 2 days
* Too many items in review

## 5. Scope Model Requirement

Signals must support explicit scope assignment.

A signal may target:

* One scope
* Multiple scopes of the same connector type
* Multiple scopes from different connectors only in later versions

For MVP, signals should target one or more scopes of the same connector type and entity type.

Example:

```yaml
signal:
  name: Support tickets open longer than 3 days
  entity_type: issue
  target_scopes:
    - connector_id: jira-bol
      scope_id: support-project
```

Another example:

```yaml
signal:
  name: Stale in-progress Scrum work
  entity_type: issue
  target_scopes:
    - connector_id: jira-bol
      scope_id: fraud-defense-scrum-board
    - connector_id: jira-bol
      scope_id: cdd-scrum-board
```

A signal must not automatically apply to every available board or project in a connector unless the user explicitly chooses an “all scopes” option.

## 6. Why Scope Must Not Live Only on Connector Level

Connector-level scoping alone is not flexible enough.

If a Jira connector is configured with multiple boards and projects, and every signal automatically runs against all of them, users cannot express different rules for different teams.

Bad model:

```text
Jira connector includes boards A, B, C
Every signal runs on boards A, B, C
```

This fails when:

* Board A is Scrum
* Board B is Kanban
* Board C is support
* Each board needs different thresholds and signal logic

Required model:

```text
Jira connector includes access to Jira
Scopes define selected boards/projects
Signals choose which scopes they apply to
```

This allows:

```text
Signal A applies only to Scrum boards
Signal B applies only to support project
Signal C applies only to Kanban board
```

## 7. Signal Creation Flow

The user clicks **New Signal**.

The system asks for:

1. Signal name
2. Optional description
3. Connector type or existing connector
4. Entity type
5. Target scope
6. Conditions
7. Logical grouping
8. Report presentation settings
9. Preview
10. Save

## 8. Signal Name

The signal name must be:

* Required
* Unique within the local workspace
* Human-readable
* Shown in reports
* Editable later

Duplicate signal names should be rejected with a clear validation message.

## 9. Source and Scope Selection

The user first selects a source connector.

Example:

```text
Jira - bol.com
```

Then the user selects where the signal applies.

For Jira, possible scopes may include:

* Project
* Board
* Saved filter
* Sprint board
* Kanban board
* JQL-backed scope, later version

Example UI flow:

```text
Source: Jira - bol.com
Entity type: Issue
Scope type: Board
Board: Fraud Defense Scrum Board
```

Or:

```text
Source: Jira - bol.com
Entity type: Issue
Scope type: Project
Project: Support Operations
```

The selected scope determines which fields and values are available to the signal builder.

For example, a Scrum board may expose sprint-related fields, while a Kanban board may not.

## 10. Connector Capability Schema

Each connector must expose a capability schema.

The schema tells EM Radar which fields, operators, scopes, entity types, and value providers are available.

The UI must be generated from this schema instead of hardcoding Jira-specific behavior directly into the signal builder.

Example:

```yaml
connector_type: jira
entity_types:
  - issue

scope_types:
  - key: project
    label: Project
  - key: board
    label: Board
  - key: saved_filter
    label: Saved Filter

fields:
  - key: status
    label: Status
    type: enum
    operators:
      - is
      - is_not
      - is_any_of
      - is_none_of
    value_provider:
      type: dynamic
      source: jira_statuses
      depends_on:
        - scope

  - key: status_category
    label: Status Category
    type: enum
    operators:
      - is
      - is_not
    values:
      - To Do
      - In Progress
      - Done

  - key: labels
    label: Labels
    type: string_list
    operators:
      - contains
      - does_not_contain
      - contains_any
      - does_not_contain_any
    value_provider:
      type: dynamic
      source: jira_labels
      depends_on:
        - scope

  - key: age_in_current_status
    label: Age in current status
    type: duration
    operators:
      - greater_than
      - less_than
      - between

  - key: sprint_day
    label: Sprint day
    type: sprint_relative_day
    operators:
      - is
      - is_before
      - is_after
      - between
    availability:
      requires_scope_capability:
        - sprint

  - key: sprint_phase
    label: Sprint phase
    type: enum
    operators:
      - is
      - is_not
    values:
      - first_day
      - middle
      - last_day
    availability:
      requires_scope_capability:
        - sprint
```

## 11. Condition Builder

A condition consists of:

```text
Field + Operator + Value
```

Examples:

```text
Status is In Progress
Status is not Done
Status category is In Progress
Labels do not contain waiting
Age in current status is greater than 3 days
Age in current status is between 3 and 5 days
Sprint day is 2
Sprint phase is last day
Issue type is Bug
Priority is High
Assignee is empty
Updated date is before 5 days ago
```

The UI must only show operators that are valid for the selected field type.

## 12. Logical Grouping

The builder must support basic logical groups.

MVP support:

* AND
* OR
* One level of nested grouping

Example:

```text
Status category is In Progress
AND Age in current status is greater than 3 days
AND Labels do not contain waiting
```

Example with OR:

```text
Status category is In Progress
AND Age in current status is greater than 3 days
AND (
  Priority is High
  OR Labels contain customer-impact
)
```

Deep arbitrary nesting is not required for MVP.

## 13. Time-Based Conditions

The system must support time-based conditions.

MVP time conditions:

* Created date is before / after / between dates
* Updated date is before / after / between dates
* Resolved date is before / after / between dates
* Age since created is greater than / less than / between duration
* Age since updated is greater than / less than / between duration
* Age in current status is greater than / less than / between duration

Sprint-aware conditions:

* Sprint day is specific day number
* Sprint day is before day number
* Sprint day is after day number
* Sprint day is between two day numbers
* Sprint phase is first day
* Sprint phase is middle
* Sprint phase is last day
* Percentage of sprint elapsed, later version

Sprint-aware conditions should only be available when the selected scope supports sprint data.

## 14. Built-in Signals as Templates

Built-in signals should be represented as templates, not hardcoded behavior.

Users can:

* Use a built-in template as-is
* Duplicate it
* Edit the duplicate
* Disable the built-in template
* Restore built-in defaults

Example template:

```yaml
template:
  key: stale-in-progress-work-item
  name: Stale in-progress work item
  description: Finds items that have stayed in progress longer than expected.
  entity_type: issue
  expression:
    type: group
    operator: all
    conditions:
      - field: status_category
        operator: is
        value: In Progress
      - field: age_in_current_status
        operator: greater_than
        value:
          amount: 3
          unit: days
      - field: labels
        operator: does_not_contain_any
        value:
          - waiting
          - parked
```

Templates should not require a scope until instantiated by the user.

## 15. Signal Preview

Before saving a signal, the user must be able to preview the result.

Preview should show:

* Number of matching items
* Sample matching items
* Source/scope used
* Relevant fields
* Explanation of why each item matched
* Validation warnings

Example:

```text
This signal matches 7 Jira issues in Fraud Defense Scrum Board.

Examples:
- FD-123 — Add risk profile persistence
  Reason: Status category is In Progress and age in current status is 5 days.

- FD-141 — Update onboarding flow
  Reason: Status category is In Progress and age in current status is 4 days.
```

## 16. Report Behavior

Reports must show signal results grouped by signal name.

Each matching item should include:

* Signal name
* Source connector name
* Scope name
* Item key or identifier
* Item title
* Relevant field values
* Reason why the item matched
* Link to source item, when available

Example:

```text
Signal: Stale in-progress work item
Scope: Fraud Defense Scrum Board

FD-123 — Add risk profile persistence
Reason: Status category is In Progress and item has been in current status for 5 days.
```

The report must be explainable. Users should understand why an item appeared.

## 17. Signal Definition Storage Model

Signal definitions must be stored as structured data, not hardcoded Python logic.

Recommended model:

```yaml
SignalDefinition:
  id: string
  name: string
  description: string | null
  entity_type: string
  target_scopes:
    - SignalTargetScope
  expression: RuleExpression
  report_settings: ReportSettings
  enabled: boolean
  origin: system_template | user_created | imported
  template_key: string | null
  created_at: datetime
  updated_at: datetime
  version: integer
```

Target scope:

```yaml
SignalTargetScope:
  connector_id: string
  scope_id: string
  scope_type: project | board | repository | saved_filter | custom
```

Rule expression:

```yaml
RuleExpression:
  type: group
  operator: all | any
  conditions:
    - Condition | RuleExpression
```

Condition:

```yaml
Condition:
  field: string
  operator: string
  value: any
```

Report settings:

```yaml
ReportSettings:
  severity: info | warning | critical
  category: flow | delivery | quality | risk | support | custom
  message_template: string | null
```

## 18. Scope Definition Storage Model

Scopes should be stored separately from signals.

Recommended model:

```yaml
ScopeDefinition:
  id: string
  connector_id: string
  name: string
  scope_type: project | board | repository | saved_filter | custom
  external_ref:
    type: string
    id: string | null
    key: string | null
    name: string | null
  capabilities:
    - sprint
    - kanban
    - statuses
    - labels
  created_at: datetime
  updated_at: datetime
```

Example Jira board scope:

```yaml
ScopeDefinition:
  id: scope-fraud-defense-board
  connector_id: jira-bol
  name: Fraud Defense Scrum Board
  scope_type: board
  external_ref:
    type: jira_board
    id: "123"
    key: null
    name: Fraud Defense Scrum Board
  capabilities:
    - sprint
    - statuses
    - labels
```

Example Jira project scope:

```yaml
ScopeDefinition:
  id: scope-support-project
  connector_id: jira-bol
  name: Support Operations
  scope_type: project
  external_ref:
    type: jira_project
    id: "10045"
    key: SUPPORT
    name: Support Operations
  capabilities:
    - statuses
    - labels
```

## 19. Import and Export Overview

EM Radar must support exporting and importing signal configurations.

There are two export modes:

1. Private backup export
2. Public shareable export

These modes solve different use cases.

## 20. Private Backup Export

Private backup export is used when the user wants to:

* Move to another computer
* Upgrade EM Radar
* Back up their configuration
* Restore their own setup
* Hand over the EM role to another EM in the same organization
* Avoid manually reselecting projects, boards, and scopes

Private backup export should include user-specific and organization-specific references.

It may include:

* Signal definitions
* Scope definitions
* Connector references
* Jira project keys
* Jira board IDs
* Jira board names
* Jira project names
* Repository names
* Scope mappings
* Template origin metadata

It must not include secrets.

Private backup export must never include:

* API tokens
* Passwords
* Personal access tokens
* OAuth refresh tokens
* Session cookies
* Local credential references that are not portable

Example private backup export:

```yaml
em_radar_export:
  format_version: 1
  export_type: private_backup
  exported_at: "2026-06-18T20:00:00Z"
  app_version: "0.3.0"

connectors:
  - local_ref: jira-bol
    connector_type: jira
    name: Jira - bol.com
    base_url: "https://example.atlassian.net"
    auth: omitted

scopes:
  - local_ref: fraud-defense-board
    connector_ref: jira-bol
    name: Fraud Defense Scrum Board
    scope_type: board
    external_ref:
      type: jira_board
      id: "123"
      name: Fraud Defense Scrum Board
    capabilities:
      - sprint
      - statuses
      - labels

signals:
  - name: Stale in-progress work item
    description: Finds Jira issues that have stayed in progress too long.
    entity_type: issue
    target_scopes:
      - connector_ref: jira-bol
        scope_ref: fraud-defense-board
    expression:
      type: group
      operator: all
      conditions:
        - field: status_category
          operator: is
          value: In Progress
        - field: age_in_current_status
          operator: greater_than
          value:
            amount: 3
            unit: days
    report_settings:
      severity: warning
      category: flow
    enabled: true
```

## 21. Public Shareable Export

Public shareable export is used when the user wants to share useful signal configurations with other engineering managers.

This export mode should remove user-specific and organization-specific details.

It should not include:

* Connector IDs
* Base URLs
* Jira project names
* Jira project keys
* Jira board IDs
* Jira board names
* Repository names
* Usernames
* Assignee names
* Organization-specific labels, unless the user explicitly chooses to keep labels
* Any secrets

Public shareable export should include:

* Signal names
* Signal descriptions
* Entity type
* Required connector type
* Required scope capabilities
* Rule expression
* Generic field references
* Report settings
* Optional setup notes

Example public shareable export:

```yaml
em_radar_export:
  format_version: 1
  export_type: public_template
  exported_at: "2026-06-18T20:00:00Z"
  app_version: "0.3.0"

signal_pack:
  name: Practical EM Flow Signals
  description: A reusable set of flow and delivery signals for engineering managers.
  author: optional
  license: optional

signals:
  - name: Stale in-progress work item
    description: Finds items that have stayed in progress longer than expected.
    required_connector_type: jira
    entity_type: issue
    required_scope_capabilities:
      - statuses
    target_scope: user_must_select
    expression:
      type: group
      operator: all
      conditions:
        - field: status_category
          operator: is
          value: In Progress
        - field: age_in_current_status
          operator: greater_than
          value:
            amount: 3
            unit: days
    report_settings:
      severity: warning
      category: flow
    enabled_by_default: true

  - name: Support ticket open longer than 3 days
    description: Finds support tickets that have not been closed within 3 days.
    required_connector_type: jira
    entity_type: issue
    required_scope_capabilities:
      - statuses
    target_scope: user_must_select
    expression:
      type: group
      operator: all
      conditions:
        - field: status_category
          operator: is_not
          value: Done
        - field: age_since_created
          operator: greater_than
          value:
            amount: 3
            unit: days
    report_settings:
      severity: critical
      category: support
    enabled_by_default: true
```

## 22. Export Modes

When exporting, the user must choose one of the following modes:

### 22.1 Backup / Migration Export

Label:

```text
Backup or move my own setup
```

Behavior:

* Includes connector references
* Includes scope references
* Includes project names/keys
* Includes board names/IDs
* Includes signal-to-scope mappings
* Excludes all secrets
* Best for moving to another machine or handing over to another EM in the same environment

### 22.2 Public Template Export

Label:

```text
Share signal templates with others
```

Behavior:

* Removes connector-specific data
* Removes project-specific data
* Removes board-specific data
* Removes user-specific data
* Replaces target scopes with required capabilities
* Importing user must map signals to their own connector and scope
* Best for sharing with the community

## 23. Import Flow

When importing a YAML file, the system must detect the export type.

### 23.1 Importing Private Backup Export

The system should try to restore the configuration as fully as possible.

Import steps:

1. Read export file
2. Validate format version
3. Show summary of connectors, scopes, and signals
4. Check whether referenced connectors already exist
5. Match connectors by type and base URL where possible
6. Check whether referenced scopes exist
7. Match scopes by external ID, key, or name where possible
8. Show unresolved mappings
9. Ask user to resolve missing connectors/scopes
10. Import signals
11. Preserve signal-to-scope mappings where possible
12. Show import summary

Private backup import should support three outcomes:

```text
Fully mapped:
  Signal can run immediately.

Partially mapped:
  Signal is imported but disabled until missing scope is resolved.

Unmapped:
  Signal is imported as a template and requires connector/scope selection.
```

### 23.2 Importing Public Template Export

The system should treat imported signals as templates.

Import steps:

1. Read export file
2. Validate format version
3. Show signal pack summary
4. Ask user which signals to import
5. Ask user to choose connector
6. Ask user to choose target scope for each signal or apply one scope to all compatible signals
7. Validate connector capabilities
8. Import selected signals
9. Run preview
10. Enable only valid signals

Public template import must not assume that the importing user has the same Jira projects, boards, statuses, labels, or workflows.

## 24. Import Mapping Requirements

The import UI must support mapping unresolved references.

For private backup imports:

```text
Exported connector: Jira - bol.com
Matched local connector: Jira - bol.com
Status: matched
```

```text
Exported scope: Fraud Defense Scrum Board
Matched local scope: Fraud Defense Scrum Board
Status: matched
```

For unresolved scopes:

```text
Exported scope: Fraud Defense Scrum Board
Status: not found

Choose replacement:
[Select Jira board]
```

For public template imports:

```text
Signal: Stale in-progress work item
Requires: Jira issue scope with statuses
Choose target scope:
[Select project or board]
```

## 25. Handling Field and Value Differences on Import

Different Jira setups may have different:

* Status names
* Workflow states
* Labels
* Priorities
* Issue types
* Custom fields
* Board structures

The importer must validate imported signals against the selected connector capability schema.

If a field is unsupported:

```text
This signal uses field 'sprint_day', but the selected scope does not support sprint data.
```

If a value is missing:

```text
This signal uses status 'In Progress', but this status was not found in the selected scope.
```

The system should allow the user to:

* Map the missing value to a local value
* Replace the condition value
* Disable the condition
* Import the signal as disabled
* Cancel importing that signal

## 26. Handling Labels in Public Exports

Labels can be tricky.

Some labels are generic:

```text
blocked
waiting
customer-impact
```

Some labels are organization-specific:

```text
bol-fintech-risk
team-frits
compliance-amsterdam
```

For public template export, the user should choose one of these options:

```text
Remove label values
Keep label values
Review label values before export
```

Default behavior should be:

```text
Review label values before export
```

This avoids accidentally sharing internal naming conventions while still allowing users to share useful generic signal packs.

## 27. YAML Format Requirements

Exported files must be YAML.

The YAML must be:

* Human-readable
* Versioned
* Validatable
* Stable enough for Git storage
* Free of secrets
* Suitable for manual review before sharing

Required top-level fields:

```yaml
em_radar_export:
  format_version: 1
  export_type: private_backup | public_template
  exported_at: string
  app_version: string
```

Public template exports may include:

```yaml
signal_pack:
  name: string
  description: string | null
  author: string | null
  license: string | null
```

## 28. Export Safety Requirements

Before creating a public export, EM Radar must show a review screen.

The review screen should warn about potentially sensitive values, including:

* Connector names
* Base URLs
* Project names
* Board names
* Repository names
* User names
* Assignee names
* Reporter names
* Labels
* Custom field names
* Free-text descriptions

The user must explicitly confirm the export.

Public export should default to removing sensitive data.

Private backup export should still exclude secrets.

## 29. Signal Packs

A public export containing one or more signals is called a signal pack.

Signal packs allow engineering managers to share practical signal configurations.

Examples:

* Scrum flow signal pack
* Kanban aging signal pack
* Support team signal pack
* Delivery risk signal pack
* Pull request hygiene signal pack
* Incident follow-up signal pack

Signal packs should be importable without requiring the same source environment as the author.

## 30. Recommended Built-in Signal Packs

EM Radar may ship with built-in signal packs.

Initial examples:

### 30.1 Scrum Flow Pack

Signals:

* Stale in-progress work item
* Sprint ending with unfinished high-priority work
* Work added after sprint start
* Too many items in progress
* Blocked item without update

### 30.2 Kanban Flow Pack

Signals:

* Item aging in active column
* Too many items in review
* Blocked item older than threshold
* No update for active item
* Work item stuck before done

### 30.3 Support Team Pack

Signals:

* Ticket open longer than 3 days
* Critical ticket open longer than 1 day
* Ticket assigned but not updated
* Unassigned support ticket
* Reopened ticket

## 31. Execution Model

Signal evaluation should happen against EM Radar’s normalized local data model where possible.

Preferred flow:

1. Connector imports data from source
2. Data is normalized into EM Radar’s local model
3. Scopes define which subset of data is relevant
4. Signal engine evaluates signal definitions against scoped data
5. Report engine renders matching results

Connector-specific optimization may be added later, but signal semantics should remain owned by EM Radar.

EM Radar should not depend on Jira JQL, GitHub search syntax, or GitLab query behavior as the primary signal engine.

## 32. MVP Jira Field Set

For MVP, Jira issue signals should support:

* Project
* Board
* Issue key
* Issue type
* Status
* Status category
* Labels
* Priority
* Assignee
* Reporter
* Created date
* Updated date
* Resolved date
* Current sprint, when available
* Sprint day, when available
* Sprint phase, when available
* Age since created
* Age since updated
* Age in current status

Board-specific concepts such as swimlanes should be added only if the Jira connector can reliably retrieve and normalize board configuration.

## 33. Validation Rules

Signal validation must check:

* Signal name is required
* Signal name is unique
* Entity type is supported
* At least one target scope is selected
* Selected scope exists
* Selected scope belongs to the selected connector
* Selected scope supports the selected entity type
* Selected field exists in the connector capability schema
* Selected operator is valid for the selected field type
* Selected value matches expected field type
* Dynamic value still exists or has a valid mapping
* Time durations are positive
* Between conditions have valid lower and upper bounds
* Sprint fields are only used with sprint-capable scopes
* Signal contains at least one condition

## 34. Import Validation Rules

Import validation must check:

* YAML is valid
* Export format version is supported
* Export type is known
* Required top-level fields exist
* Signals have valid names
* Signal expressions are structurally valid
* Fields are known or can be mapped
* Operators are supported
* Target scopes are resolved or explicitly left unmapped
* No secrets are present in the import file
* Public templates do not contain connector credentials

## 35. Conflict Handling on Import

If an imported signal has the same name as an existing signal, the user should choose:

```text
Skip
Replace existing
Import as copy
```

Default should be:

```text
Import as copy
```

Example:

```text
Existing: Stale in-progress work item
Imported as: Stale in-progress work item (Imported)
```

## 36. Enablement After Import

Imported signals should only be enabled automatically when:

* Connector is resolved
* Scope is resolved
* All fields are supported
* All required values are valid
* Preview can run successfully

Otherwise, the signal should be imported as disabled with a clear reason.

Example:

```text
Imported but disabled:
Signal uses sprint_day, but selected scope is a Kanban board.
```

## 37. Acceptance Criteria

### 37.1 Scoped Signals

Given a user has one Jira connector with multiple boards,
when the user creates a signal,
then the user must choose which board, project, or scope the signal applies to.

### 37.2 Different Signals for Different Teams

Given the user manages a Scrum board and a support project,
when the user creates a “ticket open longer than 3 days” signal for the support project,
then the signal must not apply to the Scrum board unless explicitly selected.

### 37.3 Capability-Based UI

Given the user selects a Scrum board scope,
then sprint-related fields are available in the condition builder.

Given the user selects a Kanban board without sprint support,
then sprint-related fields are hidden or disabled.

### 37.4 Private Backup Export

Given the user exports signals as a private backup,
then the YAML includes signal definitions, connector references, scope references, and signal-to-scope mappings, but excludes secrets.

### 37.5 Public Template Export

Given the user exports signals as a public template,
then the YAML removes connector-specific, project-specific, board-specific, and user-specific references.

### 37.6 Private Backup Import

Given the user imports a private backup on another computer with the same Jira connector configured,
then EM Radar should map connectors and scopes where possible and enable valid signals automatically.

### 37.7 Public Template Import

Given the user imports a public signal pack,
then EM Radar should ask the user to select their own connector and target scope before enabling the signals.

### 37.8 Import With Missing Scope

Given an imported signal references a board that does not exist locally,
then EM Radar should import the signal as disabled and ask the user to map it to an available scope.

### 37.9 Import With Unsupported Field

Given an imported signal uses `sprint_day`,
and the user maps it to a Kanban scope without sprint support,
then EM Radar should reject enabling the signal and explain the incompatibility.

### 37.10 Report Explainability

Given a signal matches an item,
when the report is generated,
then the report includes the signal name, scope, matching item, and reason why it matched.

## 38. Suggested Implementation Epics

### Epic 1: Signal Domain Model

Implement the persistent model for configurable signals.

Includes:

* SignalDefinition
* RuleExpression
* Condition
* ReportSettings
* Enabled/disabled state
* Template metadata
* Validation logic

### Epic 2: Scope Domain Model

Implement reusable scopes separate from connectors and signals.

Includes:

* ScopeDefinition
* Scope type
* External reference
* Capabilities
* Connector association
* Scope discovery from connectors

### Epic 3: Connector Capability Schema

Implement connector capability schemas.

Includes:

* Supported entity types
* Supported scope types
* Supported fields
* Supported operators
* Value providers
* Field availability rules
* Jira capability schema

### Epic 4: Signal Evaluation Engine

Implement generic signal evaluation.

Includes:

* AND/OR evaluation
* Condition evaluation
* Duration comparison
* Date comparison
* Enum comparison
* String-list comparison
* Sprint-aware field evaluation
* Explanation output

### Epic 5: Signal Builder UI

Implement the visual signal builder.

Includes:

* Signal name and description
* Source selector
* Scope selector
* Field/operator/value builder
* Logical grouping
* Validation messages
* Preview
* Save

### Epic 6: Built-in Templates

Convert built-in signals into templates.

Includes:

* Template definitions
* Duplicate template
* Disable template
* Restore default
* Template versioning

### Epic 7: Export

Implement YAML export.

Includes:

* Private backup export
* Public template export
* Export review screen
* Secret exclusion
* Sensitive value stripping
* Signal pack metadata

### Epic 8: Import

Implement YAML import.

Includes:

* Format validation
* Private backup import
* Public template import
* Connector mapping
* Scope mapping
* Field/value validation
* Conflict handling
* Import summary

### Epic 9: Report Integration

Integrate configurable signals into reports.

Includes:

* Signal grouping
* Scope display
* Matching item display
* Reason/explanation
* Source links
* Disabled/invalid signal visibility

## 39. MVP Recommendation

The first implementation should support:

* Jira connector only
* Jira issue entity only
* Explicit Jira project/board scopes
* User-created signals
* Built-in templates as duplicable definitions
* Basic AND/OR logic
* Duration/date/status/label/priority/assignee fields
* Sprint fields only when available
* Signal preview
* Report explanations
* Private backup export
* Public template export
* Public template import with manual scope mapping

Do not implement in MVP:

* Cross-source signals
* Arbitrary custom scripting
* Deep nested condition groups
* Full JQL builder
* Automatic community marketplace
* Complex custom field mapping
* Multi-tenant sharing service

## 40. Final Product Principle

EM Radar should feel like this:

```text
Start with useful engineering-management signal templates.
Adapt them to each team’s workflow.
Scope them precisely to the right board, project, or repository.
Export your setup for backup.
Share generic signal packs with other EMs.
Import shared signals safely without leaking private company data.
Understand exactly why every item appears in the report.
```

The product should be configurable enough for real engineering managers, but constrained enough to remain understandable, testable, and maintainable.
