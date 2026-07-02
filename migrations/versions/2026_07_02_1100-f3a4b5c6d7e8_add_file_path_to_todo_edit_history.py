"""add file_path to todo_edit_history

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-07-02 11:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "f3a4b5c6d7e8"
down_revision = "e2f3a4b5c6d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "todo_edit_history",
        sa.Column("file_path", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("todo_edit_history", "file_path")
