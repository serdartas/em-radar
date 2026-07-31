from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import ClassVar, cast

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
    FieldAvailability,
    SignalCapabilitySchema,
    SignalField,
    ValueProvider,
)
from em_radar_core.http_client import create_redacting_async_client
from em_radar_core.models import Repository, Source

CLIENT_FACTORY: Callable[..., httpx.AsyncClient] = httpx.AsyncClient
PAGE_SIZE = 100


class GitLabConnectorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: HttpUrl
    token: SecretStr
    verify_tls: bool = True


class GitLabConnector:
    name: ClassVar[str] = "gitlab"
    display_name: ClassVar[str] = "GitLab"
    config_schema: ClassVar[dict[str, object]] = GitLabConnectorConfig.model_json_schema()
    min_model_version: ClassVar[int] = 1

    def __init__(self, config: dict[str, object]) -> None:
        try:
            self.config = GitLabConnectorConfig.model_validate(config)
        except ValidationError as error:
            raise ConnectorConfigError("Invalid GitLab connector config") from error

        token = self.config.token.get_secret_value()
        self._client = create_redacting_async_client(
            client_factory=CLIENT_FACTORY,
            sensitive_values=(token,),
            base_url=_base_url(self.config.base_url),
            headers={"PRIVATE-TOKEN": token},
            verify=self.config.verify_tls,
        )

    async def test_connection(self) -> ConnectionTestResult:
        user_payload = await self._request_json("api/v4/user")
        token_payload = await self._request_json("api/v4/personal_access_tokens/self")
        return ConnectionTestResult(
            ok=True,
            detail="Connected to GitLab",
            user_display_name=_display_name(user_payload),
            permissions=_permissions(token_payload),
        )

    @classmethod
    def describe_capabilities(cls) -> Capabilities:
        del cls
        return Capabilities(
            provides_mergerequests=True,
            provides_repositories=True,
            provides_reviews=True,
            supports_incremental_fetch=True,
        )

    @classmethod
    def describe_signal_schema(cls) -> SignalCapabilitySchema:
        del cls
        branch_provider = ValueProvider(type="dynamic", source="gitlab_branches")
        reviews_required = FieldAvailability(requires_scope_capability=("reviews",))
        pipelines_required = FieldAvailability(requires_scope_capability=("pipelines",))
        return SignalCapabilitySchema(
            connector_type="gitlab",
            entity_types=("merge_request",),
            scope_types=(),
            fields=(
                SignalField(
                    "state",
                    "State",
                    "enum",
                    ("is", "is_not", "is_any_of", "is_none_of"),
                    values=("open", "draft", "merged", "closed"),
                ),
                SignalField(
                    "is_draft",
                    "Draft",
                    "boolean",
                    ("is", "is_not"),
                    values=(True, False),
                ),
                SignalField("title", "Title", "text", ("contains", "does_not_contain")),
                SignalField(
                    "target_branch",
                    "Target branch",
                    "enum",
                    ("is", "is_not", "is_any_of", "is_none_of"),
                    value_provider=branch_provider,
                ),
                SignalField(
                    "source_branch",
                    "Source branch",
                    "enum",
                    ("is", "is_not", "is_any_of", "is_none_of"),
                    value_provider=branch_provider,
                ),
                SignalField(
                    "changed_files_count",
                    "Changed files",
                    "number",
                    ("greater_than", "less_than", "between"),
                ),
                SignalField(
                    "additions",
                    "Lines added",
                    "number",
                    ("greater_than", "less_than", "between"),
                ),
                SignalField(
                    "deletions",
                    "Lines deleted",
                    "number",
                    ("greater_than", "less_than", "between"),
                ),
                SignalField(
                    "total_changes",
                    "Total line changes",
                    "number",
                    ("greater_than", "less_than", "between"),
                ),
                SignalField(
                    "pipeline_status",
                    "Pipeline status",
                    "enum",
                    ("is", "is_not", "is_any_of", "is_none_of"),
                    values=("success", "failed", "running", "canceled", "skipped", "none"),
                    availability=pipelines_required,
                ),
                SignalField(
                    "age_since_pipeline_update",
                    "Age since pipeline update",
                    "duration",
                    ("greater_than", "less_than", "between"),
                    availability=pipelines_required,
                ),
                SignalField(
                    "approval_count",
                    "Approval count",
                    "number",
                    ("is", "greater_than", "less_than", "between"),
                    availability=reviews_required,
                ),
                SignalField(
                    "age_since_last_review_activity",
                    "Age since last review activity",
                    "duration",
                    ("greater_than", "less_than", "between"),
                    availability=reviews_required,
                ),
                SignalField(
                    "linked_workitem_keys",
                    "Linked work item keys",
                    "string_list",
                    (
                        "is_empty",
                        "is_not_empty",
                        "contains",
                        "does_not_contain",
                        "contains_any",
                        "does_not_contain_any",
                    ),
                ),
                SignalField("created_at", "Created date", "date", ("before", "after", "between")),
                SignalField("updated_at", "Updated date", "date", ("before", "after", "between")),
                SignalField("merged_at", "Merged date", "date", ("before", "after", "between")),
                SignalField("closed_at", "Closed date", "date", ("before", "after", "between")),
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
            ),
        )

    async def list_repositories(self) -> list[Repository]:
        repositories: list[Repository] = []
        page = 1
        while True:
            payloads, next_page = await self._request_json_list_page(
                "api/v4/projects",
                params={
                    "page": page,
                    "per_page": PAGE_SIZE,
                    "order_by": "id",
                    "sort": "asc",
                },
            )
            repositories.extend(_repository_from_payload(payload) for payload in payloads)
            if next_page is None:
                return repositories
            if next_page <= page:
                raise ConnectorDataError("GitLab project pagination did not advance")
            page = next_page

    async def close(self) -> None:
        await self._client.aclose()

    async def _request_json(self, path: str) -> dict[str, object]:
        try:
            response = await self._client.get(path)
        except httpx.RequestError as error:
            raise ConnectorTransientError("Failed to reach GitLab") from error

        if response.status_code >= 400:
            raise _error_for_status(response.status_code)

        try:
            payload = response.json()
        except ValueError as error:
            raise ConnectorDataError("GitLab returned invalid JSON") from error

        if not isinstance(payload, dict):
            raise ConnectorDataError("GitLab returned an unexpected payload shape")
        return cast(dict[str, object], payload)

    async def _request_json_list_page(
        self,
        path: str,
        *,
        params: Mapping[str, object],
    ) -> tuple[list[Mapping[str, object]], int | None]:
        try:
            response = await self._client.get(path, params=params)
        except httpx.RequestError as error:
            raise ConnectorTransientError("Failed to reach GitLab") from error

        if response.status_code >= 400:
            raise _error_for_status(response.status_code)

        try:
            payload = response.json()
        except ValueError as error:
            raise ConnectorDataError("GitLab returned invalid JSON") from error

        if not isinstance(payload, list) or not all(isinstance(item, Mapping) for item in payload):
            raise ConnectorDataError("GitLab returned an unexpected payload shape")

        next_page_header = response.headers.get("X-Next-Page")
        if next_page_header is None:
            current_page = _required_positive_int(params, "page")
            next_page = current_page + 1 if len(payload) == PAGE_SIZE else None
        elif not next_page_header:
            next_page = None
        else:
            try:
                next_page = int(next_page_header)
            except ValueError as error:
                raise ConnectorDataError("GitLab returned an invalid next page") from error
            if next_page < 1:
                raise ConnectorDataError("GitLab returned an invalid next page")

        return cast(list[Mapping[str, object]], payload), next_page


def _display_name(payload: Mapping[str, object]) -> str | None:
    for key in ("name", "username"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _base_url(base_url: HttpUrl) -> str:
    return f"{str(base_url).rstrip('/')}/"


def _permissions(payload: Mapping[str, object]) -> list[str]:
    permissions = _string_values(payload.get("scopes"))
    granular_scopes = payload.get("granular_scopes")
    if isinstance(granular_scopes, Sequence) and not isinstance(granular_scopes, (str, bytes)):
        for granular_scope in granular_scopes:
            if isinstance(granular_scope, Mapping):
                permissions.extend(_string_values(granular_scope.get("permissions")))
    return sorted(set(permissions))


def _string_values(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [item for item in value if isinstance(item, str)]


def _repository_from_payload(payload: Mapping[str, object]) -> Repository:
    default_branch = payload.get("default_branch")
    if default_branch is None:
        default_branch = ""
    if not isinstance(default_branch, str):
        raise ConnectorDataError("GitLab project contained an invalid default_branch")

    return Repository(
        source=Source.GITLAB,
        external_id=str(_required_positive_int(payload, "id")),
        source_url=_optional_str(payload, "web_url"),
        name=_required_str(payload, "name"),
        full_path=_required_str(payload, "path_with_namespace"),
        default_branch=default_branch,
        is_archived=_required_bool(payload, "archived"),
    )


def _required_positive_int(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ConnectorDataError(f"GitLab payload contained an invalid {key}")
    return value


def _required_str(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ConnectorDataError(f"GitLab payload contained an invalid {key}")
    return value


def _optional_str(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConnectorDataError(f"GitLab payload contained an invalid {key}")
    return value


def _required_bool(payload: Mapping[str, object], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise ConnectorDataError(f"GitLab payload contained an invalid {key}")
    return value


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
        return ConnectorAuthError("GitLab authentication failed")
    if status_code == 404:
        return ConnectorNotFoundError("GitLab endpoint was not found")
    if status_code == 429:
        return ConnectorRateLimitedError("GitLab rate limit exceeded")
    if status_code >= 500:
        return ConnectorTransientError(f"GitLab server error ({status_code})")
    return ConnectorDataError(f"GitLab request failed with status {status_code}")
