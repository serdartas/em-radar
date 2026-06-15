from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session
from starlette.responses import Response

from em_radar_api.db import get_session, get_write_session
from em_radar_api.repositories.team_profiles import (
    InvalidTeamProfile,
    TeamProfileInUse,
    create_team_profile,
    delete_team_profile,
    get_team_profile,
    list_team_profiles,
    update_team_profile,
)
from em_radar_api.team_profiles import TeamProfileCreate, TeamProfileRead, TeamProfileUpdate

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


def _team_not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="team not found")


def _invalid_team(error: InvalidTeamProfile) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))
