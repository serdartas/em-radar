// SPDX-License-Identifier: Apache-2.0

import { ExportCard } from "@/components/signals/pack/ExportCard"
import { ImportCard } from "@/components/signals/pack/ImportCard"

export function SignalPackPage() {
  return (
    <section aria-labelledby="page-title" className="space-y-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight" id="page-title">
          Import &amp; Export Signal Pack
        </h1>
        <p className="mt-2 max-w-2xl text-slate-600">
          Export one or more signal config groups as a portable YAML pack, or import a pack and
          review the changes before applying. Credentials are never included.
        </p>
      </header>

      <ExportCard />
      <ImportCard />
    </section>
  )
}
