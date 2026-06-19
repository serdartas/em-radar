import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { SignalPackPage } from "@/pages/SignalPackPage"

const preview = {
  pack_name: "my-pack",
  warnings: [],
  unresolved_mappings: [],
  imported_signal_names: [],
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
  it("exports with the selected public template mode", async () => {
    URL.createObjectURL = URL.createObjectURL ?? (() => "blob:signal-pack")
    URL.revokeObjectURL = URL.revokeObjectURL ?? (() => undefined)
    const createObjectUrl = vi
      .spyOn(URL, "createObjectURL")
      .mockImplementation(() => "blob:signal-pack")
    const revokeObjectUrl = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined)
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined)
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.includes("/api/signal-pack/export")) {
        return Promise.resolve(new Response("kind: SignalPack", { status: 200 }))
      }
      throw new Error(`unexpected fetch: ${url}`)
    })

    renderPage()

    fireEvent.change(screen.getByLabelText("Export mode"), {
      target: { value: "public_template" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Download YAML" }))

    await waitFor(() => {
      expect(fetchMock.mock.calls[0][0]).toContain("export_type=public_template")
    })
    expect(createObjectUrl).toHaveBeenCalled()
    expect(revokeObjectUrl).toHaveBeenCalledWith("blob:signal-pack")
  })

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

  it("shows unresolved mappings for public template imports", async () => {
    const publicPreview = {
      ...preview,
      changes: [],
      unresolved_mappings: ["public-stale-work"],
      imported_signal_names: ["Public stale work"],
    }
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.endsWith("/api/signal-pack/import")) {
        return Promise.resolve(jsonResponse(publicPreview))
      }
      throw new Error(`unexpected fetch: ${url}`)
    })

    renderPage()

    fireEvent.change(screen.getByLabelText(/Paste pack YAML/), {
      target: { value: "apiVersion: emradar.dev/v1" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Preview changes" }))

    expect(await screen.findByLabelText("Unresolved mappings")).toBeInTheDocument()
    expect(screen.getByText(/public-stale-work requires local connector/)).toBeInTheDocument()
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
