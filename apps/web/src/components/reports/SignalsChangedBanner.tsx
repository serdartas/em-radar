// SPDX-License-Identifier: Apache-2.0

import { useState } from "react"

import { Callout } from "@/components/ui/callout"
import type { SignalDefinition } from "@/lib/signalDefinitions"
import type { SnapshotSignal } from "@/lib/reports"

interface SignalsChangedBannerProps {
  snapshotSignals: SnapshotSignal[]
  currentSignals: SignalDefinition[]
}

// Deep-equal via JSON.stringify. Expressions are plain JSON objects serialized
// deterministically by the backend (Python dict → JSON), so key order is stable
// across snapshot and live API responses. This avoids adding a dependency.
function deepEqual(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b)
}

function signalsChanged(
  snapshotSignals: SnapshotSignal[],
  currentSignals: SignalDefinition[],
): boolean {
  if (snapshotSignals.length === 0) return false
  const currentById = new Map(currentSignals.map((s) => [s.id, s]))
  return snapshotSignals.some((snapshot) => {
    const current = currentById.get(snapshot.id)
    if (!current) return true
    // Core identity fields — always present in every snapshot.
    if (
      current.name !== snapshot.name ||
      current.entity_type !== snapshot.entity_type ||
      current.report_settings.category !== snapshot.category ||
      current.origin !== snapshot.origin ||
      current.template_key !== snapshot.template_key
    ) {
      return true
    }
    // Extended fields — only present in snapshots written after M8.5-04.
    // Skip comparison when the snapshot entry lacks the field (legacy reports)
    // to avoid false positives.
    if (snapshot.expression !== undefined && !deepEqual(current.expression, snapshot.expression)) {
      return true
    }
    if (
      snapshot.severity !== undefined &&
      current.report_settings.severity !== snapshot.severity
    ) {
      return true
    }
    // Null-normalize both sides: the API omits message_template when absent
    // (undefined), but the snapshot stores null. Treat absent and null as equal
    // so a never-set message_template does not falsely flag the banner.
    if (
      snapshot.message_template !== undefined &&
      (current.report_settings.message_template ?? null) !== snapshot.message_template
    ) {
      return true
    }
    return false
  })
}

export function SignalsChangedBanner({
  snapshotSignals,
  currentSignals,
}: SignalsChangedBannerProps) {
  const [expanded, setExpanded] = useState(false)

  if (!signalsChanged(snapshotSignals, currentSignals)) return null

  return (
    <Callout role="status" variant="warning">
      <p>
        {"configuration of some signals changed since this run. "}
        <button
          className="font-medium underline underline-offset-2"
          onClick={() => setExpanded((v) => !v)}
          type="button"
        >
          {expanded ? "Hide" : "Show me"}
        </button>
      </p>
      {expanded && (
        <ul className="mt-2 space-y-1 text-amber-800">
          {snapshotSignals.map((signal) => (
            <li key={signal.id}>
              <span className="font-medium">{signal.name}</span>{" "}
              <span className="text-xs opacity-75">({signal.entity_type})</span>
            </li>
          ))}
        </ul>
      )}
    </Callout>
  )
}
