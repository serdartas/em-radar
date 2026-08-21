// SPDX-License-Identifier: Apache-2.0

export type WizardStep = "gitlab" | "jira" | "sources" | "team" | "welcome"

export interface WizardProgress {
  step: WizardStep
  currentTeamId: string | null
  completed: boolean
  /**
   * High-water mark: the furthest step the user has reached in this session.
   * Only advanced on forward transitions; never decremented when the user
   * clicks Back or a completed pill. Used to keep previously-entered step
   * pills interactive across back-navigation and reloads.
   */
  furthestStep: WizardStep
}

const STORAGE_KEY = "em-radar.wizard-progress"
const STEPS: WizardStep[] = ["welcome", "jira", "gitlab", "team", "sources"]

export function loadWizardProgress(): WizardProgress | null {
  let raw: string | null
  try {
    raw = localStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
  if (!raw) return null

  try {
    const parsed: unknown = JSON.parse(raw)
    if (typeof parsed !== "object" || parsed === null) return null
    const obj = parsed as Record<string, unknown>
    if (typeof obj.step !== "string" || !STEPS.includes(obj.step as WizardStep)) return null
    // Fall back to `step` for records written before furthestStep was introduced.
    const furthestStep =
      typeof obj.furthestStep === "string" && STEPS.includes(obj.furthestStep as WizardStep)
        ? (obj.furthestStep as WizardStep)
        : (obj.step as WizardStep)
    return {
      step: obj.step as WizardStep,
      currentTeamId: typeof obj.currentTeamId === "string" ? obj.currentTeamId : null,
      completed: obj.completed === true,
      furthestStep,
    }
  } catch {
    return null
  }
}

export function saveWizardProgress(progress: WizardProgress): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(progress))
  } catch {
    // Best-effort: localStorage may be unavailable (private mode / quota).
  }
}

export function clearWizardProgress(): void {
  try {
    localStorage.removeItem(STORAGE_KEY)
  } catch {
    // Best-effort.
  }
}
