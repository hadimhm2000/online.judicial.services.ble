"""تست کسری مبلغ کارت‌به‌کارت — اجرا: python -m pytest test_card_shortfall.py"""
import asyncio
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

import card_payment as cp
import runtime_state
from config import ADMIN_ID

UID = 42


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(cp, "_STORE_FILE", str(tmp_path / "card_payments.json"))
    monkeypatch.setattr(cp, "CARD_PAY_ENABLED", True)
    monkeypatch.setattr(cp, "_sync_panel", lambda *a, **k: None)
    cp._store = {}
    cp._lock = asyncio.Lock()
    cp._shortfall_wait = None
    cp._pending_deductions.clear()
    import wallet
    monkeypatch.setattr(wallet, "on_invoice", lambda data: None)
    import card_payment_image
    monkeypatch.setattr(card_payment_image, "render_card_image", lambda *a, **k: None)
    sent = []

    async def fake_bale(method, data):
        sent.append((method, data))
        return {"ok": True}
    monkeypatch.setattr(cp, "_bale_call", fake_bale)
    return sent


def _review_entry(amount_rial=1_000_000):
    payload = json.dumps({"type": "reg_prepay", "svc": "lavayeh", "uid": UID})
    cp.track_invoice({"chat_id": UID, "title": "پیش پرداخت لایحه", "payload": payload,
                      "prices": [{"label": "x", "amount": amount_rial}]})
    entry = next(iter(cp._store.values()))
    entry.update({"status": cp.S_REVIEW, "full_name": "علی",
                  "receipt": {"file_id": "f1", "kind": "photo", "msg_id": 5, "at": time.time()},
                  "admin_msg_id": 77})
    return entry, payload


def _admin_cb(data):
    cb = MagicMock()
    cb.data = data
    cb.from_user.id = ADMIN_ID
    cb.answer = AsyncMock()
    cb.message.answer = AsyncMock()
    cb.message.chat.id = ADMIN_ID
    cb.message.message_id = 77
    cb.message.photo = [object()]
    return cb


def _admin_text(text):
    m = MagicMock()
    m.text = text
    m.from_user.id = ADMIN_ID
    m.answer = AsyncMock()
    return m


def test_shortfall_flow_then_approve_replays_full_invoice(_isolated):
    async def scenario():
        bot = Bot("1:x")
        bot.edit_message_caption = AsyncMock()
        bot.send_photo = AsyncMock(return_value=MagicMock(message_id=90))
        dp = Dispatcher(storage=MemoryStorage())
        seen = []
        svc = Router()

        @svc.message(F.successful_payment)
        async def paid(message):
            seen.append(message.successful_payment)

        dp.include_router(cp.card_router)
        dp.include_router(svc)
        runtime_state.dp = dp
        entry, payload = _review_entry()

        # مدیر «کسری» را می‌زند و مبلغ را با ارقام فارسی می‌فرستد
        await cp.cb_shortfall_start(_admin_cb(f"cpay:sf:{entry['id']}"))
        assert cp._shortfall_wait["eid"] == entry["id"]
        assert await cp._AwaitingShortfallAmount()(_admin_text("۲۵,۰۰۰")) is True
        bad = _admin_text("200000")  # ≥ مبلغ فاکتور (۱۰۰,۰۰۰ تومان)
        await cp.on_shortfall_amount(bad, bot)
        assert entry["status"] == cp.S_REVIEW and "نامعتبر" in bad.answer.call_args[0][0]
        await cp.on_shortfall_amount(_admin_text("۲۵,۰۰۰"), bot)
        assert entry["status"] == cp.S_SHORTFALL and entry["shortfall_rial"] == 250_000
        assert cp._shortfall_wait is None

        # پیام به کاربر فقط مبلغ کسری را می‌خواهد
        method, data = _isolated[-1]
        assert method == "sendMessage" and data["chat_id"] == UID
        assert "25,000 تومان" in data["text"] and "باقی‌مانده" in data["text"]
        assert cp._due_rial(entry) == 250_000

        # کاربر رسید باقی‌مانده را می‌فرستد → دوباره نزد مدیر با پاسخ به رسید اول
        msg = MagicMock()
        msg.from_user.id, msg.from_user.full_name, msg.from_user.username = UID, "علی", None
        msg.photo = [MagicMock(file_id="f2")]
        msg.message_id = 6
        msg.answer = AsyncMock()
        state = MagicMock()
        state.get_state = AsyncMock(return_value=None)
        target = await cp._receipt_target(msg, state)
        assert target is entry
        cp._upload_receipt_and_sync = AsyncMock()
        await cp.on_receipt(msg, state, bot, entry)
        assert entry["status"] == cp.S_REVIEW and entry["receipt"]["file_id"] == "f2"
        assert entry["prev_receipts"][0]["file_id"] == "f1"
        kw = bot.send_photo.call_args.kwargs
        assert kw["reply_to_message_id"] == 77 and "باقی‌ماندهٔ مبلغ" in kw["caption"]

        # تایید مدیر → همان پرداخت کامل فاکتور اصلی بازپخش می‌شود
        await cp.cb_approve(_admin_cb(f"cpay:ok:{entry['id']}"), bot)
        assert entry["status"] == cp.S_APPROVED
        assert len(seen) == 1
        assert seen[0].invoice_payload == payload and seen[0].total_amount == 1_000_000

    asyncio.run(scenario())


def test_reject_of_remainder_receipt_keeps_shortfall():
    async def scenario():
        bot = Bot("1:x")
        bot.send_message = AsyncMock()
        entry, _ = _review_entry()
        entry.update({"shortfall_rial": 100_000, "shortfall_receipt": True})
        cb = _admin_cb(f"cpay:rr:{entry['id']}:amt")
        cb.message.edit_caption = AsyncMock()
        await cp.cb_reject(cb, bot)
        assert entry["status"] == cp.S_SHORTFALL and cp._due_rial(entry) == 100_000

    asyncio.run(scenario())


def test_reinvoice_does_not_reset_shortfall():
    entry, payload = _review_entry()
    entry["status"] = cp.S_SHORTFALL
    cp.track_invoice({"chat_id": UID, "payload": payload,
                      "prices": [{"label": "x", "amount": 1_000_000}]})
    assert entry["status"] == cp.S_SHORTFALL


def test_admin_command_cancels_shortfall_wait():
    async def scenario():
        cp._shortfall_wait = {"eid": "x", "until": time.time() + 60}
        assert await cp._AwaitingShortfallAmount()(_admin_text("/prepaid")) is False
        assert cp._shortfall_wait is None
        other = _admin_text("123")
        other.from_user.id = ADMIN_ID + 1
        cp._shortfall_wait = {"eid": "x", "until": time.time() + 60}
        assert await cp._AwaitingShortfallAmount()(other) is False

    asyncio.run(scenario())


def test_deduction_shown_to_admin_for_matching_invoice():
    cp.note_invoice_deduction(UID, ("reg_prepay",), 1_200_000, 200_000, "مانده/بستانکاری کاربر")
    entry, _ = _review_entry()
    assert entry["deduction"]["deducted_rial"] == 200_000
    cap = cp._admin_caption(entry)
    assert "کسر از فاکتور: 20,000 تومان" in cap and "مبلغ اصلی 120,000 تومان" in cap
    assert UID not in cp._pending_deductions


def test_deduction_not_attached_to_other_invoice_types():
    cp.note_invoice_deduction(UID, ("lavayeh",), 5_000_000, 200_000, "پیش‌پرداخت")
    entry, _ = _review_entry()  # reg_prepay
    assert "deduction" not in entry
    assert "کسر از فاکتور" not in cp._admin_caption(entry)


def test_final_fee_adjust_notes_deduction(monkeypatch):
    import prepay_registration as pr
    runtime_state.prepaid_registrations[UID] = {
        "amount_rial": 300_000, "amount_toman": 30_000, "prepay_paid_rial": 200_000}
    adjusted, _ = pr.adjust_final_fee_with_prepay(UID, 2_000_000)
    assert adjusted == 1_700_000
    ded = cp._pending_deductions[UID]
    assert ded["deducted_rial"] == 300_000 and "lavayeh" in ded["types"]
    assert ded["detail"] == "پیش‌پرداخت + مانده/بستانکاری"
