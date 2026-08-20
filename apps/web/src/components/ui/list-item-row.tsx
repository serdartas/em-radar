// SPDX-License-Identifier: Apache-2.0

import type { ReactNode } from "react"

import { cn } from "@/lib/utils"

interface ListItemRowProps {
  label: ReactNode
  action?: ReactNode
  className?: string
}

function ListItemRow({ action, className, label }: ListItemRowProps) {
  return (
    <div
      className={cn(
        "flex items-center justify-between rounded-md border border-border px-4 py-2.5",
        className,
      )}
    >
      <span className="text-sm">{label}</span>
      {action && <div className="ml-4 shrink-0">{action}</div>}
    </div>
  )
}

export { ListItemRow }
