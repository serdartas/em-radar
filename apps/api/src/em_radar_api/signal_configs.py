from uuid import UUID, uuid4

from sqlalchemy import JSON, Enum, UniqueConstraint
from sqlmodel import Field, SQLModel

from em_radar_core.models import Severity

SEVERITY_TYPE = Enum(Severity, values_callable=lambda enum: [item.value for item in enum])


class SignalConfigBase(SQLModel):
    signal_id: str
    enabled: bool = True
    severity_override: Severity | None = Field(default=None, sa_type=SEVERITY_TYPE)
    params: dict[str, object] = Field(default_factory=dict, sa_type=JSON)
    scope: dict[str, object] = Field(default_factory=dict, sa_type=JSON)


class SignalConfigUpsert(SignalConfigBase):
    pass


class SignalConfigRead(SignalConfigBase):
    id: UUID


class SignalConfigTable(SignalConfigBase, table=True):
    __tablename__ = "signal_config"
    __table_args__ = (UniqueConstraint("signal_id"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
