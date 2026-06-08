# ADR-0001: Backend framework — FastAPI

- **Status:** Accepted
- **Date:** 2026-06-01
- **Deciders:** Serdar Tas
- **Related:** [04-tech-stack.md](../04-tech-stack.md)

## Context

EM Radar needs a backend HTTP framework. Concrete needs:

- Serve a JSON API to the React frontend.
- Fetch from Jira and GitLab in parallel (I/O-bound, latency-sensitive).
- Validate inputs and YAML signal-pack imports against typed schemas.
- Publish an OpenAPI spec we can use to generate a TypeScript client for the frontend.
- Stay readable for contributors who are EMs with rusty Python. (minimal magic, conventional code)
- Free, open source, low maintenance, modern but not bleeding-edge.

## Decision

Use **FastAPI** for the backend.

## Alternatives considered

### Django
- **Strengths:** Mature (since 2005), batteries-included (ORM, admin, auth, templates, forms), huge ecosystem.
- **Weaknesses:** Built for server-rendered apps with HTML templates and a relational ORM-first worldview. We're API-only with a React frontend, so admin/templates/forms are dead weight. Django REST Framework adds boilerplate and is currently in a slow maintenance phase. Async support exists but is grafted on rather than native. Heavier startup, more cognitive overhead for what we need.
- **Verdict:** Excellent for full-stack server-rendered apps; overkill and mis-shaped for an API-first local tool.

### Flask
- **Strengths:** Minimal, mature (since 2010), extremely well-known, low-magic.
- **Weaknesses:** No native async/await (parallel Jira+GitLab fetches matter for report latency). No built-in typed request/response validation. No automatic OpenAPI generation. To match FastAPI's feature set you stack Flask-RESTful + marshmallow + apispec + Flask-Pydantic. More moving parts, more places for things to drift.
- **Verdict:** Solid but old-shaped. Reaching parity costs more than just adopting FastAPI.

### FastAPI
- **Strengths:** Native `async`/`await`. Type-hint based validation via Pydantic — the same models we use everywhere else. Auto-generated OpenAPI/JSON Schema (free TypeScript client generation, free Swagger UI). Cohesive ecosystem with **Typer** (our CLI) and **SQLModel** (our ORM layer) by the same author. Modern Python idioms, low boilerplate, fast.
- **Weaknesses:** Smaller plugin ecosystem than Flask/Django. Not "batteries included", we provide our own auth flow if we ever need one.

## Consequences

### Positive
- Async-first matches our I/O profile (parallel source fetches).
- One type system from API boundary to ORM (FastAPI → Pydantic → SQLModel).
- Free OpenAPI → free, always-correct TypeScript client for the React app.
- Cohesive author ecosystem (FastAPI + Typer + SQLModel) reduces glue code.
- Modern Python (3.11+) keeps the codebase readable to ex-coding EMs.

### Negative
- Fewer pre-built admin/auth conveniences than Django (we don't need them in MVP).
- Pydantic v2 migration / breaking changes in the Python typing world require occasional upkeep.

## Revisit when

- We need a polished server-rendered admin UI (Django would shine).
- We need a richer plugin ecosystem we cannot assemble ourselves.
- Async stops being a meaningful benefit (it won't — Jira+GitLab parallelism is core).
