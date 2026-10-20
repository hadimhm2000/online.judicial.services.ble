"""تست صف خارج از ساعت کاری / قطعی سامانه — اجرا: BOT_TOKEN=x ADMIN_ID=1 ADMIN_API_SECRET=x python -m pytest test_sana_gate.py"""
import asyncio
import datetime
import os
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("ADMIN_API_SECRET", "x")

import pytest

import runtime_state
import sana_gate
from working_hours import TEHRAN_TZ


@pytest.fixture(autouse=True)
def _tmp_state(tmp_path, monkeypatch):
    monkeypatch.setattr(sana_gate, "STATE_FILE", str(tmp_path / "gate.json"))
    sana_gate._state.update({"outage": False, "outage_since": None, "browser_closed": False, "deferred": []})


def _at(hour):
    return datetime.datetime(2026, 10, 2, hour, 0, tzinfo=TEHRAN_TZ)


def test_working_hours_boundaries():
    assert not sana_gate.is_working_hours(_at(13))
    assert sana_gate.is_working_hours(_at(14))
    assert not sana_gate.is_working_hours(_at(22))


def test_sign_tasks_never_deferred(monkeypatch):
    monkeypatch.setattr(sana_gate, "is_working_hours", lambda now=None: False)
    assert sana_gate.should_defer({"task_type": "LAVAYEH_SUBMIT"})
    assert not sana_gate.should_defer({"task_type": "LAVAYEH_SUBMIT_SIGN"})


def test_outage_defers_inside_working_hours(monkeypatch):
    monkeypatch.setattr(sana_gate, "is_working_hours", lambda now=None: True)
    assert not sana_gate.should_defer({"task_type": "CHECK_SUBMIT"})
    sana_gate._state["outage"] = True
    assert sana_gate.should_defer({"task_type": "CHECK_SUBMIT"})


def test_defer_persists_and_release_requeues(monkeypatch):
    async def scenario():
        monkeypatch.setattr(sana_gate, "is_working_hours", lambda now=None: False)
        bot = MagicMock()
        bot.send_message = AsyncMock()
        runtime_state.job_queue = asyncio.Queue()
        await sana_gate.defer({"task_type": "LAVAYEH_SUBMIT", "user_id": 7}, bot)
        await sana_gate.defer({"task_type": "CHECK_SUBMIT", "user_id": 8}, bot)
        assert bot.send_message.await_args_list[0].args[0] == 7

        sana_gate._state["deferred"] = []
        sana_gate.load()                       # بازیابی پس از ری‌استارت
        assert sana_gate.deferred_count() == 2

        assert await sana_gate.release(bot) == 2
        assert sana_gate.deferred_count() == 0
        first = runtime_state.job_queue.get_nowait()
        assert first["user_id"] == 7           # ترتیب ثبت حفظ می‌شود

    asyncio.run(scenario())


def test_inquiry_context():
    msg = MagicMock()
    msg.text = "🔍 استعلام"
    assert sana_gate.is_inquiry_context(msg, None)
    msg.text = "✍️ ثبت لایحه"
    assert not sana_gate.is_inquiry_context(msg, "Form:waiting_for_flow_type")
    msg.text = "123"
    assert sana_gate.is_inquiry_context(msg, "Form:waiting_for_tracking_code")
    assert not sana_gate.is_inquiry_context(msg, "Form:lavayeh_title")


# ── ⭐ قطعی فوری: بستن فوری مرورگر و انتقال صف ─────────────────────────────

def test_outage_on_moves_queue_and_closes_browser_now(monkeypatch):
    import asyncio as _aio
    from unittest.mock import AsyncMock as _AM, MagicMock as _MM
    monkeypatch.setattr(runtime_state, "job_queue", runtime_state._SignRoutingQueue())
    monkeypatch.setattr(runtime_state, "priority_job_queue", runtime_state._SignRoutingQueue())
    runtime_state.job_queue.put_nowait({"task_type": "LAVAYEH_SUBMIT", "user_id": 50})
    runtime_state.priority_job_queue.put_nowait({"task_type": "CHECK_SUBMIT", "user_id": 51})
    browser = _MM()
    browser.is_connected.return_value = True
    browser.close = _AM()
    monkeypatch.setattr(runtime_state, "browser", browser)
    sana_gate._busy = 1   # تسکی در حال پردازش — بستن نباید منتظر بماند
    bot = _MM()
    bot.send_message = _AM()
    msg = _MM()
    msg.answer = _AM()

    _aio.run(sana_gate.outage_on_cmd(msg, bot))

    assert sana_gate.is_outage() and sana_gate.browser_closed()
    browser.close.assert_awaited_once()
    assert runtime_state.browser is None
    assert runtime_state.job_queue.qsize() == 0 and runtime_state.priority_job_queue.qsize() == 0
    assert {it["job"]["user_id"] for it in sana_gate._state["deferred"]} == {50, 51}
    assert all(it["reason"] == "outage" for it in sana_gate._state["deferred"])
    notified = {c.args[0] for c in bot.send_message.call_args_list}
    assert {50, 51} <= notified
    sana_gate._busy = 0
