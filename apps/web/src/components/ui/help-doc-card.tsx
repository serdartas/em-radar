// SPDX-License-Identifier: Apache-2.0

import { BookOpen } from "lucide-react"
import type { ReactNode } from "react"

import { cn } from "@/lib/utils"

interface HelpDocCardProps {
  title: string
  children?: ReactNode
  className?: string
}

function HelpDocCard({ children, className, title }: HelpDocCardProps) {
  return (
    <div
      className={cn(
        "flex gap-3 rounded-md border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900",
        className,
      )}
    >
      <BookOpen aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-blue-500" />
      <div>
        <p className="font-medium">{title}</p>
        {children && <div className="mt-1 text-blue-800">{children}</div>}
      </div>
    </div>
  )
}

export { HelpDocCard }
