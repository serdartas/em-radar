import { Badge } from "@/components/ui/badge"
import { connectionErrorGuidance } from "@/lib/connectionErrors"
import { connectionErrorMessage, type ConnectionTestResult } from "@/lib/connections"

interface TestResultProps {
  error: unknown
  result: ConnectionTestResult | undefined
}

export function TestResult({ error, result }: TestResultProps) {
  if (error) {
    return (
      <p
        className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700"
        role="alert"
      >
        {connectionErrorMessage(error)}
      </p>
    )
  }
  if (!result) {
    return null
  }
  if (!result.ok) {
    const guidance = connectionErrorGuidance(result.code, result.detail)
    return (
      <div
        className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700"
        role="alert"
      >
        <p className="font-medium">{guidance.explanation}</p>
        {guidance.suggestions.length > 0 && (
          <ul className="mt-1.5 list-disc space-y-0.5 pl-5">
            {guidance.suggestions.map((suggestion) => (
              <li key={suggestion}>{suggestion}</li>
            ))}
          </ul>
        )}
      </div>
    )
  }
  return (
    <div
      className="rounded-md border border-green-200 bg-green-50 p-3 text-sm text-green-800"
      role="status"
    >
      <p>Connected as {result.user_display_name ?? "the configured user"}.</p>
      {result.permissions.length > 0 && (
        <p className="mt-1 flex flex-wrap items-center gap-1">
          <span>Permissions:</span>
          {result.permissions.map((permission) => (
            <Badge key={permission} variant="info">
              {permission}
            </Badge>
          ))}
        </p>
      )}
    </div>
  )
}
