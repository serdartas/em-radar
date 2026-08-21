// SPDX-License-Identifier: Apache-2.0

// Keys match the engine's _compare() operator identifiers in declarative.py.
const OPERATOR_LABELS: Record<string, string> = {
  // Equality
  is: "is",
  is_not: "is not",
  // Set membership
  is_any_of: "is any of",
  is_none_of: "is none of",
  // Emptiness
  is_empty: "is empty",
  is_not_empty: "is not empty",
  // String / list containment
  contains: "contains",
  does_not_contain: "does not contain",
  contains_any: "contains any of",
  does_not_contain_any: "does not contain any of",
  // Numeric comparisons (full identifiers)
  greater_than: "greater than",
  less_than: "less than",
  between: "between",
  // Numeric shorthand aliases
  gt: "greater than",
  lt: "less than",
  gte: "greater than or equal to",
  lte: "less than or equal to",
  eq: "equals",
  neq: "not equal to",
  // Date comparisons
  before: "before",
  after: "after",
  is_before: "is before",
  is_after: "is after",
  // Pattern
  matches_glob: "matches pattern",
}

/** Returns a human-readable label for a rule operator key, falling back to the key itself. */
export function humanizeOperator(operator: string): string {
  return OPERATOR_LABELS[operator] ?? operator
}
