"""تست ۱۴۰۵/۰۷: «پرونده‌های در انتظار امضا و پرداخت» و دریافت چاپ PDF درخواستی.
اجرا: BOT_TOKEN=x ADMIN_ID=1 ADMIN_API_SECRET=x python -m pytest test_pending_cases.py"""
import asyncio
import datetime
import json
import os
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("ADMIN_API_SECRET", "x")

import pytest

import final_print
import pending_cases
import runtime_state


@pytest.fixture(autouse=True)
def _tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(final_print, "STORE_FILE", str(tmp_path / "fp.json"))
    monkeypatch.setattr(pending_cases, "STORE_FILE", str(tmp_path / "pc.json"))
    runtime_state.pending_lavayeh_payments.clear()
    runtime_state.pending_tn_payments.clear()
    # ⭐ ایزوله‌سازی کیف پول (برگشت پرداخت تکراری به کیف پول)
    import wallet
    monkeypatch.setattr(wallet, "STORE_FILE", str(tmp_path / "wallet.json"))
    wallet._store = {"users": {}, "offers": {}, "holds": {}, "autopaid": {}}
    wallet._lock = asyncio.Lock()


def _lavayeh_ctx(tc="111", svc="LAVAYEH", fee=500_000):
    return {"invoice_time": datetime.datetime.now(), "final_fee": fee, "court_total": 100_000,
            "tracking_code": tc, "national_ids": "123", "lavayeh_title": "لایحه دفاعیه",
            "lavayeh_persons": [{"name": "علی"}], "is_ezhharnameh": svc == "EZHHARNAMEH",
            "service_type": svc, "sign_menu_path": None}


def _age(tc, days):
    data = pending_cases._load()
    for it in data["items"]:
        if it["tracking_code"] == tc:
            it["registered_at"] = (pending_cases._now() - datetime.timedelta(days=days)).isoformat()
    pending_cases._save(data)


# ── ۱) ثبت، پرداخت، امضا ────────────────────────────────────────────────

def test_unpaid_then_paid_then_signed_leaves_list():
    assert pending_cases.record_unpaid(7, pending_cases.KIND_LAVAYEH, _lavayeh_ctx())
    [it] = pending_cases.open_cases(7)
    assert not it["paid"] and it["final_fee"] == 500_000
    assert it["doc_category"] == "لایحه"
    assert pending_cases.mark_paid(7, "111")
    assert pending_cases.open_cases(7)[0]["paid"]
    # پایان امضای همهٔ اشخاص (final_print.mark_signed) پرونده را از منو خارج می‌کند
    final_print.mark_signed(7, "111")
    assert pending_cases.open_cases(7) == []
    # رکورد برای دریافت دوبارهٔ چاپ از «سوابق» می‌ماند
    assert pending_cases.print_category(7, "111") == ("لایحه", None)


def test_paid_record_keeps_tn_persons_from_earlier_record():
    pending_cases.record_unpaid(7, pending_cases.KIND_TN, {
        "final_fee": 900_000, "tracking_code": "555", "case_type": "تجدیدنظرخواهی",
        "tn_persons": [{"name": "x"}]})
    pending_cases.record_paid(7, pending_cases.KIND_TN, {
        "tracking_code": "555", "case_type": "تجدیدنظرخواهی", "tn_persons": []})
    [it] = pending_cases.open_cases(7)
    assert it["paid"] and it["ctx"]["tn_persons"] == [{"name": "x"}]
    assert it["doc_category"] == "دعاوی اعتراضی" and it["doc_subcategory"] == "تجدیدنظرخواهی"


# ── ۲) لایحه ۴ روز، سایر موارد همیشه ─────────────────────────────────────

def test_lavayeh_and_ealam_four_days_others_thirty():
    pending_cases.record_unpaid(7, pending_cases.KIND_LAVAYEH, _lavayeh_ctx("111", "LAVAYEH"))
    pending_cases.record_unpaid(7, pending_cases.KIND_LAVAYEH, _lavayeh_ctx("222", "EZHHARNAMEH"))
    pending_cases.record_unpaid(7, pending_cases.KIND_LAVAYEH, _lavayeh_ctx("333", "EALAM_VAKALAHT"))
    pending_cases.record_unpaid(7, pending_cases.KIND_LAVAYEH, _lavayeh_ctx("444", "CHECK"))
    for tc in ("111", "333"):
        _age(tc, 3)
    for tc in ("222", "444"):
        _age(tc, 29)
    assert {it["tracking_code"] for it in pending_cases.open_cases(7)} == {"111", "222", "333", "444"}
    for tc in ("111", "333"):
        _age(tc, 4)
    assert {it["tracking_code"] for it in pending_cases.open_cases(7)} == {"222", "444"}
    for tc in ("222", "444"):
        _age(tc, 30)
    assert pending_cases.open_cases(7) == []


def test_cancelled_hidden():
    pending_cases.record_unpaid(7, pending_cases.KIND_LAVAYEH, _lavayeh_ctx())
    pending_cases.mark_cancelled(7, "111")
    assert pending_cases.open_cases(7) == []


# ── ۳) پرداخت با payload پرونده → هندلر پرداخت موجود ───────────────────────

def test_payment_restores_invoice_and_keeps_other_open_invoice(monkeypatch):
    import lavayeh_handlers
    import pending_cases_handlers

    pending_cases.record_unpaid(7, pending_cases.KIND_LAVAYEH, _lavayeh_ctx("111"))
    other = _lavayeh_ctx("999")
    runtime_state.pending_lavayeh_payments[7] = other
    seen = {}

    async def fake_pay(message, state, bot):
        seen.update(runtime_state.pending_lavayeh_payments.pop(7))

    monkeypatch.setattr(lavayeh_handlers, "lavayeh_successful_payment", fake_pay)
    msg = MagicMock()
    msg.from_user.id = 7
    msg.successful_payment.invoice_payload = json.dumps(
        {"type": "pending_case", "uid": 7, "tc": "111"})
    assert pending_cases_handlers._is_pending_case_payment(msg)
    asyncio.run(pending_cases_handlers.pending_case_successful_payment(msg, MagicMock(), MagicMock()))
    assert seen["tracking_code"] == "111" and seen["final_fee"] == 500_000
    assert runtime_state.pending_lavayeh_payments[7] is other   # فاکتور دیگر گم نشد
    assert pending_cases.open_cases(7)[0]["paid"]


# ── ⭐ اصلاحیه ۱۴۰۵/۰۸: پرداخت تکراری / خطای هندلر ─────────────────────

def _pay_msg(uid, tc, amount_rial=500_000):
    msg = MagicMock()
    msg.from_user.id = uid
    msg.answer = AsyncMock()
    msg.successful_payment.total_amount = amount_rial
    msg.successful_payment.telegram_payment_charge_id = "BALE-DUP"
    msg.successful_payment.invoice_payload = json.dumps(
        {"type": "pending_case", "uid": uid, "tc": tc})
    return msg


def test_duplicate_payment_of_paid_case_refunds_and_skips_processing(monkeypatch):
    """دو فاکتور برای یک پرونده و هر دو پرداخت شوند → فقط اولی پردازش می‌شود؛
    دومی به کیف پول کاربر برمی‌گردد و مدیر مطلع می‌شود."""
    import lavayeh_handlers
    import pending_cases_handlers
    import wallet
    from config import ADMIN_ID

    pending_cases.record_unpaid(7, pending_cases.KIND_LAVAYEH, _lavayeh_ctx("111"))
    pending_cases.mark_paid(7, "111")            # پرداخت اول انجام شده
    calls = []

    async def fake_pay(message, state, bot):
        calls.append(1)

    monkeypatch.setattr(lavayeh_handlers, "lavayeh_successful_payment", fake_pay)
    msg = _pay_msg(7, "111")
    state = MagicMock()
    state.clear = AsyncMock()
    bot = MagicMock()
    bot.send_message = AsyncMock()
    asyncio.run(pending_cases_handlers.pending_case_successful_payment(msg, state, bot))

    assert calls == []                            # پردازش تکراری انجام نشد
    assert wallet.balance(7) == 50_000            # مبلغ به کیف پول برگشت
    assert "برگشت" in msg.answer.call_args.args[0]
    admin_texts = [c.args[1] for c in bot.send_message.await_args_list
                   if c.args and c.args[0] == ADMIN_ID and len(c.args) > 1]
    assert admin_texts and "تکراری" in admin_texts[0]
    state.clear.assert_awaited()


def test_handler_failure_still_marks_case_paid(monkeypatch):
    """mark_paid پیش از هندلر است: اگر هندلر پرداخت خطا بدهد، پرونده
    «پرداخت‌شده» می‌ماند و پرداخت دوم تکراری شناخته می‌شود (کاربر دو بار
    هزینه نمی‌دهد و از دکمهٔ «درج امضا» ادامه می‌دهد)."""
    import lavayeh_handlers
    import pending_cases_handlers

    pending_cases.record_unpaid(7, pending_cases.KIND_LAVAYEH, _lavayeh_ctx("222"))

    async def boom(message, state, bot):
        raise RuntimeError("شکست هندلر پرداخت")

    monkeypatch.setattr(lavayeh_handlers, "lavayeh_successful_payment", boom)
    # ⭐ خطا به بیرون (بازپخش کیف پول/کارت) نمی‌رسد — وگرنه مبلغ خودکار به
    # کیف پول برمی‌گشت در حالی که پرونده پرداخت‌شده می‌ماند (دریافت دوگانه)
    msg = _pay_msg(7, "222")
    bot = MagicMock()
    bot.send_message = AsyncMock()
    asyncio.run(pending_cases_handlers.pending_case_successful_payment(
        msg, MagicMock(), bot))
    bot.send_message.assert_awaited()  # مدیر مطلع شد
    # با وجود خطا، پرداخت ثبت شد
    assert pending_cases.get(7, "222")["paid"] is True


# ── ⭐ اصلاحیه ۱۴۰۵/۰۸: ثبت درست pending_case در پنل ───────────────────

def test_pending_case_card_payment_maps_to_real_panel_service():
    """پرداخت کارتی فاکتور پروندهٔ در انتظار → serviceType واقعی پرونده و
    paymentKind=FINAL (قبلاً UNKNOWN/DIRECT ثبت می‌شد و کل مبلغ سود حساب می‌شد)."""
    import card_payment as cp

    pending_cases.record_unpaid(7, pending_cases.KIND_TN, {
        "final_fee": 900_000, "tracking_code": "555", "case_type": "تجدیدنظرخواهی",
        "tn_persons": [{"name": "x"}]})

    # فاکتور جدید (payload دارای st)
    entry = {"uid": 7, "payload_obj": {"type": "pending_case", "uid": 7, "tc": "555",
                                       "st": "TAJDID_NAZAR"}}
    assert cp._panel_service_type(entry) == "TAJDID_NAZAR"
    assert cp._payment_kind(entry) == "FINAL"

    # فاکتور قدیمی بدون st → از دفتر pending_cases خوانده می‌شود
    entry2 = {"uid": 7, "payload_obj": {"type": "pending_case", "uid": 7, "tc": "555"}}
    assert cp._panel_service_type(entry2) == "TAJDID_NAZAR"
    assert cp._payment_kind(entry2) == "FINAL"

    # پروندهٔ ناشناخته → UNKNOWN (بدون تغییر رفتار پیشین در این حالت مرزی)
    entry3 = {"uid": 7, "payload_obj": {"type": "pending_case", "uid": 7, "tc": "nope"}}
    assert cp._panel_service_type(entry3) == "UNKNOWN"


def test_pending_case_invoice_payload_carries_service_type():
    """فاکتور پرونده، نوع سرویس (st) را در payload می‌برد تا پنل و شیت درست ثبت شوند."""
    import pending_cases_handlers

    pending_cases.record_unpaid(7, pending_cases.KIND_TN, {
        "final_fee": 900_000, "tracking_code": "555", "case_type": "تجدیدنظرخواهی",
        "tn_persons": []})
    it = pending_cases.get(7, "555")
    payload = json.loads(pending_cases_handlers._invoice_payload(7, it))
    assert payload["type"] == "pending_case" and payload["tc"] == "555"
    assert payload["st"] == "TAJDID_NAZAR"


# ── ۴) چاپ درخواستی کاربر ─────────────────────────────────────────────

def test_on_demand_print_does_not_touch_final_print_queue(monkeypatch):
    queue = asyncio.Queue()
    monkeypatch.setattr(runtime_state, "job_queue", queue, raising=False)
    final_print.record_registration(7, "111", service_type="LAVAYEH")

    async def scenario():
        assert await final_print.request_print(7, "111", "لایحه")
        assert not await final_print.request_print(7, "111", "لایحه")   # درخواست تکراری
        job = queue.get_nowait()
        assert job["final_print"] and "چاپ PDF" in job["print_caption"]
        final_print.mark_sent(7, "111")
        [it] = final_print._load()["items"]
        assert it["status"] == "pending"           # چاپ نهایی پس از امضا هنوز ارسال می‌شود
        assert not final_print.print_in_progress(7, "111")

        # خطا: فقط به خود کاربر پیام می‌رود، مورد صف دست نمی‌خورد
        assert await final_print.request_print(7, "111", "لایحه")
        bot = MagicMock()
        bot.send_message = AsyncMock()
        await final_print.report_failure(bot, 7, "111", "لایحه", "x")
        assert bot.send_message.await_args.args[0] == 7
        [it] = final_print._load()["items"]
        assert it["status"] == "pending" and not it.get("last_error")

    asyncio.run(scenario())


def test_history_print_category():
    import history_handlers
    assert history_handlers.print_category(7, {"serviceType": "INQUIRY", "trackingCode": "1"}) is None
    assert history_handlers.print_category(7, {"serviceType": "LAVAYEH", "trackingCode": ""}) is None
    assert history_handlers.print_category(7, {"serviceType": "EZHHARNAMEH", "trackingCode": "1"}) == ("اظهارنامه", None)
    assert history_handlers.print_category(
        7, {"serviceType": "TAJDID_NAZAR", "trackingCode": "1",
            "documentCategory": "واخواهی — پرونده 12"}) == ("دعاوی اعتراضی", "واخواهی")
    # چک بدون مسیر منو حدس زده نمی‌شود، مگر در دفتر ربات ثبت شده باشد
    assert history_handlers.print_category(7, {"serviceType": "CHECK", "trackingCode": "1"}) is None
    final_print.record_registration(7, "1", service_type="CHECK", sign_menu_path=["دادخواست بدوی"])
    assert history_handlers.print_category(7, {"serviceType": "CHECK", "trackingCode": "1"}) == ("دادخواست بدوی", None)
