"""تست صف تایید بازگشت وجه —
اجرا: BOT_TOKEN=1:x ADMIN_ID=1 ADMIN_API_SECRET=x python -m pytest test_refund_approvals.py"""
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("ADMIN_API_SECRET", "x")

import pytest

import refund_approvals as ra
import runtime_state
import wallet


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(wallet, "STORE_FILE", str(tmp_path / "wallet.json"))
    wallet._store = {"users": {}, "offers": {}, "holds": {}, "autopaid": {}}
    wallet._lock = asyncio.Lock()
    monkeypatch.setattr(ra, "STORE_FILE", str(tmp_path / "refund_approvals.json"))
    ra._store = {"items": {}}
    ra._lock = asyncio.Lock()
    ra._bot = None
    runtime_state.prepaid_registrations.clear()
    runtime_state.incomplete_tasks.clear()
    yield
    runtime_state.prepaid_registrations.clear()
    runtime_state.incomplete_tasks.clear()


def test_request_does_not_credit_wallet():
    rid = ra.request_refund_nowait(7, 5_000, "مازاد", source="t")
    assert rid and wallet.balance(7) == 0
    assert ra.pending_total_toman(7) == 5_000


def test_non_positive_amount_ignored():
    assert ra.request_refund_nowait(7, 0, "x") is None
    assert ra.request_refund_nowait(7, -5, "x") is None
    assert ra.pending() == []


def test_approve_credits_once_and_is_idempotent():
    rid = ra.request_refund_nowait(7, 5_000, "مازاد")
    assert run(ra.decide(rid, True, 1))[0] == "done"
    assert wallet.balance(7) == 5_000
    assert run(ra.decide(rid, True, 1))[0] == "closed"   # کلیک دوم
    assert wallet.balance(7) == 5_000
    assert ra.pending_total_toman(7) == 0


def test_reject_never_credits():
    rid = ra.request_refund_nowait(7, 5_000, "مازاد")
    assert run(ra.decide(rid, False, 1))[0] == "done"
    assert wallet.balance(7) == 0
    assert run(ra.decide(rid, True, 1))[0] == "closed"   # بعد از رد، تایید اثری ندارد
    assert wallet.balance(7) == 0


def test_credit_failure_returns_to_pending(monkeypatch):
    rid = ra.request_refund_nowait(7, 5_000, "مازاد")
    real_credit = wallet.credit

    async def boom(*a, **k):
        raise RuntimeError("disk")
    monkeypatch.setattr(wallet, "credit", boom)
    assert run(ra.decide(rid, True, 1))[0] == "failed"
    assert ra.pending_total_toman(7) == 5_000     # هنوز قابل تلاش دوباره
    monkeypatch.setattr(wallet, "credit", real_credit)
    assert run(ra.decide(rid, True, 1))[0] == "done"
    assert wallet.balance(7) == 5_000


def test_dedupe_key_blocks_duplicates_but_not_after_reject():
    a = ra.request_refund_nowait(7, 5_000, "x", dedupe_key="k1")
    b = ra.request_refund_nowait(7, 5_000, "x", dedupe_key="k1")
    assert a == b and len(ra.pending()) == 1
    run(ra.decide(a, False, 1))
    c = ra.request_refund_nowait(7, 5_000, "x", dedupe_key="k1")
    assert c != a


def test_cancel_pending_by_key():
    ra.request_refund_nowait(7, 5_000, "x", dedupe_key="clr-fail:R1")
    assert ra.cancel_pending("clr-fail:R1") == 1
    assert ra.pending() == []
    assert wallet.balance(7) == 0


def test_persisted_across_restart(tmp_path):
    rid = ra.request_refund_nowait(7, 5_000, "x")
    ra._store = {"items": {}}
    ra._load()
    assert rid in ra._store["items"] and ra.pending_total_toman(7) == 5_000


def test_button_requires_admin():
    rid = ra.request_refund_nowait(7, 5_000, "x")
    cb = MagicMock()
    cb.data = f"rfd:ok:{rid}"
    cb.from_user.id = 999          # غیرمدیر (ADMIN_ID=1)
    cb.answer = AsyncMock()
    run(ra._decide(cb, True))
    assert wallet.balance(7) == 0 and ra.pending_total_toman(7) == 5_000


def test_admin_button_approves_and_notifies_user():
    rid = ra.request_refund_nowait(7, 5_000, "x")
    cb = MagicMock()
    cb.data = f"rfd:ok:{rid}"
    cb.from_user.id = ra.ADMIN_ID
    cb.answer = AsyncMock()
    cb.message.edit_text = AsyncMock()
    cb.bot.send_message = AsyncMock()
    run(ra._decide(cb, True))
    assert wallet.balance(7) == 5_000
    assert cb.bot.send_message.await_args.args[0] == 7


def test_notify_pending_sends_once_with_buttons():
    rid = ra.request_refund_nowait(7, 5_000, "x")
    bot = MagicMock()
    bot.send_message = AsyncMock()
    run(ra.notify_pending(bot))
    run(ra.notify_pending(bot))
    assert bot.send_message.await_count == 1
    kb = bot.send_message.await_args.kwargs["reply_markup"]
    datas = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert datas == [f"rfd:ok:{rid}", f"rfd:no:{rid}"]


def test_duplicate_payment_refund_stays_automatic():
    """مورد ۳ و ۴ درخواست: برگشت خودکار بدون تایید مدیر (مسیر مستقیم wallet.credit)."""
    run(wallet.credit(7, 3_000, "refund", "پرداخت تکراری"))
    assert wallet.balance(7) == 3_000 and ra.pending() == []


# ── شکست ثبت در سرویس‌ها: بازگشت پیش‌پرداخت فقط با تایید مدیر ─────────────

def _prepay(uid, paid_rial, credit_rial=0, discount_rial=0, charge="c1"):
    runtime_state.prepaid_registrations[uid] = {
        "amount_rial": paid_rial + credit_rial, "amount_toman": (paid_rial + credit_rial) // 10,
        "prepay_paid_rial": paid_rial, "discount_rial": discount_rial, "charge_id": charge}


def test_incomplete_task_creates_pending_refund_not_credit():
    _prepay(7, 20_000)                    # ۲,۰۰۰ تومان (مبلغ تست)
    runtime_state.incomplete_tasks["lavayeh:B1"] = {"bill_no": "B1", "user_id": 7, "type": "lavayeh"}
    assert wallet.balance(7) == 0 and ra.pending_total_toman(7) == 2_000
    assert ra.pending()[0]["source"] == "service_fail"


def test_failure_refund_excludes_discount_and_previous_credit():
    _prepay(7, 20_000, credit_rial=50_000, discount_rial=5_000)
    runtime_state.incomplete_tasks["tn:B2"] = {"bill_no": "B2", "user_id": 7, "type": "tn"}
    assert ra.pending_total_toman(7) == 1_500       # (۲۰٬۰۰۰ − ۵٬۰۰۰) ریال؛ بدون مانده قبلی


def test_approval_credits_and_removes_prepay_so_it_is_not_deducted_twice():
    _prepay(7, 20_000, credit_rial=50_000)
    runtime_state.incomplete_tasks["ezhhar:B3"] = {"bill_no": "B3", "user_id": 7, "type": "ezhhar"}
    rid = ra.pending()[0]["id"]
    assert run(ra.decide(rid, True, 1))[0] == "done"
    assert wallet.balance(7) == 2_000
    # ⭐️ v2: رزرو همین درخواست released شد؛ فقط ماندهٔ آزاد قبلی ماند
    rec = runtime_state.prepaid_registrations[7]
    assert rec.get("version") == 2 and rec.get("free_credit_rial") == 50_000
    assert all(r.get("status") == "released" for r in rec.get("reservations", []))


def test_approval_removes_record_when_only_prepay():
    _prepay(7, 20_000)
    runtime_state.incomplete_tasks["lavayeh:B4"] = {"bill_no": "B4", "user_id": 7, "type": "lavayeh"}
    run(ra.decide(ra.pending()[0]["id"], True, 1))
    # ⭐️ v2: رکورد می‌ماند اما هیچ رزرو فعالی برای کسر مجدد نیست
    rec = runtime_state.prepaid_registrations[7]
    active = [r for r in rec.get("reservations", [])
              if r.get("status") in ("hold", "reserved", "queued")]
    assert active == [] and rec.get("free_credit_rial") == 0


def test_reject_keeps_prepay_for_next_use():
    _prepay(7, 20_000)
    runtime_state.incomplete_tasks["lavayeh:B5"] = {"bill_no": "B5", "user_id": 7, "type": "lavayeh"}
    run(ra.decide(ra.pending()[0]["id"], False, 1))
    assert wallet.balance(7) == 0
    # ⭐️ v2: رزرو همچنان فعال است (برای استفادهٔ بعدی)
    rec = runtime_state.prepaid_registrations[7]
    active = [r for r in rec.get("reservations", [])
              if r.get("status") in ("hold", "reserved", "queued")]
    assert len(active) == 1 and active[0].get("reserved_rial") == 20_000


def test_stale_when_prepay_already_consumed_pays_nothing():
    _prepay(7, 20_000)
    runtime_state.incomplete_tasks["lavayeh:B6"] = {"bill_no": "B6", "user_id": 7, "type": "lavayeh"}
    rid = ra.pending()[0]["id"]
    runtime_state.prepaid_registrations.pop(7)       # در فاکتور نهایی مصرف شد
    assert run(ra.decide(rid, True, 1))[0] == "stale"
    assert wallet.balance(7) == 0 and ra.pending() == []


def test_stale_when_prepay_replaced_by_new_payment():
    _prepay(7, 20_000, charge="old")
    runtime_state.incomplete_tasks["lavayeh:B7"] = {"bill_no": "B7", "user_id": 7, "type": "lavayeh"}
    rid = ra.pending()[0]["id"]
    _prepay(7, 40_000, charge="new")
    assert run(ra.decide(rid, True, 1))[0] == "stale"
    assert wallet.balance(7) == 0


def test_credit_failure_restores_prepay_record(monkeypatch):
    _prepay(7, 20_000, credit_rial=50_000)
    runtime_state.incomplete_tasks["lavayeh:B8"] = {"bill_no": "B8", "user_id": 7, "type": "lavayeh"}
    rid = ra.pending()[0]["id"]

    async def boom(*a, **k):
        raise RuntimeError("disk")
    real = wallet.credit
    monkeypatch.setattr(wallet, "credit", boom)
    assert run(ra.decide(rid, True, 1))[0] == "failed"
    # ⭐️ v2: رزرو به حالت فعال برگشت (مثل قبل از تصمیم)
    rec = runtime_state.prepaid_registrations[7]
    active = [r for r in rec.get("reservations", [])
              if r.get("status") in ("hold", "reserved", "queued")]
    assert len(active) == 1 and active[0].get("paid_rial") == 20_000
    assert rec.get("free_credit_rial") == 50_000
    monkeypatch.setattr(wallet, "credit", real)
    assert run(ra.decide(rid, True, 1))[0] == "done"


def test_no_request_without_prepay_or_for_bulk_rows_or_on_silent_load():
    runtime_state.incomplete_tasks["lavayeh:N1"] = {"bill_no": "N1", "user_id": 9, "type": "lavayeh"}
    _prepay(7, 20_000)
    runtime_state.incomplete_tasks["lavayeh:N2"] = {
        "bill_no": "N2", "user_id": 7, "type": "lavayeh", "task_data": {"_is_bulk": True}}
    dict.__setitem__(runtime_state.incomplete_tasks, "lavayeh:N3", {"user_id": 7, "type": "lavayeh"})
    assert ra.pending() == []


def test_same_task_key_not_requested_twice():
    _prepay(7, 20_000)
    runtime_state.incomplete_tasks["lavayeh:D1"] = {"bill_no": "D1", "user_id": 7, "type": "lavayeh"}
    runtime_state.incomplete_tasks["lavayeh:D1"] = {"bill_no": "D1", "user_id": 7, "type": "lavayeh", "x": 1}
    assert len(ra.pending()) == 1


def test_consuming_prepay_cancels_pending_failure_refund_and_success_cancels_by_key():
    _prepay(7, 20_000)
    runtime_state.incomplete_tasks["lavayeh:E1"] = {"bill_no": "E1", "user_id": 7, "type": "lavayeh"}
    assert ra.cancel_pending_for_user(7, "service_fail") == 1 and ra.pending() == []
    _prepay(8, 20_000)
    runtime_state.incomplete_tasks["lavayeh:E2"] = {"bill_no": "E2", "user_id": 8, "type": "lavayeh"}
    assert ra.cancel_pending("svc-fail:lavayeh:E2") == 1 and ra.pending() == []


def test_request_failure_refund_direct_for_check_and_ealam():
    _prepay(7, 20_000)
    assert ra.request_failure_refund(7, "check:T1", "ثبت دادخواست چک")
    assert ra.request_failure_refund(7, "check:T1", "ثبت دادخواست چک") == ra.pending()[0]["id"]
    assert len(ra.pending()) == 1 and wallet.balance(7) == 0
