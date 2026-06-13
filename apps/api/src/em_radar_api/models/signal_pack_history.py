from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import Text
from sqlmodel import Field, SQLModel


class SignalPackHistory(SQLModel, table=True):
    __tablename__ = "signal_pack_history"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    pack_name: str
    raw_yaml: str = Field(sa_type=Text)
    imported_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
