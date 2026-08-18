// SPDX-License-Identifier: Apache-2.0

import type { ReactNode } from "react"

interface PagePlaceholderProps {
  title: string
  description: string
  children?: ReactNode
}

export function PagePlaceholder({ title, description, children }: PagePlaceholderProps) {
  return (
    <section aria-labelledby="page-title">
      <h1 className="text-2xl font-semibold tracking-tight" id="page-title">
        {title}
      </h1>
      <p className="mt-2 max-w-2xl text-slate-600">{description}</p>
      <div className="mt-8 rounded-xl border border-dashed bg-white p-10 text-center text-sm text-slate-500">
        {children ?? "This page will be built in a later milestone."}
      </div>
    </section>
  )
}
