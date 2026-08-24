import { describe, expect, it } from "vitest"

import { extractPartialDataNotes, extractSnapshotSignals, formatTimestamp } from "@/lib/reports"

describe("formatTimestamp", () => {
  it("interprets an offset-less API timestamp as UTC", () => {
    expect(formatTimestamp("2026-08-13T10:00:00")).toBe(
      new Date("2026-08-13T10:00:00Z").toLocaleString(),
    )
  })

  it("leaves a Z-suffixed timestamp unchanged", () => {
    expect(formatTimestamp("2026-08-13T10:00:00Z")).toBe(
      new Date("2026-08-13T10:00:00Z").toLocaleString(),
    )
  })

  it("respects an explicit numeric offset without double-shifting", () => {
    expect(formatTimestamp("2026-08-13T10:00:00+02:00")).toBe(
      new Date("2026-08-13T10:00:00+02:00").toLocaleString(),
    )
  })

  it("returns the raw string when unparseable", () => {
    expect(formatTimestamp("not a date")).toBe("not a date")
  })
})

describe("extractPartialDataNotes", () => {
  it("returns [] for non-object snapshots", () => {
    expect(extractPartialDataNotes(null)).toEqual([])
    expect(extractPartialDataNotes(undefined)).toEqual([])
    expect(extractPartialDataNotes("partial")).toEqual([])
    expect(extractPartialDataNotes(42)).toEqual([])
    expect(extractPartialDataNotes(true)).toEqual([])
  })

  it("returns [] when partial_data_notes is missing or not an array", () => {
    expect(extractPartialDataNotes({})).toEqual([])
    expect(extractPartialDataNotes({ partial_data_notes: "board unavailable" })).toEqual([])
    expect(extractPartialDataNotes({ partial_data_notes: 7 })).toEqual([])
    expect(extractPartialDataNotes({ partial_data_notes: { source: "board" } })).toEqual([])
  })

  it("filters out entries missing source/reason or with non-string values", () => {
    const snapshot = {
      partial_data_notes: [
        { source: "board", reason: "board data unavailable" },
        { source: "code" },
        { reason: "code data unavailable" },
        { source: 1, reason: "numeric source" },
        { source: "sprints", reason: 2 },
        null,
        "not an object",
        42,
      ],
    }

    expect(extractPartialDataNotes(snapshot)).toEqual([
      { source: "board", reason: "board data unavailable" },
    ])
  })

  it("returns [] when every array entry is malformed", () => {
    expect(
      extractPartialDataNotes({ partial_data_notes: [null, "x", 3, { source: "only" }] }),
    ).toEqual([])
  })

  it("preserves all well-formed notes", () => {
    const notes = [
      { source: "board", reason: "one" },
      { source: "code", reason: "two" },
    ]
    expect(extractPartialDataNotes({ partial_data_notes: notes })).toEqual(notes)
  })
})

describe("extractSnapshotSignals", () => {
  it("returns [] for non-object snapshots", () => {
    expect(extractSnapshotSignals(null)).toEqual([])
    expect(extractSnapshotSignals(undefined)).toEqual([])
    expect(extractSnapshotSignals("string")).toEqual([])
    expect(extractSnapshotSignals(42)).toEqual([])
  })

  it("returns [] when signal_definitions is missing or not an array", () => {
    expect(extractSnapshotSignals({})).toEqual([])
    expect(extractSnapshotSignals({ signal_definitions: "not an array" })).toEqual([])
    expect(extractSnapshotSignals({ signal_definitions: 7 })).toEqual([])
    expect(extractSnapshotSignals({ signal_definitions: null })).toEqual([])
  })

  it("filters out entries missing required string fields or with invalid template_key", () => {
    const snapshot = {
      signal_definitions: [
        {
          id: "sig-1",
          name: "Signal A",
          entity_type: "workitem",
          category: "delivery_flow",
          origin: "system_template",
          template_key: null,
        },
        { id: "sig-2", name: "Missing entity_type", category: "c", origin: "o", template_key: null },
        { name: "Missing id", entity_type: "workitem", category: "c", origin: "o", template_key: null },
        { id: "sig-4", name: "Missing category", entity_type: "workitem", origin: "o", template_key: null },
        // template_key is a number — invalid
        { id: "sig-5", name: "Bad key", entity_type: "workitem", category: "c", origin: "o", template_key: 42 },
        null,
        "not an object",
        42,
      ],
    }
    const result = extractSnapshotSignals(snapshot)
    expect(result).toHaveLength(1)
    expect(result[0].id).toBe("sig-1")
  })

  it("preserves all well-formed snapshot signal entries", () => {
    const defs = [
      {
        id: "sig-a",
        name: "Signal A",
        entity_type: "workitem",
        category: "delivery_flow",
        origin: "system_template",
        template_key: "blocked_work_item",
      },
      {
        id: "sig-b",
        name: "Signal B",
        entity_type: "sprint",
        category: "sprint_health",
        origin: "user_created",
        template_key: null,
      },
    ]
    expect(extractSnapshotSignals({ signal_definitions: defs })).toEqual(defs)
  })

  it("passes through optional extended fields (expression, severity, message_template)", () => {
    const defs = [
      {
        id: "sig-x",
        name: "Extended signal",
        entity_type: "workitem",
        category: "delivery_flow",
        origin: "system_template",
        template_key: null,
        expression: { field: "days_blocked", op: "gt", value: 3 },
        severity: "critical",
        message_template: null,
      },
    ]
    expect(extractSnapshotSignals({ signal_definitions: defs })).toEqual(defs)
  })
})
