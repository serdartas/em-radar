import { apiFetch } from "@/lib/api"
import type { JsonSchema } from "@/lib/jsonSchema"
import type { Severity } from "@/lib/severity"

export interface SignalConfig {
  signal_id: string
  name: string
  description: string
  default_severity: Severity
  enabled: boolean
  severity_override: Severity | null
  params: Record<string, unknown>
  params_schema: JsonSchema
}

export interface SignalConfigPatch {
  enabled: boolean
  severity_override: Severity | null
  params: Record<string, unknown>
}

export async function listSignalConfigs(): Promise<SignalConfig[]> {
  return apiFetch<SignalConfig[]>("/signal-configs")
}

export async function updateSignalConfig(
  signalId: string,
  patch: SignalConfigPatch,
): Promise<SignalConfig> {
  return apiFetch<SignalConfig>(`/signal-configs/${signalId}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  })
}

export async function resetSignalConfig(signalId: string): Promise<SignalConfig> {
  return apiFetch<SignalConfig>(`/signal-configs/${signalId}/reset`, { method: "POST" })
}

export async function resetAllSignalConfigs(): Promise<SignalConfig[]> {
  return apiFetch<SignalConfig[]>("/signal-configs/reset", { method: "POST" })
}
