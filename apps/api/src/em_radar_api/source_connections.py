from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import field_validator
from sqlalchemy import JSON, Enum, UniqueConstraint
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator
from sqlmodel import Field, SQLModel


class ConnectorName(StrEnum):
    JIRA = "jira"
    GITLAB = "gitlab"


CONNECTOR_NAME_TYPE = Enum(
    ConnectorName, values_callable=lambda enum: [item.value for item in enum]
)


class UUIDListJSON(TypeDecorator[list[str]]):
    impl = JSON
    cache_ok = True

    def process_bind_param(self, value: list[UUID] | None, dialect: Dialect) -> list[str] | None:
        del dialect
        return [str(item) for item in value] if value is not None else None

    def process_result_value(self, value: list[str] | None, dialect: Dialect) -> list[UUID] | None:
        del dialect
        return [UUID(item) for item in value] if value is not None else None


class SourceConnectionBase(SQLModel):
    name: str = Field(min_length=1)
    connector_name: ConnectorName = Field(sa_type=CONNECTOR_NAME_TYPE)
    config: dict[str, object] = Field(default_factory=dict, sa_type=JSON)

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v


class SourceConnectionCreate(SourceConnectionBase):
    pass


class SourceConnectionUpdate(SQLModel):
    name: str | None = Field(default=None, min_length=1)
    connector_name: ConnectorName | None = None
    config: dict[str, object] | None = None

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v


class SourceConnectionRead(SourceConnectionBase):
    id: UUID
    created_at: datetime


class SourceConnectionTable(SourceConnectionBase, table=True):
    __tablename__ = "source_connection"
    __table_args__ = (UniqueConstraint("name", name="uq_source_connection_name"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
