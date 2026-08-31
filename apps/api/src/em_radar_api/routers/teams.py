# SPDX-License-Identifier: Apache-2.0

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select
from starlette.responses import Response

from em_radar_api.connector_registry import create_connector
from em_radar_api.db import get_session, get_write_session, write_lock_acquired
from em_radar_api.repositories.source_connections import instantiate_connector
from em_radar_api.repositories.team_profiles import (
    InvalidTeamProfile,
    TeamProfileInUse,
    create_team_profile,
    delete_team_profile,
    get_team_profile,
    list_team_gitlab_members,
    list_team_gitlab_repositories,
    list_team_profiles,
    update_team_profile,
)
from em_radar_api.tables import (
    TeamGitLabMemberTable,
    TeamGitLabRepositoryTable,
    TeamProfileTable,
)
from em_radar_api.team_profiles import (
    GitLabMemberInput,
    GitLabRepositoryInput,
    MemberSearchResult,
    ProjectSearchResult,
    RepositoryActivityResult,
    RepositorySuggestionsResponse,
    TeamGitLabMemberRead,
    TeamGitLabRepositoryRead,
    TeamProfileCreate,
    TeamProfileRead,
    TeamProfileUpdate,
)
from em_radar_core.connectors import (
    ConnectorAuthError,
    ConnectorBase,
    ConnectorConfigError,
    ConnectorError,
    MemberProvider,
    RepositoryActivity,
    RepositoryActivityProvider,
    RepositorySearchProvider,
)
from em_radar_core.models import ScopeVerificationStatus

try:
    from em_radar_connector_gitlab import (
        DISCOVERY_DEFAULT_WINDOW_DAYS,
        DISCOVERY_MIN_CANDIDATES,
        DISCOVERY_WIDE_WINDOW_DAYS,
    )
except ImportError:
    DISCOVERY_DEFAULT_WINDOW_DAYS = 90
    DISCOVERY_WIDE_WINDOW_DAYS = 180
    DISCOVERY_MIN_CANDIDATES = 3

_MEMBER_SEARCH_DEFAULT_LIMIT = 20
_MEMBER_SEARCH_MAX_LIMIT = 50
_PROJECT_SEARCH_DEFAULT_LIMIT = 20
_PROJECT_SEARCH_MAX_LIMIT = 50
_SUGGESTION_DEFAULT_LIMIT = 20
_SUGGESTION_MAX_LIMIT = 50

router = APIRouter()


@router.get("/teams", response_model=list[TeamProfileRead])
def list_teams(session: Session = Depends(get_session)) -> list[TeamProfileRead]:
    return list_team_profiles(session)


@router.post("/teams", response_model=TeamProfileRead, status_code=status.HTTP_201_CREATED)
def create_team(
    team: TeamProfileCreate,
    session: Session = Depends(get_write_session),
) -> TeamProfileRead:
    try:
        return create_team_profile(session, team)
    except InvalidTeamProfile as error:
        raise _invalid_team(error) from error


@router.get("/teams/{team_id}", response_model=TeamProfileRead)
def get_team(team_id: UUID, session: Session = Depends(get_session)) -> TeamProfileRead:
    team = get_team_profile(session, team_id)
    if team is None:
        raise _team_not_found()
    return team


@router.patch("/teams/{team_id}", response_model=TeamProfileRead)
def patch_team(
    team_id: UUID,
    update: TeamProfileUpdate,
    session: Session = Depends(get_write_session),
) -> TeamProfileRead:
    try:
        team = update_team_profile(session, team_id, update)
    except InvalidTeamProfile as error:
        raise _invalid_team(error) from error
    if team is None:
        raise _team_not_found()
    return team


@router.delete("/teams/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_team(team_id: UUID, session: Session = Depends(get_write_session)) -> Response:
    try:
        if not delete_team_profile(session, team_id):
            raise _team_not_found()
    except TeamProfileInUse as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# GitLab members
# ---------------------------------------------------------------------------


@router.get(
    "/teams/{team_id}/gitlab/members",
    response_model=list[TeamGitLabMemberRead],
)
def list_gitlab_members(
    team_id: UUID,
    session: Session = Depends(get_session),
) -> list[TeamGitLabMemberRead]:
    team_row = session.get(TeamProfileTable, team_id)
    if team_row is None:
        raise _team_not_found()
    rows = list_team_gitlab_members(session, team_id)
    return [TeamGitLabMemberRead.model_validate(row) for row in rows]


@router.put(
    "/teams/{team_id}/gitlab/members",
    response_model=list[TeamGitLabMemberRead],
)
async def replace_gitlab_members(
    team_id: UUID,
    body: list[GitLabMemberInput],
    session: Session = Depends(get_session),
) -> list[TeamGitLabMemberRead]:
    team_row = session.get(TeamProfileTable, team_id)
    if team_row is None:
        raise _team_not_found()
    connector = _require_gitlab_connector(session, team_row)
    try:
        if not isinstance(connector, MemberProvider):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="GitLab connector does not support member lookup",
            )
        resolved: list[tuple[int, str, str | None]] = []
        for item in body:
            try:
                ref = await connector.get_user(str(item.gitlab_user_id))
            except ConnectorAuthError as error:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)
                ) from error
            except ConnectorError as error:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)
                ) from error
            if ref is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=f"GitLab user id {item.gitlab_user_id} not found",
                )
            resolved.append((item.gitlab_user_id, ref.username, ref.display_name))
        # De-duplicate by stable id (keep first occurrence) so a repeated id in the request
        # cannot violate the (team, gitlab_user_id) unique constraint.
        deduped: dict[int, tuple[int, str, str | None]] = {}
        for entry in resolved:
            deduped.setdefault(entry[0], entry)
        now = datetime.now(UTC)
        with write_lock_acquired():
            for existing in session.exec(
                select(TeamGitLabMemberTable).where(
                    TeamGitLabMemberTable.team_profile_id == team_id
                )
            ).all():
                session.delete(existing)
            # Flush the deletes before inserting so re-saving an id that is still in the old
            # set does not collide with the not-yet-flushed delete under the unique constraint.
            session.flush()
            result_rows: list[TeamGitLabMemberTable] = []
            for gitlab_user_id, username, display_name in deduped.values():
                row = TeamGitLabMemberTable(
                    team_profile_id=team_id,
                    connection_id=team_row.code_connection_id,
                    gitlab_user_id=gitlab_user_id,
                    username=username,
                    display_name=display_name,
                    verification_status=ScopeVerificationStatus.VERIFIED,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
                result_rows.append(row)
            session.commit()
            for row in result_rows:
                session.refresh(row)
        return [TeamGitLabMemberRead.model_validate(row) for row in result_rows]
    finally:
        await connector.close()


# ---------------------------------------------------------------------------
# GitLab repositories
# ---------------------------------------------------------------------------


@router.get(
    "/teams/{team_id}/gitlab/repositories",
    response_model=list[TeamGitLabRepositoryRead],
)
def list_gitlab_repositories(
    team_id: UUID,
    session: Session = Depends(get_session),
) -> list[TeamGitLabRepositoryRead]:
    team_row = session.get(TeamProfileTable, team_id)
    if team_row is None:
        raise _team_not_found()
    rows = list_team_gitlab_repositories(session, team_id)
    return [TeamGitLabRepositoryRead.model_validate(row) for row in rows]


@router.put(
    "/teams/{team_id}/gitlab/repositories",
    response_model=list[TeamGitLabRepositoryRead],
)
async def replace_gitlab_repositories(
    team_id: UUID,
    body: list[GitLabRepositoryInput],
    session: Session = Depends(get_session),
) -> list[TeamGitLabRepositoryRead]:
    team_row = session.get(TeamProfileTable, team_id)
    if team_row is None:
        raise _team_not_found()
    connector = _require_gitlab_connector(session, team_row)
    try:
        if not isinstance(connector, RepositorySearchProvider):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="GitLab connector does not support project lookup",
            )
        resolved: list[tuple[int, str, str]] = []
        for item in body:
            try:
                ref = await connector.get_project(str(item.gitlab_project_id))
            except ConnectorAuthError as error:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)
                ) from error
            except ConnectorError as error:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)
                ) from error
            if ref is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=f"GitLab project id {item.gitlab_project_id} not found",
                )
            resolved.append((item.gitlab_project_id, ref.name, ref.path_with_namespace))
        # De-duplicate by stable id (keep first occurrence) so a repeated id in the request
        # cannot violate the (team, gitlab_project_id) unique constraint.
        deduped: dict[int, tuple[int, str, str]] = {}
        for entry in resolved:
            deduped.setdefault(entry[0], entry)
        now = datetime.now(UTC)
        with write_lock_acquired():
            for existing in session.exec(
                select(TeamGitLabRepositoryTable).where(
                    TeamGitLabRepositoryTable.team_profile_id == team_id
                )
            ).all():
                session.delete(existing)
            # Flush the deletes before inserting so re-saving an id that is still in the old
            # set does not collide with the not-yet-flushed delete under the unique constraint.
            session.flush()
            result_rows: list[TeamGitLabRepositoryTable] = []
            for gitlab_project_id, name, path_with_namespace in deduped.values():
                row = TeamGitLabRepositoryTable(
                    team_profile_id=team_id,
                    connection_id=team_row.code_connection_id,
                    gitlab_project_id=gitlab_project_id,
                    name=name,
                    path_with_namespace=path_with_namespace,
                    verification_status=ScopeVerificationStatus.VERIFIED,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
                result_rows.append(row)
            session.commit()
            for row in result_rows:
                session.refresh(row)
        return [TeamGitLabRepositoryRead.model_validate(row) for row in result_rows]
    finally:
        await connector.close()


# ---------------------------------------------------------------------------
# GitLab member search
# ---------------------------------------------------------------------------


@router.get(
    "/teams/{team_id}/gitlab/member-search",
    response_model=list[MemberSearchResult],
)
async def gitlab_member_search(
    team_id: UUID,
    q: str = Query(default=""),
    limit: int = Query(default=_MEMBER_SEARCH_DEFAULT_LIMIT, ge=1),
    page: int = Query(1, ge=1),
    session: Session = Depends(get_session),
) -> list[MemberSearchResult]:
    team_row = session.get(TeamProfileTable, team_id)
    if team_row is None:
        raise _team_not_found()
    connector = _require_gitlab_connector(session, team_row)
    try:
        if not isinstance(connector, MemberProvider):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="GitLab connector does not support member search",
            )
        capped = min(limit, _MEMBER_SEARCH_MAX_LIMIT)
        try:
            refs = await connector.search_users(q, limit=capped, page=page)
        except ConnectorAuthError as error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)
            ) from error
        except ConnectorError as error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)
            ) from error
        return [
            MemberSearchResult(
                provider_user_id=ref.provider_user_id,
                username=ref.username,
                display_name=ref.display_name,
                avatar_url=ref.avatar_url,
            )
            for ref in refs
        ]
    finally:
        await connector.close()


# ---------------------------------------------------------------------------
# GitLab project search
# ---------------------------------------------------------------------------


@router.get(
    "/teams/{team_id}/gitlab/project-search",
    response_model=list[ProjectSearchResult],
)
async def gitlab_project_search(
    team_id: UUID,
    q: str = Query(default=""),
    limit: int = Query(default=_PROJECT_SEARCH_DEFAULT_LIMIT, ge=1),
    page: int = Query(1, ge=1),
    session: Session = Depends(get_session),
) -> list[ProjectSearchResult]:
    team_row = session.get(TeamProfileTable, team_id)
    if team_row is None:
        raise _team_not_found()
    connector = _require_gitlab_connector(session, team_row)
    try:
        if not isinstance(connector, RepositorySearchProvider):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="GitLab connector does not support project search",
            )
        capped = min(limit, _PROJECT_SEARCH_MAX_LIMIT)
        try:
            refs = await connector.search_projects(q, limit=capped, page=page)
        except ConnectorAuthError as error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)
            ) from error
        except ConnectorError as error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)
            ) from error
        return [
            ProjectSearchResult(
                provider_project_id=ref.provider_project_id,
                name=ref.name,
                path_with_namespace=ref.path_with_namespace,
            )
            for ref in refs
        ]
    finally:
        await connector.close()


# ---------------------------------------------------------------------------
# Repository suggestions (activity-based discovery)
# ---------------------------------------------------------------------------


@router.get(
    "/teams/{team_id}/gitlab/repository-suggestions",
    response_model=RepositorySuggestionsResponse,
)
async def gitlab_repository_suggestions(
    team_id: UUID,
    limit: int = Query(default=_SUGGESTION_DEFAULT_LIMIT, ge=1),
    session: Session = Depends(get_session),
) -> RepositorySuggestionsResponse:
    team_row = session.get(TeamProfileTable, team_id)
    if team_row is None:
        raise _team_not_found()
    # Validate the connection exists before checking members so callers get a clear error
    # when the connection is missing, regardless of whether any members are saved.
    if team_row.code_connection_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="team has no GitLab connection configured",
        )
    all_members = list_team_gitlab_members(session, team_id)
    saved_members = [
        m
        for m in all_members
        if m.connection_id == team_row.code_connection_id
        and m.verification_status == ScopeVerificationStatus.VERIFIED
    ]
    if not saved_members:
        return RepositorySuggestionsResponse(
            window_days=DISCOVERY_DEFAULT_WINDOW_DAYS, repositories=[]
        )
    connector = _require_gitlab_connector(session, team_row)
    try:
        if not isinstance(connector, RepositoryActivityProvider):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="GitLab connector does not support repository discovery",
            )
        capped = min(limit, _SUGGESTION_MAX_LIMIT)
        # Fetch at least the widening threshold so a small caller limit cannot force a needless
        # widen (the connector caps its output at the requested limit); slice to `capped` after.
        discover_limit = max(capped, DISCOVERY_MIN_CANDIDATES)
        member_ids = [str(m.gitlab_user_id) for m in saved_members]
        now = datetime.now(UTC)

        async def _discover(window: int) -> list[RepositoryActivity]:
            try:
                return await connector.discover_repositories_by_activity(
                    member_ids,
                    since=now - timedelta(days=window),
                    limit=discover_limit,
                )
            except (ConnectorAuthError, ConnectorError) as error:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)
                ) from error

        # Start at the default window; widen once when it yields too few candidates (§15).
        window_days = DISCOVERY_DEFAULT_WINDOW_DAYS
        activities = await _discover(window_days)
        if len(activities) < DISCOVERY_MIN_CANDIDATES:
            window_days = DISCOVERY_WIDE_WINDOW_DAYS
            activities = await _discover(window_days)

        repositories = [
            RepositoryActivityResult(
                provider_project_id=activity.provider_project_id,
                name=activity.name,
                path_with_namespace=activity.path_with_namespace,
                contributing_member_count=activity.contributing_member_count,
                merge_request_count=activity.merge_request_count,
                last_activity_at=activity.last_activity_at,
            )
            for activity in activities[:capped]
        ]
        return RepositorySuggestionsResponse(window_days=window_days, repositories=repositories)
    finally:
        await connector.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_gitlab_connector(session: Session, team_row: TeamProfileTable) -> ConnectorBase:
    if team_row.code_connection_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="team has no GitLab connection configured",
        )
    try:
        connector = instantiate_connector(
            session,
            team_row.code_connection_id,
            lambda config: create_connector("gitlab", config),
        )
    except ConnectorConfigError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error
    if connector is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="GitLab connection not found"
        )
    return connector


def _team_not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="team not found")


def _invalid_team(error: InvalidTeamProfile) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))
