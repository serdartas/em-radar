# SPDX-License-Identifier: Apache-2.0

from fastapi import APIRouter

from em_radar_api.connector_registry import list_connectors

router = APIRouter()


@router.get("/connectors")
def connectors() -> list[dict[str, object]]:
    return list_connectors()
