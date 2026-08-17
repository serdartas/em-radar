// SPDX-License-Identifier: Apache-2.0

import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Select } from "@/components/ui/select"
import {
  createSignalConfigGroup,
  deleteSignalConfigGroup,
  listSignalConfigGroups,
  updateSignalConfigGroup,
  type SignalConfigGroup,
} from "@/lib/signalConfigGroups"
import { listSignalDefinitions, type SignalDefinition } from "@/lib/signalDefinitions"

const GROUPS_KEY = ["signal-config-groups"]

export function SignalConfigGroupsPage() {
  const queryClient = useQueryClient()
  const groupsQuery = useQuery({ queryKey: GROUPS_KEY, queryFn: listSignalConfigGroups })
  const definitionsQuery = useQuery({
    queryKey: ["signal-definitions"],
    queryFn: listSignalDefinitions,
  })
  const [name, setName] = useState("")

  const createMutation = useMutation({
    mutationFn: createSignalConfigGroup,
    onSuccess: () => {
      setName("")
      void queryClient.invalidateQueries({ queryKey: GROUPS_KEY })
    },
  })

  if (groupsQuery.isLoading || definitionsQuery.isLoading) {
    return <p className="text-sm text-slate-500">Loading signal config groups...</p>
  }

  const groups = groupsQuery.data ?? []
  const definitions = definitionsQuery.data ?? []

  return (
    <section aria-labelledby="page-title" className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight" id="page-title">
          Signal Config Groups
        </h1>
        <p className="mt-2 max-w-2xl text-slate-600">
          Bundle signals into reusable groups. A signal can belong to several groups, and teams
          attach groups to choose what a report evaluates.
        </p>
      </header>

      <Card>
        <CardContent className="flex flex-wrap items-end gap-3 p-4">
          <div className="space-y-1.5">
            <Label htmlFor="group-name">New group name</Label>
            <input
              className="w-64 rounded-md border px-3 py-2 text-sm"
              id="group-name"
              onChange={(event) => setName(event.target.value)}
              value={name}
            />
          </div>
          <Button
            disabled={createMutation.isPending || name.trim().length === 0}
            onClick={() => createMutation.mutate({ name: name.trim() })}
          >
            {createMutation.isPending ? "Creating..." : "Create group"}
          </Button>
        </CardContent>
      </Card>

      <ul className="space-y-4">
        {groups.map((group) => (
          <li key={group.id}>
            <GroupCard definitions={definitions} group={group} key={group.updated_at} />
          </li>
        ))}
      </ul>
    </section>
  )
}

function GroupCard({
  group,
  definitions,
}: {
  group: SignalConfigGroup
  definitions: SignalDefinition[]
}) {
  const queryClient = useQueryClient()
  const [renameValue, setRenameValue] = useState(group.name)
  const [selectedSignal, setSelectedSignal] = useState("")

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: GROUPS_KEY })
  const updateMutation = useMutation({
    mutationFn: (signal_ids: string[]) => updateSignalConfigGroup(group.id, { signal_ids }),
    onSuccess: invalidate,
  })
  const renameMutation = useMutation({
    mutationFn: (newName: string) => updateSignalConfigGroup(group.id, { name: newName }),
    onSuccess: invalidate,
  })
  const deleteMutation = useMutation({
    mutationFn: () => deleteSignalConfigGroup(group.id),
    onSuccess: invalidate,
  })

  const definitionsById = new Map(definitions.map((definition) => [definition.id, definition]))
  const available = definitions.filter((definition) => !group.signal_ids.includes(definition.id))

  return (
    <Card>
      <CardContent className="space-y-4 p-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="space-y-1.5">
            <Label htmlFor={`rename-${group.id}`}>Group name</Label>
            <input
              className="w-64 rounded-md border px-3 py-2 text-sm"
              id={`rename-${group.id}`}
              onChange={(event) => setRenameValue(event.target.value)}
              value={renameValue}
            />
          </div>
          <div className="flex gap-2">
            <Button
              disabled={renameValue.trim().length === 0 || renameValue.trim() === group.name}
              onClick={() => renameMutation.mutate(renameValue.trim())}
              size="sm"
              variant="outline"
            >
              Rename
            </Button>
            <Button onClick={() => deleteMutation.mutate()} size="sm" variant="outline">
              Delete group
            </Button>
          </div>
        </div>

        <div>
          <h3 className="text-sm font-medium text-slate-700">Signals in this group</h3>
          {group.signal_ids.length === 0 ? (
            <p className="mt-1 text-sm text-slate-500">No signals yet.</p>
          ) : (
            <ul className="mt-2 space-y-2">
              {group.signal_ids.map((signalId) => (
                <li
                  className="flex items-center justify-between gap-3 rounded-md border px-3 py-2 text-sm"
                  key={signalId}
                >
                  <span>{definitionsById.get(signalId)?.name ?? signalId}</span>
                  <Button
                    aria-label={`Remove ${definitionsById.get(signalId)?.name ?? signalId}`}
                    onClick={() =>
                      updateMutation.mutate(group.signal_ids.filter((id) => id !== signalId))
                    }
                    size="sm"
                    variant="outline"
                  >
                    Remove
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="flex flex-wrap items-end gap-3">
          <div className="space-y-1.5">
            <Label htmlFor={`add-signal-${group.id}`}>Add a signal</Label>
            <Select
              id={`add-signal-${group.id}`}
              onChange={(event) => setSelectedSignal(event.target.value)}
              value={selectedSignal}
            >
              <option value="">Select a signal</option>
              {available.map((definition) => (
                <option key={definition.id} value={definition.id}>
                  {definition.name}
                </option>
              ))}
            </Select>
          </div>
          <Button
            disabled={selectedSignal === ""}
            onClick={() => {
              updateMutation.mutate([...group.signal_ids, selectedSignal])
              setSelectedSignal("")
            }}
            size="sm"
          >
            Add signal
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
