// SPDX-License-Identifier: Apache-2.0

import { useId, useRef, useState } from "react"

import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"

interface ComboboxOption {
  value: string
  label: string
}

interface ComboboxProps {
  options: ComboboxOption[]
  value?: string
  onSelect: (value: string) => void
  placeholder?: string
  className?: string
  /** Accessible label for the input field. */
  inputLabel?: string
}

function Combobox({ className, inputLabel, onSelect, options, placeholder, value }: ComboboxProps) {
  // query is only used for filtering while the user is actively typing.
  const [query, setQuery] = useState("")
  // isEditing is true only between the first keystroke and selection/blur.
  const [isEditing, setIsEditing] = useState(false)
  const [open, setOpen] = useState(false)
  // -1 means no keyboard-active option.
  const [activeIndex, setActiveIndex] = useState(-1)
  const listboxId = useId()
  // Stable prefix for option element ids (required for aria-activedescendant).
  const optionIdPrefix = useId()
  const containerRef = useRef<HTMLDivElement>(null)

  // Derive the selected label directly from props so it resyncs automatically
  // when options load asynchronously or value changes post-mount.
  const selectedLabel = options.find((o) => o.value === value)?.label ?? ""

  // When not editing, display the resolved label; while editing, show what the user typed.
  const inputDisplayValue = isEditing ? query : selectedLabel

  // Show all options on (re)focus; filter only while the user is actively typing.
  const filtered =
    isEditing && query.trim()
      ? options.filter((o) => o.label.toLowerCase().includes(query.toLowerCase()))
      : options

  function handleSelect(option: ComboboxOption) {
    setQuery(option.label)
    setIsEditing(false)
    setOpen(false)
    setActiveIndex(-1)
    onSelect(option.value)
  }

  function handleBlur(event: React.FocusEvent<HTMLDivElement>) {
    if (!containerRef.current?.contains(event.relatedTarget as Node)) {
      setOpen(false)
      setIsEditing(false)
      setActiveIndex(-1)
    }
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault()
        setOpen(true)
        setActiveIndex((i) => (filtered.length === 0 ? -1 : (i + 1) % filtered.length))
        break
      case "ArrowUp":
        event.preventDefault()
        setOpen(true)
        setActiveIndex((i) =>
          filtered.length === 0 ? -1 : i <= 0 ? filtered.length - 1 : i - 1,
        )
        break
      case "Enter":
        if (activeIndex >= 0 && filtered[activeIndex] !== undefined) {
          event.preventDefault()
          handleSelect(filtered[activeIndex])
        }
        break
      case "Escape":
        setOpen(false)
        setActiveIndex(-1)
        break
    }
  }

  const activeOptionId =
    activeIndex >= 0 ? `${optionIdPrefix}-option-${activeIndex}` : undefined

  return (
    <div className={cn("relative", className)} onBlur={handleBlur} ref={containerRef}>
      <Input
        aria-activedescendant={activeOptionId}
        aria-autocomplete="list"
        aria-controls={listboxId}
        aria-expanded={open}
        aria-label={inputLabel}
        onChange={(e) => {
          setQuery(e.target.value)
          setIsEditing(true)
          setOpen(true)
          setActiveIndex(-1)
        }}
        onFocus={() => {
          // Treat focusing as "unedited": show all options, not filtered by selection.
          setIsEditing(false)
          setOpen(true)
          setActiveIndex(-1)
        }}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        role="combobox"
        value={inputDisplayValue}
      />
      {open && filtered.length > 0 && (
        <ul
          className="absolute z-20 mt-1 max-h-56 w-full overflow-auto rounded-md border border-border bg-background py-1 shadow-md"
          id={listboxId}
          role="listbox"
        >
          {filtered.map((option, index) => (
            <li
              aria-selected={option.value === value}
              className={cn(
                "cursor-pointer px-3 py-1.5 text-sm hover:bg-primary/10",
                index === activeIndex && "bg-primary/10",
              )}
              id={`${optionIdPrefix}-option-${index}`}
              key={option.value}
              onMouseDown={(e) => {
                // Prevent blur from firing before the click is handled.
                e.preventDefault()
                handleSelect(option)
              }}
              role="option"
            >
              {option.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export { Combobox }
export type { ComboboxOption }
