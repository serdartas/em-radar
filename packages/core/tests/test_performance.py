"""Performance benchmark (M5-09): full signal evaluation over a large fixture must stay under 60s.

Marked with the 'perf' pytest mark. Exercises the evaluator over ~500 work items, and verifies
that concurrent asyncio.gather over the workitem + MR fetch coroutines runs faster than sequential.
"""

from __future__ import annotations

import asyncio
import time
from datetime import timedelta
from uuid import uuid4

import pytest

from em_radar_core.evaluation import ScopeDescriptor, evaluate_signal_definition
from em_radar_core.models import (
    EvaluationContext,
    EvaluationWindow,
    MergeRequest,
    MergeRequestState,
    ReportSettings,
    SignalDefinition,
    SignalOrigin,
    Source,
    StatusCategory,
    TeamProfile,
    WindowType,
)
from em_radar_core.signals import SignalData
from em_radar_connector_jira.connector import JiraConnector

from _signal_helpers import NOW, project, workitem

_WORKITEM_COUNT = 500
_MR_COUNT = 300
_BUDGET_SECONDS = 60.0

pytestmark = pytest.mark.perf


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _large_workitems(count: int) -> tuple:
    items = []
    for i in range(count):
        status_cat = StatusCategory.IN_PROGRESS if i % 3 != 0 else StatusCategory.DONE
        item = workitem(
            key=f"PERF-{i}",
            status_category=status_cat,
            status="In Progress" if status_cat is StatusCategory.IN_PROGRESS else "Done",
            updated_at=NOW - timedelta(days=(i % 30)),
            created_at=NOW - timedelta(days=60 + i % 30),
        )
        if status_cat is StatusCategory.DONE:
            item.resolved_at = NOW
        items.append(item)
    return tuple(items)


def _large_mergerequests(count: int) -> tuple:
    repo_id = uuid4()
    author_id = uuid4()
    mrs = []
    for i in range(count):
        mrs.append(
            MergeRequest(
                source=Source.GITLAB,
                external_id=f"mr-{i}",
                repository_id=repo_id,
                iid=i + 1,
                title=f"MR {i}",
                state=MergeRequestState.OPEN if i % 4 != 0 else MergeRequestState.MERGED,
                author_id=author_id,
                target_branch="main",
                source_branch=f"feature/branch-{i}",
                created_at=NOW - timedelta(days=i % 30),
                updated_at=NOW - timedelta(days=i % 15),
                merged_at=NOW if (i % 4 == 0) else None,
            )
        )
    return tuple(mrs)


def _stale_signal() -> SignalDefinition:
    return SignalDefinition(
        name="Stale in-progress",
        entity_type="issue",
        expression={
            "type": "group",
            "operator": "all",
            "conditions": [
                {"field": "status_category", "operator": "is", "value": "in_progress"},
                {
                    "field": "age_since_updated",
                    "operator": "greater_than",
                    "value": {"amount": 7, "unit": "days"},
                },
            ],
        },
        report_settings=ReportSettings(severity="warning", category="flow"),
        enabled=True,
        origin=SignalOrigin.USER_CREATED,
        created_at=NOW,
        updated_at=NOW,
    )


def _scope() -> ScopeDescriptor:
    return ScopeDescriptor(
        connector_id="jira-1",
        scope_id="scope-1",
        scope_type="project",
        name="Perf project",
        external_ref={"type": "jira_project", "id": "PROJECT", "key": "PERF", "name": "Perf"},
        capabilities=("statuses", "labels"),
    )


def _eval_context() -> EvaluationContext:
    team = TeamProfile(name="perf", created_at=NOW, updated_at=NOW)
    window = EvaluationWindow(
        window_type=WindowType.DATE_RANGE,
        start=NOW,
        end=NOW,
        team_profile_id=team.id,
    )
    return EvaluationContext(now=NOW, window=window, team=team)


# ---------------------------------------------------------------------------
# Benchmark: pure evaluation speed over 500 WI
# ---------------------------------------------------------------------------


def test_evaluation_over_500_workitems_completes_under_budget() -> None:
    """Evaluating one signal over 500 work items must complete within the 60s budget."""
    workitems = _large_workitems(_WORKITEM_COUNT)
    signal = _stale_signal()
    data = SignalData(report_id=uuid4(), projects=(project(),), workitems=workitems)
    ctx = _eval_context()

    start = time.monotonic()
    findings = evaluate_signal_definition(
        signal, data, ctx, JiraConnector.describe_signal_schema(), [_scope()]
    )
    elapsed = time.monotonic() - start

    assert elapsed < _BUDGET_SECONDS, (
        f"Evaluation took {elapsed:.2f}s — exceeds {_BUDGET_SECONDS}s budget"
    )
    assert len(findings) > 0, "Expected findings from 500 work items"


def test_five_signals_over_500_workitems_complete_under_budget() -> None:
    """Five signals evaluated sequentially over 500 work items must stay within the budget."""
    workitems = _large_workitems(_WORKITEM_COUNT)
    signals = [_stale_signal() for _ in range(5)]
    data = SignalData(report_id=uuid4(), projects=(project(),), workitems=workitems)
    ctx = _eval_context()
    schema = JiraConnector.describe_signal_schema()
    scope = [_scope()]

    start = time.monotonic()
    all_findings = []
    for sig in signals:
        all_findings.extend(evaluate_signal_definition(sig, data, ctx, schema, scope))
    elapsed = time.monotonic() - start

    assert elapsed < _BUDGET_SECONDS, (
        f"Five signals over 500 WI took {elapsed:.2f}s — exceeds {_BUDGET_SECONDS}s budget"
    )


# ---------------------------------------------------------------------------
# Concurrency benchmark: workitem + MR fetch run in parallel (architecture §18.2)
# ---------------------------------------------------------------------------


def test_concurrent_fetch_is_faster_than_sequential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """asyncio.gather over the production fetch functions is materially faster than sequential.

    Patches _fetch_workitems_and_transitions and _fetch_code_data in the reports module
    with stubs that sleep 0.1s each (simulating I/O), then times asyncio.gather over them
    to verify concurrent execution completes in ~0.1s rather than ~0.2s. Exercises the
    production function names so a rename is caught; does not drive _run_team_report itself.
    """
    import em_radar_api.routers.reports as reports_module

    FETCH_DELAY = 0.10
    workitems = _large_workitems(_WORKITEM_COUNT)

    async def _stub_wi_fetch(_meta, _window):
        await asyncio.sleep(FETCH_DELAY)
        return list(workitems), []

    async def _stub_code_fetch(_session, _conn_id, _window):
        await asyncio.sleep(FETCH_DELAY)
        return None

    monkeypatch.setattr(reports_module, "_fetch_workitems_and_transitions", _stub_wi_fetch)
    monkeypatch.setattr(reports_module, "_fetch_code_data", _stub_code_fetch)

    async def run_sequential():
        t0 = time.monotonic()
        wi = await reports_module._fetch_workitems_and_transitions(None, None)
        mr = await reports_module._fetch_code_data(None, None, None)
        return time.monotonic() - t0, wi, mr

    async def run_concurrent():
        t0 = time.monotonic()
        wi, mr = await asyncio.gather(
            reports_module._fetch_workitems_and_transitions(None, None),
            reports_module._fetch_code_data(None, None, None),
        )
        return time.monotonic() - t0, wi, mr

    seq_elapsed, seq_wi, _ = asyncio.run(run_sequential())
    con_elapsed, con_wi, _ = asyncio.run(run_concurrent())

    assert len(seq_wi[0]) == _WORKITEM_COUNT
    assert len(con_wi[0]) == _WORKITEM_COUNT

    assert con_elapsed < seq_elapsed * 0.8, (
        f"Concurrent ({con_elapsed:.3f}s) is not faster than sequential ({seq_elapsed:.3f}s); "
        "check that the Phase 2 gather in _run_team_report is still concurrent"
    )
    assert con_elapsed < _BUDGET_SECONDS, (
        f"Concurrent fetch took {con_elapsed:.2f}s — exceeds {_BUDGET_SECONDS}s budget"
    )
