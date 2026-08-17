"""M7-04: Guarantee the app makes no outbound network calls during a demo report run.

Telemetry audit
---------------
Searched core, connector, and API source for analytics/telemetry/phone-home patterns:
  - SDK names: sentry, datadog, newrelic, segment, mixpanel, amplitude, posthog, honeycomb,
    opentelemetry, rudderstack, plausible, statsD.
  - Patterns: phone_home, beacon, ping_home, unauthorized outbound httpx.
Result: none found.  The only telemetry mentions are in the UI settings page (a
display-only off-by-default toggle) and in this test file.  Architecture §3.2 is satisfied.

Test harness
------------
An autouse fixture installs four layers of blocking before every test in this module:

1. socket.socket.connect / socket.socket.sendto / socket.socket.sendmsg /
   socket.create_connection — intercepts all TCP *and* UDP connections at the OS
   transport boundary.  Any attempt raises AssertionError immediately.

2. create_redacting_async_client at the BOUND name in each connector module — patches
   the symbol where the connector already imported it (patching the source module alone
   would not rebind already-imported references):
     - em_radar_connector_jira.connector.create_redacting_async_client
     - em_radar_connector_gitlab.connector.create_redacting_async_client

Three tests prove the blockers fire (positive controls).  Two integration tests verify
the full pipeline:

P2-A  (subprocess, import/startup guard) — socket blockers are installed inside a fresh
      subprocess BEFORE app import, then TestClient is entered as a context manager so
      the FastAPI lifespan (seed_default_signal_group) runs.  A GET /api/health that
      returns 200/ok is the proof.

P2-B  (real connectors, source-host allow-list) — the REAL JiraConnector and
      GitLabConnector are instantiated and their fetch methods are driven under a
      per-connector transport that allows only the connector's configured source host and
      raises AssertionError for any other destination.  This proves the real connector
      code contacts only its source and that a hypothetical phone-home call would be
      caught.
"""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
from collections.abc import AsyncIterator, Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar
from urllib.parse import urlparse
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from em_radar_connector_gitlab.connector import GitLabConnector
from em_radar_connector_jira.connector import JiraConnector
from em_radar_core.connectors import (
    Capabilities,
    ConnectionTestResult,
    MergeRequestScope,
    WorkItemScope,
)
from em_radar_core.models import (
    EvaluationWindow,
    MergeRequest,
    MergeRequestState,
    Repository,
    Source,
    WindowType,
)

from test_source_connection_routes import (
    FrozenReportDateTime,
    JiraTestConnector,
    _create_board_scope,
    _create_jira_connection,
)

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

_BOARD_CAPABILITIES = ["sprint", "statuses", "labels"]
_REPO_ID = UUID("cc000000-0000-0000-0000-000000000001")
_AUTHOR_ID = UUID("dd000000-0000-0000-0000-000000000001")
_MR_CREATED_AT = datetime(2026, 6, 1, tzinfo=timezone.utc)
_MR_UPDATED_AT = datetime(2026, 6, 10, tzinfo=timezone.utc)

# Path to apps/api/src — added to PYTHONPATH for the subprocess test so em_radar_api
# is importable without going through the pytest pythonpath machinery.
_API_SRC = Path(__file__).parent.parent / "src"

# ---------------------------------------------------------------------------
# Static in-memory GitLab connector (used by the static integration test)
# ---------------------------------------------------------------------------


class _StaticGitLabConnector:
    """In-process GitLab stand-in that returns static data without any network call."""

    name: ClassVar[str] = "gitlab"
    display_name: ClassVar[str] = "GitLab (static, no-network)"
    config_schema: ClassVar[dict[str, object]] = {
        "type": "object",
        "properties": {},
        "additionalProperties": True,
    }
    min_model_version: ClassVar[int] = 1

    def __init__(self, config: dict[str, object]) -> None:
        pass

    async def test_connection(self) -> ConnectionTestResult:
        return ConnectionTestResult(ok=True, detail="ok")

    @classmethod
    def describe_capabilities(cls) -> Capabilities:
        return Capabilities(provides_mergerequests=True, provides_repositories=True)

    async def close(self) -> None:
        pass

    async def list_repositories(self) -> list[Repository]:
        return [
            Repository(
                id=_REPO_ID,
                source=Source.GITLAB,
                external_id="repo-static",
                name="static-repo",
                full_path="demo/static-repo",
                default_branch="main",
            )
        ]

    async def fetch_mergerequests(
        self,
        scope: MergeRequestScope,
        window: EvaluationWindow,
    ) -> AsyncIterator[MergeRequest]:
        del scope, window
        yield MergeRequest(
            source=Source.GITLAB,
            external_id="mr-static-1",
            repository_id=_REPO_ID,
            iid=1,
            title="Static MR",
            state=MergeRequestState.OPEN,
            author_id=_AUTHOR_ID,
            target_branch="main",
            source_branch="feature/static",
            created_at=_MR_CREATED_AT,
            updated_at=_MR_UPDATED_AT,
        )


# ---------------------------------------------------------------------------
# Blocking transports and factories
# ---------------------------------------------------------------------------


class _BlockingTransport(httpx.AsyncBaseTransport):
    """httpx async transport that rejects every request."""

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        raise AssertionError(
            f"Unexpected outbound HTTP request during demo run: {request.method} {request.url}"
        )


def _blocking_client_factory(**kwargs: object) -> httpx.AsyncClient:
    """Replacement for create_redacting_async_client that blocks all httpx requests.

    Pops factory-specific kwargs so they are not forwarded to httpx.AsyncClient, then
    overrides the transport with _BlockingTransport.
    """
    kwargs.pop("client_factory", None)
    kwargs.pop("sensitive_values", None)
    kwargs.pop("transport", None)
    return httpx.AsyncClient(transport=_BlockingTransport(), **kwargs)  # type: ignore[arg-type]


class _SourceOnlyTransport(httpx.AsyncBaseTransport):
    """Allows requests only to a single whitelisted host; raises on everything else.

    Used for P2-B to prove the real connector code contacts only its configured source
    and that a hypothetical phone-home would be caught.
    """

    def __init__(
        self,
        allowed_host: str,
        handler: Callable[[httpx.Request], httpx.Response],
    ) -> None:
        self._allowed_host = allowed_host
        self._handler = handler

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.host != self._allowed_host:
            raise AssertionError(
                f"Connector contacted unexpected host {request.url.host!r}; "
                f"only {self._allowed_host!r} is allowed"
            )
        return self._handler(request)


def _make_source_only_factory(
    allowed_host: str,
    handler: Callable[[httpx.Request], httpx.Response],
) -> Callable[..., httpx.AsyncClient]:
    """Return a create_redacting_async_client replacement pinned to a single allowed host.

    The allowed host is supplied explicitly (derived from the connector's configured
    base_url at call-site), not from the per-invocation base_url kwarg.  This means a
    connector that opens a second httpx client to any other host (e.g. a telemetry
    endpoint) is rejected — the allow-list cannot be side-stepped by passing a different
    base_url to create_redacting_async_client.
    """

    def factory(**kwargs: object) -> httpx.AsyncClient:
        kwargs.pop("client_factory", None)
        kwargs.pop("sensitive_values", None)
        kwargs.pop("transport", None)
        return httpx.AsyncClient(
            transport=_SourceOnlyTransport(allowed_host, handler),
            **kwargs,  # type: ignore[arg-type]
        )

    return factory


# ---------------------------------------------------------------------------
# Canned Jira API payloads for P2-B
# ---------------------------------------------------------------------------

_CANNED_JI_PROJECT: dict[str, object] = {
    "id": "10000",
    "key": "TEST",
    "name": "Canned Project",
    "self": "https://jira.test.invalid/rest/api/2/project/10000",
}

_CANNED_JI_BOARD: dict[str, object] = {
    "id": "1",
    "name": "Canned Scrum Board",
    "type": "scrum",
    "location": {"projectId": "10000", "projectKey": "TEST"},
}

_CANNED_JI_SPRINT: dict[str, object] = {
    "id": "101",
    "name": "Sprint 1",
    "state": "active",
    "startDate": "2026-06-01T00:00:00Z",
    "endDate": "2026-06-14T00:00:00Z",
    "self": "https://jira.test.invalid/rest/agile/1.0/sprint/101",
}

# Work item (issue) payload for both the search endpoint and the issue-detail endpoint.
# fields.updated = 2026-06-10 is before window.end = 2026-06-17, so _workitem_in_window passes.
_CANNED_JI_ISSUE: dict[str, object] = {
    "id": "10001",
    "key": "TEST-1",
    "self": "https://jira.test.invalid/rest/api/2/issue/10001",
    "fields": {
        "summary": "Canned work item",
        "description": None,
        "issuetype": {"name": "Story"},
        "status": {
            "name": "In Progress",
            "statusCategory": {"key": "indeterminate", "id": "4", "name": "In Progress"},
        },
        "project": {"id": "10000"},
        "assignee": None,
        "reporter": None,
        "labels": [],
        "components": [],
        "created": "2026-06-01T00:00:00Z",
        "updated": "2026-06-10T00:00:00Z",
        "resolutiondate": None,
        "duedate": None,
        "customfield_10020": None,
        "customfield_10016": None,
        "customfield_10014": None,
    },
}

# Status object used by _status_categories (fetch_transitions → GET /rest/api/2/status).
_CANNED_JI_STATUS: dict[str, object] = {
    "id": "4",
    "name": "In Progress",
    "statusCategory": {"key": "indeterminate", "id": "4", "name": "In Progress"},
}


def _jira_canned_handler(request: httpx.Request) -> httpx.Response:
    """Route canned Jira API responses by path so every real connector endpoint is served.

    Endpoints covered:
    - GET /rest/api/2/myself                         — test_connection (current user)
    - GET /rest/api/2/mypermissions                  — test_connection (permission check)
    - GET /rest/api/2/project                        — list_projects
    - GET /rest/agile/1.0/board                      — list_boards
    - GET /rest/agile/1.0/board/{id}/sprint          — list_sprints
    - GET /rest/api/2/search/jql                     — fetch_workitems
    - GET /rest/api/2/status                         — _status_categories (fetch_transitions)
    - GET /rest/api/2/issue/{id}                     — fetch_transitions issue lookup
    - GET /rest/api/2/issue/{id}/changelog           — fetch_transitions changelog pages
    """
    path = request.url.path.rstrip("/")

    if path == "/rest/api/2/myself":
        return httpx.Response(200, json={"displayName": "Canned Jira User", "accountId": "u1"})
    if path == "/rest/api/2/mypermissions":
        return httpx.Response(
            200,
            json={"permissions": {"BROWSE_PROJECTS": {"havePermission": True}}},
        )
    if path == "/rest/api/2/project":
        return httpx.Response(200, json=[_CANNED_JI_PROJECT])
    if path == "/rest/api/2/status":
        return httpx.Response(200, json=[_CANNED_JI_STATUS])
    if path == "/rest/agile/1.0/board":
        return httpx.Response(200, json={"values": [_CANNED_JI_BOARD], "isLast": True})
    if path.startswith("/rest/agile/1.0/board/") and path.endswith("/sprint"):
        return httpx.Response(200, json={"values": [_CANNED_JI_SPRINT], "isLast": True})
    if "search" in path:
        return httpx.Response(200, json={"issues": [_CANNED_JI_ISSUE], "total": 1})
    # Changelog endpoint must be checked before the generic issue-detail branch so that
    # /rest/api/2/issue/{id}/changelog is not swallowed by the "/rest/api/2/issue/" check.
    if path.endswith("/changelog"):
        return httpx.Response(200, json={"values": [], "total": 0})
    if "/rest/api/2/issue/" in path:
        # Issue detail: needs at least "key" (for issue_key) and "changelog" (fallback histories).
        return httpx.Response(200, json={**_CANNED_JI_ISSUE, "changelog": {"values": []}})
    return httpx.Response(200, json={})


# ---------------------------------------------------------------------------
# Canned GitLab API payloads for P2-B
# ---------------------------------------------------------------------------

# One repository payload — _repository_from_payload requires id, name,
# path_with_namespace, default_branch (str|None), archived (bool).
_CANNED_GL_REPO: dict[str, object] = {
    "id": 101,
    "name": "canned-repo",
    "path_with_namespace": "demo/canned-repo",
    "default_branch": "main",
    "archived": False,
    "web_url": "https://gitlab.test.invalid/demo/canned-repo",
}

# One open MR payload for the list endpoint and the single-MR detail endpoint.
# "opened" + created_at before window.end passes both _payload_in_window and _mr_in_window.
_CANNED_GL_MR: dict[str, object] = {
    "id": 1001,
    "iid": 1,
    "state": "opened",
    "draft": False,
    "work_in_progress": False,
    "title": "Canned open MR",
    "author": {"id": 42},
    "target_branch": "main",
    "source_branch": "feature/canned",
    "created_at": "2026-06-01T00:00:00Z",
    "updated_at": "2026-06-10T00:00:00Z",
    "user_notes_count": 0,
    "web_url": "https://gitlab.test.invalid/demo/canned-repo/-/merge_requests/1",
}

# Detail response extends the list shape with diff stats and project_id.
# Used for both the project-scoped detail call (_resolve_diff_stats) and the
# global MR endpoint call (fetch_reviews needs project_id + iid).
_CANNED_GL_MR_DETAIL: dict[str, object] = {
    **_CANNED_GL_MR,
    "project_id": 101,
    "changes_count": 3,
    "additions": 10,
    "deletions": 2,
}


def _gitlab_canned_handler(request: httpx.Request) -> httpx.Response:
    """Route canned GitLab API responses by path so every real connector endpoint is served.

    Endpoints covered:
    - GET /api/v4/user                                           — test_connection (current user)
    - GET /api/v4/personal_access_tokens/self                    — test_connection (token info)
    - GET /api/v4/projects                                       — list_repositories
    - GET /api/v4/projects/{id}/merge_requests                   — fetch_mergerequests list
    - GET /api/v4/projects/{id}/merge_requests/{iid}             — diff-stats detail
    - GET /api/v4/projects/{id}/merge_requests/{iid}/approvals   — approval count
    - GET /api/v4/merge_requests/{id}                            — global MR (fetch_reviews)
    - GET /api/v4/projects/{id}/merge_requests/{iid}/notes       — review activity
    - GET /api/v4/projects/{id}/merge_requests/{iid}/reviewers   — reviewer requests
    """
    path = request.url.path.rstrip("/")

    if path == "/api/v4/user":
        return httpx.Response(200, json={"name": "Canned GitLab User", "username": "canned"})
    if path == "/api/v4/personal_access_tokens/self":
        return httpx.Response(200, json={"scopes": ["read_api", "read_repository"]})
    if path == "/api/v4/projects":
        return httpx.Response(200, json=[_CANNED_GL_REPO], headers={"X-Next-Page": ""})
    # Sub-resource suffixes are checked before the bare /merge_requests suffix so that
    # /merge_requests/1/notes etc. do not accidentally match the list-endpoint branch.
    if path.endswith("/approvals"):
        return httpx.Response(200, json={"approved_by": []})
    if path.endswith("/notes"):
        return httpx.Response(200, json=[], headers={"X-Next-Page": ""})
    if path.endswith("/reviewers"):
        return httpx.Response(200, json=[], headers={"X-Next-Page": ""})
    if path.endswith("/merge_requests"):
        return httpx.Response(200, json=[_CANNED_GL_MR], headers={"X-Next-Page": ""})
    # Global (non-project-scoped) MR endpoint: /api/v4/merge_requests/{id}
    # fetch_reviews calls this to resolve project_id and iid before fetching notes/reviewers.
    if "/projects/" not in path and "/merge_requests/" in path:
        return httpx.Response(200, json=_CANNED_GL_MR_DETAIL)
    # Project-scoped MR detail: /api/v4/projects/{id}/merge_requests/{iid}
    # _resolve_diff_stats calls this for additions/deletions.
    if "/merge_requests/" in path:
        return httpx.Response(200, json=_CANNED_GL_MR_DETAIL)
    return httpx.Response(200, json={})


# ---------------------------------------------------------------------------
# Socket-level blockers
# ---------------------------------------------------------------------------


def _reject_socket_connect(self: socket.socket, address: object) -> None:
    raise AssertionError(f"Outbound socket.connect blocked during demo run: {address!r}")


def _reject_create_connection(address: object, *args: object, **kwargs: object) -> None:
    raise AssertionError(f"Outbound socket.create_connection blocked during demo run: {address!r}")


def _reject_socket_sendto(self: socket.socket, *args: object, **kwargs: object) -> None:
    raise AssertionError("Outbound socket.sendto (UDP) blocked during demo run")


def _reject_socket_sendmsg(self: socket.socket, *args: object, **kwargs: object) -> None:
    raise AssertionError("Outbound socket.sendmsg (UDP) blocked during demo run")


# ---------------------------------------------------------------------------
# Autouse fixture — active for every test in this module
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _block_outbound_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Block all outbound TCP, UDP, and httpx connections for every test in this module.

    The TestClient uses an in-process ASGI transport (no real sockets), and SQLite uses
    file I/O, so neither is affected.  Only application code that attempts a real
    outbound connection triggers the blockers.

    The httpx factory is patched at the *bound* name in each connector module so that
    already-imported references are correctly intercepted (patching the source module
    alone does not rebind names imported with ``from ... import ...``).
    """
    # TCP / socket layer.
    monkeypatch.setattr(socket.socket, "connect", _reject_socket_connect)
    monkeypatch.setattr(socket, "create_connection", _reject_create_connection)
    # UDP layer (statsd-style beacons use sendto/sendmsg without connect).
    monkeypatch.setattr(socket.socket, "sendto", _reject_socket_sendto)
    if hasattr(socket.socket, "sendmsg"):
        monkeypatch.setattr(socket.socket, "sendmsg", _reject_socket_sendmsg)
    # httpx layer — patch the bound name in every module that imports the factory.
    monkeypatch.setattr(
        "em_radar_connector_jira.connector.create_redacting_async_client",
        _blocking_client_factory,
    )
    monkeypatch.setattr(
        "em_radar_connector_gitlab.connector.create_redacting_async_client",
        _blocking_client_factory,
    )


# ---------------------------------------------------------------------------
# Subprocess program for P2-A (import/startup guard)
# ---------------------------------------------------------------------------

# The program blocks sockets BEFORE importing anything from em_radar_api, then
# runs the full app lifespan (TestClient used as a context manager) and hits
# GET /api/health.  Any network call during import, startup, or the request
# causes the subprocess to exit non-zero.
_SUBPROCESS_PROGRAM = """\
import socket as _socket

def _blocked_connect(self, addr, *a, **kw):
    raise AssertionError(f"socket.connect blocked in startup test: {addr!r}")

def _blocked_create_connection(addr, *a, **kw):
    raise AssertionError(f"socket.create_connection blocked in startup test: {addr!r}")

def _blocked_sendto(self, *a, **kw):
    raise AssertionError("socket.sendto blocked in startup test")

_socket.socket.connect = _blocked_connect
_socket.create_connection = _blocked_create_connection
_socket.socket.sendto = _blocked_sendto
if hasattr(_socket.socket, "sendmsg"):
    def _blocked_sendmsg(self, *a, **kw):
        raise AssertionError("socket.sendmsg blocked in startup test")
    _socket.socket.sendmsg = _blocked_sendmsg

import os, tempfile
_tmp = tempfile.mkdtemp()
os.environ["EM_RADAR_DATABASE_PATH"] = _tmp + "/health-test.db"

import em_radar_api.tables  # registers SQLModel table metadata
from sqlmodel import SQLModel
from em_radar_api.db import engine
SQLModel.metadata.create_all(engine)

from em_radar_api.main import app
from fastapi.testclient import TestClient

with TestClient(app) as client:
    r = client.get("/api/health")
    assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text}"
    body = r.json()
    assert body == {"status": "ok"}, f"unexpected body: {body}"
"""

# ---------------------------------------------------------------------------
# Positive-control tests: prove each blocker fires before the main tests.
# ---------------------------------------------------------------------------


def test_socket_create_connection_is_blocked() -> None:
    """socket.create_connection must raise under the active blocker."""
    with pytest.raises(AssertionError, match="socket.create_connection blocked"):
        socket.create_connection(("example.invalid", 80))


def test_socket_connect_is_blocked() -> None:
    """socket.socket.connect must raise under the active blocker."""
    with pytest.raises(AssertionError, match="socket.connect blocked"):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
            client_socket.connect(("example.invalid", 80))


def test_httpx_blocking_transport_is_active() -> None:
    """_BlockingTransport must raise AssertionError on any async request."""

    async def _attempt() -> None:
        async with httpx.AsyncClient(transport=_BlockingTransport()) as client:
            await client.get("https://example.invalid")

    with pytest.raises(AssertionError, match="Unexpected outbound HTTP request"):
        asyncio.run(_attempt())


# ---------------------------------------------------------------------------
# P2-A: Import-time and startup network isolation (subprocess)
# ---------------------------------------------------------------------------


def test_no_outbound_calls_during_app_import_and_startup() -> None:
    """Socket blockers installed before app import catch any network call during
    module-level code, lifespan startup, and the health-check request.

    A fresh subprocess blocks all sockets first, then imports em_radar_api.main
    (which runs create_app() at module level), enters TestClient as a context
    manager (triggering lifespan startup and shutdown), and asserts a 200/ok
    health response.  Any outbound network attempt makes the subprocess exit
    non-zero, failing this test.
    """
    existing = os.environ.get("PYTHONPATH", "")
    pythonpath = str(_API_SRC) if not existing else f"{_API_SRC}{os.pathsep}{existing}"
    env = {**os.environ, "PYTHONPATH": pythonpath}

    result = subprocess.run(
        [sys.executable, "-c", _SUBPROCESS_PROGRAM],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    assert result.returncode == 0, (
        f"Subprocess exited with returncode {result.returncode}.\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )


# ---------------------------------------------------------------------------
# P2-A2: Connector import-time and entry-point discovery isolation (subprocess)
# ---------------------------------------------------------------------------

# Installs socket blockers BEFORE importing any connector module or running
# entry-point discovery.  This guards against module-level phone-homes that would
# slip past the in-process tests (connectors are imported during pytest plugin
# initialisation, before any autouse fixture runs).
_CONNECTOR_IMPORT_PROGRAM = """\
import socket as _socket

def _blocked_connect(self, addr, *a, **kw):
    raise AssertionError(f"socket.connect blocked during connector import: {addr!r}")

def _blocked_create_connection(addr, *a, **kw):
    raise AssertionError(f"socket.create_connection blocked during connector import: {addr!r}")

def _blocked_sendto(self, *a, **kw):
    raise AssertionError("socket.sendto blocked during connector import")

_socket.socket.connect = _blocked_connect
_socket.create_connection = _blocked_create_connection
_socket.socket.sendto = _blocked_sendto
if hasattr(_socket.socket, "sendmsg"):
    def _blocked_sendmsg(self, *a, **kw):
        raise AssertionError("socket.sendmsg blocked during connector import")
    _socket.socket.sendmsg = _blocked_sendmsg

# Import each connector module directly — proves no module-level network call.
import em_radar_connector_demo.connector
import em_radar_connector_jira.connector
import em_radar_connector_gitlab.connector

# Run the contracts-plugin discovery path, which loads all entry points just as
# the pytest plugin does during collection.
from em_radar_connector_contracts.plugin import _discover_connector_classes
classes = _discover_connector_classes()
assert len(classes) >= 3, f"expected at least 3 connector classes, got {classes}"
"""


def test_no_outbound_calls_during_connector_import_and_discovery() -> None:
    """Socket blockers installed before any connector import prove no module-level
    or entry-point-discovery network call fires in the three shipped connectors.

    The in-process demo-connector test cannot catch import-time phone-homes because
    connectors are loaded by the pytest contracts plugin before any autouse fixture
    runs.  This subprocess test closes that gap: blockers are installed first, then
    the three connector modules and the entry-point discovery routine are imported.
    """
    result = subprocess.run(
        [sys.executable, "-c", _CONNECTOR_IMPORT_PROGRAM],
        capture_output=True,
        text=True,
        timeout=30,
        env=os.environ,
    )
    assert result.returncode == 0, (
        f"Subprocess exited with returncode {result.returncode}.\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )


# ---------------------------------------------------------------------------
# Static-connector integration test
# ---------------------------------------------------------------------------


def _create_gitlab_connection(api_client: TestClient) -> str:
    return api_client.post(
        "/api/connections",
        json={"name": "GitLab Static", "connector_name": "gitlab", "config": {}},
    ).json()["id"]


def test_demo_report_run_makes_no_outbound_network_calls(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A full demo report run must not trigger any outbound network call.

    The socket and httpx blockers installed by _block_outbound_network fail the test
    immediately if any TCP/UDP connection or httpx request is attempted.  A 200 response
    with status ``"succeeded"`` is therefore proof that the entire pipeline — API routing,
    connector dispatch, normalizer, signal engine, report generator — ran without making a
    single outbound network call.  The positive-control tests confirm the blockers are
    active, making this result non-vacuous.
    """
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [JiraTestConnector, _StaticGitLabConnector],
    )
    monkeypatch.setattr("em_radar_api.routers.reports.datetime", FrozenReportDateTime)

    jira_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, jira_id, _BOARD_CAPABILITIES)
    gitlab_id = _create_gitlab_connection(api_client)
    team_id = api_client.post(
        "/api/teams",
        json={
            "name": "No-telemetry demo team",
            "connection_ids": [jira_id],
            "scope_ids": [scope_id],
            "code_connection_id": gitlab_id,
            "working_mode": "scrum",
            "sprint_length_days": 14,
        },
    ).json()["id"]

    response = api_client.post(
        "/api/reports/run",
        json={"connector": "jira", "team_profile_id": team_id},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "succeeded"


# ---------------------------------------------------------------------------
# Demo connector — network isolation proof
# ---------------------------------------------------------------------------


def test_real_demo_connector_makes_no_outbound_calls() -> None:
    """The real DemoConnector must complete its full provider surface without any network call.

    DemoConnector returns static in-memory data and uses no httpx, so the autouse socket
    and httpx blockers installed by _block_outbound_network are active throughout this test.
    Any accidental outbound call (e.g. from a future refactor) would immediately raise
    AssertionError via the socket blocker, failing this test.

    All provider methods are driven so that a phone-home added to any code path is caught:
    test_connection, list_projects, list_boards, list_sprints, fetch_workitems,
    fetch_transitions, list_repositories, fetch_mergerequests, close.
    """
    from em_radar_connector_demo.connector import DemoConnector

    async def _run() -> tuple[
        object,
        list[object],
        list[object],
        list[object],
        list[object],
        list[object],
        list[object],
        list[object],
    ]:
        connector = DemoConnector({})
        conn_result = await connector.test_connection()
        projects = await connector.list_projects()
        boards = await connector.list_boards(projects[0].external_id)
        sprints = await connector.list_sprints(boards[0].external_id)
        window = EvaluationWindow(
            window_type=WindowType.DATE_RANGE,
            start=datetime(2026, 6, 1, tzinfo=timezone.utc),
            end=datetime(2026, 6, 17, tzinfo=timezone.utc),
            team_profile_id=uuid4(),
        )
        workitems = [
            wi
            async for wi in connector.fetch_workitems(
                WorkItemScope(project_external_ids=["DEMO"]), window
            )
        ]
        transitions = [
            t
            async for t in connector.fetch_transitions(
                "workitem", [wi.external_id for wi in workitems]
            )
        ]
        repos = await connector.list_repositories()
        mrs = [
            mr
            async for mr in connector.fetch_mergerequests(
                MergeRequestScope(repository_external_ids=[r.external_id for r in repos]),
                window,
            )
        ]
        await connector.close()
        return conn_result, projects, boards, sprints, workitems, transitions, repos, mrs

    conn, projects, boards, sprints, workitems, transitions, repos, mrs = asyncio.run(_run())

    assert conn.ok, f"DemoConnector test_connection failed: {conn!r}"
    assert len(projects) == 1, f"expected 1 project, got {projects!r}"
    assert len(boards) == 1, f"expected 1 board, got {boards!r}"
    assert len(sprints) == 1, f"expected 1 sprint, got {sprints!r}"
    assert len(workitems) == 2, f"expected 2 workitems, got {workitems!r}"
    assert isinstance(transitions, list)  # DemoConnector yields no transitions
    assert len(repos) == 1, f"expected 1 repo, got {repos!r}"
    assert len(mrs) == 1, f"expected 1 MR, got {mrs!r}"


# ---------------------------------------------------------------------------
# P2-B: Real connectors under source-host allow-list transport
# ---------------------------------------------------------------------------


def test_real_connectors_only_contact_their_source_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The real JiraConnector and GitLabConnector must contact only their configured
    source host; any other destination raises AssertionError.

    The autouse _blocking_client_factory is replaced per connector with a
    _SourceOnlyTransport that allows only the connector's base_url host.  The real
    connector constructors and fetch methods execute (not static fakes), so this proves
    the actual connector code paths are clean.

    The wrong-host rejection is explicitly verified so the allow-list itself is proven
    active (making the fetch-method assertions non-vacuous).
    """
    jira_base = "https://jira.test.invalid"
    gitlab_base = "https://gitlab.test.invalid"

    # Override the autouse blocker with allow-list factories pinned to each connector's
    # configured source host.  The host is derived here (not inside the factory) so that
    # a connector opening a second client to any other URL is rejected.
    monkeypatch.setattr(
        "em_radar_connector_jira.connector.create_redacting_async_client",
        _make_source_only_factory(urlparse(jira_base).hostname or "", _jira_canned_handler),
    )
    monkeypatch.setattr(
        "em_radar_connector_gitlab.connector.create_redacting_async_client",
        _make_source_only_factory(urlparse(gitlab_base).hostname or "", _gitlab_canned_handler),
    )

    # Prove the wrong-host rejection is active before exercising the connectors.
    async def _wrong_host_attempt() -> None:
        transport = _SourceOnlyTransport("jira.test.invalid", _jira_canned_handler)
        async with httpx.AsyncClient(transport=transport) as client:
            await client.get("https://evil.example.com/steal-data")

    with pytest.raises(AssertionError, match="unexpected host"):
        asyncio.run(_wrong_host_attempt())

    # Exercise the real JiraConnector: test_connection + all five report-path methods.
    # Mirrors reports.py order: list_projects → list_boards → list_sprints →
    # fetch_workitems → fetch_transitions.
    async def _run_jira() -> tuple[
        object, list[object], list[object], list[object], list[object], list[object]
    ]:
        connector = JiraConnector({"base_url": jira_base, "token": "fake-token-1234567890"})
        conn_result = await connector.test_connection()
        projects = await connector.list_projects()
        boards = await connector.list_boards(projects[0].external_id)
        sprints = await connector.list_sprints(boards[0].external_id)
        window = EvaluationWindow(
            window_type=WindowType.DATE_RANGE,
            start=datetime(2026, 6, 1, tzinfo=timezone.utc),
            end=datetime(2026, 6, 17, tzinfo=timezone.utc),
            team_profile_id=uuid4(),
        )
        scope = WorkItemScope(
            project_external_ids=[projects[0].external_id],
            board_external_ids=[boards[0].external_id],
        )
        workitems = [wi async for wi in connector.fetch_workitems(scope, window)]
        transitions = [
            t
            async for t in connector.fetch_transitions(
                "workitem", [wi.external_id for wi in workitems]
            )
        ]
        await connector.close()
        return conn_result, projects, boards, sprints, workitems, transitions

    jira_conn, jira_projects, jira_boards, jira_sprints, jira_items, jira_transitions = asyncio.run(
        _run_jira()
    )
    # test_connection + all five real Jira methods executed under the allow-list transport.
    # Any request to a host other than jira.test.invalid would have raised AssertionError.
    assert jira_conn.ok, f"Jira test_connection failed: {jira_conn!r}"
    assert len(jira_projects) == 1, f"expected 1 project, got {jira_projects!r}"
    assert len(jira_boards) == 1, f"expected 1 board, got {jira_boards!r}"
    assert len(jira_sprints) == 1, f"expected 1 sprint, got {jira_sprints!r}"
    assert len(jira_items) == 1, f"expected 1 work item, got {jira_items!r}"
    # Canned changelog is empty so no Transition objects are expected; what matters is that
    # fetch_transitions executed (it called /status and /issue/{id}/changelog) without raising.
    assert isinstance(jira_transitions, list)

    # Exercise the real GitLabConnector: test_connection + list_repositories,
    # fetch_mergerequests, fetch_reviews.
    # Mirrors the sequence in apps/api/src/em_radar_api/routers/reports.py (lines 730-739).
    async def _run_gitlab() -> tuple[object, list[object], list[object], list[object]]:
        connector = GitLabConnector({"base_url": gitlab_base, "token": "fake-token-1234567890"})
        conn_result = await connector.test_connection()
        repos = await connector.list_repositories()
        # Use the fetched repo external_ids so the scope matches the canned data.
        mr_scope = MergeRequestScope(
            repository_external_ids=[r.external_id for r in repos],
        )
        window = EvaluationWindow(
            window_type=WindowType.DATE_RANGE,
            start=datetime(2026, 6, 1, tzinfo=timezone.utc),
            end=datetime(2026, 6, 17, tzinfo=timezone.utc),
            team_profile_id=uuid4(),
        )
        mrs = [mr async for mr in connector.fetch_mergerequests(mr_scope, window)]
        # fetch_reviews exercises: global MR endpoint, /notes, /reviewers.
        reviews = [r async for r in connector.fetch_reviews([mr.external_id for mr in mrs])]
        await connector.close()
        return conn_result, repos, mrs, reviews

    gitlab_conn, gitlab_repos, gitlab_mrs, gitlab_reviews = asyncio.run(_run_gitlab())
    # Canned handler returns representative data; test_connection + all three fetch methods
    # must have run without contacting any host other than gitlab.test.invalid.
    assert gitlab_conn.ok, f"GitLab test_connection failed: {gitlab_conn!r}"
    assert len(gitlab_repos) == 1, f"expected 1 repo from canned handler, got {gitlab_repos!r}"
    assert len(gitlab_mrs) == 1, f"expected 1 MR from canned handler, got {gitlab_mrs!r}"
    # Notes and reviewers return [] so no Review objects are expected; what matters is that
    # fetch_reviews executed (it called the notes + reviewers endpoints) without raising.
    assert isinstance(gitlab_reviews, list)
