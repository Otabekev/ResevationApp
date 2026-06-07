"""
Time helpers. Bookings are stored as naive local date+time; Uzbekistan uses a
single timezone (Asia/Tashkent), so we treat that as the platform timezone and
convert to UTC for any comparison against `now`.
"""
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

PLATFORM_TZ = ZoneInfo("Asia/Tashkent")


def now_local() -> datetime:
    """Current time in the business/platform timezone (tz-aware)."""
    return datetime.now(PLATFORM_TZ)


def to_local(d: date, t: time) -> datetime:
    """Combine a stored local date+time into a tz-aware local datetime."""
    return datetime.combine(d, t, tzinfo=PLATFORM_TZ)


def to_utc(d: date, t: time) -> datetime:
    """Convert a stored local date+time to a tz-aware UTC datetime."""
    return to_local(d, t).astimezone(timezone.utc)
