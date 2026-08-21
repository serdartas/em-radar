// SPDX-License-Identifier: Apache-2.0

import { SeverityCounts } from "@/components/SeverityCounts"
import { FindingCard } from "@/components/reports/FindingCard"
import type { Finding, ReportSectionRef } from "@/lib/reports"
import type { Severity } from "@/lib/severity"

interface ReportSectionBlockProps {
  findingsById: Map<string, Finding>
  section: ReportSectionRef
  summaryCounts: Partial<Record<Severity, number>>
  total: number
}

function ReportSectionBlock({ findingsById, section, summaryCounts, total }: ReportSectionBlockProps) {
  const headingId = `section-${section.section}`
  return (
    <section aria-labelledby={headingId} className="space-y-4">
      <h2 className="text-xl font-semibold tracking-tight" id={headingId}>
        {section.title}
      </h2>
      {section.section === "summary" ? (
        <div className="space-y-2">
          <SeverityCounts counts={summaryCounts} />
          <p className="text-sm text-slate-600">
            {total} finding{total === 1 ? "" : "s"} in total.
          </p>
        </div>
      ) : section.finding_ids.length === 0 ? (
        <p className="text-sm text-slate-500">No findings.</p>
      ) : (
        <div className="grid gap-4">
          {section.finding_ids.map((findingId) => {
            const finding = findingsById.get(findingId)
            return finding ? (
              <FindingCard finding={finding} key={`${section.section}-${findingId}`} />
            ) : null
          })}
        </div>
      )}
    </section>
  )
}

export { ReportSectionBlock }
