import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"

import { ReportResultsPage } from "@/pages/ReportResultsPage"
import { ReportRunnerPage } from "@/pages/ReportRunnerPage"
import { ReportsListPage } from "@/pages/ReportsListPage"

const report = {
  id: "report-1",
  evaluation_window_id: "window-1",
  status: "succeeded",
  started_at: "2026-06-01T10:00:00Z",
  finished_at: "2026-06-01T10:00:05Z",
  error: null,
  findings_count_by_severity: { info: 0, warning: 1, critical: 0 },
  signal_pack_snapshot: {},
  summary: { counts_by_severity: { info: 0, warning: 1, critical: 0 }, total: 1 },
  skip_notes: [],
  sections: [
    { section: "summary", title: "Summary", finding_ids: [] },
    { section: "top_risks", title: "Top Risks", finding_ids: [] },
    { section: "planning_hygiene", title: "Planning Hygiene", finding_ids: [] },
    { section: "delivery_flow", title: "Delivery Flow", finding_ids: [] },
    { section: "sprint_health", title: "Sprint Health", finding_ids: [] },
    { section: "merge_request_flow", title: "Merge Request Flow", finding_ids: [] },
    { section: "source_linking", title: "Source Linking", finding_ids: [] },
    { section: "detailed_findings", title: "Detailed Findings", finding_ids: ["finding-1"] },
    { section: "suggested_actions", title: "Suggested Actions", finding_ids: [] },
  ],
  findings: [
    {
      id: "finding-1",
      signal_id: "stale-in-progress-work-item",
      signal_name: "Stale in-progress work item",
      severity: "warning",
      confidence: "high",
      entity_type: "workitem",
      entity_id: "entity-1",
      title: "PLAT-2 stale for 12 days",
      reason: "The item has not changed recently.",
      recommendation: "Check whether the item is blocked.",
      evidence: { days_idle: 12 },
      source_link: "https://demo.invalid/browse/PLAT-2",
    },
  ],
}

const team = {
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

const noSourceTeam = {
  ...team,
  id: "team-no-source",
  name: "No Source Team",
  scope_ids: [],
  code_connection_id: null,
}

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  })
}

function renderApp() {
  const queryClient = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/reports/run"]}>
        <Routes>
          <Route element={<ReportRunnerPage />} path="/reports/run" />
          <Route element={<ReportResultsPage />} path="/reports/results/:reportId" />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("ReportRunnerPage", () => {
  it("does not show a demo report button", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.endsWith("/api/teams")) {
        return Promise.resolve(jsonResponse([]))
      }
      throw new Error(`unexpected fetch: ${url}`)
    })

    renderPage()
    await screen.findByRole("button", { name: "Run team reports" })
    expect(screen.queryByRole("button", { name: /demo/i })).toBeNull()
  })

  it("runs a report for a selected team", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.endsWith("/api/teams")) {
        return Promise.resolve(jsonResponse([team]))
      }
      if (url.endsWith("/api/reports/run")) {
        return Promise.resolve(jsonResponse(report))
      }
      if (url.endsWith("/api/reports/report-1")) {
        return Promise.resolve(jsonResponse(report))
      }
      throw new Error(`unexpected fetch: ${url}`)
    })

    renderApp()

    fireEvent.click(await screen.findByLabelText("Platform"))
    fireEvent.click(screen.getByRole("button", { name: "Run team reports" }))

    expect(await screen.findByText("PLAT-2 stale for 12 days")).toBeInTheDocument()
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

  it("exposes a sprint and date-range window picker", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.endsWith("/api/teams")) {
        return Promise.resolve(jsonResponse([team]))
      }
      throw new Error(`unexpected fetch: ${url}`)
    })

    renderPage()
    const modeSelect = (await screen.findByLabelText("Window")) as HTMLSelectElement
    const options = Array.from(modeSelect.options, (option) => option.value)
    expect(options).toEqual(["sprint", "date_range"])

    expect(screen.queryByLabelText("Start date")).toBeNull()
    fireEvent.change(modeSelect, { target: { value: "date_range" } })
    expect(screen.getByLabelText("Start date")).toBeInTheDocument()
    expect(screen.getByLabelText("End date")).toBeInTheDocument()
  })

  it("posts a date-range window when date-range mode is selected", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.endsWith("/api/teams")) {
        return Promise.resolve(jsonResponse([team]))
      }
      if (url.endsWith("/api/reports/run")) {
        return Promise.resolve(jsonResponse(report))
      }
      if (url.endsWith("/api/reports/report-1")) {
        return Promise.resolve(jsonResponse(report))
      }
      throw new Error(`unexpected fetch: ${url}`)
    })

    renderApp()

    fireEvent.click(await screen.findByLabelText("Platform"))
    fireEvent.change(screen.getByLabelText("Window"), { target: { value: "date_range" } })
    fireEvent.change(screen.getByLabelText("Start date"), { target: { value: "2026-05-01" } })
    fireEvent.change(screen.getByLabelText("End date"), { target: { value: "2026-05-15" } })
    fireEvent.click(screen.getByRole("button", { name: "Run team reports" }))

    expect(await screen.findByText("PLAT-2 stale for 12 days")).toBeInTheDocument()
    expect(
      fetchMock.mock.calls.some(
        ([url, requestInit]) =>
          String(url).endsWith("/api/reports/run") &&
          requestInit?.method === "POST" &&
          String(requestInit?.body) ===
            JSON.stringify({
              connector: "jira",
              team_profile_id: "team-1",
              window_type: "date_range",
              start: "2026-05-01T00:00:00Z",
              end: "2026-05-16T00:00:00.000Z",
            }),
      ),
    ).toBe(true)
  })

  it("allows a single-day window and includes the full selected day", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.endsWith("/api/teams")) {
        return Promise.resolve(jsonResponse([team]))
      }
      if (url.endsWith("/api/reports/run")) {
        return Promise.resolve(jsonResponse(report))
      }
      if (url.endsWith("/api/reports/report-1")) {
        return Promise.resolve(jsonResponse(report))
      }
      throw new Error(`unexpected fetch: ${url}`)
    })

    renderApp()

    fireEvent.click(await screen.findByLabelText("Platform"))
    fireEvent.change(screen.getByLabelText("Window"), { target: { value: "date_range" } })
    fireEvent.change(screen.getByLabelText("Start date"), { target: { value: "2026-05-15" } })
    fireEvent.change(screen.getByLabelText("End date"), { target: { value: "2026-05-15" } })
    fireEvent.click(screen.getByRole("button", { name: "Run team reports" }))

    expect(await screen.findByText("PLAT-2 stale for 12 days")).toBeInTheDocument()
    expect(
      fetchMock.mock.calls.some(
        ([url, requestInit]) =>
          String(url).endsWith("/api/reports/run") &&
          requestInit?.method === "POST" &&
          String(requestInit?.body) ===
            JSON.stringify({
              connector: "jira",
              team_profile_id: "team-1",
              window_type: "date_range",
              start: "2026-05-15T00:00:00Z",
              end: "2026-05-16T00:00:00.000Z",
            }),
      ),
    ).toBe(true)
  })

  it("blocks a date-range run when the dates are invalid", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.endsWith("/api/teams")) {
        return Promise.resolve(jsonResponse([team]))
      }
      throw new Error(`unexpected fetch: ${url}`)
    })

    renderApp()

    fireEvent.click(await screen.findByLabelText("Platform"))
    fireEvent.change(screen.getByLabelText("Window"), { target: { value: "date_range" } })
    fireEvent.click(screen.getByRole("button", { name: "Run team reports" }))

    expect(await screen.findByText("Choose both a start and an end date.")).toBeInTheDocument()
    expect(
      fetchMock.mock.calls.some(([url]) => String(url).endsWith("/api/reports/run")),
    ).toBe(false)
  })

  it("blocks a date-range run when the start is not before the end", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.endsWith("/api/teams")) {
        return Promise.resolve(jsonResponse([team]))
      }
      throw new Error(`unexpected fetch: ${url}`)
    })

    renderApp()

    fireEvent.click(await screen.findByLabelText("Platform"))
    fireEvent.change(screen.getByLabelText("Window"), { target: { value: "date_range" } })
    fireEvent.change(screen.getByLabelText("Start date"), { target: { value: "2026-05-15" } })
    fireEvent.change(screen.getByLabelText("End date"), { target: { value: "2026-05-01" } })
    fireEvent.click(screen.getByRole("button", { name: "Run team reports" }))

    expect(
      await screen.findByText("The start date must be before the end date."),
    ).toBeInTheDocument()
    expect(
      fetchMock.mock.calls.some(([url]) => String(url).endsWith("/api/reports/run")),
    ).toBe(false)
  })

  it("shows an error when the team run fails", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.endsWith("/api/teams")) {
        return Promise.resolve(jsonResponse([team]))
      }
      return Promise.resolve(
        new Response(JSON.stringify({ detail: "Report run failed." }), { status: 500 }),
      )
    })

    renderApp()
    fireEvent.click(await screen.findByLabelText("Platform"))
    fireEvent.click(screen.getByRole("button", { name: "Run team reports" }))

    await waitFor(() => {
      expect(screen.getByText("Report run failed.")).toBeInTheDocument()
    })
  })

  it("runs all teams despite a single failure, navigates to the list, and shows a failure note", async () => {
    const teamAlpha = { ...team, id: "team-1", name: "Alpha" }
    const teamBeta = { ...team, id: "team-2", name: "Beta" }
    const teamGamma = { ...team, id: "team-3", name: "Gamma" }
    const reportAlpha = { ...report, id: "report-1" }
    const reportGamma = { ...report, id: "report-3" }

    const runCalls: string[] = []

    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.endsWith("/api/teams")) {
        return Promise.resolve(jsonResponse([teamAlpha, teamBeta, teamGamma]))
      }
      if (url.endsWith("/api/reports/run")) {
        const body = JSON.parse(String(init?.body ?? "{}")) as { team_profile_id?: string }
        const teamId = body.team_profile_id ?? ""
        runCalls.push(teamId)
        if (teamId === "team-2") {
          return Promise.resolve(
            new Response(JSON.stringify({ detail: "Source error." }), { status: 500 }),
          )
        }
        const resp = teamId === "team-1" ? reportAlpha : reportGamma
        return Promise.resolve(jsonResponse(resp))
      }
      if (url.endsWith("/api/reports")) {
        return Promise.resolve(jsonResponse([]))
      }
      throw new Error(`unexpected fetch: ${url}`)
    })

    renderWithRoutes()

    fireEvent.click(await screen.findByLabelText("Alpha"))
    fireEvent.click(screen.getByLabelText("Beta"))
    fireEvent.click(screen.getByLabelText("Gamma"))
    fireEvent.click(screen.getByRole("button", { name: "Run team reports" }))

    // (b) navigation goes to the list — "Report Results" h1 is only on ReportsListPage
    await screen.findByRole("heading", { name: "Report Results", level: 1 })

    // (a) all three teams were attempted, including the third despite the second failing
    expect(runCalls).toEqual(["team-1", "team-2", "team-3"])

    // (c) failure note names the failed team and is visible on the DESTINATION page
    expect(
      screen.getByText(/Report generation failed for Beta\. Successful reports were still created\./),
    ).toBeInTheDocument()
  })

  it("navigates to the list when multiple teams all succeed", async () => {
    const teamAlpha = { ...team, id: "team-1", name: "Alpha" }
    const teamGamma = { ...team, id: "team-3", name: "Gamma" }
    const reportGamma = { ...report, id: "report-3" }

    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.endsWith("/api/teams")) {
        return Promise.resolve(jsonResponse([teamAlpha, teamGamma]))
      }
      if (url.endsWith("/api/reports/run")) {
        const body = JSON.parse(String(init?.body ?? "{}")) as { team_profile_id?: string }
        const teamId = body.team_profile_id ?? ""
        const resp = teamId === "team-1" ? report : reportGamma
        return Promise.resolve(jsonResponse(resp))
      }
      if (url.endsWith("/api/reports")) {
        return Promise.resolve(jsonResponse([]))
      }
      throw new Error(`unexpected fetch: ${url}`)
    })

    renderWithRoutes()

    fireEvent.click(await screen.findByLabelText("Alpha"))
    fireEvent.click(screen.getByLabelText("Gamma"))
    fireEvent.click(screen.getByRole("button", { name: "Run team reports" }))

    // "Report Results" h1 is only on ReportsListPage — confirms we landed on the list
    await screen.findByRole("heading", { name: "Report Results", level: 1 })

    // No failure note when all teams succeeded
    expect(screen.queryByText(/Report generation failed/)).toBeNull()
  })

  it("disables the checkbox and shows a message for a team with no sources", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.endsWith("/api/teams")) {
        return Promise.resolve(jsonResponse([noSourceTeam]))
      }
      throw new Error(`unexpected fetch: ${url}`)
    })

    renderPage()

    const checkbox = await screen.findByRole("checkbox", { name: /No Source Team/i })
    expect(checkbox).toBeDisabled()
    expect(screen.getByText("no sources attached")).toBeInTheDocument()
  })
})

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/reports/run"]}>
        <Routes>
          <Route element={<ReportRunnerPage />} path="/reports/run" />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

// Renders the runner and list routes so that navigation between them fully unmounts/mounts
// the respective pages — the realistic production behaviour the tests need to exercise.
function renderWithRoutes() {
  const queryClient = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/reports/run"]}>
        <Routes>
          <Route element={<ReportRunnerPage />} path="/reports/run" />
          <Route element={<ReportsListPage />} path="/reports/results" />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}
