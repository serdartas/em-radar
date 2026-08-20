// SPDX-License-Identifier: Apache-2.0

import { ChevronLeft } from "lucide-react"
import { Link } from "react-router-dom"

import { cn } from "@/lib/utils"

interface BackLinkProps {
  to: string
  children?: React.ReactNode
  className?: string
}

function BackLink({ children = "Back", className, to }: BackLinkProps) {
  return (
    <Link
      className={cn(
        "inline-flex items-center gap-1 text-sm text-slate-500 transition-colors hover:text-foreground",
        className,
      )}
      to={to}
    >
      <ChevronLeft aria-hidden="true" className="h-4 w-4" />
      {children}
    </Link>
  )
}

export { BackLink }
