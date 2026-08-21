// SPDX-License-Identifier: Apache-2.0

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import type { SignalDefinition } from "@/lib/signalDefinitions"

interface SignalListItemProps {
  definition: SignalDefinition
  onEdit: (id: string) => void
  onDelete: (id: string) => void
  deletePending?: boolean
}

export function SignalListItem({
  definition,
  onEdit,
  onDelete,
  deletePending = false,
}: SignalListItemProps) {
  return (
    <Card>
      <CardContent className="flex flex-wrap items-center justify-between gap-4 p-4">
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
      </CardContent>
    </Card>
  )
}
