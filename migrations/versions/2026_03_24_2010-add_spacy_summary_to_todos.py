"""add spacy summary to todos

Revision ID: a1f8d9b7c2e1
Revises: 2026_03_10_1725-495a3000934a
Create Date: 2026-03-24 20:10:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1f8d9b7c2e1"
down_revision: Union[str, None] = "495a3000934a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("todos", sa.Column("spacy_summary", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("todos", "spacy_summary")
