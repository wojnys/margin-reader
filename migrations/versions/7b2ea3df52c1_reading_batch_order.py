"""Preserve selected order for a batch of photographed spreads."""

import sqlalchemy as sa
from alembic import op

revision = "7b2ea3df52c1"
down_revision = "6a1d92cf41b0"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("reading_sessions", sa.Column("batch_id", sa.String(36), nullable=True))
    op.add_column("reading_sessions", sa.Column("batch_position", sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table("reading_sessions") as batch:
        batch.drop_column("batch_position")
        batch.drop_column("batch_id")
