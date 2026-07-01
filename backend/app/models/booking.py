from datetime import date, datetime, time

from sqlalchemy import (
    BigInteger, Boolean, Column, Date, DateTime, Enum,
    ForeignKey, Integer, Numeric, String, Table, Text, Time, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# A booking can reference several services (multi-service bookings). The
# primary/first service stays on Booking.service_id for backward compatibility;
# this table lists ALL selected services. Deleting a booking cascades here.
booking_services = Table(
    "booking_services",
    Base.metadata,
    Column("id", Integer, primary_key=True),
    Column("booking_id", Integer, ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("service_id", Integer, ForeignKey("services.id"), nullable=False, index=True),
    UniqueConstraint("booking_id", "service_id", name="uq_booking_service"),
)


class Customer(Base):
    """Person who makes bookings. Usually a Telegram user; walk-in customers
    created manually by an owner have telegram_id = NULL (Postgres allows
    multiple NULLs under the unique constraint)."""
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    language: Mapped[str] = mapped_column(String(5), default="uz")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    bookings = relationship("Booking", back_populates="customer")
    reviews = relationship("Review", back_populates="customer")


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), nullable=False, index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), nullable=False)
    staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True, index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True, index=True)

    # Customer info snapshot (in case customer deletes account)
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_phone: Mapped[str] = mapped_column(String(20), nullable=False)

    # Appointment time
    booking_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)  # start_time + duration_minutes

    # Price frozen at booking time, so a later service price change never
    # rewrites what this booking cost (keeps future revenue reporting accurate).
    # Duration needs no snapshot — end_time already captures it at insert.
    total_price_at_booking: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)

    status: Mapped[str] = mapped_column(
        Enum(
            "pending",
            "confirmed",
            "completed",
            "cancelled_by_customer",
            "cancelled_by_business",
            "no_show",
            "rescheduled",
            name="booking_status",
        ),
        default="pending",
        nullable=False,
        index=True,
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Notification tracking
    reminder_24h_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    reminder_1h_sent: Mapped[bool] = mapped_column(Boolean, default=False)

    # If staff_id was None at booking time ("any available"), track who was auto-assigned
    was_auto_assigned: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    business = relationship("Business", back_populates="bookings")
    service = relationship("Service", back_populates="bookings")
    # All services in this booking (multi-service); `service` above is the first.
    services = relationship("Service", secondary=booking_services)
    staff = relationship("Staff", back_populates="bookings")
    customer = relationship("Customer", back_populates="bookings")
    review = relationship("Review", back_populates="booking", uselist=False)


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id"), unique=True, nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), nullable=False, index=True)
    staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)

    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # 1–5
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    booking = relationship("Booking", back_populates="review")
    customer = relationship("Customer", back_populates="reviews")
    business = relationship("Business", back_populates="reviews")
    staff = relationship("Staff")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    notification_type: Mapped[str] = mapped_column(String(50), nullable=False)
    booking_id: Mapped[int | None] = mapped_column(ForeignKey("bookings.id"), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[str] = mapped_column(String(20), default="sent")  # sent | failed

    booking = relationship("Booking")
