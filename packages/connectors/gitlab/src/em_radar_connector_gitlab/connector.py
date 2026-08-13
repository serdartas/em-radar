from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from datetime import datetime, timezone
from typing import ClassVar, cast
from urllib.parse import urlparse
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
    Review,
    ReviewDecision,
    Source,
)

_logger = logging.getLogger(__name__)

CLIENT_FACTORY: Callable[..., httpx.AsyncClient] = httpx.AsyncClient
PAGE_SIZE = 100
_NAMESPACE = UUID("c7d8a5f1-3b4e-4f2a-8c9d-1e0f7a6b5c3d")


def _url_instance_prefix(base_url: HttpUrl) -> str:
    """Return host[:port] from a URL for namespacing entity external IDs per GitLab instance.

    Two configured GitLab instances share Source.GITLAB and their numeric entity IDs may
    collide; the host prefix makes every (source, external_id) pair globally unique.
    """
    return urlparse(str(base_url)).netloc


# Maps the beginning of a GitLab system-note body to a canonical review decision.
# Matched with str.startswith so minor suffix variations (e.g. punctuation) are tolerated.
_REVIEW_NOTE_PATTERNS: tuple[tuple[str, ReviewDecision], ...] = (
    ("approved this merge request", ReviewDecision.APPROVED),
    ("unapproved this merge request", ReviewDecision.DISMISSED),
    # Notes are historical and ordered; reviewer state is a snapshot of current state only.
    # Sourcing CHANGES_REQUESTED from notes preserves history when a reviewer subsequently
    # approves (their state becomes "approved", losing the prior "requested_changes" event).
    ("requested changes", ReviewDecision.CHANGES_REQUESTED),
)

_REVIEWER_ACTED_STATES: frozenset[str] = frozenset(
    {"approved", "requested_changes", "unapproved", "reviewed"}
)

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

        self._instance_prefix = _url_instance_prefix(self.config.base_url)
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
        namespaced_project_id: str,
        scope: MergeRequestScope,
        window: EvaluationWindow,
    ) -> AsyncIterator[MergeRequest]:
        params: dict[str, object] = {
            "state": "all",
            "order_by": "updated_at",
            "sort": "desc",
            "per_page": PAGE_SIZE,
        }
        # No updated_before upper bound: terminal MRs merged/closed inside the window but
        # updated (e.g. commented on) after window.end would be silently excluded by the
        # API if we applied it.  Post-normalization filters (_payload_in_window,
        # _mr_in_window) handle window boundaries correctly without this parameter.

        # Strip the instance prefix to get the numeric GitLab project ID for API calls.
        project_api_id = namespaced_project_id.split("/", 1)[-1]

        # Cap concurrent enrichment requests to avoid triggering GitLab rate limits on full pages.
        # Created per method call so it does not bleed across concurrent invocations.
        sem = asyncio.Semaphore(10)

        async def _enrich(
            payload: Mapping[str, object],
            is_draft: bool,
        ) -> tuple[Mapping[str, object], bool, int | None, int | None, int | None, int | None]:
            iid = _required_positive_int(payload, "iid")
            # Diff stats and approvals are independent — run them concurrently under the semaphore.
            # TaskGroup cancels the sibling coroutine on error; asyncio.gather would leave it
            # orphaned (e.g. a 500 on /approvals keeps diff-stats in flight).
            # Use plain except (not except*) so the inner ExceptionGroup is unwrapped into a
            # plain exception before propagating — the outer TaskGroup's except* expects plain
            # connector exceptions, not nested ExceptionGroups.
            async with sem:
                try:
                    async with asyncio.TaskGroup() as tg:
                        diff_task = tg.create_task(
                            self._resolve_diff_stats(project_api_id, iid, payload)
                        )
                        approval_task = tg.create_task(
                            self._fetch_approval_count(project_api_id, iid)
                        )
                except BaseExceptionGroup as eg:
                    if len(eg.exceptions) > 1:
                        _logger.warning(
                            "Multiple enrichment errors for MR; reporting first: %s", eg
                        )
                    raise eg.exceptions[0] from eg
            changed_files, additions, deletions = diff_task.result()
            return payload, is_draft, changed_files, additions, deletions, approval_task.result()

        page = 1
        while True:
            payloads, next_page = await self._request_json_list_page(
                f"api/v4/projects/{project_api_id}/merge_requests",
                params={**params, "page": page},
            )

            # Read state first so the draft heuristic can gate on it.
            # Filter before enrichment so skipped MRs never trigger extra network calls.
            accepted: list[tuple[Mapping[str, object], bool]] = []
            for payload in payloads:
                gl_state = _optional_str(payload, "state")
                is_draft = _mr_is_draft(payload, gl_state)
                is_terminal = gl_state in ("merged", "closed")
                # Terminal MRs are never excluded on the basis of the draft flag — a closed MR
                # that still carries draft=True must pass through and be normalized to CLOSED.
                if not scope.include_drafts and is_draft and not is_terminal:
                    continue
                # include_closed_unmerged governs only the "closed" (rejected/abandoned) state;
                # merged MRs are always included regardless of this flag.
                if gl_state == "closed" and not scope.include_closed_unmerged:
                    continue
                # Skip terminal MRs outside the window before enrichment to avoid 2 wasted
                # API calls (diff stats + approvals) per out-of-window MR.
                if not _payload_in_window(payload, window):
                    continue
                accepted.append((payload, is_draft))

            # Enrich all accepted MRs in the page concurrently, then yield them in order.
            # TaskGroup cancels sibling tasks immediately when one raises, preventing orphaned
            # in-flight network calls that asyncio.gather would leave running.
            tasks: list[asyncio.Task[object]] = []
            try:
                async with asyncio.TaskGroup() as tg:
                    tasks = [tg.create_task(_enrich(p, d)) for p, d in accepted]
            except* (
                ConnectorTransientError,
                ConnectorDataError,
                ConnectorAuthError,
                ConnectorNotFoundError,
                ConnectorRateLimitedError,
            ) as eg:
                raise eg.exceptions[0]
            results = [t.result() for t in tasks]
            for (
                payload,
                is_draft,
                changed_files_count,
                additions,
                deletions,
                approval_count,
            ) in results:
                mr = _mergerequest_from_payload(
                    payload,
                    namespaced_project_id,
                    self._instance_prefix,
                    is_draft,
                    approval_count,
                    changed_files_count,
                    additions,
                    deletions,
                )
                if _mr_in_window(mr, window):
                    yield mr

            if next_page is None:
                return
            if next_page <= page:
                raise ConnectorDataError("GitLab MR pagination did not advance")
            page = next_page

    async def _fetch_approval_count(self, project_id: str, iid: int) -> int | None:
        try:
            payload = await self._request_json(
                f"api/v4/projects/{project_id}/merge_requests/{iid}/approvals"
            )
        except (ConnectorNotFoundError, ConnectorAuthError):
            # Some GitLab editions or tokens do not expose the approvals API.
            # Return None so the signal skips rather than falsely firing.
            return None
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
        for changed_files_count (forward-compatibility) and always fetch the single-MR
        detail endpoint to obtain additions and deletions.  Top-level additions/deletions
        on the detail response are preferred; diff_stats_summary is used as a fallback.
        """
        diff_stats = _optional_mapping(list_payload.get("diff_stats_summary"))
        list_changed_files = _parse_changes_count(list_payload.get("changes_count"), diff_stats)

        detail = await self._fetch_mr_detail(project_id, iid)
        detail_diff_stats = _optional_mapping(detail.get("diff_stats_summary"))
        detail_changed_files = _parse_changes_count(detail.get("changes_count"), detail_diff_stats)

        changed_files = (
            list_changed_files if list_changed_files is not None else detail_changed_files
        )

        additions = _optional_nonneg_int(detail, "additions")
        if additions is None and detail_diff_stats is not None:
            additions = _optional_nonneg_int(detail_diff_stats, "additions")

        deletions = _optional_nonneg_int(detail, "deletions")
        if deletions is None and detail_diff_stats is not None:
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
                    # Restrict discovery to projects the authenticated account is a member of;
                    # without this GitLab.com returns unrelated public projects.
                    "membership": True,
                },
            )
            repositories.extend(
                _repository_from_payload(payload, self._instance_prefix) for payload in payloads
            )
            if next_page is None:
                return repositories
            if next_page <= page:
                raise ConnectorDataError("GitLab project pagination did not advance")
            page = next_page

    async def fetch_reviews(
        self,
        mergerequest_external_ids: list[str],
    ) -> AsyncIterator[Review]:
        for mr_external_id in mergerequest_external_ids:
            async for review in self._fetch_reviews_for_mr(mr_external_id):
                yield review

    async def _fetch_reviews_for_mr(self, mr_external_id: str) -> AsyncIterator[Review]:
        # Resolve project_id and iid from the global MR id.
        # GitLab exposes a non-project-scoped endpoint for this since 13.5.
        # Strip the instance prefix (e.g. "gitlab.example.com/2001" → "2001") for the API call.
        mr_api_id = mr_external_id.split("/", 1)[-1]
        mr_payload = await self._request_json(f"api/v4/merge_requests/{mr_api_id}")
        project_id = str(_required_positive_int(mr_payload, "project_id"))
        iid = _required_positive_int(mr_payload, "iid")
        mr_id = _stable_id("mergerequest", mr_external_id)

        # Activity rows first, in ascending chronological order so approve→unapprove is preserved.
        async for review in self._fetch_review_activity(project_id, iid, mr_id):
            yield review

        # Requested rows last — these carry null submitted_at and have no position in the timeline.
        async for review in self._fetch_reviewer_requests(project_id, iid, mr_id):
            yield review

    async def _fetch_review_activity(
        self,
        project_id: str,
        iid: int,
        mr_id: UUID,
    ) -> AsyncIterator[Review]:
        page = 1
        while True:
            payloads, next_page = await self._request_json_list_page(
                f"api/v4/projects/{project_id}/merge_requests/{iid}/notes",
                params={
                    "page": page,
                    "per_page": PAGE_SIZE,
                    "sort": "asc",
                    "order_by": "created_at",
                },
            )
            for note_payload in payloads:
                review = _review_from_note(note_payload, mr_id, self._instance_prefix)
                if review is not None:
                    yield review
            if next_page is None:
                return
            if next_page <= page:
                raise ConnectorDataError("GitLab notes pagination did not advance")
            page = next_page

    async def _fetch_reviewer_requests(
        self,
        project_id: str,
        iid: int,
        mr_id: UUID,
    ) -> AsyncIterator[Review]:
        page = 1
        while True:
            try:
                payloads, next_page = await self._request_json_list_page(
                    f"api/v4/projects/{project_id}/merge_requests/{iid}/reviewers",
                    params={"page": page, "per_page": PAGE_SIZE},
                )
            except (ConnectorNotFoundError, ConnectorAuthError):
                # Reviewers API unavailable on some self-managed editions or token scopes.
                return
            for reviewer_payload in payloads:
                # GitLab reviewers endpoint returns MergeRequestReviewer objects:
                # {"user": {"id": ..., ...}, "state": "unreviewed"|"reviewed"|..., "created_at": ...}
                user = _required_mapping(reviewer_payload, "user")
                reviewer_id = _stable_id(
                    "user", f"{self._instance_prefix}/{str(_required_positive_int(user, 'id'))}"
                )
                state = _optional_str(reviewer_payload, "state")
                if state not in _REVIEWER_ACTED_STATES:
                    # Snapshot-derived: this row reflects the API state at fetch time.
                    # Covers "unreviewed", "review_started", "attention_requested", and any
                    # future non-terminal states GitLab may add.
                    # A later decision row (APPROVED, CHANGES_REQUESTED, etc.) sourced from
                    # note history will supersede it during signal evaluation.
                    yield Review(
                        mergerequest_id=mr_id,
                        reviewer_id=reviewer_id,
                        decision=ReviewDecision.REQUESTED,
                        submitted_at=None,
                    )
            if next_page is None:
                return
            if next_page <= page:
                raise ConnectorDataError("GitLab reviewers pagination did not advance")
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
    namespaced_project_id: str,
    instance_prefix: str,
    is_draft: bool,
    approval_count: int | None,
    changed_files_count: int | None,
    additions: int | None,
    deletions: int | None,
) -> MergeRequest:
    mr_global_id = str(_required_positive_int(payload, "id"))
    namespaced_mr_id = f"{instance_prefix}/{mr_global_id}"
    iid = _required_positive_int(payload, "iid")
    gl_state = _optional_str(payload, "state") or ""
    state = _mr_state(gl_state, is_draft)

    merged_at: datetime | None = None
    closed_at: datetime | None = None
    if state is MergeRequestState.MERGED:
        merged_at = _required_datetime(payload, "merged_at")
    elif state is MergeRequestState.CLOSED:
        closed_at = _required_datetime(payload, "closed_at")

    author = _required_mapping(payload, "author")
    author_id = _stable_id("user", f"{instance_prefix}/{str(_required_positive_int(author, 'id'))}")

    pipeline_status, pipeline_updated_at = _pipeline_info(payload.get("head_pipeline"))

    comment_count = _optional_nonneg_int(payload, "user_notes_count") or 0

    return MergeRequest(
        id=_stable_id("mergerequest", namespaced_mr_id),
        source=Source.GITLAB,
        external_id=namespaced_mr_id,
        source_url=_optional_str(payload, "web_url"),
        repository_id=_stable_id("repository", namespaced_project_id),
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


def _mr_state(gl_state: str, is_draft: bool) -> MergeRequestState:
    # Draft only overrides non-terminal states; merged/closed take precedence unconditionally.
    if is_draft and gl_state in ("opened", "locked"):
        return MergeRequestState.DRAFT
    # Issue 3: "locked" MRs are still open in GitLab — they cannot receive new commits but are
    # not closed.  Mapping them to CLOSED would require a closed_at that GitLab does not supply.
    if gl_state in ("opened", "locked"):
        return MergeRequestState.OPEN
    if gl_state == "merged":
        return MergeRequestState.MERGED
    if gl_state == "closed":
        return MergeRequestState.CLOSED
    raise ConnectorDataError(f"Unsupported GitLab MR state: {gl_state!r}")


def _within_window_bounds(moment: datetime | None, window: EvaluationWindow) -> bool:
    if moment is None:
        return False
    if window.start is not None and moment < window.start:
        return False
    if window.end is not None and moment > window.end:
        return False
    return True


def _mr_in_window(mr: MergeRequest, window: EvaluationWindow) -> bool:
    # Open/draft MRs are always included: a stale open MR last touched before the window
    # start is exactly the case the "waiting too long" signal is designed to catch.
    if mr.state in (MergeRequestState.OPEN, MergeRequestState.DRAFT):
        return True
    # Without bounds there is nothing to filter against.
    if window.start is None and window.end is None:
        return True
    # Terminal MRs are kept only when their completion event falls within the window, not
    # when updated_at does — an MR can be updated (e.g. comment) long after it was merged.
    # The upper bound matters too: a report window ends at the run's started_at, so an MR
    # completed after that boundary must not leak into the snapshot.
    if mr.state is MergeRequestState.MERGED:
        return _within_window_bounds(mr.merged_at, window)
    if mr.state is MergeRequestState.CLOSED:
        return _within_window_bounds(mr.closed_at, window)
    return True


def _payload_in_window(payload: Mapping[str, object], window: EvaluationWindow) -> bool:
    """Pre-normalization window filter on raw GitLab MR payloads.

    Prevents enrichment calls for terminal MRs that fall outside the window.  Non-terminal
    states (open, locked, unknown) always pass through; unknown states are kept so that
    normalization can raise ConnectorDataError with a meaningful message.
    """
    if window.start is None and window.end is None:
        return True
    gl_state = _optional_str(payload, "state")
    if gl_state == "merged":
        merged_at = _parse_datetime(_optional_str(payload, "merged_at"))
        if merged_at is None:
            return True  # missing timestamp; pass through so normalization raises
        return _within_window_bounds(merged_at, window)
    if gl_state == "closed":
        closed_at = _parse_datetime(_optional_str(payload, "closed_at"))
        if closed_at is None:
            return True  # missing timestamp; pass through so normalization raises
        return _within_window_bounds(closed_at, window)
    return True


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


def _repository_from_payload(payload: Mapping[str, object], instance_prefix: str) -> Repository:
    default_branch = payload.get("default_branch")
    if default_branch is None:
        default_branch = ""
    if not isinstance(default_branch, str):
        raise ConnectorDataError("GitLab project contained an invalid default_branch")

    namespaced_id = f"{instance_prefix}/{str(_required_positive_int(payload, 'id'))}"
    return Repository(
        id=_stable_id("repository", namespaced_id),
        source=Source.GITLAB,
        external_id=namespaced_id,
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


def _review_from_note(
    note_payload: Mapping[str, object], mr_id: UUID, instance_prefix: str
) -> Review | None:
    """Return a Review from a GitLab system note, or None if the note is not a review event."""
    if note_payload.get("system") is not True:
        return None
    body = (_optional_str(note_payload, "body") or "").lower()
    decision: ReviewDecision | None = None
    for pattern, dec in _REVIEW_NOTE_PATTERNS:
        if body.startswith(pattern):
            decision = dec
            break
    if decision is None:
        return None
    author = _required_mapping(note_payload, "author")
    reviewer_id = _stable_id(
        "user", f"{instance_prefix}/{str(_required_positive_int(author, 'id'))}"
    )
    submitted_at = _required_datetime(note_payload, "created_at")
    return Review(
        mergerequest_id=mr_id,
        reviewer_id=reviewer_id,
        decision=decision,
        submitted_at=submitted_at,
    )


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
