"""add new tables

Revision ID: 796573c30868
Revises: e50af0fcd9cc
Create Date: 2026-03-03 22:01:10.950864

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "796573c30868"
down_revision: Union[str, None] = "e50af0fcd9cc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:

    # === 1. Сначала создаем Enum тип ===
    sa.Enum("ADMIN", "EDITOR", "VIEWER", name="userrole").create(
        op.get_bind(), checkfirst=True
    )

    # === 2. Теперь создаем таблицы и добавляем колонки ===
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("refresh_token", sa.String(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("revoked", sa.Boolean(), nullable=False),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        op.f("ix_refresh_tokens_id"), "refresh_tokens", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_refresh_tokens_refresh_token"),
        "refresh_tokens",
        ["refresh_token"],
        unique=False,
    )

    # Добавляем колонки в users
    op.add_column("users", sa.Column("email", sa.String(), nullable=False))
    op.add_column("users", sa.Column("hashed_password", sa.String(), nullable=False))
    op.add_column("users", sa.Column("first_name", sa.String(), nullable=False))
    op.add_column("users", sa.Column("last_name", sa.String(), nullable=False))

    # Используем уже созданный Enum
    op.add_column(
        "users",
        sa.Column(
            "role",
            sa.Enum("ADMIN", "EDITOR", "VIEWER", name="userrole"),
            nullable=False,
        ),
    )

    op.add_column("users", sa.Column("is_active", sa.Boolean(), nullable=False))
    op.add_column(
        "users",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.add_column(
        "users", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_index(op.f("ix_users_id"), "users", ["id"], unique=False)

    # Удаляем старые колонки
    op.drop_column("users", "password")
    op.drop_column("users", "name")
    op.drop_column("users", "disabled")
    # 🔥 ВАЖНО: Здесь НЕ должно быть строки с sa.Enum(...).drop(...) !!!


def downgrade() -> None:
    # 1. Возвращаем старые колонки
    op.add_column(
        "users",
        sa.Column("disabled", sa.BOOLEAN(), autoincrement=False, nullable=False),
    )
    op.add_column(
        "users", sa.Column("name", sa.VARCHAR(), autoincrement=False, nullable=False)
    )
    op.add_column(
        "users",
        sa.Column("password", sa.VARCHAR(), autoincrement=False, nullable=False),
    )

    # 2. Удаляем индексы и новые колонки (которые зависят от типа)
    op.drop_index(op.f("ix_users_id"), table_name="users")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_column("users", "updated_at")
    op.drop_column("users", "created_at")
    op.drop_column("users", "is_active")
    op.drop_column("users", "role")  # <-- Удаляем колонку, которая использует тип
    op.drop_column("users", "last_name")
    op.drop_column("users", "first_name")
    op.drop_column("users", "hashed_password")
    op.drop_column("users", "email")

    # 3. Удаляем таблицу refresh_tokens
    op.drop_index(op.f("ix_refresh_tokens_refresh_token"), table_name="refresh_tokens")
    op.drop_index(op.f("ix_refresh_tokens_id"), table_name="refresh_tokens")
    op.drop_table("refresh_tokens")

    # 4. В самом конце удаляем Enum тип (уже ничего не зависит)
    sa.Enum(name="userrole").drop(op.get_bind(), checkfirst=True)
