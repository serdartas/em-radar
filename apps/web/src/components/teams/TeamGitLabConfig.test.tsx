// SPDX-License-Identifier: Apache-2.0
//
// M9-07: GitLab gating — these tests must FAIL before the feature is implemented and
// PASS after. They use the same fetch-mock pattern as TeamsPage.test.tsx.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"

import { TeamsPage } from "@/pages/TeamsPage"

// ---------------------------------------------------------------------------
// Shared fixtures
// ---------------------------------------------------------------------------

const baseTeam = {
  id: "team-1",
  name: "Platform",
  description: null as string | null,
  connection_ids: [] as string[],
  scope_ids: [] as string[],
  signal_config_group_ids: [] as string[],
  code_connection_id: null as string | null,
  working_mode: "scrum" as const,
  sprint_length_days: 14,
  member_user_keys: [] as string[],
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
}

// Team that already has a GitLab code connection set.
const teamWithCodeConnection = {
  ...baseTeam,
  code_connection_id: "conn-gitlab",
}

const jiraConnection = {
  id: "conn-jira",
  name: "Acme Jira",
  connector_name: "jira",
  config: {},
  created_at: "2026-01-01T00:00:00Z",
}

const gitlabConnection = {
  id: "conn-gitlab",
  name: "GitLab Cloud",
  connector_name: "gitlab",
  config: {},
  created_at: "2026-01-01T00:00:00Z",
}

// A connector that supplies merge-request data (e.g. GitLab).
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

// A ticketing-only connector — no merge-request data.
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

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  })
}

type MockOptions = {
  team?: typeof baseTeam
  connectors?: unknown[]
  connections?: unknown[]
}

function mockApi(options: MockOptions = {}) {
  const teamFixture = options.team ?? baseTeam
  const connectorsList = options.connectors ?? []
  const connectionsList = options.connections ?? [jiraConnection]

  return vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    const url = typeof input === "string" ? input : input.toString()
    const method = init?.method ?? "GET"

    if (url.endsWith("/api/teams") && method === "GET") {
      return Promise.resolve(jsonResponse([teamFixture]))
    }
    if (url.endsWith("/api/teams") && method === "POST") {
      return Promise.resolve(
        jsonResponse({ ...baseTeam, id: "team-new", name: "New Team" }, 201),
      )
    }
    if (url.includes("/api/teams/") && method === "PATCH") {
      const body = JSON.parse(String(init?.body))
      return Promise.resolve(jsonResponse({ ...teamFixture, ...body }))
    }
    if (url.endsWith("/api/scopes") && method === "GET") {
      return Promise.resolve(jsonResponse([]))
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

// ---------------------------------------------------------------------------
// M9-07 §3: no GitLab connector → no GitLab sections
// ---------------------------------------------------------------------------
describe("M9-07: no GitLab connector present", () => {
  it("renders no GitLab member or repository sections in the edit panel", async () => {
    // No MR-capable connector/connection in the system.
    mockApi({ connectors: [ticketingConnector], connections: [jiraConnection] })
    renderPage()

    await screen.findByText("Platform")
    fireEvent.click(screen.getByRole("button", { name: "Edit Platform" }))

    // GitLab config headings must be completely absent.
    expect(screen.queryByRole("heading", { name: "GitLab members" })).toBeNull()
    expect(screen.queryByRole("heading", { name: "GitLab repositories" })).toBeNull()
    expect(screen.queryByRole("heading", { name: "GitLab configuration" })).toBeNull()
  })

  it("hides GitLab sections when the team's code_connection_id is stale (no MR-capable connector)", async () => {
    // Team still references a code connection, but no MR-capable connector exists anymore
    // (e.g. the GitLab connector was removed). The §3 gate must hide the sections regardless
    // of the stale code_connection_id.
    mockApi({
      team: teamWithCodeConnection,
      connectors: [ticketingConnector],
      connections: [jiraConnection, gitlabConnection],
    })
    renderPage()

    await screen.findByText("Platform")
    fireEvent.click(screen.getByRole("button", { name: "Edit Platform" }))

    // Wait for the edit panel to open (Done button present), then assert no GitLab sections.
    await screen.findByRole("button", { name: "Done editing Platform" })
    expect(screen.queryByRole("heading", { name: "GitLab members" })).toBeNull()
    expect(screen.queryByRole("heading", { name: "GitLab repositories" })).toBeNull()
  })

  it("allows team creation with name only when no GitLab connector exists", async () => {
    const fetchMock = mockApi({ connectors: [], connections: [] })
    renderPage()

    const input = await screen.findByLabelText("New team name")
    fireEvent.change(input, { target: { value: "Backend" } })

    const createBtn = screen.getByRole("button", { name: "Create team" })
    expect(createBtn).not.toBeDisabled()
    fireEvent.click(createBtn)

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([url, init]) => String(url).endsWith("/api/teams") && init?.method === "POST",
      )
      expect(call).toBeTruthy()
      const body = JSON.parse(String((call?.[1] as RequestInit).body))
      expect(body.name).toBe("Backend")
    })
  })
})

// ---------------------------------------------------------------------------
// M9-07 §4, §25.10: GitLab connector present → optional sections visible and skippable
// ---------------------------------------------------------------------------
describe("M9-07: GitLab connector present", () => {
  it("shows GitLab members and repositories sections in the edit panel when team has code_connection_id", async () => {
    // Team already has a code connection set; mrConnector + gitlabConnection in the system.
    mockApi({
      team: teamWithCodeConnection,
      connectors: [mrConnector],
      connections: [jiraConnection, gitlabConnection],
    })
    renderPage()

    await screen.findByText("Platform")
    fireEvent.click(screen.getByRole("button", { name: "Edit Platform" }))

    // Both optional sections must be present.
    expect(await screen.findByRole("heading", { name: "GitLab members" })).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "GitLab repositories" })).toBeInTheDocument()
  })

  it("does NOT show GitLab configuration when connector exists but team has no code_connection_id", async () => {
    // Connector is present but team has not yet selected a code connection.
    mockApi({
      team: baseTeam, // code_connection_id: null
      connectors: [mrConnector],
      connections: [jiraConnection, gitlabConnection],
    })
    renderPage()

    await screen.findByText("Platform")
    fireEvent.click(screen.getByRole("button", { name: "Edit Platform" }))

    // Sections must not appear until code_connection_id is set.
    await screen.findByLabelText("Code source")
    expect(screen.queryByRole("heading", { name: "GitLab members" })).toBeNull()
    expect(screen.queryByRole("heading", { name: "GitLab repositories" })).toBeNull()
  })

  it("can close the edit panel without filling GitLab sections (skippable)", async () => {
    mockApi({
      team: teamWithCodeConnection,
      connectors: [mrConnector],
      connections: [jiraConnection, gitlabConnection],
    })
    renderPage()

    await screen.findByText("Platform")
    fireEvent.click(screen.getByRole("button", { name: "Edit Platform" }))

    // GitLab sections are visible.
    expect(await screen.findByRole("heading", { name: "GitLab members" })).toBeInTheDocument()

    // Clicking Done without touching any GitLab field closes the panel normally.
    fireEvent.click(screen.getByRole("button", { name: "Done editing Platform" }))

    await waitFor(() => {
      expect(screen.queryByRole("heading", { name: "GitLab members" })).toBeNull()
    })
    // Edit button is back — panel successfully collapsed.
    expect(screen.getByRole("button", { name: "Edit Platform" })).toBeInTheDocument()
  })
})
