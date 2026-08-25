// SPDX-License-Identifier: Apache-2.0

import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { MemoryRouter } from "react-router-dom"

import { AppLayout } from "@/components/layout/AppLayout"

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  localStorage.clear()
})

function renderLayout() {
  return render(
    <MemoryRouter>
      <AppLayout />
    </MemoryRouter>,
  )
}

describe("PrimaryNav — Setup item visibility", () => {
  it("shows the Setup nav item when wizard is not completed", () => {
    renderLayout()
    expect(screen.getByRole("link", { name: /setup/i })).toBeInTheDocument()
  })

  it("shows the Setup nav item when localStorage has no wizard progress", () => {
    localStorage.clear()
    renderLayout()
    expect(screen.getByRole("link", { name: /setup/i })).toBeInTheDocument()
  })

  it("hides the Setup nav item when wizard completed flag is true", () => {
    localStorage.setItem(
      "em-radar.wizard-progress",
      JSON.stringify({ step: "sources", currentTeamId: null, completed: true, furthestStep: "sources" }),
    )
    renderLayout()
    const setupLink = screen.queryByRole("link", { name: /^setup$/i })
    expect(setupLink).not.toBeInTheDocument()
  })

  it("shows the Setup nav item when completed flag is false", () => {
    localStorage.setItem(
      "em-radar.wizard-progress",
      JSON.stringify({ step: "welcome", currentTeamId: null, completed: false, furthestStep: "welcome" }),
    )
    renderLayout()
    expect(screen.getByRole("link", { name: /^setup$/i })).toBeInTheDocument()
  })
})
