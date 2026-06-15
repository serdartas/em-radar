import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, render, screen } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"

import { ReportResultsPage } from "@/pages/ReportResultsPage"

const report = {
  id: "report-1",
  evaluation_window_id: "window-1",
  status: "succeeded",
  started_at: "2026-06-01T10:00:00Z",
  finished_at: "2026-06-01T10:00:05Z",
  error: null,
  findings_count_by_severity: { info: 0, warning: 2, critical: 1 },
  signal_pack_snapshot: {},
  findings: [
    {
      signal_id: "blocked-without-update",
      signal_name: "Blocked without update",
      severity: "critical",
      confidence: "high",
      entity_type: "workitem",
      entity_id: "entity-9",
      title: "PLAT-9 blocked for 6 days",
      reason: "Blocked and untouched.",
      recommendation: "Escalate the blocker.",
      evidence: {},
      source_link: "https://demo.invalid/browse/PLAT-9",
    },
  ],
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("ReportResultsPage", () => {
  it("loads a report by id and renders its findings and severity counts", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(report), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    )

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/reports/results/report-1"]}>
          <Routes>
            <Route element={<ReportResultsPage />} path="/reports/results/:reportId" />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    expect(await screen.findByText("PLAT-9 blocked for 6 days")).toBeInTheDocument()
    expect(screen.getByText("Escalate the blocker.")).toBeInTheDocument()

    const counts = screen.getByRole("list", { name: "Findings by severity" })
    expect(counts).toHaveTextContent("1 critical")
    expect(counts).toHaveTextContent("2 warning")
  })

  it("shows failed report errors before empty findings", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          ...report,
          status: "failed",
          error: "Connector timed out.",
          findings_count_by_severity: { info: 0, warning: 0, critical: 0 },
          findings: [],
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    )

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/reports/results/report-1"]}>
          <Routes>
            <Route element={<ReportResultsPage />} path="/reports/results/:reportId" />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    expect(await screen.findByRole("alert")).toHaveTextContent("Connector timed out.")
    expect(screen.queryByText("No findings were detected.")).not.toBeInTheDocument()
  })
})
