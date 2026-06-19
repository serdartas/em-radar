from em_radar_config import (
    JIRA_SIGNAL_TEMPLATES,
    instantiate_jira_signal_template,
    restore_jira_signal_template,
    seed_jira_signal_templates,
)
from em_radar_core.models import SignalOrigin, SignalTargetScope


def test_templates_seed_once() -> None:
    first = seed_jira_signal_templates()
    second = seed_jira_signal_templates()

    assert first == second
    assert len(first) == 8


def test_template_duplicates_into_runnable_scoped_definition() -> None:
    definition = instantiate_jira_signal_template(
        "stale-in-progress-work-item",
        [
            SignalTargetScope(
                connector_id="jira-1",
                scope_id="scope-1",
                scope_type="board",
            )
        ],
    )

    assert definition.enabled is True
    assert definition.origin is SignalOrigin.SYSTEM_TEMPLATE
    assert definition.template_key == "stale-in-progress-work-item"
    assert definition.target_scopes[0].scope_id == "scope-1"


def test_restore_built_in_defaults_without_deleting_user_copies() -> None:
    copied = instantiate_jira_signal_template(
        "blocked-without-update",
        [SignalTargetScope(connector_id="jira-1", scope_id="scope-1", scope_type="project")],
        name="Team-specific blocked work",
    )
    restored = restore_jira_signal_template("blocked-without-update")

    assert copied.name == "Team-specific blocked work"
    assert restored.name == "Blocked without update"


def test_m2_m3_parameter_overrides_have_equivalent_expression_values() -> None:
    stale = restore_jira_signal_template("stale-in-progress-work-item")
    age_condition = stale.expression["conditions"][1]

    assert age_condition["field"] == "age_in_current_status"
    assert age_condition["value"] == {"amount": 7, "unit": "days"}


def test_all_eight_jira_templates_preserve_evidence_contracts() -> None:
    expected = {
        "stale-in-progress-work-item": ("days_idle", "last_updated_at", "threshold"),
        "blocked-without-update": ("days_blocked_idle", "last_updated_at", "threshold"),
        "story-without-acceptance-criteria": ("workitem_type", "has_description"),
        "story-without-parent-epic": ("workitem_type",),
        "epic-too-broad": ("child_count", "threshold"),
        "epic-without-measurable-description": ("description_length", "threshold"),
        "repeated-carry-over": ("sprint_count", "sprint_names"),
        "sprint-scope-churn": ("original_count", "added_count", "churn_pct"),
    }

    assert {template.key: template.evidence_shape for template in JIRA_SIGNAL_TEMPLATES} == expected
