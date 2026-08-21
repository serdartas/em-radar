import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"

import { SetupPage } from "@/pages/SetupPage"
import { loadWizardProgress, saveWizardProgress } from "@/lib/wizardProgress"

const jiraConnector = {
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
    supports_incremental_fetch: false,
    supports_pagination_cursor: false,
    max_window_days: null,
  },
}

const groups = [
  {
    id: "group-default",
    name: "Default signals",
    description: null,
    signal_ids: [],
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
]

const projects = [{ id: "proj-1", external_id: "10001", key: "ALPHA", name: "Alpha Project" }]
const scrumBoards = [
  { id: "brd-1", external_id: "20001", project_id: "proj-1", name: "Alpha Scrum Board", type: "scrum" },
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

interface StoredConnection {
  id: string
  name: string
  connector_name: string
  config: Record<string, unknown>
  created_at: string
}

interface StoredTeam {
  id: string
  name: string
  description: null
  connection_ids: string[]
  scope_ids: string[]
  signal_config_group_ids: string[]
  code_connection_id: string | null
  working_mode: string
  sprint_length_days: number | null
  member_user_keys: string[]
  created_at: string
  updated_at: string
}

function storedTeam(id: string, name: string): StoredTeam {
  return {
    id,
    name,
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
}

function readOnlyMock(teams: StoredTeam[]) {
  return vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    const url = typeof input === "string" ? input : input.toString()
    const method = init?.method ?? "GET"
    if (url.endsWith("/api/connectors"))
      return Promise.resolve(jsonResponse([jiraConnector, gitlabConnector]))
    if (url.endsWith("/api/connections") && method === "GET") return Promise.resolve(jsonResponse([]))
    if (url.endsWith("/api/scopes") && method === "GET") return Promise.resolve(jsonResponse([]))
    if (url.endsWith("/api/signal-config-groups")) return Promise.resolve(jsonResponse(groups))
    if (url.endsWith("/api/teams") && method === "GET") return Promise.resolve(jsonResponse(teams))
    throw new Error(`unexpected fetch: ${method} ${url}`)
  })
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  })
}

function mockApi() {
  const connectionsStore: StoredConnection[] = []
  const teamsStore: StoredTeam[] = []
  const scopesStore: Array<Record<string, unknown>> = []
  let teamSeq = 0
  let scopeSeq = 0

  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    const url = typeof input === "string" ? input : input.toString()
    const method = init?.method ?? "GET"
    const body = init?.body ? JSON.parse(String(init.body)) : undefined

    if (url.endsWith("/api/connectors")) {
      return Promise.resolve(jsonResponse([jiraConnector, gitlabConnector]))
    }
    if (url.endsWith("/api/connections") && method === "GET") {
      return Promise.resolve(jsonResponse(connectionsStore))
    }
    if (url.endsWith("/api/connections") && method === "POST") {
      const created: StoredConnection = {
        id: `conn-${body.connector_name}`,
        name: body.name,
        connector_name: body.connector_name,
        config: body.config,
        created_at: "2026-01-01T00:00:00Z",
      }
      connectionsStore.push(created)
      return Promise.resolve(jsonResponse(created, 201))
    }
    if (url.endsWith("/api/connections/test") && method === "POST") {
      return Promise.resolve(
        jsonResponse({ ok: true, detail: "ok", user_display_name: "Ada", permissions: [] }),
      )
    }
    if (url.endsWith("/api/signal-config-groups")) {
      return Promise.resolve(jsonResponse(groups))
    }
    if (url.endsWith("/api/scopes") && method === "GET") {
      return Promise.resolve(jsonResponse(scopesStore))
    }
    if (url.endsWith("/api/scopes") && method === "POST") {
      const created = {
        id: `scope-${(scopeSeq += 1)}`,
        connection_id: body.connection_id,
        name: body.name,
        scope_type: body.scope_type,
        external_ref: body.external_ref,
        capabilities: body.capabilities,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      }
      scopesStore.push(created)
      return Promise.resolve(jsonResponse(created, 201))
    }
    if (url.endsWith("/api/teams") && method === "GET") {
      return Promise.resolve(jsonResponse(teamsStore))
    }
    if (url.endsWith("/api/teams") && method === "POST") {
      const created: StoredTeam = {
        id: `team-${(teamSeq += 1)}`,
        name: body.name,
        description: null,
        connection_ids: [],
        scope_ids: [],
        signal_config_group_ids: body.signal_config_group_ids ?? [],
        code_connection_id: null,
        working_mode: "scrum",
        sprint_length_days: 14,
        member_user_keys: [],
        created_at: "2026-01-01T00:00:00Z",
        updated_at: `2026-01-01T00:00:0${teamSeq}Z`,
      }
      teamsStore.push(created)
      return Promise.resolve(jsonResponse(created, 201))
    }
    const teamPatch = url.match(/\/api\/teams\/(team-\d+)$/)
    if (teamPatch && method === "PATCH") {
      const team = teamsStore.find((t) => t.id === teamPatch[1])
      if (team) {
        Object.assign(team, body)
        team.updated_at = `${team.updated_at}-u`
      }
      return Promise.resolve(jsonResponse(team))
    }
    if (url.match(/\/api\/connections\/[^/]+\/projects$/) && method === "GET") {
      return Promise.resolve(jsonResponse(projects))
    }
    if (url.match(/\/api\/connections\/[^/]+\/projects\/\d+\/boards$/) && method === "GET") {
      return Promise.resolve(jsonResponse(scrumBoards))
    }
    if (url.match(/\/api\/connections\/[^/]+\/boards\/\d+\/sprints$/) && method === "GET") {
      return Promise.resolve(jsonResponse(sprints))
    }
    if (url.endsWith("/api/reports/run") && method === "POST") {
      return Promise.resolve(jsonResponse({ id: "report-1", team_profile_id: body.team_profile_id }))
    }
    throw new Error(`unexpected fetch: ${method} ${url}`)
  })

  return { fetchMock, teamsStore, connectionsStore }
}

function renderWizard() {
  const queryClient = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/setup"]}>
        <Routes>
          <Route element={<SetupPage />} path="/setup" />
          <Route element={<h1>Dashboard landing</h1>} path="/" />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function findPatchBodies(fetchMock: ReturnType<typeof mockApi>["fetchMock"], id: string) {
  return fetchMock.mock.calls
    .filter(([url, init]) => String(url).endsWith(`/api/teams/${id}`) && init?.method === "PATCH")
    .map(([, init]) => JSON.parse(String((init as RequestInit).body)))
}

async function addConnection(baseUrl: string) {
  fireEvent.change(await screen.findByLabelText("Connection name"), {
    target: { value: baseUrl },
  })
  fireEvent.change(screen.getByLabelText(/^Base URL/), { target: { value: baseUrl } })
  fireEvent.change(screen.getByLabelText(/^Token/), { target: { value: "secret" } })
  fireEvent.click(screen.getByRole("button", { name: "Add connection" }))
}

async function attachBoardSource() {
  fireEvent.change(await screen.findByRole("combobox", { name: "Ticketing connection" }), {
    target: { value: "conn-jira" },
  })
  await screen.findByRole("option", { name: /Alpha Project/ })
  fireEvent.change(screen.getByRole("combobox", { name: "Project" }), {
    target: { value: "10001" },
  })
  await screen.findByRole("option", { name: /Alpha Scrum Board/ })
  fireEvent.change(screen.getByRole("combobox", { name: "Board" }), {
    target: { value: "20001" },
  })
  await screen.findByRole("combobox", { name: "Working mode" })
  fireEvent.click(screen.getByRole("button", { name: "Save board source" }))
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  localStorage.clear()
})

describe("SetupPage onboarding wizard", () => {
  it("walks welcome → connections → team → both sources → finish, persisting each step", async () => {
    const { fetchMock, teamsStore } = mockApi()
    renderWizard()

    // Step 1 — welcome
    fireEvent.click(await screen.findByRole("button", { name: "Get started" }))

    // Step 2 — named Jira connection persists
    expect(
      await screen.findByRole("heading", { name: /Connect your ticketing source/ }),
    ).toBeInTheDocument()
    await addConnection("Acme Jira")
    await screen.findByText("Acme Jira")
    const jiraPost = fetchMock.mock.calls.find(
      ([url, init]) => String(url).endsWith("/api/connections") && init?.method === "POST",
    )
    expect(JSON.parse(String((jiraPost?.[1] as RequestInit).body))).toMatchObject({
      name: "Acme Jira",
      connector_name: "jira",
    })
    fireEvent.click(screen.getByRole("button", { name: "Continue" }))

    // Step 3 — optional GitLab connection persists
    expect(
      await screen.findByRole("heading", { name: /Connect your code source/ }),
    ).toBeInTheDocument()
    await addConnection("Acme GitLab")
    await screen.findByText("Acme GitLab")
    fireEvent.click(screen.getByRole("button", { name: "Continue" }))

    // Step 4 — team created (with the default signal config group attached)
    fireEvent.change(await screen.findByLabelText("Team name"), { target: { value: "Payments" } })
    fireEvent.click(screen.getByRole("button", { name: "Create team" }))
    const teamPost = await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([url, init]) => String(url).endsWith("/api/teams") && init?.method === "POST",
      )
      expect(call).toBeTruthy()
      return call!
    })
    expect(JSON.parse(String((teamPost[1] as RequestInit).body))).toMatchObject({
      name: "Payments",
      signal_config_group_ids: ["group-default"],
    })

    // Step 5 — attach both sources
    await screen.findByRole("heading", { name: /Attach sources for Payments/ })
    await attachBoardSource()
    await waitFor(() => {
      expect(
        findPatchBodies(fetchMock, "team-1").some((b) => Array.isArray(b.scope_ids) && b.scope_ids.length > 0),
      ).toBe(true)
    })

    fireEvent.change(await screen.findByLabelText("Code source"), {
      target: { value: "conn-gitlab" },
    })
    await waitFor(() => {
      expect(
        findPatchBodies(fetchMock, "team-1").some((b) => b.code_connection_id === "conn-gitlab"),
      ).toBe(true)
    })

    // Finish → initial sync runs the team report, then lands on the dashboard.
    // findByRole waits until source saves settle and the button re-labels to "Finish setup".
    fireEvent.click(await screen.findByRole("button", { name: "Finish setup" }))
    await screen.findByRole("heading", { name: "Dashboard landing" })
    const runCall = fetchMock.mock.calls.find(
      ([url, init]) => String(url).endsWith("/api/reports/run") && init?.method === "POST",
    )
    expect(JSON.parse(String((runCall?.[1] as RequestInit).body))).toMatchObject({
      team_profile_id: "team-1",
    })
    expect(teamsStore).toHaveLength(1)
  })

  it("saves a team with no sources and loops to add a second team", async () => {
    const { fetchMock, teamsStore } = mockApi()
    renderWizard()

    fireEvent.click(await screen.findByRole("button", { name: "Get started" }))
    await addConnection("Acme Jira")
    await screen.findByText("Acme Jira")
    fireEvent.click(screen.getByRole("button", { name: "Continue" }))

    // Skip GitLab entirely — it is optional
    fireEvent.click(await screen.findByRole("button", { name: "Skip for now" }))

    // First team, saved with no sources
    fireEvent.change(await screen.findByLabelText("Team name"), { target: { value: "Payments" } })
    fireEvent.click(screen.getByRole("button", { name: "Create team" }))
    await screen.findByRole("heading", { name: /Attach sources for Payments/ })
    expect(teamsStore[0].scope_ids).toHaveLength(0)
    expect(teamsStore[0].code_connection_id).toBeNull()

    // Loop — add a second team without touching the first team's sources
    fireEvent.click(screen.getByRole("button", { name: "Add another team" }))
    fireEvent.change(await screen.findByLabelText("Team name"), { target: { value: "Search" } })
    fireEvent.click(screen.getByRole("button", { name: "Create team" }))
    await screen.findByRole("heading", { name: /Attach sources for Search/ })

    await waitFor(() => expect(teamsStore).toHaveLength(2))
    expect(teamsStore.map((t) => t.name)).toEqual(["Payments", "Search"])
    const teamPosts = fetchMock.mock.calls.filter(
      ([url, init]) => String(url).endsWith("/api/teams") && init?.method === "POST",
    )
    expect(teamPosts).toHaveLength(2)
  })

  it("resumes at the sources step when a team already exists (no persisted progress)", async () => {
    readOnlyMock([storedTeam("team-1", "Payments")])
    renderWizard()

    expect(
      await screen.findByRole("heading", { name: /Attach sources for Payments/ }),
    ).toBeInTheDocument()
    // The progress rail marks the Sources step as current.
    const rail = screen.getByRole("list", { name: "Setup progress" })
    expect(within(rail).getByText(/Sources/)).toHaveAttribute("aria-current", "step")
  })

  it("resumes at the persisted step/team rather than the source-presence heuristic", async () => {
    // Two source-less teams: the heuristic would pick the first, but persisted progress points
    // at the second — the wizard must honor where onboarding actually stopped.
    readOnlyMock([storedTeam("team-1", "Payments"), storedTeam("team-2", "Search")])
    saveWizardProgress({ step: "sources", currentTeamId: "team-2", furthestStep: "sources", completed: false })
    renderWizard()

    expect(
      await screen.findByRole("heading", { name: /Attach sources for Search/ }),
    ).toBeInTheDocument()
  })

  it("navigates to the dashboard when persisted progress is marked completed", async () => {
    readOnlyMock([storedTeam("team-1", "Payments")])
    saveWizardProgress({ step: "sources", currentTeamId: "team-1", furthestStep: "sources", completed: true })
    renderWizard()

    await screen.findByRole("heading", { name: "Dashboard landing" })
  })

  it("clears a stale completed marker and restarts onboarding when all teams are gone", async () => {
    // A completed marker with zero teams (all deleted) must not bounce between Dashboard and
    // Setup: the wizard drops the stale marker and falls back to the heuristic (welcome).
    readOnlyMock([])
    saveWizardProgress({ step: "sources", currentTeamId: "team-1", furthestStep: "sources", completed: true })
    renderWizard()

    expect(await screen.findByRole("heading", { name: "Welcome to EM Radar" })).toBeInTheDocument()
    expect(screen.queryByRole("heading", { name: "Dashboard landing" })).not.toBeInTheDocument()
    // The stale completed marker is dropped; onboarding restarts from a non-completed state.
    expect(loadWizardProgress()?.completed ?? false).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// M8.5-05: navigation — Back button, clickable step pills, WizardStepFooter
// ---------------------------------------------------------------------------

describe("SetupPage wizard navigation (M8.5-05)", () => {
  it("shows no Back button on the Welcome step", async () => {
    readOnlyMock([])
    renderWizard()

    await screen.findByRole("heading", { name: "Welcome to EM Radar" })
    expect(screen.queryByRole("button", { name: "Back" })).not.toBeInTheDocument()
  })

  it("shows a Back button on the Ticketing step and navigates back to Welcome", async () => {
    readOnlyMock([])
    saveWizardProgress({ step: "jira", currentTeamId: null, furthestStep: "jira", completed: false })
    renderWizard()

    await screen.findByRole("heading", { name: /Connect your ticketing source/ })
    const backBtn = screen.getByRole("button", { name: "Back" })
    expect(backBtn).toBeInTheDocument()
    fireEvent.click(backBtn)
    expect(await screen.findByRole("heading", { name: "Welcome to EM Radar" })).toBeInTheDocument()
  })

  it("shows a Back button on the Code step and navigates back to Ticketing", async () => {
    readOnlyMock([])
    saveWizardProgress({ step: "gitlab", currentTeamId: null, furthestStep: "gitlab", completed: false })
    renderWizard()

    await screen.findByRole("heading", { name: /Connect your code source/ })
    expect(screen.getByRole("button", { name: "Back" })).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Back" }))
    expect(await screen.findByRole("heading", { name: /Connect your ticketing source/ })).toBeInTheDocument()
  })

  it("shows a Back button on the Team step", async () => {
    readOnlyMock([])
    saveWizardProgress({ step: "team", currentTeamId: null, furthestStep: "team", completed: false })
    renderWizard()

    await screen.findByRole("heading", { name: "Create a team" })
    expect(screen.getByRole("button", { name: "Back" })).toBeInTheDocument()
  })

  it("shows a Back button on the Sources step", async () => {
    readOnlyMock([storedTeam("team-1", "Payments")])
    saveWizardProgress({ step: "sources", currentTeamId: "team-1", furthestStep: "sources", completed: false })
    renderWizard()

    await screen.findByRole("heading", { name: /Attach sources for Payments/ })
    expect(screen.getByRole("button", { name: "Back" })).toBeInTheDocument()
  })

  it("completed step pills are clickable and navigate back; future pills are non-interactive", async () => {
    readOnlyMock([])
    // furthestStep = "gitlab": Welcome and Ticketing are done, Team and Sources are locked.
    saveWizardProgress({ step: "gitlab", currentTeamId: null, furthestStep: "gitlab", completed: false })
    renderWizard()

    await screen.findByRole("heading", { name: /Connect your code source/ })

    const rail = screen.getByRole("list", { name: "Setup progress" })

    // Welcome and Ticketing pills: rendered as buttons (clickable, completed).
    const welcomeBtn = within(rail).getByRole("button", { name: /Welcome/ })
    const ticketingBtn = within(rail).getByRole("button", { name: /Ticketing/ })
    expect(welcomeBtn).toBeInTheDocument()
    expect(ticketingBtn).toBeInTheDocument()

    // Team and Sources pills: plain list items — no button role, not interactive.
    expect(within(rail).queryByRole("button", { name: /Team/ })).not.toBeInTheDocument()
    expect(within(rail).queryByRole("button", { name: /Sources/ })).not.toBeInTheDocument()

    // Clicking a completed pill navigates back to that step.
    fireEvent.click(welcomeBtn)
    expect(await screen.findByRole("heading", { name: "Welcome to EM Radar" })).toBeInTheDocument()
  })

  it("previously-entered pills stay clickable after back-navigation (high-water mark respected)", async () => {
    readOnlyMock([])
    // furthestStep = "team" (was reached), but current = "jira" (user went back).
    // Jira, GitLab, and Team pills were all previously entered and should remain as buttons.
    saveWizardProgress({ step: "jira", currentTeamId: null, furthestStep: "team", completed: false })
    renderWizard()

    await screen.findByRole("heading", { name: /Connect your ticketing source/ })

    const rail = screen.getByRole("list", { name: "Setup progress" })

    // Welcome is done (index 0 <= furthestIndex 3, not current).
    expect(within(rail).getByRole("button", { name: /Welcome/ })).toBeInTheDocument()
    // GitLab is done (index 2 <= 3, not current) — was previously entered.
    expect(within(rail).getByRole("button", { name: /Code/ })).toBeInTheDocument()
    // Team is done (index 3 <= 3, not current) — was previously entered.
    expect(within(rail).getByRole("button", { name: /Team/ })).toBeInTheDocument()
    // Sources is locked (index 4 > furthestIndex 3).
    expect(within(rail).queryByRole("button", { name: /Sources/ })).not.toBeInTheDocument()
  })

  it("persisted furthestStep round-trips: completed pills stay clickable after remount", async () => {
    // Simulate: wizard was at gitlab with furthestStep = "gitlab", then browser is closed and
    // reopened. The remount must read furthestStep from storage so Ticketing pill is still a button.
    readOnlyMock([])
    saveWizardProgress({ step: "gitlab", currentTeamId: null, furthestStep: "gitlab", completed: false })

    // First mount
    const { unmount } = renderWizard()
    await screen.findByRole("heading", { name: /Connect your code source/ })
    unmount()
    cleanup()

    // Remount — simulates browser reload
    renderWizard()
    await screen.findByRole("heading", { name: /Connect your code source/ })

    const rail = screen.getByRole("list", { name: "Setup progress" })
    // Ticketing pill must still be a button (from the persisted furthestStep).
    expect(within(rail).getByRole("button", { name: /Ticketing/ })).toBeInTheDocument()
    // Team pill must still be non-interactive (not yet reached).
    expect(within(rail).queryByRole("button", { name: /Team/ })).not.toBeInTheDocument()
  })

  it("the step footer exposes exactly one primary action", async () => {
    readOnlyMock([])
    saveWizardProgress({ step: "gitlab", currentTeamId: null, furthestStep: "gitlab", completed: false })
    renderWizard()

    await screen.findByRole("heading", { name: /Connect your code source/ })

    // "Skip for now" is the sole primary action for an optional step with no connections.
    // queryAllByRole asserting length 1 verifies uniqueness, not just presence.
    expect(screen.queryAllByRole("button", { name: "Skip for now" })).toHaveLength(1)
    expect(screen.getByRole("button", { name: "Skip for now" })).not.toBeDisabled()
  })
})
