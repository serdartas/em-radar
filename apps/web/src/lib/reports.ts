// SPDX-License-Identifier: Apache-2.0


import { API_BASE_URL, ApiError, apiFetch } from "@/lib/api"
import type { Severity } from "@/lib/severity"

export type Confidence = "high" | "low" | "medium"
export type EntityType = "mergerequest" | "repository" | "sprint" | "workitem"
export type ReportStatus = "failed" | "pending" | "running" | "succeeded"

export interface Finding {
  id: string
  signal_id: string
  signal_name: string
  severity: Severity
  confidence: Confidence
  entity_type: EntityType
  entity_id: string
  title: string
  reason: string
  recommendation: string | null
  evidence: unknown
  source_link: string | null
}

export interface ReportSummary {
  id: string
  evaluation_window_id: string
  team_profile_id: string | null
  team_name: string | null
  status: ReportStatus
  started_at: string
  finished_at: string | null
  error: string | null
  findings_count_by_severity: Partial<Record<Severity, number>>
}

export interface ReportSectionRef {
  section: string
  title: string
  finding_ids: string[]
}

export interface SkipNote {
  signal_id: string
  reason: string
}

export interface ReportSummaryCounts {
  counts_by_severity: Partial<Record<Severity, number>>
  total: number
}

export interface ReportDetail extends ReportSummary {
  signal_pack_snapshot: unknown
  findings: Finding[]
  summary: ReportSummaryCounts
  sections: ReportSectionRef[]
  skip_notes: SkipNote[]
}

export interface PartialDataNote {
  source: string
  reason: string
}

export function formatTimestamp(value: string): string {
  // The API serializes started_at/finished_at from naive SQLite columns (stored as UTC
  // wall-time) without a timezone marker. Treat an offset-less string as UTC so viewers in
  // non-UTC zones do not see shifted labels; strings that already carry a zone are used as-is.
  const normalized = /([zZ]|[+-]\d{2}:?\d{2})$/.test(value) ? value : `${value}Z`
  const parsed = new Date(normalized)
  return Number.isNaN(parsed.valueOf()) ? value : parsed.toLocaleString()
}

export function extractPartialDataNotes(snapshot: unknown): PartialDataNote[] {
  if (typeof snapshot !== "object" || snapshot === null) {
    return []
  }
  const notes = (snapshot as Record<string, unknown>).partial_data_notes
  if (!Array.isArray(notes)) {
    return []
  }
  return notes.filter(
    (note): note is PartialDataNote =>
      typeof note === "object" &&
      note !== null &&
      typeof (note as Record<string, unknown>).source === "string" &&
      typeof (note as Record<string, unknown>).reason === "string",
  )
}

export type JobStatus = "done" | "failed" | "queued" | "running"

export interface ReportJob {
  id: string
  team_profile_id: string
  status: JobStatus
  enqueued_at: string
  started_at: string | null
  finished_at: string | null
  report_id: string | null
  error: string | null
}

export interface JiraSprintReportRequest {
  connectionId: string
  projectExternalId: string
  boardExternalId: string
  workingMode: "kanban" | "scrum"
  sprintLengthDays: number | null
}

export async function runJiraSprintReport(
  request: JiraSprintReportRequest,
): Promise<ReportDetail> {
  return apiFetch<ReportDetail>("/reports/run", {
    method: "POST",
    body: JSON.stringify({
      connector: "jira",
      jira: {
        connection_id: request.connectionId,
        project_external_id: request.projectExternalId,
        board_external_id: request.boardExternalId,
        working_mode: request.workingMode,
        sprint_length_days: request.sprintLengthDays,
      },
    }),
  })
}

export async function enqueueTeamReport(
  teamProfileId: string,
  window?: { start: string; end: string },
): Promise<ReportJob> {
  const body = window
    ? {
        connector: "jira",
        team_profile_id: teamProfileId,
        window_type: "date_range",
        start: window.start,
        end: window.end,
      }
    : { connector: "jira", team_profile_id: teamProfileId }
  return apiFetch<ReportJob>("/reports/run", {
    method: "POST",
    body: JSON.stringify(body),
  })
}

export async function listJobs(): Promise<ReportJob[]> {
  return apiFetch<ReportJob[]>("/reports/jobs")
}

async function pollJobUntilTerminal(job: ReportJob): Promise<ReportJob> {
  let current = job
  while (current.status === "queued" || current.status === "running") {
    await new Promise<void>((r) => setTimeout(r, 1000))
    current = await apiFetch<ReportJob>(`/reports/jobs/${current.id}`)
  }
  return current
}

/**
 * Enqueue a team report and poll until it reaches a terminal state.
 * Kept for DashboardPage and SetupPage which need the completed state before proceeding.
 */
export async function runTeamReport(
  teamProfileId: string,
  window?: { start: string; end: string },
): Promise<ReportJob> {
  const job = await enqueueTeamReport(teamProfileId, window)
  const terminal = await pollJobUntilTerminal(job)
  if (terminal.status === "failed") {
    throw new Error(terminal.error ?? "Report job failed")
  }
  return terminal
}

export async function listReports(): Promise<ReportSummary[]> {
  return apiFetch<ReportSummary[]>("/reports")
}

export async function getReport(reportId: string): Promise<ReportDetail> {
  return apiFetch<ReportDetail>(`/reports/${reportId}`)
}

export function reportMarkdownExportPath(reportId: string): string {
  return `/reports/${reportId}/export.md`
}

export async function getReportMarkdown(reportId: string): Promise<string> {
  const response = await fetch(`${API_BASE_URL}${reportMarkdownExportPath(reportId)}`)
  if (!response.ok) {
    throw new ApiError(
      response.status,
      `Markdown export for report ${reportId} failed with status ${response.status}.`,
    )
  }
  return response.text()
}

export function reportMarkdownQuery(reportId: string) {
  return {
    queryKey: ["reports", reportId, "export.md"] as const,
    queryFn: () => getReportMarkdown(reportId),
  }
}

export async function deleteReportHistory(teamId?: string): Promise<void> {
  const query = teamId ? `?team_id=${encodeURIComponent(teamId)}` : ""
  await apiFetch<void>(`/reports${query}`, { method: "DELETE" })
}
