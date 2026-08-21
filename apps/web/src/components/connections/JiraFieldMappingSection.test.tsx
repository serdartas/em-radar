// SPDX-License-Identifier: Apache-2.0

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import {
  FieldMappingRow,
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

function wrapper({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      {children}
    </QueryClientProvider>
  )
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
    render(
      <JiraFieldMappingSection
        fieldMappingValues={{}}
        onFieldMappingChange={() => undefined}
      />,
      { wrapper },
    )

    expect(screen.getByRole("group", { name: "Jira Field Mapping" })).toBeInTheDocument()
  })

  it("shows helper copy about using other Jira fields directly", () => {
    render(
      <JiraFieldMappingSection
        fieldMappingValues={{}}
        onFieldMappingChange={() => undefined}
      />,
      { wrapper },
    )

    expect(screen.getByText(/All other Jira fields and labels are available directly/i)).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// JiraFieldMappingSection — no Epic Link or Blocked rows
// ---------------------------------------------------------------------------

describe("JiraFieldMappingSection — removed rows", () => {
  it("does not render an Epic Link row", () => {
    render(
      <JiraFieldMappingSection
        fieldMappingValues={{}}
        onFieldMappingChange={() => undefined}
      />,
      { wrapper },
    )

    expect(screen.queryByText(/epic link/i)).not.toBeInTheDocument()
  })

  it("does not render a Blocked row", () => {
    render(
      <JiraFieldMappingSection
        fieldMappingValues={{}}
        onFieldMappingChange={() => undefined}
      />,
      { wrapper },
    )

    expect(screen.queryByText(/blocked/i)).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// JiraFieldMappingSection — Story Points (toggle state is independent)
// ---------------------------------------------------------------------------

describe("JiraFieldMappingSection — Story Points", () => {
  it("starts as 'Not configured' when story_points is absent", () => {
    render(
      <JiraFieldMappingSection
        fieldMappingValues={{}}
        onFieldMappingChange={() => undefined}
      />,
      { wrapper },
    )

    const labels = screen.getAllByText("Not configured")
    expect(labels.length).toBeGreaterThanOrEqual(1)
  })

  it("reveals the dropdown (with 'Save first' guidance) when SP is toggled ON without a connectionId", () => {
    render(
      <JiraFieldMappingSection
        // No connectionId — unsaved connection, no field discovery possible
        fieldMappingValues={{ story_points: "" }}
        onFieldMappingChange={() => undefined}
      />,
      { wrapper },
    )

    // Before toggle: both SP and AC show "Not configured"
    expect(screen.getAllByText("Not configured")).toHaveLength(2)

    const spSwitch = screen.getAllByRole("switch")[0]
    fireEvent.click(spSwitch)

    // After toggle: only AC remains "Not configured"; SP row reveals its control
    expect(screen.getAllByText("Not configured")).toHaveLength(1)
    // Guidance text is visible inside the revealed SP dropdown
    expect(screen.getByText("Save the connection first to load fields")).toBeInTheDocument()
  })

  it("does NOT call onFieldMappingChange when SP is toggled ON (waits for field selection)", () => {
    const onChange = vi.fn()
    render(
      <JiraFieldMappingSection
        fieldMappingValues={{}}
        onFieldMappingChange={onChange}
      />,
      { wrapper },
    )

    const spSwitch = screen.getAllByRole("switch")[0]
    fireEvent.click(spSwitch)

    // Enabling the toggle alone must not emit a value — user must pick a field first
    expect(onChange).not.toHaveBeenCalled()
  })

  it("calls onFieldMappingChange without story_points when SP is toggled OFF", () => {
    const onChange = vi.fn()
    render(
      <JiraFieldMappingSection
        fieldMappingValues={{ story_points: "customfield_10016" }}
        onFieldMappingChange={onChange}
      />,
      { wrapper },
    )

    const spSwitch = screen.getAllByRole("switch")[0]
    fireEvent.click(spSwitch)

    expect(onChange).toHaveBeenCalledOnce()
    const emitted = onChange.mock.calls[0][0] as Record<string, unknown>
    // story_points must be omitted so the backend default applies
    expect("story_points" in emitted).toBe(false)
  })

  it("reveals the discovered custom-field dropdown when SP is enabled with a stored value", async () => {
    render(
      <JiraFieldMappingSection
        connectionId="conn-1"
        fieldMappingValues={{ story_points: "customfield_10016" }}
        onFieldMappingChange={() => undefined}
      />,
      { wrapper },
    )

    await waitFor(() => {
      expect(screen.getByRole("combobox", { name: "Story points field" })).toBeInTheDocument()
    })
  })

  it("shows 'Choose a field...' placeholder when SP is enabled but no field selected yet", async () => {
    render(
      <JiraFieldMappingSection
        connectionId="conn-1"
        fieldMappingValues={{ story_points: "" }}
        onFieldMappingChange={() => undefined}
      />,
      { wrapper },
    )

    // Toggle SP on
    fireEvent.click(screen.getAllByRole("switch")[0])

    await waitFor(() => {
      const select = screen.getByRole("combobox", { name: "Story points field" }) as HTMLSelectElement
      // The placeholder option must be present
      expect(
        Array.from(select.options).some((o) => o.text === "Choose a field..."),
      ).toBe(true)
    })
  })

  it("reflects a prop-loaded story_points value without unmounting (edit transition regression)", () => {
    // Simulate SourceConnectionsPage keeping a single ConnectionForm mounted
    // across add→edit transitions: props change but the component is NOT remounted.
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    const { rerender } = render(
      <QueryClientProvider client={qc}>
        <JiraFieldMappingSection
          fieldMappingValues={{}}
          onFieldMappingChange={() => undefined}
        />
      </QueryClientProvider>,
    )

    // Initially "Not configured" (no SP value in props, spForcedOpen = false)
    expect(screen.getAllByText("Not configured")).toHaveLength(2)

    // Simulate the edit effect: ConnectionForm receives a different connection whose
    // config has story_points set. Values are updated in place — no remount.
    rerender(
      <QueryClientProvider client={qc}>
        <JiraFieldMappingSection
          fieldMappingValues={{ story_points: "customfield_20000" }}
          onFieldMappingChange={() => undefined}
        />
      </QueryClientProvider>,
    )

    // SP row must now show as enabled (value in props), not "Not configured"
    expect(screen.getAllByText("Not configured")).toHaveLength(1) // only AC
    expect(screen.getByRole("combobox", { name: "Story points field" })).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// JiraFieldMappingSection — Acceptance Criteria
// ---------------------------------------------------------------------------

describe("JiraFieldMappingSection — Acceptance Criteria", () => {
  it("shows 'Text in description' controls when AC heading is set", () => {
    render(
      <JiraFieldMappingSection
        fieldMappingValues={{
          acceptance_criteria: null,
          acceptance_criteria_heading: "### Acceptance Criteria",
        }}
        onFieldMappingChange={() => undefined}
      />,
      { wrapper },
    )

    expect(screen.getByRole("combobox", { name: "How is it recorded?" })).toBeInTheDocument()
    expect(screen.getByPlaceholderText("### Acceptance Criteria")).toBeInTheDocument()
  })

  it("shows the custom-field dropdown when AC mode is 'Custom field'", async () => {
    render(
      <JiraFieldMappingSection
        connectionId="conn-1"
        fieldMappingValues={{
          acceptance_criteria: "customfield_99001",
          acceptance_criteria_heading: null,
        }}
        onFieldMappingChange={() => undefined}
      />,
      { wrapper },
    )

    await waitFor(() => {
      const modeSelect = screen.getByRole("combobox", { name: "How is it recorded?" })
      expect((modeSelect as HTMLSelectElement).value).toBe("custom_field")
    })

    expect(screen.getByRole("combobox", { name: "Acceptance criteria field" })).toBeInTheDocument()
  })

  it("switching from 'Text in description' to 'Custom field' sets acceptance_criteria_heading to null", () => {
    const onChange = vi.fn()
    render(
      <JiraFieldMappingSection
        fieldMappingValues={{
          acceptance_criteria: null,
          acceptance_criteria_heading: "### Acceptance Criteria",
        }}
        onFieldMappingChange={onChange}
      />,
      { wrapper },
    )

    const modeSelect = screen.getByRole("combobox", { name: "How is it recorded?" })
    fireEvent.change(modeSelect, { target: { value: "custom_field" } })

    expect(onChange).toHaveBeenCalledOnce()
    const call = onChange.mock.calls[0][0] as {
      acceptance_criteria: string | null
      acceptance_criteria_heading: string | null
    }
    expect(call.acceptance_criteria_heading).toBeNull()
    // No pre-selection: acceptance_criteria must not be a discovered field id
    expect(call.acceptance_criteria).toBe("")
  })

  it("the Acceptance Criteria heading textbox shows an InfoTooltip", () => {
    render(
      <JiraFieldMappingSection
        fieldMappingValues={{
          acceptance_criteria: null,
          acceptance_criteria_heading: "### AC",
        }}
        onFieldMappingChange={() => undefined}
      />,
      { wrapper },
    )

    expect(screen.getByRole("button", { name: /About heading text/i })).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// CustomFieldSelect — stale value handling
// ---------------------------------------------------------------------------

describe("JiraFieldMappingSection — stale field value", () => {
  it("shows a '(not in discovered fields)' option when the stored id is absent from discovered list", async () => {
    render(
      <JiraFieldMappingSection
        connectionId="conn-1"
        fieldMappingValues={{ story_points: "customfield_99999" }}
        onFieldMappingChange={() => undefined}
      />,
      { wrapper },
    )

    await waitFor(() => {
      const select = screen.getByRole("combobox", { name: "Story points field" }) as HTMLSelectElement
      expect(
        Array.from(select.options).some((o) =>
          o.text.includes("not in discovered fields"),
        ),
      ).toBe(true)
    })
  })
})
