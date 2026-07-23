from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import authorize_business_access, authorize_business_or_provider, get_current_dashboard_user, get_current_user
from app.models.business import Business
from app.models.service import Service
from app.models.user import User

router = APIRouter(prefix="/businesses/{business_id}/services", tags=["services"])


class ServiceCreate(BaseModel):
    name_uz: str = Field(..., min_length=1, max_length=255)
    name_ru: str = Field(..., min_length=1, max_length=255)
    name_en: str = Field(..., min_length=1, max_length=255)
    description_uz: str | None = Field(None, max_length=2000)
    description_ru: str | None = Field(None, max_length=2000)
    description_en: str | None = Field(None, max_length=2000)
    duration_minutes: int = Field(..., gt=0, le=1440)
    buffer_before_minutes: int = Field(0, ge=0, le=1440)
    buffer_after_minutes: int = Field(0, ge=0, le=1440)
    price: float | None = Field(None, ge=0)
    currency: str = Field("UZS", max_length=5)
    requires_confirmation: bool = False
    sort_order: int = Field(0, ge=0)
    online_bookable: bool = True
    max_per_day: int | None = Field(None, ge=1, le=1000)


class ServiceUpdate(BaseModel):
    name_uz: str | None = Field(None, min_length=1, max_length=255)
    name_ru: str | None = Field(None, min_length=1, max_length=255)
    name_en: str | None = Field(None, min_length=1, max_length=255)
    description_uz: str | None = Field(None, max_length=2000)
    description_ru: str | None = Field(None, max_length=2000)
    description_en: str | None = Field(None, max_length=2000)
    duration_minutes: int | None = Field(None, gt=0, le=1440)
    buffer_before_minutes: int | None = Field(None, ge=0, le=1440)
    buffer_after_minutes: int | None = Field(None, ge=0, le=1440)
    price: float | None = Field(None, ge=0)
    is_active: bool | None = None
    requires_confirmation: bool | None = None
    sort_order: int | None = Field(None, ge=0)
    online_bookable: bool | None = None
    max_per_day: int | None = Field(None, ge=0, le=1000)


class ServiceOut(BaseModel):
    id: int
    business_id: int
    name_uz: str
    name_ru: str
    name_en: str
    description_uz: str | None
    description_ru: str | None
    description_en: str | None
    duration_minutes: int
    buffer_before_minutes: int
    buffer_after_minutes: int
    price: float | None
    currency: str
    is_active: bool
    requires_confirmation: bool
    sort_order: int

    model_config = {"from_attributes": True}


# All owner-facing service endpoints are manager-allowed (a desk-manager may
# add/edit/remove services). authorize_business_access enforces per-business scope.


@router.get("", response_model=list[ServiceOut])
async def list_services(business_id: int, db: AsyncSession = Depends(get_db)):
    # Public/customer list (the bot). online_bookable=False services (e.g. a
    # dentist's multi-day treatment) are staff-scheduled only — never self-booked
    # — so they're hidden here. The owner dashboard uses /all (unfiltered).
    result = await db.execute(
        select(Service)
        .where(
            Service.business_id == business_id,
            Service.is_active == True,  # noqa: E712
            Service.online_bookable == True,  # noqa: E712
        )
        .order_by(Service.sort_order, Service.id)
    )
    return result.scalars().all()


@router.get("/all", response_model=list[ServiceOut])
async def list_all_services(
    business_id: int,
    user: User = Depends(get_current_dashboard_user),
    db: AsyncSession = Depends(get_db),
):
    """Full service menu incl. disabled ones. Read-only for a provider too, so
    their setup page can pick which of these they offer (create/edit/delete stay
    manager-only below)."""
    await authorize_business_or_provider(business_id, user, db)
    result = await db.execute(
        select(Service).where(Service.business_id == business_id).order_by(Service.sort_order, Service.id)
    )
    return result.scalars().all()


@router.post("", response_model=ServiceOut, status_code=status.HTTP_201_CREATED)
async def create_service(
    business_id: int,
    body: ServiceCreate,
    user: User = Depends(get_current_dashboard_user),
    db: AsyncSession = Depends(get_db),
):
    await authorize_business_access(business_id, user, db)
    service = Service(business_id=business_id, **body.model_dump())
    db.add(service)
    await db.commit()
    await db.refresh(service)
    return service


@router.patch("/{service_id}", response_model=ServiceOut)
async def update_service(
    business_id: int,
    service_id: int,
    body: ServiceUpdate,
    user: User = Depends(get_current_dashboard_user),
    db: AsyncSession = Depends(get_db),
):
    await authorize_business_access(business_id, user, db)
    service = await db.get(Service, service_id)
    if not service or service.business_id != business_id:
        raise HTTPException(status_code=404, detail="Service not found")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(service, field, value)

    db.add(service)
    await db.commit()
    await db.refresh(service)
    return service


@router.delete("/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service(
    business_id: int,
    service_id: int,
    user: User = Depends(get_current_dashboard_user),
    db: AsyncSession = Depends(get_db),
):
    await authorize_business_access(business_id, user, db)
    service = await db.get(Service, service_id)
    if not service or service.business_id != business_id:
        raise HTTPException(status_code=404, detail="Service not found")
    # Soft delete
    service.is_active = False
    db.add(service)
    await db.commit()
