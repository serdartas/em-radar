import type { ConnectionErrorCode } from "@/lib/connections"

export interface ConnectionErrorGuidance {
  explanation: string
  suggestions: string[]
}

const GUIDANCE: Record<ConnectionErrorCode, ConnectionErrorGuidance> = {
  auth: {
    explanation: "The credentials were rejected by the source.",
    suggestions: [
      "Check the token is correct and has not expired or been revoked.",
      "For Jira Cloud, confirm the account email matches the API token.",
      "Make sure the account can browse the projects and boards you report on.",
    ],
  },
  not_found: {
    explanation: "The source responded but the requested endpoint was not found.",
    suggestions: [
      "Verify the Base URL points to your instance root (no trailing API path).",
      "For Jira Cloud the URL usually ends in .atlassian.net.",
    ],
  },
  rate_limited: {
    explanation: "The source is rate limiting requests right now.",
    suggestions: ["Wait a minute and test again.", "Avoid running several tests in quick succession."],
  },
  transient: {
    explanation: "EM Radar could not reach the source.",
    suggestions: [
      "Check the Base URL and your network connection.",
      "If the instance uses a private or self-signed certificate, review the TLS verification setting.",
      "Try again — the source may be temporarily unavailable.",
    ],
  },
  config: {
    explanation: "The connection settings are incomplete or invalid.",
    suggestions: [
      "Review the required fields above for typos or missing values.",
      "Confirm the Base URL is a full URL including https://.",
    ],
  },
  data: {
    explanation: "The source returned an unexpected response.",
    suggestions: ["Confirm the Base URL points to a supported source.", "Try again, then check the source status."],
  },
  unknown: {
    explanation: "The connection test failed.",
    suggestions: ["Review the connection settings and try again."],
  },
}

export function connectionErrorGuidance(
  code: ConnectionErrorCode | null | undefined,
  detail: string,
): ConnectionErrorGuidance {
  if (code && code in GUIDANCE) {
    return GUIDANCE[code]
  }
  return { explanation: detail, suggestions: [] }
}
