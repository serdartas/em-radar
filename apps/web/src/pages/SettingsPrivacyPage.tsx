// SPDX-License-Identifier: Apache-2.0

import { useState } from "react"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { ConnectionDeleteConfirm } from "@/components/connections/ConnectionDeleteConfirm"
import { Button } from "@/components/ui/button"
import { Callout } from "@/components/ui/callout"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { listConnections, type SourceConnection } from "@/lib/connections"
import { deleteReportHistory } from "@/lib/reports"
import { getSettings, updateSettings } from "@/lib/settings"

const GUARANTEES = [
  "Your source data, reports, and tokens are stored locally in EM Radar's database and never leave this machine.",
  "Telemetry is off by default. EM Radar collects no usage analytics unless you explicitly opt in.",
  "EM Radar only reads from Jira and GitLab. It never writes back to your source systems.",
]

export function SettingsPrivacyPage() {
  const queryClient = useQueryClient()
  const settingsQuery = useQuery({ queryKey: ["settings"], queryFn: getSettings })
  const telemetryEnabled = settingsQuery.data?.telemetry_enabled ?? false

  const telemetryMutation = useMutation({
    mutationFn: (value: boolean) => updateSettings({ telemetry_enabled: value }),
    onSuccess: (data) => {
      queryClient.setQueryData(["settings"], data)
    },
  })

  return (
    <section aria-labelledby="page-title" className="space-y-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight" id="page-title">
          Settings &amp; Privacy
        </h1>
        <p className="mt-2 max-w-2xl text-slate-600">
          EM Radar is local-first by design. Here is exactly what that means and how to manage your
          data.
        </p>
      </header>

      <Card>
        <CardHeader>
          <h2 className="text-lg font-semibold">Local-first guarantees</h2>
        </CardHeader>
        <CardContent>
          <ul className="space-y-3 text-sm text-slate-600">
            {GUARANTEES.map((guarantee) => (
              <li className="flex gap-2" key={guarantee}>
                <span aria-hidden="true" className="mt-0.5 text-green-600">
                  ✓
                </span>
                <span>{guarantee}</span>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <h2 className="text-lg font-semibold">Telemetry</h2>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-start justify-between gap-4">
            <div>
              <Label htmlFor="telemetry-toggle">Enable anonymous telemetry</Label>
              <p className="mt-1 text-sm text-slate-600">
                Off by default. When enabled, EM Radar may send anonymous, non-identifying usage
                metrics. No source data or tokens are ever included.
              </p>
            </div>
            <Switch
              aria-label="Enable anonymous telemetry"
              checked={telemetryEnabled}
              disabled={!settingsQuery.isSuccess || telemetryMutation.isPending}
              id="telemetry-toggle"
              onCheckedChange={(value) => telemetryMutation.mutate(value)}
            />
          </div>
          {settingsQuery.isError && (
            <Callout role="alert" variant="error">
              Could not load settings. Reload the page to try again.
            </Callout>
          )}
          {telemetryMutation.isError && (
            <Callout role="alert" variant="error">
              Could not update the telemetry setting. Try again.
            </Callout>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <h2 className="text-lg font-semibold">Data management</h2>
          <p className="text-sm text-slate-600">
            These actions permanently remove local data. They require confirmation and never touch
            your source systems.
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          <DeleteConnectionSection />
          <DeleteReportHistoryAction />
        </CardContent>
      </Card>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Delete connection section
// ---------------------------------------------------------------------------

function DeleteConnectionSection() {
  const connectionsQuery = useQuery({ queryKey: ["connections"], queryFn: listConnections })
  const connections = connectionsQuery.data ?? []

  if (connectionsQuery.isLoading) {
    return (
      <div className="rounded-lg border p-4 text-sm text-slate-500">
        Loading connections&hellip;
      </div>
    )
  }

  if (connections.length === 0) {
    return (
      <div className="rounded-lg border p-4">
        <p className="font-medium">Delete connection &amp; cached data</p>
        <p className="mt-1 text-sm text-slate-600">No connections configured.</p>
      </div>
    )
  }

  return (
    <div className="rounded-lg border p-4">
      <p className="font-medium">Delete connection &amp; cached data</p>
      <p className="mt-1 text-sm text-slate-600">
        Removes a source connection along with the source data cached for it.
      </p>
      <ul className="mt-3 space-y-2">
        {connections.map((conn) => (
          <DeleteConnectionItem connection={conn} key={conn.id} />
        ))}
      </ul>
    </div>
  )
}

interface DeleteConnectionItemProps {
  connection: SourceConnection
}

function DeleteConnectionItem({ connection }: DeleteConnectionItemProps) {
  const queryClient = useQueryClient()
  const [confirming, setConfirming] = useState(false)

  return (
    <li className="rounded-md border px-3 py-2">
      <div className="flex items-center justify-between gap-4">
        <div>
          <span className="text-sm font-medium">{connection.name}</span>
          <span className="ml-2 text-xs text-slate-500">{connection.connector_name}</span>
        </div>
        {!confirming && (
          <Button onClick={() => setConfirming(true)} size="sm" variant="outline">
            Delete
          </Button>
        )}
      </div>

      {confirming && (
        <ConnectionDeleteConfirm
          className="mt-3"
          connectionId={connection.id}
          connectionName={connection.name}
          onCancel={() => setConfirming(false)}
          onDeleted={() => {
            void queryClient.invalidateQueries({ queryKey: ["connections"] })
            void queryClient.invalidateQueries({ queryKey: ["teams"] })
            setConfirming(false)
          }}
        />
      )}
    </li>
  )
}

// ---------------------------------------------------------------------------
// Delete report history action
// ---------------------------------------------------------------------------

function DeleteReportHistoryAction() {
  const queryClient = useQueryClient()
  const [confirming, setConfirming] = useState(false)

  const deleteMutation = useMutation({
    mutationFn: () => deleteReportHistory(),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["reports"] })
      setConfirming(false)
    },
  })

  return (
    <div className="rounded-lg border p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="font-medium">Delete report history</p>
          <p className="mt-1 text-sm text-slate-600">
            Removes every stored report and its findings. Configuration is kept.
          </p>
        </div>
        {!confirming && (
          <Button className="shrink-0" onClick={() => setConfirming(true)} variant="outline">
            Delete report history
          </Button>
        )}
      </div>
      {confirming && (
        <div
          aria-label="Confirm: Delete report history"
          className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"
          role="alertdialog"
        >
          <p>This cannot be undone. All report history and findings will be permanently removed.</p>
          <div className="mt-3 flex gap-2">
            <Button
              disabled={deleteMutation.isPending}
              onClick={() => deleteMutation.mutate()}
              size="sm"
            >
              Confirm delete
            </Button>
            <Button onClick={() => setConfirming(false)} size="sm" variant="outline">
              Cancel
            </Button>
          </div>
          {deleteMutation.isError && (
            <Callout className="mt-3" role="alert" variant="error">
              Could not delete report history. Please try again.
            </Callout>
          )}
        </div>
      )}
    </div>
  )
}
