from datetime import date, datetime, time

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Time, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class WorkingHours(Base):
    """
    Recurring weekly schedule for a business or staff member.

    Priority: if staff has their own working_hours rows, those take precedence
    over the business-level rows. If staff has no rows, fall back to business rows.
    """
    __tablename__ = "working_hours"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int | None] = mapped_column(ForeignKey("businesses.id"), nullable=True, index=True)
    staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True, index=True)

    # 0 = Monday … 6 = Sunday
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    is_day_off: Mapped[bool] = mapped_column(Boolean, default=False)

    business = relationship(
        "Business",
        back_populates="working_hours",
        foreign_keys=[business_id],
        overlaps="working_hours",
    )
    staff = relationship(
        "Staff",
        back_populates="working_hours",
        foreign_keys=[staff_id],
        overlaps="working_hours",
    )


class BreakTime(Base):
    """
    Recurring break within a working day (e.g. lunch 13:00-14:00 every day).
    Applies to either a business (all staff) or a specific staff member.
    """
    __tablename__ = "break_times"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int | None] = mapped_column(ForeignKey("businesses.id"), nullable=True, index=True)
    staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True, index=True)

    day_of_week: Mapped[int | None] = mapped_column(Integer, nullable=True)  # None = every day
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    label: Mapped[str | None] = mapped_column(String(100), nullable=True)  # e.g. "Lunch"


class BlockedTime(Base):
    """
    One-off blocked period — holiday, vacation, emergency closure, personal time.
    Can target an entire day or a specific time range.
    """
    __tablename__ = "blocked_times"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int | None] = mapped_column(ForeignKey("businesses.id"), nullable=True, index=True)
    staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True, index=True)

    # If full_day=True, start_datetime/end_datetime are ignored and the whole day is blocked
    blocked_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    start_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    full_day: Mapped[bool] = mapped_column(Boolean, default=False)

    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    business = relationship(
        "Business",
        back_populates="blocked_times",
        foreign_keys=[business_id],
        overlaps="blocked_times",
    )
    staff = relationship(
        "Staff",
        back_populates="blocked_times",
        foreign_keys=[staff_id],
        overlaps="blocked_times",
    )
