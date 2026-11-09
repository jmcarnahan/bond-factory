"""Direct sign-in: identity binding and the break-glass flag on users, refresh sessions, native hand-offs.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("oauth_handoffs",
    sa.Column("id", sa.String(), nullable=False),
    sa.Column("code_hash", sa.String(length=64), nullable=False),
    sa.Column("device_hash", sa.String(length=64), nullable=False),
    sa.Column("purpose", sa.String(length=16), nullable=False),
    sa.Column("provider", sa.String(), nullable=False),
    sa.Column("attempt_id", sa.String(length=64), nullable=True),
    sa.Column("payload_enc", sa.Text(), nullable=False),
    sa.Column("created_at", sa.DateTime(), nullable=False),
    sa.Column("expires_at", sa.DateTime(), nullable=False),
    sa.Column("used_at", sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint("code_hash")
    )
    with op.batch_alter_table("oauth_handoffs", schema=None) as batch_op:
        batch_op.create_index("ix_oauth_handoffs_expires_at", ["expires_at"], unique=False)

    op.create_table("auth_sessions",
    sa.Column("id", sa.String(), nullable=False),
    sa.Column("family_id", sa.String(), nullable=False),
    sa.Column("token_hash", sa.String(length=43), nullable=False),
    sa.Column("parent_id", sa.String(), nullable=True),
    sa.Column("provider", sa.String(length=16), nullable=False),
    sa.Column("auth_time", sa.DateTime(), nullable=False),
    sa.Column("family_expires_at", sa.DateTime(), nullable=True),
    sa.Column("expires_at", sa.DateTime(), nullable=False),
    sa.Column("created_at", sa.DateTime(), nullable=False),
    sa.Column("last_used_at", sa.DateTime(), nullable=True),
    sa.Column("rotated_at", sa.DateTime(), nullable=True),
    sa.Column("revoked_at", sa.DateTime(), nullable=True),
    sa.Column("revoke_reason", sa.String(length=16), nullable=True),
    sa.Column("device_label", sa.String(length=80), nullable=True),
    sa.Column("rotation_id", sa.String(length=64), nullable=True),
    sa.Column("last_probed_at", sa.DateTime(), nullable=True),
    sa.Column("user_id", sa.String(), nullable=False),
    sa.ForeignKeyConstraint(["user_id"], ["users.id"], ),
    sa.PrimaryKeyConstraint("id")
    )
    with op.batch_alter_table("auth_sessions", schema=None) as batch_op:
        batch_op.create_index("ix_auth_sessions_expires_at", ["expires_at"], unique=False)
        batch_op.create_index("ix_auth_sessions_family_id", ["family_id"], unique=False)
        batch_op.create_index("ix_auth_sessions_user_revoked", ["user_id", "revoked_at"], unique=False)
        batch_op.create_index("uq_auth_sessions_token_hash", ["token_hash"], unique=True)

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("identity_provider", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("identity_subject", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("allow_password", sa.Boolean(), server_default=sa.false(), nullable=False))
        batch_op.create_unique_constraint("uq_users_identity", ["identity_provider", "identity_subject"])

    # Dev databases made before this revision: the fake seed owner becomes the break-glass row. Matches only the
    # seeded demo row (id AND e-mail), so a real database is untouched. `rm out/*.db` is the simpler path.
    op.get_bind().execute(sa.text("UPDATE users SET allow_password = :yes WHERE id = 'demo-user-1' "
                                  "AND email = 'demo@example.com'"), {"yes": True})



def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_constraint("uq_users_identity", type_="unique")
        batch_op.drop_column("allow_password")
        batch_op.drop_column("identity_subject")
        batch_op.drop_column("identity_provider")

    with op.batch_alter_table("auth_sessions", schema=None) as batch_op:
        batch_op.drop_index("uq_auth_sessions_token_hash")
        batch_op.drop_index("ix_auth_sessions_user_revoked")
        batch_op.drop_index("ix_auth_sessions_family_id")
        batch_op.drop_index("ix_auth_sessions_expires_at")

    op.drop_table("auth_sessions")
    with op.batch_alter_table("oauth_handoffs", schema=None) as batch_op:
        batch_op.drop_index("ix_oauth_handoffs_expires_at")

    op.drop_table("oauth_handoffs")
