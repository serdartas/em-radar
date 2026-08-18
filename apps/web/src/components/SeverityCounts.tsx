// SPDX-License-Identifier: Apache-2.0

import { Badge } from "@/components/ui/badge"
import { SEVERITIES, type Severity } from "@/lib/severity"

interface SeverityCountsProps {
  counts: Partial<Record<Severity, number>>
}

export function SeverityCounts({ counts }: SeverityCountsProps) {
  return (
    <ul className="flex flex-wrap gap-2" aria-label="Findings by severity">
      {[...SEVERITIES].reverse().map((severity) => (
        <li key={severity}>
          <Badge variant={severity}>
            {counts[severity] ?? 0} {severity}
          </Badge>
        </li>
      ))}
    </ul>
  )
}
