// SPDX-License-Identifier: Apache-2.0
//
// M9-08: GitLabMemberPicker — these tests must FAIL before the component is
// implemented and PASS after. They use the same fetch-mock pattern as
// TeamGitLabConfig.test.tsx.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { GitLabMemberPicker } from "@/components/teams/GitLabMemberPicker"

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const teamId = "team-42"

const searchResults = [
  {
    provider_user_id: "101",
    username: "jsmith",
    display_name: "John Smith",
    avatar_url: null,
  },
  {
    provider_user_id: "102",
    username: "jdoe",
    display_name: "Jane Doe",
    avatar_url: null,
  },
]

const existingMember = {
  id: "mbr-1",
  team_profile_id: teamId,
  connection_id: "conn-1",
  gitlab_user_id: 101,
  username: "jsmith",
  display_name: "John Smith",
  verification_status: "verified",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
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

interface MockApiOptions {
  initialMembers?: unknown[]
  searchResponse?: unknown[]
  putResponse?: unknown[]
}

/**
 * Spy on `globalThis.fetch` and route calls to the GitLab member endpoints.
 *
 * - GET  ...\/member-search → searchResponse
 * - GET  ...\/gitlab/members → initialMembers
 * - PUT  ...\/gitlab/members → putResponse (falls back to initialMembers)
 */
function mockApi({
  initialMembers = [],
  searchResponse = searchResults,
  putResponse,
}: MockApiOptions = {}) {
  return vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    const url = typeof input === "string" ? input : input.toString()
    const method = (init as RequestInit | undefined)?.method ?? "GET"

    if (url.includes("member-search")) {
      return Promise.resolve(jsonResponse(searchResponse))
    }
    if (url.includes("/gitlab/members")) {
      if (method === "PUT") {
        return Promise.resolve(jsonResponse(putResponse ?? initialMembers))
      }
      return Promise.resolve(jsonResponse(initialMembers))
    }
    throw new Error(`unexpected fetch: ${method} ${url}`)
  })
}

const connectionId = "conn-1"

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
// Debounce: search fires once per settled query, not once per keystroke (§24)
// ---------------------------------------------------------------------------

describe("GitLabMemberPicker: debounce", () => {
  it("does not fire a search request while typing and fires exactly one after settling", async () => {
    const fetchMock = mockApi({ searchResponse: searchResults })
    renderPicker()

    // The picker gates on the initial members load; wait for it to complete
    // before interacting with the Combobox.
    const input = await screen.findByRole("combobox")

    // Type four chars in rapid succession (all within the debounce window).
    fireEvent.change(input, { target: { value: "j" } })
    fireEvent.change(input, { target: { value: "jo" } })
    fireEvent.change(input, { target: { value: "joh" } })
    fireEvent.change(input, { target: { value: "john" } })

    // Immediately after typing: no search request yet.
    const earlySearchCalls = fetchMock.mock.calls.filter(([url]) =>
      String(url).includes("member-search"),
    )
    expect(earlySearchCalls).toHaveLength(0)

    // After the debounce window (~300 ms) plus fetch round-trip: exactly one
    // search call, keyed on the final query value.
    await waitFor(
      () => {
        const searchCalls = fetchMock.mock.calls.filter(([url]) =>
          String(url).includes("member-search"),
        )
        expect(searchCalls).toHaveLength(1)
        expect(String(searchCalls[0][0])).toContain("q=john")
      },
      { timeout: 1500 },
    )
  })
})

// ---------------------------------------------------------------------------
// Selection: picking a result adds a chip and sends PUT (§5.1, §5.4)
// ---------------------------------------------------------------------------

describe("GitLabMemberPicker: selection", () => {
  it("selecting a search result adds it as a removable chip and sends PUT", async () => {
    const fetchMock = mockApi({
      initialMembers: [],
      searchResponse: searchResults,
      putResponse: [existingMember],
    })
    renderPicker()

    // Wait for the initial load gate to lift.
    const input = await screen.findByRole("combobox")
    fireEvent.change(input, { target: { value: "john" } })

    // Wait for the debounce + fetch; option should appear in the listbox.
    const option = await screen.findByRole("option", { name: /John Smith @jsmith/ })
    fireEvent.mouseDown(option)

    // Chip should be visible immediately after selection.
    expect(screen.getByText("John Smith @jsmith")).toBeInTheDocument()

    // PUT must have been sent with the selected member's gitlab_user_id.
    await waitFor(() => {
      const putCalls = fetchMock.mock.calls.filter(
        (args) => (args[1] as RequestInit | undefined)?.method === "PUT",
      )
      expect(putCalls).toHaveLength(1)
      const body = JSON.parse(
        (putCalls[0][1] as RequestInit).body as string,
      ) as Array<{ gitlab_user_id: number }>
      expect(body).toContainEqual({ gitlab_user_id: 101 })
    })
  })
})

// ---------------------------------------------------------------------------
// Removal: removing a chip sends PUT with reduced set (§5.4)
// ---------------------------------------------------------------------------

describe("GitLabMemberPicker: removal", () => {
  it("removing a selected member removes the chip and sends PUT with reduced set", async () => {
    const fetchMock = mockApi({
      initialMembers: [existingMember],
      putResponse: [],
    })
    renderPicker()

    // Wait for the existing member chip to appear after the initial GET resolves.
    await screen.findByText("John Smith @jsmith")

    // Click the remove button.
    fireEvent.click(screen.getByRole("button", { name: "Remove John Smith" }))

    // Chip must be gone immediately.
    expect(screen.queryByText("John Smith @jsmith")).toBeNull()

    // PUT must have been sent with an empty array (no remaining members).
    await waitFor(() => {
      const putCalls = fetchMock.mock.calls.filter(
        (args) => (args[1] as RequestInit | undefined)?.method === "PUT",
      )
      expect(putCalls).toHaveLength(1)
      const body = JSON.parse(
        (putCalls[0][1] as RequestInit).body as string,
      ) as Array<unknown>
      expect(body).toHaveLength(0)
    })
  })
})

// ---------------------------------------------------------------------------
// Free-text guard: blurring without selecting cannot add a member (§5.2)
// ---------------------------------------------------------------------------

describe("GitLabMemberPicker: free-text guard", () => {
  it("typing and blurring without selecting an option adds nothing and sends no PUT", async () => {
    const fetchMock = mockApi({ searchResponse: [] })
    renderPicker()

    // Wait for the initial load gate to lift.
    const input = await screen.findByRole("combobox")
    fireEvent.change(input, { target: { value: "nonexistent-user" } })
    fireEvent.blur(input)

    // No member chip list should be rendered (selectedMembers is empty).
    expect(screen.queryByRole("list", { name: "Selected GitLab members" })).toBeNull()

    // No PUT — blurring free text must never persist anything.
    await waitFor(() => {
      const putCalls = fetchMock.mock.calls.filter(
        (args) => (args[1] as RequestInit | undefined)?.method === "PUT",
      )
      expect(putCalls).toHaveLength(0)
    })
  })

  it("results visible but user blurs without clicking: nothing is added, no PUT sent", async () => {
    const fetchMock = mockApi({ searchResponse: searchResults })
    renderPicker()

    // Wait for the initial load gate to lift.
    const input = await screen.findByRole("combobox")
    fireEvent.change(input, { target: { value: "john" } })

    // Wait for results to load in the listbox.
    await screen.findByRole("option", { name: /John Smith @jsmith/ })

    // Blur without selecting any option.
    fireEvent.blur(input)

    // No chip should appear.
    expect(screen.queryByRole("list", { name: "Selected GitLab members" })).toBeNull()

    // Confirm no PUT was ever sent.
    await waitFor(() => {
      const putCalls = fetchMock.mock.calls.filter(
        (args) => (args[1] as RequestInit | undefined)?.method === "PUT",
      )
      expect(putCalls).toHaveLength(0)
    })
  })
})

// ---------------------------------------------------------------------------
// Replace semantics: PUT must contain the full set, not just the new delta
// ---------------------------------------------------------------------------

describe("GitLabMemberPicker: full replace set", () => {
  it("adding to an existing selection sends PUT with both ids (proves no delta-only regression)", async () => {
    const jdoeSaved = {
      id: "mbr-2",
      team_profile_id: teamId,
      connection_id: "conn-1",
      gitlab_user_id: 102,
      username: "jdoe",
      display_name: "Jane Doe",
      verification_status: "verified",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    }
    const fetchMock = mockApi({
      initialMembers: [existingMember], // jsmith pre-seeded
      searchResponse: [searchResults[1]], // search returns only Jane Doe
      putResponse: [existingMember, jdoeSaved],
    })
    renderPicker()

    // Wait for the existing member chip to load.
    await screen.findByText("John Smith @jsmith")

    // Search for and select the second member.
    const input = await screen.findByRole("combobox")
    fireEvent.change(input, { target: { value: "jane" } })
    const option = await screen.findByRole("option", { name: /Jane Doe @jdoe/ })
    fireEvent.mouseDown(option)

    // Both chips should appear immediately (optimistic update).
    expect(screen.getByText("John Smith @jsmith")).toBeInTheDocument()
    expect(screen.getByText("Jane Doe @jdoe")).toBeInTheDocument()

    // PUT body must contain BOTH ids (full replace, not delta-only).
    await waitFor(() => {
      const putCalls = fetchMock.mock.calls.filter(
        (args) => (args[1] as RequestInit | undefined)?.method === "PUT",
      )
      expect(putCalls).toHaveLength(1)
      const body = JSON.parse(
        (putCalls[0][1] as RequestInit).body as string,
      ) as Array<{ gitlab_user_id: number }>
      expect(body).toHaveLength(2)
      expect(body).toContainEqual({ gitlab_user_id: 101 })
      expect(body).toContainEqual({ gitlab_user_id: 102 })
    })
  })
})

// ---------------------------------------------------------------------------
// Connection filter: members anchored to a different connection are not seeded
// ---------------------------------------------------------------------------

describe("GitLabMemberPicker: connection filter", () => {
  it("does not seed or re-send members anchored to a different connection", async () => {
    const staleMember = {
      ...existingMember,
      id: "mbr-stale",
      connection_id: "conn-OTHER",
      gitlab_user_id: 999,
      username: "stale",
      display_name: "Stale User",
    }
    const jdoeSaved = {
      ...existingMember,
      id: "mbr-2",
      gitlab_user_id: 102,
      username: "jdoe",
      display_name: "Jane Doe",
    }
    const fetchMock = mockApi({
      // GET returns a member on the active connection plus one on a different connection.
      initialMembers: [existingMember, staleMember],
      searchResponse: [searchResults[1]], // Jane Doe
      putResponse: [existingMember, jdoeSaved],
    })
    renderPicker()

    // Only the active-connection member is shown; the stale-connection member is not.
    await screen.findByText("John Smith @jsmith")
    expect(screen.queryByText("Stale User @stale")).toBeNull()

    // Add a new member; the PUT must not include the stale-connection id (999).
    const input = await screen.findByRole("combobox")
    fireEvent.change(input, { target: { value: "jane" } })
    const option = await screen.findByRole("option", { name: /Jane Doe @jdoe/ })
    fireEvent.mouseDown(option)

    await waitFor(() => {
      const putCalls = fetchMock.mock.calls.filter(
        (args) => (args[1] as RequestInit | undefined)?.method === "PUT",
      )
      expect(putCalls).toHaveLength(1)
      const body = JSON.parse(
        (putCalls[0][1] as RequestInit).body as string,
      ) as Array<{ gitlab_user_id: number }>
      expect(body).toContainEqual({ gitlab_user_id: 101 })
      expect(body).toContainEqual({ gitlab_user_id: 102 })
      expect(body).not.toContainEqual({ gitlab_user_id: 999 })
    })
  })
})

// ---------------------------------------------------------------------------
// Serialization: edits are blocked while a replace PUT is in flight
// ---------------------------------------------------------------------------

describe("GitLabMemberPicker: serialized writes", () => {
  it("disables the picker while a save is pending so overlapping PUTs cannot race", async () => {
    let resolvePut!: (r: Response) => void
    // The PUT stays pending until we resolve it, keeping the mutation in flight.
    const pendingPut = new Promise<Response>((resolve) => {
      resolvePut = resolve
    })
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = typeof input === "string" ? input : input.toString()
      const method = (init as RequestInit | undefined)?.method ?? "GET"
      if (url.includes("member-search")) {
        return Promise.resolve(jsonResponse(searchResults))
      }
      if (url.includes("/gitlab/members")) {
        if (method === "PUT") {
          return pendingPut
        }
        return Promise.resolve(jsonResponse([existingMember]))
      }
      throw new Error(`unexpected fetch: ${method} ${url}`)
    })
    renderPicker()

    await screen.findByText("John Smith @jsmith")

    // Start a removal — the PUT stays pending.
    fireEvent.click(screen.getByRole("button", { name: "Remove John Smith" }))

    // While pending, the search combobox and any remove buttons are disabled, so a
    // second overlapping PUT cannot be started.
    await waitFor(() => {
      expect(screen.getByRole("combobox")).toBeDisabled()
    })

    const putCalls = fetchMock.mock.calls.filter(
      (args) => (args[1] as RequestInit | undefined)?.method === "PUT",
    )
    expect(putCalls).toHaveLength(1)

    // Clean up the hanging promise so the test runner does not leak it.
    resolvePut(jsonResponse([]))
  })
})

// ---------------------------------------------------------------------------
// Load-gate: a failed initial GET must not enable a destructive replace
// ---------------------------------------------------------------------------

describe("GitLabMemberPicker: load gate", () => {
  it("shows an error and prevents any PUT when the initial members load fails", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = typeof input === "string" ? input : input.toString()
      const method = (init as RequestInit | undefined)?.method ?? "GET"
      if (url.includes("/gitlab/members")) {
        if (method === "PUT") throw new Error("PUT must not be called during a load failure")
        return Promise.resolve(jsonResponse({ detail: "Internal server error" }, 500))
      }
      return Promise.resolve(jsonResponse([]))
    })
    renderPicker()

    // Error state is shown instead of the picker.
    await screen.findByRole("alert")

    // Combobox must not be rendered — no interaction possible.
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument()

    // No PUT was sent.
    const putCalls = fetchMock.mock.calls.filter(
      (args) => (args[1] as RequestInit | undefined)?.method === "PUT",
    )
    expect(putCalls).toHaveLength(0)
  })
})

// ---------------------------------------------------------------------------
// onError rollback: a failed PUT must revert the optimistic update
// ---------------------------------------------------------------------------

describe("GitLabMemberPicker: PUT failure rollback", () => {
  it("rolls back the optimistic update and shows an error when PUT fails", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = typeof input === "string" ? input : input.toString()
      const method = (init as RequestInit | undefined)?.method ?? "GET"
      if (url.includes("member-search")) {
        return Promise.resolve(jsonResponse([searchResults[1]])) // Jane Doe only
      }
      if (url.includes("/gitlab/members")) {
        if (method === "PUT") {
          return Promise.resolve(jsonResponse({ detail: "Server error" }, 500))
        }
        return Promise.resolve(jsonResponse([existingMember])) // initial GET succeeds
      }
      throw new Error(`unexpected fetch: ${method} ${url}`)
    })
    renderPicker()

    // Wait for existing member (jsmith) to load.
    await screen.findByText("John Smith @jsmith")

    // Search and select jdoe.
    const input = await screen.findByRole("combobox")
    fireEvent.change(input, { target: { value: "jane" } })
    const option = await screen.findByRole("option", { name: /Jane Doe @jdoe/ })
    fireEvent.mouseDown(option)

    // After the PUT fails the optimistic add must be rolled back.
    await waitFor(() => {
      expect(screen.queryByText("Jane Doe @jdoe")).not.toBeInTheDocument()
    })

    // An inline error alert must be visible.
    expect(screen.getByRole("alert")).toBeInTheDocument()

    // The original member is still shown.
    expect(screen.getByText("John Smith @jsmith")).toBeInTheDocument()
  })
})
