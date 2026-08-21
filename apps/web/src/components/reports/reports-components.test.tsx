import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { FindingCard } from "@/components/reports/FindingCard"
import { FindingEvidence } from "@/components/reports/FindingEvidence"
import { PartialDataNotes } from "@/components/reports/PartialDataNotes"
import { ReportExportActions } from "@/components/reports/ReportExportActions"
import { ReportSectionBlock } from "@/components/reports/ReportSectionBlock"
import { SkippedSignals } from "@/components/reports/SkippedSignals"
import type { Finding, PartialDataNote, ReportSectionRef, SkipNote } from "@/lib/reports"

const finding: Finding = {
  id: "f-1",
  signal_id: "blocked-work-item",
  signal_name: "Blocked work item",
  severity: "critical",
  confidence: "high",
  entity_type: "workitem",
  entity_id: "e1",
  title: "PLAT-3 blocked for 6 days",
  reason: "Blocked and untouched.",
  recommendation: "Escalate the blocker.",
  evidence: { days_blocked: 6 },
  source_link: "https://demo.invalid/browse/PLAT-3",
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

// ---------------------------------------------------------------------------
// FindingCard
// ---------------------------------------------------------------------------

describe("FindingCard", () => {
  it("renders title, severity badge, signal name, reason, recommendation, and source link", () => {
    render(<FindingCard finding={finding} />)
    expect(screen.getByRole("heading", { level: 3, name: "PLAT-3 blocked for 6 days" })).toBeInTheDocument()
    expect(screen.getByText("critical")).toBeInTheDocument()
    expect(screen.getByText("Blocked work item")).toBeInTheDocument()
    expect(screen.getByText("Blocked and untouched.")).toBeInTheDocument()
    expect(screen.getByText("Escalate the blocker.")).toBeInTheDocument()
    const link = screen.getByRole("link", { name: "View source" })
    expect(link).toHaveAttribute("href", "https://demo.invalid/browse/PLAT-3")
  })

  it("hides the recommendation and source link when absent", () => {
    render(<FindingCard finding={{ ...finding, recommendation: null, source_link: null }} />)
    expect(screen.queryByText("Recommendation")).toBeNull()
    expect(screen.queryByRole("link", { name: "View source" })).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// FindingEvidence
// ---------------------------------------------------------------------------

describe("FindingEvidence", () => {
  it("renders object evidence as a key-value list", () => {
    render(<FindingEvidence evidence={{ days_blocked: 6 }} />)
    expect(screen.getByRole("heading", { name: "Evidence" })).toBeInTheDocument()
    expect(screen.getByText("days_blocked")).toBeInTheDocument()
    expect(screen.getByText(/6/)).toBeInTheDocument()
  })

  it("renders nothing for empty object evidence", () => {
    const { container } = render(<FindingEvidence evidence={{}} />)
    expect(container.firstChild).toBeNull()
  })

  it("renders nothing for null evidence", () => {
    const { container } = render(<FindingEvidence evidence={null} />)
    expect(container.firstChild).toBeNull()
  })

  it("renders array evidence as a comma-joined string", () => {
    render(<FindingEvidence evidence={["a", "b"]} />)
    expect(screen.getByText(/a, b/)).toBeInTheDocument()
  })

  it("renders a scalar string as evidence", () => {
    render(<FindingEvidence evidence="some scalar" />)
    expect(screen.getByText("some scalar")).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// ReportSectionBlock
// ---------------------------------------------------------------------------

describe("ReportSectionBlock", () => {
  const findingsById = new Map<string, Finding>([["f-1", finding]])
  const section: ReportSectionRef = {
    section: "top_risks",
    title: "Top Risks",
    finding_ids: ["f-1"],
  }

  it("renders section heading and finding cards", () => {
    render(
      <ReportSectionBlock
        findingsById={findingsById}
        section={section}
        summaryCounts={{}}
        total={1}
      />,
    )
    expect(screen.getByRole("heading", { level: 2, name: "Top Risks" })).toBeInTheDocument()
    expect(screen.getByText("PLAT-3 blocked for 6 days")).toBeInTheDocument()
  })

  it("renders 'No findings' when finding_ids is empty", () => {
    render(
      <ReportSectionBlock
        findingsById={findingsById}
        section={{ ...section, finding_ids: [] }}
        summaryCounts={{}}
        total={0}
      />,
    )
    expect(screen.getByText("No findings.")).toBeInTheDocument()
  })

  it("renders severity counts and total for the summary section", () => {
    render(
      <ReportSectionBlock
        findingsById={new Map()}
        section={{ section: "summary", title: "Summary", finding_ids: [] }}
        summaryCounts={{ critical: 1, warning: 2 }}
        total={3}
      />,
    )
    expect(screen.getByText("1 critical")).toBeInTheDocument()
    expect(screen.getByText("3 findings in total.")).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// PartialDataNotes
// ---------------------------------------------------------------------------

describe("PartialDataNotes", () => {
  const notes: PartialDataNote[] = [
    { source: "board", reason: "Board data unavailable." },
    { source: "code", reason: "Code data unavailable." },
  ]

  it("renders the heading and each note", () => {
    render(<PartialDataNotes notes={notes} />)
    expect(screen.getByRole("heading", { name: "Partial data" })).toBeInTheDocument()
    expect(screen.getByText(/Board data unavailable/)).toBeInTheDocument()
    expect(screen.getByText(/Code data unavailable/)).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// SkippedSignals
// ---------------------------------------------------------------------------

describe("SkippedSignals", () => {
  const notes: SkipNote[] = [
    { signal_id: "sig-a", reason: "Missing board scope." },
    { signal_id: "sig-b", reason: "No code connection." },
  ]

  it("renders the heading and each skipped signal", () => {
    render(<SkippedSignals notes={notes} />)
    expect(screen.getByRole("heading", { name: "Skipped signals" })).toBeInTheDocument()
    expect(screen.getByText("sig-a")).toBeInTheDocument()
    expect(screen.getByText(/Missing board scope/)).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// ReportExportActions
// ---------------------------------------------------------------------------

const MARKDOWN = "# Report\n"

function renderExportActions() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <ReportExportActions reportId="report-1" />
    </QueryClientProvider>,
  )
}

describe("ReportExportActions", () => {
  it("renders Download and Copy buttons", () => {
    renderExportActions()
    expect(screen.getByRole("button", { name: "Download .md" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Copy to clipboard" })).toBeInTheDocument()
  })

  it("shows 'Copied to clipboard' after a successful copy", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(MARKDOWN, { status: 200, headers: { "Content-Type": "text/markdown" } }),
    )
    const writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } })

    renderExportActions()
    fireEvent.click(screen.getByRole("button", { name: "Copy to clipboard" }))

    expect(await screen.findByText("Copied to clipboard.")).toBeInTheDocument()
    expect(writeText).toHaveBeenCalledWith(MARKDOWN)
  })

  it("shows an error message when the export fails", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("nope", { status: 500 }))
    renderExportActions()
    fireEvent.click(screen.getByRole("button", { name: "Copy to clipboard" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("The export could not be generated.")
  })
})
