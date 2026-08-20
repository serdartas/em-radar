# SPDX-License-Identifier: Apache-2.0

from pydantic import BaseModel
from fastapi import APIRouter, Depends
from sqlmodel import Session

from em_radar_api.db import get_session, get_write_session
from em_radar_api.tables import AppSettingsTable

router = APIRouter()

_SETTINGS_ID = 1


def _get_or_create(session: Session) -> AppSettingsTable:
    row = session.get(AppSettingsTable, _SETTINGS_ID)
    if row is None:
        row = AppSettingsTable(id=_SETTINGS_ID, telemetry_enabled=False)
        session.add(row)
        session.commit()
        session.refresh(row)
    return row


class AppSettingsResponse(BaseModel):
    telemetry_enabled: bool


class AppSettingsPatch(BaseModel):
    telemetry_enabled: bool


@router.get("/settings", response_model=AppSettingsResponse)
def get_settings(session: Session = Depends(get_session)) -> AppSettingsResponse:
    row = session.get(AppSettingsTable, _SETTINGS_ID)
    telemetry_enabled = row.telemetry_enabled if row is not None else False
    return AppSettingsResponse(telemetry_enabled=telemetry_enabled)


@router.patch("/settings", response_model=AppSettingsResponse)
def update_settings(
    patch: AppSettingsPatch,
    session: Session = Depends(get_write_session),
) -> AppSettingsResponse:
    row = _get_or_create(session)
    row.telemetry_enabled = patch.telemetry_enabled
    session.add(row)
    session.commit()
    session.refresh(row)
    return AppSettingsResponse(telemetry_enabled=row.telemetry_enabled)
