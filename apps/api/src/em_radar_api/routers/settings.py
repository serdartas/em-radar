# SPDX-License-Identifier: Apache-2.0

from typing import Literal

from pydantic import BaseModel, field_validator
from fastapi import APIRouter, Depends
from sqlmodel import Session

from em_radar_api.db import get_session, get_write_session
from em_radar_api.tables import AppSettingsTable

router = APIRouter()

_SETTINGS_ID = 1

DateFormat = Literal["dd/mm/yyyy", "mm/dd/yyyy", "yyyy-mm-dd"]
_VALID_DATE_FORMATS: set[str] = {"dd/mm/yyyy", "mm/dd/yyyy", "yyyy-mm-dd"}


def _get_or_create(session: Session) -> AppSettingsTable:
    row = session.get(AppSettingsTable, _SETTINGS_ID)
    if row is None:
        row = AppSettingsTable(id=_SETTINGS_ID, telemetry_enabled=False, date_format="dd/mm/yyyy")
        session.add(row)
        session.commit()
        session.refresh(row)
    return row


class AppSettingsResponse(BaseModel):
    telemetry_enabled: bool
    date_format: str


class AppSettingsPatch(BaseModel):
    telemetry_enabled: bool | None = None
    date_format: DateFormat | None = None

    @field_validator("date_format")
    @classmethod
    def validate_date_format(cls, v: str | None) -> str | None:
        if v is not None and v not in _VALID_DATE_FORMATS:
            raise ValueError(f"date_format must be one of {sorted(_VALID_DATE_FORMATS)}")
        return v


@router.get("/settings", response_model=AppSettingsResponse)
def get_settings(session: Session = Depends(get_session)) -> AppSettingsResponse:
    row = session.get(AppSettingsTable, _SETTINGS_ID)
    telemetry_enabled = row.telemetry_enabled if row is not None else False
    date_format = row.date_format if row is not None else "dd/mm/yyyy"
    return AppSettingsResponse(telemetry_enabled=telemetry_enabled, date_format=date_format)


@router.patch("/settings", response_model=AppSettingsResponse)
def update_settings(
    patch: AppSettingsPatch,
    session: Session = Depends(get_write_session),
) -> AppSettingsResponse:
    row = _get_or_create(session)
    if patch.telemetry_enabled is not None:
        row.telemetry_enabled = patch.telemetry_enabled
    if patch.date_format is not None:
        row.date_format = patch.date_format
    session.add(row)
    session.commit()
    session.refresh(row)
    return AppSettingsResponse(telemetry_enabled=row.telemetry_enabled, date_format=row.date_format)
