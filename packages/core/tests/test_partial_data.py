"""Partial-data handling (M5-08): a typed connector error for one source does not fail the report.

The report runner catches ConnectorRateLimitedError, ConnectorTransientError, and ConnectorAuthError
during fetch, continues with available data, and surfaces a partial-data note.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel

import em_radar_api.tables  # noqa: F401 — registers table metadata

from em_radar_api.db import create_db_engine, create_session_factory, get_session, get_write_session
from em_radar_api.main import app
from em_radar_core.connectors import (
    Capabilities,
    ConnectionTestResult,
    ConnectorTransientError,
    MergeRequestScope,
)
from em_radar_core.models import (
    EvaluationWindow,
    MergeRequest,
    Repository,
    Source,
)

from test_source_connection_routes import (
    JiraTestConnector,
    _create_board_scope,
    _create_jira_connection,
    _create_jira_team,
)


# ---------------------------------------------------------------------------
# Test client fixture (self-contained)
# ---------------------------------------------------------------------------


@pytest.fixture
def _api_harness(tmp_path: Path) -> Iterator[SimpleNamespace]:
    engine = create_db_engine(tmp_path / "partial-data-test.db")
    SQLModel.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    def _session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_write_session] = _session
    try:
        yield SimpleNamespace(client=TestClient(app), session_factory=session_factory)
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


@pytest.fixture
def api_client(_api_harness: SimpleNamespace) -> TestClient:
    return _api_harness.client


# ---------------------------------------------------------------------------
# Fake GitLab connector that raises a transient error on fetch
# ---------------------------------------------------------------------------


class _FailingGitLabConnector:
    """GitLab connector stub that raises ConnectorTransientError on fetch_mergerequests."""

    name: ClassVar[str] = "gitlab"
    display_name: ClassVar[str] = "GitLab (failing stub)"
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
                id=UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890"),
                source=Source.GITLAB,
                external_id="repo-1",
                name="my-repo",
                full_path="group/my-repo",
                default_branch="main",
            )
        ]

    async def fetch_mergerequests(
        self,
        scope: MergeRequestScope,
        window: EvaluationWindow,
    ) -> AsyncIterator[MergeRequest]:
        raise ConnectorTransientError("GitLab is temporarily unavailable")
        yield  # make it an async generator


def _create_gitlab_connection(api_client: TestClient) -> str:
    return api_client.post(
        "/api/connections",
        json={"name": "GitLab", "connector_name": "gitlab", "config": {}},
    ).json()["id"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_transient_code_source_error_produces_partial_data_note(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When GitLab raises a transient error, the report is still succeeded and carries a note."""
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [JiraTestConnector, _FailingGitLabConnector],
    )

    jira_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, jira_id, ["sprint", "statuses", "labels"])
    gitlab_id = _create_gitlab_connection(api_client)
    team_id = api_client.post(
        "/api/teams",
        json={
            "name": "Partial-data team",
            "connection_ids": [jira_id],
            "scope_ids": [scope_id],
            "code_connection_id": gitlab_id,
            "working_mode": "scrum",
            "sprint_length_days": 14,
        },
    ).json()["id"]

    response = api_client.post(
        "/api/reports/run", json={"connector": "jira", "team_profile_id": team_id}
    )

    assert response.status_code == 200
    report = response.json()
    assert report["status"] == "succeeded", "report must succeed even when one source fails"

    snapshot = report["signal_pack_snapshot"]
    notes = snapshot.get("partial_data_notes", [])
    assert len(notes) == 1, f"expected one partial-data note, got: {notes}"
    assert notes[0]["source"] == "code"
    assert "ConnectorTransientError" in notes[0]["reason"]


def test_no_partial_data_note_when_all_sources_succeed(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When all sources succeed, partial_data_notes must be empty."""
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [JiraTestConnector],
    )

    jira_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, jira_id, ["sprint", "statuses", "labels"])
    team_id = _create_jira_team(api_client, jira_id, scope_id, "scrum", sprint_length_days=14)

    response = api_client.post(
        "/api/reports/run", json={"connector": "jira", "team_profile_id": team_id}
    )

    assert response.status_code == 200
    snapshot = response.json()["signal_pack_snapshot"]
    assert snapshot.get("partial_data_notes", []) == []
