// SPDX-License-Identifier: Apache-2.0

import { useState } from "react"
import type { ReactNode } from "react"
import { useMutation } from "@tanstack/react-query"

import { ConfirmDialog } from "@/components/ui/confirm-dialog"
import { ApiError } from "@/lib/api"
import { type ConnectionConflict, deleteConnection } from "@/lib/connections"

interface ConnectionDeleteConfirmProps {
  connectionId: string
  connectionName: string
  /** Called after a successful delete; use it to invalidate queries. */
  onDeleted: () => void
  onCancel: () => void
  className?: string
}

/**
 * Handles the two-phase connection-delete flow (initial confirm → 409 conflict → force
 * confirm) built on the shared ConfirmDialog primitive. Encapsulates the delete mutation
 * and conflict state so call sites only need to track whether the dialog is open.
 */
function ConnectionDeleteConfirm({
  className,
  connectionId,
  connectionName,
  onCancel,
  onDeleted,
}: ConnectionDeleteConfirmProps) {
  const [conflict, setConflict] = useState<ConnectionConflict | null>(null)

  const deleteMutation = useMutation({
    mutationFn: (force: boolean) => deleteConnection(connectionId, force),
    onSuccess: onDeleted,
    onError: (error: unknown) => {
      if (
        error instanceof ApiError &&
        error.status === 409 &&
        typeof error.detail === "object" &&
        error.detail !== null &&
        "dependent_teams" in error.detail
      ) {
        setConflict(error.detail as ConnectionConflict)
      }
    },
  })

  const isForce = conflict !== null
  const confirmLabel = isForce ? "Confirm force delete" : "Confirm delete"

  const onConfirm = () => deleteMutation.mutate(isForce)

  let body: ReactNode
  if (conflict) {
    body = (
      <>
        {conflict.dependent_teams.length > 0 ? (
          <>
            <p className="font-medium">This connection is used by the following teams:</p>
            <ul className="mt-1 list-disc pl-4">
              {conflict.dependent_teams.map((t) => (
                <li key={t.id}>{t.name}</li>
              ))}
            </ul>
          </>
        ) : (
          <p className="font-medium">
            This connection has scope definitions that will be removed.
          </p>
        )}
        <p className="mt-2">
          Proceeding will remove the connection, its cached data, and all references to it.
          This cannot be undone.
        </p>
      </>
    )
  } else {
    body = (
      <p>
        This removes the connection and all cached source data for it. This cannot be undone.
      </p>
    )
  }

  return (
    <ConfirmDialog
      body={body}
      className={className}
      confirmLabel={confirmLabel}
      onCancel={onCancel}
      onConfirm={onConfirm}
      pending={deleteMutation.isPending}
      title={`Delete connection ${connectionName}`}
    />
  )
}

export { ConnectionDeleteConfirm }
