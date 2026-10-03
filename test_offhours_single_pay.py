"""تست ساعت کاری مدیر، پرداخت تکی تمبر/خسارت و محاسبه هزینه دادرسی —
اجرا: BOT_TOKEN=x ADMIN_ID=1 ADMIN_API_SECRET=x python -m pytest test_offhours_single_pay.py"""
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("ADMIN_API_SECRET", "x")

import pytest

import court_fee as cf
import runtime_state
import sana_gate
from config import ADMIN_ID


@pytest.fixture(autouse=True)
def _clean(tmp_path, monkeypatch):
    monkeypatch.setattr(sana_gate, "STATE_FILE", str(tmp_path / "gate.json"))
    sana_gate._state.update({"outage": False, "outage_since": None, "browser_closed": False,
                             "deferred": [], "offhours_log": []})
    runtime_state.user_free_usage.clear()
    runtime_state.user_subscriptions.clear()
    monkeypatch.setattr(sana_gate, "is_working_hours", lambda now=None: False)


# ── محاسبه هزینه دادرسی ──────────────────────────────────────────────────

def test_court_fee_first_instance_below_threshold():
    r = cf.calc_court_fee(100_000_000, cf.CAT_FIRST)
    assert r["fee"] == 2_500_000


def test_court_fee_first_instance_with_excess():
    r = cf.calc_court_fee(500_000_000, cf.CAT_FIRST)
    # ۲۰۰م × ۲٫۵٪ + ۳۰۰م × ۳٫۵٪
    assert r["fee"] == 5_000_000 + 10_500_000
    assert r["excess"] == 300_000_000


def test_court_fee_appeal_and_retrial():
    assert cf.calc_court_fee(100_000_000, cf.CAT_APPEAL)["fee"] == 4_500_000
    assert cf.calc_court_fee(100_000_000, cf.CAT_RETRIAL)["fee"] == 5_500_000
    assert cf.calc_court_fee(1_000, cf.CAT_RETRIAL)["fee"] == 55


def test_court_fee_rounding_and_invalid():
    assert cf.calc_court_fee(10, cf.CAT_FIRST)["fee"] == 0       # 0.25 → 0
    assert cf.calc_court_fee(20, cf.CAT_FIRST)["fee"] == 1       # 0.5 → 1
    with pytest.raises(ValueError):
        cf.calc_court_fee(0, cf.CAT_FIRST)
    with pytest.raises(ValueError):
        cf.calc_court_fee(100, "x")
    assert "۳٫۵" in cf.format_result_fa(cf.calc_court_fee(500_000_000, cf.CAT_FIRST))


# ── سهمیهٔ رایگان، پرداخت تکی، مدیر ─────────────────────────────────────

def test_two_free_then_single_credit():
    uid = 555
    for _ in range(2):
        assert runtime_state.can_use_service(uid, "stamp")
        runtime_state.increment_usage(uid, "stamp")
    assert not runtime_state.can_use_service(uid, "stamp")
    runtime_state.add_single_use_credit(uid, "stamp")
    assert runtime_state.can_use_service(uid, "stamp")
    assert runtime_state.can_use_service(uid, "damages")
    runtime_state.increment_usage(uid, "stamp")          # اعتبار تکی مصرف می‌شود
    assert runtime_state.get_single_use_credits(uid, "stamp") == 0
    assert runtime_state.get_user_usage(uid)["stamp"] == 2
    assert not runtime_state.can_use_service(uid, "stamp")


def test_sections_counted_separately():
    uid = 556
    runtime_state.increment_usage(uid, "stamp")
    runtime_state.increment_usage(uid, "stamp")
    assert not runtime_state.can_use_service(uid, "stamp")
    assert runtime_state.can_use_service(uid, "damages")
    assert runtime_state.can_use_service(uid, "tools")


def test_admin_never_limited():
    for _ in range(5):
        assert runtime_state.can_use_service(ADMIN_ID, "stamp")
        runtime_state.increment_usage(ADMIN_ID, "stamp")
    assert runtime_state.get_user_usage(ADMIN_ID)["stamp"] == 0
    assert "مدیر" in runtime_state.usage_status_line(ADMIN_ID, "tools")


def test_single_use_fees():
    assert runtime_state.SINGLE_USE_FEES == {"stamp": 200_000, "damages": 450_000}


# ── خارج از ساعت کاری ────────────────────────────────────────────────────

def test_admin_jobs_not_deferred_offhours():
    assert sana_gate.should_defer({"task_type": "LAVAYEH_SUBMIT", "user_id": 99})
    assert not sana_gate.should_defer({"task_type": "LAVAYEH_SUBMIT", "user_id": ADMIN_ID})
    assert not sana_gate.should_defer({"task_type": "LAVAYEH_SUBMIT", "user_id": 99, "admin_forced": True})
    sana_gate._state["browser_closed"] = True
    assert sana_gate.should_defer({"task_type": "LAVAYEH_SUBMIT", "user_id": ADMIN_ID})
    sana_gate._state["browser_closed"] = False
    sana_gate._state["outage"] = True
    assert sana_gate.should_defer({"task_type": "LAVAYEH_SUBMIT", "user_id": ADMIN_ID})


def test_main_menu_buttons_not_inquiry():
    msg = MagicMock()
    for text in ("💰 محاسبه تمبر", "🔧 ابزار فایل", "📈 خسارت تأخیر و مهریه",
                 "🧾 محاسبه هزینه دادرسی", "✍️ ثبت لایحه"):
        msg.text = text
        assert not sana_gate.is_inquiry_context(msg, "Form:main_menu"), text
    msg.text = "1️⃣ استعلام لوایح، اظهارنامه، دادخواست و ..."
    assert sana_gate.is_inquiry_context(msg, "Form:main_menu")


def test_offhours_report_and_admin_submit():
    async def scenario():
        bot = MagicMock()
        bot.send_message = AsyncMock()
        runtime_state.job_queue = asyncio.Queue()
        await sana_gate.defer({"task_type": "LAVAYEH_SUBMIT", "user_id": 7}, bot)
        await sana_gate.defer({"task_type": "CHECK_SUBMIT", "user_id": 8}, bot)
        await sana_gate.defer({"task_type": "EZHHARNAMEH_SUBMIT", "user_id": 7}, bot)

        text, kb = sana_gate.offhours_report()
        assert "2 کاربر، 3 درخواست" in text
        assert "`7`" in text and "لایحه" in text and "_" not in text.replace("/offhours_submit", "")
        assert len(kb.inline_keyboard) == 2

        reply = await sana_gate._submit_and_report("7")
        assert "2 درخواست" in reply
        assert sana_gate.deferred_count() == 1
        job = runtime_state.job_queue.get_nowait()
        assert job["user_id"] == 7 and job["admin_forced"]
        assert not sana_gate.should_defer(job)
        statuses = {e["uid"]: e["status"] for e in sana_gate._state["offhours_log"]}
        assert statuses == {7: "admin_submitted", 8: "queued"}

        assert "در صف" in await sana_gate._submit_and_report("12345")
        assert "نامعتبر" in await sana_gate._submit_and_report("abc")

        # بعد از ری‌استارت سابقه باقی می‌ماند
        sana_gate._state["offhours_log"] = []
        sana_gate.load()
        assert len(sana_gate._state["offhours_log"]) == 3

    asyncio.run(scenario())
