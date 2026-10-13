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
