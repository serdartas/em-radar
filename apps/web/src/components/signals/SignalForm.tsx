// SPDX-License-Identifier: Apache-2.0

import { useState } from "react"

import { RuleValueControl } from "@/components/signals/RuleValueControl"
import { NO_VALUE_OPERATORS, defaultValueForRule } from "@/components/signals/ruleValue"
import { Button } from "@/components/ui/button"
import { Callout } from "@/components/ui/callout"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select } from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import type { SignalField } from "@/lib/connectors"
import type { JiraFieldInfo } from "@/lib/connections"
import { humanizeOperator } from "@/lib/operatorLabels"
import { SEVERITIES, type Severity } from "@/lib/severity"
import type { SignalDefinition, SignalDefinitionCreate } from "@/lib/signalDefinitions"

const MAX_RULES = 5

// Human-readable labels for known entity types; unknown types fall back to the raw value.
const ENTITY_TYPE_LABELS: Record<string, string> = {
  issue: "Work tracking / tickets (Jira)",
  merge_request: "Merge requests (GitLab)",
  sprint: "Sprints (Jira)",
}

// Full set of known categories. A free-text value outside this list is still
// rendered as a selectable option so an existing signal's category is never lost.
const CATEGORIES = ["flow", "hygiene", "quality", "sprint", "planning", "delivery"]

// Sentinel key used when the user selects "Custom field" before picking a specific field.
const CUSTOM_FIELD_KEY = "__custom__"

type Connector = "" | "AND" | "OR"

interface RuleRow {
  id: string
  field: string
  operator: string
  value: unknown
}

let rowIdCounter = 0

function nextRowId(): string {
  rowIdCounter += 1
  return `rule-${rowIdCounter}`
}

interface SignalFormProps {
  fieldsByEntityType: Record<string, SignalField[]>
  /** Discovered Jira custom fields, used to drive the custom-field picker and operator/value controls. */
  jiraCustomFields?: JiraFieldInfo[]
  /** When provided, the form opens prefilled in edit mode. */
  initialValue?: SignalDefinition
  /** Controls the heading and default submit button label. Defaults to "create". */
  mode?: "create" | "edit"
  /** Overrides the submit button label. Defaults to "Save signal" (create) or "Save changes" (edit). */
  submitLabel?: string
  onCancel: () => void
  onSave: (definition: SignalDefinitionCreate) => void
  pending: boolean
  errorMessage: string | null
}

export function SignalForm({
  fieldsByEntityType,
  jiraCustomFields = [],
  initialValue,
  mode = "create",
  submitLabel,
  onCancel,
  onSave,
  pending,
  errorMessage,
}: SignalFormProps) {
  const [name, setName] = useState(initialValue?.name ?? "")
  const [entityType, setEntityType] = useState(
    () =>
      initialValue?.entity_type ??
      (Object.keys(fieldsByEntityType)[0] ?? "issue"),
  )
  const [severity, setSeverity] = useState<Severity>(
    initialValue?.report_settings.severity ?? "warning",
  )
  const [category, setCategory] = useState(initialValue?.report_settings.category ?? CATEGORIES[0])
  const [message, setMessage] = useState(initialValue?.report_settings.message_template ?? "")

  // Built-in fields sorted by label, with "Custom field" appended at the end.
  // The "Custom field" entry is only added for the issue entity type because Jira custom
  // fields are not relevant to merge_request signals.
  const sortedBuiltinFields = [...(fieldsByEntityType[entityType] ?? [])].sort((a, b) =>
    a.label.localeCompare(b.label),
  )
  const showCustomFieldOption = entityType === "issue" && jiraCustomFields.length > 0
  const sortedCustomFields = [...jiraCustomFields].sort((a, b) => a.name.localeCompare(b.name))

  const firstField = sortedBuiltinFields[0]

  // Entity type options: all types reported by connected connectors, plus the persisted
  // type from initialValue so editing a sprint/unknown-type signal never loses it.
  const availableEntityTypes = Object.keys(fieldsByEntityType)
  const entityTypeOptions = [
    ...availableEntityTypes,
    ...(initialValue && !availableEntityTypes.includes(initialValue.entity_type)
      ? [initialValue.entity_type]
      : []),
  ]

  // Advanced-expression guard: detect when the stored expression cannot be faithfully
  // represented by the flat rule builder. A condition that is itself a group (has a
  // `conditions` array) or lacks a `field` key would be corrupted if we rebuilt from rows.
  const isAdvanced =
    mode === "edit" && initialValue != null && isAdvancedExpression(initialValue.expression)

  const [groupOperator, setGroupOperator] = useState<Connector>(() => {
    if (initialValue && !isAdvancedExpression(initialValue.expression)) {
      return parseExpression(initialValue.expression).groupOperator
    }
    return ""
  })

  const [rows, setRows] = useState<RuleRow[]>(() => {
    if (initialValue && !isAdvancedExpression(initialValue.expression)) {
      const { rows: parsed } = parseExpression(initialValue.expression)
      return parsed.length > 0 ? parsed : [makeRow(firstField)]
    }
    return [makeRow(firstField)]
  })

  function handleEntityTypeChange(newType: string) {
    setEntityType(newType)
    setGroupOperator("")
    const newFields = [...(fieldsByEntityType[newType] ?? [])].sort((a, b) =>
      a.label.localeCompare(b.label),
    )
    setRows([makeRow(newFields[0])])
  }

  function updateRow(index: number, patch: Partial<RuleRow>) {
    setRows((prev) => prev.map((row, current) => (current === index ? { ...row, ...patch } : row)))
  }

  function changeField(index: number, key: string) {
    if (key === CUSTOM_FIELD_KEY) {
      // User clicked "Custom field" — wait for the second picker selection.
      updateRow(index, { field: CUSTOM_FIELD_KEY, operator: "is", value: "" })
      return
    }
    const field = resolveField(key, sortedBuiltinFields, jiraCustomFields)
    const operator = field?.operators[0] ?? "is"
    updateRow(index, { field: key, operator, value: defaultValueForRule(field, operator) })
  }

  function changeCustomField(index: number, jiraFieldId: string) {
    const field = resolveField(jiraFieldId, sortedBuiltinFields, jiraCustomFields)
    const operator = field?.operators[0] ?? "is"
    updateRow(index, { field: jiraFieldId, operator, value: defaultValueForRule(field, operator) })
  }

  function changeOperator(index: number, operator: string) {
    const field = resolveField(rows[index].field, sortedBuiltinFields, jiraCustomFields)
    updateRow(index, { operator, value: defaultValueForRule(field, operator) })
  }

  function addRow(connector: Connector) {
    if (connector === "" || rows.length >= MAX_RULES) {
      return
    }
    setGroupOperator(connector)
    setRows((prev) => [...prev, makeRow(firstField)])
  }

  function removeRow(index: number) {
    setRows((prev) => prev.filter((_, current) => current !== index))
  }

  // A row still on the sentinel means the user opened "Custom field" but hasn't
  // chosen a concrete field yet — block save so no sentinel leaks into the expression.
  const hasSentinelRow = !isAdvanced && rows.some((row) => row.field === CUSTOM_FIELD_KEY)
  // Value-bearing rules must not have blank values; between ranges must have lower <= upper.
  const rowsValid = isAdvanced || rows.every(isRowValid)
  const canSave = name.trim().length > 0 && !pending && !hasSentinelRow && rowsValid

  const heading = mode === "edit" ? "Edit signal" : "Create signal"
  const buttonLabel = submitLabel ?? (mode === "edit" ? "Save changes" : "Save signal")

  function save() {
    if (!canSave) {
      return
    }
    onSave({
      name: name.trim(),
      entity_type: entityType,
      // Advanced expressions are preserved byte-for-byte; rebuilding from rows would corrupt them.
      expression: isAdvanced ? initialValue!.expression : buildExpression(rows, groupOperator),
      report_settings: {
        severity,
        category,
        message_template: message.trim() || null,
      },
      origin: initialValue?.origin ?? "user_created",
      template_key: initialValue?.template_key ?? null,
    })
  }

  return (
    <Card>
      <CardContent className="space-y-5 p-5">
        <h2 className="text-lg font-semibold">{heading}</h2>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="signal-name">Name</Label>
            <Input
              id="signal-name"
              onChange={(event) => setName(event.target.value)}
              placeholder="Unique signal name"
              value={name}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="signal-type">Type</Label>
            <Select
              disabled={isAdvanced}
              id="signal-type"
              onChange={(event) => handleEntityTypeChange(event.target.value)}
              value={entityType}
            >
              {entityTypeOptions.map((type) => (
                <option key={type} value={type}>
                  {ENTITY_TYPE_LABELS[type] ?? type}
                </option>
              ))}
            </Select>
          </div>
        </div>

        {isAdvanced ? (
          <Callout title="Advanced condition" variant="info">
            This signal uses a nested condition that cannot be displayed in the rule builder.
            To change the rules, export the signal pack and edit the YAML directly. You can
            still update the name, type, severity, category, and message above and below.
          </Callout>
        ) : (
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
                Rules
              </h3>
              <div className="h-px flex-1 bg-border" />
            </div>

            <ul className="space-y-2">
              {rows.map((row, index) => {
                const isUsingCustomField = isCustomFieldRow(row.field, sortedBuiltinFields)
                const field = resolveField(row.field, sortedBuiltinFields, jiraCustomFields)
                const fieldSelectValue = isUsingCustomField ? CUSTOM_FIELD_KEY : row.field
                const isLast = index === rows.length - 1
                return (
                  <li
                    className="flex flex-wrap items-end gap-2 rounded-md border border-border p-3"
                    key={row.id}
                  >
                    <div className="min-w-40 flex-1 space-y-1.5">
                      <Label htmlFor={`rule-field-${index}`}>Field</Label>
                      <Select
                        id={`rule-field-${index}`}
                        onChange={(event) => changeField(index, event.target.value)}
                        value={fieldSelectValue}
                      >
                        {sortedBuiltinFields.map((option) => (
                          <option key={option.key} value={option.key}>
                            {option.label}
                          </option>
                        ))}
                        {showCustomFieldOption && (
                          <option value={CUSTOM_FIELD_KEY}>Custom field</option>
                        )}
                      </Select>
                    </div>

                    {/* Second picker: revealed only when "Custom field" is active */}
                    {isUsingCustomField && (
                      <div className="min-w-40 flex-1 space-y-1.5">
                        <Label htmlFor={`rule-custom-field-${index}`}>Jira field</Label>
                        <Select
                          id={`rule-custom-field-${index}`}
                          onChange={(event) => changeCustomField(index, event.target.value)}
                          value={row.field === CUSTOM_FIELD_KEY ? "" : row.field}
                        >
                          {row.field === CUSTOM_FIELD_KEY && (
                            <option disabled value="">
                              Choose a field...
                            </option>
                          )}
                          {/* When the stored field id is no longer in discovered fields (field
                              deleted from Jira), keep it as a selectable option so the select
                              remains controlled and the user can replace it. */}
                          {row.field !== CUSTOM_FIELD_KEY &&
                            !sortedCustomFields.some((jf) => jf.id === row.field) && (
                              <option value={row.field}>{row.field}</option>
                            )}
                          {sortedCustomFields.map((jf) => (
                            <option key={jf.id} value={jf.id}>
                              {jf.name} ({jf.id})
                            </option>
                          ))}
                        </Select>
                      </div>
                    )}

                    {/* Suppress operator/value controls until a concrete field is resolved.
                        When row.field is the sentinel (Custom field picked, no specific
                        field chosen yet) there are no operators to show. */}
                    {row.field !== CUSTOM_FIELD_KEY && (
                      <>
                        <div className="min-w-36 flex-1 space-y-1.5">
                          <Label htmlFor={`rule-operator-${index}`}>Operator</Label>
                          <Select
                            id={`rule-operator-${index}`}
                            onChange={(event) => changeOperator(index, event.target.value)}
                            value={row.operator}
                          >
                            {(field?.operators ?? []).map((operator) => (
                              <option key={operator} value={operator}>
                                {humanizeOperator(operator)}
                              </option>
                            ))}
                          </Select>
                        </div>
                        {!NO_VALUE_OPERATORS.has(row.operator) && (
                          <div className="min-w-40 flex-1 space-y-1.5">
                            <Label htmlFor={`rule-value-${index}`}>Value</Label>
                            <RuleValueControl
                              field={field}
                              id={`rule-value-${index}`}
                              onChange={(value) => updateRow(index, { value })}
                              operator={row.operator}
                              value={row.value}
                            />
                          </div>
                        )}
                      </>
                    )}
                    <div className="w-28 space-y-1.5">
                      <Label htmlFor={`rule-connector-${index}`}>
                        {isLast ? "Add rule" : "Join"}
                      </Label>
                      {isLast ? (
                        rows.length < MAX_RULES ? (
                          <Select
                            id={`rule-connector-${index}`}
                            onChange={(event) => addRow(event.target.value as Connector)}
                            value=""
                          >
                            <option value="">--</option>
                            <option value="AND">AND</option>
                            <option value="OR">OR</option>
                          </Select>
                        ) : (
                          <p className="text-xs text-slate-400">Max {MAX_RULES}</p>
                        )
                      ) : (
                        <Select
                          aria-label={`Connector ${index + 1}`}
                          id={`rule-connector-${index}`}
                          onChange={(event) => setGroupOperator(event.target.value as Connector)}
                          value={groupOperator || "AND"}
                        >
                          <option value="AND">AND</option>
                          <option value="OR">OR</option>
                        </Select>
                      )}
                    </div>
                    {rows.length > 1 && (
                      <Button
                        aria-label={`Remove rule ${index + 1}`}
                        onClick={() => removeRow(index)}
                        size="sm"
                        variant="outline"
                      >
                        Remove
                      </Button>
                    )}
                  </li>
                )
              })}
            </ul>
          </div>
        )}

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="signal-severity">Severity</Label>
            <Select
              id="signal-severity"
              onChange={(event) => setSeverity(event.target.value as Severity)}
              value={severity}
            >
              {SEVERITIES.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="signal-category">Category</Label>
            <Select
              id="signal-category"
              onChange={(event) => setCategory(event.target.value)}
              value={category}
            >
              {/* If the persisted category is outside the known set, render it first so it
                  stays selectable and isn't silently replaced by the first option. */}
              {!CATEGORIES.includes(category) && (
                <option value={category}>{category}</option>
              )}
              {CATEGORIES.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </Select>
          </div>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="signal-message">Message</Label>
          <Textarea
            id="signal-message"
            onChange={(event) => setMessage(event.target.value)}
            placeholder="Optional report message shown for matches"
            value={message}
          />
        </div>

        {errorMessage && (
          <p className="text-sm text-red-700" role="alert">
            {errorMessage}
          </p>
        )}

        <div className="flex gap-2">
          <Button disabled={!canSave} onClick={save}>
            {pending ? "Saving..." : buttonLabel}
          </Button>
          <Button onClick={onCancel} variant="outline">
            Cancel
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Custom-field helpers
// ---------------------------------------------------------------------------

/**
 * Returns true when the given field key represents a discovered Jira custom field
 * (i.e. it is not a built-in field key and is not the sentinel CUSTOM_FIELD_KEY).
 */
function isCustomFieldRow(field: string, builtins: SignalField[]): boolean {
  return field === CUSTOM_FIELD_KEY || (field !== "" && !builtins.some((f) => f.key === field))
}

/**
 * Derives operator and allowed values for a Jira custom field from its field_type.
 * Returned as a partial SignalField so it can be used directly by RuleValueControl.
 */
function customFieldToSignalField(jiraField: JiraFieldInfo): SignalField {
  const { operators, values } = operatorsForJiraFieldType(jiraField.field_type)
  return {
    key: jiraField.id,
    label: jiraField.name,
    type: jiraField.field_type ?? "string",
    operators,
    values,
    value_provider: null,
    availability: null,
    entity_type: "issue",
  }
}

function operatorsForJiraFieldType(fieldType: string | null): {
  operators: string[]
  values: unknown[]
} {
  switch (fieldType) {
    case "number":
      return { operators: ["is", "greater_than", "less_than"], values: [] }
    case "string":
      return { operators: ["is_empty", "is_not_empty"], values: [] }
    case "option":
      return { operators: ["is", "is_not"], values: [] }
    case "array":
      // list[str] coercion means is/is_not always mismatch; contains/does_not_contain
      // compare correctly against list values and are in the engine allowlist.
      return { operators: ["contains", "does_not_contain"], values: [] }
    default:
      return { operators: ["is", "is_not", "is_empty", "is_not_empty"], values: [] }
  }
}

/**
 * Resolves a SignalField for a given field key, checking built-in fields first,
 * then discovered Jira custom fields. When a custom-field id is stored but the
 * field is no longer in jiraCustomFields (deleted in Jira or not yet loaded),
 * a generic fallback SignalField is synthesised so operator/value controls
 * remain usable rather than rendering an empty dropdown.
 */
function resolveField(
  key: string,
  builtins: SignalField[],
  jiraCustomFields: JiraFieldInfo[],
): SignalField | undefined {
  const builtin = builtins.find((f) => f.key === key)
  if (builtin) return builtin
  const jiraField = jiraCustomFields.find((f) => f.id === key)
  if (jiraField) return customFieldToSignalField(jiraField)
  // Fallback: the key looks like a custom-field id that is no longer discoverable.
  // Synthesise a generic field so the form remains usable.
  if (key && key !== CUSTOM_FIELD_KEY) {
    return {
      key,
      label: key,
      type: "string",
      operators: ["is", "is_not", "is_empty", "is_not_empty"],
      values: [],
      value_provider: null,
      availability: null,
      entity_type: "issue",
    }
  }
  return undefined
}

// ---------------------------------------------------------------------------
// Row / expression helpers
// ---------------------------------------------------------------------------

function makeRow(field: SignalField | undefined): RuleRow {
  const operator = field?.operators[0] ?? "is"
  return { id: nextRowId(), field: field?.key ?? "", operator, value: defaultValueForRule(field, operator) }
}

function buildExpression(rows: RuleRow[], groupOperator: Connector): Record<string, unknown> {
  return {
    type: "group",
    operator: groupOperator === "OR" ? "any" : "all",
    conditions: rows.map((row) => {
      const condition: Record<string, unknown> = { field: row.field, operator: row.operator }
      if (!NO_VALUE_OPERATORS.has(row.operator)) {
        condition.value = row.value
      }
      return condition
    }),
  }
}

/**
 * Returns true when the expression contains conditions that the flat rule builder
 * cannot faithfully represent — specifically, any condition that is itself a group
 * (has a `conditions` array) or is missing the `field` key required for a leaf rule.
 * Such expressions must be preserved verbatim on save to avoid data corruption.
 */
function isAdvancedExpression(expression: Record<string, unknown>): boolean {
  const conditions =
    (expression.conditions as Array<Record<string, unknown>> | undefined) ?? []
  return conditions.some((cond) => Array.isArray(cond.conditions) || !("field" in cond))
}

/**
 * Returns true when a rule row has a valid value.
 * - No-value operators (is_empty, is_not_empty) are always valid.
 * - The `between` operator requires both bounds to be non-empty; for numeric bounds,
 *   lower must not exceed upper; for date string bounds, the same check applies via
 *   lexicographic comparison (valid for ISO 8601 dates).
 * - All other value-bearing operators are invalid when the value is an empty string.
 */
function isRowValid(row: RuleRow): boolean {
  if (NO_VALUE_OPERATORS.has(row.operator)) return true
  if (row.field === CUSTOM_FIELD_KEY) return false
  if (row.operator === "between") {
    const pair = Array.isArray(row.value) ? row.value : [null, null]
    const [lower, upper] = pair
    // Reject null/undefined or empty bounds.
    if (lower == null || upper == null || lower === "" || upper === "") return false
    if (typeof lower === "number" && typeof upper === "number") return lower <= upper
    if (typeof lower === "string" && typeof upper === "string") return lower <= upper
    // Reject mixed or non-comparable types (e.g. malformed prefill).
    return false
  }
  return row.value !== ""
}

/**
 * Reconstructs RuleRow[] and groupOperator from a stored expression (for edit-mode prefill).
 * Handles the standard group expression format produced by buildExpression, as well as a
 * top-level bare condition (no group wrapper) — the engine accepts a single condition object
 * directly, so it must map to one row rather than being discarded.
 * Returns an empty rows array for malformed/missing conditions — callers are
 * responsible for substituting a sensible default (e.g. makeRow(firstField)).
 * Only call this after confirming !isAdvancedExpression(expression).
 */
function parseExpression(expression: Record<string, unknown>): {
  rows: RuleRow[]
  groupOperator: Connector
} {
  const groupConditions = expression.conditions as Array<Record<string, unknown>> | undefined
  const conditions =
    groupConditions ?? ("field" in expression ? [expression] : [])
  const rows: RuleRow[] = conditions.map((cond) => ({
    id: nextRowId(),
    field: String(cond.field ?? ""),
    operator: String(cond.operator ?? "is"),
    value: "value" in cond ? cond.value : null,
  }))
  const groupOperator: Connector =
    conditions.length <= 1 ? "" : expression.operator === "any" ? "OR" : "AND"
  return { rows, groupOperator }
}
