"""merge telegram_chat_id and deadline reminders heads

Revision ID: 5fdd56f7a79f
Revises: a5b6c7d8e9f0, a1b2c3d4e5f6
Create Date: 2026-07-08 08:13:08.925656

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5fdd56f7a79f'
down_revision: Union[str, None] = ('a5b6c7d8e9f0', 'a1b2c3d4e5f6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
