"""staff.is_owner — owner acting as a bookable provider

Adds a flag marking the one Staff record that represents the business owner
working as a provider (auto-linked to the owner's account, no invite). Existing
rows default to false. Reversible.

Revision ID: 0005_staff_is_owner
Revises: 0004_hide_retired_categories
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_staff_is_owner"
down_revision = "0004_hide_retired_categories"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "staff",
        sa.Column("is_owner", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("staff", "is_owner")
