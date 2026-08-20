// SPDX-License-Identifier: Apache-2.0

import { Button } from "@/components/ui/button"
import type { ConflictMode } from "@/lib/signalPack"

interface ConflictResolverProps {
  clashes: string[]
  onChoose: (conflict: ConflictMode) => void
  pending: boolean
}

function ConflictResolver({ clashes, onChoose, pending }: ConflictResolverProps) {
  return (
    <div
      className="space-y-3 rounded-md border border-amber-200 bg-amber-50 p-3"
      data-testid="conflict-resolver"
    >
      <p className="text-sm text-amber-900">
        {clashes.length} item{clashes.length === 1 ? "" : "s"} already exist with the same name:{" "}
        <span className="font-medium">{clashes.join(", ")}</span>. Choose how to apply the import.
      </p>
      <div className="flex flex-wrap gap-2">
        <Button disabled={pending} onClick={() => onChoose("skip")} size="sm" variant="outline">
          Skip
        </Button>
        <Button
          disabled={pending}
          onClick={() => onChoose("overwrite")}
          size="sm"
          variant="outline"
        >
          Overwrite
        </Button>
        <Button
          disabled={pending}
          onClick={() => onChoose("keep_both")}
          size="sm"
          variant="outline"
        >
          Keep both
        </Button>
        <Button
          disabled={pending}
          onClick={() => onChoose("cancel")}
          size="sm"
          variant="outline"
        >
          Cancel
        </Button>
      </div>
    </div>
  )
}

export { ConflictResolver }
