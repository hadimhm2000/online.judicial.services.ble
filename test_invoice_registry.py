"""تست دفتر فاکتورهای پرونده‌محور: انقضای ۲۴ ساعته، قفل پرداخت هم‌زمان، یک‌بارمصرف،
و شناسایی پرداخت هر پرونده (چند لایحه/اظهارنامه هم‌زمان) مستقل از state."""
import asyncio
import json
import time
from types import SimpleNamespace

import pytest

import invoice_registry as ir


@pytest.fixture(autouse=True)
def _fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(ir, "STORE_FILE", str(tmp_path / "invoice_registry.json"))
    ir.reset_for_tests()
    yield
    ir.reset_for_tests()


def _issue(uid=1, tc="TC1", st="LAVAYEH", amount=1_000_000):
    inv, payload = ir.issue(uid, tc, st, amount)
    return inv, payload


def test_payload_identifies_case():
    inv, payload = _issue(uid=5, tc="1405220952369732", st="EZHHARNAMEH")
    obj = json.loads(payload)
    assert obj == {"type": "pending_case", "uid": 5, "tc": "1405220952369732",
                   "st": "EZHHARNAMEH", "inv": inv}
    assert ir.inv_of(payload) == inv
    assert ir.inv_of('{"type":"lavayeh","uid":5}') == ""
    assert ir.inv_of("not json") == ""


def test_two_cases_same_user_are_independent():
    inv_a, _ = _issue(tc="A", st="LAVAYEH")
    inv_b, _ = _issue(tc="B", st="EZHHARNAMEH")
    assert ir.claim(inv_a, 1) == (True, "")
    assert ir.settle(inv_a, 1, "c1") == (True, "")
    # پرداخت پروندهٔ A روی B اثری ندارد
    assert ir.case_paid(1, "A") and not ir.case_paid(1, "B")
    assert ir.claim(inv_b, 1) == (True, "")
    assert ir.settle(inv_b, 1, "c2") == (True, "")


def test_invoice_expires_after_24h(monkeypatch):
    inv, _ = _issue()
    real = time.time()
    monkeypatch.setattr(ir.time, "time", lambda: real + ir.EXPIRE_SECONDS + 1)
    assert ir.claim(inv, 1) == (False, "expired")
    # بله بدون pre_checkout هم پول را کسر کرده باشد: رد می‌شود (فراخوان به کیف پول برمی‌گرداند)
    assert ir.settle(inv, 1, "gateway-1") == (False, "expired")


def test_not_expired_just_before_24h(monkeypatch):
    inv, _ = _issue()
    real = time.time()
    monkeypatch.setattr(ir.time, "time", lambda: real + ir.EXPIRE_SECONDS - 60)
    assert ir.claim(inv, 1) == (True, "")


def test_concurrent_payment_blocked_then_released():
    inv, _ = _issue()
    assert ir.claim(inv, 1) == (True, "")
    assert ir.claim(inv, 1) == (False, "busy")          # پرداخت هم‌زمان
    ir.unclaim(inv)
    assert ir.claim(inv, 1) == (True, "")


def test_stale_claim_lapses(monkeypatch):
    inv, _ = _issue()
    assert ir.claim(inv, 1) == (True, "")
    real = time.time()
    monkeypatch.setattr(ir.time, "time", lambda: real + ir.CLAIM_SECONDS + 1)
    assert ir.claim(inv, 1) == (True, "")               # کاربر پرداخت را رها کرده بود


def test_single_use_after_payment():
    inv, _ = _issue()
    assert ir.claim(inv, 1) == (True, "")
    assert ir.settle(inv, 1, "c1") == (True, "")
    assert ir.claim(inv, 1) == (False, "paid")
    assert ir.settle(inv, 1, "c2") == (False, "paid")   # پرداخت دوم → کیف پول


def test_new_invoice_supersedes_old():
    old, _ = _issue()
    new, _ = _issue()
    assert old != new
    assert ir.claim(old, 1) == (False, "superseded")
    assert ir.settle(old, 1, "c1") == (False, "superseded")
    assert ir.claim(new, 1) == (True, "")


def test_issue_refused_while_payment_in_progress_or_paid():
    inv, _ = _issue()
    ir.claim(inv, 1)
    assert ir.issue(1, "TC1", "LAVAYEH", 5) is None      # پرداخت در جریان است
    ir.settle(inv, 1, "c1")
    assert ir.issue(1, "TC1", "LAVAYEH", 5) is None      # قبلاً پرداخت شده


def test_other_user_cannot_pay():
    inv, _ = _issue(uid=1)
    assert ir.claim(inv, 2) == (False, "owner")
    assert ir.settle(inv, 2, "c") == (False, "owner")


def test_replay_accepted_even_if_expired_but_not_twice(monkeypatch):
    inv, _ = _issue()
    real = time.time()
    monkeypatch.setattr(ir.time, "time", lambda: real + ir.EXPIRE_SECONDS + 10)
    # رسید کارت‌به‌کارت پس از انقضا توسط مدیر تایید شد: پول واقعاً دریافت شده
    assert ir.settle(inv, 1, "CARD-abc") == (True, "")
    assert ir.settle(inv, 1, "CARD-def") == (False, "paid")


def test_close_case_voids_open_invoices():
    inv, _ = _issue()
    ir.close_case(1, "TC1")
    assert ir.claim(inv, 1) == (False, "superseded")


def test_unknown_invoice_is_allowed():
    assert ir.claim("nope", 1) == (True, "")
    assert ir.settle("nope", 1, "c") == (True, "")


def test_persisted_across_restart(tmp_path):
    inv, _ = _issue()
    ir.settle(inv, 1, "c1")
    ir._store.clear()
    ir._loaded = False                                    # شبیه ری‌استارت
    assert ir.case_paid(1, "TC1")


# ── میان‌افزارها ────────────────────────────────────────────────────────────

class _Bot:
    def __init__(self):
        self.answers, self.sent = [], []

    async def answer_pre_checkout_query(self, qid, ok, error_message=None):
        self.answers.append((qid, ok, error_message))

    async def send_message(self, chat_id, text, **kw):
        self.sent.append((chat_id, text))


def _run(coro):
    return asyncio.run(coro)


def test_pre_checkout_middleware_rejects_expired(monkeypatch):
    inv, payload = _issue()
    real = time.time()
    monkeypatch.setattr(ir.time, "time", lambda: real + ir.EXPIRE_SECONDS + 1)
    bot, called = _Bot(), []

    async def handler(event, data):
        called.append(1)

    ev = SimpleNamespace(id="q1", invoice_payload=payload, from_user=SimpleNamespace(id=1))
    _run(ir.RegistryPreCheckoutMiddleware()(handler, ev, {"bot": bot}))
    assert not called
    assert bot.answers and bot.answers[0][1] is False


def test_pre_checkout_middleware_passes_legacy_and_valid():
    inv, payload = _issue()
    bot, called = _Bot(), []

    async def handler(event, data):
        called.append(event.invoice_payload)

    mw = ir.RegistryPreCheckoutMiddleware()
    _run(mw(handler, SimpleNamespace(id="q", invoice_payload=payload, from_user=SimpleNamespace(id=1)), {"bot": bot}))
    _run(mw(handler, SimpleNamespace(id="q", invoice_payload='{"type":"single"}', from_user=SimpleNamespace(id=1)), {"bot": bot}))
    assert len(called) == 2


def test_payment_middleware_refunds_duplicate_to_wallet(monkeypatch):
    inv, payload = _issue()
    credits = []

    class _Wallet:
        @staticmethod
        async def credit(uid, amount, kind, note):
            credits.append((uid, amount, kind))

        @staticmethod
        def balance(uid):
            return 100

    import sys
    monkeypatch.setitem(sys.modules, "wallet", _Wallet)
    bot, called = _Bot(), []

    async def handler(event, data):
        called.append(1)

    def msg(charge):
        sp = SimpleNamespace(invoice_payload=payload, telegram_payment_charge_id=charge, total_amount=1_000_000)
        return SimpleNamespace(successful_payment=sp, from_user=SimpleNamespace(id=1))

    mw = ir.RegistryPaymentMiddleware()
    _run(mw(handler, msg("G1"), {"bot": bot}))           # اولین پرداخت: اعمال می‌شود
    _run(mw(handler, msg("G2"), {"bot": bot}))           # دومی: به کیف پول برمی‌گردد
    assert called == [1]
    assert credits == [(1, 100_000, "refund")]
