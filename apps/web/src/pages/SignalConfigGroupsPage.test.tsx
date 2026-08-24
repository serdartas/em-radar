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

  it("surfaces an error when group creation fails", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = typeof input === "string" ? input : input.toString()
      const method = init?.method ?? "GET"
      if (url.endsWith("/api/signal-definitions")) {
        return Promise.resolve(jsonResponse(definitions))
      }
      if (url.endsWith("/api/signal-config-groups") && method === "GET") {
        return Promise.resolve(jsonResponse([]))
      }
      if (url.endsWith("/api/signal-config-groups") && method === "POST") {
        return Promise.resolve(
          new Response(JSON.stringify({ detail: "Group name already exists" }), {
            status: 409,
            headers: { "Content-Type": "application/json" },
          }),
        )
      }
      throw new Error(`unexpected fetch: ${method} ${url}`)
    })
    renderPage()

    const input = await screen.findByLabelText("New group name")
    fireEvent.change(input, { target: { value: "Backend signals" } })
    fireEvent.click(screen.getByRole("button", { name: "Create group" }))

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /already exists|Failed to create the group/i,
    )
  })
})

// Stale-window race: Add signal button must stay disabled through the post-PATCH refetch.
describe("SignalConfigGroupsPage - stale-write prevention via awaited invalidation", () => {
  // Custom render that disables background refetch triggers so the only refetch is the
  // one driven by invalidateQueries from onSuccess.
  function renderPageStable() {
    const queryClient = new QueryClient({
      defaultOptions: {
        mutations: { retry: false },
        queries: { retry: false, staleTime: Infinity, refetchOnWindowFocus: false },
      },
    })
    return render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <SignalConfigGroupsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    )
  }

  it("Remove button stays locked through the post-PATCH groups refetch", async () => {
    // sig-1 is already in the group so the Remove button exists from the start.
    // That button is gated only on updateMutation.isPending — not on a select value —
    // so it is the cleanest probe for isPending in this component.
    const baseGroup = {
      id: "group-1",
      name: "Backend signals",
      description: null,
      signal_ids: ["sig-1"],
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    }

    let resolvePatch!: (v: Response) => void
    const deferredPatch = new Promise<Response>((resolve) => {
      resolvePatch = resolve
    })
    let resolveRefetch!: (v: Response) => void
    const deferredRefetch = new Promise<Response>((resolve) => {
      resolveRefetch = resolve
    })
    let getCallCount = 0

    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = typeof input === "string" ? input : input.toString()
      const method = init?.method ?? "GET"

      if (url.endsWith("/api/signal-definitions")) {
        return Promise.resolve(jsonResponse(definitions))
      }

      if (url.endsWith("/api/signal-config-groups") && method === "GET") {
        getCallCount++
        if (getCallCount === 1) {
          return Promise.resolve(jsonResponse([baseGroup]))
        }
        // Second call is the post-PATCH refetch — held pending.
        return deferredRefetch
      }

      if (url.includes("/api/signal-config-groups/") && method === "PATCH") {
        return deferredPatch
      }

      throw new Error(`unexpected: ${method} ${url}`)
    })

    renderPageStable()

    // Phase 1: initial data loads. "Backend signals" is an Input value, not text content.
    await screen.findByDisplayValue("Backend signals")
    const removeBtn = screen.getByRole("button", { name: "Remove Signal A" })
    expect(removeBtn).not.toBeDisabled()

    // Phase 2: click Remove — this fires a PATCH (deferred).
    fireEvent.click(removeBtn)

    // Button is disabled while PATCH is pending.
    await waitFor(() => expect(removeBtn).toBeDisabled())

    // Phase 3: resolve the PATCH — onSuccess awaits invalidateQueries which triggers the
    // second GET (still deferred). With the fix: isPending stays true; without: it clears.
    resolvePatch(
      new Response(JSON.stringify({ ...baseGroup, signal_ids: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    )

    // Wait for the refetch to be triggered (PATCH resolved + invalidateQueries called).
    await waitFor(() => expect(getCallCount).toBe(2))

    // With the fix: Remove button is still disabled (isPending covers the pending GET).
    expect(removeBtn).toBeDisabled()

    // Phase 4: resolve refetch with updated group (signal removed).
    resolveRefetch(
      new Response(
        JSON.stringify([{ ...baseGroup, signal_ids: [], updated_at: "2026-01-02T00:00:00Z" }]),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    )

    // After fresh data arrives, GroupCard remounts with signal_ids=[] so Remove Signal A
    // disappears from the DOM — confirming the locked window is closed.
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Remove Signal A" })).not.toBeInTheDocument(),
    )
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
