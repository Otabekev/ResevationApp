from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class QueueEntry(Base):
    """One person's place in a doctor's live queue (no fixed time). Position and
    wait time are computed on demand from joined_at ordering — nothing runs a
    background loop recalculating them. A line = the waiting rows for one
    (business_id, staff_id), ordered by joined_at.

    status: waiting → called → done ; or no_show / cancelled (left / dropped).
    """
    __tablename__ = "queue_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), nullable=False, index=True)
    staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id"), nullable=False, index=True)
    service_id: Mapped[int | None] = mapped_column(ForeignKey("services.id"), nullable=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)

    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Denormalized so the scheduler can push notifications without joining customers.
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    language: Mapped[str] = mapped_column(String(5), default="uz", server_default="uz")

    status: Mapped[str] = mapped_column(String(16), nullable=False, default="waiting", index=True)

    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    called_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Throttling state (so we don't spam pushes or pings):
    # last position we told this person, and the still-coming ping bookkeeping.
    notified_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_ping_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ping_misses: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    staff = relationship("Staff")
    service = relationship("Service")
