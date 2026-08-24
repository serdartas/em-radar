import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"

import { SignalSettingsPage } from "@/pages/SignalSettingsPage"

const connectors = [
  {
    name: "jira",
    display_name: "Jira",
    config_schema: { type: "object", properties: {} },
    capabilities: {
      provides_workitems: true,
      provides_sprints: true,
      provides_mergerequests: false,
      provides_repositories: false,
      provides_reviews: false,
      provides_comments: false,
      provides_transitions: true,
      supports_incremental_fetch: true,
      supports_pagination_cursor: false,
      max_window_days: null,
    },
    signal_schema: {
      connector_type: "jira",
      entity_types: ["issue"],
      scope_types: [],
      fields: [
        {
          key: "age_in_current_status",
          label: "Age in current status",
          type: "duration",
          operators: ["greater_than", "less_than"],
          values: [],
          value_provider: null,
          availability: null,
        },
        {
          key: "status_category",
          label: "Status Category",
          type: "enum",
          operators: ["is", "is_not"],
          values: ["todo", "in_progress", "done"],
          value_provider: null,
          availability: null,
        },
      ],
    },
  },
  {
    name: "gitlab",
    display_name: "GitLab",
    config_schema: { type: "object", properties: {} },
    capabilities: {
      provides_workitems: false,
      provides_sprints: false,
      provides_mergerequests: true,
      provides_repositories: true,
      provides_reviews: true,
      provides_comments: false,
      provides_transitions: false,
      supports_incremental_fetch: true,
      supports_pagination_cursor: false,
      max_window_days: null,
    },
    signal_schema: {
      connector_type: "gitlab",
      entity_types: ["merge_request"],
      scope_types: [],
      fields: [
        {
          key: "state",
          label: "State",
          type: "enum",
          operators: ["is", "is_not"],
          values: ["open", "draft", "merged", "closed"],
          value_provider: null,
          availability: null,
        },
        {
          key: "approval_count",
          label: "Approval count",
          type: "number",
          operators: ["is", "greater_than", "less_than"],
          values: [],
          value_provider: null,
          availability: { requires_scope_capability: ["reviews"] },
        },
        {
          key: "pipeline_status",
          label: "Pipeline status",
          type: "enum",
          operators: ["is", "is_not"],
          values: ["success", "failed", "running"],
          value_provider: null,
          availability: { requires_scope_capability: ["pipelines"] },
        },
      ],
    },
  },
]

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  })
}

const EXISTING_DEFINITION = {
  id: "def-abc",
  name: "Stale issues",
  description: null,
  entity_type: "issue",
  expression: {
    type: "group",
    operator: "all",
    conditions: [{ field: "status_category", operator: "is", value: "in_progress" }],
  },
  report_settings: { severity: "warning", category: "flow" },
  origin: "user_created",
  template_key: null,
  created_at: "2024-01-01T00:00:00Z",
  updated_at: "2024-01-01T00:00:00Z",
}

function mockApi(
  options: { duplicateName?: boolean; withDefinitions?: boolean; deleteFails?: boolean } = {},
) {
  return vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    const url = typeof input === "string" ? input : input.toString()
    const method = init?.method ?? "GET"
    if (url.endsWith("/api/signal-definitions") && method === "GET") {
      return Promise.resolve(
        jsonResponse(options.withDefinitions ? [EXISTING_DEFINITION] : []),
      )
    }
    if (url.endsWith("/api/connectors")) {
      return Promise.resolve(jsonResponse(connectors))
    }
    if (url.endsWith("/api/connections") && method === "GET") {
      return Promise.resolve(jsonResponse([]))
    }
    if (url.endsWith("/api/signal-definitions") && method === "POST") {
      if (options.duplicateName) {
        return Promise.resolve(
          jsonResponse({ detail: { code: "conflict", message: "signal name must be unique" } }, 409),
        )
      }
      return Promise.resolve(jsonResponse({ id: "signal-1", ...JSON.parse(String(init?.body)) }))
    }
    if (url.includes("/api/signal-definitions/") && method === "PATCH") {
      const id = url.split("/api/signal-definitions/")[1]
      return Promise.resolve(
        jsonResponse({ ...EXISTING_DEFINITION, id, ...JSON.parse(String(init?.body)) }),
      )
    }
    if (url.includes("/api/signal-definitions/") && method === "DELETE") {
      if (options.deleteFails) {
        return Promise.resolve(
          jsonResponse(
            { detail: { code: "conflict", message: "Signal is used by a config group" } },
            409,
          ),
        )
      }
      return Promise.resolve(new Response(null, { status: 204 }))
    }
    throw new Error(`unexpected fetch: ${method} ${url}`)
  })
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <SignalSettingsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

async function openForm() {
  fireEvent.click(await screen.findByRole("button", { name: "Create new" }))
  await screen.findByRole("button", { name: "Save signal" })
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("SignalSettingsPage", () => {
  it("shows the create form without any template controls", async () => {
    mockApi()
    renderPage()

    await openForm()

    expect(screen.queryByRole("button", { name: "Duplicate" })).not.toBeInTheDocument()
    expect(screen.getByLabelText("Name")).toBeInTheDocument()
    expect(screen.getByLabelText("Type")).toBeInTheDocument()
  })

  it("adds a second rule joined by a uniform connector shown on both rows", async () => {
    mockApi()
    renderPage()
    await openForm()

    fireEvent.change(screen.getByLabelText("Add rule"), { target: { value: "OR" } })

    // The first row connector now reflects the shared operator, the new last row offers add again.
    expect((screen.getByLabelText("Connector 1") as HTMLSelectElement).value).toBe("OR")
    expect(screen.getByLabelText("Add rule")).toBeInTheDocument()
  })

  it("saves a two-rule OR signal with operator any and two conditions", async () => {
    const fetchMock = mockApi()
    renderPage()
    await openForm()

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "My signal" } })
    fireEvent.change(screen.getByLabelText("Add rule"), { target: { value: "OR" } })
    fireEvent.click(screen.getByRole("button", { name: "Save signal" }))

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([url, init]) => String(url).endsWith("/api/signal-definitions") && init?.method === "POST",
      )
      expect(call).toBeTruthy()
      const body = JSON.parse(String((call?.[1] as RequestInit).body))
      expect(body.name).toBe("My signal")
      expect(body.expression.operator).toBe("any")
      expect(body.expression.conditions).toHaveLength(2)
      expect(body.report_settings.severity).toBe("warning")
    })
  })

  it("does not exceed five rules", async () => {
    mockApi()
    renderPage()
    await openForm()

    for (let index = 0; index < 4; index += 1) {
      fireEvent.change(screen.getByLabelText("Add rule"), { target: { value: "AND" } })
    }

    expect(screen.queryByLabelText("Add rule")).not.toBeInTheDocument()
    expect(screen.getByText("Max 5")).toBeInTheDocument()
  })

  it("renders an enum value dropdown for enum fields", async () => {
    mockApi()
    renderPage()
    await openForm()

    fireEvent.change(screen.getByLabelText("Field"), { target: { value: "status_category" } })

    const valueControl = screen.getByLabelText("Value") as HTMLSelectElement
    expect(valueControl.tagName).toBe("SELECT")
    expect(screen.getByRole("option", { name: "in_progress" })).toBeInTheDocument()
  })

  it("surfaces a duplicate-name conflict message", async () => {
    mockApi({ duplicateName: true })
    renderPage()
    await openForm()

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Taken" } })
    fireEvent.click(screen.getByRole("button", { name: "Save signal" }))

    expect(await screen.findByRole("alert")).toHaveTextContent("signal name must be unique")
  })

  // -------------------------------------------------------------------------
  // MR entity type tests
  // -------------------------------------------------------------------------

  it("shows merge_request option in entity type selector", async () => {
    mockApi()
    renderPage()
    await openForm()

    const typeSelect = screen.getByLabelText("Type") as HTMLSelectElement
    const options = Array.from(typeSelect.options).map((o) => o.value)
    expect(options).toContain("issue")
    expect(options).toContain("merge_request")
  })

  it("switching to merge_request shows GitLab MR fields and hides issue-only fields", async () => {
    mockApi()
    renderPage()
    await openForm()

    expect(screen.getAllByRole("option", { name: "Status Category" })).not.toHaveLength(0)

    fireEvent.change(screen.getByLabelText("Type"), { target: { value: "merge_request" } })

    await waitFor(() => {
      expect(screen.queryByRole("option", { name: "Status Category" })).not.toBeInTheDocument()
      expect(screen.getAllByRole("option", { name: "State" })).not.toHaveLength(0)
      expect(screen.getAllByRole("option", { name: "Approval count" })).not.toHaveLength(0)
    })
  })

  it("switching back to issue hides MR fields and shows issue fields", async () => {
    mockApi()
    renderPage()
    await openForm()

    fireEvent.change(screen.getByLabelText("Type"), { target: { value: "merge_request" } })
    await waitFor(() => {
      expect(screen.getAllByRole("option", { name: "State" })).not.toHaveLength(0)
    })

    fireEvent.change(screen.getByLabelText("Type"), { target: { value: "issue" } })
    await waitFor(() => {
      expect(screen.queryByRole("option", { name: "State" })).not.toBeInTheDocument()
      expect(screen.getAllByRole("option", { name: "Status Category" })).not.toHaveLength(0)
    })
  })

  it("with only GitLab connector shows only merge_request type and saves correctly", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = typeof input === "string" ? input : input.toString()
      const method = init?.method ?? "GET"
      if (url.endsWith("/api/signal-definitions") && method === "GET") {
        return Promise.resolve(jsonResponse([]))
      }
      if (url.endsWith("/api/connectors")) {
        return Promise.resolve(jsonResponse([connectors[1]])) // GitLab only
      }
      if (url.endsWith("/api/connections") && method === "GET") {
        return Promise.resolve(jsonResponse([]))
      }
      if (url.endsWith("/api/signal-definitions") && method === "POST") {
        return Promise.resolve(jsonResponse({ id: "signal-1", ...JSON.parse(String(init?.body)) }))
      }
      throw new Error(`unexpected fetch: ${method} ${url}`)
    })
    renderPage()
    await openForm()

    const typeSelect = screen.getByLabelText("Type") as HTMLSelectElement
    const options = Array.from(typeSelect.options).map((o) => o.value)
    // Only merge_request is available — issue has no fields
    expect(options).toContain("merge_request")
    expect(options).not.toContain("issue")

    // Default entity type snapped to merge_request → MR fields are visible
    expect(screen.getAllByRole("option", { name: "State" })).not.toHaveLength(0)
    expect(screen.queryByRole("option", { name: "Status Category" })).not.toBeInTheDocument()

    // Saving emits merge_request
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "MR signal" } })
    // Default first MR field is "approval_count" (number, empty sentinel = invalid). Use state (enum).
    fireEvent.change(screen.getByLabelText("Field"), { target: { value: "state" } })
    const fetchMock = vi.mocked(globalThis.fetch)
    fireEvent.click(screen.getByRole("button", { name: "Save signal" }))

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([url, init]) => String(url).endsWith("/api/signal-definitions") && init?.method === "POST",
      )
      expect(call).toBeTruthy()
      const body = JSON.parse(String((call?.[1] as RequestInit).body))
      expect(body.entity_type).toBe("merge_request")
    })
  })

  it("saves a merge_request signal with entity_type merge_request", async () => {
    const fetchMock = mockApi()
    renderPage()
    await openForm()

    fireEvent.change(screen.getByLabelText("Type"), { target: { value: "merge_request" } })
    await waitFor(() => {
      expect(screen.getAllByRole("option", { name: "State" })).not.toHaveLength(0)
    })

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Merged without approval" } })
    fireEvent.change(screen.getByLabelText("Field"), { target: { value: "state" } })
    // Add second rule
    fireEvent.change(screen.getByLabelText("Add rule"), { target: { value: "AND" } })
    // New row defaults to "approval_count" (number, empty sentinel = invalid); switch to an enum field.
    fireEvent.change(screen.getAllByLabelText("Field")[1], { target: { value: "state" } })

    fireEvent.click(screen.getByRole("button", { name: "Save signal" }))

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([url, init]) => String(url).endsWith("/api/signal-definitions") && init?.method === "POST",
      )
      expect(call).toBeTruthy()
      const body = JSON.parse(String((call?.[1] as RequestInit).body))
      expect(body.entity_type).toBe("merge_request")
      expect(body.name).toBe("Merged without approval")
      expect(body.expression.conditions).toHaveLength(2)
    })
  })
})

// ---------------------------------------------------------------------------
// Edit flow: SignalListItem Edit button + update path
// ---------------------------------------------------------------------------

describe("SignalSettingsPage — edit flow", () => {
  it("shows an Edit button on each signal list item", async () => {
    mockApi({ withDefinitions: true })
    renderPage()

    expect(await screen.findByRole("button", { name: "Edit" })).toBeInTheDocument()
  })

  it("clicking Edit opens the form in edit mode prefilled with the signal's name", async () => {
    mockApi({ withDefinitions: true })
    renderPage()

    fireEvent.click(await screen.findByRole("button", { name: "Edit" }))

    const nameInput = (await screen.findByLabelText("Name")) as HTMLInputElement
    expect(nameInput.value).toBe("Stale issues")
    expect(await screen.findByRole("heading", { name: "Edit signal" })).toBeInTheDocument()
  })

  it("clicking Edit shows 'Save changes' button (not 'Save signal')", async () => {
    mockApi({ withDefinitions: true })
    renderPage()

    fireEvent.click(await screen.findByRole("button", { name: "Edit" }))

    expect(await screen.findByRole("button", { name: "Save changes" })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Save signal" })).not.toBeInTheDocument()
  })

  it("submitting in edit mode calls PATCH (not POST), overwrites in place", async () => {
    const fetchMock = mockApi({ withDefinitions: true })
    renderPage()

    fireEvent.click(await screen.findByRole("button", { name: "Edit" }))
    await screen.findByRole("button", { name: "Save changes" })

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Renamed signal" } })
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }))

    await waitFor(() => {
      const patchCall = fetchMock.mock.calls.find(
        ([url, init]) =>
          String(url).includes("/api/signal-definitions/def-abc") && init?.method === "PATCH",
      )
      expect(patchCall).toBeTruthy()
      const body = JSON.parse(String((patchCall?.[1] as RequestInit).body))
      expect(body.name).toBe("Renamed signal")
    })

    // No POST to /api/signal-definitions (no new version created)
    const postCall = fetchMock.mock.calls.find(
      ([url, init]) => String(url).endsWith("/api/signal-definitions") && init?.method === "POST",
    )
    expect(postCall).toBeUndefined()
  })

  it("surfaces an error next to the item when deleting a signal fails", async () => {
    mockApi({ withDefinitions: true, deleteFails: true })
    renderPage()

    fireEvent.click(await screen.findByRole("button", { name: "Delete" }))

    expect(await screen.findByText("Signal is used by a config group")).toBeInTheDocument()
  })

  it("after successful edit, the list is shown (form closes)", async () => {
    mockApi({ withDefinitions: true })
    renderPage()

    fireEvent.click(await screen.findByRole("button", { name: "Edit" }))
    await screen.findByRole("button", { name: "Save changes" })

    fireEvent.click(screen.getByRole("button", { name: "Save changes" }))

    // Form should close and list should reappear
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "Save changes" })).not.toBeInTheDocument()
    })
  })
})
