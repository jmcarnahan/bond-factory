"""E-signing: requests, signers and the append-only event log of bond_esign.

Revision ID: 0007
Revises: 0006

Three tables as the library's mixins declare them (`EsignRequestMixin`, `EsignSignerMixin`, `EsignEventMixin`;
the library's `tests/test_schema.py` is the pin). The downgrade drops them, evidence included: an app that signed
real documents archives the export first.
"""

import sqlalchemy as sa

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "esign_requests",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("subject_type", sa.String(), nullable=True),
        sa.Column("subject_id", sa.String(), nullable=True),
        sa.Column("document_sha256", sa.String(length=64), nullable=False),
        sa.Column("document_bytes", sa.Integer(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("consent_version", sa.String(), nullable=False),
        sa.Column("consent_language", sa.String(), nullable=False),
        sa.Column("consent_sha256", sa.String(length=64), nullable=False),
        sa.Column("consent_text", sa.Text(), nullable=False),
        sa.Column("policy", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("signed_sha256", sa.String(length=64), nullable=True),
        sa.Column("sealed", sa.Boolean(), nullable=False),
        sa.Column("timestamped", sa.Boolean(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("voided_at", sa.DateTime(), nullable=True),
        sa.Column("declined_at", sa.DateTime(), nullable=True),
        sa.Column("void_reason", sa.Text(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_esign_requests_subject", "esign_requests", ["subject_type", "subject_id"], unique=False)
    op.create_table(
        "esign_signers",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("request_id", sa.String(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("key", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("placement", sa.JSON(), nullable=True),
        sa.Column("date_placement", sa.JSON(), nullable=True),
        sa.Column("token_sha256", sa.String(length=64), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(), nullable=True),
        sa.Column("code_sha256", sa.String(length=64), nullable=True),
        sa.Column("code_expires_at", sa.DateTime(), nullable=True),
        sa.Column("code_sent_at", sa.DateTime(), nullable=True),
        sa.Column("code_verified_at", sa.DateTime(), nullable=True),
        sa.Column("code_attempts", sa.Integer(), nullable=False),
        sa.Column("method", sa.String(), nullable=True),
        sa.Column("witness", sa.String(), nullable=True),
        sa.Column("signature_kind", sa.String(), nullable=True),
        sa.Column("typed_name", sa.String(), nullable=True),
        sa.Column("signature_png", sa.LargeBinary(), nullable=True),
        sa.Column("signature_sha256", sa.String(length=64), nullable=True),
        sa.Column("signed_at", sa.DateTime(), nullable=True),
        sa.Column("ip", sa.String(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("decline_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["request_id"], ["esign_requests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id", "position", name="uq_esign_signers_request_position"),
        sa.UniqueConstraint("token_sha256"),
    )
    op.create_index("ix_esign_signers_request_id", "esign_signers", ["request_id"], unique=False)
    op.create_table(
        "esign_events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("request_id", sa.String(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("signer_id", sa.String(), nullable=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("at", sa.DateTime(), nullable=False),
        sa.Column("ip", sa.String(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("actor", sa.String(), nullable=True),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("prev_hash", sa.String(length=64), nullable=False),
        sa.Column("row_hash", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["request_id"], ["esign_requests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id", "seq", name="uq_esign_events_request_seq"),
    )


def downgrade() -> None:
    op.drop_table("esign_events")
    op.drop_index("ix_esign_signers_request_id", table_name="esign_signers")
    op.drop_table("esign_signers")
    op.drop_index("ix_esign_requests_subject", table_name="esign_requests")
    op.drop_table("esign_requests")
