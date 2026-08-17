# EM Radar

[![CI](https://github.com/serdartas/em-radar/actions/workflows/ci.yml/badge.svg)](https://github.com/serdartas/em-radar/actions/workflows/ci.yml)

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

```bash
docker compose -f deploy/docker/docker-compose.yml up
```

Then open http://localhost:8080.

### Get to your first report

The app opens a setup wizard on the first visit. You need a Jira account with a read-only API
token to complete setup; a GitLab connection is optional and can be added later.

1. Open http://localhost:8080. The wizard starts automatically when no teams exist yet.
2. Click **Get started**.
3. **Add a Jira connection.** Enter a display name (for example `My Jira`), your Jira base URL
   (`https://your-org.atlassian.net` for Jira Cloud), your account email, and a read-only API
   token. Click **Add connection**, then **Continue**. See [How to generate a Jira
   token](http://localhost:8080/help/jira) (available once the app is running) for step-by-step
   instructions.
4. **Add a GitLab connection** (optional). Enter your GitLab URL and a `read_api` personal access
   token, or click **Skip for now**.
5. **Create a team.** Type a name for the team you manage (for example `Payments`) and click
   **Create team**.
6. **Attach sources.** Under **Task-board source**, choose your **Ticketing connection**, pick a
   **Project** and **Board**, and click **Save board source**. Optionally choose a **Code source**
   (a GitLab connection; this saves automatically on selection). Then click **Finish setup**.
7. EM Radar syncs the selected sources and runs the first report automatically.
8. On the Dashboard, click **Open report** to see the full findings.

### Zero to a real report (Jira + GitLab, under 15 minutes)

The quickstart above outlines the wizard flow. This section adds the token-creation steps and
the Markdown export, so you can follow the full path from a fresh install to a shareable report.

**Step 1 - Create a read-only Jira token**

The token type depends on whether you use Jira Cloud or Jira Server / Data Center.

**Jira Cloud**: Sign in to https://id.atlassian.com/manage-profile/security/api-tokens with
the Atlassian account that can browse the projects and boards you want to report on. Click
**Create API token**, give it a label (for example `EM Radar`), and copy the token. In Step 4,
enter that account's email in **Auth Email** and paste the token into **Token**.

**Jira Server / Data Center**: In Jira, open your user menu and go to **Profile** -
**Personal Access Tokens**. Create a token with at least read access to the projects and boards
you want to report on and copy it. In Step 4, leave **Auth Email** blank and paste the PAT into
**Token** (the connector sends it as a Bearer token, which is what Jira Server/DC expects).

For annotated screenshots of the Cloud steps, see the in-app guide at
http://localhost:8080/help/jira (available once the app is running). Minimum token scopes are
documented in the permissions reference (added separately).

**Step 2 - Create a read-only GitLab personal access token**

1. In GitLab, open your user menu and go to **Preferences** - **Access Tokens** (or
   **Edit profile** - **Access Tokens** on older releases).
2. Click **Add new token**, give it a name (for example `EM Radar`), set an optional expiry,
   and tick only the `read_api` scope. That is the only scope EM Radar needs.
3. Click **Create personal access token** and copy the token.

Minimum token scopes are documented in the permissions reference (added separately).

**Step 3 - Start the app and open the wizard**

```bash
docker compose -f deploy/docker/docker-compose.yml up
```

Open http://localhost:8080. If no teams exist the setup wizard starts automatically. Click
**Get started**.

**Step 4 - Add the Jira connection**

On the **Connect your ticketing source (Jira)** step:

1. **Connection name** - a display label for this instance (for example `Acme Jira`).
2. **Base Url** - `https://your-org.atlassian.net` for Jira Cloud, or your self-hosted address.
3. **Auth Email** - the Atlassian account email that owns the token (Jira Cloud only; leave
   blank for Jira Server / Data Center, which authenticates with the token alone).
4. **Token** - paste your API token here.
5. Click **Test connection**. On success click **Add connection**, then **Continue**.

**Step 5 - Add the GitLab connection**

On the **Connect your code source (GitLab)** step:

1. **Connection name** - a display label for this instance (for example `Acme GitLab`).
2. **Base Url** - `https://gitlab.com` for GitLab SaaS, or your self-hosted address.
3. **Token** - paste your `read_api` personal access token.
4. Click **Test connection**, then **Add connection**, then **Continue**.

To add GitLab later, click **Skip for now**.

**Step 6 - Create a team**

Type the name of the team you manage (for example `Payments`) and click **Create team**.

**Step 7 - Attach sources**

Under **Task-board source**: choose a **Ticketing connection**, pick a **Project** and a
**Board** from the searchable dropdowns, confirm or adjust the detected working mode and
sprint length, and click **Save board source**.

Note: for a **Scrum** board, the automatic first report (Step 8) requires an active sprint. If
your board has no active sprint - common between sprints or for backlog-only boards - the wizard
will stay on the Setup page with the error "Jira board has no active sprint". To avoid this,
change the **Working mode** dropdown to **Kanban** before clicking **Save board source**; EM
Radar will then use a 14-day rolling date range instead of requiring a sprint. You can switch
the working mode back to **Scrum** from the Teams page once a sprint is active.

Under **Code source**: choose your GitLab connection from the dropdown. The selection saves
automatically - no extra click needed.

**Step 8 - Finish setup**

Click **Finish setup**. EM Radar syncs the selected sources and runs the first report for
each team that has at least one source attached. You land on the Dashboard automatically.

**Step 9 - Open the report**

On the Dashboard, each team card shows severity counts and the top three risks. Click **Open
report** to see the full sectioned findings.

**Step 10 - Export to Markdown**

On the Report Results page, use the **Download .md** button (top-right area) to save the
report as a Markdown file, or click **Copy to clipboard** to paste it into a document, Slack
message, or sprint notes.

By default the container binds only to `127.0.0.1:8080`, so the app is not reachable from
other machines on your network. To opt into LAN access, choose one of the options below -
only do this on a trusted network, as EM Radar has no authentication in the current release.

**Option A - edit `docker-compose.yml` directly (simplest):** change the `ports` entry from
`"127.0.0.1:8080:8080"` to `"0.0.0.0:8080:8080"` (or `"8080:8080"`).

**Option B - Compose override file (keeps the base file unchanged):** create
`deploy/docker/docker-compose.override.yml` with `!override` so the base mapping is
replaced rather than merged:

```yaml
# deploy/docker/docker-compose.override.yml  (not committed; place next to docker-compose.yml)
services:
  emradar:
    ports: !override
      - "0.0.0.0:8080:8080"
```

```bash
docker compose -f deploy/docker/docker-compose.yml -f deploy/docker/docker-compose.override.yml up
```

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

See [the tech stack decision record](docs/04-tech-stack.md) for the rationale and per-decision
ADRs.

## Documentation

Specs live in [`docs/`](docs/):

- [vision & scope](docs/01-vision-and-scope.md)
- [requirements](docs/02-requirements.md)
- [architecture](docs/03-architecture-overview.md)
- [tech stack](docs/04-tech-stack.md)
- [data model](docs/05-data-model.md)
- [signal YAML spec](docs/06-signal-yaml-spec.md)
- [connector interface](docs/07-connector-interface.md)
- [MVP roadmap](docs/08-mvp-roadmap.md)
- [functional flows](docs/09-functional-flows.md)

The [`docs/backlog/`](docs/backlog/) implementation backlog slices the work into issues.

## License

Apache-2.0 © Serdar Tas
