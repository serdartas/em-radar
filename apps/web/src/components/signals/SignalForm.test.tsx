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
]

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

    // Pick a concrete Jira field
    fireEvent.change(screen.getByLabelText("Jira field"), {
      target: { value: "customfield_10001" },
    })

    expect(screen.getByRole("button", { name: "Save signal" })).not.toBeDisabled()
  })
})

// ---------------------------------------------------------------------------
// Array field type uses contains/does_not_contain
// ---------------------------------------------------------------------------

describe("SignalForm — array field type operators", () => {
  it("array field type shows contains / does not contain operators", () => {
    renderForm({ jiraCustomFields: JIRA_CUSTOM_FIELDS })

    fireEvent.change(screen.getByLabelText("Field"), { target: { value: "__custom__" } })
    fireEvent.change(screen.getByLabelText("Jira field"), {
      target: { value: "customfield_10004" }, // Labels List — array
    })

    const operatorSelect = screen.getByLabelText("Operator") as HTMLSelectElement
    const optionLabels = Array.from(operatorSelect.options).map((o) => o.text)
    expect(optionLabels).toContain("contains")
    expect(optionLabels).toContain("does not contain")
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
