# SPDX-License-Identifier: Apache-2.0

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

from em_radar_api.source_connections import UUIDListJSON


class SignalConfigGroupBase(SQLModel):
    name: str
    description: str | None = None
    signal_ids: list[UUID] = Field(default_factory=list, sa_type=UUIDListJSON)


class SignalConfigGroupCreate(SignalConfigGroupBase):
    pass


class SignalConfigGroupUpdate(SQLModel):
    name: str | None = None
    description: str | None = None
    signal_ids: list[UUID] | None = None


class SignalConfigGroupRead(SignalConfigGroupBase):
    id: UUID
    created_at: datetime
    updated_at: datetime


class SignalConfigGroupTable(SignalConfigGroupBase, table=True):
    __tablename__ = "signal_config_group"
    __table_args__ = (UniqueConstraint("name"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
