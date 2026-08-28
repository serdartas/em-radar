// SPDX-License-Identifier: Apache-2.0

import type { SourceConnection } from "@/lib/connections"
import type { TeamProfile } from "@/lib/teams"

export interface TeamGitLabConfigProps {
  team: TeamProfile
  /** Full list of MR-capable connections (already filtered by teamSetup.ts). */
  codeConnections: SourceConnection[]
}

/**
 * Optional GitLab configuration area inside the team edit card.
 *
 * Renders two skippable sections ("GitLab members", "GitLab repositories") only when the
 * team already has a code_connection_id that resolves to one of the supplied codeConnections.
 * Returns null otherwise so the caller renders nothing.
 *
 * Component boundary for follow-up tickets:
 *   M9-08: replace the placeholder inside the "GitLab members" section with a real picker,
 *          passing { team, codeConnection }.
 *   M9-09: replace the placeholder inside the "GitLab repositories" section with a real picker,
 *          passing { team, codeConnection }.
 */
export function TeamGitLabConfig({ codeConnections, team }: TeamGitLabConfigProps) {
  // Only a GitLab connection gets these sections: the member/repository endpoints and pickers
  // are GitLab-specific, so a non-GitLab MR-capable source (e.g. demo, or a future GitHub
  // connector) must not render them. A provider-agnostic version is M9-17.
  const codeConnection =
    codeConnections.find(
      (c) => c.id === team.code_connection_id && c.connector_name === "gitlab",
    ) ?? null

  if (!codeConnection) {
    return null
  }

  const membersHeadingId = `gitlab-members-heading-${team.id}`
  const reposHeadingId = `gitlab-repositories-heading-${team.id}`

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <h3 className="text-sm font-medium text-slate-700">GitLab configuration</h3>
        <span className="text-xs text-slate-400">(optional)</span>
      </div>
      <p className="text-sm text-slate-500">
        Both sections below are optional. You can save the team without configuring GitLab and
        return to set them up later.
      </p>

      {/* GitLab members section — M9-08 mounts its picker here. */}
      <section aria-labelledby={membersHeadingId} className="space-y-2 rounded-md border p-4">
        <h4 className="text-sm font-medium text-slate-700" id={membersHeadingId}>
          GitLab members
        </h4>
        <p className="text-sm text-slate-500">
          Select the GitLab users who belong to this team. Used to scope merge-request activity by
          author.
        </p>
        {/* M9-08: replace this paragraph with <TeamGitLabMembersPicker team={team} codeConnection={codeConnection} /> */}
        <p className="text-sm text-slate-400">
          GitLab member selection is coming soon. Save without selecting members and configure this
          later.
        </p>
      </section>

      {/* GitLab repositories section — M9-09 mounts its picker here. */}
      <section aria-labelledby={reposHeadingId} className="space-y-2 rounded-md border p-4">
        <h4 className="text-sm font-medium text-slate-700" id={reposHeadingId}>
          GitLab repositories
        </h4>
        <p className="text-sm text-slate-500">
          Select the repositories owned by this team. Used to scope merge-request activity by
          project.
        </p>
        {/* M9-09: replace this paragraph with <TeamGitLabRepositoriesPicker team={team} codeConnection={codeConnection} /> */}
        <p className="text-sm text-slate-400">
          GitLab repository selection is coming soon. Save without selecting repositories and
          configure this later.
        </p>
      </section>
    </div>
  )
}
