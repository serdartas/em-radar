from datetime import UTC, datetime
from uuid import UUID

from pydantic import ValidationError
from sqlmodel import Session, select

from em_radar_api.source_connections import SourceConnectionTable
from em_radar_api.tables import TeamProfileTable
from em_radar_api.team_profiles import TeamProfileCreate, TeamProfileRead, TeamProfileUpdate
from em_radar_core.models import WorkingMode


class InvalidTeamProfile(ValueError):
    pass


def create_team_profile(session: Session, team: TeamProfileCreate) -> TeamProfileRead:
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
    session.delete(row)
    session.commit()
    return True


def _validate_team_profile(session: Session, team: TeamProfileCreate) -> None:
    if team.working_mode is WorkingMode.KANBAN and team.sprint_length_days is not None:
        raise InvalidTeamProfile("sprint_length_days must be null for kanban teams")

    connections = session.exec(
        select(SourceConnectionTable).where(SourceConnectionTable.id.in_(team.connection_ids))
    ).all()
    if len(connections) != len(set(team.connection_ids)):
        raise InvalidTeamProfile("connection_ids must reference existing connections")

    scoped_ids = (
        ("project_ids", team.project_ids, "selected_project_ids"),
        ("board_ids", team.board_ids, "selected_board_ids"),
        ("repository_ids", team.repository_ids, "selected_repository_ids"),
    )
    for field_name, values, connection_field in scoped_ids:
        available = {
            item for connection in connections for item in getattr(connection, connection_field)
        }
        if not set(values).issubset(available):
            raise InvalidTeamProfile(f"{field_name} must reference the selected connections")


def _write(session: Session, row: TeamProfileTable) -> None:
    session.add(row)
    session.commit()
    session.refresh(row)
