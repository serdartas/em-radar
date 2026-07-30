from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from em_radar_api.db import session_factory
from em_radar_api.routers.connectors import router as connectors_router
from em_radar_api.routers.health import router as health_router
from em_radar_api.routers.reports import router as reports_router
from em_radar_api.routers.scopes import router as scopes_router
from em_radar_api.routers.signal_config_groups import router as signal_config_groups_router
from em_radar_api.routers.signal_configs import router as signal_configs_router
from em_radar_api.routers.signal_definitions import router as signal_definitions_router
from em_radar_api.routers.signal_pack import router as signal_pack_router
from em_radar_api.routers.source_connections import router as source_connections_router
from em_radar_api.routers.teams import router as teams_router
from em_radar_api.startup import seed_default_signal_configs, seed_default_signal_group


class SPAStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            response = await super().get_response(path, scope)
        except HTTPException as error:
            if error.status_code != 404 or _is_api_path(scope["path"]):
                raise
            return await super().get_response("index.html", scope)

        if response.status_code == 404 and not _is_api_path(scope["path"]):
            return await super().get_response("index.html", scope)
        return response


def _is_api_path(path: str) -> bool:
    return path == "/api" or path.startswith("/api/")


def create_app(
    static_dir: Path | None = None,
    app_session_factory: sessionmaker[Session] = session_factory,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        del app
        seed_default_signal_configs(app_session_factory)
        seed_default_signal_group(app_session_factory)
        yield

    app = FastAPI(title="EM Radar", lifespan=lifespan)
    app.include_router(connectors_router, prefix="/api")
    app.include_router(health_router, prefix="/api")
    app.include_router(reports_router, prefix="/api")
    app.include_router(scopes_router, prefix="/api")
    app.include_router(signal_config_groups_router, prefix="/api")
    app.include_router(signal_configs_router, prefix="/api")
    app.include_router(signal_definitions_router, prefix="/api")
    app.include_router(signal_pack_router, prefix="/api")
    app.include_router(source_connections_router, prefix="/api")
    app.include_router(teams_router, prefix="/api")

    static_dir = static_dir or Path(__file__).parent / "static"
    if static_dir.is_dir():
        app.mount("/", SPAStaticFiles(directory=static_dir, html=True), name="spa")

    return app


app = create_app()
