// SPDX-License-Identifier: Apache-2.0

import { useEffect, useId, useRef, useState } from "react"

import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"

interface ComboboxOption {
  value: string
  label: string
  /** Optional avatar / thumbnail URL. When present a small decorative image is
   *  rendered before the label in the dropdown. Existing consumers that omit
   *  this field render exactly as before. */
  imageUrl?: string
}

interface ComboboxProps {
  options: ComboboxOption[]
  value?: string
  onSelect: (value: string) => void
  placeholder?: string
  className?: string
  /** Accessible label for the input field (aria-label). */
  inputLabel?: string
  /**
   * Standard input labeling attributes so the combobox can be composed inside
   * FormRow: the cloned aria-describedby / id from cloneElement must reach the
   * actual <input> element or the label/hint association is lost.
   */
  id?: string
  "aria-describedby"?: string
  "aria-labelledby"?: string
  /**
   * When set, limits the number of options shown on focus/open before the user
   * starts typing. Once the user types, all matching options are shown regardless
   * of this limit. Useful for long lists where showing a few "top" items on focus
   * gives a quick preview without overwhelming the UI.
   */
  maxOnFocus?: number
  /**
   * When true, the input is disabled and the listbox does not open. Matches the
   * HTML `disabled` attribute semantics and lets callers reflect a loading or
   * empty-options state without the user being able to type into a stale input.
   */
  disabled?: boolean
  /**
   * Optional callback fired whenever the internal query string changes (i.e. on
   * every user keystroke). When provided the caller is responsible for
   * server-side search: it should debounce the value, fetch matching options,
   * and supply them via the `options` prop. Client-side filtering of `options`
   * is skipped when this prop is present so server results are shown as-is.
   *
   * Do NOT pass this prop if you are using a static `options` list — the
   * existing client-side filter behaviour is preserved when it is absent.
   */
  onQueryChange?: (query: string) => void
}

function Combobox({
  "aria-describedby": ariaDescribedby,
  "aria-labelledby": ariaLabelledby,
  className,
  disabled,
  id,
  inputLabel,
  maxOnFocus,
  onQueryChange,
  onSelect,
  options,
  placeholder,
  value,
}: ComboboxProps) {
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

  // Show options on (re)focus (limited by maxOnFocus when set); filter while typing.
  // When onQueryChange is provided (server-side search mode) the caller already
  // supplies filtered options so client-side filtering is skipped.
  const filtered =
    isEditing && query.trim()
      ? onQueryChange !== undefined
        ? options
        : options.filter((o) => o.label.toLowerCase().includes(query.toLowerCase()))
      : maxOnFocus !== undefined
        ? options.slice(0, maxOnFocus)
        : options

  // aria-expanded must track whether the popup is actually visible, not just
  // whether the component intends to open. When the filter matches nothing the
  // listbox is removed from the DOM but `open` stays true — keep them in sync.
  const listboxVisible = open && filtered.length > 0

  // Scroll the keyboard-active option into view so it's visible in the capped
  // max-h-56 container when navigating a long list.
  useEffect(() => {
    if (activeIndex < 0) return
    document
      .getElementById(`${optionIdPrefix}-option-${activeIndex}`)
      // scrollIntoView is not available in all test environments; the ?. makes
      // it a no-op in jsdom while remaining functional in real browsers.
      ?.scrollIntoView?.({ block: "nearest" })
  }, [activeIndex, optionIdPrefix])

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
        aria-controls={listboxVisible ? listboxId : undefined}
        aria-describedby={ariaDescribedby}
        aria-expanded={listboxVisible}
        aria-label={inputLabel}
        aria-labelledby={ariaLabelledby}
        disabled={disabled}
        id={id}
        onChange={(e) => {
          if (disabled) return
          setQuery(e.target.value)
          setIsEditing(true)
          setOpen(true)
          setActiveIndex(-1)
          onQueryChange?.(e.target.value)
        }}
        onFocus={() => {
          if (disabled) return
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
      {listboxVisible && (
        <ul
          className="absolute z-20 mt-1 max-h-56 w-full overflow-auto rounded-md border border-border bg-background py-1 shadow-md"
          id={listboxId}
          role="listbox"
        >
          {filtered.map((option, index) => (
            <li
              aria-selected={option.value === value}
              className={cn(
                "flex cursor-pointer items-center px-3 py-1.5 text-sm hover:bg-primary/10",
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
              {option.imageUrl && (
                <img
                  alt=""
                  className="mr-2 h-5 w-5 flex-shrink-0 rounded-full object-cover"
                  src={option.imageUrl}
                />
              )}
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
