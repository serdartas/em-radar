// SPDX-License-Identifier: Apache-2.0

import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it } from "vitest"

import { SignalsChangedBanner } from "@/components/reports/SignalsChangedBanner"
import type { SignalDefinition } from "@/lib/signalDefinitions"
import type { SnapshotSignal } from "@/lib/reports"

afterEach(cleanup)

const snapshotSignal: SnapshotSignal = {
  id: "sig-1",
  name: "Blocked work item",
  entity_type: "workitem",
  category: "delivery_flow",
  origin: "system_template",
  template_key: "blocked_work_item",
}

const matchingCurrentSignal: SignalDefinition = {
  id: "sig-1",
  name: "Blocked work item",
  entity_type: "workitem",
  expression: {},
  report_settings: { severity: "critical", category: "delivery_flow" },
  origin: "system_template",
  template_key: "blocked_work_item",
  description: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
}

// ---------------------------------------------------------------------------
// Absence when snapshot matches current definitions
// ---------------------------------------------------------------------------

describe("SignalsChangedBanner absence", () => {
  it("renders nothing when snapshot signals match current definitions exactly", () => {
    const { container } = render(
      <SignalsChangedBanner
        currentSignals={[matchingCurrentSignal]}
        snapshotSignals={[snapshotSignal]}
      />,
    )
    expect(container.firstChild).toBeNull()
  })

  it("renders nothing when snapshotSignals is empty", () => {
    const { container } = render(
      <SignalsChangedBanner currentSignals={[matchingCurrentSignal]} snapshotSignals={[]} />,
    )
    expect(container.firstChild).toBeNull()
  })

  it("renders nothing when snapshot matches and currentSignals has additional signals", () => {
    const extra: SignalDefinition = {
      ...matchingCurrentSignal,
      id: "sig-2",
      name: "Stale item",
      template_key: "stale_item",
    }
    const { container } = render(
      <SignalsChangedBanner
        currentSignals={[matchingCurrentSignal, extra]}
        snapshotSignals={[snapshotSignal]}
      />,
    )
    expect(container.firstChild).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// Presence when snapshot differs from current definitions
// ---------------------------------------------------------------------------

describe("SignalsChangedBanner presence", () => {
  it("renders banner with exact copy when a signal was deleted", () => {
    render(
      <SignalsChangedBanner currentSignals={[]} snapshotSignals={[snapshotSignal]} />,
    )
    expect(
      screen.getByText(/configuration of some signals changed since this run/i),
    ).toBeInTheDocument()
  })

  it("renders banner when a signal name changed", () => {
    const renamed: SignalDefinition = { ...matchingCurrentSignal, name: "Renamed signal" }
    render(
      <SignalsChangedBanner
        currentSignals={[renamed]}
        snapshotSignals={[snapshotSignal]}
      />,
    )
    expect(
      screen.getByText(/configuration of some signals changed since this run/i),
    ).toBeInTheDocument()
  })

  it("renders banner when a signal category changed", () => {
    const recategorized: SignalDefinition = {
      ...matchingCurrentSignal,
      report_settings: { severity: "critical", category: "planning_hygiene" },
    }
    render(
      <SignalsChangedBanner
        currentSignals={[recategorized]}
        snapshotSignals={[snapshotSignal]}
      />,
    )
    expect(
      screen.getByText(/configuration of some signals changed since this run/i),
    ).toBeInTheDocument()
  })

  it("renders banner when a signal entity_type changed", () => {
    const retyped: SignalDefinition = { ...matchingCurrentSignal, entity_type: "sprint" }
    render(
      <SignalsChangedBanner
        currentSignals={[retyped]}
        snapshotSignals={[snapshotSignal]}
      />,
    )
    expect(
      screen.getByText(/configuration of some signals changed since this run/i),
    ).toBeInTheDocument()
  })

  it("renders banner when a signal origin changed", () => {
    const reorigined: SignalDefinition = { ...matchingCurrentSignal, origin: "user_created" }
    render(
      <SignalsChangedBanner
        currentSignals={[reorigined]}
        snapshotSignals={[snapshotSignal]}
      />,
    )
    expect(
      screen.getByText(/configuration of some signals changed since this run/i),
    ).toBeInTheDocument()
  })

  it("renders banner when a signal template_key changed", () => {
    const rekeyed: SignalDefinition = { ...matchingCurrentSignal, template_key: "other_key" }
    render(
      <SignalsChangedBanner
        currentSignals={[rekeyed]}
        snapshotSignals={[snapshotSignal]}
      />,
    )
    expect(
      screen.getByText(/configuration of some signals changed since this run/i),
    ).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// "Show me" disclosure reveals snapshot signals
// ---------------------------------------------------------------------------

describe("SignalsChangedBanner disclosure", () => {
  it("does not show snapshot signal list before 'Show me' is clicked", () => {
    render(
      <SignalsChangedBanner currentSignals={[]} snapshotSignals={[snapshotSignal]} />,
    )
    expect(screen.queryByText("Blocked work item")).toBeNull()
  })

  it("reveals snapshot signal list when 'Show me' is clicked", () => {
    render(
      <SignalsChangedBanner currentSignals={[]} snapshotSignals={[snapshotSignal]} />,
    )
    fireEvent.click(screen.getByRole("button", { name: "Show me" }))
    expect(screen.getByText("Blocked work item")).toBeInTheDocument()
    expect(screen.getByText("(workitem)")).toBeInTheDocument()
  })

  it("shows all snapshot signals in the expanded list", () => {
    const second: SnapshotSignal = {
      id: "sig-2",
      name: "Stale sprint",
      entity_type: "sprint",
      category: "sprint_health",
      origin: "system_template",
      template_key: "stale_sprint",
    }
    render(
      <SignalsChangedBanner
        currentSignals={[]}
        snapshotSignals={[snapshotSignal, second]}
      />,
    )
    fireEvent.click(screen.getByRole("button", { name: "Show me" }))
    expect(screen.getByText("Blocked work item")).toBeInTheDocument()
    expect(screen.getByText("Stale sprint")).toBeInTheDocument()
  })

  it("hides snapshot signal list when 'Hide' is clicked after expanding", () => {
    render(
      <SignalsChangedBanner currentSignals={[]} snapshotSignals={[snapshotSignal]} />,
    )
    fireEvent.click(screen.getByRole("button", { name: "Show me" }))
    expect(screen.getByText("Blocked work item")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Hide" }))
    expect(screen.queryByText("Blocked work item")).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// Extended fields: expression / severity / message_template
// ---------------------------------------------------------------------------

const snapshotWithExtended: SnapshotSignal = {
  ...snapshotSignal,
  expression: { field: "days_blocked", op: "gt", value: 3 },
  severity: "critical",
  message_template: null,
}

const currentWithExtended: SignalDefinition = {
  ...matchingCurrentSignal,
  expression: { field: "days_blocked", op: "gt", value: 3 },
  report_settings: { severity: "critical", category: "delivery_flow", message_template: null },
}

describe("SignalsChangedBanner extended field detection", () => {
  it("renders nothing when expression, severity, and message_template all match", () => {
    const { container } = render(
      <SignalsChangedBanner
        currentSignals={[currentWithExtended]}
        snapshotSignals={[snapshotWithExtended]}
      />,
    )
    expect(container.firstChild).toBeNull()
  })

  it("renders banner when expression changed (rule edit)", () => {
    const editedExpression: SignalDefinition = {
      ...currentWithExtended,
      expression: { field: "days_blocked", op: "gt", value: 7 },
    }
    render(
      <SignalsChangedBanner
        currentSignals={[editedExpression]}
        snapshotSignals={[snapshotWithExtended]}
      />,
    )
    expect(
      screen.getByText(/configuration of some signals changed since this run/i),
    ).toBeInTheDocument()
  })

  it("renders banner when severity changed", () => {
    const editedSeverity: SignalDefinition = {
      ...currentWithExtended,
      report_settings: { severity: "warning", category: "delivery_flow", message_template: null },
    }
    render(
      <SignalsChangedBanner
        currentSignals={[editedSeverity]}
        snapshotSignals={[snapshotWithExtended]}
      />,
    )
    expect(
      screen.getByText(/configuration of some signals changed since this run/i),
    ).toBeInTheDocument()
  })

  it("renders banner when message_template changed", () => {
    const editedTemplate: SignalDefinition = {
      ...currentWithExtended,
      report_settings: {
        severity: "critical",
        category: "delivery_flow",
        message_template: "Custom message",
      },
    }
    render(
      <SignalsChangedBanner
        currentSignals={[editedTemplate]}
        snapshotSignals={[snapshotWithExtended]}
      />,
    )
    expect(
      screen.getByText(/configuration of some signals changed since this run/i),
    ).toBeInTheDocument()
  })

  it("does NOT false-positive for legacy snapshot entries that lack extended fields", () => {
    // snapshotSignal has no expression/severity/message_template — legacy format.
    // currentWithExtended has those fields; they must be ignored for the legacy entry.
    const { container } = render(
      <SignalsChangedBanner
        currentSignals={[currentWithExtended]}
        snapshotSignals={[snapshotSignal]}
      />,
    )
    expect(container.firstChild).toBeNull()
  })

  it("does NOT false-positive when expressions are deeply equal but different objects", () => {
    const snapshotCopy: SnapshotSignal = {
      ...snapshotWithExtended,
      // Structurally identical expression but a new object reference
      expression: { field: "days_blocked", op: "gt", value: 3 },
    }
    const { container } = render(
      <SignalsChangedBanner
        currentSignals={[currentWithExtended]}
        snapshotSignals={[snapshotCopy]}
      />,
    )
    expect(container.firstChild).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// message_template null-vs-absent normalization (false-positive regression)
// ---------------------------------------------------------------------------

describe("SignalsChangedBanner message_template null/absent normalization", () => {
  // Snapshot stores null (Python None serialized); API may return the field absent (undefined).
  it("does NOT false-positive when snapshot has null and current omits message_template", () => {
    const snapshotWithNull: SnapshotSignal = {
      ...snapshotSignal,
      expression: { field: "days_blocked", op: "gt", value: 3 },
      severity: "critical",
      message_template: null,
    }
    // Current signal from API has no message_template property at all (absent = undefined).
    const currentOmitted: SignalDefinition = {
      ...matchingCurrentSignal,
      expression: { field: "days_blocked", op: "gt", value: 3 },
      report_settings: { severity: "critical", category: "delivery_flow" },
      // message_template intentionally absent (not set, so undefined at runtime)
    }
    const { container } = render(
      <SignalsChangedBanner
        currentSignals={[currentOmitted]}
        snapshotSignals={[snapshotWithNull]}
      />,
    )
    expect(container.firstChild).toBeNull()
  })

  it("flags banner when message_template changes from null/absent to a real string", () => {
    const snapshotWithNull: SnapshotSignal = {
      ...snapshotSignal,
      expression: {},
      severity: "critical",
      message_template: null,
    }
    const currentWithString: SignalDefinition = {
      ...matchingCurrentSignal,
      report_settings: {
        severity: "critical",
        category: "delivery_flow",
        message_template: "Now there is a template",
      },
    }
    render(
      <SignalsChangedBanner
        currentSignals={[currentWithString]}
        snapshotSignals={[snapshotWithNull]}
      />,
    )
    expect(
      screen.getByText(/configuration of some signals changed since this run/i),
    ).toBeInTheDocument()
  })

  it("flags banner when message_template changes from a real string back to null/absent", () => {
    const snapshotWithString: SnapshotSignal = {
      ...snapshotSignal,
      expression: {},
      severity: "critical",
      message_template: "Old template",
    }
    // Current signal has no message_template (omitted = undefined, normalized to null).
    const currentOmitted: SignalDefinition = {
      ...matchingCurrentSignal,
      report_settings: { severity: "critical", category: "delivery_flow" },
    }
    render(
      <SignalsChangedBanner
        currentSignals={[currentOmitted]}
        snapshotSignals={[snapshotWithString]}
      />,
    )
    expect(
      screen.getByText(/configuration of some signals changed since this run/i),
    ).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Accessibility: role="status" on the Callout
// ---------------------------------------------------------------------------

describe("SignalsChangedBanner accessibility", () => {
  it("renders the callout with role=status for assistive tech announcement", () => {
    render(
      <SignalsChangedBanner currentSignals={[]} snapshotSignals={[snapshotSignal]} />,
    )
    expect(screen.getByRole("status")).toBeInTheDocument()
  })
})
