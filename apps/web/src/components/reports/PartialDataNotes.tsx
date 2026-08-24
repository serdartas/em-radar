// SPDX-License-Identifier: Apache-2.0

import type { PartialDataNote } from "@/lib/reports"

interface PartialDataNotesProps {
  notes: PartialDataNote[]
}

function PartialDataNotes({ notes }: PartialDataNotesProps) {
  return (
    <section
      aria-labelledby="partial-data-title"
      className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900"
    >
      <h2 className="font-semibold" id="partial-data-title">
        Partial data
      </h2>
      <p className="mt-1 text-amber-800">
        Some sources were unavailable when this report ran. Findings may be incomplete.
      </p>
      <ul className="mt-2 space-y-1">
        {notes.map((note, index) => (
          <li key={`${index}-${note.source}-${note.reason}`}>
            <span className="font-medium">{note.source}</span>: {note.reason}
          </li>
        ))}
      </ul>
    </section>
  )
}

export { PartialDataNotes }
