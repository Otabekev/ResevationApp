"""Live queue (walk-in line) — bot + dashboard endpoints.

Cost design: positions are computed on demand (queue_engine), never in a loop.
Telegram pushes go out as BackgroundTasks so a slow send never pins the pooled
DB connection (same discipline as the booking-notification path).
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import authorize_business_access, get_current_dashboard_user, require_bot_secret
from app.models.booking import Customer
from app.models.business import Business
from app.models.queue import QueueEntry
from app.models.staff import Staff
from app.models.user import User
from app.routers.bookings import _normalize_uz_phone
from app.services.notification_service import (
    queue_still_coming, queue_turn_message, send_telegram_message,
)
from app.services.queue_engine import eta_clock, eta_minutes, front_waiting, position_of
from app.timeutils import now_local

logger = logging.getLogger("rezerv.queue")

public_router = APIRouter(prefix="/public/queue", tags=["queue"])
router = APIRouter(prefix="/businesses/{business_id}/queue", tags=["queue"])


def _eta_fields(position: int, avg_minutes: int) -> dict:
    """position → {eta_minutes, eta_time}. The wall-clock estimate is only
    meaningful when someone is ahead; for the person at the front there's no wait
    to project, so eta_time is None and the bot shows no wait line."""
    eta = eta_minutes(position, avg_minutes)
    return {
        "eta_minutes": eta,
        "eta_time": eta_clock(now_local(), eta) if position > 1 else None,
    }


async def _queue_staff(db: AsyncSession, business_id: int, staff_id: int) -> Staff:
    staff = await db.get(Staff, staff_id)
    if not staff or staff.business_id != business_id or not staff.is_active:
        raise HTTPException(status_code=404, detail="Staff not found")
    return staff


async def _front_notice(db: AsyncSession, staff: Staff):
    """After the line advances, tell the NEW front person their turn is near — a
    single 'you're next — still coming?' with Yes/No buttons. Marks them notified
    (in-request DB write) so the periodic sweep never asks again. Returns
    (chat_id, text, markup) to push in the background — or None."""
    fronts = await front_waiting(db, staff.id, limit=1)
    if not fronts:
        return None
    top = fronts[0]
    if top.telegram_id and top.notified_position != 1:
        top.notified_position = 1
        top.last_ping_at = datetime.now(timezone.utc)  # so the sweep won't re-ask
        db.add(top)
        text, markup = queue_still_coming(top.language, staff.name, top.id)
        return (top.telegram_id, text, markup)
    return None


# ── Public (bot) ─────────────────────────────────────────────────────────────

class QueueJoin(BaseModel):
    business_id: int
    staff_id: int
    service_id: int | None = None
    customer_name: str = Field(..., min_length=1, max_length=255)
    customer_phone: str | None = Field(None, max_length=20)
    telegram_id: int | None = None
    language: str = "uz"


@public_router.post("/join", dependencies=[Depends(require_bot_secret)])
async def join_queue(body: QueueJoin, db: AsyncSession = Depends(get_db)):
    biz = await db.get(Business, body.business_id)
    if not biz or biz.status not in ("active", "trial"):
        raise HTTPException(status_code=404, detail="Business not found")
    staff = await _queue_staff(db, body.business_id, body.staff_id)
    if not staff.is_provider or staff.scheduling_mode != "queue":
        raise HTTPException(status_code=400, detail="This provider is not using a live queue")

    # Idempotent join: if this Telegram user is already waiting here, return their
    # current place instead of adding a duplicate.
    if body.telegram_id is not None:
        dup = (
            await db.execute(
                select(QueueEntry).where(
                    and_(
                        QueueEntry.staff_id == staff.id,
                        QueueEntry.telegram_id == body.telegram_id,
                        QueueEntry.status == "waiting",
                    )
                ).limit(1)
            )
        ).scalar_one_or_none()
        if dup is not None:
            pos = await position_of(db, dup)
            return {"entry_id": dup.id, "position": pos, **_eta_fields(pos, staff.queue_avg_minutes),
                    "staff_name": staff.name, "already": True}

    customer_id = None
    if body.telegram_id is not None:
        cust = (
            await db.execute(select(Customer).where(Customer.telegram_id == body.telegram_id).limit(1))
        ).scalar_one_or_none()
        customer_id = cust.id if cust else None

    phone = _normalize_uz_phone(body.customer_phone) if body.customer_phone else None
    entry = QueueEntry(
        business_id=body.business_id, staff_id=staff.id, service_id=body.service_id,
        customer_id=customer_id, customer_name=body.customer_name.strip(), customer_phone=phone,
        telegram_id=body.telegram_id,
        language=body.language if body.language in ("uz", "ru", "en") else "uz",
        status="waiting",
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    pos = await position_of(db, entry)
    return {"entry_id": entry.id, "position": pos, **_eta_fields(pos, staff.queue_avg_minutes),
            "staff_name": staff.name, "already": False}


@public_router.get("/status/{entry_id}", dependencies=[Depends(require_bot_secret)])
async def queue_status(entry_id: int, db: AsyncSession = Depends(get_db)):
    entry = await db.get(QueueEntry, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Not in queue")
    staff = await db.get(Staff, entry.staff_id)
    pos = await position_of(db, entry)
    return {"entry_id": entry.id, "status": entry.status, "position": pos,
            **_eta_fields(pos, staff.queue_avg_minutes if staff else 15),
            "staff_name": staff.name if staff else ""}


@public_router.post("/leave/{entry_id}", dependencies=[Depends(require_bot_secret)])
async def leave_queue(entry_id: int, background: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    entry = await db.get(QueueEntry, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Not in queue")
    if entry.status != "waiting":
        return {"ok": True}
    entry.status = "cancelled"
    entry.finished_at = datetime.now(timezone.utc)
    db.add(entry)
    staff = await db.get(Staff, entry.staff_id)
    notice = await _front_notice(db, staff) if staff else None
    await db.commit()
    if notice:
        background.add_task(send_telegram_message, notice[0], notice[1], reply_markup=notice[2])
    return {"ok": True}


@public_router.post("/confirm/{entry_id}", dependencies=[Depends(require_bot_secret)])
async def confirm_still_coming(entry_id: int, db: AsyncSession = Depends(get_db)):
    entry = await db.get(QueueEntry, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Not in queue")
    entry.ping_misses = 0
    db.add(entry)
    await db.commit()
    return {"ok": True}


# ── Dashboard (owner / manager) ──────────────────────────────────────────────

class WalkInJoin(BaseModel):
    staff_id: int
    service_id: int | None = None
    customer_name: str = Field(..., min_length=1, max_length=255)
    customer_phone: str | None = Field(None, max_length=20)


@router.get("")
async def list_queue(
    business_id: int, staff_id: int | None = None,
    user: User = Depends(get_current_dashboard_user), db: AsyncSession = Depends(get_db),
):
    """The live line(s) — waiting + currently-called entries, in order, with a
    computed position per waiting person."""
    await authorize_business_access(business_id, user, db)
    filters = [QueueEntry.business_id == business_id, QueueEntry.status.in_(("waiting", "called"))]
    if staff_id:
        filters.append(QueueEntry.staff_id == staff_id)
    rows = (
        await db.execute(
            select(QueueEntry).where(and_(*filters)).order_by(QueueEntry.staff_id, QueueEntry.id)
        )
    ).scalars().all()
    counters: dict[int, int] = {}
    out = []
    for e in rows:
        pos = None
        if e.status == "waiting":
            counters[e.staff_id] = counters.get(e.staff_id, 0) + 1
            pos = counters[e.staff_id]
        out.append({
            "id": e.id, "staff_id": e.staff_id, "status": e.status, "position": pos,
            "customer_name": e.customer_name, "customer_phone": e.customer_phone,
            "has_telegram": e.telegram_id is not None,
            "joined_at": e.joined_at.isoformat() if e.joined_at else None,
        })
    return out


@router.post("")
async def add_walkin(
    business_id: int, body: WalkInJoin,
    user: User = Depends(get_current_dashboard_user), db: AsyncSession = Depends(get_db),
):
    """Staff adds a walk-in (someone who showed up in person) to the line."""
    await authorize_business_access(business_id, user, db)
    staff = await _queue_staff(db, business_id, body.staff_id)
    phone = _normalize_uz_phone(body.customer_phone) if body.customer_phone else None
    entry = QueueEntry(
        business_id=business_id, staff_id=staff.id, service_id=body.service_id,
        customer_name=body.customer_name.strip(), customer_phone=phone, status="waiting",
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return {"id": entry.id}


async def _get_entry(db: AsyncSession, business_id: int, entry_id: int) -> QueueEntry:
    entry = await db.get(QueueEntry, entry_id)
    if not entry or entry.business_id != business_id:
        raise HTTPException(status_code=404, detail="Not found")
    return entry


async def _advance(db: AsyncSession, business_id: int, entry_id: int, user: User, new_status: str):
    """Shared: move an entry to a terminal/called status and return (staff, notice)."""
    await authorize_business_access(business_id, user, db)
    entry = await _get_entry(db, business_id, entry_id)
    entry.status = new_status
    if new_status == "called":
        entry.called_at = datetime.now(timezone.utc)
    else:
        entry.finished_at = datetime.now(timezone.utc)
    db.add(entry)
    staff = await db.get(Staff, entry.staff_id)
    notice = await _front_notice(db, staff) if staff else None
    return entry, staff, notice


@router.post("/{entry_id}/call")
async def call_entry(
    business_id: int, entry_id: int, background: BackgroundTasks,
    user: User = Depends(get_current_dashboard_user), db: AsyncSession = Depends(get_db),
):
    entry, staff, notice = await _advance(db, business_id, entry_id, user, "called")
    turn = (entry.telegram_id, queue_turn_message(entry.language, staff.name)) if (entry.telegram_id and staff) else None
    await db.commit()
    if turn:
        background.add_task(send_telegram_message, turn[0], turn[1])
    if notice:
        background.add_task(send_telegram_message, notice[0], notice[1], reply_markup=notice[2])
    return {"ok": True}


@router.post("/{entry_id}/done")
async def done_entry(
    business_id: int, entry_id: int, background: BackgroundTasks,
    user: User = Depends(get_current_dashboard_user), db: AsyncSession = Depends(get_db),
):
    _entry, _staff, notice = await _advance(db, business_id, entry_id, user, "done")
    await db.commit()
    if notice:
        background.add_task(send_telegram_message, notice[0], notice[1], reply_markup=notice[2])
    return {"ok": True}


@router.post("/{entry_id}/no_show")
async def no_show_entry(
    business_id: int, entry_id: int, background: BackgroundTasks,
    user: User = Depends(get_current_dashboard_user), db: AsyncSession = Depends(get_db),
):
    _entry, _staff, notice = await _advance(db, business_id, entry_id, user, "no_show")
    await db.commit()
    if notice:
        background.add_task(send_telegram_message, notice[0], notice[1], reply_markup=notice[2])
    return {"ok": True}
