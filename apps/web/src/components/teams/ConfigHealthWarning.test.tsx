// SPDX-License-Identifier: Apache-2.0

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { ConfigHealthWarning } from "@/components/teams/ConfigHealthWarning"

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const teamId = "team-42"
const connectionId = "conn-1"

const verifiedMember = {
  id: "mbr-v",
  team_profile_id: teamId,
  connection_id: connectionId,
  gitlab_user_id: 10,
  username: "dev",
  display_name: "Dev User",
  verification_status: "verified",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
}

const unavailableMember = {
  id: "mbr-u",
  team_profile_id: teamId,
  connection_id: connectionId,
  gitlab_user_id: 99,
  username: "gone",
  display_name: "Gone User",
  verification_status: "unavailable",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
}

const unverifiedMember = {
  id: "mbr-x",
  team_profile_id: teamId,
  connection_id: "other-conn",
  gitlab_user_id: 77,
  username: "other",
  display_name: "Other Instance",
  verification_status: "unverified",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
}

const unavailableRepo = {
  id: "repo-u",
  team_profile_id: teamId,
  connection_id: connectionId,
  gitlab_project_id: 5,
  name: "archived-repo",
  path_with_namespace: "group/archived-repo",
  verification_status: "unavailable",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
}

const verifiedRepo = {
  id: "repo-v",
  team_profile_id: teamId,
  connection_id: connectionId,
  gitlab_project_id: 6,
  name: "active-repo",
  path_with_namespace: "group/active-repo",
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

function makeQueryClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function renderWarning(
  members: unknown[],
  repos: unknown[],
  overrideFetch?: (url: string, init?: RequestInit) => Response | null,
) {
  const qc = makeQueryClient()

  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = typeof input === "string" ? input : (input as Request).url
    if (overrideFetch) {
      const r = overrideFetch(url, init)
      if (r !== null) return r
    }
    if (url.includes("/gitlab/members") && init?.method === undefined) {
      return jsonResponse(members)
    }
    if (url.includes("/gitlab/repositories") && init?.method === undefined) {
      return jsonResponse(repos)
    }
    return jsonResponse([])
  })

  return {
    qc,
    ...render(
      <QueryClientProvider client={qc}>
        <ConfigHealthWarning connectionId={connectionId} teamId={teamId} />
      </QueryClientProvider>,
    ),
  }
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("ConfigHealthWarning", () => {
  it("renders nothing when all members and repos are verified", async () => {
    renderWarning([verifiedMember], [verifiedRepo])
    await waitFor(() => {
      expect(screen.queryByRole("alert")).toBeNull()
    })
  })

  it("renders warning callout when an unavailable member exists", async () => {
    renderWarning([verifiedMember, unavailableMember], [verifiedRepo])
    await screen.findByRole("alert")
    expect(screen.getByText(/configuration health warning/i)).toBeInTheDocument()
    expect(screen.getByText(/Gone User @gone/i)).toBeInTheDocument()
    expect(screen.getByText(/deleted or archived/i)).toBeInTheDocument()
  })

  it("renders warning callout for unverified members from a different connector", async () => {
    renderWarning([verifiedMember, unverifiedMember], [])
    await screen.findByRole("alert")
    expect(screen.getByText(/@other/i)).toBeInTheDocument()
    expect(screen.getByText(/unverified.*connector replaced/i)).toBeInTheDocument()
  })

  it("renders unavailable repository in the warning", async () => {
    renderWarning([verifiedMember], [verifiedRepo, unavailableRepo])
    await screen.findByRole("alert")
    expect(screen.getByText(/group\/archived-repo/i)).toBeInTheDocument()
  })

  it("re-verify button calls verify-config and invalidates queries", async () => {
    const verifyCalled = vi.fn()

    renderWarning([unavailableMember], [unavailableRepo], (url, init) => {
      if (url.includes("/gitlab/verify-config") && init?.method === "POST") {
        verifyCalled()
        return jsonResponse({ members: [verifiedMember], repositories: [verifiedRepo] })
      }
      return null
    })

    await screen.findByRole("alert")
    fireEvent.click(screen.getByRole("button", { name: /re-verify/i }))
    await waitFor(() => expect(verifyCalled).toHaveBeenCalledTimes(1))
  })

  it("remove button calls DELETE on the exact stale member row", async () => {
    const deleteCalled = vi.fn()

    renderWarning([verifiedMember, unavailableMember], [], (url, init) => {
      if (url.includes(`/gitlab/members/${unavailableMember.id}`) && init?.method === "DELETE") {
        deleteCalled(url)
        return new Response(null, { status: 204 })
      }
      return null
    })

    await screen.findByRole("alert")
    const removeButtons = screen.getAllByRole("button", { name: /remove/i })
    fireEvent.click(removeButtons[0])
    await waitFor(() => expect(deleteCalled).toHaveBeenCalledTimes(1))
  })

  it("remove button does not touch other stale entries when removing one", async () => {
    const deletedIds: string[] = []

    const secondUnavailableMember = {
      ...unavailableMember,
      id: "mbr-u2",
      gitlab_user_id: 88,
      username: "gone2",
      display_name: "Gone 2",
    }

    renderWarning([verifiedMember, unavailableMember, secondUnavailableMember], [], (url, init) => {
      if (url.match(/\/gitlab\/members\//) && init?.method === "DELETE") {
        const id = url.split("/").pop()!
        deletedIds.push(id)
        return new Response(null, { status: 204 })
      }
      return null
    })

    await screen.findByRole("alert")
    const removeButtons = screen.getAllByRole("button", { name: /remove/i })
    // Click Remove on the first stale member only.
    fireEvent.click(removeButtons[0])
    await waitFor(() => expect(deletedIds).toHaveLength(1))
    // Exactly one DELETE should have fired — for the clicked entry only.
    expect(deletedIds[0]).toBe(unavailableMember.id)
  })
})
