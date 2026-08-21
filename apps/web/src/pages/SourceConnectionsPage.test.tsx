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
      if (url.endsWith("/api/connections/connection-1") && init?.method === "PATCH") {
        return Promise.resolve(jsonResponse({}))
      }
      throw new Error(`unexpected fetch: ${init?.method ?? "GET"} ${url}`)
    })
    renderPage()

    fireEvent.click(await screen.findByRole("button", { name: "Edit" }))
    fireEvent.change(screen.getByLabelText(/^Base URL/), {
      target: { value: "https://updated.invalid" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Save connection" }))

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

    fireEvent.change(screen.getByLabelText(/Connection name/), {
      target: { value: "My Jira" },
    })
    expect(submitButton).not.toBeDisabled()

    fireEvent.change(screen.getByLabelText(/Connection name/), {
      target: { value: "" },
    })
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

  it("shows the add form directly when there are no connections", async () => {
    mockApi()
    renderPage()

    // Form fields are immediately accessible without any click
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

    // Connection is listed
    expect(await screen.findByText("Jira Prod")).toBeInTheDocument()

    // Add form is hidden — no form fields yet
    expect(screen.queryByLabelText(/^Base URL/)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/Connection name/)).not.toBeInTheDocument()

    // Reveal button is present
    const revealButton = screen.getByRole("button", { name: "Add connection" })
    expect(revealButton).toBeInTheDocument()

    // Click reveal — form appears
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
    // Reveal button is back
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
})
