import { useEffect, useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "react-router-dom"

import { ConnectionForm } from "@/components/connections/ConnectionForm"
import { CodeSourcePicker } from "@/components/teams/CodeSourcePicker"
import { SignalGroupAttachList } from "@/components/teams/SignalGroupAttachList"
import { TaskBoardPicker } from "@/components/teams/TaskBoardPicker"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { apiErrorMessage } from "@/lib/api"
import { type SourceConnection } from "@/lib/connections"
import { runTeamReport } from "@/lib/reports"
import { type SignalConfigGroup } from "@/lib/signalConfigGroups"
import { createTeam, type TeamProfile } from "@/lib/teams"
import { TEAMS_KEY, useTeamSetupData } from "@/lib/teamSetup"

const DEFAULT_GROUP_NAME = "Default signals"

type Step = "gitlab" | "jira" | "sources" | "team" | "welcome"

const STEP_ORDER: Step[] = ["welcome", "jira", "gitlab", "team", "sources"]
const STEP_LABELS: Record<Step, string> = {
  welcome: "Welcome",
  jira: "Ticketing",
  gitlab: "Code",
  team: "Team",
  sources: "Sources",
}

function teamHasSources(team: TeamProfile): boolean {
  return team.scope_ids.length > 0 || team.code_connection_id !== null
}

function defaultGroupId(groups: SignalConfigGroup[]): string | undefined {
  return (groups.find((group) => group.name === DEFAULT_GROUP_NAME) ?? groups[0])?.id
}

export function SetupPage() {
  const {
    isLoading,
    teams,
    boardScopes,
    groups,
    connections,
    jiraConnections,
    codeConnections,
  } = useTeamSetupData()

  const [step, setStep] = useState<Step>("welcome")
  const [currentTeamId, setCurrentTeamId] = useState<string | null>(null)
  const [initialized, setInitialized] = useState(false)

  // Resumability: on first load, jump to the first incomplete step based on stored state.
  // Rendering is gated until this resolves so returning users never see a Welcome flash.
  useEffect(() => {
    if (initialized || isLoading) return

    if (teams.length > 0) {
      const incomplete = teams.find((team) => !teamHasSources(team)) ?? teams[teams.length - 1]
      setCurrentTeamId(incomplete.id)
      setStep("sources")
    } else if (jiraConnections.length > 0) {
      setStep("team")
    } else if (connections.length > 0) {
      setStep("jira")
    } else {
      setStep("welcome")
    }
    setInitialized(true)
  }, [initialized, isLoading, teams, jiraConnections, connections])

  const currentTeam = teams.find((team) => team.id === currentTeamId) ?? null

  return (
    <section aria-labelledby="page-title" className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight" id="page-title">
          Setup
        </h1>
        <p className="mt-2 max-w-2xl text-slate-600">
          A guided walkthrough from an empty install to a populated dashboard: connect your sources,
          create one or more teams, and give each team its task-board and code sources.
        </p>
      </header>

      <WizardProgress current={step} />

      {!initialized && <p className="text-sm text-slate-500">Loading setup...</p>}

      {initialized && step === "welcome" && <WelcomeStep onStart={() => setStep("jira")} />}

      {step === "jira" && (
        <ConnectionStep
          connections={jiraConnections}
          description="Add a named Jira connection. It is required to run work-item signals. Credentials are stored locally and shown masked."
          lockConnectorName="jira"
          onContinue={() => setStep("gitlab")}
          optional={false}
          title="Connect your ticketing source (Jira)"
        />
      )}

      {step === "gitlab" && (
        <ConnectionStep
          connections={codeConnections}
          description="Add a named GitLab connection for merge-request signals. This step is optional but recommended."
          lockConnectorName="gitlab"
          onBack={() => setStep("jira")}
          onContinue={() => setStep("team")}
          optional
          title="Connect your code source (GitLab)"
        />
      )}

      {step === "team" && (
        <TeamStep
          groups={groups}
          onBack={() => setStep("gitlab")}
          onCreated={(team) => {
            setCurrentTeamId(team.id)
            setStep("sources")
          }}
        />
      )}

      {step === "sources" && (
        <SourcesStep
          boardScopes={boardScopes}
          codeConnections={codeConnections}
          groups={groups}
          jiraConnections={jiraConnections}
          onAddAnother={() => {
            setCurrentTeamId(null)
            setStep("team")
          }}
          team={currentTeam}
        />
      )}
    </section>
  )
}

function WizardProgress({ current }: { current: Step }) {
  const currentIndex = STEP_ORDER.indexOf(current)
  return (
    <ol aria-label="Setup progress" className="flex flex-wrap gap-2 text-xs">
      {STEP_ORDER.map((step, index) => {
        const state = index < currentIndex ? "done" : index === currentIndex ? "current" : "todo"
        return (
          <li
            aria-current={state === "current" ? "step" : undefined}
            className={
              "rounded-full border px-3 py-1 font-medium " +
              (state === "current"
                ? "border-primary bg-primary text-primary-foreground"
                : state === "done"
                  ? "border-green-300 bg-green-50 text-green-800"
                  : "border-slate-200 text-slate-500")
            }
            key={step}
          >
            {index + 1}. {STEP_LABELS[step]}
          </li>
        )
      })}
    </ol>
  )
}

function WelcomeStep({ onStart }: { onStart: () => void }) {
  return (
    <Card>
      <CardContent className="space-y-4 p-6">
        <h2 className="text-lg font-semibold">Welcome to EM Radar</h2>
        <div className="space-y-2 text-sm text-slate-600">
          <p>
            EM Radar is local-first. Your data, tokens, and reports stay on this machine. There is
            no telemetry and EM Radar only reads from your sources.
          </p>
          <p>
            You will connect Jira (and optionally GitLab), then create one or more teams and give
            each a task-board and code source. Every step is saved as you go, so you can close this
            page and pick up where you left off.
          </p>
        </div>
        <Button onClick={onStart}>Get started</Button>
      </CardContent>
    </Card>
  )
}

function ConnectionStep({
  connections,
  description,
  lockConnectorName,
  onBack,
  onContinue,
  optional,
  title,
}: {
  connections: SourceConnection[]
  description: string
  lockConnectorName: string
  onBack?: () => void
  onContinue: () => void
  optional: boolean
  title: string
}) {
  const { connectors } = useTeamSetupData()
  const canContinue = optional || connections.length > 0

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="space-y-3 p-6">
          <h2 className="text-lg font-semibold">{title}</h2>
          <p className="text-sm text-slate-600">{description}</p>
          {connections.length > 0 ? (
            <ul aria-label="Saved connections" className="space-y-1 text-sm">
              {connections.map((conn) => (
                <li className="rounded-md border px-3 py-2" key={conn.id}>
                  {conn.name}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-slate-500">No connections added yet.</p>
          )}
        </CardContent>
      </Card>

      <ConnectionForm connectors={connectors} lockConnectorName={lockConnectorName} />

      <div className="flex flex-wrap gap-3">
        {onBack && (
          <Button onClick={onBack} variant="outline">
            Back
          </Button>
        )}
        <Button disabled={!canContinue} onClick={onContinue}>
          {optional && connections.length === 0 ? "Skip for now" : "Continue"}
        </Button>
      </div>
    </div>
  )
}

function TeamStep({
  groups,
  onBack,
  onCreated,
}: {
  groups: SignalConfigGroup[]
  onBack: () => void
  onCreated: (team: TeamProfile) => void
}) {
  const queryClient = useQueryClient()
  const [name, setName] = useState("")
  const createMutation = useMutation({
    mutationFn: createTeam,
    onSuccess: (team) => {
      void queryClient.invalidateQueries({ queryKey: TEAMS_KEY })
      onCreated(team)
    },
  })

  function submit() {
    const trimmed = name.trim()
    if (trimmed.length === 0) return
    const groupId = defaultGroupId(groups)
    createMutation.mutate({
      name: trimmed,
      signal_config_group_ids: groupId ? [groupId] : [],
    })
  }

  return (
    <Card>
      <CardContent className="space-y-4 p-6">
        <h2 className="text-lg font-semibold">Create a team</h2>
        <p className="text-sm text-slate-600">
          Name the team you manage. It is saved right away and you can attach its sources next. A
          team can be saved with no sources.
        </p>
        <div className="space-y-1.5">
          <Label htmlFor="wizard-team-name">Team name</Label>
          <Input
            id="wizard-team-name"
            onChange={(event) => setName(event.target.value)}
            placeholder="e.g. Payments"
            value={name}
          />
        </div>
        <div className="flex flex-wrap gap-3">
          <Button onClick={onBack} variant="outline">
            Back
          </Button>
          <Button
            disabled={createMutation.isPending || name.trim().length === 0}
            onClick={submit}
          >
            {createMutation.isPending ? "Creating..." : "Create team"}
          </Button>
        </div>
        {createMutation.isError && (
          <p className="text-sm text-red-700" role="alert">
            {apiErrorMessage(createMutation.error, "Failed to create the team. Please try again.")}
          </p>
        )}
      </CardContent>
    </Card>
  )
}

function SourcesStep({
  boardScopes,
  codeConnections,
  groups,
  jiraConnections,
  onAddAnother,
  team,
}: {
  boardScopes: Parameters<typeof TaskBoardPicker>[0]["boardScopes"]
  codeConnections: SourceConnection[]
  groups: SignalConfigGroup[]
  jiraConnections: SourceConnection[]
  onAddAnother: () => void
  team: TeamProfile | null
}) {
  const navigate = useNavigate()
  const { teams } = useTeamSetupData()

  const finishMutation = useMutation({
    mutationFn: async () => {
      for (const t of teams) {
        if (teamHasSources(t)) {
          await runTeamReport(t.id)
        }
      }
    },
    onSuccess: () => navigate("/"),
  })

  if (!team) {
    return <p className="text-sm text-slate-500">Loading team...</p>
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="space-y-4 p-6">
          <div>
            <h2 className="text-lg font-semibold">Attach sources for {team.name}</h2>
            <p className="mt-1 text-sm text-slate-600">
              Give this team a task-board source and a code source. Either can be left unset, but a
              report needs at least one. Changes are saved as you make them.
            </p>
          </div>

          <TaskBoardPicker boardScopes={boardScopes} jiraConnections={jiraConnections} team={team} />

          <CodeSourcePicker codeConnections={codeConnections} team={team} />

          <SignalGroupAttachList groups={groups} team={team} />
        </CardContent>
      </Card>

      <div className="flex flex-wrap gap-3">
        <Button onClick={onAddAnother} variant="outline">
          Add another team
        </Button>
        <Button disabled={finishMutation.isPending} onClick={() => finishMutation.mutate()}>
          {finishMutation.isPending ? "Starting sync..." : "Finish setup"}
        </Button>
      </div>
      {finishMutation.isError && (
        <p className="text-sm text-red-700" role="alert">
          {apiErrorMessage(finishMutation.error, "The initial sync failed. Please try again.")}
        </p>
      )}
    </div>
  )
}
