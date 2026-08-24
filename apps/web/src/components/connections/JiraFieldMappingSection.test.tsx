// SPDX-License-Identifier: Apache-2.0

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import {
  FieldMappingRow,
  type FieldMappingValues,
  JiraFieldMappingSection,
} from "@/components/connections/JiraFieldMappingSection"

// ---------------------------------------------------------------------------
// Mock the API call so tests don't hit the network
// ---------------------------------------------------------------------------

vi.mock("@/lib/connections", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/lib/connections")>()
  return {
    ...original,
    listJiraFields: vi.fn().mockResolvedValue([
      { id: "customfield_10016", name: "Story Points", custom: true, field_type: "number" },
      { id: "customfield_10020", name: "Sprint", custom: true, field_type: "array" },
      { id: "customfield_99001", name: "Acceptance Criteria", custom: true, field_type: "string" },
    ]),
  }
})

// Default prop values sourced from the Jira connector schema (same as production defaults).
const SP_DEFAULT = "customfield_10016"
const AC_HEADING_DEFAULT = "### Acceptance Criteria"

function wrapper({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      {children}
    </QueryClientProvider>
  )
}

// Helper to render JiraFieldMappingSection with the required schema-sourced defaults.
function renderSection(
  props: Partial<{
    connectionId: string
    fieldMappingValues: FieldMappingValues
    onFieldMappingChange: (v: FieldMappingValues) => void
    acHeadingDefault: string
    spDefault: string
  }> = {},
) {
  const merged = {
    acHeadingDefault: AC_HEADING_DEFAULT,
    spDefault: SP_DEFAULT,
    onFieldMappingChange: () => undefined,
    ...props,
  }
  return render(<JiraFieldMappingSection {...merged} />, { wrapper })
}

afterEach(cleanup)

// ---------------------------------------------------------------------------
// FieldMappingRow
// ---------------------------------------------------------------------------

describe("FieldMappingRow", () => {
  it("shows 'Not configured' when disabled", () => {
    render(
      <FieldMappingRow
        enabled={false}
        label="Story Points"
        onEnabledChange={() => undefined}
        switchId="sp-switch"
      >
        <input id="sp-field" />
      </FieldMappingRow>,
    )

    expect(screen.getByText("Not configured")).toBeInTheDocument()
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument()
  })

  it("reveals children when enabled", () => {
    render(
      <FieldMappingRow
        enabled={true}
        label="Story Points"
        onEnabledChange={() => undefined}
        switchId="sp-switch"
      >
        <input id="sp-field" aria-label="Custom field" />
      </FieldMappingRow>,
    )

    expect(screen.queryByText("Not configured")).not.toBeInTheDocument()
    expect(screen.getByLabelText("Custom field")).toBeInTheDocument()
  })

  it("calls onEnabledChange when the switch is clicked", () => {
    const onChange = vi.fn()
    render(
      <FieldMappingRow
        enabled={false}
        label="Story Points"
        onEnabledChange={onChange}
        switchId="sp-switch"
      >
        <span />
      </FieldMappingRow>,
    )

    fireEvent.click(screen.getByRole("switch"))
    expect(onChange).toHaveBeenCalledWith(true)
  })
})

// ---------------------------------------------------------------------------
// JiraFieldMappingSection — legend and structure
// ---------------------------------------------------------------------------

describe("JiraFieldMappingSection — legend", () => {
  it("renders the legend as 'Jira Field Mapping'", () => {
    renderSection()
    expect(screen.getByRole("group", { name: "Jira Field Mapping" })).toBeInTheDocument()
  })

  it("shows helper copy about using other Jira fields directly", () => {
    renderSection()
    expect(
      screen.getByText(/All other Jira fields and labels are available directly/i),
    ).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// JiraFieldMappingSection — no Epic Link or Blocked rows
// ---------------------------------------------------------------------------

describe("JiraFieldMappingSection — removed rows", () => {
  it("does not render an Epic Link row", () => {
    renderSection()
    expect(screen.queryByText(/epic link/i)).not.toBeInTheDocument()
  })

  it("does not render a Blocked row", () => {
    renderSection()
    expect(screen.queryByText(/blocked/i)).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// JiraFieldMappingSection — Story Points
// ---------------------------------------------------------------------------

describe("JiraFieldMappingSection — Story Points", () => {
  // When field_mapping is absent the connector applies its schema defaults at runtime, so
  // the UI mirrors that: SP shows enabled with the default field (and AC enabled too),
  // never "Not configured".
  it("shows the schema-default mapping as enabled when field_mapping is absent", () => {
    renderSection()
    expect(screen.queryByText("Not configured")).not.toBeInTheDocument()
  })

  it("reveals the dropdown (with 'Save first' guidance) when SP is toggled ON without a connectionId", () => {
    // Explicit off values (not absence) keep both mappings disabled to start.
    renderSection({
      fieldMappingValues: {
        story_points: "",
        acceptance_criteria: null,
        acceptance_criteria_heading: null,
      },
    })

    // Before toggle: both SP and AC show "Not configured"
    expect(screen.getAllByText("Not configured")).toHaveLength(2)

    fireEvent.click(screen.getAllByRole("switch")[0])

    // After toggle: only AC remains "Not configured"; SP row reveals its control
    expect(screen.getAllByText("Not configured")).toHaveLength(1)
    expect(screen.getByText("Save the connection first to load fields")).toBeInTheDocument()
  })

  it("does NOT call onFieldMappingChange when SP is toggled ON (waits for field selection)", () => {
    const onChange = vi.fn()
    // Start with SP explicitly off so toggling the switch turns it ON.
    renderSection({ fieldMappingValues: { story_points: "" }, onFieldMappingChange: onChange })

    fireEvent.click(screen.getAllByRole("switch")[0])

    expect(onChange).not.toHaveBeenCalled()
  })

  // [R1] Turning SP OFF must emit an empty story_points (mirrors AC's null "off" state):
  // this clears any stored override via the PATCH deep-merge AND round-trips back as an
  // empty value so the switch stays reliably off (see the round-trip test below).
  it("emits an empty story_points (not the default, not omitted) when SP is turned OFF", () => {
    const onChange = vi.fn()
    renderSection({
      // A stored value keeps SP enabled at first.
      fieldMappingValues: { story_points: "customfield_99999" },
      onFieldMappingChange: onChange,
    })

    // SP starts enabled (stored value is non-empty)
    fireEvent.click(screen.getAllByRole("switch")[0])

    expect(onChange).toHaveBeenCalledOnce()
    const emitted = onChange.mock.calls[0][0] as FieldMappingValues
    // Emitted key is present (not omitted) and empty (not the schema default)
    expect(emitted).toHaveProperty("story_points")
    expect(emitted.story_points).toBe("")
  })

  // [R1] The value emitted when SP is turned OFF must round-trip back through props as a
  // stable "off": re-feeding it must NOT flip the switch on again.
  it("keeps the SP switch OFF after the emitted off-value round-trips back as props", () => {
    const onChange = vi.fn()
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    const { rerender } = render(
      <QueryClientProvider client={qc}>
        <JiraFieldMappingSection
          acHeadingDefault={AC_HEADING_DEFAULT}
          fieldMappingValues={{ story_points: "customfield_99999" }}
          onFieldMappingChange={onChange}
          spDefault={SP_DEFAULT}
        />
      </QueryClientProvider>,
    )

    // SP starts on (non-default value); toggling off emits the off-value.
    expect(screen.getAllByRole("switch")[0]).toHaveAttribute("aria-checked", "true")
    fireEvent.click(screen.getAllByRole("switch")[0])

    const emitted = onChange.mock.calls[0][0] as FieldMappingValues

    // Feed the emitted story_points straight back as props, as the controlled parent would.
    rerender(
      <QueryClientProvider client={qc}>
        <JiraFieldMappingSection
          acHeadingDefault={AC_HEADING_DEFAULT}
          fieldMappingValues={{ story_points: emitted.story_points }}
          onFieldMappingChange={onChange}
          spDefault={SP_DEFAULT}
        />
      </QueryClientProvider>,
    )

    // The emitted off-value ("") must round-trip to a reliably OFF switch (not the default).
    expect(screen.getAllByRole("switch")[0]).toHaveAttribute("aria-checked", "false")
  })

  it("reveals the discovered custom-field dropdown when SP is enabled with a stored value", async () => {
    renderSection({
      connectionId: "conn-1",
      fieldMappingValues: { story_points: "customfield_10016" },
    })

    await waitFor(() => {
      expect(screen.getByRole("combobox", { name: "Story points field" })).toBeInTheDocument()
    })
  })

  it("shows 'Choose a field...' placeholder when SP is enabled but no field selected yet", async () => {
    renderSection({ connectionId: "conn-1", fieldMappingValues: { story_points: "" } })

    fireEvent.click(screen.getAllByRole("switch")[0])

    await waitFor(() => {
      const select = screen.getByRole("combobox", { name: "Story points field" }) as HTMLSelectElement
      expect(Array.from(select.options).some((o) => o.text === "Choose a field...")).toBe(true)
    })
  })

  it("reflects a prop-loaded story_points value without unmounting (edit transition regression)", () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    const { rerender } = render(
      <QueryClientProvider client={qc}>
        <JiraFieldMappingSection
          acHeadingDefault={AC_HEADING_DEFAULT}
          fieldMappingValues={{
            story_points: "",
            acceptance_criteria: null,
            acceptance_criteria_heading: null,
          }}
          onFieldMappingChange={() => undefined}
          spDefault={SP_DEFAULT}
        />
      </QueryClientProvider>,
    )

    // Initially both SP and AC are "Not configured" (explicit off values)
    expect(screen.getAllByText("Not configured")).toHaveLength(2)

    rerender(
      <QueryClientProvider client={qc}>
        <JiraFieldMappingSection
          acHeadingDefault={AC_HEADING_DEFAULT}
          fieldMappingValues={{
            story_points: "customfield_20000",
            acceptance_criteria: null,
            acceptance_criteria_heading: null,
          }}
          onFieldMappingChange={() => undefined}
          spDefault={SP_DEFAULT}
        />
      </QueryClientProvider>,
    )

    // SP row must show as enabled (value arrived via props); only AC is "Not configured"
    expect(screen.getAllByText("Not configured")).toHaveLength(1)
    expect(screen.getByRole("combobox", { name: "Story points field" })).toBeInTheDocument()
  })

  // [P3] spForcedOpen must reset when connectionId changes so a "toggled open but
  // no value picked" state doesn't bleed into the next connection.
  it("resets spForcedOpen to false when connectionId changes (prevents stale open state)", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    // Explicit off values keep both mappings disabled so spForcedOpen is the only thing
    // that can open the SP row.
    const offValues: FieldMappingValues = {
      story_points: "",
      acceptance_criteria: null,
      acceptance_criteria_heading: null,
    }

    const { rerender } = render(
      <QueryClientProvider client={qc}>
        <JiraFieldMappingSection
          acHeadingDefault={AC_HEADING_DEFAULT}
          connectionId="conn-A"
          fieldMappingValues={offValues}
          onFieldMappingChange={() => undefined}
          spDefault={SP_DEFAULT}
        />
      </QueryClientProvider>,
    )

    // Open SP without picking a field (spForcedOpen = true)
    fireEvent.click(screen.getAllByRole("switch")[0])
    expect(screen.getAllByText("Not configured")).toHaveLength(1) // only AC

    // Switch to a different connection that also has no story_points
    rerender(
      <QueryClientProvider client={qc}>
        <JiraFieldMappingSection
          acHeadingDefault={AC_HEADING_DEFAULT}
          connectionId="conn-B"
          fieldMappingValues={offValues}
          onFieldMappingChange={() => undefined}
          spDefault={SP_DEFAULT}
        />
      </QueryClientProvider>,
    )

    // spForcedOpen must have reset: SP is now "Not configured" for the new connection
    await waitFor(() => {
      expect(screen.getAllByText("Not configured")).toHaveLength(2)
    })
  })
})

// ---------------------------------------------------------------------------
// JiraFieldMappingSection — Acceptance Criteria
// ---------------------------------------------------------------------------

describe("JiraFieldMappingSection — Acceptance Criteria", () => {
  it("shows 'Text in description' controls when AC heading is set", () => {
    renderSection({
      fieldMappingValues: {
        acceptance_criteria: null,
        acceptance_criteria_heading: "### Acceptance Criteria",
      },
    })

    expect(screen.getByRole("combobox", { name: "How is it recorded?" })).toBeInTheDocument()
    expect(screen.getByPlaceholderText(AC_HEADING_DEFAULT)).toBeInTheDocument()
  })

  it("shows the custom-field dropdown when AC mode is 'Custom field'", async () => {
    renderSection({
      connectionId: "conn-1",
      fieldMappingValues: {
        acceptance_criteria: "customfield_99001",
        acceptance_criteria_heading: null,
      },
    })

    await waitFor(() => {
      const modeSelect = screen.getByRole("combobox", { name: "How is it recorded?" })
      expect((modeSelect as HTMLSelectElement).value).toBe("custom_field")
    })

    expect(screen.getByRole("combobox", { name: "Acceptance criteria field" })).toBeInTheDocument()
  })

  it("switching from 'Text in description' to 'Custom field' sets acceptance_criteria_heading to null", () => {
    const onChange = vi.fn()
    renderSection({
      fieldMappingValues: {
        acceptance_criteria: null,
        acceptance_criteria_heading: "### Acceptance Criteria",
      },
      onFieldMappingChange: onChange,
    })

    fireEvent.change(screen.getByRole("combobox", { name: "How is it recorded?" }), {
      target: { value: "custom_field" },
    })

    expect(onChange).toHaveBeenCalledOnce()
    const call = onChange.mock.calls[0][0] as FieldMappingValues
    expect(call.acceptance_criteria_heading).toBeNull()
    // No pre-selection when switching to custom_field mode
    expect(call.acceptance_criteria).toBe("")
  })

  it("the Acceptance Criteria heading textbox shows an InfoTooltip", () => {
    renderSection({
      fieldMappingValues: {
        acceptance_criteria: null,
        acceptance_criteria_heading: "### AC",
      },
    })

    expect(screen.getByRole("button", { name: /About heading text/i })).toBeInTheDocument()
  })

  // [P1/P2] Enabling AC must emit the schema-sourced heading default (non-null, non-hardcoded).
  // A non-standard acHeadingDefault prop verifies the value comes from the prop, not hardcoded.
  it("enabling AC emits the schema-default heading (sourced from acHeadingDefault prop)", () => {
    const onChange = vi.fn()
    const customDefault = "## My AC Heading"
    renderSection({
      // AC explicitly off so toggling the switch turns it ON.
      fieldMappingValues: { acceptance_criteria: null, acceptance_criteria_heading: null },
      onFieldMappingChange: onChange,
      acHeadingDefault: customDefault,
    })

    const acSwitch = screen.getAllByRole("switch")[1]
    fireEvent.click(acSwitch)

    expect(onChange).toHaveBeenCalledOnce()
    const emitted = onChange.mock.calls[0][0] as FieldMappingValues
    // Must be the prop value, not the hardcoded "### Acceptance Criteria"
    expect(emitted.acceptance_criteria_heading).toBe(customDefault)
    expect(emitted.acceptance_criteria_heading).not.toBeNull()
  })

  // [P2] Changing Story Points must NOT write null acceptance_criteria_heading. When the AC
  // keys are absent the connector defaults AC to description mode with its schema heading, so
  // an SP-triggered emit must carry that default heading (never null, which would disable the
  // connector's default extraction via the PATCH deep-merge).
  it("changing Story Points emits the default AC heading (not null) when AC keys are absent", () => {
    const onChange = vi.fn()
    renderSection({
      // SP has a value; AC keys absent → AC is default-on (description mode).
      fieldMappingValues: { story_points: SP_DEFAULT },
      onFieldMappingChange: onChange,
    })

    // Turn SP off — this triggers an emit
    fireEvent.click(screen.getAllByRole("switch")[0])

    expect(onChange).toHaveBeenCalledOnce()
    const emitted = onChange.mock.calls[0][0] as FieldMappingValues
    expect(emitted.acceptance_criteria_heading).toBe(AC_HEADING_DEFAULT)
  })

  // [P2] When AC is in description mode, any SP-triggered emit must keep the heading non-null.
  it("changing Story Points preserves a non-null AC heading when AC is in description mode", () => {
    const onChange = vi.fn()
    renderSection({
      fieldMappingValues: {
        story_points: SP_DEFAULT,
        acceptance_criteria: null,
        acceptance_criteria_heading: "### Acceptance Criteria",
      },
      onFieldMappingChange: onChange,
    })

    // Turn SP off → emit
    fireEvent.click(screen.getAllByRole("switch")[0])

    expect(onChange).toHaveBeenCalledOnce()
    const emitted = onChange.mock.calls[0][0] as FieldMappingValues
    expect(emitted.acceptance_criteria_heading).not.toBeNull()
    expect(emitted.acceptance_criteria_heading).toBe("### Acceptance Criteria")
  })
})

// ---------------------------------------------------------------------------
// JiraFieldMappingSection — schema defaults for absent field_mapping
// ---------------------------------------------------------------------------

describe("JiraFieldMappingSection — schema defaults", () => {
  it("shows SP enabled with the default field when field_mapping is absent", async () => {
    renderSection({ connectionId: "conn-1" })

    await waitFor(() => {
      const select = screen.getByRole("combobox", {
        name: "Story points field",
      }) as HTMLSelectElement
      expect(select.value).toBe(SP_DEFAULT)
    })
  })

  it("shows AC enabled in description mode with the default heading when field_mapping is absent", () => {
    renderSection()

    const modeSelect = screen.getByRole("combobox", { name: "How is it recorded?" })
    expect((modeSelect as HTMLSelectElement).value).toBe("description")
    expect(screen.getByLabelText("Heading text")).toHaveValue(AC_HEADING_DEFAULT)
  })

  it("preserves an explicit AC off (null/null) rather than reapplying the default heading", () => {
    renderSection({
      fieldMappingValues: { acceptance_criteria: null, acceptance_criteria_heading: null },
    })

    // AC row is disabled: the AC switch (second) is unchecked.
    expect(screen.getAllByRole("switch")[1]).toHaveAttribute("aria-checked", "false")
  })
})

// ---------------------------------------------------------------------------
// CustomFieldSelect — stale value handling
// ---------------------------------------------------------------------------

describe("JiraFieldMappingSection — stale field value", () => {
  it("shows a '(not in discovered fields)' option when the stored id is absent from discovered list", async () => {
    renderSection({
      connectionId: "conn-1",
      fieldMappingValues: { story_points: "customfield_99999" },
    })

    await waitFor(() => {
      const select = screen.getByRole("combobox", { name: "Story points field" }) as HTMLSelectElement
      expect(
        Array.from(select.options).some((o) => o.text.includes("not in discovered fields")),
      ).toBe(true)
    })
  })
})
