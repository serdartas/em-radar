import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Link, useNavigate } from "react-router-dom"

import { Button } from "@/components/ui/button"
import { apiErrorMessage } from "@/lib/api"
import { runDemoReport } from "@/lib/reports"

export function ReportRunnerPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const run = useMutation({
    mutationFn: runDemoReport,
    onSuccess: (report) => {
      void queryClient.invalidateQueries({ queryKey: ["reports"], exact: true })
      navigate(`/reports/results/${report.id}`)
    },
  })

  return (
    <section aria-labelledby="page-title">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight" id="page-title">
            Report Runner
          </h1>
          <p className="mt-2 max-w-xl text-slate-600">
            Run the deterministic demo report. The result is stored and opens automatically.
          </p>
        </div>
        <Button disabled={run.isPending} onClick={() => run.mutate()} size="lg">
          {run.isPending ? "Running demo report…" : "Run demo report"}
        </Button>
      </header>

      <div aria-live="polite" className="mt-8 space-y-4">
        {run.isPending && (
          <p className="rounded-lg border p-8 text-center text-slate-500">
            Evaluating demo data and saving the report…
          </p>
        )}
        {run.isError && (
          <p className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-700" role="alert">
            {apiErrorMessage(run.error, "The report run failed. Please try again.")}
          </p>
        )}
        {run.isIdle && (
          <p className="rounded-lg border border-dashed p-8 text-center text-slate-500">
            No report has been run yet.{" "}
            <Link className="font-medium text-blue-700 underline-offset-4 hover:underline" to="/reports/results">
              Browse past reports
            </Link>
            .
          </p>
        )}
      </div>
    </section>
  )
}
