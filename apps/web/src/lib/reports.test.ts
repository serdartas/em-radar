import { describe, expect, it } from "vitest"

import { extractPartialDataNotes, formatTimestamp } from "@/lib/reports"

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
