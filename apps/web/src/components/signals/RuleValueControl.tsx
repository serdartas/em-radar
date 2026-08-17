// SPDX-License-Identifier: Apache-2.0

import { NO_VALUE_OPERATORS, isNumberType } from "@/components/signals/ruleValue"
import { Input } from "@/components/ui/input"
import { Select } from "@/components/ui/select"
import type { SignalField } from "@/lib/connectors"

interface RuleValueControlProps {
  field: SignalField | undefined
  operator: string
  value: unknown
  onChange: (value: unknown) => void
  id: string
}

export function RuleValueControl({ field, operator, value, onChange, id }: RuleValueControlProps) {
  if (NO_VALUE_OPERATORS.has(operator)) {
    return null
  }

  if (operator === "between") {
    const isDate = field?.type === "date"
    const pair = Array.isArray(value) ? value : isDate ? ["", ""] : [0, 0]
    const inputType = isDate ? "date" : "number"
    const cast = (raw: string): unknown => (isDate ? raw : Number(raw))
    return (
      <div className="flex gap-2">
        <Input
          aria-label="Lower bound"
          id={`${id}-min`}
          onChange={(event) => onChange([cast(event.target.value), pair[1]])}
          type={inputType}
          value={String(pair[0] ?? "")}
        />
        <Input
          aria-label="Upper bound"
          id={`${id}-max`}
          onChange={(event) => onChange([pair[0], cast(event.target.value)])}
          type={inputType}
          value={String(pair[1] ?? "")}
        />
      </div>
    )
  }

  if (field?.type === "duration") {
    const amount = isRecord(value) && typeof value.amount === "number" ? value.amount : 0
    return (
      <Input
        aria-label="Value in days"
        id={id}
        min={0}
        onChange={(event) => onChange({ amount: Number(event.target.value), unit: "days" })}
        type="number"
        value={amount}
      />
    )
  }

  if (isNumberType(field?.type)) {
    return (
      <Input
        aria-label="Value"
        id={id}
        onChange={(event) => onChange(Number(event.target.value))}
        type="number"
        value={typeof value === "number" ? value : 0}
      />
    )
  }

  if (field?.type === "date") {
    return (
      <Input
        aria-label="Value"
        id={id}
        onChange={(event) => onChange(event.target.value)}
        type="date"
        value={typeof value === "string" ? value : ""}
      />
    )
  }

  if (field && field.values.length > 0) {
    if (field.type === "boolean") {
      const boolValue = typeof value === "boolean" ? value : value === "true"
      return (
        <Select
          aria-label="Value"
          id={id}
          onChange={(event) => onChange(event.target.value === "true")}
          value={String(boolValue)}
        >
          {field.values.map((item) => (
            <option key={String(item)} value={String(item)}>
              {String(item)}
            </option>
          ))}
        </Select>
      )
    }
    const stringValue = typeof value === "string" ? value : String(value ?? "")
    return (
      <Select
        aria-label="Value"
        id={id}
        onChange={(event) => onChange(event.target.value)}
        value={stringValue}
      >
        {field.values.map((item) => (
          <option key={String(item)} value={String(item)}>
            {String(item)}
          </option>
        ))}
      </Select>
    )
  }

  const stringValue = typeof value === "string" ? value : String(value ?? "")
  return (
    <Input
      aria-label="Value"
      id={id}
      onChange={(event) => onChange(event.target.value)}
      value={stringValue}
    />
  )
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null
}
