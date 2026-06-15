import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"

import { type SignalConfig } from "@/lib/signalConfigs"
import { SignalSettingsPage } from "@/pages/SignalSettingsPage"

const SIGNAL_IDS = [
  "stale-in-progress-work-item",
  "blocked-without-update",
  "story-without-acceptance-criteria",
  "story-without-parent-epic",
  "epic-too-broad",
  "epic-without-measurable-description",
  "repeated-carry-over",
  "sprint-scope-churn",
  "mergerequest-waiting-too-long",
  "mergerequest-without-linked-workitem",
  "large-mergerequest-risk",
  "failing-pipeline-too-long",
  "merged-without-enough-approval",
]

function makeConfig(signalId: string): SignalConfig {
  if (signalId === "stale-in-progress-work-item") {
    return {
      signal_id: signalId,
      name: "Stale in-progress work item",
      description: "Flags items stuck in progress.",
      default_severity: "warning",
      enabled: true,
      severity_override: null,
      params: { days_threshold: 14 },
      params_schema: {
        type: "object",
        properties: {
          days_threshold: { type: "integer", title: "Days Threshold", default: 7 },
        },
      },
    }
  }
  return {
    signal_id: signalId,
    name: signalId,
    description: `Description for ${signalId}.`,
    default_severity: "info",
    enabled: true,
    severity_override: null,
    params: {},
    params_schema: { type: "object", properties: {} },
  }
}

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

    if (url.endsWith("/api/signal-configs") && method === "GET") {
      return Promise.resolve(jsonResponse(SIGNAL_IDS.map(makeConfig)))
    }
    if (url.endsWith("/stale-in-progress-work-item/reset") && method === "POST") {
      const reset = makeConfig("stale-in-progress-work-item")
      reset.params = { days_threshold: 7 }
      return Promise.resolve(jsonResponse(reset))
    }
    if (url.endsWith("/api/signal-configs/stale-in-progress-work-item") && method === "PATCH") {
      const patched = makeConfig("stale-in-progress-work-item")
      patched.params = JSON.parse(String(init?.body)).params
      return Promise.resolve(jsonResponse(patched))
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
  it("lists all 13 signals", async () => {
    mockApi()
    renderPage()

    await screen.findByText("Stale in-progress work item")
    expect(screen.getAllByRole("listitem")).toHaveLength(13)
  })

  it("issues a PATCH with the edited threshold", async () => {
    const fetchMock = mockApi()
    renderPage()

    const input = (await screen.findByLabelText(/Days Threshold/)) as HTMLInputElement
    fireEvent.change(input, { target: { value: "10" } })

    const row = input.closest("li")
    expect(row).not.toBeNull()
    fireEvent.click(within(row as HTMLElement).getByRole("button", { name: "Save" }))

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([url, requestInit]) =>
          String(url).endsWith("/api/signal-configs/stale-in-progress-work-item") &&
          requestInit?.method === "PATCH",
      )
      expect(call).toBeTruthy()
      const body = JSON.parse(String((call?.[1] as RequestInit).body))
      expect(body.params.days_threshold).toBe(10)
    })
  })

  it("restores the default when reset", async () => {
    const fetchMock = mockApi()
    renderPage()

    const input = (await screen.findByLabelText(/Days Threshold/)) as HTMLInputElement
    expect(input.value).toBe("14")

    const row = input.closest("li")
    fireEvent.click(within(row as HTMLElement).getByRole("button", { name: "Reset to default" }))

    await waitFor(() => {
      expect((screen.getByLabelText(/Days Threshold/) as HTMLInputElement).value).toBe("7")
    })
    expect(
      fetchMock.mock.calls.some(([url, requestInit]) =>
        String(url).endsWith("/stale-in-progress-work-item/reset") && requestInit?.method === "POST",
      ),
    ).toBe(true)
  })
})
