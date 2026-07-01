"""booking duplicate guard + frozen price snapshot

Two data-integrity items that must land on clean pre-launch data:

- Idempotency for the "any available staff" booking path. The 0002 EXCLUDE
  constraint is keyed on staff_id, so a lost-response re-submit that gets a
  DIFFERENT auto-assigned staff would create a genuine duplicate for the same
  customer + slot. A partial unique index on (customer, business, date, start)
  over ACTIVE bookings rejects it — the existing IntegrityError→409 path already
  surfaces it cleanly to the bot as "slot taken".

- total_price_at_booking: freeze the price at booking time so a later service
  price change never rewrites what a past booking cost.

Postgres uses the partial WHERE clause; the app-level uniqueness is the same idea
the rest of the booking system relies on.

Revision ID: 0008_booking_dedup
Revises: 0007_broadcasts
"""
import sqlalchemy as sa
from alembic import op

revision = "0008_booking_dedup"
down_revision = "0007_broadcasts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "bookings",
        sa.Column("total_price_at_booking", sa.Numeric(10, 2), nullable=True),
    )
    # One active booking per (customer, business, date, start). Excludes
    # completed/cancelled/no_show (a customer can rebook the same slot later) and
    # walk-ins with no customer_id.
    op.execute(
        """
        CREATE UNIQUE INDEX uq_active_booking_customer_slot
        ON bookings (customer_id, business_id, booking_date, start_time)
        WHERE status IN ('pending', 'confirmed') AND customer_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_active_booking_customer_slot")
    op.drop_column("bookings", "total_price_at_booking")
