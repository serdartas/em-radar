import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it } from "vitest"

import { InfoTooltip } from "@/components/ui/info-tooltip"

afterEach(cleanup)

describe("InfoTooltip", () => {
  it("toggles the help panel on click", () => {
    render(<InfoTooltip label="About Token">Token help text</InfoTooltip>)

    const button = screen.getByRole("button", { name: "About Token" })
    expect(button).toHaveAttribute("aria-expanded", "false")
    expect(screen.queryByText("Token help text")).not.toBeInTheDocument()

    fireEvent.click(button)
    expect(button).toHaveAttribute("aria-expanded", "true")
    expect(screen.getByText("Token help text")).toBeInTheDocument()

    fireEvent.click(button)
    expect(button).toHaveAttribute("aria-expanded", "false")
    expect(screen.queryByText("Token help text")).not.toBeInTheDocument()
  })

  it("closes the panel on Escape", () => {
    render(<InfoTooltip label="About Token">Token help text</InfoTooltip>)

    fireEvent.click(screen.getByRole("button", { name: "About Token" }))
    expect(screen.getByText("Token help text")).toBeInTheDocument()

    fireEvent.keyDown(document, { key: "Escape" })
    expect(screen.queryByText("Token help text")).not.toBeInTheDocument()
  })
})
