// SPDX-License-Identifier: Apache-2.0

import { useId, useState, type ReactNode } from "react"
import { useQuery } from "@tanstack/react-query"

import { Callout } from "@/components/ui/callout"
import { FormRow } from "@/components/ui/form-row"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { type JiraFieldInfo, listJiraFields } from "@/lib/connections"

// ---------------------------------------------------------------------------
// Public data types
// ---------------------------------------------------------------------------

export interface FieldMappingValues {
  story_points?: string
  acceptance_criteria?: string | null
  acceptance_criteria_heading?: string | null
}

// ---------------------------------------------------------------------------
// FieldMappingRow
// ---------------------------------------------------------------------------

interface FieldMappingRowProps {
  /** Display label for the row and the switch's accessible name. */
  label: string
  /** Stable id for the switch element (also used as htmlFor on the Label). */
  switchId: string
  enabled: boolean
  onEnabledChange: (enabled: boolean) => void
  /** Revealed control shown only when enabled. */
  children: ReactNode
  /** Optional InfoTooltip content shown next to the label. */
  tooltip?: ReactNode
}

export function FieldMappingRow({
  children,
  enabled,
  label,
  onEnabledChange,
  switchId,
  tooltip,
}: FieldMappingRowProps) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-1.5">
          <Label htmlFor={switchId}>{label}</Label>
          {tooltip !== undefined && (
            <InfoTooltip label={`About ${label}`}>{tooltip}</InfoTooltip>
          )}
        </div>
        <Switch checked={enabled} id={switchId} onCheckedChange={onEnabledChange} />
      </div>
      {enabled ? (
        <div>{children}</div>
      ) : (
        <p className="text-xs text-slate-400">Not configured</p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Custom-field Select
// ---------------------------------------------------------------------------

interface CustomFieldSelectProps {
  id: string
  /** Accessible label forwarded to the <select> via FormRow's htmlFor linkage. */
  label: string
  value: string
  onChange: (value: string) => void
  fields: JiraFieldInfo[]
}

function CustomFieldSelect({ fields, id, label, onChange, value }: CustomFieldSelectProps) {
  const valueInList = fields.some((f) => f.id === value)

  return (
    <FormRow htmlFor={id} label={label}>
      <Select id={id} onChange={(e) => onChange(e.target.value)} value={value}>
        {/* Placeholder when no selection */}
        {!value && (
          <option disabled value="">
            {fields.length === 0
              ? "Save the connection first to load fields"
              : "Choose a field..."}
          </option>
        )}
        {/* Show current value if not in discovered list so the select is never visually blank */}
        {value && !valueInList && (
          <option value={value}>{value} (not in discovered fields)</option>
        )}
        {fields.map((field) => (
          <option key={field.id} value={field.id}>
            {field.name} ({field.id})
          </option>
        ))}
      </Select>
    </FormRow>
  )
}

// ---------------------------------------------------------------------------
// JiraFieldMappingSection
// ---------------------------------------------------------------------------

const HELPER_COPY =
  "Only Story Points and Acceptance Criteria need mapping here. All other Jira fields and " +
  "labels are available directly when writing signal rules, without any extra configuration."

type AcMode = "description" | "custom_field"

interface JiraFieldMappingSectionProps {
  /** The saved connection id, used to fetch discovered fields. Undefined when adding a new connection. */
  connectionId?: string
  fieldMappingValues?: FieldMappingValues
  onFieldMappingChange: (values: FieldMappingValues) => void
}

export function JiraFieldMappingSection({
  connectionId,
  fieldMappingValues,
  onFieldMappingChange,
}: JiraFieldMappingSectionProps) {
  const spSwitchId = useId()
  const acSwitchId = useId()
  const acModeSelectId = useId()
  const acHeadingId = useId()
  const acCustomFieldId = useId()
  const spFieldSelectId = useId()

  // Drive the Story Points toggle from independent local state so it is not a
  // dead control on a new (unsaved) connection where no fields are discovered
  // yet and story_points would otherwise remain "".
  const [spToggled, setSpToggled] = useState(() => !!(fieldMappingValues?.story_points))

  const { data: allFields = [] } = useQuery({
    queryKey: ["jiraFields", connectionId],
    queryFn: () => listJiraFields(connectionId!),
    enabled: !!connectionId,
  })

  const customFields = allFields
    .filter((f) => f.custom)
    .sort((a, b) => a.name.localeCompare(b.name))

  // Read controlled values
  const storyPointsValue = fieldMappingValues?.story_points ?? ""
  const acCustomField = fieldMappingValues?.acceptance_criteria ?? null
  const acHeading = fieldMappingValues?.acceptance_criteria_heading ?? null

  // AC enabled/mode are fully derived from props (AC always sets a non-null value on enable).
  const acEnabled = acCustomField !== null || acHeading !== null
  const acMode: AcMode = acCustomField !== null ? "custom_field" : "description"

  // Returns the current AC values for use in every emitted FieldMappingValues object.
  // story_points is included only when a non-empty value is stored in props so we never
  // emit story_points: "" to the backend.
  function currentBase(): FieldMappingValues {
    const base: FieldMappingValues = {
      acceptance_criteria: acCustomField,
      acceptance_criteria_heading: acHeading,
    }
    if (storyPointsValue) {
      base.story_points = storyPointsValue
    }
    return base
  }

  // ── Story Points handlers ─────────────────────────────────────────────────

  function handleSpToggle(on: boolean) {
    setSpToggled(on)
    if (!on) {
      // Omit story_points so the backend default applies; never emit story_points: "".
      onFieldMappingChange({
        acceptance_criteria: acCustomField,
        acceptance_criteria_heading: acHeading,
      })
    }
    // When enabling: do NOT pre-select a field. The revealed control shows
    // "Choose a field..." (or "Save first…") and waits for an explicit choice.
  }

  function handleSpChange(value: string) {
    const next: FieldMappingValues = { ...currentBase() }
    if (value) {
      next.story_points = value
    } else {
      delete next.story_points
    }
    onFieldMappingChange(next)
  }

  // ── Acceptance Criteria handlers ─────────────────────────────────────────

  function handleAcToggle(on: boolean) {
    if (on) {
      onFieldMappingChange({
        ...currentBase(),
        acceptance_criteria: null,
        acceptance_criteria_heading: "### Acceptance Criteria",
      })
    } else {
      onFieldMappingChange({
        ...currentBase(),
        acceptance_criteria: null,
        acceptance_criteria_heading: null,
      })
    }
  }

  function handleAcModeChange(mode: AcMode) {
    if (mode === "description") {
      onFieldMappingChange({
        ...currentBase(),
        acceptance_criteria: null,
        acceptance_criteria_heading: acHeading ?? "### Acceptance Criteria",
      })
    } else {
      // Switch to custom_field mode: keep any previously stored field id or start
      // with no selection — never pre-select the first discovered field.
      onFieldMappingChange({
        ...currentBase(),
        acceptance_criteria: acCustomField ?? "",
        acceptance_criteria_heading: null,
      })
    }
  }

  function handleAcHeadingChange(heading: string) {
    onFieldMappingChange({ ...currentBase(), acceptance_criteria_heading: heading })
  }

  function handleAcCustomFieldChange(value: string) {
    onFieldMappingChange({ ...currentBase(), acceptance_criteria: value })
  }

  return (
    <fieldset className="rounded-md border px-4 pb-4">
      <legend className="px-1 text-sm font-medium">Jira Field Mapping</legend>

      <div className="space-y-6 pt-4">
        {/* Story Points */}
        <FieldMappingRow
          enabled={spToggled}
          label="Story Points"
          onEnabledChange={handleSpToggle}
          switchId={spSwitchId}
        >
          <CustomFieldSelect
            fields={customFields}
            id={spFieldSelectId}
            label="Story points field"
            onChange={handleSpChange}
            value={storyPointsValue}
          />
        </FieldMappingRow>

        {/* Acceptance Criteria */}
        <FieldMappingRow
          enabled={acEnabled}
          label="Acceptance Criteria"
          onEnabledChange={handleAcToggle}
          switchId={acSwitchId}
        >
          <div className="space-y-3">
            <FormRow htmlFor={acModeSelectId} label="How is it recorded?">
              <Select
                id={acModeSelectId}
                onChange={(e) => handleAcModeChange(e.target.value as AcMode)}
                value={acMode}
              >
                <option value="description">Text in description</option>
                <option value="custom_field">Custom field</option>
              </Select>
            </FormRow>

            {acMode === "description" && (
              <FormRow
                action={
                  <InfoTooltip label="About heading text">
                    <p>
                      Enter the exact Markdown heading used to mark the Acceptance Criteria section
                      in your issue descriptions (for example,{" "}
                      <code className="rounded bg-blue-100 px-1">### Acceptance Criteria</code>).
                      EM Radar extracts the text that appears directly below this heading.
                    </p>
                  </InfoTooltip>
                }
                hint="The exact Markdown heading that marks the Acceptance Criteria section. Text immediately below this heading is extracted."
                htmlFor={acHeadingId}
                label="Heading text"
              >
                <Input
                  id={acHeadingId}
                  onChange={(e) => handleAcHeadingChange(e.target.value)}
                  placeholder="### Acceptance Criteria"
                  value={acHeading ?? ""}
                />
              </FormRow>
            )}

            {acMode === "custom_field" && (
              <CustomFieldSelect
                fields={customFields}
                id={acCustomFieldId}
                label="Acceptance criteria field"
                onChange={handleAcCustomFieldChange}
                value={acCustomField ?? ""}
              />
            )}
          </div>
        </FieldMappingRow>

        {/* Helper copy (F-MAP-8) */}
        <Callout variant="info">
          <p>{HELPER_COPY}</p>
        </Callout>
      </div>
    </fieldset>
  )
}
