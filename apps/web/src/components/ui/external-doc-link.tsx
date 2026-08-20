// SPDX-License-Identifier: Apache-2.0

import { ExternalLink } from "lucide-react"
import type { ComponentProps } from "react"

import { cn } from "@/lib/utils"

interface ExternalDocLinkProps extends Omit<ComponentProps<"a">, "target" | "rel"> {
  href: string
}

function ExternalDocLink({ children, className, href, ...props }: ExternalDocLinkProps) {
  return (
    <a
      className={cn(
        "inline-flex items-center gap-1 text-sm text-primary underline-offset-4 hover:underline",
        className,
      )}
      href={href}
      rel="noopener noreferrer"
      target="_blank"
      {...props}
    >
      {children}
      <ExternalLink aria-hidden="true" className="h-3.5 w-3.5 shrink-0" />
    </a>
  )
}

export { ExternalDocLink }
