import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, render, screen, waitFor, within } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"

import { ReportsListPage } from "@/pages/ReportsListPage"

const reports = [
  {
    id: "report-alpha-2",
    evaluation_window_id: "window-1",
    team_profile_id: "team-alpha",
    team_name: "Team Alpha",
    status: "succeeded",
    started_at: "2026-06-03T10:00:00Z",
    finished_at: "2026-06-03T10:00:05Z",
    error: null,
    findings_count_by_severity: { info: 0, warning: 1, critical: 0 },
  },
  {
    id: "report-beta-1",
    evaluation_window_id: "window-2",
    team_profile_id: "team-beta",
    team_name: "Team Beta",
    status: "succeeded",
    started_at: "2026-06-02T10:00:00Z",
    finished_at: "2026-06-02T10:00:05Z",
    error: null,
    findings_count_by_severity: { info: 0, warning: 0, critical: 2 },
  },
  {
    id: "report-alpha-1",
    evaluation_window_id: "window-3",
    team_profile_id: "team-alpha",
    team_name: "Team Alpha",
    status: "succeeded",
    started_at: "2026-06-01T10:00:00Z",
    finished_at: "2026-06-01T10:00:05Z",
    error: null,
    findings_count_by_severity: { info: 0, warning: 0, critical: 0 },
  },
]

function renderReportsList() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/reports/results"]}>
        <ReportsListPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("ReportsListPage", () => {
  it("renders persisted reports grouped under each team name", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(reports), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    )

    renderReportsList()

    const alphaGroup = (await screen.findByRole("heading", { name: "Team Alpha" }))
      .closest("section") as HTMLElement
    const betaGroup = screen
      .getByRole("heading", { name: "Team Beta" })
      .closest("section") as HTMLElement

    expect(within(alphaGroup).getAllByRole("link")).toHaveLength(2)
    expect(within(betaGroup).getAllByRole("link")).toHaveLength(1)

    // Groups are ordered by their most recent report (Team Alpha's 2026-06-03 precedes
    // Team Beta's 2026-06-02).
    const headings = screen.getAllByRole("heading", { level: 2 }).map((node) => node.textContent)
    expect(headings).toEqual(["Team Alpha", "Team Beta"])
  })

  // AUDIT-30: history.replaceState must be called in a useEffect, not during render,
  // and only when there was state to consume (to preserve React Router's history fields).
  it("AUDIT-30: consumes history failedTeams state and clears it via useEffect", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    )
    const replaceStateSpy = vi.spyOn(window.history, "replaceState")

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter
          initialEntries={[{ pathname: "/reports/results", state: { failedTeams: ["Team Alpha"] } }]}
        >
          <ReportsListPage />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    // The failed-teams banner should appear after mount.
    const alert = await screen.findByRole("alert")
    expect(alert.textContent).toMatch(/Team Alpha/)

    // replaceState must have been called with usr: null to clear the payload
    // while preserving React Router's internal history fields.
    await waitFor(() => {
      expect(replaceStateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ usr: null }),
        "",
      )
    })
  })

  it("AUDIT-30: does not call replaceState when location.state has no failedTeams", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    )
    const replaceStateSpy = vi.spyOn(window.history, "replaceState")

    renderReportsList() // standard render with no state

    await screen.findByText(/No reports yet/)

    expect(replaceStateSpy).not.toHaveBeenCalled()
  })

  it("falls back to Unknown team when a report has no team", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify([
          {
            ...reports[0],
            id: "report-orphan",
            team_profile_id: null,
            team_name: null,
          },
        ]),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    )

    renderReportsList()

    expect(await screen.findByRole("heading", { name: "Unknown team" })).toBeInTheDocument()
  })
})
