import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import App from "./App"

const finding = {
  signal_id: "stale-in-progress-work-item",
  signal_name: "Stale in-progress work item",
  severity: "warning",
  confidence: "high",
  entity_type: "workitem",
  entity_id: "15ed96df-469c-4f29-b6dc-cbf826764f37",
  title: "PLAT-2 stale for 12 days",
  reason: "The item has not changed recently.",
  recommendation: "Check whether the item is blocked.",
  evidence: { days_idle: 12 },
  source_link: "https://demo.invalid/browse/PLAT-2",
}

function renderApp() {
  const queryClient = new QueryClient({
    defaultOptions: {
      mutations: { retry: false },
    },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>,
  )
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("App", () => {
  it("runs the demo report and renders findings with their severities", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ findings: [finding] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    )

    renderApp()

    fireEvent.click(screen.getByRole("button", { name: "Run demo report" }))

    expect(await screen.findByText(finding.title)).toBeInTheDocument()
    expect(screen.getByText("warning")).toBeInTheDocument()
    expect(screen.getByText(finding.reason)).toBeInTheDocument()
    expect(screen.getByText(finding.recommendation)).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "View source" })).toHaveAttribute(
      "href",
      finding.source_link,
    )
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/reports/run",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ connector: "demo" }),
      }),
    )
  })

  it("renders an empty state when the report has no findings", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ findings: [] }), { status: 200 }),
    )

    renderApp()
    fireEvent.click(screen.getByRole("button", { name: "Run demo report" }))

    await waitFor(() => {
      expect(screen.getByText("No findings were detected.")).toBeInTheDocument()
    })
  })
})
