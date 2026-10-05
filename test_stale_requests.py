"""تست لغو خودکار درخواست‌های بی‌پیشرفت پس از ۲۴ ساعت (stale_requests) —
اجرا: BOT_TOKEN=1:x ADMIN_ID=1 ADMIN_API_SECRET=x python -m pytest test_stale_requests.py"""
import asyncio
import datetime
import os
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("ADMIN_API_SECRET", "x")

import pytest

import panel_sync
import runtime_state
import sana_gate
import stale_requests as sr


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for name in ("pending_lavayeh_payments", "pending_lavayeh_sign", "pending_nid_fix_windows",
                 "incomplete_tasks", "pending_admin_payment_review"):
        getattr(runtime_state, name).clear()
    runtime_state.active_lavayeh_users.clear()
    monkeypatch.setattr(sana_gate, "is_outage", lambda: False)
    monkeypatch.setattr(sana_gate, "deferred_by_user", lambda: {})
    yield


def _bot():
    bot = MagicMock()
    bot.id = None
    bot.send_message = AsyncMock()
    return bot


def _ago(hours):
    return datetime.datetime.now() - datetime.timedelta(hours=hours)


def test_excludes_users_with_live_process(monkeypatch):
    runtime_state.pending_lavayeh_payments[10] = {"invoice_time": _ago(2)}    # تازه → کنار
    runtime_state.pending_lavayeh_payments[11] = {"invoice_time": _ago(30)}   # کهنه → نه
    runtime_state.pending_nid_fix_windows[12] = {"deadline": datetime.datetime.now()
                                                 + datetime.timedelta(minutes=10)}
    monkeypatch.setattr(sana_gate, "deferred_by_user", lambda: {13: [{}]})
    ex = sr._excluded_users()
    assert {"10", "12", "13"} <= ex
    assert "11" not in ex


def test_sweep_clears_memory_and_notifies_paid_only(monkeypatch):
    runtime_state.pending_lavayeh_payments[101] = {"invoice_time": _ago(30)}
    runtime_state.active_lavayeh_users.add(101)
    runtime_state.incomplete_tasks["lavayeh:T1"] = {"user_id": 101}
    runtime_state.pending_lavayeh_payments[4] = {"invoice_time": _ago(2)}
    seen = {}

    async def fake(hours, win, excl):
        seen.update(hours=hours, excl=excl)
        return {"expired": 5, "userIds": ["101", "102", "107"], "recent": [
            {"baleUserId": "101", "serviceType": "LAVAYEH", "trackingCode": "T1", "paid": True},
            {"baleUserId": "102", "serviceType": "CHECK", "paid": False},
            {"baleUserId": "107", "serviceType": "CLEARANCE_CERT", "paid": True}]}
    monkeypatch.setattr(panel_sync, "expire_stale_cases", fake)

    bot = _bot()
    asyncio.run(sr.sweep(bot))

    assert seen["hours"] == 24 and "4" in seen["excl"]
    assert 101 not in runtime_state.pending_lavayeh_payments
    assert 101 not in runtime_state.active_lavayeh_users
    assert not runtime_state.incomplete_tasks
    assert 4 in runtime_state.pending_lavayeh_payments
    sent = {c.args[0]: c.args[1] for c in bot.send_message.call_args_list}
    assert set(sent) == {101, 107, sr.ADMIN_ID}
    assert "09306186888" in sent[101] and "T1" in sent[101]
    assert "گواهی عدم سوءپیشینه" in sent[107]
    assert "2 پروندهٔ قدیمی‌تر" in sent[sr.ADMIN_ID]


def test_skipped_during_outage(monkeypatch):
    monkeypatch.setattr(sana_gate, "is_outage", lambda: True)
    called = AsyncMock()
    monkeypatch.setattr(panel_sync, "expire_stale_cases", called)
    asyncio.run(sr.sweep(_bot()))
    called.assert_not_called()


def test_downtime_extends_window():
    assert sr._effective_hours(0) == 24
    assert sr._effective_hours(3 * 3600) == 28
