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


# ── ⭐ اصلاحیه ۱۴۰۵/۰۸: انقضای کسری پرداخت‌نشده ───────────────────────────

def test_shortfall_expires_after_window_and_fresh_invoice_gets_new_entry():
    """کسری که کاربر هرگز نپرداخت → پس از CARD_PAY_EXPIRE_HOURS منقضی می‌شود؛
    فاکتور جدید همان payload دیگر «در حال بررسی» نیست و ورودی تازه می‌گیرد
    (قبلاً ورودی برای همیشه فعال می‌ماند و کاربر دیگر پیشنهاد کارت نمی‌گرفت)."""
    entry, payload = _review_entry()
    entry.update({"status": cp.S_SHORTFALL, "shortfall_rial": 250_000,
                  "shortfall_at": time.time() - (cp.CARD_PAY_EXPIRE_HOURS * 3600 + 60)})
    cp._expire_stale_entries(time.time())
    assert entry["status"] == cp.S_EXPIRED

    # فاکتور جدید با همان payload → ورودی تازه (نه بازنویسی ورودی منقضی)
    cp.track_invoice({"chat_id": UID, "payload": payload,
                      "prices": [{"label": "x", "amount": 1_000_000}]})
    fresh = cp._find_active(UID, payload)
    assert fresh is not None and fresh["id"] != entry["id"]
    assert fresh["status"] == cp.S_INVOICE


def test_fresh_shortfall_survives_and_still_blocks_reinvoice():
    """کسری تازه منقضی نمی‌شود و یادآوری همان فاکتور همچنان نادیده گرفته می‌شود."""
    entry, payload = _review_entry()
    entry.update({"status": cp.S_SHORTFALL, "shortfall_rial": 250_000,
                  "shortfall_at": time.time()})
    cp._expire_stale_entries(time.time())
    assert entry["status"] == cp.S_SHORTFALL
    cp.track_invoice({"chat_id": UID, "payload": payload,
                      "prices": [{"label": "x", "amount": 1_000_000}]})
    assert cp._find_active(UID, payload)["id"] == entry["id"]


def test_shortfall_expiry_measured_from_shortfall_declaration():
    """سن کسری از «اعلام کسری» حساب می‌شود، نه از فاکتور اصلی."""
    entry, payload = _review_entry()
    old_invoice = time.time() - (cp.CARD_PAY_EXPIRE_HOURS * 3600 + 3600)
    entry["invoice_at"] = old_invoice          # فاکتور قدیمی است
    entry.update({"status": cp.S_SHORTFALL, "shortfall_rial": 250_000,
                  "shortfall_at": time.time() - 60})   # کسری همین حالا اعلام شده
    cp._expire_stale_entries(time.time())
    assert entry["status"] == cp.S_SHORTFALL   # هنوز معتبر است


# ── ⭐ اصلاحیه ۱۴۰۵/۰۸: بررسی state در تأیید کارتی reg_prepay ──────────────

def _reg_prepay_review_entry():
    payload = json.dumps({"type": "reg_prepay", "svc": "lavayeh", "uid": UID})
    cp.track_invoice({"chat_id": UID, "title": "پیش پرداخت لایحه", "payload": payload,
                      "prices": [{"label": "x", "amount": 1_000_000}]})
    entry = next(iter(cp._store.values()))
    entry.update({"status": cp.S_REVIEW, "full_name": "علی",
                  "receipt": {"file_id": "f1", "kind": "photo", "msg_id": 5, "at": time.time()},
                  "admin_msg_id": 78})
    return entry, payload


def test_reg_prepay_approval_with_changed_state_warns_not_applies(monkeypatch):
    """reg_prepay وابسته به state است: اگر کاربر سراغ سرویس دیگری رفته باشد،
    تایید بدون force انجام نمی‌شود (قبلاً چون payload-محور تلقی می‌شد، بدون
    بررسی state اعمال می‌شد و پرداخت سرویس قدیمی به سرویس جدید می‌رفت)."""

    async def fake_get_state(bot, uid):
        return "Form:waiting_for_ezhhar_prepay", {}   # کاربر در سرویس دیگری است

    async def scenario():
        bot = Bot("1:x")
        bot.edit_message_caption = AsyncMock()
        monkeypatch.setattr(cp, "_get_state", fake_get_state)
        monkeypatch.setattr(cp, "_restore_state", AsyncMock())
        entry, _ = _reg_prepay_review_entry()
        entry["state_snapshot"] = "Form:waiting_for_lavayeh_prepay"
        cb = _admin_cb(f"cpay:ok:{entry['id']}")
        cb.message.photo = [object()]
        cb.message.edit_caption = AsyncMock()
        await cp.cb_approve(cb, bot)
        # تایید انجام نشد؛ هشدار «وضعیت تغییر کرده» + دکمهٔ بازگردانی نمایش داده شد
        assert entry["status"] == cp.S_REVIEW
        assert cb.message.edit_caption.await_count == 1
        assert "وضعیت کاربر تغییر کرده است" in cb.message.edit_caption.await_args.kwargs["caption"]
        # بدون force هیچ stateای بازگردانی و پرداختی اعمال نمی‌شود
        assert cp._restore_state.await_count == 0
        await bot.session.close()

    asyncio.run(scenario())


def test_reg_prepay_approval_with_matching_state_applies(monkeypatch):
    """کاربر هنوز در همان state پیش‌پرداخت → تایید مستقیم انجام می‌شود."""

    async def fake_get_state(bot, uid):
        return "Form:waiting_for_lavayeh_prepay", {}

    async def scenario():
        bot = Bot("1:x")
        bot.edit_message_caption = AsyncMock()
        seen = []
        svc = Router()

        @svc.message(F.successful_payment)
        async def paid(message):
            seen.append(message.successful_payment)

        # ⚠️ card_router یک singleton ماژولی است و در تست‌های قبلی همین فایل به
        # Dispatcher دیگری چسبیده — برای بازپخش فقط dp با روتر ضبط‌کننده کافی است.
        dp = Dispatcher(storage=MemoryStorage())
        dp.include_router(svc)
        runtime_state.dp = dp
        monkeypatch.setattr(cp, "_get_state", fake_get_state)
        entry, _ = _reg_prepay_review_entry()
        entry["state_snapshot"] = "Form:waiting_for_lavayeh_prepay"
        await cp.cb_approve(_admin_cb(f"cpay:ok:{entry['id']}"), bot)
        assert entry["status"] == cp.S_APPROVED and len(seen) == 1
        await bot.session.close()

    asyncio.run(scenario())


def test_payload_routed_types_still_skip_state_check(monkeypatch):
    """نوع‌های payload-محور واقعی (مثل wallet_topup) همچنان بدون بررسی state
    تایید می‌شوند — فقط reg_prepay از مجموعهٔ معاف خارج شد."""

    async def fake_get_state(bot, uid):
        return "SomeOther:state", {}

    async def scenario():
        bot = Bot("1:x")
        bot.edit_message_caption = AsyncMock()
        monkeypatch.setattr(cp, "_get_state", fake_get_state)
        # dp تازه برای بازپخش (بدون وابستگی به تست‌های قبلی)
        dp = Dispatcher(storage=MemoryStorage())
        runtime_state.dp = dp
        payload = json.dumps({"type": "wallet_topup", "amt": 100_000, "uid": UID})
        cp.track_invoice({"chat_id": UID, "title": "شارژ کیف پول", "payload": payload,
                          "prices": [{"label": "x", "amount": 1_000_000}]})
        entry = next(iter(cp._store.values()))
        entry.update({"status": cp.S_REVIEW, "full_name": "علی",
                      "receipt": {"file_id": "f1", "kind": "photo", "msg_id": 5,
                                  "at": time.time()},
                      "admin_msg_id": 79, "state_snapshot": None})
        cb = _admin_cb(f"cpay:ok:{entry['id']}")
        cb.message.photo = [object()]
        await cp.cb_approve(cb, bot)
        assert entry["status"] == cp.S_APPROVED
        await bot.session.close()

    asyncio.run(scenario())


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
