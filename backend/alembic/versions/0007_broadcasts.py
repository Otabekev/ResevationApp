"""broadcasts: super-admin announcements sent to bot users

Adds a single `broadcasts` table that records each announcement (text, chosen
audience, schedule, and live delivery counters). Purely additive — touches
nothing in the booking path.

Revision ID: 0007_broadcasts
Revises: 0006_multi_service_bookings
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_broadcasts"
down_revision = "0006_multi_service_bookings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "broadcasts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column(
            "audience",
            sa.Enum("all", "owners_staff", "customers", name="broadcast_audience"),
            nullable=False,
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("scheduled", "sending", "done", "cancelled", name="broadcast_status"),
            nullable=False,
            server_default="scheduled",
            index=True,
        ),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_recipients", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sent_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("broadcasts")
    sa.Enum(name="broadcast_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="broadcast_audience").drop(op.get_bind(), checkfirst=True)
