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
  it("runs the demo report and navigates to the persisted results", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.endsWith("/api/reports/run")) {
        return Promise.resolve(jsonResponse(report))
      }
      if (url.endsWith("/api/reports/report-1")) {
        return Promise.resolve(jsonResponse(report))
      }
      throw new Error(`unexpected fetch: ${url}`)
    })

    renderApp()

    fireEvent.click(screen.getByRole("button", { name: "Run demo report" }))

    expect(await screen.findByText("PLAT-2 stale for 12 days")).toBeInTheDocument()
    expect(screen.getByText("Check whether the item is blocked.")).toBeInTheDocument()

    expect(
      fetchMock.mock.calls.some(
        ([url, requestInit]) =>
          String(url).endsWith("/api/reports/run") &&
          requestInit?.method === "POST" &&
          String(requestInit?.body) === JSON.stringify({ connector: "demo" }),
      ),
    ).toBe(true)
  })

  it("shows an error when the run fails", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "Demo data unavailable." }), { status: 500 }),
    )

    renderApp()
    fireEvent.click(screen.getByRole("button", { name: "Run demo report" }))

    await waitFor(() => {
      expect(screen.getByText("Demo data unavailable.")).toBeInTheDocument()
    })
  })
})
