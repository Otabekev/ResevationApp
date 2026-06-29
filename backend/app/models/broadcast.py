from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Broadcast(Base):
    """A one-off announcement the super-admin sends to bot users.

    Recipients are resolved from the `users` table by `audience` at send time.
    A row holds the message, the chosen audience, and live delivery counters so
    the admin can see results and history. `scheduled_at` is null for an
    immediate send, or a future time the scheduler's poller picks up.
    """
    __tablename__ = "broadcasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    audience: Mapped[str] = mapped_column(
        Enum("all", "owners_staff", "customers", name="broadcast_audience"),
        nullable=False,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[str] = mapped_column(
        Enum("scheduled", "sending", "done", "cancelled", name="broadcast_status"),
        nullable=False,
        default="scheduled",
        index=True,
    )
    # Null = send immediately; a future timestamp = the scheduler sends it then.
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    total_recipients: Mapped[int] = mapped_column(Integer, default=0)
    sent_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
