# SPDX-License-Identifier: Apache-2.0

"""Demo connector — returns static in-memory data; no credentials or network required."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import ClassVar
from uuid import UUID

from em_radar_core.connectors import (
    Capabilities,
    ConnectionTestResult,
    ConnectorConfigError,
    MergeRequestScope,
    WorkItemScope,
)
from em_radar_core.models import (
    Board,
    EvaluationWindow,
    MergeRequest,
    MergeRequestState,
    Project,
    Repository,
    Source,
    Sprint,
    SprintState,
    StatusCategory,
    Transition,
    WorkItem,
    WorkItemType,
)

_NOW = datetime(2026, 1, 20, 12, tzinfo=timezone.utc)

_PROJECT_ID = UUID("00000000-0000-0000-0000-000000000001")
_BOARD_ID = UUID("00000000-0000-0000-0000-000000000002")
_REPO_ID = UUID("00000000-0000-0000-0000-000000000003")
_AUTHOR_ID = UUID("00000000-0000-0000-0000-000000000004")


class DemoConnector:
    """Minimal connector that returns static data without any external service."""

    name: ClassVar[str] = "demo"
    display_name: ClassVar[str] = "Demo (static data)"
    config_schema: ClassVar[dict[str, object]] = {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }
    min_model_version: ClassVar[int] = 1

    def __init__(self, config: dict[str, object]) -> None:
        if config:
            raise ConnectorConfigError("Demo connector takes no configuration")

    async def test_connection(self) -> ConnectionTestResult:
        return ConnectionTestResult(
            ok=True,
            detail="Connected to demo data source",
            user_display_name="Demo User",
        )

    @classmethod
    def describe_capabilities(cls) -> Capabilities:
        del cls
        return Capabilities(
            provides_workitems=True,
            provides_sprints=True,
            provides_mergerequests=True,
            provides_repositories=True,
            provides_transitions=True,
        )

    async def close(self) -> None:
        pass

    # ------------------------------------------------------------------
    # WorkItemProvider
    # ------------------------------------------------------------------

    async def list_projects(self) -> list[Project]:
        return [
            Project(
                id=_PROJECT_ID,
                source=Source.DEMO,
                external_id="DEMO",
                key="DEMO",
                name="Demo Project",
            )
        ]

    async def list_boards(self, project_id: str) -> list[Board]:
        del project_id
        return [
            Board(
                id=_BOARD_ID,
                source=Source.DEMO,
                external_id="BOARD-1",
                project_id=_PROJECT_ID,
                name="Demo Board",
            )
        ]

    async def list_sprints(self, board_id: str) -> list[Sprint]:
        del board_id
        return [
            Sprint(
                source=Source.DEMO,
                external_id="SPRINT-1",
                board_id=_BOARD_ID,
                name="Demo Sprint 1",
                state=SprintState.ACTIVE,
                start_date=_NOW,
            )
        ]

    async def fetch_workitems(
        self,
        scope: WorkItemScope,
        window: EvaluationWindow,
    ) -> AsyncIterator[WorkItem]:
        del scope, window
        yield WorkItem(
            source=Source.DEMO,
            external_id="DEMO-1",
            project_id=_PROJECT_ID,
            key="DEMO-1",
            type=WorkItemType.STORY,
            title="Demo in-progress story",
            status="In Progress",
            status_category=StatusCategory.IN_PROGRESS,
            created_at=_NOW,
            updated_at=_NOW,
        )
        yield WorkItem(
            source=Source.DEMO,
            external_id="DEMO-2",
            project_id=_PROJECT_ID,
            key="DEMO-2",
            type=WorkItemType.BUG,
            title="Demo done bug",
            status="Done",
            status_category=StatusCategory.DONE,
            created_at=_NOW,
            updated_at=_NOW,
            resolved_at=_NOW,
        )

    # ------------------------------------------------------------------
    # TransitionProvider
    # ------------------------------------------------------------------

    async def fetch_transitions(
        self,
        entity_type: str,
        entity_external_ids: list[str],
    ) -> AsyncIterator[Transition]:
        del entity_type, entity_external_ids
        return
        yield  # make it an async generator

    # ------------------------------------------------------------------
    # MergeRequestProvider
    # ------------------------------------------------------------------

    async def list_repositories(self) -> list[Repository]:
        return [
            Repository(
                id=_REPO_ID,
                source=Source.DEMO,
                external_id="repo-demo",
                name="demo-repo",
                full_path="demo/demo-repo",
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
            source=Source.DEMO,
            external_id="MR-1",
            repository_id=_REPO_ID,
            iid=1,
            title="Demo open MR",
            state=MergeRequestState.OPEN,
            author_id=_AUTHOR_ID,
            target_branch="main",
            source_branch="feature/demo",
            created_at=_NOW,
            updated_at=_NOW,
        )
