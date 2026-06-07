"""booking exclusion constraint + composite indexes + staff_services unique

Closes AUDIT findings D2 (no DB-level overlap guard), E3 (missing composite
indexes for the hot availability/list queries), D7 (duplicate staff_services).

Postgres-specific (btree_gist EXCLUDE). Safe on a fresh DB; if existing data
already contains overlapping bookings for one staff member, the constraint
creation will fail — clean those rows first (this is intentional: they are bugs).

Revision ID: 0002_booking_constraints
Revises: 0001_initial
"""
from alembic import op

revision = "0002_booking_constraints"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── D2: make double-booking structurally impossible ──────────────────────
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute(
        """
        ALTER TABLE bookings
        ADD CONSTRAINT no_overlapping_bookings
        EXCLUDE USING gist (
            staff_id WITH =,
            tsrange(
                (booking_date + start_time),
                (booking_date + end_time)
            ) WITH &&
        )
        WHERE (status IN ('pending', 'confirmed') AND staff_id IS NOT NULL)
        """
    )

    # ── E3: composite indexes for the hot queries ───────────────────────────
    op.create_index(
        "ix_bookings_staff_date_status",
        "bookings",
        ["staff_id", "booking_date", "status"],
    )
    op.create_index(
        "ix_bookings_business_date",
        "bookings",
        ["business_id", "booking_date"],
    )

    # ── D7: a staff member can't be linked to the same service twice ─────────
    op.create_unique_constraint(
        "uq_staff_services_staff_service",
        "staff_services",
        ["staff_id", "service_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_staff_services_staff_service", "staff_services", type_="unique")
    op.drop_index("ix_bookings_business_date", "bookings")
    op.drop_index("ix_bookings_staff_date_status", "bookings")
    op.execute("ALTER TABLE bookings DROP CONSTRAINT IF EXISTS no_overlapping_bookings")
