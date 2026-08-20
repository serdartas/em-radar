// SPDX-License-Identifier: Apache-2.0

function formatEvidenceValue(value: unknown): string {
  if (value === null) {
    return "null"
  }
  if (typeof value === "string") {
    return value
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value)
  }
  return JSON.stringify(value)
}

function evidenceEntries(evidence: unknown): [string, unknown][] | null {
  if (evidence === null || evidence === undefined) {
    return null
  }
  if (typeof evidence === "object" && !Array.isArray(evidence)) {
    const entries = Object.entries(evidence as Record<string, unknown>)
    return entries.length > 0 ? entries : null
  }
  return null
}

interface FindingEvidenceProps {
  evidence: unknown
}

function FindingEvidence({ evidence }: FindingEvidenceProps) {
  const entries = evidenceEntries(evidence)
  if (entries) {
    return (
      <div>
        <h4 className="font-semibold">Evidence</h4>
        <ul className="mt-1 space-y-1 text-slate-600">
          {entries.map(([key, value]) => (
            <li key={key}>
              <span className="font-medium">{key}</span>: {formatEvidenceValue(value)}
            </li>
          ))}
        </ul>
      </div>
    )
  }
  if (Array.isArray(evidence)) {
    if (evidence.length === 0) {
      return null
    }
    return (
      <div>
        <h4 className="font-semibold">Evidence</h4>
        <p className="mt-1 text-slate-600">
          {evidence.map((item) => formatEvidenceValue(item)).join(", ")}
        </p>
      </div>
    )
  }
  // Only meaningful scalars remain worth showing. Objects that produced no entries
  // (e.g. `{}`), null, undefined, and empty strings render nothing rather than a bare value.
  const isScalar =
    typeof evidence === "number" ||
    typeof evidence === "boolean" ||
    (typeof evidence === "string" && evidence !== "")
  if (!isScalar) {
    return null
  }
  return (
    <div>
      <h4 className="font-semibold">Evidence</h4>
      <p className="mt-1 text-slate-600">{formatEvidenceValue(evidence)}</p>
    </div>
  )
}

export { FindingEvidence }
