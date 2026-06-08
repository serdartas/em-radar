# Contributing to EM Radar

Thanks for your interest in contributing! EM Radar is a local-first engineering management
signal engine, and it is being built in the open. This guide explains how the project is
organized and how to get a change merged.

> **Status: pre-alpha.** The codebase is still being scaffolded. Structure, APIs, and
> conventions may change. If something here is out of date, a PR fixing it is a great first
> contribution.

---

## 1. Code of Conduct

This project follows a [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to
uphold it. Please report unacceptable behavior as described there.

---

## 2. How the work is organized

EM Radar is built from a prescriptive backlog rather than ad-hoc issues. Before proposing a
change, read:

- **[`docs/`](docs/)** — the specifications. These are authoritative.
- **[`docs/backlog/`](docs/backlog/)** — the implementation backlog, sliced into milestones
  (M0–M7, v0.1.0) and issues. Each issue has a stable ID (e.g. `M3-07`), a `Depends on` list,
  an explicit `Scope` / `Out of scope`, and a `Verification` block.
- **[`AGENTS.md`](AGENTS.md)** — the binding conventions (stack, package names, runtime
  constants, critical rules). Everything in there applies to human contributors too.

Work proceeds in **dependency order**. Do not start an issue until the issues it `Depends on`
are merged.

---

## 3. Development setup

### Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python 3.12+)
- Node.js (LTS) and npm
- Docker + Docker Compose

### Backend (`apps/api`)

```bash
cd apps/api
uv sync                                          # create .venv and install deps
uv run uvicorn em_radar_api.main:app --port 8080 # run locally
uv run pytest                                    # tests
uv run ruff check .                              # lint
uv run ruff format .                             # format
```

### Frontend (`apps/web`)

```bash
cd apps/web
npm install
npm run dev      # local dev server
npm run test     # tests (Vitest)
npm run lint     # ESLint
npm run build    # production build → dist/
```

### Full stack (Docker)

```bash
docker compose -f deploy/docker/docker-compose.yml up --build
# then open http://localhost:8080
```

---

## 4. Stack — do not substitute

EM Radar has deliberate, documented technology choices ([`docs/04-tech-stack.md`](docs/04-tech-stack.md)).
PRs that swap a core dependency (e.g. pip for uv, black for ruff, yarn for npm, MUI for
shadcn/ui) will not be accepted unless they come with an ADR proposing the change. The full
"do not substitute" table is in [`AGENTS.md`](AGENTS.md#2-stack--do-not-substitute).

---

## 5. Making a change

1. **Pick an issue.** Comment on the GitHub issue (or open one referencing the backlog ID)
   so work isn't duplicated. Confirm its dependencies are merged.
2. **Branch.** Create a feature branch off `main` (e.g. `m3-07-jira-board-mapping`).
3. **Implement exactly the issue's scope.** Do not change anything outside it. Resist
   "while I'm here" edits — they make review harder and break the dependency model.
4. **Write tests.** Any change that ships behavior ships with a test. Scaffolding and docs
   changes are exempt. See the testing rules in [`AGENTS.md`](AGENTS.md#8-tests).
5. **Run lint, format, and tests locally** before pushing (commands above).
6. **Open a PR.** Reference the issue with `Fixes #<n>` so it auto-closes on merge. Fill in
   the PR template.

---

## 6. Coding standards

The authoritative style rules live in [`AGENTS.md`](AGENTS.md#7-code-style). In short:

- **Python:** Ruff (line length 100, target py312); type-hint all signatures; avoid `Any`.
- **TypeScript/React:** strict mode; functional components only; avoid `any`.
- **Comments:** no redundant comments that restate the code. Docstrings welcome on public
  APIs (connectors, signal definitions, core models), not required on private helpers.

Two project-specific rules that are easy to get wrong:

- **Determinism.** Signals must compute time-based values against the injected
  `EvaluationContext.now`, never `datetime.now()` inline.
- **Source-agnostic core.** The signal engine evaluates canonical models only; it must never
  import a connector or call Jira/GitLab directly.

---

## 7. Commit and PR conventions

- Keep commits focused; write clear messages explaining *why*, not just *what*.
- One issue per PR where possible.
- PRs must be green in CI (lint + test + build) before review.
- Keep the PR scoped to the issue — reviewers will ask you to split unrelated changes out.

---

## 8. Reporting bugs and requesting features

- **Bugs:** open an issue using the bug report template. Include repro steps, expected vs
  actual behavior, and your environment.
- **Features:** open an issue using the feature request template. Note that MVP scope is
  fixed ([`docs/08-mvp-roadmap.md`](docs/08-mvp-roadmap.md)) — features outside it will be
  tagged for a later phase rather than rejected.
- **Security vulnerabilities:** do **not** open a public issue. Follow
  [`SECURITY.md`](SECURITY.md).

---

## 9. Contributor rights and assignment

EM Radar requires a copyright assignment so accepted original contributions have a single
copyright owner who can maintain, license, and commercially develop the project. Before a
contribution can be merged, every contributor must read and accept the
[`CONTRIBUTOR_ASSIGNMENT_AGREEMENT.md`](CONTRIBUTOR_ASSIGNMENT_AGREEMENT.md).

Accept the agreement by checking its acceptance box in the pull request template. That
acceptance confirms that you have authority to assign the contribution, including any
required permission from your employer or another rights holder. The maintainer may require a
separately signed agreement, especially for contributions made on behalf of a legal entity.

Accepted contributions in the public repository remain available under the project's
[Apache-2.0 License](LICENSE). The assignment does not prevent contributors from reusing their
own original contributions as described in the agreement.
