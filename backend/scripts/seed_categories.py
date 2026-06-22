"""
Seed / reconcile default business categories.
Usage: python -m scripts.seed_categories

Idempotent: inserts missing categories, refreshes names/icon/sort/active for
existing ones (matched by slug), and hides every slug in RETIRED_SLUGS. Hiding
sets is_active=False rather than deleting, so businesses already on a retired
category (and their bookings) stay intact and the category can be brought back
later by moving its slug into CATEGORIES. The /businesses/categories endpoint
only returns is_active rows, so hidden categories drop out of both the owner
setup picker and the customer booking flow.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.business import BusinessCategory

# Categories shown in the picker (display order = sort_order).
CATEGORIES = [
    {"slug": "barbershop",    "name_uz": "Sartaroshxona",     "name_ru": "Барбершоп",        "name_en": "Barbershop",      "icon": "✂️",  "default_slot_step_minutes": 15, "sort_order": 1},
    {"slug": "beauty_salon",  "name_uz": "Go'zallik saloni",  "name_ru": "Салон красоты",     "name_en": "Beauty Salon",    "icon": "💄",  "default_slot_step_minutes": 15, "sort_order": 2},
    {"slug": "nail_studio",   "name_uz": "Nail studiya",      "name_ru": "Ногтевая студия",   "name_en": "Nail Studio",     "icon": "💅",  "default_slot_step_minutes": 15, "sort_order": 3},
    {"slug": "dentist",       "name_uz": "Stomatologiya",     "name_ru": "Стоматология",      "name_en": "Dentist",         "icon": "🦷",  "default_slot_step_minutes": 15, "sort_order": 4},
    {"slug": "clinic",        "name_uz": "Klinika",           "name_ru": "Клиника",           "name_en": "Clinic",          "icon": "🏥",  "default_slot_step_minutes": 15, "sort_order": 5},
    {"slug": "massage",       "name_uz": "Massaj saloni",     "name_ru": "Массажный салон",   "name_en": "Massage",         "icon": "💆",  "default_slot_step_minutes": 30, "sort_order": 6},
    {"slug": "football_field","name_uz": "Futbol maydoni",    "name_ru": "Футбольное поле",   "name_en": "Football Field",  "icon": "⚽",  "default_slot_step_minutes": 60, "sort_order": 7},
    {"slug": "gym",           "name_uz": "Sport zal",         "name_ru": "Спортзал",          "name_en": "Gym",             "icon": "🏋️", "default_slot_step_minutes": 60, "sort_order": 8},
    {"slug": "tutor",         "name_uz": "Repetitor",         "name_ru": "Репетитор",         "name_en": "Tutor",           "icon": "📚",  "default_slot_step_minutes": 60, "sort_order": 9},
    {"slug": "other",         "name_uz": "Boshqa",            "name_ru": "Другое",            "name_en": "Other",           "icon": "🏪",  "default_slot_step_minutes": 30, "sort_order": 99},
]

# Hidden for the launch — not deleted. Move a slug back into CATEGORIES to revive it.
RETIRED_SLUGS = ["photographer", "car_wash"]


async def seed():
    async with AsyncSessionLocal() as db:
        for cat_data in CATEGORIES:
            result = await db.execute(
                select(BusinessCategory).where(BusinessCategory.slug == cat_data["slug"])
            )
            existing = result.scalar_one_or_none()
            if existing:
                for field, value in cat_data.items():
                    setattr(existing, field, value)
                existing.is_active = True
                print(f"  updated {cat_data['slug']}")
            else:
                db.add(BusinessCategory(**cat_data))
                print(f"  added {cat_data['slug']}")

        for slug in RETIRED_SLUGS:
            result = await db.execute(
                select(BusinessCategory).where(BusinessCategory.slug == slug)
            )
            existing = result.scalar_one_or_none()
            if existing and existing.is_active:
                existing.is_active = False
                print(f"  hid {slug}")

        await db.commit()
        print("Done.")


if __name__ == "__main__":
    asyncio.run(seed())
