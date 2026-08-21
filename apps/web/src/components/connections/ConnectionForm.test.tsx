import { useState } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"

import { ConnectionForm } from "@/components/connections/ConnectionForm"
import { type Connector } from "@/lib/connectors"
import { type SourceConnection } from "@/lib/connections"

const jiraConnector: Connector = {
  name: "jira",
  display_name: "Jira",
  config_schema: {
    type: "object",
    properties: {
      base_url: { type: "string", title: "Base URL" },
      token: { type: "string", title: "Token", writeOnly: true },
    },
    required: ["base_url", "token"],
  },
  capabilities: {
    provides_workitems: true,
    provides_sprints: true,
    provides_mergerequests: false,
    provides_repositories: false,
    provides_reviews: false,
    provides_comments: false,
    provides_transitions: true,
    supports_incremental_fetch: false,
    supports_pagination_cursor: false,
    max_window_days: null,
  },
}

const existingConnection: SourceConnection = {
  id: "conn-1",
  name: "Acme Jira",
  connector_name: "jira",
  config: { base_url: "https://acme.atlassian.net" },
  created_at: "2026-01-01T00:00:00Z",
}

function Harness() {
  const [editing, setEditing] = useState<SourceConnection | null>(existingConnection)
  return (
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <ConnectionForm
          connectors={[jiraConnector]}
          editing={editing}
          onCancel={() => setEditing(null)}
        />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

afterEach(cleanup)

describe("ConnectionForm cancel-edit", () => {
  it("resets to a clean add form when an edit is canceled", () => {
    render(<Harness />)

    // Edit mode is pre-populated with the connection's name and config.
    expect(screen.getByRole("heading", { name: "Edit connection" })).toBeInTheDocument()
    expect(screen.getByLabelText("Connection name")).toHaveValue("Acme Jira")
    expect(screen.getByLabelText(/^Base URL/)).toHaveValue("https://acme.atlassian.net")

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }))

    // Back to Add mode with a blank form so a submit cannot resurrect the abandoned edit.
    expect(screen.getByRole("heading", { name: "Add connection" })).toBeInTheDocument()
    expect(screen.getByLabelText("Connection name")).toHaveValue("")
    expect(screen.getByLabelText(/^Base URL/)).toHaveValue("")
  })
})

// ---------------------------------------------------------------------------
// Required-field client-side validation (AUDIT-12)
// ---------------------------------------------------------------------------

function AddHarness({ onSaved = vi.fn() }: { onSaved?: () => void }) {
  return (
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <ConnectionForm connectors={[jiraConnector]} onSaved={onSaved} />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe("ConnectionForm — required schema field validation", () => {
  it("Add connection button is disabled when required schema fields are blank", () => {
    render(<AddHarness />)

    // Fill in the connection name but leave base_url and token blank.
    fireEvent.change(screen.getByLabelText("Connection name"), {
      target: { value: "My Jira" },
    })

    expect(screen.getByRole("button", { name: "Add connection" })).toBeDisabled()
  })

  it("Add connection button is enabled when all required fields are filled", () => {
    render(<AddHarness />)

    fireEvent.change(screen.getByLabelText("Connection name"), {
      target: { value: "My Jira" },
    })
    fireEvent.change(screen.getByLabelText(/^Base URL/), {
      target: { value: "https://acme.atlassian.net" },
    })
    fireEvent.change(screen.getByLabelText(/^Token/), {
      target: { value: "secret-token" },
    })

    expect(screen.getByRole("button", { name: "Add connection" })).not.toBeDisabled()
  })

  it("base_url input has required and aria-required attributes", () => {
    render(<AddHarness />)

    const input = screen.getByLabelText(/^Base URL/)
    expect(input).toHaveAttribute("required")
    expect(input).toHaveAttribute("aria-required", "true")
  })

  it("edit mode: Save connection button is enabled when the token is left blank (keep existing)", () => {
    // In edit mode, the token field is cleared to "" so the user can optionally re-enter it.
    // Leaving it blank means "keep the existing token on the server" — submit must not be blocked.
    render(<Harness />)

    // The token field is already blank (edit mode wipes secrets); name and base_url are filled.
    // Leaving token blank should not block Save.
    expect(screen.getByRole("button", { name: "Save connection" })).not.toBeDisabled()
  })
})
