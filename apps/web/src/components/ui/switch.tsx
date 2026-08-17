// SPDX-License-Identifier: Apache-2.0

import type { ComponentProps } from "react"

import { cn } from "@/lib/utils"

interface SwitchProps extends Omit<ComponentProps<"button">, "onChange"> {
  checked: boolean
  onCheckedChange: (checked: boolean) => void
}

function Switch({ checked, className, disabled, onCheckedChange, ...props }: SwitchProps) {
  return (
    <button
      aria-checked={checked}
      className={cn(
        "inline-flex h-5 w-9 shrink-0 items-center rounded-full border border-transparent transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2",
        "disabled:cursor-not-allowed disabled:opacity-50",
        checked ? "bg-primary" : "bg-slate-300",
        className,
      )}
      disabled={disabled}
      onClick={() => onCheckedChange(!checked)}
      role="switch"
      type="button"
      {...props}
    >
      <span
        className={cn(
          "pointer-events-none block h-4 w-4 rounded-full bg-white shadow transition-transform",
          checked ? "translate-x-4" : "translate-x-0.5",
        )}
      />
    </button>
  )
}

export { Switch }
