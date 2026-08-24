// SPDX-License-Identifier: Apache-2.0

import { useState } from "react"
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link } from "react-router-dom"

import { SignalForm } from "@/components/signals/SignalForm"
import { SignalListItem } from "@/components/signals/SignalListItem"
import { Button } from "@/components/ui/button"
import { apiErrorMessage } from "@/lib/api"
import { getConnectors, type SignalField } from "@/lib/connectors"
import { type JiraFieldInfo, listConnections, listJiraFields } from "@/lib/connections"
import {
  createSignalDefinition,
  deleteSignalDefinition,
  listSignalDefinitions,
  updateSignalDefinition,
  type SignalDefinition,
  type SignalDefinitionCreate,
} from "@/lib/signalDefinitions"

export function SignalSettingsPage() {
  const queryClient = useQueryClient()
  const definitionsQuery = useQuery({
    queryKey: ["signal-definitions"],
    queryFn: listSignalDefinitions,
  })
  const connectorsQuery = useQuery({ queryKey: ["connectors"], queryFn: getConnectors })
  const connectionsQuery = useQuery({ queryKey: ["connections"], queryFn: listConnections })
  const [creating, setCreating] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)

  // Discover custom fields from EVERY Jira connection: a workspace may hold several Jira
  // instances, and a signal built for a team backed by any of them must be able to pick
  // that instance's fields. Restricting discovery to one connection would hide the rest.
  const jiraConnectionIds = (connectionsQuery.data ?? [])
    .filter((c) => c.connector_name === "jira")
    .map((c) => c.id)
  const jiraFieldQueries = useQueries({
    queries: jiraConnectionIds.map((id) => ({
      queryKey: ["jiraFields", id],
      queryFn: () => listJiraFields(id),
    })),
  })

  // Merge and de-duplicate custom fields by id (the same field id can exist across
  // instances; keep the first occurrence).
  const jiraCustomFields: JiraFieldInfo[] = (() => {
    const byId = new Map<string, JiraFieldInfo>()
    for (const query of jiraFieldQueries) {
      for (const field of query.data ?? []) {
        if (field.custom && !byId.has(field.id)) {
          byId.set(field.id, field)
        }
      }
    }
    return [...byId.values()]
  })()

  const jiraFieldsError = jiraConnectionIds.length > 0 && jiraFieldQueries.some((q) => q.isError)

  // Build fieldsByEntityType from all registered connector schemas.
  // issue fields come from Jira; merge_request fields come from GitLab.
  // Fields with a declared entity_type are restricted to that entity; fields
  // without one (entity_type: null) are available to all entity types.
  const fieldsByEntityType: Record<string, SignalField[]> =
    connectorsQuery.data?.reduce(
      (acc, connector) => {
        for (const entityType of connector.signal_schema?.entity_types ?? []) {
          if (!acc[entityType]) {
            acc[entityType] = (connector.signal_schema?.fields ?? []).filter(
              (f) => f.entity_type == null || f.entity_type === entityType,
            )
          }
        }
        return acc
      },
      {} as Record<string, SignalField[]>,
    ) ?? {}

  const createMutation = useMutation({
    mutationFn: createSignalDefinition,
    onSuccess: () => {
      setCreating(false)
      void queryClient.invalidateQueries({ queryKey: ["signal-definitions"] })
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, definition }: { id: string; definition: Partial<SignalDefinitionCreate> }) =>
      updateSignalDefinition(id, definition),
    onSuccess: () => {
      setEditingId(null)
      void queryClient.invalidateQueries({ queryKey: ["signal-definitions"] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: deleteSignalDefinition,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["signal-definitions"] }),
    // Failure is surfaced next to the affected list item via deleteMutation.isError below.
    onError: () => {},
  })

  // Block render until Jira custom fields are available so the edit form never opens
  // with an unresolved field picker (custom-field ids would degrade to empty dropdowns).
  const jiraFieldsLoading = jiraFieldQueries.some((q) => q.isLoading)

  if (
    definitionsQuery.isLoading ||
    connectorsQuery.isLoading ||
    connectionsQuery.isLoading ||
    jiraFieldsLoading
  ) {
    return <p className="text-sm text-slate-500">Loading signals...</p>
  }

  if (Object.keys(fieldsByEntityType).length === 0) {
    return <p className="text-sm text-red-700">Signals could not be loaded.</p>
  }

  // A discovery failure must not masquerade as "no custom fields": that would silently
  // hide the custom-field option and block both creating and editing custom-field signals.
  // Surface it with a retry instead.
  if (jiraFieldsError) {
    return (
      <div className="space-y-3" role="alert">
        <p className="text-sm text-red-700">
          Jira custom fields could not be loaded, so custom-field signals cannot be configured
          right now. Check the affected Jira connection and try again.
        </p>
        <Button
          onClick={() => {
            for (const query of jiraFieldQueries) {
              void query.refetch()
            }
          }}
          variant="outline"
        >
          Retry
        </Button>
      </div>
    )
  }

  const definitions = definitionsQuery.data ?? []
  const editingDefinition: SignalDefinition | undefined = editingId
    ? definitions.find((d) => d.id === editingId)
    : undefined

  const showingForm = creating || !!editingDefinition

  return (
    <section aria-labelledby="page-title" className="space-y-6">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight" id="page-title">
            Signal Settings
          </h1>
          <p className="mt-2 max-w-2xl text-slate-600">
            Build custom signals from your own rules, then bundle them into groups to attach to
            teams.
          </p>
        </div>
        <div className="flex gap-2">
          <Button asChild variant="outline">
            <Link to="/signals/groups">Signal config groups</Link>
          </Button>
          <Button asChild variant="outline">
            <Link to="/signals/import-export">Import / export pack</Link>
          </Button>
          {!showingForm && (
            <Button
              onClick={() => {
                createMutation.reset()
                setCreating(true)
              }}
            >
              Create new
            </Button>
          )}
        </div>
      </header>

      {creating ? (
        <SignalForm
          key="create"
          errorMessage={
            createMutation.isError
              ? apiErrorMessage(createMutation.error, "Could not save the signal.")
              : null
          }
          fieldsByEntityType={fieldsByEntityType}
          jiraCustomFields={jiraCustomFields}
          mode="create"
          onCancel={() => setCreating(false)}
          onSave={(definition) => createMutation.mutate(definition)}
          pending={createMutation.isPending}
        />
      ) : editingDefinition ? (
        <SignalForm
          key={editingDefinition.id}
          errorMessage={
            updateMutation.isError
              ? apiErrorMessage(updateMutation.error, "Could not save the signal.")
              : null
          }
          fieldsByEntityType={fieldsByEntityType}
          initialValue={editingDefinition}
          jiraCustomFields={jiraCustomFields}
          mode="edit"
          onCancel={() => {
            setEditingId(null)
            updateMutation.reset()
          }}
          onSave={(definition) =>
            updateMutation.mutate({ id: editingDefinition.id, definition })
          }
          pending={updateMutation.isPending}
        />
      ) : (
        <SignalList
          definitions={definitions}
          deleteMutation={deleteMutation}
          onEdit={(id) => {
            updateMutation.reset()
            setEditingId(id)
          }}
        />
      )}
    </section>
  )
}

interface SignalListProps {
  definitions: SignalDefinition[]
  deleteMutation: ReturnType<typeof useMutation<void, Error, string>>
  onEdit: (id: string) => void
}

function SignalList({ definitions, deleteMutation, onEdit }: SignalListProps) {
  if (definitions.length === 0) {
    return (
      <p className="text-sm text-slate-500">
        No signals yet. Use "Create new" to build your first signal.
      </p>
    )
  }

  return (
    <section aria-labelledby="signals-title" className="space-y-3">
      <h2 className="text-lg font-semibold" id="signals-title">
        Signals
      </h2>
      <ul className="space-y-3">
        {definitions.map((definition) => (
          <li key={definition.id}>
            <SignalListItem
              definition={definition}
              deleteError={
                deleteMutation.isError && deleteMutation.variables === definition.id
                  ? apiErrorMessage(deleteMutation.error, "Could not delete the signal.")
                  : null
              }
              deletePending={deleteMutation.isPending && deleteMutation.variables === definition.id}
              onDelete={(id) => deleteMutation.mutate(id)}
              onEdit={onEdit}
            />
          </li>
        ))}
      </ul>
    </section>
  )
}
