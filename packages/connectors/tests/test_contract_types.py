from dataclasses import FrozenInstanceError
from typing import ClassVar

import pytest

from em_radar_core.connectors import (
    Capabilities,
    CommentProvider,
    ConnectionTestResult,
    ConnectorAuthError,
    ConnectorBase,
    ConnectorConfigError,
    ConnectorDataError,
    ConnectorError,
    ConnectorNotFoundError,
    ConnectorRateLimitedError,
    ConnectorTransientError,
    MergeRequestProvider,
    MergeRequestScope,
    ReviewProvider,
    TransitionProvider,
    WorkItemProvider,
    WorkItemScope,
)


class StubConnector:
    name: ClassVar[str] = "stub"
    display_name: ClassVar[str] = "Stub"
    config_schema: ClassVar[dict[str, object]] = {"type": "object"}
    min_model_version: ClassVar[int] = 1

    def __init__(self, config: dict[str, object]) -> None:
        self.config = config

    async def test_connection(self) -> ConnectionTestResult:
        return ConnectionTestResult(ok=True, detail="Connected")

    def describe_capabilities(self) -> Capabilities:
        return Capabilities()

    async def close(self) -> None:
        pass


def accepts_connector(connector: ConnectorBase) -> ConnectorBase:
    return connector


def test_stub_satisfies_connector_base() -> None:
    connector = StubConnector({})

    assert accepts_connector(connector) is connector
    assert isinstance(connector, ConnectorBase)


@pytest.mark.parametrize(
    "protocol",
    [
        ConnectorBase,
        WorkItemProvider,
        MergeRequestProvider,
        ReviewProvider,
        TransitionProvider,
        CommentProvider,
    ],
)
def test_protocols_are_runtime_checkable(protocol: type[object]) -> None:
    assert isinstance(object(), protocol) is False


def test_capabilities_is_frozen_and_defaults_to_no_capabilities() -> None:
    capabilities = Capabilities()

    assert capabilities == Capabilities()
    with pytest.raises(FrozenInstanceError):
        capabilities.provides_workitems = True


def test_scope_and_result_list_defaults_are_independent() -> None:
    first_workitem_scope = WorkItemScope(project_external_ids=["project-1"])
    second_workitem_scope = WorkItemScope(project_external_ids=["project-2"])
    first_result = ConnectionTestResult(ok=True, detail="Connected")
    second_result = ConnectionTestResult(ok=True, detail="Connected")

    first_workitem_scope.board_external_ids.append("board-1")
    first_result.permissions.append("read")

    assert second_workitem_scope.board_external_ids == []
    assert second_result.permissions == []
    assert MergeRequestScope(repository_external_ids=["repo-1"]).include_drafts is True


@pytest.mark.parametrize(
    "error_type",
    [
        ConnectorAuthError,
        ConnectorNotFoundError,
        ConnectorRateLimitedError,
        ConnectorTransientError,
        ConnectorConfigError,
        ConnectorDataError,
    ],
)
def test_connector_errors_share_base(error_type: type[ConnectorError]) -> None:
    assert issubclass(error_type, ConnectorError)
