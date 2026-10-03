"""تست ثبت دسته‌جمعی چک (۳ تصویر هر ردیف + پیش‌پرداخت یکجا)
اجرا: BOT_TOKEN=x ADMIN_ID=1 python -m pytest test_check_bulk_images.py"""
import asyncio
import json
import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("ADMIN_ID", "1")

import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update

import runtime_state
import handlers
import check_bulk_handlers as cbh
from bulk_submissions import BULK_TASKS
from states import Form

UID = 4242
PER_ROW_RIAL = 200_000


class _FakeBot(Bot):
    async def __call__(self, method, request_timeout=None):
        self.sent.append(getattr(method, "text", None))
        return None


def _update(n, text=None, photo=None, payment=None):
    msg = {"message_id": n, "date": int(datetime.now().timestamp()),
           "chat": {"id": UID, "type": "private"},
           "from": {"id": UID, "is_bot": False, "first_name": "x"}}
    if photo:
        msg["photo"] = [{"file_id": photo, "file_unique_id": photo, "width": 1, "height": 1}]
    elif payment:
        msg["successful_payment"] = payment
    else:
        msg["text"] = text
    return Update.model_validate({"update_id": n, "message": msg})


def _item(n):
    return {"check_request_title": "مطالبه وجه چک", "check_amount": 1000, "check_tracking_no": str(n),
            "check_plainiffs": [{"person_type": "شخص حقیقی", "national_id": "0012345679"}],
            "check_defendants": [{"person_type": "شخص حقوقی", "company_id": "10102345670",
                                  "representative_type": "", "national_id": ""}],
            "check_images": [], "check_attachment_groups": [], "_bulk_row_index": n}


def _payment(payload, charge):
    return {"currency": "IRR", "total_amount": 2 * PER_ROW_RIAL,
            "invoice_payload": payload,
            "telegram_payment_charge_id": charge, "provider_payment_charge_id": charge}


@pytest.fixture
def env(monkeypatch):
    """Dispatcher با روتر اصلی ربات (همان مسیری که پیام‌ها در production طی می‌کنند)."""
    handlers.router._parent_router = None
    bot = _FakeBot("1:x")
    bot.sent = []
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(handlers.router)
    queue = asyncio.Queue()
    monkeypatch.setattr(runtime_state, "job_queue", queue, raising=False)

    import admin_forward, exempt_users, sheets, card_payment
    admin_copy = AsyncMock()
    monkeypatch.setattr(admin_forward, "send_check_submission_to_admin", admin_copy)
    monkeypatch.setattr(exempt_users, "is_exempt_user", AsyncMock(return_value=False))
    monkeypatch.setattr(sheets, "log_event", AsyncMock())
    monkeypatch.setattr(card_payment, "track_invoice", lambda data: None)
    invoices = []
    monkeypatch.setattr(cbh, "_send_invoice", AsyncMock(side_effect=invoices.append))
    monkeypatch.setattr(cbh, "_prepay_per_row_rial", lambda: PER_ROW_RIAL)

    counter = [0]

    async def send(**kw):
        counter[0] += 1
        await dp.feed_update(bot, _update(counter[0], **kw))

    async def start(items):
        state = dp.fsm.get_context(bot, UID, UID)
        msg = MagicMock()
        msg.answer = AsyncMock()
        await cbh.start_check_bulk_images(msg, state, items)
        return state

    yield MagicMock(bot=bot, queue=queue, admin_copy=admin_copy, invoices=invoices,
                    send=send, start=start, exempt=exempt_users)
    asyncio.run(bot.session.close())
    handlers.router._parent_router = None


def test_images_then_one_prepay_invoice_then_queue(env):
    async def scenario():
        state = await env.start([_item(2), _item(5)])
        send = env.send
        assert await state.get_state() == Form.bulk_check_images_row.state

        # ادامه قبل از ۳ تصویر پذیرفته نمی‌شود
        await send(photo="a1")
        await send(text=cbh.BTN_IMAGES_DONE)
        assert await state.get_state() == Form.bulk_check_images_row.state
        await send(photo="a2")
        await send(photo="a3")
        await send(photo="a4")          # تصویر چهارم رد می‌شود
        await send(text=cbh.BTN_IMAGES_DONE)
        assert await state.get_state() == Form.bulk_check_extra_attachment_choice.state
        # مدرک اضافی برای ردیف اول
        await send(text=cbh.BTN_EXTRA_YES)
        await send(text="وکالتنامه")
        await send(photo="x1")
        await send(text=cbh.BTN_EXTRA_DONE)
        await send(text=cbh.BTN_EXTRA_NO)
        # ردیف دوم: یک تصویر اشتباه حذف و جایگزین می‌شود
        for fid in ("b1", "bad"):
            await send(photo=fid)
        await send(text=cbh.BTN_UNDO)
        for fid in ("b2", "b3"):
            await send(photo=fid)
        await send(text=cbh.BTN_IMAGES_DONE)
        await send(text=cbh.BTN_EXTRA_NO)

        # یک فاکتور برای همهٔ ردیف‌ها؛ تا پرداخت چیزی صف نمی‌شود
        assert await state.get_state() == Form.bulk_prepay_wait.state
        assert env.queue.empty()
        (inv,) = env.invoices
        assert inv["prices"][0]["amount"] == 2 * PER_ROW_RIAL
        payload = json.loads(inv["payload"])
        assert payload["type"] == "bulk_prepay" and payload["svc"] == "check"
        code = payload["tracking_code"]
        assert BULK_TASKS[code]["status"] == "awaiting_prepay"

        # پرداخت از مسیر هندلر سراسری successful_payment
        await send(payment=_payment(inv["payload"], "c1"))
        assert await state.get_state() is None
        jobs = [env.queue.get_nowait() for _ in range(env.queue.qsize())]
        assert len(jobs) == 2 and env.admin_copy.await_count == 2
        first, second = jobs
        assert [i["file_id"] for i in first["check_images"]] == ["a1", "a2", "a3"]
        assert first["check_attachment_groups"] == [{"title": "وکالتنامه", "images": ["x1"]}]
        assert [i["file_id"] for i in second["check_images"]] == ["b1", "b2", "b3"]
        assert second["check_attachment_groups"] == []
        assert first["batch_tracking_code"] == second["batch_tracking_code"] == code
        assert first["_is_bulk_check"] and first["task_type"] == "CHECK_SUBMIT"
        assert (first["_bulk_row_index"], second["_bulk_row_index"]) == (2, 5)
        task = BULK_TASKS[code]
        assert task["queued_count"] == 2 and task["status"] == "processing"
        assert task["prepaid_total_rial"] == 2 * PER_ROW_RIAL and task["user_id"] == UID

        # پرداخت تکراری دوباره صف نمی‌کند
        await send(payment=_payment(inv["payload"], "c2"))
        assert env.queue.empty()
        BULK_TASKS.pop(code, None)

    asyncio.run(scenario())


def test_exempt_user_skips_prepay(env):
    async def scenario():
        env.exempt.is_exempt_user.return_value = True
        await env.start([_item(2)])
        for fid in ("a1", "a2", "a3"):
            await env.send(photo=fid)
        await env.send(text=cbh.BTN_IMAGES_DONE)
        await env.send(text=cbh.BTN_EXTRA_NO)
        assert not env.invoices
        job = env.queue.get_nowait()
        assert BULK_TASKS[job["batch_tracking_code"]]["prepaid_total_rial"] == 0
        BULK_TASKS.pop(job["batch_tracking_code"], None)

    asyncio.run(scenario())


def test_cancel_queues_nothing(env):
    async def scenario():
        state = await env.start([_item(2)])
        await env.send(photo="a1")
        await env.send(text=cbh.BTN_CANCEL)
        assert await state.get_state() is None and env.queue.empty() and not env.invoices

    asyncio.run(scenario())


def test_settlement_payment_reaches_sign_menu(env, monkeypatch):
    """پرداخت فاکتور تسویهٔ پایان بچ قبلاً در هندلر سراسری بی‌صدا رها می‌شد."""
    import bulk_submissions
    sign_menu = AsyncMock()
    monkeypatch.setattr(bulk_submissions, "_show_bulk_sign_menu", sign_menu)
    monkeypatch.setattr(bulk_submissions, "_mark_bulk_items_paid_and_ready", AsyncMock())
    BULK_TASKS["CHK-T1"] = {"user_id": UID, "status": "processing", "items": []}

    async def scenario():
        payload = json.dumps({"type": "bulk_settlement", "uid": UID, "tracking_code": "CHK-T1"})
        await env.send(payment=_payment(payload, "s1"))
        sign_menu.assert_awaited_once()
        assert sign_menu.await_args.args[1:] == (UID, "CHK-T1")

    try:
        asyncio.run(scenario())
    finally:
        BULK_TASKS.pop("CHK-T1", None)
