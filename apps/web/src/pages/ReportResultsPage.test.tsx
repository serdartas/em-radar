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

const SECTION_ORDER = [
  ["summary", "Summary"],
  ["top_risks", "Top Risks"],
  ["planning_hygiene", "Planning Hygiene"],
  ["delivery_flow", "Delivery Flow"],
  ["sprint_health", "Sprint Health"],
  ["merge_request_flow", "Merge Request Flow"],
  ["source_linking", "Source Linking"],
  ["detailed_findings", "Detailed Findings"],
  ["suggested_actions", "Suggested Actions"],
] as const

function buildSections(assignments: Record<string, string[]>) {
  return SECTION_ORDER.map(([section, title]) => ({
    section,
    title,
    finding_ids: assignments[section] ?? [],
  }))
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
  summary: { counts_by_severity: { info: 0, warning: 2, critical: 1 }, total: 1 },
  skip_notes: [],
  sections: buildSections({ detailed_findings: ["finding-9"] }),
  findings: [
    {
      id: "finding-9",
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

  it("omits the Evidence block for empty evidence and pluralizes the total", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(report), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    )

    renderReportResults()
    await screen.findByText("PLAT-9 blocked for 6 days")

    // The single finding carries `evidence: {}`, which must render no Evidence block.
    expect(screen.queryByRole("heading", { name: "Evidence" })).toBeNull()
    expect(screen.getByText("1 finding in total.")).toBeInTheDocument()
  })

  it("renders all nine sections, severity-ordered findings, and a source link each", async () => {
    const sectionedReport = {
      ...report,
      findings_count_by_severity: { info: 1, warning: 1, critical: 1 },
      summary: { counts_by_severity: { info: 1, warning: 1, critical: 1 }, total: 3 },
      sections: buildSections({
        top_risks: ["f-crit", "f-warn", "f-info"],
        detailed_findings: ["f-crit", "f-warn", "f-info"],
      }),
      findings: [
        {
          id: "f-info",
          signal_id: "sig-info",
          signal_name: "Info signal",
          severity: "info",
          confidence: "low",
          entity_type: "workitem",
          entity_id: "entity-info",
          title: "INFO-3 minor note",
          reason: "Minor.",
          recommendation: null,
          evidence: null,
          source_link: "https://demo.invalid/browse/INFO-3",
        },
        {
          id: "f-crit",
          signal_id: "sig-crit",
          signal_name: "Critical signal",
          severity: "critical",
          confidence: "high",
          entity_type: "workitem",
          entity_id: "entity-crit",
          title: "CRIT-1 blocked",
          reason: "Blocked.",
          recommendation: "Escalate.",
          evidence: { days_blocked: 6 },
          source_link: "https://demo.invalid/browse/CRIT-1",
        },
        {
          id: "f-warn",
          signal_id: "sig-warn",
          signal_name: "Warning signal",
          severity: "warning",
          confidence: "medium",
          entity_type: "workitem",
          entity_id: "entity-warn",
          title: "WARN-2 stale",
          reason: "Stale.",
          recommendation: "Review.",
          evidence: { days_idle: 12 },
          source_link: "https://demo.invalid/browse/WARN-2",
        },
      ],
    }
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(sectionedReport), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    )

    renderReportResults()
    await screen.findByRole("heading", { level: 2, name: "Detailed Findings" })

    for (const [, title] of SECTION_ORDER) {
      expect(screen.getByRole("heading", { level: 2, name: title })).toBeInTheDocument()
    }

    const detailedSection = screen
      .getByRole("heading", { level: 2, name: "Detailed Findings" })
      .closest("section") as HTMLElement
    const orderedTitles = Array.from(
      detailedSection.querySelectorAll("h3"),
      (heading) => heading.textContent,
    )
    expect(orderedTitles).toEqual(["CRIT-1 blocked", "WARN-2 stale", "INFO-3 minor note"])

    const sourceLinks = detailedSection.querySelectorAll('a[href*="/browse/"]')
    expect(sourceLinks).toHaveLength(3)
    for (const link of Array.from(sourceLinks)) {
      expect(link).toHaveAttribute("href")
    }
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

  it("renders persisted findings offline when only the report and signal-definitions endpoints resolve", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input)
      if (url.endsWith("/api/reports/report-1")) {
        return Promise.resolve(
          new Response(JSON.stringify(report), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        )
      }
      if (url.endsWith("/api/signal-definitions")) {
        return Promise.resolve(
          new Response(JSON.stringify([]), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        )
      }
      // Source/connector calls must never be made when viewing a persisted report.
      return Promise.reject(new Error(`unexpected offline fetch to ${url}`))
    })

    renderReportResults()

    expect(await screen.findByText("PLAT-9 blocked for 6 days")).toBeInTheDocument()
    expect(screen.getByText("Escalate the blocker.")).toBeInTheDocument()
  })

  it("renders partial-data notes captured in the snapshot", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          ...report,
          signal_pack_snapshot: {
            partial_data_notes: [
              { source: "board", reason: "board data unavailable: ConnectorTransientError" },
              { source: "code", reason: "code data unavailable: ConnectorAuthError" },
            ],
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    )

    renderReportResults()

    expect(await screen.findByRole("heading", { name: "Partial data" })).toBeInTheDocument()
    expect(
      screen.getByText("board data unavailable: ConnectorTransientError", { exact: false }),
    ).toBeInTheDocument()
    expect(
      screen.getByText("code data unavailable: ConnectorAuthError", { exact: false }),
    ).toBeInTheDocument()
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

  it("shows immutability copy on every report results page", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(report), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    )
    renderReportResults()
    await screen.findByText("PLAT-9 blocked for 6 days")
    expect(
      screen.getByText(
        "Results reflect signal configuration at run time. Edits to signals affect only future runs.",
      ),
    ).toBeInTheDocument()
  })

  it("shows the signals-changed banner when a snapshot signal was deleted from current definitions", async () => {
    const reportWithSnapshot = {
      ...report,
      signal_pack_snapshot: {
        signal_definitions: [
          {
            id: "sig-deleted",
            name: "Deleted signal",
            entity_type: "workitem",
            category: "delivery_flow",
            origin: "system_template",
            template_key: null,
          },
        ],
      },
    }
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input)
      if (url.endsWith("/api/signal-definitions")) {
        return Promise.resolve(
          new Response(JSON.stringify([]), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        )
      }
      return Promise.resolve(
        new Response(JSON.stringify(reportWithSnapshot), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      )
    })
    renderReportResults()
    await screen.findByText("PLAT-9 blocked for 6 days")
    expect(
      await screen.findByText(/configuration of some signals changed since this run/i),
    ).toBeInTheDocument()
  })

  it("hides the signals-changed banner when snapshot matches current definitions", async () => {
    const signalDef = {
      id: "sig-1",
      name: "Blocked work item",
      entity_type: "workitem",
      expression: {},
      report_settings: { severity: "critical", category: "delivery_flow" },
      origin: "system_template",
      template_key: "blocked_work_item",
      description: null,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    }
    const reportWithSnapshot = {
      ...report,
      signal_pack_snapshot: {
        signal_definitions: [
          {
            id: "sig-1",
            name: "Blocked work item",
            entity_type: "workitem",
            category: "delivery_flow",
            origin: "system_template",
            template_key: "blocked_work_item",
          },
        ],
      },
    }
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input)
      if (url.endsWith("/api/signal-definitions")) {
        return Promise.resolve(
          new Response(JSON.stringify([signalDef]), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        )
      }
      return Promise.resolve(
        new Response(JSON.stringify(reportWithSnapshot), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      )
    })
    renderReportResults()
    await screen.findByText("PLAT-9 blocked for 6 days")
    expect(
      screen.queryByText(/configuration of some signals changed since this run/i),
    ).toBeNull()
  })

  it("reveals snapshot signals when 'Show me' is clicked in the banner", async () => {
    const reportWithSnapshot = {
      ...report,
      signal_pack_snapshot: {
        signal_definitions: [
          {
            id: "sig-gone",
            name: "Gone signal",
            entity_type: "sprint",
            category: "sprint_health",
            origin: "user_created",
            template_key: null,
          },
        ],
      },
    }
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input)
      if (url.endsWith("/api/signal-definitions")) {
        return Promise.resolve(
          new Response(JSON.stringify([]), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        )
      }
      return Promise.resolve(
        new Response(JSON.stringify(reportWithSnapshot), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      )
    })
    renderReportResults()
    await screen.findByText(/configuration of some signals changed since this run/i)

    fireEvent.click(screen.getByRole("button", { name: "Show me" }))
    expect(screen.getByText("Gone signal")).toBeInTheDocument()
    expect(screen.getByText("(sprint)")).toBeInTheDocument()
  })
})
