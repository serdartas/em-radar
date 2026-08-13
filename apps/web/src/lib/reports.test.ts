import { describe, expect, it } from "vitest"

import { extractPartialDataNotes } from "@/lib/reports"

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
