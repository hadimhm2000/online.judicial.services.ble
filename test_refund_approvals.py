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
