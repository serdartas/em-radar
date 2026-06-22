# EM Radar — Signal Pack YAML Specification

- **Status:** Draft v0.2
- **Schema version:** `emradar.dev/v1`
- **Date:** 2026-06-01
- **Owner:** Serdar Tas
- **Related:** [05-data-model.md](./05-data-model.md), [02-requirements.md](./02-requirements.md) §4.5

## 1. Purpose

This document specifies the YAML format used to describe **Signal Packs** in EM Radar.

A Signal Pack is the import/export representation of a **Signal Config Group**
([data model §5.12C](./05-data-model.md#512c-signalconfiggroup)): a named, reusable bundle of
signals plus their configuration. The same format is used for:

- The default pack bundled with the application (seeds the default signal config group).
- A group exported from the UI.
- Community packs imported into the UI (each import creates a new group).
- (Later) marketplace listings.

The contract is: **what is imported in YAML can be exported in equivalent YAML**, modulo credentials
and runtime-only state.

A pack carries **only signals and their configuration**. It deliberately carries no source
connections, no scopes, and no teams: scope is a property of the team a group is later attached to,
resolved at report time, not stored on a signal. This keeps packs portable and safe to share —
connectors provide access, teams own the board scope, and a pack is just the rules.

## 2. Core Concepts

- **Pack.** A named, versioned bundle of signals and their configuration — the on-disk form of a Signal Config Group.
- **Signal Config Group.** The in-app entity a pack maps to: a reusable bundle of signals, attached to any number of teams. See [data model §5.12C](./05-data-model.md#512c-signalconfiggroup).
- **Template.** A built-in signal shipped with the application. A template seeds a signal in a group; it is configuration, not executable code. Built-in signals are catalogued in §12.
- **Signal.** A named, structured rule expression over one entity type, carrying its own configuration (params, severity, enabled state). A signal is **scope-agnostic**: it is not assigned to any scope. Scope is resolved from the team at report time.
- **Condition.** A field/operator/value predicate validated against the selected connector capability schema.
- **Severity.** The importance level a finding from this signal should carry (`info`, `warning`, `critical`). Each signal declares a default; packs may override.
- **Capability schema.** Connector metadata describing available entity types, fields, operators, value providers, and field availability constraints.

## 3. File Structure

A Signal Pack is a single YAML file. Top-level shape:

```yaml
apiVersion: emradar.dev/v1
kind: SignalPack
metadata:
  name: scrum-team-health
  version: 1.2.0
  description: Sensible defaults for Scrum teams using Jira + GitLab.
  author: Serdar Tas
  license: Apache-2.0
  homepage: https://github.com/example/scrum-team-health-pack
  tags: [scrum, jira, gitlab]
spec:
  export_type: public_template
  signals:
    - name: Stale in-progress work item
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
            value: {amount: 7, unit: days}
      report_settings:
        severity: warning
        category: flow
      enabled: true
      origin: system_template
      template_key: stale-in-progress-work-item
```

On import, this pack becomes a Signal Config Group named `scrum-team-health` containing one signal.
The user then attaches the group to one or more teams; each team supplies the board scope at report
time.

The `apiVersion` and `kind` discriminator pattern is intentional: future kinds (e.g. `FieldMappingPack`, `ConnectorPreset`) will live alongside `SignalPack` under the same `emradar.dev/v1` umbrella.

## 4. Schema Versioning

- `apiVersion` is required. Current value: `emradar.dev/v1`.
- Adding a new optional field is a v1-compatible change. No bump.
- Removing a field, renaming a field, or changing field semantics requires a new `apiVersion` (e.g. `emradar.dev/v2`).
- EM Radar may continue to read `v1` packs after `v2` exists. When breaking, a one-shot in-app migration converts the user's stored config.
- The pack's own `metadata.version` is the **content** version (semver), independent of `apiVersion`. Bump the content version when the pack's signal selection or thresholds change.

## 5. Top-Level Fields

### 5.1 `apiVersion` (required, string)

Must be `emradar.dev/v1` for this specification.

### 5.2 `kind` (required, string)

Must be `SignalPack`.

### 5.3 `metadata` (required, object)

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes | Lowercase, kebab-case, unique within a user's local catalog. Pattern: `^[a-z][a-z0-9-]{1,62}[a-z0-9]$`. |
| `version` | string | yes | Semantic version of the pack's content. |
| `description` | string | yes | One-paragraph human description. |
| `author` | string | no | Pack author or org. |
| `license` | string | no | SPDX identifier. Recommended for shared packs. |
| `homepage` | string (URL) | no | Project page. |
| `tags` | string[] | no | Free-form tags for search/discovery. |
| `min_emradar_version` | string | no | Earliest EM Radar version this pack supports. EM Radar refuses to load incompatible packs. |

### 5.4 `spec` (required, object)

Holds the actual configuration.

| Field | Type | Required | Description |
|---|---|---|---|
| `export_type` | enum | yes | `private_backup` or `public_template`. Controls how aggressively org-specific condition values are scrubbed on export. See §15. |
| `signals` | array | yes | The signals in the group. Each is a scope-agnostic signal definition. See §9. |
| `field_mappings` | object | no | Optional Jira/GitLab field-mapping hints. See §11. |

A pack does not carry `connectors`, `scopes`, or `teams` — see §6 and §7.

## 6. What a Pack Does Not Contain

A pack is the export of a Signal Config Group, and a group is pure signal membership. Packs
therefore **never** carry:

- **Source connections.** Connectors provide access and live only in the local app, masked at rest
  ([ADR-0006](./ADRs/0006-token-storage.md)). A pack contains no `base_url`, no `auth`, no
  connector ids.
- **Scopes.** Scope (a Jira board) is a property of the **team** a group is attached to, resolved
  at report time — never stored on a signal or in a pack. There is no `scopes` block and no
  `target_scopes` field.
- **Teams.** Team membership and group↔team attachments are local configuration, not part of a
  portable pack.

A signal does declare its `entity_type` (e.g. `issue`, `merge_request`); when a group is attached
to a team, only signals whose entity type the team's scope can supply are evaluated.

## 7. Signal Config Group Mapping

Import and export map a pack to a Signal Config Group:

- **Export.** A group named `growth-team` with three signals exports to a pack whose
  `metadata.name` is `growth-team` and whose `spec.signals` are those three signals (with their
  configuration, minus any scrubbed org-specific values for public exports).
- **Import.** A pack creates a **new** Signal Config Group named from `metadata.name` (suffixed if
  the name already exists), containing one `SignalDefinition` per `spec.signals` entry. The user
  then attaches the new group to teams; no scope or connector mapping step is required.

Because a signal can belong to many groups, importing the same signal in two packs yields two
distinct signal definitions unless the user later deduplicates; packs do not share signal identity
across installs.

## 8. Signal Templates

Built-in signals ship as **templates**: pre-written signal definitions catalogued in §12. A
template is configuration, not executable code. Users may add a template to a group as-is, duplicate
it into an editable signal (`origin: user_created`), disable it, or restore the built-in default. A
template carries no scope — it is added to a group, and scope is resolved from the team later.

## 9. Signal Definitions

Each entry in `spec.signals` is a scope-agnostic signal. It carries its rule and configuration but
no scope — scope is resolved from the team a group is attached to.

```yaml
- id: sig-stale-fraud-defense
  name: Stale in-progress Scrum work
  description: Finds issues that stayed in progress longer than expected.
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
        value: {amount: 3, unit: days}
  report_settings:
    severity: warning
    category: flow
  enabled: true
  origin: system_template
  template_key: stale-in-progress-work-item
```

### 9.1 Signal Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | yes | Stable local signal id. |
| `name` | string | yes | Human-readable name, unique in the local workspace. |
| `description` | string | no | Shown in the builder and reports. |
| `entity_type` | string | yes | Connector-provided entity type such as `issue` or `merge_request`. |
| `expression` | object | yes | Rule expression. See §10. |
| `report_settings` | object | yes | Severity, category, and optional message template. |
| `enabled` | boolean | yes | Disabled signals are persisted but not evaluated. |
| `origin` | enum | yes | `system_template`, `user_created`, or `imported`. |
| `template_key` | string | no | Source template key when instantiated from a template. |

## 10. Rule Expressions

The MVP expression grammar is intentionally small:

```yaml
type: group
operator: all # all | any
conditions:
  - field: status_category
    operator: is
    value: In Progress
  - type: group
    operator: any
    conditions:
      - field: priority
        operator: is
        value: High
      - field: labels
        operator: contains
        value: customer-impact
```

Groups support `all` and `any`, with one level of nested grouping in MVP. Conditions use
field/operator/value triples. Fields, operators, and values are validated against the selected
connector capability schema.

Time-based fields include created/updated/resolved dates, age since created/updated, and age in
current status. Sprint-aware fields are evaluated only when the team's scope supplies sprint data
(scrum boards); on date-range/kanban runs, sprint-only signals are skipped at report time
([data model §6.7](./05-data-model.md#67-workingmode)).

## 11. Field Mapping Block (Optional)

Field mappings are technically separate from signals (they belong to connectors), but a pack may bundle a recommended mapping. The mapping block is **advisory**: the UI prompts the user to apply it; it is never silently merged.

```yaml
spec:
  field_mappings:
    jira:
      story_points: customfield_10016
      acceptance_criteria_heading: "### Acceptance Criteria"
      blocked_label: blocked
    gitlab:
      workitem_key_pattern: "[A-Z]+-\\d+"
```

## 12. Built-in Signal Template Catalog (MVP)

Each entry below lists the canonical template key, default severity, default condition values, and
the canonical evidence shape. These templates seed the product and can be duplicated into editable
signal definitions.

### 12.1 `stale-in-progress-work-item`
- **Default severity:** `warning`
- **Template defaults:**
  - `days_threshold` (integer, default `7`)
  - `exclude_labels` (string[], default `[]`)
- **Evidence:** `{ days_idle, last_updated_at, threshold }`

### 12.2 `blocked-without-update`
- **Default severity:** `critical`
- **Template defaults:**
  - `days_threshold` (integer, default `3`)
- **Evidence:** `{ days_blocked_idle, last_updated_at, threshold }`

### 12.3 `story-without-acceptance-criteria`
- **Default severity:** `warning`
- **Template defaults:** none
- **Evidence:** `{ workitem_type, has_description }`

### 12.4 `story-without-parent-epic`
- **Default severity:** `info`
- **Template defaults:** none
- **Evidence:** `{ workitem_type }`

### 12.5 `epic-too-broad`
- **Default severity:** `warning`
- **Template defaults:**
  - `max_children` (integer, default `15`)
- **Evidence:** `{ child_count, threshold }`

### 12.6 `epic-without-measurable-description`
- **Default severity:** `info`
- **Template defaults:**
  - `min_description_length` (integer, default `100`)
- **Evidence:** `{ description_length, threshold }`

### 12.7 `repeated-carry-over`
- **Default severity:** `warning`
- **Template defaults:**
  - `min_sprint_count` (integer, default `2`)
- **Evidence:** `{ sprint_count, sprint_names[] }`

### 12.8 `sprint-scope-churn`
- **Default severity:** `warning`
- **Template defaults:**
  - `warning_pct` (number, default `20.0`)
  - `critical_pct` (number, default `35.0`)
- **Notes:** This signal escalates its own severity from `warning` to `critical` when `critical_pct` is reached. `severity` field in the pack acts as a ceiling.
- **Evidence:** `{ original_count, added_count, churn_pct }`

### 12.9 `mergerequest-waiting-too-long`
- **Default severity:** `warning`
- **Template defaults:**
  - `days_threshold` (integer, default `3`)
- **Evidence:** `{ age_days, threshold, last_review_at }`

### 12.10 `mergerequest-without-linked-workitem`
- **Default severity:** `warning`
- **Template defaults:**
  - `workitem_key_pattern` (string, default `"[A-Z]+-\\d+"`)
- **Evidence:** `{ checked_fields: [title, description, source_branch] }`

### 12.11 `large-mergerequest-risk`
- **Default severity:** `warning`
- **Template defaults:**
  - `max_files` (integer, default `20`)
  - `max_changes` (integer, default `500`)
- **Evidence:** `{ files_changed, additions, deletions, total_changes }`

### 12.12 `failing-pipeline-too-long`
- **Default severity:** `warning`
- **Template defaults:**
  - `days_threshold` (integer, default `1`)
- **Evidence:** `{ pipeline_status, hours_failing }`

### 12.13 `merged-without-enough-approval`
- **Default severity:** `critical`
- **Template defaults:**
  - `min_approvals` (integer, default `1`)
- **Evidence:** `{ approval_count, threshold }`

## 13. Validation Rules

A pack is **rejected** at import time if any of the following are true:

1. `apiVersion` is missing or unknown.
2. `kind` is not `SignalPack`.
3. `metadata.name` is missing or does not match the kebab-case pattern.
4. `metadata.version` is not a valid semver string.
5. `spec.signals` is missing or empty.
6. A signal expression uses a field unavailable for its connector type or entity type.
7. A signal expression uses an operator invalid for the chosen field type.
8. `min_emradar_version`, if set, is greater than the running EM Radar version.
9. The YAML contains any field or section starting with `!`, `&`, `*`, or `<<` outside of standard YAML anchors and merge keys used safely.
10. The YAML contains tagged constructors (`!!python/object` and similar). Only safe-load is permitted.

Soft validation **warnings** (import succeeds, UI shows a banner):

- A signal's `report_settings.severity` differs significantly from the template default (e.g. demoting a default-`critical` template to `info`).
- An imported group name collides with an existing group (import proceeds with a suffixed name).
- A `field_mappings` block is present and differs from the user's existing mapping.

## 14. Forbidden Content

The pack format is **declarative only**. Per [REQ-NF-012](./02-requirements.md), the following are explicitly forbidden:

- Executable code in any field (Python, JavaScript, shell, expression languages).
- Template expansion that reads environment variables or files.
- References to remote URLs that EM Radar would fetch automatically.
- Credentials of any kind. Imports containing fields named `token`, `password`, `api_key`, `secret`, `authorization` are rejected.

## 15. Export Behavior

When the user exports a Signal Config Group:

- `metadata.name` defaults to the group's name unless the user renames it.
- All of the group's signals are included with their configuration.
- The user chooses `private_backup` or `public_template`:
  - `private_backup` keeps org-specific condition values (e.g. concrete label or status names) verbatim — best for moving your own setup to another machine.
  - `public_template` prompts the user to review and scrub org-specific condition values before sharing, so generic rules can be shared without leaking internal naming.
- Credential fields are never included. Neither are connectors, scopes, or teams (§6).
- Field mappings are included only if the user opts in.

## 16. Import Behavior

When the user imports a pack:

- The pack is validated per §13 before any state changes.
- A preview is shown: the resulting group name, its signals, and any validation warnings.
- The user explicitly confirms.
- Import creates a **new Signal Config Group** named from `metadata.name` (suffixed on collision), containing one signal per `spec.signals` entry. There is no connector or scope mapping step.
- The user attaches the new group to teams afterward; each team supplies the board scope at report time.
- The original imported YAML is stored in the pack history table for round-trip export.

## 17. Examples

### 17.1 Public template pack

```yaml
apiVersion: emradar.dev/v1
kind: SignalPack
metadata:
  name: tighter-mr-review
  version: 0.1.0
  description: Tighten MR review latency to 1 day.
spec:
  export_type: public_template
  signals:
    - name: Merge request waiting longer than 1 day
      entity_type: merge_request
      expression:
        type: group
        operator: all
        conditions:
          - field: state
            operator: is
            value: opened
          - field: age_since_last_review_activity
            operator: greater_than
            value: {amount: 1, unit: days}
      report_settings:
        severity: warning
        category: flow
      enabled: true
      origin: system_template
      template_key: mergerequest-waiting-too-long
```

### 17.2 Private backup of a multi-signal group

```yaml
apiVersion: emradar.dev/v1
kind: SignalPack
metadata:
  name: platform-team-pack
  version: 1.0.0
  description: Stricter rules used by the Platform team.
spec:
  export_type: private_backup
  signals:
    - id: sig-platform-review
      name: Platform MR waiting too long
      entity_type: merge_request
      expression:
        type: group
        operator: all
        conditions:
          - field: age_since_last_review_activity
            operator: greater_than
            value: {amount: 1, unit: days}
      report_settings:
        severity: critical
        category: flow
      enabled: true
      origin: user_created
    - id: sig-platform-stale
      name: Platform stale in-progress work
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
            value: {amount: 5, unit: days}
      report_settings:
        severity: warning
        category: flow
      enabled: true
      origin: user_created
```

On import this becomes a group `platform-team-pack` with two signals, ready to attach to any team.

### 17.3 Disabled imported signal

```yaml
apiVersion: emradar.dev/v1
kind: SignalPack
metadata:
  name: partial-import
  version: 0.1.0
  description: Example of a signal imported disabled (kept off until reviewed).
spec:
  export_type: private_backup
  signals:
    - id: sig-disabled
      name: Imported stale work signal
      entity_type: issue
      expression:
        type: group
        operator: all
        conditions:
          - field: status_category
            operator: is
            value: In Progress
      report_settings:
        severity: warning
        category: flow
      enabled: false
      origin: imported
```

## 18. Forward Compatibility (Later)

The following are **not** in MVP but are reserved in the schema so they can be added without a `v2` bump:

- `spec.views[]` for named report views composed of signal subsets.
- `metadata.signing` for marketplace signature metadata.

Reserving these names today prevents future user-pack collisions.
