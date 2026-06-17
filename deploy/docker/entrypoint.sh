#!/bin/sh
set -eu

uv run --no-sync alembic -c /app/alembic.ini upgrade head
exec uv run --no-sync uvicorn em_radar_api.main:app --host 0.0.0.0 --port 8080
