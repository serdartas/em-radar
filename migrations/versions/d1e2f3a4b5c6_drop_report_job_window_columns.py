"""drop report_job window_type/window_start/window_end columns

These three columns were populated at job-enqueue time but never read anywhere —
ReportJobResponse omits them and the runner passes the window directly as an argument.
Removing them keeps the schema in sync with the model.

Revision ID: d1e2f3a4b5c6
Revises: b4c5d6e7f8a9
Create Date: 2026-08-20 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, Sequence[str], None] = "b4c5d6e7f8a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("report_job") as batch_op:
        batch_op.drop_column("window_type")
        batch_op.drop_column("window_start")
        batch_op.drop_column("window_end")


def downgrade() -> None:
    with op.batch_alter_table("report_job") as batch_op:
        batch_op.add_column(sa.Column("window_end", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("window_start", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("window_type", sa.String(), nullable=True))
