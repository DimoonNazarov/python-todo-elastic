"""make tag nullable

Revision ID: c4d5e6f7a8b9
Revises: b3f1a2c4d5e6
Create Date: 2026-03-25 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, None] = 'b3f1a2c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('todos', 'tag', nullable=True, existing_type=sa.String())


def downgrade() -> None:
    op.execute("UPDATE todos SET tag = 'Планы' WHERE tag IS NULL")
    op.alter_column('todos', 'tag', nullable=False, existing_type=sa.String())
