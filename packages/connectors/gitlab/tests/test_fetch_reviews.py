import asyncio
from collections.abc import Callable
from datetime import datetime, timezone

import httpx
import pytest

import em_radar_connector_gitlab.connector as gitlab_connector_module
from em_radar_connector_gitlab.connector import GitLabConnector, _stable_id
from em_radar_core.connectors import ConnectorDataError, ConnectorTransientError
from em_radar_core.models import Review, ReviewDecision


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


async def _collect(iterator: object) -> list[Review]:
    items: list[Review] = []
    async for item in iterator:
        items.append(item)
    return items


def _mr_global_payload(
    *,
    mr_id: int = 2001,
    project_id: int = 101,
    iid: int = 7,
) -> dict[str, object]:
    """Minimal payload returned by GET /api/v4/merge_requests/:id."""
    return {"id": mr_id, "project_id": project_id, "iid": iid}


def _note_payload(
    *,
    note_id: int = 1,
    body: str = "approved this merge request",
    author_id: int = 42,
    author_name: str = "Alice",
    created_at: str = "2026-05-10T10:00:00Z",
    system: bool = True,
) -> dict[str, object]:
    return {
        "id": note_id,
        "body": body,
        "author": {"id": author_id, "name": author_name, "username": "alice"},
        "created_at": created_at,
        "updated_at": created_at,
        "system": system,
    }


def _reviewer_payload(
    *,
    reviewer_id: int = 99,
    name: str = "Bob",
    state: str = "unreviewed",
    created_at: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "user": {"id": reviewer_id, "name": name, "username": "bob"},
        "state": state,
    }
    if created_at is not None:
        payload["created_at"] = created_at
    return payload


def _notes_response(
    notes: list[dict[str, object]],
    *,
    next_page: str = "",
) -> httpx.Response:
    return httpx.Response(200, headers={"X-Next-Page": next_page}, json=notes)


def _reviewers_response(reviewers: list[dict[str, object]]) -> httpx.Response:
    return httpx.Response(200, headers={"X-Next-Page": ""}, json=reviewers)


# ---------------------------------------------------------------------------
# Full normalization
# ---------------------------------------------------------------------------


def test_fetch_reviews_normalizes_approved_note(monkeypatch: pytest.MonkeyPatch) -> None:
    """An 'approved this merge request' system note produces an approved Review row."""

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path.endswith("/merge_requests/2001"):
                return httpx.Response(200, json=_mr_global_payload())
            if "/notes" in path:
                return _notes_response(
                    [_note_payload(author_id=42, created_at="2026-05-10T10:00:00Z")]
                )
            if "/reviewers" in path:
                return _reviewers_response([])
            raise AssertionError(f"unexpected path: {path}")

        connector = _make_connector(monkeypatch, handler)
        reviews = await _collect(connector.fetch_reviews(["gitlab.example.com/2001"]))
        await connector.close()

        assert len(reviews) == 1
        r = reviews[0]
        assert r.decision is ReviewDecision.APPROVED
        assert r.reviewer_id == _stable_id("user", "gitlab.example.com/42")
        assert r.mergerequest_id == _stable_id("mergerequest", "gitlab.example.com/2001")
        assert r.submitted_at == datetime(2026, 5, 10, 10, 0, 0, tzinfo=timezone.utc)

    asyncio.run(run())


def test_fetch_reviews_normalizes_dismissed_from_unapproved_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An 'unapproved this merge request' note maps to decision=dismissed."""

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path.endswith("/merge_requests/2001"):
                return httpx.Response(200, json=_mr_global_payload())
            if "/notes" in path:
                return _notes_response([_note_payload(body="unapproved this merge request")])
            if "/reviewers" in path:
                return _reviewers_response([])
            raise AssertionError(f"unexpected path: {path}")

        connector = _make_connector(monkeypatch, handler)
        reviews = await _collect(connector.fetch_reviews(["gitlab.example.com/2001"]))
        await connector.close()

        assert len(reviews) == 1
        assert reviews[0].decision is ReviewDecision.DISMISSED

    asyncio.run(run())


def test_fetch_reviews_changes_requested_note_produces_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 'requested changes' system note produces a CHANGES_REQUESTED row.

    Notes are historical and ordered, so they are the authoritative source for
    CHANGES_REQUESTED.  Reviewer state is a snapshot of current state only — if a reviewer
    requests changes and then approves, the state becomes 'approved' and the prior
    CHANGES_REQUESTED event would be silently lost if sourced from reviewer state alone.
    """

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path.endswith("/merge_requests/2001"):
                return httpx.Response(200, json=_mr_global_payload())
            if "/notes" in path:
                return _notes_response(
                    [
                        _note_payload(
                            body="requested changes",
                            author_id=42,
                            created_at="2026-05-10T10:00:00Z",
                        )
                    ]
                )
            if "/reviewers" in path:
                return _reviewers_response([])
            raise AssertionError(f"unexpected path: {path}")

        connector = _make_connector(monkeypatch, handler)
        reviews = await _collect(connector.fetch_reviews(["gitlab.example.com/2001"]))
        await connector.close()

        assert len(reviews) == 1
        r = reviews[0]
        assert r.decision is ReviewDecision.CHANGES_REQUESTED
        assert r.reviewer_id == _stable_id("user", "gitlab.example.com/42")
        assert r.submitted_at == datetime(2026, 5, 10, 10, 0, 0, tzinfo=timezone.utc)

    asyncio.run(run())


def test_fetch_reviews_requested_row_has_null_submitted_at(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Assigned reviewers produce a requested row with submitted_at=None."""

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path.endswith("/merge_requests/2001"):
                return httpx.Response(200, json=_mr_global_payload())
            if "/notes" in path:
                return _notes_response([])
            if "/reviewers" in path:
                return _reviewers_response([_reviewer_payload(reviewer_id=99)])
            raise AssertionError(f"unexpected path: {path}")

        connector = _make_connector(monkeypatch, handler)
        reviews = await _collect(connector.fetch_reviews(["gitlab.example.com/2001"]))
        await connector.close()

        assert len(reviews) == 1
        r = reviews[0]
        assert r.decision is ReviewDecision.REQUESTED
        assert r.submitted_at is None
        assert r.reviewer_id == _stable_id("user", "gitlab.example.com/99")
        assert r.mergerequest_id == _stable_id("mergerequest", "gitlab.example.com/2001")

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Ordering: approve then unapprove yields two rows in order
# ---------------------------------------------------------------------------


def test_fetch_reviews_approve_then_unapprove_yields_two_ordered_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Approve followed by unapprove produces two Review rows preserving event order."""

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path.endswith("/merge_requests/2001"):
                return httpx.Response(200, json=_mr_global_payload())
            if "/notes" in path:
                return _notes_response(
                    [
                        _note_payload(
                            note_id=1,
                            body="approved this merge request",
                            author_id=42,
                            created_at="2026-05-10T10:00:00Z",
                        ),
                        _note_payload(
                            note_id=2,
                            body="unapproved this merge request",
                            author_id=42,
                            created_at="2026-05-10T11:00:00Z",
                        ),
                    ]
                )
            if "/reviewers" in path:
                return _reviewers_response([])
            raise AssertionError(f"unexpected path: {path}")

        connector = _make_connector(monkeypatch, handler)
        reviews = await _collect(connector.fetch_reviews(["gitlab.example.com/2001"]))
        await connector.close()

        assert len(reviews) == 2
        assert reviews[0].decision is ReviewDecision.APPROVED
        assert reviews[0].submitted_at == datetime(2026, 5, 10, 10, 0, 0, tzinfo=timezone.utc)
        assert reviews[1].decision is ReviewDecision.DISMISSED
        assert reviews[1].submitted_at == datetime(2026, 5, 10, 11, 0, 0, tzinfo=timezone.utc)
        # Both rows belong to the same reviewer.
        assert reviews[0].reviewer_id == reviews[1].reviewer_id

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Non-review notes are skipped
# ---------------------------------------------------------------------------


def test_fetch_reviews_skips_non_system_notes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Notes with system=False are not converted to Review rows."""

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path.endswith("/merge_requests/2001"):
                return httpx.Response(200, json=_mr_global_payload())
            if "/notes" in path:
                return _notes_response(
                    [
                        _note_payload(
                            body="approved this merge request",
                            system=False,
                        )
                    ]
                )
            if "/reviewers" in path:
                return _reviewers_response([])
            raise AssertionError(f"unexpected path: {path}")

        connector = _make_connector(monkeypatch, handler)
        reviews = await _collect(connector.fetch_reviews(["gitlab.example.com/2001"]))
        await connector.close()

        assert reviews == []

    asyncio.run(run())


def test_fetch_reviews_skips_unrecognised_system_notes(monkeypatch: pytest.MonkeyPatch) -> None:
    """System notes that do not match any review pattern are silently skipped."""

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path.endswith("/merge_requests/2001"):
                return httpx.Response(200, json=_mr_global_payload())
            if "/notes" in path:
                return _notes_response(
                    [
                        _note_payload(
                            body="added 2 commits",
                            system=True,
                        ),
                        _note_payload(
                            body="marked this merge request as ready",
                            system=True,
                        ),
                    ]
                )
            if "/reviewers" in path:
                return _reviewers_response([])
            raise AssertionError(f"unexpected path: {path}")

        connector = _make_connector(monkeypatch, handler)
        reviews = await _collect(connector.fetch_reviews(["gitlab.example.com/2001"]))
        await connector.close()

        assert reviews == []

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Mixed: notes + reviewer requests
# ---------------------------------------------------------------------------


def test_fetch_reviews_yields_activity_then_requested(monkeypatch: pytest.MonkeyPatch) -> None:
    """Activity rows (from notes) come before requested rows in the output."""

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path.endswith("/merge_requests/2001"):
                return httpx.Response(200, json=_mr_global_payload())
            if "/notes" in path:
                return _notes_response(
                    [_note_payload(body="approved this merge request", author_id=42)]
                )
            if "/reviewers" in path:
                return _reviewers_response([_reviewer_payload(reviewer_id=99)])
            raise AssertionError(f"unexpected path: {path}")

        connector = _make_connector(monkeypatch, handler)
        reviews = await _collect(connector.fetch_reviews(["gitlab.example.com/2001"]))
        await connector.close()

        assert len(reviews) == 2
        assert reviews[0].decision is ReviewDecision.APPROVED
        assert reviews[0].submitted_at is not None
        assert reviews[1].decision is ReviewDecision.REQUESTED
        assert reviews[1].submitted_at is None

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Multiple MRs
# ---------------------------------------------------------------------------


def test_fetch_reviews_iterates_multiple_mr_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reviews are yielded for each MR in the input list, in order."""

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path.endswith("/merge_requests/2001"):
                return httpx.Response(200, json=_mr_global_payload(mr_id=2001, iid=7))
            if path.endswith("/merge_requests/3001"):
                return httpx.Response(
                    200, json=_mr_global_payload(mr_id=3001, project_id=202, iid=12)
                )
            if "/projects/101/" in path and "/notes" in path:
                return _notes_response(
                    [_note_payload(body="approved this merge request", author_id=10)]
                )
            if "/projects/202/" in path and "/notes" in path:
                return _notes_response(
                    [_note_payload(body="approved this merge request", author_id=20)]
                )
            if "/reviewers" in path:
                return _reviewers_response([])
            raise AssertionError(f"unexpected path: {path}")

        connector = _make_connector(monkeypatch, handler)
        reviews = await _collect(connector.fetch_reviews(["gitlab.example.com/2001", "gitlab.example.com/3001"]))
        await connector.close()

        assert len(reviews) == 2
        assert reviews[0].mergerequest_id == _stable_id("mergerequest", "gitlab.example.com/2001")
        assert reviews[1].mergerequest_id == _stable_id("mergerequest", "gitlab.example.com/3001")

    asyncio.run(run())


def test_fetch_reviews_empty_mr_id_list_yields_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError(f"unexpected request: {request.url.path}")

        connector = _make_connector(monkeypatch, handler)
        reviews = await _collect(connector.fetch_reviews([]))
        await connector.close()

        assert reviews == []

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Pagination of notes
# ---------------------------------------------------------------------------


def test_fetch_reviews_paginates_notes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Notes are fetched across multiple pages; all matching rows are yielded."""

    async def run() -> None:
        pages_fetched: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path.endswith("/merge_requests/2001"):
                return httpx.Response(200, json=_mr_global_payload())
            if "/notes" in path:
                page = request.url.params.get("page", "1")
                pages_fetched.append(page)
                if page == "1":
                    return _notes_response(
                        [_note_payload(note_id=1, body="approved this merge request")],
                        next_page="2",
                    )
                # Page 2 — last page.
                return _notes_response(
                    [_note_payload(note_id=2, body="unapproved this merge request")]
                )
            if "/reviewers" in path:
                return _reviewers_response([])
            raise AssertionError(f"unexpected path: {path}")

        connector = _make_connector(monkeypatch, handler)
        reviews = await _collect(connector.fetch_reviews(["gitlab.example.com/2001"]))
        await connector.close()

        assert len(reviews) == 2
        assert reviews[0].decision is ReviewDecision.APPROVED
        assert reviews[1].decision is ReviewDecision.DISMISSED
        assert pages_fetched == ["1", "2"]

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Reviewer state filtering (fix #2 and #3)
# ---------------------------------------------------------------------------


def test_fetch_reviews_acted_reviewer_does_not_produce_requested_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A reviewer who already approved does not produce a requested row."""

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path.endswith("/merge_requests/2001"):
                return httpx.Response(200, json=_mr_global_payload())
            if "/notes" in path:
                return _notes_response([])
            if "/reviewers" in path:
                return _reviewers_response([_reviewer_payload(reviewer_id=99, state="approved")])
            raise AssertionError(f"unexpected path: {path}")

        connector = _make_connector(monkeypatch, handler)
        reviews = await _collect(connector.fetch_reviews(["gitlab.example.com/2001"]))
        await connector.close()

        assert reviews == []

    asyncio.run(run())


def test_fetch_reviews_review_started_produces_requested_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A reviewer with state='review_started' (non-terminal) produces a REQUESTED row."""

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path.endswith("/merge_requests/2001"):
                return httpx.Response(200, json=_mr_global_payload())
            if "/notes" in path:
                return _notes_response([])
            if "/reviewers" in path:
                return _reviewers_response(
                    [_reviewer_payload(reviewer_id=99, state="review_started")]
                )
            raise AssertionError(f"unexpected path: {path}")

        connector = _make_connector(monkeypatch, handler)
        reviews = await _collect(connector.fetch_reviews(["gitlab.example.com/2001"]))
        await connector.close()

        assert len(reviews) == 1
        assert reviews[0].decision is ReviewDecision.REQUESTED
        assert reviews[0].submitted_at is None
        assert reviews[0].reviewer_id == _stable_id("user", "gitlab.example.com/99")

    asyncio.run(run())


def test_fetch_reviews_reviewed_state_yields_no_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression guard: state='reviewed' is a terminal/acted state and yields zero rows."""

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path.endswith("/merge_requests/2001"):
                return httpx.Response(200, json=_mr_global_payload())
            if "/notes" in path:
                return _notes_response([])
            if "/reviewers" in path:
                return _reviewers_response([_reviewer_payload(reviewer_id=99, state="reviewed")])
            raise AssertionError(f"unexpected path: {path}")

        connector = _make_connector(monkeypatch, handler)
        reviews = await _collect(connector.fetch_reviews(["gitlab.example.com/2001"]))
        await connector.close()

        assert reviews == []

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Pagination of reviewer requests (fix #4)
# ---------------------------------------------------------------------------


def test_fetch_reviews_paginates_reviewers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reviewer requests are fetched across multiple pages; all rows are yielded."""

    async def run() -> None:
        pages_fetched: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path.endswith("/merge_requests/2001"):
                return httpx.Response(200, json=_mr_global_payload())
            if "/notes" in path:
                return _notes_response([])
            if "/reviewers" in path:
                page = request.url.params.get("page", "1")
                pages_fetched.append(page)
                if page == "1":
                    return httpx.Response(
                        200,
                        headers={"X-Next-Page": "2"},
                        json=[_reviewer_payload(reviewer_id=99)],
                    )
                return httpx.Response(
                    200,
                    headers={"X-Next-Page": ""},
                    json=[_reviewer_payload(reviewer_id=100)],
                )
            raise AssertionError(f"unexpected path: {path}")

        connector = _make_connector(monkeypatch, handler)
        reviews = await _collect(connector.fetch_reviews(["gitlab.example.com/2001"]))
        await connector.close()

        assert pages_fetched == ["1", "2"]
        assert len(reviews) == 2
        assert all(r.decision is ReviewDecision.REQUESTED for r in reviews)
        reviewer_ids = {r.reviewer_id for r in reviews}
        assert reviewer_ids == {
            _stable_id("user", "gitlab.example.com/99"),
            _stable_id("user", "gitlab.example.com/100"),
        }

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Reviewers endpoint degradation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status_code", [404, 403])
def test_fetch_reviews_reviewer_endpoint_unavailable_degrades_gracefully(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
) -> None:
    """Reviewers endpoint returning 404/403 is silently ignored; activity rows still emit."""

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path.endswith("/merge_requests/2001"):
                return httpx.Response(200, json=_mr_global_payload())
            if "/notes" in path:
                return _notes_response([_note_payload(body="approved this merge request")])
            if "/reviewers" in path:
                return httpx.Response(status_code)
            raise AssertionError(f"unexpected path: {path}")

        connector = _make_connector(monkeypatch, handler)
        reviews = await _collect(connector.fetch_reviews(["gitlab.example.com/2001"]))
        await connector.close()

        # Activity row from note is still yielded even though reviewers was unavailable.
        assert len(reviews) == 1
        assert reviews[0].decision is ReviewDecision.APPROVED

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_fetch_reviews_mr_global_404_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 404 on the global MR lookup raises ConnectorDataError (not a silent skip)."""

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404)

        connector = _make_connector(monkeypatch, handler)
        # ConnectorNotFoundError is a subclass of ConnectorError; the engine handles it.
        from em_radar_core.connectors import ConnectorNotFoundError

        with pytest.raises(ConnectorNotFoundError):
            await _collect(connector.fetch_reviews(["gitlab.example.com/9999"]))
        await connector.close()

    asyncio.run(run())


def test_fetch_reviews_network_error_raises_transient(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("network down", request=request)

        connector = _make_connector(monkeypatch, handler)
        with pytest.raises(ConnectorTransientError):
            await _collect(connector.fetch_reviews(["gitlab.example.com/2001"]))
        await connector.close()

    asyncio.run(run())


def test_fetch_reviews_notes_500_raises_transient(monkeypatch: pytest.MonkeyPatch) -> None:
    """HTTP 500 from the notes endpoint propagates as ConnectorTransientError."""

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path.endswith("/merge_requests/2001"):
                return httpx.Response(200, json=_mr_global_payload())
            if "/notes" in path:
                return httpx.Response(500)
            raise AssertionError(f"unexpected path: {path}")

        connector = _make_connector(monkeypatch, handler)
        with pytest.raises(ConnectorTransientError):
            await _collect(connector.fetch_reviews(["gitlab.example.com/2001"]))
        await connector.close()

    asyncio.run(run())


def test_fetch_reviews_invalid_note_datetime_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unparseable created_at in a matching note raises ConnectorDataError."""

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path.endswith("/merge_requests/2001"):
                return httpx.Response(200, json=_mr_global_payload())
            if "/notes" in path:
                return _notes_response(
                    [
                        _note_payload(
                            body="approved this merge request",
                            created_at="not-a-date",
                        )
                    ]
                )
            if "/reviewers" in path:
                return _reviewers_response([])
            raise AssertionError(f"unexpected path: {path}")

        connector = _make_connector(monkeypatch, handler)
        with pytest.raises(ConnectorDataError, match="not-a-date"):
            await _collect(connector.fetch_reviews(["gitlab.example.com/2001"]))
        await connector.close()

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Decision mapping — parametrized
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("note_body", "expected_decision"),
    [
        ("approved this merge request", ReviewDecision.APPROVED),
        ("approved this merge request at 2026-05-01", ReviewDecision.APPROVED),  # suffix variation
        ("unapproved this merge request", ReviewDecision.DISMISSED),
        ("requested changes", ReviewDecision.CHANGES_REQUESTED),
    ],
)
def test_fetch_reviews_decision_mapping(
    monkeypatch: pytest.MonkeyPatch,
    note_body: str,
    expected_decision: ReviewDecision,
) -> None:
    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path.endswith("/merge_requests/2001"):
                return httpx.Response(200, json=_mr_global_payload())
            if "/notes" in path:
                return _notes_response([_note_payload(body=note_body)])
            if "/reviewers" in path:
                return _reviewers_response([])
            raise AssertionError(f"unexpected path: {path}")

        connector = _make_connector(monkeypatch, handler)
        reviews = await _collect(connector.fetch_reviews(["gitlab.example.com/2001"]))
        await connector.close()

        assert len(reviews) == 1
        assert reviews[0].decision is expected_decision

    asyncio.run(run())
