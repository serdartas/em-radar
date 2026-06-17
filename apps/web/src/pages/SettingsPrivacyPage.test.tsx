import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it } from "vitest"

import { SettingsPrivacyPage } from "@/pages/SettingsPrivacyPage"

afterEach(cleanup)

describe("SettingsPrivacyPage", () => {
  it("renders the local-first privacy copy", () => {
    render(<SettingsPrivacyPage />)

    expect(screen.getByRole("heading", { name: "Local-first guarantees" })).toBeInTheDocument()
    expect(screen.getByText(/never leave this machine/)).toBeInTheDocument()
  })

  it("defaults the telemetry toggle to off", () => {
    render(<SettingsPrivacyPage />)

    const toggle = screen.getByRole("switch", { name: "Enable anonymous telemetry" })
    expect(toggle).toHaveAttribute("aria-checked", "false")
  })

  it("gates destructive actions behind a confirmation affordance", () => {
    render(<SettingsPrivacyPage />)

    fireEvent.click(screen.getByRole("button", { name: "Delete report history" }))

    const dialog = screen.getByRole("alertdialog", { name: "Confirm: Delete report history" })
    expect(dialog).toBeInTheDocument()
    expect(screen.getByText(/This cannot be undone/)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Confirm delete" })).toBeDisabled()
  })
})
