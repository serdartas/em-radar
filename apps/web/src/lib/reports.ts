export type FindingSeverity = "critical" | "info" | "warning"

export interface Finding {
  signal_id: string
  signal_name: string
  severity: FindingSeverity
  confidence: "high" | "low" | "medium"
  entity_type: "mergerequest" | "repository" | "sprint" | "workitem"
  entity_id: string
  title: string
  reason: string
  recommendation: string | null
  evidence: unknown
  source_link: string | null
}

interface ReportRunResponse {
  findings: Finding[]
}

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? "/api").replace(/\/$/, "")

export async function runDemoReport(): Promise<ReportRunResponse> {
  const response = await fetch(`${apiBaseUrl}/reports/run`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ connector: "demo" }),
  })

  if (!response.ok) {
    throw new Error("The demo report could not be run.")
  }

  return response.json() as Promise<ReportRunResponse>
}
