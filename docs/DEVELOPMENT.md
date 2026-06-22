# Development & Debugging Guide

This guide covers running EM Radar **locally without Docker**, connecting to the database,
debugging the backend and frontend, and common troubleshooting. It complements
[`CONTRIBUTING.md`](../CONTRIBUTING.md) (the contribution *process*) and
[`AGENTS.md`](../AGENTS.md) (the binding conventions). For architecture and data-model
details, see [`docs/`](.).

> **Never commit credentials.** Real Jira/GitLab tokens must never appear in this repo,
> in `.env` files that get committed, in logs, or in YAML exports. Use placeholders. See
> [`SECURITY.md`](../SECURITY.md) and the token-safety rule in
> [`AGENTS.md`](../AGENTS.md).

---

## 1. Two ways to run

| Mode | What it gives you | When to use |
|---|---|---|
| **Docker** (`docker compose`) | Full stack, production-like, frontend built and served by the API at `http://localhost:8080` | Smoke-testing the whole app, reproducing prod behavior |
| **Local (no Docker)** | Backend with `--reload`, frontend with HMR, a debugger attached, direct DB access | Day-to-day development and debugging |

The Docker flow is documented in [`CONTRIBUTING.md` §3](../CONTRIBUTING.md). The rest of this
guide is about the **local** flow.

---

## 2. Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python 3.12 — the repo pins `>=3.12,<3.13`)
- Node.js (LTS) and npm
- `sqlite3` CLI (optional, for inspecting the database)

---

## 3. Running the backend locally

The API lives in `apps/api` and has its own uv environment.

### 3.1 Point the database somewhere writable

By default the API opens the SQLite database at `/data/em-radar.db` (the in-container path).
That directory does not exist on your machine, so **set `EM_RADAR_DATABASE_PATH`** to a local
file before doing anything else:

```bash
export EM_RADAR_DATABASE_PATH="$PWD/.local/em-radar.db"
mkdir -p "$(dirname "$EM_RADAR_DATABASE_PATH")"
```

`.local/` is a good choice — `*.db`, `*.sqlite`, and `*.sqlite3` are already gitignored, so
the database file will not be accidentally committed.

### 3.2 Install dependencies

```bash
cd apps/api
uv sync          # creates apps/api/.venv and installs deps
```

### 3.3 Apply migrations

Migrations are **not** run automatically when the API starts (only the default signal
configs are seeded). You must run them yourself — this mirrors what
`deploy/docker/entrypoint.sh` does in the container:

```bash
# from apps/api, with EM_RADAR_DATABASE_PATH exported
uv run alembic -c ../../alembic.ini upgrade head
```

`alembic.ini` lives at the repo root; `migrations/env.py` builds its engine from
`EM_RADAR_DATABASE_PATH`, so the same env var drives both migrations and the running app.

### 3.4 Start the API with auto-reload

```bash
uv run uvicorn em_radar_api.main:app --reload --port 8080
```

Verify it is up:

```bash
curl http://localhost:8080/api/health     # → {"status":"ok"}
```

### 3.5 Interactive API docs

When you run the backend locally **without** a built frontend, FastAPI's interactive docs are
available at:

- Swagger UI: `http://localhost:8080/docs`
- OpenAPI schema: `http://localhost:8080/openapi.json`

(Once a built SPA is mounted at `/` — see §4.2 — the SPA owns the root path, but `/docs`
still resolves because it is an explicit route. All application routes are under `/api`.)

---

## 4. Running the frontend locally

The web app lives in `apps/web` (React + Vite + TypeScript).

```bash
cd apps/web
npm install
npm run dev       # Vite dev server with HMR, default http://localhost:5173
```

### 4.1 Connecting the dev server to the API

The frontend chooses its API base from `VITE_API_BASE_URL` (default `/api`, see
`apps/web/.env.example` and `apps/web/src/lib/api.ts`). The backend does **not** enable CORS,
so a browser on `:5173` cannot fetch `http://localhost:8080` cross-origin directly. Instead,
`apps/web/vite.config.ts` ships a **same-origin proxy** that forwards `/api` requests from the
dev server to the API:

```ts
server: {
  proxy: {
    "/api": "http://localhost:8080",
  },
},
```

So just start the API on `:8080`, run `npm run dev`, and leave `VITE_API_BASE_URL` at its
default (`/api`): you get HMR on `:5173` while requests reach the API on `:8080`. No extra
configuration needed.

### 4.2 Alternative: serve the built SPA from the API

For a production-like single-origin run without Docker, build the web app into the location
the API serves static files from (`apps/api/src/em_radar_api/static`):

```bash
cd apps/web && npm run build
cp -r dist/. ../api/src/em_radar_api/static/
```

Restart the API and open `http://localhost:8080` — the SPA is served at `/` with client-side
routing falling back to `index.html`. This loses HMR; it is only useful for verifying the
served-together behavior. The `static/` directory is build output, so do not commit it.

---

## 5. The database

| Fact | Value |
|---|---|
| Engine | SQLite (file-based) |
| Local path | whatever `EM_RADAR_DATABASE_PATH` points at |
| Default path | `/data/em-radar.db` (in-container only) |
| Pragmas | `journal_mode=WAL`, `foreign_keys=ON` |

Because WAL is enabled, you will see `-wal` and `-shm` sidecar files next to the database —
that is expected.

### 5.1 Inspecting the database

```bash
sqlite3 "$EM_RADAR_DATABASE_PATH"
```

```
.tables                 -- list tables
.schema source_connections
SELECT * FROM signal_config;
.quit
```

Any GUI works too (DB Browser for SQLite, the JetBrains database tools, etc.) — just point it
at the file in `EM_RADAR_DATABASE_PATH`.

### 5.2 Migrations (alembic)

All commands run from `apps/api` with `EM_RADAR_DATABASE_PATH` exported, using
`-c ../../alembic.ini`:

```bash
uv run alembic -c ../../alembic.ini upgrade head        # apply all migrations
uv run alembic -c ../../alembic.ini current             # show current revision
uv run alembic -c ../../alembic.ini history              # list revisions
uv run alembic -c ../../alembic.ini downgrade -1         # roll back one revision
uv run alembic -c ../../alembic.ini revision --autogenerate -m "add X table"
```

Autogenerate compares `SQLModel.metadata` (all tables registered via
`em_radar_api.tables`) against the current database. Always review the generated migration
before committing — autogenerate is a starting point, not the final word.

### 5.3 Resetting the database

The fastest reset is to delete the file and re-migrate:

```bash
rm -f "$EM_RADAR_DATABASE_PATH" "$EM_RADAR_DATABASE_PATH"-wal "$EM_RADAR_DATABASE_PATH"-shm
uv run alembic -c ../../alembic.ini upgrade head
```

On the next API start, default signal configs are re-seeded from
`packages/config/defaults/default-pack.yaml`.

---

## 6. Debugging

### 6.1 Backend — VS Code

Create `.vscode/launch.json` (gitignored, so it stays local):

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "EM Radar API",
      "type": "debugpy",
      "request": "launch",
      "module": "uvicorn",
      "args": ["em_radar_api.main:app", "--reload", "--port", "8080"],
      "cwd": "${workspaceFolder}/apps/api",
      "python": "${workspaceFolder}/apps/api/.venv/bin/python",
      "env": { "EM_RADAR_DATABASE_PATH": "${workspaceFolder}/.local/em-radar.db" },
      "jinja": false
    }
  ]
}
```

> With `--reload`, the reloader runs your app in a child process. If breakpoints don't bind,
> drop `--reload` for the debug session.

### 6.2 Backend — PyCharm / other

Configure a Python run config: module `uvicorn`, parameters
`em_radar_api.main:app --port 8080`, working directory `apps/api`, interpreter
`apps/api/.venv`, and an env var `EM_RADAR_DATABASE_PATH`.

### 6.3 Backend — ad-hoc

Drop a `breakpoint()` into any handler and run uvicorn **without** `--reload` in a terminal to
get an interactive `pdb` prompt.

### 6.4 Frontend

- Use the browser devtools and the React Developer Tools extension. Vite ships source maps in
  dev, so breakpoints map back to the `.tsx` sources.
- TanStack Query is the data layer; its devtools (if added) or the Network tab show request
  state and cache behavior.

---

## 7. Environment variables

| Variable | Used by | Default | Notes |
|---|---|---|---|
| `EM_RADAR_DATABASE_PATH` | API + alembic | `/data/em-radar.db` | Set to a local writable path for local dev |
| `VITE_API_BASE_URL` | web | `/api` | Build/dev-time; leave at `/api` and use the Vite proxy (§4.1) |

`.env` is gitignored at the repo root; `apps/web/.env.example` documents the frontend var.
Never commit a real `.env` containing tokens.

---

## 8. Tests, lint, and format (quick reference)

Full rules live in [`AGENTS.md` §7–8](../AGENTS.md) and [`CONTRIBUTING.md`](../CONTRIBUTING.md).

```bash
# Backend (from apps/api)
uv run pytest
uv run ruff check .
uv run ruff format .

# Frontend (from apps/web)
npm run test      # Vitest
npm run lint      # ESLint
npm run build     # type-check + production build
```

Backend tests use an isolated temporary SQLite database per test (see
`apps/api/tests/conftest.py`); they do not touch `EM_RADAR_DATABASE_PATH` and never need a
running server.

---

## 9. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `sqlite3.OperationalError: unable to open database file` | `EM_RADAR_DATABASE_PATH` points at a directory that doesn't exist, or the default `/data` isn't writable. Set it to a local path and `mkdir -p` the parent (§3.1). |
| API returns 404 for `/api/...` | Route is mounted under `/api`; check the path prefix. Non-`/api` paths fall back to the SPA's `index.html`. |
| Frontend calls fail in the browser console (CORS / connection refused) | The API doesn't enable CORS. Use the Vite proxy in §4.1 instead of pointing `VITE_API_BASE_URL` at `http://localhost:8080`. |
| `Address already in use` on port 8080 | Another process (often a stale uvicorn or a running container) holds the port. Stop it, or run uvicorn on a different `--port`. |
| Migration errors / schema looks stale | You started the API without running `alembic upgrade head`. Migrations are not automatic locally (§3.3). |
| Tables missing after pointing at a new DB file | New file → run migrations against it. |
| `*.db-wal` / `*.db-shm` files appear | Expected (WAL mode). Delete them alongside the `.db` only when resetting (§5.3). |
| `uv run` fails resolving the interpreter | Re-create the env: `rm -rf .venv && uv sync` in the relevant app directory. |
