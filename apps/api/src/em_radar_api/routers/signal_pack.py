from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session
from starlette.responses import Response

from em_radar_api.db import get_session, get_write_session
from em_radar_api.repositories.signal_configs import list_signal_configs
from em_radar_api.repositories.signal_definitions import list_signal_definitions
from em_radar_api.repositories.scope_definitions import list_scope_definitions
from em_radar_api.repositories.source_connections import list_source_connections
from em_radar_api.signal_pack_export import export_signal_definition_pack, export_signal_pack
from em_radar_api.signal_pack_import import (
    SignalPackImportPreview,
    apply_signal_pack_import,
    preview_signal_pack_import,
)
from em_radar_config import PackValidationError

router = APIRouter()

PackName = Annotated[
    str | None,
    Query(pattern=r"^[a-z][a-z0-9-]{1,62}[a-z0-9]$"),
]


class SignalPackImportRequest(BaseModel):
    raw_yaml: str
    mode: Literal["additive", "replace_all"] = "additive"


@router.get("/signal-pack/export")
def export_signal_pack_route(
    mode: Literal["minimal", "full"] = "minimal",
    export_type: Literal["legacy", "private_backup", "public_template"] = "legacy",
    name: PackName = None,
    session: Session = Depends(get_session),
) -> Response:
    yaml_text = (
        export_signal_pack(
            list_signal_configs(session),
            full=mode == "full",
            name=name,
        )
        if export_type == "legacy"
        else export_signal_definition_pack(
            list_signal_definitions(session),
            list_scope_definitions(session),
            list_source_connections(session),
            export_type=export_type,
            name=name,
        )
    )
    return Response(
        content=yaml_text,
        media_type="application/yaml",
        headers={"Content-Disposition": 'attachment; filename="signal-pack.yaml"'},
    )


@router.post(
    "/signal-pack/import",
    response_model=SignalPackImportPreview,
    response_model_exclude_defaults=True,
)
def preview_signal_pack_import_route(
    request: SignalPackImportRequest,
    session: Session = Depends(get_session),
) -> SignalPackImportPreview:
    try:
        return preview_signal_pack_import(
            session,
            request.raw_yaml,
            replace_all=request.mode == "replace_all",
        )
    except PackValidationError as error:
        raise _invalid_pack(error) from error


@router.post(
    "/signal-pack/import/apply",
    response_model=SignalPackImportPreview,
    response_model_exclude_defaults=True,
)
def apply_signal_pack_import_route(
    request: SignalPackImportRequest,
    session: Session = Depends(get_write_session),
) -> SignalPackImportPreview:
    try:
        return apply_signal_pack_import(
            session,
            request.raw_yaml,
            replace_all=request.mode == "replace_all",
        )
    except PackValidationError as error:
        raise _invalid_pack(error) from error


def _invalid_pack(error: PackValidationError) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={"code": "invalid-signal-pack", "message": str(error)},
    )
