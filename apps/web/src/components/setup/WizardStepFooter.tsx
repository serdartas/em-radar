// SPDX-License-Identifier: Apache-2.0

import type { ReactNode } from "react"

import { Button } from "@/components/ui/button"

interface WizardStepFooterProps {
  /**
   * When provided, renders an outlined Back button on the left.
   * Omit on the first (Welcome) step — there is nowhere to go back to.
   */
  onBack?: () => void
  /** Primary action label (e.g. "Continue", "Create team", "Finish setup"). */
  primaryLabel: string
  /** Called when the primary button is clicked. */
  onPrimary: () => void
  /** Disables the primary button while data is loading or requirements are unmet. */
  primaryDisabled?: boolean
  /**
   * Optional de-emphasised secondary actions rendered between Back and the primary
   * button (e.g. an "Add another team" outline button).
   */
  secondaryActions?: ReactNode
  /**
   * Optional feedback message displayed above the button row when the step's
   * requirement is met, pointing the user toward the next step.
   */
  successMessage?: string
}

export function WizardStepFooter({
  onBack,
  primaryLabel,
  onPrimary,
  primaryDisabled = false,
  secondaryActions,
  successMessage,
}: WizardStepFooterProps) {
  return (
    <div className="space-y-3">
      {successMessage && (
        <p className="text-sm text-green-700" role="status">
          {successMessage}
        </p>
      )}
      <div className="flex flex-wrap gap-3">
        {onBack && (
          <Button onClick={onBack} variant="outline">
            Back
          </Button>
        )}
        {secondaryActions}
        <Button disabled={primaryDisabled} onClick={onPrimary}>
          {primaryLabel}
        </Button>
      </div>
    </div>
  )
}
