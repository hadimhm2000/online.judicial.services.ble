"""تست مرحلهٔ ۳ تصویر چک در ثبت دسته‌جمعی — اجرا: BOT_TOKEN=x ADMIN_ID=1 python -m pytest test_check_bulk_images.py"""
import asyncio
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
import check_bulk_handlers as cbh
from bulk_submissions import BULK_TASKS
from states import Form

UID = 4242


@pytest.fixture(autouse=True)
def _detach_router():
    # هر تست Dispatcher خودش را دارد؛ روتر ماژول باید آزاد باشد
    cbh.check_bulk_router._parent_router = None
    yield
    cbh.check_bulk_router._parent_router = None


class _FakeBot(Bot):
    async def __call__(self, method, request_timeout=None):
        self.sent.append(getattr(method, "text", None))
        return None


def _update(n, text=None, photo=None):
    msg = {"message_id": n, "date": int(datetime.now().timestamp()),
           "chat": {"id": UID, "type": "private"},
           "from": {"id": UID, "is_bot": False, "first_name": "x"}}
    if photo:
        msg["photo"] = [{"file_id": photo, "file_unique_id": photo, "width": 1, "height": 1}]
    else:
        msg["text"] = text
    return Update.model_validate({"update_id": n, "message": msg})


def _item(n):
    return {"check_request_title": "مطالبه وجه چک", "check_amount": 1000, "check_tracking_no": str(n),
            "check_plainiffs": [{"person_type": "شخص حقیقی", "national_id": "0012345679"}],
            "check_defendants": [{"person_type": "شخص حقوقی", "company_id": "10102345670",
                                  "representative_type": "", "national_id": ""}],
            "check_images": [], "check_attachment_groups": [], "_bulk_row_index": n}


def test_three_images_required_then_batch_queued(monkeypatch):
    async def scenario():
        bot = _FakeBot("1:x")
        bot.sent = []
        dp = Dispatcher(storage=MemoryStorage())
        dp.include_router(cbh.check_bulk_router)
        queue = asyncio.Queue()
        monkeypatch.setattr(runtime_state, "job_queue", queue, raising=False)
        admin_copy = AsyncMock()
        import admin_forward
        monkeypatch.setattr(admin_forward, "send_check_submission_to_admin", admin_copy)

        state = dp.fsm.get_context(bot, UID, UID)
        start_msg = MagicMock()
        start_msg.answer = AsyncMock()
        await cbh.start_check_bulk_images(start_msg, state, [_item(2), _item(5)])
        assert await state.get_state() == Form.bulk_check_images_row.state

        n = 0

        async def send(**kw):
            nonlocal n
            n += 1
            await dp.feed_update(bot, _update(n, **kw))

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

        assert await state.get_state() is None
        jobs = [queue.get_nowait() for _ in range(queue.qsize())]
        assert len(jobs) == 2 and admin_copy.await_count == 2
        first, second = jobs
        assert [i["file_id"] for i in first["check_images"]] == ["a1", "a2", "a3"]
        assert first["check_attachment_groups"] == [{"title": "وکالتنامه", "images": ["x1"]}]
        assert [i["file_id"] for i in second["check_images"]] == ["b1", "b2", "b3"]
        assert second["check_attachment_groups"] == []
        code = first["batch_tracking_code"]
        assert code and second["batch_tracking_code"] == code
        assert first["_is_bulk_check"] and first["task_type"] == "CHECK_SUBMIT"
        assert (first["_bulk_row_index"], second["_bulk_row_index"]) == (2, 5)
        assert BULK_TASKS[code]["queued_count"] == 2 and BULK_TASKS[code]["service_type"] == "CHECK"
        BULK_TASKS.pop(code, None)
        await bot.session.close()

    asyncio.run(scenario())


def test_cancel_queues_nothing(monkeypatch):
    async def scenario():
        bot = _FakeBot("1:x")
        bot.sent = []
        dp = Dispatcher(storage=MemoryStorage())
        dp.include_router(cbh.check_bulk_router)
        queue = asyncio.Queue()
        monkeypatch.setattr(runtime_state, "job_queue", queue, raising=False)
        state = dp.fsm.get_context(bot, UID, UID)
        start_msg = MagicMock()
        start_msg.answer = AsyncMock()
        await cbh.start_check_bulk_images(start_msg, state, [_item(2)])
        await dp.feed_update(bot, _update(1, photo="a1"))
        await dp.feed_update(bot, _update(2, text=cbh.BTN_CANCEL))
        assert await state.get_state() is None and queue.empty()
        await bot.session.close()

    asyncio.run(scenario())
