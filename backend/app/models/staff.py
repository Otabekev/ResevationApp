from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Staff(Base):
    __tablename__ = "staff"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)

    # Profile (can exist before user joins — owner fills this in)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)

    role: Mapped[str] = mapped_column(String(20), default="staff")  # manager | staff

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    can_set_own_hours: Mapped[bool] = mapped_column(Boolean, default=False)
    # True when this provider record IS the business owner working as a bookable
    # provider (auto-linked to the owner's account, no invite). One per business.
    is_owner: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    business = relationship("Business", back_populates="staff_members")
    user = relationship("User", back_populates="staff_records", foreign_keys=[user_id])
    staff_services = relationship("StaffService", back_populates="staff", cascade="all, delete-orphan")
    working_hours = relationship(
        "WorkingHours",
        back_populates="staff",
        primaryjoin="WorkingHours.staff_id == Staff.id",
        cascade="all, delete-orphan",
        overlaps="working_hours",
    )
    blocked_times = relationship(
        "BlockedTime",
        back_populates="staff",
        primaryjoin="BlockedTime.staff_id == Staff.id",
        cascade="all, delete-orphan",
        overlaps="blocked_times",
    )
    bookings = relationship("Booking", back_populates="staff")


class StaffInvite(Base):
    __tablename__ = "staff_invites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), nullable=False)
    staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StaffService(Base):
    """Links a staff member to services they can perform."""
    __tablename__ = "staff_services"
    # Matches the prod constraint added in migration 0002 (D7). Declared here so
    # the test schema (built from models) enforces it too — otherwise a
    # delete-then-reinsert that trips this constraint passes tests but 500s live.
    __table_args__ = (
        UniqueConstraint("staff_id", "service_id", name="uq_staff_services_staff_service"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id"), nullable=False, index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), nullable=False, index=True)

    staff = relationship("Staff", back_populates="staff_services")
    service = relationship("Service", back_populates="staff_services")
