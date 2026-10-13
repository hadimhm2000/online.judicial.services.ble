"""تست ۱۴۰۵/۰۷: صف استعلام خارج از ساعت کاری، بازهٔ ۱۴ الی ۲۲ استعلام‌های لحظه‌ای،
ارسال چاپ نهایی فقط پس از تکمیل امضا.
اجرا: BOT_TOKEN=x ADMIN_ID=1 ADMIN_API_SECRET=x python -m pytest test_offhours_inquiry.py"""
import asyncio
import datetime
import os
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("ADMIN_API_SECRET", "x")

import pytest

import final_print
import runtime_state
import sana_gate
from working_hours import TEHRAN_TZ


@pytest.fixture(autouse=True)
def _tmp_state(tmp_path, monkeypatch):
    monkeypatch.setattr(sana_gate, "STATE_FILE", str(tmp_path / "gate.json"))
    monkeypatch.setattr(final_print, "STORE_FILE", str(tmp_path / "fp.json"))
    sana_gate._state.update({"outage": False, "outage_since": None, "browser_closed": False,
                             "deferred": [], "offhours_log": []})
    sana_gate._inquiry_notified_at.clear()


def _at(hour):
    return datetime.datetime(2026, 10, 2, hour, 0, tzinfo=TEHRAN_TZ)


# ── ۱) استعلام خارج از ساعت کاری به صف می‌رود ──────────────────────────────

def test_inquiry_job_deferred_with_inquiry_text_once_per_cart(monkeypatch):
    async def scenario():
        monkeypatch.setattr(sana_gate, "is_working_hours", lambda now=None: False)
        bot = MagicMock()
        bot.send_message = AsyncMock()
        job = {"user_id": 7, "query_type": "کد رهگیری", "tracking_code": "1"}
        assert sana_gate.should_defer(job)
        await sana_gate.defer(job, bot)
        await sana_gate.defer({**job, "tracking_code": "2"}, bot)   # سبد: پیام دوم نمی‌رود
        assert sana_gate.deferred_count() == 2
        assert bot.send_message.await_count == 1
        assert "استعلام شما" in bot.send_message.await_args.args[1]

    asyncio.run(scenario())


def test_final_print_job_deferred_silently(monkeypatch):
    async def scenario():
        monkeypatch.setattr(sana_gate, "is_working_hours", lambda now=None: False)
        bot = MagicMock()
        bot.send_message = AsyncMock()
        await sana_gate.defer({"user_id": 7, "query_type": "کد رهگیری", "final_print": True}, bot)
        assert sana_gate.deferred_count() == 1
        bot.send_message.assert_not_awaited()

    asyncio.run(scenario())


# ── ۲ و ۳) استعلام تعداد برگ پیوست / افراد پرونده: فقط ۱۴ الی ۲۲ ─────────────

def test_live_inquiry_window(monkeypatch):
    monkeypatch.setattr(sana_gate, "is_working_hours", lambda now=None: True)
    assert sana_gate.live_inquiry_closed_text(7, _at(14)) is None
    assert sana_gate.live_inquiry_closed_text(7, _at(21)) is None
    assert "۱۴ الی ۲۲" in sana_gate.live_inquiry_closed_text(7, _at(13))
    assert "۱۴ الی ۲۲" in sana_gate.live_inquiry_closed_text(7, _at(22))
    assert sana_gate.live_inquiry_closed_text(1, _at(23)) is None        # مدیر


def test_live_inquiry_closed_on_outage(monkeypatch):
    monkeypatch.setattr(sana_gate, "is_working_hours", lambda now=None: True)
    sana_gate._state["outage"] = True
    assert "قطع" in sana_gate.live_inquiry_closed_text(7, _at(15))


# ── ۴) چاپ نهایی فقط پس از تکمیل امضا ───────────────────────────────────────

def _register(code="111", uid=7):
    assert final_print.record_registration(uid, code, service_type="LAVAYEH")


def _set_dates(registered=None, signed=None):
    data = final_print._load()
    for it in data["items"]:
        if registered:
            it["registered_date"] = registered
        if signed and it.get("signed"):
            it["signed_date"] = signed
    final_print._save(data)


def test_unsigned_item_not_due():
    _register()
    _set_dates(registered="2026-10-01")
    assert final_print._due_items(final_print._load(), "2026-10-02") == []


def test_signed_item_due_day_after_signing():
    _register()
    _set_dates(registered="2026-10-01")
    assert final_print.mark_signed(7, "111")
    today = final_print._today()
    _set_dates(signed=today)
    assert final_print._due_items(final_print._load(), today) == []        # همان روز امضا نه
    tomorrow = (datetime.date.fromisoformat(today) + datetime.timedelta(days=1)).isoformat()
    assert len(final_print._due_items(final_print._load(), tomorrow)) == 1


def test_mark_signed_matches_code_and_single_fallback():
    _register("111")
    _register("222")
    assert not final_print.mark_signed(7, "999")          # دو مورد بدون امضا → حدس نمی‌زند
    assert final_print.mark_signed(7, "", "222")          # کد ردیف دسته‌جمعی
    signed = {it["tracking_code"] for it in final_print._load()["items"] if it.get("signed")}
    assert signed == {"222"}
    assert final_print.mark_signed(7, "")                 # فقط یک مورد بدون امضا مانده
    assert all(it.get("signed") for it in final_print._load()["items"])


def test_legacy_items_without_flag_still_sent():
    data = final_print._load()
    data["items"].append({"user_id": 7, "tracking_code": "1", "doc_category": "لایحه",
                          "registered_date": "2026-10-01", "status": "pending", "attempts": 0})
    final_print._save(data)
    assert len(final_print._due_items(final_print._load(), "2026-10-02")) == 1
