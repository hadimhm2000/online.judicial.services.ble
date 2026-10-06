"""تست ثبت دسته‌جمعی لایحه: کد رهگیری برای چاپ نهایی، فاکتور کلی پایان دسته،
لیست کدهای رهگیری برای امضا.
اجرا: BOT_TOKEN=x ADMIN_ID=1 python -m pytest test_bulk_lavayeh_sign.py"""
import asyncio
import os
from unittest.mock import AsyncMock

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("ADMIN_ID", "1")

import pytest

import runtime_state
import bulk_submissions
import lavayeh_handlers
import lavayeh_sign_handlers
from bulk_submissions import BULK_TASKS

UID = 5151
BATCH = "LYH-TEST1"


@pytest.fixture
def env(monkeypatch, tmp_path):
    import wallet
    monkeypatch.setattr(wallet, "STORE_FILE", str(tmp_path / "wallet.json"))
    monkeypatch.setattr(wallet, "_store", {"users": {}, "offers": {}, "holds": {}, "autopaid": {}})
    bot = AsyncMock()
    recorded = []
    import final_print
    monkeypatch.setattr(final_print, "record_registration",
                        lambda uid, tc, **kw: recorded.append(tc) or True)
    monkeypatch.setattr(lavayeh_handlers, "upsert_case_to_panel", AsyncMock())
    monkeypatch.setattr(lavayeh_handlers, "_send_lavayeh_pdf_safely", AsyncMock(return_value=True))
    monkeypatch.setattr(bulk_submissions, "_mark_bulk_items_paid_and_ready", AsyncMock())
    invoice = AsyncMock()
    monkeypatch.setattr(bulk_submissions, "_send_bulk_settlement_invoice", invoice)
    BULK_TASKS[BATCH] = {
        "user_id": UID, "service_type": "lavayeh", "items": [], "status": "queued",
        "signable_items": [], "failures": [], "queued_count": 2, "completed_count": 0,
        "done_rows": [], "prepaid_total_rial": 100_000,
    }
    runtime_state.pending_lavayeh_sign.pop(UID, None)
    yield bot, recorded, invoice
    BULK_TASKS.pop(BATCH, None)
    runtime_state.pending_lavayeh_sign.pop(UID, None)


def _texts(bot):
    return [str(c.args[1]) for c in bot.send_message.await_args_list if len(c.args) > 1]


async def _register(bot, row, bill_no, archive_no, cost=60_000):
    await lavayeh_handlers.send_bulk_item_result(
        bot, UID, "x.pdf", cost, tracking_code=archive_no, lavayeh_title="لایحه دفاعیه",
        batch_tracking_code=BATCH, row_index=row, lavayeh_bill_no=bill_no,
        bulk_row_key=f"{BATCH}#{row}")


def test_tracking_code_used_for_final_print_and_sign_list(env):
    bot, recorded, _ = env

    async def scenario():
        await _register(bot, 1, "140412345678", "9901234")

    asyncio.run(scenario())
    assert recorded == ["140412345678"]
    item = BULK_TASKS[BATCH]["signable_items"][0]
    assert item["tracking_code"] == "140412345678"
    assert item["case_ref"] == "9901234"


def test_batch_finalizes_when_a_row_exits_without_result(env):
    """یک ردیف موفق + یک ردیف که منتظر اصلاح ماند → فاکتور کلی و منوی امضا."""
    bot, _, invoice = env

    async def scenario():
        await _register(bot, 1, "111", "a1", cost=150_000)
        data = {"_is_bulk": True, "batch_tracking_code": BATCH, "_bulk_row_key": f"{BATCH}#2",
                "_bulk_row_index": 2, "lavayeh_title": "لایحه دفاعیه"}
        await bulk_submissions.ensure_bulk_row_done(bot, UID, data)
        await bulk_submissions.ensure_bulk_row_done(bot, UID, data)  # دوباره شمرده نشود

    asyncio.run(scenario())
    task = BULK_TASKS[BATCH]
    assert task["completed_count"] == 2 and task["finalized"]
    assert len(task["failures"]) == 1
    invoice.assert_awaited_once_with(bot, UID, BATCH, 50_000)
    assert any("گزارش مالی نهایی" in t for t in _texts(bot))


def test_success_row_counted_once(env):
    bot, _, _ = env

    async def scenario():
        await _register(bot, 1, "111", "a1")
        await bulk_submissions.mark_bulk_item_done(bot, UID, BATCH, row_key=f"{BATCH}#1")

    asyncio.run(scenario())
    assert BULK_TASKS[BATCH]["completed_count"] == 1
    assert not BULK_TASKS[BATCH].get("finalized")


def test_sign_list_drops_signed_codes(env):
    bot, _, _ = env

    async def scenario():
        await _register(bot, 1, "111", "a1", cost=40_000)
        await _register(bot, 2, "222", "a2", cost=40_000)
        bot.send_message.reset_mock()
        task = BULK_TASKS[BATCH]
        task["signing_in_progress"] = "111"
        runtime_state.pending_lavayeh_sign[UID] = {"bulk_batch_tc": BATCH, "bulk_item_tc": "111"}
        sign_info = runtime_state.pending_lavayeh_sign.pop(UID)
        await bulk_submissions.on_bulk_item_sign_finished(bot, UID, sign_info, signed=True)
        kb = bot.send_message.await_args.kwargs["reply_markup"]
        cbs = [row[0].callback_data for row in kb.inline_keyboard]
        assert cbs == ["bulk_sign_select:222"]
        assert task["signing_in_progress"] is None

        bot.send_message.reset_mock()
        task["signing_in_progress"] = "222"
        await bulk_submissions.on_bulk_item_sign_finished(
            bot, UID, {"bulk_batch_tc": BATCH, "bulk_item_tc": "222"}, signed=True)
        assert any("امضای همهٔ کدهای رهگیری" in t for t in _texts(bot))

    asyncio.run(scenario())


def test_aborted_sign_keeps_code_and_releases_lock(env):
    bot, _, _ = env

    async def scenario():
        await _register(bot, 1, "111", "a1")
        BULK_TASKS[BATCH]["signing_in_progress"] = "111"
        await bulk_submissions.on_bulk_item_sign_finished(
            bot, UID, {"bulk_batch_tc": BATCH, "bulk_item_tc": "111"}, signed=False)

    asyncio.run(scenario())
    item = BULK_TASKS[BATCH]["signable_items"][0]
    assert item["status"] == "awaiting_sign"
    assert BULK_TASKS[BATCH]["signing_in_progress"] is None


def test_stale_lock_released_after_restart(env):
    task = BULK_TASKS[BATCH]
    task["signing_in_progress"] = "111"
    bulk_submissions._release_stale_sign_lock(UID, task)
    assert task["signing_in_progress"] is None


def test_late_row_uses_surplus_then_sign_menu(env):
    import wallet
    bot, _, invoice = env

    async def scenario():
        await _register(bot, 1, "111", "a1", cost=30_000)
        data = {"_is_bulk": True, "batch_tracking_code": BATCH, "_bulk_row_key": f"{BATCH}#2",
                "_bulk_row_index": 2, "lavayeh_title": "لایحه دفاعیه"}
        await bulk_submissions.ensure_bulk_row_done(bot, UID, data)
        # مازاد پیش‌پرداخت به کیف پول کاربر رفت
        assert BULK_TASKS[BATCH]["surplus_rial"] == 0 and wallet.balance(UID) == 7_000
        bot.send_message.reset_mock()
        # پس از اصلاح، ردیف ۲ ثبت می‌شود
        await _register(bot, 2, "222", "a2", cost=50_000)

    asyncio.run(scenario())
    task = BULK_TASKS[BATCH]
    assert wallet.balance(UID) == 2_000 and task["failures"] == []
    invoice.assert_not_awaited()
    kb = bot.send_message.await_args.kwargs["reply_markup"]
    assert [r[0].callback_data for r in kb.inline_keyboard] == [
        "bulk_sign_select:111", "bulk_sign_select:222"]


def test_sign_timer_ignores_other_bulk_code():
    store = {UID: {"sign_session_id": "new"}}
    assert not lavayeh_sign_handlers._same_sign_session(store, UID, "old")
    assert lavayeh_sign_handlers._same_sign_session(store, UID, "new")
    # فلوی تکی (بدون شناسه) مثل قبل
    assert lavayeh_sign_handlers._same_sign_session({UID: {"tracking_code": "x"}}, UID, None)


def test_safe_send_awaitable():
    bot = AsyncMock()
    asyncio.run(bulk_submissions._safe_send(bot, UID, "سلام"))
    bot.send_message.assert_awaited_once()
