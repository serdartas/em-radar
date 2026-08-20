// SPDX-License-Identifier: Apache-2.0

import { useState } from "react"
import { useQueryClient } from "@tanstack/react-query"

import { Button } from "@/components/ui/button"
import { reportMarkdownQuery } from "@/lib/reports"

interface ReportExportActionsProps {
  reportId: string
}

function ReportExportActions({ reportId }: ReportExportActionsProps) {
  const queryClient = useQueryClient()
  const [status, setStatus] = useState<"copied" | "error" | "idle">("idle")
  const [busy, setBusy] = useState<"copy" | "download" | null>(null)

  async function handleDownload() {
    setBusy("download")
    setStatus("idle")
    try {
      const markdown = await queryClient.fetchQuery(reportMarkdownQuery(reportId))
      const url = URL.createObjectURL(new Blob([markdown], { type: "text/markdown" }))
      const anchor = document.createElement("a")
      anchor.href = url
      anchor.download = `report-${reportId}.md`
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      // Defer the revoke so the browser can claim the download stream before the
      // blob URL is invalidated (Firefox cancels the download otherwise).
      setTimeout(() => URL.revokeObjectURL(url), 0)
    } catch {
      setStatus("error")
    } finally {
      setBusy(null)
    }
  }

  async function handleCopy() {
    setBusy("copy")
    setStatus("idle")
    try {
      const markdown = await queryClient.fetchQuery(reportMarkdownQuery(reportId))
      await navigator.clipboard.writeText(markdown)
      setStatus("copied")
    } catch {
      setStatus("error")
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="flex flex-col items-start gap-2 sm:items-end">
      <div className="flex flex-wrap gap-2">
        <Button
          disabled={busy !== null}
          onClick={handleDownload}
          size="sm"
          title="Download this report as a Markdown file"
          variant="outline"
        >
          Download .md
        </Button>
        <Button
          disabled={busy !== null}
          onClick={handleCopy}
          size="sm"
          title="Copy the Markdown export to your clipboard"
          variant="outline"
        >
          Copy to clipboard
        </Button>
      </div>
      {status === "copied" && (
        <p aria-live="polite" className="text-xs text-slate-500">
          Copied to clipboard.
        </p>
      )}
      {status === "error" && (
        <p aria-live="polite" className="text-xs text-red-700" role="alert">
          The export could not be generated.
        </p>
      )}
    </div>
  )
}

export { ReportExportActions }
