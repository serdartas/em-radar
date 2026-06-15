import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { SourceConnectionsPage } from "@/pages/SourceConnectionsPage"

const demoConnector = {
  name: "demo",
  display_name: "Demo company",
  config_schema: {
    type: "object",
    properties: {
      base_url: { type: "string", title: "Base URL" },
      token: { type: "string", title: "Token", writeOnly: true },
    },
    required: ["base_url", "token"],
  },
  capabilities: {
    provides_workitems: true,
    provides_sprints: true,
    provides_mergerequests: true,
    provides_repositories: true,
    provides_reviews: true,
    provides_comments: true,
    provides_transitions: true,
    supports_incremental_fetch: false,
    supports_pagination_cursor: false,
    max_window_days: null,
  },
}

const testResult = {
  ok: true,
  detail: "Connected",
  user_display_name: "Ada Lovelace",
  permissions: ["read"],
}

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  })
}

function mockApi(testHandler: () => Response = () => jsonResponse(testResult)) {
  return vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    const url = typeof input === "string" ? input : input.toString()
    if (url.endsWith("/api/connectors")) {
      return Promise.resolve(jsonResponse([demoConnector]))
    }
    if (url.endsWith("/api/connections") && (init?.method ?? "GET") === "GET") {
      return Promise.resolve(jsonResponse([]))
    }
    if (url.endsWith("/api/connections/test")) {
      return Promise.resolve(testHandler())
    }
    throw new Error(`unexpected fetch: ${init?.method ?? "GET"} ${url}`)
  })
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <SourceConnectionsPage />
    </QueryClientProvider>,
  )
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("SourceConnectionsPage", () => {
  it("renders the connector form with a write-only secret field", async () => {
    mockApi()
    renderPage()

    const token = (await screen.findByLabelText(/Token/)) as HTMLInputElement
    expect(token.type).toBe("password")
    expect(screen.getByLabelText(/Base URL/)).toBeInTheDocument()
  })

  it("shows the authenticated user after a successful test", async () => {
    mockApi()
    renderPage()

    fireEvent.change(await screen.findByLabelText(/Base URL/), {
      target: { value: "https://demo.invalid" },
    })
    fireEvent.change(screen.getByLabelText(/Token/), { target: { value: "secret-token" } })
    fireEvent.click(screen.getByRole("button", { name: "Test connection" }))

    expect(await screen.findByText(/Connected as Ada Lovelace/)).toBeInTheDocument()
  })

  it("surfaces a token-free error when the test fails", async () => {
    mockApi(() =>
      jsonResponse({
        ok: false,
        detail: "Credentials were rejected.",
        user_display_name: null,
        permissions: [],
      }),
    )
    renderPage()

    fireEvent.change(await screen.findByLabelText(/Base URL/), {
      target: { value: "https://demo.invalid" },
    })
    fireEvent.change(screen.getByLabelText(/Token/), { target: { value: "rejected-token" } })
    fireEvent.click(screen.getByRole("button", { name: "Test connection" }))

    await waitFor(() => {
      expect(screen.getByText("Credentials were rejected.")).toBeInTheDocument()
    })
  })
})
