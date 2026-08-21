import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { ConnectionDeleteConfirm } from "@/components/connections/ConnectionDeleteConfirm"

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

function renderConfirm(
  onDeleted = vi.fn(),
  onCancel = vi.fn(),
  connectionId = "conn-1",
  connectionName = "Jira Prod",
) {
  const queryClient = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <ConnectionDeleteConfirm
        connectionId={connectionId}
        connectionName={connectionName}
        onCancel={onCancel}
        onDeleted={onDeleted}
      />
    </QueryClientProvider>,
  )
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  })
}

describe("ConnectionDeleteConfirm", () => {
  it("renders the alertdialog with the connection name in the aria-label", () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, { status: 204 }))
    renderConfirm()
    expect(
      screen.getByRole("alertdialog", { name: "Confirm: Delete connection Jira Prod" }),
    ).toBeInTheDocument()
  })

  it("shows 'Confirm delete' and 'Cancel' buttons initially", () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, { status: 204 }))
    renderConfirm()
    expect(screen.getByRole("button", { name: "Confirm delete" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument()
  })

  it("calls onCancel when Cancel is clicked", () => {
    const onCancel = vi.fn()
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, { status: 204 }))
    renderConfirm(vi.fn(), onCancel)
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }))
    expect(onCancel).toHaveBeenCalledTimes(1)
  })

  it("calls the delete API when Confirm delete is clicked", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(null, { status: 204 }))
    renderConfirm()
    fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }))

    await waitFor(() => {
      const deleteCalls = fetchMock.mock.calls.filter(
        ([, init]) => (init?.method ?? "GET").toUpperCase() === "DELETE",
      )
      expect(deleteCalls.length).toBeGreaterThan(0)
    })
  })

  it("calls onDeleted after a successful delete", async () => {
    const onDeleted = vi.fn()
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, { status: 204 }))
    renderConfirm(onDeleted)
    fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }))
    await waitFor(() => expect(onDeleted).toHaveBeenCalledTimes(1))
  })

  it("shows conflict info and 'Confirm force delete' after a 409 conflict", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse(
        {
          detail: {
            message: "connection is in use",
            dependent_teams: [{ id: "team-1", name: "Platform" }],
          },
        },
        409,
      ),
    )
    renderConfirm()
    fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }))

    expect(await screen.findByText("Platform")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Confirm force delete" })).toBeInTheDocument()
  })

  it("retries with force=true when Confirm force delete is clicked", async () => {
    let forceUsed = false
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input)
      if (url.includes("force=true")) {
        forceUsed = true
        return Promise.resolve(new Response(null, { status: 204 }))
      }
      return Promise.resolve(
        jsonResponse(
          {
            detail: {
              message: "connection is in use",
              dependent_teams: [{ id: "team-1", name: "Platform" }],
            },
          },
          409,
        ),
      )
    })

    renderConfirm()
    fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }))
    await screen.findByRole("button", { name: "Confirm force delete" })
    fireEvent.click(screen.getByRole("button", { name: "Confirm force delete" }))

    await waitFor(() => expect(forceUsed).toBe(true))
  })
})
