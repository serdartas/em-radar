// SPDX-License-Identifier: Apache-2.0

import type { ReportStatus } from "@/lib/reports"

interface ReportStatusBadgeProps {
  status: ReportStatus
  error: string | null
}

/**
 * Renders the status label and an explanatory message for non-succeeded report states
 * (running, pending, failed).
 */
function ReportStatusBadge({ error, status }: ReportStatusBadgeProps) {
  return (
    <>
      <p className="text-xs uppercase tracking-wide text-slate-500">{status}</p>
      {status === "failed" ? (
        <p
          className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700"
          role="alert"
        >
          Last run failed. {error ?? "The report run failed."}
        </p>
      ) : (
        <p className="text-sm text-slate-500">Last run is still in progress.</p>
      )}
    </>
  )
}

export { ReportStatusBadge }
