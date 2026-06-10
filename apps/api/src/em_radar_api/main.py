from pathlib import Path

from fastapi import FastAPI
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from em_radar_api.routers.health import router as health_router
from em_radar_api.routers.reports import router as reports_router


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


def create_app(static_dir: Path | None = None) -> FastAPI:
    app = FastAPI(title="EM Radar")
    app.include_router(health_router, prefix="/api")
    app.include_router(reports_router, prefix="/api")

    static_dir = static_dir or Path(__file__).parent / "static"
    if static_dir.is_dir():
        app.mount("/", SPAStaticFiles(directory=static_dir, html=True), name="spa")

    return app


app = create_app()
