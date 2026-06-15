from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session
from starlette.responses import Response

from em_radar_api.db import get_session
from em_radar_api.repositories.signal_configs import list_signal_configs
from em_radar_api.signal_pack_export import export_signal_pack

router = APIRouter()

PackName = Annotated[
    str | None,
    Query(pattern=r"^[a-z][a-z0-9-]{1,62}[a-z0-9]$"),
]


@router.get("/signal-pack/export")
def export_signal_pack_route(
    mode: Literal["minimal", "full"] = "minimal",
    name: PackName = None,
    session: Session = Depends(get_session),
) -> Response:
    yaml_text = export_signal_pack(
        list_signal_configs(session),
        full=mode == "full",
        name=name,
    )
    return Response(
        content=yaml_text,
        media_type="application/yaml",
        headers={"Content-Disposition": 'attachment; filename="signal-pack.yaml"'},
    )
