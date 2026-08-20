// SPDX-License-Identifier: Apache-2.0

import type { ComponentProps } from "react"

import { cn } from "@/lib/utils"

type CheckboxProps = Omit<ComponentProps<"input">, "type">

function Checkbox({ className, ...props }: CheckboxProps) {
  return (
    <input
      className={cn(
        "h-4 w-4 rounded border border-border bg-background text-primary transition-colors",
        "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary",
        "disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      type="checkbox"
      {...props}
    />
  )
}

export { Checkbox }
