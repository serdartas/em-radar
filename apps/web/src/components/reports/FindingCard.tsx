// SPDX-License-Identifier: Apache-2.0

import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { FindingEvidence } from "@/components/reports/FindingEvidence"
import type { Finding } from "@/lib/reports"

interface FindingCardProps {
  finding: Finding
}

function FindingCard({ finding }: FindingCardProps) {
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <h3 className="text-lg font-semibold leading-snug">{finding.title}</h3>
          <Badge variant={finding.severity}>{finding.severity}</Badge>
        </div>
        <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
          {finding.signal_name}
        </p>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <div>
          <h4 className="font-semibold">Reason</h4>
          <p className="mt-1 text-slate-600">{finding.reason}</p>
        </div>
        <FindingEvidence evidence={finding.evidence} />
        {finding.recommendation && (
          <div>
            <h4 className="font-semibold">Recommendation</h4>
            <p className="mt-1 text-slate-600">{finding.recommendation}</p>
          </div>
        )}
        {finding.source_link && (
          <a
            className="inline-flex font-medium text-blue-700 underline-offset-4 hover:underline"
            href={finding.source_link}
            rel="noreferrer"
            target="_blank"
          >
            View source
          </a>
        )}
      </CardContent>
    </Card>
  )
}

export { FindingCard }
