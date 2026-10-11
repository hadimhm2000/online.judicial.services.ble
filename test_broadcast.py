"""تست ارسال همگانی پیام مدیر (/broadcast) —
اجرا: BOT_TOKEN=x ADMIN_ID=1 ADMIN_API_SECRET=x python -m pytest test_broadcast.py"""
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("ADMIN_API_SECRET", "x")

from aiogram.exceptions import TelegramRetryAfter

import broadcast_handlers as bh
from config import ADMIN_ID


def _msg(**kw):
    m = MagicMock()
    for attr in ("photo", "document", "video", "voice", "audio", "text", "caption"):
        setattr(m, attr, kw.get(attr))
    return m


def test_extract_payload_kinds():
    assert bh.extract_payload(_msg(text="سلام")) == {"kind": "text", "text": "سلام"}
    photo = [MagicMock(file_id="small"), MagicMock(file_id="big")]
    assert bh.extract_payload(_msg(photo=photo, caption="c")) == {"kind": "photo", "file_id": "big", "caption": "c"}
    doc = MagicMock(file_id="doc1")
    assert bh.extract_payload(_msg(document=doc)) == {"kind": "document", "file_id": "doc1", "caption": None}
    assert bh.extract_payload(_msg()) is None


def test_broadcast_counts_and_retry():
    bot = MagicMock()
    bot.send_message = AsyncMock()
    calls = {"n": 0}

    async def send_document(chat_id, file_id, caption=None, parse_mode=None):
        if chat_id == 20:
            raise RuntimeError("blocked")
        if chat_id == 30 and calls["n"] == 0:
            calls["n"] += 1
            raise TelegramRetryAfter(method=MagicMock(), message="slow", retry_after=0)

    bot.send_document = AsyncMock(side_effect=send_document)
    payload = {"kind": "document", "file_id": "f", "caption": "x"}
    sent, failed = asyncio.run(bh.broadcast(bot, [10, 20, 30], payload, interval=0))
    assert (sent, failed) == (2, 1)
    assert bot.send_document.await_count == 4          # ۳ کاربر + یک تلاش مجدد
    final = bot.send_message.await_args_list[-1]
    assert final.args[0] == ADMIN_ID and "موفق: 2" in final.args[1]


def test_text_payload_uses_send_message():
    bot = MagicMock()
    bot.send_message = AsyncMock()
    asyncio.run(bh.send_payload(bot, 5, {"kind": "text", "text": "اطلاعیه"}))
    bot.send_message.assert_awaited_once_with(5, "اطلاعیه", parse_mode=None)
