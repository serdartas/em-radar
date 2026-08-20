// SPDX-License-Identifier: Apache-2.0

import { Badge } from "@/components/ui/badge"
import type { SignalImportDiff } from "@/lib/signalPack"

interface ChangeRowProps {
  change: SignalImportDiff
}

function ChangeRow({ change }: ChangeRowProps) {
  return (
    <div className="space-y-1">
      <p className="font-medium">{change.signal_id}</p>
      {change.enabled && (
        <p className="text-slate-600">
          {change.enabled.after ? "Enabled" : "Disabled"} (was{" "}
          {change.enabled.before ? "enabled" : "disabled"})
        </p>
      )}
      {change.severity && (
        <p className="flex items-center gap-1 text-slate-600">
          Severity:
          <Badge variant={change.severity.before}>{change.severity.before}</Badge>→
          <Badge variant={change.severity.after}>{change.severity.after}</Badge>
        </p>
      )}
      {change.params && (
        <p className="text-slate-600">
          Parameters: <code className="text-xs">{JSON.stringify(change.params.before)}</code> →{" "}
          <code className="text-xs">{JSON.stringify(change.params.after)}</code>
        </p>
      )}
    </div>
  )
}

export { ChangeRow }
