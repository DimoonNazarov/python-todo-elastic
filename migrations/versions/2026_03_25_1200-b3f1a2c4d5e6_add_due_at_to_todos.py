"""add due_at to todos

Revision ID: b3f1a2c4d5e6
Revises: 495a3000934a
Create Date: 2026-03-25 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b3f1a2c4d5e6'
down_revision: Union[str, None] = '495a3000934a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('todos', sa.Column('due_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('todos', 'due_at')
