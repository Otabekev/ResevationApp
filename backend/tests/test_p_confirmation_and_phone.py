"""
Confirmation richness (item 8) + manual-booking phone validation (item 9).

  P1. booking_confirmed_message includes address / phone / price when given.
  P2. …and omits them cleanly when not given (no dangling labels).
  P3. Manual booking rejects a non-phone like "asdf".
  P4. Manual booking normalizes a valid Uzbek number to +998XXXXXXXXX.
"""
import pytest
from pydantic import ValidationError

from app.routers.bookings import BookingCreateManual
from app.services.notification_service import booking_confirmed_message


def test_p1_confirmation_includes_address_phone_price():
    msg = booking_confirmed_message(
        lang="uz", business_name="Anora", service_name="Soch olish",
        staff_name="Aziz", date_str="2026-07-20", time_str="10:00",
        address="Pop, Mustaqillik 5", phone="+998901234567", price=80000,
    )
    assert "Pop, Mustaqillik 5" in msg      # address
    assert "+998901234567" in msg           # phone
    assert "80,000" in msg and "so'm" in msg  # price + unit
    assert "Soch olish" in msg


def test_p2_confirmation_omits_optionals_when_absent():
    msg = booking_confirmed_message(
        lang="en", business_name="Anora", service_name="Cut",
        staff_name="Aziz", date_str="2026-07-20", time_str="10:00",
    )
    # No dangling labels when the data isn't provided.
    assert "Address" not in msg
    assert "Phone" not in msg
    assert "Price" not in msg
    assert "Booking confirmed" in msg


def _manual(**over):
    base = dict(
        service_id=1, booking_date="2030-01-01", start_time="10:00",
        customer_name="Walk-in", customer_phone="+998901234567",
    )
    base.update(over)
    return BookingCreateManual(**base)


def test_p3_manual_rejects_garbage_phone():
    with pytest.raises(ValidationError):
        _manual(customer_phone="asdf")


def test_p4_manual_normalizes_uz_phone():
    assert _manual(customer_phone="90 123 45 67").customer_phone == "+998901234567"
    assert _manual(customer_phone="998901234567").customer_phone == "+998901234567"
    assert _manual(customer_phone="+998 90 123 45 67").customer_phone == "+998901234567"
