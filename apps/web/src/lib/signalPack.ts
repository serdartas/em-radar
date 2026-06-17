import { API_BASE_URL, ApiError, apiFetch } from "@/lib/api"
import type { Severity } from "@/lib/severity"

export type ExportMode = "full" | "minimal"
export type ImportMode = "additive" | "replace_all"

export interface ImportWarning {
  code: string
  message: string
  path: string
}

export interface BoolChange {
  before: boolean
  after: boolean
}

export interface SeverityChange {
  before: Severity
  after: Severity
}

export interface ParamsChange {
  before: Record<string, unknown>
  after: Record<string, unknown>
}

export interface SignalImportDiff {
  signal_id: string
  enabled?: BoolChange | null
  severity?: SeverityChange | null
  params?: ParamsChange | null
}

export interface SignalPackImportPreview {
  pack_name: string
  warnings: ImportWarning[]
  changes: SignalImportDiff[]
}

export interface ImportRequest {
  raw_yaml: string
  mode: ImportMode
}

export async function exportSignalPack(mode: ExportMode): Promise<string> {
  const response = await fetch(`${API_BASE_URL}/signal-pack/export?mode=${mode}`)
  if (!response.ok) {
    throw new ApiError(response.status, `Export failed with status ${response.status}.`)
  }
  return response.text()
}

export async function previewSignalPackImport(
  request: ImportRequest,
): Promise<SignalPackImportPreview> {
  return apiFetch<SignalPackImportPreview>("/signal-pack/import", {
    method: "POST",
    body: JSON.stringify(request),
  })
}

export async function applySignalPackImport(
  request: ImportRequest,
): Promise<SignalPackImportPreview> {
  return apiFetch<SignalPackImportPreview>("/signal-pack/import/apply", {
    method: "POST",
    body: JSON.stringify(request),
  })
}
