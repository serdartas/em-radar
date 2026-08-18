# SPDX-License-Identifier: Apache-2.0

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import JSON, Enum
from sqlmodel import Field, SQLModel


class ScopeType(StrEnum):
    PROJECT = "project"
    BOARD = "board"
    REPOSITORY = "repository"
    SAVED_FILTER = "saved_filter"
    CUSTOM = "custom"


SCOPE_TYPE = Enum(ScopeType, values_callable=lambda enum: [item.value for item in enum])


class ScopeDefinitionBase(SQLModel):
    connection_id: UUID
    name: str
    scope_type: ScopeType = Field(sa_type=SCOPE_TYPE)
    external_ref: dict[str, str | None] = Field(default_factory=dict, sa_type=JSON)
    capabilities: list[str] = Field(default_factory=list, sa_type=JSON)


class ScopeDefinitionCreate(ScopeDefinitionBase):
    pass


class ScopeDefinitionUpdate(SQLModel):
    connection_id: UUID | None = None
    name: str | None = None
    scope_type: ScopeType | None = None
    external_ref: dict[str, str | None] | None = None
    capabilities: list[str] | None = None


class ScopeDefinitionRead(ScopeDefinitionBase):
    id: UUID
    created_at: datetime
    updated_at: datetime


class ScopeDefinitionTable(ScopeDefinitionBase, table=True):
    __tablename__ = "scope_definition"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    connection_id: UUID = Field(foreign_key="source_connection.id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
