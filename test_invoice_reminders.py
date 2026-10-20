"""تست یادآوری فاکتورهای پرداخت‌نشده (invoice_reminders) —
اجرا: BOT_TOKEN=1:x ADMIN_ID=1 ADMIN_API_SECRET=x python -m pytest test_invoice_reminders.py"""
import asyncio
import datetime
import os
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("ADMIN_API_SECRET", "x")

import pytest

import bot_settings
import invoice_reminders as ir
import pending_cases
import runtime_state
from final_print import TEHRAN_TZ

NOON = datetime.datetime(2026, 10, 20, 12, 0, tzinfo=TEHRAN_TZ)


@pytest.fixture(autouse=True)
def _files(tmp_path, monkeypatch):
    monkeypatch.setattr(pending_cases, "STORE_FILE", str(tmp_path / "pc.json"))
    monkeypatch.setattr(ir, "STATE_FILE", str(tmp_path / "ir.json"))
    monkeypatch.setattr(pending_cases, "_now", lambda: NOON)
    monkeypatch.setattr(ir, "SEND_GAP_SECONDS", 0)
    monkeypatch.setattr(bot_settings, "_values", {})

    async def no_sync(uid):
        return None
    monkeypatch.setattr(pending_cases, "sync_with_panel", no_sync)
    runtime_state.pending_admin_payment_review.clear()
    yield


def _bot():
    bot = MagicMock()
    bot.id = None
    bot.send_message = AsyncMock()
    return bot


def _add(uid, tc, hours_ago, service="CHECK", fee=500_000, paid=False):
    pending_cases._upsert(uid, pending_cases.KIND_LAVAYEH,
                          {"tracking_code": tc, "final_fee": fee}, paid=paid, service_type=service)
    data = pending_cases._load()
    for it in data["items"]:
        if it["tracking_code"] == tc:
            it["registered_at"] = (NOON - datetime.timedelta(hours=hours_ago)).isoformat()
    pending_cases._save(data)


def _run(bot, now=NOON):
    return asyncio.run(ir.run_once(bot, now))


def test_first_reminder_once_with_pay_button():
    _add(10, "T1", hours_ago=2)
    bot = _bot()
    assert _run(bot) == 1
    args, kwargs = bot.send_message.call_args
    assert args[0] == 10 and "50,000 تومان" in args[1]
    assert kwargs["reply_markup"].inline_keyboard[0][0].callback_data == "pc:pay:T1"
    assert _run(bot) == 0   # تکرار نمی‌شود


def test_not_due_yet_paid_admin_or_zero_fee_skipped():
    _add(10, "T1", hours_ago=0.5)
    _add(11, "T2", hours_ago=2, paid=True)
    _add(1, "T3", hours_ago=2)            # ADMIN_ID
    _add(12, "T4", hours_ago=2, fee=0)
    assert _run(_bot()) == 0


def test_old_invoice_skips_first_and_gets_last_before_expiry():
    _add(10, "OLD", hours_ago=30)                              # چک: ۳۰ روز
    assert _run(_bot()) == 0
    _add(11, "LV", hours_ago=4 * 24 - 5, service="LAVAYEH")     # ۵ ساعت تا حذف
    bot = _bot()
    assert _run(bot) == 1
    assert "آخرین یادآوری" in bot.send_message.call_args[0][1]
    assert _run(bot) == 0


def test_quiet_hours_and_disabled_setting(monkeypatch):
    _add(10, "T1", hours_ago=2)
    night = NOON.replace(hour=23)
    monkeypatch.setattr(pending_cases, "_now", lambda: night)
    assert _run(_bot(), night) == 0
    monkeypatch.setattr(pending_cases, "_now", lambda: NOON)
    monkeypatch.setattr(bot_settings, "_values", {"reminder.enabled": "false"})
    assert _run(_bot()) == 0


def test_receipt_under_review_skipped():
    _add(10, "T1", hours_ago=2)
    runtime_state.pending_admin_payment_review[10] = {}
    assert _run(_bot()) == 0


def test_first_hours_setting(monkeypatch):
    _add(10, "T1", hours_ago=2)
    monkeypatch.setattr(bot_settings, "_values", {"reminder.first_hours": "3"})
    assert _run(_bot()) == 0
