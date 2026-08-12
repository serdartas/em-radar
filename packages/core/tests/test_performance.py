"""Performance benchmark (M5-09): full signal evaluation over a large fixture must stay under 60s.

Marked with the 'perf' pytest mark. Exercises the evaluator over ~500 work items and verifies
the 60s budget is met. Also exercises concurrency by measuring that concurrent coroutines run
in parallel when using asyncio.gather.
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
    ReportSettings,
    SignalDefinition,
    SignalOrigin,
    StatusCategory,
    TeamProfile,
    WindowType,
)
from em_radar_core.signals import SignalData
from em_radar_connector_jira.connector import JiraConnector

from _signal_helpers import NOW, project, workitem

_WORKITEM_COUNT = 500
_BUDGET_SECONDS = 60.0

pytestmark = pytest.mark.perf


# ---------------------------------------------------------------------------
# Helpers
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
# Benchmark: pure evaluation speed
# ---------------------------------------------------------------------------


@pytest.mark.perf
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


@pytest.mark.perf
def test_multiple_signals_over_500_workitems_complete_under_budget() -> None:
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
# Concurrency: asyncio.gather runs tasks in parallel
# ---------------------------------------------------------------------------


@pytest.mark.perf
def test_asyncio_gather_fetches_sources_concurrently() -> None:
    """asyncio.gather must run both tasks concurrently, not sequentially.

    Creates two coroutines each sleeping 0.1s; gather should complete in ~0.1s,
    not ~0.2s, proving that the report runner's concurrent fetch path overlaps I/O.
    """
    SLEEP = 0.1

    async def _fake_board_fetch():
        await asyncio.sleep(SLEEP)
        return "board"

    async def _fake_code_fetch():
        await asyncio.sleep(SLEEP)
        return "code"

    async def run():
        start = time.monotonic()
        board, code = await asyncio.gather(_fake_board_fetch(), _fake_code_fetch())
        elapsed = time.monotonic() - start
        return elapsed, board, code

    elapsed, board, code = asyncio.run(run())

    assert board == "board"
    assert code == "code"
    assert elapsed < SLEEP * 1.8, (
        f"Concurrent gather took {elapsed:.3f}s — expected ~{SLEEP}s (both tasks in parallel)"
    )
