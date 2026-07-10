"""business photo: one storefront image per business

Adds:
- businesses.photo_updated_at — NULL = no photo; doubles as the cache-bust
  version baked into the public photo URL.
- business_photos — the raw (server-recompressed JPEG) bytes, kept in a separate
  table so ordinary business reads never drag the blob. ON DELETE CASCADE ties
  the photo's lifetime to its business.

Revision ID: 0010_business_photo
Revises: 0009_scale_indexes
"""
import sqlalchemy as sa
from alembic import op

revision = "0010_business_photo"
down_revision = "0009_scale_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "businesses",
        sa.Column("photo_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "business_photos",
        sa.Column(
            "business_id",
            sa.Integer(),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("content_type", sa.String(length=50), nullable=False, server_default="image/jpeg"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("business_photos")
    op.drop_column("businesses", "photo_updated_at")
