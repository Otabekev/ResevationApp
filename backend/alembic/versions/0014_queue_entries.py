"""queue_entries — the live-queue (walk-in line) table

A row is one person's place in a doctor's line. Position/ETA are computed on
demand from joined_at ordering (no stored position to keep in sync).

Revision ID: 0014_queue_entries
Revises: 0013_scheduling_modes
"""
import sqlalchemy as sa
from alembic import op

revision = "0014_queue_entries"
down_revision = "0013_scheduling_modes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "queue_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("business_id", sa.Integer(), sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("staff_id", sa.Integer(), sa.ForeignKey("staff.id"), nullable=False),
        sa.Column("service_id", sa.Integer(), sa.ForeignKey("services.id"), nullable=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True),
        sa.Column("customer_name", sa.String(length=255), nullable=False),
        sa.Column("customer_phone", sa.String(length=20), nullable=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("language", sa.String(length=5), nullable=False, server_default="uz"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="waiting"),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("called_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notified_position", sa.Integer(), nullable=True),
        sa.Column("last_ping_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ping_misses", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_queue_entries_business_id", "queue_entries", ["business_id"])
    op.create_index("ix_queue_entries_staff_id", "queue_entries", ["staff_id"])
    op.create_index("ix_queue_entries_telegram_id", "queue_entries", ["telegram_id"])
    op.create_index("ix_queue_entries_status", "queue_entries", ["status"])
    op.create_index("ix_queue_entries_joined_at", "queue_entries", ["joined_at"])
    # The hot query: a doctor's waiting line in order.
    op.create_index("ix_queue_line", "queue_entries", ["staff_id", "status", "joined_at"])


def downgrade() -> None:
    op.drop_index("ix_queue_line", table_name="queue_entries")
    op.drop_index("ix_queue_entries_joined_at", table_name="queue_entries")
    op.drop_index("ix_queue_entries_status", table_name="queue_entries")
    op.drop_index("ix_queue_entries_telegram_id", table_name="queue_entries")
    op.drop_index("ix_queue_entries_staff_id", table_name="queue_entries")
    op.drop_index("ix_queue_entries_business_id", table_name="queue_entries")
    op.drop_table("queue_entries")
