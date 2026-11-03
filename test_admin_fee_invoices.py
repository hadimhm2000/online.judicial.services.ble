"""تست اصلاحیه ۱۴۰۵/۰۸ — فاکتورهای دستی مدیر (/fee) با شناسهٔ یکتا per فاکتور.

مشکل قبلی: pending_admin_fee_payments فقط با آیدی کاربر کلید می‌خورد → فاکتور
دومِ همان کاربر اولی را بازنویسی می‌کرد؛ و پرداخت فاکتوری که رکوردی برایش
نبود فقط پیام «فاکتور فعالی ثبت نشده» می‌گرفت — بدون برگشت پول به کاربر و
بدون هشدار به مدیر.

اجرا: BOT_TOKEN=1:x ADMIN_ID=1 ADMIN_API_SECRET=x python -m pytest test_admin_fee_invoices.py
"""
import asyncio
import datetime
import json
import os
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("ADMIN_API_SECRET", "x")

import pytest

import runtime_state
import wallet
from admin_relay import admin_fee_successful_payment
from config import ADMIN_ID


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(wallet, "STORE_FILE", str(tmp_path / "wallet.json"))
    wallet._store = {"users": {}, "offers": {}, "holds": {}, "autopaid": {}}
    wallet._lock = asyncio.Lock()
    runtime_state.pending_admin_fee_payments.clear()

    # عوارض جانبی هندلر (شیت/پنل) در تست بی‌اثر می‌شوند
    import sheets
    import panel_sync

    async def _noop_event(*a, **k):
        return None

    async def _noop_case(*a, **k):
        return None

    monkeypatch.setattr(sheets, "log_event", _noop_event)
    monkeypatch.setattr(panel_sync, "upsert_case_to_panel", _noop_case)
    monkeypatch.setattr(panel_sync, "mark_case_ready_to_send_by_tracking", _noop_case)
    yield
    runtime_state.pending_admin_fee_payments.clear()


def _record(fid, uid, amount_rial, svc="INQUIRY", tracking=""):
    rec = {
        "uid": uid,
        "invoice_time": datetime.datetime.now(),
        "final_fee": amount_rial,
        "service_type": svc,
        "tracking_code": tracking,
        "sign_menu_path": None,
        "admin_id": ADMIN_ID,
    }
    if fid is not None:
        rec["fid"] = fid
    return rec


def _payment_msg(uid, fid, amount_rial):
    msg = MagicMock()
    msg.from_user.id = uid
    msg.from_user.full_name = "کاربر تست"
    msg.answer = AsyncMock()
    msg.successful_payment.total_amount = amount_rial
    msg.successful_payment.telegram_payment_charge_id = "BALE-X1"
    pl = {"type": "admin_fee", "uid": uid}
    if fid:
        pl["fid"] = fid
    msg.successful_payment.invoice_payload = json.dumps(pl)
    return msg


def _run(msg):
    state = MagicMock()
    state.clear = AsyncMock()
    bot = MagicMock()
    bot.send_message = AsyncMock()
    asyncio.run(admin_fee_successful_payment(msg, state, bot))
    return state, bot


def test_second_invoice_does_not_overwrite_first():
    """دو فاکتور هم‌زمان برای یک کاربر هر دو سر جایشان می‌مانند."""
    runtime_state.pending_admin_fee_payments["f1"] = _record("f1", 7, 100_000, tracking="T1")
    runtime_state.pending_admin_fee_payments["f2"] = _record("f2", 7, 200_000, tracking="T2")
    assert len(runtime_state.pending_admin_fee_payments) == 2


def test_payment_routes_to_its_own_invoice_by_fid():
    """پرداخت فاکتور دوم → فقط رکورد همان فاکتور مصرف می‌شود؛ اولی می‌ماند."""
    runtime_state.pending_admin_fee_payments["f1"] = _record("f1", 7, 100_000, tracking="T1")
    runtime_state.pending_admin_fee_payments["f2"] = _record("f2", 7, 200_000, tracking="T2")
    msg = _payment_msg(7, "f2", 200_000)
    _run(msg)
    assert "f2" not in runtime_state.pending_admin_fee_payments
    assert "f1" in runtime_state.pending_admin_fee_payments
    # مبلغ درست (فاکتور دوم) به کاربر اعلام شد
    text = msg.answer.call_args.args[0]
    assert "20,000 تومان" in text


def test_legacy_payment_without_fid_matches_latest_record():
    """فاکتور قدیمی بدون fid → آخرین فاکتور فعال همان کاربر (سازگاری)."""
    runtime_state.pending_admin_fee_payments[7] = _record(None, 7, 150_000, tracking="OLD")
    msg = _payment_msg(7, "", 150_000)   # payload بدون fid
    _run(msg)
    assert 7 not in runtime_state.pending_admin_fee_payments
    assert "15,000 تومان" in msg.answer.call_args.args[0]


def test_payment_without_record_refunds_and_alerts_admin():
    """پرداخت فاکتور بدون رکورد → مبلغ به کیف پول برمی‌گردد + هشدار مدیر."""
    msg = _payment_msg(7, "ghost", 100_000)
    state, bot = _run(msg)
    # پول به کیف پول کاربر برگشت
    assert wallet.balance(7) == 10_000
    # کاربر جواب روشن گرفت (نه فقط «فاکتور فعالی ثبت نشده»)
    assert "برگشت" in msg.answer.call_args.args[0]
    # مدیر هشدار گرفت
    admin_texts = [c.args[1] for c in bot.send_message.await_args_list
                   if c.args and c.args[0] == ADMIN_ID and len(c.args) > 1]
    assert admin_texts and "بدون رکورد" in admin_texts[0] and "کاربر 7" in admin_texts[0]
    state.clear.assert_awaited()


def test_wrong_user_fid_not_matched_and_refunded():
    """fid متعلق به کاربر دیگری → تطبیق نمی‌خورد و مبلغ برمی‌گردد."""
    runtime_state.pending_admin_fee_payments["f1"] = _record("f1", 8, 100_000)
    msg = _payment_msg(7, "f1", 100_000)   # کاربر ۷ فاکتور کاربر ۸ را پرداخت کرده
    _run(msg)
    # رکورد کاربر ۸ دست‌نخورده ماند و پول کاربر ۷ برگشت
    assert "f1" in runtime_state.pending_admin_fee_payments
    assert wallet.balance(7) == 10_000 and wallet.balance(8) == 0
