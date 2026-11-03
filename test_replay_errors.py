"""تست اصلاحیه ۱۴۰۵/۰۸ — دیده‌شدن شکستِ بازپخش پرداخت (wallet / card_payment).

مشکل: در aiogram 3 «وجودِ» هندلر خطا (مثل خطاگیر سراسری bot.py) به‌تنهایی
استثنای هندلرها را سرکوب می‌کند — مقدار برگشتی هندلر (True/False/None)
تفاوتی ندارد و dp.feed_update هرگز خطا نمی‌دهد. نتیجه: بازپخش‌های مصنوعی
(WALLET-…/CARD-…) همیشه «موفق» دیده می‌شدند و مسیرهای «برگشت خودکار وجه»
(wallet._auto_pay / cb_wallet_pay / پیام «اعمال خودکار با خطا» به مدیر)
هرگز اجرا نمی‌شدند.

راه‌حل: runtime_state.replay_payment_mode (ContextVar) — در طول dp.feed_update
مصنوعی ست می‌شود و خطاگیر سراسری استثنا را دوباره پرتاب می‌کند.

اجرا: BOT_TOKEN=1:x ADMIN_ID=1 ADMIN_API_SECRET=x python -m pytest test_replay_errors.py
"""
import asyncio
import datetime
import json
import os
import time
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("ADMIN_API_SECRET", "x")

import pytest
from aiogram import Bot, Dispatcher, F, Router
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent, User

import card_payment as cp
import runtime_state
import wallet


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(wallet, "STORE_FILE", str(tmp_path / "wallet.json"))
    wallet._store = {"users": {}, "offers": {}, "holds": {}, "autopaid": {}}
    wallet._lock = asyncio.Lock()
    wallet._user_name_cache.clear()
    monkeypatch.setattr(cp, "_STORE_FILE", str(tmp_path / "card_payments.json"))
    cp._store = {}
    cp._lock = asyncio.Lock()
    monkeypatch.setattr(cp, "_sync_panel", lambda *a, **k: None)
    runtime_state.prepaid_registrations.clear()
    yield
    runtime_state.prepaid_registrations.clear()


def _dp_with_payment_handler(raise_on_pay: bool, re_raise_in_errors: bool):
    """Dispatcher با الگوی bot.py + هندلر successful_payment (اختیاری خطادار)."""
    dp = Dispatcher(storage=MemoryStorage())
    svc = Router()

    @svc.message(F.successful_payment)
    async def pay(message):
        if raise_on_pay:
            raise RuntimeError("شکست اعمال پرداخت در سرویس")
        return "ok"

    @dp.errors()
    async def global_error(event: ErrorEvent):
        # همان الگوی اصلاح‌شدهٔ bot.py: در حالت بازپخش، پرتاب دوباره
        if re_raise_in_errors and runtime_state.replay_payment_mode.get():
            raise event.exception
        return True

    dp.include_router(svc)
    runtime_state.dp = dp
    return dp



async def _set_prepay_state(uid):
    """⭐ reg_prepay فقط در state انتظار پیش‌پرداخت به‌صورت خودکار از کیف پول
    پرداخت می‌شود (همان وضعیتی که هندلر فرستندهٔ فاکتور می‌گذارد)."""
    from aiogram.fsm.storage.base import StorageKey
    from states import Form
    dp = runtime_state.dp
    await dp.storage.set_state(StorageKey(bot_id=1, chat_id=uid, user_id=uid),
                               Form.waiting_for_lavayeh_prepay.state)

def test_wallet_replay_failure_is_visible():
    """شکست هندلر پرداخت → _replay_payment نتیجهٔ False می‌دهد (برگشت وجه فعال می‌شود)."""

    async def scenario():
        bot = Bot("1:x")
        _dp_with_payment_handler(raise_on_pay=True, re_raise_in_errors=True)
        ok, err = await wallet._replay_payment(
            bot, 42, User(id=42, is_bot=False, first_name="کاربر"),
            json.dumps({"type": "reg_prepay", "svc": "lavayeh", "uid": 42}),
            100_000, "ab12cd34")
        assert not ok and "شکست اعمال پرداخت" in err
        await bot.session.close()

    asyncio.run(scenario())


def test_wallet_replay_success_stays_success():
    """هندلر سالم → بازپخش همچنان موفق است (رفتار سالم تغییر نکرده)."""

    async def scenario():
        bot = Bot("1:x")
        _dp_with_payment_handler(raise_on_pay=False, re_raise_in_errors=True)
        ok, err = await wallet._replay_payment(
            bot, 42, User(id=42, is_bot=False, first_name="کاربر"),
            json.dumps({"type": "reg_prepay", "svc": "lavayeh", "uid": 42}),
            100_000, "ab12cd34")
        assert ok and err == ""
        await bot.session.close()

    asyncio.run(scenario())


def test_aiogram_swallows_errors_without_replay_mode():
    """سند رفتار aiogram (چرا اصلاح لازم بود): بدون پرتاب دوباره از خطاگیر،
    حتی False/None هم استثنا را سرکوب می‌کند و بازپخش «موفق» دیده می‌شود."""

    async def scenario():
        bot = Bot("1:x")
        # خطاگیر «قدیمی»: True برمی‌گرداند و در حالت بازپخش هم پرتاب نمی‌کند
        _dp_with_payment_handler(raise_on_pay=True, re_raise_in_errors=False)
        ok, err = await wallet._replay_payment(
            bot, 42, User(id=42, is_bot=False, first_name="کاربر"),
            json.dumps({"type": "reg_prepay", "svc": "lavayeh", "uid": 42}),
            100_000, "ab12cd34")
        assert ok  # ← باگ قدیمی: شکست دیده نمی‌شد
        await bot.session.close()

    asyncio.run(scenario())


def test_card_replay_failure_is_visible():
    """شکست هندلر پرداخت در بازپخش کارت‌به‌کارت → _replay_successful_payment
    نتیجهٔ False می‌دهد (پیام «تایید شد ولی اعمال خودکار با خطا» فعال می‌شود)."""

    async def scenario():
        bot = Bot("1:x")
        _dp_with_payment_handler(raise_on_pay=True, re_raise_in_errors=True)
        entry = {
            "id": "ab12cd34",
            "uid": 42,
            "payload": json.dumps({"type": "reg_prepay", "svc": "lavayeh", "uid": 42}),
            "payload_obj": {"type": "reg_prepay", "svc": "lavayeh", "uid": 42},
            "amount_rial": 100_000,
            "full_name": "علی رضایی",
            "username": "",
            "receipt": {"file_id": "f1", "kind": "photo", "msg_id": 5, "at": time.time()},
        }
        ok, err = await cp._replay_successful_payment(bot, entry)
        assert not ok and "شکست اعمال پرداخت" in err
        await bot.session.close()

    asyncio.run(scenario())


def test_auto_pay_failure_refunds_and_notifies(monkeypatch):
    """پرداخت خودکار کیف پول با شکست مواجه شود → مبلغ خودکار برمی‌گردد،
    رکورد autopaid پاک می‌شود و کاربر و مدیر مطلع می‌شوند (wallet.py مسیر
    برگشت که قبلاً هرگز اجرا نمی‌شد)."""
    monkeypatch.setattr(wallet, "AUTOPAY_FIRST_DELAY", 0)
    monkeypatch.setattr(wallet, "AUTOPAY_STABLE_DELAY", 0)

    async def scenario():
        bot = Bot("1:x")
        sent = []

        async def fake_send(chat_id, text, **kw):
            sent.append((chat_id, text))

        async def no_chat(uid):
            raise RuntimeError("آفلاین")

        bot.send_message = fake_send
        bot.get_chat = no_chat
        _dp_with_payment_handler(raise_on_pay=True, re_raise_in_errors=True)
        wallet.set_bot(bot)
        wallet._apply(9, 20_000, "topup", "t")

        payload = json.dumps({"type": "reg_prepay", "svc": "lavayeh", "uid": 9})
        await _set_prepay_state(9)
        await wallet._auto_pay(9, payload, "reg_prepay", 100_000, "پیش پرداخت")

        # مبلغ خودکار برگشت خورد و رکورد «خودکار پرداخت‌شده» پاک شد
        assert wallet.balance(9) == 20_000
        assert wallet._store["autopaid"] == {}
        # کاربر و مدیر هر دو مطلع شدند
        assert any(uid == 9 for uid, _ in sent)
        assert any(uid == wallet.ADMIN_ID for uid, _ in sent)
        await bot.session.close()

    asyncio.run(scenario())
