FROM node:22-bookworm-slim AS web-builder

WORKDIR /build/apps/web

COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci

COPY apps/web/ ./
RUN npm run build


FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml ./
COPY packages/core/src ./packages/core/src
COPY packages/connectors/demo/src ./packages/connectors/demo/src
COPY apps/api/pyproject.toml apps/api/uv.lock ./apps/api/
COPY apps/api/src ./apps/api/src
COPY alembic.ini ./
COPY migrations ./migrations
COPY deploy/docker/entrypoint.sh ./deploy/docker/entrypoint.sh

WORKDIR /app/apps/api
RUN uv sync --frozen --no-dev

COPY --from=web-builder /build/apps/web/dist ./src/em_radar_api/static

EXPOSE 8080

CMD ["/app/deploy/docker/entrypoint.sh"]
