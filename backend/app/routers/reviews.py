from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import require_bot_secret
from app.limiter import limiter
from app.models.booking import Booking, Customer, Review

router = APIRouter(tags=["reviews"])


class ReviewCreate(BaseModel):
    booking_id: int
    rating: int = Field(..., ge=1, le=5)
    comment: str | None = Field(None, max_length=1000)
    telegram_id: int


class ReviewOut(BaseModel):
    id: int
    booking_id: int
    rating: int
    comment: str | None
    customer_id: int

    model_config = {"from_attributes": True}


@router.post("/reviews", response_model=ReviewOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def create_review(
    request: Request,
    body: ReviewCreate,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_bot_secret),
):
    # Verify booking exists and belongs to this customer
    booking = await db.get(Booking, body.booking_id)
    if not booking or booking.status != "completed":
        raise HTTPException(status_code=400, detail="Booking not completed or not found")

    customer_result = await db.execute(select(Customer).where(Customer.telegram_id == body.telegram_id))
    customer = customer_result.scalar_one_or_none()
    if not customer or booking.customer_id != customer.id:
        raise HTTPException(status_code=403, detail="Not your booking")

    # Check no existing review
    existing = await db.execute(select(Review).where(Review.booking_id == body.booking_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Review already submitted")

    review = Review(
        booking_id=booking.id,
        customer_id=customer.id,
        business_id=booking.business_id,
        staff_id=booking.staff_id,
        rating=body.rating,
        comment=body.comment,
    )
    db.add(review)
    await db.commit()
    await db.refresh(review)
    return review


@router.get("/businesses/{business_id}/reviews", response_model=list[ReviewOut])
async def get_business_reviews(business_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Review).where(
            and_(Review.business_id == business_id, Review.is_visible == True)
        ).order_by(Review.created_at.desc()).limit(50)
    )
    return result.scalars().all()
