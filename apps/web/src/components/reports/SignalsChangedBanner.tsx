// SPDX-License-Identifier: Apache-2.0

import { useState } from "react"

import { Callout } from "@/components/ui/callout"
import type { SignalDefinition } from "@/lib/signalDefinitions"
import type { SnapshotSignal } from "@/lib/reports"

interface SignalsChangedBannerProps {
  snapshotSignals: SnapshotSignal[]
  currentSignals: SignalDefinition[]
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
    return (
      current.name !== snapshot.name ||
      current.entity_type !== snapshot.entity_type ||
      current.report_settings.category !== snapshot.category ||
      current.origin !== snapshot.origin ||
      current.template_key !== snapshot.template_key
    )
  })
}

export function SignalsChangedBanner({
  snapshotSignals,
  currentSignals,
}: SignalsChangedBannerProps) {
  const [expanded, setExpanded] = useState(false)

  if (!signalsChanged(snapshotSignals, currentSignals)) return null

  return (
    <Callout variant="warning">
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
