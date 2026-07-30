from datetime import UTC, datetime
from uuid import UUID

from pydantic import ValidationError
from sqlmodel import Session, select

from em_radar_api.connector_registry import get_connector_capabilities
from em_radar_api.scope_definitions import ScopeDefinitionTable, ScopeType
from em_radar_api.signal_config_groups import SignalConfigGroupTable
from em_radar_api.source_connections import SourceConnectionTable
from em_radar_api.tables import EvaluationWindowTable, TeamProfileTable
from em_radar_api.team_profiles import TeamProfileCreate, TeamProfileRead, TeamProfileUpdate
from em_radar_core.models import WorkingMode


class InvalidTeamProfile(ValueError):
    pass


class TeamProfileInUse(ValueError):
    pass


def create_team_profile(session: Session, team: TeamProfileCreate) -> TeamProfileRead:
    derived_conn_ids = _derive_connection_ids(session, team.scope_ids, team.code_connection_id)
    team = team.model_copy(update={"connection_ids": derived_conn_ids})
    _validate_team_profile(session, team)
    now = datetime.now(UTC)
    row = TeamProfileTable.model_validate(team, update={"created_at": now, "updated_at": now})
    _write(session, row)
    return TeamProfileRead.model_validate(row)


def list_team_profiles(session: Session) -> list[TeamProfileRead]:
    rows = session.exec(select(TeamProfileTable).order_by(TeamProfileTable.created_at)).all()
    return [TeamProfileRead.model_validate(row) for row in rows]


def get_team_profile(session: Session, team_id: UUID) -> TeamProfileRead | None:
    row = session.get(TeamProfileTable, team_id)
    return TeamProfileRead.model_validate(row) if row is not None else None


def update_team_profile(
    session: Session, team_id: UUID, update: TeamProfileUpdate
) -> TeamProfileRead | None:
    row = session.get(TeamProfileTable, team_id)
    if row is None:
        return None

    values = update.model_dump(exclude_unset=True)

    # Always derive connection_ids from the team's actual sources so that changing the board
    # scope or the code connection from any client never leaves stale IDs in the list.
    effective_scope_ids = values.get("scope_ids", list(row.scope_ids or []))
    effective_code_cid = (
        values["code_connection_id"] if "code_connection_id" in values else row.code_connection_id
    )
    values["connection_ids"] = _derive_connection_ids(
        session, effective_scope_ids, effective_code_cid
    )

    try:
        candidate = TeamProfileCreate.model_validate(
            {
                **TeamProfileRead.model_validate(row).model_dump(
                    include=set(TeamProfileCreate.model_fields)
                ),
                **values,
            }
        )
    except ValidationError as error:
        message = str(error.errors()[0]["msg"]).removeprefix("Value error, ")
        raise InvalidTeamProfile(message) from error
    _validate_team_profile(session, candidate)
    row.sqlmodel_update(values)
    row.updated_at = datetime.now(UTC)
    _write(session, row)
    return TeamProfileRead.model_validate(row)


def delete_team_profile(session: Session, team_id: UUID) -> bool:
    row = session.get(TeamProfileTable, team_id)
    if row is None:
        return False
    window = session.exec(
        select(EvaluationWindowTable).where(EvaluationWindowTable.team_profile_id == team_id)
    ).first()
    if window is not None:
        raise TeamProfileInUse("team is referenced by an evaluation window")
    session.delete(row)
    session.commit()
    return True


def _validate_team_profile(session: Session, team: TeamProfileCreate) -> None:
    if team.working_mode is WorkingMode.KANBAN and team.sprint_length_days is not None:
        raise InvalidTeamProfile("sprint_length_days must be null for kanban teams")

    # Validate code_connection_id before connection_ids so its specific error takes precedence
    # (code_connection_id is auto-merged into connection_ids before validation).
    if team.code_connection_id is not None:
        conn = session.get(SourceConnectionTable, team.code_connection_id)
        if conn is None:
            raise InvalidTeamProfile("code_connection_id must reference an existing connection")
        caps = get_connector_capabilities(conn.connector_name)
        if caps is None or not caps.provides_mergerequests:
            raise InvalidTeamProfile(
                "code_connection_id must reference a connection that provides merge-request data"
            )

    scopes = session.exec(
        select(ScopeDefinitionTable).where(ScopeDefinitionTable.id.in_(team.scope_ids))
    ).all()
    if len(scopes) != len(set(team.scope_ids)):
        raise InvalidTeamProfile("scope_ids must reference existing scopes")
    board_scope_ids = {scope.id for scope in scopes if scope.scope_type is ScopeType.BOARD}
    if sum(scope_id in board_scope_ids for scope_id in team.scope_ids) > 1:
        raise InvalidTeamProfile("scope_ids may contain at most one board scope")

    if len(set(team.signal_config_group_ids)) != len(team.signal_config_group_ids):
        raise InvalidTeamProfile("signal_config_group_ids must not contain duplicates")
    groups = session.exec(
        select(SignalConfigGroupTable).where(
            SignalConfigGroupTable.id.in_(team.signal_config_group_ids)
        )
    ).all()
    if len(groups) != len(set(team.signal_config_group_ids)):
        raise InvalidTeamProfile(
            "signal_config_group_ids must reference existing signal config groups"
        )


def _derive_connection_ids(
    session: Session,
    scope_ids: list[UUID],
    code_connection_id: UUID | None,
) -> list[UUID]:
    """Compute connection_ids from the team's actual sources.

    Collects connection_ids from each referenced scope (stable insertion order, deduped),
    then appends the code connection if set and not already present.  Any connection_ids
    value sent by the caller is ignored — the result is fully server-derived.
    """
    result: list[UUID] = []
    seen: set[UUID] = set()
    if scope_ids:
        scopes = session.exec(
            select(ScopeDefinitionTable).where(ScopeDefinitionTable.id.in_(scope_ids))
        ).all()
        scope_by_id = {s.id: s for s in scopes}
        for sid in scope_ids:
            scope = scope_by_id.get(sid)
            if scope is not None and scope.connection_id not in seen:
                seen.add(scope.connection_id)
                result.append(scope.connection_id)
    if code_connection_id is not None and code_connection_id not in seen:
        result.append(code_connection_id)
    return result


def _write(session: Session, row: TeamProfileTable) -> None:
    session.add(row)
    session.commit()
    session.refresh(row)
