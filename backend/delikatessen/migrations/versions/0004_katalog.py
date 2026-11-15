"""Katalog für Stufe 3: Lebensmittelgruppe, Dichte, Saison und Gewichte je Einheit

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-15 12:00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ingredient") as batch:
        batch.add_column(sa.Column("food_group", sa.String(length=20), nullable=True))
        batch.add_column(sa.Column("density", sa.Float(), nullable=True))
        batch.add_column(sa.Column("season_months", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("catalog_applied", sa.JSON(), nullable=True))
    op.create_table(
        "ingredient_unit_weight",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ingredient_id", sa.Integer(), nullable=False),
        sa.Column("unit", sa.String(length=20), nullable=False),
        sa.Column("grams", sa.Float(), nullable=False),
        sa.CheckConstraint("grams > 0", name="unit_weight_grams"),
        sa.ForeignKeyConstraint(["ingredient_id"], ["ingredient.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ingredient_id", "unit", name="uq_unit_weight"),
    )


def downgrade() -> None:
    op.drop_table("ingredient_unit_weight")
    with op.batch_alter_table("ingredient") as batch:
        batch.drop_column("catalog_applied")
        batch.drop_column("season_months")
        batch.drop_column("density")
        batch.drop_column("food_group")
