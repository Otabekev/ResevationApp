from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.limiter import limiter
from app.services.booking_engine import get_available_slots

router = APIRouter(prefix="/availability", tags=["availability"])


class SlotOut(BaseModel):
    start_time: str  # "HH:MM"
    end_time: str
    available_staff_ids: list[int]


@router.get("")
@limiter.limit("60/minute")
async def get_slots(
    request: Request,
    business_id: int = Query(...),
    service_id: int = Query(...),
    date: date = Query(...),
    staff_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> list[SlotOut]:
    """
    Returns available time slots for a given service on a given date.
    Public endpoint — used by the Telegram bot and Mini App booking flow.
    """
    slots = await get_available_slots(
        db=db,
        business_id=business_id,
        service_id=service_id,
        target_date=date,
        staff_id=staff_id,
    )
    return [
        SlotOut(
            start_time=s.start_time.strftime("%H:%M"),
            end_time=s.end_time.strftime("%H:%M"),
            available_staff_ids=s.available_staff_ids,
        )
        for s in slots
    ]
