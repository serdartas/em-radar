# SPDX-License-Identifier: Apache-2.0

from datetime import datetime
from uuid import UUID

from sqlmodel import SQLModel

from em_radar_core.models.enums import ScopeVerificationStatus


class TeamGitLabMember(SQLModel):
    """A GitLab user explicitly added to a team's member roster.

    Keyed by stable GitLab numeric user id. Rows are preserved even when the
    anchoring connection becomes unavailable; `verification_status` is set to
    UNAVAILABLE in that case so report scoping can skip stale entries without data loss.
    """

    team_profile_id: UUID
    connection_id: UUID | None = None
    gitlab_user_id: int
    username: str
    display_name: str | None = None
    verification_status: ScopeVerificationStatus = ScopeVerificationStatus.VERIFIED
    created_at: datetime
    updated_at: datetime


class TeamGitLabRepository(SQLModel):
    """A GitLab project explicitly added to a team's repository roster.

    Keyed by stable GitLab numeric project id. Preservation semantics mirror
    TeamGitLabMember: rows survive connection removal and are flagged via
    `verification_status`.
    """

    team_profile_id: UUID
    connection_id: UUID | None = None
    gitlab_project_id: int
    name: str
    path_with_namespace: str
    verification_status: ScopeVerificationStatus = ScopeVerificationStatus.VERIFIED
    created_at: datetime
    updated_at: datetime
