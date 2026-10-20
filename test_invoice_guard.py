"""تست invoice_guard — رد پرداخت فاکتور قدیمی/نامربوط، بدون اثر روی پرداخت‌های عادی."""
import json

import pytest

import invoice_guard
from states import Form


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(invoice_guard, "STORE_FILE", str(tmp_path / "invoice_guard.json"))
    monkeypatch.setattr(invoice_guard, "_store", {})
    monkeypatch.setattr(invoice_guard, "_loaded", True)


def _inv(uid, ptype, amount, **extra):
    payload = json.dumps({"type": ptype, "uid": uid, **extra})
    return {"chat_id": uid, "payload": payload, "prices": [{"label": "x", "amount": amount}]}, payload


LAV = Form.waiting_for_lavayeh_payment_receipt.state
CART = Form.waiting_for_payment_receipt.state


def test_normal_payment_passes():
    inv, payload = _inv(1, "lavayeh", 2_000_000)
    invoice_guard.record(inv)
    assert invoice_guard.check(1, payload, 2_000_000, LAV) is None


def test_cheap_cart_invoice_in_lavayeh_state_rejected():
    _, cart_payload = _inv(1, "cart", 500_000)
    assert invoice_guard.check(1, cart_payload, 500_000, LAV) is not None


def test_prepay_invoice_in_lavayeh_state_rejected():
    _, payload = _inv(1, "reg_prepay", 10_000, svc="lavayeh")
    assert invoice_guard.check(1, payload, 10_000, LAV) is not None


def test_lavayeh_invoice_in_cart_state_rejected():
    _, payload = _inv(1, "lavayeh", 10_000)
    assert invoice_guard.check(1, payload, 10_000, CART) is not None


def test_payload_routed_types_allowed_in_any_state():
    for ptype in ("admin_fee", "panel_message", "single_use", "pending_case", "clearance", "wallet_topup"):
        _, payload = _inv(1, ptype, 10_000)
        assert invoice_guard.check(1, payload, 10_000, LAV) is None, ptype


def test_prepay_allowed_outside_guarded_states():
    _, payload = _inv(1, "reg_prepay", 10_000, svc="lavayeh")
    assert invoice_guard.check(1, payload, 10_000, Form.waiting_for_lavayeh_prepay.state) is None
    assert invoice_guard.check(1, payload, 10_000, None) is None


def test_older_cheaper_invoice_same_payload_rejected():
    old, payload = _inv(1, "cart", 500_000)
    invoice_guard.record(old)
    new, _ = _inv(1, "cart", 2_000_000)
    invoice_guard.record(new)
    assert invoice_guard.check(1, payload, 500_000, CART) is not None
    assert invoice_guard.check(1, payload, 2_000_000, CART) is None


def test_newer_reduced_invoice_allowed():
    # لایحهٔ کنسل‌شده: فاکتور جدید با مبلغ کمتر صادر می‌شود — همان باید پرداخت‌پذیر باشد
    full, payload = _inv(1, "lavayeh", 2_000_000)
    invoice_guard.record(full)
    reduced, _ = _inv(1, "lavayeh", 800_000)
    invoice_guard.record(reduced)
    assert invoice_guard.check(1, payload, 800_000, LAV) is None


def test_admin_fee_multiple_invoices_not_amount_checked():
    a, payload = _inv(1, "admin_fee", 100_000)
    invoice_guard.record(a)
    b, _ = _inv(1, "admin_fee", 500_000)
    invoice_guard.record(b)
    assert invoice_guard.check(1, payload, 100_000, None) is None


def test_unknown_or_legacy_payload_allowed():
    assert invoice_guard.check(1, "legacy-payload", 1_000, LAV) is None
    assert invoice_guard.check(1, json.dumps({"type": "something_new"}), 1_000, LAV) is None


def test_other_user_record_not_used():
    inv, payload = _inv(1, "cart", 2_000_000)
    invoice_guard.record(inv)
    _, payload2 = _inv(2, "cart", 500_000)
    assert invoice_guard.check(2, payload2, 500_000, CART) is None


# ── میان‌افزار successful_payment (پشتیبان pre_checkout) ─────────────────────

def _run_payment(uid, payload, total, state_value, charge="BALE-1"):
    import asyncio
    import datetime as _dt
    import os
    from unittest.mock import AsyncMock

    os.environ.setdefault("BOT_TOKEN", "1:x")
    os.environ.setdefault("ADMIN_ID", "1")
    from aiogram import Bot, Dispatcher, F, Router
    from aiogram.fsm.storage.base import StorageKey
    from aiogram.fsm.storage.memory import MemoryStorage
    from aiogram.types import Chat, Message, SuccessfulPayment, Update, User

    import wallet

    async def scenario():
        bot = Bot("1:x")
        bot.send_message = AsyncMock()
        dp = Dispatcher(storage=MemoryStorage())
        dp.message.outer_middleware(invoice_guard.InvoiceGuardMiddleware())
        seen = []
        svc = Router()

        @svc.message(F.successful_payment)
        async def service_paid(message):
            seen.append(message.successful_payment)

        dp.include_router(svc)
        if state_value:
            await dp.storage.set_state(StorageKey(bot_id=bot.id, chat_id=uid, user_id=uid), state_value)
        msg = Message(message_id=1, date=_dt.datetime.now(_dt.timezone.utc), chat=Chat(id=uid, type="private"),
                      from_user=User(id=uid, is_bot=False, first_name="x"),
                      successful_payment=SuccessfulPayment(currency="IRR", total_amount=total,
                                                           invoice_payload=payload,
                                                           telegram_payment_charge_id=charge,
                                                           provider_payment_charge_id=charge))
        await dp.feed_update(bot, Update(update_id=1, message=msg))
        await bot.session.close()
        return seen

    return asyncio.run(scenario())


@pytest.fixture
def _tmp_wallet(tmp_path, monkeypatch):
    import asyncio
    import wallet
    monkeypatch.setattr(wallet, "STORE_FILE", str(tmp_path / "wallet.json"))
    wallet._store = {"users": {}, "offers": {}, "holds": {}, "autopaid": {}}
    wallet._lock = asyncio.Lock()
    return wallet


def test_middleware_passes_matching_payment(_tmp_wallet):
    inv, payload = _inv(5, "lavayeh", 2_000_000)
    invoice_guard.record(inv)
    seen = _run_payment(5, payload, 2_000_000, LAV)
    assert len(seen) == 1 and _tmp_wallet.balance(5) == 0


def test_middleware_refunds_mismatched_payment_to_wallet(_tmp_wallet):
    _, payload = _inv(5, "reg_prepay", 10_000, svc="lavayeh")
    seen = _run_payment(5, payload, 10_000, LAV)
    assert seen == []
    assert _tmp_wallet.balance(5) == 1_000


def test_middleware_skips_wallet_and_card_replays(_tmp_wallet):
    _, payload = _inv(5, "reg_prepay", 10_000, svc="lavayeh")
    assert len(_run_payment(5, payload, 10_000, LAV, charge="WALLET-ab")) == 1
    assert len(_run_payment(5, payload, 10_000, LAV, charge="CARD-ab")) == 1
