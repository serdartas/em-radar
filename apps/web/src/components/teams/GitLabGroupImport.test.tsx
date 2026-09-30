// SPDX-License-Identifier: Apache-2.0
//
// M9-14: Group member import — these tests must FAIL before the feature is
// implemented and PASS after. They mirror the GitLabMemberPicker.test.tsx pattern.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { GitLabMemberPicker } from "@/components/teams/GitLabMemberPicker"

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const teamId = "team-group-import"
const connectionId = "conn-group"

const groupSearchResults = [
  { provider_group_id: "7", name: "Frontend", full_path: "acme/frontend" },
  { provider_group_id: "8", name: "Backend", full_path: "acme/backend" },
]

const groupMembers = [
  {
    provider_user_id: "101",
    username: "alice",
    display_name: "Alice",
    avatar_url: null,
  },
  {
    provider_user_id: "102",
    username: "bob",
    display_name: "Bob",
    avatar_url: null,
  },
]

const existingMember = {
  id: "mbr-99",
  team_profile_id: teamId,
  connection_id: connectionId,
  gitlab_user_id: 99,
  username: "existing",
  display_name: "Existing User",
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

interface MockGroupApiOptions {
  initialMembers?: unknown[]
  groupSearchResponse?: unknown[]
  groupMembersResponse?: unknown[]
  putResponse?: unknown[]
}

/**
 * Mock fetch for the group import flow.
 *
 * - GET .../gitlab/members         -> initialMembers
 * - GET .../gitlab/group-search?.. -> groupSearchResponse
 * - GET .../gitlab/group-members?. -> groupMembersResponse
 * - PUT .../gitlab/members         -> putResponse
 */
function mockGroupApi({
  initialMembers = [],
  groupSearchResponse = groupSearchResults,
  groupMembersResponse = groupMembers,
  putResponse = [],
}: MockGroupApiOptions = {}) {
  return vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    const url = typeof input === "string" ? input : input.toString()
    const method = (init as RequestInit | undefined)?.method ?? "GET"

    if (url.includes("group-search")) {
      return Promise.resolve(jsonResponse(groupSearchResponse))
    }
    if (url.includes("group-members")) {
      return Promise.resolve(jsonResponse(groupMembersResponse))
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
// Toggle: "Import from group" button shows/hides the group import panel
// ---------------------------------------------------------------------------

describe("GitLabGroupImport: panel toggle", () => {
  it("shows the group import panel when the toggle button is clicked", async () => {
    mockGroupApi()
    renderPicker()

    await screen.findByRole("button", { name: "Import candidates from GitLab group" })

    // Group search input should not be visible yet.
    expect(screen.queryByRole("combobox", { name: /Search GitLab groups/i })).toBeNull()

    fireEvent.click(
      screen.getByRole("button", { name: "Import candidates from GitLab group" }),
    )

    // Now the group search combobox should be visible.
    expect(
      screen.getByRole("combobox", { name: /Search GitLab groups/i }),
    ).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Manual search remains available alongside the group import panel
// ---------------------------------------------------------------------------

describe("GitLabGroupImport: manual search still present", () => {
  it("manual member search combobox is visible alongside the group import panel", async () => {
    mockGroupApi()
    renderPicker()

    // Wait for initial load.
    await screen.findByRole("button", { name: "Import candidates from GitLab group" })

    // Open the group panel.
    fireEvent.click(
      screen.getByRole("button", { name: "Import candidates from GitLab group" }),
    )

    // Both the manual search combobox and the group search combobox are present.
    const comboboxes = screen.getAllByRole("combobox")
    expect(comboboxes.length).toBeGreaterThanOrEqual(2)
    expect(screen.getByRole("combobox", { name: /Search GitLab members/i })).toBeInTheDocument()
    expect(screen.getByRole("combobox", { name: /Search GitLab groups/i })).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Candidate listing: selecting a group lists its members as unchecked checkboxes
// ---------------------------------------------------------------------------

describe("GitLabGroupImport: candidate listing", () => {
  it("selecting a group lists its members as candidates with unchecked checkboxes", async () => {
    mockGroupApi()
    renderPicker()

    await screen.findByRole("button", { name: "Import candidates from GitLab group" })
    fireEvent.click(
      screen.getByRole("button", { name: "Import candidates from GitLab group" }),
    )

    // Type in the group search to get results.
    const groupCombobox = screen.getByRole("combobox", { name: /Search GitLab groups/i })
    fireEvent.change(groupCombobox, { target: { value: "acme" } })

    // Wait for group option to appear and select it.
    const groupOption = await screen.findByRole("option", { name: /Frontend/ })
    fireEvent.mouseDown(groupOption)

    // Group members should load and appear as checkboxes, none pre-checked.
    const aliceCheckbox = await screen.findByRole("checkbox", { name: /Select Alice/ })
    const bobCheckbox = screen.getByRole("checkbox", { name: /Select Bob/ })

    expect(aliceCheckbox).not.toBeChecked()
    expect(bobCheckbox).not.toBeChecked()

    // No PUT should have been sent yet.
    await waitFor(() => {
      const putCalls = (
        vi.mocked(globalThis.fetch).mock.calls.filter(
          (args) => (args[1] as RequestInit | undefined)?.method === "PUT",
        )
      )
      expect(putCalls).toHaveLength(0)
    })
  })
})

// ---------------------------------------------------------------------------
// Nothing added until confirmed: Add selected button is disabled with no selection
// ---------------------------------------------------------------------------

describe("GitLabGroupImport: nothing added until confirmed", () => {
  it("Add selected button is disabled when no candidates are checked", async () => {
    mockGroupApi()
    renderPicker()

    await screen.findByRole("button", { name: "Import candidates from GitLab group" })
    fireEvent.click(
      screen.getByRole("button", { name: "Import candidates from GitLab group" }),
    )

    const groupCombobox = screen.getByRole("combobox", { name: /Search GitLab groups/i })
    fireEvent.change(groupCombobox, { target: { value: "acme" } })
    const groupOption = await screen.findByRole("option", { name: /Frontend/ })
    fireEvent.mouseDown(groupOption)

    // Wait for candidate list to appear.
    await screen.findByRole("checkbox", { name: /Select Alice/ })

    // Add selected button exists but is disabled.
    const addBtn = screen.getByRole("button", { name: /Add selected \(0\)/ })
    expect(addBtn).toBeDisabled()

    // Confirm no PUT sent.
    await waitFor(() => {
      const putCalls = (
        vi.mocked(globalThis.fetch).mock.calls.filter(
          (args) => (args[1] as RequestInit | undefined)?.method === "PUT",
        )
      )
      expect(putCalls).toHaveLength(0)
    })
  })
})

// ---------------------------------------------------------------------------
// Only selected candidates added: PUT body contains only checked members, unioned with existing
// ---------------------------------------------------------------------------

describe("GitLabGroupImport: only selected candidates added", () => {
  it("PUT body includes only checked candidates, unioned with existing members", async () => {
    const aliceSaved = {
      id: "mbr-101",
      team_profile_id: teamId,
      connection_id: connectionId,
      gitlab_user_id: 101,
      username: "alice",
      display_name: "Alice",
      verification_status: "verified",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    }
    const fetchMock = mockGroupApi({
      initialMembers: [existingMember],
      putResponse: [existingMember, aliceSaved],
    })
    renderPicker()

    // Wait for the existing member chip.
    await screen.findByText("Existing User @existing")

    fireEvent.click(
      screen.getByRole("button", { name: "Import candidates from GitLab group" }),
    )

    const groupCombobox = screen.getByRole("combobox", { name: /Search GitLab groups/i })
    fireEvent.change(groupCombobox, { target: { value: "acme" } })
    const groupOption = await screen.findByRole("option", { name: /Frontend/ })
    fireEvent.mouseDown(groupOption)

    // Check only Alice; leave Bob unchecked.
    const aliceCheckbox = await screen.findByRole("checkbox", { name: /Select Alice/ })
    fireEvent.click(aliceCheckbox)

    // Confirm count rises to 1.
    expect(screen.getByRole("button", { name: /Add selected \(1\)/ })).toBeInTheDocument()

    // Click Add selected.
    fireEvent.click(screen.getByRole("button", { name: /Add selected \(1\)/ }))

    // PUT body must contain the existing member (gitlab_user_id: 99) and Alice (101),
    // but not Bob (102).
    await waitFor(() => {
      const putCalls = fetchMock.mock.calls.filter(
        (args) => (args[1] as RequestInit | undefined)?.method === "PUT",
      )
      expect(putCalls).toHaveLength(1)
      const body = JSON.parse(
        (putCalls[0][1] as RequestInit).body as string,
      ) as Array<{ gitlab_user_id: number }>
      expect(body).toContainEqual({ gitlab_user_id: 99 })  // existing member
      expect(body).toContainEqual({ gitlab_user_id: 101 })  // Alice (checked)
      expect(body).not.toContainEqual({ gitlab_user_id: 102 })  // Bob (not checked)
    })
  })
})

// ---------------------------------------------------------------------------
// Already-added members shown as checked+disabled (not re-addable)
// ---------------------------------------------------------------------------

describe("GitLabGroupImport: already-added members are disabled", () => {
  it("group member already in the selection is shown as checked and disabled", async () => {
    // alice (gitlab_user_id: 101, provider_user_id: "101") is already a member.
    const aliceExisting = {
      id: "mbr-101",
      team_profile_id: teamId,
      connection_id: connectionId,
      gitlab_user_id: 101,
      username: "alice",
      display_name: "Alice",
      verification_status: "verified",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    }
    mockGroupApi({ initialMembers: [aliceExisting] })
    renderPicker()

    await screen.findByText("Alice @alice")

    fireEvent.click(
      screen.getByRole("button", { name: "Import candidates from GitLab group" }),
    )

    const groupCombobox = screen.getByRole("combobox", { name: /Search GitLab groups/i })
    fireEvent.change(groupCombobox, { target: { value: "acme" } })
    const groupOption = await screen.findByRole("option", { name: /Frontend/ })
    fireEvent.mouseDown(groupOption)

    // Alice should appear as checked and disabled in the candidate list.
    const aliceCheckbox = await screen.findByRole("checkbox", { name: /Select Alice/ })
    expect(aliceCheckbox).toBeChecked()
    expect(aliceCheckbox).toBeDisabled()

    // Bob should be unchecked and enabled.
    const bobCheckbox = screen.getByRole("checkbox", { name: /Select Bob/ })
    expect(bobCheckbox).not.toBeChecked()
    expect(bobCheckbox).not.toBeDisabled()
  })
})
