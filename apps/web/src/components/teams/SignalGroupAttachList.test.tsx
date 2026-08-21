import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { SignalGroupAttachList } from "@/components/teams/SignalGroupAttachList"

const team = {
  id: "team-1",
  name: "Platform",
  description: null,
  connection_ids: [],
  scope_ids: [],
  signal_config_group_ids: [],
  code_connection_id: null,
  working_mode: "scrum" as const,
  sprint_length_days: 14,
  member_user_keys: [],
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
}

const groups = [
  {
    id: "g1",
    name: "Backend signals",
    description: null,
    signal_ids: [],
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
  {
    id: "g2",
    name: "Frontend signals",
    description: null,
    signal_ids: [],
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
]

function renderList(teamOverrides: Partial<typeof team> = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <SignalGroupAttachList groups={groups} team={{ ...team, ...teamOverrides }} />
    </QueryClientProvider>,
  )
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

// AUDIT-8: all toggle buttons disabled while any write is in-flight (serialization)
describe("SignalGroupAttachList - AUDIT-8: pending toggle disables controls", () => {
  it("disables ALL group buttons while any mutation is pending and does not lose a rapid second write", async () => {
    let patchCallCount = 0
    let resolvePatch!: (value: Response) => void
    const pendingPatch = new Promise<Response>((resolve) => {
      resolvePatch = resolve
    })

    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.includes("/api/teams/") && init?.method === "PATCH") {
        patchCallCount++
        return pendingPatch
      }
      throw new Error(`unexpected fetch: ${url}`)
    })

    renderList()

    const [btnG1, btnG2] = screen.getAllByRole("button", { name: "Attach" })

    // Click g1 Attach
    fireEvent.click(btnG1)

    // Both buttons must be disabled while the mutation is in-flight (cross-group serialization).
    await waitFor(() => expect(btnG1).toBeDisabled())
    expect(btnG2).toBeDisabled()

    // Attempting to click g2 while g1 is pending has no effect (write not lost = not double-submitted).
    fireEvent.click(btnG2)

    // Resolve g1's PATCH.
    resolvePatch(
      new Response(JSON.stringify({ ...team, signal_config_group_ids: ["g1"] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    )

    await waitFor(() => expect(btnG1).not.toBeDisabled())
    expect(btnG2).not.toBeDisabled()

    // Only one PATCH fired; g2's "click while disabled" was blocked.
    expect(patchCallCount).toBe(1)
  })
})

// AUDIT-9: error surfacing via Callout
describe("SignalGroupAttachList - AUDIT-9: Callout error on mutation failure", () => {
  it("renders a Callout error when the attach mutation fails", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.includes("/api/teams/") && init?.method === "PATCH") {
        return Promise.resolve(
          new Response(JSON.stringify({ detail: "server error" }), { status: 500 }),
        )
      }
      throw new Error(`unexpected fetch: ${url}`)
    })

    renderList()

    fireEvent.click(screen.getAllByRole("button", { name: "Attach" })[0])

    const alert = await screen.findByRole("alert")
    expect(alert).toBeInTheDocument()
    expect(alert.textContent).toMatch(/could not update signal config groups/i)
  })
})
