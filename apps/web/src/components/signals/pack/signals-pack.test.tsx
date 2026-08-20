import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { ChangeRow } from "@/components/signals/pack/ChangeRow"
import { ConflictResolver } from "@/components/signals/pack/ConflictResolver"
import { ExportCard } from "@/components/signals/pack/ExportCard"
import { ImportCard } from "@/components/signals/pack/ImportCard"
import { ImportPreview } from "@/components/signals/pack/ImportPreview"
import type { SignalImportDiff, SignalPackImportPreview } from "@/lib/signalPack"

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

function withQuery(node: React.ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  })
  return render(<QueryClientProvider client={queryClient}>{node}</QueryClientProvider>)
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  })
}

const groups = [
  { id: "g1", name: "Group A", description: null, signal_ids: [], created_at: "", updated_at: "" },
]

// ---------------------------------------------------------------------------
// ChangeRow
// ---------------------------------------------------------------------------

describe("ChangeRow", () => {
  const enabledChange: SignalImportDiff = {
    signal_id: "stale-work-item",
    enabled: { before: true, after: false },
    severity: null,
    params: null,
  }

  const severityChange: SignalImportDiff = {
    signal_id: "blocked-work-item",
    enabled: null,
    severity: { before: "warning", after: "critical" },
    params: null,
  }

  it("renders signal_id and enabled change", () => {
    render(<ChangeRow change={enabledChange} />)
    expect(screen.getByText("stale-work-item")).toBeInTheDocument()
    expect(screen.getByText(/Disabled/)).toBeInTheDocument()
    expect(screen.getByText(/was enabled/)).toBeInTheDocument()
  })

  it("renders severity change with before and after badges", () => {
    render(<ChangeRow change={severityChange} />)
    expect(screen.getByText("blocked-work-item")).toBeInTheDocument()
    expect(screen.getByText(/Severity:/)).toBeInTheDocument()
    expect(screen.getAllByText("warning").length).toBeGreaterThan(0)
    expect(screen.getAllByText("critical").length).toBeGreaterThan(0)
  })

  it("renders params change as JSON", () => {
    const paramChange: SignalImportDiff = {
      signal_id: "param-signal",
      enabled: null,
      severity: null,
      params: { before: { days: 3 }, after: { days: 5 } },
    }
    render(<ChangeRow change={paramChange} />)
    expect(screen.getByText(/Parameters/)).toBeInTheDocument()
    expect(screen.getByText(/days.*3/)).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// ConflictResolver
// ---------------------------------------------------------------------------

describe("ConflictResolver", () => {
  it("renders clash names and four action buttons", () => {
    const onChoose = vi.fn()
    render(
      <ConflictResolver clashes={["Signal A", "Signal B"]} onChoose={onChoose} pending={false} />,
    )
    expect(screen.getByTestId("conflict-resolver")).toBeInTheDocument()
    expect(screen.getByText(/Signal A, Signal B/)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Skip" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Overwrite" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Keep both" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument()
  })

  it("calls onChoose with the correct mode when each button is clicked", () => {
    const onChoose = vi.fn()
    render(<ConflictResolver clashes={["A"]} onChoose={onChoose} pending={false} />)

    fireEvent.click(screen.getByRole("button", { name: "Skip" }))
    expect(onChoose).toHaveBeenCalledWith("skip")

    fireEvent.click(screen.getByRole("button", { name: "Overwrite" }))
    expect(onChoose).toHaveBeenCalledWith("overwrite")

    fireEvent.click(screen.getByRole("button", { name: "Keep both" }))
    expect(onChoose).toHaveBeenCalledWith("keep_both")

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }))
    expect(onChoose).toHaveBeenCalledWith("cancel")
  })

  it("disables all buttons when pending", () => {
    render(<ConflictResolver clashes={["A"]} onChoose={vi.fn()} pending={true} />)
    for (const name of ["Skip", "Overwrite", "Keep both", "Cancel"]) {
      expect(screen.getByRole("button", { name })).toBeDisabled()
    }
  })
})

// ---------------------------------------------------------------------------
// ImportPreview
// ---------------------------------------------------------------------------

describe("ImportPreview", () => {
  const preview: SignalPackImportPreview = {
    pack_name: "my-pack",
    warnings: [],
    unresolved_mappings: [],
    imported_signal_names: [],
    signal_name_clashes: [],
    group_name_clashes: [],
    changes: [
      {
        signal_id: "stale-in-progress",
        enabled: { before: true, after: false },
        severity: null,
        params: null,
      },
    ],
  }

  it("renders the pack name and change rows", () => {
    render(<ImportPreview preview={preview} />)
    expect(screen.getByTestId("import-preview")).toBeInTheDocument()
    expect(screen.getByText(/my-pack/)).toBeInTheDocument()
    expect(screen.getByText("stale-in-progress")).toBeInTheDocument()
  })

  it("shows a warning count summary when imported_signal_names has items", () => {
    render(
      <ImportPreview
        preview={{
          ...preview,
          imported_signal_names: ["sig-a", "sig-b"],
          changes: [],
        }}
      />,
    )
    expect(screen.getByText(/2 signals to import/)).toBeInTheDocument()
  })

  it("shows 'no changes' when both imported and changes are empty", () => {
    render(
      <ImportPreview
        preview={{ ...preview, imported_signal_names: [], changes: [] }}
      />,
    )
    expect(screen.getByText(/no changes from your current configuration/)).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// ExportCard
// ---------------------------------------------------------------------------

describe("ExportCard", () => {
  it("renders group checkboxes and export controls", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(groups))
    withQuery(<ExportCard />)
    expect(await screen.findByLabelText("Group A")).toBeInTheDocument()
    expect(screen.getByLabelText("Export mode")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Download YAML" })).toBeDisabled()
  })

  it("enables Download YAML after a group is selected", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(groups))
    withQuery(<ExportCard />)
    fireEvent.click(await screen.findByLabelText("Group A"))
    expect(screen.getByRole("button", { name: "Download YAML" })).not.toBeDisabled()
  })
})

// ---------------------------------------------------------------------------
// ImportCard
// ---------------------------------------------------------------------------

const previewData: SignalPackImportPreview = {
  pack_name: "test-pack",
  warnings: [],
  unresolved_mappings: [],
  imported_signal_names: [],
  signal_name_clashes: [],
  group_name_clashes: [],
  changes: [
    { signal_id: "stale-signal", enabled: { before: true, after: false }, severity: null, params: null },
  ],
}

describe("ImportCard", () => {
  it("renders the YAML textarea and Preview button", () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse([]))
    withQuery(<ImportCard />)
    expect(screen.getByLabelText(/Paste pack YAML/)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Preview changes" })).toBeInTheDocument()
  })

  it("shows ImportPreview after a successful preview call", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(previewData))
    withQuery(<ImportCard />)

    fireEvent.change(screen.getByLabelText(/Paste pack YAML/), {
      target: { value: "apiVersion: emradar.dev/v1" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Preview changes" }))

    expect(await screen.findByTestId("import-preview")).toBeInTheDocument()
    expect(screen.getByText(/test-pack/)).toBeInTheDocument()
  })

  it("shows ConflictResolver when clashes are present", async () => {
    const clashPreview: SignalPackImportPreview = {
      ...previewData,
      changes: [],
      signal_name_clashes: ["Stale work"],
    }
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(clashPreview))
    withQuery(<ImportCard />)

    fireEvent.change(screen.getByLabelText(/Paste pack YAML/), {
      target: { value: "apiVersion: emradar.dev/v1" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Preview changes" }))

    expect(await screen.findByTestId("conflict-resolver")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Apply pack" })).not.toBeInTheDocument()
  })

  it("shows an error message when preview fails", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ detail: { code: "invalid-signal-pack", message: "Unknown signal id: bogus" } }, 422),
    )
    withQuery(<ImportCard />)

    fireEvent.change(screen.getByLabelText(/Paste pack YAML/), {
      target: { value: "broken: yaml" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Preview changes" }))

    await waitFor(() => expect(screen.getByText("Unknown signal id: bogus")).toBeInTheDocument())
  })
})
