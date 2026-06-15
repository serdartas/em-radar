import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import {
  fieldLabel,
  isSecret,
  type JsonSchema,
  type JsonSchemaProperty,
  schemaType,
} from "@/lib/jsonSchema"

interface SchemaFormProps {
  schema: JsonSchema
  values: Record<string, unknown>
  idPrefix: string
  onChange: (key: string, value: unknown) => void
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

export function SchemaForm({ idPrefix, onChange, schema, values }: SchemaFormProps) {
  const properties = Object.entries(schema.properties ?? {})
  const required = new Set(schema.required ?? [])

  if (properties.length === 0) {
    return (
      <p className="text-sm text-slate-500">This connector needs no configuration.</p>
    )
  }

  return (
    <div className="space-y-4">
      {properties.map(([key, property]) => (
        <SchemaField
          fieldId={`${idPrefix}-${key}`}
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
}

function SchemaField({ fieldId, name, onChange, property, required, value }: SchemaFieldProps) {
  const label = fieldLabel(name, property)
  const type = schemaType(property)

  if (type === "boolean") {
    return (
      <div className="flex items-center justify-between gap-4">
        <FieldLabel htmlFor={fieldId} label={label} property={property} required={required} />
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
      <FieldLabel htmlFor={fieldId} label={label} property={property} required={required} />
      {renderControl({ fieldId, name, onChange, property, type, value })}
      {property.description && <p className="text-xs text-slate-500">{property.description}</p>}
    </div>
  )
}

interface FieldLabelProps {
  htmlFor: string
  label: string
  property: JsonSchemaProperty
  required: boolean
}

function FieldLabel({ htmlFor, label, property, required }: FieldLabelProps) {
  return (
    <Label htmlFor={htmlFor}>
      {label}
      {required && <span className="ml-0.5 text-red-600"> *</span>}
      {isSecret(property) && (
        <span className="ml-2 text-xs font-normal text-slate-500">(write-only)</span>
      )}
    </Label>
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
