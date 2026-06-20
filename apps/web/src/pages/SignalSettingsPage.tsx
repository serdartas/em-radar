import { useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query"
import { Link } from "react-router-dom"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Select } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { getConnectors, type SignalField } from "@/lib/connectors"
import { listScopes, type ScopeDefinition } from "@/lib/scopes"
import {
  createSignalDefinition,
  deleteSignalDefinition,
  listSignalDefinitions,
  listSignalTemplates,
  previewSignalDefinition,
  restoreSignalTemplate,
  updateSignalDefinition,
  type SignalDefinition,
  type SignalDefinitionCreate,
  type SignalDefinitionPreview,
  type SignalTemplate,
} from "@/lib/signalDefinitions"

interface BuilderDraft {
  templateKey: string
  name: string
  scopeId: string
  field: string
  operator: string
  amount: number
  value: unknown
}

export function SignalSettingsPage() {
  const queryClient = useQueryClient()
  const templatesQuery = useQuery({ queryKey: ["signal-templates"], queryFn: listSignalTemplates })
  const definitionsQuery = useQuery({
    queryKey: ["signal-definitions"],
    queryFn: listSignalDefinitions,
  })
  const connectorsQuery = useQuery({ queryKey: ["connectors"], queryFn: getConnectors })
  const scopesQuery = useQuery({ queryKey: ["scopes"], queryFn: listScopes })
  const templates = templatesQuery.data ?? []
  const scopes = scopesQuery.data ?? []
  const schema = connectorsQuery.data?.find((connector) => connector.name === "jira")?.signal_schema
  const defaultTemplate = templates[0]
  const [draft, setDraft] = useState<BuilderDraft | null>(null)

  const createMutation = useMutation({
    mutationFn: createSignalDefinition,
    onSuccess: () => {
      setDraft(null)
      void queryClient.invalidateQueries({ queryKey: ["signal-definitions"] })
    },
  })
  const restoreMutation = useMutation({
    mutationFn: restoreSignalTemplate,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["signal-templates"] }),
  })

  function duplicate(template: SignalTemplate) {
    const condition = firstCondition(template.expression)
    setDraft({
      templateKey: template.key,
      name: `${template.name} copy`,
      scopeId: scopes[0]?.id ?? "",
      field: condition.field,
      operator: condition.operator,
      amount: condition.amount,
      value: condition.value,
    })
  }

  if (templatesQuery.isLoading || definitionsQuery.isLoading || connectorsQuery.isLoading) {
    return <p className="text-sm text-slate-500">Loading signals...</p>
  }

  if (!defaultTemplate || !schema) {
    return <p className="text-sm text-red-700">Signals could not be loaded.</p>
  }

  const activeDraft = draft ?? {
    templateKey: defaultTemplate.key,
    name: `${defaultTemplate.name} copy`,
    scopeId: scopes[0]?.id ?? "",
    ...firstCondition(defaultTemplate.expression),
  }

  return (
    <section aria-labelledby="page-title" className="space-y-6">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight" id="page-title">
            Signal Settings
          </h1>
          <p className="mt-2 max-w-2xl text-slate-600">
            Manage Jira templates and scoped runnable signal definitions.
          </p>
        </div>
        <Button asChild variant="outline">
          <Link to="/signals/import-export">Import / export pack</Link>
        </Button>
      </header>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-5">
          <section aria-labelledby="templates-title" className="space-y-3">
            <h2 className="text-lg font-semibold" id="templates-title">
              Templates
            </h2>
            <ul className="grid gap-3 md:grid-cols-2">
              {templates.map((template) => (
                <li key={template.key}>
                  <Card>
                    <CardContent className="space-y-3 p-4">
                      <div>
                        <h3 className="font-semibold">{template.name}</h3>
                        <p className="mt-1 text-sm text-slate-600">{template.description}</p>
                      </div>
                      <div className="flex items-center justify-between gap-3">
                        <Badge>{template.entity_type}</Badge>
                        <div className="flex gap-2">
                          <Button onClick={() => duplicate(template)} size="sm" variant="outline">
                            Duplicate
                          </Button>
                          <Button
                            onClick={() => restoreMutation.mutate(template.key)}
                            size="sm"
                            variant="outline"
                          >
                            Restore default
                          </Button>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                </li>
              ))}
            </ul>
          </section>

          <RunnableSignals definitions={definitionsQuery.data ?? []} />
        </div>

        <SignalBuilder
          draft={activeDraft}
          fields={schema.fields}
          onChange={(next) => setDraft(next)}
          onSave={(definition) => createMutation.mutate(definition)}
          pending={createMutation.isPending}
          scopes={scopes}
          templates={templates}
        />
      </div>
    </section>
  )
}

function RunnableSignals({ definitions }: { definitions: SignalDefinition[] }) {
  const queryClient = useQueryClient()
  const disableMutation = useMutation({
    mutationFn: (definition: SignalDefinition) =>
      updateSignalDefinition(definition.id, { enabled: !definition.enabled }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["signal-definitions"] }),
  })
  const deleteMutation = useMutation({
    mutationFn: deleteSignalDefinition,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["signal-definitions"] }),
  })

  return (
    <section aria-labelledby="runnable-title" className="space-y-3">
      <h2 className="text-lg font-semibold" id="runnable-title">
        Runnable Signals
      </h2>
      <ul className="space-y-3">
        {definitions.map((definition) => (
          <li key={definition.id}>
            <Card>
              <CardContent className="flex flex-wrap items-center justify-between gap-4 p-4">
                <div>
                  <h3 className="font-semibold">{definition.name}</h3>
                  <p className="mt-1 text-sm text-slate-600">
                    {definition.target_scopes.length} target scope
                    {definition.target_scopes.length === 1 ? "" : "s"} · version{" "}
                    {definition.version}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <Switch
                    aria-label={`Enable ${definition.name}`}
                    checked={definition.enabled}
                    onCheckedChange={() => disableMutation.mutate(definition)}
                  />
                  <Button onClick={() => disableMutation.mutate(definition)} size="sm" variant="outline">
                    {definition.enabled ? "Disable" : "Enable"}
                  </Button>
                  <Button
                    onClick={() => deleteMutation.mutate(definition.id)}
                    size="sm"
                    variant="outline"
                  >
                    Delete
                  </Button>
                </div>
              </CardContent>
            </Card>
          </li>
        ))}
      </ul>
    </section>
  )
}

interface SignalBuilderProps {
  draft: BuilderDraft
  fields: SignalField[]
  onChange: (draft: BuilderDraft) => void
  onSave: (definition: SignalDefinitionCreate) => void
  pending: boolean
  scopes: ScopeDefinition[]
  templates: SignalTemplate[]
}

function SignalBuilder({
  draft,
  fields,
  onChange,
  onSave,
  pending,
  scopes,
  templates,
}: SignalBuilderProps) {
  const template = templates.find((item) => item.key === draft.templateKey) ?? templates[0]
  const selectedScope = scopes.find((scope) => scope.id === draft.scopeId)
  const selectedField = fields.find((field) => field.key === draft.field) ?? fields[0]
  const operators = selectedField?.operators ?? []
  const definitionDraft = selectedScope
    ? definitionFromDraft(template, draft, selectedField, selectedScope)
    : null
  const warnings = useMemo(
    () => previewWarnings(selectedField, selectedScope),
    [selectedField, selectedScope],
  )
  const previewQuery = useQuery({
    enabled: warnings.length === 0 && definitionDraft !== null,
    queryKey: ["signal-definition-preview", definitionDraft],
    queryFn: () => previewSignalDefinition(definitionDraft as SignalDefinitionCreate),
  })
  const previewWarningsList = [...warnings, ...(previewQuery.data?.warnings ?? [])]

  function save() {
    if (!definitionDraft || previewWarningsList.length > 0) {
      return
    }
    onSave(definitionDraft)
  }

  return (
    <aside className="space-y-4">
      <Card>
        <CardContent className="space-y-4 p-4">
          <h2 className="text-lg font-semibold">Builder</h2>

          <div className="space-y-1.5">
            <Label htmlFor="builder-template">Template</Label>
            <Select
              id="builder-template"
              onChange={(event) => {
                const nextTemplate = templates.find((item) => item.key === event.target.value)
                if (!nextTemplate) {
                  return
                }
                const condition = firstCondition(nextTemplate.expression)
                onChange({
                  ...draft,
                  templateKey: nextTemplate.key,
                  name: `${nextTemplate.name} copy`,
                  field: condition.field,
                  operator: condition.operator,
                  amount: condition.amount,
                  value: condition.value,
                })
              }}
              value={draft.templateKey}
            >
              {templates.map((item) => (
                <option key={item.key} value={item.key}>
                  {item.name}
                </option>
              ))}
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="builder-name">Name</Label>
            <input
              className="w-full rounded-md border px-3 py-2 text-sm"
              id="builder-name"
              onChange={(event) => onChange({ ...draft, name: event.target.value })}
              value={draft.name}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="builder-scope">Jira target scope</Label>
            <Select
              id="builder-scope"
              onChange={(event) => onChange({ ...draft, scopeId: event.target.value })}
              value={draft.scopeId}
            >
              <option value="">Select a scope</option>
              {scopes.map((scope) => (
                <option key={scope.id} value={scope.id}>
                  {scope.name}
                </option>
              ))}
            </Select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="builder-field">Field</Label>
              <Select
                id="builder-field"
                onChange={(event) => {
                  const nextField = fields.find((field) => field.key === event.target.value)
                  onChange({
                    ...draft,
                    field: event.target.value,
                    operator: nextField?.operators[0] ?? "is",
                    value: defaultValueForField(nextField),
                    amount: nextField?.type === "duration" ? draft.amount : 0,
                  })
                }}
                value={draft.field}
              >
                {fields.map((field) => (
                  <option key={field.key} value={field.key}>
                    {field.label}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="builder-operator">Operator</Label>
              <Select
                id="builder-operator"
                onChange={(event) => onChange({ ...draft, operator: event.target.value })}
                value={draft.operator}
              >
                {operators.map((operator) => (
                  <option key={operator} value={operator}>
                    {operator}
                  </option>
                ))}
              </Select>
            </div>
          </div>

          {selectedField?.type === "duration" ? (
            <div className="space-y-1.5">
              <Label htmlFor="builder-duration">Duration days</Label>
              <input
                className="w-full rounded-md border px-3 py-2 text-sm"
                id="builder-duration"
                min={0}
                onChange={(event) => onChange({ ...draft, amount: Number(event.target.value) })}
                type="number"
                value={draft.amount}
              />
            </div>
          ) : (
            <SignalValueControl
              field={selectedField}
              onChange={(value) => onChange({ ...draft, value })}
              value={draft.value}
            />
          )}

          <div className="rounded-md border p-3 text-sm">
            <p className="font-medium">Preview</p>
            <p className="mt-1 text-slate-600">
              {previewText(previewQuery, selectedScope)}
            </p>
            {(previewQuery.data?.samples.length ?? 0) > 0 && (
              <ul aria-label="Preview samples" className="mt-2 space-y-1 text-slate-700">
                {previewQuery.data?.samples.map((sample) => (
                  <li key={sample.item_key}>
                    {sample.item_key}: {sample.reason}
                  </li>
                ))}
              </ul>
            )}
            {previewWarningsList.length > 0 && (
              <ul aria-label="Validation warnings" className="mt-2 space-y-1 text-red-700">
                {previewWarningsList.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            )}
          </div>

          <Button disabled={pending || previewWarningsList.length > 0 || !selectedScope} onClick={save}>
            {pending ? "Saving..." : "Save signal"}
          </Button>
        </CardContent>
      </Card>
    </aside>
  )
}

function definitionFromDraft(
  template: SignalTemplate,
  draft: BuilderDraft,
  field: SignalField | undefined,
  scope: ScopeDefinition,
): SignalDefinitionCreate {
  return {
    name: draft.name,
    description: template.description,
    entity_type: template.entity_type,
    target_scopes: [
      {
        connector_id: scope.connection_id,
        scope_id: scope.id,
        scope_type: scope.scope_type,
      },
    ],
    expression: expressionFromDraft(template.expression, draft, field),
    report_settings: template.report_settings,
    enabled: true,
    origin: "system_template",
    template_key: template.key,
  }
}

function previewText(
  query: UseQueryResult<SignalDefinitionPreview, Error>,
  scope: ScopeDefinition | undefined,
): string {
  if (!scope) {
    return "Select a scope to preview matches."
  }
  if (query.isLoading || query.isFetching) {
    return `Loading preview for ${scope.name}.`
  }
  if (query.isError) {
    return `Preview could not be loaded for ${scope.name}.`
  }
  return `${query.data?.match_count ?? 0} matching sample items in ${scope.name}.`
}

function firstCondition(expression: Record<string, unknown>) {
  const condition = firstLeafCondition(expression)
  const value = condition && typeof condition.value === "object" ? condition.value : null
  const amount =
    value !== null && "amount" in value && typeof value.amount === "number" ? value.amount : 3
  return {
    field: typeof condition?.field === "string" ? condition.field : "age_in_current_status",
    operator: typeof condition?.operator === "string" ? condition.operator : "greater_than",
    amount,
    value: condition?.value ?? "",
  }
}

function SignalValueControl({
  field,
  onChange,
  value,
}: {
  field: SignalField | undefined
  onChange: (value: unknown) => void
  value: unknown
}) {
  const stringValue = typeof value === "string" ? value : String(value ?? "")
  if (field && field.values.length > 0) {
    return (
      <div className="space-y-1.5">
        <Label htmlFor="builder-value">Value</Label>
        <Select
          id="builder-value"
          onChange={(event) => onChange(event.target.value)}
          value={stringValue}
        >
          {field.values.map((item) => (
            <option key={String(item)} value={String(item)}>
              {String(item)}
            </option>
          ))}
        </Select>
      </div>
    )
  }
  return (
    <div className="space-y-1.5">
      <Label htmlFor="builder-value">Value</Label>
      <input
        className="w-full rounded-md border px-3 py-2 text-sm"
        id="builder-value"
        onChange={(event) => onChange(event.target.value)}
        value={stringValue}
      />
    </div>
  )
}

function expressionFromDraft(
  expression: Record<string, unknown>,
  draft: BuilderDraft,
  field: SignalField | undefined,
) {
  const condition = {
    field: draft.field,
    operator: draft.operator,
    value: field?.type === "duration" ? { amount: draft.amount, unit: "days" } : draft.value,
  }
  const clone = jsonClone(expression)
  if (replaceFirstLeafCondition(clone, condition)) {
    return clone
  }
  return {
    ...clone,
    type: "group",
    operator: clone.operator === "any" ? "any" : "all",
    conditions: [...(Array.isArray(clone.conditions) ? clone.conditions : []), condition],
  }
}

function firstLeafCondition(expression: Record<string, unknown>): Record<string, unknown> | null {
  const conditions = Array.isArray(expression.conditions) ? expression.conditions : []
  for (const item of conditions) {
    if (typeof item !== "object" || item === null) {
      continue
    }
    const condition = item as Record<string, unknown>
    if (condition.type === "group") {
      const nested = firstLeafCondition(condition)
      if (nested) {
        return nested
      }
    } else {
      return condition
    }
  }
  return null
}

function replaceFirstLeafCondition(
  expression: Record<string, unknown>,
  replacement: Record<string, unknown>,
): boolean {
  const conditions = Array.isArray(expression.conditions) ? expression.conditions : []
  for (let index = 0; index < conditions.length; index += 1) {
    const item = conditions[index]
    if (typeof item !== "object" || item === null) {
      continue
    }
    const condition = item as Record<string, unknown>
    if (condition.type === "group") {
      if (replaceFirstLeafCondition(condition, replacement)) {
        return true
      }
    } else {
      conditions[index] = replacement
      expression.conditions = conditions
      return true
    }
  }
  return false
}

function defaultValueForField(field: SignalField | undefined): unknown {
  if (!field) {
    return ""
  }
  if (field.type === "duration") {
    return { amount: 3, unit: "days" }
  }
  return field.values[0] ?? ""
}

function jsonClone(value: Record<string, unknown>): Record<string, unknown> {
  return JSON.parse(JSON.stringify(value)) as Record<string, unknown>
}

function previewWarnings(field: SignalField | undefined, scope: ScopeDefinition | undefined) {
  if (!field || !scope || !field.availability) {
    return []
  }
  const missing = field.availability.requires_scope_capability.filter(
    (capability) => !scope.capabilities.includes(capability),
  )
  return missing.length === 0
    ? []
    : [`${field.label} requires ${missing.join(", ")} scope capability.`]
}
