FROM node:22-bookworm-slim AS web-builder

WORKDIR /build/apps/web

COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci

COPY apps/web/ ./
RUN npm run build


FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY apps/api/pyproject.toml apps/api/uv.lock ./
COPY apps/api/src ./src
RUN uv sync --frozen --no-dev

COPY --from=web-builder /build/apps/web/dist ./src/em_radar_api/static

EXPOSE 8080

CMD ["uv", "run", "--no-sync", "uvicorn", "em_radar_api.main:app", "--host", "0.0.0.0", "--port", "8080"]
