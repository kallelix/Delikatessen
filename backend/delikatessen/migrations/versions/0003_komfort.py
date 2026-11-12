"""Verbrauchen-Auswahl je Woche und Push-Abonnements

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-12 19:00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("plan_week") as batch:
        batch.add_column(sa.Column("use_up", sa.JSON(), nullable=True))
    op.create_table(
        "push_subscription",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("endpoint", sa.String(length=1000), nullable=False),
        sa.Column("p256dh", sa.String(length=200), nullable=False),
        sa.Column("auth", sa.String(length=100), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("endpoint"),
    )


def downgrade() -> None:
    op.drop_table("push_subscription")
    with op.batch_alter_table("plan_week") as batch:
        batch.drop_column("use_up")
