// SPDX-License-Identifier: Apache-2.0

import { ChangeRow } from "@/components/signals/pack/ChangeRow"
import type { SignalPackImportPreview } from "@/lib/signalPack"

interface ImportPreviewProps {
  preview: SignalPackImportPreview
}

function ImportPreview({ preview }: ImportPreviewProps) {
  const importedSignals = preview.imported_signal_names ?? []
  return (
    <div className="space-y-4" data-testid="import-preview">
      <p className="text-sm text-slate-600">
        Pack <span className="font-medium">{preview.pack_name}</span>
        {importedSignals.length > 0
          ? ` — ${importedSignals.length} signal${importedSignals.length === 1 ? "" : "s"} to import.`
          : preview.changes.length === 0
            ? " — no changes from your current configuration."
            : ` — ${preview.changes.length} signal${preview.changes.length === 1 ? "" : "s"} affected.`}
      </p>

      {preview.warnings.length > 0 && (
        <ul aria-label="Validation warnings" className="space-y-2">
          {preview.warnings.map((warning) => (
            <li
              className="rounded-md border border-amber-200 bg-amber-50 p-2 text-sm text-amber-900"
              key={`${warning.code}-${warning.path}`}
            >
              {warning.message}
            </li>
          ))}
        </ul>
      )}

      {preview.unresolved_mappings.length > 0 && (
        <ul aria-label="Unresolved mappings" className="space-y-2">
          {preview.unresolved_mappings.map((mapping) => (
            <li
              className="rounded-md border border-amber-200 bg-amber-50 p-2 text-sm text-amber-900"
              key={mapping}
            >
              {mapping} requires local connector and target scope mapping before it can be enabled.
            </li>
          ))}
        </ul>
      )}

      {preview.changes.length > 0 && (
        <ul aria-label="Pending changes" className="space-y-2">
          {preview.changes.map((change) => (
            <li className="rounded-md border p-3 text-sm" key={change.signal_id}>
              <ChangeRow change={change} />
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export { ImportPreview }
