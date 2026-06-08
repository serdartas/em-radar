# ADR-0002: Default database — SQLite

- **Status:** Accepted
- **Date:** 2026-06-01
- **Deciders:** Serdar Tas
- **Related:** [04-tech-stack.md](../04-tech-stack.md), [01-vision-and-scope.md](../01-vision-and-scope.md), [02-requirements.md](../02-requirements.md) (REQ-F-003, REQ-F-004)

## Context

EM Radar is **local-first**. The MVP target user is a single EM on their laptop, running EM Radar in Docker. Storage requirements:

- Persist connector config, signal config, normalized source data cache, generated reports, findings.
- Survive container restart from a mounted local volume.
- Work offline.
- Be trivial to set up (no separate server, no port management, no users/passwords).
- Be trivial to back up and delete ("copy this file" / "delete this file").

Write volume is low: periodic data refresh + occasional config edits. Read volume is moderate during report generation.

A future enterprise/multi-user mode is anticipated but explicitly out of MVP scope.

## Decision

Use **SQLite** as the default storage engine for MVP and single-user deployments. Architect the data layer (SQLModel / SQLAlchemy) so that **PostgreSQL** can be swapped in later for enterprise/multi-user deployments without rewriting application code.

## Alternatives considered

### PostgreSQL
- **Strengths:** Multi-writer concurrency, mature JSON/JSONB ops, full-text search, mature replication, role-based access, the obvious choice for any server-side app.
- **Weaknesses for our case:**
  - Requires a second Docker container (or external server).
  - Requires a port, a user, a password, an init script.
  - More memory at idle than SQLite (which uses ~0 when not queried).
  - "Copy my data" / "delete my data" is not a single-file operation.
  - Network failures between containers become a new failure mode.
  - More friction for the "EM comfortable with Docker but not a DBA" persona.
- **Verdict:** Right answer for enterprise/multi-user. Overkill and friction-heavy for local-first single-user.

### SQLite
- **Strengths:**
  - Single file. Ships with Python's stdlib.
  - Zero configuration. No server, no port, no auth.
  - One Docker container instead of two.
  - Trivial backup (copy the `.db` file) and trivial deletion (delete the file).
  - Works offline by definition.
  - Plenty fast for our data size (REQ-NF-020: up to 500 work items / 300 MRs per window).
- **Weaknesses:**
  - One writer at a time (a non-issue for single-user, careful design needed if we ever expose it to multiple users, at which point we'd switch to PG anyway).
  - No multi-machine access.
  - Lacks some Postgres-only features (advanced JSON ops, partial indexes are simpler in PG, no built-in full-text search beyond FTS5).

### DuckDB
- **Strengths:** Excellent for analytical workloads, columnar, embedded.
- **Weaknesses:** Optimized for OLAP, not OLTP. Mixing config writes and report generation in DuckDB would be unusual. Smaller community.
- **Verdict:** Not a fit for the mixed config-store + cache + reports workload.

## Consequences

### Positive
- Simplest possible "docker compose up" experience. One container, one volume.
- Backup/restore is `cp em-radar.db em-radar.db.bak`.
- Privacy story is crisp: one file, on the user's disk, period.
- Lower memory footprint, suitable for laptops.

### Negative
- Single-writer limitation: if we ever support concurrent users on a shared instance, we must switch to PostgreSQL.
- Some Postgres-native niceties (e.g. richer JSON querying) are not available. Acceptable for MVP signal logic.

## Mitigation

- Use **SQLAlchemy / SQLModel** so the migration path to PostgreSQL is mostly mechanical.
- Keep custom SQL to a minimum; prefer ORM-level expressions that work on both engines.
- Use Alembic for schema migrations from day one.

## Revisit when

- We start work on enterprise/multi-user mode (per architecture doc §17.2). At that point, add PostgreSQL as an alternative engine, not a replacement. SQLite stays as the local-first default.
- We need full-text search beyond what SQLite FTS5 provides.
