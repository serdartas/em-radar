from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, Enum, UniqueConstraint
from sqlmodel import Field, SQLModel

from em_radar_core.models import SignalOrigin

SIGNAL_ORIGIN_TYPE = Enum(SignalOrigin, values_callable=lambda enum: [item.value for item in enum])


class SignalDefinitionBase(SQLModel):
    name: str
    description: str | None = None
    entity_type: str
    expression: dict[str, object] = Field(sa_type=JSON)
    report_settings: dict[str, object] = Field(sa_type=JSON)
    enabled: bool = True
    origin: SignalOrigin = Field(sa_type=SIGNAL_ORIGIN_TYPE)
    template_key: str | None = None


class SignalDefinitionCreate(SignalDefinitionBase):
    pass


class SignalDefinitionUpdate(SQLModel):
    name: str | None = None
    description: str | None = None
    entity_type: str | None = None
    expression: dict[str, object] | None = None
    report_settings: dict[str, object] | None = None
    enabled: bool | None = None
    origin: SignalOrigin | None = None
    template_key: str | None = None


class SignalDefinitionRead(SignalDefinitionBase):
    id: UUID
    version: int
    created_at: datetime
    updated_at: datetime


class SignalDefinitionTable(SignalDefinitionBase, table=True):
    __tablename__ = "signal_definition"
    __table_args__ = (UniqueConstraint("name"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    version: int = 1
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
