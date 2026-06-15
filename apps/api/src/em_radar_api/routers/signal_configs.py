from typing import cast
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, JsonValue, ValidationError
from sqlmodel import Session

from em_radar_api.db import get_session, get_write_session
from em_radar_api.repositories.signal_configs import (
    list_signal_configs,
    reset_all_signal_configs,
    reset_signal_config,
    upsert_signal_config,
)
from em_radar_api.signal_configs import SignalConfigRead, SignalConfigUpsert
from em_radar_config import SIGNAL_CATALOG
from em_radar_core.models import Severity

router = APIRouter()


class SignalConfigPatch(BaseModel):
    enabled: bool | None = None
    severity_override: Severity | None = None
    params: dict[str, JsonValue] | None = None


class SignalConfigResponse(BaseModel):
    signal_id: str
    name: str
    description: str
    default_severity: Severity
    enabled: bool
    severity_override: Severity | None
    params: dict[str, JsonValue]
    params_schema: dict[str, JsonValue] = Field(default_factory=dict)


@router.get("/signal-configs", response_model=list[SignalConfigResponse])
def list_signal_config_endpoint(
    session: Session = Depends(get_session),
) -> list[SignalConfigResponse]:
    stored = {config.signal_id: config for config in list_signal_configs(session)}
    return [
        _response(stored.get(signal_id) or _default_config(signal_id))
        for signal_id in SIGNAL_CATALOG
    ]


@router.patch("/signal-configs/{signal_id}", response_model=SignalConfigResponse)
def patch_signal_config_endpoint(
    signal_id: str,
    patch: SignalConfigPatch,
    session: Session = Depends(get_write_session),
) -> SignalConfigResponse:
    current = _current_config(session, signal_id)
    values = patch.model_dump(exclude_unset=True)
    updated = SignalConfigUpsert(
        signal_id=signal_id,
        enabled=values.get("enabled", current.enabled),
        severity_override=values.get("severity_override", current.severity_override),
        params=values.get("params", current.params),
        scope=current.scope,
    )
    try:
        return _response(upsert_signal_config(session, updated))
    except (ValidationError, ValueError) as error:
        raise _invalid_signal_config(error) from error


@router.post("/signal-configs/{signal_id}/reset", response_model=SignalConfigResponse)
def reset_signal_config_endpoint(
    signal_id: str,
    session: Session = Depends(get_write_session),
) -> SignalConfigResponse:
    try:
        return _response(reset_signal_config(session, signal_id))
    except ValueError as error:
        raise _signal_not_found(signal_id) from error


@router.post("/signal-configs/reset", response_model=list[SignalConfigResponse])
def reset_all_signal_config_endpoint(
    session: Session = Depends(get_write_session),
) -> list[SignalConfigResponse]:
    reset_all_signal_configs(session)
    return [
        _response(upsert_signal_config(session, _default_upsert(signal_id)))
        for signal_id in SIGNAL_CATALOG
    ]


def _current_config(session: Session, signal_id: str) -> SignalConfigRead:
    for config in list_signal_configs(session):
        if config.signal_id == signal_id:
            return config
    if signal_id not in SIGNAL_CATALOG:
        raise _signal_not_found(signal_id)
    return _default_config(signal_id)


def _default_config(signal_id: str) -> SignalConfigRead:
    return SignalConfigRead.model_validate(_default_upsert(signal_id), update={"id": uuid4()})


def _default_upsert(signal_id: str) -> SignalConfigUpsert:
    catalog_entry = SIGNAL_CATALOG[signal_id]
    return SignalConfigUpsert(
        signal_id=signal_id,
        params=catalog_entry.params_schema().model_dump(mode="json"),
    )


def _response(config: SignalConfigRead) -> SignalConfigResponse:
    try:
        catalog_entry = SIGNAL_CATALOG[config.signal_id]
    except KeyError as error:
        raise _signal_not_found(config.signal_id) from error

    return SignalConfigResponse(
        signal_id=config.signal_id,
        name=_display_name(config.signal_id),
        description=f"Configure the {config.signal_id.replace('-', ' ')} signal.",
        default_severity=catalog_entry.default_severity,
        enabled=config.enabled,
        severity_override=config.severity_override,
        params=config.params,
        params_schema=cast(dict[str, JsonValue], catalog_entry.params_schema.model_json_schema()),
    )


def _display_name(signal_id: str) -> str:
    if signal_id == "stale-in-progress-work-item":
        return "Stale in-progress work item"
    return signal_id.replace("-", " ").capitalize()


def _signal_not_found(signal_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"signal config not found: {signal_id}",
    )


def _invalid_signal_config(error: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))
