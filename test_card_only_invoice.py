"""تست «فقط کارت‌به‌کارت» برای فاکتور بالای ۱,۰۰۰,۰۰۰ تومان — اجرا: python -m pytest test_card_only_invoice.py"""
import asyncio
import json
import os

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("ADMIN_API_SECRET", "x")

import pytest

import card_payment as cp

UID = 42


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(cp, "_STORE_FILE", str(tmp_path / "card_payments.json"))
    monkeypatch.setattr(cp, "CARD_PAY_ENABLED", True)
    monkeypatch.setattr(cp, "CARD_ONLY_ABOVE_TOMAN", 1_000_000)
    cp._store = {}
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


def _invoice(amount_rial, ptype="tajdid_nazar"):
    return {"chat_id": UID, "title": "فاکتور دعوی اعتراضی",
            "payload": json.dumps({"type": ptype, "uid": UID}),
            "prices": [{"label": "x", "amount": amount_rial}]}


def test_threshold_is_strictly_above_one_million_toman():
    assert not cp.card_only_required(_invoice(10_000_000))   # دقیقاً ۱,۰۰۰,۰۰۰ تومان
    assert cp.card_only_required(_invoice(10_000_010))
    assert not cp.card_only_required(_invoice(5_000_000))


def test_disabled_when_threshold_zero(monkeypatch):
    monkeypatch.setattr(cp, "CARD_ONLY_ABOVE_TOMAN", 0)
    assert not cp.card_only_required(_invoice(50_000_000))


def test_card_only_offer_waits_for_payment_state_then_sends(_isolated, monkeypatch):
    cp.track_card_only_invoice(_invoice(20_000_000))
    entry = next(iter(cp._store.values()))
    assert entry["card_only"] and entry["status"] == cp.S_INVOICE
    # سررسید حلقه چند ثانیه بعد است، نه ۲۰ دقیقه
    due_in = entry["invoice_at"] + cp.CARD_PAY_DELAY_MINUTES * 60 - cp._now()
    assert due_in <= cp._CARD_ONLY_FIRST_DELAY + 1

    states = iter([("Form:some_other_state", {}), ("Form:waiting_for_tn_payment_receipt", {})])

    async def fake_state(_bot, _uid):
        return next(states)
    monkeypatch.setattr(cp, "_get_state", fake_state)

    asyncio.run(cp._send_card_offer(None, entry))
    assert entry["status"] == cp.S_INVOICE and not _isolated   # هنوز state پرداخت ست نشده
    asyncio.run(cp._send_card_offer(None, entry))
    assert entry["status"] == cp.S_CARD_SENT
    caption = _isolated[0][1]["text"]
    assert "درگاه امکان‌پذیر نیست" in caption and "فاکتور قبلی" not in caption


def test_card_only_resend_on_reminder(_isolated):
    cp.track_card_only_invoice(_invoice(20_000_000))
    entry = next(iter(cp._store.values()))
    entry["status"] = cp.S_CARD_SENT
    cp.track_card_only_invoice(_invoice(20_000_000))
    assert entry["status"] == cp.S_INVOICE   # دوباره ارسال می‌شود


def test_default_delay_is_ten_minutes(monkeypatch):
    import importlib
    import config
    monkeypatch.delenv("CARD_PAY_DELAY_MINUTES", raising=False)
    assert importlib.reload(config).CARD_PAY_DELAY_MINUTES == 10


@pytest.mark.parametrize("ptype", ["wallet_topup", "pending_case"])
def test_payload_routed_invoice_gets_card_offer_without_payment_state(_isolated, monkeypatch, ptype):
    """فاکتورهای بدون state انتظار پرداخت (شارژ کیف پول، پروندهٔ در انتظار) هم کارت‌به‌کارت بگیرند."""
    cp.track_invoice(_invoice(1_000_000, ptype))
    entry = next(iter(cp._store.values()))

    async def fake_state(_bot, _uid):
        return None, {}
    monkeypatch.setattr(cp, "_get_state", fake_state)
    asyncio.run(cp._send_card_offer(None, entry))
    assert entry["status"] == cp.S_CARD_SENT


def test_wallet_topup_card_choice_sends_card_offer_with_choice_caption(_isolated, monkeypatch):
    import wallet
    from unittest.mock import AsyncMock, MagicMock
    cb = MagicMock()
    cb.data = "wal:cc:200000"
    cb.from_user.id = UID
    cb.answer = AsyncMock()
    cb.message.answer = AsyncMock()
    asyncio.run(wallet.cb_wallet_topup_card(cb))

    entry = next(iter(cp._store.values()))
    assert entry["card_only"] and entry["card_by_choice"] and entry["amount_rial"] == 2_000_000
    assert json.loads(entry["payload"])["type"] == wallet.TOPUP_TYPE

    async def fake_state(_bot, _uid):
        return None, {}
    monkeypatch.setattr(cp, "_get_state", fake_state)
    asyncio.run(cp._send_card_offer(None, entry))
    assert entry["status"] == cp.S_CARD_SENT
    caption = _isolated[0][1]["text"]
    assert "200,000 تومان" in caption and "درگاه امکان‌پذیر نیست" not in caption


def test_wallet_topup_amount_asks_for_payment_method(monkeypatch):
    import wallet
    from unittest.mock import AsyncMock, MagicMock
    monkeypatch.setattr("config.CARD_PAY_ENABLED", True)
    cb = MagicMock()
    cb.data = "wal:top:100000"
    cb.answer = AsyncMock()
    cb.message.answer = AsyncMock()
    asyncio.run(wallet.cb_wallet_topup(cb))
    kb = cb.message.answer.await_args.kwargs["reply_markup"].inline_keyboard
    assert [b[0].callback_data for b in kb] == ["wal:gw:100000", "wal:cc:100000"]


def test_receipt_without_state_matches_payload_routed_entry(_isolated):
    from unittest.mock import AsyncMock, MagicMock
    cp.track_invoice(_invoice(1_000_000, "wallet_topup"))
    entry = next(iter(cp._store.values()))
    entry.update(status=cp.S_CARD_SENT, state_snapshot=None)
    msg = MagicMock()
    msg.from_user.id = UID
    state = MagicMock()
    state.get_state = AsyncMock(return_value=None)
    assert asyncio.run(cp._receipt_target(msg, state)) is entry
    state.get_state = AsyncMock(return_value="Form:something")
    assert asyncio.run(cp._receipt_target(msg, state)) is None
