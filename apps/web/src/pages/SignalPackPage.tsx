import { type ChangeEvent, useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Select } from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import { apiErrorMessage } from "@/lib/api"
import {
  applySignalPackImport,
  exportSignalPack,
  type ExportMode,
  type ImportMode,
  type ImportRequest,
  previewSignalPackImport,
  type SignalImportDiff,
  type SignalPackImportPreview,
} from "@/lib/signalPack"

function errorMessage(error: unknown): string {
  return apiErrorMessage(error, "Something went wrong. Please try again.")
}

export function SignalPackPage() {
  return (
    <section aria-labelledby="page-title" className="space-y-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight" id="page-title">
          Import &amp; Export Signal Pack
        </h1>
        <p className="mt-2 max-w-2xl text-slate-600">
          Export your current signal configuration as a portable YAML pack, or import a pack and
          review the changes before applying. Credentials are never included.
        </p>
      </header>

      <ExportCard />
      <ImportCard />
    </section>
  )
}

function ExportCard() {
  const [mode, setMode] = useState<ExportMode>("minimal")
  const exportMutation = useMutation({ mutationFn: () => exportSignalPack(mode) })
  const [copied, setCopied] = useState(false)

  async function copy() {
    setCopied(false)
    const yaml = await exportMutation.mutateAsync()
    await navigator.clipboard?.writeText(yaml)
    setCopied(true)
  }

  async function download() {
    const yaml = await exportMutation.mutateAsync()
    const url = URL.createObjectURL(new Blob([yaml], { type: "application/yaml" }))
    const anchor = document.createElement("a")
    anchor.href = url
    anchor.download = "signal-pack.yaml"
    anchor.click()
    URL.revokeObjectURL(url)
  }

  return (
    <Card>
      <CardHeader>
        <h2 className="text-lg font-semibold">Export</h2>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="max-w-xs space-y-1.5">
          <Label htmlFor="export-mode">Pack contents</Label>
          <Select
            id="export-mode"
            onChange={(event) => setMode(event.target.value as ExportMode)}
            value={mode}
          >
            <option value="minimal">Minimal (only changes from defaults)</option>
            <option value="full">Full (every signal)</option>
          </Select>
        </div>
        <div className="flex flex-wrap gap-3">
          <Button disabled={exportMutation.isPending} onClick={() => void download()}>
            Download YAML
          </Button>
          <Button
            disabled={exportMutation.isPending}
            onClick={() => void copy()}
            variant="outline"
          >
            Copy to clipboard
          </Button>
        </div>
        {copied && (
          <p className="text-sm text-green-700" role="status">
            Copied to clipboard.
          </p>
        )}
        {exportMutation.isError && (
          <p className="text-sm text-red-700" role="alert">
            {errorMessage(exportMutation.error)}
          </p>
        )}
      </CardContent>
    </Card>
  )
}

function ImportCard() {
  const queryClient = useQueryClient()
  const [rawYaml, setRawYaml] = useState("")
  const [mode, setMode] = useState<ImportMode>("additive")

  const previewMutation = useMutation({ mutationFn: previewSignalPackImport })
  const applyMutation = useMutation({
    mutationFn: applySignalPackImport,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["signal-configs"] }),
  })

  function resetResults() {
    previewMutation.reset()
    applyMutation.reset()
  }

  function request(): ImportRequest {
    return { raw_yaml: rawYaml, mode }
  }

  function onFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) {
      return
    }
    void file.text().then((text) => {
      setRawYaml(text)
      resetResults()
    })
  }

  const preview = previewMutation.data
  const applied = applyMutation.data

  return (
    <Card>
      <CardHeader>
        <h2 className="text-lg font-semibold">Import</h2>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="import-yaml">Paste pack YAML</Label>
          <Textarea
            id="import-yaml"
            onChange={(event) => {
              setRawYaml(event.target.value)
              resetResults()
            }}
            placeholder="schema_id: emradar.dev/v1&#10;..."
            rows={10}
            value={rawYaml}
          />
        </div>

        <div className="flex flex-wrap items-end gap-4">
          <div className="space-y-1.5">
            <Label htmlFor="import-file">…or upload a file</Label>
            <input accept=".yaml,.yml" id="import-file" onChange={onFile} type="file" />
          </div>
          <div className="max-w-xs space-y-1.5">
            <Label htmlFor="import-mode">Apply mode</Label>
            <Select
              id="import-mode"
              onChange={(event) => {
                setMode(event.target.value as ImportMode)
                resetResults()
              }}
              value={mode}
            >
              <option value="additive">Additive (merge into current)</option>
              <option value="replace_all">Replace all (reset others to default)</option>
            </Select>
          </div>
        </div>

        <div className="flex flex-wrap gap-3">
          <Button
            disabled={rawYaml.trim() === "" || previewMutation.isPending}
            onClick={() => previewMutation.mutate(request())}
          >
            {previewMutation.isPending ? "Validating…" : "Preview changes"}
          </Button>
          {preview && !applied && (
            <Button
              disabled={applyMutation.isPending}
              onClick={() => applyMutation.mutate(request())}
              variant="outline"
            >
              {applyMutation.isPending ? "Applying…" : "Apply pack"}
            </Button>
          )}
        </div>

        {previewMutation.isError && (
          <p
            className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700"
            role="alert"
          >
            {errorMessage(previewMutation.error)}
          </p>
        )}
        {applyMutation.isError && (
          <p
            className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700"
            role="alert"
          >
            {errorMessage(applyMutation.error)}
          </p>
        )}

        {applied ? (
          <p
            className="rounded-md border border-green-200 bg-green-50 p-3 text-sm text-green-800"
            role="status"
          >
            Applied pack “{applied.pack_name}”.
          </p>
        ) : (
          preview && <ImportPreview preview={preview} />
        )}
      </CardContent>
    </Card>
  )
}

function ImportPreview({ preview }: { preview: SignalPackImportPreview }) {
  return (
    <div className="space-y-4" data-testid="import-preview">
      <p className="text-sm text-slate-600">
        Pack <span className="font-medium">{preview.pack_name}</span> —{" "}
        {preview.changes.length === 0
          ? "no changes from your current configuration."
          : `${preview.changes.length} signal${preview.changes.length === 1 ? "" : "s"} affected.`}
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

function ChangeRow({ change }: { change: SignalImportDiff }) {
  return (
    <div className="space-y-1">
      <p className="font-medium">{change.signal_id}</p>
      {change.enabled && (
        <p className="text-slate-600">
          {change.enabled.after ? "Enabled" : "Disabled"} (was{" "}
          {change.enabled.before ? "enabled" : "disabled"})
        </p>
      )}
      {change.severity && (
        <p className="flex items-center gap-1 text-slate-600">
          Severity:
          <Badge variant={change.severity.before}>{change.severity.before}</Badge>→
          <Badge variant={change.severity.after}>{change.severity.after}</Badge>
        </p>
      )}
      {change.params && (
        <p className="text-slate-600">
          Parameters: <code className="text-xs">{JSON.stringify(change.params.before)}</code> →{" "}
          <code className="text-xs">{JSON.stringify(change.params.after)}</code>
        </p>
      )}
    </div>
  )
}
