// SPDX-License-Identifier: Apache-2.0

import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { ConfirmDialog } from "@/components/ui/confirm-dialog"

afterEach(cleanup)

describe("ConfirmDialog", () => {
  it("moves focus to Cancel on mount", () => {
    render(
      <ConfirmDialog
        body="This cannot be undone."
        confirmLabel="Delete"
        onCancel={() => undefined}
        onConfirm={() => undefined}
        title="Delete thing"
      />,
    )

    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus()
  })

  it("calls onCancel when Escape is pressed", () => {
    const onCancel = vi.fn()
    render(
      <ConfirmDialog
        body="This cannot be undone."
        confirmLabel="Delete"
        onCancel={onCancel}
        onConfirm={() => undefined}
        title="Delete thing"
      />,
    )

    fireEvent.keyDown(screen.getByRole("alertdialog"), { key: "Escape" })
    expect(onCancel).toHaveBeenCalledOnce()
  })

  it("restores focus to the opener when it unmounts", () => {
    function Harness({ open }: { open: boolean }) {
      return (
        <div>
          <button type="button">opener</button>
          {open && (
            <ConfirmDialog
              body="This cannot be undone."
              confirmLabel="Delete"
              onCancel={() => undefined}
              onConfirm={() => undefined}
              title="Delete thing"
            />
          )}
        </div>
      )
    }

    // Simulate a real trigger being focused before the dialog opens.
    const { rerender } = render(<Harness open={false} />)
    const openerButton = screen.getByRole("button", { name: "opener" })
    openerButton.focus()
    expect(openerButton).toHaveFocus()

    rerender(<Harness open={true} />)
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus()

    rerender(<Harness open={false} />)
    expect(openerButton).toHaveFocus()
  })
})
