// SPDX-License-Identifier: Apache-2.0

import { useState } from "react"
import { useMutation, useQuery } from "@tanstack/react-query"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Label } from "@/components/ui/label"
import { Select } from "@/components/ui/select"
import { apiErrorMessage } from "@/lib/api"
import { listSignalConfigGroups } from "@/lib/signalConfigGroups"
import { exportSignalGroupsPack } from "@/lib/signalPack"

type GroupExportType = "private_backup" | "public_template"

function errorMessage(error: unknown): string {
  return apiErrorMessage(error, "Something went wrong. Please try again.")
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
                  <Checkbox
                    checked={selected.includes(group.id)}
                    id={`export-group-${group.id}`}
                    onChange={() => toggle(group.id)}
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

export { ExportCard }
