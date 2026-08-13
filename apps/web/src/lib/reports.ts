import { API_BASE_URL, ApiError, apiFetch } from "@/lib/api"
import type { Severity } from "@/lib/severity"

export type Confidence = "high" | "low" | "medium"
export type EntityType = "mergerequest" | "repository" | "sprint" | "workitem"
export type ReportStatus = "failed" | "pending" | "running" | "succeeded"

export interface Finding {
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
  status: ReportStatus
  started_at: string
  finished_at: string | null
  error: string | null
  findings_count_by_severity: Partial<Record<Severity, number>>
}

export interface ReportDetail extends ReportSummary {
  signal_pack_snapshot: unknown
  findings: Finding[]
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

export async function runTeamReport(teamProfileId: string): Promise<ReportDetail> {
  return apiFetch<ReportDetail>("/reports/run", {
    method: "POST",
    body: JSON.stringify({ connector: "jira", team_profile_id: teamProfileId }),
  })
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
