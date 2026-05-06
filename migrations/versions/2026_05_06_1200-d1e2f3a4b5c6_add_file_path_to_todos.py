"""add file_path to todos

Revision ID: d1e2f3a4b5c6
Revises: c9d0e1f2a3b4
Create Date: 2026-05-06 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "d1e2f3a4b5c6"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("todos", sa.Column("file_path", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("todos", "file_path")
