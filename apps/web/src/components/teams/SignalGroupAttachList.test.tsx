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

describe("SignalGroupAttachList — AUDIT-8: pending toggle disables control", () => {
  it("disables the toggled button while its mutation is pending and does not lose a rapid second write", async () => {
    // Deferred promise so we can assert the disabled state before mutation resolves.
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

    // Use getAllByRole since both groups render an "Attach" button.
    const [attachBtn] = screen.getAllByRole("button", { name: "Attach" })
    expect(attachBtn).not.toBeDisabled()

    fireEvent.click(attachBtn)

    // Button must be disabled while the mutation is in-flight (no double-submit).
    expect(attachBtn).toBeDisabled()

    // A second rapid click on the same disabled button is ignored.
    fireEvent.click(attachBtn)

    // Resolve the PATCH.
    resolvePatch(
      new Response(JSON.stringify({ ...team, signal_config_group_ids: ["g1"] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    )

    await waitFor(() => expect(attachBtn).not.toBeDisabled())

    // Only one PATCH was sent despite two clicks — the write is not "doubled".
    expect(patchCallCount).toBe(1)
  })
})

describe("SignalGroupAttachList — AUDIT-9: error surfacing via Callout", () => {
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
