"""Connector contract test suite (connector spec §13).

Runs the same assertions against every registered connector. A connector that fails these tests
does not conform to the connector interface spec. The demo, Jira, and GitLab connectors are
parametrized below; a deliberately non-conforming stub is also included to prove the suite bites.
"""

from __future__ import annotations

import asyncio
from typing import ClassVar

import httpx
import pytest

from em_radar_core.connectors import (
    Capabilities,
    ConnectionTestResult,
    ConnectorBase,
    MergeRequestProvider,
    ReviewProvider,
    TransitionProvider,
    WorkItemProvider,
    WorkItemScope,
)
from em_radar_core.models import (
    EvaluationWindow,
    Source,
    WindowType,
    WorkItemType,
)
from em_radar_core.models.evaluation import TeamProfile

from em_radar_connector_demo.connector import DemoConnector
from em_radar_connector_gitlab.connector import GitLabConnector
from em_radar_connector_jira.connector import JiraConnector

# ---------------------------------------------------------------------------
# HTTP mock helpers for connectors that require network
# ---------------------------------------------------------------------------


def _jira_mock_factory(handler):
    """Return a client factory that routes all requests through handler."""

    def factory(**kwargs):
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    return factory


def _gitlab_mock_factory(handler):
    def factory(**kwargs):
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    return factory


def _jira_success_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if "myself" in path:
        return httpx.Response(200, json={"displayName": "Test User", "accountId": "user-1"})
    if "mypermissions" in path:
        return httpx.Response(
            200, json={"permissions": {"BROWSE_PROJECTS": {"havePermission": True}}}
        )
    if "/project" in path and "search" not in path:
        return httpx.Response(200, json=[{"key": "DEMO", "name": "Demo Project", "id": "1"}])
    if "search" in path:
        return httpx.Response(200, json={"issues": [], "total": 0, "startAt": 0, "maxResults": 50})
    return httpx.Response(200, json={"values": [], "total": 0, "isLast": True})


def _gitlab_success_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if "/user" in path and "personal_access_tokens" not in path:
        return httpx.Response(200, json={"name": "Test User", "id": 1, "username": "test"})
    if "personal_access_tokens" in path:
        return httpx.Response(200, json={"scopes": ["read_api"]})
    return httpx.Response(200, json=[])


# ---------------------------------------------------------------------------
# Non-conforming stub to prove the suite catches violations
# ---------------------------------------------------------------------------


class _BadCapabilityConnector:
    """Declares provides_workitems=True but does NOT implement WorkItemProvider."""

    name: ClassVar[str] = "bad-cap"
    display_name: ClassVar[str] = "Bad Capability Connector"
    config_schema: ClassVar[dict[str, object]] = {"type": "object"}
    min_model_version: ClassVar[int] = 1

    def __init__(self, config: dict[str, object]) -> None:
        pass

    async def test_connection(self) -> ConnectionTestResult:
        return ConnectionTestResult(ok=True, detail="connected")

    @classmethod
    def describe_capabilities(cls) -> Capabilities:
        del cls
        return Capabilities(provides_workitems=True)  # lies: not a WorkItemProvider

    async def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Conforming fixture entries
# ---------------------------------------------------------------------------


@pytest.fixture(
    params=["demo", "jira", "gitlab"],
    ids=["demo", "jira", "gitlab"],
)
def conforming_connector(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch):
    """Return a ready-to-use connector instance for each conforming connector."""
    name = request.param
    if name == "demo":
        return DemoConnector({})
    if name == "jira":
        import em_radar_connector_jira.connector as jira_mod

        monkeypatch.setattr(jira_mod, "CLIENT_FACTORY", _jira_mock_factory(_jira_success_handler))
        return JiraConnector({"base_url": "https://jira.example.com", "token": "tok"})
    if name == "gitlab":
        import em_radar_connector_gitlab.connector as gl_mod

        monkeypatch.setattr(gl_mod, "CLIENT_FACTORY", _gitlab_mock_factory(_gitlab_success_handler))
        return GitLabConnector({"base_url": "https://gitlab.example.com", "token": "tok"})
    raise ValueError(f"unknown connector: {name}")


# ---------------------------------------------------------------------------
# Contract assertions — all must hold for every conforming connector
# ---------------------------------------------------------------------------


def test_name_and_display_name_are_nonempty_strings(conforming_connector) -> None:
    cls = type(conforming_connector)
    assert isinstance(cls.name, str) and cls.name
    assert isinstance(cls.display_name, str) and cls.display_name


def test_config_schema_is_a_dict(conforming_connector) -> None:
    assert isinstance(type(conforming_connector).config_schema, dict)


def test_describe_capabilities_returns_capabilities_instance(conforming_connector) -> None:
    caps = type(conforming_connector).describe_capabilities()
    assert isinstance(caps, Capabilities)


def test_capabilities_match_implemented_protocols(conforming_connector) -> None:
    """If a connector declares a capability, it must implement the matching provider protocol."""
    caps = type(conforming_connector).describe_capabilities()
    if caps.provides_workitems:
        assert isinstance(conforming_connector, WorkItemProvider), (
            f"{type(conforming_connector).name} declares provides_workitems but "
            "does not implement WorkItemProvider"
        )
    if caps.provides_mergerequests:
        assert isinstance(conforming_connector, MergeRequestProvider), (
            f"{type(conforming_connector).name} declares provides_mergerequests but "
            "does not implement MergeRequestProvider"
        )
    if caps.provides_reviews:
        assert isinstance(conforming_connector, ReviewProvider)
    if caps.provides_transitions:
        assert isinstance(conforming_connector, TransitionProvider)


def test_test_connection_returns_connection_test_result(conforming_connector) -> None:
    result = asyncio.run(conforming_connector.test_connection())
    assert isinstance(result, ConnectionTestResult)
    assert isinstance(result.ok, bool)
    assert isinstance(result.detail, str)


def test_workitem_provider_returns_valid_work_items(conforming_connector) -> None:
    if not isinstance(conforming_connector, WorkItemProvider):
        pytest.skip("not a WorkItemProvider")
    team = TeamProfile(name="t", created_at=_static_now(), updated_at=_static_now())
    window = EvaluationWindow(
        window_type=WindowType.DATE_RANGE,
        start=_static_now(),
        end=_static_now(),
        team_profile_id=team.id,
    )
    scope = WorkItemScope(project_external_ids=["DEMO"])

    async def collect():
        return [item async for item in conforming_connector.fetch_workitems(scope, window)]

    items = asyncio.run(collect())
    for item in items:
        assert isinstance(item.type, WorkItemType)
        assert isinstance(item.source, Source)
        assert item.key


def test_mergerequest_provider_returns_valid_mergerequests(conforming_connector) -> None:
    from em_radar_core.connectors import MergeRequestScope as MRScope
    from em_radar_core.models import MergeRequestState

    if not isinstance(conforming_connector, MergeRequestProvider):
        pytest.skip("not a MergeRequestProvider")
    team = TeamProfile(name="t", created_at=_static_now(), updated_at=_static_now())
    window = EvaluationWindow(
        window_type=WindowType.DATE_RANGE,
        start=_static_now(),
        end=_static_now(),
        team_profile_id=team.id,
    )
    scope = MRScope(repository_external_ids=["repo-1"])

    async def collect():
        return [mr async for mr in conforming_connector.fetch_mergerequests(scope, window)]

    mrs = asyncio.run(collect())
    for mr in mrs:
        assert isinstance(mr.state, MergeRequestState)
        assert isinstance(mr.source, Source)


def test_connector_base_protocol_satisfied(conforming_connector) -> None:
    assert isinstance(conforming_connector, ConnectorBase)


def test_close_is_awaitable(conforming_connector) -> None:
    asyncio.run(conforming_connector.close())


# ---------------------------------------------------------------------------
# Negative test: non-conforming connector MUST fail capability-protocol check
# ---------------------------------------------------------------------------


def test_bad_capability_connector_fails_protocol_check() -> None:
    """_BadCapabilityConnector lies about provides_workitems — the contract must catch it."""
    bad = _BadCapabilityConnector({})
    caps = type(bad).describe_capabilities()

    assert caps.provides_workitems is True
    assert not isinstance(bad, WorkItemProvider), (
        "_BadCapabilityConnector must NOT satisfy WorkItemProvider"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _static_now():
    from datetime import datetime, timezone

    return datetime(2026, 1, 20, 12, tzinfo=timezone.utc)
