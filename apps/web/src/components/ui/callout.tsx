// SPDX-License-Identifier: Apache-2.0

import { cva, type VariantProps } from "class-variance-authority"
import type { ReactNode } from "react"

import { cn } from "@/lib/utils"

const calloutVariants = cva(
  "rounded-md border p-4 text-sm",
  {
    variants: {
      variant: {
        error: "border-red-200 bg-red-50 text-red-900",
        warning: "border-amber-200 bg-amber-50 text-amber-900",
        success: "border-green-200 bg-green-50 text-green-900",
        info: "border-blue-200 bg-blue-50 text-blue-900",
      },
    },
    defaultVariants: {
      variant: "info",
    },
  },
)

interface CalloutProps extends VariantProps<typeof calloutVariants> {
  title?: string
  children?: ReactNode
  role?: string
  className?: string
}

function Callout({ children, className, role, title, variant }: CalloutProps) {
  return (
    <div className={cn(calloutVariants({ variant }), className)} role={role}>
      {title && <p className="font-medium">{title}</p>}
      {children && <div className={cn(title ? "mt-1" : undefined)}>{children}</div>}
    </div>
  )
}

export { Callout }
