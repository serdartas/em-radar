import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"

import { DashboardTeamCard } from "@/components/dashboard/DashboardTeamCard"
import { ReportStatusBadge } from "@/components/dashboard/ReportStatusBadge"
import { TopRisksList } from "@/components/dashboard/TopRisksList"
import type { ReportSummary } from "@/lib/reports"

const baseTeam = {
  id: "team-1",
  name: "Platform",
  description: null,
  connection_ids: ["conn-1"],
  scope_ids: ["board-1"],
  signal_config_group_ids: ["group-1"],
  code_connection_id: null,
  working_mode: "scrum" as const,
  sprint_length_days: 14,
  member_user_keys: [],
  gitlab_config_status: "not_applicable" as const,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
}

const noSourceTeam = { ...baseTeam, id: "team-2", name: "Solo", scope_ids: [], code_connection_id: null }

const succeededSummary = {
  id: "report-1",
  evaluation_window_id: "window-1",
  team_profile_id: "team-1",
  team_name: "Platform",
  status: "succeeded" as const,
  started_at: "2026-06-01T10:00:00",
  finished_at: "2026-06-01T10:00:05",
  error: null,
  findings_count_by_severity: { info: 0, warning: 1, critical: 1 },
}

const topFinding = {
  id: "f-1",
  signal_id: "blocked",
  signal_name: "Blocked",
  severity: "critical" as const,
  confidence: "high" as const,
  entity_type: "workitem" as const,
  entity_id: "e1",
  title: "PLAT-3 is blocked",
  reason: "Blocked",
  recommendation: null,
  evidence: {},
  source_link: null,
}

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  })
}

function reportDetail(summary: typeof succeededSummary, findings: typeof topFinding[]) {
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
        finding_ids: findings.map((f) => f.id),
      },
    ],
    findings,
  }
}

function renderCard(
  team = baseTeam,
  latestSummary?: ReportSummary,
  { reportsError = false, reportsLoading = false } = {},
) {
  const queryClient = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  })
  queryClient.setQueryData(["settings"], { telemetry_enabled: false, date_format: "dd/mm/yyyy" })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <DashboardTeamCard
          latestSummary={latestSummary}
          reportsError={reportsError}
          reportsLoading={reportsLoading}
          team={team}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function renderCardWithSummary(summary: ReportSummary) {
  return renderCard(baseTeam, summary)
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("DashboardTeamCard", () => {
  it("renders team name and working mode", () => {
    renderCardWithSummary(succeededSummary)
    expect(screen.getByRole("heading", { level: 2, name: "Platform" })).toBeInTheDocument()
    expect(screen.getByText("scrum")).toBeInTheDocument()
  })

  it("shows severity counts for a succeeded report", () => {
    renderCardWithSummary(succeededSummary)
    expect(screen.getByText("1 critical")).toBeInTheDocument()
    expect(screen.getByText("1 warning")).toBeInTheDocument()
  })

  it("renders top findings after fetching report detail", async () => {
    const detail = reportDetail(succeededSummary, [topFinding])
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse(detail))
    renderCardWithSummary(succeededSummary)
    expect(await screen.findByText("PLAT-3 is blocked")).toBeInTheDocument()
  })

  it("shows 'No report yet' when no summary", () => {
    renderCard()
    expect(screen.getByText("No report yet.")).toBeInTheDocument()
  })

  it("shows 'Loading report' while reports are loading", () => {
    renderCard(baseTeam, undefined, { reportsLoading: true })
    expect(screen.getByText("Loading report...")).toBeInTheDocument()
  })

  it("shows partial data badge when snapshot contains partial_data_notes", async () => {
    const detail = {
      ...reportDetail(succeededSummary, []),
      signal_pack_snapshot: {
        partial_data_notes: [{ source: "gitlab", reason: "Source timed out." }],
      },
    }
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse(detail))
    renderCardWithSummary(succeededSummary)
    expect(await screen.findByText("Partial data")).toBeInTheDocument()
  })

  it("disables Refresh when team has no sources", () => {
    renderCard(noSourceTeam)
    expect(screen.getByRole("button", { name: "Refresh" })).toBeDisabled()
    expect(screen.getByText("no sources attached")).toBeInTheDocument()
  })
})

describe("TopRisksList", () => {
  it("renders top findings with severity badges", () => {
    render(
      <TopRisksList
        detail={{ sections: [], findings: [topFinding] } as unknown as Parameters<typeof TopRisksList>[0]["detail"]}
        detailIsError={false}
        detailIsLoading={false}
        topFindings={[topFinding]}
      />,
    )
    expect(screen.getByText("PLAT-3 is blocked")).toBeInTheDocument()
    expect(screen.getByText("critical")).toBeInTheDocument()
  })

  it("shows 'No risks flagged' when topFindings is empty and detail is loaded", () => {
    render(
      <TopRisksList
        detail={{ sections: [], findings: [] } as unknown as Parameters<typeof TopRisksList>[0]["detail"]}
        detailIsError={false}
        detailIsLoading={false}
        topFindings={[]}
      />,
    )
    expect(screen.getByText("No risks flagged.")).toBeInTheDocument()
  })

  it("shows loading state when detail is undefined and loading", () => {
    render(
      <TopRisksList
        detail={undefined}
        detailIsError={false}
        detailIsLoading={true}
        topFindings={[]}
      />,
    )
    expect(screen.getByText("Loading top risks...")).toBeInTheDocument()
  })

  it("shows error state when detail is undefined and error occurred", () => {
    render(
      <TopRisksList
        detail={undefined}
        detailIsError={true}
        detailIsLoading={false}
        topFindings={[]}
      />,
    )
    expect(screen.getByText("Top risks could not be loaded.")).toBeInTheDocument()
  })

  it("shows stale warning alongside cached findings when detail is loaded but refetch errored", () => {
    render(
      <TopRisksList
        detail={{ sections: [], findings: [topFinding] } as unknown as Parameters<typeof TopRisksList>[0]["detail"]}
        detailIsError={true}
        detailIsLoading={false}
        topFindings={[topFinding]}
      />,
    )
    expect(screen.getByText("PLAT-3 is blocked")).toBeInTheDocument()
    expect(
      screen.getByText("Top risks could not be refreshed. Showing the last loaded results."),
    ).toBeInTheDocument()
  })
})

describe("ReportStatusBadge", () => {
  it("renders failed status with the error message", () => {
    render(<ReportStatusBadge error="Connector timed out." status="failed" />)
    expect(screen.getByRole("alert")).toHaveTextContent("Last run failed. Connector timed out.")
  })

  it("renders failed status with default fallback when error is null", () => {
    render(<ReportStatusBadge error={null} status="failed" />)
    expect(screen.getByRole("alert")).toHaveTextContent("Last run failed. The report run failed.")
  })

  it("renders running status with in-progress message", () => {
    render(<ReportStatusBadge error={null} status="running" />)
    expect(screen.getByText("running")).toBeInTheDocument()
    expect(screen.getByText("Last run is still in progress.")).toBeInTheDocument()
  })

  it("renders pending status with in-progress message", () => {
    render(<ReportStatusBadge error={null} status="pending" />)
    expect(screen.getByText("pending")).toBeInTheDocument()
    expect(screen.getByText("Last run is still in progress.")).toBeInTheDocument()
  })
})
