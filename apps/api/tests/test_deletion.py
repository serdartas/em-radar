"""Tests for M7-05: delete connection + cached data + report history."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, select

from em_radar_core.models import (
    Board,
    BoardType,
    MergeRequest,
    MergeRequestState,
    Project,
    Repository,
    Source,
    Sprint,
    SprintState,
    User,
    WorkItem,
    WorkItemType,
    StatusCategory,
)
from em_radar_api.repositories.canonical import persist_fetch
from em_radar_api.tables import (
    BoardTable,
    ProjectTable,
    ReportJobTable,
    ReportTable,
    SignalFindingTable,
    SprintTable,
    UserTable,
    WorkItemTable,
    EvaluationWindowTable,
    MergeRequestTable,
    RepositoryTable,
)


_NOW = datetime(2026, 7, 1, 12, tzinfo=UTC)


def _create_jira_connection(api_client: TestClient, name: str = "Jira Prod") -> str:
    return api_client.post(
        "/api/connections",
        json={"name": name, "connector_name": "jira", "config": {}},
    ).json()["id"]


def _create_gitlab_connection(api_client: TestClient, name: str = "GitLab Prod") -> str:
    return api_client.post(
        "/api/connections",
        json={"name": name, "connector_name": "gitlab", "config": {}},
    ).json()["id"]


def _create_scope(api_client: TestClient, connection_id: str) -> str:
    return api_client.post(
        "/api/scopes",
        json={
            "connection_id": connection_id,
            "name": "Platform Board",
            "scope_type": "board",
            "external_ref": {"type": "jira_board", "id": "20000"},
            "capabilities": ["sprint"],
        },
    ).json()["id"]


def _create_team(
    api_client: TestClient,
    connection_id: str,
    scope_id: str,
    *,
    code_connection_id: str | None = None,
) -> str:
    payload: dict[str, object] = {
        "name": f"Team-{scope_id[:8]}",
        "connection_ids": [connection_id],
        "scope_ids": [scope_id],
        "working_mode": "kanban",
        "signal_config_group_ids": [],
    }
    if code_connection_id is not None:
        payload["code_connection_id"] = code_connection_id
    return api_client.post("/api/teams", json=payload).json()["id"]


def _seed_jira_data(session_factory: sessionmaker[Session]) -> None:
    """Insert minimal Jira canonical entities into the DB."""
    user = User(id=uuid4(), source=Source.JIRA, external_id="u1", display_name="Alice")
    project = Project(id=uuid4(), source=Source.JIRA, external_id="p1", key="PLAT", name="Platform")
    board = Board(
        id=uuid4(),
        source=Source.JIRA,
        external_id="b1",
        project_id=project.id,
        name="Scrum",
        type=BoardType.SCRUM,
    )
    sprint = Sprint(
        id=uuid4(),
        source=Source.JIRA,
        external_id="sp1",
        board_id=board.id,
        name="Sprint 1",
        state=SprintState.ACTIVE,
    )
    work_item = WorkItem(
        id=uuid4(),
        source=Source.JIRA,
        external_id="PLAT-1",
        project_id=project.id,
        key="PLAT-1",
        type=WorkItemType.TASK,
        title="Test task",
        status="In Progress",
        status_category=StatusCategory.IN_PROGRESS,
        created_at=_NOW,
        updated_at=_NOW,
    )
    with session_factory() as session:
        persist_fetch(
            session,
            users=[user],
            projects=[project],
            boards=[board],
            sprints=[sprint],
            workitems=[work_item],
        )


def _seed_gitlab_data(session_factory: sessionmaker[Session]) -> None:
    """Insert minimal GitLab canonical entities into the DB."""
    user = User(id=uuid4(), source=Source.GITLAB, external_id="gu1", display_name="Bob")
    repo = Repository(
        id=uuid4(),
        source=Source.GITLAB,
        external_id="r1",
        name="backend",
        full_path="org/backend",
        default_branch="main",
    )
    mr = MergeRequest(
        id=uuid4(),
        source=Source.GITLAB,
        external_id="mr1",
        repository_id=repo.id,
        iid=1,
        title="Fix bug",
        state=MergeRequestState.OPEN,
        author_id=user.id,
        target_branch="main",
        source_branch="fix/bug",
        created_at=_NOW,
        updated_at=_NOW,
    )
    with session_factory() as session:
        persist_fetch(session, users=[user], repositories=[repo], mergerequests=[mr])


# ---------------------------------------------------------------------------
# Delete connection + cached data
# ---------------------------------------------------------------------------


def test_delete_free_connection_removes_it(api_client: TestClient) -> None:
    conn_id = _create_jira_connection(api_client)
    assert api_client.delete(f"/api/connections/{conn_id}").status_code == 204
    assert api_client.get("/api/connections").json() == []


def test_delete_connection_removes_cached_canonical_entities(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    """Free delete (no force, no dependents) removes cached data when it is the only connection."""
    _seed_jira_data(session_factory)

    conn_id = _create_jira_connection(api_client)

    # Verify data exists before delete.
    with session_factory() as session:
        assert session.exec(select(UserTable).where(UserTable.source == "jira")).first() is not None
        assert session.exec(select(ProjectTable)).first() is not None

    # No ?force — a free connection with no dependents must remove its cached data.
    assert api_client.delete(f"/api/connections/{conn_id}").status_code == 204

    with session_factory() as session:
        assert session.exec(select(UserTable).where(UserTable.source == "jira")).first() is None
        assert session.exec(select(ProjectTable)).first() is None
        assert session.exec(select(BoardTable)).first() is None
        assert session.exec(select(SprintTable)).first() is None
        assert session.exec(select(WorkItemTable)).first() is None


def test_delete_one_of_two_same_source_connections_retains_cached_data(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    """Deleting one of two same-source connections must not wipe the shared cached data."""
    _seed_jira_data(session_factory)
    conn_id_1 = _create_jira_connection(api_client, "Jira A")
    conn_id_2 = _create_jira_connection(api_client, "Jira B")

    # Delete first connection — sibling still exists, cache must be retained.
    assert api_client.delete(f"/api/connections/{conn_id_1}").status_code == 204

    with session_factory() as session:
        assert session.exec(select(UserTable).where(UserTable.source == "jira")).first() is not None
        assert session.exec(select(ProjectTable)).first() is not None

    # Delete second (last) connection — cache must now be removed.
    assert api_client.delete(f"/api/connections/{conn_id_2}").status_code == 204

    with session_factory() as session:
        assert session.exec(select(UserTable).where(UserTable.source == "jira")).first() is None
        assert session.exec(select(ProjectTable)).first() is None


def test_delete_connection_blocked_when_team_depends_via_scope(
    api_client: TestClient,
) -> None:
    conn_id = _create_jira_connection(api_client)
    scope_id = _create_scope(api_client, conn_id)
    team_id = _create_team(api_client, conn_id, scope_id)

    response = api_client.delete(f"/api/connections/{conn_id}")
    assert response.status_code == 409
    body = response.json()
    assert "dependent_teams" in body["detail"]
    teams = body["detail"]["dependent_teams"]
    assert any(t["id"] == team_id for t in teams)


def test_delete_connection_blocked_when_team_depends_via_code_connection(
    api_client: TestClient,
) -> None:
    jira_conn_id = _create_jira_connection(api_client)
    gitlab_conn_id = _create_gitlab_connection(api_client)
    scope_id = _create_scope(api_client, jira_conn_id)
    team_id = _create_team(api_client, jira_conn_id, scope_id, code_connection_id=gitlab_conn_id)

    response = api_client.delete(f"/api/connections/{gitlab_conn_id}")
    assert response.status_code == 409
    body = response.json()
    teams = body["detail"]["dependent_teams"]
    assert any(t["id"] == team_id for t in teams)


def test_delete_connection_force_removes_team_references_and_scope(
    api_client: TestClient,
) -> None:
    conn_id = _create_jira_connection(api_client)
    scope_id = _create_scope(api_client, conn_id)
    team_id = _create_team(api_client, conn_id, scope_id)

    assert api_client.delete(f"/api/connections/{conn_id}?force=true").status_code == 204

    # Connection is gone.
    assert api_client.get("/api/connections").json() == []

    # Scope is gone.
    scopes = api_client.get(f"/api/scopes?connection_id={conn_id}").json()
    assert scopes == []

    # Team still exists but its connection/scope refs are cleared.
    team = api_client.get(f"/api/teams/{team_id}").json()
    assert conn_id not in team["connection_ids"]
    assert conn_id not in team["scope_ids"]


def test_delete_connection_force_clears_code_connection_id(
    api_client: TestClient,
) -> None:
    jira_conn_id = _create_jira_connection(api_client)
    gitlab_conn_id = _create_gitlab_connection(api_client)
    scope_id = _create_scope(api_client, jira_conn_id)
    team_id = _create_team(api_client, jira_conn_id, scope_id, code_connection_id=gitlab_conn_id)

    assert api_client.delete(f"/api/connections/{gitlab_conn_id}?force=true").status_code == 204

    team = api_client.get(f"/api/teams/{team_id}").json()
    assert team.get("code_connection_id") is None


def test_delete_connection_does_not_touch_source_systems(
    api_client: TestClient,
    monkeypatch,
) -> None:
    """Deletion must never make outbound HTTP calls."""
    import httpx

    def _raise(*args: object, **kwargs: object) -> None:
        raise AssertionError("outbound request made during deletion")

    monkeypatch.setattr(httpx, "AsyncClient", _raise)

    conn_id = _create_jira_connection(api_client)
    assert api_client.delete(f"/api/connections/{conn_id}").status_code == 204


def test_delete_connection_scope_only_removes_same_source_canonical_data(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    """Deleting a Jira connection must not remove GitLab cached data."""
    _seed_jira_data(session_factory)
    _seed_gitlab_data(session_factory)

    conn_id = _create_jira_connection(api_client)
    assert api_client.delete(f"/api/connections/{conn_id}?force=true").status_code == 204

    with session_factory() as session:
        # Jira data is gone.
        assert session.exec(select(UserTable).where(UserTable.source == "jira")).first() is None
        # GitLab data is intact.
        assert (
            session.exec(select(UserTable).where(UserTable.source == "gitlab")).first() is not None
        )
        assert session.exec(select(RepositoryTable)).first() is not None
        assert session.exec(select(MergeRequestTable)).first() is not None


# ---------------------------------------------------------------------------
# Delete report history
# ---------------------------------------------------------------------------


def _create_minimal_report(
    session_factory: sessionmaker[Session],
    team_id: UUID,
) -> UUID:
    """Directly insert a minimal report row for testing."""
    from em_radar_core.models import ReportStatus, WindowType

    window = EvaluationWindowTable(
        id=uuid4(),
        window_type=WindowType.DATE_RANGE,
        start=datetime(2026, 6, 1, tzinfo=UTC).replace(tzinfo=None),
        end=datetime(2026, 7, 1, tzinfo=UTC).replace(tzinfo=None),
        team_profile_id=team_id,
    )
    report = ReportTable(
        id=uuid4(),
        evaluation_window_id=window.id,
        status=ReportStatus.SUCCEEDED,
        started_at=datetime(2026, 7, 1, tzinfo=UTC).replace(tzinfo=None),
        findings_count_by_severity={},
        signal_pack_snapshot={},
    )
    with session_factory() as session:
        session.add(window)
        session.add(report)
        session.commit()
    return report.id


def _create_minimal_job(
    session_factory: sessionmaker[Session],
    team_id: UUID,
    report_id: UUID | None = None,
) -> UUID:
    """Directly insert a minimal ReportJobTable row for testing."""
    job = ReportJobTable(
        id=uuid4(),
        team_profile_id=team_id,
        status="done",
        enqueued_at=datetime(2026, 7, 1, tzinfo=UTC).replace(tzinfo=None),
        report_id=report_id,
    )
    with session_factory() as session:
        session.add(job)
        session.commit()
    return job.id


def test_delete_all_report_history(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    conn_id = _create_jira_connection(api_client)
    scope_id = _create_scope(api_client, conn_id)
    team_id = UUID(_create_team(api_client, conn_id, scope_id))

    report_id = _create_minimal_report(session_factory, team_id)
    _create_minimal_report(session_factory, team_id)
    _create_minimal_job(session_factory, team_id, report_id)

    reports_before = api_client.get("/api/reports").json()
    assert len(reports_before) == 2

    assert api_client.delete("/api/reports").status_code == 204

    assert api_client.get("/api/reports").json() == []

    with session_factory() as session:
        assert session.exec(select(ReportTable)).first() is None
        assert session.exec(select(EvaluationWindowTable)).first() is None
        assert session.exec(select(SignalFindingTable)).first() is None
        assert session.exec(select(ReportJobTable)).first() is None


def test_delete_report_history_per_team(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    conn_id = _create_jira_connection(api_client)
    scope_a_id = _create_scope(api_client, conn_id)

    scope_b_resp = api_client.post(
        "/api/scopes",
        json={
            "connection_id": conn_id,
            "name": "Board B",
            "scope_type": "board",
            "external_ref": {"type": "jira_board", "id": "20001"},
            "capabilities": [],
        },
    )
    scope_b_id = scope_b_resp.json()["id"]

    team_a_id = UUID(_create_team(api_client, conn_id, scope_a_id))
    team_b_id = UUID(_create_team(api_client, conn_id, scope_b_id))

    _create_minimal_report(session_factory, team_a_id)
    report_b_id = _create_minimal_report(session_factory, team_b_id)
    _create_minimal_job(session_factory, team_a_id)
    _create_minimal_job(session_factory, team_b_id)

    assert api_client.delete(f"/api/reports?team_id={team_a_id}").status_code == 204

    remaining = api_client.get("/api/reports").json()
    assert len(remaining) == 1
    assert remaining[0]["id"] == str(report_b_id)

    with session_factory() as session:
        jobs = list(session.exec(select(ReportJobTable)))
        assert len(jobs) == 1
        assert jobs[0].team_profile_id == team_b_id


def test_delete_report_history_removes_job_without_window(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    """A report that failed before persisting an evaluation window leaves a job row but no window.
    Per-team deletion must still remove that job row rather than short-circuiting on empty windows."""
    conn_id = _create_jira_connection(api_client)
    scope_id = _create_scope(api_client, conn_id)
    team_id = UUID(_create_team(api_client, conn_id, scope_id))

    _create_minimal_job(session_factory, team_id)

    with session_factory() as session:
        assert session.exec(select(EvaluationWindowTable)).first() is None
        assert session.exec(select(ReportJobTable)).first() is not None

    assert api_client.delete(f"/api/reports?team_id={team_id}").status_code == 204

    with session_factory() as session:
        assert session.exec(select(ReportJobTable)).first() is None


def test_delete_report_history_unknown_team_is_noop(api_client: TestClient) -> None:
    assert api_client.delete(f"/api/reports?team_id={uuid4()}").status_code == 204


# ---------------------------------------------------------------------------
# Connector type change clears old cached data
# ---------------------------------------------------------------------------


def test_patch_connector_name_clears_old_source_canonical_data(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    """Changing a connection's connector_name removes cached data for the old source type."""
    _seed_jira_data(session_factory)
    conn_id = _create_jira_connection(api_client)

    with session_factory() as session:
        assert session.exec(select(UserTable).where(UserTable.source == "jira")).first() is not None

    resp = api_client.patch(
        f"/api/connections/{conn_id}",
        json={"connector_name": "gitlab"},
    )
    assert resp.status_code == 200

    with session_factory() as session:
        assert session.exec(select(UserTable).where(UserTable.source == "jira")).first() is None
        assert session.exec(select(ProjectTable)).first() is None


def test_patch_connector_name_preserves_old_source_data_when_sibling_remains(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    """Old-source cache is kept when a sibling Jira connection still exists after the type change."""
    _seed_jira_data(session_factory)
    conn_id_1 = _create_jira_connection(api_client, "Jira A")
    _create_jira_connection(api_client, "Jira B")

    resp = api_client.patch(
        f"/api/connections/{conn_id_1}",
        json={"connector_name": "gitlab"},
    )
    assert resp.status_code == 200

    with session_factory() as session:
        assert session.exec(select(UserTable).where(UserTable.source == "jira")).first() is not None
        assert session.exec(select(ProjectTable)).first() is not None


# ---------------------------------------------------------------------------
# Atomicity: connector_name change + cache cleanup commit together
# ---------------------------------------------------------------------------


def test_patch_connector_name_type_change_is_atomic(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch,
) -> None:
    """If cache cleanup raises after the connector_name PATCH, the whole update rolls back."""
    import em_radar_api.repositories.source_connections as sc_repo

    _seed_jira_data(session_factory)
    conn_id = _create_jira_connection(api_client)

    def _boom(session, source) -> None:  # noqa: ANN001
        raise RuntimeError("simulated cleanup failure")

    monkeypatch.setattr(sc_repo, "delete_canonical_data_for_source", _boom)

    # Disable exception re-raise so we can inspect the 500 response without the TestClient
    # propagating the RuntimeError.
    from fastapi.testclient import TestClient as _TC

    non_raising_client = _TC(api_client.app, raise_server_exceptions=False)
    resp = non_raising_client.patch(
        f"/api/connections/{conn_id}", json={"connector_name": "gitlab"}
    )
    assert resp.status_code == 500

    # connector_name must be rolled back — still "jira".
    all_conns = api_client.get("/api/connections").json()
    conn = next((c for c in all_conns if c["id"] == conn_id), None)
    assert conn is not None, f"connection {conn_id} not found in {all_conns}"
    assert conn["connector_name"] == "jira"

    # Old-source cached rows must still be present.
    with session_factory() as session:
        assert session.exec(select(UserTable).where(UserTable.source == "jira")).first() is not None
        assert session.exec(select(ProjectTable)).first() is not None


# ---------------------------------------------------------------------------
# Sprint label is preserved in report export after cache deletion
# ---------------------------------------------------------------------------


def _create_sprint_report(
    session_factory: sessionmaker[Session],
    team_id: UUID,
    sprint_id: UUID,
    sprint_label: str,
) -> UUID:
    """Insert a minimal sprint-window report with a stored sprint_label snapshot."""
    from em_radar_core.models import ReportStatus, WindowType

    window = EvaluationWindowTable(
        id=uuid4(),
        window_type=WindowType.SPRINT,
        team_profile_id=team_id,
        sprint_id=sprint_id,
        sprint_label=sprint_label,
    )
    report = ReportTable(
        id=uuid4(),
        evaluation_window_id=window.id,
        status=ReportStatus.SUCCEEDED,
        started_at=datetime(2026, 7, 1, tzinfo=UTC).replace(tzinfo=None),
        findings_count_by_severity={},
        signal_pack_snapshot={},
    )
    with session_factory() as session:
        session.add(window)
        session.add(report)
        session.commit()
    return report.id


def test_sprint_label_preserved_in_export_after_cache_deletion(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    """Cached-data deletion must not degrade retained sprint reports (flows §8).

    The EvaluationWindowTable.sprint_label snapshot keeps the sprint name readable even
    after sprint_id is nulled (FK integrity) when the last Jira connection is deleted.
    """
    _seed_jira_data(session_factory)
    conn_id = _create_jira_connection(api_client)
    scope_id = _create_scope(api_client, conn_id)
    team_id = UUID(_create_team(api_client, conn_id, scope_id))

    # Find the persisted sprint so we can reference it in the window row.
    with session_factory() as session:
        sprint_row = session.exec(select(SprintTable)).first()
        assert sprint_row is not None
        sprint_db_id = sprint_row.id
        sprint_name = sprint_row.name

    report_id = _create_sprint_report(session_factory, team_id, sprint_db_id, sprint_name)

    # Baseline: export works before deletion and contains the sprint label.
    pre_resp = api_client.get(f"/api/reports/{report_id}/export.md")
    assert pre_resp.status_code == 200
    assert sprint_name in pre_resp.text

    # Delete the last Jira connection (force=true because a team references it).
    # Clears the sprint cache and nulls sprint_id on the evaluation window.
    assert api_client.delete(f"/api/connections/{conn_id}?force=true").status_code == 204

    with session_factory() as session:
        assert session.exec(select(SprintTable)).first() is None
        window_row = session.exec(
            select(EvaluationWindowTable).where(EvaluationWindowTable.team_profile_id == team_id)
        ).first()
        assert window_row is not None
        assert window_row.sprint_id is None  # FK nulled
        assert window_row.sprint_label == sprint_name  # snapshot preserved

    # Export must still show the sprint label — NOT "Sprint unknown".
    post_resp = api_client.get(f"/api/reports/{report_id}/export.md")
    assert post_resp.status_code == 200
    assert sprint_name in post_resp.text
    assert "Sprint unknown" not in post_resp.text
