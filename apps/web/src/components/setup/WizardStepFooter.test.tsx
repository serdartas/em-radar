// SPDX-License-Identifier: Apache-2.0

import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { WizardStepFooter } from "@/components/setup/WizardStepFooter"

afterEach(cleanup)

describe("WizardStepFooter", () => {
  it("renders the primary action button", () => {
    render(
      <WizardStepFooter onPrimary={vi.fn()} primaryLabel="Continue" />,
    )
    expect(screen.getByRole("button", { name: "Continue" })).toBeInTheDocument()
  })

  it("does NOT render a Back button when onBack is omitted (Welcome scenario)", () => {
    render(
      <WizardStepFooter onPrimary={vi.fn()} primaryLabel="Get started" />,
    )
    expect(screen.queryByRole("button", { name: "Back" })).not.toBeInTheDocument()
  })

  it("renders a Back button when onBack is provided (non-Welcome steps)", () => {
    render(
      <WizardStepFooter onBack={vi.fn()} onPrimary={vi.fn()} primaryLabel="Continue" />,
    )
    expect(screen.getByRole("button", { name: "Back" })).toBeInTheDocument()
  })

  it("calls onBack when the Back button is clicked", () => {
    const onBack = vi.fn()
    render(
      <WizardStepFooter onBack={onBack} onPrimary={vi.fn()} primaryLabel="Continue" />,
    )
    fireEvent.click(screen.getByRole("button", { name: "Back" }))
    expect(onBack).toHaveBeenCalledOnce()
  })

  it("calls onPrimary when the primary button is clicked", () => {
    const onPrimary = vi.fn()
    render(
      <WizardStepFooter onPrimary={onPrimary} primaryLabel="Continue" />,
    )
    fireEvent.click(screen.getByRole("button", { name: "Continue" }))
    expect(onPrimary).toHaveBeenCalledOnce()
  })

  it("disables the primary button when primaryDisabled is true", () => {
    render(
      <WizardStepFooter onPrimary={vi.fn()} primaryDisabled primaryLabel="Continue" />,
    )
    expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled()
  })

  it("renders secondary actions between Back and the primary button", () => {
    render(
      <WizardStepFooter
        onBack={vi.fn()}
        onPrimary={vi.fn()}
        primaryLabel="Finish setup"
        secondaryActions={<button type="button">Add another team</button>}
      />,
    )
    expect(screen.getByRole("button", { name: "Add another team" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Back" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Finish setup" })).toBeInTheDocument()
  })

  it("shows the success message when provided", () => {
    render(
      <WizardStepFooter
        onPrimary={vi.fn()}
        primaryLabel="Continue"
        successMessage="Connection saved. Ready to continue."
      />,
    )
    expect(screen.getByText("Connection saved. Ready to continue.")).toBeInTheDocument()
  })

  it("does not show a success message when the prop is omitted", () => {
    render(
      <WizardStepFooter onPrimary={vi.fn()} primaryLabel="Continue" />,
    )
    expect(screen.queryByRole("status")).not.toBeInTheDocument()
  })
})
