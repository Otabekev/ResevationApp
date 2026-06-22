"""hide retired business categories (photographer, car wash)

For the launch we pull "Fotograf" and "Avto myjka" from the category picker.
We hide (is_active = false) rather than delete, so any business already on
those categories — and its bookings — stay intact, and they can be brought
back later. The /businesses/categories endpoint only returns is_active rows,
so they drop out of both the owner setup picker and the customer booking flow.

Idempotent: a fresh DB seeded without these slugs simply matches 0 rows.
Mirrors RETIRED_SLUGS in scripts/seed_categories.py.

Revision ID: 0004_hide_retired_categories
Revises: 0003_walkin_customers
"""
from alembic import op

revision = "0004_hide_retired_categories"
down_revision = "0003_walkin_customers"
branch_labels = None
depends_on = None

_RETIRED_SLUGS = "('photographer', 'car_wash')"


def upgrade() -> None:
    op.execute(f"UPDATE business_categories SET is_active = false WHERE slug IN {_RETIRED_SLUGS}")


def downgrade() -> None:
    op.execute(f"UPDATE business_categories SET is_active = true WHERE slug IN {_RETIRED_SLUGS}")
