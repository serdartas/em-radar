import type { ComponentProps } from "react"

import { cn } from "@/lib/utils"

function Input({ className, type = "text", ...props }: ComponentProps<"input">) {
  return (
    <input
      className={cn(
        "flex h-9 w-full rounded-md border border-border bg-background px-3 py-1 text-sm shadow-sm transition-colors",
        "placeholder:text-slate-400 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary",
        "disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      type={type}
      {...props}
    />
  )
}

export { Input }
