// SPDX-License-Identifier: Apache-2.0

const OPERATOR_LABELS: Record<string, string> = {
  is: "is",
  is_not: "is not",
  is_any_of: "is any of",
  is_not_any_of: "is not any of",
  is_empty: "is empty",
  is_not_empty: "is not empty",
  greater_than: "greater than",
  less_than: "less than",
  between: "between",
  contains: "contains",
  not_contains: "does not contain",
}

/** Returns a human-readable label for a rule operator key, falling back to the key itself. */
export function humanizeOperator(operator: string): string {
  return OPERATOR_LABELS[operator] ?? operator
}
