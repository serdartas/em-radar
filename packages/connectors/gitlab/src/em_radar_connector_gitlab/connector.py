from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
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
    FieldAvailability,
    MergeRequestScope,
    SignalCapabilitySchema,
    SignalField,
    ValueProvider,
)
from em_radar_core.http_client import create_redacting_async_client
from em_radar_core.models import (
    EvaluationWindow,
    MergeRequest,
    MergeRequestState,
    PipelineStatus,
    Repository,
    Source,
    WindowType,
)

CLIENT_FACTORY: Callable[..., httpx.AsyncClient] = httpx.AsyncClient
PAGE_SIZE = 100
_NAMESPACE = UUID("c7d8a5f1-3b4e-4f2a-8c9d-1e0f7a6b5c3d")

# Issue 6: module-level constant so the dict is built once, not per MR.
_PIPELINE_STATUS_MAP: dict[str, PipelineStatus] = {
    "success": PipelineStatus.SUCCESS,
    "passed": PipelineStatus.SUCCESS,
    "failed": PipelineStatus.FAILED,
    "running": PipelineStatus.RUNNING,
    "canceled": PipelineStatus.CANCELED,
    "skipped": PipelineStatus.SKIPPED,
    # Intermediate / queued states map to running so signals read them as "still going".
    "pending": PipelineStatus.RUNNING,
    "preparing": PipelineStatus.RUNNING,
    "waiting_for_resource": PipelineStatus.RUNNING,
    "manual": PipelineStatus.RUNNING,
    "scheduled": PipelineStatus.RUNNING,
    "created": PipelineStatus.RUNNING,
}


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
        # Group/project tokens and older self-managed instances 401/403 or 404 on this endpoint.
        # Authentication success is determined by /api/v4/user above; treat introspection as advisory.
        try:
            token_payload = await self._request_json("api/v4/personal_access_tokens/self")
            permissions = _permissions(token_payload)
        except (
            ConnectorAuthError,
            ConnectorNotFoundError,
            ConnectorRateLimitedError,
            ConnectorTransientError,
            ConnectorDataError,
        ):
            permissions = []
        return ConnectionTestResult(
            ok=True,
            detail="Connected to GitLab",
            user_display_name=_display_name(user_payload),
            permissions=permissions,
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

    async def fetch_mergerequests(
        self,
        scope: MergeRequestScope,
        window: EvaluationWindow,
    ) -> AsyncIterator[MergeRequest]:
        for project_id in scope.repository_external_ids:
            async for mr in self._fetch_project_mergerequests(project_id, scope, window):
                yield mr

    async def _fetch_project_mergerequests(
        self,
        project_id: str,
        scope: MergeRequestScope,
        window: EvaluationWindow,
    ) -> AsyncIterator[MergeRequest]:
        params: dict[str, object] = {
            "state": "all",
            "order_by": "updated_at",
            "sort": "desc",
            "per_page": PAGE_SIZE,
        }
        # Issue 1: bound the DATE_RANGE window on both ends; SPRINT has no time filter so that
        # stale-MR detection can still see MRs that were last updated before the sprint started.
        if window.window_type is WindowType.DATE_RANGE:
            if window.end is not None:
                params["updated_before"] = _format_iso_datetime(window.end)
            if window.start is not None:
                params["updated_after"] = _format_iso_datetime(window.start)

        # Cap concurrent enrichment requests to avoid triggering GitLab rate limits on full pages.
        # Created per method call so it does not bleed across concurrent invocations.
        sem = asyncio.Semaphore(10)

        async def _enrich(
            payload: Mapping[str, object],
            is_draft: bool,
        ) -> tuple[Mapping[str, object], bool, tuple[int | None, int | None, int | None], int]:
            iid = _required_positive_int(payload, "iid")
            # Issue 2: diff stats are absent from the list endpoint; fetch them separately.
            # Both fetches are independent — run them concurrently, under the shared semaphore.
            async with sem:
                diff_stats, approval_count = await asyncio.gather(
                    self._resolve_diff_stats(project_id, iid, payload),
                    self._fetch_approval_count(project_id, iid),
                )
            return payload, is_draft, diff_stats, approval_count

        page = 1
        while True:
            payloads, next_page = await self._request_json_list_page(
                f"api/v4/projects/{project_id}/merge_requests",
                params={**params, "page": page},
            )

            # Issue 4: read state first so the draft heuristic can gate on it.
            # Filter before enrichment so skipped MRs never trigger extra network calls.
            accepted: list[tuple[Mapping[str, object], bool]] = []
            for payload in payloads:
                gl_state = _optional_str(payload, "state")
                is_draft = _mr_is_draft(payload, gl_state)
                if not scope.include_drafts and is_draft:
                    continue
                if gl_state == "closed" and not scope.include_closed_unmerged:
                    continue
                accepted.append((payload, is_draft))

            # Enrich all accepted MRs in the page concurrently, then yield them in order.
            results = await asyncio.gather(*[_enrich(p, d) for p, d in accepted])
            for payload, is_draft, diff_stats, approval_count in results:
                yield _mergerequest_from_payload(
                    payload, project_id, is_draft, approval_count, diff_stats
                )

            if next_page is None:
                return
            if next_page <= page:
                raise ConnectorDataError("GitLab MR pagination did not advance")
            page = next_page

    async def _fetch_approval_count(self, project_id: str, iid: int) -> int:
        try:
            payload = await self._request_json(
                f"api/v4/projects/{project_id}/merge_requests/{iid}/approvals"
            )
        except (ConnectorNotFoundError, ConnectorAuthError):
            # Some GitLab editions or tokens do not have approvals access.
            return 0
        approved_by = payload.get("approved_by")
        if not isinstance(approved_by, list):
            return 0
        # Issue 7: count distinct approver IDs; the API can occasionally return duplicate entries.
        distinct_ids: set[object] = set()
        for entry in approved_by:
            if not isinstance(entry, Mapping):
                continue
            user = entry.get("user")
            if not isinstance(user, Mapping):
                continue
            uid = user.get("id")
            if uid is not None:
                distinct_ids.add(uid)
        return len(distinct_ids)

    async def _fetch_mr_detail(self, project_id: str, iid: int) -> Mapping[str, object]:
        """Fetch the single-MR detail endpoint.

        Returns an empty mapping when the MR is not found so callers can treat missing
        diff-stat fields as None rather than aborting the entire fetch.
        """
        try:
            return await self._request_json(f"api/v4/projects/{project_id}/merge_requests/{iid}")
        except (ConnectorNotFoundError, ConnectorAuthError):
            return {}

    async def _resolve_diff_stats(
        self,
        project_id: str,
        iid: int,
        list_payload: Mapping[str, object],
    ) -> tuple[int | None, int | None, int | None]:
        """Return (changed_files_count, additions, deletions).

        The REST list endpoint does not include diff stats; we try the list payload first
        (forward-compatibility) and fall back to the single-MR endpoint for any missing field.
        """
        diff_stats = _optional_mapping(list_payload.get("diff_stats_summary"))
        changed_files = _parse_changes_count(list_payload.get("changes_count"), diff_stats)
        additions = (
            _optional_nonneg_int(diff_stats, "additions") if diff_stats is not None else None
        )
        deletions = (
            _optional_nonneg_int(diff_stats, "deletions") if diff_stats is not None else None
        )

        if changed_files is None or additions is None or deletions is None:
            detail = await self._fetch_mr_detail(project_id, iid)
            detail_diff_stats = _optional_mapping(detail.get("diff_stats_summary"))
            if changed_files is None:
                changed_files = _parse_changes_count(detail.get("changes_count"), detail_diff_stats)
            if additions is None:
                raw = detail.get("additions")
                if isinstance(raw, int) and not isinstance(raw, bool) and raw >= 0:
                    additions = raw
                elif detail_diff_stats is not None:
                    additions = _optional_nonneg_int(detail_diff_stats, "additions")
            if deletions is None:
                raw = detail.get("deletions")
                if isinstance(raw, int) and not isinstance(raw, bool) and raw >= 0:
                    deletions = raw
                elif detail_diff_stats is not None:
                    deletions = _optional_nonneg_int(detail_diff_stats, "deletions")

        return changed_files, additions, deletions

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


def _stable_id(kind: str, external_id: str) -> UUID:
    return uuid5(_NAMESPACE, f"{kind}:{external_id}")


def _mergerequest_from_payload(
    payload: Mapping[str, object],
    project_id: str,
    is_draft: bool,
    approval_count: int,
    diff_stats: tuple[int | None, int | None, int | None],
) -> MergeRequest:
    mr_global_id = str(_required_positive_int(payload, "id"))
    iid = _required_positive_int(payload, "iid")
    state = _mr_state(payload, is_draft)

    merged_at: datetime | None = None
    closed_at: datetime | None = None
    if state is MergeRequestState.MERGED:
        merged_at = _required_datetime(payload, "merged_at")
    elif state is MergeRequestState.CLOSED:
        closed_at = _required_datetime(payload, "closed_at")

    author = _required_mapping(payload, "author")
    author_id = _stable_id("user", str(_required_positive_int(author, "id")))

    pipeline_status, pipeline_updated_at = _pipeline_info(payload.get("head_pipeline"))

    changed_files_count, additions, deletions = diff_stats

    comment_count = _optional_nonneg_int(payload, "user_notes_count") or 0

    return MergeRequest(
        id=_stable_id("mergerequest", mr_global_id),
        source=Source.GITLAB,
        external_id=mr_global_id,
        source_url=_optional_str(payload, "web_url"),
        repository_id=_stable_id("repository", project_id),
        iid=iid,
        title=_required_str(payload, "title"),
        description=_optional_str(payload, "description"),
        state=state,
        is_draft=is_draft,
        author_id=author_id,
        target_branch=_required_str(payload, "target_branch"),
        source_branch=_required_str(payload, "source_branch"),
        created_at=_required_datetime(payload, "created_at"),
        updated_at=_required_datetime(payload, "updated_at"),
        merged_at=merged_at,
        closed_at=closed_at,
        changed_files_count=changed_files_count,
        additions=additions,
        deletions=deletions,
        pipeline_status=pipeline_status,
        pipeline_updated_at=pipeline_updated_at,
        approval_count=approval_count,
        comment_count=comment_count,
    )


def _mr_is_draft(payload: Mapping[str, object], gl_state: str | None) -> bool:
    # The API-level draft/work_in_progress flags are authoritative for all states.
    if payload.get("draft") is True:
        return True
    if payload.get("work_in_progress") is True:
        return True
    # Title-prefix heuristic only applies to open MRs; a merged "WIP: hotfix" stays MERGED.
    if gl_state == "opened":
        title = payload.get("title")
        if isinstance(title, str):
            lower = title.strip().lower()
            return lower.startswith(("[draft]", "draft:", "wip:"))
    return False


def _mr_state(payload: Mapping[str, object], is_draft: bool) -> MergeRequestState:
    if is_draft:
        return MergeRequestState.DRAFT
    gl_state = _optional_str(payload, "state")
    # Issue 3: "locked" MRs are still open in GitLab — they cannot receive new commits but are
    # not closed.  Mapping them to CLOSED would require a closed_at that GitLab does not supply.
    if gl_state in ("opened", "locked"):
        return MergeRequestState.OPEN
    if gl_state == "merged":
        return MergeRequestState.MERGED
    if gl_state == "closed":
        return MergeRequestState.CLOSED
    raise ConnectorDataError(f"Unsupported GitLab MR state: {gl_state!r}")


def _pipeline_info(
    pipeline: object,
) -> tuple[PipelineStatus | None, datetime | None]:
    if pipeline is None:
        return PipelineStatus.NONE, None
    if not isinstance(pipeline, Mapping):
        raise ConnectorDataError("GitLab MR head_pipeline was invalid")
    status_str = _optional_str(pipeline, "status")
    status = _map_pipeline_status(status_str) if status_str else PipelineStatus.NONE
    updated_at = _parse_datetime(_optional_str(pipeline, "updated_at"))
    return status, updated_at


def _map_pipeline_status(value: str) -> PipelineStatus:
    return _PIPELINE_STATUS_MAP.get(value, PipelineStatus.NONE)


def _parse_changes_count(
    value: object,
    diff_stats: Mapping[str, object] | None,
) -> int | None:
    if diff_stats is not None:
        file_count = diff_stats.get("file_count")
        if isinstance(file_count, int) and not isinstance(file_count, bool) and file_count >= 0:
            return file_count
    if isinstance(value, str):
        numeric = value.rstrip("+").strip()
        try:
            return int(numeric)
        except ValueError:
            return None
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ConnectorDataError(f"Invalid GitLab datetime: {value}") from error
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _required_datetime(payload: Mapping[str, object], key: str) -> datetime:
    raw = _optional_str(payload, key)
    parsed = _parse_datetime(raw)
    if parsed is None:
        raise ConnectorDataError(f"GitLab MR payload was missing {key}")
    return parsed


def _required_mapping(payload: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = payload.get(key)
    if isinstance(value, Mapping):
        return value
    raise ConnectorDataError(f"GitLab payload contained an invalid {key}")


def _optional_mapping(value: object) -> Mapping[str, object] | None:
    return value if isinstance(value, Mapping) else None


def _optional_nonneg_int(payload: Mapping[str, object], key: str) -> int | None:
    value = payload.get(key)
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _format_iso_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
