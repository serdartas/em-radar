// SPDX-License-Identifier: Apache-2.0

import { useState } from "react"

import { ConnectionForm } from "@/components/connections/ConnectionForm"
import { Button } from "@/components/ui/button"
import { type Connector } from "@/lib/connectors"

interface AddConnectionPanelProps {
  connectors: Connector[]
}

/**
 * Progressive-disclosure wrapper: shows an "Add connection" button when collapsed,
 * and the full ConnectionForm when expanded. Collapses again after a successful save
 * or when the user cancels.
 */
export function AddConnectionPanel({ connectors }: AddConnectionPanelProps) {
  const [open, setOpen] = useState(false)

  if (!open) {
    return (
      <Button onClick={() => setOpen(true)} type="button" variant="outline">
        Add connection
      </Button>
    )
  }

  return (
    <ConnectionForm
      connectors={connectors}
      onCancel={() => setOpen(false)}
      onSaved={() => setOpen(false)}
    />
  )
}
