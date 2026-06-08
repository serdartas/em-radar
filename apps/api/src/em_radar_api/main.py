from fastapi import FastAPI

from em_radar_api.routers.health import router as health_router


def create_app() -> FastAPI:
    app = FastAPI(title="EM Radar")
    app.include_router(health_router, prefix="/api")
    return app


app = create_app()
