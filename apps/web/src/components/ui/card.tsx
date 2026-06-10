import type { ComponentProps } from "react"

import { cn } from "@/lib/utils"

function Card({ className, ...props }: ComponentProps<"article">) {
  return (
    <article
      className={cn("rounded-lg border bg-background shadow-sm", className)}
      {...props}
    />
  )
}

function CardHeader({ className, ...props }: ComponentProps<"header">) {
  return (
    <header
      className={cn("flex flex-col gap-2 p-6", className)}
      {...props}
    />
  )
}

function CardContent({ className, ...props }: ComponentProps<"div">) {
  return <div className={cn("px-6 pb-6", className)} {...props} />
}

export { Card, CardContent, CardHeader }
