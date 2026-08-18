// SPDX-License-Identifier: Apache-2.0

import type { ReactNode } from "react"

import { Input } from "@/components/ui/input"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { Label } from "@/components/ui/label"
import { Select } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import {
  fieldLabel,
  isSecret,
  type JsonSchema,
  type JsonSchemaProperty,
  resolveProperty,
  schemaType,
} from "@/lib/jsonSchema"

interface SchemaFormProps {
  schema: JsonSchema
  values: Record<string, unknown>
  idPrefix: string
  onChange: (key: string, value: unknown) => void
  fieldHelp?: Record<string, ReactNode>
}

function toInputString(value: unknown): string {
  if (value === undefined || value === null) {
    return ""
  }
  if (Array.isArray(value)) {
    return value.join(", ")
  }
  return String(value)
}

export function SchemaForm({ fieldHelp, idPrefix, onChange, schema, values }: SchemaFormProps) {
  const properties = Object.entries(schema.properties ?? {})
  const required = new Set(schema.required ?? [])
  const defs = schema.$defs ?? {}

  if (properties.length === 0) {
    return (
      <p className="text-sm text-slate-500">This connector needs no configuration.</p>
    )
  }

  return (
    <div className="space-y-4">
      {properties.map(([key, property]) => (
        <SchemaField
          defs={defs}
          fieldId={`${idPrefix}-${key}`}
          help={fieldHelp?.[key]}
          key={key}
          name={key}
          onChange={onChange}
          property={property}
          required={required.has(key)}
          value={values[key]}
        />
      ))}
    </div>
  )
}

interface SchemaFieldProps {
  fieldId: string
  name: string
  property: JsonSchemaProperty
  required: boolean
  value: unknown
  onChange: (key: string, value: unknown) => void
  help?: ReactNode
  defs: Record<string, JsonSchemaProperty>
}

function SchemaField({ defs, fieldId, help, name, onChange, property, required, value }: SchemaFieldProps) {
  const resolved = resolveProperty(property, defs)
  const label = fieldLabel(name, resolved)
  const type = schemaType(resolved)

  if (type === "object" && resolved.properties) {
    return (
      <ObjectField
        defs={defs}
        fieldId={fieldId}
        help={help}
        label={label}
        name={name}
        onChange={onChange}
        properties={resolved.properties}
        required={resolved.required ?? []}
        value={value}
      />
    )
  }

  if (type === "boolean") {
    return (
      <div className="flex items-center justify-between gap-4">
        <FieldLabel help={help} htmlFor={fieldId} label={label} property={resolved} required={required} />
        <Switch
          checked={value === true}
          id={fieldId}
          onCheckedChange={(checked) => onChange(name, checked)}
        />
      </div>
    )
  }

  return (
    <div className="space-y-1.5">
      <FieldLabel help={help} htmlFor={fieldId} label={label} property={resolved} required={required} />
      {renderControl({ fieldId, name, onChange, property: resolved, type, value })}
      {resolved.description && <p className="text-xs text-slate-500">{resolved.description}</p>}
    </div>
  )
}

interface ObjectFieldProps {
  defs: Record<string, JsonSchemaProperty>
  fieldId: string
  help?: ReactNode
  label: string
  name: string
  onChange: (key: string, value: unknown) => void
  properties: Record<string, JsonSchemaProperty>
  required: string[]
  value: unknown
}

function ObjectField({
  defs,
  fieldId,
  help,
  label,
  name,
  onChange,
  properties,
  required,
  value,
}: ObjectFieldProps) {
  const nestedValues: Record<string, unknown> =
    typeof value === "object" && value !== null && !Array.isArray(value)
      ? (value as Record<string, unknown>)
      : {}

  const requiredSet = new Set(required)

  function handleSubChange(subKey: string, subValue: unknown) {
    onChange(name, { ...nestedValues, [subKey]: subValue })
  }

  return (
    <fieldset className="rounded-md border px-4 pb-4">
      <legend className="px-1 text-sm font-medium">{label}</legend>
      {help && <div className="mb-3 mt-2 text-sm text-slate-600">{help}</div>}
      <div className="space-y-4 pt-2">
        {Object.entries(properties).map(([subKey, subProperty]) => (
          <SchemaField
            defs={defs}
            fieldId={`${fieldId}-${subKey}`}
            key={subKey}
            name={subKey}
            onChange={handleSubChange}
            property={subProperty}
            required={requiredSet.has(subKey)}
            value={subKey in nestedValues ? nestedValues[subKey] : subProperty.default}
          />
        ))}
      </div>
    </fieldset>
  )
}

interface FieldLabelProps {
  htmlFor: string
  label: string
  property: JsonSchemaProperty
  required: boolean
  help?: ReactNode
}

function FieldLabel({ help, htmlFor, label, property, required }: FieldLabelProps) {
  return (
    <div className="flex items-center gap-1.5">
      <Label htmlFor={htmlFor}>{label}</Label>
      {required && (
        <span aria-hidden="true" className="text-red-600">
          *
        </span>
      )}
      {isSecret(property) && (
        <span aria-hidden="true" className="text-xs font-normal text-slate-500">
          (write-only)
        </span>
      )}
      {help && <InfoTooltip label={`About ${label}`}>{help}</InfoTooltip>}
    </div>
  )
}

interface ControlProps {
  fieldId: string
  name: string
  property: JsonSchemaProperty
  type: ReturnType<typeof schemaType>
  value: unknown
  onChange: (key: string, value: unknown) => void
}

function renderControl({ fieldId, name, onChange, property, type, value }: ControlProps) {
  if (property.enum) {
    return (
      <Select
        id={fieldId}
        onChange={(event) => onChange(name, event.target.value)}
        value={toInputString(value)}
      >
        {property.enum.map((option) => (
          <option key={String(option)} value={String(option)}>
            {String(option)}
          </option>
        ))}
      </Select>
    )
  }

  if (type === "integer" || type === "number") {
    return (
      <Input
        id={fieldId}
        onChange={(event) => {
          const raw = event.target.value
          onChange(name, raw === "" ? null : Number(raw))
        }}
        step={type === "integer" ? 1 : "any"}
        type="number"
        value={toInputString(value)}
      />
    )
  }

  if (type === "array") {
    return (
      <Input
        id={fieldId}
        onChange={(event) =>
          onChange(
            name,
            event.target.value
              .split(",")
              .map((item) => item.trim())
              .filter((item) => item.length > 0),
          )
        }
        placeholder="comma, separated, values"
        value={toInputString(value)}
      />
    )
  }

  return (
    <Input
      autoComplete={isSecret(property) ? "new-password" : undefined}
      id={fieldId}
      onChange={(event) => onChange(name, event.target.value)}
      type={isSecret(property) ? "password" : "text"}
      value={toInputString(value)}
    />
  )
}
