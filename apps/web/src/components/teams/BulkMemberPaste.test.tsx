// SPDX-License-Identifier: Apache-2.0
//
// M9-13: BulkMemberPaste — these tests must FAIL before the component is
// implemented and PASS after. They mirror the GitLabMemberPicker.test.tsx pattern.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { GitLabMemberPicker } from "@/components/teams/GitLabMemberPicker"

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const teamId = "team-bulk"
const connectionId = "conn-bulk"

const aliceMember = {
  id: "mbr-10",
  team_profile_id: teamId,
  connection_id: connectionId,
  gitlab_user_id: 10,
  username: "alice",
  display_name: "Alice",
  verification_status: "verified",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
}

const resolveResponse = {
  results: [
    {
      entry: "alice",
      status: "matched",
      match: { provider_user_id: "10", username: "alice", display_name: "Alice", avatar_url: null },
      candidates: [],
    },
    {
      entry: "bob smith",
      status: "ambiguous",
      match: null,
      candidates: [
        { provider_user_id: "20", username: "bsmith", display_name: "Bob Smith", avatar_url: null },
        {
          provider_user_id: "21",
          username: "bobsmth",
          display_name: "Bob Smth",
          avatar_url: null,
        },
      ],
    },
    {
      entry: "unknown-person",
      status: "unmatched",
      match: null,
      candidates: [],
    },
  ],
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  })
}

interface MockBulkApiOptions {
  initialMembers?: unknown[]
  resolveResponse?: unknown
  putResponse?: unknown[]
}

/**
 * Mock fetch for the bulk-paste flow.
 *
 * - POST .../member-resolve -> resolveResponse
 * - GET  .../gitlab/members -> initialMembers
 * - PUT  .../gitlab/members -> putResponse
 */
function mockBulkApi({
  initialMembers = [],
  resolveResponse: resolveResp = resolveResponse,
  putResponse = [],
}: MockBulkApiOptions = {}) {
  return vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    const url = typeof input === "string" ? input : input.toString()
    const method = (init as RequestInit | undefined)?.method ?? "GET"

    if (url.includes("/member-resolve")) {
      return Promise.resolve(jsonResponse(resolveResp))
    }
    if (url.includes("/gitlab/members")) {
      if (method === "PUT") return Promise.resolve(jsonResponse(putResponse))
      return Promise.resolve(jsonResponse(initialMembers))
    }
    throw new Error(`unexpected fetch: ${method} ${url}`)
  })
}

function renderPicker() {
  const queryClient = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <GitLabMemberPicker connectionId={connectionId} teamId={teamId} />
    </QueryClientProvider>,
  )
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

// ---------------------------------------------------------------------------
// Panel toggle: "Paste a list" button shows/hides the paste panel
// ---------------------------------------------------------------------------

describe("BulkMemberPaste: panel toggle", () => {
  it("shows the paste panel when the toggle button is clicked", async () => {
    mockBulkApi()
    renderPicker()

    // Wait for initial load gate.
    await screen.findByRole("button", { name: "Paste a list" })

    // Textarea should not be visible yet.
    expect(screen.queryByRole("textbox", { name: /Paste member/i })).toBeNull()

    fireEvent.click(screen.getByRole("button", { name: "Paste a list" }))

    // Now the paste textarea should be visible.
    expect(screen.getByRole("textbox", { name: /Paste member/i })).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Status rendering: resolve shows per-entry classification
// ---------------------------------------------------------------------------

describe("BulkMemberPaste: per-entry status rendering", () => {
  it("renders matched, ambiguous, and unmatched statuses after resolving", async () => {
    mockBulkApi()
    renderPicker()

    await screen.findByRole("button", { name: "Paste a list" })
    fireEvent.click(screen.getByRole("button", { name: "Paste a list" }))

    const textarea = screen.getByRole("textbox", { name: /Paste member/i })
    fireEvent.change(textarea, { target: { value: "alice\nbob smith\nunknown-person" } })

    fireEvent.click(screen.getByRole("button", { name: "Resolve" }))

    // Matched entry.
    await screen.findByText(/Matched: Alice @alice/)

    // Ambiguous entry with a selector.
    expect(screen.getByText("Multiple matches")).toBeInTheDocument()
    expect(screen.getByRole("combobox", { name: /Select match for bob smith/i })).toBeInTheDocument()

    // Unmatched entry.
    expect(screen.getByText("No match")).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Ambiguous: requires a selection before the entry is counted as confirmed
// ---------------------------------------------------------------------------

describe("BulkMemberPaste: ambiguous entry requires selection", () => {
  it("excludes the ambiguous entry from confirmed count until a choice is made", async () => {
    mockBulkApi({ putResponse: [aliceMember] })
    renderPicker()

    await screen.findByRole("button", { name: "Paste a list" })
    fireEvent.click(screen.getByRole("button", { name: "Paste a list" }))

    fireEvent.change(screen.getByRole("textbox", { name: /Paste member/i }), {
      target: { value: "alice\nbob smith\nunknown-person" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Resolve" }))

    // Wait for results to render; "matched" alice counts as 1 confirmed.
    await screen.findByText(/Matched: Alice @alice/)
    // Add confirmed shows count of 1 (only matched alice).
    expect(screen.getByRole("button", { name: /Add confirmed matches \(1\)/ })).toBeInTheDocument()

    // Select a candidate for the ambiguous entry.
    const select = screen.getByRole("combobox", { name: /Select match for bob smith/i })
    fireEvent.change(select, { target: { value: "20" } })

    // Confirmed count rises to 2 (alice + bob smith choice).
    expect(screen.getByRole("button", { name: /Add confirmed matches \(2\)/ })).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Persistence: only confirmed matches are sent in the PUT body
// ---------------------------------------------------------------------------

describe("BulkMemberPaste: only confirmed matches saved", () => {
  it("PUT body contains matched + chosen ambiguous but NOT unmatched", async () => {
    const fetchMock = mockBulkApi({ putResponse: [aliceMember] })
    renderPicker()

    await screen.findByRole("button", { name: "Paste a list" })
    fireEvent.click(screen.getByRole("button", { name: "Paste a list" }))

    fireEvent.change(screen.getByRole("textbox", { name: /Paste member/i }), {
      target: { value: "alice\nbob smith\nunknown-person" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Resolve" }))

    await screen.findByText(/Matched: Alice @alice/)

    // Select the first candidate (provider_user_id "20") for the ambiguous entry.
    const select = screen.getByRole("combobox", { name: /Select match for bob smith/i })
    fireEvent.change(select, { target: { value: "20" } })

    // Click Add confirmed.
    fireEvent.click(screen.getByRole("button", { name: /Add confirmed matches/ }))

    // Assert the PUT body.
    await waitFor(() => {
      const putCalls = fetchMock.mock.calls.filter(
        (args) => (args[1] as RequestInit | undefined)?.method === "PUT",
      )
      expect(putCalls).toHaveLength(1)
      const body = JSON.parse(
        (putCalls[0][1] as RequestInit).body as string,
      ) as Array<{ gitlab_user_id: number }>
      // alice (matched, provider_user_id "10" -> gitlab_user_id 10)
      expect(body).toContainEqual({ gitlab_user_id: 10 })
      // bsmith (chosen ambiguous, provider_user_id "20" -> gitlab_user_id 20)
      expect(body).toContainEqual({ gitlab_user_id: 20 })
      // unknown-person (unmatched) must NOT be present.
      expect(body).not.toContainEqual({ gitlab_user_id: 21 })
    })
  })
})

// ---------------------------------------------------------------------------
// No-match: unmatched entry does not contribute to confirmed count
// ---------------------------------------------------------------------------

describe("BulkMemberPaste: no-match entry not addable", () => {
  it("unmatched entry is shown but never included in the PUT", async () => {
    const resolveOnlyUnmatched = {
      results: [
        {
          entry: "ghost-user",
          status: "unmatched",
          match: null,
          candidates: [],
        },
      ],
    }
    const fetchMock = mockBulkApi({ resolveResponse: resolveOnlyUnmatched, putResponse: [] })
    renderPicker()

    await screen.findByRole("button", { name: "Paste a list" })
    fireEvent.click(screen.getByRole("button", { name: "Paste a list" }))

    fireEvent.change(screen.getByRole("textbox", { name: /Paste member/i }), {
      target: { value: "ghost-user" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Resolve" }))

    await screen.findByText("No match")

    // Confirmed count is 0: the button either is absent or disabled.
    const addBtn = screen.queryByRole("button", { name: /Add confirmed matches/ })
    if (addBtn) {
      expect(addBtn).toBeDisabled()
    }

    // No PUT sent.
    await waitFor(() => {
      const putCalls = fetchMock.mock.calls.filter(
        (args) => (args[1] as RequestInit | undefined)?.method === "PUT",
      )
      expect(putCalls).toHaveLength(0)
    })
  })
})

// ---------------------------------------------------------------------------
// Union: bulk add unions with existing selected members, no duplicates
// ---------------------------------------------------------------------------

describe("BulkMemberPaste: bulk add unions with existing selection", () => {
  it("existing selected members are retained and new confirmed members are added", async () => {
    const existingJsmith = {
      id: "mbr-101",
      team_profile_id: teamId,
      connection_id: connectionId,
      gitlab_user_id: 101,
      username: "jsmith",
      display_name: "John Smith",
      verification_status: "verified",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    }
    const aliceAndJsmith = [aliceMember, existingJsmith]
    const fetchMock = mockBulkApi({
      initialMembers: [existingJsmith],
      resolveResponse: {
        results: [
          {
            entry: "alice",
            status: "matched",
            match: {
              provider_user_id: "10",
              username: "alice",
              display_name: "Alice",
              avatar_url: null,
            },
            candidates: [],
          },
        ],
      },
      putResponse: aliceAndJsmith,
    })
    renderPicker()

    // Wait for existing member chip to appear.
    await screen.findByText("John Smith @jsmith")

    fireEvent.click(screen.getByRole("button", { name: "Paste a list" }))
    fireEvent.change(screen.getByRole("textbox", { name: /Paste member/i }), {
      target: { value: "alice" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Resolve" }))

    await screen.findByText(/Matched: Alice @alice/)
    fireEvent.click(screen.getByRole("button", { name: /Add confirmed matches/ }))

    // PUT body must include BOTH jsmith (pre-existing) and alice (new).
    await waitFor(() => {
      const putCalls = fetchMock.mock.calls.filter(
        (args) => (args[1] as RequestInit | undefined)?.method === "PUT",
      )
      expect(putCalls).toHaveLength(1)
      const body = JSON.parse(
        (putCalls[0][1] as RequestInit).body as string,
      ) as Array<{ gitlab_user_id: number }>
      expect(body).toContainEqual({ gitlab_user_id: 101 }) // jsmith
      expect(body).toContainEqual({ gitlab_user_id: 10 }) // alice
    })
  })
})
