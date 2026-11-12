"""Bring!-Kennungen an den Einträgen der Einkaufsliste

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-12 17:00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("shopping_item") as batch:
        batch.add_column(sa.Column("bring_uuid", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("bring_name", sa.String(length=200), nullable=True))
        batch.add_column(sa.Column("bring_spec", sa.String(length=200), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("shopping_item") as batch:
        batch.drop_column("bring_spec")
        batch.drop_column("bring_name")
        batch.drop_column("bring_uuid")
