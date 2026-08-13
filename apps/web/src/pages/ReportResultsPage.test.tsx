import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"

import { ReportResultsPage } from "@/pages/ReportResultsPage"

const MARKDOWN_EXPORT = "# EM Radar Report\n\n## Summary\n\n- **Total:** 1\n"

function renderReportResults() {
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
}

function mockReportAndExportFetch() {
  return vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
    const url = String(input)
    if (url.endsWith("/export.md")) {
      return Promise.resolve(
        new Response(MARKDOWN_EXPORT, {
          status: 200,
          headers: { "Content-Type": "text/markdown" },
        }),
      )
    }
    return Promise.resolve(
      new Response(JSON.stringify(report), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    )
  })
}

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
  vi.unstubAllGlobals()
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

  it("copies the Markdown export to the clipboard from the export endpoint", async () => {
    const fetchMock = mockReportAndExportFetch()
    const writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } })

    renderReportResults()
    await screen.findByText("PLAT-9 blocked for 6 days")

    fireEvent.click(screen.getByRole("button", { name: "Copy to clipboard" }))

    await waitFor(() => expect(writeText).toHaveBeenCalledWith(MARKDOWN_EXPORT))
    expect(
      fetchMock.mock.calls.some(([input]) =>
        String(input).endsWith("/api/reports/report-1/export.md"),
      ),
    ).toBe(true)
    expect(await screen.findByText("Copied to clipboard.")).toBeInTheDocument()
  })

  it("downloads the Markdown export as a .md file", async () => {
    const fetchMock = mockReportAndExportFetch()
    const createObjectURL = vi.fn().mockReturnValue("blob:report")
    const revokeObjectURL = vi.fn()
    vi.stubGlobal("URL", { ...URL, createObjectURL, revokeObjectURL })
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined)

    renderReportResults()
    await screen.findByText("PLAT-9 blocked for 6 days")

    fireEvent.click(screen.getByRole("button", { name: "Download .md" }))

    await waitFor(() => expect(createObjectURL).toHaveBeenCalledTimes(1))
    expect(clickSpy).toHaveBeenCalledTimes(1)
    expect(
      fetchMock.mock.calls.some(([input]) =>
        String(input).endsWith("/api/reports/report-1/export.md"),
      ),
    ).toBe(true)
    // The revoke is deferred to a macrotask so the browser can claim the download.
    await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledWith("blob:report"))
  })

  it("surfaces an error when the export cannot be generated", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input)
      if (url.endsWith("/export.md")) {
        return Promise.resolve(new Response("nope", { status: 500 }))
      }
      return Promise.resolve(
        new Response(JSON.stringify(report), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      )
    })

    renderReportResults()
    await screen.findByText("PLAT-9 blocked for 6 days")

    fireEvent.click(screen.getByRole("button", { name: "Copy to clipboard" }))

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The export could not be generated.",
    )
  })
})
