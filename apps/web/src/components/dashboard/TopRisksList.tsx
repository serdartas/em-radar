// SPDX-License-Identifier: Apache-2.0

import { Badge } from "@/components/ui/badge"
import type { Finding, ReportDetail } from "@/lib/reports"

interface TopRisksListProps {
  detail: ReportDetail | undefined
  detailIsLoading: boolean
  detailIsError: boolean
  topFindings: Finding[]
}

/**
 * Renders the "Top risks" section inside a dashboard team card.
 * Handles loading, error, and empty states for the detail query.
 */
function TopRisksList({ detail, detailIsError, detailIsLoading, topFindings }: TopRisksListProps) {
  return (
    <div className="space-y-2">
      <h3 className="text-xs font-medium uppercase tracking-wide text-slate-500">Top risks</h3>
      {detail ? (
        <>
          {detailIsError && (
            <p className="text-xs text-amber-800" role="alert">
              Top risks could not be refreshed. Showing the last loaded results.
            </p>
          )}
          {topFindings.length === 0 ? (
            <p className="text-sm text-slate-500">No risks flagged.</p>
          ) : (
            <ul className="space-y-2">
              {topFindings.map((finding) => (
                <li className="flex items-start justify-between gap-3" key={finding.id}>
                  <span className="leading-snug">{finding.title}</span>
                  <Badge variant={finding.severity}>{finding.severity}</Badge>
                </li>
              ))}
            </ul>
          )}
        </>
      ) : detailIsLoading ? (
        <p className="text-sm text-slate-500">Loading top risks...</p>
      ) : detailIsError ? (
        <p className="text-sm text-red-700" role="alert">
          Top risks could not be loaded.
        </p>
      ) : (
        <p className="text-sm text-slate-500">No risks flagged.</p>
      )}
    </div>
  )
}

export { TopRisksList }
