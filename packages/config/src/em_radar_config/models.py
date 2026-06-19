from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictBool

from em_radar_core.models import Severity, WorkItemType


class PackModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


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
    id: str | None = None
    name: str | None = None
    description: str | None = None
    entity_type: str | None = None
    target_scopes: list[dict[str, str]] | None = None
    expression: dict[str, JsonValue] | None = None
    report_settings: dict[str, JsonValue] | None = None
    enabled: StrictBool = True
    origin: str | None = None
    template_key: str | None = None
    severity: Severity | None = None
    scope: SignalScope | None = None
    params: dict[str, JsonValue] | None = None


class ConnectorReference(PackModel):
    local_ref: str
    connector_type: str
    name: str
    base_url: str | None = None
    auth: str | None = None


class ScopeReference(PackModel):
    local_ref: str
    connector_ref: str
    name: str
    scope_type: str
    external_ref: dict[str, JsonValue] = Field(default_factory=dict)
    capabilities: list[str] = Field(default_factory=list)


class TemplateEntry(PackModel):
    key: str
    name: str
    description: str | None = None
    required_connector_type: str
    entity_type: str
    required_scope_capabilities: list[str] = Field(default_factory=list)
    expression: dict[str, JsonValue]
    report_settings: dict[str, JsonValue]
    enabled_by_default: StrictBool = True


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
    export_type: str = "private_backup"
    connectors: list[ConnectorReference] | None = None
    scopes: list[ScopeReference] | None = None
    templates: list[TemplateEntry] | None = None
    defaults: PackDefaults | None = None
    signals: list[SignalEntry] = Field(default_factory=list)
    field_mappings: FieldMappings | None = None


class SignalPack(PackModel):
    api_version: str = Field(alias="apiVersion")
    kind: str
    metadata: PackMetadata
    spec: SignalPackSpec
