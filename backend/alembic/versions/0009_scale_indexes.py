"""scale indexes: business browse + customer history + growth feed

Composite / support indexes for hot read paths that lacked one:
- businesses (district, status) and (category_id, status): the public browse
  filters + name sort (C7).
- bookings (customer_id, booking_date): the "my bookings" history sort.
- bookings (created_at): the investor growth feed's per-day aggregation (C4).

Index-only migration; safe to apply on live data (small at launch).

Revision ID: 0009_scale_indexes
Revises: 0008_booking_dedup
"""
from alembic import op

revision = "0009_scale_indexes"
down_revision = "0008_booking_dedup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_businesses_district_status", "businesses", ["district", "status"])
    op.create_index("ix_businesses_category_status", "businesses", ["category_id", "status"])
    op.create_index("ix_bookings_customer_date", "bookings", ["customer_id", "booking_date"])
    op.create_index("ix_bookings_created_at", "bookings", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_bookings_created_at", table_name="bookings")
    op.drop_index("ix_bookings_customer_date", table_name="bookings")
    op.drop_index("ix_businesses_category_status", table_name="businesses")
    op.drop_index("ix_businesses_district_status", table_name="businesses")
