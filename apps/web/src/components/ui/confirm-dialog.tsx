// SPDX-License-Identifier: Apache-2.0

import { useEffect, useId, useRef } from "react"
import type { KeyboardEvent, ReactNode } from "react"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

interface ConfirmDialogProps {
  title: string
  /** Keep `title` as the accessible name but omit the visible heading. */
  titleHidden?: boolean
  body: ReactNode
  confirmLabel: string
  onConfirm: () => void
  pending?: boolean
  onCancel: () => void
  className?: string
}

function ConfirmDialog({
  body,
  className,
  confirmLabel,
  onCancel,
  onConfirm,
  pending = false,
  title,
  titleHidden = false,
}: ConfirmDialogProps) {
  const bodyId = useId()
  // Ref lives on a wrapper so we don't need forwardRef on Button.
  const cancelWrapRef = useRef<HTMLDivElement>(null)

  // Move focus to Cancel on mount so keyboard users can dismiss without extra tabbing,
  // and restore focus to the element that opened the dialog when it unmounts so the
  // trigger's replacement doesn't strand keyboard/screen-reader users.
  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null
    cancelWrapRef.current?.querySelector<HTMLElement>("button")?.focus()
    return () => {
      previouslyFocused?.focus?.()
    }
  }, [])

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.stopPropagation()
      onCancel()
    }
  }

  return (
    <div
      aria-describedby={bodyId}
      aria-label={`Confirm: ${title}`}
      className={cn(
        "rounded-md border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900",
        className,
      )}
      onKeyDown={handleKeyDown}
      role="alertdialog"
    >
      {!titleHidden && <p className="font-medium">{title}</p>}
      <div className="mt-1 text-amber-800" id={bodyId}>
        {body}
      </div>
      <div className="mt-3 flex gap-2">
        <Button
          className="bg-red-600 text-white hover:bg-red-700"
          disabled={pending}
          onClick={onConfirm}
          size="sm"
          variant="default"
        >
          {confirmLabel}
        </Button>
        <div ref={cancelWrapRef}>
          <Button onClick={onCancel} size="sm" variant="outline">
            Cancel
          </Button>
        </div>
      </div>
    </div>
  )
}

export { ConfirmDialog }
