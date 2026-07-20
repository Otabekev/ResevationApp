"""business.allow_any_staff — toggle the "Any available" booking choice

Default TRUE (barbers/interchangeable staff keep the current behavior). Clinics
set it FALSE so patients must pick a specific specialist and never get
auto-assigned across specialties.

Revision ID: 0011_allow_any_staff
Revises: 0010_business_photo
"""
import sqlalchemy as sa
from alembic import op

revision = "0011_allow_any_staff"
down_revision = "0010_business_photo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "businesses",
        sa.Column("allow_any_staff", sa.Boolean(), nullable=False, server_default="true"),
    )


def downgrade() -> None:
    op.drop_column("businesses", "allow_any_staff")
