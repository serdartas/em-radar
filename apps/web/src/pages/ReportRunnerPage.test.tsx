import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
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

// A job returned immediately after enqueueing (queued/done in tests since BackgroundTasks runs sync).
const doneJob = {
  id: "job-1",
  team_profile_id: "team-1",
  status: "done",
  enqueued_at: "2026-06-01T10:00:00Z",
  started_at: "2026-06-01T10:00:00Z",
  finished_at: "2026-06-01T10:00:05Z",
  report_id: "report-1",
  error: null,
}

const failedJob = {
  id: "job-2",
  team_profile_id: "team-1",
  status: "failed",
  enqueued_at: "2026-06-01T11:00:00Z",
  started_at: "2026-06-01T11:00:01Z",
  finished_at: "2026-06-01T11:00:02Z",
  report_id: null,
  error: "no active sprint",
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  })
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("ReportRunnerPage", () => {
  it("does not show a demo report button", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.endsWith("/api/teams")) return Promise.resolve(jsonResponse([]))
      if (url.endsWith("/api/reports/jobs")) return Promise.resolve(jsonResponse([]))
      throw new Error(`unexpected fetch: ${url}`)
    })

    renderPage()
    await screen.findByRole("button", { name: "Run team reports" })
    expect(screen.queryByRole("button", { name: /demo/i })).toBeNull()
  })

  it("runs a report for a selected team and navigates to the report", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.endsWith("/api/teams")) return Promise.resolve(jsonResponse([team]))
      if (url.includes("/api/teams/team-1/sprints")) return Promise.resolve(jsonResponse([]))
      if (url.endsWith("/api/reports/run")) return Promise.resolve(jsonResponse(doneJob))
      if (url.includes("/api/reports/jobs/")) return Promise.resolve(jsonResponse(doneJob))
      if (url.endsWith("/api/reports/jobs")) return Promise.resolve(jsonResponse([doneJob]))
      if (url.endsWith("/api/reports/report-1")) return Promise.resolve(jsonResponse(report))
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
      if (url.endsWith("/api/teams")) return Promise.resolve(jsonResponse([team]))
      if (url.endsWith("/api/reports/jobs")) return Promise.resolve(jsonResponse([]))
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
      if (url.endsWith("/api/teams")) return Promise.resolve(jsonResponse([team]))
      if (url.endsWith("/api/reports/run")) return Promise.resolve(jsonResponse(doneJob))
      if (url.includes("/api/reports/jobs/")) return Promise.resolve(jsonResponse(doneJob))
      if (url.endsWith("/api/reports/jobs")) return Promise.resolve(jsonResponse([doneJob]))
      if (url.endsWith("/api/reports/report-1")) return Promise.resolve(jsonResponse(report))
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
      if (url.endsWith("/api/teams")) return Promise.resolve(jsonResponse([team]))
      if (url.endsWith("/api/reports/run")) return Promise.resolve(jsonResponse(doneJob))
      if (url.includes("/api/reports/jobs/")) return Promise.resolve(jsonResponse(doneJob))
      if (url.endsWith("/api/reports/jobs")) return Promise.resolve(jsonResponse([doneJob]))
      if (url.endsWith("/api/reports/report-1")) return Promise.resolve(jsonResponse(report))
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
      if (url.endsWith("/api/teams")) return Promise.resolve(jsonResponse([team]))
      if (url.endsWith("/api/reports/jobs")) return Promise.resolve(jsonResponse([]))
      throw new Error(`unexpected fetch: ${url}`)
    })

    renderPage()

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
      if (url.endsWith("/api/teams")) return Promise.resolve(jsonResponse([team]))
      if (url.endsWith("/api/reports/jobs")) return Promise.resolve(jsonResponse([]))
      throw new Error(`unexpected fetch: ${url}`)
    })

    renderPage()

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

  it("navigates to the list when multiple teams are selected", async () => {
    const teamAlpha = { ...team, id: "team-1", name: "Alpha" }
    const teamBeta = { ...team, id: "team-2", name: "Beta" }
    const jobAlpha = { ...doneJob, id: "job-a", team_profile_id: "team-1" }
    const jobBeta = { ...doneJob, id: "job-b", team_profile_id: "team-2", report_id: "report-2" }
    let postCount = 0

    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.endsWith("/api/teams")) return Promise.resolve(jsonResponse([teamAlpha, teamBeta]))
      if (url.endsWith("/api/reports/run") && init?.method === "POST") {
        postCount++
        return Promise.resolve(jsonResponse(postCount === 1 ? jobAlpha : jobBeta))
      }
      if (url.endsWith("/api/reports/jobs/job-a")) return Promise.resolve(jsonResponse(jobAlpha))
      if (url.endsWith("/api/reports/jobs/job-b")) return Promise.resolve(jsonResponse(jobBeta))
      if (url.endsWith("/api/reports/jobs")) return Promise.resolve(jsonResponse([jobAlpha, jobBeta]))
      if (url.endsWith("/api/reports")) return Promise.resolve(jsonResponse([]))
      throw new Error(`unexpected fetch: ${url}`)
    })

    renderWithRoutes()

    fireEvent.click(await screen.findByLabelText("Alpha"))
    fireEvent.click(screen.getByLabelText("Beta"))
    fireEvent.click(screen.getByRole("button", { name: "Run team reports" }))

    await screen.findByRole("heading", { name: "Report Results", level: 1 })
  })

  it("disables the checkbox and shows a message for a team with no sources", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.endsWith("/api/teams")) return Promise.resolve(jsonResponse([noSourceTeam]))
      if (url.endsWith("/api/reports/jobs")) return Promise.resolve(jsonResponse([]))
      throw new Error(`unexpected fetch: ${url}`)
    })

    renderPage()

    const checkbox = await screen.findByRole("checkbox", { name: /No Source Team/i })
    expect(checkbox).toBeDisabled()
    expect(screen.getByText("no sources attached")).toBeInTheDocument()
  })

  it("shows the running/recent jobs list from polled data", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.endsWith("/api/teams")) return Promise.resolve(jsonResponse([team]))
      if (url.endsWith("/api/reports/jobs"))
        return Promise.resolve(jsonResponse([doneJob, failedJob]))
      throw new Error(`unexpected fetch: ${url}`)
    })

    renderPage()

    // Both jobs render in the running/recent list.
    expect(await screen.findByText("Done")).toBeInTheDocument()
    expect(screen.getByText("Failed")).toBeInTheDocument()
    // Failed job shows error text.
    expect(screen.getByText("no active sprint")).toBeInTheDocument()
  })

  it("shows a sprint picker for a single team and sends sprint_external_id in the run request", async () => {
    const sprints = [
      {
        id: "sprint-db-1",
        external_id: "30000",
        name: "Platform Sprint 12",
        state: "active",
        start_date: null,
        end_date: null,
      },
    ]

    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.endsWith("/api/teams")) return Promise.resolve(jsonResponse([team]))
      if (url.includes("/api/teams/team-1/sprints")) return Promise.resolve(jsonResponse(sprints))
      if (url.endsWith("/api/reports/run")) return Promise.resolve(jsonResponse(doneJob))
      if (url.includes("/api/reports/jobs/")) return Promise.resolve(jsonResponse(doneJob))
      if (url.endsWith("/api/reports/jobs")) return Promise.resolve(jsonResponse([doneJob]))
      if (url.endsWith("/api/reports/report-1")) return Promise.resolve(jsonResponse(report))
      throw new Error(`unexpected fetch: ${url}`)
    })

    renderApp()

    fireEvent.click(await screen.findByLabelText("Platform"))
    const sprintSelect = await screen.findByLabelText("Sprint")
    expect(sprintSelect).toBeInTheDocument()
    // Wait for sprint options to load from the mocked API before selecting.
    await screen.findByText("Platform Sprint 12")
    fireEvent.change(sprintSelect, { target: { value: "30000" } })
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
              window_type: "sprint",
              sprint_external_id: "30000",
            }),
      ),
    ).toBe(true)
  })

  it("surfaces the enqueue error to the user when the run request fails", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.endsWith("/api/teams")) return Promise.resolve(jsonResponse([team]))
      if (url.includes("/api/teams/team-1/sprints")) return Promise.resolve(jsonResponse([]))
      if (url.endsWith("/api/reports/jobs")) return Promise.resolve(jsonResponse([]))
      if (url.endsWith("/api/reports/run"))
        return Promise.resolve(jsonResponse({ detail: "Internal server error" }, 500))
      throw new Error(`unexpected fetch: ${url}`)
    })

    renderPage()

    fireEvent.click(await screen.findByLabelText("Platform"))
    fireEvent.click(screen.getByRole("button", { name: "Run team reports" }))

    const alert = await screen.findByRole("alert")
    expect(alert).toHaveTextContent("Internal server error")
  })
})

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
