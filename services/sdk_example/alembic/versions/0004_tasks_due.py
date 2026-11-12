"""Tasks: priority, the due instant and its index.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.add_column(sa.Column("priority", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("due_at", sa.DateTime(), nullable=True))
        batch_op.create_index("ix_tasks_status_due_at", ["status", "due_at"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.drop_index("ix_tasks_status_due_at")
        batch_op.drop_column("due_at")
        batch_op.drop_column("priority")
