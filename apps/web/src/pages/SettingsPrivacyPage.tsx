import { useState } from "react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"

const GUARANTEES = [
  "Your source data, reports, and tokens are stored locally in EM Radar's database and never leave this machine.",
  "Telemetry is off by default. EM Radar collects no usage analytics unless you explicitly opt in.",
  "EM Radar only reads from Jira and GitLab. It never writes back to your source systems.",
]

export function SettingsPrivacyPage() {
  const [telemetryEnabled, setTelemetryEnabled] = useState(false)

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
        <CardContent className="flex items-start justify-between gap-4">
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
            id="telemetry-toggle"
            onCheckedChange={setTelemetryEnabled}
          />
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
          <DestructiveAction
            description="Removes a source connection along with the source data cached for it."
            title="Delete connection &amp; cached data"
          />
          <DestructiveAction
            description="Removes every stored report and its findings. Configuration is kept."
            title="Delete report history"
          />
        </CardContent>
      </Card>
    </section>
  )
}

interface DestructiveActionProps {
  description: string
  title: string
}

function DestructiveAction({ description, title }: DestructiveActionProps) {
  const [confirming, setConfirming] = useState(false)

  return (
    <div className="rounded-lg border p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="font-medium">{title}</p>
          <p className="mt-1 text-sm text-slate-600">{description}</p>
        </div>
        {!confirming && (
          <Button className="shrink-0" onClick={() => setConfirming(true)} variant="outline">
            {title}
          </Button>
        )}
      </div>
      {confirming && (
        <div
          className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"
          role="alertdialog"
          aria-label={`Confirm: ${title}`}
        >
          <p>This cannot be undone. Full deletion behavior is wired in a later release (M7-05).</p>
          <div className="mt-3 flex gap-2">
            <Button disabled size="sm">
              Confirm delete
            </Button>
            <Button onClick={() => setConfirming(false)} size="sm" variant="outline">
              Cancel
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
