// SPDX-License-Identifier: Apache-2.0

import { useEffect, useId, useState, type ReactNode } from "react"
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
  /**
   * Default value for acceptance_criteria_heading, sourced from the connector's config_schema
   * (`$defs.JiraFieldMappingConfig.properties.acceptance_criteria_heading.default`).
   * Emitted as the heading when AC is enabled in description mode and no heading is set.
   */
  acHeadingDefault: string
  /**
   * Default value for story_points, sourced from the connector's config_schema
   * (`$defs.JiraFieldMappingConfig.properties.story_points.default`).
   * Shown when a saved connection omits the key, so the UI mirrors the field the
   * connector actually uses at runtime rather than displaying it as unconfigured.
   */
  spDefault: string
  /**
   * When true, the section is locked and shows an explanation in place of its controls.
   * Kept false once the connection is saved and a test has passed.
   */
  disabled?: boolean
}

export function JiraFieldMappingSection({
  acHeadingDefault,
  connectionId,
  disabled = false,
  fieldMappingValues,
  onFieldMappingChange,
  spDefault,
}: JiraFieldMappingSectionProps) {
  const spSwitchId = useId()
  const acSwitchId = useId()
  const acModeSelectId = useId()
  const acHeadingId = useId()
  const acCustomFieldId = useId()
  const spFieldSelectId = useId()

  // spForcedOpen is true only while the user clicked the switch ON without a value
  // present (e.g. unsaved connection, no discovered fields). It is reset to false on
  // disable or when connectionId changes so it never leaks into a different connection.
  const [spForcedOpen, setSpForcedOpen] = useState(false)

  // Reset the forced-open state whenever the connection context changes.
  // This prevents an "open but no value" SP toggle from carrying over to
  // the next connection loaded into the same mounted form.
  useEffect(() => {
    setSpForcedOpen(false)
  }, [connectionId])

  const { data: allFields = [] } = useQuery({
    queryKey: ["jiraFields", connectionId],
    queryFn: () => listJiraFields(connectionId!),
    // Only fetch once the section is unlocked: avoids exhausting retries while
    // disabled so the query fires fresh when the gate opens.
    enabled: !!connectionId && !disabled,
  })

  const customFields = allFields
    .filter((f) => f.custom)
    .sort((a, b) => a.name.localeCompare(b.name))

  // Read controlled values. An ABSENT key (undefined) means the saved connection relies on
  // the connector's default, which it actively applies at runtime — so mirror that default
  // here instead of showing the mapping as unconfigured. An EXPLICIT off value ("" for story
  // points, null for AC) is a deliberate user choice and is preserved as-is.
  const storyPointsValue =
    fieldMappingValues?.story_points === undefined ? spDefault : fieldMappingValues.story_points
  const acCustomField =
    fieldMappingValues?.acceptance_criteria === undefined
      ? null
      : fieldMappingValues.acceptance_criteria
  const acHeading =
    fieldMappingValues?.acceptance_criteria_heading === undefined
      ? acHeadingDefault
      : fieldMappingValues.acceptance_criteria_heading

  // spEnabled re-syncs from props on every render (mirrors AC's fully-derived approach).
  // It is true when a saved value exists in props OR when the user explicitly clicked ON.
  // "Off" is a real, stable state: turning SP off emits an empty story_points (see
  // handleSpToggle / currentSpPart), which round-trips back as "" and keeps the switch off.
  const spEnabled = storyPointsValue !== "" || spForcedOpen

  // AC enabled/mode are fully derived from props (AC always sets a non-null value on enable).
  const acEnabled = acCustomField !== null || acHeading !== null
  const acMode: AcMode = acCustomField !== null ? "custom_field" : "description"

  // ── Helpers for building the emitted FieldMappingValues ──────────────────
  //
  // story_points is ALWAYS emitted:
  //  - When SP is on and has a value: emit that value.
  //  - When SP is off or has no value yet: emit "" (mirrors AC's null "off" state).
  //    The empty string clears any previously stored override via the backend's
  //    deep-merge and round-trips back as an empty story_points, so spEnabled stays
  //    false and the switch is reliably off.
  // AC keys are emitted ONLY when the user has actively configured AC;
  // omitting them preserves whatever the backend already stores (or its default).

  function currentSpPart(): { story_points: string } {
    return {
      story_points: spEnabled && storyPointsValue ? storyPointsValue : "",
    }
  }

  function currentAcPart(): Partial<FieldMappingValues> {
    if (!acEnabled) {
      // AC not configured: omit AC keys so stored behavior is preserved.
      return {}
    }
    if (acMode === "description") {
      return {
        acceptance_criteria: null,
        // Use the schema default heading if none is stored so we never emit null
        // in description mode, which would disable the connector's default extraction.
        acceptance_criteria_heading: acHeading ?? acHeadingDefault,
      }
    }
    // custom_field mode
    return {
      acceptance_criteria: acCustomField,
      acceptance_criteria_heading: null,
    }
  }

  // ── Story Points handlers ─────────────────────────────────────────────────

  function handleSpToggle(on: boolean) {
    setSpForcedOpen(on)
    if (!on) {
      // SP turned off: emit an empty story_points so any stored custom-field override
      // is cleared by the deep-merge and the disabled state round-trips back as props.
      onFieldMappingChange({
        story_points: "",
        ...currentAcPart(),
      })
    }
    // When enabling: do NOT pre-select a field. The revealed control shows
    // "Choose a field..." (or "Save first…") and waits for an explicit choice.
  }

  function handleSpChange(value: string) {
    onFieldMappingChange({
      story_points: value,
      ...currentAcPart(),
    })
  }

  // ── Acceptance Criteria handlers ─────────────────────────────────────────

  function handleAcToggle(on: boolean) {
    if (on) {
      onFieldMappingChange({
        ...currentSpPart(),
        acceptance_criteria: null,
        acceptance_criteria_heading: acHeadingDefault,
      })
    } else {
      onFieldMappingChange({
        ...currentSpPart(),
        acceptance_criteria: null,
        acceptance_criteria_heading: null,
      })
    }
  }

  function handleAcModeChange(mode: AcMode) {
    if (mode === "description") {
      onFieldMappingChange({
        ...currentSpPart(),
        acceptance_criteria: null,
        acceptance_criteria_heading: acHeading ?? acHeadingDefault,
      })
    } else {
      // Switch to custom_field mode: keep any previously stored field id or start
      // with no selection — never pre-select the first discovered field.
      onFieldMappingChange({
        ...currentSpPart(),
        acceptance_criteria: acCustomField ?? "",
        acceptance_criteria_heading: null,
      })
    }
  }

  function handleAcHeadingChange(heading: string) {
    onFieldMappingChange({
      ...currentSpPart(),
      acceptance_criteria: null,
      acceptance_criteria_heading: heading,
    })
  }

  function handleAcCustomFieldChange(value: string) {
    onFieldMappingChange({
      ...currentSpPart(),
      acceptance_criteria: value,
      acceptance_criteria_heading: null,
    })
  }

  const gateCopy = connectionId
    ? "Run a successful test to configure field mapping."
    : "Save the connection and run a successful test to configure field mapping."

  return (
    <fieldset className="rounded-md border px-4 pb-4">
      <legend className="px-1 text-sm font-medium">Jira Field Mapping</legend>

      {disabled ? (
        <div className="pt-4">
          <Callout variant="info">
            <p>{gateCopy}</p>
          </Callout>
        </div>
      ) : (
      <div className="space-y-6 pt-4">
        {/* Story Points */}
        <FieldMappingRow
          enabled={spEnabled}
          label="Story Points"
          onEnabledChange={handleSpToggle}
          switchId={spSwitchId}
          tooltip={
            <p>
              Select the Jira custom field that stores story point estimates. EM Radar reads
              this field to calculate velocity and sizing metrics.
            </p>
          }
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
          tooltip={
            <p>
              Specify where acceptance criteria are recorded in your Jira issues. EM Radar
              extracts this text to evaluate definition-of-done completeness.
            </p>
          }
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
                  placeholder={acHeadingDefault}
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
      )}
    </fieldset>
  )
}
