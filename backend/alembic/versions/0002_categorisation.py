"""Categorisation: rules, learned merchant memory, provenance columns.

Revision ID: 0002_categorisation
Revises: 0001_initial_ledger
Create Date: 2026-11-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_categorisation"
down_revision: str | None = "0001_initial_ledger"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "category_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("pattern", sa.String(length=120), nullable=False),
        sa.Column("match_type", sa.String(length=16), nullable=False),
        sa.Column("field", sa.String(length=16), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("origin", sa.String(length=16), nullable=False),
        sa.Column("is_transfer", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "user_id", "origin", "pattern", "match_type", "field",
            name="uq_category_rules_user_identity",
        ),
    )
    op.create_index("ix_category_rules_user_active", "category_rules", ["user_id", "is_active"])
    op.create_index("ix_category_rules_category_id", "category_rules", ["category_id"])

    op.create_table(
        "merchant_memory",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("merchant_norm", sa.String(length=160), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("hits", sa.Integer(), nullable=False),
        sa.Column(
            "last_confirmed_at", sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "user_id", "merchant_norm", name="uq_merchant_memory_user_merchant"
        ),
    )
    op.create_index("ix_merchant_memory_category_id", "merchant_memory", ["category_id"])

    # SQLite cannot add a foreign key to an existing table, so batch mode
    # recreates it (Postgres gets plain ALTER TABLE).
    with op.batch_alter_table("transactions") as batch:
        batch.add_column(sa.Column("category_rule_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_transactions_category_rule",
            "category_rules",
            ["category_rule_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_transactions_category_rule_id", ["category_rule_id"])
        batch.create_index("ix_transactions_user_source", ["user_id", "category_source"])


def downgrade() -> None:
    with op.batch_alter_table("transactions") as batch:
        batch.drop_index("ix_transactions_user_source")
        batch.drop_index("ix_transactions_category_rule_id")
        batch.drop_constraint("fk_transactions_category_rule", type_="foreignkey")
        batch.drop_column("category_rule_id")

    op.drop_index("ix_merchant_memory_category_id", table_name="merchant_memory")
    op.drop_table("merchant_memory")
    op.drop_index("ix_category_rules_category_id", table_name="category_rules")
    op.drop_index("ix_category_rules_user_active", table_name="category_rules")
    op.drop_table("category_rules")
