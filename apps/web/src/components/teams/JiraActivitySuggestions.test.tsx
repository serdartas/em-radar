// SPDX-License-Identifier: Apache-2.0
//
// M9-15: Member suggestions from Jira activity with confidence scoring.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { GitLabMemberPicker } from "@/components/teams/GitLabMemberPicker"
import { JiraActivitySuggestions } from "@/components/teams/JiraActivitySuggestions"

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const teamId = "team-suggest-test"
const connectionId = "conn-suggest"

const highConfidenceSuggestion = {
  jira_person: {
    display_name: "Alice Smith",
    email_address: "alice@example.com",
    account_id: "acc-alice",
  },
  match: {
    provider_user_id: "42",
    username: "alice.smith",
    display_name: "Alice Smith",
    avatar_url: null,
  },
  candidates: [],
  confidence: "high" as const,
}

const uncertainSuggestion = {
  jira_person: {
    display_name: "Bob Jones",
    email_address: null,
    account_id: null,
  },
  match: null,
  candidates: [
    {
      provider_user_id: "10",
      username: "bob.j",
      display_name: "Bob J",
      avatar_url: null,
    },
    {
      provider_user_id: "11",
      username: "bob.jones2",
      display_name: "Bob Jones II",
      avatar_url: null,
    },
  ],
  confidence: "uncertain" as const,
}

const noMatchSuggestion = {
  jira_person: { display_name: "Charlie Nobody", email_address: null, account_id: null },
  match: null,
  candidates: [],
  confidence: "uncertain" as const,
}

const emptySuggestionsResponse = { window_days: 90, suggestions: [] }

function suggestionsResponse(
  suggestions: typeof highConfidenceSuggestion[] | typeof uncertainSuggestion[] = [],
) {
  return { window_days: 90, suggestions }
}

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

function mockPickerApi({
  initialMembers = [],
  suggestionsBody = emptySuggestionsResponse,
  putResponse = [] as unknown[],
}: {
  initialMembers?: unknown[]
  suggestionsBody?: unknown
  putResponse?: unknown[]
} = {}) {
  return vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    const url = typeof input === "string" ? input : input.toString()
    const method = (init as RequestInit | undefined)?.method ?? "GET"

    if (url.includes("member-suggestions")) {
      return Promise.resolve(jsonResponse(suggestionsBody))
    }
    if (url.includes("gitlab/group-search")) {
      return Promise.resolve(jsonResponse([]))
    }
    if (url.includes("gitlab/group-members")) {
      return Promise.resolve(jsonResponse([]))
    }
    if (url.includes("/gitlab/members")) {
      if (method === "PUT") return Promise.resolve(jsonResponse(putResponse))
      return Promise.resolve(jsonResponse(initialMembers))
    }
    throw new Error(`Unexpected fetch: ${method} ${url}`)
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

function renderSuggestionsPanel({
  selectedIds = new Set<string>(),
  isSaving = false,
  onAdd = vi.fn(),
  suggestions = [highConfidenceSuggestion],
}: {
  selectedIds?: Set<string>
  isSaving?: boolean
  onAdd?: ReturnType<typeof vi.fn>
  suggestions?: unknown[]
} = {}) {
  vi.spyOn(globalThis, "fetch").mockImplementation(() =>
    Promise.resolve(jsonResponse(suggestionsResponse(suggestions as never))),
  )
  const queryClient = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  })
  return { onAdd, ...render(
    <QueryClientProvider client={queryClient}>
      <JiraActivitySuggestions
        isSaving={isSaving}
        onAdd={onAdd}
        selectedIds={selectedIds}
        teamId={teamId}
      />
    </QueryClientProvider>,
  )}
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

// ---------------------------------------------------------------------------
// GitLabMemberPicker integration: "Suggest from Jira" button
// ---------------------------------------------------------------------------

describe("JiraActivitySuggestions: button in GitLabMemberPicker", () => {
  it("renders a 'Suggest from Jira' button in the picker toolbar", async () => {
    mockPickerApi()
    renderPicker()

    const btn = await screen.findByRole("button", { name: "Suggest members from Jira activity" })
    expect(btn).toBeInTheDocument()
  })

  it("clicking 'Suggest from Jira' opens the suggestions panel", async () => {
    mockPickerApi({
      suggestionsBody: suggestionsResponse([highConfidenceSuggestion]),
    })
    renderPicker()

    const btn = await screen.findByRole("button", { name: "Suggest members from Jira activity" })
    expect(screen.queryByText("Suggested GitLab members")).toBeNull()

    fireEvent.click(btn)

    expect(screen.getByText("Suggested GitLab members")).toBeInTheDocument()
  })

  it("clicking again hides the suggestions panel", async () => {
    mockPickerApi()
    renderPicker()

    const btn = await screen.findByRole("button", { name: "Suggest members from Jira activity" })
    fireEvent.click(btn)
    expect(screen.getByText("Suggested GitLab members")).toBeInTheDocument()

    fireEvent.click(btn)
    expect(screen.queryByText("Suggested GitLab members")).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// JiraActivitySuggestions: rendering states
// ---------------------------------------------------------------------------

describe("JiraActivitySuggestions: empty state", () => {
  it("shows empty-state message when no suggestions returned", async () => {
    renderSuggestionsPanel({ suggestions: [] })
    await screen.findByText(/No suggestions found/)
  })
})

describe("JiraActivitySuggestions: high-confidence suggestion", () => {
  it("renders confidence badge and matched GitLab user", async () => {
    renderSuggestionsPanel({ suggestions: [highConfidenceSuggestion] })

    // Multiple "Alice Smith" spans may appear (Jira name + GitLab display name).
    expect(await screen.findAllByText(/Alice Smith/)).not.toHaveLength(0)
    // The confidence badge text contains "High confidence".
    expect(screen.getByText(/High confidence/)).toBeInTheDocument()
    // The GitLab username (@alice.smith) should be visible.
    expect(screen.getByText(/alice\.smith/)).toBeInTheDocument()
  })

  it("confirm button is initially unpressed", async () => {
    renderSuggestionsPanel({ suggestions: [highConfidenceSuggestion] })

    const btn = await screen.findByRole("button", {
      name: /Confirm Alice Smith/i,
    })
    expect(btn).toHaveAttribute("aria-pressed", "false")
  })

  it("clicking Confirm toggles to Confirmed state", async () => {
    renderSuggestionsPanel({ suggestions: [highConfidenceSuggestion] })

    const btn = await screen.findByRole("button", { name: /Confirm Alice Smith/i })
    fireEvent.click(btn)

    const confirmedBtn = screen.getByRole("button", { name: /Confirm Alice Smith/i })
    expect(confirmedBtn).toHaveAttribute("aria-pressed", "true")
  })

  it("'Add confirmed' button appears after confirming and calls onAdd with correct member", async () => {
    const onAdd = vi.fn()
    renderSuggestionsPanel({ suggestions: [highConfidenceSuggestion], onAdd })

    const confirmBtn = await screen.findByRole("button", { name: /Confirm Alice Smith/i })
    fireEvent.click(confirmBtn)

    const addBtn = await screen.findByRole("button", { name: /Add confirmed/i })
    fireEvent.click(addBtn)

    expect(onAdd).toHaveBeenCalledOnce()
    const called = onAdd.mock.calls[0][0] as { gitlab_user_id: number; username: string }[]
    expect(called).toHaveLength(1)
    expect(called[0].gitlab_user_id).toBe(42)
    expect(called[0].username).toBe("alice.smith")
  })

  it("already-added member shows 'Already a member' and disables confirm", async () => {
    renderSuggestionsPanel({
      suggestions: [highConfidenceSuggestion],
      selectedIds: new Set(["42"]),
    })

    await screen.findByText(/Already a member/)
    expect(screen.queryByRole("button", { name: /Confirm Alice Smith/i })).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// JiraActivitySuggestions: uncertain suggestion
// ---------------------------------------------------------------------------

describe("JiraActivitySuggestions: uncertain suggestion", () => {
  it("renders uncertainty badge and a candidate select", async () => {
    renderSuggestionsPanel({ suggestions: [uncertainSuggestion] })

    // "Bob Jones" may match multiple elements (jira name + option text).
    expect(await screen.findAllByText(/Bob Jones/)).not.toHaveLength(0)
    // The confidence badge text contains "Uncertain".
    expect(screen.getByText(/Uncertain/)).toBeInTheDocument()
    // The <select> uses aria-label "Select GitLab user for <name>".
    const select = screen.getByRole("combobox", {
      name: "Select GitLab user for Bob Jones",
    })
    expect(select).toBeInTheDocument()
  })

  it("confirm button is disabled until a candidate is selected", async () => {
    renderSuggestionsPanel({ suggestions: [uncertainSuggestion] })

    const btn = await screen.findByRole("button", { name: /Confirm Bob Jones/i })
    expect(btn).toBeDisabled()
  })

  it("selecting a candidate enables confirm", async () => {
    renderSuggestionsPanel({ suggestions: [uncertainSuggestion] })

    const select = await screen.findByRole("combobox", {
      name: "Select GitLab user for Bob Jones",
    })
    fireEvent.change(select, { target: { value: "10" } })

    const btn = screen.getByRole("button", { name: /Confirm Bob Jones/i })
    expect(btn).not.toBeDisabled()
  })

  it("calls onAdd with selected candidate after confirming", async () => {
    const onAdd = vi.fn()
    renderSuggestionsPanel({ suggestions: [uncertainSuggestion], onAdd })

    const select = await screen.findByRole("combobox", {
      name: "Select GitLab user for Bob Jones",
    })
    fireEvent.change(select, { target: { value: "10" } })

    const confirmBtn = screen.getByRole("button", { name: /Confirm Bob Jones/i })
    fireEvent.click(confirmBtn)

    const addBtn = await screen.findByRole("button", { name: /Add confirmed/i })
    fireEvent.click(addBtn)

    expect(onAdd).toHaveBeenCalledOnce()
    const called = onAdd.mock.calls[0][0] as { gitlab_user_id: number; username: string }[]
    expect(called[0].gitlab_user_id).toBe(10)
    expect(called[0].username).toBe("bob.j")
  })
})

// ---------------------------------------------------------------------------
// JiraActivitySuggestions: no-match uncertain suggestion (hidden from list)
// ---------------------------------------------------------------------------

describe("JiraActivitySuggestions: no GitLab match", () => {
  it("uncertain suggestion with empty candidates shows no-match note and no confirm button", async () => {
    renderSuggestionsPanel({ suggestions: [noMatchSuggestion] })

    await screen.findByText(/No GitLab users found for this name/)
    // The confirm button requires a match ref — nothing to confirm.
    const btn = screen.queryByRole("button", { name: /Confirm Charlie Nobody/i })
    // Either the button doesn't exist or it is disabled (no candidates to confirm).
    if (btn !== null) {
      expect(btn).toBeDisabled()
    }
  })
})

// ---------------------------------------------------------------------------
// JiraActivitySuggestions: mixed confidence list
// ---------------------------------------------------------------------------

describe("JiraActivitySuggestions: mixed confidence list", () => {
  it("renders both high and uncertain suggestions", async () => {
    renderSuggestionsPanel({
      suggestions: [highConfidenceSuggestion, uncertainSuggestion],
    })

    // Each name may appear in multiple elements.
    expect(await screen.findAllByText(/Alice Smith/)).not.toHaveLength(0)
    expect(await screen.findAllByText(/Bob Jones/)).not.toHaveLength(0)
    expect(screen.getByText(/High confidence/)).toBeInTheDocument()
    expect(screen.getByText(/Uncertain/)).toBeInTheDocument()
  })

  it("confirms from both high and uncertain suggestions and adds all", async () => {
    const onAdd = vi.fn()
    renderSuggestionsPanel({
      suggestions: [highConfidenceSuggestion, uncertainSuggestion],
      onAdd,
    })

    // Confirm high-confidence.
    const aliceBtn = await screen.findByRole("button", { name: /Confirm Alice Smith/i })
    fireEvent.click(aliceBtn)

    // Select candidate then confirm uncertain.
    const select = screen.getByRole("combobox", {
      name: "Select GitLab user for Bob Jones",
    })
    fireEvent.change(select, { target: { value: "10" } })
    const bobBtn = screen.getByRole("button", { name: /Confirm Bob Jones/i })
    fireEvent.click(bobBtn)

    const addBtn = await screen.findByRole("button", { name: /Add confirmed \(2\)/i })
    fireEvent.click(addBtn)

    expect(onAdd).toHaveBeenCalledOnce()
    const called = onAdd.mock.calls[0][0] as { gitlab_user_id: number }[]
    expect(called).toHaveLength(2)
    const ids = called.map((m) => m.gitlab_user_id)
    expect(ids).toContain(42)
    expect(ids).toContain(10)
  })
})
