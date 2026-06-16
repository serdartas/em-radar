from __future__ import annotations

import base64
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import ClassVar, cast
from uuid import UUID, uuid5

import httpx
from pydantic import BaseModel, ConfigDict, HttpUrl, SecretStr, ValidationError

from em_radar_core.connectors import (
    Capabilities,
    ConnectionTestResult,
    ConnectorAuthError,
    ConnectorConfigError,
    ConnectorDataError,
    ConnectorNotFoundError,
    ConnectorRateLimitedError,
    ConnectorTransientError,
)
from em_radar_core.models import Board, BoardType, Project, Source, Sprint, SprintState

CLIENT_FACTORY: Callable[..., httpx.AsyncClient] = httpx.AsyncClient
PAGE_SIZE = 50
_NAMESPACE = UUID("1b6514a2-8027-43f2-a820-c771c419ca33")


class JiraConnectorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: HttpUrl
    token: SecretStr
    auth_email: str | None = None
    verify_tls: bool = True


class JiraConnector:
    name: ClassVar[str] = "jira"
    display_name: ClassVar[str] = "Jira (Cloud or Server)"
    config_schema: ClassVar[dict[str, object]] = JiraConnectorConfig.model_json_schema()
    min_model_version: ClassVar[int] = 1

    def __init__(self, config: dict[str, object]) -> None:
        try:
            self.config = JiraConnectorConfig.model_validate(config)
        except ValidationError as error:
            raise ConnectorConfigError("Invalid Jira connector config") from error

        self._client = CLIENT_FACTORY(
            base_url=str(self.config.base_url),
            headers={"Authorization": _authorization_header(self.config)},
            verify=self.config.verify_tls,
        )

    async def test_connection(self) -> ConnectionTestResult:
        user_payload = await self._request_json("rest/api/2/myself")
        permissions_payload = await self._request_json("rest/api/2/mypermissions")
        return ConnectionTestResult(
            ok=True,
            detail="Connected to Jira",
            user_display_name=_display_name(user_payload),
            permissions=_permissions(permissions_payload),
        )

    @classmethod
    def describe_capabilities(cls) -> Capabilities:
        del cls
        return Capabilities(
            provides_workitems=False,
            provides_sprints=False,
            provides_transitions=False,
            supports_incremental_fetch=False,
        )

    async def list_projects(self) -> list[Project]:
        payloads = await self._request_paginated_values("/rest/api/3/project/search")
        return [_project_from_payload(payload, self._base_url) for payload in payloads]

    async def list_boards(self, project_id: str) -> list[Board]:
        payloads = await self._request_paginated_values(
            "/rest/agile/1.0/board",
            params={"projectKeyOrId": project_id},
        )
        return [_board_from_payload(payload, self._base_url, project_id) for payload in payloads]

    async def list_sprints(self, board_id: str) -> list[Sprint]:
        payloads = await self._request_paginated_values(f"/rest/agile/1.0/board/{board_id}/sprint")
        return [_sprint_from_payload(payload, board_id) for payload in payloads]

    async def close(self) -> None:
        await self._client.aclose()

    async def _request_json(
        self,
        path: str,
        *,
        params: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        try:
            response = await self._client.get(path, params=params)
        except httpx.RequestError as error:
            raise ConnectorTransientError("Failed to reach Jira") from error

        if response.status_code >= 400:
            raise _error_for_status(response.status_code)

        try:
            payload = response.json()
        except ValueError as error:
            raise ConnectorDataError("Jira returned invalid JSON") from error

        if not isinstance(payload, dict):
            raise ConnectorDataError("Jira returned an unexpected payload shape")
        return cast(dict[str, object], payload)

    async def _request_paginated_values(
        self,
        path: str,
        *,
        params: Mapping[str, object] | None = None,
    ) -> list[Mapping[str, object]]:
        values: list[Mapping[str, object]] = []
        start_at = 0
        while True:
            page_params = {
                "startAt": start_at,
                "maxResults": PAGE_SIZE,
                **dict(params or {}),
            }
            payload = await self._request_json(path, params=page_params)
            page_values = _payload_values(payload)
            values.extend(page_values)

            next_start_at = start_at + len(page_values)
            if _is_last_page(payload, next_start_at):
                return values
            if next_start_at == start_at:
                raise ConnectorDataError("Jira pagination did not advance")
            start_at = next_start_at

    @property
    def _base_url(self) -> str:
        return str(self.config.base_url).rstrip("/")


def _authorization_header(config: JiraConnectorConfig) -> str:
    token = config.token.get_secret_value()
    if config.auth_email is None:
        return f"Bearer {token}"

    secret = f"{config.auth_email}:{token}".encode("utf-8")
    encoded = base64.b64encode(secret).decode("ascii")
    return f"Basic {encoded}"


def _display_name(payload: Mapping[str, object]) -> str | None:
    for key in ("displayName", "name", "accountId"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _permissions(payload: Mapping[str, object]) -> list[str]:
    raw_permissions = payload.get("permissions")
    if not isinstance(raw_permissions, Mapping):
        return []

    permissions = [str(name) for name, value in raw_permissions.items() if _has_permission(value)]
    return sorted(permissions)


def _has_permission(value: object) -> bool:
    if isinstance(value, Mapping):
        candidate = value.get("havePermission")
        return isinstance(candidate, bool) and candidate
    return isinstance(value, bool) and value


def _payload_values(payload: Mapping[str, object]) -> list[Mapping[str, object]]:
    raw_values = payload.get("values")
    if not isinstance(raw_values, list):
        raise ConnectorDataError("Jira paginated response did not contain values")
    if not all(isinstance(value, Mapping) for value in raw_values):
        raise ConnectorDataError("Jira paginated response contained an invalid item")
    return cast(list[Mapping[str, object]], raw_values)


def _is_last_page(payload: Mapping[str, object], next_start_at: int) -> bool:
    is_last = payload.get("isLast")
    if isinstance(is_last, bool):
        return is_last

    total = payload.get("total")
    if isinstance(total, int):
        return next_start_at >= total

    return len(_payload_values(payload)) < PAGE_SIZE


def _project_from_payload(payload: Mapping[str, object], base_url: str) -> Project:
    external_id = _required_str(payload, "id", "project")
    key = _required_str(payload, "key", "project")
    return Project(
        **_common_fields(
            "project",
            external_id,
            source_url=f"{base_url}/browse/{key}",
            source_metadata=_metadata(payload, "self"),
        ),
        key=key,
        name=_required_str(payload, "name", "project"),
    )


def _board_from_payload(payload: Mapping[str, object], base_url: str, project_id: str) -> Board:
    external_id = _required_str(payload, "id", "board")
    location = payload.get("location")
    location_project_id = (
        _optional_str(location, "projectId") if isinstance(location, Mapping) else None
    )
    location_project_key = (
        _optional_str(location, "projectKey") if isinstance(location, Mapping) else None
    )
    canonical_project_external_id = location_project_id or project_id

    return Board(
        **_common_fields(
            "board",
            external_id,
            source_url=_board_url(base_url, external_id, location_project_key),
            source_metadata=_metadata(payload, "self", "location"),
        ),
        project_id=_stable_id("project", canonical_project_external_id),
        name=_required_str(payload, "name", "board"),
        type=_board_type(_optional_str(payload, "type")),
    )


def _sprint_from_payload(payload: Mapping[str, object], board_id: str) -> Sprint:
    external_id = _required_str(payload, "id", "sprint")
    return Sprint(
        **_common_fields(
            "sprint",
            external_id,
            source_url=_optional_str(payload, "self"),
            source_metadata=_metadata(payload, "originBoardId", "self"),
        ),
        board_id=_stable_id("board", board_id),
        name=_required_str(payload, "name", "sprint"),
        state=_sprint_state(_required_str(payload, "state", "sprint")),
        start_date=_parse_datetime(_optional_str(payload, "startDate")),
        end_date=_parse_datetime(_optional_str(payload, "endDate")),
        complete_date=_parse_datetime(_optional_str(payload, "completeDate")),
        goal=_optional_str(payload, "goal"),
    )


def _common_fields(
    kind: str,
    external_id: str,
    *,
    source_url: str | None,
    source_metadata: dict[str, object],
) -> dict[str, object]:
    return {
        "id": _stable_id(kind, external_id),
        "source": Source.JIRA,
        "external_id": external_id,
        "source_url": source_url,
        "source_metadata": source_metadata,
    }


def _stable_id(kind: str, external_id: str) -> UUID:
    return uuid5(_NAMESPACE, f"{kind}:{external_id}")


def _required_str(payload: Mapping[str, object], key: str, entity: str) -> str:
    value = payload.get(key)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str) and value:
        return value
    raise ConnectorDataError(f"Jira {entity} payload was missing {key}")


def _optional_str(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str) and value:
        return value
    return None


def _metadata(payload: Mapping[str, object], *keys: str) -> dict[str, object]:
    return {key: value for key in keys if (value := payload.get(key)) is not None}


def _board_type(value: str | None) -> BoardType:
    if value == "scrum":
        return BoardType.SCRUM
    if value == "kanban":
        return BoardType.KANBAN
    return BoardType.OTHER


def _sprint_state(value: str) -> SprintState:
    normalized = value.lower()
    if normalized == "future":
        return SprintState.FUTURE
    if normalized == "active":
        return SprintState.ACTIVE
    if normalized == "closed":
        return SprintState.CLOSED
    raise ConnectorDataError(f"Unsupported Jira sprint state: {value}")


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ConnectorDataError(f"Invalid Jira datetime: {value}") from error
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _board_url(base_url: str, board_id: str, project_key: str | None) -> str | None:
    if project_key is None:
        return None
    return f"{base_url}/jira/software/c/projects/{project_key}/boards/{board_id}"


def _error_for_status(
    status_code: int,
) -> (
    ConnectorAuthError
    | ConnectorNotFoundError
    | ConnectorRateLimitedError
    | ConnectorTransientError
    | ConnectorDataError
):
    if status_code in (401, 403):
        return ConnectorAuthError("Jira authentication failed")
    if status_code == 404:
        return ConnectorNotFoundError("Jira endpoint was not found")
    if status_code == 429:
        return ConnectorRateLimitedError("Jira rate limit exceeded")
    if status_code >= 500:
        return ConnectorTransientError(f"Jira server error ({status_code})")
    return ConnectorDataError(f"Jira request failed with status {status_code}")
