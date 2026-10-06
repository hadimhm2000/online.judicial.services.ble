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
    wallet._store = {"users": {}, "offers": {}, "holds": {}, "autopaid": {}}
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


# ── کسر خودکار موجودی از فاکتورها (۱۴۰۵/۰۷) ─────────────────────────────

def _inv(uid, amount_rial, ptype="single"):
    return {"chat_id": uid, "title": "فاکتور تست", "description": "توضیح",
            "payload": json.dumps({"type": ptype, "uid": uid}),
            "prices": [{"label": "تست", "amount": amount_rial}]}


def _dp_with_service(seen):
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.outer_middleware(wallet.WalletPaymentMiddleware())
    svc = Router()

    @svc.message(F.successful_payment)
    async def service_paid(message):
        seen.append(message.successful_payment)

    dp.include_router(svc)
    runtime_state.dp = dp
    return dp


def _feed_payment(dp, bot, uid, payload, total, charge="BALE-1"):
    import datetime as _dt
    from aiogram.types import Chat, Message, SuccessfulPayment, Update, User
    msg = Message(message_id=1, date=_dt.datetime.now(_dt.timezone.utc), chat=Chat(id=uid, type="private"),
                  from_user=User(id=uid, is_bot=False, first_name="x"),
                  successful_payment=SuccessfulPayment(currency="IRR", total_amount=total, invoice_payload=payload,
                                                       telegram_payment_charge_id=charge,
                                                       provider_payment_charge_id=charge))
    return dp.feed_update(bot, Update(update_id=1, message=msg))


def test_partial_balance_reduces_invoice_and_restores_full_amount_on_payment():
    async def scenario():
        bot = Bot("1:x")
        bot.send_message = AsyncMock()
        seen = []
        dp = _dp_with_service(seen)
        async with wallet._lock:
            wallet._apply(5, 3_000, "refund", "مازاد")
        inv = wallet.prepare_invoice(_inv(5, 100_000))
        assert inv["prices"][0]["amount"] == 70_000
        assert "کیف پول" in inv["description"]
        assert wallet.available(5) == 0 and wallet.balance(5) == 3_000

        await _feed_payment(dp, bot, 5, inv["payload"], 70_000)
        assert len(seen) == 1 and seen[0].total_amount == 100_000
        assert wallet.balance(5) == 0 and wallet._store["holds"] == {}
        await bot.session.close()

    asyncio.run(scenario())


def test_invoice_never_goes_below_api_minimum():
    wallet._apply(6, 9_500, "refund")
    inv = wallet.prepare_invoice(_inv(6, 100_000))
    assert inv["prices"][0]["amount"] == wallet.MIN_INVOICE_RIAL
    assert wallet.available(6) == 500


def test_topup_invoice_untouched_and_unpaid_hold_replaced_by_new_invoice():
    wallet._apply(8, 5_000, "refund")
    top = _inv(8, 100_000, ptype=wallet.TOPUP_TYPE)
    assert wallet.prepare_invoice(top) is top
    first = wallet.prepare_invoice(_inv(8, 100_000))
    second = wallet.prepare_invoice(_inv(8, 100_000))  # یادآوری همان فاکتور
    assert first["prices"][0]["amount"] == second["prices"][0]["amount"] == 50_000
    assert len(wallet._store["holds"]) == 1 and wallet.available(8) == 0


def test_full_balance_auto_pays_and_duplicate_payment_returns_to_wallet(monkeypatch):
    monkeypatch.setattr(wallet, "AUTOPAY_FIRST_DELAY", 0)
    monkeypatch.setattr(wallet, "AUTOPAY_STABLE_DELAY", 0)

    async def scenario():
        bot = Bot("1:x")
        bot.send_message = AsyncMock()
        seen = []
        dp = _dp_with_service(seen)
        wallet.set_bot(bot)
        wallet._apply(9, 20_000, "topup")
        inv = wallet.prepare_invoice(_inv(9, 100_000, ptype="reg_prepay"))
        assert inv["prices"][0]["amount"] == 100_000  # موجودی کافی → فاکتور دست‌نخورده
        await wallet._auto_pay(9, inv["payload"], "reg_prepay", 100_000, "پیش پرداخت")
        assert len(seen) == 1 and seen[0].total_amount == 100_000
        assert wallet.balance(9) == 10_000

        # کاربر همان فاکتور را از درگاه هم پرداخت کرد → به کیف پول برمی‌گردد و سرویس دوباره اجرا نمی‌شود
        await _feed_payment(dp, bot, 9, inv["payload"], 100_000)
        assert len(seen) == 1 and wallet.balance(9) == 20_000

        # فاکتور جدید با همان payload، پرداخت عادی است نه تکراری
        wallet._store["users"]["9"]["balance"] = 0
        inv2 = wallet.prepare_invoice(_inv(9, 100_000, ptype="reg_prepay"))
        await _feed_payment(dp, bot, 9, inv2["payload"], 100_000)
        assert len(seen) == 2
        await bot.session.close()

    asyncio.run(scenario())


def test_leftover_after_final_invoice_goes_to_wallet():
    import prepay_registration as pr
    runtime_state.prepaid_registrations[21] = {"amount_rial": 150_000, "amount_toman": 15_000,
                                               "prepay_paid_rial": 150_000}
    adjusted, info = pr.adjust_final_fee_with_prepay(21, 100_000)
    assert adjusted == 0 and info["leftover_rial"] == 50_000
    assert wallet.balance(21) == 5_000
    assert 21 not in runtime_state.prepaid_registrations
    assert "کیف پول" in pr.build_prepay_fee_text(0, info, 100_000)


def test_migrate_legacy_credits_moves_credit_and_keeps_inflight_prepay():
    from bulk_submissions import BULK_TASKS
    runtime_state.prepaid_registrations.clear()
    runtime_state.prepaid_registrations[31] = {"amount_rial": 300_000, "manual": True}
    runtime_state.prepaid_registrations[32] = {"amount_rial": 50_000, "prepay_paid_rial": 20_000}
    BULK_TASKS["T-MIG"] = {"user_id": 33, "finalized": True, "surplus_rial": 70_000}
    try:
        assert wallet.migrate_legacy_credits() == 3
        assert wallet.balance(31) == 30_000 and 31 not in runtime_state.prepaid_registrations
        assert wallet.balance(32) == 3_000
        assert runtime_state.prepaid_registrations[32]["amount_rial"] == 20_000
        assert wallet.balance(33) == 7_000 and BULK_TASKS["T-MIG"]["surplus_rial"] == 0
        assert wallet.migrate_legacy_credits() == 0  # تکرار بی‌اثر
    finally:
        BULK_TASKS.pop("T-MIG", None)
        runtime_state.prepaid_registrations.clear()


def test_owed_command_lists_balances():
    async def scenario():
        wallet._apply(41, 12_000, "refund", "مازاد پیش‌پرداخت")
        msg = MagicMock()
        msg.answer = AsyncMock()
        await wallet.admin_owed(msg)
        text = msg.answer.call_args.args[0]
        assert "12,000" in text and "41" in text

    asyncio.run(scenario())
