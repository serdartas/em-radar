// SPDX-License-Identifier: Apache-2.0

import { useEffect, useRef, useState } from "react"

import { ConnectionForm } from "@/components/connections/ConnectionForm"
import { Button } from "@/components/ui/button"
import { type Connector } from "@/lib/connectors"
import { type SourceConnection } from "@/lib/connections"

interface AddConnectionPanelProps {
  connectors: Connector[]
  onSaved?: (connection: SourceConnection) => void
}

/**
 * Progressive-disclosure wrapper: shows an "Add connection" button when collapsed,
 * and the full ConnectionForm when expanded. Collapses again after a successful save
 * or when the user cancels.
 *
 * Focus management: when the panel opens, focus moves to the first interactive field
 * inside the form so keyboard and screen-reader users land inside the form without
 * extra tab stops. When it collapses, focus returns to the "Add connection" reveal
 * button so the user does not lose their place in the page.
 */
export function AddConnectionPanel({ connectors, onSaved }: AddConnectionPanelProps) {
  const [open, setOpen] = useState(false)
  const revealButtonRef = useRef<HTMLButtonElement>(null)
  const formContainerRef = useRef<HTMLDivElement>(null)
  // Tracks the previous open value so the close-focus branch is skipped on initial mount.
  const wasOpenRef = useRef(false)

  useEffect(() => {
    if (open) {
      const firstField = formContainerRef.current?.querySelector<HTMLElement>(
        "input, select, textarea, button",
      )
      firstField?.focus()
    } else if (wasOpenRef.current) {
      // Returning from expanded state — give focus back to the reveal button.
      revealButtonRef.current?.focus()
    }
    wasOpenRef.current = open
  }, [open])

  if (!open) {
    return (
      <Button ref={revealButtonRef} onClick={() => setOpen(true)} type="button" variant="outline">
        Add connection
      </Button>
    )
  }

  return (
    <div ref={formContainerRef}>
      <ConnectionForm
        connectors={connectors}
        onCancel={() => setOpen(false)}
        onSaved={(conn) => { setOpen(false); onSaved?.(conn) }}
      />
    </div>
  )
}
