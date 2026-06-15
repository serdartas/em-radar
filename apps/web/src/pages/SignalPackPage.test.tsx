import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { SignalPackPage } from "@/pages/SignalPackPage"

const preview = {
  pack_name: "my-pack",
  warnings: [],
  changes: [
    {
      signal_id: "stale-in-progress-work-item",
      enabled: { before: true, after: false },
      severity: null,
      params: null,
    },
  ],
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  })
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <SignalPackPage />
    </QueryClientProvider>,
  )
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("SignalPackPage", () => {
  it("previews a pack and applies it on confirmation", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.endsWith("/api/signal-pack/import")) {
        return Promise.resolve(jsonResponse(preview))
      }
      if (url.endsWith("/api/signal-pack/import/apply")) {
        return Promise.resolve(jsonResponse(preview))
      }
      throw new Error(`unexpected fetch: ${url}`)
    })

    renderPage()

    fireEvent.change(screen.getByLabelText(/Paste pack YAML/), {
      target: { value: "schema_id: emradar.dev/v1" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Preview changes" }))

    expect(await screen.findByTestId("import-preview")).toBeInTheDocument()
    expect(screen.getByText("stale-in-progress-work-item")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Apply pack" }))

    await waitFor(() => {
      expect(screen.getByText(/Applied pack/)).toBeInTheDocument()
    })
    expect(
      fetchMock.mock.calls.some(([url]) =>
        String(url).endsWith("/api/signal-pack/import/apply"),
      ),
    ).toBe(true)
  })

  it("surfaces a backend error for an invalid pack without applying", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.endsWith("/api/signal-pack/import")) {
        return Promise.resolve(
          jsonResponse(
            { detail: { code: "invalid-signal-pack", message: "Unknown signal id: bogus" } },
            422,
          ),
        )
      }
      throw new Error(`unexpected fetch: ${url}`)
    })

    renderPage()

    fireEvent.change(screen.getByLabelText(/Paste pack YAML/), {
      target: { value: "broken: yaml" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Preview changes" }))

    await waitFor(() => {
      expect(screen.getByText("Unknown signal id: bogus")).toBeInTheDocument()
    })
    expect(screen.queryByRole("button", { name: "Apply pack" })).not.toBeInTheDocument()
    expect(
      fetchMock.mock.calls.some(([url]) =>
        String(url).endsWith("/api/signal-pack/import/apply"),
      ),
    ).toBe(false)
  })
})
