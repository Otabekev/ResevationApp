"""Live-queue math — position and wait-time, computed ON DEMAND.

Deliberately no stored position and no background loop keeping positions in sync:
a person's place is just how many people joined their doctor's line before them
and are still waiting. One tiny indexed COUNT answers it. This keeps the queue
cheap — cost scales with taps, not with idle time.
"""
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.queue import QueueEntry


async def waiting_count(db: AsyncSession, staff_id: int) -> int:
    return (
        await db.scalar(
            select(func.count(QueueEntry.id)).where(
                and_(QueueEntry.staff_id == staff_id, QueueEntry.status == "waiting")
            )
        )
    ) or 0


async def position_of(db: AsyncSession, entry: QueueEntry) -> int:
    """1-based place in the doctor's waiting line, by join order. 0 if not waiting.
    Ordered by id (auto-increment = exact join order) — precise integer compare,
    no timestamp-precision pitfalls."""
    if entry.status != "waiting":
        return 0
    ahead = (
        await db.scalar(
            select(func.count(QueueEntry.id)).where(
                and_(
                    QueueEntry.staff_id == entry.staff_id,
                    QueueEntry.status == "waiting",
                    QueueEntry.id < entry.id,
                )
            )
        )
    ) or 0
    return ahead + 1


def eta_minutes(position: int, avg_minutes: int) -> int:
    """Estimated wait for someone at `position`: people ahead × avg service time."""
    return max(0, position - 1) * max(1, avg_minutes)


async def front_waiting(db: AsyncSession, staff_id: int, limit: int = 1) -> list[QueueEntry]:
    """The first `limit` people still waiting for this doctor, in join order."""
    rows = await db.execute(
        select(QueueEntry)
        .where(and_(QueueEntry.staff_id == staff_id, QueueEntry.status == "waiting"))
        .order_by(QueueEntry.id)
        .limit(limit)
    )
    return list(rows.scalars().all())
