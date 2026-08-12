"""Connector contract test suite (connector spec §13).

Uses the ``connector_cls`` fixture provided by the ``em-radar-connector-contracts``
pytest plugin (registered via ``pytest11`` entry point). The plugin auto-discovers
every connector registered under the ``em_radar.connectors`` entry-point group, so
private connector packages gain contract coverage just by adding an entry point.

A deliberately non-conforming stub connector is also tested to prove the suite
catches violations.
"""

from __future__ import annotations

import asyncio
from typing import ClassVar

import httpx
import pytest

from em_radar_core.connectors import (
    Capabilities,
    CommentProvider,
    ConnectionTestResult,
    ConnectorAuthError,
    ConnectorBase,
    ConnectorConfigError,
    MergeRequestProvider,
    MergeRequestScope,
    ReviewProvider,
    TransitionProvider,
    WorkItemProvider,
    WorkItemScope,
)
from em_radar_core.models import (
    EvaluationWindow,
    MergeRequestState,
    Source,
    WindowType,
    WorkItemType,
)
from em_radar_core.models.evaluation import TeamProfile

# ---------------------------------------------------------------------------
# HTTP mock helpers
# ---------------------------------------------------------------------------


def _client_factory(handler):
    def factory(**kwargs):
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    return factory


def _jira_success_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if "myself" in path:
        return httpx.Response(200, json={"displayName": "Test User", "accountId": "u-1"})
    if "mypermissions" in path:
        return httpx.Response(
            200, json={"permissions": {"BROWSE_PROJECTS": {"havePermission": True}}}
        )
    if "/project" in path and "search" not in path:
        return httpx.Response(200, json=[{"key": "DEMO", "name": "Demo Project", "id": "1"}])
    if "search" in path:
        return httpx.Response(
            200,
            json={
                "issues": [
                    {
                        "key": "DEMO-1",
                        "id": "10001",
                        "fields": {
                            "summary": "Demo issue",
                            "issuetype": {"name": "Story"},
                            "status": {
                                "name": "In Progress",
                                "statusCategory": {"key": "indeterminate"},
                            },
                            "project": {"key": "DEMO", "id": "10000"},
                            "labels": [],
                            "components": [],
                            "created": "2026-01-01T00:00:00.000+0000",
                            "updated": "2026-01-10T00:00:00.000+0000",
                            "resolutiondate": None,
                            "duedate": None,
                            "assignee": None,
                            "reporter": None,
                            "parent": None,
                            "description": None,
                        },
                    }
                ],
                "total": 1,
                "startAt": 0,
                "maxResults": 50,
            },
        )
    return httpx.Response(200, json={"values": [], "total": 0, "isLast": True})


def _jira_auth_error_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(401, json={"errorMessages": ["Unauthorized"]})


def _jira_multipage_handler_factory():
    """Return a Jira handler that simulates two pages of search results (page 1 + page 2)."""
    _issue = lambda key: {  # noqa: E731
        "key": key,
        "id": key,
        "fields": {
            "summary": f"Issue {key}",
            "issuetype": {"name": "Story"},
            "status": {"name": "In Progress", "statusCategory": {"key": "indeterminate"}},
            "project": {"key": "DEMO", "id": "10000"},
            "labels": [],
            "components": [],
            "created": "2026-01-01T00:00:00.000+0000",
            "updated": "2026-01-10T00:00:00.000+0000",
            "resolutiondate": None,
            "duedate": None,
            "assignee": None,
            "reporter": None,
            "parent": None,
            "description": None,
        },
    }
    page_calls = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if "myself" in path:
            return httpx.Response(200, json={"displayName": "User", "accountId": "u"})
        if "mypermissions" in path:
            return httpx.Response(
                200, json={"permissions": {"BROWSE_PROJECTS": {"havePermission": True}}}
            )
        if "search" in path:
            page_calls[0] += 1
            if page_calls[0] == 1:
                return httpx.Response(
                    200,
                    json={"issues": [_issue("DEMO-1")], "total": 2, "nextPageToken": "page2"},
                )
            return httpx.Response(200, json={"issues": [_issue("DEMO-2")], "total": 2})
        return httpx.Response(200, json={"values": [], "total": 0, "isLast": True})

    return handler


_GITLAB_MR_PAYLOAD = {
    "id": 1,
    "iid": 1,
    "title": "Demo MR",
    "description": None,
    "state": "opened",
    "draft": False,
    "target_branch": "main",
    "source_branch": "feature/demo",
    "author": {"id": 42},
    "created_at": "2026-01-01T00:00:00.000Z",
    "updated_at": "2026-01-10T00:00:00.000Z",
    "merged_at": None,
    "closed_at": None,
    "changes_count": None,
    "additions": None,
    "deletions": None,
    "diff_stats_summary": None,
    "head_pipeline": None,
    "approvals_before_merge": None,
    "user_notes_count": 0,
}


def _gitlab_success_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if "/user" in path and "personal_access_tokens" not in path:
        return httpx.Response(200, json={"name": "Test User", "id": 1, "username": "test"})
    if "personal_access_tokens" in path:
        return httpx.Response(200, json={"scopes": ["read_api"]})
    if "projects" in path and "merge_requests" not in path:
        return httpx.Response(
            200,
            json=[{"id": 1, "name": "demo-repo", "path_with_namespace": "demo/demo-repo"}],
        )
    if "approvals" in path:
        return httpx.Response(200, json={"approved_by": []})
    if "merge_requests" in path:
        parts = path.rstrip("/").split("/")
        # Single MR detail endpoint: path ends with /{iid} (a digit)
        if parts[-1].isdigit():
            return httpx.Response(200, json=_GITLAB_MR_PAYLOAD)
        # MR list endpoint
        return httpx.Response(
            200,
            json=[_GITLAB_MR_PAYLOAD],
            headers={"x-next-page": ""},
        )
    return httpx.Response(200, json=[])


def _gitlab_auth_error_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(401, json={"message": "401 Unauthorized"})


# ---------------------------------------------------------------------------
# Per-connector setup: instantiate, monkeypatch HTTP, and return (connector, bad_config)
# ---------------------------------------------------------------------------


def _setup_connector(connector_cls: type, monkeypatch: pytest.MonkeyPatch):
    """Return ``(connector_instance, bad_config_factory)``.

    ``bad_config_factory`` is a callable that attempts to construct the connector
    with deliberately bad credentials; it should raise ``ConnectorConfigError``,
    or the connector's ``test_connection()`` should return ``ok=False``.
    """
    name = connector_cls.name
    if name == "demo":
        from em_radar_connector_demo.connector import DemoConnector

        return DemoConnector({}), lambda: DemoConnector({"extra": "unexpected"})

    if name == "jira":
        import em_radar_connector_jira.connector as jira_mod

        monkeypatch.setattr(jira_mod, "CLIENT_FACTORY", _client_factory(_jira_success_handler))
        connector = connector_cls({"base_url": "https://jira.example.com", "token": "tok"})

        def bad_factory():
            monkeypatch.setattr(
                jira_mod, "CLIENT_FACTORY", _client_factory(_jira_auth_error_handler)
            )
            return connector_cls({"base_url": "https://jira.example.com", "token": "bad"})

        return connector, bad_factory

    if name == "gitlab":
        import em_radar_connector_gitlab.connector as gl_mod

        monkeypatch.setattr(gl_mod, "CLIENT_FACTORY", _client_factory(_gitlab_success_handler))
        connector = connector_cls({"base_url": "https://gitlab.example.com", "token": "tok"})

        def bad_factory():
            monkeypatch.setattr(
                gl_mod, "CLIENT_FACTORY", _client_factory(_gitlab_auth_error_handler)
            )
            return connector_cls({"base_url": "https://gitlab.example.com", "token": "bad"})

        return connector, bad_factory

    pytest.skip(f"no test setup for connector: {name}")


@pytest.fixture
def conforming_connector(connector_cls, monkeypatch: pytest.MonkeyPatch):
    connector, _ = _setup_connector(connector_cls, monkeypatch)
    return connector


@pytest.fixture
def bad_connector_factory(connector_cls, monkeypatch: pytest.MonkeyPatch):
    _, factory = _setup_connector(connector_cls, monkeypatch)
    return factory


# ---------------------------------------------------------------------------
# Non-conforming stub
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
        return Capabilities(provides_workitems=True)

    async def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _static_now():
    from datetime import datetime, timezone

    return datetime(2026, 1, 20, 12, tzinfo=timezone.utc)


def _date_range_window():
    team = TeamProfile(name="t", created_at=_static_now(), updated_at=_static_now())
    return EvaluationWindow(
        window_type=WindowType.DATE_RANGE,
        start=_static_now(),
        end=_static_now(),
        team_profile_id=team.id,
    )


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
    """If a connector declares a capability, it must implement the matching provider protocol,
    and vice versa — a connector implementing a provider must declare the capability.
    """
    caps = type(conforming_connector).describe_capabilities()
    _assert_cap_protocol_match(conforming_connector, caps.provides_workitems, WorkItemProvider)
    _assert_cap_protocol_match(
        conforming_connector, caps.provides_mergerequests, MergeRequestProvider
    )
    _assert_cap_protocol_match(conforming_connector, caps.provides_reviews, ReviewProvider)
    _assert_cap_protocol_match(conforming_connector, caps.provides_transitions, TransitionProvider)
    _assert_cap_protocol_match(conforming_connector, caps.provides_comments, CommentProvider)


def _assert_cap_protocol_match(connector, declared: bool, protocol: type) -> None:
    implements = isinstance(connector, protocol)
    assert declared == implements, (
        f"{type(connector).name}: declared={declared} but implements={implements} "
        f"for {protocol.__name__}"
    )


def test_test_connection_success_returns_structured_result(conforming_connector) -> None:
    result = asyncio.run(conforming_connector.test_connection())
    assert isinstance(result, ConnectionTestResult)
    assert result.ok is True
    assert isinstance(result.detail, str)


def test_test_connection_bad_config_raises_or_returns_failure(
    connector_cls, bad_connector_factory
) -> None:
    """Bad credentials must raise ConnectorConfigError, a ConnectorError, or return ok=False."""
    from em_radar_core.connectors import ConnectorError

    try:
        bad_connector = bad_connector_factory()
    except ConnectorConfigError:
        return  # connector validates config at construction time — acceptable

    try:
        result = asyncio.run(bad_connector.test_connection())
    except ConnectorError:
        return  # typed error hierarchy — acceptable per spec §10
    else:
        assert isinstance(result, ConnectionTestResult)
        assert result.ok is False, (
            f"{connector_cls.name}: bad credentials should yield ok=False, got ok=True"
        )


def test_workitem_provider_fetch_yields_valid_canonical_models(conforming_connector) -> None:
    if not isinstance(conforming_connector, WorkItemProvider):
        pytest.skip("not a WorkItemProvider")
    scope = WorkItemScope(project_external_ids=["DEMO"])

    async def collect():
        return [
            item async for item in conforming_connector.fetch_workitems(scope, _date_range_window())
        ]

    items = asyncio.run(collect())
    # Contract: items yielded must be valid WorkItem canonical models
    for item in items:
        assert isinstance(item.type, WorkItemType)
        assert isinstance(item.source, Source)
        assert item.key


def test_workitem_provider_handles_empty_scope(conforming_connector) -> None:
    if not isinstance(conforming_connector, WorkItemProvider):
        pytest.skip("not a WorkItemProvider")
    scope = WorkItemScope(project_external_ids=[])

    async def collect():
        return [
            item async for item in conforming_connector.fetch_workitems(scope, _date_range_window())
        ]

    items = asyncio.run(collect())
    assert isinstance(items, list)


def test_mergerequest_provider_fetch_yields_valid_canonical_models(conforming_connector) -> None:
    if not isinstance(conforming_connector, MergeRequestProvider):
        pytest.skip("not a MergeRequestProvider")
    scope = MergeRequestScope(repository_external_ids=["repo-demo"])

    async def collect():
        return [
            mr async for mr in conforming_connector.fetch_mergerequests(scope, _date_range_window())
        ]

    mrs = asyncio.run(collect())
    for mr in mrs:
        assert isinstance(mr.state, MergeRequestState)
        assert isinstance(mr.source, Source)


def test_mergerequest_provider_handles_empty_scope(conforming_connector) -> None:
    if not isinstance(conforming_connector, MergeRequestProvider):
        pytest.skip("not a MergeRequestProvider")
    scope = MergeRequestScope(repository_external_ids=[])

    async def collect():
        return [
            mr async for mr in conforming_connector.fetch_mergerequests(scope, _date_range_window())
        ]

    mrs = asyncio.run(collect())
    assert isinstance(mrs, list)


def test_workitem_pagination_collects_all_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    """Multi-page Jira search (page 1 with nextPageToken + page 2 terminal) must yield both items."""
    import em_radar_connector_jira.connector as jira_mod

    handler = _jira_multipage_handler_factory()
    monkeypatch.setattr(jira_mod, "CLIENT_FACTORY", _client_factory(handler))
    connector = jira_mod.JiraConnector({"base_url": "https://jira.example.com", "token": "tok"})
    scope = WorkItemScope(project_external_ids=["DEMO"])

    async def collect():
        return [item async for item in connector.fetch_workitems(scope, _date_range_window())]

    items = asyncio.run(collect())
    keys = {item.key for item in items}
    assert keys == {"DEMO-1", "DEMO-2"}, f"Expected 2 items across pages, got: {keys}"


def test_connector_errors_use_typed_hierarchy(
    connector_cls, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A connector must raise only ConnectorError subclasses, never raw httpx exceptions."""
    from em_radar_core.connectors import ConnectorError

    name = connector_cls.name
    if name == "demo":
        pytest.skip("demo uses no network; error hierarchy tested via ConnectorConfigError")

    if name == "jira":
        import em_radar_connector_jira.connector as jira_mod

        monkeypatch.setattr(jira_mod, "CLIENT_FACTORY", _client_factory(_jira_auth_error_handler))
        bad = connector_cls({"base_url": "https://jira.example.com", "token": "bad"})
        with pytest.raises(ConnectorError) as exc_info:
            asyncio.run(bad.test_connection())
        assert isinstance(exc_info.value, ConnectorAuthError)
        return

    if name == "gitlab":
        import em_radar_connector_gitlab.connector as gl_mod

        monkeypatch.setattr(gl_mod, "CLIENT_FACTORY", _client_factory(_gitlab_auth_error_handler))
        bad = connector_cls({"base_url": "https://gitlab.example.com", "token": "bad"})
        with pytest.raises(ConnectorError) as exc_info:
            asyncio.run(bad.test_connection())
        assert isinstance(exc_info.value, ConnectorAuthError)
        return

    pytest.skip(f"no error-response mock for connector: {name}")


def test_connector_base_protocol_satisfied(conforming_connector) -> None:
    assert isinstance(conforming_connector, ConnectorBase)


def test_close_is_awaitable(conforming_connector) -> None:
    asyncio.run(conforming_connector.close())


# ---------------------------------------------------------------------------
# Negative test: non-conforming connector MUST fail capability-protocol check
# ---------------------------------------------------------------------------


def test_bad_capability_connector_fails_capabilities_match_check() -> None:
    """_BadCapabilityConnector lies about provides_workitems. The contract assertion must catch it."""
    bad = _BadCapabilityConnector({})
    caps = type(bad).describe_capabilities()

    assert caps.provides_workitems is True
    assert not isinstance(bad, WorkItemProvider)

    with pytest.raises(AssertionError, match="declared=True but implements=False"):
        _assert_cap_protocol_match(bad, caps.provides_workitems, WorkItemProvider)
