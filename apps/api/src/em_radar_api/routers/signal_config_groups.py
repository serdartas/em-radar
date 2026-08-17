# SPDX-License-Identifier: Apache-2.0

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from em_radar_api.db import get_session, get_write_session
from em_radar_api.repositories.signal_config_groups import (
    DuplicateGroupName,
    InvalidSignalConfigGroup,
    SignalConfigGroupInUse,
    create_signal_config_group,
    delete_signal_config_group,
    get_signal_config_group,
    list_signal_config_groups,
    update_signal_config_group,
)
from em_radar_api.signal_config_groups import (
    SignalConfigGroupCreate,
    SignalConfigGroupRead,
    SignalConfigGroupUpdate,
)

router = APIRouter()


@router.get("/signal-config-groups", response_model=list[SignalConfigGroupRead])
def list_signal_config_groups_route(
    session: Session = Depends(get_session),
) -> list[SignalConfigGroupRead]:
    return list_signal_config_groups(session)


@router.post(
    "/signal-config-groups",
    response_model=SignalConfigGroupRead,
    status_code=status.HTTP_201_CREATED,
)
def create_signal_config_group_route(
    group: SignalConfigGroupCreate,
    session: Session = Depends(get_write_session),
) -> SignalConfigGroupRead:
    try:
        return create_signal_config_group(session, group)
    except DuplicateGroupName as error:
        raise _conflict(error) from error
    except InvalidSignalConfigGroup as error:
        raise _invalid(error) from error


@router.get("/signal-config-groups/{group_id}", response_model=SignalConfigGroupRead)
def get_signal_config_group_route(
    group_id: UUID,
    session: Session = Depends(get_session),
) -> SignalConfigGroupRead:
    group = get_signal_config_group(session, group_id)
    if group is None:
        raise _not_found(group_id)
    return group


@router.patch("/signal-config-groups/{group_id}", response_model=SignalConfigGroupRead)
def update_signal_config_group_route(
    group_id: UUID,
    update: SignalConfigGroupUpdate,
    session: Session = Depends(get_write_session),
) -> SignalConfigGroupRead:
    try:
        group = update_signal_config_group(session, group_id, update)
    except DuplicateGroupName as error:
        raise _conflict(error) from error
    except InvalidSignalConfigGroup as error:
        raise _invalid(error) from error
    if group is None:
        raise _not_found(group_id)
    return group


@router.delete("/signal-config-groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_signal_config_group_route(
    group_id: UUID,
    session: Session = Depends(get_write_session),
) -> None:
    try:
        if not delete_signal_config_group(session, group_id):
            raise _not_found(group_id)
    except SignalConfigGroupInUse as error:
        raise _conflict(error) from error


def _not_found(group_id: UUID) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"signal config group not found: {group_id}",
    )


def _invalid(error: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


def _conflict(error: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
