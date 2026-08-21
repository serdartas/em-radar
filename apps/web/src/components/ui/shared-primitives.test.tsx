import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { useState } from "react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"

import { BackLink } from "@/components/ui/back-link"
import { Callout } from "@/components/ui/callout"
import { Checkbox } from "@/components/ui/checkbox"
import { Combobox, type ComboboxOption } from "@/components/ui/combobox"
import { ConfirmDialog } from "@/components/ui/confirm-dialog"
import { ExternalDocLink } from "@/components/ui/external-doc-link"
import { FormRow } from "@/components/ui/form-row"
import { HelpDocCard } from "@/components/ui/help-doc-card"
import { InlineCreateRow } from "@/components/ui/inline-create-row"
import { ListItemRow } from "@/components/ui/list-item-row"

afterEach(cleanup)

// ---------------------------------------------------------------------------
// Checkbox
// ---------------------------------------------------------------------------
describe("Checkbox", () => {
  it("renders an unchecked checkbox by default", () => {
    render(<Checkbox aria-label="Accept terms" readOnly />)
    const checkbox = screen.getByRole("checkbox", { name: "Accept terms" })
    expect(checkbox).not.toBeChecked()
  })

  it("renders as checked when the checked prop is true", () => {
    render(<Checkbox aria-label="Accept terms" checked readOnly />)
    expect(screen.getByRole("checkbox")).toBeChecked()
  })

  it("fires onChange when clicked", () => {
    const onChange = vi.fn()
    render(<Checkbox aria-label="Accept terms" onChange={onChange} />)
    fireEvent.click(screen.getByRole("checkbox"))
    expect(onChange).toHaveBeenCalledOnce()
  })
})

// ---------------------------------------------------------------------------
// ConfirmDialog
// ---------------------------------------------------------------------------
describe("ConfirmDialog", () => {
  it("renders title, body and confirmLabel", () => {
    render(
      <ConfirmDialog
        body="This cannot be undone."
        confirmLabel="Confirm delete"
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
        title="Delete item"
      />,
    )
    expect(screen.getByRole("alertdialog")).toBeInTheDocument()
    expect(screen.getByText("Delete item")).toBeInTheDocument()
    expect(screen.getByText("This cannot be undone.")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Confirm delete" })).toBeInTheDocument()
  })

  it("omits the visible heading but keeps the accessible name when titleHidden", () => {
    render(
      <ConfirmDialog
        body="This cannot be undone."
        confirmLabel="Confirm delete"
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
        title="Delete item"
        titleHidden
      />,
    )
    expect(screen.getByRole("alertdialog", { name: "Confirm: Delete item" })).toBeInTheDocument()
    expect(screen.queryByText("Delete item")).not.toBeInTheDocument()
  })

  it("calls onConfirm when the confirm button is clicked", () => {
    const onConfirm = vi.fn()
    render(
      <ConfirmDialog
        body="Body"
        confirmLabel="Confirm delete"
        onCancel={vi.fn()}
        onConfirm={onConfirm}
        title="Title"
      />,
    )
    fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }))
    expect(onConfirm).toHaveBeenCalledOnce()
  })

  it("calls onCancel when the Cancel button is clicked", () => {
    const onCancel = vi.fn()
    render(
      <ConfirmDialog
        body="Body"
        confirmLabel="Confirm delete"
        onCancel={onCancel}
        onConfirm={vi.fn()}
        title="Title"
      />,
    )
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }))
    expect(onCancel).toHaveBeenCalledOnce()
  })

  it("disables the confirm button when pending is true", () => {
    render(
      <ConfirmDialog
        body="Body"
        confirmLabel="Confirm delete"
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
        pending
        title="Title"
      />,
    )
    expect(screen.getByRole("button", { name: "Confirm delete" })).toBeDisabled()
  })

  it("does not disable the confirm button when pending is false", () => {
    render(
      <ConfirmDialog
        body="Body"
        confirmLabel="Confirm delete"
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
        pending={false}
        title="Title"
      />,
    )
    expect(screen.getByRole("button", { name: "Confirm delete" })).not.toBeDisabled()
  })

  it("has aria-describedby pointing at the body element", () => {
    render(
      <ConfirmDialog
        body="Body text here"
        confirmLabel="Confirm"
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
        title="Title"
      />,
    )
    expect(screen.getByRole("alertdialog")).toHaveAccessibleDescription("Body text here")
  })

  it("moves focus to the Cancel button on mount", () => {
    render(
      <ConfirmDialog
        body="Body"
        confirmLabel="Confirm delete"
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
        title="Title"
      />,
    )
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Cancel" }))
  })
})

// ---------------------------------------------------------------------------
// Callout
// ---------------------------------------------------------------------------
describe("Callout", () => {
  it.each(["error", "warning", "success", "info"] as const)(
    "renders the %s variant",
    (variant) => {
      render(<Callout variant={variant}>Message</Callout>)
      expect(screen.getByText("Message")).toBeInTheDocument()
    },
  )

  it("renders the optional title", () => {
    render(<Callout title="Heads up" variant="info">Detail</Callout>)
    expect(screen.getByText("Heads up")).toBeInTheDocument()
    expect(screen.getByText("Detail")).toBeInTheDocument()
  })

  it("passes through the role prop", () => {
    render(<Callout role="alert" variant="error">Error occurred</Callout>)
    expect(screen.getByRole("alert")).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// FormRow
// ---------------------------------------------------------------------------
describe("FormRow", () => {
  it("associates the label with the field via htmlFor", () => {
    render(
      <FormRow htmlFor="my-field" label="My label">
        <input id="my-field" />
      </FormRow>,
    )
    const label = screen.getByText("My label")
    expect(label).toHaveAttribute("for", "my-field")
    expect(screen.getByLabelText("My label")).toBeInTheDocument()
  })

  it("renders an optional hint", () => {
    render(
      <FormRow hint="Use lowercase" htmlFor="field" label="Label">
        <input id="field" />
      </FormRow>,
    )
    expect(screen.getByText("Use lowercase")).toBeInTheDocument()
  })

  it("associates the hint with the field via aria-describedby", () => {
    render(
      <FormRow hint="Use lowercase" htmlFor="field" label="Label">
        <input id="field" />
      </FormRow>,
    )
    const input = screen.getByRole("textbox")
    const hint = screen.getByText("Use lowercase")
    expect(input).toHaveAttribute("aria-describedby", hint.id)
  })

  it("preserves existing aria-describedby alongside the hint id", () => {
    render(
      <FormRow hint="Use lowercase" htmlFor="field" label="Label">
        <input aria-describedby="existing-desc" id="field" />
      </FormRow>,
    )
    const input = screen.getByRole("textbox")
    const hint = screen.getByText("Use lowercase")
    const describedBy = input.getAttribute("aria-describedby") ?? ""
    expect(describedBy).toContain("existing-desc")
    expect(describedBy).toContain(hint.id)
  })

  it("forwards the hint id to a Combobox child via aria-describedby", () => {
    const comboOptions: ComboboxOption[] = [{ label: "Apple", value: "apple" }]
    render(
      <FormRow hint="Pick carefully" htmlFor="fruit" label="Fruit">
        <Combobox
          id="fruit"
          inputLabel="Fruit"
          onSelect={vi.fn()}
          options={comboOptions}
          placeholder="Pick..."
        />
      </FormRow>,
    )
    const input = screen.getByRole("combobox")
    const hint = screen.getByText("Pick carefully")
    expect(input).toHaveAttribute("aria-describedby", hint.id)
  })

  it("renders an optional action", () => {
    render(
      <FormRow action={<button type="button">Go</button>} htmlFor="field" label="Label">
        <input id="field" />
      </FormRow>,
    )
    expect(screen.getByRole("button", { name: "Go" })).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Combobox / TypeaheadSelect
// ---------------------------------------------------------------------------

/** Wrapper that lets tests drive value and options as controlled state. */
function ControlledCombobox({
  initialOptions = [] as ComboboxOption[],
  initialValue = undefined as string | undefined,
}: {
  initialOptions?: ComboboxOption[]
  initialValue?: string
}) {
  const [value, setValue] = useState(initialValue)
  const [options, setOptions] = useState(initialOptions)

  return (
    <>
      <Combobox
        inputLabel="Fruit"
        onSelect={setValue}
        options={options}
        placeholder="Pick..."
        value={value}
      />
      <button
        onClick={() => {
          setOptions([{ label: "Apple", value: "apple" }])
          setValue("apple")
        }}
        type="button"
      >
        Load options
      </button>
    </>
  )
}

describe("Combobox", () => {
  const options: ComboboxOption[] = [
    { label: "Apple", value: "apple" },
    { label: "Banana", value: "banana" },
    { label: "Cherry", value: "cherry" },
  ]

  it("shows all options when focused", () => {
    render(
      <Combobox inputLabel="Fruit" onSelect={vi.fn()} options={options} placeholder="Pick..." />,
    )
    fireEvent.focus(screen.getByRole("combobox"))
    expect(screen.getByRole("listbox")).toBeInTheDocument()
    expect(screen.getAllByRole("option")).toHaveLength(3)
  })

  it("filters options as the user types", () => {
    render(
      <Combobox inputLabel="Fruit" onSelect={vi.fn()} options={options} placeholder="Pick..." />,
    )
    const input = screen.getByRole("combobox")
    fireEvent.focus(input)
    fireEvent.change(input, { target: { value: "an" } })
    // "Banana" contains "an"; Apple and Cherry do not.
    const visible = screen.getAllByRole("option")
    expect(visible).toHaveLength(1)
    expect(visible[0]).toHaveTextContent("Banana")
  })

  it("calls onSelect and closes the list when an option is clicked", () => {
    const onSelect = vi.fn()
    render(
      <Combobox inputLabel="Fruit" onSelect={onSelect} options={options} placeholder="Pick..." />,
    )
    fireEvent.focus(screen.getByRole("combobox"))
    fireEvent.mouseDown(screen.getByRole("option", { name: "Cherry" }))
    expect(onSelect).toHaveBeenCalledWith("cherry")
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument()
  })

  it("shows all options when refocused with an existing selection", () => {
    render(
      <Combobox
        inputLabel="Fruit"
        onSelect={vi.fn()}
        options={options}
        placeholder="Pick..."
        value="banana"
      />,
    )
    const input = screen.getByRole("combobox")
    expect(input).toHaveValue("Banana")
    fireEvent.focus(input)
    // Must show all 3 options, not filtered down to just "Banana".
    expect(screen.getAllByRole("option")).toHaveLength(3)
  })

  it("resyncs the display label when value and options load asynchronously post-mount", () => {
    render(<ControlledCombobox />)
    // Initially no options and no value.
    expect(screen.getByRole("combobox")).toHaveValue("")

    // Simulate the parent resolving async options + a preselected value.
    fireEvent.click(screen.getByRole("button", { name: "Load options" }))

    expect(screen.getByRole("combobox")).toHaveValue("Apple")
  })

  it("moves aria-activedescendant via ArrowDown/ArrowUp", () => {
    render(
      <Combobox inputLabel="Fruit" onSelect={vi.fn()} options={options} placeholder="Pick..." />,
    )
    const input = screen.getByRole("combobox")
    fireEvent.focus(input)

    fireEvent.keyDown(input, { key: "ArrowDown" })
    const firstOptionId = screen.getAllByRole("option")[0].id
    expect(input).toHaveAttribute("aria-activedescendant", firstOptionId)

    fireEvent.keyDown(input, { key: "ArrowDown" })
    const secondOptionId = screen.getAllByRole("option")[1].id
    expect(input).toHaveAttribute("aria-activedescendant", secondOptionId)

    fireEvent.keyDown(input, { key: "ArrowUp" })
    expect(input).toHaveAttribute("aria-activedescendant", firstOptionId)
  })

  it("selects the active option on Enter", () => {
    const onSelect = vi.fn()
    render(
      <Combobox inputLabel="Fruit" onSelect={onSelect} options={options} placeholder="Pick..." />,
    )
    const input = screen.getByRole("combobox")
    fireEvent.focus(input)
    fireEvent.keyDown(input, { key: "ArrowDown" }) // active = Apple (index 0)
    fireEvent.keyDown(input, { key: "Enter" })
    expect(onSelect).toHaveBeenCalledWith("apple")
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument()
  })

  it("closes the listbox on Escape", () => {
    render(
      <Combobox inputLabel="Fruit" onSelect={vi.fn()} options={options} placeholder="Pick..." />,
    )
    const input = screen.getByRole("combobox")
    fireEvent.focus(input)
    expect(screen.getByRole("listbox")).toBeInTheDocument()
    fireEvent.keyDown(input, { key: "Escape" })
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument()
  })

  it("sets aria-expanded to false when the filter matches no options", () => {
    render(
      <Combobox inputLabel="Fruit" onSelect={vi.fn()} options={options} placeholder="Pick..." />,
    )
    const input = screen.getByRole("combobox")
    fireEvent.focus(input)
    fireEvent.change(input, { target: { value: "zzz" } })
    // No options match — listbox must be absent and aria-expanded must be false.
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument()
    expect(input).toHaveAttribute("aria-expanded", "false")
  })

  it("only sets aria-controls while the listbox is in the DOM", () => {
    render(
      <Combobox inputLabel="Fruit" onSelect={vi.fn()} options={options} placeholder="Pick..." />,
    )
    const input = screen.getByRole("combobox")
    // Closed on mount: no dangling reference to a non-existent listbox.
    expect(input).not.toHaveAttribute("aria-controls")

    fireEvent.focus(input)
    const listboxId = screen.getByRole("listbox").id
    expect(input).toHaveAttribute("aria-controls", listboxId)

    fireEvent.change(input, { target: { value: "zzz" } })
    expect(input).not.toHaveAttribute("aria-controls")
  })

  it("disabled Combobox does not open or accept input", () => {
    render(
      <Combobox
        disabled
        inputLabel="Fruit"
        onSelect={vi.fn()}
        options={options}
        placeholder="Pick..."
      />,
    )
    const input = screen.getByRole("combobox")
    expect(input).toBeDisabled()
    // Focus and change must not open the listbox.
    fireEvent.focus(input)
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument()
    fireEvent.change(input, { target: { value: "an" } })
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument()
  })

  it("calls scrollIntoView on the active option when navigating with keyboard", () => {
    const scrollIntoView = vi.fn()
    window.HTMLElement.prototype.scrollIntoView = scrollIntoView

    render(
      <Combobox inputLabel="Fruit" onSelect={vi.fn()} options={options} placeholder="Pick..." />,
    )
    const input = screen.getByRole("combobox")
    fireEvent.focus(input)
    fireEvent.keyDown(input, { key: "ArrowDown" })

    expect(scrollIntoView).toHaveBeenCalledWith({ block: "nearest" })
  })
})

// ---------------------------------------------------------------------------
// InlineCreateRow
// ---------------------------------------------------------------------------
describe("InlineCreateRow", () => {
  it("renders label, input and action button", () => {
    render(
      <InlineCreateRow
        inputId="new-team"
        label="New team"
        onChange={vi.fn()}
        onAction={vi.fn()}
        value=""
      />,
    )
    expect(screen.getByLabelText("New team")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Create" })).toBeInTheDocument()
  })

  it("calls onChange when the input changes", () => {
    const onChange = vi.fn()
    render(
      <InlineCreateRow
        inputId="field"
        label="Label"
        onChange={onChange}
        onAction={vi.fn()}
        value=""
      />,
    )
    fireEvent.change(screen.getByLabelText("Label"), { target: { value: "foo" } })
    expect(onChange).toHaveBeenCalledWith("foo")
  })

  it("calls onAction when the button is clicked", () => {
    const onAction = vi.fn()
    render(
      <InlineCreateRow
        inputId="field"
        label="Label"
        onChange={vi.fn()}
        onAction={onAction}
        value="foo"
      />,
    )
    fireEvent.click(screen.getByRole("button", { name: "Create" }))
    expect(onAction).toHaveBeenCalledOnce()
  })

  it("accepts a custom actionLabel", () => {
    render(
      <InlineCreateRow
        actionLabel="Add"
        inputId="field"
        label="Label"
        onChange={vi.fn()}
        onAction={vi.fn()}
        value=""
      />,
    )
    expect(screen.getByRole("button", { name: "Add" })).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// ListItemRow
// ---------------------------------------------------------------------------
describe("ListItemRow", () => {
  it("renders the label", () => {
    render(<ListItemRow label="My item" />)
    expect(screen.getByText("My item")).toBeInTheDocument()
  })

  it("renders a trailing action", () => {
    render(<ListItemRow action={<button type="button">Delete</button>} label="My item" />)
    expect(screen.getByRole("button", { name: "Delete" })).toBeInTheDocument()
  })

  it("fires the action handler", () => {
    const onClick = vi.fn()
    render(
      <ListItemRow
        action={<button onClick={onClick} type="button">Delete</button>}
        label="Item"
      />,
    )
    fireEvent.click(screen.getByRole("button", { name: "Delete" }))
    expect(onClick).toHaveBeenCalledOnce()
  })
})

// ---------------------------------------------------------------------------
// BackLink
// ---------------------------------------------------------------------------
describe("BackLink", () => {
  it("renders a link with default text", () => {
    render(
      <MemoryRouter>
        <BackLink to="/settings" />
      </MemoryRouter>,
    )
    expect(screen.getByRole("link", { name: /back/i })).toBeInTheDocument()
  })

  it("renders custom children as link text", () => {
    render(
      <MemoryRouter>
        <BackLink to="/settings">Return to settings</BackLink>
      </MemoryRouter>,
    )
    expect(screen.getByRole("link", { name: /return to settings/i })).toBeInTheDocument()
  })

  it("has the correct href", () => {
    render(
      <MemoryRouter>
        <BackLink to="/reports">Back to reports</BackLink>
      </MemoryRouter>,
    )
    expect(screen.getByRole("link")).toHaveAttribute("href", "/reports")
  })
})

// ---------------------------------------------------------------------------
// HelpDocCard
// ---------------------------------------------------------------------------
describe("HelpDocCard", () => {
  it("renders the title", () => {
    render(<HelpDocCard title="Setup guide" />)
    expect(screen.getByText("Setup guide")).toBeInTheDocument()
  })

  it("renders children content", () => {
    render(<HelpDocCard title="Guide">Step-by-step instructions here.</HelpDocCard>)
    expect(screen.getByText("Step-by-step instructions here.")).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// ExternalDocLink
// ---------------------------------------------------------------------------
describe("ExternalDocLink", () => {
  it("renders the link text", () => {
    render(<ExternalDocLink href="https://example.com">Read the docs</ExternalDocLink>)
    expect(screen.getByRole("link", { name: /read the docs/i })).toBeInTheDocument()
  })

  it("sets target=_blank and rel=noopener noreferrer", () => {
    render(<ExternalDocLink href="https://example.com">Docs</ExternalDocLink>)
    const link = screen.getByRole("link", { name: /docs/i })
    expect(link).toHaveAttribute("target", "_blank")
    expect(link).toHaveAttribute("rel", "noopener noreferrer")
  })

  it("points to the correct href", () => {
    render(<ExternalDocLink href="https://docs.example.com/api">API Reference</ExternalDocLink>)
    expect(screen.getByRole("link")).toHaveAttribute("href", "https://docs.example.com/api")
  })
})
