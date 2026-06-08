# EM Radar

> Status: pre-alpha. Foundations are being built; EM Radar is not yet usable.
> APIs, schema, signals, and repository structure will change without notice.

EM Radar is a local-first engineering management signal engine for Engineering Managers who want earlier visibility into planning, delivery, and code-review risks.

It connects to tools like Jira, GitLab, and GitHub, normalizes the data into a source-agnostic model, evaluates configurable signals, and produces actionable reports for sprint reviews, planning, one-on-ones, and team health checks.

The goal is not to build another generic dashboard. EM Radar is designed to help Engineering Managers answer one practical question:

> What should I pay attention to before this becomes a delivery, quality, or team-health problem?

Example signals EM Radar may help surface:

- tickets entering development without enough readiness
- pull requests waiting too long for review
- work items repeatedly blocked or reopened
- delivery risk increasing during a sprint
- uneven review or ownership patterns
- trends that should be discussed with the team before they become incidents

## Principles

- Local-first. Runs on your machine via Docker. Data, tokens, and reports stay local; telemetry is off by default. No company data is sent to an external SaaS.
- Rules-first, AI-optional. The engine is deterministic and rule-based. AI may be added later as an optional external component, but the core product will not depend on LLMs.
- Source-agnostic core. Source systems are accessed through connectors that normalize their data into a canonical model. The signal engine never talks to Jira, GitLab, or GitHub directly.
- Team improvement, not surveillance. EM Radar is intended to support better conversations, earlier risk detection, and healthier delivery systems, not individual performance scoring.
- Open generic core, private company context. The generic engine, connectors, and default signal packs are open source. Company-specific mappings, thresholds, and adapters can live outside this repo.

## Quick start

> Not yet functional — tracked in M0 — Foundations.

```bash
docker compose -f deploy/docker/docker-compose.yml up --build
```

Then open http://localhost:8080.

## Development

This is a monorepo: a Python FastAPI backend and a React Vite frontend, built into a single container that serves the UI at / and the API under /api.

Prerequisites: uv with Python 3.12+, Node.js, and Docker.

Backend (apps/api):

```bash
cd apps/api
uv sync
uv run uvicorn em_radar_api.main:app --port 8080
uv run pytest
uv run ruff check .
```

Frontend (apps/web):

```bash
cd apps/web
npm install
npm run dev
npm run test
npm run build
```

## Repository layout

```text
apps/
  api/   src/em_radar_api/        # FastAPI app: routers, schemas, db session
  web/   src/                     # React + Vite + TypeScript + Tailwind + shadcn/ui
  cli/   src/em_radar_cli/        # Typer CLI scaffold; deferred post-MVP
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

## Tech stack

Python 3.12 + FastAPI, SQLModel/SQLAlchemy/Alembic, Pydantic v2, httpx, Typer, Ruff, pytest ·
React + Vite + TypeScript, Tailwind + shadcn/ui, TanStack Query, Vitest + Testing Library ·
uv for Python and npm for web · Docker + Docker Compose · SQLite by default.

See docs/04-tech-stack.md for the rationale and per-decision ADRs.

## Documentation

Specs live in docs/:

- vision & scope
- requirements
- architecture
- tech stack
- data model
- signal YAML spec
- connector interface
- MVP roadmap
- functional flows

The implementation backlog slices the work into issues.

## License

Apache-2.0 © Serdar Tas
