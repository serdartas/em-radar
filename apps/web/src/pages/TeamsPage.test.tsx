import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"

import { TeamsPage } from "@/pages/TeamsPage"

const team = {
  id: "team-1",
  name: "Platform",
  description: null,
  connection_ids: [],
  scope_ids: [],
  signal_config_group_ids: [],
  code_connection_id: null,
  working_mode: "scrum",
  sprint_length_days: 14,
  member_user_keys: [],
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
}

const connections = [
  {
    id: "conn-1",
    name: "Acme Jira",
    connector_name: "jira",
    config: {},
    created_at: "2026-01-01T00:00:00Z",
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

const projects = [
  { id: "proj-1", external_id: "10001", key: "ALPHA", name: "Alpha Project" },
  { id: "proj-2", external_id: "10002", key: "BETA", name: "Beta Project" },
]

const scrumBoards = [
  {
    id: "brd-1",
    external_id: "20001",
    project_id: "proj-1",
    name: "Alpha Scrum Board",
    type: "scrum",
  },
]

const kanbanBoards = [
  {
    id: "brd-2",
    external_id: "20002",
    project_id: "proj-1",
    name: "Alpha Kanban Board",
    type: "kanban",
  },
]

const sprints = [
  {
    id: "sp-1",
    external_id: "30001",
    board_id: "brd-1",
    name: "Sprint 1",
    state: "closed",
    start_date: "2026-01-01T00:00:00Z",
    end_date: "2026-01-15T00:00:00Z",
    complete_date: "2026-01-15T00:00:00Z",
    goal: null,
  },
]

const createdScope = {
  id: "scope-new-1",
  connection_id: "conn-1",
  name: "ALPHA / Alpha Scrum Board",
  scope_type: "board",
  external_ref: { id: "20001", key: "ALPHA", name: "Alpha Scrum Board" },
  capabilities: ["sprint", "statuses"],
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
}

// A connector that can supply merge-request data (e.g. GitLab).
const mrConnector = {
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
    supports_incremental_fetch: false,
    supports_pagination_cursor: false,
    max_window_days: null,
  },
}

// A ticketing-only connector (e.g. Jira) — cannot supply merge-request data.
const ticketingConnector = {
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
    supports_incremental_fetch: false,
    supports_pagination_cursor: false,
    max_window_days: null,
  },
}

const gitlabConnection = {
  id: "conn-gitlab",
  name: "GitLab Cloud",
  connector_name: "gitlab",
  config: {},
  created_at: "2026-01-01T00:00:00Z",
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  })
}

type MockOptions = {
  boards?: typeof scrumBoards | typeof kanbanBoards | Array<(typeof scrumBoards)[0] | (typeof kanbanBoards)[0]>
  sprintsResponse?: typeof sprints | Promise<Response>
  scopePostResponse?: Response
  connectors?: unknown[]
  connections?: unknown[]
}

function mockApi(options: MockOptions = {}) {
  const boards = options.boards ?? scrumBoards
  const scopePostResponse = options.scopePostResponse ?? jsonResponse(createdScope, 201)
  const connectorsList = options.connectors ?? []
  const connectionsList = options.connections ?? connections

  return vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    const url = typeof input === "string" ? input : input.toString()
    const method = init?.method ?? "GET"

    if (url.endsWith("/api/teams") && method === "GET") {
      return Promise.resolve(jsonResponse([team]))
    }
    if (url.endsWith("/api/scopes") && method === "GET") {
      return Promise.resolve(jsonResponse([]))
    }
    if (url.endsWith("/api/scopes") && method === "POST") {
      return Promise.resolve(scopePostResponse)
    }
    if (url.endsWith("/api/signal-config-groups")) {
      return Promise.resolve(jsonResponse(groups))
    }
    if (url.endsWith("/api/connectors")) {
      return Promise.resolve(jsonResponse(connectorsList))
    }
    if (url.endsWith("/api/connections") && method === "GET") {
      return Promise.resolve(jsonResponse(connectionsList))
    }
    if (url.match(/\/api\/connections\/conn-1\/projects$/) && method === "GET") {
      return Promise.resolve(jsonResponse(projects))
    }
    if (url.match(/\/api\/connections\/conn-1\/projects\/\d+\/boards$/) && method === "GET") {
      return Promise.resolve(jsonResponse(boards))
    }
    if (url.match(/\/api\/connections\/conn-1\/boards\/\d+\/sprints$/) && method === "GET") {
      const sr = options.sprintsResponse ?? sprints
      return sr instanceof Promise ? sr : Promise.resolve(jsonResponse(sr))
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

/** Drives the picker to the board selection step via the new Combobox interaction. */
async function selectUpToBoard(boards: typeof scrumBoards) {
  const connSelect = await screen.findByRole("combobox", { name: "Ticketing connection" })
  fireEvent.change(connSelect, { target: { value: "conn-1" } })

  const projectCombobox = await screen.findByRole("combobox", { name: "Project" })
  fireEvent.focus(projectCombobox)
  await screen.findByRole("option", { name: /Alpha Project/ })
  fireEvent.mouseDown(screen.getByRole("option", { name: /Alpha Project/ }))

  const boardCombobox = await screen.findByRole("combobox", { name: "Board" })
  fireEvent.focus(boardCombobox)
  await screen.findByRole("option", { name: new RegExp(boards[0].name) })
  fireEvent.mouseDown(screen.getByRole("option", { name: new RegExp(boards[0].name) }))
  return boardCombobox
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("TeamsPage — signal config group", () => {
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
})

describe("TeamsPage — task-board source picker", () => {
  it("filters the project list as the user types", async () => {
    mockApi()
    renderPage()

    const connSelect = await screen.findByRole("combobox", { name: "Ticketing connection" })
    fireEvent.change(connSelect, { target: { value: "conn-1" } })

    const projectCombobox = await screen.findByRole("combobox", { name: "Project" })
    fireEvent.focus(projectCombobox)
    await screen.findByRole("option", { name: /Alpha Project/ })
    await screen.findByRole("option", { name: /Beta Project/ })

    fireEvent.change(projectCombobox, { target: { value: "beta" } })

    expect(screen.queryByRole("option", { name: /Alpha Project/ })).toBeNull()
    expect(screen.getByRole("option", { name: /Beta Project/ })).toBeInTheDocument()
  })

  it("filters the board list as the user types", async () => {
    mockApi({ boards: [...scrumBoards, ...kanbanBoards] })
    renderPage()

    const connSelect = await screen.findByRole("combobox", { name: "Ticketing connection" })
    fireEvent.change(connSelect, { target: { value: "conn-1" } })

    const projectCombobox = await screen.findByRole("combobox", { name: "Project" })
    fireEvent.focus(projectCombobox)
    await screen.findByRole("option", { name: /Alpha Project/ })
    fireEvent.mouseDown(screen.getByRole("option", { name: /Alpha Project/ }))

    const boardCombobox = await screen.findByRole("combobox", { name: "Board" })
    fireEvent.focus(boardCombobox)
    await screen.findByRole("option", { name: /Alpha Scrum Board/ })
    await screen.findByRole("option", { name: /Alpha Kanban Board/ })

    fireEvent.change(boardCombobox, { target: { value: "kanban" } })

    expect(screen.queryByRole("option", { name: /Alpha Scrum Board/ })).toBeNull()
    expect(screen.getByRole("option", { name: /Alpha Kanban Board/ })).toBeInTheDocument()
  })

  it("selecting a scrum board persists board scope and detected working mode", async () => {
    const fetchMock = mockApi()
    renderPage()

    await selectUpToBoard(scrumBoards)
    await screen.findByRole("combobox", { name: "Working mode" })

    fireEvent.click(screen.getByRole("button", { name: "Save board source" }))

    await waitFor(() => {
      const scopeCall = fetchMock.mock.calls.find(
        ([url, init]) => String(url).endsWith("/api/scopes") && init?.method === "POST",
      )
      expect(scopeCall).toBeTruthy()
      const scopeBody = JSON.parse(String((scopeCall?.[1] as RequestInit).body))
      expect(scopeBody.external_ref).toMatchObject({ id: "20001" })
      expect(scopeBody.scope_type).toBe("board")
    })

    await waitFor(() => {
      const teamCall = fetchMock.mock.calls.find(
        ([url, init]) => String(url).includes("/api/teams/") && init?.method === "PATCH",
      )
      expect(teamCall).toBeTruthy()
      const body = JSON.parse(String((teamCall?.[1] as RequestInit).body))
      expect(body.scope_ids).toEqual(["scope-new-1"])
      expect(body.connection_ids).toEqual(["conn-1"])
      expect(body.working_mode).toBe("scrum")
      // sprint_length_days must be present and positive — would fail if mode were ignored
      expect(body.sprint_length_days).toBeGreaterThan(0)
    })
  })

  it("selecting a Kanban board persists working_mode=kanban and sprint_length_days=null", async () => {
    const fetchMock = mockApi({ boards: kanbanBoards, sprintsResponse: [] })
    renderPage()

    await selectUpToBoard(kanbanBoards)
    await screen.findByRole("combobox", { name: "Working mode" })

    fireEvent.click(screen.getByRole("button", { name: "Save board source" }))

    await waitFor(() => {
      const teamCall = fetchMock.mock.calls.find(
        ([url, init]) => String(url).includes("/api/teams/") && init?.method === "PATCH",
      )
      expect(teamCall).toBeTruthy()
      const body = JSON.parse(String((teamCall?.[1] as RequestInit).body))
      // Must be kanban — NOT the default scrum
      expect(body.working_mode).toBe("kanban")
      expect(body.sprint_length_days).toBeNull()
    })
  })

  it("can be left unset — Save is disabled with no board selected", async () => {
    mockApi()
    renderPage()

    await screen.findByText("Platform")
    await screen.findByRole("combobox", { name: "Ticketing connection" })

    expect(screen.getByRole("button", { name: "Save board source" })).toBeDisabled()
  })

  it("shows an error when POST /scopes fails and does not call updateTeam", async () => {
    const fetchMock = mockApi({
      scopePostResponse: jsonResponse({ detail: "scope creation failed" }, 422),
    })
    renderPage()

    await selectUpToBoard(scrumBoards)
    await screen.findByRole("combobox", { name: "Working mode" })

    fireEvent.click(screen.getByRole("button", { name: "Save board source" }))

    // Error message must appear near the Save button
    await screen.findByRole("alert")
    expect(screen.getByRole("alert")).toHaveTextContent("scope creation failed")

    // updateTeam must NOT have been called
    const teamCall = fetchMock.mock.calls.find(
      ([url, init]) => String(url).includes("/api/teams/") && init?.method === "PATCH",
    )
    expect(teamCall).toBeUndefined()
  })

  it("preserves manual mode override when sprint data arrives after user changes mode", async () => {
    let resolveSprintsRequest!: (v: Response) => void
    const sprintsDeferred = new Promise<Response>((resolve) => {
      resolveSprintsRequest = resolve
    })

    const fetchMock = mockApi({ sprintsResponse: sprintsDeferred })
    renderPage()

    // Drive to board selection — sprints are pending (deferred)
    await selectUpToBoard(scrumBoards)

    // Working mode section appears from board.type detection before sprints load
    const modeSelect = await screen.findByRole("combobox", { name: "Working mode" })
    expect(modeSelect).toHaveValue("scrum")

    // User manually overrides to kanban
    fireEvent.change(modeSelect, { target: { value: "kanban" } })
    expect(modeSelect).toHaveValue("kanban")

    // Now let sprints resolve — this must NOT clobber the user's override
    resolveSprintsRequest(jsonResponse(sprints))

    await waitFor(() => {
      expect(screen.getByRole("combobox", { name: "Working mode" })).toHaveValue("kanban")
    })

    // Save must persist the user's kanban override, not the detected scrum
    fireEvent.click(screen.getByRole("button", { name: "Save board source" }))

    await waitFor(() => {
      const teamCall = fetchMock.mock.calls.find(
        ([url, init]) => String(url).includes("/api/teams/") && init?.method === "PATCH",
      )
      expect(teamCall).toBeTruthy()
      const body = JSON.parse(String((teamCall?.[1] as RequestInit).body))
      expect(body.working_mode).toBe("kanban")
      expect(body.sprint_length_days).toBeNull()
    })
  })

  it("disables Save when scrum sprint length is cleared", async () => {
    mockApi()
    renderPage()

    await selectUpToBoard(scrumBoards)

    // Wait until sprint data has been applied to the field (14 days from mock sprint data).
    // This ensures no pending detection effect can override the clear that follows.
    await waitFor(() => {
      expect(screen.getByLabelText("Sprint length (days)")).toHaveValue(14)
    })

    // Clear the sprint length input — Number("") = 0, which is invalid.
    fireEvent.change(screen.getByLabelText("Sprint length (days)"), { target: { value: "" } })

    // userOverrodeModeRef is now true, so detection cannot reset the value back to 14.
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Save board source" })).toBeDisabled()
    })
  })

  it("shows an empty-state message when no MR-capable connections exist", async () => {
    mockApi({ connectors: [ticketingConnector], connections: [] })
    renderPage()

    expect(
      await screen.findByText(/no code connections available/i),
    ).toBeInTheDocument()
  })

  it("attaches a code connection", async () => {
    const fetchMock = mockApi({
      connectors: [mrConnector],
      connections: [gitlabConnection],
    })
    renderPage()

    fireEvent.change(await screen.findByLabelText("Code source"), {
      target: { value: "conn-gitlab" },
    })

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([url, init]) => String(url).includes("/api/teams/") && init?.method === "PATCH",
      )
      expect(call).toBeTruthy()
      const body = JSON.parse(String((call?.[1] as RequestInit).body))
      expect(body.code_connection_id).toEqual("conn-gitlab")
    })
  })

  it("detaches a code connection by selecting the empty option", async () => {
    const teamWithCode = { ...team, code_connection_id: "conn-gitlab" }
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = typeof input === "string" ? input : input.toString()
      const method = init?.method ?? "GET"
      if (url.endsWith("/api/teams") && method === "GET") {
        return Promise.resolve(jsonResponse([teamWithCode]))
      }
      if (url.endsWith("/api/scopes")) return Promise.resolve(jsonResponse([]))
      if (url.endsWith("/api/signal-config-groups")) return Promise.resolve(jsonResponse(groups))
      if (url.endsWith("/api/connectors")) return Promise.resolve(jsonResponse([mrConnector]))
      if (url.endsWith("/api/connections") && method === "GET") {
        return Promise.resolve(jsonResponse([gitlabConnection]))
      }
      if (url.includes("/api/teams/") && method === "PATCH") {
        const body = JSON.parse(String(init?.body))
        return Promise.resolve(jsonResponse({ ...teamWithCode, ...body }))
      }
      throw new Error(`unexpected fetch: ${method} ${url}`)
    })

    renderPage()

    fireEvent.change(await screen.findByLabelText("Code source"), {
      target: { value: "" },
    })

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([url, init]) => String(url).includes("/api/teams/") && init?.method === "PATCH",
      )
      expect(call).toBeTruthy()
      const body = JSON.parse(String((call?.[1] as RequestInit).body))
      expect(body.code_connection_id).toBeNull()
    })
  })
})
