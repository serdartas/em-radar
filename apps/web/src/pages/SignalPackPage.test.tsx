import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { SignalPackPage } from "@/pages/SignalPackPage"

const preview = {
  pack_name: "my-pack",
  warnings: [],
  unresolved_mappings: [],
  imported_signal_names: [],
  signal_name_clashes: [],
  group_name_clashes: [],
  changes: [
    {
      signal_id: "stale-in-progress-work-item",
      enabled: { before: true, after: false },
      severity: null,
      params: null,
    },
  ],
}

const groups = [
  { id: "g1", name: "Group A", description: null, signal_ids: [], created_at: "", updated_at: "" },
  { id: "g2", name: "Group B", description: null, signal_ids: [], created_at: "", updated_at: "" },
]

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
  it("exports the selected groups as repeated group_ids", async () => {
    URL.createObjectURL = URL.createObjectURL ?? (() => "blob:signal-pack")
    URL.revokeObjectURL = URL.revokeObjectURL ?? (() => undefined)
    vi.spyOn(URL, "createObjectURL").mockImplementation(() => "blob:signal-pack")
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined)
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined)
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.endsWith("/api/signal-config-groups")) {
        return Promise.resolve(jsonResponse(groups))
      }
      if (url.includes("/api/signal-pack/export")) {
        return Promise.resolve(new Response("kind: SignalPack", { status: 200 }))
      }
      throw new Error(`unexpected fetch: ${url}`)
    })

    renderPage()

    fireEvent.click(await screen.findByLabelText("Group A"))
    fireEvent.click(screen.getByLabelText("Group B"))
    fireEvent.change(screen.getByLabelText("Export mode"), { target: { value: "public_template" } })
    fireEvent.click(screen.getByRole("button", { name: "Download YAML" }))

    await waitFor(() => {
      const exportCall = fetchMock.mock.calls.find(([url]) =>
        String(url).includes("/api/signal-pack/export"),
      )
      const exportUrl = String(exportCall?.[0])
      expect(exportUrl).toContain("export_type=public_template")
      expect(exportUrl).toContain("group_ids=g1")
      expect(exportUrl).toContain("group_ids=g2")
    })
  })

  it("previews a pack and applies it on confirmation", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.endsWith("/api/signal-config-groups")) {
        return Promise.resolve(jsonResponse(groups))
      }
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
      target: { value: "apiVersion: emradar.dev/v1" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Preview changes" }))

    expect(await screen.findByTestId("import-preview")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Apply pack" }))

    await waitFor(() => {
      expect(screen.getByText(/Applied pack/)).toBeInTheDocument()
    })
    const applyCall = fetchMock.mock.calls.find(([url]) =>
      String(url).endsWith("/api/signal-pack/import/apply"),
    )
    expect(applyCall).toBeTruthy()
    expect(JSON.parse(String((applyCall?.[1] as RequestInit).body)).conflict).toBe("keep_both")
  })

  it("offers a four-way conflict choice and applies overwrite", async () => {
    const clashPreview = {
      ...preview,
      changes: [],
      imported_signal_names: ["Stale work"],
      signal_name_clashes: ["Stale work"],
      group_name_clashes: ["scrum-health"],
    }
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.endsWith("/api/signal-config-groups")) {
        return Promise.resolve(jsonResponse(groups))
      }
      if (url.endsWith("/api/signal-pack/import")) {
        return Promise.resolve(jsonResponse(clashPreview))
      }
      if (url.endsWith("/api/signal-pack/import/apply")) {
        return Promise.resolve(jsonResponse({ ...clashPreview, pack_name: "my-pack" }))
      }
      throw new Error(`unexpected fetch: ${url}`)
    })

    renderPage()

    fireEvent.change(screen.getByLabelText(/Paste pack YAML/), {
      target: { value: "apiVersion: emradar.dev/v1" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Preview changes" }))

    expect(await screen.findByTestId("conflict-resolver")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Apply pack" })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Overwrite" }))

    await waitFor(() => {
      const applyCall = fetchMock.mock.calls.find(([url]) =>
        String(url).endsWith("/api/signal-pack/import/apply"),
      )
      expect(applyCall).toBeTruthy()
      expect(JSON.parse(String((applyCall?.[1] as RequestInit).body)).conflict).toBe("overwrite")
    })
  })

  it("AUDIT-10: appends the download anchor to document.body for Firefox compatibility", async () => {
    URL.createObjectURL = URL.createObjectURL ?? (() => "blob:signal-pack")
    URL.revokeObjectURL = URL.revokeObjectURL ?? (() => undefined)
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:signal-pack")
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined)

    const appendChildSpy = vi.spyOn(document.body, "appendChild")
    const removeChildSpy = vi.spyOn(document.body, "removeChild")
    const anchorClickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(
      () => undefined,
    )

    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.endsWith("/api/signal-config-groups")) {
        return Promise.resolve(jsonResponse(groups))
      }
      if (url.includes("/api/signal-pack/export")) {
        return Promise.resolve(new Response("kind: SignalPack", { status: 200 }))
      }
      throw new Error(`unexpected fetch: ${url}`)
    })

    renderPage()

    fireEvent.click(await screen.findByLabelText("Group A"))
    fireEvent.click(screen.getByRole("button", { name: "Download YAML" }))

    await waitFor(() => expect(anchorClickSpy).toHaveBeenCalledTimes(1))

    // Anchor must have been appended to body and subsequently removed.
    expect(appendChildSpy).toHaveBeenCalledWith(expect.any(HTMLAnchorElement))
    expect(removeChildSpy).toHaveBeenCalledWith(expect.any(HTMLAnchorElement))
  })

  it("AUDIT-11: shows a Callout error when navigator.clipboard is unavailable", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.endsWith("/api/signal-config-groups")) {
        return Promise.resolve(jsonResponse(groups))
      }
      if (url.includes("/api/signal-pack/export")) {
        return Promise.resolve(new Response("kind: SignalPack", { status: 200 }))
      }
      throw new Error(`unexpected fetch: ${url}`)
    })

    // Remove navigator.clipboard to simulate an insecure context or unsupported browser.
    const originalClipboard = navigator.clipboard
    Object.defineProperty(navigator, "clipboard", { value: undefined, configurable: true })

    renderPage()

    fireEvent.click(await screen.findByLabelText("Group A"))
    fireEvent.click(screen.getByRole("button", { name: "Copy to clipboard" }))

    const alert = await screen.findByRole("alert")
    expect(alert).toBeInTheDocument()
    expect(alert.textContent).toMatch(/clipboard is not available/i)

    // Restore
    Object.defineProperty(navigator, "clipboard", { value: originalClipboard, configurable: true })
  })

  it("AUDIT-11: shows a Callout error when clipboard.writeText rejects", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.endsWith("/api/signal-config-groups")) {
        return Promise.resolve(jsonResponse(groups))
      }
      if (url.includes("/api/signal-pack/export")) {
        return Promise.resolve(new Response("kind: SignalPack", { status: 200 }))
      }
      throw new Error(`unexpected fetch: ${url}`)
    })

    // Stub clipboard.writeText to reject.
    const originalClipboard = navigator.clipboard
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: vi.fn().mockRejectedValue(new Error("Permission denied")) },
      configurable: true,
    })

    renderPage()

    fireEvent.click(await screen.findByLabelText("Group A"))
    fireEvent.click(screen.getByRole("button", { name: "Copy to clipboard" }))

    const alert = await screen.findByRole("alert")
    expect(alert).toBeInTheDocument()
    expect(alert.textContent).toMatch(/could not copy to clipboard/i)

    Object.defineProperty(navigator, "clipboard", { value: originalClipboard, configurable: true })
  })

  it("surfaces a backend error for an invalid pack without applying", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = typeof input === "string" ? input : input.toString()
      if (url.endsWith("/api/signal-config-groups")) {
        return Promise.resolve(jsonResponse(groups))
      }
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
      fetchMock.mock.calls.some(([url]) => String(url).endsWith("/api/signal-pack/import/apply")),
    ).toBe(false)
  })
})
