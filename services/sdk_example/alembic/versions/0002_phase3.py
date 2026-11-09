"""Tasks table.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("owner_user_id", sa.String(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("assigned_user_id", sa.String(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("due_time", sa.String(length=5), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("completed_by", sa.String(), nullable=True),
        sa.Column("checklist", sa.JSON(), nullable=False),
        sa.Column("remind_minutes_before", sa.Integer(), nullable=False),
        sa.Column("remind_at", sa.DateTime(), nullable=True),
        sa.Column("reminded_at", sa.DateTime(), nullable=True),
        sa.Column("mirror_enabled", sa.Boolean(), nullable=False),
        sa.Column("mirror_status", sa.String(), nullable=False),
        sa.Column("external_provider", sa.String(), nullable=True),
        sa.Column("external_event_id", sa.String(), nullable=True),
        sa.Column("external_account_user_id", sa.String(), nullable=True),
        sa.Column("external_etag", sa.String(), nullable=True),
        sa.Column("links", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tasks_owner_user_id", "tasks", ["owner_user_id"], unique=False)
    op.create_index("ix_tasks_assigned_user_id", "tasks", ["assigned_user_id"], unique=False)
    op.create_index("ix_tasks_due_date", "tasks", ["due_date"], unique=False)
    op.create_index("ix_tasks_owner_status_due", "tasks", ["owner_user_id", "status", "due_date"], unique=False)
    op.create_index("ix_tasks_assignee_status_due", "tasks", ["assigned_user_id", "status", "due_date"], unique=False)


def downgrade() -> None:
    op.drop_table("tasks")
