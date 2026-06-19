# EM Radar — Signal Pack YAML Specification

- **Status:** Draft v0.2
- **Schema version:** `emradar.dev/v1`
- **Date:** 2026-06-01
- **Owner:** Serdar Tas
- **Related:** [05-data-model.md](./05-data-model.md), [02-requirements.md](./02-requirements.md) §4.5, [12-revised-signal-requirements.md](./12-revised-signal-requirements.md)

## 1. Purpose

This document specifies the YAML format used to describe **Signal Packs** in EM Radar.

A Signal Pack is the unit of configuration shared between users and (later) the marketplace. The same format is used for:

- The default pack bundled with the application.
- User edits exported from the UI.
- Community packs imported into the UI.
- (Later) marketplace listings.

The contract is: **what is imported in YAML can be exported in equivalent YAML**, modulo credentials and runtime-only state.

This document reflects the revised post-UAT signal model: connectors provide access, scopes select
where a signal applies, and signals define what rule is evaluated. See
[12-revised-signal-requirements](./12-revised-signal-requirements.md) for the product rationale and
UI behavior.

## 2. Core Concepts

- **Pack.** A named, versioned bundle of signal templates, signal definitions, and optional scope mappings.
- **Template.** A reusable signal definition that is not runnable until instantiated with target scopes. Built-in signals are shipped as templates.
- **Signal.** A named, structured rule expression over one entity type, assigned to one or more target scopes.
- **Condition.** A field/operator/value predicate validated against the selected connector capability schema.
- **Severity.** The importance level a finding from this signal should carry (`info`, `warning`, `critical`). Each signal declares a default; packs may override.
- **Scope.** A reusable connector-local data subset, such as a Jira board, Jira project, saved filter, GitLab repository, or GitLab project.
- **Capability schema.** Connector metadata describing available entity types, scope types, fields, operators, value providers, and field availability constraints.

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
  templates:
    - key: stale-in-progress-work-item
      name: Stale in-progress work item
      required_connector_type: jira
      entity_type: issue
      required_scope_capabilities: [statuses]
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
```

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
| `export_type` | enum | yes | `private_backup` or `public_template`. See §13. |
| `connectors` | array | no | Private backup connector references. Never includes secrets. See §6. |
| `scopes` | array | no | Private backup scope definitions. See §7. |
| `templates` | array | no | Public shareable signal templates that require local scope selection on import. See §8. |
| `signals` | array | no | Runnable signal definitions with explicit `target_scopes`. Required for private backup exports. See §9. |
| `field_mappings` | object | no | Optional Jira/GitLab field-mapping hints. See §11. |

## 6. Connector References

```yaml
spec:
  connectors:
    - local_ref: jira-bol
      connector_type: jira
      name: Jira - bol.com
      base_url: https://example.atlassian.net
      auth: omitted
```

Connector references are allowed only for `private_backup` exports. They are used to help the
importer map exported scopes and signals to local connectors. Secrets are always omitted.

## 7. Scope Definitions

Scopes are reusable connector-local targets.

```yaml
- local_ref: fraud-defense-board
  connector_ref: jira-bol
  name: Fraud Defense Scrum Board
  scope_type: board
  external_ref:
    type: jira_board
    id: "123"
    key: null
    name: Fraud Defense Scrum Board
  capabilities: [sprint, statuses, labels]
```

Scope definitions are allowed only for `private_backup` exports. Public templates replace concrete
scope references with `required_connector_type` and `required_scope_capabilities`.

## 8. Signal Templates

Templates are reusable signal definitions. They are not runnable until the importing user chooses
target scopes.

```yaml
- key: support-ticket-open-longer-than-3-days
  name: Support ticket open longer than 3 days
  description: Finds support tickets that have not closed within 3 days.
  required_connector_type: jira
  entity_type: issue
  required_scope_capabilities: [statuses]
  expression:
    type: group
    operator: all
    conditions:
      - field: status_category
        operator: is_not
        value: Done
      - field: age_since_created
        operator: greater_than
        value: {amount: 3, unit: days}
  report_settings:
    severity: critical
    category: support
  enabled_by_default: true
```

Built-in signals are represented as templates. Users may instantiate them as-is, duplicate them,
edit the duplicate, disable an instance, and restore the built-in default template.

## 9. Runnable Signal Definitions

Each entry in `spec.signals` is a runnable signal. It must include explicit `target_scopes` unless
it is imported disabled for later mapping.

```yaml
- id: sig-stale-fraud-defense
  name: Stale in-progress Scrum work
  description: Finds issues that stayed in progress longer than expected.
  entity_type: issue
  target_scopes:
    - connector_ref: jira-bol
      scope_ref: fraud-defense-board
      scope_type: board
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
| `target_scopes` | array | yes | One or more scopes of the same connector type and entity type for MVP. |
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
field/operator/value triples. Fields, operators, values, and availability are validated against the
selected connector capability schema and target scope capabilities.

Time-based fields include created/updated/resolved dates, age since created/updated, and age in
current status. Sprint-aware fields are available only for scopes with sprint capability.

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
5. A runnable enabled signal has no `target_scopes`.
6. A signal or template expression uses a field unavailable for its connector type, entity type, or selected scope capabilities.
7. A signal or template expression uses an operator invalid for the chosen field type.
8. `min_emradar_version`, if set, is greater than the running EM Radar version.
9. The YAML contains any field or section starting with `!`, `&`, `*`, or `<<` outside of standard YAML anchors and merge keys used safely.
10. The YAML contains tagged constructors (`!!python/object` and similar). Only safe-load is permitted.

Soft validation **warnings** (import succeeds, UI shows a banner):

- A signal's `report_settings.severity` differs significantly from the template default (e.g. demoting a default-`critical` template to `info`).
- A private backup scope cannot be matched to an existing local connector scope.
- A `field_mappings` block is present and differs from the user's existing mapping.

## 14. Forbidden Content

The pack format is **declarative only**. Per [REQ-NF-012](./02-requirements.md), the following are explicitly forbidden:

- Executable code in any field (Python, JavaScript, shell, expression languages).
- Template expansion that reads environment variables or files.
- References to remote URLs that EM Radar would fetch automatically.
- Credentials of any kind. Imports containing fields named `token`, `password`, `api_key`, `secret`, `authorization` are rejected.

## 15. Export Behavior

When the user exports their current configuration:

- The user chooses `private_backup` or `public_template`.
- Private backup exports include connector references, scope definitions, and runnable signals with `target_scopes`.
- Public template exports include templates and required capabilities, not connector/scope ids.
- `metadata.name` defaults to `local-overrides-<timestamp>` unless the user names it.
- Credential fields are never included.
- Field mappings are included only if the user opts in.

## 16. Import Behavior

When the user imports a pack:

- The pack is validated per §13 before any state changes.
- A preview is shown: connectors, scopes, templates, signals, unresolved mappings, and validation warnings.
- The user explicitly confirms.
- Private backup imports try to map connectors and scopes by type, URL, external id, key, and name.
- Public template imports require the user to choose local connector and target scopes before enabling imported signals.
- Signals with unresolved mappings are imported disabled until fixed.
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
  templates:
    - key: tighter-mr-review
      name: Merge request waiting longer than 1 day
      required_connector_type: gitlab
      entity_type: merge_request
      required_scope_capabilities: []
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
      enabled_by_default: true
```

### 17.2 Private backup pack with scope mapping

```yaml
apiVersion: emradar.dev/v1
kind: SignalPack
metadata:
  name: platform-team-pack
  version: 1.0.0
  description: Stricter rules for the Platform team's repos.
spec:
  export_type: private_backup
  connectors:
    - local_ref: gitlab-main
      connector_type: gitlab
      name: GitLab
      base_url: https://gitlab.example.com
      auth: omitted
  scopes:
    - local_ref: platform-repos
      connector_ref: gitlab-main
      name: Platform repositories
      scope_type: repository
      external_ref:
        type: gitlab_project
        id: "42"
        key: engineering/platform/api
        name: engineering/platform/api
      capabilities: []
  signals:
    - id: sig-platform-review
      name: Platform MR waiting too long
      entity_type: merge_request
      target_scopes:
        - connector_ref: gitlab-main
          scope_ref: platform-repos
          scope_type: repository
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
```

### 17.3 Disabled imported signal with unresolved scope

```yaml
apiVersion: emradar.dev/v1
kind: SignalPack
metadata:
  name: unmapped-import
  version: 0.1.0
  description: Example of a signal that needs target scope resolution.
spec:
  export_type: private_backup
  signals:
    - id: sig-unmapped
      name: Imported stale work signal
      entity_type: issue
      target_scopes: []
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
