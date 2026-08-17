// SPDX-License-Identifier: Apache-2.0

import { Info } from "lucide-react"
import { type ReactNode, useEffect, useId, useRef, useState } from "react"

import { cn } from "@/lib/utils"

interface InfoTooltipProps {
  label: string
  children: ReactNode
  className?: string
}

export function InfoTooltip({ children, className, label }: InfoTooltipProps) {
  const [open, setOpen] = useState(false)
  const panelId = useId()
  const containerRef = useRef<HTMLSpanElement>(null)

  useEffect(() => {
    if (!open) {
      return
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false)
      }
    }

    function handlePointerDown(event: PointerEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }

    document.addEventListener("keydown", handleKeyDown)
    document.addEventListener("pointerdown", handlePointerDown)
    return () => {
      document.removeEventListener("keydown", handleKeyDown)
      document.removeEventListener("pointerdown", handlePointerDown)
    }
  }, [open])

  return (
    <span className={cn("relative inline-flex", className)} ref={containerRef}>
      <button
        aria-controls={panelId}
        aria-expanded={open}
        aria-label={label}
        className="inline-flex h-5 w-5 items-center justify-center rounded-full text-slate-400 transition-colors hover:text-slate-600 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary"
        onClick={() => setOpen((current) => !current)}
        type="button"
      >
        <Info aria-hidden="true" className="h-4 w-4" />
      </button>
      {open && (
        <div
          className="absolute left-0 top-full z-20 mt-2 w-72 rounded-md border border-blue-200 bg-blue-50 p-3 text-sm font-normal text-blue-900 shadow-sm"
          id={panelId}
          role="note"
        >
          {children}
        </div>
      )}
    </span>
  )
}
