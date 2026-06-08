# EM Radar — Agent Instructions

This file is the authoritative context for coding agents (Codex, Claude Code, etc.) working
on this repository. Read it before touching any code. Follow every constraint exactly —
these are not suggestions.

---

## 1. What this project is

EM Radar is a local-first engineering management signal engine. It connects to Jira and
GitLab, normalizes their data, evaluates configurable deterministic signals, and produces
actionable reports. See `docs/03-architecture-overview.md` for the full architecture.

---

## 2. Stack — do not substitute

| Layer | Choice | Do not use |
|---|---|---|
| Python package manager | `uv` | pip, Poetry, Hatch, PDM |
| Python lint + format | `ruff` | black, flake8, isort, pylint |
| Python tests | `pytest` | unittest, nose |
| Python HTTP client | `httpx` | requests, aiohttp |
| Python web framework | `fastapi` | Django, Flask, Litestar |
| ORM | `sqlmodel` + `sqlalchemy` | tortoise, peewee, raw SQL models |
| Migrations | `alembic` | anything else |
| Schema validation | `pydantic v2` | marshmallow, attrs, dataclasses alone |
| CLI framework | `typer` | click, argparse |
| Node package manager | `npm` | yarn, pnpm, bun |
| Frontend library | React (via `vite` + TypeScript template) | Next.js, Vue, SvelteKit, HTMX |
| UI components | `shadcn/ui` + `tailwind` | MUI, Chakra, Mantine, Bootstrap |
| Frontend data layer | `@tanstack/react-query` | SWR, Redux, hand-rolled fetch |
| Frontend tests | `vitest` + `@testing-library/react` | Jest, Cypress (for unit/component) |
| Container | `docker` + `docker compose` | Podman, Kubernetes |

Python version: **3.12**. Do not add `typing_extensions` workarounds for features available
in 3.12.

---

## 3. Repository layout

```text
em-radar/
  apps/
    api/   src/em_radar_api/        # FastAPI app: routers, schemas, db session
    web/   src/                     # React + Vite + TS + Tailwind + shadcn/ui
    cli/   src/em_radar_cli/        # Typer CLI — scaffold only, deferred post-MVP
  packages/
    core/        src/em_radar_core/{models,signals,evaluation,scoring}
    connectors/  jira/  gitlab/  demo/
    normalizer/  src/em_radar_normalizer/
    reports/     src/em_radar_reports/
    config/      src/em_radar_config/  defaults/  schemas/
  deploy/docker/   Dockerfile  docker-compose.yml
  examples/fake-company/
  docs/
```

---

## 4. Python package names

Use these exactly — they are referenced by connector entry points and cross-package imports.

| Component | Import package |
|---|---|
| API | `em_radar_api` |
| Core | `em_radar_core` |
| Normalizer | `em_radar_normalizer` |
| Reports | `em_radar_reports` |
| Config | `em_radar_config` |
| Jira connector | `em_radar_connector_jira` |
| GitLab connector | `em_radar_connector_gitlab` |
| Demo connector | `em_radar_connector_demo` |

---

## 5. Runtime constants

Do not hardcode alternatives to these values.

| Constant | Value |
|---|---|
| App URL / port | `http://localhost:8080` |
| API prefix | `/api` (all routes; UI served at `/`) |
| Health endpoint | `GET /api/health` → `{"status": "ok"}` |
| DB path (in container) | `/data/em-radar.db` |
| Signal schema id | `emradar.dev/v1` |
| Work-item key pattern | `[A-Z]+-\d+` |

---

## 6. Critical rules

**Determinism.** Signals compute ages and staleness against an injected
`EvaluationContext.now` (the report's start time). Never call `datetime.now()` or
`datetime.utcnow()` inline inside signal or evaluation logic. This makes demo runs and
tests reproducible.

**API prefix.** Every backend route is mounted under `/api`. The SPA is served at `/`; any
non-`/api` path must fall back to `index.html` for client-side routing.

**Token safety.** Credentials are never logged, never included in YAML exports, and always
masked in the UI. Do not add debug logging that could leak token values.

**Signal engine is source-agnostic.** The signal engine evaluates canonical models only
(`WorkItem`, `MergeRequest`, etc.). It must never import from a connector package or call
Jira/GitLab APIs directly.

**No AI in the runtime path.** The MVP engine is deterministic. Do not add LLM calls,
embeddings, or AI provider dependencies to any core or connector package.

**CLI is deferred.** `apps/cli/` is scaffolded but empty in MVP. Do not implement Typer
commands unless the issue explicitly targets the CLI.

---

## 7. Code style

**Python**
- Ruff: line length 100, target `py312`.
- Type-hint all function signatures.
- No `Any` unless unavoidable and commented.
- No comments explaining *what* the code does — only *why* when non-obvious.

**TypeScript / React**
- Strict TypeScript (`strict: true`).
- Functional components only; no class components.
- No `any`; use `unknown` and narrow.

**General**
- No redundant comments that restate the code. Docstrings are welcome on public APIs
  (connectors, signal definitions, core models) but not required on private helpers.
- No backwards-compatibility shims for removed code.
- No feature flags in MVP code.

---

## 8. Tests

- Every issue that ships behavior ships with a test.
- Scaffolding and docs issues are exempt.
- Backend: `pytest` with `httpx.AsyncClient` / `TestClient` for route tests.
- Frontend: `vitest` + `@testing-library/react` for component tests.
- Do not mock the database in integration tests — use an in-memory SQLite instance.
- Signal tests use fixture canonical models with a fixed `EvaluationContext.now`.

---

## 9. Issue workflow

Issues are defined in `docs/backlog/`. Each issue has:
- A `Depends on` list — do not start an issue until its dependencies are merged.
- A `Scope` — implement exactly what is listed, nothing more.
- An `Out of scope` — do not implement these even if they seem natural.
- A `Verification` — the issue is done when this passes, not before.

When implementing an issue, reference it in the PR as `Fixes #<n>`.

---

## 10. Spec documents

Always check the relevant spec before implementing. The specs are authoritative.

| Document | What it governs |
|---|---|
| `docs/01-vision-and-scope.md` | Product principles, what is and is not in MVP |
| `docs/02-requirements.md` | Functional and non-functional requirements |
| `docs/03-architecture-overview.md` | Layer boundaries, canonical models, deployment |
| `docs/04-tech-stack.md` | Stack choices and ADRs |
| `docs/05-data-model.md` | Canonical model schemas |
| `docs/06-signal-yaml-spec.md` | Signal pack YAML format |
| `docs/07-connector-interface.md` | Connector contract and entry points |
| `docs/08-mvp-roadmap.md` | Milestone sequencing; what is in v0.1 vs deferred |
| `docs/09-functional-flows.md` | End-to-end user flows |
| `docs/10-er-diagram.md` | Entity-relationship diagram for the data model |
| `docs/backlog/` | Implementation issues (M0–M7, v0.1.0) |
