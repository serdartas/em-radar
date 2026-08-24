// SPDX-License-Identifier: Apache-2.0

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import type { SignalDefinition } from "@/lib/signalDefinitions"

interface SignalListItemProps {
  definition: SignalDefinition
  onEdit: (id: string) => void
  onDelete: (id: string) => void
  deletePending?: boolean
  deleteError?: string | null
}

export function SignalListItem({
  definition,
  onEdit,
  onDelete,
  deletePending = false,
  deleteError = null,
}: SignalListItemProps) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-2 p-4">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h3 className="font-semibold">{definition.name}</h3>
          </div>
          <div className="flex items-center gap-3">
            <Button onClick={() => onEdit(definition.id)} size="sm" variant="outline">
              Edit
            </Button>
            <Button
              disabled={deletePending}
              onClick={() => onDelete(definition.id)}
              size="sm"
              variant="outline"
            >
              Delete
            </Button>
          </div>
        </div>
        {deleteError && (
          <p className="text-sm text-red-700" role="alert">
            {deleteError}
          </p>
        )}
      </CardContent>
    </Card>
  )
}
