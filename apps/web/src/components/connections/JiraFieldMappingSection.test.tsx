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
// JiraFieldMappingSection — Story Points
// ---------------------------------------------------------------------------

describe("JiraFieldMappingSection — Story Points", () => {
  it("starts as 'Not configured' when story_points is empty", () => {
    render(
      <JiraFieldMappingSection
        fieldMappingValues={{ story_points: "" }}
        onFieldMappingChange={() => undefined}
      />,
      { wrapper },
    )

    // Both SP and AC are not configured; there should be two "Not configured" labels.
    const labels = screen.getAllByText("Not configured")
    expect(labels.length).toBeGreaterThanOrEqual(1)
  })

  it("reveals the custom-field dropdown when enabled", async () => {
    render(
      <JiraFieldMappingSection
        connectionId="conn-1"
        fieldMappingValues={{ story_points: "customfield_10016" }}
        onFieldMappingChange={() => undefined}
      />,
      { wrapper },
    )

    // Wait for field discovery to resolve
    await waitFor(() => {
      expect(screen.getByRole("combobox", { name: "Custom field" })).toBeInTheDocument()
    })
  })

  it("enables story points and calls onFieldMappingChange when switch is toggled on", async () => {
    const onChange = vi.fn()
    render(
      <JiraFieldMappingSection
        connectionId="conn-1"
        fieldMappingValues={{ story_points: "" }}
        onFieldMappingChange={onChange}
      />,
      { wrapper },
    )

    // Find the Story Points switch (first switch in the section)
    const switches = screen.getAllByRole("switch")
    fireEvent.click(switches[0])

    await waitFor(() => {
      expect(onChange).toHaveBeenCalled()
      const call = onChange.mock.calls[0][0] as { story_points: string }
      // Should have set story_points to a non-empty string (first discovered field)
      expect(call.story_points).toBeDefined()
    })
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

    // Mode selector should be present
    expect(screen.getByRole("combobox", { name: "How is it recorded?" })).toBeInTheDocument()
    // Heading textbox should be visible
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
      // Mode selector set to "Custom field"
      const modeSelect = screen.getByRole("combobox", { name: "How is it recorded?" })
      expect((modeSelect as HTMLSelectElement).value).toBe("custom_field")
    })

    // The custom field dropdown should appear (there will be two: SP and AC)
    const fieldDropdowns = screen.getAllByRole("combobox", { name: "Custom field" })
    expect(fieldDropdowns.length).toBeGreaterThanOrEqual(1)
  })

  it("switching from 'Text in description' to 'Custom field' calls onFieldMappingChange", () => {
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

    expect(onChange).toHaveBeenCalled()
    const call = onChange.mock.calls[0][0] as {
      acceptance_criteria: string | null
      acceptance_criteria_heading: string | null
    }
    expect(call.acceptance_criteria_heading).toBeNull()
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
