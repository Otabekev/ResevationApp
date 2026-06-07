from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Telegram username
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)  # for web login
    role: Mapped[str] = mapped_column(
        Enum("super_admin", "business_owner", "staff", "customer", name="user_role"),
        nullable=False,
        default="customer",
    )
    language: Mapped[str] = mapped_column(String(5), default="uz")  # uz / ru / en
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    businesses = relationship("Business", back_populates="owner", foreign_keys="Business.owner_id")
    staff_records = relationship("Staff", back_populates="user", foreign_keys="Staff.user_id")
