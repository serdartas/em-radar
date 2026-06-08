# EM Radar — Tech Stack Decision Record

## 1. Purpose

This document records the technology choices for **EM Radar** and the rationale behind them. Significant "X vs Y" forks have dedicated Architecture Decision Records (ADRs) in [`docs/ADRs/`](./ADRs/); this document is the index and the high-level rationale.

## 2. Selection Criteria

Every technology choice was evaluated against the same five criteria, in priority order:

1. **Free and open source.** No vendor billing, no closed runtime.
2. **Easy to use and low maintenance.** Minimal toolchain churn, minimal moving parts.
3. **Modern but not hype-driven.** Current, but not adopted for novelty. Will still be the right call in three years.
4. **Not old-fashioned.** Won't look dated to EMs or contributors evaluating the project.
5. **Safe for the target audience.** EMs comfortable with Docker but not coding daily should not be intimidated; contributors should not need exotic knowledge.

## 3. Stack Summary

| Layer | Choice | Considered Against | ADR |
|---|---|---|---|
| Backend framework | **FastAPI** | Django, Flask | [ADR-0001](./ADRs/0001-backend-framework.md) |
| Default database | **SQLite** | PostgreSQL, DuckDB | [ADR-0002](./ADRs/0002-default-database.md) |
| Frontend framework | **React + Vite** | HTMX + Jinja2, Vue, SvelteKit, Next.js | [ADR-0003](./ADRs/0003-frontend-framework.md) |
| UI component library | **Tailwind CSS + shadcn/ui** | Material UI, Chakra UI, Mantine, Bootstrap | [ADR-0004](./ADRs/0004-ui-component-library.md) |
| Python package manager | **uv** | Poetry, pip-tools, Hatch/PDM | [ADR-0005](./ADRs/0005-python-package-manager.md) |
| Token storage | **SQLite (masked)** | OS keyring, encrypted SQLite, env vars | [ADR-0006](./ADRs/0006-token-storage.md) |

## 4. The Choices

### 4.1 Backend — FastAPI

Python + FastAPI. Native async (parallel Jira/GitLab fetches), type-hint based validation via Pydantic, auto-generated OpenAPI for free TypeScript client generation, and a cohesive author ecosystem (FastAPI + Typer + SQLModel). Django is overkill for an API-only app; Flask requires too many extensions to reach parity.

→ See [ADR-0001](./ADRs/0001-backend-framework.md)

### 4.2 Storage — SQLite

Single file, zero ops, ships with Python. Perfect for local-first single-user. PostgreSQL is the right answer for enterprise/multi-user mode but introduces a second container, port, auth, and DBA mindset that doesn't fit the MVP persona. The data layer is built on SQLAlchemy / SQLModel so swapping in PostgreSQL later is mostly mechanical.

→ See [ADR-0002](./ADRs/0002-default-database.md)

### 4.3 Frontend — React + Vite

Largest contributor pool of any UI tech. Vite gives modern HMR and tiny build config. HTMX + Jinja2 was genuinely tempting on maintenance grounds, but loses on contributor reach and first-impression polish, both of which matter for an OSS project trying to build a community.

→ See [ADR-0003](./ADRs/0003-frontend-framework.md)

### 4.4 UI — Tailwind CSS + shadcn/ui

shadcn/ui copies accessible Radix-based components directly into our repo. We own the code, no vendor lock-in, no runtime CSS-in-JS overhead. Industry-standard combo by 2026.

→ See [ADR-0004](./ADRs/0004-ui-component-library.md)

### 4.5 Python tooling — uv

10–100× faster than Poetry, single tool for env + deps + Python install + lockfile, same vendor as Ruff (which we're also using), standards-aligned (`pyproject.toml`). Mainstream by 2026, no longer the bleeding-edge pick.

→ See [ADR-0005](./ADRs/0005-python-package-manager.md)

### 4.6 Token storage — SQLite with masking

Store tokens in the local SQLite database. Mask in UI, never log, exclude from exports, recommend read-only tokens. OS keyring is the right answer for a future desktop-native wrapper but adds Docker friction the MVP doesn't justify.

→ See [ADR-0006](./ADRs/0006-token-storage.md)

## 5. Minor Choices (no dedicated ADR)

These follow naturally from the major decisions or are too obvious to warrant a full ADR. Captured here for transparency.

| Concern | Choice | Reason |
|---|---|---|
| ORM layer | **SQLModel** on top of SQLAlchemy | Same author as FastAPI; pairs Pydantic models with SQLAlchemy tables; less boilerplate. |
| Migrations | **Alembic** | Standard for SQLAlchemy. Works with both SQLite and PostgreSQL. |
| Schema validation | **Pydantic v2** | Same models the API and ORM already use; powers YAML signal-pack validation. |
| HTTP client | **httpx** | Modern, async-friendly, drop-in replacement for `requests`. |
| CLI framework | **Typer** | Same author as FastAPI; uses type hints; near-zero maintenance. |
| Lint + format | **Ruff** | Replaces black + flake8 + isort with one tool. Same vendor as uv. |
| Python tests | **pytest** | Default for the Python ecosystem. |
| Frontend tests | **Vitest + Testing Library** | Native fit for Vite; ergonomic for React. |
| Frontend data layer | **TanStack Query** | Removes hand-rolled fetch/cache/retry/invalidation logic. |
| API client (frontend) | **Generated from FastAPI's OpenAPI** | Free, always-correct types end to end. |
| Containerization | **Docker + Docker Compose** | Matches the EM-comfortable-with-Docker persona; one-command local startup. |
| CI | **GitHub Actions** | Free for open source; ubiquitous. |
| License | **TBD** (recommended: **Apache-2.0**) | Friendly to the "private adapters on top of open core" model. To be confirmed before public release. |

## 6. What We Deliberately Did NOT Pick

To keep the rationale honest, here is what we considered and rejected at the stack level:

- **Node.js backend / TypeScript everywhere.** Would let CLI + backend + frontend share a language, but Python's data ergonomics and ecosystem for Jira/GitLab/signal logic win for our use case.
- **Go backend.** Single binary distribution is attractive, but a smaller contributor pool of EM-shaped engineers and weaker data-handling ergonomics than Python.
- **Kubernetes / Helm for MVP.** Out of scope per [vision-and-scope §15](./01-vision-and-scope.md). Local Docker is the MVP runtime; Helm is a Phase 6 concern.
- **Cloud-managed databases / serverless runtimes.** Conflicts with local-first by definition.
- **LLM in the runtime path.** Out of MVP scope per [vision-and-scope §3.2](./01-vision-and-scope.md). AI remains optional and external.
- **Monorepo tooling (Nx, Turborepo).** Plain folder layout is enough at our scale. Add only if a real pain emerges.

## 7. Things to Revisit Later

These are not undecided. They are decisions whose right answer depends on conditions that don't exist yet.

- **PostgreSQL support.** Needed when enterprise/multi-user mode begins.
- **Stronger token storage.** Needed if/when we ship a desktop-native wrapper or an enterprise build.
- **Desktop wrapper** (Tauri / Electron). Optional later distribution.
- **Telemetry framework.** Opt-in only, design before any anonymous usage data is ever sent.
- **Marketplace backend.** Initial version can be a public GitHub repository serving signal-pack YAML; a real registry comes only if scale demands it.

## 8. How New ADRs Should Be Added

When a future "X vs Y" decision arises:

1. Create `docs/ADRs/NNNN-short-title.md` using the existing ADRs as a template (Context → Decision → Alternatives → Consequences → Revisit-when).
2. Add a row to the table in §3 (or §5 for minor decisions).
3. Link the ADR from any other document that depends on the decision (architecture, requirements, etc.).
4. Never edit an Accepted ADR in place. Supersede it with a new one and mark the old one `Status: Superseded by ADR-NNNN`.
