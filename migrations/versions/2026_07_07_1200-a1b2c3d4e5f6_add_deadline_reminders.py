"""add deadline reminders

Revision ID: a1b2c3d4e5f6
Revises: f3a4b5c6d7e8
Create Date: 2026-07-07 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "a1b2c3d4e5f6"
down_revision = "f3a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "todos",
        sa.Column("reminder_sent", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column(
        "notifications",
        "comment_id",
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "notifications",
        "comment_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.drop_column("todos", "reminder_sent")