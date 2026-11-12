"""TODO checklist: settings, link index, notice ledger and outbox, inbox, push devices; the old reminder columns go.

Revision ID: 0005
Revises: 0004

Six tables as the libs' mixins declare them (the `*_COLUMNS` constants are the pin). `tasks.remind_at` and
`tasks.reminded_at` are dropped: the sweep replaces the single queued reminder. Pending reminder jobs of the old
kind are not touched here; the job table only holds rows an old worker would no longer find a handler for.
"""

import sqlalchemy as sa

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_user_settings",
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("time_zone", sa.String(length=64), nullable=True),
        sa.Column("start_of_day", sa.String(length=5), nullable=False),
        sa.Column("end_of_day", sa.String(length=5), nullable=False),
        sa.Column("lead_minutes", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "task_link_index",
        sa.Column("task_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("ref_id", sa.String(length=128), nullable=False),
        sa.PrimaryKeyConstraint("task_id", "kind", "ref_id"),
    )
    op.create_index("ix_task_link_ref", "task_link_index", ["kind", "ref_id", "task_id"], unique=False)
    op.create_table(
        "task_notice_ledger",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("task_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("stage", sa.String(length=8), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("deadline_token", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.Column("stage_at", sa.DateTime(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("claimed_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "user_id", "stage", "seq", "deadline_token", name="uq_task_notice_ledger_key"),
    )
    op.create_index("ix_task_notice_ledger_task_id", "task_notice_ledger", ["task_id"], unique=False)
    op.create_index("ix_task_notice_ledger_claimed_at", "task_notice_ledger", ["claimed_at"], unique=False)
    op.create_table(
        "task_notice_outbox",
        sa.Column("ledger_id", sa.String(length=32), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.Column("failed_at", sa.DateTime(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("lease_until", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("ledger_id", "channel"),
    )
    op.create_index("ix_task_notice_outbox_pending", "task_notice_outbox",
                    ["failed_at", "delivered_at", "lease_until"], unique=False)
    op.create_table(
        "notices",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("source_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notices_user_created", "notices", ["user_id", "created_at"], unique=False)
    op.create_index("ix_notices_source_id", "notices", ["source_id"], unique=False)
    op.create_table(
        "push_devices",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("token", sa.String(length=255), nullable=False),
        sa.Column("platform", sa.String(length=8), nullable=False),
        sa.Column("environment", sa.String(length=12), nullable=False),
        sa.Column("topic", sa.String(length=255), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("disabled_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "device_id", name="uq_push_devices_user_device"),
        sa.UniqueConstraint("token"),
    )
    op.create_index("ix_push_devices_user_id", "push_devices", ["user_id"], unique=False)
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.drop_column("remind_at")
        batch_op.drop_column("reminded_at")


def downgrade() -> None:
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.add_column(sa.Column("remind_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("reminded_at", sa.DateTime(), nullable=True))
    op.drop_table("push_devices")
    op.drop_table("notices")
    op.drop_table("task_notice_outbox")
    op.drop_table("task_notice_ledger")
    op.drop_table("task_link_index")
    op.drop_table("task_user_settings")
