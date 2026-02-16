"""add run execution timestamps

Revision ID: 20260216_000002
Revises: 20260216_000001
Create Date: 2026-02-16 00:00:02
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260216_000002"
down_revision: Union[str, Sequence[str], None] = "20260216_000001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("runs", sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "finished_at")
    op.drop_column("runs", "started_at")
