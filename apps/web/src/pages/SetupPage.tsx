// SPDX-License-Identifier: Apache-2.0

import { useEffect, useState } from "react"
import { useIsMutating, useMutation, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "react-router-dom"

import { ConnectionForm } from "@/components/connections/ConnectionForm"
import { WizardStepFooter } from "@/components/setup/WizardStepFooter"
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
import { TEAM_SOURCE_MUTATION_KEY, TEAMS_KEY, useTeamSetupData } from "@/lib/teamSetup"
import {
  clearWizardProgress,
  loadWizardProgress,
  saveWizardProgress,
  type WizardStep,
} from "@/lib/wizardProgress"

const DEFAULT_GROUP_NAME = "Default signals"

type Step = WizardStep

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

  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [step, setStep] = useState<Step>("welcome")
  // High-water mark: only advances on forward transitions; never decremented on Back.
  // Drives pill interactivity so previously-entered steps stay clickable after back-navigation.
  const [furthestStep, setFurthestStep] = useState<Step>("welcome")
  const [currentTeamId, setCurrentTeamId] = useState<string | null>(null)
  const [initialized, setInitialized] = useState(false)

  const sourceMutating = useIsMutating({ mutationKey: TEAM_SOURCE_MUTATION_KEY })

  const finishMutation = useMutation({
    mutationFn: async () => {
      // Read authoritative team state so a source saved moments before Finish is not missed
      // due to a stale render closure or an in-flight refetch.
      await queryClient.refetchQueries({ queryKey: TEAMS_KEY })
      const fresh = queryClient.getQueryData<TeamProfile[]>(TEAMS_KEY) ?? []
      const teamsWithSources = fresh.filter(teamHasSources)
      // Run each team's initial report independently so one failure does not skip the rest.
      const results = await Promise.allSettled(
        teamsWithSources.map((team) => runTeamReport(team.id)),
      )
      const failed = results.filter(
        (result): result is PromiseRejectedResult => result.status === "rejected",
      )
      // Surface an error only when every run failed; partial failures remain visible per-team
      // on the dashboard, which the user reaches on success.
      if (teamsWithSources.length > 0 && failed.length === teamsWithSources.length) {
        throw failed[0].reason
      }
    },
    onSuccess: () => {
      saveWizardProgress({ step, currentTeamId, furthestStep, completed: true })
      navigate("/", { replace: true })
    },
  })

  // Navigate to a step. Advances the furthestStep high-water mark on forward transitions;
  // going back leaves furthestStep unchanged so previously-entered pills stay clickable.
  function goToStep(newStep: Step) {
    setStep(newStep)
    setFurthestStep((prev) =>
      STEP_ORDER.indexOf(newStep) > STEP_ORDER.indexOf(prev) ? newStep : prev,
    )
  }

  // Resumability: prefer explicit persisted wizard progress; otherwise infer from stored data.
  // Rendering is gated until this resolves so returning users never see a Welcome flash.
  useEffect(() => {
    if (initialized || isLoading) return

    const persisted = loadWizardProgress()
    if (persisted?.completed) {
      // A completed marker with teams present means onboarding is done; leave the wizard.
      // With no teams (all deleted) the marker is stale, so drop it and restart onboarding.
      if (teams.length > 0) {
        navigate("/", { replace: true })
        return
      }
      clearWizardProgress()
    } else if (persisted) {
      const teamValid =
        persisted.currentTeamId !== null && teams.some((team) => team.id === persisted.currentTeamId)
      const canResume = persisted.step !== "sources" || teamValid
      if (canResume) {
        setStep(persisted.step)
        setFurthestStep(persisted.furthestStep)
        setCurrentTeamId(teamValid ? persisted.currentTeamId : null)
        setInitialized(true)
        return
      }
    }

    // Heuristic fallback: infer the right entry point from stored data.
    if (teams.length > 0) {
      const incomplete = teams.find((team) => !teamHasSources(team)) ?? teams[teams.length - 1]
      setCurrentTeamId(incomplete.id)
      setStep("sources")
      setFurthestStep("sources")
    } else if (jiraConnections.length > 0) {
      setStep("team")
      setFurthestStep("team")
    } else if (connections.length > 0) {
      setStep("jira")
      setFurthestStep("jira")
    } else {
      setStep("welcome")
      setFurthestStep("welcome")
    }
    setInitialized(true)
  }, [initialized, isLoading, teams, jiraConnections, connections, navigate])

  // Persist each transition so closing the browser mid-wizard resumes at the right step.
  useEffect(() => {
    if (!initialized || finishMutation.isSuccess) return
    saveWizardProgress({ step, currentTeamId, furthestStep, completed: false })
  }, [initialized, step, currentTeamId, furthestStep, finishMutation.isSuccess])

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

      <WizardProgress
        current={step}
        furthestStep={furthestStep}
        onGoToStep={goToStep}
        sourcesReachable={currentTeamId !== null}
      />

      {!initialized && <p className="text-sm text-slate-500">Loading setup...</p>}

      {initialized && step === "welcome" && <WelcomeStep onStart={() => goToStep("jira")} />}

      {step === "jira" && (
        <ConnectionStep
          connections={jiraConnections}
          description="Add a named Jira connection. It is required to run work-item signals. Credentials are stored locally and shown masked."
          lockConnectorName="jira"
          onBack={() => goToStep("welcome")}
          onContinue={() => goToStep("gitlab")}
          optional={false}
          title="Connect your ticketing source (Jira)"
        />
      )}

      {step === "gitlab" && (
        <ConnectionStep
          connections={codeConnections}
          description="Add a named GitLab connection for merge-request signals. This step is optional but recommended."
          lockConnectorName="gitlab"
          onBack={() => goToStep("jira")}
          onContinue={() => goToStep("team")}
          optional
          title="Connect your code source (GitLab)"
        />
      )}

      {step === "team" && (
        <TeamStep
          groups={groups}
          onBack={() => goToStep("gitlab")}
          onCreated={(team) => {
            setCurrentTeamId(team.id)
            goToStep("sources")
          }}
        />
      )}

      {step === "sources" && (
        <SourcesStep
          boardScopes={boardScopes}
          busy={sourceMutating > 0}
          codeConnections={codeConnections}
          finishError={finishMutation.isError ? finishMutation.error : null}
          finishPending={finishMutation.isPending}
          groups={groups}
          jiraConnections={jiraConnections}
          onAddAnother={() => {
            // Starting a fresh team context: Sources is no longer reachable until a new
            // team is created, so reset the high-water mark back to "team".
            setCurrentTeamId(null)
            setStep("team")
            setFurthestStep("team")
          }}
          onBack={() => goToStep("team")}
          onFinish={() => finishMutation.mutate()}
          team={currentTeam}
        />
      )}
    </section>
  )
}

// ---------------------------------------------------------------------------
// WizardProgress
// ---------------------------------------------------------------------------

function WizardProgress({
  current,
  furthestStep,
  onGoToStep,
  sourcesReachable,
}: {
  current: Step
  furthestStep: Step
  onGoToStep: (step: Step) => void
  /** False when currentTeamId is null; prevents the Sources pill from being
   *  interactive even if furthestStep covers it, avoiding a null-team render. */
  sourcesReachable: boolean
}) {
  const currentIndex = STEP_ORDER.indexOf(current)
  const furthestIndex = STEP_ORDER.indexOf(furthestStep)

  return (
    <ol aria-label="Setup progress" className="flex flex-wrap gap-2 text-xs">
      {STEP_ORDER.map((step, index) => {
        const isCurrent = index === currentIndex
        // A step is "done" (previously entered, clickable) when its index is at or before
        // the furthest step reached AND it is not the current step. The Sources step also
        // requires a selected team so clicking it never opens SourcesStep with team === null.
        const isStepReachable = step !== "sources" || sourcesReachable
        const isDone = !isCurrent && index <= furthestIndex && isStepReachable
        const label = `${index + 1}. ${STEP_LABELS[step]}`

        if (isCurrent) {
          return (
            <li
              aria-current="step"
              className="rounded-full border border-primary bg-primary px-3 py-1 font-medium text-primary-foreground"
              key={step}
            >
              {label}
            </li>
          )
        }

        if (isDone) {
          return (
            <li key={step}>
              <button
                className="rounded-full border border-green-300 bg-green-50 px-3 py-1 font-medium text-green-800 hover:bg-green-100"
                onClick={() => onGoToStep(step)}
                type="button"
              >
                {label}
              </button>
            </li>
          )
        }

        // Future / not yet reached: non-interactive, visually de-emphasised.
        return (
          <li
            className="rounded-full border border-slate-200 px-3 py-1 font-medium text-slate-400 opacity-50"
            key={step}
          >
            {label}
          </li>
        )
      })}
    </ol>
  )
}

// ---------------------------------------------------------------------------
// WelcomeStep
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// ConnectionStep
// ---------------------------------------------------------------------------

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
  const successMessage =
    connections.length > 0
      ? `${connections.length === 1 ? "Connection" : `${connections.length} connections`} saved. Ready to continue.`
      : undefined

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

      <WizardStepFooter
        onBack={onBack}
        onPrimary={onContinue}
        primaryDisabled={!canContinue}
        primaryLabel={optional && connections.length === 0 ? "Skip for now" : "Continue"}
        successMessage={successMessage}
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// TeamStep
// ---------------------------------------------------------------------------

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
        <WizardStepFooter
          onBack={onBack}
          onPrimary={submit}
          primaryDisabled={createMutation.isPending || name.trim().length === 0}
          primaryLabel={createMutation.isPending ? "Creating..." : "Create team"}
        />
        {createMutation.isError && (
          <p className="text-sm text-red-700" role="alert">
            {apiErrorMessage(createMutation.error, "Failed to create the team. Please try again.")}
          </p>
        )}
      </CardContent>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// SourcesStep
// ---------------------------------------------------------------------------

function SourcesStep({
  boardScopes,
  busy,
  codeConnections,
  finishError,
  finishPending,
  groups,
  jiraConnections,
  onAddAnother,
  onBack,
  onFinish,
  team,
}: {
  boardScopes: Parameters<typeof TaskBoardPicker>[0]["boardScopes"]
  busy: boolean
  codeConnections: SourceConnection[]
  finishError: unknown
  finishPending: boolean
  groups: SignalConfigGroup[]
  jiraConnections: SourceConnection[]
  onAddAnother: () => void
  onBack: () => void
  onFinish: () => void
  team: TeamProfile | null
}) {
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

      <WizardStepFooter
        onBack={onBack}
        onPrimary={onFinish}
        primaryDisabled={busy || finishPending}
        primaryLabel={finishPending ? "Starting sync..." : busy ? "Saving sources..." : "Finish setup"}
        secondaryActions={
          <Button disabled={busy || finishPending} onClick={onAddAnother} variant="outline">
            Add another team
          </Button>
        }
      />
      {finishError !== null && (
        <p className="text-sm text-red-700" role="alert">
          {apiErrorMessage(finishError, "The initial sync failed. Please try again.")}
        </p>
      )}
    </div>
  )
}
