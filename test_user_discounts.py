"""تست تخفیف اختصاصی — اجرا: BOT_TOKEN=x ADMIN_ID=1 ADMIN_API_SECRET=x python -m pytest test_user_discounts.py"""
import json
import os

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("ADMIN_API_SECRET", "x")

import pytest

import prepay_registration
import runtime_state
import user_discounts


@pytest.fixture(autouse=True)
def _discounts(monkeypatch):
    monkeypatch.setattr(user_discounts, "_percents", {"7": 30})
    prepay_registration._pending_discounts.clear()
    runtime_state.prepaid_registrations = {}
    runtime_state.consumed_prepay_for_panel = {}


def _invoice(uid, ptype, amount):
    return {"chat_id": uid, "payload": json.dumps({"type": ptype, "uid": uid}),
            "description": "x", "prices": [{"label": "l", "amount": amount}]}


def test_inquiry_invoice_discounted_once():
    data = user_discounts.apply_to_invoice(_invoice(7, "single", 650_000))
    assert data["prices"][0]["amount"] == 455_000
    # ارسال دوبارهٔ همان فاکتور نباید دوباره تخفیف بخورد
    again = user_discounts.apply_to_invoice(data)
    assert again["prices"][0]["amount"] == 455_000


def test_other_invoices_and_users_untouched():
    final = _invoice(7, "lavayeh", 2_000_000)
    assert user_discounts.apply_to_invoice(final) is final
    other = _invoice(8, "cart", 650_000)
    assert user_discounts.apply_to_invoice(other) is other


def test_discount_keeps_min_invoice():
    assert user_discounts.discount_amount(7, 12_000) == 2_000
    assert user_discounts.discount_amount(7, 10_000) == 0


def test_prepay_discount_credited_in_full_at_final():
    # کاربر ۷۰٪ پیش‌پرداخت ۱,۰۰۰,۰۰۰ ریالی را می‌پردازد
    prepay_registration._pending_discounts[7] = 300_000
    prepay_registration.register_prepaid(7, 70_000, "lavayeh", "لایحه")
    fee, info = prepay_registration.adjust_final_fee_with_prepay(7, 5_000_000)
    assert fee == 4_000_000
    assert info["applied_rial"] == 1_000_000
    # مبنای سود پنل فقط پول واقعاً دریافت‌شده است
    assert runtime_state.consumed_prepay_for_panel[7]["amount_toman"] == 70_000
