"""تست ساعت کاری از پنل، بستن خودکار مرورگر، امضای خارج از ساعت کاری و دفتر ماندگار تسک‌ها.
اجرا: python -m pytest test_browser_gate.py"""
import asyncio
import datetime
import os
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("ADMIN_API_SECRET", "x")

import pytest

import pending_jobs
import runtime_state
import sana_gate
import working_hours
from working_hours import TEHRAN_TZ

# شنبه ۲۰۲۶-۱۰-۱۰ (dayOfWeek پنل = 0)
SAT = datetime.date(2026, 10, 10)


def _at(day: datetime.date, hour: int, minute: int = 0):
    return datetime.datetime.combine(day, datetime.time(hour, minute), tzinfo=TEHRAN_TZ)


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(sana_gate, "STATE_FILE", str(tmp_path / "gate.json"))
    monkeypatch.setattr(pending_jobs, "STATE_FILE", str(tmp_path / "jobs.json"))
    monkeypatch.setattr(working_hours, "CACHE_FILE", str(tmp_path / "wh.json"))
    sana_gate._state.update({"outage": False, "outage_since": None, "browser_closed": False,
                             "browser_closed_reason": None, "admin_open": False, "deferred": []})
    pending_jobs._state.update({"jobs": {}, "failed": []})
    monkeypatch.setattr(working_hours, "_schedule", {d: working_hours._default_day(d) for d in range(7)})
    sana_gate._busy = 0


def _panel(items):
    async def fake():
        return items
    return fake


def _apply(monkeypatch, items):
    import panel_sync
    monkeypatch.setattr(panel_sync, "get_working_hours", _panel(items))
    assert asyncio.run(working_hours.refresh())


# ── ساعت کاری پنل ────────────────────────────────────────────────────────

def test_panel_dow_mapping():
    assert working_hours.panel_dow(SAT) == 0
    assert working_hours.panel_dow(SAT + datetime.timedelta(days=6)) == 6   # جمعه


def test_panel_schedule_applied_and_cached(monkeypatch):
    week = [{"dayOfWeek": d, "startHour": 8, "startMin": 30, "endHour": 16, "endMin": 0,
             "enabled": d != 6} for d in range(7)]
    _apply(monkeypatch, week)
    assert working_hours.source() == "panel"
    assert not working_hours.is_working_hours(_at(SAT, 8, 29))
    assert working_hours.is_working_hours(_at(SAT, 8, 30))
    assert working_hours.is_working_hours(_at(SAT, 14))
    assert not working_hours.is_working_hours(_at(SAT, 16))
    friday = SAT + datetime.timedelta(days=6)
    assert not working_hours.is_working_hours(_at(friday, 10))       # جمعه تعطیل
    assert working_hours.today_label(_at(SAT, 9)) == "8:30 الی 16:00"
    # شروع بعدی از پنجشنبه عصر → شنبه (جمعه تعطیل)
    thu = SAT + datetime.timedelta(days=5)
    assert working_hours.next_start(_at(thu, 17)) == _at(SAT + datetime.timedelta(days=7), 8, 30)

    # ری‌استارت بدون پنل → همان برنامهٔ ذخیره‌شده
    monkeypatch.setattr(working_hours, "_schedule", {d: working_hours._default_day(d) for d in range(7)})
    working_hours._load_cache()
    assert working_hours.source() == "cache"
    assert working_hours.is_working_hours(_at(SAT, 9))


def test_panel_failure_keeps_last_schedule(monkeypatch):
    week = [{"dayOfWeek": d, "startHour": 9, "startMin": 0, "endHour": 12, "endMin": 0,
             "enabled": True} for d in range(7)]
    _apply(monkeypatch, week)
    import panel_sync
    monkeypatch.setattr(panel_sync, "get_working_hours", _panel(None))
    assert not asyncio.run(working_hours.refresh())
    assert working_hours.is_working_hours(_at(SAT, 10))
    assert not working_hours.is_working_hours(_at(SAT, 14))


def test_overnight_window(monkeypatch):
    week = [{"dayOfWeek": d, "startHour": 20, "startMin": 0, "endHour": 2, "endMin": 0,
             "enabled": True} for d in range(7)]
    _apply(monkeypatch, week)
    assert working_hours.is_working_hours(_at(SAT, 23))
    assert working_hours.is_working_hours(_at(SAT + datetime.timedelta(days=1), 1))
    assert not working_hours.is_working_hours(_at(SAT, 3))


def test_gate_uses_panel_hours(monkeypatch):
    week = [{"dayOfWeek": d, "startHour": 8, "startMin": 0, "endHour": 13, "endMin": 0,
             "enabled": True} for d in range(7)]
    _apply(monkeypatch, week)
    assert sana_gate.is_working_hours(_at(SAT, 9))
    assert not sana_gate.is_working_hours(_at(SAT, 15))   # قبلاً (۱۴-۲۲) داخل بود


# ── امضا خارج از ساعت کاری ───────────────────────────────────────────────

def test_sign_navigation_deferred_offhours(monkeypatch):
    monkeypatch.setattr(sana_gate, "is_working_hours", lambda now=None: False)
    nav = {"task_type": "LAVAYEH_SEND_SIGN_CODE", "user_id": 5, "phase": "send_code",
           "tracking_code": "T1", "target_row_indices": [0]}
    assert sana_gate.sign_should_defer(nav)
    # ثبت کدِ از قبل ارسال‌شده — اگر مرورگر باز است انجام شود (کد هدر نرود)
    assert not sana_gate.sign_should_defer({"task_type": "LAVAYEH_SUBMIT_SIGN", "user_id": 5})
    sana_gate._state["browser_closed"] = True
    assert sana_gate.sign_should_defer(nav)

    async def run():
        bot = MagicMock()
        bot.send_message = AsyncMock()
        await sana_gate.defer_sign(nav, bot)
        await sana_gate.defer_sign(nav, bot)      # تکراری → یک ناوبری
        assert sana_gate.deferred_count() == 1
        job = sana_gate._state["deferred"][0]["job"]
        assert job["phase"] == "navigate" and "target_row_indices" not in job
    asyncio.run(run())


def test_sign_runs_in_hours_and_admin_open(monkeypatch):
    nav = {"task_type": "EZHHARNAMEH_SEND_SIGN_CODE", "user_id": 5, "phase": "navigate"}
    monkeypatch.setattr(sana_gate, "is_working_hours", lambda now=None: True)
    assert not sana_gate.sign_should_defer(nav)
    monkeypatch.setattr(sana_gate, "is_working_hours", lambda now=None: False)
    sana_gate._state["admin_open"] = True
    assert not sana_gate.sign_should_defer(nav)


# ── بستن/باز کردن خودکار مرورگر ──────────────────────────────────────────

def _fake_browser():
    b = MagicMock()
    b.is_connected.return_value = True
    b.close = AsyncMock()
    return b


def test_auto_close_offhours_when_idle(monkeypatch):
    monkeypatch.setattr(sana_gate, "is_working_hours", lambda now=None: False)
    runtime_state.job_queue = asyncio.Queue()
    runtime_state.priority_job_queue = asyncio.Queue()
    runtime_state.sign_job_queue = asyncio.Queue()
    browser = _fake_browser()
    runtime_state.browser = browser

    async def run():
        bot = MagicMock()
        bot.send_message = AsyncMock()
        sana_gate.job_started()
        await sana_gate._auto_close_if_idle(bot)
        assert not sana_gate.browser_closed()          # تسک در جریان → صبر
        sana_gate.job_finished()
        await sana_gate._auto_close_if_idle(bot)
        assert sana_gate.browser_closed()
        assert sana_gate._state["browser_closed_reason"] == "auto"
        browser.close.assert_awaited()
    asyncio.run(run())


def test_admin_open_prevents_auto_close(monkeypatch):
    monkeypatch.setattr(sana_gate, "is_working_hours", lambda now=None: False)
    runtime_state.browser = _fake_browser()
    sana_gate._state["admin_open"] = True
    asyncio.run(sana_gate._auto_close_if_idle(MagicMock()))
    assert not sana_gate.browser_closed()


def test_startup_launch_respects_hours(monkeypatch):
    monkeypatch.setattr(sana_gate, "is_working_hours", lambda now=None: False)
    assert not sana_gate.should_launch_on_startup()
    assert sana_gate.browser_closed()
    sana_gate._state["browser_closed"] = False
    monkeypatch.setattr(sana_gate, "is_working_hours", lambda now=None: True)
    assert sana_gate.should_launch_on_startup()


# ── دفتر ماندگار تسک‌ها ───────────────────────────────────────────────────

def test_journal_survives_restart():
    a = {"task_type": "LAVAYEH_SUBMIT", "user_id": 7, "tracking_code": "A"}
    b = {"task_type": "CHECK_SUBMIT", "user_id": 8}
    c = {"task_type": "EZHHARNAMEH_SUBMIT", "user_id": 9}
    for j in (a, b, c):
        pending_jobs.track(j)
    pending_jobs.track({"task_type": "PRE_CHECK", "user_id": 1})        # ثبت نمی‌شود
    pending_jobs.track({"task_type": "LAVAYEH_SUBMIT_SIGN", "user_id": 1})
    pending_jobs.mark_running(b)
    pending_jobs.done(c)

    pending_jobs._state.update({"jobs": {}, "failed": []})
    pending_jobs.load()
    queued, interrupted = pending_jobs.restore()
    assert [j["user_id"] for j in queued] == [7]
    assert [j["user_id"] for j in interrupted] == [8]
    assert [it["user_id"] for it in pending_jobs.failed_items()] == [8]
    assert pending_jobs.user_ids() == {"7", "8"}

    job = pending_jobs.pop_failed(pending_jobs.failed_items()[0]["jid"])
    assert job["user_id"] == 8 and not pending_jobs.failed_items()


def test_routing_queue_journals_and_defer_hands_over(monkeypatch):
    q = runtime_state._SignRoutingQueue()
    job = {"task_type": "TN_APPEAL", "user_id": 3}
    q.put_nowait(job)
    assert pending_jobs.queued_count() == 1 and job.get("_jid")

    monkeypatch.setattr(sana_gate, "is_working_hours", lambda now=None: False)
    bot = MagicMock()
    bot.send_message = AsyncMock()
    asyncio.run(sana_gate.defer(job, bot))
    assert pending_jobs.queued_count() == 0           # حالا در صف ماندگار sana_gate
    assert sana_gate.deferred_count() == 1


def test_pace_spaces_back_to_back_tasks(monkeypatch):
    monkeypatch.setattr(sana_gate, "PACE_MIN_SECONDS", 0.05)
    monkeypatch.setattr(sana_gate, "PACE_MAX_SECONDS", 0.1)
    monkeypatch.setattr(sana_gate, "_last_task_at", 0.0)

    async def run():
        loop = asyncio.get_event_loop()
        await sana_gate.pace()                 # صف خالی بوده → بدون صبر
        t0 = loop.time()
        await sana_gate.pace()
        assert loop.time() - t0 >= 0.04
    asyncio.run(run())
