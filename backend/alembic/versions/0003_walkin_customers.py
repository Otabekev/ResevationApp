"""walk-in customers: customers.telegram_id becomes nullable

Manual (walk-in / phone) bookings created by an owner have no Telegram
account. The previous code inserted telegram_id=0 for every walk-in, which
violated the unique constraint on the second manual booking and 500-ed.
NULL is the correct representation — Postgres permits multiple NULLs under
a UNIQUE constraint, so real Telegram ids stay unique while walk-ins are
unlimited.

Also repairs any telegram_id=0 placeholder row a previous build created.

Revision ID: 0003_walkin_customers
Revises: 0002_booking_constraints
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_walkin_customers"
down_revision = "0002_booking_constraints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "customers",
        "telegram_id",
        existing_type=sa.BigInteger(),
        nullable=True,
    )
    # Repair the legacy placeholder (at most one row can exist due to UNIQUE).
    op.execute("UPDATE customers SET telegram_id = NULL WHERE telegram_id = 0")


def downgrade() -> None:
    # Re-applying NOT NULL requires no NULLs. Keep one walk-in row as the
    # telegram_id=0 placeholder, repoint bookings of the others to it, then
    # remove them (bookings keep their customer_name/phone snapshot columns).
    op.execute(
        "UPDATE customers SET telegram_id = 0 "
        "WHERE telegram_id IS NULL AND id = ("
        "  SELECT min(id) FROM customers WHERE telegram_id IS NULL"
        ")"
    )
    op.execute(
        "UPDATE bookings SET customer_id = (SELECT id FROM customers WHERE telegram_id = 0) "
        "WHERE customer_id IN (SELECT id FROM customers WHERE telegram_id IS NULL)"
    )
    op.execute(
        "UPDATE reviews SET customer_id = (SELECT id FROM customers WHERE telegram_id = 0) "
        "WHERE customer_id IN (SELECT id FROM customers WHERE telegram_id IS NULL)"
    )
    op.execute("DELETE FROM customers WHERE telegram_id IS NULL")
    op.alter_column(
        "customers",
        "telegram_id",
        existing_type=sa.BigInteger(),
        nullable=False,
    )
