// SPDX-License-Identifier: Apache-2.0

import { cloneElement, isValidElement, useId } from "react"
import type { ReactNode } from "react"

import { Label } from "@/components/ui/label"
import { cn } from "@/lib/utils"

interface FormRowProps {
  /** The `for` attribute value — must match the field's `id`. */
  htmlFor: string
  label: string
  children: ReactNode
  /** Optional hint text shown below the field. Wired to the field via aria-describedby. */
  hint?: string
  /** Optional action element (e.g. a button) placed to the right of the field. */
  action?: ReactNode
  className?: string
}

function FormRow({ action, children, className, hint, htmlFor, label }: FormRowProps) {
  const hintId = useId()

  // Inject aria-describedby on the direct field element when a hint is present.
  // Concatenate with any existing aria-describedby so validation / help text
  // already on the field is not silently dropped.
  const enhancedChildren = (() => {
    if (!hint || !isValidElement<{ "aria-describedby"?: string }>(children)) {
      return children
    }
    const existing = children.props["aria-describedby"]
    const combined = [existing, hintId].filter(Boolean).join(" ")
    return cloneElement(children, { "aria-describedby": combined })
  })()

  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <Label htmlFor={htmlFor}>{label}</Label>
      <div className="flex items-center gap-2">
        <div className="flex-1">{enhancedChildren}</div>
        {action && <div className="shrink-0">{action}</div>}
      </div>
      {hint && (
        <p className="text-xs text-slate-500" id={hintId}>
          {hint}
        </p>
      )}
    </div>
  )
}

export { FormRow }
