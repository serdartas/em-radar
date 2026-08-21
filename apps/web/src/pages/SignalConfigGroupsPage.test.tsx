import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"

import { SignalConfigGroupsPage } from "@/pages/SignalConfigGroupsPage"

const definitions = [
  {
    id: "sig-1",
    name: "Signal A",
    description: null,
    entity_type: "issue",
    expression: {},
    report_settings: { severity: "warning", category: "flow" },
    enabled: true,
    origin: "user_created",
    template_key: null,
    version: 1,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
]

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  })
}

function mockApi() {
  const groups: Array<Record<string, unknown>> = []
  return vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    const url = typeof input === "string" ? input : input.toString()
    const method = init?.method ?? "GET"
    if (url.endsWith("/api/signal-definitions")) {
      return Promise.resolve(jsonResponse(definitions))
    }
    if (url.endsWith("/api/signal-config-groups") && method === "GET") {
      return Promise.resolve(jsonResponse(groups))
    }
    if (url.endsWith("/api/signal-config-groups") && method === "POST") {
      const body = JSON.parse(String(init?.body))
      const created = {
        id: "group-1",
        name: body.name,
        description: null,
        signal_ids: body.signal_ids ?? [],
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      }
      groups.push(created)
      return Promise.resolve(jsonResponse(created))
    }
    if (url.includes("/api/signal-config-groups/") && method === "PATCH") {
      const body = JSON.parse(String(init?.body))
      Object.assign(groups[0], body)
      return Promise.resolve(jsonResponse(groups[0]))
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
        <SignalConfigGroupsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("SignalConfigGroupsPage — create form", () => {
  it("uses InlineCreateRow with shared Input for the new-group form", async () => {
    mockApi()
    renderPage()

    // The label and input are wired via InlineCreateRow (shared Input component)
    const input = await screen.findByLabelText("New group name")
    expect(input.tagName).toBe("INPUT")

    // The create button is present and disabled when the input is empty
    expect(screen.getByRole("button", { name: "Create group" })).toBeDisabled()

    // Typing a name enables the button
    fireEvent.change(input, { target: { value: "Backend signals" } })
    expect(screen.getByRole("button", { name: "Create group" })).not.toBeDisabled()
  })
})

describe("SignalConfigGroupsPage", () => {
  it("creates a group and adds a signal to it", async () => {
    const fetchMock = mockApi()
    renderPage()

    fireEvent.change(await screen.findByLabelText("New group name"), {
      target: { value: "Backend signals" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Create group" }))

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([url, init]) =>
          String(url).endsWith("/api/signal-config-groups") && init?.method === "POST",
      )
      const body = JSON.parse(String((call?.[1] as RequestInit).body))
      expect(body.name).toBe("Backend signals")
    })

    fireEvent.change(await screen.findByLabelText("Add a signal"), { target: { value: "sig-1" } })
    fireEvent.click(screen.getByRole("button", { name: "Add signal" }))

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([url, init]) =>
          String(url).includes("/api/signal-config-groups/") && init?.method === "PATCH",
      )
      expect(call).toBeTruthy()
      const body = JSON.parse(String((call?.[1] as RequestInit).body))
      expect(body.signal_ids).toEqual(["sig-1"])
    })

    expect(await screen.findByText("Signal A")).toBeInTheDocument()
  })
})
