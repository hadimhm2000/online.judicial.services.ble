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
    # ⭐ ایزوله‌سازی صف بازگشت وجه — مهاجرت مبالغ قدیمی اکنون از این صف
    # عبور می‌کند (بازگشت وجه فقط با تایید مدیر)
    import refund_approvals as _ra
    monkeypatch.setattr(_ra, "STORE_FILE", str(tmp_path / "refund_approvals.json"))
    _ra._store = {"items": {}}
    _ra._lock = asyncio.Lock()
    _ra._bot = None



async def _set_prepay_state(uid):
    """⭐ reg_prepay فقط در state انتظار پیش‌پرداخت به‌صورت خودکار از کیف پول
    پرداخت می‌شود (همان وضعیتی که هندلر فرستندهٔ فاکتور می‌گذارد)."""
    from aiogram.fsm.storage.base import StorageKey
    from states import Form
    dp = runtime_state.dp
    await dp.storage.set_state(StorageKey(bot_id=1, chat_id=uid, user_id=uid),
                               Form.waiting_for_lavayeh_prepay.state)

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
        await _set_prepay_state(9)
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


def test_auto_pay_payload_routed_types_include_single_use_and_pending_case(monkeypatch):
    """⭐ اصلاحیه ۱۴۰۵/۰۸: نوع‌های payload-محور (single_use / pending_case)
    مثل card_payment شناخته می‌شوند؛ پرداخت خودکار بدون state انجام می‌شود و
    دکمهٔ دستی دیگر با «مرحله تغییر کرده» رد نمی‌شود."""
    monkeypatch.setattr(wallet, "AUTOPAY_FIRST_DELAY", 0)
    monkeypatch.setattr(wallet, "AUTOPAY_STABLE_DELAY", 0)

    async def scenario():
        bot = Bot("1:x")
        bot.send_message = AsyncMock()

        async def no_chat(uid):
            raise RuntimeError("آفلاین")

        bot.get_chat = no_chat
        seen = []
        dp = _dp_with_service(seen)
        wallet.set_bot(bot)
        wallet._apply(9, 20_000, "topup")
        for ptype in ("single_use", "pending_case"):
            payload = json.dumps({"type": ptype, "uid": 9, "tc": "T1"})
            await wallet._auto_pay(9, payload, ptype, 100_000, f"فاکتور {ptype}")
            assert len(seen) == ("single_use", "pending_case").index(ptype) + 1
        # بدون state هم پرداخت خودکار انجام شد؛ دکمهٔ دستی «پرداخت از کیف پول»
        # پیشنهاد نشد (رکوردهای offer با used=True/auto=True فقط رسید پرداخت خودکارند)
        assert len(seen) == 2
        assert all(o.get("used") and o.get("auto") for o in wallet._store["offers"].values())
        assert wallet.balance(9) == 0
        await bot.session.close()

    asyncio.run(scenario())


def test_leftover_after_final_invoice_goes_to_refund_queue():
    """⭐ مطابق سیاست «بازگشت وجه فقط با تایید مدیر»: مازاد پیش‌پرداخت به صف
    تایید می‌رود، نه واریز مستقیم به کیف پول (تست قبلی مستقیم کیف پول را
    می‌خواست و از زمان سیاست جدیدِ refund_approvals منسوخ شده بود)."""
    import prepay_registration as pr
    import refund_approvals as ra
    runtime_state.prepaid_registrations[21] = {"amount_rial": 150_000, "amount_toman": 15_000,
                                               "prepay_paid_rial": 150_000}
    adjusted, info = pr.adjust_final_fee_with_prepay(21, 100_000)
    assert adjusted == 0 and info["leftover_rial"] == 50_000
    assert wallet.balance(21) == 0            # هنوز واریز نشده
    assert ra.pending_total_toman(21) == 5_000  # در انتظار تایید مدیر
    assert 21 not in runtime_state.prepaid_registrations
    assert "تایید مدیریت" in pr.build_prepay_fee_text(0, info, 100_000)


def test_migrate_legacy_credits_requests_refund_and_keeps_inflight_prepay():
    """⭐ اصلاحیه ۱۴۰۵/۰۸: مهاجرت مبالغ قدیمی به «صف تایید مدیر» می‌رود، نه
    واریز مستقیم به کیف پول (هم‌راستا با سیاست «بازگشت وجه فقط با تایید»)."""
    import refund_approvals as ra
    from bulk_submissions import BULK_TASKS
    runtime_state.prepaid_registrations.clear()
    runtime_state.prepaid_registrations[31] = {"amount_rial": 300_000, "manual": True}
    runtime_state.prepaid_registrations[32] = {"amount_rial": 50_000, "prepay_paid_rial": 20_000}
    BULK_TASKS["T-MIG"] = {"user_id": 33, "finalized": True, "surplus_rial": 70_000}
    try:
        assert wallet.migrate_legacy_credits() == 3
        # هنوز چیزی به کیف پول واریز نشده — همه در انتظار تایید مدیر
        assert wallet.balance(31) == 0 and 31 not in runtime_state.prepaid_registrations
        assert ra.pending_total_toman(31) == 30_000
        assert wallet.balance(32) == 0
        assert ra.pending_total_toman(32) == 3_000
        assert runtime_state.prepaid_registrations[32]["amount_rial"] == 20_000
        assert wallet.balance(33) == 0 and BULK_TASKS["T-MIG"]["surplus_rial"] == 0
        assert ra.pending_total_toman(33) == 7_000
        assert wallet.migrate_legacy_credits() == 0  # تکرار بی‌اثر
        # تایید مدیر → واریز به کیف پول (فقط همان مبلغ مهاجرت‌شده)
        rid31 = next(v["id"] for v in ra._store["items"].values() if v.get("uid") == 31)
        assert asyncio.run(ra.decide(rid31, True, 1))[0] == "done"
        assert wallet.balance(31) == 30_000
        # رد پس از مهاجرت → در ری‌استارت بعدی درخواست تازه ساخته نمی‌شود
        rid32 = next(v["id"] for v in ra._store["items"].values() if v.get("uid") == 32)
        assert asyncio.run(ra.decide(rid32, False, 1))[0] == "done"
        assert wallet.balance(32) == 0
        runtime_state.prepaid_registrations[31] = {"amount_rial": 500_000, "manual": True}
        assert wallet.migrate_legacy_credits() == 0  # fid/کلید یگانه جلوی تکرار را می‌گیرد
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


# ── پشتیبان، فایل خراب و دفتر تراکنش‌ها ─────────────────────────────────────

def test_save_keeps_backup_and_ledger():
    wallet.credit_nowait(7, 1_000, "refund", "a")
    wallet.credit_nowait(7, 2_000, "refund", "b")
    with open(wallet.STORE_FILE + ".bak", encoding="utf-8") as f:
        assert json.load(f)["users"]["7"]["balance"] == 1_000
    with open(wallet._ledger_file(), encoding="utf-8") as f:
        lines = [json.loads(x) for x in f]
    assert [(x["uid"], x["amount"], x["balance"]) for x in lines] == [("7", 1_000, 1_000), ("7", 2_000, 3_000)]


def test_corrupt_file_is_set_aside_and_backup_loaded(monkeypatch):
    wallet.credit_nowait(7, 1_000)
    wallet.credit_nowait(7, 2_000)
    with open(wallet.STORE_FILE, "w", encoding="utf-8") as f:
        f.write("{broken")
    monkeypatch.setattr(wallet, "_load_problem", "")
    wallet._store = {"users": {}, "offers": {}, "holds": {}, "autopaid": {}}
    wallet._load()
    assert wallet.balance(7) == 1_000
    assert wallet._load_problem
    folder = os.path.dirname(wallet.STORE_FILE)
    aside = [n for n in os.listdir(folder) if n.startswith("wallet.json.corrupt-")]
    assert len(aside) == 1
    # ذخیرهٔ بعدی نسخهٔ پشتیبان سالم را با فایل خراب جایگزین نمی‌کند
    wallet.credit_nowait(7, 500)
    with open(wallet.STORE_FILE + ".bak", encoding="utf-8") as f:
        assert json.load(f)["users"]["7"]["balance"] == 1_000


def test_normal_load_has_no_problem(monkeypatch):
    wallet.credit_nowait(7, 1_000)
    monkeypatch.setattr(wallet, "_load_problem", "")
    wallet._store = {"users": {}, "offers": {}, "holds": {}, "autopaid": {}}
    wallet._load()
    assert wallet.balance(7) == 1_000 and wallet._load_problem == ""
