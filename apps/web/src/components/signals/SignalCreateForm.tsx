// SPDX-License-Identifier: Apache-2.0

import { useState } from "react"

import { RuleValueControl } from "@/components/signals/RuleValueControl"
import { NO_VALUE_OPERATORS, defaultValueForRule } from "@/components/signals/ruleValue"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select } from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import type { SignalField } from "@/lib/connectors"
import { SEVERITIES, type Severity } from "@/lib/severity"
import type { SignalDefinitionCreate } from "@/lib/signalDefinitions"

const MAX_RULES = 5
const SIGNAL_TYPES = [
  { value: "issue", label: "Work tracking / tickets (Jira)" },
  { value: "merge_request", label: "Merge requests (GitLab)" },
]
const CATEGORIES = ["flow", "hygiene", "quality", "sprint"]

type Connector = "" | "AND" | "OR"

interface RuleRow {
  field: string
  operator: string
  value: unknown
}

interface SignalCreateFormProps {
  fieldsByEntityType: Record<string, SignalField[]>
  onCancel: () => void
  onSave: (definition: SignalDefinitionCreate) => void
  pending: boolean
  errorMessage: string | null
}

export function SignalCreateForm({
  fieldsByEntityType,
  onCancel,
  onSave,
  pending,
  errorMessage,
}: SignalCreateFormProps) {
  const [name, setName] = useState("")
  const [entityType, setEntityType] = useState(
    () => SIGNAL_TYPES.find((t) => (fieldsByEntityType[t.value] ?? []).length > 0)?.value ?? SIGNAL_TYPES[0].value,
  )
  const [groupOperator, setGroupOperator] = useState<Connector>("")
  const [severity, setSeverity] = useState<Severity>("warning")
  const [category, setCategory] = useState(CATEGORIES[0])
  const [message, setMessage] = useState("")

  const fields = fieldsByEntityType[entityType] ?? []
  const firstField = fields[0]

  const [rows, setRows] = useState<RuleRow[]>([makeRow(firstField)])

  function handleEntityTypeChange(newType: string) {
    setEntityType(newType)
    setGroupOperator("")
    const newFields = fieldsByEntityType[newType] ?? []
    setRows([makeRow(newFields[0])])
  }

  function updateRow(index: number, patch: Partial<RuleRow>) {
    setRows((prev) => prev.map((row, current) => (current === index ? { ...row, ...patch } : row)))
  }

  function changeField(index: number, key: string) {
    const field = fieldByKey(fields, key)
    const operator = field?.operators[0] ?? "is"
    updateRow(index, { field: key, operator, value: defaultValueForRule(field, operator) })
  }

  function changeOperator(index: number, operator: string) {
    const field = fieldByKey(fields, rows[index].field)
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

  const canSave = name.trim().length > 0 && !pending

  function save() {
    if (!canSave) {
      return
    }
    onSave({
      name: name.trim(),
      entity_type: entityType,
      expression: buildExpression(rows, groupOperator),
      report_settings: {
        severity,
        category,
        message_template: message.trim() || null,
      },
      enabled: true,
      origin: "user_created",
      template_key: null,
    })
  }

  return (
    <Card>
      <CardContent className="space-y-5 p-5">
        <h2 className="text-lg font-semibold">Create signal</h2>

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
              id="signal-type"
              onChange={(event) => handleEntityTypeChange(event.target.value)}
              value={entityType}
            >
              {SIGNAL_TYPES.filter((type) => (fieldsByEntityType[type.value] ?? []).length > 0).map(
                (type) => (
                  <option key={type.value} value={type.value}>
                    {type.label}
                  </option>
                ),
              )}
            </Select>
          </div>
        </div>

        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Rules</h3>
            <div className="h-px flex-1 bg-border" />
          </div>

          <ul className="space-y-2">
            {rows.map((row, index) => {
              const field = fieldByKey(fields, row.field)
              const isLast = index === rows.length - 1
              return (
                <li
                  className="flex flex-wrap items-end gap-2 rounded-md border border-border p-3"
                  key={index}
                >
                  <div className="min-w-40 flex-1 space-y-1.5">
                    <Label htmlFor={`rule-field-${index}`}>Field</Label>
                    <Select
                      id={`rule-field-${index}`}
                      onChange={(event) => changeField(index, event.target.value)}
                      value={row.field}
                    >
                      {fields.map((option) => (
                        <option key={option.key} value={option.key}>
                          {option.label}
                        </option>
                      ))}
                    </Select>
                  </div>
                  <div className="min-w-36 flex-1 space-y-1.5">
                    <Label htmlFor={`rule-operator-${index}`}>Operator</Label>
                    <Select
                      id={`rule-operator-${index}`}
                      onChange={(event) => changeOperator(index, event.target.value)}
                      value={row.operator}
                    >
                      {(field?.operators ?? []).map((operator) => (
                        <option key={operator} value={operator}>
                          {operator}
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
                  <div className="w-28 space-y-1.5">
                    <Label htmlFor={`rule-connector-${index}`}>Join</Label>
                    {isLast ? (
                      rows.length < MAX_RULES ? (
                        <Select
                          aria-label="Add rule"
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
            {pending ? "Saving..." : "Save signal"}
          </Button>
          <Button onClick={onCancel} variant="outline">
            Cancel
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

function makeRow(field: SignalField | undefined): RuleRow {
  const operator = field?.operators[0] ?? "is"
  return { field: field?.key ?? "", operator, value: defaultValueForRule(field, operator) }
}

function fieldByKey(fields: SignalField[], key: string): SignalField | undefined {
  return fields.find((field) => field.key === key)
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
