import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"

import { SourceConnectionsPage } from "@/pages/SourceConnectionsPage"

const demoConnector = {
  name: "demo",
  display_name: "Demo company",
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
    provides_mergerequests: true,
    provides_repositories: true,
    provides_reviews: true,
    provides_comments: true,
    provides_transitions: true,
    supports_incremental_fetch: false,
    supports_pagination_cursor: false,
    max_window_days: null,
  },
}

const jiraConnector = {
  ...demoConnector,
  name: "jira",
  display_name: "Jira (Cloud or Server)",
}

const testResult = {
  ok: true,
  detail: "Connected",
  user_display_name: "Ada Lovelace",
  permissions: ["read"],
}

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  })
}

function mockApi(testHandler: () => Response = () => jsonResponse(testResult)) {
  return vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    const url = typeof input === "string" ? input : input.toString()
    if (url.endsWith("/api/connectors")) {
      return Promise.resolve(jsonResponse([demoConnector]))
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
  it("renders the connector form with a write-only secret field", async () => {
    mockApi()
    renderPage()

    const token = (await screen.findByLabelText(/Token/)) as HTMLInputElement
    expect(token.type).toBe("password")
    expect(screen.getByLabelText(/Base URL/)).toBeInTheDocument()
  })

  it("shows the authenticated user after a successful test", async () => {
    mockApi()
    renderPage()

    fireEvent.change(await screen.findByLabelText(/Base URL/), {
      target: { value: "https://demo.invalid" },
    })
    fireEvent.change(screen.getByLabelText(/Token/), { target: { value: "secret-token" } })
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

    fireEvent.change(await screen.findByLabelText(/Base URL/), {
      target: { value: "https://demo.invalid" },
    })
    fireEvent.change(screen.getByLabelText(/Token/), { target: { value: "rejected-token" } })
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

    fireEvent.change(await screen.findByLabelText(/Base URL/), {
      target: { value: "https://demo.invalid" },
    })
    fireEvent.change(screen.getByLabelText(/Token/), { target: { value: "bad-token" } })
    fireEvent.click(screen.getByRole("button", { name: "Test connection" }))

    expect(await screen.findByText("The credentials were rejected by the source.")).toBeInTheDocument()
    expect(
      screen.getByText(/Check the token is correct and has not expired/),
    ).toBeInTheDocument()
  })

  it("offers click-to-toggle help for the Jira Base URL and Token fields", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.endsWith("/api/connectors")) {
        return Promise.resolve(jsonResponse([jiraConnector]))
      }
      if (url.endsWith("/api/connections") && (init?.method ?? "GET") === "GET") {
        return Promise.resolve(jsonResponse([]))
      }
      throw new Error(`unexpected fetch: ${init?.method ?? "GET"} ${url}`)
    })
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
        return Promise.resolve(jsonResponse([demoConnector]))
      }
      if (url.endsWith("/api/connections") && (init?.method ?? "GET") === "GET") {
        return Promise.resolve(
          jsonResponse([
            {
              id: "connection-1",
              connector_name: "demo",
              config: { base_url: "https://demo.invalid", token: "****5678" },
              selected_project_ids: [],
              selected_board_ids: [],
              selected_repository_ids: [],
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
    fireEvent.change(screen.getByLabelText(/Base URL/), {
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

  it("loads Jira project and board choices and enables running the active sprint report", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.endsWith("/api/connectors")) {
        return Promise.resolve(jsonResponse([jiraConnector]))
      }
      if (url.endsWith("/api/connections") && (init?.method ?? "GET") === "GET") {
        return Promise.resolve(
          jsonResponse([
            {
              id: "connection-1",
              connector_name: "jira",
              config: { base_url: "https://jira.invalid", token: "****5678" },
              selected_project_ids: [],
              selected_board_ids: [],
              selected_repository_ids: [],
              created_at: "2026-06-01T10:00:00Z",
            },
          ]),
        )
      }
      if (url.endsWith("/api/connections/connection-1/projects")) {
        return Promise.resolve(
          jsonResponse([
            {
              id: "project-1",
              external_id: "10000",
              key: "PLAT",
              name: "Platform",
            },
          ]),
        )
      }
      if (url.endsWith("/api/connections/connection-1/projects/10000/boards")) {
        return Promise.resolve(
          jsonResponse([
            {
              id: "board-1",
              external_id: "20000",
              project_id: "project-1",
              name: "Platform Scrum",
              type: "scrum",
            },
          ]),
        )
      }
      if (url.endsWith("/api/connections/connection-1/boards/20000/sprints")) {
        return Promise.resolve(
          jsonResponse([
            {
              id: "sprint-1",
              external_id: "30000",
              board_id: "board-1",
              name: "Platform Sprint 12",
              state: "active",
              start_date: "2026-06-01T00:00:00Z",
              end_date: "2026-06-15T00:00:00Z",
              complete_date: null,
              goal: null,
            },
          ]),
        )
      }
      throw new Error(`unexpected fetch: ${init?.method ?? "GET"} ${url}`)
    })

    renderPage()

    expect(await screen.findByText("Platform Scrum")).toBeInTheDocument()
    expect(await screen.findByText("Scrum · 14 days")).toBeInTheDocument()
    expect(await screen.findByText("Active sprint: Platform Sprint 12")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Run report" })).toBeEnabled()
  })
})
