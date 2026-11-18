"""Saved book chats and durable source snapshots per turn."""

import sqlalchemy as sa
from alembic import op

revision = "8c3fb4e063d2"
down_revision = "7b2ea3df52c1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("chat_threads",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("book_id", sa.String(36), sa.ForeignKey("books.id"), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("language", sa.String(2), nullable=False),
        sa.Column("active_turn_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_chat_threads_book_id", "chat_threads", ["book_id"])
    op.create_table("chat_turns",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("thread_id", sa.String(36), sa.ForeignKey("chat_threads.id"), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("answer", sa.JSON(), nullable=True),
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("source_count", sa.Integer(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(200), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_cost", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("thread_id", "request_id"),
    )
    op.create_index("ix_chat_turns_thread_id", "chat_turns", ["thread_id"])


def downgrade():
    op.drop_table("chat_turns")
    op.drop_table("chat_threads")
