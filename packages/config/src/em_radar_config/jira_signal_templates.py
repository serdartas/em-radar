# SPDX-License-Identifier: Apache-2.0

from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from em_radar_core.models import ReportSettings, SignalDefinition, SignalOrigin


@dataclass(frozen=True)
class JiraSignalTemplate:
    key: str
    name: str
    description: str
    expression: dict[str, object]
    report_settings: ReportSettings
    required_scope_capabilities: tuple[str, ...] = ()
    evidence_shape: tuple[str, ...] = ()
    entity_type: str = "issue"
    required_connector_type: str = "jira"


JIRA_SIGNAL_TEMPLATES: tuple[JiraSignalTemplate, ...] = (
    JiraSignalTemplate(
        key="stale-in-progress-work-item",
        name="Stale in-progress work item",
        description="Finds issues that have stayed in progress longer than expected.",
        expression={
            "type": "group",
            "operator": "all",
            "conditions": [
                {"field": "status_category", "operator": "is", "value": "in_progress"},
                {
                    "field": "age_in_current_status",
                    "operator": "greater_than",
                    "value": {"amount": 7, "unit": "days"},
                },
            ],
        },
        report_settings=ReportSettings(severity="warning", category="flow"),
        evidence_shape=("status_category", "age_in_current_status"),
    ),
    JiraSignalTemplate(
        key="story-without-acceptance-criteria",
        name="Story without acceptance criteria",
        description="Finds stories missing acceptance criteria.",
        expression={
            "type": "group",
            "operator": "all",
            "conditions": [
                {"field": "issue_type", "operator": "is", "value": "story"},
                {"field": "acceptance_criteria", "operator": "is_empty", "value": None},
            ],
        },
        report_settings=ReportSettings(severity="warning", category="quality"),
        evidence_shape=("issue_type", "acceptance_criteria"),
    ),
    JiraSignalTemplate(
        key="story-without-parent-epic",
        name="Story without parent epic",
        description="Finds stories that are not linked to an epic.",
        expression={
            "type": "group",
            "operator": "all",
            "conditions": [
                {"field": "issue_type", "operator": "is", "value": "story"},
                {"field": "has_epic_parent", "operator": "is", "value": False},
            ],
        },
        report_settings=ReportSettings(severity="info", category="planning"),
        evidence_shape=("issue_type", "has_epic_parent"),
    ),
    JiraSignalTemplate(
        key="epic-too-broad",
        name="Epic too broad",
        description="Finds epics that exceed the default child-count threshold.",
        expression={
            "type": "group",
            "operator": "all",
            "conditions": [
                {"field": "issue_type", "operator": "is", "value": "epic"},
                {"field": "child_count", "operator": "greater_than", "value": 15},
            ],
        },
        report_settings=ReportSettings(severity="warning", category="planning"),
        evidence_shape=("issue_type", "child_count"),
    ),
    JiraSignalTemplate(
        key="epic-without-measurable-description",
        name="Epic without measurable description",
        description="Finds epics whose descriptions are too thin to evaluate.",
        expression={
            "type": "group",
            "operator": "all",
            "conditions": [
                {"field": "issue_type", "operator": "is", "value": "epic"},
                {"field": "description_length", "operator": "less_than", "value": 100},
            ],
        },
        report_settings=ReportSettings(severity="info", category="planning"),
        evidence_shape=("issue_type", "description_length"),
    ),
    JiraSignalTemplate(
        key="repeated-carry-over",
        name="Repeated carry-over",
        description="Finds issues carried across multiple sprints.",
        expression={
            "type": "group",
            "operator": "all",
            "conditions": [
                {"field": "status_category", "operator": "is_not", "value": "done"},
                {"field": "sprint_count", "operator": "greater_than", "value": 1},
            ],
        },
        report_settings=ReportSettings(severity="warning", category="delivery"),
        required_scope_capabilities=("sprint",),
        evidence_shape=("status_category", "sprint_count"),
    ),
    JiraSignalTemplate(
        key="sprint-scope-churn",
        name="Sprint scope churn",
        description="Finds sprints where scope was added after sprint start beyond the threshold.",
        entity_type="sprint",
        expression={
            "type": "group",
            "operator": "all",
            "conditions": [
                {
                    "field": "sprint_scope_added_pct",
                    "operator": "greater_than",
                    "value": 20.0,
                },
            ],
        },
        report_settings=ReportSettings(severity="warning", category="delivery"),
        required_scope_capabilities=("sprint",),
        evidence_shape=("original_count", "added_count", "churn_pct"),
    ),
)

_seeded_templates: dict[str, JiraSignalTemplate] = {}


def seed_jira_signal_templates() -> tuple[JiraSignalTemplate, ...]:
    for template in JIRA_SIGNAL_TEMPLATES:
        _seeded_templates.setdefault(template.key, template)
    return tuple(_seeded_templates.values())


def restore_jira_signal_template(key: str) -> JiraSignalTemplate:
    for template in JIRA_SIGNAL_TEMPLATES:
        if template.key == key:
            _seeded_templates[key] = template
            return template
    raise KeyError(f"unknown Jira signal template: {key}")


def instantiate_jira_signal_template(
    key: str,
    *,
    name: str | None = None,
) -> SignalDefinition:
    template = restore_jira_signal_template(key)
    return SignalDefinition(
        id=uuid4(),
        name=name or template.name,
        description=template.description,
        entity_type=template.entity_type,
        expression=deepcopy(template.expression),
        report_settings=template.report_settings.model_copy(),
        origin=SignalOrigin.SYSTEM_TEMPLATE,
        template_key=template.key,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
