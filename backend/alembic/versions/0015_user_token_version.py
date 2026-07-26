"""users.token_version — a server-side kill switch for issued JWTs

Every access/refresh token now carries the user's token_version at mint time;
auth verification rejects a token whose version is stale. Bumping the column
(POST /auth/logout-all) invalidates every token issued before the bump WITHOUT
disabling the account — the token-level revocation that localStorage sessions
otherwise lacked.

Defaults to 0 so it is fully backward compatible: tokens minted before this
change carry no version claim, which verification reads as 0, matching the
column default — no existing session is logged out on deploy.

Revision ID: 0015_user_token_version
Revises: 0014_queue_entries
"""
import sqlalchemy as sa
from alembic import op

revision = "0015_user_token_version"
down_revision = "0014_queue_entries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("users", "token_version")
