# EM Radar — Signal Pack YAML Specification

- **Status:** Draft v0.1
- **Schema version:** `emradar.dev/v1`
- **Date:** 2026-06-01
- **Owner:** Serdar Tas
- **Related:** [05-data-model.md](./05-data-model.md), [02-requirements.md](./02-requirements.md) §4.5

## 1. Purpose

This document specifies the YAML format used to describe **Signal Packs** in EM Radar.

A Signal Pack is the unit of configuration shared between users and (later) the marketplace. The same format is used for:

- The default pack bundled with the application.
- User edits exported from the UI.
- Community packs imported into the UI.
- (Later) marketplace listings.

The contract is: **what is imported in YAML can be exported in equivalent YAML**, modulo credentials and runtime-only state.

## 2. Core Concepts

- **Pack.** A named, versioned bundle of signal configurations.
- **Signal.** A built-in detector identified by a stable `id`. Has parameters with defaults. A pack overrides parameters and toggles enable/disable.
- **Parameter.** A typed input to a signal (e.g. `days_threshold: 7`). Each signal documents its parameters and defaults.
- **Severity.** The importance level a finding from this signal should carry (`info`, `warning`, `critical`). Each signal declares a default; packs may override.
- **Scope.** Optional filters limiting where the signal evaluates (e.g. only certain projects, repositories, or labels).

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
  defaults:
    severity_override: null
  signals:
    - id: stale-in-progress-work-item
      enabled: true
      severity: warning
      params:
        days_threshold: 7
    - id: blocked-without-update
      enabled: true
      severity: critical
      params:
        days_threshold: 3
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
| `defaults` | object | no | Pack-level defaults applied to every signal unless overridden. See §6. |
| `signals` | array | yes | List of signal entries. See §7. |
| `field_mappings` | object | no | Optional Jira/GitLab field-mapping hints. See §9. |

## 6. Pack-Level Defaults

```yaml
spec:
  defaults:
    severity_override: warning      # forces every signal to this severity unless the signal itself sets one
    scope:
      project_keys: [ABC, XYZ]
      repository_paths: [engineering/*]
```

- `severity_override` (enum, optional): if set, all signals without their own `severity` inherit this. Useful for "strict" or "lenient" pack presets.
- `scope` (object, optional): same shape as signal-level `scope` (§7.4). Applied to every signal unless that signal sets its own.

## 7. Signal Entries

Each entry in `spec.signals` configures one built-in signal.

```yaml
- id: stale-in-progress-work-item
  enabled: true
  severity: warning
  scope:
    project_keys: [ABC]
    workitem_types: [story, task, bug]
  params:
    days_threshold: 7
    exclude_labels: [parked, on-hold]
```

### 7.1 `id` (required, string)

Stable ID from the built-in signal catalog (§10). Unknown IDs are a validation error.

### 7.2 `enabled` (required, boolean)

If `false`, the signal is not evaluated. Disabled signals are still kept in the pack so users can re-enable without losing their parameter overrides.

### 7.3 `severity` (optional, enum)

`info`, `warning`, or `critical`. If omitted, falls back to `defaults.severity_override`, then to the signal's catalog default.

### 7.4 `scope` (optional, object)

All fields are optional; specifying none means "no scope restriction".

| Field | Type | Applies to | Description |
|---|---|---|---|
| `project_keys` | string[] | workitem signals | Restrict to Jira-style project keys. |
| `repository_paths` | string[] (glob) | mergerequest signals | Restrict to repos by full path; supports `*` wildcards. |
| `workitem_types` | enum[] | workitem signals | Restrict to specific types (see [data model §6.1](./05-data-model.md#61-workitemtype)). |
| `labels` | string[] | workitem signals | Restrict to items carrying any of these labels. |
| `exclude_labels` | string[] | workitem signals | Skip items carrying any of these labels. |
| `branches` | string[] (glob) | mergerequest signals | Restrict by target branch. |

### 7.5 `params` (optional, object)

A free-form object whose keys depend on the signal. Validated against the signal's declared parameter schema (§10). Unknown keys are a validation error.

## 8. Severity Resolution Order

For a given signal, the effective severity is resolved as:

1. Signal entry's `severity` field (if set).
2. Pack `defaults.severity_override` (if set).
3. Signal catalog default (always set).

## 9. Field Mapping Block (Optional)

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

## 10. Built-in Signal Catalog (MVP)

Each entry below lists the canonical `id`, default severity, default parameters, and the canonical evidence shape. These are the only signals available in MVP. User-defined declarative signals are out of MVP scope (see [requirements REQ-F-034](./02-requirements.md)).

### 10.1 `stale-in-progress-work-item`
- **Default severity:** `warning`
- **Params:**
  - `days_threshold` (integer, default `7`)
  - `exclude_labels` (string[], default `[]`)
- **Evidence:** `{ days_idle, last_updated_at, threshold }`

### 10.2 `blocked-without-update`
- **Default severity:** `critical`
- **Params:**
  - `days_threshold` (integer, default `3`)
- **Evidence:** `{ days_blocked_idle, last_updated_at, threshold }`

### 10.3 `story-without-acceptance-criteria`
- **Default severity:** `warning`
- **Params:** none
- **Evidence:** `{ workitem_type, has_description }`

### 10.4 `story-without-parent-epic`
- **Default severity:** `info`
- **Params:** none
- **Evidence:** `{ workitem_type }`

### 10.5 `epic-too-broad`
- **Default severity:** `warning`
- **Params:**
  - `max_children` (integer, default `15`)
- **Evidence:** `{ child_count, threshold }`

### 10.6 `epic-without-measurable-description`
- **Default severity:** `info`
- **Params:**
  - `min_description_length` (integer, default `100`)
- **Evidence:** `{ description_length, threshold }`

### 10.7 `repeated-carry-over`
- **Default severity:** `warning`
- **Params:**
  - `min_sprint_count` (integer, default `2`)
- **Evidence:** `{ sprint_count, sprint_names[] }`

### 10.8 `sprint-scope-churn`
- **Default severity:** `warning`
- **Params:**
  - `warning_pct` (number, default `20.0`)
  - `critical_pct` (number, default `35.0`)
- **Notes:** This signal escalates its own severity from `warning` to `critical` when `critical_pct` is reached. `severity` field in the pack acts as a ceiling.
- **Evidence:** `{ original_count, added_count, churn_pct }`

### 10.9 `mergerequest-waiting-too-long`
- **Default severity:** `warning`
- **Params:**
  - `days_threshold` (integer, default `3`)
- **Evidence:** `{ age_days, threshold, last_review_at }`

### 10.10 `mergerequest-without-linked-workitem`
- **Default severity:** `warning`
- **Params:**
  - `workitem_key_pattern` (string, default `"[A-Z]+-\\d+"`)
- **Evidence:** `{ checked_fields: [title, description, source_branch] }`

### 10.11 `large-mergerequest-risk`
- **Default severity:** `warning`
- **Params:**
  - `max_files` (integer, default `20`)
  - `max_changes` (integer, default `500`)
- **Evidence:** `{ files_changed, additions, deletions, total_changes }`

### 10.12 `failing-pipeline-too-long`
- **Default severity:** `warning`
- **Params:**
  - `days_threshold` (integer, default `1`)
- **Evidence:** `{ pipeline_status, hours_failing }`

### 10.13 `merged-without-enough-approval`
- **Default severity:** `critical`
- **Params:**
  - `min_approvals` (integer, default `1`)
- **Evidence:** `{ approval_count, threshold }`

## 11. Validation Rules

A pack is **rejected** at import time if any of the following are true:

1. `apiVersion` is missing or unknown.
2. `kind` is not `SignalPack`.
3. `metadata.name` is missing or does not match the kebab-case pattern.
4. `metadata.version` is not a valid semver string.
5. Any signal entry references an `id` not present in the built-in catalog.
6. Any signal entry includes `params` keys not declared for that signal.
7. Any signal entry includes `params` whose types do not match the declared types.
8. `min_emradar_version`, if set, is greater than the running EM Radar version.
9. The YAML contains any field or section starting with `!`, `&`, `*`, or `<<` outside of standard YAML anchors and merge keys used safely.
10. The YAML contains tagged constructors (`!!python/object` and similar). Only safe-load is permitted.

Soft validation **warnings** (import succeeds, UI shows a banner):

- A signal's `severity` differs significantly from the catalog default (e.g. demoting a default-`critical` signal to `info`).
- A `scope` filter targets a `project_key` or `repository_path` that does not currently exist in the user's connected sources.
- A `field_mappings` block is present and differs from the user's existing mapping.

## 12. Forbidden Content

The pack format is **declarative only**. Per [REQ-NF-012](./02-requirements.md), the following are explicitly forbidden:

- Executable code in any field (Python, JavaScript, shell, expression languages).
- Template expansion that reads environment variables or files.
- References to remote URLs that EM Radar would fetch automatically.
- Credentials of any kind. Imports containing fields named `token`, `password`, `api_key`, `secret`, `authorization` are rejected.

## 13. Export Behavior

When the user exports their current configuration:

- The exported file is a complete, self-contained pack.
- `metadata.name` defaults to `local-overrides-<timestamp>` unless the user names it.
- Every signal that has been touched (enabled, disabled, parameter-overridden, severity-overridden) is included.
- Untouched signals are **omitted** by default (a "minimal diff" export). A "full snapshot" export option includes every signal with its current effective values.
- Credential fields are never included.
- Field mappings are included only if the user opts in.

## 14. Import Behavior

When the user imports a pack:

- The pack is validated per §11 before any state changes.
- A diff preview is shown: which signals will be enabled/disabled, which parameters will change.
- The user explicitly confirms.
- The import is **additive**: signals not mentioned in the imported pack keep their current local settings unless the user picks "replace all".
- The original imported YAML is stored in the pack history table for round-trip export.

## 15. Examples

### 15.1 Minimal pack (overrides one signal)

```yaml
apiVersion: emradar.dev/v1
kind: SignalPack
metadata:
  name: tighter-mr-review
  version: 0.1.0
  description: Tighten MR review latency to 1 day.
spec:
  signals:
    - id: mergerequest-waiting-too-long
      enabled: true
      params:
        days_threshold: 1
```

### 15.2 Scoped pack (platform team only)

```yaml
apiVersion: emradar.dev/v1
kind: SignalPack
metadata:
  name: platform-team-pack
  version: 1.0.0
  description: Stricter rules for the Platform team's repos.
spec:
  defaults:
    scope:
      repository_paths: [engineering/platform/*]
  signals:
    - id: mergerequest-waiting-too-long
      enabled: true
      severity: critical
      params:
        days_threshold: 1
    - id: large-mergerequest-risk
      enabled: true
      params:
        max_files: 10
        max_changes: 300
```

### 15.3 Disabling a default signal

```yaml
apiVersion: emradar.dev/v1
kind: SignalPack
metadata:
  name: no-epic-description-checks
  version: 0.1.0
  description: Our epics live in Confluence; skip description checks.
spec:
  signals:
    - id: epic-without-measurable-description
      enabled: false
```

## 16. Forward Compatibility (Later)

The following are **not** in MVP but are reserved in the schema so they can be added without a `v2` bump:

- `spec.custom_signals[]` for user-defined declarative signals. The grammar (likely a restricted expression language over the canonical model) will be specified in a separate ADR when this work begins. Until then, packs using `custom_signals` are rejected.
- `spec.views[]` for named report views composed of signal subsets.
- `metadata.signing` for marketplace signature metadata.

Reserving these names today prevents future user-pack collisions.
