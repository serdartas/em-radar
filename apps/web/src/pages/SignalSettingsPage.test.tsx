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
  it("renders the builder with no scope control", async () => {
    mockApi()
    renderPage()

    await screen.findByRole("button", { name: "Duplicate" })

    expect(screen.queryByLabelText("Jira target scope")).not.toBeInTheDocument()
  })

  it("duplicates a template, edits duration, and saves without target scopes", async () => {
    const fetchMock = mockApi()
    renderPage()

    fireEvent.click(await screen.findByRole("button", { name: "Duplicate" }))
    fireEvent.change(screen.getByLabelText("Duration days"), { target: { value: "5" } })
    fireEvent.click(screen.getByRole("button", { name: "Save signal" }))

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([url, init]) => String(url).endsWith("/api/signal-definitions") && init?.method === "POST",
      )
      expect(call).toBeTruthy()
      const body = JSON.parse(String((call?.[1] as RequestInit).body))
      expect(body.target_scopes).toBeUndefined()
      expect(body.expression.conditions[0].value.amount).toBe(5)
    })
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
