"""
Reminder scheduler (_send_reminders).

  N1. PENDING bookings get reminded — not just confirmed (the requires_confirmation
      no-show gap). Before the fix the send count was 0.
  N2. A transient Telegram failure leaves reminder_*_sent False so the next sweep
      retries; a later success sets it and stops.
  N3. Walk-in pending (no telegram_id) is skipped but flagged, so it isn't
      rescanned forever.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.models.booking import Booking, Customer
from app.services import scheduler
from app.timeutils import PLATFORM_TZ
from tests import factories as f


async def _booking_24h_out(db, *, status, telegram_id=5555):
    """A booking whose local start time is ~24h from now, so to_utc() lands in
    the 24h reminder window."""
    cat = await f.create_category(db)
    owner = await f.create_user(db, role="business_owner", telegram_id=telegram_id + 1)
    biz = await f.create_business(db, owner_id=owner.id, category_id=cat.id)
    svc = await f.create_service(db, business_id=biz.id)
    cust = await f.create_customer(db, telegram_id=telegram_id)
    target = (datetime.now(timezone.utc) + timedelta(hours=24)).astimezone(PLATFORM_TZ)
    booking = await f.create_booking(
        db, business_id=biz.id, service_id=svc.id, staff_id=None, customer_id=cust.id,
        booking_date=target.date(), start_time=target.time().replace(second=0, microsecond=0),
        status=status,
    )
    return booking, cust


def _patch(monkeypatch, sessionmaker_, sender):
    monkeypatch.setattr(scheduler, "AsyncSessionLocal", sessionmaker_)
    monkeypatch.setattr(scheduler, "send_telegram_message", sender)
    monkeypatch.setattr(scheduler, "send_telegram_location", sender)


async def test_n1_pending_booking_gets_reminded(db, sessionmaker_, monkeypatch):
    booking, _ = await _booking_24h_out(db, status="pending")
    sent = []

    async def _send(chat_id, *a, **k):
        sent.append(chat_id)
        return True

    _patch(monkeypatch, sessionmaker_, _send)
    await scheduler._send_reminders()

    assert 5555 in sent, "pending booking should have been reminded"
    refreshed = await db.get(Booking, booking.id)
    await db.refresh(refreshed)
    assert refreshed.reminder_24h_sent is True


async def test_n2_transient_failure_retries_then_succeeds(db, sessionmaker_, monkeypatch):
    booking, _ = await _booking_24h_out(db, status="confirmed", telegram_id=5560)

    # First sweep: send fails → flag must stay False (so it can be retried).
    async def _fail(chat_id, *a, **k):
        return False

    _patch(monkeypatch, sessionmaker_, _fail)
    await scheduler._send_reminders()
    refreshed = await db.get(Booking, booking.id)
    await db.refresh(refreshed)
    assert refreshed.reminder_24h_sent is False, "failed send must not mark the reminder sent"

    # Second sweep: send succeeds → flag flips, no permanent loss.
    calls = []

    async def _ok(chat_id, *a, **k):
        calls.append(chat_id)
        return True

    _patch(monkeypatch, sessionmaker_, _ok)
    await scheduler._send_reminders()
    refreshed = await db.get(Booking, booking.id)
    await db.refresh(refreshed)
    assert 5560 in calls
    assert refreshed.reminder_24h_sent is True


async def test_n3_walkin_pending_skipped_but_flagged(db, sessionmaker_, monkeypatch):
    booking, cust = await _booking_24h_out(db, status="pending", telegram_id=5570)
    # Make the customer a walk-in (no Telegram) after creation.
    cust = await db.get(Customer, cust.id)
    cust.telegram_id = None
    await db.commit()

    sent = []

    async def _send(chat_id, *a, **k):
        sent.append(chat_id)
        return True

    _patch(monkeypatch, sessionmaker_, _send)
    await scheduler._send_reminders()

    assert sent == [], "walk-in with no Telegram should not be messaged"
    refreshed = await db.get(Booking, booking.id)
    await db.refresh(refreshed)
    assert refreshed.reminder_24h_sent is True, "flag set so the row isn't rescanned forever"


async def test_n4_reminder_carries_cancel_button(db, sessionmaker_, monkeypatch):
    """The reminder must include a one-tap Cancel button routing to the bot's
    cancel_ask handler — a can't-make-it customer frees the slot vs no-showing."""
    booking, _ = await _booking_24h_out(db, status="confirmed", telegram_id=5580)
    calls = []

    async def _send(chat_id, *a, **k):
        calls.append(k)
        return True

    _patch(monkeypatch, sessionmaker_, _send)
    await scheduler._send_reminders()

    kb = next((k.get("reply_markup") for k in calls if k.get("reply_markup")), None)
    assert kb is not None, "reminder should carry an inline keyboard"
    assert kb["inline_keyboard"][0][0]["callback_data"] == f"cancel_ask_{booking.id}"
