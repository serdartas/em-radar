import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, describe, expect, it } from "vitest"

import { AppRoutes } from "@/AppRoutes"
import { navItems } from "@/lib/navigation"

function renderApp(path = "/") {
  const queryClient = new QueryClient()

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

afterEach(cleanup)

describe("App shell routing", () => {
  it("renders a primary navigation link for every MVP page", () => {
    renderApp()

    const nav = screen.getByRole("navigation", { name: "Primary" })
    for (const item of navItems) {
      expect(within(nav).getByRole("link", { name: item.label })).toBeInTheDocument()
    }
  })

  it("mounts the dashboard stub on the index route", () => {
    renderApp("/")

    expect(screen.getByRole("heading", { level: 1, name: "Dashboard" })).toBeInTheDocument()
  })

  it("mounts the matching stub when a nav link is clicked", () => {
    renderApp("/")

    const nav = screen.getByRole("navigation", { name: "Primary" })
    fireEvent.click(within(nav).getByRole("link", { name: "Teams" }))

    expect(screen.getByRole("heading", { level: 1, name: "Teams" })).toBeInTheDocument()
    expect(
      screen.queryByRole("heading", { level: 1, name: "Dashboard" }),
    ).not.toBeInTheDocument()
  })

  it("renders the report runner stub on its route", () => {
    renderApp("/reports/run")

    expect(screen.getByRole("heading", { level: 1, name: "Report Runner" })).toBeInTheDocument()
  })

  it("renders a not-found stub for unknown routes", () => {
    renderApp("/does-not-exist")

    expect(screen.getByRole("heading", { level: 1, name: "Page not found" })).toBeInTheDocument()
  })
})
