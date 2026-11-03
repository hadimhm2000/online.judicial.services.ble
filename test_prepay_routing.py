"""تست اصلاحیه ۱۴۰۵/۰۸ — اولویت «سرویس فاکتور» (svc در payload) بر state فعلی
در global_successful_payment_handler برای فاکتورهای پیش‌پرداخت (reg_prepay).

مشکل: بازپخش‌های کارت‌به‌کارت/کیف پول از invoice_guard معاف‌اند؛ اگر کاربر
فاکتور پیش‌پرداخت سرویس A (مثلاً لایحه) را می‌خواست و پیش از پرداخت سراغ
سرویس B (مثلاً اظهارنامه) می‌رفت، state فعلی (B) مبنای مسیریابی می‌شد و
پرداخت A به‌اشتباه برای B ثبت می‌شد.

اجرا: BOT_TOKEN=1:x ADMIN_ID=1 ADMIN_API_SECRET=x python -m pytest test_prepay_routing.py
"""
import asyncio
import datetime
import json
import os
from unittest.mock import AsyncMock

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("ADMIN_API_SECRET", "x")

import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Chat, Message, SuccessfulPayment, Update, User

import runtime_state
from handlers import router as main_router
from states import Form

UID = 42


@pytest.fixture(scope="module")
def _bot_dp():
    """روتر اصلی یک singleton ماژولی است و فقط به یک Dispatcher می‌چسبد؛
    پس dp و bot یک‌بار برای کل فایل ساخته می‌شوند و هر تست فقط state
    کاربر را عوض می‌کند."""
    bot = Bot("1:x")
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(main_router)
    runtime_state.dp = dp
    yield bot, dp
    asyncio.run(bot.session.close())


@pytest.fixture(autouse=True)
def _recorders(monkeypatch):
    """هندلرهای پیش‌پرداخت هر سرویس با ضبط‌کننده جایگزین می‌شوند (هندلر سراسری
    آن‌ها را داخل تابع import می‌کند؛ پس attribute ماژول را می‌سازیم)."""
    import check_handlers
    import ezhharnameh_handlers
    import lavayeh_handlers
    import tajdid_nazar_handlers

    called = []
    for mod, func, label in (
            (lavayeh_handlers, "lavayeh_prepay_successful_payment", "lavayeh"),
            (ezhharnameh_handlers, "ezhhar_prepay_successful_payment", "ezhharnameh"),
            (tajdid_nazar_handlers, "tn_prepay_successful_payment", "tn"),
            (check_handlers, "check_prepay_successful_payment", "check")):
        async def rec(message, state, bot, _label=label):
            called.append(_label)
        monkeypatch.setattr(mod, func, rec)
    yield called


def _payment_update(payload: dict):
    msg = Message(
        message_id=1,
        date=datetime.datetime.now(datetime.timezone.utc),
        chat=Chat(id=UID, type="private"),
        from_user=User(id=UID, is_bot=False, first_name="کاربر تست"),
        successful_payment=SuccessfulPayment(
            currency="IRR", total_amount=100_000,
            invoice_payload=json.dumps(payload),
            telegram_payment_charge_id="CARD-test", provider_payment_charge_id="CARD-test"),
    )
    return Update(update_id=1, message=msg)


def _run(payload: dict, state, bot, dp) -> None:
    """state کاربر را می‌گذارد و فاکتور را از مسیر Dispatcher پردازش می‌کند."""

    async def scenario():
        key = StorageKey(bot_id=bot.id, chat_id=UID, user_id=UID)
        await dp.storage.set_state(key, state)
        await dp.storage.set_data(key, {})
        await dp.feed_update(bot, _payment_update(payload))

    asyncio.run(scenario())


def test_payment_routes_by_payload_svc_not_current_state(_bot_dp, _recorders):
    """پرداخت فاکتور لایحه (svc=lavayeh) وقتی کاربر در state پیش‌پرداخت
    اظهارنامه است → باید به «لایحه» برود، نه اظهارنامه."""
    bot, dp = _bot_dp
    _run({"type": "reg_prepay", "svc": "lavayeh", "uid": UID},
         Form.waiting_for_ezhhar_prepay.state, bot, dp)
    assert _recorders == ["lavayeh"]


def test_payment_routes_by_payload_svc_reverse(_bot_dp, _recorders):
    """برعکس: پرداخت فاکتور اظهارنامه وقتی کاربر در state لایحه است."""
    bot, dp = _bot_dp
    _run({"type": "reg_prepay", "svc": "ezhharnameh", "uid": UID},
         Form.waiting_for_lavayeh_prepay.state, bot, dp)
    assert _recorders == ["ezhharnameh"]


def test_matching_state_and_svc_still_routes_correctly(_bot_dp, _recorders):
    """حالت سالم: state و svc هم‌خوان → همان سرویس (رفتار سالم تغییر نکرده)."""
    bot, dp = _bot_dp
    _run({"type": "reg_prepay", "svc": "tn", "uid": UID},
         Form.waiting_for_tn_prepay.state, bot, dp)
    assert _recorders == ["tn"]


def test_legacy_payload_without_svc_falls_back_to_state(_bot_dp, _recorders):
    """فاکتور قدیمی بدون svc → همچنان بر اساس state فعلی مسیریابی می‌شود."""
    bot, dp = _bot_dp
    _run({"type": "reg_prepay", "uid": UID},
         Form.waiting_for_check_prepay.state, bot, dp)
    assert _recorders == ["check"]
