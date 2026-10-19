"""تست secret_redact — توکن ربات در لاگ و پیام خروجی دیده نشود، بقیهٔ متن دست‌نخورده بماند."""
import asyncio
import io
import logging
import os

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("ADMIN_ID", "1")

import pytest

import secret_redact

FAKE = "123456789:FAKE-token-for-tests"


@pytest.fixture(autouse=True)
def _fake_token(monkeypatch):
    monkeypatch.setattr(secret_redact, "BOT_TOKEN", FAKE)


def test_redact_replaces_only_token():
    url = f"https://tapi.bale.ai/bot{FAKE}/sendInvoice"
    assert secret_redact.redact(url) == "https://tapi.bale.ai/bot<BOT_TOKEN>/sendInvoice"
    assert secret_redact.redact("متن عادی") == "متن عادی"
    assert secret_redact.redact(None) is None


def _logger_with_filter():
    buf = io.StringIO()
    h = logging.StreamHandler(buf)
    h.setFormatter(logging.Formatter("%(message)s"))
    h.addFilter(secret_redact.TokenRedactFilter())
    lg = logging.getLogger("test_secret_redact")
    lg.handlers, lg.propagate = [h], False
    return lg, buf


def test_log_message_and_args_redacted():
    lg, buf = _logger_with_filter()
    lg.error("خطا: %s", f"url=/bot{FAKE}/x")
    lg.error(f"خطا مستقیم /bot{FAKE}/y")
    out = buf.getvalue()
    assert FAKE not in out and out.count("<BOT_TOKEN>") == 2


def test_log_traceback_redacted():
    lg, buf = _logger_with_filter()
    try:
        raise RuntimeError(f"POST https://tapi.bale.ai/bot{FAKE}/sendInvoice failed")
    except RuntimeError:
        lg.error("ارسال فاکتور ناموفق", exc_info=True)
    out = buf.getvalue()
    assert FAKE not in out and "Traceback" in out and "<BOT_TOKEN>" in out


def test_outgoing_message_text_redacted():
    from unittest.mock import AsyncMock

    from aiogram import Bot
    from aiogram.client.session.aiohttp import AiohttpSession
    from aiogram.methods import SendMessage

    async def scenario():
        session = AiohttpSession()
        session.middleware(secret_redact.TokenRedactRequestMiddleware())
        session.make_request = AsyncMock(return_value=None)
        bot = Bot("1:x", session=session)
        await bot(SendMessage(chat_id=1, text=f"⚠️ خطا در دانلود فایل: url=/file/bot{FAKE}/a.xlsx"))
        await session.close()
        return session.make_request.call_args

    call = asyncio.run(scenario())
    sent = call.args[1]
    assert FAKE not in sent.text and "<BOT_TOKEN>" in sent.text
    assert sent.text.startswith("⚠️ خطا در دانلود فایل")
