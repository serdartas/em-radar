import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"

import { SignalSettingsPage } from "@/pages/SignalSettingsPage"

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

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  })
}

function mockApi(options: { duplicateName?: boolean } = {}) {
  return vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    const url = typeof input === "string" ? input : input.toString()
    const method = init?.method ?? "GET"
    if (url.endsWith("/api/signal-definitions") && method === "GET") {
      return Promise.resolve(jsonResponse([]))
    }
    if (url.endsWith("/api/connectors")) {
      return Promise.resolve(jsonResponse(connectors))
    }
    if (url.endsWith("/api/signal-definitions") && method === "POST") {
      if (options.duplicateName) {
        return Promise.resolve(
          jsonResponse({ detail: { code: "conflict", message: "signal name must be unique" } }, 409),
        )
      }
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

async function openForm() {
  fireEvent.click(await screen.findByRole("button", { name: "Create new" }))
  await screen.findByRole("button", { name: "Save signal" })
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("SignalSettingsPage", () => {
  it("shows the create form without any template controls", async () => {
    mockApi()
    renderPage()

    await openForm()

    expect(screen.queryByRole("button", { name: "Duplicate" })).not.toBeInTheDocument()
    expect(screen.getByLabelText("Name")).toBeInTheDocument()
    expect(screen.getByLabelText("Type")).toBeInTheDocument()
  })

  it("adds a second rule joined by a uniform connector shown on both rows", async () => {
    mockApi()
    renderPage()
    await openForm()

    fireEvent.change(screen.getByLabelText("Add rule"), { target: { value: "OR" } })

    // The first row connector now reflects the shared operator, the new last row offers add again.
    expect((screen.getByLabelText("Connector 1") as HTMLSelectElement).value).toBe("OR")
    expect(screen.getByLabelText("Add rule")).toBeInTheDocument()
  })

  it("saves a two-rule OR signal with operator any and two conditions", async () => {
    const fetchMock = mockApi()
    renderPage()
    await openForm()

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "My signal" } })
    fireEvent.change(screen.getByLabelText("Add rule"), { target: { value: "OR" } })
    fireEvent.click(screen.getByRole("button", { name: "Save signal" }))

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([url, init]) => String(url).endsWith("/api/signal-definitions") && init?.method === "POST",
      )
      expect(call).toBeTruthy()
      const body = JSON.parse(String((call?.[1] as RequestInit).body))
      expect(body.name).toBe("My signal")
      expect(body.expression.operator).toBe("any")
      expect(body.expression.conditions).toHaveLength(2)
      expect(body.report_settings.severity).toBe("warning")
    })
  })

  it("does not exceed five rules", async () => {
    mockApi()
    renderPage()
    await openForm()

    for (let index = 0; index < 4; index += 1) {
      fireEvent.change(screen.getByLabelText("Add rule"), { target: { value: "AND" } })
    }

    expect(screen.queryByLabelText("Add rule")).not.toBeInTheDocument()
    expect(screen.getByText("Max 5")).toBeInTheDocument()
  })

  it("renders an enum value dropdown for enum fields", async () => {
    mockApi()
    renderPage()
    await openForm()

    fireEvent.change(screen.getByLabelText("Field"), { target: { value: "status_category" } })

    const valueControl = screen.getByLabelText("Value") as HTMLSelectElement
    expect(valueControl.tagName).toBe("SELECT")
    expect(screen.getByRole("option", { name: "in_progress" })).toBeInTheDocument()
  })

  it("surfaces a duplicate-name conflict message", async () => {
    mockApi({ duplicateName: true })
    renderPage()
    await openForm()

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Taken" } })
    fireEvent.click(screen.getByRole("button", { name: "Save signal" }))

    expect(await screen.findByRole("alert")).toHaveTextContent("signal name must be unique")
  })
})
