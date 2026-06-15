from pydantic import BaseModel, ConfigDict, Field, JsonValue

from em_radar_core.models import Severity, WorkItemType


class PackModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class SignalScope(PackModel):
    project_keys: list[str] | None = None
    repository_paths: list[str] | None = None
    workitem_types: list[WorkItemType] | None = None
    labels: list[str] | None = None
    exclude_labels: list[str] | None = None
    branches: list[str] | None = None


class PackDefaults(PackModel):
    severity_override: Severity | None = None
    scope: SignalScope | None = None


class SignalEntry(PackModel):
    id: str
    enabled: bool
    severity: Severity | None = None
    scope: SignalScope | None = None
    params: dict[str, JsonValue] | None = None


class JiraFieldMappings(PackModel):
    story_points: str | None = None
    acceptance_criteria_heading: str | None = None
    blocked_label: str | None = None


class GitLabFieldMappings(PackModel):
    workitem_key_pattern: str | None = None


class FieldMappings(PackModel):
    jira: JiraFieldMappings | None = None
    gitlab: GitLabFieldMappings | None = None


class PackMetadata(PackModel):
    name: str
    version: str
    description: str
    author: str | None = None
    license: str | None = None
    homepage: str | None = None
    tags: list[str] | None = None
    min_emradar_version: str | None = None


class SignalPackSpec(PackModel):
    defaults: PackDefaults | None = None
    signals: list[SignalEntry]
    field_mappings: FieldMappings | None = None


class SignalPack(PackModel):
    api_version: str = Field(alias="apiVersion")
    kind: str
    metadata: PackMetadata
    spec: SignalPackSpec
