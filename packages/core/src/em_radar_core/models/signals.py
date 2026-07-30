from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import JsonValue
from sqlalchemy import JSON
from sqlmodel import Field, SQLModel


class SignalOrigin(StrEnum):
    SYSTEM_TEMPLATE = "system_template"
    USER_CREATED = "user_created"
    IMPORTED = "imported"


class SignalTargetScope(SQLModel):
    connector_id: UUID | str
    scope_id: UUID | str
    scope_type: str


class ReportSettings(SQLModel):
    severity: str
    category: str
    message_template: str | None = None


class SignalDefinition(SQLModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    description: str | None = None
    entity_type: str
    expression: JsonValue = Field(sa_type=JSON)
    report_settings: ReportSettings = Field(sa_type=JSON)
    enabled: bool = True
    origin: SignalOrigin
    template_key: str | None = None
    version: int = 1
    created_at: datetime
    updated_at: datetime
