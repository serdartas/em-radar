import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link } from "react-router-dom"

import { SchemaForm } from "@/components/SchemaForm"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Select } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import {
  listSignalConfigs,
  resetAllSignalConfigs,
  resetSignalConfig,
  type SignalConfig,
  type SignalConfigPatch,
  updateSignalConfig,
} from "@/lib/signalConfigs"
import { SEVERITIES, type Severity } from "@/lib/severity"

type Drafts = Record<string, SignalConfigPatch>

function toDraft(config: SignalConfig): SignalConfigPatch {
  return {
    enabled: config.enabled,
    severity_override: config.severity_override,
    params: config.params,
  }
}

function buildDrafts(configs: SignalConfig[]): Drafts {
  return Object.fromEntries(configs.map((config) => [config.signal_id, toDraft(config)]))
}

export function SignalSettingsPage() {
  const queryClient = useQueryClient()
  const query = useQuery({ queryKey: ["signal-configs"], queryFn: listSignalConfigs })
  const [drafts, setDrafts] = useState<Drafts | null>(null)

  useEffect(() => {
    if (query.data && drafts === null) {
      setDrafts(buildDrafts(query.data))
    }
  }, [query.data, drafts])

  const resetAllMutation = useMutation({
    mutationFn: resetAllSignalConfigs,
    onSuccess: (configs) => {
      setDrafts(buildDrafts(configs))
      queryClient.setQueryData(["signal-configs"], configs)
    },
  })

  function setDraft(signalId: string, next: SignalConfigPatch) {
    setDrafts((current) => ({ ...(current ?? {}), [signalId]: next }))
  }

  if (query.isLoading || drafts === null) {
    return (
      <section aria-labelledby="page-title">
        <SignalSettingsHeader onResetAll={() => undefined} resetAllPending={false} />
        <p className="mt-8 text-sm text-slate-500">Loading signals…</p>
      </section>
    )
  }

  if (query.isError || !query.data) {
    return (
      <section aria-labelledby="page-title">
        <SignalSettingsHeader onResetAll={() => undefined} resetAllPending={false} />
        <p className="mt-8 text-sm text-red-700" role="alert">
          Signals could not be loaded.
        </p>
      </section>
    )
  }

  return (
    <section aria-labelledby="page-title" className="space-y-6">
      <SignalSettingsHeader
        onResetAll={() => {
          if (window.confirm("Reset all signals to their defaults?")) {
            resetAllMutation.mutate()
          }
        }}
        resetAllPending={resetAllMutation.isPending}
      />

      <ul aria-label="Signals" className="space-y-3">
        {query.data.map((config) => (
          <SignalRow
            config={config}
            draft={drafts[config.signal_id]}
            key={config.signal_id}
            onDraftChange={(next) => setDraft(config.signal_id, next)}
          />
        ))}
      </ul>
    </section>
  )
}

interface SignalSettingsHeaderProps {
  onResetAll: () => void
  resetAllPending: boolean
}

function SignalSettingsHeader({ onResetAll, resetAllPending }: SignalSettingsHeaderProps) {
  return (
    <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight" id="page-title">
          Signal Settings
        </h1>
        <p className="mt-2 max-w-2xl text-slate-600">
          Enable or disable signals, tune their thresholds, and override severities. Changes drive
          the next report run.
        </p>
      </div>
      <div className="flex flex-wrap gap-3">
        <Button asChild variant="outline">
          <Link to="/signals/import-export">Import / export pack</Link>
        </Button>
        <Button disabled={resetAllPending} onClick={onResetAll} variant="outline">
          Reset all to defaults
        </Button>
      </div>
    </header>
  )
}

interface SignalRowProps {
  config: SignalConfig
  draft: SignalConfigPatch
  onDraftChange: (next: SignalConfigPatch) => void
}

function SignalRow({ config, draft, onDraftChange }: SignalRowProps) {
  const saveMutation = useMutation({
    mutationFn: () => updateSignalConfig(config.signal_id, draft),
    onSuccess: (updated) => onDraftChange(toDraft(updated)),
  })
  const resetMutation = useMutation({
    mutationFn: () => resetSignalConfig(config.signal_id),
    onSuccess: (reset) => onDraftChange(toDraft(reset)),
  })

  const hasParams = Object.keys(config.params_schema.properties ?? {}).length > 0
  const effectiveSeverity = draft.severity_override ?? config.default_severity

  return (
    <li>
      <Card>
        <CardContent className="space-y-4 p-5">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <h3 className="font-semibold">{config.name}</h3>
              <p className="mt-1 text-sm text-slate-600">{config.description}</p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <Badge variant={effectiveSeverity}>{effectiveSeverity}</Badge>
              <Switch
                aria-label={`Enable ${config.name}`}
                checked={draft.enabled}
                onCheckedChange={(enabled) => onDraftChange({ ...draft, enabled })}
              />
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor={`${config.signal_id}-severity`}>Severity</Label>
              <Select
                id={`${config.signal_id}-severity`}
                onChange={(event) =>
                  onDraftChange({
                    ...draft,
                    severity_override:
                      event.target.value === "" ? null : (event.target.value as Severity),
                  })
                }
                value={draft.severity_override ?? ""}
              >
                <option value="">Default ({config.default_severity})</option>
                {SEVERITIES.map((severity) => (
                  <option key={severity} value={severity}>
                    {severity}
                  </option>
                ))}
              </Select>
            </div>
          </div>

          {hasParams && (
            <SchemaForm
              idPrefix={config.signal_id}
              onChange={(key, value) =>
                onDraftChange({ ...draft, params: { ...draft.params, [key]: value } })
              }
              schema={config.params_schema}
              values={draft.params}
            />
          )}

          <div className="flex flex-wrap gap-3">
            <Button disabled={saveMutation.isPending} onClick={() => saveMutation.mutate()} size="sm">
              {saveMutation.isPending ? "Saving…" : "Save"}
            </Button>
            <Button
              disabled={resetMutation.isPending}
              onClick={() => resetMutation.mutate()}
              size="sm"
              variant="outline"
            >
              Reset to default
            </Button>
          </div>
        </CardContent>
      </Card>
    </li>
  )
}
