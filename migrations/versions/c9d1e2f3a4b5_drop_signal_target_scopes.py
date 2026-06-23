"""drop signal_definition.target_scopes and backfill default group

Revision ID: c9d1e2f3a4b5
Revises: b7e2c1a9d4f3
Create Date: 2026-06-22 02:00:00.000000

"""

import uuid
from datetime import UTC, datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c9d1e2f3a4b5"
down_revision: Union[str, Sequence[str], None] = "b7e2c1a9d4f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_signal_definition = sa.table("signal_definition", sa.column("id", sa.Uuid()))
_signal_config_group = sa.table(
    "signal_config_group",
    sa.column("id", sa.Uuid()),
    sa.column("name", sa.String()),
    sa.column("description", sa.String()),
    sa.column("signal_ids", sa.JSON()),
    sa.column("created_at", sa.DateTime()),
    sa.column("updated_at", sa.DateTime()),
)


def upgrade() -> None:
    _backfill_default_group()
    with op.batch_alter_table("signal_definition") as batch_op:
        batch_op.drop_column("target_scopes")


def _backfill_default_group() -> None:
    bind = op.get_bind()
    group_count = bind.execute(
        sa.select(sa.func.count()).select_from(_signal_config_group)
    ).scalar()
    if group_count:
        return
    signal_ids = [str(row[0]) for row in bind.execute(sa.select(_signal_definition.c.id)).all()]
    if not signal_ids:
        return
    now = datetime.now(UTC)
    bind.execute(
        _signal_config_group.insert().values(
            id=uuid.uuid4(),
            name="Default signals",
            description="Signals migrated from the pre-group model.",
            signal_ids=signal_ids,
            created_at=now,
            updated_at=now,
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("signal_definition") as batch_op:
        batch_op.add_column(sa.Column("target_scopes", sa.JSON(), nullable=True))
    op.execute("UPDATE signal_definition SET target_scopes = '[]' WHERE target_scopes IS NULL")
    with op.batch_alter_table("signal_definition") as batch_op:
        batch_op.alter_column("target_scopes", nullable=False)
