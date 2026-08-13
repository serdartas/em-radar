import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"

import { DashboardPage } from "@/pages/DashboardPage"

const platformTeam = {
  id: "team-1",
  name: "Platform",
  description: null,
  connection_ids: ["conn-1"],
  scope_ids: ["board-1"],
  project_ids: [],
  board_ids: [],
  repository_ids: [],
  signal_config_group_ids: ["group-1"],
  code_connection_id: null,
  working_mode: "scrum",
  sprint_length_days: 14,
  member_user_keys: [],
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
}

const growthTeam = {
  ...platformTeam,
  id: "team-2",
  name: "Growth",
  working_mode: "kanban",
  scope_ids: ["board-2"],
}

const noSourceTeam = {
  ...platformTeam,
  id: "team-3",
  name: "Solo",
  scope_ids: [],
  code_connection_id: null,
}

const platformSummaryOld = {
  id: "report-0",
  evaluation_window_id: "window-0",
  team_profile_id: "team-1",
  team_name: "Platform",
  status: "succeeded",
  started_at: "2026-05-01T10:00:00",
  finished_at: "2026-05-01T10:00:05",
  error: null,
  findings_count_by_severity: { info: 9, warning: 9, critical: 9 },
}

const platformSummary = {
  id: "report-1",
  evaluation_window_id: "window-1",
  team_profile_id: "team-1",
  team_name: "Platform",
  status: "succeeded",
  started_at: "2026-06-01T10:00:00",
  finished_at: "2026-06-01T10:00:05",
  error: null,
  findings_count_by_severity: { info: 0, warning: 1, critical: 1 },
}

const growthSummary = {
  id: "report-2",
  evaluation_window_id: "window-2",
  team_profile_id: "team-2",
  team_name: "Growth",
  status: "succeeded",
  started_at: "2026-06-02T09:00:00",
  finished_at: "2026-06-02T09:00:04",
  error: null,
  findings_count_by_severity: { info: 2, warning: 0, critical: 0 },
}

function detail(summary: typeof platformSummary, findings: unknown[]) {
  return {
    ...summary,
    signal_pack_snapshot: {},
    summary: { counts_by_severity: summary.findings_count_by_severity, total: findings.length },
    skip_notes: [],
    sections: [
      { section: "summary", title: "Summary", finding_ids: [] },
      {
        section: "top_risks",
        title: "Top Risks",
        finding_ids: findings.map((f) => (f as { id: string }).id),
      },
    ],
    findings,
  }
}

const platformDetail = detail(platformSummary, [
  {
    id: "f-crit",
    signal_id: "blocked-work-item",
    signal_name: "Blocked work item",
    severity: "critical",
    confidence: "high",
    entity_type: "workitem",
    entity_id: "e1",
    title: "PLAT-3 blocked for a week",
    reason: "r",
    recommendation: null,
    evidence: {},
    source_link: null,
  },
  {
    id: "f-warn",
    signal_id: "stale-in-progress-work-item",
    signal_name: "Stale in-progress work item",
    severity: "warning",
    confidence: "high",
    entity_type: "workitem",
    entity_id: "e2",
    title: "PLAT-2 stale for 12 days",
    reason: "r",
    recommendation: null,
    evidence: {},
    source_link: null,
  },
])

const growthDetail = detail(growthSummary, [
  {
    id: "g-info",
    signal_id: "unlinked-merge-request",
    signal_name: "Unlinked merge request",
    severity: "info",
    confidence: "medium",
    entity_type: "mergerequest",
    entity_id: "e3",
    title: "MR !42 has no linked work item",
    reason: "r",
    recommendation: null,
    evidence: {},
    source_link: null,
  },
])

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  })
}

function mockApi(options?: { teams?: unknown[]; reports?: unknown[] }) {
  const teams = options?.teams ?? [platformTeam, growthTeam]
  const reports = options?.reports ?? [platformSummaryOld, platformSummary, growthSummary]
  return vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    const url = typeof input === "string" ? input : input.toString()
    if (url.endsWith("/api/teams")) {
      return Promise.resolve(jsonResponse(teams))
    }
    if (url.endsWith("/api/reports") && init?.method !== "POST") {
      return Promise.resolve(jsonResponse(reports))
    }
    if (url.endsWith("/api/reports/report-1")) {
      return Promise.resolve(jsonResponse(platformDetail))
    }
    if (url.endsWith("/api/reports/report-2")) {
      return Promise.resolve(jsonResponse(growthDetail))
    }
    if (url.endsWith("/api/reports/run")) {
      return Promise.resolve(jsonResponse(platformDetail))
    }
    throw new Error(`unexpected fetch: ${url} ${init?.method ?? "GET"}`)
  })
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route element={<DashboardPage />} path="/" />
          <Route element={<div>Setup wizard</div>} path="/setup" />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function cardFor(teamName: string): HTMLElement {
  return screen.getByRole("heading", { level: 2, name: teamName }).closest("article") as HTMLElement
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("DashboardPage", () => {
  it("renders one card per team with the latest report counts and top risks", async () => {
    mockApi()
    renderPage()

    await screen.findByText("PLAT-3 blocked for a week")

    const platform = within(cardFor("Platform"))
    expect(platform.getByText("scrum")).toBeInTheDocument()
    expect(platform.getByText("1 critical")).toBeInTheDocument()
    expect(platform.getByText("1 warning")).toBeInTheDocument()
    expect(platform.getByText("0 info")).toBeInTheDocument()
    expect(platform.getByText("PLAT-3 blocked for a week")).toBeInTheDocument()
    expect(platform.getByText("PLAT-2 stale for 12 days")).toBeInTheDocument()
    // The older report for this team must not win the "latest" selection.
    expect(platform.queryByText("9 critical")).toBeNull()

    const growth = within(cardFor("Growth"))
    expect(growth.getByText("kanban")).toBeInTheDocument()
    expect(growth.getByText("2 info")).toBeInTheDocument()
    expect(growth.getByText("MR !42 has no linked work item")).toBeInTheDocument()
  })

  it("wires the Refresh action to runTeamReport with the team id", async () => {
    const fetchMock = mockApi()
    renderPage()

    await screen.findByText("PLAT-3 blocked for a week")
    fireEvent.click(within(cardFor("Platform")).getByRole("button", { name: "Refresh" }))

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(
          ([url, requestInit]) =>
            String(url).endsWith("/api/reports/run") &&
            requestInit?.method === "POST" &&
            String(requestInit?.body) ===
              JSON.stringify({ connector: "jira", team_profile_id: "team-1" }),
        ),
      ).toBe(true)
    })
  })

  it("links Open report to the sectioned results view", async () => {
    mockApi()
    renderPage()

    await screen.findByText("PLAT-3 blocked for a week")
    const openLink = within(cardFor("Platform")).getByRole("link", { name: "Open report" })
    expect(openLink).toHaveAttribute("href", "/reports/results/report-1")
  })

  it("shows an empty state and keeps Refresh enabled when a team has no report", async () => {
    mockApi({ teams: [platformTeam], reports: [] })
    renderPage()

    const card = within(await screen.findByRole("article"))
    expect(card.getByText("No report yet.")).toBeInTheDocument()
    expect(card.getByRole("button", { name: "Refresh" })).not.toBeDisabled()
    expect(card.queryByRole("link", { name: "Open report" })).toBeNull()
  })

  it("disables Refresh for a team with no sources", async () => {
    mockApi({ teams: [noSourceTeam], reports: [] })
    renderPage()

    const card = within(await screen.findByRole("article"))
    expect(card.getByRole("button", { name: "Refresh" })).toBeDisabled()
    expect(card.getByText("no sources attached")).toBeInTheDocument()
  })

  it("redirects to setup when there are no teams", async () => {
    mockApi({ teams: [], reports: [] })
    renderPage()

    expect(await screen.findByText("Setup wizard")).toBeInTheDocument()
  })

  it("shows a Partial data badge when the latest report has partial-data notes", async () => {
    const partialDetail = {
      ...platformDetail,
      signal_pack_snapshot: {
        partial_data_notes: [{ source: "gitlab", reason: "Source timed out." }],
      },
    }
    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.endsWith("/api/teams")) {
        return Promise.resolve(jsonResponse([platformTeam]))
      }
      if (url.endsWith("/api/reports") && init?.method !== "POST") {
        return Promise.resolve(jsonResponse([platformSummary]))
      }
      if (url.endsWith("/api/reports/report-1")) {
        return Promise.resolve(jsonResponse(partialDetail))
      }
      throw new Error(`unexpected fetch: ${url}`)
    })
    renderPage()

    expect(await screen.findByText("Partial data")).toBeInTheDocument()
  })

  it("shows the failure indicator and partial-data badge for a failed report, no risk block", async () => {
    const failedSummary = {
      ...platformSummary,
      id: "report-fail",
      status: "failed",
      error: "Jira request timed out.",
    }
    const failedDetail = {
      ...platformDetail,
      ...failedSummary,
      signal_pack_snapshot: {
        partial_data_notes: [{ source: "jira", reason: "Source timed out." }],
      },
    }
    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.endsWith("/api/teams")) {
        return Promise.resolve(jsonResponse([platformTeam]))
      }
      if (url.endsWith("/api/reports") && init?.method !== "POST") {
        return Promise.resolve(jsonResponse([failedSummary]))
      }
      if (url.endsWith("/api/reports/report-fail")) {
        return Promise.resolve(jsonResponse(failedDetail))
      }
      throw new Error(`unexpected fetch: ${url}`)
    })
    renderPage()

    expect(await screen.findByText("Partial data")).toBeInTheDocument()
    const card = within(cardFor("Platform"))
    expect(card.getByText(/Last run failed\./)).toBeInTheDocument()
    expect(card.getByText(/Jira request timed out\./)).toBeInTheDocument()
    expect(card.queryByText("No risks flagged.")).toBeNull()
    expect(card.queryByText("PLAT-3 blocked for a week")).toBeNull()
    expect(card.getByRole("button", { name: "Refresh" })).toBeInTheDocument()
    expect(card.getByRole("link", { name: "Open report" })).toHaveAttribute(
      "href",
      "/reports/results/report-fail",
    )
  })

  it("shows a report-history error state when the reports list fails to load", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.endsWith("/api/teams")) {
        return Promise.resolve(jsonResponse([platformTeam]))
      }
      if (url.endsWith("/api/reports") && init?.method !== "POST") {
        return Promise.resolve(new Response("boom", { status: 500 }))
      }
      throw new Error(`unexpected fetch: ${url}`)
    })
    renderPage()

    const card = within(await screen.findByRole("article"))
    expect(await card.findByText("Report history could not be loaded.")).toBeInTheDocument()
    expect(card.queryByText("No report yet.")).toBeNull()
    expect(card.getByRole("button", { name: "Refresh" })).toBeInTheDocument()
    expect(card.queryByRole("link", { name: "Open report" })).toBeNull()
  })
})
