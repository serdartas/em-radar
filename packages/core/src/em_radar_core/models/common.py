from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import JSON
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator
from sqlmodel import Field, SQLModel

from em_radar_core.models.enums import Source


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UUIDListJSON(TypeDecorator[list[UUID]]):
    """JSON column that round-trips a ``list[UUID]`` as a list of strings."""

    impl = JSON
    cache_ok = True

    def process_bind_param(self, value: list[UUID] | None, dialect: Dialect) -> list[str] | None:
        del dialect
        return [str(item) for item in value] if value is not None else None

    def process_result_value(self, value: list[str] | None, dialect: Dialect) -> list[UUID] | None:
        del dialect
        return [UUID(item) for item in value] if value is not None else None


class CommonFields(SQLModel):
    id: UUID = Field(default_factory=uuid4)
    source: Source
    external_id: str
    source_url: str | None = None
    source_metadata: dict[str, object] | None = Field(default_factory=dict, sa_type=JSON)
    fetched_at: datetime = Field(default_factory=utc_now)
    created_at: datetime | None = None
    updated_at: datetime | None = None
