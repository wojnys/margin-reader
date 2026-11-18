"""Conversation generation jobs and source-linked expression cards."""

import sqlalchemy as sa
from alembic import op

revision = "6a1d92cf41b0"
down_revision = "503679474f95"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("conversation_sets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("reading_sessions.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.UniqueConstraint("session_id", "revision"),
    )
    op.create_index("ix_conversation_sets_session_id", "conversation_sets", ["session_id"])
    op.create_table("conversation_expressions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("set_id", sa.String(36), sa.ForeignKey("conversation_sets.id"), nullable=False),
        sa.Column("source_index", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("set_id", "source_index"),
    )
    op.create_index("ix_conversation_expressions_set_id", "conversation_expressions", ["set_id"])


def downgrade():
    op.drop_table("conversation_expressions")
    op.drop_table("conversation_sets")
