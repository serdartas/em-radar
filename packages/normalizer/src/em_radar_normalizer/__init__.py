# SPDX-License-Identifier: Apache-2.0

from em_radar_normalizer.identity import (
    REFERENCE_FIELDS,
    IdentityMap,
    ReferenceSpec,
    reference_spec,
    resolve_references,
)
from em_radar_normalizer.linking import (
    DEFAULT_WORKITEM_KEY_PATTERN,
    extract_workitem_keys,
    index_workitems_by_key,
    link_merge_request,
    populate_merge_request_links,
    resolve_workitem_ids,
)

__all__ = [
    "DEFAULT_WORKITEM_KEY_PATTERN",
    "REFERENCE_FIELDS",
    "IdentityMap",
    "ReferenceSpec",
    "extract_workitem_keys",
    "index_workitems_by_key",
    "link_merge_request",
    "populate_merge_request_links",
    "reference_spec",
    "resolve_references",
    "resolve_workitem_ids",
]
