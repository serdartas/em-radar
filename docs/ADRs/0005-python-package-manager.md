# ADR-0005: Python package manager — uv

- **Status:** Accepted
- **Date:** 2026-06-01
- **Deciders:** Serdar Tas
- **Related:** [04-tech-stack.md](../04-tech-stack.md), [ADR-0001](./0001-backend-framework.md)

## Context

EM Radar's backend is Python. We need:

- Deterministic dependency resolution with a lockfile.
- Virtual environment management.
- Python version management (contributors may have 3.10/3.11/3.12 installed).
- Fast CI installs.
- A familiar workflow for contributors.

## Decision

Use **uv** (by Astral) as the Python package manager, virtual environment manager, and Python installer.

## Alternatives considered

### pip + requirements.txt
- **Strengths:** Built into Python. Everyone knows it.
- **Weaknesses:** No real lockfile semantics (requirements.txt vs. requirements-lock.txt patterns are ad hoc). Manual venv creation. No Python version management. Slow.
- **Verdict:** Insufficient for a real project in 2026.

### pip-tools
- **Strengths:** Adds proper lockfile semantics on top of pip.
- **Weaknesses:** Multi-tool combo (pip + pip-tools + venv + pyenv). Slower than uv.
- **Verdict:** Strictly worse than uv on the same niche.

### Poetry
- **Strengths:** Established since 2018. Mature dependency resolver. Widely known in the Python community. Good documentation. Plugin ecosystem.
- **Weaknesses:**
  - Significantly slower than uv (especially in CI cold-start).
  - Heavier install footprint.
  - Historically used a non-standard lockfile format and `pyproject.toml` extensions before PEP 621/735 standardized things. Poetry users developed habits that lag the standard.
  - Bigger surface area for "Poetry fights you on an edge case" issues.
- **Verdict:** A reasonable choice (the "safe" pick of 2022). But uv has clearly won the speed and ergonomics race by 2026.

### Hatch / PDM
- **Strengths:** Standards-aligned, capable.
- **Weaknesses:** Smaller communities than Poetry or uv. No compelling advantage over uv.
- **Verdict:** Fine alternatives, not differentiated enough to prefer.

### uv (chosen)
- **Strengths:**
  - 10–100× faster than Poetry / pip for installs and resolution. Materially better CI experience.
  - One tool replaces pip + venv + pyenv + pip-tools + pipx.
  - Manages Python interpreters too (contributors get the right Python version automatically).
  - Uses standard `pyproject.toml` (PEP 621). Projects stay portable.
  - Built by **Astral**, the same team behind **Ruff** (also in our stack). Same Rust-fast, standards-aligned philosophy.
  - Mainstream by 2026. Adopted by major OSS projects and companies; no longer "the new hot thing."
- **Weaknesses:**
  - Younger than Poetry (released 2024). Some older blog posts and tutorials still default to Poetry.
  - Plugin ecosystem smaller than Poetry's (we don't currently need plugins).

## Consequences

### Positive
- Fast contributor onboarding (`uv sync` and you're done, no global Python juggling).
- Fast CI: lockfile-based installs in seconds, not minutes.
- One tool to learn, one tool to document.
- Same vendor as Ruff. Consistent tooling story.

### Negative
- Contributors used to Poetry need a short orientation. Mitigated by adding a one-page "uv quick reference" to `CONTRIBUTING.md`.
- We depend on Astral continuing to maintain uv (low risk given current momentum and funding).

## Revisit when

- A required dependency or workflow only works through Poetry plugins we cannot replicate.
- Astral abandons uv (no signs of this).
