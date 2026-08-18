# EM Radar — Signal Pack YAML Specification

- **Status:** Draft v0.3
- **Schema version:** `emradar.dev/v1`
- **Date:** 2026-06-26
- **Owner:** Serdar Tas
- **Related:** [05-data-model.md](./05-data-model.md), [02-requirements.md](./02-requirements.md) §4.5

## 1. Purpose

This document specifies the YAML format used to describe **Signal Packs** in EM Radar.

A Signal Pack is the import/export representation of one or more **Signal Config Groups**
([data model §5.12C](./05-data-model.md#512c-signalconfiggroup)): named, reusable bundles of
signals plus their configuration. A pack serializes every referenced signal **once** under
`spec.signals` and lists the groups under `spec.groups`, where each group references its member
signals **by name**. This lets several groups that share a signal export to a single file without
duplicating the signal definition. The same format is used for:

- The default pack bundled with the application (seeds the default signal config group).
- One or more groups exported together from the UI.
- Community packs imported into the UI (each import may create several groups).
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
- **Template.** A pre-authored signal definition shipped with the application (the default pack). A template seeds a signal in a group; it is configuration, not executable code, and carries no privileged behavior — a user can recreate the same signal from scratch. Templates are catalogued in §12.
- **Signal.** A named, structured rule expression over one signal entity type, carrying its own
  configuration (params, severity). In MVP, `issue` belongs to the work-tracking
  domain — the **task-board source** — and `merge_request` belongs to the code-repository domain —
  the **code source**. These entity types line up 1:1 with the two team sources of the same names
  ([data model §5.12](./05-data-model.md#512-teamprofile)). A signal selects neither a connection nor
  a project, board, or repository; the team supplies compatible source data at report time.
  Cross-domain signals are deferred until after MVP.
- **Condition.** A field/operator/value predicate validated against capability schemas for the
  signal's declared entity type. Fields are **canonical and connector-independent**: a condition like
  `status_category is In Progress` or `age_in_current_status > 7 days` means the same thing whatever
  connector supplied the data (Jira today, GitHub or Linear later), because signals filter the
  canonical model, never raw source payloads.
- **Severity.** The importance level a finding from this signal should carry (`info`, `warning`, `critical`). Each signal declares a default; packs may override.
- **Capability schema.** Connector metadata describing available entity types, fields, operators,
  value providers, and field availability constraints.

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
| `signals` | array | yes | The signal definitions referenced by the pack, each serialized once and declaring one signal entity type. See §9. |
| `groups` | array | no | The signal config groups in the pack. Each entry references its member signals by name. See §7. When omitted, the pack is read as a single legacy group (back-compat). |
| `field_mappings` | object | no | Optional Jira/GitLab field-mapping hints. See §11. |

A pack does not carry `connectors`, `scopes`, or `teams` — see §6 and §7.

### 5.5 `spec.groups[]` (optional, array)

Each entry describes one Signal Config Group:

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes | Group name, unique in the local workspace (suffixed on collision when keeping both). |
| `description` | string | no | Group description. |
| `signals` | string[] | yes | Names of member signals, each of which must appear in `spec.signals`. |

A signal may be referenced by several groups; it is still serialized only once in `spec.signals`.

## 6. What a Pack Does Not Contain

A pack is the export of a Signal Config Group, and a group is pure signal membership. Packs
therefore **never** carry:

- **Source connections.** Connectors provide access and live only in the local app, masked at rest
  ([ADR-0006](./ADRs/0006-token-storage.md)). A pack contains no `base_url`, no `auth`, no
  connector ids.
- **Team source selections.** A Jira project/board pair is a property of the **team** a group is
  attached to, resolved at report time — never stored on a signal or in a pack. There is no
  project, board, repository, or connection mapping block.
- **Teams.** Team membership and group↔team attachments are local configuration, not part of a
  portable pack.

A signal declares exactly one `entity_type` in MVP (`issue` for work tracking or `merge_request`
for code repository). When a group is attached to a team, only signals whose entity type the
team's attached sources can supply are evaluated.

## 7. Signal Config Group Mapping

Import and export map a pack to one or more Signal Config Groups:

- **Export.** The user selects one or more groups. Every signal across the selection is written
  once to `spec.signals` (minus any scrubbed org-specific values for public exports), and each
  group is written to `spec.groups` referencing its signals by name.
- **Import.** A pack with `spec.groups` creates one Signal Config Group per entry, each containing
  the `SignalDefinition`s named in its `signals` list. Name collisions (for signals and groups) are
  resolved by the import conflict choice (§16). The user then attaches the new groups to teams; no
  scope or connector mapping step is required.

**Back-compat.** A pack with no `spec.groups` is read as a single legacy group named from
`metadata.name` containing every entry in `spec.signals` — the pre-v0.3 shape. Such packs still
import unchanged.

Because a signal can belong to many groups, importing the same signal name in two separate imports
yields distinct signal definitions (suffixed under "keep both"); packs do not share signal identity
across installs.

## 8. Signal Templates

The default pack's signals ship as **templates**: pre-written signal definitions catalogued in §12. A
template is configuration, not executable code, and has no privileged evaluation path — the engine
runs it exactly as it runs a user-authored signal, so any template can be recreated from scratch in
the builder. Users may add a template to a group as-is, duplicate it into an editable signal
(`origin: user_created`), disable it, or restore the shipped default. A template carries no scope —
it is added to a group, and scope is resolved from the team later.

## 9. Signal Definitions

Each entry in `spec.signals` carries its rule and configuration for one signal entity type. It
contains no connection, project, board, or repository selection; those are resolved from the team
to which a group is attached.

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
  origin: system_template
  template_key: stale-in-progress-work-item
```

### 9.1 Signal Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | yes | Stable local signal id. |
| `name` | string | yes | Human-readable name, unique in the local workspace. |
| `description` | string | no | Shown in the builder and reports. |
| `entity_type` | string | yes | Exactly one signal entity type in MVP: `issue` (work tracking) or `merge_request` (code repository). |
| `expression` | object | yes | Rule expression. See §10. |
| `report_settings` | object | yes | Severity, category, and optional message template. |
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

The Jira connector exposes the following additional work-item fields in its capability schema:

| Field | Type | Operators |
|---|---|---|
| `components` | `string_list` | `contains`, `does_not_contain`, `contains_any`, `does_not_contain_any` |
| `story_points` | `number` | `gt`, `lt`, `gte`, `lte`, `eq`, `neq`, `is_empty`, `is_not_empty` |
| `labels` | `string_list` | `contains`, `does_not_contain`, `contains_any`, `does_not_contain_any` |

Negative label filtering (formerly `exclude_labels`) is expressed using `labels does_not_contain`
or `labels does_not_contain_any`.

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

## 12. Default Pack Signal Catalog (MVP)

This is the catalog of signals in the **default pack** — the bundle seeded on first run. Each is a
declarative signal definition, not a hardcoded engine check: it is expressed entirely in the rule
grammar of §10 over the fields the connector capability schema exposes for its entity type. A user
can duplicate, edit, delete, or **recreate any of these from scratch in the UI rule builder** — the
"template" is just pre-authored seed content with no privileged behavior.

Each entry below lists the canonical template key, default severity, default condition values, and
the canonical evidence shape. Because severity is a fixed per-signal value (§5), none of these
signals escalates its own severity; a stricter tier is a second signal, which a user creates the same
way.

### 12.1 `stale-in-progress-work-item`
- **Default severity:** `warning`
- **Template defaults:**
  - `days_threshold` (integer, default `7`)
- **Evidence:** `{ days_idle, last_updated_at, threshold }`
- **Tip:** To exclude items by label, add a `labels does_not_contain` rule (e.g. `labels does_not_contain "wont-fix"`). To exclude by component, use `components does_not_contain`.

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
  - `churn_pct` (number, default `20.0`)
- **Notes:** Fixed severity, like every other signal — it does not self-escalate. To flag a stricter
  tier (e.g. 35% → `critical`), create a second signal with a higher threshold in the builder.
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
6. A signal expression uses a field unavailable for its declared entity type.
7. A signal expression uses an operator invalid for the chosen field type.
8. `min_emradar_version`, if set, is greater than the running EM Radar version.
9. The YAML contains any field or section starting with `!`, `&`, `*`, or `<<` outside of standard YAML anchors and merge keys used safely.
10. The YAML contains tagged constructors (`!!python/object` and similar). Only safe-load is permitted.
11. A `spec.groups[]` entry references a signal name that does not appear in `spec.signals`.

Soft validation **warnings** (import succeeds, UI shows a banner):

- A signal's `report_settings.severity` differs significantly from the template default (e.g. demoting a default-`critical` template to `info`).
- A `field_mappings` block is present and differs from the user's existing mapping.

Name collisions are not warnings: they are surfaced in the import preview and resolved by the
import conflict choice (§16).

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
- A preview is shown: the resulting groups, their signals, any validation warnings, and the names
  of signals and groups that **already exist** in the local workspace (clashes).
- If there are clashes, the user picks **one** resolution applied to the whole import:
  - **skip** — clashing signals and groups are not imported; a kept group that references an
    already-present signal name wires to the existing signal.
  - **overwrite** — clashing signals and groups are updated in place from the pack.
  - **keep both** — clashing signals and groups are imported under a suffixed name (e.g. `name (2)`);
    a kept group's references are rewired to the freshly suffixed signals.
  - **cancel** — nothing is written.
- With no clashes the import applies directly (equivalent to "keep both").
- Import creates the groups from `spec.groups` (or a single legacy group when `spec.groups` is
  absent — see §7). There is no connector or scope mapping step.
- The user attaches the new groups to teams afterward; each team supplies the board scope at report time.
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
      origin: imported
```

### 17.4 Multiple groups sharing a signal

```yaml
apiVersion: emradar.dev/v1
kind: SignalPack
metadata:
  name: team-health-bundle
  version: 1.0.0
  description: Two groups that reuse one shared signal.
spec:
  export_type: private_backup
  signals:
    - name: Stale in-progress work
      entity_type: issue
      expression:
        type: group
        operator: all
        conditions:
          - field: status_category
            operator: is
            value: in_progress
          - field: age_in_current_status
            operator: greater_than
            value: {amount: 5, unit: days}
      report_settings:
        severity: warning
        category: flow
      origin: user_created
  groups:
    - name: scrum-health
      signals: [Stale in-progress work]
    - name: flow-health
      signals: [Stale in-progress work]
```

On import this creates two groups, `scrum-health` and `flow-health`, both wired to a single
imported `Stale in-progress work` signal.

## 18. Forward Compatibility (Later)

The following are **not** in MVP but are reserved in the schema so they can be added without a `v2` bump:

- `spec.views[]` for named report views composed of signal subsets.
- `metadata.signing` for marketplace signature metadata.

Reserving these names today prevents future user-pack collisions.
