from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, Enum, Float, ForeignKey,
    Integer, String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class BusinessCategory(Base):
    __tablename__ = "business_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)  # e.g. "barbershop"
    name_uz: Mapped[str] = mapped_column(String(100), nullable=False)
    name_ru: Mapped[str] = mapped_column(String(100), nullable=False)
    name_en: Mapped[str] = mapped_column(String(100), nullable=False)
    icon: Mapped[str | None] = mapped_column(String(50), nullable=True)  # emoji or icon name
    description_uz: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_ru: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_slot_step_minutes: Mapped[int] = mapped_column(Integer, default=15)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    businesses = relationship("Business", back_populates="category")


class Business(Base):
    __tablename__ = "businesses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("business_categories.id"), nullable=False)

    # Identity
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)  # URL-friendly name
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Location
    region: Mapped[str] = mapped_column(String(100), default="Namangan")
    district: Mapped[str] = mapped_column(String(100), default="Pop")
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    address: Mapped[str] = mapped_column(String(500), nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Contact
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    telegram_username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    instagram_link: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Status
    status: Mapped[str] = mapped_column(
        Enum("pending", "active", "trial", "suspended", "blocked", name="business_status"),
        default="pending",
        nullable=False,
        index=True,
    )
    is_online_booking_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Booking rules
    min_advance_booking_minutes: Mapped[int] = mapped_column(Integer, default=60)
    max_advance_booking_days: Mapped[int] = mapped_column(Integer, default=30)
    cancellation_policy_hours: Mapped[int] = mapped_column(Integer, default=2)
    slot_step_minutes: Mapped[int] = mapped_column(Integer, default=15)  # granularity for available slots

    # Custom messaging
    custom_message_uz: Mapped[str | None] = mapped_column(Text, nullable=True)
    custom_message_ru: Mapped[str | None] = mapped_column(Text, nullable=True)
    custom_message_en: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Trial / subscription
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    owner = relationship("User", back_populates="businesses", foreign_keys=[owner_id])
    category = relationship("BusinessCategory", back_populates="businesses")
    services = relationship("Service", back_populates="business", cascade="all, delete-orphan")
    staff_members = relationship("Staff", back_populates="business", cascade="all, delete-orphan")
    working_hours = relationship(
        "WorkingHours",
        back_populates="business",
        primaryjoin="and_(WorkingHours.business_id == Business.id, WorkingHours.staff_id == None)",
        cascade="all, delete-orphan",
        overlaps="working_hours",
    )
    blocked_times = relationship(
        "BlockedTime",
        back_populates="business",
        primaryjoin="and_(BlockedTime.business_id == Business.id, BlockedTime.staff_id == None)",
        cascade="all, delete-orphan",
        overlaps="blocked_times",
    )
    bookings = relationship("Booking", back_populates="business", cascade="all, delete-orphan")
    reviews = relationship("Review", back_populates="business")
