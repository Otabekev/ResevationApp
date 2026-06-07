"""
Run once to seed default business categories.
Usage: python -m scripts.seed_categories
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.database import AsyncSessionLocal
from app.models.business import BusinessCategory

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
    {"slug": "photographer",  "name_uz": "Fotograf",          "name_ru": "Фотограф",          "name_en": "Photographer",    "icon": "📸",  "default_slot_step_minutes": 60, "sort_order": 10},
    {"slug": "car_wash",      "name_uz": "Avto myjka",        "name_ru": "Автомойка",         "name_en": "Car Wash",        "icon": "🚗",  "default_slot_step_minutes": 30, "sort_order": 11},
    {"slug": "other",         "name_uz": "Boshqa",            "name_ru": "Другое",            "name_en": "Other",           "icon": "🏪",  "default_slot_step_minutes": 30, "sort_order": 99},
]


async def seed():
    async with AsyncSessionLocal() as db:
        for cat_data in CATEGORIES:
            existing = await db.execute(
                __import__("sqlalchemy", fromlist=["select"]).select(BusinessCategory).where(
                    BusinessCategory.slug == cat_data["slug"]
                )
            )
            if existing.scalar_one_or_none():
                print(f"  skip {cat_data['slug']} (exists)")
                continue
            cat = BusinessCategory(**cat_data)
            db.add(cat)
            print(f"  added {cat_data['slug']}")
        await db.commit()
        print("Done.")


if __name__ == "__main__":
    asyncio.run(seed())
