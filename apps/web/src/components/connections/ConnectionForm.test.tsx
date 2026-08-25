import { useState } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"

import { ConnectionForm } from "@/components/connections/ConnectionForm"
import { type Connector } from "@/lib/connectors"
import { type SourceConnection } from "@/lib/connections"

vi.mock("@/lib/connections", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/connections")>()
  return {
    ...actual,
    testConnectionDraft: vi.fn().mockResolvedValue({ ok: true, detail: "OK", user_display_name: "Test User", permissions: [] }),
    createConnection: vi.fn().mockResolvedValue({ id: "new-id", name: "x", connector_name: "jira", config: {}, created_at: "" }),
    updateConnection: vi.fn().mockResolvedValue({ id: "conn-1", name: "x", connector_name: "jira", config: {}, created_at: "" }),
  }
})

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

  it("add mode: the token input has the required attribute so browsers and screen readers flag it as required", () => {
    render(<AddHarness />)

    expect(screen.getByLabelText(/^Token/)).toHaveAttribute("required")
    expect(screen.getByLabelText(/^Token/)).toHaveAttribute("aria-required", "true")
  })

  it("edit mode: the token input does not have the required attribute — blank means keep existing, not missing", () => {
    render(<Harness />)

    // Without this fix, native browser constraint validation would block the Save click
    // when token is blank in edit mode, even though our JS gate already allows it.
    expect(screen.getByLabelText(/^Token/)).not.toHaveAttribute("required")
    expect(screen.getByLabelText(/^Token/)).not.toHaveAttribute("aria-required", "true")
  })

  it("a required boolean field with no default does not block submit while the switch is unchecked", () => {
    // A boolean switch always represents a definite value (unchecked = false).
    // It must never be treated as "missing" by requiredSchemaFieldsFilled.
    const boolConnector: Connector = {
      ...jiraConnector,
      name: "jira",
      config_schema: {
        type: "object",
        properties: {
          base_url: { type: "string", title: "Base URL" },
          active: { type: "boolean", title: "Active" },
        },
        required: ["base_url", "active"],
      },
    }

    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <ConnectionForm connectors={[boolConnector]} />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    // Fill the non-boolean required fields.
    fireEvent.change(screen.getByLabelText("Connection name"), { target: { value: "Test" } })
    fireEvent.change(screen.getByLabelText(/^Base URL/), { target: { value: "https://test.invalid" } })

    // The boolean switch is unchecked (= false) — this is a valid value, not a missing one.
    expect(screen.getByRole("button", { name: "Add connection" })).not.toBeDisabled()
  })
})

// ---------------------------------------------------------------------------
// Base URL https:// normalization (M8.7-01)
// ---------------------------------------------------------------------------

describe("ConnectionForm — base_url normalization", () => {
  it("prepends https:// to a scheme-less base_url when Test connection is clicked", async () => {
    const { testConnectionDraft } = await import("@/lib/connections")
    vi.mocked(testConnectionDraft).mockClear()

    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <ConnectionForm connectors={[jiraConnector]} />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    fireEvent.change(screen.getByLabelText("Connection name"), {
      target: { value: "Test Jira" },
    })
    fireEvent.change(screen.getByLabelText(/^Base URL/), {
      target: { value: "acme.atlassian.net" },
    })
    fireEvent.change(screen.getByLabelText(/^Token/), {
      target: { value: "tok" },
    })

    fireEvent.click(screen.getByRole("button", { name: "Test connection" }))

    await waitFor(() => {
      expect(vi.mocked(testConnectionDraft)).toHaveBeenCalledWith(
        expect.objectContaining({
          config: expect.objectContaining({ base_url: "https://acme.atlassian.net" }),
        }),
        expect.anything(),
      )
    })
  })

  it("does not double-prepend when the URL already starts with https://", async () => {
    const { testConnectionDraft } = await import("@/lib/connections")
    vi.mocked(testConnectionDraft).mockClear()

    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <ConnectionForm connectors={[jiraConnector]} />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    fireEvent.change(screen.getByLabelText("Connection name"), {
      target: { value: "Test Jira" },
    })
    fireEvent.change(screen.getByLabelText(/^Base URL/), {
      target: { value: "https://acme.atlassian.net" },
    })
    fireEvent.change(screen.getByLabelText(/^Token/), {
      target: { value: "tok" },
    })

    fireEvent.click(screen.getByRole("button", { name: "Test connection" }))

    await waitFor(() => {
      expect(vi.mocked(testConnectionDraft)).toHaveBeenCalledWith(
        expect.objectContaining({
          config: expect.objectContaining({ base_url: "https://acme.atlassian.net" }),
        }),
        expect.anything(),
      )
    })
  })

  it("passes through an http:// URL unchanged", async () => {
    const { testConnectionDraft } = await import("@/lib/connections")
    vi.mocked(testConnectionDraft).mockClear()

    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <ConnectionForm connectors={[jiraConnector]} />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    fireEvent.change(screen.getByLabelText("Connection name"), {
      target: { value: "Test Jira" },
    })
    fireEvent.change(screen.getByLabelText(/^Base URL/), {
      target: { value: "http://internal.acme.net" },
    })
    fireEvent.change(screen.getByLabelText(/^Token/), {
      target: { value: "tok" },
    })

    fireEvent.click(screen.getByRole("button", { name: "Test connection" }))

    await waitFor(() => {
      expect(vi.mocked(testConnectionDraft)).toHaveBeenCalledWith(
        expect.objectContaining({
          config: expect.objectContaining({ base_url: "http://internal.acme.net" }),
        }),
        expect.anything(),
      )
    })
  })

  it("trims leading/trailing whitespace and prepends https:// to a scheme-less URL", async () => {
    const { testConnectionDraft } = await import("@/lib/connections")
    vi.mocked(testConnectionDraft).mockClear()

    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <ConnectionForm connectors={[jiraConnector]} />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    fireEvent.change(screen.getByLabelText("Connection name"), {
      target: { value: "Test Jira" },
    })
    fireEvent.change(screen.getByLabelText(/^Base URL/), {
      target: { value: "  bol.atlassian.net  " },
    })
    fireEvent.change(screen.getByLabelText(/^Token/), {
      target: { value: "tok" },
    })

    fireEvent.click(screen.getByRole("button", { name: "Test connection" }))

    await waitFor(() => {
      expect(vi.mocked(testConnectionDraft)).toHaveBeenCalledWith(
        expect.objectContaining({
          config: expect.objectContaining({ base_url: "https://bol.atlassian.net" }),
        }),
        expect.anything(),
      )
    })
  })

  it("normalizes base_url on save (Add connection submit path)", async () => {
    const { createConnection } = await import("@/lib/connections")
    vi.mocked(createConnection).mockClear()

    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <ConnectionForm connectors={[jiraConnector]} />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    fireEvent.change(screen.getByLabelText("Connection name"), {
      target: { value: "My Jira" },
    })
    fireEvent.change(screen.getByLabelText(/^Base URL/), {
      target: { value: "acme.atlassian.net" },
    })
    fireEvent.change(screen.getByLabelText(/^Token/), {
      target: { value: "tok" },
    })

    fireEvent.click(screen.getByRole("button", { name: "Add connection" }))

    await waitFor(() => {
      expect(vi.mocked(createConnection)).toHaveBeenCalledWith(
        expect.objectContaining({
          config: expect.objectContaining({ base_url: "https://acme.atlassian.net" }),
        }),
      )
    })
  })
})

// ---------------------------------------------------------------------------
// Token help links open in a new tab (M8.7-01)
// ---------------------------------------------------------------------------

describe("ConnectionForm — token help links", () => {
  it("the Jira token help link has target=_blank and rel=noopener noreferrer", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <ConnectionForm connectors={[jiraConnector]} />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    // The token help is hidden behind an InfoTooltip; open it first.
    fireEvent.click(screen.getByRole("button", { name: "About Token" }))

    const link = screen.getByRole("link", { name: /how to generate a jira token/i })
    expect(link).toHaveAttribute("target", "_blank")
    expect(link).toHaveAttribute("rel", "noopener noreferrer")
  })
})

// ---------------------------------------------------------------------------
// Jira field mapping gate (M8.7-02)
// ---------------------------------------------------------------------------

describe("ConnectionForm — Jira field mapping gate", () => {
  it("shows the gate callout (not the form controls) in add mode before any test", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <ConnectionForm connectors={[jiraConnector]} />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    expect(
      screen.getByText(/Save the connection and run a successful test to configure field mapping/i),
    ).toBeInTheDocument()
    // Switches inside the field-mapping section must not be present while gated.
    // (The SchemaForm above may still render other controls, but the mapping toggles are absent.)
    const switches = screen.queryAllByRole("switch")
    expect(switches).toHaveLength(0)
  })

  it("shows the gate callout in edit mode before a successful test", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <ConnectionForm connectors={[jiraConnector]} editing={existingConnection} />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    expect(
      screen.getByText(/Run a successful test to configure field mapping/i),
    ).toBeInTheDocument()
  })

  it("reveals the field-mapping switches after a successful test in edit mode", async () => {
    const { testConnectionDraft } = await import("@/lib/connections")
    vi.mocked(testConnectionDraft).mockResolvedValueOnce({
      ok: true,
      detail: "OK",
      user_display_name: "Test User",
      permissions: [],
    })

    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <ConnectionForm connectors={[jiraConnector]} editing={existingConnection} />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    fireEvent.click(screen.getByRole("button", { name: "Test connection" }))

    await waitFor(() => {
      expect(screen.queryByText(/configure field mapping/i)).not.toBeInTheDocument()
      expect(screen.getAllByRole("switch").length).toBeGreaterThanOrEqual(2)
    })
  })

  it("keeps the gate callout when the test returns ok:false (bad credentials)", async () => {
    const { testConnectionDraft } = await import("@/lib/connections")
    vi.mocked(testConnectionDraft).mockResolvedValueOnce({
      ok: false,
      detail: "Bad credentials",
      user_display_name: null,
      permissions: [],
    })

    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <ConnectionForm connectors={[jiraConnector]} editing={existingConnection} />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    fireEvent.click(screen.getByRole("button", { name: "Test connection" }))

    await waitFor(() => {
      // The mutation resolves (no throw), but ok:false must NOT unlock field mapping.
      expect(
        screen.getByText(/Run a successful test to configure field mapping/i),
      ).toBeInTheDocument()
      expect(screen.queryByRole("switch")).not.toBeInTheDocument()
    })
  })
})
