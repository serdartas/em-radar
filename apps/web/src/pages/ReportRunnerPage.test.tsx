import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"

import { ReportResultsPage } from "@/pages/ReportResultsPage"
import { ReportRunnerPage } from "@/pages/ReportRunnerPage"

const report = {
  id: "report-1",
  evaluation_window_id: "window-1",
  status: "succeeded",
  started_at: "2026-06-01T10:00:00Z",
  finished_at: "2026-06-01T10:00:05Z",
  error: null,
  findings_count_by_severity: { info: 0, warning: 1, critical: 0 },
  signal_pack_snapshot: {},
  findings: [
    {
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
