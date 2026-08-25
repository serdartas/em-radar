import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { MemoryRouter } from "react-router-dom"

import { SettingsPrivacyPage } from "@/pages/SettingsPrivacyPage"

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  localStorage.clear()
})

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  })
  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <SettingsPrivacyPage />
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

function mockFetch(
  connectionsResponse: unknown = [],
  deleteStatus = 204,
  settingsResponse: { telemetry_enabled: boolean } = { telemetry_enabled: false },
) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input)
    const method = (init?.method ?? "GET").toUpperCase()

    if (method === "GET" && url.includes("/api/settings")) {
      return new Response(JSON.stringify(settingsResponse), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    }
    if (method === "PATCH" && url.includes("/api/settings")) {
      const body = JSON.parse(init?.body as string) as { telemetry_enabled: boolean }
      return new Response(JSON.stringify({ telemetry_enabled: body.telemetry_enabled }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    }
    if (method === "GET" && url.includes("/connections")) {
      return new Response(JSON.stringify(connectionsResponse), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    }
    if (method === "DELETE" && url.includes("/reports")) {
      return new Response(null, { status: deleteStatus })
    }
    if (method === "DELETE" && url.includes("/connections")) {
      return new Response(null, { status: deleteStatus })
    }
    throw new Error(`unexpected fetch: ${method} ${url}`)
  })
}

describe("SettingsPrivacyPage", () => {
  it("renders the local-first privacy copy", () => {
    mockFetch()
    renderPage()

    expect(screen.getByRole("heading", { name: "Local-first guarantees" })).toBeInTheDocument()
    expect(screen.getByText(/never leave this machine/)).toBeInTheDocument()
  })

  it("defaults the telemetry toggle to off", async () => {
    mockFetch()
    renderPage()

    const toggle = await screen.findByRole("switch", { name: "Enable anonymous telemetry" })
    expect(toggle).toHaveAttribute("aria-checked", "false")
  })

  it("reflects the persisted telemetry value from the API", async () => {
    mockFetch([], 204, { telemetry_enabled: true })
    renderPage()

    await waitFor(() =>
      expect(screen.getByRole("switch", { name: "Enable anonymous telemetry" })).toHaveAttribute(
        "aria-checked",
        "true",
      ),
    )
  })

  it("PATCHes the settings endpoint when the toggle changes", async () => {
    const fetchSpy = mockFetch()
    renderPage()

    const toggle = screen.getByRole("switch", { name: "Enable anonymous telemetry" })
    // Wait for settings to load so the switch becomes enabled before clicking
    await waitFor(() => expect(toggle).not.toBeDisabled())
    fireEvent.click(toggle)

    await waitFor(() => {
      const patchCalls = fetchSpy.mock.calls.filter(
        ([, init]) => (init?.method ?? "GET").toUpperCase() === "PATCH",
      )
      expect(patchCalls.length).toBeGreaterThan(0)
      const body = JSON.parse(patchCalls[0][1]?.body as string) as {
        telemetry_enabled: boolean
      }
      expect(body.telemetry_enabled).toBe(true)
    })
  })

  it("gates destructive actions behind a confirmation affordance", () => {
    mockFetch()
    renderPage()

    fireEvent.click(screen.getByRole("button", { name: "Delete report history" }))

    const dialog = screen.getByRole("alertdialog", { name: "Confirm: Delete report history" })
    expect(dialog).toBeInTheDocument()
    expect(screen.getByText(/This cannot be undone/)).toBeInTheDocument()
  })

  it("confirm delete button is enabled after opening the confirmation dialog", () => {
    mockFetch()
    renderPage()

    fireEvent.click(screen.getByRole("button", { name: "Delete report history" }))

    const confirmBtn = screen.getByRole("button", { name: "Confirm delete" })
    expect(confirmBtn).not.toBeDisabled()
  })

  it("cancel dismisses the confirmation dialog without calling the API", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input)
      const method = (init?.method ?? "GET").toUpperCase()
      if (method === "GET" && url.includes("/api/settings")) {
        return new Response(JSON.stringify({ telemetry_enabled: false }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      }
      if (method === "GET" && url.includes("/connections")) {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      }
      throw new Error(`unexpected: ${method} ${url}`)
    })

    renderPage()

    fireEvent.click(screen.getByRole("button", { name: "Delete report history" }))
    expect(screen.getByRole("alertdialog", { name: "Confirm: Delete report history" })).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }))
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument()

    const deleteCalls = fetchSpy.mock.calls.filter(
      ([, init]) => (init?.method ?? "GET").toUpperCase() === "DELETE",
    )
    expect(deleteCalls).toHaveLength(0)
  })

  it("clicking confirm delete calls the delete API", async () => {
    mockFetch([], 204)
    renderPage()

    fireEvent.click(screen.getByRole("button", { name: "Delete report history" }))
    fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }))

    await waitFor(() => {
      const deleteCalls = vi.mocked(globalThis.fetch).mock.calls.filter(
        ([, init]) => (init?.method ?? "GET").toUpperCase() === "DELETE",
      )
      expect(deleteCalls.length).toBeGreaterThan(0)
    })
  })

  it("shows a per-connection delete button when connections exist", async () => {
    mockFetch([{ id: "conn-1", name: "Jira Prod", connector_name: "jira", config: {}, created_at: "2026-01-01T00:00:00Z" }])
    renderPage()

    await screen.findByRole("button", { name: "Delete" })
    expect(screen.getByText("Jira Prod")).toBeInTheDocument()
  })

  it("per-connection delete shows confirmation dialog before calling API", async () => {
    mockFetch([{ id: "conn-1", name: "Jira Prod", connector_name: "jira", config: {}, created_at: "2026-01-01T00:00:00Z" }])
    renderPage()

    const deleteBtn = await screen.findByRole("button", { name: "Delete" })
    fireEvent.click(deleteBtn)

    const dialog = screen.getByRole("alertdialog", {
      name: "Confirm: Delete connection Jira Prod",
    })
    expect(dialog).toBeInTheDocument()
    expect(screen.queryByRole("alertdialog")).not.toBeNull()
  })

  it("toggle is disabled while settings are still loading", () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input)
      const method = (init?.method ?? "GET").toUpperCase()
      if (method === "GET" && url.includes("/api/settings")) {
        // Never resolves — simulates a slow GET so we can assert the pre-load state
        return new Promise<Response>(() => {})
      }
      if (method === "GET" && url.includes("/connections")) {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      }
      throw new Error(`unexpected: ${method} ${url}`)
    })
    renderPage()

    expect(screen.getByRole("switch", { name: "Enable anonymous telemetry" })).toBeDisabled()
  })

  it("renders a Re-run setup link pointing to /setup", () => {
    mockFetch()
    renderPage()

    const link = screen.getByRole("link", { name: /re-run setup/i })
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute("href", "/setup")
  })

  it("clicking Re-run setup clears wizard progress so the wizard does not immediately redirect back", () => {
    localStorage.setItem(
      "em-radar.wizard-progress",
      JSON.stringify({ step: "sources", currentTeamId: null, completed: true, furthestStep: "sources" }),
    )
    mockFetch()
    renderPage()

    fireEvent.click(screen.getByRole("link", { name: /re-run setup/i }))

    expect(localStorage.getItem("em-radar.wizard-progress")).toBeNull()
  })

  it("shows a Callout alert when the delete report history mutation fails", async () => {
    mockFetch([], 500)
    renderPage()

    fireEvent.click(screen.getByRole("button", { name: "Delete report history" }))
    fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }))

    const alert = await screen.findByRole("alert")
    expect(alert).toBeInTheDocument()
    expect(alert.textContent).toMatch(/could not delete report history/i)
  })

  it("toggle is disabled and an error message is shown when settings query fails", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input)
      const method = (init?.method ?? "GET").toUpperCase()
      if (method === "GET" && url.includes("/api/settings")) {
        return new Response(JSON.stringify({ detail: "Internal Server Error" }), { status: 500 })
      }
      if (method === "GET" && url.includes("/connections")) {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      }
      throw new Error(`unexpected: ${method} ${url}`)
    })
    renderPage()

    await waitFor(() => {
      expect(screen.getByRole("switch", { name: "Enable anonymous telemetry" })).toBeDisabled()
      expect(screen.getByRole("alert")).toBeInTheDocument()
    })
  })
})
