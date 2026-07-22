"""consult-first service flags + per-provider scheduling mode

- services.online_bookable (default true): OFF hides a service from self-booking
  (staff-scheduled only, e.g. multi-day treatment).
- services.max_per_day (nullable): cap self-bookings/day for a service (checkup).
- staff.scheduling_mode (default 'appointments'): 'appointments' | 'queue'.
- staff.queue_avg_minutes (default 15): avg minutes per patient for ETA.

All backwards-compatible defaults, so existing businesses are unchanged.

Revision ID: 0013_scheduling_modes
Revises: 0012_staff_manager_flags
"""
import sqlalchemy as sa
from alembic import op

revision = "0013_scheduling_modes"
down_revision = "0012_staff_manager_flags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("services", sa.Column("online_bookable", sa.Boolean(), nullable=False, server_default="true"))
    op.add_column("services", sa.Column("max_per_day", sa.Integer(), nullable=True))
    op.add_column("staff", sa.Column("scheduling_mode", sa.String(length=20), nullable=False, server_default="appointments"))
    op.add_column("staff", sa.Column("queue_avg_minutes", sa.Integer(), nullable=False, server_default="15"))


def downgrade() -> None:
    op.drop_column("staff", "queue_avg_minutes")
    op.drop_column("staff", "scheduling_mode")
    op.drop_column("services", "max_per_day")
    op.drop_column("services", "online_bookable")
