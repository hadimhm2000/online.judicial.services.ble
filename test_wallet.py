"""تست کیف پول — اجرا: BOT_TOKEN=x ADMIN_ID=1 ADMIN_API_SECRET=x python -m pytest test_wallet.py"""
import asyncio
import json
import os
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("ADMIN_API_SECRET", "x")

import pytest
from aiogram import Bot, Dispatcher, F, Router
from aiogram.fsm.storage.memory import MemoryStorage

import runtime_state
import wallet


@pytest.fixture(autouse=True)
def _tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(wallet, "STORE_FILE", str(tmp_path / "wallet.json"))
    wallet._store = {"users": {}, "offers": {}}
    wallet._lock = asyncio.Lock()


def test_pay_from_wallet_replays_original_invoice():
    async def scenario():
        bot = Bot("1:x")
        bot.send_message = AsyncMock()
        dp = Dispatcher(storage=MemoryStorage())
        seen = []
        svc = Router()

        @svc.message(F.successful_payment)
        async def service_paid(message):
            seen.append(message.successful_payment)

        dp.include_router(wallet.wallet_router)
        dp.include_router(svc)
        runtime_state.dp = dp
        wallet.set_bot(bot)

        async with wallet._lock:
            wallet._apply(42, 50_000, "topup", "t1")
        payload = json.dumps({"type": "reg_prepay", "svc": "lavayeh", "uid": 42})
        await wallet._send_offer(42, payload, "reg_prepay", 100_000, "پیش پرداخت")
        oid = next(iter(wallet._store["offers"]))

        cb = MagicMock()
        cb.data = f"wal:pay:{oid}"
        cb.from_user.id = 42
        cb.from_user.first_name, cb.from_user.last_name, cb.from_user.username = "علی", None, None
        cb.answer = AsyncMock()
        cb.message.answer = AsyncMock()
        cb.message.edit_reply_markup = AsyncMock()
        await wallet.cb_wallet_pay(cb, bot)

        assert wallet.balance(42) == 40_000
        assert len(seen) == 1
        assert seen[0].invoice_payload == payload and seen[0].total_amount == 100_000
        assert seen[0].telegram_payment_charge_id == f"WALLET-{oid}"

        # دکمهٔ تکراری دوباره کسر نمی‌کند
        await wallet.cb_wallet_pay(cb, bot)
        assert wallet.balance(42) == 40_000 and len(seen) == 1
        await bot.session.close()

    asyncio.run(scenario())


def test_no_offer_when_balance_insufficient():
    wallet.set_bot(MagicMock())
    wallet.on_invoice({"chat_id": 7, "payload": "{}", "prices": [{"amount": 10_000}]})
    assert wallet._store["offers"] == {}
