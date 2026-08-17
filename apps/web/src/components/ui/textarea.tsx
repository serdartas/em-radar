// SPDX-License-Identifier: Apache-2.0

import type { ComponentProps } from "react"

import { cn } from "@/lib/utils"

function Textarea({ className, ...props }: ComponentProps<"textarea">) {
  return (
    <textarea
      className={cn(
        "flex min-h-24 w-full rounded-md border border-border bg-background px-3 py-2 text-sm shadow-sm transition-colors",
        "placeholder:text-slate-400 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary",
        "disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  )
}

export { Textarea }
