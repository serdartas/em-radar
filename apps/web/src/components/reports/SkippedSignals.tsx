// SPDX-License-Identifier: Apache-2.0

import type { SkipNote } from "@/lib/reports"

interface SkippedSignalsProps {
  notes: SkipNote[]
}

function SkippedSignals({ notes }: SkippedSignalsProps) {
  return (
    <section
      aria-labelledby="skipped-signals-title"
      className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700"
    >
      <h2 className="font-semibold" id="skipped-signals-title">
        Skipped signals
      </h2>
      <p className="mt-1 text-slate-600">These signals did not run for this report.</p>
      <ul className="mt-2 space-y-1">
        {notes.map((note, index) => (
          <li key={`${index}-${note.signal_id}-${note.reason}`}>
            <span className="font-medium">{note.signal_id}</span>: {note.reason}
          </li>
        ))}
      </ul>
    </section>
  )
}

export { SkippedSignals }
