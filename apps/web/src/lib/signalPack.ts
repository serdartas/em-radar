// SPDX-License-Identifier: Apache-2.0

import { API_BASE_URL, ApiError, apiFetch } from "@/lib/api"
import type { Severity } from "@/lib/severity"

export type ExportType = "private_backup" | "public_template"
export type ImportMode = "additive"
export type ConflictMode = "skip" | "overwrite" | "keep_both" | "cancel"

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
  unresolved_mappings: string[]
  imported_signal_names: string[]
  signal_name_clashes?: string[]
  group_name_clashes?: string[]
}

export interface ImportRequest {
  raw_yaml: string
  mode: ImportMode
  conflict?: ConflictMode
}

export async function exportSignalGroupsPack(
  groupIds: string[],
  exportType: ExportType,
): Promise<string> {
  const params = new URLSearchParams({ export_type: exportType })
  for (const groupId of groupIds) {
    params.append("group_ids", groupId)
  }
  const response = await fetch(`${API_BASE_URL}/signal-pack/export?${params.toString()}`)
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
