from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import JSON, Enum
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator
from sqlmodel import Field, SQLModel


class ConnectorName(StrEnum):
    DEMO = "demo"
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
    connector_name: ConnectorName = Field(sa_type=CONNECTOR_NAME_TYPE)
    config: dict[str, object] = Field(default_factory=dict, sa_type=JSON)
    selected_project_ids: list[UUID] = Field(default_factory=list, sa_type=UUIDListJSON)
    selected_board_ids: list[UUID] = Field(default_factory=list, sa_type=UUIDListJSON)
    selected_repository_ids: list[UUID] = Field(default_factory=list, sa_type=UUIDListJSON)


class SourceConnectionCreate(SourceConnectionBase):
    pass


class SourceConnectionUpdate(SQLModel):
    connector_name: ConnectorName | None = None
    config: dict[str, object] | None = None
    selected_project_ids: list[UUID] | None = None
    selected_board_ids: list[UUID] | None = None
    selected_repository_ids: list[UUID] | None = None


class SourceConnectionRead(SourceConnectionBase):
    id: UUID
    created_at: datetime


class SourceConnectionTable(SourceConnectionBase, table=True):
    __tablename__ = "source_connection"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
