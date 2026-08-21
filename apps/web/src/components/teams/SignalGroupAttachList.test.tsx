import { useQuery, QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { SignalGroupAttachList } from "@/components/teams/SignalGroupAttachList"
import { TEAMS_KEY } from "@/lib/teamSetup"

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

// Wrapper that maintains an active TEAMS_KEY query so that invalidateQueries resolves
// only after the refetch completes (not immediately). This is required to test that
// isPending covers both the PATCH and the subsequent refetch.
function WithTeamsQuery() {
  const query = useQuery({
    queryKey: TEAMS_KEY,
    queryFn: (): Promise<(typeof team)[]> =>
      fetch("/api/teams").then((r) => r.json()) as Promise<(typeof team)[]>,
    staleTime: Infinity, // suppress background refetches unrelated to our test
  })
  const currentTeam = query.data?.[0]
  if (!currentTeam) return null
  return <SignalGroupAttachList groups={groups} team={currentTeam} />
}

function renderWithTeamsQuery() {
  const queryClient = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <WithTeamsQuery />
    </QueryClientProvider>,
  )
}

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

// Stale-window race: isPending must cover PATCH + refetch so a second edit cannot read
// stale ids from the cache.
describe("SignalGroupAttachList - stale-write prevention via awaited invalidation", () => {
  it("stays locked through the post-PATCH refetch so a second edit reads fresh data", async () => {
    let getCallCount = 0
    let resolveRefetch!: (v: Response) => void
    const deferredRefetch = new Promise<Response>((resolve) => {
      resolveRefetch = resolve
    })
    const patchBodies: { signal_config_group_ids: string[] }[] = []

    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = typeof input === "string" ? input : input.toString()
      const method = (init?.method ?? "GET").toUpperCase()

      if (url.endsWith("/api/teams") && method === "GET") {
        getCallCount++
        if (getCallCount === 1) {
          // Initial fetch — return immediately with the base team (no groups attached).
          return Promise.resolve(
            new Response(JSON.stringify([team]), {
              status: 200,
              headers: { "Content-Type": "application/json" },
            }),
          )
        }
        // Post-PATCH refetch — hold pending so we can observe the locked window.
        return deferredRefetch
      }

      if (url.includes("/api/teams/") && method === "PATCH") {
        patchBodies.push(JSON.parse(String(init?.body)) as { signal_config_group_ids: string[] })
        // PATCH resolves immediately; the refetch stays deferred.
        return Promise.resolve(
          new Response(
            JSON.stringify({ ...team, signal_config_group_ids: ["g1"] }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        )
      }

      throw new Error(`unexpected: ${method} ${url}`)
    })

    renderWithTeamsQuery()

    // Wait for initial data so the query observer is active.
    const buttons = await screen.findAllByRole("button", { name: "Attach" })
    const [btnG1, btnG2] = buttons

    // Attach g1.
    fireEvent.click(btnG1)

    // Wait until the refetch has been triggered (PATCH resolved + invalidateQueries called).
    // At this point the GET is still deferred, so with the fix isPending is still true;
    // without the fix isPending has already become false.
    await waitFor(() => expect(getCallCount).toBe(2))

    // With the fix: both buttons are disabled (isPending covers the pending GET).
    expect(btnG1).toBeDisabled()
    expect(btnG2).toBeDisabled()

    // g2 click in this window is blocked — no stale PATCH fired.
    fireEvent.click(btnG2)

    // Resolve the refetch with the updated team (g1 now attached).
    resolveRefetch(
      new Response(JSON.stringify([{ ...team, signal_config_group_ids: ["g1"] }]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    )

    // Buttons re-enable once fresh data has arrived.
    await waitFor(() => expect(btnG2).not.toBeDisabled())

    // The click during the locked window was blocked — only one PATCH was sent so far.
    expect(patchBodies).toHaveLength(1)

    // Now issue a real g2 click; the prop carries the fresh ids (["g1"]).
    fireEvent.click(btnG2)
    await waitFor(() => expect(patchBodies).toHaveLength(2))

    // The second PATCH must include g1 (not built from stale []).
    expect(patchBodies[1].signal_config_group_ids).toContain("g1")
    expect(patchBodies[1].signal_config_group_ids).toContain("g2")
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
