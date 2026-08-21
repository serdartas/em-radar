// SPDX-License-Identifier: Apache-2.0

import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { SignalCreateForm } from "@/components/signals/SignalCreateForm"
import type { SignalField } from "@/lib/connectors"
import type { JiraFieldInfo } from "@/lib/connections"

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
]

const FIELDS_BY_ENTITY: Record<string, SignalField[]> = {
  issue: ISSUE_FIELDS,
}

function renderForm(overrides: Partial<Parameters<typeof SignalCreateForm>[0]> = {}) {
  const onSave = vi.fn()
  const onCancel = vi.fn()

  render(
    <SignalCreateForm
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

describe("SignalCreateForm — field sorting", () => {
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

describe("SignalCreateForm — custom field picker", () => {
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

    // Sorted: "Notes", "Priority Score", "Team"
    expect(optionLabels[0]).toMatch(/Notes/)
    expect(optionLabels[1]).toMatch(/Priority Score/)
    expect(optionLabels[2]).toMatch(/Team/)
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

describe("SignalCreateForm — operator and value controls by field type", () => {
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

  it("option field type shows is / is not operators and a text value input", () => {
    renderForm({ jiraCustomFields: JIRA_CUSTOM_FIELDS })

    fireEvent.change(screen.getByLabelText("Field"), { target: { value: "__custom__" } })
    fireEvent.change(screen.getByLabelText("Jira field"), {
      target: { value: "customfield_10002" }, // Team — option
    })

    const operatorSelect = screen.getByLabelText("Operator") as HTMLSelectElement
    const optionLabels = Array.from(operatorSelect.options).map((o) => o.text)
    expect(optionLabels).toContain("is")
    expect(optionLabels).toContain("is not")

    // Should have a text value control
    expect(screen.getByLabelText("Value")).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Humanized operator labels
// ---------------------------------------------------------------------------

describe("SignalCreateForm — humanized operator labels", () => {
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
