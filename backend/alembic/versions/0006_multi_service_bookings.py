"""multi-service bookings: business toggle + booking_services link table

Adds businesses.allow_multi_service (default false) and a booking_services
association table so one booking can reference several services. Additive and
reversible; the single-service path is unchanged (it just has one link row).

Revision ID: 0006_multi_service_bookings
Revises: 0005_staff_is_owner
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_multi_service_bookings"
down_revision = "0005_staff_is_owner"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "businesses",
        sa.Column("allow_multi_service", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "booking_services",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("booking_id", sa.Integer(), sa.ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("service_id", sa.Integer(), sa.ForeignKey("services.id"), nullable=False),
        sa.UniqueConstraint("booking_id", "service_id", name="uq_booking_service"),
    )
    op.create_index("ix_booking_services_booking_id", "booking_services", ["booking_id"])
    op.create_index("ix_booking_services_service_id", "booking_services", ["service_id"])


def downgrade() -> None:
    op.drop_index("ix_booking_services_service_id", table_name="booking_services")
    op.drop_index("ix_booking_services_booking_id", table_name="booking_services")
    op.drop_table("booking_services")
    op.drop_column("businesses", "allow_multi_service")
