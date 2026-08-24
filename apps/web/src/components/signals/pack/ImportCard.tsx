// SPDX-License-Identifier: Apache-2.0

import { type ChangeEvent, useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { ConflictResolver } from "@/components/signals/pack/ConflictResolver"
import { ImportPreview } from "@/components/signals/pack/ImportPreview"
import { apiErrorMessage } from "@/lib/api"
import {
  applySignalPackImport,
  type ConflictMode,
  type ImportRequest,
  previewSignalPackImport,
} from "@/lib/signalPack"

function errorMessage(error: unknown): string {
  return apiErrorMessage(error, "Something went wrong. Please try again.")
}

function ImportCard() {
  const queryClient = useQueryClient()
  const [rawYaml, setRawYaml] = useState("")
  const [fileError, setFileError] = useState<string | null>(null)

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
    const input = event.target
    const file = input.files?.[0]
    if (!file) {
      return
    }
    setFileError(null)
    file
      .text()
      .then((text) => {
        setRawYaml(text)
        resetResults()
      })
      .catch(() => {
        setFileError("Could not read the selected file. Please try again.")
      })
      .finally(() => {
        // Reset so selecting the same file again refires the change event.
        input.value = ""
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
          {fileError && (
            <p className="text-sm text-red-700" role="alert">
              {fileError}
            </p>
          )}
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
            Applied pack &ldquo;{applied.pack_name}&rdquo;.
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

export { ImportCard }
