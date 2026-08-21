import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"

import { SignalConfigGroupsPage } from "@/pages/SignalConfigGroupsPage"

const definitions = [
  {
    id: "sig-1",
    name: "Signal A",
    description: null,
    entity_type: "issue",
    expression: {},
    report_settings: { severity: "warning", category: "flow" },
    enabled: true,
    origin: "user_created",
    template_key: null,
    version: 1,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
]

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  })
}

function mockApi() {
  const groups: Array<Record<string, unknown>> = []
  return vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    const url = typeof input === "string" ? input : input.toString()
    const method = init?.method ?? "GET"
    if (url.endsWith("/api/signal-definitions")) {
      return Promise.resolve(jsonResponse(definitions))
    }
    if (url.endsWith("/api/signal-config-groups") && method === "GET") {
      return Promise.resolve(jsonResponse(groups))
    }
    if (url.endsWith("/api/signal-config-groups") && method === "POST") {
      const body = JSON.parse(String(init?.body))
      const created = {
        id: "group-1",
        name: body.name,
        description: null,
        signal_ids: body.signal_ids ?? [],
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      }
      groups.push(created)
      return Promise.resolve(jsonResponse(created))
    }
    if (url.includes("/api/signal-config-groups/") && method === "PATCH") {
      const body = JSON.parse(String(init?.body))
      Object.assign(groups[0], body)
      return Promise.resolve(jsonResponse(groups[0]))
    }
    throw new Error(`unexpected fetch: ${method} ${url}`)
  })
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <SignalConfigGroupsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("SignalConfigGroupsPage — create form", () => {
  it("uses InlineCreateRow with shared Input (h-9 class) for the new-group form", async () => {
    mockApi()
    renderPage()

    // The label and input are wired via InlineCreateRow using the shared Input component.
    // The shared Input renders with h-9; a raw <input className="w-64 ..."> would not.
    const input = await screen.findByLabelText("New group name")
    expect(input.tagName).toBe("INPUT")
    expect(input).toHaveClass("h-9")

    // Input must NOT be disabled when empty — the user needs to be able to type.
    // (Pre-fix: disabled was forwarded to the Input too, blocking the first keystroke.)
    expect(input).not.toBeDisabled()

    // The create button IS disabled when the input is empty
    expect(screen.getByRole("button", { name: "Create group" })).toBeDisabled()

    // Typing a name enables the button
    fireEvent.change(input, { target: { value: "Backend signals" } })
    expect(screen.getByRole("button", { name: "Create group" })).not.toBeDisabled()
  })
})

describe("SignalConfigGroupsPage", () => {
  it("creates a group and adds a signal to it", async () => {
    const fetchMock = mockApi()
    renderPage()

    fireEvent.change(await screen.findByLabelText("New group name"), {
      target: { value: "Backend signals" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Create group" }))

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([url, init]) =>
          String(url).endsWith("/api/signal-config-groups") && init?.method === "POST",
      )
      const body = JSON.parse(String((call?.[1] as RequestInit).body))
      expect(body.name).toBe("Backend signals")
    })

    fireEvent.change(await screen.findByLabelText("Add a signal"), { target: { value: "sig-1" } })
    fireEvent.click(screen.getByRole("button", { name: "Add signal" }))

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([url, init]) =>
          String(url).includes("/api/signal-config-groups/") && init?.method === "PATCH",
      )
      expect(call).toBeTruthy()
      const body = JSON.parse(String((call?.[1] as RequestInit).body))
      expect(body.signal_ids).toEqual(["sig-1"])
    })

    expect(await screen.findByText("Signal A")).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// AUDIT-8: disable controls while pending
// ---------------------------------------------------------------------------

describe("SignalConfigGroupsPage — AUDIT-8: disable while pending", () => {
  it("disables Add signal and Remove while an update mutation is pending", async () => {
    // Set up a group that already has sig-1 so the Remove button is visible.
    const groupWithSignal = {
      id: "group-1",
      name: "Backend signals",
      description: null,
      signal_ids: ["sig-1"],
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    }

    let resolvePatch!: (v: Response) => void
    const pendingPatch = new Promise<Response>((resolve) => {
      resolvePatch = resolve
    })

    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.endsWith("/api/signal-definitions")) {
        return Promise.resolve(jsonResponse(definitions))
      }
      if (url.endsWith("/api/signal-config-groups") && (init?.method ?? "GET") === "GET") {
        return Promise.resolve(jsonResponse([groupWithSignal]))
      }
      if (url.includes("/api/signal-config-groups/") && init?.method === "PATCH") {
        return pendingPatch
      }
      throw new Error(`unexpected fetch: ${String(url)}`)
    })

    renderPage()

    const removeBtn = await screen.findByRole("button", { name: "Remove Signal A" })
    expect(removeBtn).not.toBeDisabled()

    fireEvent.click(removeBtn)

    // Both Remove and Add signal are disabled while the update mutation is in-flight.
    await waitFor(() => expect(removeBtn).toBeDisabled())
    expect(screen.getByRole("button", { name: "Add signal" })).toBeDisabled()

    resolvePatch(
      new Response(JSON.stringify({ ...groupWithSignal, signal_ids: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    )

    await waitFor(() => expect(removeBtn).not.toBeDisabled())
  })
})

// ---------------------------------------------------------------------------
// AUDIT-9: surface mutation errors via Callout
// ---------------------------------------------------------------------------

describe("SignalConfigGroupsPage — AUDIT-9: Callout errors", () => {
  function mockApiWithErrors(patchStatus = 500) {
    const groups: Array<Record<string, unknown>> = []
    return vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = typeof input === "string" ? input : input.toString()
      const method = init?.method ?? "GET"
      if (url.endsWith("/api/signal-definitions")) {
        return Promise.resolve(jsonResponse(definitions))
      }
      if (url.endsWith("/api/signal-config-groups") && method === "GET") {
        return Promise.resolve(jsonResponse(groups))
      }
      if (url.endsWith("/api/signal-config-groups") && method === "POST") {
        const body = JSON.parse(String(init?.body))
        const created = {
          id: "group-1",
          name: body.name as string,
          description: null,
          signal_ids: [],
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        }
        groups.push(created)
        return Promise.resolve(jsonResponse(created))
      }
      if (url.includes("/api/signal-config-groups/") && method === "PATCH") {
        return Promise.resolve(
          new Response(JSON.stringify({ detail: "server error" }), { status: patchStatus }),
        )
      }
      if (url.includes("/api/signal-config-groups/") && method === "DELETE") {
        return Promise.resolve(
          new Response(JSON.stringify({ detail: "server error" }), { status: patchStatus }),
        )
      }
      throw new Error(`unexpected fetch: ${method} ${url}`)
    })
  }

  it("shows a Callout alert when the add-signal mutation fails", async () => {
    mockApiWithErrors()
    renderPage()

    // Create a group first
    fireEvent.change(await screen.findByLabelText("New group name"), {
      target: { value: "Backend signals" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Create group" }))

    // Select and add a signal
    fireEvent.change(await screen.findByLabelText("Add a signal"), { target: { value: "sig-1" } })
    fireEvent.click(screen.getByRole("button", { name: "Add signal" }))

    const alert = await screen.findByRole("alert")
    expect(alert).toBeInTheDocument()
    expect(alert.textContent).toMatch(/could not update signals/i)
  })

  it("shows a Callout alert when the delete-group mutation fails", async () => {
    mockApiWithErrors()
    renderPage()

    fireEvent.change(await screen.findByLabelText("New group name"), {
      target: { value: "Backend signals" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Create group" }))

    await screen.findByRole("button", { name: "Delete group" })
    fireEvent.click(screen.getByRole("button", { name: "Delete group" }))

    const alert = await screen.findByRole("alert")
    expect(alert).toBeInTheDocument()
    expect(alert.textContent).toMatch(/could not delete/i)
  })

  it("shows a Callout alert when the rename mutation fails", async () => {
    mockApiWithErrors()
    renderPage()

    fireEvent.change(await screen.findByLabelText("New group name"), {
      target: { value: "Backend signals" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Create group" }))

    const renameInput = await screen.findByLabelText("Group name")
    fireEvent.change(renameInput, { target: { value: "Updated name" } })
    fireEvent.click(screen.getByRole("button", { name: "Rename" }))

    const alert = await screen.findByRole("alert")
    expect(alert).toBeInTheDocument()
    expect(alert.textContent).toMatch(/could not rename/i)
  })
})
