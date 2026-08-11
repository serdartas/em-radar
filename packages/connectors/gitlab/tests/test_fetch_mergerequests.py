import asyncio
from collections.abc import Callable
from datetime import datetime, timezone
from uuid import uuid4

import httpx
import pytest

import em_radar_connector_gitlab.connector as gitlab_connector_module
from em_radar_connector_gitlab.connector import GitLabConnector, _stable_id
from em_radar_core.connectors import ConnectorDataError, ConnectorTransientError, MergeRequestScope
from em_radar_core.models import (
    EvaluationWindow,
    MergeRequest,
    MergeRequestState,
    PipelineStatus,
    Source,
    WindowType,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _client_factory_for(
    handler: Callable[[httpx.Request], httpx.Response],
) -> Callable[..., httpx.AsyncClient]:
    def factory(**kwargs: object) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    return factory


def _make_connector(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
) -> GitLabConnector:
    monkeypatch.setattr(gitlab_connector_module, "CLIENT_FACTORY", _client_factory_for(handler))
    return GitLabConnector({"base_url": "https://gitlab.example.com", "token": "token-1234"})


def _is_mr_detail_path(path: str) -> bool:
    """True when the path is a single-MR detail endpoint (last segment is an integer IID)."""
    segments = path.rstrip("/").split("/")
    return len(segments) > 0 and segments[-1].isdigit()


def _mr_payload(
    *,
    mr_id: int = 1001,
    iid: int = 1,
    title: str = "Feature: add endpoint",
    state: str = "opened",
    draft: bool = False,
    work_in_progress: bool = False,
    author_id: int = 42,
    target_branch: str = "main",
    source_branch: str = "feature/add-endpoint",
    created_at: str = "2026-05-01T09:00:00Z",
    updated_at: str = "2026-05-10T12:00:00Z",
    merged_at: str | None = None,
    closed_at: str | None = None,
    user_notes_count: int = 2,
    head_pipeline: dict[str, object] | None = None,
    web_url: str | None = None,
) -> dict[str, object]:
    """Realistic GitLab list-endpoint MR payload.

    Note: ``changes_count`` and ``diff_stats_summary`` are intentionally absent — the REST list
    endpoint does not include them.  Diff stats must come from the single-MR detail endpoint.
    """
    return {
        "id": mr_id,
        "iid": iid,
        "title": title,
        "description": "This is a description",
        "state": state,
        "draft": draft,
        "work_in_progress": work_in_progress,
        "author": {"id": author_id, "name": "Test Author"},
        "target_branch": target_branch,
        "source_branch": source_branch,
        "created_at": created_at,
        "updated_at": updated_at,
        "merged_at": merged_at,
        "closed_at": closed_at,
        "user_notes_count": user_notes_count,
        "head_pipeline": head_pipeline,
        "web_url": web_url or f"https://gitlab.example.com/group/project/-/merge_requests/{iid}",
    }


def _mr_detail_response(
    *,
    changes_count: str | int | None = "3",
    additions: int | None = 10,
    deletions: int | None = 5,
) -> dict[str, object]:
    """Payload returned by the single-MR detail endpoint for diff-stat fields."""
    payload: dict[str, object] = {}
    if changes_count is not None:
        payload["changes_count"] = changes_count
    if additions is not None:
        payload["additions"] = additions
    if deletions is not None:
        payload["deletions"] = deletions
    return payload


def _approvals_response(user_ids: list[int]) -> dict[str, object]:
    return {"approved_by": [{"user": {"id": uid, "name": f"User {uid}"}} for uid in user_ids]}


async def _collect(iterator: object) -> list[MergeRequest]:
    items: list[MergeRequest] = []
    async for item in iterator:
        items.append(item)
    return items


def _date_window() -> EvaluationWindow:
    return EvaluationWindow(
        window_type=WindowType.DATE_RANGE,
        start=datetime(2026, 5, 1, tzinfo=timezone.utc),
        end=datetime(2026, 5, 31, tzinfo=timezone.utc),
        team_profile_id=uuid4(),
    )


def _sprint_window() -> EvaluationWindow:
    return EvaluationWindow(
        window_type=WindowType.SPRINT,
        sprint_id=uuid4(),
        team_profile_id=uuid4(),
    )


# ---------------------------------------------------------------------------
# Full normalization
# ---------------------------------------------------------------------------


def test_fetch_mergerequests_normalizes_open_mr(monkeypatch: pytest.MonkeyPatch) -> None:
    """All scalar fields map correctly for a typical open merge request."""

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if _is_mr_detail_path(request.url.path):
                # Diff stats sourced from the single-MR detail endpoint.
                return httpx.Response(
                    200, json=_mr_detail_response(changes_count="5", additions=20, deletions=8)
                )
            if request.url.path.endswith("/approvals"):
                return httpx.Response(200, json=_approvals_response([10, 11]))
            return httpx.Response(
                200,
                headers={"X-Next-Page": ""},
                json=[
                    _mr_payload(
                        mr_id=2001,
                        iid=7,
                        title="Feature: normalisation test",
                        state="opened",
                        author_id=42,
                        target_branch="main",
                        source_branch="feature/normalisation",
                        created_at="2026-05-01T09:00:00Z",
                        updated_at="2026-05-10T12:00:00Z",
                        user_notes_count=3,
                        head_pipeline={
                            "id": 9001,
                            "status": "success",
                            "updated_at": "2026-05-10T11:00:00Z",
                        },
                    )
                ],
            )

        connector = _make_connector(monkeypatch, handler)
        mrs = await _collect(
            connector.fetch_mergerequests(
                MergeRequestScope(repository_external_ids=["101"]),
                _date_window(),
            )
        )
        await connector.close()

        assert len(mrs) == 1
        mr = mrs[0]

        assert mr.source is Source.GITLAB
        assert mr.external_id == "2001"
        assert mr.iid == 7
        assert mr.title == "Feature: normalisation test"
        assert mr.state is MergeRequestState.OPEN
        assert mr.is_draft is False
        assert mr.target_branch == "main"
        assert mr.source_branch == "feature/normalisation"

        expected_created = datetime(2026, 5, 1, 9, 0, 0, tzinfo=timezone.utc)
        expected_updated = datetime(2026, 5, 10, 12, 0, 0, tzinfo=timezone.utc)
        assert mr.created_at == expected_created
        assert mr.updated_at == expected_updated
        assert mr.merged_at is None
        assert mr.closed_at is None

        # Diff stats sourced from the single-MR detail endpoint.
        assert mr.changed_files_count == 5
        assert mr.additions == 20
        assert mr.deletions == 8

        assert mr.pipeline_status is PipelineStatus.SUCCESS
        assert mr.pipeline_updated_at == datetime(2026, 5, 10, 11, 0, 0, tzinfo=timezone.utc)

        assert mr.approval_count == 2
        assert mr.comment_count == 3

        # Stable IDs are deterministic from project_id and mr global id.
        assert mr.repository_id == _stable_id("repository", "101")
        assert mr.id == _stable_id("mergerequest", "2001")
        assert mr.author_id == _stable_id("user", "42")

    asyncio.run(run())


# ---------------------------------------------------------------------------
# State and draft detection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("draft_kwarg", "expected_state"),
    [
        ({"draft": True}, MergeRequestState.DRAFT),
        ({"work_in_progress": True}, MergeRequestState.DRAFT),
        ({"title": "Draft: my feature"}, MergeRequestState.DRAFT),
        ({"title": "[Draft] my feature"}, MergeRequestState.DRAFT),
        ({"title": "WIP: my feature"}, MergeRequestState.DRAFT),
        ({}, MergeRequestState.OPEN),
    ],
)
def test_fetch_mergerequests_draft_detection(
    monkeypatch: pytest.MonkeyPatch,
    draft_kwarg: dict[str, object],
    expected_state: MergeRequestState,
) -> None:
    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if _is_mr_detail_path(request.url.path):
                return httpx.Response(200, json=_mr_detail_response())
            if request.url.path.endswith("/approvals"):
                return httpx.Response(200, json=_approvals_response([]))
            return httpx.Response(
                200,
                headers={"X-Next-Page": ""},
                json=[_mr_payload(**draft_kwarg)],
            )

        connector = _make_connector(monkeypatch, handler)
        mrs = await _collect(
            connector.fetch_mergerequests(
                MergeRequestScope(repository_external_ids=["101"]),
                _date_window(),
            )
        )
        await connector.close()

        assert len(mrs) == 1
        assert mrs[0].state is expected_state
        assert mrs[0].is_draft is (expected_state is MergeRequestState.DRAFT)

    asyncio.run(run())


def test_fetch_mergerequests_wip_prefix_not_applied_to_merged_mr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 'WIP:' title prefix on a merged MR keeps MERGED state; heuristic is gated on gl_state."""

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if _is_mr_detail_path(request.url.path):
                return httpx.Response(200, json=_mr_detail_response())
            if request.url.path.endswith("/approvals"):
                return httpx.Response(200, json=_approvals_response([]))
            return httpx.Response(
                200,
                headers={"X-Next-Page": ""},
                json=[
                    _mr_payload(
                        title="WIP: hotfix",
                        state="merged",
                        merged_at="2026-05-15T16:30:00Z",
                    )
                ],
            )

        connector = _make_connector(monkeypatch, handler)
        mrs = await _collect(
            connector.fetch_mergerequests(
                MergeRequestScope(repository_external_ids=["101"]),
                _date_window(),
            )
        )
        await connector.close()

        assert len(mrs) == 1
        mr = mrs[0]
        assert mr.state is MergeRequestState.MERGED
        assert mr.is_draft is False
        assert mr.merged_at == datetime(2026, 5, 15, 16, 30, 0, tzinfo=timezone.utc)

    asyncio.run(run())


def test_fetch_mergerequests_normalizes_merged_mr(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if _is_mr_detail_path(request.url.path):
                return httpx.Response(200, json=_mr_detail_response())
            if request.url.path.endswith("/approvals"):
                return httpx.Response(200, json=_approvals_response([10]))
            return httpx.Response(
                200,
                headers={"X-Next-Page": ""},
                json=[
                    _mr_payload(
                        state="merged",
                        merged_at="2026-05-15T16:30:00Z",
                    )
                ],
            )

        connector = _make_connector(monkeypatch, handler)
        mrs = await _collect(
            connector.fetch_mergerequests(
                MergeRequestScope(repository_external_ids=["101"]),
                _date_window(),
            )
        )
        await connector.close()

        assert len(mrs) == 1
        mr = mrs[0]
        assert mr.state is MergeRequestState.MERGED
        assert mr.merged_at == datetime(2026, 5, 15, 16, 30, 0, tzinfo=timezone.utc)
        assert mr.closed_at is None

    asyncio.run(run())


def test_fetch_mergerequests_closed_draft_mr_state_is_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A GitLab MR that is both closed and draft normalizes to CLOSED, not DRAFT.

    Terminal states win over the draft flag so that closed_at is populated and closed-state
    signals can see the MR.  The is_draft flag itself is preserved on the model.
    """

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if _is_mr_detail_path(request.url.path):
                return httpx.Response(200, json=_mr_detail_response())
            if request.url.path.endswith("/approvals"):
                return httpx.Response(200, json=_approvals_response([]))
            return httpx.Response(
                200,
                headers={"X-Next-Page": ""},
                json=[
                    _mr_payload(
                        state="closed",
                        draft=True,
                        closed_at="2026-05-20T14:00:00Z",
                    )
                ],
            )

        connector = _make_connector(monkeypatch, handler)
        mrs = await _collect(
            connector.fetch_mergerequests(
                MergeRequestScope(
                    repository_external_ids=["101"],
                    include_drafts=True,
                    include_closed_unmerged=True,
                ),
                _date_window(),
            )
        )
        await connector.close()

        assert len(mrs) == 1
        mr = mrs[0]
        assert mr.state is MergeRequestState.CLOSED
        assert mr.closed_at == datetime(2026, 5, 20, 14, 0, 0, tzinfo=timezone.utc)
        assert mr.is_draft is True

    asyncio.run(run())


def test_fetch_mergerequests_merged_draft_mr_state_is_merged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A GitLab MR that is both merged and draft normalizes to MERGED, not DRAFT.

    Terminal states win over the draft flag; merged_at must be populated and is_draft preserved.
    """

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if _is_mr_detail_path(request.url.path):
                return httpx.Response(200, json=_mr_detail_response())
            if request.url.path.endswith("/approvals"):
                return httpx.Response(200, json=_approvals_response([]))
            return httpx.Response(
                200,
                headers={"X-Next-Page": ""},
                json=[
                    _mr_payload(
                        state="merged",
                        draft=True,
                        merged_at="2026-05-18T10:00:00Z",
                    )
                ],
            )

        connector = _make_connector(monkeypatch, handler)
        mrs = await _collect(
            connector.fetch_mergerequests(
                MergeRequestScope(
                    repository_external_ids=["101"],
                    include_drafts=True,
                ),
                _date_window(),
            )
        )
        await connector.close()

        assert len(mrs) == 1
        mr = mrs[0]
        assert mr.state is MergeRequestState.MERGED
        assert mr.merged_at == datetime(2026, 5, 18, 10, 0, 0, tzinfo=timezone.utc)
        assert mr.is_draft is True

    asyncio.run(run())


def test_fetch_mergerequests_locked_mr_maps_to_open_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """'locked' GitLab MRs cannot receive new commits but are still open, not closed."""

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if _is_mr_detail_path(request.url.path):
                return httpx.Response(200, json=_mr_detail_response())
            if request.url.path.endswith("/approvals"):
                return httpx.Response(200, json=_approvals_response([]))
            return httpx.Response(
                200,
                headers={"X-Next-Page": ""},
                json=[_mr_payload(state="locked")],
            )

        connector = _make_connector(monkeypatch, handler)
        mrs = await _collect(
            connector.fetch_mergerequests(
                MergeRequestScope(repository_external_ids=["101"]),
                _date_window(),
            )
        )
        await connector.close()

        assert len(mrs) == 1
        mr = mrs[0]
        assert mr.state is MergeRequestState.OPEN
        assert mr.closed_at is None
        assert mr.merged_at is None

    asyncio.run(run())


def test_fetch_mergerequests_normalizes_closed_mr_with_include_closed_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if _is_mr_detail_path(request.url.path):
                return httpx.Response(200, json=_mr_detail_response())
            if request.url.path.endswith("/approvals"):
                return httpx.Response(200, json=_approvals_response([]))
            return httpx.Response(
                200,
                headers={"X-Next-Page": ""},
                json=[
                    _mr_payload(
                        state="closed",
                        closed_at="2026-05-12T10:00:00Z",
                    )
                ],
            )

        connector = _make_connector(monkeypatch, handler)
        mrs = await _collect(
            connector.fetch_mergerequests(
                MergeRequestScope(
                    repository_external_ids=["101"],
                    include_closed_unmerged=True,
                ),
                _date_window(),
            )
        )
        await connector.close()

        assert len(mrs) == 1
        mr = mrs[0]
        assert mr.state is MergeRequestState.CLOSED
        assert mr.closed_at == datetime(2026, 5, 12, 10, 0, 0, tzinfo=timezone.utc)
        assert mr.merged_at is None

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Scope filters
# ---------------------------------------------------------------------------


def test_fetch_mergerequests_excludes_drafts_when_include_drafts_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if _is_mr_detail_path(request.url.path):
                return httpx.Response(200, json=_mr_detail_response())
            if request.url.path.endswith("/approvals"):
                return httpx.Response(200, json=_approvals_response([]))
            return httpx.Response(
                200,
                headers={"X-Next-Page": ""},
                json=[
                    _mr_payload(iid=1, title="Draft: wip feature", draft=True),
                    _mr_payload(iid=2, mr_id=1002, title="Ready feature"),
                ],
            )

        connector = _make_connector(monkeypatch, handler)
        mrs = await _collect(
            connector.fetch_mergerequests(
                MergeRequestScope(
                    repository_external_ids=["101"],
                    include_drafts=False,
                ),
                _date_window(),
            )
        )
        await connector.close()

        assert len(mrs) == 1
        assert mrs[0].iid == 2
        assert mrs[0].state is MergeRequestState.OPEN

    asyncio.run(run())


def test_fetch_mergerequests_excludes_closed_when_include_closed_unmerged_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if _is_mr_detail_path(request.url.path):
                return httpx.Response(200, json=_mr_detail_response())
            if request.url.path.endswith("/approvals"):
                return httpx.Response(200, json=_approvals_response([]))
            return httpx.Response(
                200,
                headers={"X-Next-Page": ""},
                json=[
                    _mr_payload(iid=1, state="closed", closed_at="2026-05-12T10:00:00Z"),
                    _mr_payload(
                        iid=2, mr_id=1002, state="merged", merged_at="2026-05-13T10:00:00Z"
                    ),
                    _mr_payload(iid=3, mr_id=1003, state="opened"),
                ],
            )

        connector = _make_connector(monkeypatch, handler)
        # include_closed_unmerged defaults to False
        mrs = await _collect(
            connector.fetch_mergerequests(
                MergeRequestScope(repository_external_ids=["101"]),
                _date_window(),
            )
        )
        await connector.close()

        assert len(mrs) == 2
        assert {mr.iid for mr in mrs} == {2, 3}

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Pipeline status
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("gl_status", "expected"),
    [
        ("success", PipelineStatus.SUCCESS),
        ("passed", PipelineStatus.SUCCESS),
        ("failed", PipelineStatus.FAILED),
        ("running", PipelineStatus.RUNNING),
        ("canceled", PipelineStatus.CANCELED),
        ("skipped", PipelineStatus.SKIPPED),
        ("pending", PipelineStatus.RUNNING),
        ("preparing", PipelineStatus.RUNNING),
        ("manual", PipelineStatus.RUNNING),
        ("unknown_future_status", PipelineStatus.NONE),
    ],
)
def test_fetch_mergerequests_maps_pipeline_status(
    monkeypatch: pytest.MonkeyPatch,
    gl_status: str,
    expected: PipelineStatus,
) -> None:
    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if _is_mr_detail_path(request.url.path):
                return httpx.Response(200, json=_mr_detail_response())
            if request.url.path.endswith("/approvals"):
                return httpx.Response(200, json=_approvals_response([]))
            return httpx.Response(
                200,
                headers={"X-Next-Page": ""},
                json=[
                    _mr_payload(
                        head_pipeline={
                            "id": 1,
                            "status": gl_status,
                            "updated_at": "2026-05-10T11:00:00Z",
                        }
                    )
                ],
            )

        connector = _make_connector(monkeypatch, handler)
        mrs = await _collect(
            connector.fetch_mergerequests(
                MergeRequestScope(repository_external_ids=["101"]),
                _date_window(),
            )
        )
        await connector.close()

        assert len(mrs) == 1
        assert mrs[0].pipeline_status is expected

    asyncio.run(run())


def test_fetch_mergerequests_no_pipeline_yields_none_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if _is_mr_detail_path(request.url.path):
                return httpx.Response(200, json=_mr_detail_response())
            if request.url.path.endswith("/approvals"):
                return httpx.Response(200, json=_approvals_response([]))
            return httpx.Response(
                200,
                headers={"X-Next-Page": ""},
                json=[_mr_payload(head_pipeline=None)],
            )

        connector = _make_connector(monkeypatch, handler)
        mrs = await _collect(
            connector.fetch_mergerequests(
                MergeRequestScope(repository_external_ids=["101"]),
                _date_window(),
            )
        )
        await connector.close()

        assert mrs[0].pipeline_status is PipelineStatus.NONE
        assert mrs[0].pipeline_updated_at is None

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Diff stats — sourced from the single-MR detail endpoint
# ---------------------------------------------------------------------------


def test_fetch_mergerequests_diff_stats_from_detail_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """changed_files_count, additions, deletions come from the detail endpoint, not the list."""

    async def run() -> None:
        detail_paths: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if _is_mr_detail_path(request.url.path):
                detail_paths.append(request.url.path)
                return httpx.Response(
                    200,
                    json=_mr_detail_response(changes_count="7", additions=30, deletions=12),
                )
            if request.url.path.endswith("/approvals"):
                return httpx.Response(200, json=_approvals_response([]))
            return httpx.Response(
                200,
                headers={"X-Next-Page": ""},
                # List payload intentionally has no changes_count / diff_stats_summary.
                json=[_mr_payload(iid=7)],
            )

        connector = _make_connector(monkeypatch, handler)
        mrs = await _collect(
            connector.fetch_mergerequests(
                MergeRequestScope(repository_external_ids=["101"]),
                _date_window(),
            )
        )
        await connector.close()

        assert len(mrs) == 1
        assert mrs[0].changed_files_count == 7
        assert mrs[0].additions == 30
        assert mrs[0].deletions == 12
        # Verify the detail endpoint was actually called.
        assert len(detail_paths) == 1
        assert detail_paths[0].endswith("/7")

    asyncio.run(run())


def test_fetch_mergerequests_parses_changes_count_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """String changes_count like '1000+' from the detail endpoint is parsed as 1000."""

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if _is_mr_detail_path(request.url.path):
                # No additions/deletions — verify they stay None.
                return httpx.Response(
                    200,
                    json=_mr_detail_response(changes_count="1000+", additions=None, deletions=None),
                )
            if request.url.path.endswith("/approvals"):
                return httpx.Response(200, json=_approvals_response([]))
            return httpx.Response(
                200,
                headers={"X-Next-Page": ""},
                json=[_mr_payload()],
            )

        connector = _make_connector(monkeypatch, handler)
        mrs = await _collect(
            connector.fetch_mergerequests(
                MergeRequestScope(repository_external_ids=["101"]),
                _date_window(),
            )
        )
        await connector.close()

        assert mrs[0].changed_files_count == 1000
        assert mrs[0].additions is None
        assert mrs[0].deletions is None

    asyncio.run(run())


def test_fetch_mergerequests_diff_stats_from_detail_diff_stats_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """additions/deletions fall back to detail diff_stats_summary when top-level fields are absent."""

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if _is_mr_detail_path(request.url.path):
                return httpx.Response(
                    200,
                    json={
                        "changes_count": "5",
                        "diff_stats_summary": {"additions": 15, "deletions": 7, "file_count": 5},
                        # No top-level "additions" or "deletions"
                    },
                )
            if request.url.path.endswith("/approvals"):
                return httpx.Response(200, json=_approvals_response([]))
            return httpx.Response(
                200,
                headers={"X-Next-Page": ""},
                json=[_mr_payload()],
            )

        connector = _make_connector(monkeypatch, handler)
        mrs = await _collect(
            connector.fetch_mergerequests(
                MergeRequestScope(repository_external_ids=["101"]),
                _date_window(),
            )
        )
        await connector.close()

        assert len(mrs) == 1
        assert mrs[0].changed_files_count == 5
        assert mrs[0].additions == 15
        assert mrs[0].deletions == 7

    asyncio.run(run())


def test_fetch_mergerequests_mr_detail_404_degrades_gracefully(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Detail endpoint 404 does not drop the MR; diff stats degrade to None."""

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if _is_mr_detail_path(request.url.path):
                return httpx.Response(404)
            if request.url.path.endswith("/approvals"):
                return httpx.Response(200, json=_approvals_response([]))
            return httpx.Response(
                200,
                headers={"X-Next-Page": ""},
                json=[_mr_payload()],
            )

        connector = _make_connector(monkeypatch, handler)
        mrs = await _collect(
            connector.fetch_mergerequests(
                MergeRequestScope(repository_external_ids=["101"]),
                _date_window(),
            )
        )
        await connector.close()

        assert len(mrs) == 1
        mr = mrs[0]
        assert mr.changed_files_count is None
        assert mr.additions is None
        assert mr.deletions is None

    asyncio.run(run())


def test_fetch_mergerequests_mr_detail_403_degrades_gracefully(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Detail endpoint 403 does not drop the MR; diff stats degrade to None."""

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if _is_mr_detail_path(request.url.path):
                return httpx.Response(403)
            if request.url.path.endswith("/approvals"):
                return httpx.Response(200, json=_approvals_response([]))
            return httpx.Response(
                200,
                headers={"X-Next-Page": ""},
                json=[_mr_payload()],
            )

        connector = _make_connector(monkeypatch, handler)
        mrs = await _collect(
            connector.fetch_mergerequests(
                MergeRequestScope(repository_external_ids=["101"]),
                _date_window(),
            )
        )
        await connector.close()

        assert len(mrs) == 1
        mr = mrs[0]
        assert mr.changed_files_count is None
        assert mr.additions is None
        assert mr.deletions is None

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Approvals
# ---------------------------------------------------------------------------


def test_fetch_mergerequests_counts_distinct_approvers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        approval_requests: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if _is_mr_detail_path(request.url.path):
                return httpx.Response(200, json=_mr_detail_response())
            if request.url.path.endswith("/approvals"):
                approval_requests.append(request.url.path)
                return httpx.Response(200, json=_approvals_response([10, 11, 12]))
            return httpx.Response(
                200,
                headers={"X-Next-Page": ""},
                json=[_mr_payload()],
            )

        connector = _make_connector(monkeypatch, handler)
        mrs = await _collect(
            connector.fetch_mergerequests(
                MergeRequestScope(repository_external_ids=["101"]),
                _date_window(),
            )
        )
        await connector.close()

        assert mrs[0].approval_count == 3
        assert len(approval_requests) == 1
        assert approval_requests[0].endswith("/1/approvals")

    asyncio.run(run())


def test_fetch_mergerequests_deduplicates_approvers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Duplicate user entries in approved_by are counted once per distinct user ID."""

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if _is_mr_detail_path(request.url.path):
                return httpx.Response(200, json=_mr_detail_response())
            if request.url.path.endswith("/approvals"):
                return httpx.Response(
                    200,
                    json={
                        "approved_by": [
                            {"user": {"id": 10, "name": "User 10"}},
                            {"user": {"id": 10, "name": "User 10"}},  # duplicate
                            {"user": {"id": 11, "name": "User 11"}},
                        ]
                    },
                )
            return httpx.Response(200, headers={"X-Next-Page": ""}, json=[_mr_payload()])

        connector = _make_connector(monkeypatch, handler)
        mrs = await _collect(
            connector.fetch_mergerequests(
                MergeRequestScope(repository_external_ids=["101"]),
                _date_window(),
            )
        )
        await connector.close()

        assert mrs[0].approval_count == 2  # user 10 and 11, not 3

    asyncio.run(run())


def test_fetch_mergerequests_approval_404_yields_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Approvals endpoint 404 (MR not EE or token has no access) defaults to 0."""

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if _is_mr_detail_path(request.url.path):
                return httpx.Response(200, json=_mr_detail_response())
            if request.url.path.endswith("/approvals"):
                return httpx.Response(404)
            return httpx.Response(
                200,
                headers={"X-Next-Page": ""},
                json=[_mr_payload()],
            )

        connector = _make_connector(monkeypatch, handler)
        mrs = await _collect(
            connector.fetch_mergerequests(
                MergeRequestScope(repository_external_ids=["101"]),
                _date_window(),
            )
        )
        await connector.close()

        assert mrs[0].approval_count == 0

    asyncio.run(run())


def test_fetch_mergerequests_approval_403_yields_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if _is_mr_detail_path(request.url.path):
                return httpx.Response(200, json=_mr_detail_response())
            if request.url.path.endswith("/approvals"):
                return httpx.Response(403)
            return httpx.Response(
                200,
                headers={"X-Next-Page": ""},
                json=[_mr_payload()],
            )

        connector = _make_connector(monkeypatch, handler)
        mrs = await _collect(
            connector.fetch_mergerequests(
                MergeRequestScope(repository_external_ids=["101"]),
                _date_window(),
            )
        )
        await connector.close()

        assert mrs[0].approval_count == 0

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Enrichment pairing
# ---------------------------------------------------------------------------


def test_fetch_mergerequests_enrichment_paired_per_mr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each MR on a page receives its own distinct enrichment (diff stats + approvals).

    Both handlers route by iid so a cross-wiring bug — MR A getting MR B's enrichment —
    produces wrong values and fails the per-iid assertions.
    """

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            segments = path.rstrip("/").split("/")
            if path.endswith("/approvals"):
                iid = int(segments[-2])
                if iid == 1:
                    return httpx.Response(200, json=_approvals_response([10]))
                if iid == 2:
                    return httpx.Response(200, json=_approvals_response([10, 11]))
                raise AssertionError(f"Unexpected approvals iid: {iid}")
            if _is_mr_detail_path(path):
                iid = int(segments[-1])
                if iid == 1:
                    return httpx.Response(
                        200,
                        json=_mr_detail_response(changes_count=3, additions=10, deletions=2),
                    )
                if iid == 2:
                    return httpx.Response(
                        200,
                        json=_mr_detail_response(changes_count=7, additions=30, deletions=5),
                    )
                raise AssertionError(f"Unexpected detail iid: {iid}")
            return httpx.Response(
                200,
                headers={"X-Next-Page": ""},
                json=[
                    _mr_payload(mr_id=1001, iid=1),
                    _mr_payload(mr_id=1002, iid=2),
                ],
            )

        connector = _make_connector(monkeypatch, handler)
        mrs = await _collect(
            connector.fetch_mergerequests(
                MergeRequestScope(repository_external_ids=["101"]),
                _date_window(),
            )
        )
        await connector.close()

        assert len(mrs) == 2
        by_iid = {mr.iid: mr for mr in mrs}

        mr1 = by_iid[1]
        assert mr1.changed_files_count == 3
        assert mr1.additions == 10
        assert mr1.deletions == 2
        assert mr1.approval_count == 1

        mr2 = by_iid[2]
        assert mr2.changed_files_count == 7
        assert mr2.additions == 30
        assert mr2.deletions == 5
        assert mr2.approval_count == 2

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("case", "expected_count"),
    [
        ("empty", 0),
        ("partial", 1),
        ("full", 102),
    ],
)
def test_fetch_mergerequests_handles_empty_partial_and_full_pages(
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    expected_count: int,
) -> None:
    seen_pages: list[str] = []

    async def run() -> None:
        pages = _pages_for_case(case)

        def handler(request: httpx.Request) -> httpx.Response:
            if _is_mr_detail_path(request.url.path):
                return httpx.Response(200, json=_mr_detail_response())
            if request.url.path.endswith("/approvals"):
                return httpx.Response(200, json=_approvals_response([]))
            seen_pages.append(request.url.params["page"])
            page_index = len(seen_pages) - 1
            if page_index >= len(pages):
                raise AssertionError(f"Unexpected page {page_index}")
            is_last = page_index == len(pages) - 1
            return httpx.Response(
                200,
                headers={"X-Next-Page": "" if is_last else str(page_index + 2)},
                json=pages[page_index],
            )

        connector = _make_connector(monkeypatch, handler)
        mrs = await _collect(
            connector.fetch_mergerequests(
                MergeRequestScope(repository_external_ids=["101"]),
                _date_window(),
            )
        )
        await connector.close()

        assert len(mrs) == expected_count

    asyncio.run(run())

    if case == "empty":
        assert seen_pages == ["1"]
    elif case == "partial":
        assert seen_pages == ["1"]
    else:
        assert seen_pages == ["1", "2"]


def _pages_for_case(case: str) -> list[list[dict[str, object]]]:
    if case == "empty":
        return [[]]
    if case == "partial":
        return [[_mr_payload(mr_id=1001, iid=1)]]
    if case == "full":
        # Page 1 is full (100 items), page 2 has 2 items
        page1 = [_mr_payload(mr_id=1000 + i, iid=i) for i in range(1, 101)]
        page2 = [
            _mr_payload(mr_id=1101, iid=101),
            _mr_payload(mr_id=1102, iid=102),
        ]
        return [page1, page2]
    raise AssertionError(f"unknown case: {case}")


# ---------------------------------------------------------------------------
# Multiple repositories
# ---------------------------------------------------------------------------


def test_fetch_mergerequests_iterates_multiple_repositories(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if _is_mr_detail_path(request.url.path):
                return httpx.Response(200, json=_mr_detail_response())
            if request.url.path.endswith("/approvals"):
                return httpx.Response(200, json=_approvals_response([]))
            # Route by project ID in path
            if "/projects/101/" in request.url.path:
                return httpx.Response(
                    200,
                    headers={"X-Next-Page": ""},
                    json=[_mr_payload(mr_id=2001, iid=1)],
                )
            if "/projects/202/" in request.url.path:
                return httpx.Response(
                    200,
                    headers={"X-Next-Page": ""},
                    json=[
                        _mr_payload(mr_id=3001, iid=1),
                        _mr_payload(mr_id=3002, iid=2),
                    ],
                )
            raise AssertionError(f"unexpected path: {request.url.path}")

        connector = _make_connector(monkeypatch, handler)
        mrs = await _collect(
            connector.fetch_mergerequests(
                MergeRequestScope(repository_external_ids=["101", "202"]),
                _date_window(),
            )
        )
        await connector.close()

        assert len(mrs) == 3
        repo_101_ids = [
            mr.external_id for mr in mrs if mr.repository_id == _stable_id("repository", "101")
        ]
        repo_202_ids = [
            mr.external_id for mr in mrs if mr.repository_id == _stable_id("repository", "202")
        ]
        assert repo_101_ids == ["2001"]
        assert sorted(repo_202_ids) == ["3001", "3002"]

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Window: date_range sends updated_before and updated_after params
# ---------------------------------------------------------------------------


def test_fetch_mergerequests_sends_updated_before_for_date_range_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_params: list[str | None] = []

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/approvals"):
                return httpx.Response(200, json=_approvals_response([]))
            seen_params.append(request.url.params.get("updated_before"))
            return httpx.Response(200, headers={"X-Next-Page": ""}, json=[])

        connector = _make_connector(monkeypatch, handler)
        await _collect(
            connector.fetch_mergerequests(
                MergeRequestScope(repository_external_ids=["101"]),
                _date_window(),
            )
        )
        await connector.close()

    asyncio.run(run())

    assert len(seen_params) == 1
    assert seen_params[0] == "2026-05-31T00:00:00Z"


def test_fetch_mergerequests_sends_updated_after_for_date_range_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DATE_RANGE window passes updated_after=window.start to bound the fetch from below."""
    seen_params: list[str | None] = []

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/approvals"):
                return httpx.Response(200, json=_approvals_response([]))
            seen_params.append(request.url.params.get("updated_after"))
            return httpx.Response(200, headers={"X-Next-Page": ""}, json=[])

        connector = _make_connector(monkeypatch, handler)
        await _collect(
            connector.fetch_mergerequests(
                MergeRequestScope(repository_external_ids=["101"]),
                _date_window(),
            )
        )
        await connector.close()

    asyncio.run(run())

    assert len(seen_params) == 1
    assert seen_params[0] == "2026-05-01T00:00:00Z"


def test_fetch_mergerequests_no_updated_before_for_sprint_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_params: list[str | None] = []

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/approvals"):
                return httpx.Response(200, json=_approvals_response([]))
            seen_params.append(request.url.params.get("updated_before"))
            return httpx.Response(200, headers={"X-Next-Page": ""}, json=[])

        connector = _make_connector(monkeypatch, handler)
        await _collect(
            connector.fetch_mergerequests(
                MergeRequestScope(repository_external_ids=["101"]),
                _sprint_window(),
            )
        )
        await connector.close()

    asyncio.run(run())

    assert seen_params == [None]


def test_fetch_mergerequests_no_updated_after_for_sprint_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SPRINT window sends neither updated_before nor updated_after."""
    seen_params: list[str | None] = []

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/approvals"):
                return httpx.Response(200, json=_approvals_response([]))
            seen_params.append(request.url.params.get("updated_after"))
            return httpx.Response(200, headers={"X-Next-Page": ""}, json=[])

        connector = _make_connector(monkeypatch, handler)
        await _collect(
            connector.fetch_mergerequests(
                MergeRequestScope(repository_external_ids=["101"]),
                _sprint_window(),
            )
        )
        await connector.close()

    asyncio.run(run())

    assert seen_params == [None]


# ---------------------------------------------------------------------------
# Invariants
# ---------------------------------------------------------------------------


def test_fetch_mergerequests_merged_mr_satisfies_invariant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Merged state sets merged_at; closed_at is None (invariant: mutually exclusive)."""

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if _is_mr_detail_path(request.url.path):
                return httpx.Response(200, json=_mr_detail_response())
            if request.url.path.endswith("/approvals"):
                return httpx.Response(200, json=_approvals_response([]))
            return httpx.Response(
                200,
                headers={"X-Next-Page": ""},
                json=[_mr_payload(state="merged", merged_at="2026-05-15T10:00:00Z")],
            )

        connector = _make_connector(monkeypatch, handler)
        mrs = await _collect(
            connector.fetch_mergerequests(
                MergeRequestScope(repository_external_ids=["101"]),
                _date_window(),
            )
        )
        await connector.close()

        mr = mrs[0]
        assert mr.state is MergeRequestState.MERGED
        assert mr.merged_at is not None
        assert mr.closed_at is None
        # If we got here the model validator accepted the object — invariant holds.

    asyncio.run(run())


def test_fetch_mergerequests_closed_mr_satisfies_invariant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Closed state sets closed_at; merged_at is None (invariant: mutually exclusive)."""

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if _is_mr_detail_path(request.url.path):
                return httpx.Response(200, json=_mr_detail_response())
            if request.url.path.endswith("/approvals"):
                return httpx.Response(200, json=_approvals_response([]))
            return httpx.Response(
                200,
                headers={"X-Next-Page": ""},
                json=[_mr_payload(state="closed", closed_at="2026-05-20T14:00:00Z")],
            )

        connector = _make_connector(monkeypatch, handler)
        mrs = await _collect(
            connector.fetch_mergerequests(
                MergeRequestScope(
                    repository_external_ids=["101"],
                    include_closed_unmerged=True,
                ),
                _date_window(),
            )
        )
        await connector.close()

        mr = mrs[0]
        assert mr.state is MergeRequestState.CLOSED
        assert mr.closed_at is not None
        assert mr.merged_at is None

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Draft filter — terminal-state precedence
# ---------------------------------------------------------------------------


def test_fetch_mergerequests_closed_draft_mr_included_when_closed_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A closed MR carrying draft=True is included when include_closed_unmerged=True.

    The draft filter must not drop MRs whose GitLab state is already terminal; only the
    include_closed_unmerged flag governs whether terminal MRs pass through.
    """

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if _is_mr_detail_path(request.url.path):
                return httpx.Response(200, json=_mr_detail_response())
            if request.url.path.endswith("/approvals"):
                return httpx.Response(200, json=_approvals_response([]))
            return httpx.Response(
                200,
                headers={"X-Next-Page": ""},
                json=[
                    _mr_payload(
                        state="closed",
                        draft=True,
                        closed_at="2026-05-20T14:00:00Z",
                        merged_at=None,
                    )
                ],
            )

        scope_include = MergeRequestScope(
            repository_external_ids=["101"],
            include_drafts=False,
            include_closed_unmerged=True,
        )

        connector = _make_connector(monkeypatch, handler)
        mrs = await _collect(connector.fetch_mergerequests(scope_include, _date_window()))
        await connector.close()

        assert len(mrs) == 1
        mr = mrs[0]
        assert mr.state is MergeRequestState.CLOSED
        assert mr.is_draft is True
        assert mr.closed_at is not None
        assert mr.merged_at is None

    asyncio.run(run())


def test_fetch_mergerequests_closed_draft_mr_excluded_when_closed_not_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A closed MR carrying draft=True is excluded when include_closed_unmerged=False.

    The include_closed_unmerged filter applies to all terminal MRs regardless of the draft flag.
    """

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if _is_mr_detail_path(request.url.path):
                return httpx.Response(200, json=_mr_detail_response())
            if request.url.path.endswith("/approvals"):
                return httpx.Response(200, json=_approvals_response([]))
            return httpx.Response(
                200,
                headers={"X-Next-Page": ""},
                json=[
                    _mr_payload(
                        state="closed",
                        draft=True,
                        closed_at="2026-05-20T14:00:00Z",
                        merged_at=None,
                    )
                ],
            )

        scope_exclude = MergeRequestScope(
            repository_external_ids=["101"],
            include_drafts=False,
            include_closed_unmerged=False,
        )

        connector = _make_connector(monkeypatch, handler)
        mrs = await _collect(connector.fetch_mergerequests(scope_exclude, _date_window()))
        await connector.close()

        assert len(mrs) == 0

    asyncio.run(run())


def test_fetch_mergerequests_merged_draft_mr_included_when_drafts_excluded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A merged MR carrying draft=True is included even when include_drafts=False.

    The draft filter must not drop MRs whose GitLab state is already terminal (merged);
    only the include_drafts flag governs open draft MRs.  This guards against a future
    regression where is_terminal is narrowed to only ("closed",), which would wrongly
    drop merged+draft MRs when include_drafts=False.
    """

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if _is_mr_detail_path(request.url.path):
                return httpx.Response(200, json=_mr_detail_response())
            if request.url.path.endswith("/approvals"):
                return httpx.Response(200, json=_approvals_response([]))
            return httpx.Response(
                200,
                headers={"X-Next-Page": ""},
                json=[
                    _mr_payload(
                        state="merged",
                        draft=True,
                        merged_at="2026-05-18T10:00:00Z",
                    )
                ],
            )

        connector = _make_connector(monkeypatch, handler)
        mrs = await _collect(
            connector.fetch_mergerequests(
                MergeRequestScope(
                    repository_external_ids=["101"],
                    include_drafts=False,
                ),
                _date_window(),
            )
        )
        await connector.close()

        assert len(mrs) == 1
        mr = mrs[0]
        assert mr.state is MergeRequestState.MERGED
        assert mr.is_draft is True

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Error handling — typed errors and invariant violations
# ---------------------------------------------------------------------------


def test_fetch_mergerequests_missing_merged_at_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A merged MR payload with no merged_at raises ConnectorDataError."""

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if _is_mr_detail_path(request.url.path):
                return httpx.Response(200, json=_mr_detail_response())
            if request.url.path.endswith("/approvals"):
                return httpx.Response(200, json=_approvals_response([]))
            return httpx.Response(
                200,
                headers={"X-Next-Page": ""},
                json=[_mr_payload(state="merged", merged_at=None)],
            )

        connector = _make_connector(monkeypatch, handler)
        with pytest.raises(ConnectorDataError, match="merged_at"):
            await _collect(
                connector.fetch_mergerequests(
                    MergeRequestScope(repository_external_ids=["101"]),
                    _date_window(),
                )
            )
        await connector.close()

    asyncio.run(run())


def test_fetch_mergerequests_missing_closed_at_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A closed MR payload with no closed_at raises ConnectorDataError."""

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if _is_mr_detail_path(request.url.path):
                return httpx.Response(200, json=_mr_detail_response())
            if request.url.path.endswith("/approvals"):
                return httpx.Response(200, json=_approvals_response([]))
            return httpx.Response(
                200,
                headers={"X-Next-Page": ""},
                json=[_mr_payload(state="closed", closed_at=None)],
            )

        connector = _make_connector(monkeypatch, handler)
        with pytest.raises(ConnectorDataError, match="closed_at"):
            await _collect(
                connector.fetch_mergerequests(
                    MergeRequestScope(
                        repository_external_ids=["101"],
                        include_closed_unmerged=True,
                    ),
                    _date_window(),
                )
            )
        await connector.close()

    asyncio.run(run())


def test_fetch_mergerequests_invalid_datetime_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unparseable datetime string in the payload raises ConnectorDataError."""

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if _is_mr_detail_path(request.url.path):
                return httpx.Response(200, json=_mr_detail_response())
            if request.url.path.endswith("/approvals"):
                return httpx.Response(200, json=_approvals_response([]))
            return httpx.Response(
                200,
                headers={"X-Next-Page": ""},
                json=[_mr_payload(created_at="not-a-datetime")],
            )

        connector = _make_connector(monkeypatch, handler)
        with pytest.raises(ConnectorDataError, match="not-a-datetime"):
            await _collect(
                connector.fetch_mergerequests(
                    MergeRequestScope(repository_external_ids=["101"]),
                    _date_window(),
                )
            )
        await connector.close()

    asyncio.run(run())


def test_fetch_mergerequests_non_list_response_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-list JSON body from the list endpoint raises ConnectorDataError."""

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"error": "unexpected"})

        connector = _make_connector(monkeypatch, handler)
        with pytest.raises(ConnectorDataError):
            await _collect(
                connector.fetch_mergerequests(
                    MergeRequestScope(repository_external_ids=["101"]),
                    _date_window(),
                )
            )
        await connector.close()

    asyncio.run(run())


def test_fetch_mergerequests_wraps_network_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("network down", request=request)

        connector = _make_connector(monkeypatch, handler)
        with pytest.raises(ConnectorTransientError):
            await _collect(
                connector.fetch_mergerequests(
                    MergeRequestScope(repository_external_ids=["101"]),
                    _date_window(),
                )
            )
        await connector.close()

    asyncio.run(run())
