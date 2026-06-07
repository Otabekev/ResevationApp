"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-15
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Enums ────────────────────────────────────────────────────────────────
    op.execute("CREATE TYPE user_role AS ENUM ('super_admin', 'business_owner', 'staff', 'customer')")
    op.execute("CREATE TYPE business_status AS ENUM ('pending', 'active', 'trial', 'suspended', 'blocked')")
    op.execute("CREATE TYPE booking_status AS ENUM ('pending', 'confirmed', 'completed', 'cancelled_by_customer', 'cancelled_by_business', 'no_show', 'rescheduled')")
    op.execute("CREATE TYPE subscription_plan AS ENUM ('trial', 'basic', 'premium')")

    # ── users ────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), unique=True, nullable=True),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("username", sa.String(100), nullable=True),
        sa.Column("hashed_password", sa.String(255), nullable=True),
        sa.Column("role", sa.Enum("super_admin", "business_owner", "staff", "customer", name="user_role", create_type=False), nullable=False, server_default="customer"),
        sa.Column("language", sa.String(5), server_default="uz"),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"])

    # ── business_categories ──────────────────────────────────────────────────
    op.create_table(
        "business_categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(50), unique=True, nullable=False),
        sa.Column("name_uz", sa.String(100), nullable=False),
        sa.Column("name_ru", sa.String(100), nullable=False),
        sa.Column("name_en", sa.String(100), nullable=False),
        sa.Column("icon", sa.String(50), nullable=True),
        sa.Column("description_uz", sa.Text(), nullable=True),
        sa.Column("description_ru", sa.Text(), nullable=True),
        sa.Column("description_en", sa.Text(), nullable=True),
        sa.Column("default_slot_step_minutes", sa.Integer(), server_default="15"),
        sa.Column("sort_order", sa.Integer(), server_default="0"),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
    )

    # ── businesses ───────────────────────────────────────────────────────────
    op.create_table(
        "businesses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("business_categories.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), unique=True, nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("region", sa.String(100), server_default="Namangan"),
        sa.Column("district", sa.String(100), server_default="Pop"),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("address", sa.String(500), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("telegram_username", sa.String(100), nullable=True),
        sa.Column("instagram_link", sa.String(255), nullable=True),
        sa.Column("status", sa.Enum("pending", "active", "trial", "suspended", "blocked", name="business_status", create_type=False), nullable=False, server_default="pending"),
        sa.Column("is_online_booking_enabled", sa.Boolean(), server_default="true"),
        sa.Column("min_advance_booking_minutes", sa.Integer(), server_default="60"),
        sa.Column("max_advance_booking_days", sa.Integer(), server_default="30"),
        sa.Column("cancellation_policy_hours", sa.Integer(), server_default="2"),
        sa.Column("slot_step_minutes", sa.Integer(), server_default="15"),
        sa.Column("custom_message_uz", sa.Text(), nullable=True),
        sa.Column("custom_message_ru", sa.Text(), nullable=True),
        sa.Column("custom_message_en", sa.Text(), nullable=True),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_businesses_owner_id", "businesses", ["owner_id"])
    op.create_index("ix_businesses_status", "businesses", ["status"])

    # ── services ─────────────────────────────────────────────────────────────
    op.create_table(
        "services",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("business_id", sa.Integer(), sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("name_uz", sa.String(255), nullable=False),
        sa.Column("name_ru", sa.String(255), nullable=False),
        sa.Column("name_en", sa.String(255), nullable=False),
        sa.Column("description_uz", sa.Text(), nullable=True),
        sa.Column("description_ru", sa.Text(), nullable=True),
        sa.Column("description_en", sa.Text(), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("buffer_before_minutes", sa.Integer(), server_default="0"),
        sa.Column("buffer_after_minutes", sa.Integer(), server_default="0"),
        sa.Column("price", sa.Numeric(10, 2), nullable=True),
        sa.Column("currency", sa.String(5), server_default="UZS"),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("requires_confirmation", sa.Boolean(), server_default="false"),
        sa.Column("sort_order", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_services_business_id", "services", ["business_id"])

    # ── staff ────────────────────────────────────────────────────────────────
    op.create_table(
        "staff",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("business_id", sa.Integer(), sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("role", sa.String(20), server_default="staff"),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("can_set_own_hours", sa.Boolean(), server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_staff_business_id", "staff", ["business_id"])
    op.create_index("ix_staff_user_id", "staff", ["user_id"])

    # ── staff_invites ────────────────────────────────────────────────────────
    op.create_table(
        "staff_invites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("business_id", sa.Integer(), sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("staff_id", sa.Integer(), sa.ForeignKey("staff.id"), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token", sa.String(64), unique=True, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_staff_invites_token", "staff_invites", ["token"])

    # ── staff_services ───────────────────────────────────────────────────────
    op.create_table(
        "staff_services",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("staff_id", sa.Integer(), sa.ForeignKey("staff.id"), nullable=False),
        sa.Column("service_id", sa.Integer(), sa.ForeignKey("services.id"), nullable=False),
    )
    op.create_index("ix_staff_services_staff_id", "staff_services", ["staff_id"])
    op.create_index("ix_staff_services_service_id", "staff_services", ["service_id"])

    # ── working_hours ────────────────────────────────────────────────────────
    op.create_table(
        "working_hours",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("business_id", sa.Integer(), sa.ForeignKey("businesses.id"), nullable=True),
        sa.Column("staff_id", sa.Integer(), sa.ForeignKey("staff.id"), nullable=True),
        sa.Column("day_of_week", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("is_day_off", sa.Boolean(), server_default="false"),
    )
    op.create_index("ix_working_hours_business_id", "working_hours", ["business_id"])
    op.create_index("ix_working_hours_staff_id", "working_hours", ["staff_id"])

    # ── break_times ──────────────────────────────────────────────────────────
    op.create_table(
        "break_times",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("business_id", sa.Integer(), sa.ForeignKey("businesses.id"), nullable=True),
        sa.Column("staff_id", sa.Integer(), sa.ForeignKey("staff.id"), nullable=True),
        sa.Column("day_of_week", sa.Integer(), nullable=True),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("label", sa.String(100), nullable=True),
    )
    op.create_index("ix_break_times_business_id", "break_times", ["business_id"])
    op.create_index("ix_break_times_staff_id", "break_times", ["staff_id"])

    # ── blocked_times ────────────────────────────────────────────────────────
    op.create_table(
        "blocked_times",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("business_id", sa.Integer(), sa.ForeignKey("businesses.id"), nullable=True),
        sa.Column("staff_id", sa.Integer(), sa.ForeignKey("staff.id"), nullable=True),
        sa.Column("blocked_date", sa.Date(), nullable=True),
        sa.Column("start_datetime", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_datetime", sa.DateTime(timezone=True), nullable=True),
        sa.Column("full_day", sa.Boolean(), server_default="false"),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_blocked_times_business_id", "blocked_times", ["business_id"])
    op.create_index("ix_blocked_times_staff_id", "blocked_times", ["staff_id"])
    op.create_index("ix_blocked_times_blocked_date", "blocked_times", ["blocked_date"])

    # ── customers ────────────────────────────────────────────────────────────
    op.create_table(
        "customers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), unique=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("username", sa.String(100), nullable=True),
        sa.Column("language", sa.String(5), server_default="uz"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_customers_telegram_id", "customers", ["telegram_id"])

    # ── bookings ─────────────────────────────────────────────────────────────
    op.create_table(
        "bookings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("business_id", sa.Integer(), sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("service_id", sa.Integer(), sa.ForeignKey("services.id"), nullable=False),
        sa.Column("staff_id", sa.Integer(), sa.ForeignKey("staff.id"), nullable=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True),
        sa.Column("customer_name", sa.String(255), nullable=False),
        sa.Column("customer_phone", sa.String(20), nullable=False),
        sa.Column("booking_date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("status", sa.Enum("pending", "confirmed", "completed", "cancelled_by_customer", "cancelled_by_business", "no_show", "rescheduled", name="booking_status", create_type=False), nullable=False, server_default="pending"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column("reminder_24h_sent", sa.Boolean(), server_default="false"),
        sa.Column("reminder_1h_sent", sa.Boolean(), server_default="false"),
        sa.Column("was_auto_assigned", sa.Boolean(), server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_bookings_business_id", "bookings", ["business_id"])
    op.create_index("ix_bookings_staff_id", "bookings", ["staff_id"])
    op.create_index("ix_bookings_customer_id", "bookings", ["customer_id"])
    op.create_index("ix_bookings_booking_date", "bookings", ["booking_date"])
    op.create_index("ix_bookings_status", "bookings", ["status"])

    # ── reviews ──────────────────────────────────────────────────────────────
    op.create_table(
        "reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("booking_id", sa.Integer(), sa.ForeignKey("bookings.id"), unique=True, nullable=False),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("business_id", sa.Integer(), sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("staff_id", sa.Integer(), sa.ForeignKey("staff.id"), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("is_visible", sa.Boolean(), server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_reviews_business_id", "reviews", ["business_id"])

    # ── notifications ────────────────────────────────────────────────────────
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("notification_type", sa.String(50), nullable=False),
        sa.Column("booking_id", sa.Integer(), sa.ForeignKey("bookings.id"), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("status", sa.String(20), server_default="sent"),
    )
    op.create_index("ix_notifications_telegram_id", "notifications", ["telegram_id"])

    # ── subscriptions ────────────────────────────────────────────────────────
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("business_id", sa.Integer(), sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("plan", sa.Enum("trial", "basic", "premium", name="subscription_plan", create_type=False), nullable=False, server_default="trial"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("paid_amount", sa.Integer(), nullable=True),
        sa.Column("payment_note", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_subscriptions_business_id", "subscriptions", ["business_id"])

    # ── audit_logs ───────────────────────────────────────────────────────────
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=True),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("subscriptions")
    op.drop_table("notifications")
    op.drop_table("reviews")
    op.drop_table("bookings")
    op.drop_table("customers")
    op.drop_table("blocked_times")
    op.drop_table("break_times")
    op.drop_table("working_hours")
    op.drop_table("staff_services")
    op.drop_table("staff_invites")
    op.drop_table("staff")
    op.drop_table("services")
    op.drop_table("businesses")
    op.drop_table("business_categories")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS subscription_plan")
    op.execute("DROP TYPE IF EXISTS booking_status")
    op.execute("DROP TYPE IF EXISTS business_status")
    op.execute("DROP TYPE IF EXISTS user_role")
