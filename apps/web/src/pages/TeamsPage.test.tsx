import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"

import { TeamsPage } from "@/pages/TeamsPage"

const team = {
  id: "team-1",
  name: "Platform",
  description: null,
  connection_ids: ["conn-1"],
  scope_ids: [],
  project_ids: [],
  board_ids: [],
  repository_ids: [],
  signal_config_group_ids: [],
  working_mode: "scrum",
  sprint_length_days: 14,
  member_user_keys: [],
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
}

const scopes = [
  {
    id: "board-1",
    connection_id: "conn-1",
    name: "Platform Scrum",
    scope_type: "board",
    external_ref: { id: "20000" },
    capabilities: ["sprint", "statuses"],
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
]

const groups = [
  {
    id: "group-1",
    name: "Backend signals",
    description: null,
    signal_ids: [],
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
]

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  })
}

function mockApi() {
  return vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    const url = typeof input === "string" ? input : input.toString()
    const method = init?.method ?? "GET"
    if (url.endsWith("/api/teams") && method === "GET") {
      return Promise.resolve(jsonResponse([team]))
    }
    if (url.endsWith("/api/scopes")) {
      return Promise.resolve(jsonResponse(scopes))
    }
    if (url.endsWith("/api/signal-config-groups")) {
      return Promise.resolve(jsonResponse(groups))
    }
    if (url.includes("/api/teams/") && method === "PATCH") {
      const body = JSON.parse(String(init?.body))
      return Promise.resolve(jsonResponse({ ...team, ...body }))
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
        <TeamsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("TeamsPage", () => {
  it("attaches a signal config group to a team", async () => {
    const fetchMock = mockApi()
    renderPage()

    fireEvent.click(await screen.findByRole("button", { name: "Attach" }))

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([url, init]) => String(url).includes("/api/teams/") && init?.method === "PATCH",
      )
      expect(call).toBeTruthy()
      const body = JSON.parse(String((call?.[1] as RequestInit).body))
      expect(body.signal_config_group_ids).toEqual(["group-1"])
    })
  })

  it("sets the team's board scope and its connection", async () => {
    const fetchMock = mockApi()
    renderPage()

    fireEvent.change(await screen.findByLabelText("Jira board scope"), {
      target: { value: "board-1" },
    })

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([url, init]) => String(url).includes("/api/teams/") && init?.method === "PATCH",
      )
      expect(call).toBeTruthy()
      const body = JSON.parse(String((call?.[1] as RequestInit).body))
      expect(body.scope_ids).toEqual(["board-1"])
      expect(body.connection_ids).toEqual(["conn-1"])
    })
  })
})
