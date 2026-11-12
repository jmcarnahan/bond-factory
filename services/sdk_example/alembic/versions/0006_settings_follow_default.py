"""Task settings: the work day and the lead time may be NULL, meaning "follow the app default".

Revision ID: 0006
Revises: 0005

`start_of_day`, `end_of_day` and `lead_minutes` of `task_user_settings` become nullable, with no server default
(`time_zone` already was). A stored value is the person's own choice; NULL is "not set", and the app's default work day
applies (`SDK_EXAMPLE_START_OF_DAY`, `_END_OF_DAY`, `_LEAD_MINUTES`). Every existing row stored all three values, so a stored value equal to the old constant (08:00, 17:00, 60) is set to NULL:
it was a default, not a choice, and would otherwise read as overridden forever. Other values are kept as the person's own.
The downgrade fills each NULL with the old constants (08:00, 17:00, 60) before it restores NOT NULL.
"""

import sqlalchemy as sa

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

COLUMNS = (
    ("start_of_day", sa.String(length=5), "'08:00'"),
    ("end_of_day", sa.String(length=5), "'17:00'"),
    ("lead_minutes", sa.Integer(), "60"),
)


def upgrade() -> None:
    with op.batch_alter_table("task_user_settings", schema=None) as batch_op:
        for name, kind, _ in COLUMNS:
            batch_op.alter_column(name, existing_type=kind, nullable=True, server_default=None)
    for name, _, constant in COLUMNS:
        op.execute(sa.text(f"UPDATE task_user_settings SET {name} = NULL WHERE {name} = {constant}"))


def downgrade() -> None:
    for name, _, fill in COLUMNS:
        op.execute(sa.text(f"UPDATE task_user_settings SET {name} = {fill} WHERE {name} IS NULL"))
    with op.batch_alter_table("task_user_settings", schema=None) as batch_op:
        for name, kind, _ in COLUMNS:
            batch_op.alter_column(name, existing_type=kind, nullable=False)
