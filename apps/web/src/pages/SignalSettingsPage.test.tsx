import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"

import { SignalSettingsPage } from "@/pages/SignalSettingsPage"

const templates = [
  {
    key: "stale-in-progress-work-item",
    name: "Stale in-progress work item",
    description: "Finds stale Jira issues.",
    required_connector_type: "jira",
    entity_type: "issue",
    required_scope_capabilities: ["statuses"],
    expression: {
      type: "group",
      operator: "all",
      conditions: [
        {
          field: "age_in_current_status",
          operator: "greater_than",
          value: { amount: 7, unit: "days" },
        },
      ],
    },
    report_settings: { severity: "warning", category: "flow" },
  },
]

const scopes = [
  {
    id: "scrum-scope",
    connection_id: "jira-1",
    name: "Scrum Board",
    scope_type: "board",
    external_ref: { id: "1" },
    capabilities: ["sprint", "statuses", "labels"],
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
  {
    id: "project-scope",
    connection_id: "jira-1",
    name: "Support Project",
    scope_type: "project",
    external_ref: { key: "SUP" },
    capabilities: ["statuses", "labels"],
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
]

const connectors = [
  {
    name: "jira",
    display_name: "Jira",
    config_schema: { type: "object", properties: {} },
    capabilities: {
      provides_workitems: true,
      provides_sprints: true,
      provides_mergerequests: false,
      provides_repositories: false,
      provides_reviews: false,
      provides_comments: false,
      provides_transitions: true,
      supports_incremental_fetch: true,
      supports_pagination_cursor: false,
      max_window_days: null,
    },
    signal_schema: {
      connector_type: "jira",
      entity_types: ["issue"],
      scope_types: [],
      fields: [
        {
          key: "age_in_current_status",
          label: "Age in current status",
          type: "duration",
          operators: ["greater_than", "less_than"],
          values: [],
          value_provider: null,
          availability: null,
        },
        {
          key: "sprint_day",
          label: "Sprint day",
          type: "sprint_relative_day",
          operators: ["is_after"],
          values: [],
          value_provider: null,
          availability: { requires_scope_capability: ["sprint"] },
        },
        {
          key: "status_category",
          label: "Status Category",
          type: "enum",
          operators: ["is", "is_not"],
          values: ["todo", "in_progress", "done"],
          value_provider: null,
          availability: null,
        },
      ],
    },
  },
]

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  })
}

function mockApi() {
  return vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    const url = typeof input === "string" ? input : input.toString()
    const method = init?.method ?? "GET"
    if (url.endsWith("/api/signal-templates")) {
      return Promise.resolve(jsonResponse(templates))
    }
    if (url.endsWith("/api/signal-definitions") && method === "GET") {
      return Promise.resolve(jsonResponse([]))
    }
    if (url.endsWith("/api/connectors")) {
      return Promise.resolve(jsonResponse(connectors))
    }
    if (url.endsWith("/api/scopes")) {
      return Promise.resolve(jsonResponse(scopes))
    }
    if (url.endsWith("/api/signal-definitions/preview") && method === "POST") {
      const body = JSON.parse(String(init?.body))
      if (body.expression.conditions[0].field === "sprint_day") {
        return Promise.resolve(
          jsonResponse({
            match_count: 0,
            samples: [],
            warnings: ["sprint_day requires scope capability: sprint"],
          }),
        )
      }
      return Promise.resolve(
        jsonResponse({
          match_count: 2,
          samples: [
            {
              item_key: "RAD-1",
              title: "RAD-1 - Stale work",
              reason: "age_in_current_status greater_than 5 (observed 8)",
              evidence: { age_in_current_status: 8 },
            },
          ],
          warnings: [],
        }),
      )
    }
    if (url.endsWith("/api/signal-definitions") && method === "POST") {
      return Promise.resolve(jsonResponse({ id: "signal-1", ...JSON.parse(String(init?.body)) }))
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
        <SignalSettingsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("SignalSettingsPage", () => {
  it("duplicates a Jira template, previews, edits duration, and saves", async () => {
    const fetchMock = mockApi()
    renderPage()

    fireEvent.click(await screen.findByRole("button", { name: "Duplicate" }))
    fireEvent.change(screen.getByLabelText("Jira target scope"), {
      target: { value: "scrum-scope" },
    })
    fireEvent.change(screen.getByLabelText("Duration days"), { target: { value: "5" } })

    expect(await screen.findByText(/2 matching sample items/)).toBeInTheDocument()
    expect(screen.getByText(/age_in_current_status greater_than 5/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Save signal" }))

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([url, init]) => String(url).endsWith("/api/signal-definitions") && init?.method === "POST",
      )
      expect(call).toBeTruthy()
      const body = JSON.parse(String((call?.[1] as RequestInit).body))
      expect(body.target_scopes[0].scope_id).toBe("scrum-scope")
      expect(body.expression.conditions[0].value.amount).toBe(5)
    })
  })

  it("blocks an unsupported sprint field for a non-sprint scope", async () => {
    mockApi()
    renderPage()

    await screen.findByRole("button", { name: "Duplicate" })
    fireEvent.change(screen.getByLabelText("Jira target scope"), {
      target: { value: "project-scope" },
    })
    fireEvent.change(screen.getByLabelText("Field"), { target: { value: "sprint_day" } })

    expect(screen.getByText(/Sprint day requires sprint scope capability/)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Save signal" })).toBeDisabled()
  })

  it("preserves enum values when saving a non-duration condition", async () => {
    const fetchMock = mockApi()
    renderPage()

    await screen.findByRole("button", { name: "Duplicate" })
    fireEvent.change(screen.getByLabelText("Field"), { target: { value: "status_category" } })
    fireEvent.change(screen.getByLabelText("Value"), { target: { value: "in_progress" } })
    fireEvent.click(screen.getByRole("button", { name: "Save signal" }))

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([url, init]) => String(url).endsWith("/api/signal-definitions") && init?.method === "POST",
      )
      expect(call).toBeTruthy()
      const body = JSON.parse(String((call?.[1] as RequestInit).body))
      expect(body.expression.conditions[0]).toMatchObject({
        field: "status_category",
        operator: "is",
        value: "in_progress",
      })
    })
  })
})
