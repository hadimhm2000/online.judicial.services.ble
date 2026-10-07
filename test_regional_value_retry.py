"""تست تکرار خودکار استعلام/PDF ارزش منطقه‌ای (هر یک دقیقه) و نمایش سهم قبلی در زنجیرهٔ «سهم از سهم» —
اجرا: BOT_TOKEN=x ADMIN_ID=1 ADMIN_API_SECRET=x python -m pytest test_regional_value_retry.py"""
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("ADMIN_API_SECRET", "x")

import pytest

import ownership_share as osh
import regional_value_handlers as rv

UID = 777


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    monkeypatch.setattr(rv, "_QUERY_RETRY_DELAY_SECONDS", 0)
    monkeypatch.setattr(rv, "_PDF_RETRY_DELAY_SECONDS", 0)
    monkeypatch.setattr(rv, "update_case_in_panel", AsyncMock())
    monkeypatch.setattr(rv.asyncio, "sleep", AsyncMock())


def _bot():
    bot = MagicMock()
    bot.send_message = AsyncMock()
    return bot


def _sent(bot):
    return [str(c.args[1]) for c in bot.send_message.call_args_list]


def test_query_retried_every_minute_with_same_data(monkeypatch):
    calls = []

    def fake_query(province, address, lat, lng):
        calls.append((province, address, lat, lng))
        if len(calls) < 4:
            raise ConnectionError("tax site down")
        return {"tax_info": {}}

    processed = AsyncMock()
    monkeypatch.setattr(rv, "_do_query_sync", fake_query)
    monkeypatch.setattr(rv, "_process_query_result", processed)

    async def scenario():
        bot = _bot()
        data = {"rv_province": "تهران", "rv_address": "خیابان آزادی", "rv_lat": 35.7, "rv_lng": 51.3}
        result, err = await rv._run_query_attempts(UID, data, attempts=2)
        assert result is None and isinstance(err, ConnectionError)
        rv._schedule_query_retry(bot, UID, "کاربر", data, "case1", err)
        await asyncio.gather(*list(rv._pending_tasks))
        assert len(calls) == 4 and len(set(calls)) == 1
        processed.assert_awaited_once()
        assert processed.await_args.args[1] == UID and processed.await_args.args[5] == "case1"
    asyncio.run(scenario())


def test_query_gives_up_after_max_attempts(monkeypatch):
    monkeypatch.setattr(rv, "_QUERY_RETRY_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(rv, "_do_query_sync", MagicMock(side_effect=TimeoutError("x")))

    async def scenario():
        bot = _bot()
        await rv._query_retry_worker(bot, UID, "کاربر", {"rv_province": "تهران"}, "case1", TimeoutError("x"))
        texts = _sent(bot)
        assert any("پس از 3 تلاش" in t for t in texts)                 # ادمین
        assert any("همچنان پاسخ نمی‌دهد" in t for t in texts)          # کاربر
        rv.update_case_in_panel.assert_awaited_with("case1", status="FAILED", errorDetails="x",
                                                    errorStep="unhandled_exception")
    asyncio.run(scenario())


def test_value_error_not_retried(monkeypatch):
    q = MagicMock(side_effect=ValueError("آدرس نامعتبر"))
    monkeypatch.setattr(rv, "_do_query_sync", q)

    async def scenario():
        result, err = await rv._run_query_attempts(UID, {}, attempts=2)
        assert isinstance(err, ValueError) and q.call_count == 1
    asyncio.run(scenario())


def test_pdf_retried_until_sent(monkeypatch):
    attempts = []

    def fake_build(path, *a, **k):
        attempts.append(path)
        if len(attempts) < 5:
            raise OSError("disk busy")
        open(path, "wb").write(b"%PDF")
        return True

    send = AsyncMock(return_value=True)
    monkeypatch.setattr(rv, "_build_pdf_sync", fake_build)
    monkeypatch.setattr(rv, "send_document_direct", send)

    async def scenario():
        bot = _bot()
        calc = {"land": {"value": 10}, "building": None, "land_value": 10, "building_value": 0, "total": 10}
        job = {"user_id": UID, "province": "تهران", "county": "تهران", "address": "-", "tax_result": {},
               "calc": calc, "plak": None, "has_building": False, "inputs_summary": "-", "full_name": "x"}
        assert not await rv._build_and_send_pdf(bot, job)      # دو تلاش داخلی
        rv._schedule_pdf_retry(bot, job)
        await asyncio.gather(*list(rv._pending_tasks))
        send.assert_awaited_once()
        assert len(attempts) == 5
    asyncio.run(scenario())


def test_share_chain_previous_result_button():
    wip = {"links": [{"k": osh.KIND_SAHM, "n": "230", "d": "2816"}], "kind": osh.KIND_SAHM}
    assert rv._prev_sahm_total(wip) == 2816
    btn = rv._prev_share_button(wip)
    assert btn == "↩️ همان ۲٬۸۱۶ سهم قبلی"
    assert rv._chain_so_far(wip).endswith("سهم")
    assert rv._prev_share_button({"links": [{"k": osh.KIND_DANG, "n": "3"}]}) is None
    assert rv._prev_share_button({"links": []}) is None
