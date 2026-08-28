// SPDX-License-Identifier: Apache-2.0
//
// M9-09: GitLabRepositoryPicker — these tests must FAIL before the component is
// implemented and PASS after. They mirror the fetch-mock pattern of
// GitLabMemberPicker.test.tsx.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { GitLabRepositoryPicker } from "@/components/teams/GitLabRepositoryPicker"

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const teamId = "team-99"
const connectionId = "conn-gl-1"

/** Two suggestions: "frontend" has 3 contributors (>= LIKELY_THRESHOLD=2 -> likely);
 *  "utils" has 1 contributor (< LIKELY_THRESHOLD -> lower confidence). */
const suggestionsData = [
  {
    provider_project_id: "201",
    name: "frontend",
    path_with_namespace: "acme/frontend",
    contributing_member_count: 3,
    merge_request_count: 42,
    last_activity_at: "2026-07-01T00:00:00Z",
  },
  {
    provider_project_id: "202",
    name: "utils",
    path_with_namespace: "acme/utils",
    contributing_member_count: 1,
    merge_request_count: 5,
    last_activity_at: "2026-06-01T00:00:00Z",
  },
]

const searchResultsData = [
  {
    provider_project_id: "301",
    name: "backend",
    path_with_namespace: "acme/backend",
  },
]

const savedRepo201 = {
  id: "repo-1",
  team_profile_id: teamId,
  connection_id: connectionId,
  gitlab_project_id: 201,
  name: "frontend",
  path_with_namespace: "acme/frontend",
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
  initialRepos?: unknown[]
  suggestions?: unknown[]
  searchResponse?: unknown[]
  putResponse?: unknown[]
}

/**
 * Spy on `globalThis.fetch` and route calls to the GitLab repository endpoints.
 *
 * - GET  .../repository-suggestions  -> suggestions
 * - GET  .../project-search          -> searchResponse
 * - GET  .../gitlab/repositories     -> initialRepos
 * - PUT  .../gitlab/repositories     -> putResponse (falls back to initialRepos)
 */
function mockApi({
  initialRepos = [],
  putResponse,
  searchResponse = [],
  suggestions = [],
}: MockApiOptions = {}) {
  return vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    const url = typeof input === "string" ? input : input.toString()
    const method = (init as RequestInit | undefined)?.method ?? "GET"

    if (url.includes("repository-suggestions")) {
      return Promise.resolve(jsonResponse(suggestions))
    }
    if (url.includes("project-search")) {
      return Promise.resolve(jsonResponse(searchResponse))
    }
    if (url.includes("/gitlab/repositories")) {
      if (method === "PUT") {
        return Promise.resolve(jsonResponse(putResponse ?? initialRepos))
      }
      return Promise.resolve(jsonResponse(initialRepos))
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
      <GitLabRepositoryPicker connectionId={connectionId} teamId={teamId} />
    </QueryClientProvider>,
  )
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

// ---------------------------------------------------------------------------
// Suggestions render: ranked with activity counts; correct heading; split visible
// ---------------------------------------------------------------------------

describe("GitLabRepositoryPicker: suggestions rendering", () => {
  it("shows the 'Suggested repositories' heading (not 'Team repositories')", async () => {
    mockApi({ suggestions: suggestionsData })
    renderPicker()

    // Wait for the load gate to lift (initial repos GET resolves).
    await screen.findByText(/Suggested repositories/i)

    // Must NOT use the disallowed "Team repositories" wording.
    expect(screen.queryByText(/Team repositories/i)).not.toBeInTheDocument()
  })

  it("renders activity counts for each suggestion", async () => {
    mockApi({ suggestions: suggestionsData })
    renderPicker()

    // Wait for the component to render the suggestions.
    await screen.findByText(/3 members · 42 MRs/)
    expect(screen.getByText(/1 member · 5 MRs/)).toBeInTheDocument()
  })

  it("splits suggestions into likely and lower-confidence groups", async () => {
    mockApi({ suggestions: suggestionsData })
    renderPicker()

    // "frontend" (3 contributors >= LIKELY_THRESHOLD=2) -> in the "Likely repositories" list.
    const likelyList = await screen.findByRole("list", { name: "Likely repositories" })
    expect(likelyList).toBeInTheDocument()
    expect(likelyList.textContent).toContain("frontend")

    // "utils" (1 contributor < LIKELY_THRESHOLD=2) -> in the "Lower-confidence repositories" list.
    const lowerList = screen.getByRole("list", { name: "Lower-confidence repositories" })
    expect(lowerList).toBeInTheDocument()
    expect(lowerList.textContent).toContain("utils")

    // "frontend" must NOT appear in the lower-confidence list.
    expect(lowerList.textContent).not.toContain("frontend")
  })

  it("shows a 'No suggestions yet' note when the API returns an empty array", async () => {
    mockApi({ suggestions: [] })
    renderPicker()

    // Wait for the component to mount and suggestions query to resolve.
    await screen.findByText(/Suggested repositories/i)
    expect(screen.getByText(/No suggestions yet/i)).toBeInTheDocument()
  })

  it("shows an error notice (not 'No suggestions yet') when the suggestions load fails", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = typeof input === "string" ? input : input.toString()
      const method = (init as RequestInit | undefined)?.method ?? "GET"
      if (url.includes("repository-suggestions")) {
        return Promise.resolve(jsonResponse({ detail: "Server error" }, 500))
      }
      if (url.includes("/gitlab/repositories") && method === "GET") {
        // Initial repositories load succeeds so the picker is not load-gated.
        return Promise.resolve(jsonResponse([]))
      }
      throw new Error(`unexpected fetch: ${method} ${url}`)
    })
    renderPicker()

    await screen.findByText(/Suggested repositories/i)
    // A failed suggestions load surfaces an alert and must NOT be misreported as empty.
    expect(await screen.findByRole("alert")).toBeInTheDocument()
    expect(screen.queryByText(/No suggestions yet/i)).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// Explicit confirmation: nothing pre-checked; confirming sends PUT (§12)
// ---------------------------------------------------------------------------

describe("GitLabRepositoryPicker: explicit confirmation", () => {
  it("renders suggestion checkboxes in an unchecked state by default", async () => {
    mockApi({ suggestions: suggestionsData })
    renderPicker()

    const checkbox = await screen.findByRole("checkbox", {
      name: /Confirm acme\/frontend/i,
    })
    // Nothing is pre-checked (§12).
    expect(checkbox).not.toBeChecked()
  })

  it("confirming a suggestion sends PUT containing its gitlab_project_id", async () => {
    const fetchMock = mockApi({
      suggestions: suggestionsData,
      putResponse: [savedRepo201],
    })
    renderPicker()

    const checkbox = await screen.findByRole("checkbox", {
      name: /Confirm acme\/frontend/i,
    })
    fireEvent.click(checkbox)

    // PUT must have been sent with the confirmed repo's gitlab_project_id.
    await waitFor(() => {
      const putCalls = fetchMock.mock.calls.filter(
        (args) => (args[1] as RequestInit | undefined)?.method === "PUT",
      )
      expect(putCalls).toHaveLength(1)
      const body = JSON.parse(
        (putCalls[0][1] as RequestInit).body as string,
      ) as Array<{ gitlab_project_id: number }>
      expect(body).toContainEqual({ gitlab_project_id: 201 })
    })
  })

  it("confirmed repo appears as a removable chip and is removed from suggestions", async () => {
    mockApi({
      suggestions: suggestionsData,
      putResponse: [savedRepo201],
    })
    renderPicker()

    const checkbox = await screen.findByRole("checkbox", {
      name: /Confirm acme\/frontend/i,
    })
    fireEvent.click(checkbox)

    // The chip should appear in the confirmed list after the PUT resolves.
    await screen.findByRole("list", { name: "Confirmed repositories" })
    expect(screen.getByRole("button", { name: /Remove frontend/ })).toBeInTheDocument()

    // The suggestion checkbox for "frontend" must no longer be present.
    await waitFor(() => {
      expect(
        screen.queryByRole("checkbox", { name: /Confirm acme\/frontend/i }),
      ).not.toBeInTheDocument()
    })
  })
})

// ---------------------------------------------------------------------------
// Add-repository autocomplete: debounced project-search, selection-only (§13, §24)
// ---------------------------------------------------------------------------

describe("GitLabRepositoryPicker: add-repository autocomplete", () => {
  it("does not fire a search request while typing and fires exactly one after settling", async () => {
    const fetchMock = mockApi({ searchResponse: searchResultsData })
    renderPicker()

    const input = await screen.findByRole("combobox")

    // Type four characters in rapid succession (all within the debounce window).
    fireEvent.change(input, { target: { value: "b" } })
    fireEvent.change(input, { target: { value: "ba" } })
    fireEvent.change(input, { target: { value: "bac" } })
    fireEvent.change(input, { target: { value: "back" } })

    // Immediately after typing: no project-search request yet.
    const earlySearchCalls = fetchMock.mock.calls.filter(([url]) =>
      String(url).includes("project-search"),
    )
    expect(earlySearchCalls).toHaveLength(0)

    // After the debounce window (~300 ms) plus fetch round-trip: exactly one search call.
    await waitFor(
      () => {
        const searchCalls = fetchMock.mock.calls.filter(([url]) =>
          String(url).includes("project-search"),
        )
        expect(searchCalls).toHaveLength(1)
        expect(String(searchCalls[0][0])).toContain("q=back")
      },
      { timeout: 1500 },
    )
  })

  it("selecting a search result adds it as a chip and sends PUT", async () => {
    const savedBackend = {
      id: "repo-3",
      team_profile_id: teamId,
      connection_id: connectionId,
      gitlab_project_id: 301,
      name: "backend",
      path_with_namespace: "acme/backend",
      verification_status: "verified",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    }
    const fetchMock = mockApi({
      searchResponse: searchResultsData,
      putResponse: [savedBackend],
    })
    renderPicker()

    const input = await screen.findByRole("combobox")
    fireEvent.change(input, { target: { value: "back" } })

    const option = await screen.findByRole("option", { name: /acme\/backend/ })
    fireEvent.mouseDown(option)

    // Chip should appear.
    await screen.findByRole("list", { name: "Confirmed repositories" })
    expect(screen.getByRole("button", { name: /Remove backend/ })).toBeInTheDocument()

    // PUT must have been sent with the selected repo's gitlab_project_id.
    await waitFor(() => {
      const putCalls = fetchMock.mock.calls.filter(
        (args) => (args[1] as RequestInit | undefined)?.method === "PUT",
      )
      expect(putCalls).toHaveLength(1)
      const body = JSON.parse(
        (putCalls[0][1] as RequestInit).body as string,
      ) as Array<{ gitlab_project_id: number }>
      expect(body).toContainEqual({ gitlab_project_id: 301 })
    })
  })

  it("typing and blurring without selecting adds nothing and sends no PUT", async () => {
    const fetchMock = mockApi({ searchResponse: [] })
    renderPicker()

    const input = await screen.findByRole("combobox")
    fireEvent.change(input, { target: { value: "nonexistent-project" } })
    fireEvent.blur(input)

    // No confirmed repos list should be rendered.
    expect(screen.queryByRole("list", { name: "Confirmed repositories" })).toBeNull()

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
// Removal: removing a chip sends PUT with reduced set
// ---------------------------------------------------------------------------

describe("GitLabRepositoryPicker: removal", () => {
  it("removing a confirmed repo sends PUT with the reduced set", async () => {
    const fetchMock = mockApi({
      initialRepos: [savedRepo201],
      putResponse: [],
    })
    renderPicker()

    // Wait for the chip from the initial GET to appear.
    await screen.findByRole("button", { name: /Remove frontend/ })

    fireEvent.click(screen.getByRole("button", { name: /Remove frontend/ }))

    // Chip must be gone immediately (optimistic update).
    expect(screen.queryByRole("button", { name: /Remove frontend/ })).toBeNull()

    // PUT sent with an empty array (no remaining repos).
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
// Full replace set: PUT must contain all confirmed ids, not just the delta
// ---------------------------------------------------------------------------

describe("GitLabRepositoryPicker: full replace set", () => {
  it("adding a second repo sends PUT with both ids (proves no delta-only regression)", async () => {
    const savedRepo202 = {
      ...savedRepo201,
      id: "repo-2",
      gitlab_project_id: 202,
      name: "utils",
      path_with_namespace: "acme/utils",
    }
    const fetchMock = mockApi({
      initialRepos: [savedRepo201], // frontend pre-confirmed
      suggestions: [suggestionsData[1]], // only "utils" suggestion (lower confidence)
      putResponse: [savedRepo201, savedRepo202],
    })
    renderPicker()

    // Wait for the initial chip to load.
    await screen.findByRole("button", { name: /Remove frontend/ })

    // Confirm the "utils" suggestion.
    const checkbox = await screen.findByRole("checkbox", {
      name: /Confirm acme\/utils/i,
    })
    fireEvent.click(checkbox)

    // PUT body must contain BOTH ids (full replace, not delta-only).
    await waitFor(() => {
      const putCalls = fetchMock.mock.calls.filter(
        (args) => (args[1] as RequestInit | undefined)?.method === "PUT",
      )
      expect(putCalls).toHaveLength(1)
      const body = JSON.parse(
        (putCalls[0][1] as RequestInit).body as string,
      ) as Array<{ gitlab_project_id: number }>
      expect(body).toHaveLength(2)
      expect(body).toContainEqual({ gitlab_project_id: 201 })
      expect(body).toContainEqual({ gitlab_project_id: 202 })
    })
  })
})

// ---------------------------------------------------------------------------
// Connection filter: repos anchored to a different connection are not seeded
// ---------------------------------------------------------------------------

describe("GitLabRepositoryPicker: connection filter", () => {
  it("does not seed or re-send repos anchored to a different connection", async () => {
    const staleRepo = {
      ...savedRepo201,
      id: "repo-stale",
      connection_id: "conn-OTHER",
      gitlab_project_id: 999,
      name: "stale-project",
      path_with_namespace: "acme/stale-project",
    }
    const savedBackend = {
      id: "repo-3",
      team_profile_id: teamId,
      connection_id: connectionId,
      gitlab_project_id: 301,
      name: "backend",
      path_with_namespace: "acme/backend",
      verification_status: "verified",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    }
    const fetchMock = mockApi({
      initialRepos: [savedRepo201, staleRepo],
      searchResponse: searchResultsData,
      putResponse: [savedRepo201, savedBackend],
    })
    renderPicker()

    // Only the active-connection repo is shown; the stale-connection repo is not.
    await screen.findByRole("button", { name: /Remove frontend/ })
    expect(screen.queryByText("stale-project")).not.toBeInTheDocument()

    // Add a repo via search; the PUT must not include the stale-connection id (999).
    const input = await screen.findByRole("combobox")
    fireEvent.change(input, { target: { value: "back" } })
    const option = await screen.findByRole("option", { name: /acme\/backend/ })
    fireEvent.mouseDown(option)

    await waitFor(() => {
      const putCalls = fetchMock.mock.calls.filter(
        (args) => (args[1] as RequestInit | undefined)?.method === "PUT",
      )
      expect(putCalls).toHaveLength(1)
      const body = JSON.parse(
        (putCalls[0][1] as RequestInit).body as string,
      ) as Array<{ gitlab_project_id: number }>
      expect(body).toContainEqual({ gitlab_project_id: 201 })
      expect(body).toContainEqual({ gitlab_project_id: 301 })
      expect(body).not.toContainEqual({ gitlab_project_id: 999 })
    })
  })
})

// ---------------------------------------------------------------------------
// Serialized writes: picker disabled while a replace PUT is in flight
// ---------------------------------------------------------------------------

describe("GitLabRepositoryPicker: serialized writes", () => {
  it("disables the combobox, checkboxes, and remove buttons while a save is pending", async () => {
    let resolvePut!: (r: Response) => void
    const pendingPut = new Promise<Response>((resolve) => {
      resolvePut = resolve
    })
    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = typeof input === "string" ? input : input.toString()
      const method = (init as RequestInit | undefined)?.method ?? "GET"
      if (url.includes("repository-suggestions")) {
        return Promise.resolve(jsonResponse(suggestionsData))
      }
      if (url.includes("project-search")) {
        return Promise.resolve(jsonResponse(searchResultsData))
      }
      if (url.includes("/gitlab/repositories")) {
        if (method === "PUT") return pendingPut
        return Promise.resolve(jsonResponse([savedRepo201]))
      }
      throw new Error(`unexpected fetch: ${method} ${url}`)
    })
    renderPicker()

    // Wait for the existing chip (with its remove button) to load.
    await screen.findByRole("button", { name: /Remove frontend/ })

    // Confirm a suggestion — the PUT stays pending, and the existing chip (and its
    // remove button) remains, so we can assert the remove button is disabled too.
    const checkboxesBefore = screen.getAllByRole("checkbox")
    fireEvent.click(checkboxesBefore[0])

    // While pending: the combobox is disabled.
    await waitFor(() => {
      expect(screen.getByRole("combobox")).toBeDisabled()
    })

    // The remaining suggestion checkboxes are disabled.
    screen.queryAllByRole("checkbox").forEach((cb) => {
      expect(cb).toBeDisabled()
    })

    // The existing chip's remove button is disabled while the save is in flight.
    expect(screen.getByRole("button", { name: /Remove frontend/ })).toBeDisabled()

    // Clean up the hanging promise.
    resolvePut(jsonResponse([]))
  })
})

// ---------------------------------------------------------------------------
// Load gate: a failed initial GET must not enable a destructive replace
// ---------------------------------------------------------------------------

describe("GitLabRepositoryPicker: load gate", () => {
  it("shows an error and prevents any PUT when the initial repositories load fails", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = typeof input === "string" ? input : input.toString()
      const method = (init as RequestInit | undefined)?.method ?? "GET"
      if (url.includes("repository-suggestions")) {
        return Promise.resolve(jsonResponse([]))
      }
      if (url.includes("/gitlab/repositories")) {
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

    // No suggestion checkboxes either.
    expect(screen.queryAllByRole("checkbox")).toHaveLength(0)

    // No PUT was sent.
    const putCalls = fetchMock.mock.calls.filter(
      (args) => (args[1] as RequestInit | undefined)?.method === "PUT",
    )
    expect(putCalls).toHaveLength(0)
  })
})

// ---------------------------------------------------------------------------
// Connection change re-seed: picker re-seeds when connectionId prop changes
// (Testing-library rerender keeps the SAME instance so this exercises the
// internal seededConnectionId guard, not a parent-key remount.)
// ---------------------------------------------------------------------------

describe("GitLabRepositoryPicker: connection change re-seed", () => {
  it("re-seeds from the new connection and clears the old connection's chips", async () => {
    const repoA = {
      id: "repo-a",
      team_profile_id: teamId,
      connection_id: "conn-A",
      gitlab_project_id: 101,
      name: "repo-alpha",
      path_with_namespace: "acme/repo-alpha",
      verification_status: "verified",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    }
    const repoB = {
      id: "repo-b",
      team_profile_id: teamId,
      connection_id: "conn-B",
      gitlab_project_id: 202,
      name: "repo-beta",
      path_with_namespace: "acme/repo-beta",
      verification_status: "verified",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    }
    // The repositories GET always returns both rows; the seed effect filters by connectionId.
    mockApi({ initialRepos: [repoA, repoB] })

    const queryClient = new QueryClient({
      defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
    })

    const { rerender } = render(
      <QueryClientProvider client={queryClient}>
        <GitLabRepositoryPicker connectionId="conn-A" teamId={teamId} />
      </QueryClientProvider>,
    )

    // Initial seed: only the conn-A chip should appear.
    await screen.findByRole("button", { name: /Remove repo-alpha/ })
    expect(screen.queryByRole("button", { name: /Remove repo-beta/ })).toBeNull()

    // Rerender the SAME component instance with a different connectionId.
    // seededConnectionId ("conn-A") !== connectionId ("conn-B") so re-seed fires.
    rerender(
      <QueryClientProvider client={queryClient}>
        <GitLabRepositoryPicker connectionId="conn-B" teamId={teamId} />
      </QueryClientProvider>,
    )

    // After re-seed: conn-B chip appears and conn-A chip is gone.
    await screen.findByRole("button", { name: /Remove repo-beta/ })
    expect(screen.queryByRole("button", { name: /Remove repo-alpha/ })).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// onError rollback: a failed PUT must revert the optimistic update
// ---------------------------------------------------------------------------

describe("GitLabRepositoryPicker: PUT failure rollback", () => {
  it("rolls back the optimistic update and shows an error when PUT fails", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = typeof input === "string" ? input : input.toString()
      const method = (init as RequestInit | undefined)?.method ?? "GET"
      if (url.includes("repository-suggestions")) {
        return Promise.resolve(jsonResponse(suggestionsData))
      }
      if (url.includes("project-search")) {
        return Promise.resolve(jsonResponse(searchResultsData))
      }
      if (url.includes("/gitlab/repositories")) {
        if (method === "PUT") {
          return Promise.resolve(jsonResponse({ detail: "Server error" }, 500))
        }
        return Promise.resolve(jsonResponse([savedRepo201])) // initial GET succeeds
      }
      throw new Error(`unexpected fetch: ${method} ${url}`)
    })
    renderPicker()

    // Wait for the existing chip to load.
    await screen.findByRole("button", { name: /Remove frontend/ })

    // Attempt to remove the chip — the PUT fails.
    fireEvent.click(screen.getByRole("button", { name: /Remove frontend/ }))

    // After the PUT fails, the optimistic removal must be rolled back.
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Remove frontend/ })).toBeInTheDocument()
    })

    // An inline error alert must be visible.
    expect(screen.getByRole("alert")).toBeInTheDocument()
  })
})
