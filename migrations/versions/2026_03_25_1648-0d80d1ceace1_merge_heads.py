"""merge heads

Revision ID: 0d80d1ceace1
Revises: a1f8d9b7c2e1, c4d5e6f7a8b9
Create Date: 2026-03-25 16:48:44.854871

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0d80d1ceace1'
down_revision: Union[str, None] = ('a1f8d9b7c2e1', 'c4d5e6f7a8b9')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
