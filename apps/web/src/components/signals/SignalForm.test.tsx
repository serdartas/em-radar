// SPDX-License-Identifier: Apache-2.0

import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { SignalForm } from "@/components/signals/SignalForm"
import type { SignalField } from "@/lib/connectors"
import type { JiraFieldInfo } from "@/lib/connections"
import type { SignalDefinition } from "@/lib/signalDefinitions"

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

// Intentionally provided out of alphabetical order to verify the sort.
const ISSUE_FIELDS: SignalField[] = [
  {
    key: "status_category",
    label: "Status Category",
    type: "enum",
    operators: ["is", "is_not"],
    values: ["todo", "in_progress", "done"],
    value_provider: null,
    availability: null,
    entity_type: "issue",
  },
  {
    key: "age_in_current_status",
    label: "Age in current status",
    type: "duration",
    operators: ["greater_than", "less_than"],
    values: [],
    value_provider: null,
    availability: null,
    entity_type: "issue",
  },
  {
    key: "priority",
    label: "Priority",
    type: "enum",
    operators: ["is", "is_not"],
    values: ["high", "medium", "low"],
    value_provider: null,
    availability: null,
    entity_type: "issue",
  },
  {
    key: "days_open",
    label: "Days Open",
    type: "number",
    operators: ["greater_than", "less_than", "between"],
    values: [],
    value_provider: null,
    availability: null,
    entity_type: "issue",
  },
]

const FIELDS_BY_ENTITY_WITH_DATE: Record<string, SignalField[]> = {
  issue: [
    ...ISSUE_FIELDS,
    {
      key: "due_date",
      label: "Due Date",
      type: "date",
      operators: ["is", "between"],
      values: [],
      value_provider: null,
      availability: null,
      entity_type: "issue",
    },
  ],
}

const JIRA_CUSTOM_FIELDS: JiraFieldInfo[] = [
  { id: "customfield_10001", name: "Priority Score", custom: true, field_type: "number" },
  { id: "customfield_10002", name: "Team", custom: true, field_type: "option" },
  { id: "customfield_10003", name: "Notes", custom: true, field_type: "string" },
  { id: "customfield_10004", name: "Labels List", custom: true, field_type: "array" },
]

const FIELDS_BY_ENTITY: Record<string, SignalField[]> = {
  issue: ISSUE_FIELDS,
}

function makeDefinition(overrides: Partial<SignalDefinition> = {}): SignalDefinition {
  return {
    id: "def-1",
    name: "Stale issues",
    description: null,
    entity_type: "issue",
    expression: {
      type: "group",
      operator: "all",
      conditions: [{ field: "status_category", operator: "is", value: "in_progress" }],
    },
    report_settings: { severity: "critical", category: "quality" },
    origin: "user_created",
    template_key: null,
    created_at: "2024-01-01T00:00:00Z",
    updated_at: "2024-01-01T00:00:00Z",
    ...overrides,
  }
}

function renderForm(overrides: Partial<Parameters<typeof SignalForm>[0]> = {}) {
  const onSave = vi.fn()
  const onCancel = vi.fn()

  render(
    <SignalForm
      errorMessage={null}
      fieldsByEntityType={FIELDS_BY_ENTITY}
      onCancel={onCancel}
      onSave={onSave}
      pending={false}
      {...overrides}
    />,
  )

  return { onSave, onCancel }
}

afterEach(cleanup)

// ---------------------------------------------------------------------------
// Sorting
// ---------------------------------------------------------------------------

describe("SignalForm — field sorting", () => {
  it("renders the Field dropdown options sorted by label (not schema order)", () => {
    renderForm()

    const select = screen.getByLabelText("Field") as HTMLSelectElement
    const optionLabels = Array.from(select.options).map((o) => o.text)

    // "Age in current status" < "Priority" < "Status Category" alphabetically
    expect(optionLabels.indexOf("Age in current status")).toBeLessThan(
      optionLabels.indexOf("Priority"),
    )
    expect(optionLabels.indexOf("Priority")).toBeLessThan(
      optionLabels.indexOf("Status Category"),
    )
  })

  it("does not show 'Custom field' when no jiraCustomFields are provided", () => {
    renderForm()

    const select = screen.getByLabelText("Field") as HTMLSelectElement
    const optionLabels = Array.from(select.options).map((o) => o.text)
    expect(optionLabels).not.toContain("Custom field")
  })
})

// ---------------------------------------------------------------------------
// Custom field progressive disclosure
// ---------------------------------------------------------------------------

describe("SignalForm — custom field picker", () => {
  it("shows 'Custom field' option in the Field dropdown when jiraCustomFields are provided", () => {
    renderForm({ jiraCustomFields: JIRA_CUSTOM_FIELDS })

    const select = screen.getByLabelText("Field") as HTMLSelectElement
    const optionLabels = Array.from(select.options).map((o) => o.text)
    expect(optionLabels).toContain("Custom field")
  })

  it("selecting 'Custom field' reveals a second 'Jira field' dropdown", () => {
    renderForm({ jiraCustomFields: JIRA_CUSTOM_FIELDS })

    expect(screen.queryByLabelText("Jira field")).not.toBeInTheDocument()

    fireEvent.change(screen.getByLabelText("Field"), { target: { value: "__custom__" } })

    expect(screen.getByLabelText("Jira field")).toBeInTheDocument()
  })

  it("the Jira field dropdown lists discovered custom fields sorted by name", () => {
    renderForm({ jiraCustomFields: JIRA_CUSTOM_FIELDS })

    fireEvent.change(screen.getByLabelText("Field"), { target: { value: "__custom__" } })

    const jiraSelect = screen.getByLabelText("Jira field") as HTMLSelectElement
    // Filter out the placeholder "Choose a field..." option
    const optionLabels = Array.from(jiraSelect.options)
      .filter((o) => !o.disabled)
      .map((o) => o.text)

    // Sorted alphabetically: "Labels List", "Notes", "Priority Score", "Team"
    expect(optionLabels[0]).toMatch(/Labels List/)
    expect(optionLabels[1]).toMatch(/Notes/)
    expect(optionLabels[2]).toMatch(/Priority Score/)
    expect(optionLabels[3]).toMatch(/Team/)
  })

  it("shows a placeholder 'Choose a field...' when no specific custom field is picked yet", () => {
    renderForm({ jiraCustomFields: JIRA_CUSTOM_FIELDS })

    fireEvent.change(screen.getByLabelText("Field"), { target: { value: "__custom__" } })

    const jiraSelect = screen.getByLabelText("Jira field") as HTMLSelectElement
    const placeholderOption = Array.from(jiraSelect.options).find((o) => o.disabled)
    expect(placeholderOption?.text).toBe("Choose a field...")
  })
})

// ---------------------------------------------------------------------------
// Operator / value controls driven by discovered field type
// ---------------------------------------------------------------------------

describe("SignalForm — operator and value controls by field type", () => {
  it("number field type shows numeric operator options (greater than, less than)", () => {
    renderForm({ jiraCustomFields: JIRA_CUSTOM_FIELDS })

    fireEvent.change(screen.getByLabelText("Field"), { target: { value: "__custom__" } })
    fireEvent.change(screen.getByLabelText("Jira field"), {
      target: { value: "customfield_10001" }, // Priority Score — number
    })

    const operatorSelect = screen.getByLabelText("Operator") as HTMLSelectElement
    const optionLabels = Array.from(operatorSelect.options).map((o) => o.text)
    expect(optionLabels).toContain("greater than")
    expect(optionLabels).toContain("less than")
  })

  it("number field type shows a numeric (number) value input", () => {
    renderForm({ jiraCustomFields: JIRA_CUSTOM_FIELDS })

    fireEvent.change(screen.getByLabelText("Field"), { target: { value: "__custom__" } })
    fireEvent.change(screen.getByLabelText("Jira field"), {
      target: { value: "customfield_10001" }, // Priority Score — number
    })

    const valueInput = screen.getByLabelText("Value") as HTMLInputElement
    expect(valueInput.type).toBe("number")
  })

  it("string field type shows is_empty / is_not_empty operators and no value control", () => {
    renderForm({ jiraCustomFields: JIRA_CUSTOM_FIELDS })

    fireEvent.change(screen.getByLabelText("Field"), { target: { value: "__custom__" } })
    fireEvent.change(screen.getByLabelText("Jira field"), {
      target: { value: "customfield_10003" }, // Notes — string
    })

    const operatorSelect = screen.getByLabelText("Operator") as HTMLSelectElement
    const optionLabels = Array.from(operatorSelect.options).map((o) => o.text)
    expect(optionLabels).toContain("is empty")
    expect(optionLabels).toContain("is not empty")

    // No value input: is_empty is a no-value operator
    expect(screen.queryByLabelText("Value")).not.toBeInTheDocument()
  })

  it("option field type shows is / is not operators and a free-text (input) value control", () => {
    renderForm({ jiraCustomFields: JIRA_CUSTOM_FIELDS })

    fireEvent.change(screen.getByLabelText("Field"), { target: { value: "__custom__" } })
    fireEvent.change(screen.getByLabelText("Jira field"), {
      target: { value: "customfield_10002" }, // Team — option
    })

    const operatorSelect = screen.getByLabelText("Operator") as HTMLSelectElement
    const optionLabels = Array.from(operatorSelect.options).map((o) => o.text)
    expect(optionLabels).toContain("is")
    expect(optionLabels).toContain("is not")

    // Must be a plain text <input>, not a <select>, because option values are not discoverable.
    const valueControl = screen.getByLabelText("Value") as HTMLInputElement
    expect(valueControl.tagName).toBe("INPUT")
  })

  it("selecting 'Custom field' sentinel before picking a concrete field hides Operator and Value", () => {
    renderForm({ jiraCustomFields: JIRA_CUSTOM_FIELDS })

    fireEvent.change(screen.getByLabelText("Field"), { target: { value: "__custom__" } })

    // Jira field picker is visible but no concrete field chosen yet
    expect(screen.getByLabelText("Jira field")).toBeInTheDocument()
    // Operator and Value must not appear until a concrete field is picked
    expect(screen.queryByLabelText("Operator")).not.toBeInTheDocument()
    expect(screen.queryByLabelText("Value")).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Humanized operator labels
// ---------------------------------------------------------------------------

describe("SignalForm — humanized operator labels", () => {
  it("renders operator options with human-readable labels for built-in fields", () => {
    renderForm()

    fireEvent.change(screen.getByLabelText("Field"), {
      target: { value: "status_category" },
    })

    const operatorSelect = screen.getByLabelText("Operator") as HTMLSelectElement
    const optionLabels = Array.from(operatorSelect.options).map((o) => o.text)
    // Should show "is not" not "is_not"
    expect(optionLabels).toContain("is not")
    expect(optionLabels).not.toContain("is_not")
  })

  it("submits the underlying operator value (is_not) even though the label shows 'is not'", () => {
    const { onSave } = renderForm()

    // Fill in a name to enable save
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "My signal" } })

    fireEvent.change(screen.getByLabelText("Field"), {
      target: { value: "status_category" },
    })
    fireEvent.change(screen.getByLabelText("Operator"), { target: { value: "is_not" } })
    fireEvent.click(screen.getByRole("button", { name: "Save signal" }))

    expect(onSave).toHaveBeenCalledOnce()
    const call = onSave.mock.calls[0][0] as { expression: { conditions: Array<{ operator: string }> } }
    expect(call.expression.conditions[0].operator).toBe("is_not")
  })

  it("renders humanized 'greater than' label for duration/number operator", () => {
    renderForm()

    fireEvent.change(screen.getByLabelText("Field"), {
      target: { value: "age_in_current_status" },
    })

    const operatorSelect = screen.getByLabelText("Operator") as HTMLSelectElement
    const optionLabels = Array.from(operatorSelect.options).map((o) => o.text)
    expect(optionLabels).toContain("greater than")
    expect(optionLabels).not.toContain("greater_than")
  })

  it("submits the underlying operator value (greater_than) for a custom number field", () => {
    const { onSave } = renderForm({ jiraCustomFields: JIRA_CUSTOM_FIELDS })

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "High score signal" } })
    fireEvent.change(screen.getByLabelText("Field"), { target: { value: "__custom__" } })
    fireEvent.change(screen.getByLabelText("Jira field"), {
      target: { value: "customfield_10001" }, // Priority Score — number
    })
    fireEvent.change(screen.getByLabelText("Operator"), { target: { value: "greater_than" } })
    // Numeric default is now "" (empty sentinel); enter a value to enable Save.
    fireEvent.change(screen.getByLabelText("Value"), { target: { value: "5" } })
    fireEvent.click(screen.getByRole("button", { name: "Save signal" }))

    expect(onSave).toHaveBeenCalledOnce()
    const call = onSave.mock.calls[0][0] as {
      expression: { conditions: Array<{ field: string; operator: string }> }
    }
    expect(call.expression.conditions[0].field).toBe("customfield_10001")
    expect(call.expression.conditions[0].operator).toBe("greater_than")
  })
})

// ---------------------------------------------------------------------------
// Sentinel guard: Save disabled while __custom__ is unresolved
// ---------------------------------------------------------------------------

describe("SignalForm — sentinel guard", () => {
  it("Save is disabled when 'Custom field' is selected but no concrete field is chosen", () => {
    renderForm({ jiraCustomFields: JIRA_CUSTOM_FIELDS })

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "My signal" } })
    fireEvent.change(screen.getByLabelText("Field"), { target: { value: "__custom__" } })

    const saveButton = screen.getByRole("button", { name: "Save signal" })
    expect(saveButton).toBeDisabled()
  })

  it("Save is enabled once a concrete custom field is chosen after the sentinel", () => {
    renderForm({ jiraCustomFields: JIRA_CUSTOM_FIELDS })

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "My signal" } })
    fireEvent.change(screen.getByLabelText("Field"), { target: { value: "__custom__" } })

    // Save still disabled at sentinel
    expect(screen.getByRole("button", { name: "Save signal" })).toBeDisabled()

    // Pick a concrete Jira field — use a string field (is_empty operator, no value required).
    fireEvent.change(screen.getByLabelText("Jira field"), {
      target: { value: "customfield_10003" }, // Notes — string, is_empty is a no-value operator
    })

    expect(screen.getByRole("button", { name: "Save signal" })).not.toBeDisabled()
  })
})

// ---------------------------------------------------------------------------
// Array field type uses contains/does_not_contain/is_empty/is_not_empty
// ---------------------------------------------------------------------------

describe("SignalForm — array field type operators", () => {
  it("array field type shows contains, does not contain, is empty, and is not empty operators", () => {
    renderForm({ jiraCustomFields: JIRA_CUSTOM_FIELDS })

    fireEvent.change(screen.getByLabelText("Field"), { target: { value: "__custom__" } })
    fireEvent.change(screen.getByLabelText("Jira field"), {
      target: { value: "customfield_10004" }, // Labels List — array
    })

    const operatorSelect = screen.getByLabelText("Operator") as HTMLSelectElement
    const optionLabels = Array.from(operatorSelect.options).map((o) => o.text)
    expect(optionLabels).toContain("contains")
    expect(optionLabels).toContain("does not contain")
    expect(optionLabels).toContain("is empty")
    expect(optionLabels).toContain("is not empty")
    expect(optionLabels).not.toContain("is")
    expect(optionLabels).not.toContain("is not")
  })

  it("array field type renders a value input (contains is value-bearing)", () => {
    renderForm({ jiraCustomFields: JIRA_CUSTOM_FIELDS })

    fireEvent.change(screen.getByLabelText("Field"), { target: { value: "__custom__" } })
    fireEvent.change(screen.getByLabelText("Jira field"), {
      target: { value: "customfield_10004" }, // Labels List — array
    })

    // contains is not a no-value operator so the value control must render
    expect(screen.getByLabelText("Value")).toBeInTheDocument()
  })

  it("choosing is_empty on an array field hides the value control and leaves Save enabled", () => {
    renderForm({ jiraCustomFields: JIRA_CUSTOM_FIELDS })

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "My signal" } })
    fireEvent.change(screen.getByLabelText("Field"), { target: { value: "__custom__" } })
    fireEvent.change(screen.getByLabelText("Jira field"), {
      target: { value: "customfield_10004" }, // Labels List — array
    })
    fireEvent.change(screen.getByLabelText("Operator"), { target: { value: "is_empty" } })

    expect(screen.queryByLabelText("Value")).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Save signal" })).not.toBeDisabled()
  })

  it("choosing is_not_empty on an array field hides the value control and leaves Save enabled", () => {
    renderForm({ jiraCustomFields: JIRA_CUSTOM_FIELDS })

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "My signal" } })
    fireEvent.change(screen.getByLabelText("Field"), { target: { value: "__custom__" } })
    fireEvent.change(screen.getByLabelText("Jira field"), {
      target: { value: "customfield_10004" }, // Labels List — array
    })
    fireEvent.change(screen.getByLabelText("Operator"), { target: { value: "is_not_empty" } })

    expect(screen.queryByLabelText("Value")).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Save signal" })).not.toBeDisabled()
  })
})

// ---------------------------------------------------------------------------
// Operator label correctness (humanizeOperator mapping)
// ---------------------------------------------------------------------------

describe("SignalForm — operator label correctness", () => {
  it("renders 'does not contain' label for does_not_contain operator", () => {
    renderForm({ jiraCustomFields: JIRA_CUSTOM_FIELDS })

    fireEvent.change(screen.getByLabelText("Field"), { target: { value: "__custom__" } })
    fireEvent.change(screen.getByLabelText("Jira field"), {
      target: { value: "customfield_10004" }, // Labels List — array
    })

    const operatorSelect = screen.getByLabelText("Operator") as HTMLSelectElement
    const optionTexts = Array.from(operatorSelect.options).map((o) => o.text)
    expect(optionTexts).toContain("does not contain")
    expect(optionTexts).not.toContain("does_not_contain")
  })

  it("underlying operator value is does_not_contain when label shows 'does not contain'", () => {
    const { onSave } = renderForm({ jiraCustomFields: JIRA_CUSTOM_FIELDS })

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "My signal" } })
    fireEvent.change(screen.getByLabelText("Field"), { target: { value: "__custom__" } })
    fireEvent.change(screen.getByLabelText("Jira field"), {
      target: { value: "customfield_10004" },
    })
    fireEvent.change(screen.getByLabelText("Operator"), { target: { value: "does_not_contain" } })
    // Array fields use a free-text input; a non-empty value is required to enable Save.
    fireEvent.change(screen.getByLabelText("Value"), { target: { value: "backend" } })
    fireEvent.click(screen.getByRole("button", { name: "Save signal" }))

    expect(onSave).toHaveBeenCalledOnce()
    const call = onSave.mock.calls[0][0] as {
      expression: { conditions: Array<{ operator: string }> }
    }
    expect(call.expression.conditions[0].operator).toBe("does_not_contain")
  })
})

// ---------------------------------------------------------------------------
// Edit mode: prefill
// ---------------------------------------------------------------------------

describe("SignalForm — edit mode prefill", () => {
  it("shows 'Edit signal' heading and 'Save changes' button in edit mode", () => {
    renderForm({ mode: "edit", initialValue: makeDefinition() })

    expect(screen.getByRole("heading", { name: "Edit signal" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Save changes" })).toBeInTheDocument()
  })

  it("prefills name from initialValue", () => {
    renderForm({ mode: "edit", initialValue: makeDefinition({ name: "Stale issues" }) })

    const nameInput = screen.getByLabelText("Name") as HTMLInputElement
    expect(nameInput.value).toBe("Stale issues")
  })

  it("prefills severity from initialValue", () => {
    renderForm({ mode: "edit", initialValue: makeDefinition() })

    const severitySelect = screen.getByLabelText("Severity") as HTMLSelectElement
    expect(severitySelect.value).toBe("critical")
  })

  it("prefills category from initialValue", () => {
    renderForm({ mode: "edit", initialValue: makeDefinition() })

    const categorySelect = screen.getByLabelText("Category") as HTMLSelectElement
    expect(categorySelect.value).toBe("quality")
  })

  it("prefills the field rule from the stored expression", () => {
    renderForm({ mode: "edit", initialValue: makeDefinition() })

    const fieldSelect = screen.getByLabelText("Field") as HTMLSelectElement
    expect(fieldSelect.value).toBe("status_category")
  })

  it("prefills the operator from the stored expression", () => {
    renderForm({ mode: "edit", initialValue: makeDefinition() })

    const operatorSelect = screen.getByLabelText("Operator") as HTMLSelectElement
    expect(operatorSelect.value).toBe("is")
  })

  it("calls onSave with updated values preserving origin from initialValue", () => {
    const { onSave } = renderForm({
      mode: "edit",
      initialValue: makeDefinition({ origin: "user_created" }),
    })

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Renamed signal" } })
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }))

    expect(onSave).toHaveBeenCalledOnce()
    const call = onSave.mock.calls[0][0] as { name: string; origin: string }
    expect(call.name).toBe("Renamed signal")
    expect(call.origin).toBe("user_created")
  })

  it("does not show 'Create signal' heading when in edit mode", () => {
    renderForm({ mode: "edit", initialValue: makeDefinition() })

    expect(screen.queryByRole("heading", { name: "Create signal" })).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Edit mode: custom-field row prefill (guards against M8.5-02 regression)
// ---------------------------------------------------------------------------

describe("SignalForm — edit mode custom-field row prefill", () => {
  it("prefills a custom-field rule: shows 'Custom field' in the field selector", () => {
    const customFieldDef = makeDefinition({
      expression: {
        type: "group",
        operator: "all",
        conditions: [{ field: "customfield_10001", operator: "greater_than", value: 5 }],
      },
    })
    renderForm({
      mode: "edit",
      initialValue: customFieldDef,
      jiraCustomFields: JIRA_CUSTOM_FIELDS,
    })

    // Field selector should show "Custom field" (CUSTOM_FIELD_KEY) as selected value
    const fieldSelect = screen.getByLabelText("Field") as HTMLSelectElement
    expect(fieldSelect.value).toBe("__custom__")
  })

  it("prefills a custom-field rule: Jira field picker is visible with the stored field selected", () => {
    const customFieldDef = makeDefinition({
      expression: {
        type: "group",
        operator: "all",
        conditions: [{ field: "customfield_10001", operator: "greater_than", value: 5 }],
      },
    })
    renderForm({
      mode: "edit",
      initialValue: customFieldDef,
      jiraCustomFields: JIRA_CUSTOM_FIELDS,
    })

    const jiraSelect = screen.getByLabelText("Jira field") as HTMLSelectElement
    expect(jiraSelect.value).toBe("customfield_10001")
  })

  it("prefills a custom-field rule: correct operator is selected", () => {
    const customFieldDef = makeDefinition({
      expression: {
        type: "group",
        operator: "all",
        conditions: [{ field: "customfield_10001", operator: "greater_than", value: 5 }],
      },
    })
    renderForm({
      mode: "edit",
      initialValue: customFieldDef,
      jiraCustomFields: JIRA_CUSTOM_FIELDS,
    })

    const operatorSelect = screen.getByLabelText("Operator") as HTMLSelectElement
    expect(operatorSelect.value).toBe("greater_than")
  })

  it("unresolved custom-field id (not in jiraCustomFields) still renders usable operator options", () => {
    // Guards against degraded state when jiraCustomFields are absent/loading or the field was deleted.
    const customFieldDef = makeDefinition({
      expression: {
        type: "group",
        operator: "all",
        conditions: [{ field: "customfield_99999", operator: "is", value: "x" }],
      },
    })
    renderForm({
      mode: "edit",
      initialValue: customFieldDef,
      jiraCustomFields: JIRA_CUSTOM_FIELDS, // does NOT contain customfield_99999
    })

    // Operator dropdown must have options from the fallback field (not empty)
    const operatorSelect = screen.getByLabelText("Operator") as HTMLSelectElement
    expect(operatorSelect.options.length).toBeGreaterThan(0)

    // The Jira field picker must be visible and show the raw id as a selectable option
    const jiraSelect = screen.getByLabelText("Jira field") as HTMLSelectElement
    expect(jiraSelect.value).toBe("customfield_99999")
  })

  it("edit mode with custom-field prefill: submit sends correct field and operator", () => {
    const customFieldDef = makeDefinition({
      name: "Custom signal",
      expression: {
        type: "group",
        operator: "all",
        conditions: [{ field: "customfield_10001", operator: "greater_than", value: 5 }],
      },
    })
    const { onSave } = renderForm({
      mode: "edit",
      initialValue: customFieldDef,
      jiraCustomFields: JIRA_CUSTOM_FIELDS,
    })

    fireEvent.click(screen.getByRole("button", { name: "Save changes" }))

    expect(onSave).toHaveBeenCalledOnce()
    const call = onSave.mock.calls[0][0] as {
      expression: { conditions: Array<{ field: string; operator: string; value: unknown }> }
    }
    expect(call.expression.conditions[0].field).toBe("customfield_10001")
    expect(call.expression.conditions[0].operator).toBe("greater_than")
    expect(call.expression.conditions[0].value).toBe(5)
  })
})

// ---------------------------------------------------------------------------
// P1 — Nested / advanced expression: no corruption, builder replaced by Callout
// ---------------------------------------------------------------------------

const NESTED_EXPRESSION = {
  type: "group",
  operator: "all",
  conditions: [
    {
      // A condition that is itself a group — cannot be represented in the flat builder.
      operator: "any",
      conditions: [
        { field: "status_category", operator: "is", value: "in_progress" },
        { field: "age_in_current_status", operator: "greater_than", value: 7 },
      ],
    },
  ],
}

describe("SignalForm — nested/advanced expression guard", () => {
  it("flat rule builder is NOT shown for a nested-group expression", () => {
    renderForm({
      mode: "edit",
      initialValue: makeDefinition({ expression: NESTED_EXPRESSION }),
    })

    // The rules list must not be rendered; the Callout replaces it.
    expect(screen.queryByLabelText("Field")).not.toBeInTheDocument()
    expect(screen.queryByLabelText("Operator")).not.toBeInTheDocument()
  })

  it("shows the advanced-condition Callout for a nested-group expression", () => {
    renderForm({
      mode: "edit",
      initialValue: makeDefinition({ expression: NESTED_EXPRESSION }),
    })

    expect(screen.getByText(/advanced condition/i)).toBeInTheDocument()
  })

  it("metadata fields remain editable for a nested-group expression", () => {
    renderForm({
      mode: "edit",
      initialValue: makeDefinition({ name: "Nested signal", expression: NESTED_EXPRESSION }),
    })

    expect(screen.getByLabelText("Name")).toBeInTheDocument()
    expect(screen.getByLabelText("Severity")).toBeInTheDocument()
    expect(screen.getByLabelText("Category")).toBeInTheDocument()
  })

  it("saving after a name-only edit preserves the nested expression byte-for-byte", () => {
    const { onSave } = renderForm({
      mode: "edit",
      initialValue: makeDefinition({ name: "Old name", expression: NESTED_EXPRESSION }),
    })

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "New name" } })
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }))

    expect(onSave).toHaveBeenCalledOnce()
    const call = onSave.mock.calls[0][0] as { name: string; expression: unknown }
    expect(call.name).toBe("New name")
    // Expression must be the original object, not a flattened rebuild.
    expect(call.expression).toEqual(NESTED_EXPRESSION)
  })

  it("flat signals are unaffected (no Callout, rule builder present)", () => {
    renderForm({ mode: "edit", initialValue: makeDefinition() })

    expect(screen.queryByText(/advanced condition/i)).not.toBeInTheDocument()
    expect(screen.getByLabelText("Field")).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Top-level bare condition (no group wrapper) — engine accepts it; must not be discarded
// ---------------------------------------------------------------------------

describe("SignalForm — top-level bare condition", () => {
  // A condition without a `type:"group"` wrapper and without a `conditions` array.
  const BARE_EXPRESSION = { field: "status_category", operator: "is_not", value: "done" }

  it("shows the rule builder (not the advanced Callout) for a bare condition", () => {
    renderForm({ mode: "edit", initialValue: makeDefinition({ expression: BARE_EXPRESSION }) })

    expect(screen.queryByText(/advanced condition/i)).not.toBeInTheDocument()
    expect(screen.getByLabelText("Field")).toBeInTheDocument()
  })

  it("prefills field and operator from the bare condition instead of a blank default row", () => {
    renderForm({ mode: "edit", initialValue: makeDefinition({ expression: BARE_EXPRESSION }) })

    expect((screen.getByLabelText("Field") as HTMLSelectElement).value).toBe("status_category")
    expect((screen.getByLabelText("Operator") as HTMLSelectElement).value).toBe("is_not")
  })

  it("preserves the real rule on save (does not silently discard it)", () => {
    const { onSave } = renderForm({
      mode: "edit",
      initialValue: makeDefinition({ name: "Bare signal", expression: BARE_EXPRESSION }),
    })

    fireEvent.click(screen.getByRole("button", { name: "Save changes" }))

    expect(onSave).toHaveBeenCalledOnce()
    const call = onSave.mock.calls[0][0] as {
      expression: { conditions: Array<{ field: string; operator: string; value: unknown }> }
    }
    expect(call.expression.conditions).toHaveLength(1)
    expect(call.expression.conditions[0]).toMatchObject({
      field: "status_category",
      operator: "is_not",
      value: "done",
    })
  })
})

// ---------------------------------------------------------------------------
// P2 — Sprint entity type shown correctly in Type selector
// ---------------------------------------------------------------------------

const SPRINT_FIELDS: SignalField[] = [
  {
    key: "sprint_state",
    label: "Sprint state",
    type: "enum",
    operators: ["is", "is_not"],
    values: ["active", "closed", "future"],
    value_provider: null,
    availability: null,
    entity_type: "sprint",
  },
]

describe("SignalForm — sprint entity type", () => {
  it("editing a sprint signal shows 'sprint' selected in the Type control", () => {
    renderForm({
      fieldsByEntityType: { issue: ISSUE_FIELDS, sprint: SPRINT_FIELDS },
      mode: "edit",
      initialValue: makeDefinition({
        entity_type: "sprint",
        expression: {
          type: "group",
          operator: "all",
          conditions: [{ field: "sprint_state", operator: "is", value: "active" }],
        },
      }),
    })

    const typeSelect = screen.getByLabelText("Type") as HTMLSelectElement
    expect(typeSelect.value).toBe("sprint")
  })

  it("sprint label falls back to raw value when not in ENTITY_TYPE_LABELS", () => {
    const unknownType = "custom_entity"
    renderForm({
      fieldsByEntityType: { custom_entity: ISSUE_FIELDS },
      mode: "edit",
      initialValue: makeDefinition({
        entity_type: unknownType,
        expression: {
          type: "group",
          operator: "all",
          conditions: [{ field: "status_category", operator: "is", value: "in_progress" }],
        },
      }),
    })

    const typeSelect = screen.getByLabelText("Type") as HTMLSelectElement
    expect(typeSelect.value).toBe(unknownType)
    const option = Array.from(typeSelect.options).find((o) => o.value === unknownType)
    expect(option?.text).toBe(unknownType)
  })
})

// ---------------------------------------------------------------------------
// P2 — Planning / delivery categories shown correctly
// ---------------------------------------------------------------------------

describe("SignalForm — extended categories", () => {
  it("editing a 'planning' signal shows planning selected in Category", () => {
    renderForm({
      mode: "edit",
      initialValue: makeDefinition({
        report_settings: { severity: "warning", category: "planning" },
      }),
    })

    const categorySelect = screen.getByLabelText("Category") as HTMLSelectElement
    expect(categorySelect.value).toBe("planning")
  })

  it("editing a 'delivery' signal shows delivery selected in Category", () => {
    renderForm({
      mode: "edit",
      initialValue: makeDefinition({
        report_settings: { severity: "warning", category: "delivery" },
      }),
    })

    const categorySelect = screen.getByLabelText("Category") as HTMLSelectElement
    expect(categorySelect.value).toBe("delivery")
  })

  it("an unknown category outside the known set is still rendered as a selectable option", () => {
    renderForm({
      mode: "edit",
      initialValue: makeDefinition({
        report_settings: { severity: "warning", category: "custom_cat" },
      }),
    })

    const categorySelect = screen.getByLabelText("Category") as HTMLSelectElement
    expect(categorySelect.value).toBe("custom_cat")
    const option = Array.from(categorySelect.options).find((o) => o.value === "custom_cat")
    expect(option).toBeTruthy()
  })
})

// ---------------------------------------------------------------------------
// Rule value validation (AUDIT-12)
// ---------------------------------------------------------------------------

describe("SignalForm — rule value validation", () => {
  it("Save is disabled when an option-type custom field has an empty (blank) value", () => {
    // customfield_10002 (Team, option) renders a free-text input with default ""
    renderForm({ jiraCustomFields: JIRA_CUSTOM_FIELDS })

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "My signal" } })
    fireEvent.change(screen.getByLabelText("Field"), { target: { value: "__custom__" } })
    fireEvent.change(screen.getByLabelText("Jira field"), {
      target: { value: "customfield_10002" },
    })

    expect(screen.getByRole("button", { name: "Save signal" })).toBeDisabled()
  })

  it("Save is enabled once the blank value is filled in", () => {
    renderForm({ jiraCustomFields: JIRA_CUSTOM_FIELDS })

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "My signal" } })
    fireEvent.change(screen.getByLabelText("Field"), { target: { value: "__custom__" } })
    fireEvent.change(screen.getByLabelText("Jira field"), {
      target: { value: "customfield_10002" },
    })

    // Still disabled with blank value
    expect(screen.getByRole("button", { name: "Save signal" })).toBeDisabled()

    fireEvent.change(screen.getByLabelText("Value"), { target: { value: "Backend" } })

    expect(screen.getByRole("button", { name: "Save signal" })).not.toBeDisabled()
  })

  it("Save is disabled for between when lower > upper (numeric bounds)", () => {
    // days_open supports between; default ["", ""] is invalid (empty bounds block Save).
    renderForm({ fieldsByEntityType: { issue: ISSUE_FIELDS } })

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "My signal" } })
    fireEvent.change(screen.getByLabelText("Field"), { target: { value: "days_open" } })
    fireEvent.change(screen.getByLabelText("Operator"), { target: { value: "between" } })

    // Enter valid bounds [5, 10] — Save must be enabled.
    fireEvent.change(screen.getByLabelText("Lower bound"), { target: { value: "5" } })
    fireEvent.change(screen.getByLabelText("Upper bound"), { target: { value: "10" } })
    expect(screen.getByRole("button", { name: "Save signal" })).not.toBeDisabled()

    // Invert to lower > upper — Save must be disabled.
    fireEvent.change(screen.getByLabelText("Lower bound"), { target: { value: "10" } })
    fireEvent.change(screen.getByLabelText("Upper bound"), { target: { value: "3" } })
    expect(screen.getByRole("button", { name: "Save signal" })).toBeDisabled()
  })

  it("Save is enabled once between bounds satisfy lower <= upper", () => {
    renderForm({ fieldsByEntityType: { issue: ISSUE_FIELDS } })

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "My signal" } })
    fireEvent.change(screen.getByLabelText("Field"), { target: { value: "days_open" } })
    fireEvent.change(screen.getByLabelText("Operator"), { target: { value: "between" } })

    fireEvent.change(screen.getByLabelText("Lower bound"), { target: { value: "5" } })
    fireEvent.change(screen.getByLabelText("Upper bound"), { target: { value: "3" } })

    // Disabled with lower > upper
    expect(screen.getByRole("button", { name: "Save signal" })).toBeDisabled()

    // Fix: set upper bound >= lower bound
    fireEvent.change(screen.getByLabelText("Upper bound"), { target: { value: "10" } })

    expect(screen.getByRole("button", { name: "Save signal" })).not.toBeDisabled()
  })

  it("Save is disabled when a date between rule has empty bounds", () => {
    // date type between defaults to ["", ""], both empty => invalid
    renderForm({ fieldsByEntityType: FIELDS_BY_ENTITY_WITH_DATE })

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "My signal" } })
    fireEvent.change(screen.getByLabelText("Field"), { target: { value: "due_date" } })
    fireEvent.change(screen.getByLabelText("Operator"), { target: { value: "between" } })

    expect(screen.getByRole("button", { name: "Save signal" })).toBeDisabled()
  })

  it("no-value operators (is_empty) are always valid regardless of value", () => {
    // status_category has no is_empty operator; use age_in_current_status which uses
    // greater_than/less_than. Use a custom string field which has is_empty.
    renderForm({ jiraCustomFields: JIRA_CUSTOM_FIELDS })

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "My signal" } })
    fireEvent.change(screen.getByLabelText("Field"), { target: { value: "__custom__" } })
    fireEvent.change(screen.getByLabelText("Jira field"), {
      target: { value: "customfield_10003" }, // Notes — string, default is_empty
    })

    // is_empty is a no-value operator — Save must be enabled with no value input
    expect(screen.queryByLabelText("Value")).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Save signal" })).not.toBeDisabled()
  })

  it("advanced-expression edit mode: Save is enabled even without touching rules", () => {
    // The rule builder is replaced by a Callout; isAdvanced bypasses row validation.
    const { onSave } = renderForm({
      mode: "edit",
      initialValue: makeDefinition({ name: "Nested signal", expression: NESTED_EXPRESSION }),
    })

    fireEvent.click(screen.getByRole("button", { name: "Save changes" }))

    expect(onSave).toHaveBeenCalledOnce()
  })

  // ---------------------------------------------------------------------------
  // Numeric empty sentinel (P2 — guards Number("") === 0 silent coercion)
  // ---------------------------------------------------------------------------

  it("a fresh numeric rule keeps Save disabled until a value is entered", () => {
    // days_open default operator is greater_than; defaultValueForRule returns "" not 0.
    renderForm({ fieldsByEntityType: { issue: ISSUE_FIELDS } })

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "My signal" } })
    fireEvent.change(screen.getByLabelText("Field"), { target: { value: "days_open" } })

    expect(screen.getByRole("button", { name: "Save signal" })).toBeDisabled()
  })

  it("entering a number enables Save and emits the value as a number (not a string)", () => {
    const { onSave } = renderForm({ fieldsByEntityType: { issue: ISSUE_FIELDS } })

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "My signal" } })
    fireEvent.change(screen.getByLabelText("Field"), { target: { value: "days_open" } })
    // Still disabled with empty sentinel
    expect(screen.getByRole("button", { name: "Save signal" })).toBeDisabled()

    fireEvent.change(screen.getByLabelText("Value"), { target: { value: "7" } })
    expect(screen.getByRole("button", { name: "Save signal" })).not.toBeDisabled()

    fireEvent.click(screen.getByRole("button", { name: "Save signal" }))
    expect(onSave).toHaveBeenCalledOnce()
    const call = onSave.mock.calls[0][0] as {
      expression: { conditions: Array<{ value: unknown }> }
    }
    // Must be the number 7, not the string "7".
    expect(call.expression.conditions[0].value).toBe(7)
  })

  it("clearing a numeric value after entering it disables Save", () => {
    renderForm({ fieldsByEntityType: { issue: ISSUE_FIELDS } })

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "My signal" } })
    fireEvent.change(screen.getByLabelText("Field"), { target: { value: "days_open" } })
    fireEvent.change(screen.getByLabelText("Value"), { target: { value: "7" } })
    expect(screen.getByRole("button", { name: "Save signal" })).not.toBeDisabled()

    // Clear the value: empty sentinel is emitted, not 0.
    fireEvent.change(screen.getByLabelText("Value"), { target: { value: "" } })
    expect(screen.getByRole("button", { name: "Save signal" })).toBeDisabled()
  })

  it("clearing one between numeric bound after entering valid bounds disables Save", () => {
    renderForm({ fieldsByEntityType: { issue: ISSUE_FIELDS } })

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "My signal" } })
    fireEvent.change(screen.getByLabelText("Field"), { target: { value: "days_open" } })
    fireEvent.change(screen.getByLabelText("Operator"), { target: { value: "between" } })

    // Enter valid bounds — Save enabled.
    fireEvent.change(screen.getByLabelText("Lower bound"), { target: { value: "5" } })
    fireEvent.change(screen.getByLabelText("Upper bound"), { target: { value: "10" } })
    expect(screen.getByRole("button", { name: "Save signal" })).not.toBeDisabled()

    // Clear the upper bound: empty sentinel, not 0.
    fireEvent.change(screen.getByLabelText("Upper bound"), { target: { value: "" } })
    expect(screen.getByRole("button", { name: "Save signal" })).toBeDisabled()
  })
})
