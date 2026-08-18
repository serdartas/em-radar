// SPDX-License-Identifier: Apache-2.0

import { type ChangeEvent, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Select } from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import { apiErrorMessage } from "@/lib/api"
import { listSignalConfigGroups } from "@/lib/signalConfigGroups"
import {
  applySignalPackImport,
  type ConflictMode,
  exportSignalGroupsPack,
  type ImportRequest,
  previewSignalPackImport,
  type SignalImportDiff,
  type SignalPackImportPreview,
} from "@/lib/signalPack"

type GroupExportType = "private_backup" | "public_template"

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
          Export one or more signal config groups as a portable YAML pack, or import a pack and
          review the changes before applying. Credentials are never included.
        </p>
      </header>

      <ExportCard />
      <ImportCard />
    </section>
  )
}

function ExportCard() {
  const groupsQuery = useQuery({
    queryKey: ["signal-config-groups"],
    queryFn: listSignalConfigGroups,
  })
  const [exportType, setExportType] = useState<GroupExportType>("private_backup")
  const [selected, setSelected] = useState<string[]>([])
  const [copied, setCopied] = useState(false)
  const exportMutation = useMutation({
    mutationFn: () => exportSignalGroupsPack(selected, exportType),
  })

  function toggle(groupId: string) {
    setCopied(false)
    setSelected((prev) =>
      prev.includes(groupId) ? prev.filter((id) => id !== groupId) : [...prev, groupId],
    )
  }

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

  const groups = groupsQuery.data ?? []
  const disabled = selected.length === 0 || exportMutation.isPending

  return (
    <Card>
      <CardHeader>
        <h2 className="text-lg font-semibold">Export</h2>
      </CardHeader>
      <CardContent className="space-y-4">
        <fieldset className="space-y-2">
          <legend className="text-sm font-medium text-foreground">Signal config groups</legend>
          {groups.length === 0 ? (
            <p className="text-sm text-slate-500">No signal config groups to export yet.</p>
          ) : (
            <ul className="space-y-1.5">
              {groups.map((group) => (
                <li className="flex items-center gap-2" key={group.id}>
                  <input
                    checked={selected.includes(group.id)}
                    id={`export-group-${group.id}`}
                    onChange={() => toggle(group.id)}
                    type="checkbox"
                  />
                  <Label htmlFor={`export-group-${group.id}`}>{group.name}</Label>
                </li>
              ))}
            </ul>
          )}
        </fieldset>

        <div className="max-w-xs space-y-1.5">
          <Label htmlFor="export-type">Export mode</Label>
          <Select
            id="export-type"
            onChange={(event) => setExportType(event.target.value as GroupExportType)}
            value={exportType}
          >
            <option value="private_backup">Private backup / migration</option>
            <option value="public_template">Public template</option>
          </Select>
        </div>

        <div className="flex flex-wrap gap-3">
          <Button disabled={disabled} onClick={() => void download()}>
            Download YAML
          </Button>
          <Button disabled={disabled} onClick={() => void copy()} variant="outline">
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

  const previewMutation = useMutation({ mutationFn: previewSignalPackImport })
  const applyMutation = useMutation({
    mutationFn: applySignalPackImport,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["signal-definitions"] })
      void queryClient.invalidateQueries({ queryKey: ["signal-config-groups"] })
    },
  })

  function resetResults() {
    previewMutation.reset()
    applyMutation.reset()
  }

  function request(conflict: ConflictMode): ImportRequest {
    return { raw_yaml: rawYaml, mode: "additive", conflict }
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
  const clashes = preview
    ? [...(preview.signal_name_clashes ?? []), ...(preview.group_name_clashes ?? [])]
    : []

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
            placeholder="apiVersion: emradar.dev/v1&#10;..."
            rows={10}
            value={rawYaml}
          />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="import-file">…or upload a file</Label>
          <input accept=".yaml,.yml" id="import-file" onChange={onFile} type="file" />
        </div>

        <div className="flex flex-wrap gap-3">
          <Button
            disabled={rawYaml.trim() === "" || previewMutation.isPending}
            onClick={() => previewMutation.mutate(request("keep_both"))}
          >
            {previewMutation.isPending ? "Validating…" : "Preview changes"}
          </Button>
          {preview && !applied && clashes.length === 0 && (
            <Button
              disabled={applyMutation.isPending}
              onClick={() => applyMutation.mutate(request("keep_both"))}
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
          preview && (
            <>
              <ImportPreview preview={preview} />
              {clashes.length > 0 && (
                <ConflictResolver
                  clashes={clashes}
                  onChoose={(conflict) => {
                    if (conflict === "cancel") {
                      resetResults()
                      return
                    }
                    applyMutation.mutate(request(conflict))
                  }}
                  pending={applyMutation.isPending}
                />
              )}
            </>
          )
        )}
      </CardContent>
    </Card>
  )
}

function ConflictResolver({
  clashes,
  onChoose,
  pending,
}: {
  clashes: string[]
  onChoose: (conflict: ConflictMode) => void
  pending: boolean
}) {
  return (
    <div
      className="space-y-3 rounded-md border border-amber-200 bg-amber-50 p-3"
      data-testid="conflict-resolver"
    >
      <p className="text-sm text-amber-900">
        {clashes.length} item{clashes.length === 1 ? "" : "s"} already exist with the same name:{" "}
        <span className="font-medium">{clashes.join(", ")}</span>. Choose how to apply the import.
      </p>
      <div className="flex flex-wrap gap-2">
        <Button disabled={pending} onClick={() => onChoose("skip")} size="sm" variant="outline">
          Skip
        </Button>
        <Button disabled={pending} onClick={() => onChoose("overwrite")} size="sm" variant="outline">
          Overwrite
        </Button>
        <Button disabled={pending} onClick={() => onChoose("keep_both")} size="sm" variant="outline">
          Keep both
        </Button>
        <Button disabled={pending} onClick={() => onChoose("cancel")} size="sm" variant="outline">
          Cancel
        </Button>
      </div>
    </div>
  )
}

function ImportPreview({ preview }: { preview: SignalPackImportPreview }) {
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
