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
    BulkMemberResolveRequest,
    BulkMemberResolveResponse,
    ConfidenceBand,
    ConfigHealthReport,
    GitLabMemberInput,
    GitLabRepositoryInput,
    GroupSearchResult,
    JiraPersonRef,
    MemberResolveResult,
    MemberResolveStatus,
    MemberSearchResult,
    MemberSuggestion,
    MemberSuggestionsResponse,
    ProjectSearchResult,
    RepositoryActivityResult,
    RepositorySuggestionsResponse,
    TeamGitLabMemberRead,
    TeamGitLabRepositoryRead,
    TeamProfileCreate,
    TeamProfileRead,
    TeamProfileUpdate,
)
from em_radar_api.scope_definitions import ScopeDefinitionTable, ScopeType
from em_radar_api.source_connections import ConnectorName, SourceConnectionTable
from em_radar_core.connectors import (
    ConnectorAuthError,
    ConnectorBase,
    ConnectorConfigError,
    ConnectorError,
    GroupMemberProvider,
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

try:
    from em_radar_connector_jira.connector import (
        JIRA_ACTIVITY_MAX_USERS,
        JIRA_ACTIVITY_WINDOW_DAYS,
    )
except ImportError:
    JIRA_ACTIVITY_WINDOW_DAYS = 90
    JIRA_ACTIVITY_MAX_USERS = 50

_MEMBER_SEARCH_DEFAULT_LIMIT = 20
_MEMBER_SEARCH_MAX_LIMIT = 50
_PROJECT_SEARCH_DEFAULT_LIMIT = 20
_PROJECT_SEARCH_MAX_LIMIT = 50
_SUGGESTION_DEFAULT_LIMIT = 20
_SUGGESTION_MAX_LIMIT = 50
_BULK_RESOLVE_PER_ENTRY_LIMIT = 5
_GROUP_SEARCH_DEFAULT_LIMIT = 20
_GROUP_SEARCH_MAX_LIMIT = 50
_GROUP_MEMBERS_DEFAULT_LIMIT = 50
_GROUP_MEMBERS_MAX_LIMIT = 100
# Maximum GitLab candidates to search per Jira person for member suggestions.
_MEMBER_SUGGESTION_GL_LIMIT = 5

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
# GitLab bulk member resolve
# ---------------------------------------------------------------------------


@router.post(
    "/teams/{team_id}/gitlab/member-resolve",
    response_model=BulkMemberResolveResponse,
)
async def gitlab_member_bulk_resolve(
    team_id: UUID,
    body: BulkMemberResolveRequest,
    session: Session = Depends(get_session),
) -> BulkMemberResolveResponse:
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
        results: list[MemberResolveResult] = []
        for entry in body.entries:
            stripped = entry.strip()
            if not stripped:
                continue
            try:
                refs = await connector.search_users(stripped, limit=_BULK_RESOLVE_PER_ENTRY_LIMIT)
            except ConnectorAuthError as error:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)
                ) from error
            except ConnectorError as error:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)
                ) from error
            candidates = [
                MemberSearchResult(
                    provider_user_id=ref.provider_user_id,
                    username=ref.username,
                    display_name=ref.display_name,
                    avatar_url=ref.avatar_url,
                )
                for ref in refs
            ]
            if len(candidates) == 1:
                results.append(
                    MemberResolveResult(
                        entry=stripped,
                        status=MemberResolveStatus.MATCHED,
                        match=candidates[0],
                    )
                )
            elif len(candidates) > 1:
                results.append(
                    MemberResolveResult(
                        entry=stripped,
                        status=MemberResolveStatus.AMBIGUOUS,
                        candidates=candidates,
                    )
                )
            else:
                results.append(
                    MemberResolveResult(
                        entry=stripped,
                        status=MemberResolveStatus.UNMATCHED,
                    )
                )
        return BulkMemberResolveResponse(results=results)
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
# GitLab group search and group member import
# ---------------------------------------------------------------------------


@router.get(
    "/teams/{team_id}/gitlab/group-search",
    response_model=list[GroupSearchResult],
)
async def gitlab_group_search(
    team_id: UUID,
    q: str = Query(default=""),
    limit: int = Query(default=_GROUP_SEARCH_DEFAULT_LIMIT, ge=1),
    page: int = Query(1, ge=1),
    session: Session = Depends(get_session),
) -> list[GroupSearchResult]:
    team_row = session.get(TeamProfileTable, team_id)
    if team_row is None:
        raise _team_not_found()
    connector = _require_gitlab_connector(session, team_row)
    try:
        if not isinstance(connector, GroupMemberProvider):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="GitLab connector does not support group member import",
            )
        capped = min(limit, _GROUP_SEARCH_MAX_LIMIT)
        try:
            refs = await connector.search_groups(q, limit=capped, page=page)
        except ConnectorAuthError as error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)
            ) from error
        except ConnectorError as error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)
            ) from error
        return [
            GroupSearchResult(
                provider_group_id=ref.provider_group_id,
                name=ref.name,
                full_path=ref.full_path,
            )
            for ref in refs
        ]
    finally:
        await connector.close()


@router.get(
    "/teams/{team_id}/gitlab/group-members",
    response_model=list[MemberSearchResult],
)
async def gitlab_group_members(
    team_id: UUID,
    group_id: str = Query(...),
    limit: int = Query(default=_GROUP_MEMBERS_DEFAULT_LIMIT, ge=1),
    page: int = Query(1, ge=1),
    session: Session = Depends(get_session),
) -> list[MemberSearchResult]:
    team_row = session.get(TeamProfileTable, team_id)
    if team_row is None:
        raise _team_not_found()
    connector = _require_gitlab_connector(session, team_row)
    try:
        if not isinstance(connector, GroupMemberProvider):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="GitLab connector does not support group member import",
            )
        capped = min(limit, _GROUP_MEMBERS_MAX_LIMIT)
        try:
            refs = await connector.list_group_members(group_id, limit=capped, page=page)
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
# Member suggestions (Jira activity → GitLab user matching, M9-15)
# ---------------------------------------------------------------------------


@router.get(
    "/teams/{team_id}/gitlab/member-suggestions",
    response_model=MemberSuggestionsResponse,
)
async def gitlab_member_suggestions(
    team_id: UUID,
    session: Session = Depends(get_session),
) -> MemberSuggestionsResponse:
    team_row = session.get(TeamProfileTable, team_id)
    if team_row is None:
        raise _team_not_found()

    # Require a GitLab connection — this endpoint returns GitLab user candidates.
    if team_row.code_connection_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="team has no GitLab connection configured",
        )

    # Find the first Jira connection associated with this team.
    # Teams with no Jira scope gracefully return an empty response.
    jira_connection_id = None
    for cid in team_row.connection_ids:
        conn_row = session.get(SourceConnectionTable, cid)
        if conn_row is not None and conn_row.connector_name == ConnectorName.JIRA:
            jira_connection_id = cid
            break

    if jira_connection_id is None:
        return MemberSuggestionsResponse(window_days=JIRA_ACTIVITY_WINDOW_DAYS, suggestions=[])

    jira_connector = instantiate_connector(
        session,
        jira_connection_id,
        lambda config: create_connector("jira", config),
    )
    if jira_connector is None:
        return MemberSuggestionsResponse(window_days=JIRA_ACTIVITY_WINDOW_DAYS, suggestions=[])

    gitlab_connector = _require_gitlab_connector(session, team_row)

    try:
        if not isinstance(gitlab_connector, MemberProvider):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="GitLab connector does not support member search",
            )
        if not hasattr(jira_connector, "list_recently_active_users"):
            return MemberSuggestionsResponse(window_days=JIRA_ACTIVITY_WINDOW_DAYS, suggestions=[])

        now = datetime.now(UTC)
        since = now - timedelta(days=JIRA_ACTIVITY_WINDOW_DAYS)

        # Collect project keys from the team's Jira project scopes so the JQL
        # is restricted to issues the team actually owns. Without this filter,
        # a shared Jira credential would search all visible issues and could
        # exhaust the user cap with people from unrelated teams.
        jira_project_keys: list[str] = []
        if team_row.scope_ids:
            scopes = session.exec(
                select(ScopeDefinitionTable).where(ScopeDefinitionTable.id.in_(team_row.scope_ids))
            ).all()
            for scope in scopes:
                if (
                    scope.connection_id == jira_connection_id
                    and scope.scope_type is ScopeType.PROJECT
                ):
                    key = scope.external_ref.get("key")
                    if key:
                        jira_project_keys.append(str(key))

        try:
            jira_people = await jira_connector.list_recently_active_users(
                since=since,
                max_users=JIRA_ACTIVITY_MAX_USERS,
                project_keys=jira_project_keys or None,
            )
        except ConnectorAuthError as error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)
            ) from error
        except ConnectorError as error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)
            ) from error

        suggestions: list[MemberSuggestion] = []
        for jira_person in jira_people:
            query = jira_person.display_name or jira_person.email_address or ""
            if not query:
                continue
            try:
                refs = await gitlab_connector.search_users(query, limit=_MEMBER_SUGGESTION_GL_LIMIT)
            except ConnectorAuthError as error:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)
                ) from error
            except ConnectorError as error:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)
                ) from error

            candidates = [
                MemberSearchResult(
                    provider_user_id=ref.provider_user_id,
                    username=ref.username,
                    display_name=ref.display_name,
                    avatar_url=ref.avatar_url,
                )
                for ref in refs
            ]

            person_ref = JiraPersonRef(
                display_name=jira_person.display_name,
                email_address=getattr(jira_person, "email_address", None),
                account_id=getattr(jira_person, "account_id", None),
            )

            if len(candidates) == 1:
                suggestions.append(
                    MemberSuggestion(
                        jira_person=person_ref,
                        match=candidates[0],
                        candidates=[],
                        confidence=ConfidenceBand.HIGH,
                    )
                )
            else:
                suggestions.append(
                    MemberSuggestion(
                        jira_person=person_ref,
                        match=None,
                        candidates=candidates,
                        confidence=ConfidenceBand.UNCERTAIN,
                    )
                )

        return MemberSuggestionsResponse(
            window_days=JIRA_ACTIVITY_WINDOW_DAYS, suggestions=suggestions
        )
    finally:
        await gitlab_connector.close()
        if jira_connector is not None:
            await jira_connector.close()


# ---------------------------------------------------------------------------
# Config health verification
# ---------------------------------------------------------------------------


@router.post(
    "/teams/{team_id}/gitlab/verify-config",
    response_model=ConfigHealthReport,
)
async def verify_gitlab_config(
    team_id: UUID,
    session: Session = Depends(get_session),
) -> ConfigHealthReport:
    """Re-resolve all stored members and repositories against the GitLab connector.

    Entries whose connection_id no longer matches the team's current code_connection_id
    are marked UNVERIFIED (connector-instance mismatch, §22). Entries from the current
    connector are re-fetched: deleted users (404) and archived repositories become
    UNAVAILABLE; renamed-but-same-id entities are refreshed and stay VERIFIED.
    Transient connector errors leave the existing status unchanged.
    """
    team_row = session.get(TeamProfileTable, team_id)
    if team_row is None:
        raise _team_not_found()

    member_rows = list_team_gitlab_members(session, team_id)
    repo_rows = list_team_gitlab_repositories(session, team_id)

    now = datetime.now(UTC)
    connector: ConnectorBase | None = None

    try:
        if team_row.code_connection_id is not None:
            try:
                connector = _require_gitlab_connector(session, team_row)
            except HTTPException:
                pass  # Connector unavailable; only instance-mismatch entries are updated below.

        for member_row in member_rows:
            if member_row.connection_id != team_row.code_connection_id:
                member_row.verification_status = ScopeVerificationStatus.UNVERIFIED
                member_row.updated_at = now
            elif connector is not None and isinstance(connector, MemberProvider):
                try:
                    ref = await connector.get_user(str(member_row.gitlab_user_id))
                except ConnectorError:
                    pass  # Transient error; leave current status unchanged.
                else:
                    if ref is None:
                        member_row.verification_status = ScopeVerificationStatus.UNAVAILABLE
                    else:
                        member_row.username = ref.username
                        member_row.display_name = ref.display_name
                        member_row.verification_status = ScopeVerificationStatus.VERIFIED
                    member_row.updated_at = now

        for repo_row in repo_rows:
            if repo_row.connection_id != team_row.code_connection_id:
                repo_row.verification_status = ScopeVerificationStatus.UNVERIFIED
                repo_row.updated_at = now
            elif connector is not None and isinstance(connector, RepositorySearchProvider):
                try:
                    ref = await connector.get_project(str(repo_row.gitlab_project_id))
                except ConnectorError:
                    pass  # Transient error; leave current status unchanged.
                else:
                    if ref is None or ref.is_archived:
                        repo_row.verification_status = ScopeVerificationStatus.UNAVAILABLE
                    else:
                        repo_row.name = ref.name
                        repo_row.path_with_namespace = ref.path_with_namespace
                        repo_row.verification_status = ScopeVerificationStatus.VERIFIED
                    repo_row.updated_at = now

        with write_lock_acquired():
            for row in member_rows:
                session.add(row)
            for row in repo_rows:
                session.add(row)
            session.commit()

        for row in member_rows:
            session.refresh(row)
        for row in repo_rows:
            session.refresh(row)

    finally:
        if connector is not None:
            await connector.close()

    return ConfigHealthReport(
        members=[TeamGitLabMemberRead.model_validate(r) for r in member_rows],
        repositories=[TeamGitLabRepositoryRead.model_validate(r) for r in repo_rows],
    )


# ---------------------------------------------------------------------------
# Per-item member / repository removal (config-health cleanup)
# ---------------------------------------------------------------------------


@router.delete(
    "/teams/{team_id}/gitlab/members/{member_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_gitlab_member(
    team_id: UUID,
    member_id: UUID,
    session: Session = Depends(get_write_session),
) -> Response:
    """Remove exactly one stored GitLab member row regardless of its verification status.

    Designed for config-health cleanup: removes only the targeted row without
    re-validating or touching any other member entries.
    """
    team_row = session.get(TeamProfileTable, team_id)
    if team_row is None:
        raise _team_not_found()
    row = session.exec(
        select(TeamGitLabMemberTable).where(
            TeamGitLabMemberTable.id == member_id,
            TeamGitLabMemberTable.team_profile_id == team_id,
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="member not found")
    with write_lock_acquired():
        session.delete(row)
        session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/teams/{team_id}/gitlab/repositories/{repo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_gitlab_repository(
    team_id: UUID,
    repo_id: UUID,
    session: Session = Depends(get_write_session),
) -> Response:
    """Remove exactly one stored GitLab repository row regardless of its verification status.

    Designed for config-health cleanup: removes only the targeted row without
    re-validating or touching any other repository entries.
    """
    team_row = session.get(TeamProfileTable, team_id)
    if team_row is None:
        raise _team_not_found()
    row = session.exec(
        select(TeamGitLabRepositoryTable).where(
            TeamGitLabRepositoryTable.id == repo_id,
            TeamGitLabRepositoryTable.team_profile_id == team_id,
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="repository not found")
    with write_lock_acquired():
        session.delete(row)
        session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
