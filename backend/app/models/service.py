from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), nullable=False, index=True)

    # Multilingual names
    name_uz: Mapped[str] = mapped_column(String(255), nullable=False)
    name_ru: Mapped[str] = mapped_column(String(255), nullable=False)
    name_en: Mapped[str] = mapped_column(String(255), nullable=False)

    # Multilingual descriptions
    description_uz: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_ru: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_en: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timing
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    buffer_before_minutes: Mapped[int] = mapped_column(Integer, default=0)
    buffer_after_minutes: Mapped[int] = mapped_column(Integer, default=0)

    # Pricing
    price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(5), default="UZS")

    # Flags
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    requires_confirmation: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    business = relationship("Business", back_populates="services")
    staff_services = relationship("StaffService", back_populates="service", cascade="all, delete-orphan")
    bookings = relationship("Booking", back_populates="service")

    @property
    def total_block_minutes(self) -> int:
        """Total time this service blocks on a staff calendar."""
        return self.buffer_before_minutes + self.duration_minutes + self.buffer_after_minutes
