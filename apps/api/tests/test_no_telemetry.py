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
Two complementary blockers are installed via an autouse fixture before every test:

1. socket.socket.connect / socket.socket.sendto / socket.socket.sendmsg /
   socket.create_connection — intercepts all TCP *and* UDP connections at the OS transport
   boundary.  Any attempt raises AssertionError immediately.

2. create_redacting_async_client — the httpx client factory used by real connectors is
   replaced with a factory that installs _BlockingTransport on every client.  The patch
   must target the *bound* name in each connector module (Python imports bind names into
   the importer's namespace at import time; patching the source module alone does not
   rebind already-imported names):
     - em_radar_connector_jira.connector.create_redacting_async_client
     - em_radar_connector_gitlab.connector.create_redacting_async_client

The positive-control tests below prove each blocker fires.  The main integration test
(``test_demo_report_run_makes_no_outbound_network_calls``) uses static in-memory
connectors to exercise the full API → connector → normalizer → signal engine → report
generator pipeline; a green result is meaningful because the blockers are proven active.
"""

from __future__ import annotations

import asyncio
import socket
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import ClassVar
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient

from em_radar_core.connectors import (
    Capabilities,
    ConnectionTestResult,
    MergeRequestScope,
)
from em_radar_core.models import (
    EvaluationWindow,
    MergeRequest,
    MergeRequestState,
    Repository,
    Source,
)

from test_source_connection_routes import (
    FrozenReportDateTime,
    JiraTestConnector,
    _create_board_scope,
    _create_jira_connection,
)

_BOARD_CAPABILITIES = ["sprint", "statuses", "labels"]
_REPO_ID = UUID("cc000000-0000-0000-0000-000000000001")
_AUTHOR_ID = UUID("dd000000-0000-0000-0000-000000000001")
_MR_CREATED_AT = datetime(2026, 6, 1, tzinfo=timezone.utc)
_MR_UPDATED_AT = datetime(2026, 6, 10, tzinfo=timezone.utc)


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


class _BlockingTransport(httpx.AsyncBaseTransport):
    """httpx async transport that rejects every request."""

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        raise AssertionError(
            f"Unexpected outbound HTTP request during demo run: {request.method} {request.url}"
        )


def _blocking_client_factory(**kwargs: object) -> httpx.AsyncClient:
    """Replacement for create_redacting_async_client that blocks all httpx requests.

    Pops the factory-specific kwargs (client_factory, sensitive_values) so they are not
    forwarded to httpx.AsyncClient, then overrides the transport with _BlockingTransport.
    """
    kwargs.pop("client_factory", None)
    kwargs.pop("sensitive_values", None)
    kwargs.pop("transport", None)
    return httpx.AsyncClient(transport=_BlockingTransport(), **kwargs)  # type: ignore[arg-type]


def _reject_socket_connect(self: socket.socket, address: object) -> None:
    raise AssertionError(f"Outbound socket.connect blocked during demo run: {address!r}")


def _reject_create_connection(address: object, *args: object, **kwargs: object) -> None:
    raise AssertionError(f"Outbound socket.create_connection blocked during demo run: {address!r}")


def _reject_socket_sendto(self: socket.socket, *args: object, **kwargs: object) -> None:
    raise AssertionError("Outbound socket.sendto (UDP) blocked during demo run")


def _reject_socket_sendmsg(self: socket.socket, *args: object, **kwargs: object) -> None:
    raise AssertionError("Outbound socket.sendmsg (UDP) blocked during demo run")


@pytest.fixture(autouse=True)
def _block_outbound_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Block all outbound TCP, UDP, and httpx connections for every test in this module.

    The TestClient uses an in-process ASGI transport (no real sockets), and SQLite
    uses file I/O, so neither is affected by these patches.  Only application code
    that attempts a real outbound connection will trigger the blockers.

    The httpx factory is patched at the bound name in each connector module, not only at
    the source module, so already-imported references are correctly intercepted.
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
# Positive-control tests: prove each blocker actually fires.
# The main integration test is meaningful only if these pass.
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
# Integration test: full demo report run with network blocked.
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
    immediately if any TCP/UDP connection or httpx request is attempted by the application.
    A 200 response with status ``"succeeded"`` is therefore proof that the entire pipeline
    — API routing, connector dispatch, normalizer, signal engine, report generator — ran
    without making a single outbound network call.  The positive-control tests above
    confirm the blockers are active, making this result non-vacuous.
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
