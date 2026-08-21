// SPDX-License-Identifier: Apache-2.0

import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { BoardPicker, ProjectPicker } from "@/components/teams/TaskBoardPicker"
import type { JiraBoard, JiraProject } from "@/lib/connections"

afterEach(cleanup)

const mockProjects: JiraProject[] = [
  { id: "1", external_id: "ext-alpha", key: "ALPHA", name: "Alpha Project" },
  { id: "2", external_id: "ext-beta", key: "BETA", name: "Beta Project" },
  { id: "3", external_id: "ext-gamma", key: "GAMMA", name: "Gamma Project" },
]

const makeBoards = (count: number): JiraBoard[] =>
  Array.from({ length: count }, (_, i) => ({
    id: String(i + 1),
    external_id: `board-ext-${i + 1}`,
    project_id: "1",
    name: `Sprint Board ${i + 1}`,
    type: "scrum" as const,
  }))

// ---------------------------------------------------------------------------
// ProjectPicker
// ---------------------------------------------------------------------------
describe("ProjectPicker", () => {
  it("shows all projects when focused", () => {
    render(
      <ProjectPicker
        isLoading={false}
        onSelect={vi.fn()}
        projects={mockProjects}
        value=""
      />,
    )
    fireEvent.focus(screen.getByRole("combobox"))
    expect(screen.getAllByRole("option")).toHaveLength(3)
  })

  it("typing filters the project options", () => {
    render(
      <ProjectPicker
        isLoading={false}
        onSelect={vi.fn()}
        projects={mockProjects}
        value=""
      />,
    )
    const input = screen.getByRole("combobox")
    fireEvent.focus(input)
    fireEvent.change(input, { target: { value: "alpha" } })
    const options = screen.getAllByRole("option")
    expect(options).toHaveLength(1)
    expect(options[0]).toHaveTextContent("ALPHA")
  })

  it("selecting an option calls onSelect with the project external_id", () => {
    const onSelect = vi.fn()
    render(
      <ProjectPicker
        isLoading={false}
        onSelect={onSelect}
        projects={mockProjects}
        value=""
      />,
    )
    fireEvent.focus(screen.getByRole("combobox"))
    fireEvent.mouseDown(screen.getByRole("option", { name: /Alpha Project/i }))
    expect(onSelect).toHaveBeenCalledWith("ext-alpha")
  })

  it("shows the selected project label when a value is provided", () => {
    render(
      <ProjectPicker
        isLoading={false}
        onSelect={vi.fn()}
        projects={mockProjects}
        value="ext-beta"
      />,
    )
    expect(screen.getByRole("combobox")).toHaveValue("BETA - Beta Project")
  })
})

// ---------------------------------------------------------------------------
// BoardPicker
// ---------------------------------------------------------------------------
describe("BoardPicker", () => {
  it("shows up to 5 boards on focus (top ~5 behavior)", () => {
    render(
      <BoardPicker
        boards={makeBoards(10)}
        isLoading={false}
        onSelect={vi.fn()}
        value=""
      />,
    )
    fireEvent.focus(screen.getByRole("combobox"))
    expect(screen.getAllByRole("option")).toHaveLength(5)
  })

  it("shows all boards when there are fewer than 5", () => {
    render(
      <BoardPicker
        boards={makeBoards(3)}
        isLoading={false}
        onSelect={vi.fn()}
        value=""
      />,
    )
    fireEvent.focus(screen.getByRole("combobox"))
    expect(screen.getAllByRole("option")).toHaveLength(3)
  })

  it("typing filters beyond the focus limit and shows all matches", () => {
    render(
      <BoardPicker
        boards={makeBoards(10)}
        isLoading={false}
        onSelect={vi.fn()}
        value=""
      />,
    )
    const input = screen.getByRole("combobox")
    fireEvent.focus(input)
    // Only "Sprint Board 10" contains "10".
    fireEvent.change(input, { target: { value: "Board 10" } })
    const options = screen.getAllByRole("option")
    expect(options).toHaveLength(1)
    expect(options[0]).toHaveTextContent("Sprint Board 10")
  })

  it("typing shows all matching boards even beyond the 5-item focus cap", () => {
    render(
      <BoardPicker
        boards={makeBoards(8)}
        isLoading={false}
        onSelect={vi.fn()}
        value=""
      />,
    )
    const input = screen.getByRole("combobox")
    fireEvent.focus(input)
    // Typing a common substring that matches all 8 boards.
    fireEvent.change(input, { target: { value: "Sprint" } })
    expect(screen.getAllByRole("option")).toHaveLength(8)
  })

  it("selecting an option calls onSelect with the board external_id", () => {
    const onSelect = vi.fn()
    render(
      <BoardPicker
        boards={makeBoards(5)}
        isLoading={false}
        onSelect={onSelect}
        value=""
      />,
    )
    fireEvent.focus(screen.getByRole("combobox"))
    fireEvent.mouseDown(screen.getByRole("option", { name: "Sprint Board 3" }))
    expect(onSelect).toHaveBeenCalledWith("board-ext-3")
  })

  it("shows the selected board label when a value is provided", () => {
    render(
      <BoardPicker
        boards={makeBoards(5)}
        isLoading={false}
        onSelect={vi.fn()}
        value="board-ext-2"
      />,
    )
    expect(screen.getByRole("combobox")).toHaveValue("Sprint Board 2")
  })
})
