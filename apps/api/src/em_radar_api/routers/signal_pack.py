# SPDX-License-Identifier: Apache-2.0

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session
from starlette.responses import Response

from em_radar_api.db import get_session, get_write_session
from em_radar_api.repositories.signal_config_groups import get_signal_config_group
from em_radar_api.repositories.signal_definitions import get_signal_definition
from em_radar_api.signal_pack_export import export_signal_groups_pack
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
    conflict: Literal["skip", "overwrite", "keep_both", "cancel"] = "keep_both"


@router.get("/signal-pack/export")
def export_signal_pack_route(
    export_type: Literal["private_backup", "public_template"] = "private_backup",
    group_ids: list[UUID] = Query(default=[]),
    name: PackName = None,
    session: Session = Depends(get_session),
) -> Response:
    if not group_ids:
        raise HTTPException(status_code=422, detail="group_ids is required")
    groups = []
    for group_id in group_ids:
        group = get_signal_config_group(session, group_id)
        if group is None:
            raise HTTPException(status_code=404, detail="signal config group not found")
        groups.append(group)
    definitions_by_id = {
        signal_id: definition
        for group in groups
        for signal_id in group.signal_ids
        if (definition := get_signal_definition(session, signal_id)) is not None
    }
    try:
        yaml_text = export_signal_groups_pack(
            groups,
            definitions_by_id,
            export_type=export_type,
            name=name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(
        content=yaml_text,
        media_type="application/yaml",
        headers={"Content-Disposition": 'attachment; filename="signal-pack.yaml"'},
    )


@router.post(
    "/signal-pack/import",
    response_model=SignalPackImportPreview,
)
def preview_signal_pack_import_route(
    request: SignalPackImportRequest,
    session: Session = Depends(get_session),
) -> SignalPackImportPreview:
    if request.mode == "replace_all":
        raise HTTPException(status_code=422, detail="replace_all mode is not yet supported")
    try:
        return preview_signal_pack_import(
            session,
            request.raw_yaml,
            replace_all=False,
        )
    except PackValidationError as error:
        raise _invalid_pack(error) from error


@router.post(
    "/signal-pack/import/apply",
    response_model=SignalPackImportPreview,
)
def apply_signal_pack_import_route(
    request: SignalPackImportRequest,
    session: Session = Depends(get_write_session),
) -> SignalPackImportPreview:
    if request.mode == "replace_all":
        raise HTTPException(status_code=422, detail="replace_all mode is not yet supported")
    try:
        return apply_signal_pack_import(
            session,
            request.raw_yaml,
            replace_all=False,
            conflict=request.conflict,
        )
    except PackValidationError as error:
        raise _invalid_pack(error) from error


def _invalid_pack(error: PackValidationError) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={"code": "invalid-signal-pack", "message": str(error)},
    )
