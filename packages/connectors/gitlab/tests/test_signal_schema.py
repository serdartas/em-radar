from dataclasses import asdict

from em_radar_connector_gitlab.connector import GitLabConnector


def _field(key: str) -> dict[str, object]:
    schema = asdict(GitLabConnector.describe_signal_schema())
    return next(field for field in schema["fields"] if field["key"] == key)


def test_connector_declares_expected_capabilities() -> None:
    capabilities = GitLabConnector.describe_capabilities()

    assert capabilities.provides_mergerequests is False
    assert capabilities.provides_repositories is True
    assert capabilities.provides_reviews is False
    assert capabilities.supports_incremental_fetch is False
    assert capabilities.provides_workitems is False
    assert capabilities.provides_sprints is False


def test_signal_schema_contains_expected_merge_request_fields_and_operators() -> None:
    schema = asdict(GitLabConnector.describe_signal_schema())

    assert schema["connector_type"] == "gitlab"
    assert schema["entity_types"] == ("merge_request",)
    assert schema["scope_types"] == ()
    assert {"is", "is_not", "is_any_of", "is_none_of"}.issubset(set(_field("state")["operators"]))
    assert {"greater_than", "less_than", "between"}.issubset(
        set(_field("changed_files_count")["operators"])
    )
    assert {
        "age_since_last_review_activity",
        "linked_workitem_keys",
        "total_changes",
        "pipeline_status",
        "age_since_pipeline_update",
        "approval_count",
    }.issubset({field["key"] for field in schema["fields"]})


def test_signal_schema_has_no_source_selection_fields() -> None:
    field_keys = {
        field["key"] for field in asdict(GitLabConnector.describe_signal_schema())["fields"]
    }

    assert field_keys.isdisjoint(
        {
            "connection",
            "connection_id",
            "connector",
            "connector_type",
            "repository",
            "repository_id",
            "repository_path",
            "scope",
        }
    )


def test_branch_value_provider_does_not_depend_on_source_selection() -> None:
    assert _field("target_branch")["value_provider"] == {
        "type": "dynamic",
        "source": "gitlab_branches",
        "depends_on": (),
    }
    assert _field("source_branch")["value_provider"]["depends_on"] == ()


def test_review_and_pipeline_fields_declare_availability_constraints() -> None:
    assert _field("age_since_last_review_activity")["availability"][
        "requires_scope_capability"
    ] == ("reviews",)
    assert _field("pipeline_status")["availability"]["requires_scope_capability"] == ("pipelines",)
