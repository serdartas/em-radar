from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session
from starlette.responses import Response

from em_radar_api.db import get_session, get_write_session
from em_radar_api.repositories.signal_config_groups import get_signal_config_group
from em_radar_api.repositories.signal_configs import list_signal_configs
from em_radar_api.repositories.signal_definitions import get_signal_definition
from em_radar_api.signal_pack_export import export_signal_group_pack, export_signal_pack
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
    group_id: UUID | None = Query(default=None),
    name: PackName = None,
    session: Session = Depends(get_session),
) -> Response:
    if export_type == "legacy":
        yaml_text = export_signal_pack(
            list_signal_configs(session),
            full=mode == "full",
            name=name,
        )
    else:
        if group_id is None:
            raise HTTPException(status_code=422, detail="group_id is required for this export type")
        group = get_signal_config_group(session, group_id)
        if group is None:
            raise HTTPException(status_code=404, detail="signal config group not found")
        definitions = [
            definition
            for signal_id in group.signal_ids
            if (definition := get_signal_definition(session, signal_id)) is not None
        ]
        yaml_text = export_signal_group_pack(
            group.name,
            definitions,
            export_type=export_type,
            name=name,
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
