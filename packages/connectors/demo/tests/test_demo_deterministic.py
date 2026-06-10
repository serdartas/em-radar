import asyncio
from collections.abc import AsyncIterator
from importlib.metadata import entry_points
from uuid import UUID

from em_radar_connector_demo import (
    DEMO_COMMENT_COUNT,
    DEMO_MERGEREQUEST_COUNT,
    DEMO_PROJECT_COUNT,
    DEMO_REPOSITORY_COUNT,
    DEMO_REVIEW_COUNT,
    DEMO_SPRINT_COUNT,
    DEMO_TRANSITION_COUNT,
    DEMO_WORKITEM_COUNT,
    DemoConnector,
)
from em_radar_core.connectors import (
    CommentProvider,
    ConnectorBase,
    MergeRequestProvider,
    MergeRequestScope,
    ReviewProvider,
    TransitionProvider,
    WorkItemProvider,
    WorkItemScope,
)
from em_radar_core.models import (
    EntityType,
    EvaluationWindow,
    SprintState,
    WindowType,
)


async def collect(iterator: AsyncIterator[object]) -> list[object]:
    return [item async for item in iterator]


def sprint_window(sprint_id: UUID) -> EvaluationWindow:
    return EvaluationWindow(
        window_type=WindowType.SPRINT,
        sprint_id=sprint_id,
        team_profile_id=UUID(int=1),
    )


def test_two_connectors_produce_identical_documented_fixture() -> None:
    asyncio.run(_assert_two_connectors_produce_identical_documented_fixture())


async def _assert_two_connectors_produce_identical_documented_fixture() -> None:
    first = DemoConnector({})
    second = DemoConnector({})
    projects = await first.list_projects()
    boards = [board for project in projects for board in await first.list_boards(str(project.id))]
    sprints = [sprint for board in boards for sprint in await first.list_sprints(str(board.id))]
    repositories = await first.list_repositories()
    active_sprint = next(sprint for sprint in sprints if sprint.state is SprintState.ACTIVE)
    workitem_scope = WorkItemScope(project_external_ids=[project.external_id for project in projects])
    mr_scope = MergeRequestScope(
        repository_external_ids=[repository.external_id for repository in repositories],
        include_closed_unmerged=True,
    )
    merge_requests = await collect(
        first.fetch_mergerequests(mr_scope, sprint_window(active_sprint.id))
    )
    all_workitems = await collect(
        first.fetch_workitems(
            workitem_scope,
            EvaluationWindow(
                window_type=WindowType.DATE_RANGE,
                start=active_sprint.created_at,
                end=active_sprint.end_date,
                team_profile_id=UUID(int=1),
            ),
        )
    )
    reviews = await collect(
        first.fetch_reviews([merge_request.external_id for merge_request in merge_requests])
    )
    transitions = await collect(
        first.fetch_transitions(
            "workitem", [workitem.external_id for workitem in all_workitems]
        )
    )
    workitem_comments = await collect(
        first.fetch_comments("workitem", [workitem.external_id for workitem in all_workitems])
    )
    mr_comments = await collect(
        first.fetch_comments(
            "mergerequest", [merge_request.external_id for merge_request in merge_requests]
        )
    )

    assert len(projects) == DEMO_PROJECT_COUNT
    assert len(sprints) == DEMO_SPRINT_COUNT
    assert sum(sprint.state is SprintState.ACTIVE for sprint in sprints) == 1
    assert len(all_workitems) == DEMO_WORKITEM_COUNT
    assert len(repositories) == DEMO_REPOSITORY_COUNT
    assert len(merge_requests) == DEMO_MERGEREQUEST_COUNT
    assert len(reviews) == DEMO_REVIEW_COUNT
    assert len(transitions) == DEMO_TRANSITION_COUNT
    assert len(workitem_comments) + len(mr_comments) == DEMO_COMMENT_COUNT

    second_projects = await second.list_projects()
    second_repositories = await second.list_repositories()
    second_workitems = await collect(
        second.fetch_workitems(
            WorkItemScope(
                project_external_ids=[project.external_id for project in second_projects]
            ),
            EvaluationWindow(
                window_type=WindowType.DATE_RANGE,
                start=active_sprint.created_at,
                end=active_sprint.end_date,
                team_profile_id=UUID(int=1),
            ),
        )
    )
    second_merge_requests = await collect(
        second.fetch_mergerequests(
            MergeRequestScope(
                repository_external_ids=[
                    repository.external_id for repository in second_repositories
                ],
                include_closed_unmerged=True,
            ),
            sprint_window(active_sprint.id),
        )
    )

    assert [project.model_dump() for project in projects] == [
        project.model_dump() for project in second_projects
    ]
    assert [item.model_dump() for item in all_workitems] == [
        item.model_dump() for item in second_workitems
    ]
    assert [mr.model_dump() for mr in merge_requests] == [
        mr.model_dump() for mr in second_merge_requests
    ]


def test_connection_capabilities_protocols_and_entry_point() -> None:
    asyncio.run(_assert_connection_capabilities_protocols_and_entry_point())


async def _assert_connection_capabilities_protocols_and_entry_point() -> None:
    connector = DemoConnector({})
    result = await connector.test_connection()
    capabilities = connector.describe_capabilities()
    registered = entry_points(group="em_radar.connectors")

    assert result.ok is True
    assert all(
        isinstance(connector, protocol)
        for protocol in (
            ConnectorBase,
            WorkItemProvider,
            MergeRequestProvider,
            ReviewProvider,
            TransitionProvider,
            CommentProvider,
        )
    )
    assert all(
        (
            capabilities.provides_workitems,
            capabilities.provides_sprints,
            capabilities.provides_mergerequests,
            capabilities.provides_repositories,
            capabilities.provides_reviews,
            capabilities.provides_comments,
            capabilities.provides_transitions,
        )
    )
    assert any(
        entry_point.name == "demo"
        and entry_point.value == "em_radar_connector_demo:DemoConnector"
        for entry_point in registered
    )


def test_provider_filters_are_honored() -> None:
    asyncio.run(_assert_provider_filters_are_honored())


async def _assert_provider_filters_are_honored() -> None:
    connector = DemoConnector({})
    project = (await connector.list_projects())[0]
    repository = (await connector.list_repositories())[0]
    board = (await connector.list_boards(str(project.id)))[0]
    active_sprint = next(
        sprint
        for sprint in await connector.list_sprints(str(board.id))
        if sprint.state is SprintState.ACTIVE
    )

    workitems = await collect(
        connector.fetch_workitems(
            WorkItemScope(project_external_ids=[project.external_id]),
            sprint_window(active_sprint.id),
        )
    )
    merge_requests = await collect(
        connector.fetch_mergerequests(
            MergeRequestScope(
                repository_external_ids=[repository.external_id],
                include_drafts=False,
                include_closed_unmerged=False,
            ),
            sprint_window(active_sprint.id),
        )
    )

    assert workitems
    assert all(workitem.project_id == project.id for workitem in workitems)
    assert all(active_sprint.id in workitem.sprint_ids for workitem in workitems)
    assert all(merge_request.repository_id == repository.id for merge_request in merge_requests)
    assert all(not merge_request.is_draft for merge_request in merge_requests)
    assert all(merge_request.state.value != "closed" for merge_request in merge_requests)
    assert await collect(connector.fetch_comments(EntityType.WORKITEM, ["unknown"])) == []
