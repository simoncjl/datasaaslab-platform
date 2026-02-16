"""batch pipeline schema

Revision ID: 20260216_000003
Revises: 20260216_000002
Create Date: 2026-02-16 00:00:03
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260216_000003"
down_revision: Union[str, Sequence[str], None] = "20260216_000002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


batch_status = sa.Enum("queued", "running", "succeeded", "failed", name="batch_status")


def upgrade() -> None:
    op.add_column("batches", sa.Column("model", sa.String(length=255), nullable=True))
    op.drop_constraint("batches_run_id_fkey", "batches", type_="foreignkey")
    op.drop_column("batches", "run_id")

    op.create_table(
        "batch_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("topic_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("custom_id", sa.String(length=255), nullable=False),
        sa.Column("status", batch_status, nullable=False, server_default=sa.text("'queued'")),
        sa.Column("response_code", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["batch_id"], ["batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_batch_items_batch_id", "batch_items", ["batch_id"], unique=False)
    op.create_index("ix_batch_items_run_id", "batch_items", ["run_id"], unique=False)
    op.create_index("ix_batch_items_topic_id", "batch_items", ["topic_id"], unique=False)
    op.create_index("ix_batch_items_custom_id", "batch_items", ["custom_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_batch_items_custom_id", table_name="batch_items")
    op.drop_index("ix_batch_items_topic_id", table_name="batch_items")
    op.drop_index("ix_batch_items_run_id", table_name="batch_items")
    op.drop_index("ix_batch_items_batch_id", table_name="batch_items")
    op.drop_table("batch_items")

    op.add_column("batches", sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False))
    op.create_foreign_key("batches_run_id_fkey", "batches", "runs", ["run_id"], ["id"], ondelete="CASCADE")
    op.drop_column("batches", "model")
