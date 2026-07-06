import type { SignalField } from "@/lib/connectors"

export const NO_VALUE_OPERATORS = new Set(["is_empty", "is_not_empty"])

const NUMBER_TYPES = new Set(["number", "sprint_relative_day"])

export function isNumberType(type: string | undefined): boolean {
  return type !== undefined && NUMBER_TYPES.has(type)
}

export function defaultValueForRule(field: SignalField | undefined, operator: string): unknown {
  if (NO_VALUE_OPERATORS.has(operator)) {
    return undefined
  }
  if (operator === "between") {
    return field?.type === "date" ? ["", ""] : [0, 0]
  }
  if (field?.type === "duration") {
    return { amount: 3, unit: "days" }
  }
  if (field && isNumberType(field.type)) {
    return 0
  }
  if (field?.type === "date") {
    return ""
  }
  if (field && field.values.length > 0) {
    return String(field.values[0])
  }
  return ""
}
