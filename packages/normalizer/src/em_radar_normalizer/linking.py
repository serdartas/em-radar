import re
from collections.abc import Iterable, Mapping
from uuid import UUID

from em_radar_core.models import MergeRequest, WorkItem

DEFAULT_WORKITEM_KEY_PATTERN = r"[A-Z]+-\d+"


def extract_workitem_keys(
    title: str,
    description: str | None,
    source_branch: str,
    pattern: str = DEFAULT_WORKITEM_KEY_PATTERN,
) -> list[str]:
    """Extract deduplicated work-item keys from an MR's text fields.

    Keys are collected in first-seen order across ``title`` → ``description`` →
    ``source_branch`` so the result is deterministic. ``pattern`` matches whole keys as
    standalone tokens (word-bounded) to avoid partial captures inside larger identifiers.
    """
    compiled = re.compile(rf"\b{pattern}\b")
    seen: dict[str, None] = {}
    for field in (title, description or "", source_branch):
        for match in compiled.findall(field):
            seen.setdefault(match, None)
    return list(seen)


def resolve_workitem_ids(
    keys: Iterable[str],
    workitems_by_key: Mapping[str, UUID],
) -> list[UUID]:
    """Resolve work-item keys to WorkItem ids, dropping keys with no matching WorkItem.

    Order follows ``keys``; unmatched keys are left unresolved rather than added as gaps.
    """
    return [workitems_by_key[key] for key in keys if key in workitems_by_key]


def index_workitems_by_key(workitems: Iterable[WorkItem]) -> dict[str, UUID]:
    return {workitem.key: workitem.id for workitem in workitems}


def link_merge_request(
    merge_request: MergeRequest,
    workitems: Iterable[WorkItem],
    pattern: str = DEFAULT_WORKITEM_KEY_PATTERN,
) -> tuple[list[str], list[UUID]]:
    """Extract keys from ``merge_request`` and resolve them against ``workitems``.

    Returns the ``(linked_workitem_keys, linked_workitem_ids)`` pair without mutating the
    merge request, leaving persistence to the caller.
    """
    keys = extract_workitem_keys(
        merge_request.title,
        merge_request.description,
        merge_request.source_branch,
        pattern,
    )
    ids = resolve_workitem_ids(keys, index_workitems_by_key(workitems))
    return keys, ids
