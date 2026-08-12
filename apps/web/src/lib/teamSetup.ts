import { useQuery } from "@tanstack/react-query"

import { getConnectors, type Connector } from "@/lib/connectors"
import { listConnections, type SourceConnection } from "@/lib/connections"
import { listScopes } from "@/lib/scopes"
import { listSignalConfigGroups } from "@/lib/signalConfigGroups"
import { listTeams } from "@/lib/teams"

export const TEAMS_KEY = ["teams"]

export function useTeamSetupData() {
  const teamsQuery = useQuery({ queryKey: TEAMS_KEY, queryFn: listTeams })
  const scopesQuery = useQuery({ queryKey: ["scopes"], queryFn: listScopes })
  const groupsQuery = useQuery({
    queryKey: ["signal-config-groups"],
    queryFn: listSignalConfigGroups,
  })
  const connectorsQuery = useQuery({ queryKey: ["connectors"], queryFn: getConnectors })
  const connectionsQuery = useQuery({ queryKey: ["connections"], queryFn: listConnections })

  const teams = teamsQuery.data ?? []
  const boardScopes = (scopesQuery.data ?? []).filter((scope) => scope.scope_type === "board")
  const groups = groupsQuery.data ?? []
  const connections = connectionsQuery.data ?? []
  const connectors = connectorsQuery.data ?? []

  const jiraConnections = connections.filter((conn) => conn.connector_name === "jira")
  const mrCapableConnectorNames = new Set(
    connectors
      .filter((c: Connector) => c.capabilities.provides_mergerequests)
      .map((c: Connector) => c.name),
  )
  const codeConnections = connections.filter((conn: SourceConnection) =>
    mrCapableConnectorNames.has(conn.connector_name),
  )

  return {
    isLoading:
      teamsQuery.isLoading ||
      scopesQuery.isLoading ||
      groupsQuery.isLoading ||
      connectorsQuery.isLoading ||
      connectionsQuery.isLoading,
    teams,
    boardScopes,
    groups,
    connections,
    connectors,
    jiraConnections,
    codeConnections,
  }
}
