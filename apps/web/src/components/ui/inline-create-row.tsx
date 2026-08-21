// SPDX-License-Identifier: Apache-2.0

import type { ComponentProps } from "react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { cn } from "@/lib/utils"

interface InlineCreateRowProps extends Omit<ComponentProps<"div">, "onChange"> {
  /** Input field id — used to associate the label. */
  inputId: string
  label: string
  value: string
  onChange: (value: string) => void
  onAction: () => void
  actionLabel?: string
  placeholder?: string
  disabled?: boolean
}

function InlineCreateRow({
  actionLabel = "Create",
  className,
  disabled,
  inputId,
  label,
  onChange,
  onAction,
  placeholder,
  value,
  ...props
}: InlineCreateRowProps) {
  return (
    <div className={cn("flex items-end gap-2", className)} {...props}>
      <div className="flex flex-1 flex-col gap-1.5">
        <Label htmlFor={inputId}>{label}</Label>
        <Input
          disabled={disabled}
          id={inputId}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          value={value}
        />
      </div>
      <Button disabled={disabled || value.trim() === ""} onClick={onAction} type="button">
        {actionLabel}
      </Button>
    </div>
  )
}

export { InlineCreateRow }
