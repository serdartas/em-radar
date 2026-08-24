# SPDX-License-Identifier: Apache-2.0
"""Tests for custom-field extraction, coercion, and discovery in the Jira connector."""

import asyncio
from collections.abc import Callable

import httpx
import pytest

import em_radar_connector_jira.connector as jira_connector_module
from em_radar_connector_jira.connector import (
    JiraConnector,
    JiraFieldMappingConfig,
    _coerce_custom_field,
    _custom_fields_from_payload,
    _issue_fields,
)
from em_radar_core.connectors import WorkItemScope
from em_radar_core.models import EvaluationWindow, WindowType


def _field_mapping_config() -> JiraFieldMappingConfig:
    return JiraFieldMappingConfig()


def _client_factory_for(
    handler: Callable[[httpx.Request], httpx.Response],
) -> Callable[..., httpx.AsyncClient]:
    def factory(**kwargs: object) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    return factory


def _issue(
    *,
    issue_id: str = "10001",
    key: str = "PLAT-1",
    custom_fields: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build a minimal Jira issue payload."""
    fields: dict[str, object] = {
        "summary": f"{key} summary",
        "description": None,
        "issuetype": {"name": "Story"},
        "status": {"name": "In Progress", "statusCategory": {"key": "indeterminate"}},
        "project": {"id": "10000", "key": "PLAT"},
        "labels": [],
        "components": [],
        "customfield_10016": None,  # story points
        "customfield_10020": [],  # sprint
        "created": "2026-01-01T09:00:00.000+0000",
        "updated": "2026-01-10T09:00:00.000+0000",
        "resolutiondate": None,
        "duedate": None,
    }
    if custom_fields:
        fields.update(custom_fields)
    return {
        "id": issue_id,
        "key": key,
        "self": f"https://jira.example.com/rest/api/2/issue/{issue_id}",
        "fields": fields,
    }


# ---------------------------------------------------------------------------
# _coerce_custom_field
# ---------------------------------------------------------------------------


class TestCoerceCustomField:
    def test_number_int_to_float(self) -> None:
        assert _coerce_custom_field(42, "number") == 42.0
        assert isinstance(_coerce_custom_field(42, "number"), float)

    def test_number_float_passthrough(self) -> None:
        assert _coerce_custom_field(3.14, "number") == 3.14

    def test_number_bool_returns_none(self) -> None:
        assert _coerce_custom_field(True, "number") is None

    def test_number_string_returns_none(self) -> None:
        assert _coerce_custom_field("42", "number") is None

    def test_number_none_returns_none(self) -> None:
        assert _coerce_custom_field(None, "number") is None

    def test_string_strips_whitespace(self) -> None:
        assert _coerce_custom_field("  hello  ", "string") == "hello"

    def test_string_empty_after_strip_returns_none(self) -> None:
        assert _coerce_custom_field("   ", "string") is None

    def test_text_same_as_string(self) -> None:
        assert _coerce_custom_field("note", "text") == "note"

    def test_option_mapping_extracts_value(self) -> None:
        assert _coerce_custom_field({"value": "Backend", "id": "1"}, "option") == "Backend"

    def test_option_mapping_none_value_returns_none(self) -> None:
        assert _coerce_custom_field({"value": None}, "option") is None

    def test_option_scalar_string_coerced(self) -> None:
        assert _coerce_custom_field("plain", "option") == "plain"

    def test_array_list_of_strings(self) -> None:
        assert _coerce_custom_field(["a", "b", "c"], "array") == ["a", "b", "c"]

    def test_array_list_of_mappings_extracts_value(self) -> None:
        raw = [{"value": "Backend"}, {"value": "Frontend"}]
        assert _coerce_custom_field(raw, "array") == ["Backend", "Frontend"]

    def test_array_skips_none_items(self) -> None:
        raw = [None, "a", None, "b"]
        assert _coerce_custom_field(raw, "array") == ["a", "b"]

    def test_array_empty_result_returns_none(self) -> None:
        assert _coerce_custom_field([None, None], "array") is None

    def test_array_non_list_returns_none(self) -> None:
        assert _coerce_custom_field("not-a-list", "array") is None

    def test_unknown_type_scalar_string_passthrough(self) -> None:
        assert _coerce_custom_field("val", "unknown_type") == "val"

    def test_unknown_type_bool_returns_none(self) -> None:
        assert _coerce_custom_field(True, "unknown_type") is None

    def test_none_input_returns_none(self) -> None:
        assert _coerce_custom_field(None, None) is None


# ---------------------------------------------------------------------------
# _custom_fields_from_payload
# ---------------------------------------------------------------------------


class TestCustomFieldsFromPayload:
    def test_coerces_requested_field(self) -> None:
        fields = {"customfield_10100": 5}
        types = {"customfield_10100": "number"}
        result = _custom_fields_from_payload(fields, types)
        assert result == {"customfield_10100": 5.0}

    def test_retains_requested_sprint_field(self) -> None:
        # A signal that explicitly selects the mapped sprint id must observe its value,
        # not None. ``types`` only ever contains signal-requested ids.
        fields = {"customfield_10020": [{"value": "Sprint 1"}], "customfield_10100": "hello"}
        types = {"customfield_10020": "array", "customfield_10100": "string"}
        result = _custom_fields_from_payload(fields, types)
        assert result["customfield_10020"] == ["Sprint 1"]

    def test_retains_requested_story_points_field(self) -> None:
        fm = _field_mapping_config()
        fields = {fm.story_points: 8.0, "customfield_10100": 1.0}
        types = {fm.story_points: "number", "customfield_10100": "number"}
        result = _custom_fields_from_payload(fields, types)
        assert result[fm.story_points] == 8.0

    def test_retains_requested_acceptance_criteria_field(self) -> None:
        fields = {"customfield_10300": "Given When Then", "customfield_10100": "x"}
        types = {"customfield_10300": "string", "customfield_10100": "string"}
        result = _custom_fields_from_payload(fields, types)
        assert result["customfield_10300"] == "Given When Then"

    def test_omits_none_fields(self) -> None:
        fields: dict[str, object] = {"customfield_10100": None}
        types = {"customfield_10100": "string"}
        result = _custom_fields_from_payload(fields, types)
        assert "customfield_10100" not in result

    def test_omits_fields_missing_from_payload(self) -> None:
        fields: dict[str, object] = {}
        types = {"customfield_10100": "string"}
        result = _custom_fields_from_payload(fields, types)
        assert result == {}

    def test_omits_coercion_failure(self) -> None:
        fields = {"customfield_10100": True}  # bool → None for number type
        types = {"customfield_10100": "number"}
        result = _custom_fields_from_payload(fields, types)
        assert "customfield_10100" not in result


# ---------------------------------------------------------------------------
# _issue_fields deduplication
# ---------------------------------------------------------------------------


class TestIssueFields:
    def test_does_not_duplicate_system_fields(self) -> None:
        fm = _field_mapping_config()
        fields = _issue_fields(fm, custom_field_ids=(fm.story_points,))
        assert fields.count(fm.story_points) == 1

    def test_appends_new_custom_field_ids(self) -> None:
        fm = _field_mapping_config()
        fields = _issue_fields(fm, custom_field_ids=("customfield_10100", "customfield_10200"))
        assert "customfield_10100" in fields
        assert "customfield_10200" in fields

    def test_does_not_duplicate_custom_field_ids(self) -> None:
        fm = _field_mapping_config()
        fields = _issue_fields(fm, custom_field_ids=("customfield_10100", "customfield_10100"))
        assert fields.count("customfield_10100") == 1


# ---------------------------------------------------------------------------
# fetch_workitems: discovery failure silently resets to empty custom_fields
# ---------------------------------------------------------------------------


class TestFetchWorkitemsDiscoveryFailure:
    def test_discovery_failure_yields_empty_custom_fields(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If discover_fields raises, fetch_workitems continues with custom_fields={} and flags it."""
        # Clear the field discovery cache so we always hit the network.
        jira_connector_module._field_discovery_cache.clear()  # type: ignore[attr-defined]

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/field"):
                # Simulate discovery failure for both API v2 and v3
                return httpx.Response(500, text="Server Error")
            # JQL search: return one issue
            return httpx.Response(
                200,
                json={
                    "issues": [_issue()],
                    "total": 1,
                    "maxResults": 50,
                    "startAt": 0,
                },
            )

        monkeypatch.setattr(
            jira_connector_module,
            "CLIENT_FACTORY",
            _client_factory_for(handler),
        )
        connector = JiraConnector(
            config={
                "base_url": "https://jira.example.com",
                "token": "demo-token-123456789012345",
            }
        )

        scope = WorkItemScope(
            project_external_ids=["10000"],
            board_external_ids=["20000"],
            custom_field_ids=["customfield_10100"],
        )

        from datetime import UTC, datetime
        from uuid import uuid4

        window = EvaluationWindow(
            window_type=WindowType.DATE_RANGE,
            start=datetime(2026, 6, 1, tzinfo=UTC),
            end=datetime(2026, 6, 17, tzinfo=UTC),
            team_profile_id=uuid4(),
        )

        async def run() -> list:
            items = []
            async for item in connector.fetch_workitems(scope, window):
                items.append(item)
            return items

        items = asyncio.run(run())
        assert len(items) == 1
        assert items[0].custom_fields == {}
        # The degradation is surfaced so the report can attach a partial-data note.
        assert connector.custom_fields_unavailable is True
