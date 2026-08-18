# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import base64
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from datetime import datetime, timedelta, timezone
from typing import ClassVar, Literal, cast
from uuid import UUID, uuid5

import httpx
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, SecretStr, ValidationError

from em_radar_core.connectors import (
    Capabilities,
    ConnectionTestResult,
    ConnectorAuthError,
    ConnectorConfigError,
    ConnectorDataError,
    ConnectorNotFoundError,
    ConnectorRateLimitedError,
    ConnectorTransientError,
    FieldAvailability,
    SignalCapabilitySchema,
    SignalField,
    SignalScopeType,
    ValueProvider,
    WorkItemScope,
)
from em_radar_core.http_client import create_redacting_async_client
from em_radar_core.models import (
    Board,
    BoardType,
    EntityType,
    EvaluationWindow,
    Project,
    Source,
    Sprint,
    SprintState,
    StatusCategory,
    Transition,
    WindowType,
    WorkItem,
    WorkItemType,
)

CLIENT_FACTORY: Callable[..., httpx.AsyncClient] = httpx.AsyncClient
PAGE_SIZE = 50
_NAMESPACE = UUID("1b6514a2-8027-43f2-a820-c771c419ca33")
_STORY_POINTS_FIELD = "customfield_10016"
_SPRINT_FIELD = "customfield_10020"
_ACCEPTANCE_CRITERIA_HEADING = "### Acceptance Criteria"
_BLOCKED_LABEL = "blocked"
_BLOCKED_STATUS = "Blocked"
# Jira requires an explicit permission key list on GET /mypermissions (400 otherwise).
_PERMISSION_KEYS = ("BROWSE_PROJECTS",)
_SYSTEM_ISSUE_FIELDS = (
    "summary",
    "description",
    "issuetype",
    "status",
    "assignee",
    "reporter",
    "project",
    "parent",
    "labels",
    "components",
    "created",
    "updated",
    "resolutiondate",
    "duedate",
    _SPRINT_FIELD,
)


class JiraFieldMappingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    story_points: str = _STORY_POINTS_FIELD
    acceptance_criteria: str | None = None
    acceptance_criteria_heading: str | None = _ACCEPTANCE_CRITERIA_HEADING
    blocked_label: str | None = _BLOCKED_LABEL
    blocked_status: str | None = _BLOCKED_STATUS


class JiraConnectorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: HttpUrl
    token: SecretStr
    auth_email: str | None = None
    verify_tls: bool = True
    field_mapping: JiraFieldMappingConfig = Field(default_factory=JiraFieldMappingConfig)


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

        token = self.config.token.get_secret_value()
        auth_header = _authorization_header(self.config)
        self._client = create_redacting_async_client(
            client_factory=CLIENT_FACTORY,
            sensitive_values=(token, auth_header),
            base_url=str(self.config.base_url),
            headers={"Authorization": auth_header},
            verify=self.config.verify_tls,
        )

    async def test_connection(self) -> ConnectionTestResult:
        user_payload = await self._request_json("rest/api/2/myself")
        permissions_payload = await self._request_json(
            "rest/api/2/mypermissions",
            params={"permissions": ",".join(_PERMISSION_KEYS)},
        )
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
            provides_workitems=True,
            provides_sprints=True,
            provides_transitions=True,
            supports_incremental_fetch=True,
        )

    @classmethod
    def describe_signal_schema(cls) -> SignalCapabilitySchema:
        del cls
        status_provider = ValueProvider(
            type="dynamic",
            source="jira_statuses",
            depends_on=("scope",),
        )
        labels_provider = ValueProvider(
            type="dynamic",
            source="jira_labels",
            depends_on=("scope",),
        )
        sprint_only = FieldAvailability(requires_scope_capability=("sprint",))
        return SignalCapabilitySchema(
            connector_type="jira",
            entity_types=("issue", "sprint"),
            scope_types=(
                SignalScopeType("project", "Project", ("statuses", "labels")),
                SignalScopeType("board", "Board", ("statuses", "labels", "sprint", "kanban")),
                SignalScopeType("saved_filter", "Saved Filter", ("statuses", "labels")),
            ),
            fields=(
                SignalField(
                    "status",
                    "Status",
                    "enum",
                    ("is", "is_not", "is_any_of", "is_none_of"),
                    value_provider=status_provider,
                ),
                SignalField(
                    "status_category",
                    "Status Category",
                    "enum",
                    ("is", "is_not", "is_any_of", "is_none_of"),
                    values=("todo", "in_progress", "done", "blocked"),
                ),
                SignalField(
                    "labels",
                    "Labels",
                    "string_list",
                    ("contains", "does_not_contain", "contains_any", "does_not_contain_any"),
                    value_provider=labels_provider,
                ),
                SignalField(
                    "exclude_labels",
                    "Exclude Labels",
                    "string_list",
                    ("does_not_contain", "does_not_contain_any"),
                    value_provider=labels_provider,
                ),
                SignalField(
                    "workitem_types",
                    "Workitem Types",
                    "enum",
                    ("is", "is_not"),
                    values=("epic", "story", "task", "bug", "subtask", "spike", "other"),
                ),
                SignalField("issue_type", "Issue Type", "enum", ("is", "is_not", "is_any_of")),
                SignalField("assignee", "Assignee", "nullable", ("is_empty", "is_not_empty")),
                SignalField(
                    "acceptance_criteria",
                    "Acceptance Criteria",
                    "text",
                    ("is_empty", "is_not_empty"),
                ),
                SignalField("parent_id", "Parent", "nullable", ("is_empty", "is_not_empty")),
                SignalField(
                    "has_epic_parent",
                    "Has Epic Parent",
                    "boolean",
                    ("is",),
                ),
                SignalField(
                    "description_length",
                    "Description Length",
                    "number",
                    ("greater_than", "less_than", "between"),
                ),
                SignalField(
                    "child_count",
                    "Child Count",
                    "number",
                    ("greater_than", "less_than", "between"),
                ),
                SignalField("created_at", "Created date", "date", ("before", "after", "between")),
                SignalField("updated_at", "Updated date", "date", ("before", "after", "between")),
                SignalField("resolved_at", "Resolved date", "date", ("before", "after", "between")),
                SignalField(
                    "age_since_created",
                    "Age since created",
                    "duration",
                    ("greater_than", "less_than", "between"),
                ),
                SignalField(
                    "age_since_updated",
                    "Age since updated",
                    "duration",
                    ("greater_than", "less_than", "between"),
                ),
                SignalField(
                    "age_in_current_status",
                    "Age in current status",
                    "duration",
                    ("greater_than", "less_than", "between"),
                ),
                SignalField(
                    "sprint_day",
                    "Sprint day",
                    "sprint_relative_day",
                    ("is", "is_before", "is_after", "between"),
                    availability=sprint_only,
                ),
                SignalField(
                    "sprint_phase",
                    "Sprint phase",
                    "enum",
                    ("is", "is_not"),
                    values=("first_day", "middle", "last_day"),
                    availability=sprint_only,
                ),
                SignalField(
                    "sprint_count",
                    "Sprint Count",
                    "number",
                    ("greater_than", "less_than", "between"),
                    availability=sprint_only,
                ),
                SignalField(
                    "sprint_scope_added_pct",
                    "Sprint scope added %",
                    "number",
                    ("greater_than", "less_than", "between"),
                    availability=sprint_only,
                    entity_type="sprint",
                ),
            ),
        )

    async def list_projects(self) -> list[Project]:
        payloads = await self._request_json_list("rest/api/2/project")
        return [_project_from_payload(payload, self._base_url) for payload in payloads]

    async def list_boards(self, project_id: str) -> list[Board]:
        payloads = await self._request_paginated_values(
            "rest/agile/1.0/board",
            params={"projectKeyOrId": project_id},
        )
        return [_board_from_payload(payload, self._base_url, project_id) for payload in payloads]

    async def list_sprints(self, board_id: str) -> list[Sprint]:
        payloads = await self._request_paginated_values(f"rest/agile/1.0/board/{board_id}/sprint")
        return [_sprint_from_payload(payload, board_id) for payload in payloads]

    async def fetch_workitems(
        self,
        scope: WorkItemScope,
        window: EvaluationWindow,
    ) -> AsyncIterator[WorkItem]:
        async for payload in self._request_paginated_issues(
            params={
                "jql": _workitem_jql(scope, window),
                "fields": ",".join(_issue_fields(self.config.field_mapping)),
            }
        ):
            workitem = _workitem_from_payload(payload, self._base_url, self.config.field_mapping)
            if _workitem_in_window(workitem, window):
                yield workitem

    async def fetch_transitions(
        self,
        entity_type: Literal["workitem", "mergerequest"],
        entity_external_ids: list[str],
    ) -> AsyncIterator[Transition]:
        if entity_type != EntityType.WORKITEM:
            raise ConnectorDataError("Jira transitions only support workitems")

        status_categories = await self._status_categories()
        for external_id in entity_external_ids:
            issue_payload = await self._request_json(
                f"rest/api/2/issue/{external_id}",
                params={"fields": "key", "expand": "changelog"},
            )
            issue_key = _required_str(issue_payload, "key", "issue")
            histories = await self._changelog_histories(external_id, issue_payload)
            for transition in _transitions_from_changelog(issue_key, histories, status_categories):
                yield transition

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

    async def _request_json_list(self, path: str) -> list[Mapping[str, object]]:
        try:
            response = await self._client.get(path)
        except httpx.RequestError as error:
            raise ConnectorTransientError("Failed to reach Jira") from error

        if response.status_code >= 400:
            raise _error_for_status(response.status_code)

        try:
            payload = response.json()
        except ValueError as error:
            raise ConnectorDataError("Jira returned invalid JSON") from error

        if not isinstance(payload, list) or not all(
            isinstance(value, Mapping) for value in payload
        ):
            raise ConnectorDataError("Jira returned an unexpected payload shape")
        return cast(list[Mapping[str, object]], payload)

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

    async def _request_paginated_issues(
        self,
        *,
        params: Mapping[str, object],
    ) -> AsyncIterator[Mapping[str, object]]:
        sent_token: str | None = None
        while True:
            page_params: dict[str, object] = {"maxResults": PAGE_SIZE, **dict(params)}
            if sent_token is not None:
                page_params["nextPageToken"] = sent_token
            try:
                payload = await self._request_json("rest/api/2/search/jql", params=page_params)
            except ConnectorNotFoundError:
                if sent_token is not None:
                    # Pagination has already advanced past page 1; a mid-stream 404 must not
                    # restart from startAt=0 and re-yield already-emitted issues.
                    raise
                # Jira Data Center/Server has no enhanced search endpoint; use classic pagination.
                async for issue in self._request_paginated_issues_legacy(params=params):
                    yield issue
                return

            for issue in _payload_issues(payload):
                yield issue

            received_token = _next_page_token(payload)
            if received_token is None:
                return
            if received_token == sent_token:
                raise ConnectorDataError("Jira issue pagination did not advance")
            sent_token = received_token

    async def _request_paginated_issues_legacy(
        self,
        *,
        params: Mapping[str, object],
    ) -> AsyncIterator[Mapping[str, object]]:
        start_at = 0
        while True:
            page_params = {
                "startAt": start_at,
                "maxResults": PAGE_SIZE,
                **dict(params),
            }
            payload = await self._request_json("rest/api/2/search", params=page_params)
            page_values = _payload_issues(payload)
            for issue in page_values:
                yield issue

            next_start_at = start_at + len(page_values)
            if _is_last_issue_page(payload, next_start_at):
                return
            if next_start_at == start_at:
                raise ConnectorDataError("Jira issue pagination did not advance")
            start_at = next_start_at

    async def _request_paginated_changelog(
        self,
        issue_external_id: str,
    ) -> list[Mapping[str, object]]:
        histories: list[Mapping[str, object]] = []
        start_at = 0
        while True:
            payload = await self._request_json(
                f"rest/api/2/issue/{issue_external_id}/changelog",
                params={"startAt": start_at, "maxResults": PAGE_SIZE},
            )
            page_values = _payload_histories(payload)
            histories.extend(page_values)

            next_start_at = start_at + len(page_values)
            if _is_last_changelog_page(payload, next_start_at):
                return histories
            if next_start_at == start_at:
                raise ConnectorDataError("Jira changelog pagination did not advance")
            start_at = next_start_at

    async def _changelog_histories(
        self,
        issue_external_id: str,
        issue_payload: Mapping[str, object],
    ) -> list[Mapping[str, object]]:
        try:
            return await self._request_paginated_changelog(issue_external_id)
        except ConnectorNotFoundError:
            changelog = _optional_mapping(issue_payload.get("changelog"))
            if changelog is None:
                raise
            return _payload_histories(changelog)

    @property
    def _base_url(self) -> str:
        return str(self.config.base_url).rstrip("/")

    async def _status_categories(self) -> dict[str, StatusCategory]:
        payloads = await self._request_json_list("rest/api/2/status")
        categories: dict[str, StatusCategory] = {}
        for payload in payloads:
            category = _status_category(payload, [], self.config.field_mapping)
            status_id = _optional_str(payload, "id")
            name = _optional_str(payload, "name")
            if status_id is not None:
                categories[status_id] = category
            if name is not None:
                categories[_status_key(name)] = category
        return categories


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


def _payload_histories(payload: Mapping[str, object]) -> list[Mapping[str, object]]:
    raw_values = payload.get("values")
    if raw_values is None:
        raw_values = payload.get("histories")
    if not isinstance(raw_values, list):
        raise ConnectorDataError("Jira changelog response did not contain values")
    if not all(isinstance(value, Mapping) for value in raw_values):
        raise ConnectorDataError("Jira changelog response contained an invalid history")
    return cast(list[Mapping[str, object]], raw_values)


def _payload_issues(payload: Mapping[str, object]) -> list[Mapping[str, object]]:
    raw_issues = payload.get("issues")
    if not isinstance(raw_issues, list):
        raise ConnectorDataError("Jira search response did not contain issues")
    if not all(isinstance(issue, Mapping) for issue in raw_issues):
        raise ConnectorDataError("Jira search response contained an invalid issue")
    return cast(list[Mapping[str, object]], raw_issues)


def _next_page_token(payload: Mapping[str, object]) -> str | None:
    token = payload.get("nextPageToken")
    if token is None:
        return None
    if isinstance(token, str) and token:
        return token
    raise ConnectorDataError("Jira search response contained an invalid nextPageToken")


def _is_last_page(payload: Mapping[str, object], next_start_at: int) -> bool:
    is_last = payload.get("isLast")
    if isinstance(is_last, bool):
        return is_last

    total = payload.get("total")
    if isinstance(total, int):
        return next_start_at >= total

    return len(_payload_values(payload)) < PAGE_SIZE


def _is_last_issue_page(payload: Mapping[str, object], next_start_at: int) -> bool:
    total = payload.get("total")
    if isinstance(total, int):
        return next_start_at >= total

    max_results = payload.get("maxResults")
    if isinstance(max_results, int):
        return len(_payload_issues(payload)) < max_results

    return len(_payload_issues(payload)) < PAGE_SIZE


def _is_last_changelog_page(payload: Mapping[str, object], next_start_at: int) -> bool:
    total = payload.get("total")
    if isinstance(total, int):
        return next_start_at >= total

    max_results = payload.get("maxResults")
    if isinstance(max_results, int):
        return len(_payload_histories(payload)) < max_results

    return len(_payload_histories(payload)) < PAGE_SIZE


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


def _workitem_from_payload(
    payload: Mapping[str, object],
    base_url: str,
    field_mapping: JiraFieldMappingConfig,
) -> WorkItem:
    external_id = _required_str(payload, "id", "issue")
    key = _required_str(payload, "key", "issue")
    fields = _required_mapping(payload, "fields", "issue")
    status = _required_mapping(fields, "status", "issue")
    labels = _string_list(fields.get("labels"), "labels")
    status_category = _status_category(status, labels, field_mapping)
    sprints = _sprints_from_field(fields.get(_SPRINT_FIELD))

    return WorkItem(
        **_workitem_common_fields(
            external_id,
            key,
            source_url=f"{base_url}/browse/{key}",
            source_metadata=_metadata(payload, "self"),
        ),
        project_id=_stable_id("project", _project_external_id(fields)),
        key=key,
        type=_workitem_type(_required_mapping(fields, "issuetype", "issue")),
        title=_required_str(fields, "summary", "issue"),
        description=_optional_str(fields, "description"),
        status=_required_str(status, "name", "issue status"),
        status_category=status_category,
        assignee_id=_user_id(fields.get("assignee")),
        reporter_id=_user_id(fields.get("reporter")),
        labels=labels,
        components=_components(fields.get("components")),
        parent_id=_parent_id(fields, field_mapping),
        story_points=_number_or_none(
            fields.get(field_mapping.story_points),
            field_mapping.story_points,
        ),
        acceptance_criteria=_acceptance_criteria(fields, field_mapping),
        is_blocked=status_category is StatusCategory.BLOCKED,
        resolved_at=_parse_datetime(_optional_str(fields, "resolutiondate"))
        if status_category is StatusCategory.DONE
        else None,
        due_date=_parse_datetime(_optional_str(fields, "duedate")),
        sprint_ids=[sprint_id for sprint_id, _ in sprints],
        current_sprint_id=_current_sprint_id(sprints),
        created_at=_parse_datetime(_optional_str(fields, "created")),
        updated_at=_parse_datetime(_optional_str(fields, "updated")),
    )


def _transitions_from_changelog(
    issue_key: str,
    histories: Sequence[Mapping[str, object]],
    status_categories: Mapping[str, StatusCategory],
) -> list[Transition]:
    transitions: list[Transition] = []
    for history in histories:
        occurred_at = _required_datetime(history, "created", "changelog history")
        actor_id = _user_id(history.get("author"))
        history_id = _required_str(history, "id", "changelog history")
        items = history.get("items")
        if not isinstance(items, list) or not all(isinstance(item, Mapping) for item in items):
            raise ConnectorDataError("Jira changelog history contained invalid items")

        for index, item in enumerate(cast(list[Mapping[str, object]], items)):
            if _optional_str(item, "field") != "status":
                continue
            to_status = _required_str(item, "toString", "status changelog item")
            transitions.append(
                Transition(
                    id=_stable_id("transition", f"{issue_key}:{history_id}:{index}"),
                    entity_type=EntityType.WORKITEM,
                    entity_id=_stable_id("workitem", issue_key),
                    from_status=_optional_str(item, "fromString"),
                    to_status=to_status,
                    from_status_category=_status_category_for_changelog_value(
                        item,
                        "from",
                        "fromString",
                        status_categories,
                    ),
                    to_status_category=_required_status_category_for_changelog_value(
                        item,
                        "to",
                        "toString",
                        status_categories,
                    ),
                    actor_id=actor_id,
                    occurred_at=occurred_at,
                )
            )

    return sorted(transitions, key=lambda transition: transition.occurred_at)


def _workitem_common_fields(
    external_id: str,
    key: str,
    *,
    source_url: str | None,
    source_metadata: dict[str, object],
) -> dict[str, object]:
    fields = _common_fields(
        "workitem",
        external_id,
        source_url=source_url,
        source_metadata=source_metadata,
    )
    fields["id"] = _stable_id("workitem", key)
    return fields


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


def _required_mapping(payload: Mapping[str, object], key: str, entity: str) -> Mapping[str, object]:
    value = payload.get(key)
    if isinstance(value, Mapping):
        return value
    raise ConnectorDataError(f"Jira {entity} payload was missing {key}")


def _optional_str(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str) and value:
        return value
    return None


def _optional_mapping(value: object) -> Mapping[str, object] | None:
    return value if isinstance(value, Mapping) else None


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


def _workitem_type(payload: Mapping[str, object]) -> WorkItemType:
    name = _required_str(payload, "name", "issue type").strip().lower().replace("_", " ")
    if name == "epic":
        return WorkItemType.EPIC
    if name in {"story", "user story"}:
        return WorkItemType.STORY
    if name == "bug":
        return WorkItemType.BUG
    if name in {"sub-task", "subtask"}:
        return WorkItemType.SUBTASK
    if name == "spike":
        return WorkItemType.SPIKE
    if name == "task":
        return WorkItemType.TASK
    return WorkItemType.OTHER


def _status_category(
    status: Mapping[str, object],
    labels: Sequence[str],
    field_mapping: JiraFieldMappingConfig | None = None,
) -> StatusCategory:
    name = _required_str(status, "name", "issue status")
    if _is_blocked(name, labels, field_mapping or JiraFieldMappingConfig()):
        return StatusCategory.BLOCKED

    status_category = _required_mapping(status, "statusCategory", "issue status")
    key = _optional_str(status_category, "key")
    category_id = _optional_str(status_category, "id")
    category_name = _optional_str(status_category, "name")
    normalized = (key or category_id or category_name or "").strip().lower().replace(" ", "_")
    if normalized in {"new", "to_do", "todo", "2"}:
        return StatusCategory.TODO
    if normalized in {"indeterminate", "in_progress", "4"}:
        return StatusCategory.IN_PROGRESS
    if normalized in {"done", "3"}:
        return StatusCategory.DONE
    # Jira's built-in "No Category" (key="undefined", id=1) and any other unrecognised
    # category default to TODO rather than aborting the page fetch.
    return StatusCategory.TODO


def _status_key(value: str) -> str:
    return value.strip().lower()


def _status_category_for_changelog_value(
    item: Mapping[str, object],
    status_id_key: str,
    status_name_key: str,
    status_categories: Mapping[str, StatusCategory],
) -> StatusCategory | None:
    status_id = _optional_str(item, status_id_key)
    if status_id is not None and status_id in status_categories:
        return status_categories[status_id]

    status_name = _optional_str(item, status_name_key)
    if status_name is not None:
        status_key = _status_key(status_name)
        if status_key in status_categories:
            return status_categories[status_key]

    return None


def _required_status_category_for_changelog_value(
    item: Mapping[str, object],
    status_id_key: str,
    status_name_key: str,
    status_categories: Mapping[str, StatusCategory],
) -> StatusCategory:
    category = _status_category_for_changelog_value(
        item,
        status_id_key,
        status_name_key,
        status_categories,
    )
    if category is None:
        status_value = _optional_str(item, status_id_key) or _optional_str(item, status_name_key)
        raise ConnectorDataError(f"Unknown Jira status in changelog: {status_value or '<missing>'}")
    return category


def _is_blocked(
    status_name: str,
    labels: Sequence[str],
    field_mapping: JiraFieldMappingConfig,
) -> bool:
    blocked_status = field_mapping.blocked_status
    if blocked_status is not None and _normalized_text(status_name) == _normalized_text(
        blocked_status
    ):
        return True

    blocked_label = field_mapping.blocked_label
    return blocked_label is not None and any(
        _normalized_text(label) == _normalized_text(blocked_label) for label in labels
    )


def _normalized_text(value: str) -> str:
    return value.strip().casefold()


def _project_external_id(fields: Mapping[str, object]) -> str:
    project = _required_mapping(fields, "project", "issue")
    return _required_str(project, "id", "issue project")


def _user_id(value: object) -> UUID | None:
    user = _optional_mapping(value)
    if user is None:
        return None
    account_id = (
        _optional_str(user, "accountId")
        or _optional_str(user, "key")
        or _optional_str(user, "name")
    )
    return _stable_id("user", account_id) if account_id is not None else None


def _parent_id(fields: Mapping[str, object], field_mapping: JiraFieldMappingConfig) -> UUID | None:
    parent = _optional_mapping(fields.get("parent"))
    if parent is not None:
        parent_reference = _optional_str(parent, "key") or _required_str(
            parent, "id", "issue parent"
        )
        return _stable_id("workitem", parent_reference)
    return None


def _acceptance_criteria(
    fields: Mapping[str, object],
    field_mapping: JiraFieldMappingConfig,
) -> str | None:
    custom_field = field_mapping.acceptance_criteria
    if custom_field is not None:
        custom_value = fields.get(custom_field)
        if isinstance(custom_value, str):
            stripped = custom_value.strip()
            return stripped or None
        if custom_value is not None:
            raise ConnectorDataError(f"Jira issue {custom_field} field was invalid")

    heading = field_mapping.acceptance_criteria_heading
    description = _optional_str(fields, "description")
    if heading is None or description is None:
        return None
    return _section_after_heading(description, heading)


def _issue_fields(field_mapping: JiraFieldMappingConfig) -> tuple[str, ...]:
    configurable_fields = [
        field_mapping.story_points,
        field_mapping.acceptance_criteria,
    ]
    fields = [*_SYSTEM_ISSUE_FIELDS]
    for field_name in configurable_fields:
        if field_name is not None and field_name not in fields:
            fields.append(field_name)
    return tuple(fields)


def _section_after_heading(value: str, heading: str) -> str | None:
    lines = value.splitlines()
    heading_marker = heading.strip()
    heading_level = _markdown_heading_level(heading_marker)
    if heading_level is None:
        return None

    body: list[str] = []
    found = False
    for line in lines:
        if not found:
            found = line.strip().casefold() == heading_marker.casefold()
            continue

        line_heading_level = _markdown_heading_level(line.strip())
        if line_heading_level is not None and line_heading_level <= heading_level:
            break
        body.append(line)

    criteria = "\n".join(body).strip()
    return criteria or None


def _markdown_heading_level(value: str) -> int | None:
    hashes, _, title = value.partition(" ")
    if not hashes or set(hashes) != {"#"} or not title:
        return None
    return len(hashes)


def _components(value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ConnectorDataError("Jira issue components field was invalid")

    components: list[str] = []
    for item in value:
        component = _optional_mapping(item)
        if component is None:
            raise ConnectorDataError("Jira issue component was invalid")
        name = _optional_str(component, "name")
        if name is not None:
            components.append(name)
    return components


def _string_list(value: object, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConnectorDataError(f"Jira issue {field_name} field was invalid")
    return list(value)


def _number_or_none(value: object, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    raise ConnectorDataError(f"Jira issue {field_name} field was invalid")


def _sprints_from_field(value: object) -> list[tuple[UUID, SprintState | None]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ConnectorDataError("Jira issue sprint field was invalid")

    sprints: list[tuple[UUID, SprintState | None]] = []
    for item in value:
        sprint_id, state = _sprint_reference(item)
        if sprint_id not in {existing_id for existing_id, _ in sprints}:
            sprints.append((sprint_id, state))
    return sprints


def _sprint_reference(value: object) -> tuple[UUID, SprintState | None]:
    if isinstance(value, Mapping):
        external_id = _required_str(value, "id", "issue sprint")
        state = (
            _sprint_state(_required_str(value, "state", "issue sprint"))
            if "state" in value
            else None
        )
        return _stable_id("sprint", external_id), state
    if isinstance(value, str):
        attributes = _legacy_sprint_attributes(value)
        external_id = attributes.get("id")
        if external_id is None:
            raise ConnectorDataError("Jira legacy sprint value was missing id")
        state = _sprint_state(attributes["state"]) if "state" in attributes else None
        return _stable_id("sprint", external_id), state
    raise ConnectorDataError("Jira issue sprint field contained an invalid item")


def _legacy_sprint_attributes(value: str) -> dict[str, str]:
    _, _, body = value.partition("[")
    body = body.rstrip("]")
    attributes: dict[str, str] = {}
    for part in body.split(","):
        key, separator, raw_value = part.partition("=")
        if separator and raw_value:
            attributes[key.strip()] = raw_value.strip()
    return attributes


def _current_sprint_id(sprints: Sequence[tuple[UUID, SprintState | None]]) -> UUID | None:
    for sprint_id, state in sprints:
        if state is SprintState.ACTIVE:
            return sprint_id
    return None


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


def _required_datetime(payload: Mapping[str, object], key: str, entity: str) -> datetime:
    parsed = _parse_datetime(_required_str(payload, key, entity))
    if parsed is None:
        raise ConnectorDataError(f"Jira {entity} payload was missing {key}")
    return parsed


def _board_url(base_url: str, board_id: str, project_key: str | None) -> str | None:
    if project_key is None:
        return None
    return f"{base_url}/jira/software/c/projects/{project_key}/boards/{board_id}"


def _workitem_jql(scope: WorkItemScope, window: EvaluationWindow) -> str:
    clauses: list[str] = []
    if scope.project_external_ids:
        clauses.append(f"project in ({_jql_list(scope.project_external_ids)})")
    if scope.workitem_types:
        clauses.append(f"issuetype in ({_jql_list(_jira_issue_type_names(scope.workitem_types))})")
    if window.window_type is WindowType.DATE_RANGE:
        if window.end is None:
            raise ConnectorDataError("Date-range window was missing end")
        clauses.append(f'updated < "{_jql_datetime(_ceil_to_minute(window.end))}"')
    return " AND ".join(clauses) if clauses else "ORDER BY updated ASC"


def _workitem_in_window(workitem: WorkItem, window: EvaluationWindow) -> bool:
    if window.window_type is WindowType.SPRINT:
        if window.sprint_id is None:
            raise ConnectorDataError("Sprint window was missing sprint_id")
        return window.sprint_id in workitem.sprint_ids
    if window.window_type is WindowType.DATE_RANGE and window.end is not None:
        # Exact exclusive-end filter: the coarse JQL boundary is rounded up to the next
        # minute, so items in the final partial minute must be dropped here precisely.
        return workitem.updated_at is None or workitem.updated_at < window.end
    return True


def _jql_list(values: Sequence[str]) -> str:
    return ", ".join(f'"{value.replace(chr(34), chr(92) + chr(34))}"' for value in values)


def _jira_issue_type_names(types: Sequence[WorkItemType]) -> list[str]:
    names = {
        WorkItemType.EPIC: "Epic",
        WorkItemType.STORY: "Story",
        WorkItemType.TASK: "Task",
        WorkItemType.BUG: "Bug",
        WorkItemType.SUBTASK: "Sub-task",
        WorkItemType.SPIKE: "Spike",
        WorkItemType.OTHER: "Other",
    }
    return [names[item_type] for item_type in types]


def _ceil_to_minute(value: datetime) -> datetime:
    """Round a datetime UP to the next whole minute if it has sub-minute precision.

    This ensures a JQL `updated < "<minute>"` coarse boundary never drops candidates
    updated in the final partial minute of a window. For already-aligned datetimes
    (zero seconds and microseconds) the value is returned unchanged.
    """
    if value.second == 0 and value.microsecond == 0:
        return value
    floored = value.replace(second=0, microsecond=0)
    return floored + timedelta(minutes=1)


def _jql_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        normalized = value.replace(tzinfo=timezone.utc)
    else:
        normalized = value.astimezone(timezone.utc)
    return normalized.strftime("%Y-%m-%d %H:%M")


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
