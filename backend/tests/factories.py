"""Async factory helpers for seeding test data. Each commits so the HTTP client
session (a separate session on the same engine) sees the rows."""
from datetime import date, time

from app.models.booking import Booking, Customer
from app.models.business import Business, BusinessCategory
from app.models.service import Service
from app.models.staff import Staff, StaffService
from app.models.user import User
from app.services.auth_service import create_access_token


def auth_header(user_id: int) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


async def create_category(db, slug="barbershop") -> BusinessCategory:
    cat = BusinessCategory(slug=slug, name_uz=slug, name_ru=slug, name_en=slug)
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return cat


async def create_user(db, *, role="business_owner", telegram_id=None, name="User") -> User:
    user = User(telegram_id=telegram_id, name=name, role=role)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def create_business(db, *, owner_id, category_id, name="Biz", status="active") -> Business:
    biz = Business(
        owner_id=owner_id,
        category_id=category_id,
        name=name,
        city="Namangan",
        address="Main St 1",
        phone="+998901234567",
        status=status,
    )
    db.add(biz)
    await db.commit()
    await db.refresh(biz)
    return biz


async def create_service(db, *, business_id, duration_minutes=30, name="Cut") -> Service:
    svc = Service(
        business_id=business_id,
        name_uz=name, name_ru=name, name_en=name,
        duration_minutes=duration_minutes,
    )
    db.add(svc)
    await db.commit()
    await db.refresh(svc)
    return svc


async def create_staff(db, *, business_id, user_id=None, name="Barber") -> Staff:
    staff = Staff(business_id=business_id, user_id=user_id, name=name)
    db.add(staff)
    await db.commit()
    await db.refresh(staff)
    return staff


async def link_staff_service(db, *, staff_id, service_id) -> None:
    db.add(StaffService(staff_id=staff_id, service_id=service_id))
    await db.commit()


async def create_customer(db, *, telegram_id, name="Cust", phone="+998900000000") -> Customer:
    cust = Customer(telegram_id=telegram_id, name=name, phone=phone)
    db.add(cust)
    await db.commit()
    await db.refresh(cust)
    return cust


async def create_booking(
    db, *, business_id, service_id, staff_id, customer_id,
    booking_date=None, start_time=None, end_time=None, status="confirmed",
    customer_name="Cust", customer_phone="+998900000000",
) -> Booking:
    booking = Booking(
        business_id=business_id,
        service_id=service_id,
        staff_id=staff_id,
        customer_id=customer_id,
        customer_name=customer_name,
        customer_phone=customer_phone,
        booking_date=booking_date or date(2030, 1, 1),
        start_time=start_time or time(10, 0),
        end_time=end_time or time(10, 30),
        status=status,
    )
    db.add(booking)
    await db.commit()
    await db.refresh(booking)
    return booking
