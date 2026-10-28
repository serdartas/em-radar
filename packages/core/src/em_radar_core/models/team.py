# SPDX-License-Identifier: Apache-2.0

from datetime import datetime
from uuid import UUID

from sqlmodel import SQLModel

from em_radar_core.models.enums import ScopeVerificationStatus


class TeamGitLabMember(SQLModel):
    """A code-provider user explicitly added to a team's member roster.

    Keyed by the opaque, stable `provider_user_id` string assigned by the connector
    (e.g. "123" for GitLab, "MDQ6VXNl..." for GitHub). Rows are preserved even when
    the anchoring connection becomes unavailable; `verification_status` is set to
    UNAVAILABLE in that case so report scoping can skip stale entries without data loss.
    """

    team_profile_id: UUID
    connection_id: UUID | None = None
    provider_user_id: str
    username: str
    display_name: str | None = None
    verification_status: ScopeVerificationStatus = ScopeVerificationStatus.VERIFIED
    created_at: datetime
    updated_at: datetime


class TeamGitLabRepository(SQLModel):
    """A code-provider project explicitly added to a team's repository roster.

    Keyed by the opaque, stable `provider_project_id` string assigned by the connector.
    Preservation semantics mirror TeamGitLabMember: rows survive connection removal
    and are flagged via `verification_status`.
    """

    team_profile_id: UUID
    connection_id: UUID | None = None
    provider_project_id: str
    name: str
    path_with_namespace: str
    verification_status: ScopeVerificationStatus = ScopeVerificationStatus.VERIFIED
    created_at: datetime
    updated_at: datetime
