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
