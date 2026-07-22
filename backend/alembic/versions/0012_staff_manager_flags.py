"""staff.can_manage + staff.is_provider — the secretary/desk-manager role

can_manage: a staff member linked to a user account who may manage this
business's dashboard (bookings/schedules/staff/services) without owning it.
is_provider: whether this staff appears as a bookable provider. A pure
secretary is can_manage=True, is_provider=False.

Both default to backwards-compatible values (existing staff: can_manage=False,
is_provider=True), so no existing behavior changes.

Revision ID: 0012_staff_manager_flags
Revises: 0011_allow_any_staff
"""
import sqlalchemy as sa
from alembic import op

revision = "0012_staff_manager_flags"
down_revision = "0011_allow_any_staff"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "staff",
        sa.Column("can_manage", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "staff",
        sa.Column("is_provider", sa.Boolean(), nullable=False, server_default="true"),
    )


def downgrade() -> None:
    op.drop_column("staff", "is_provider")
    op.drop_column("staff", "can_manage")
