from datetime import datetime
from typing import Self
from uuid import UUID, uuid4

from pydantic import JsonValue, model_validator
from sqlalchemy import JSON
from sqlmodel import Field, SQLModel

from em_radar_core.models.enums import (
    Confidence,
    EntityType,
    ReportStatus,
    Severity,
    WindowType,
    WorkingMode,
)


class TeamProfile(SQLModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    description: str | None = None
    connection_ids: list[UUID] = Field(default_factory=list, sa_type=JSON)
    project_ids: list[UUID] = Field(sa_type=JSON)
    board_ids: list[UUID] = Field(default_factory=list, sa_type=JSON)
    repository_ids: list[UUID] = Field(sa_type=JSON)
    working_mode: WorkingMode = WorkingMode.SCRUM
    sprint_length_days: int | None = None
    member_user_keys: list[str] = Field(default_factory=list, sa_type=JSON)
    created_at: datetime
    updated_at: datetime


class EvaluationWindow(SQLModel):
    id: UUID = Field(default_factory=uuid4)
    window_type: WindowType
    sprint_id: UUID | None = None
    start: datetime | None = None
    end: datetime | None = None
    team_profile_id: UUID

    @model_validator(mode="after")
    def validate_scope(self) -> Self:
        if self.window_type is WindowType.SPRINT:
            if self.sprint_id is None or self.start is not None or self.end is not None:
                raise ValueError("sprint windows require only sprint_id")
        elif self.sprint_id is not None or self.start is None or self.end is None:
            raise ValueError("date-range windows require only start and end")
        return self


class SignalFinding(SQLModel):
    id: UUID = Field(default_factory=uuid4)
    report_id: UUID
    signal_id: str
    signal_name: str
    severity: Severity
    confidence: Confidence
    entity_type: EntityType
    entity_id: UUID
    title: str
    reason: str
    recommendation: str | None = None
    evidence: JsonValue = Field(sa_type=JSON)
    source_link: str | None = None
    created_at: datetime

    @property
    def uniqueness_key(self) -> tuple[UUID, str, EntityType, UUID]:
        return (self.report_id, self.signal_id, self.entity_type, self.entity_id)


class Report(SQLModel):
    id: UUID = Field(default_factory=uuid4)
    evaluation_window_id: UUID
    signal_pack_snapshot: JsonValue = Field(sa_type=JSON)
    status: ReportStatus
    started_at: datetime
    finished_at: datetime | None = None
    error: str | None = None
    findings_count_by_severity: dict[Severity, int] = Field(
        default_factory=lambda: {severity: 0 for severity in Severity},
        sa_type=JSON,
    )

    @model_validator(mode="after")
    def validate_findings_count_shape(self) -> Self:
        if set(self.findings_count_by_severity) != set(Severity):
            raise ValueError("findings_count_by_severity must contain info, warning, and critical")
        if any(count < 0 for count in self.findings_count_by_severity.values()):
            raise ValueError("findings_count_by_severity values cannot be negative")
        return self


class EvaluationContext(SQLModel):
    """Immutable inputs shared by signals; `now` is their only source of current time."""

    now: datetime
    window: EvaluationWindow
    team: TeamProfile
