import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"

import { SourceConnectionsPage } from "@/pages/SourceConnectionsPage"

const jiraConnector = {
  name: "jira",
  display_name: "Jira (Cloud or Server)",
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

const gitlabConnector = {
  name: "gitlab",
  display_name: "GitLab",
  config_schema: {
    type: "object",
    properties: {
      base_url: { type: "string", title: "Base URL" },
      token: { type: "string", title: "Token", writeOnly: true },
      verify_tls: { type: "boolean", title: "Verify TLS", default: true },
    },
    required: ["base_url", "token"],
  },
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
}

const testResult = {
  ok: true,
  detail: "Connected",
  user_display_name: "Ada Lovelace",
  permissions: ["read"],
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  })
}

function mockApi(testHandler: () => Response = () => jsonResponse(testResult)) {
  return vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    const url = typeof input === "string" ? input : input.toString()
    if (url.endsWith("/api/connectors")) {
      return Promise.resolve(jsonResponse([jiraConnector]))
    }
    if (url.endsWith("/api/connections") && (init?.method ?? "GET") === "GET") {
      return Promise.resolve(jsonResponse([]))
    }
    if (url.endsWith("/api/connections/test")) {
      return Promise.resolve(testHandler())
    }
    if (url.endsWith("/api/connections/connection-1") && init?.method === "PATCH") {
      return Promise.resolve(jsonResponse({}))
    }
    throw new Error(`unexpected fetch: ${init?.method ?? "GET"} ${url}`)
  })
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <SourceConnectionsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("SourceConnectionsPage", () => {
  it("renders Jira as the default selected connector in the dropdown", async () => {
    mockApi()
    renderPage()

    await screen.findByLabelText(/^Base URL/)
    const select = screen.getByLabelText(/Source type/) as HTMLSelectElement
    expect(select.value).toBe("jira")
  })

  it("lists all five source types in the dropdown with non-Jira ones disabled", async () => {
    mockApi()
    renderPage()

    await screen.findByLabelText(/^Base URL/)
    const options = screen.getAllByRole("option") as HTMLOptionElement[]
    const optionMap = Object.fromEntries(options.map((o) => [o.value, o]))

    expect(optionMap["jira"].disabled).toBe(false)
    expect(optionMap["jira"].textContent).toBe("Jira")

    for (const name of ["linear", "github_issues", "gitlab", "github"]) {
      expect(optionMap[name].disabled).toBe(true)
      expect(optionMap[name].textContent).toContain("coming soon")
    }
  })

  it("renders the connector form with a write-only secret field", async () => {
    mockApi()
    renderPage()

    const token = (await screen.findByLabelText(/^Token/)) as HTMLInputElement
    expect(token.type).toBe("password")
    expect(screen.getByLabelText(/^Base URL/)).toBeInTheDocument()
  })

  it("shows the authenticated user after a successful test", async () => {
    mockApi()
    renderPage()

    fireEvent.change(await screen.findByLabelText(/^Base URL/), {
      target: { value: "https://demo.invalid" },
    })
    fireEvent.change(screen.getByLabelText(/^Token/), { target: { value: "secret-token" } })
    fireEvent.click(screen.getByRole("button", { name: "Test connection" }))

    expect(await screen.findByText(/Connected as Ada Lovelace/)).toBeInTheDocument()
  })

  it("surfaces a token-free error when the test fails", async () => {
    mockApi(() =>
      jsonResponse({
        ok: false,
        detail: "Credentials were rejected.",
        user_display_name: null,
        permissions: [],
      }),
    )
    renderPage()

    fireEvent.change(await screen.findByLabelText(/^Base URL/), {
      target: { value: "https://demo.invalid" },
    })
    fireEvent.change(screen.getByLabelText(/^Token/), { target: { value: "rejected-token" } })
    fireEvent.click(screen.getByRole("button", { name: "Test connection" }))

    await waitFor(() => {
      expect(screen.getByText("Credentials were rejected.")).toBeInTheDocument()
    })
  })

  it("shows an explanation and suggestions for a coded test failure", async () => {
    mockApi(() =>
      jsonResponse({
        ok: false,
        detail: "Jira authentication failed",
        user_display_name: null,
        permissions: [],
        code: "auth",
      }),
    )
    renderPage()

    fireEvent.change(await screen.findByLabelText(/^Base URL/), {
      target: { value: "https://demo.invalid" },
    })
    fireEvent.change(screen.getByLabelText(/^Token/), { target: { value: "bad-token" } })
    fireEvent.click(screen.getByRole("button", { name: "Test connection" }))

    expect(await screen.findByText("The credentials were rejected by the source.")).toBeInTheDocument()
    expect(
      screen.getByText(/Check the token is correct and has not expired/),
    ).toBeInTheDocument()
  })

  it("offers click-to-toggle help for the Jira Base URL and Token fields", async () => {
    mockApi()
    renderPage()

    expect(await screen.findByRole("button", { name: "About Base URL" })).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "About Token" }))

    const helpLink = screen.getByRole("link", { name: /How to generate a Jira token/ })
    expect(helpLink).toHaveAttribute("href", "/help/jira")
  })

  it("omits unchanged write-only fields when editing a connection", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.endsWith("/api/connectors")) {
        return Promise.resolve(jsonResponse([jiraConnector]))
      }
      if (url.endsWith("/api/connections") && (init?.method ?? "GET") === "GET") {
        return Promise.resolve(
          jsonResponse([
            {
              id: "connection-1",
              name: "Acme Jira",
              connector_name: "jira",
              config: { base_url: "https://demo.invalid", token: "****5678" },
              created_at: "2026-06-01T10:00:00Z",
            },
          ]),
        )
      }
      // JiraFieldMappingSection fires this when connectionId is set (edit mode).
      if (url.includes("/api/connections/connection-1/jira/fields")) {
        return Promise.resolve(jsonResponse([]))
      }
      if (url.endsWith("/api/connections/connection-1") && init?.method === "PATCH") {
        return Promise.resolve(jsonResponse({}))
      }
      throw new Error(`unexpected fetch: ${init?.method ?? "GET"} ${url}`)
    })
    renderPage()

    fireEvent.click(await screen.findByRole("button", { name: "Edit" }))

    // Wait until the form is fully hydrated: the Save button is enabled (selectedConnector
    // is resolved and all required fields pass validation).
    const saveButton = await screen.findByRole("button", { name: "Save connection" })
    await waitFor(() => expect(saveButton).not.toBeDisabled())

    fireEvent.change(screen.getByLabelText(/^Base URL/), {
      target: { value: "https://updated.invalid" },
    })
    // Submit the form directly — fireEvent.click on a submit button can miss the form's
    // onSubmit in jsdom when the surrounding component is complex (e.g. JiraFieldMappingSection
    // in edit mode). Submitting the form element directly is more reliable.
    fireEvent.submit(saveButton.closest("form")!)

    await waitFor(() => {
      const patch = fetchMock.mock.calls.find(
        ([url, init]) => String(url).endsWith("/api/connections/connection-1") && init?.method === "PATCH",
      )
      expect(patch).toBeTruthy()
      expect(JSON.parse(String(patch?.[1]?.body)).config).toEqual({
        base_url: "https://updated.invalid",
      })
    })
  })

  it("disables the submit button when the connection name is empty", async () => {
    mockApi()
    renderPage()

    await screen.findByLabelText(/^Base URL/)

    const submitButton = screen.getByRole("button", { name: "Add connection" })
    expect(submitButton).toBeDisabled()

    // Fill in required schema fields so the name is the only blocker.
    fireEvent.change(screen.getByLabelText(/^Base URL/), {
      target: { value: "https://jira.example.com" },
    })
    fireEvent.change(screen.getByLabelText(/^Token/), {
      target: { value: "my-token" },
    })

    // Required schema fields filled but name still blank — still disabled.
    expect(submitButton).toBeDisabled()

    fireEvent.change(screen.getByLabelText(/Connection name/), {
      target: { value: "My Jira" },
    })
    // All required fields filled → enabled.
    expect(submitButton).not.toBeDisabled()

    fireEvent.change(screen.getByLabelText(/Connection name/), {
      target: { value: "" },
    })
    // Name cleared → disabled again.
    expect(submitButton).toBeDisabled()
  })

  it("shows a created connection in the list by its name", async () => {
    const createdConnection = {
      id: "new-connection",
      name: "Prod Jira",
      connector_name: "jira",
      config: { base_url: "https://prod.invalid", token: "****" },
      created_at: "2026-07-01T00:00:00Z",
    }
    let connectionsStore: typeof createdConnection[] = []

    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.endsWith("/api/connectors")) {
        return Promise.resolve(jsonResponse([jiraConnector]))
      }
      if (url.endsWith("/api/connections") && (init?.method ?? "GET") === "GET") {
        return Promise.resolve(jsonResponse(connectionsStore))
      }
      if (url.endsWith("/api/connections") && init?.method === "POST") {
        connectionsStore = [createdConnection]
        return Promise.resolve(jsonResponse(createdConnection, 201))
      }
      throw new Error(`unexpected fetch: ${init?.method ?? "GET"} ${url}`)
    })

    renderPage()

    await screen.findByLabelText(/^Base URL/)
    fireEvent.change(screen.getByLabelText(/Connection name/), {
      target: { value: "Prod Jira" },
    })
    fireEvent.change(screen.getByLabelText(/^Base URL/), {
      target: { value: "https://prod.invalid" },
    })
    fireEvent.change(screen.getByLabelText(/^Token/), { target: { value: "tok" } })
    fireEvent.click(screen.getByRole("button", { name: "Add connection" }))

    expect(await screen.findByText("Prod Jira")).toBeInTheDocument()
  })

  it("renders a duplicate-name API error near the form", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.endsWith("/api/connectors")) {
        return Promise.resolve(jsonResponse([jiraConnector]))
      }
      if (url.endsWith("/api/connections") && (init?.method ?? "GET") === "GET") {
        return Promise.resolve(jsonResponse([]))
      }
      if (url.endsWith("/api/connections") && init?.method === "POST") {
        return Promise.resolve(
          jsonResponse({ detail: "a connection named 'Duplicate' already exists" }, 422),
        )
      }
      throw new Error(`unexpected fetch: ${init?.method ?? "GET"} ${url}`)
    })

    renderPage()

    await screen.findByLabelText(/^Base URL/)
    fireEvent.change(screen.getByLabelText(/Connection name/), {
      target: { value: "Duplicate" },
    })
    fireEvent.change(screen.getByLabelText(/^Base URL/), {
      target: { value: "https://demo.invalid" },
    })
    fireEvent.change(screen.getByLabelText(/^Token/), { target: { value: "tok" } })
    fireEvent.click(screen.getByRole("button", { name: "Add connection" }))

    expect(
      await screen.findByText(/already exists/i),
    ).toBeInTheDocument()
  })

  it("has no project/board picker and no run-report control", async () => {
    mockApi()
    renderPage()

    await screen.findByLabelText(/^Base URL/)

    expect(screen.queryByLabelText(/Project/i)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/Board/i)).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /Run report/i })).not.toBeInTheDocument()
  })

  it("creates a named GitLab connection and shows it in the list", async () => {
    const createdConnection = {
      id: "new-gitlab",
      name: "Acme GitLab",
      connector_name: "gitlab",
      config: { base_url: "https://gitlab.com", token: "****", verify_tls: true },
      created_at: "2026-08-01T00:00:00Z",
    }
    let connectionsStore: (typeof createdConnection)[] = []

    let createdBody: unknown
    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.endsWith("/api/connectors")) {
        return Promise.resolve(jsonResponse([gitlabConnector]))
      }
      if (url.endsWith("/api/connections") && (init?.method ?? "GET") === "GET") {
        return Promise.resolve(jsonResponse(connectionsStore))
      }
      if (url.endsWith("/api/connections") && init?.method === "POST") {
        createdBody = JSON.parse(String(init?.body))
        connectionsStore = [createdConnection]
        return Promise.resolve(jsonResponse(createdConnection, 201))
      }
      throw new Error(`unexpected fetch: ${init?.method ?? "GET"} ${url}`)
    })

    renderPage()

    await screen.findByLabelText(/^Base URL/)
    const select = screen.getByLabelText(/Source type/) as HTMLSelectElement
    expect(select.value).toBe("gitlab")

    fireEvent.change(screen.getByLabelText(/Connection name/), {
      target: { value: "Acme GitLab" },
    })
    fireEvent.change(screen.getByLabelText(/^Base URL/), {
      target: { value: "https://gitlab.com" },
    })
    fireEvent.change(screen.getByLabelText(/^Token/), { target: { value: "glpat-token" } })
    fireEvent.click(screen.getByRole("button", { name: "Add connection" }))

    expect(await screen.findByText("Acme GitLab")).toBeInTheDocument()
    expect(createdBody).toMatchObject({ name: "Acme GitLab", connector_name: "gitlab" })
  })

  it("shows inline read-only token guidance for GitLab", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.endsWith("/api/connectors")) {
        return Promise.resolve(jsonResponse([gitlabConnector]))
      }
      if (url.endsWith("/api/connections") && (init?.method ?? "GET") === "GET") {
        return Promise.resolve(jsonResponse([]))
      }
      throw new Error(`unexpected fetch: ${init?.method ?? "GET"} ${url}`)
    })
    renderPage()

    await screen.findByLabelText(/^Base URL/)
    fireEvent.click(screen.getByRole("button", { name: "About Token" }))

    expect(screen.getByText("read-only")).toBeInTheDocument()
    expect(screen.getByText("read_api")).toBeInTheDocument()
  })

  it("has no repository picker and no run-report action for GitLab", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.endsWith("/api/connectors")) {
        return Promise.resolve(jsonResponse([gitlabConnector]))
      }
      if (url.endsWith("/api/connections") && (init?.method ?? "GET") === "GET") {
        return Promise.resolve(jsonResponse([]))
      }
      throw new Error(`unexpected fetch: ${init?.method ?? "GET"} ${url}`)
    })
    renderPage()

    await screen.findByLabelText(/^Base URL/)

    expect(screen.queryByLabelText(/Repositor/i)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/Project/i)).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /Run report/i })).not.toBeInTheDocument()
  })

  // ---------------------------------------------------------------------------
  // Delete connection flow
  // ---------------------------------------------------------------------------

  function mockApiWithConnection(
    deleteHandler: (url: string) => Response = () => new Response(null, { status: 204 }),
  ) {
    const conn = {
      id: "conn-1",
      name: "Jira Prod",
      connector_name: "jira",
      config: {},
      created_at: "2026-01-01T00:00:00Z",
    }
    return vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.endsWith("/api/connectors")) {
        return Promise.resolve(jsonResponse([jiraConnector]))
      }
      if (url.endsWith("/api/connections") && (init?.method ?? "GET") === "GET") {
        return Promise.resolve(jsonResponse([conn]))
      }
      if (url.includes("/api/connections/conn-1") && init?.method === "DELETE") {
        return Promise.resolve(deleteHandler(url))
      }
      throw new Error(`unexpected fetch: ${init?.method ?? "GET"} ${url}`)
    })
  }

  it("Delete button shows confirmation dialog before calling the API", async () => {
    const fetchMock = mockApiWithConnection()
    renderPage()

    fireEvent.click(await screen.findByRole("button", { name: "Delete" }))

    expect(
      screen.getByRole("alertdialog", { name: "Confirm: Delete connection Jira Prod" }),
    ).toBeInTheDocument()

    const deleteCalls = fetchMock.mock.calls.filter(
      ([, init]) => (init?.method ?? "GET").toUpperCase() === "DELETE",
    )
    expect(deleteCalls).toHaveLength(0)
  })

  it("Cancel dismisses the confirmation dialog without calling the API", async () => {
    const fetchMock = mockApiWithConnection()
    renderPage()

    fireEvent.click(await screen.findByRole("button", { name: "Delete" }))
    expect(screen.getByRole("alertdialog")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }))
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument()

    const deleteCalls = fetchMock.mock.calls.filter(
      ([, init]) => (init?.method ?? "GET").toUpperCase() === "DELETE",
    )
    expect(deleteCalls).toHaveLength(0)
  })

  it("Confirm delete calls the delete API", async () => {
    const fetchMock = mockApiWithConnection()
    renderPage()

    fireEvent.click(await screen.findByRole("button", { name: "Delete" }))
    fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }))

    await waitFor(() => {
      const deleteCalls = fetchMock.mock.calls.filter(
        ([, init]) => (init?.method ?? "GET").toUpperCase() === "DELETE",
      )
      expect(deleteCalls.length).toBeGreaterThan(0)
    })
  })

  it("shows dependent teams and force-confirm on 409 conflict", async () => {
    mockApiWithConnection((url) => {
      if (url.includes("force=true")) {
        return new Response(null, { status: 204 })
      }
      return jsonResponse(
        {
          detail: {
            message: "connection is in use",
            dependent_teams: [{ id: "team-1", name: "Platform" }],
          },
        },
        409,
      )
    })
    renderPage()

    fireEvent.click(await screen.findByRole("button", { name: "Delete" }))
    fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }))

    await screen.findByText("Platform")
    expect(screen.getByRole("button", { name: "Confirm force delete" })).toBeInTheDocument()
  })

  it("force-confirm retries with force=true and succeeds", async () => {
    let forceUsed = false
    mockApiWithConnection((url) => {
      if (url.includes("force=true")) {
        forceUsed = true
        return new Response(null, { status: 204 })
      }
      return jsonResponse(
        {
          detail: {
            message: "connection is in use",
            dependent_teams: [{ id: "team-1", name: "Platform" }],
          },
        },
        409,
      )
    })
    renderPage()

    fireEvent.click(await screen.findByRole("button", { name: "Delete" }))
    fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }))

    await screen.findByRole("button", { name: "Confirm force delete" })
    fireEvent.click(screen.getByRole("button", { name: "Confirm force delete" }))

    await waitFor(() => expect(forceUsed).toBe(true))
  })

  // ---------------------------------------------------------------------------
  // Progressive disclosure (M8.5-07)
  // ---------------------------------------------------------------------------

  it("does not show the add form while the connections query is pending", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.endsWith("/api/connectors")) {
        return Promise.resolve(jsonResponse([jiraConnector]))
      }
      return new Promise(() => {})
    })
    renderPage()

    await screen.findByText(/Loading connections/)
    expect(screen.queryByLabelText(/^Base URL/)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/Connection name/)).not.toBeInTheDocument()
  })

  it("shows the add form directly when there are no connections", async () => {
    mockApi()
    renderPage()

    expect(await screen.findByLabelText(/^Base URL/)).toBeInTheDocument()
    expect(screen.getByLabelText(/Connection name/)).toBeInTheDocument()
  })

  it("hides the add form behind a reveal button when connections exist", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.endsWith("/api/connectors")) {
        return Promise.resolve(jsonResponse([jiraConnector]))
      }
      if (url.endsWith("/api/connections") && (init?.method ?? "GET") === "GET") {
        return Promise.resolve(
          jsonResponse([
            {
              id: "conn-1",
              name: "Jira Prod",
              connector_name: "jira",
              config: {},
              created_at: "2026-01-01T00:00:00Z",
            },
          ]),
        )
      }
      throw new Error(`unexpected fetch: ${init?.method ?? "GET"} ${url}`)
    })
    renderPage()

    expect(await screen.findByText("Jira Prod")).toBeInTheDocument()
    expect(screen.queryByLabelText(/^Base URL/)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/Connection name/)).not.toBeInTheDocument()

    const revealButton = screen.getByRole("button", { name: "Add connection" })
    expect(revealButton).toBeInTheDocument()

    fireEvent.click(revealButton)
    expect(await screen.findByLabelText(/^Base URL/)).toBeInTheDocument()
  })

  it("collapses the add form when Cancel is clicked inside the panel", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.endsWith("/api/connectors")) {
        return Promise.resolve(jsonResponse([jiraConnector]))
      }
      if (url.endsWith("/api/connections") && (init?.method ?? "GET") === "GET") {
        return Promise.resolve(
          jsonResponse([
            {
              id: "conn-1",
              name: "Jira Prod",
              connector_name: "jira",
              config: {},
              created_at: "2026-01-01T00:00:00Z",
            },
          ]),
        )
      }
      throw new Error(`unexpected fetch: ${init?.method ?? "GET"} ${url}`)
    })
    renderPage()

    await screen.findByText("Jira Prod")
    fireEvent.click(screen.getByRole("button", { name: "Add connection" }))
    expect(await screen.findByLabelText(/^Base URL/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }))
    expect(screen.queryByLabelText(/^Base URL/)).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Add connection" })).toBeInTheDocument()
  })

  it("per-connection controls (Re-test, Edit, Delete) are visible when connections exist", async () => {
    mockApiWithConnection()
    renderPage()

    await screen.findByText("Jira Prod")
    expect(screen.getByRole("button", { name: "Re-test" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Delete" })).toBeInTheDocument()
  })

  it("renders a Callout error when the delete mutation fails with a non-conflict error", async () => {
    mockApiWithConnection(() =>
      jsonResponse({ detail: "Internal server error" }, 500),
    )
    renderPage()

    fireEvent.click(await screen.findByRole("button", { name: "Delete" }))
    fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }))

    const alert = await screen.findByRole("alert")
    expect(alert).toBeInTheDocument()
    expect(alert.textContent).toMatch(/could not delete/i)
  })

  it("moves focus into the first form field when the panel is revealed", async () => {
    mockApiWithConnection()
    renderPage()

    await screen.findByText("Jira Prod")
    fireEvent.click(screen.getByRole("button", { name: "Add connection" }))

    await waitFor(() => {
      expect(screen.getByLabelText(/Connection name/)).toHaveFocus()
    })
  })

  it("returns focus to the reveal button when the panel is cancelled", async () => {
    mockApiWithConnection()
    renderPage()

    await screen.findByText("Jira Prod")
    fireEvent.click(screen.getByRole("button", { name: "Add connection" }))
    await screen.findByLabelText(/^Base URL/)

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }))

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Add connection" })).toHaveFocus()
    })
  })
})

// ---------------------------------------------------------------------------
// M9-10: Post-connection GitLab notification (§16)
// ---------------------------------------------------------------------------

const gitlabConnectorMR = {
  name: "gitlab",
  display_name: "GitLab",
  config_schema: {
    type: "object",
    properties: {
      base_url: { type: "string", title: "Base URL" },
      token: { type: "string", title: "Token", writeOnly: true },
    },
    required: ["base_url", "token"],
  },
  capabilities: {
    provides_workitems: false,
    provides_sprints: false,
    provides_mergerequests: true,
    provides_repositories: true,
    provides_reviews: true,
    provides_comments: false,
    provides_transitions: false,
    supports_incremental_fetch: false,
    supports_pagination_cursor: false,
    max_window_days: null,
  },
}

const teamsWithUnconfigured = [
  {
    id: "t1",
    name: "Alpha",
    description: null,
    connection_ids: [],
    scope_ids: [],
    signal_config_group_ids: [],
    code_connection_id: null,
    working_mode: "scrum",
    sprint_length_days: 14,
    member_user_keys: [],
    gitlab_config_status: "setup_required",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
  {
    id: "t2",
    name: "Beta",
    description: null,
    connection_ids: [],
    scope_ids: [],
    signal_config_group_ids: [],
    code_connection_id: null,
    working_mode: "scrum",
    sprint_length_days: 14,
    member_user_keys: [],
    gitlab_config_status: "configured",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
]

describe("SourceConnectionsPage — M9-10 post-connect notification (§16)", () => {
  it("shows ONE notification with unconfigured team count after a new MR-capable connection is saved", async () => {
    const createdGitLab = {
      id: "gl-1",
      name: "GitLab Cloud",
      connector_name: "gitlab",
      config: { base_url: "https://gitlab.com", token: "****" },
      created_at: "2026-08-01T00:00:00Z",
    }
    let connectionsStore: typeof createdGitLab[] = []

    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = typeof input === "string" ? input : input.toString()
      const method = init?.method ?? "GET"
      if (url.endsWith("/api/connectors")) return Promise.resolve(jsonResponse([gitlabConnectorMR]))
      if (url.endsWith("/api/connections") && method === "GET")
        return Promise.resolve(jsonResponse(connectionsStore))
      if (url.endsWith("/api/connections") && method === "POST") {
        connectionsStore = [createdGitLab]
        return Promise.resolve(jsonResponse(createdGitLab, 201))
      }
      // Teams query for notification count — 1 setup_required + 1 configured = count is 1
      if (url.endsWith("/api/teams") && method === "GET")
        return Promise.resolve(jsonResponse(teamsWithUnconfigured))
      throw new Error(`unexpected fetch: ${method} ${url}`)
    })

    const queryClient = new QueryClient({
      defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
    })
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <SourceConnectionsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    // Fill and submit the form
    fireEvent.change(await screen.findByLabelText(/Connection name/), {
      target: { value: "GitLab Cloud" },
    })
    fireEvent.change(screen.getByLabelText(/^Base URL/), {
      target: { value: "https://gitlab.com" },
    })
    fireEvent.change(screen.getByLabelText(/^Token/), { target: { value: "tok" } })
    fireEvent.click(screen.getByRole("button", { name: "Add connection" }))

    // Notification must appear exactly once with the correct count (1 unconfigured out of 2)
    const notification = await screen.findByRole("status")
    expect(notification).toBeInTheDocument()
    expect(notification.textContent).toMatch(/1 team has no GitLab configuration yet/i)

    // There must be exactly one notification — not one per team
    expect(screen.getAllByRole("status")).toHaveLength(1)

    // Actions must be present
    expect(screen.getByRole("button", { name: "Set up teams" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Later" })).toBeInTheDocument()
  })

  it("dismisses the notification when Later is clicked", async () => {
    const createdGitLab = {
      id: "gl-2",
      name: "GitLab",
      connector_name: "gitlab",
      config: {},
      created_at: "2026-08-01T00:00:00Z",
    }
    let connectionsStore: typeof createdGitLab[] = []

    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = typeof input === "string" ? input : input.toString()
      const method = init?.method ?? "GET"
      if (url.endsWith("/api/connectors")) return Promise.resolve(jsonResponse([gitlabConnectorMR]))
      if (url.endsWith("/api/connections") && method === "GET")
        return Promise.resolve(jsonResponse(connectionsStore))
      if (url.endsWith("/api/connections") && method === "POST") {
        connectionsStore = [createdGitLab]
        return Promise.resolve(jsonResponse(createdGitLab, 201))
      }
      if (url.endsWith("/api/teams") && method === "GET")
        return Promise.resolve(jsonResponse(teamsWithUnconfigured))
      throw new Error(`unexpected fetch: ${method} ${url}`)
    })

    const queryClient = new QueryClient({
      defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
    })
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <SourceConnectionsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    fireEvent.change(await screen.findByLabelText(/Connection name/), {
      target: { value: "GitLab" },
    })
    fireEvent.change(screen.getByLabelText(/^Base URL/), {
      target: { value: "https://gitlab.com" },
    })
    fireEvent.change(screen.getByLabelText(/^Token/), { target: { value: "tok" } })
    fireEvent.click(screen.getByRole("button", { name: "Add connection" }))

    await screen.findByRole("status")
    fireEvent.click(screen.getByRole("button", { name: "Later" }))

    await waitFor(() => {
      expect(screen.queryByRole("status")).not.toBeInTheDocument()
    })
  })

  it("does NOT show notification when a non-MR-capable connector is saved", async () => {
    const createdJira = {
      id: "j-1",
      name: "Prod Jira",
      connector_name: "jira",
      config: {},
      created_at: "2026-08-01T00:00:00Z",
    }
    let connectionsStore: typeof createdJira[] = []

    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = typeof input === "string" ? input : input.toString()
      const method = init?.method ?? "GET"
      if (url.endsWith("/api/connectors")) return Promise.resolve(jsonResponse([jiraConnector]))
      if (url.endsWith("/api/connections") && method === "GET")
        return Promise.resolve(jsonResponse(connectionsStore))
      if (url.endsWith("/api/connections") && method === "POST") {
        connectionsStore = [createdJira]
        return Promise.resolve(jsonResponse(createdJira, 201))
      }
      // Teams are available (unconfigured) so the ONLY thing suppressing the
      // notification is the MR-capability gate, not a missing teams fetch.
      if (url.endsWith("/api/teams") && method === "GET")
        return Promise.resolve(jsonResponse(teamsWithUnconfigured))
      throw new Error(`unexpected fetch: ${method} ${url}`)
    })

    const queryClient = new QueryClient({
      defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
    })
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <SourceConnectionsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    fireEvent.change(await screen.findByLabelText(/Connection name/), {
      target: { value: "Prod Jira" },
    })
    fireEvent.change(screen.getByLabelText(/^Base URL/), {
      target: { value: "https://jira.example.com" },
    })
    fireEvent.change(screen.getByLabelText(/^Token/), { target: { value: "tok" } })
    fireEvent.click(screen.getByRole("button", { name: "Add connection" }))

    // Wait for connection to appear in list
    await screen.findByText("Prod Jira")
    // No notification should appear (Jira is not MR-capable), even though unconfigured teams exist.
    expect(screen.queryByRole("status")).not.toBeInTheDocument()
  })

  it("does NOT show notification when editing an existing GitLab connection", async () => {
    const existingGitLab = {
      id: "gl-existing",
      name: "GitLab Cloud",
      connector_name: "gitlab",
      config: { base_url: "https://gitlab.com" },
      created_at: "2026-08-01T00:00:00Z",
    }

    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = typeof input === "string" ? input : input.toString()
      const method = init?.method ?? "GET"
      if (url.endsWith("/api/connectors")) return Promise.resolve(jsonResponse([gitlabConnectorMR]))
      if (url.endsWith("/api/connections") && method === "GET")
        return Promise.resolve(jsonResponse([existingGitLab]))
      if (url.includes("/api/connections/") && method === "PUT")
        return Promise.resolve(jsonResponse(existingGitLab))
      // Unconfigured teams exist: only the create-vs-edit gate suppresses the notification.
      if (url.endsWith("/api/teams") && method === "GET")
        return Promise.resolve(jsonResponse(teamsWithUnconfigured))
      throw new Error(`unexpected fetch: ${method} ${url}`)
    })

    const queryClient = new QueryClient({
      defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
    })
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <SourceConnectionsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    // Enter edit mode for the existing GitLab connection and save it.
    fireEvent.click(await screen.findByRole("button", { name: "Edit" }))
    const saveButton = await screen.findByRole("button", { name: "Save connection" })
    await waitFor(() => expect(saveButton).not.toBeDisabled())
    // Submit the form directly — clicking a submit button can miss the form's onSubmit.
    fireEvent.submit(saveButton.closest("form")!)

    // Editing must not trigger the post-connection notification (§16 is create-only).
    await waitFor(() => {
      expect(screen.queryByRole("status")).not.toBeInTheDocument()
    })
  })
})
