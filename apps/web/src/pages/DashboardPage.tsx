import { useEffect } from "react"
import { useQuery } from "@tanstack/react-query"
import { useNavigate } from "react-router-dom"

import { PagePlaceholder } from "@/components/PagePlaceholder"
import { listTeams } from "@/lib/teams"

export function DashboardPage() {
  const navigate = useNavigate()
  const teamsQuery = useQuery({ queryKey: ["teams"], queryFn: listTeams })

  // First-run entry: with no team yet, send the user into the onboarding wizard.
  useEffect(() => {
    if (teamsQuery.isSuccess && teamsQuery.data.length === 0) {
      navigate("/setup", { replace: true })
    }
  }, [teamsQuery.isSuccess, teamsQuery.data, navigate])

  return (
    <PagePlaceholder
      description="The latest report for each team will appear here once setup is complete."
      title="Dashboard"
    />
  )
}
