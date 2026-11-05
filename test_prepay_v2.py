"""تست نسخهٔ ۲ سیستم پیش‌پرداخت — سند «پیش‌پرداخت ثبت / مانده» §۷ (۱۴۰۵/۱۱).

۱۱ سناریوی سند + معیارهای پذیرش:
  ۱. بازتولید حادثه: ۶ ثبت پشت‌سرهم ⇒ ۶ فاکتور کامل و ۶ رزرو؛ هیچ ثبت رایگان نیست
  ۲. cover واقعی: ۳ ثبت پشت‌سرهم با مانده ⇒ مانده صفر و ۳ رزرو؛ ثبت چهارم ⇒ فاکتور
  ۳. کلیک دوبل: دو تایید همزمان ⇒ فقط یک job و یک رزرو
  ۴. پرداخت تکراری: همان charge_id دوبار ⇒ فقط یک‌بار ثبت
  ۵. مانده ناقص: فاکتور ۶۰۰٬۰۰۰ + hold ۴۰۰٬۰۰۰؛ انصراف ⇒ برگشت سهم مانده
  ۶. پایان کار هم‌زمان ۳ تسک: هر تسک فقط رزرو خودش؛ سرویس اشتباه کسر نمی‌شود
  ۷. مازاد: هزینه کمتر از رزرو ⇒ مازاد همان رزرو به صف بازگشت می‌رود
  ۸. شکست تسک: رزرو آزاد و پول به ماندهٔ آزاد برمی‌گردد
  ۹. مهاجرت v1→v2: رکورد قدیمی به رزرو + ماندهٔ آزاد تبدیل و FIFO مصرف می‌شود
  ۱۰. pay_reconcile: رزرو queued هشدار نمی‌دهد؛ reserved بدون job هشدار می‌دهد
  ۱۱. lavayeh_entry: کاربرِ دارای تسک در صف از active_lavayeh_users حذف نمی‌شود

اجرا: BOT_TOKEN=1:x ADMIN_ID=1 ADMIN_API_SECRET=x python -m pytest test_prepay_v2.py -v
"""
import asyncio
import datetime
import os
import uuid
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("ADMIN_API_SECRET", "x")
os.environ.setdefault("BALE_API_BASE", "https://tapi.bale.ai")

import pytest

import runtime_state
import prepay_registration as pr
import refund_approvals
import wallet
import persistence
import sana_gate

UID = 501


# ── ایزوله‌سازی فایل‌های وضعیت و فروشگاه‌ها (الگوی test_startup_data_fixes) ──

@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "save_state", lambda data, filepath=None: None)
    monkeypatch.setattr(persistence, "load_state", lambda filepath=None: {})
    monkeypatch.setattr(wallet, "STORE_FILE", str(tmp_path / "wallet.json"))
    wallet._store = {"users": {}, "offers": {}, "holds": {}, "autopaid": {}}
    monkeypatch.setattr(refund_approvals, "STORE_FILE", str(tmp_path / "refund.json"))
    refund_approvals._store = {"items": {}}
    _saved_prepaid = dict(runtime_state.prepaid_registrations)
    runtime_state.prepaid_registrations.clear()
    runtime_state.processed_charge_ids = set()
    runtime_state.consumed_prepay_for_panel = {}
    _saved_active = set(runtime_state.active_lavayeh_users)
    runtime_state.active_lavayeh_users.clear()
    _saved_queue = runtime_state.job_queue
    runtime_state.job_queue = asyncio.Queue()
    yield
    runtime_state.prepaid_registrations.clear()
    runtime_state.prepaid_registrations.update(_saved_prepaid)
    runtime_state.active_lavayeh_users.clear()
    runtime_state.active_lavayeh_users.update(_saved_active)
    runtime_state.job_queue = _saved_queue


def _give_free_credit(uid, rial):
    rec = pr._rec(uid, create=True)
    rec["free_credit_rial"] = rial


def _active_reservations(uid):
    rec = pr._rec(uid)
    return [r for r in (rec or {}).get("reservations", [])
            if r.get("status") in ("hold", "reserved", "queued")]


def _paid_registration(uid, svc, paid_rial, charge=None):
    """ثبت با پرداخت کامل (مثل successful_payment با tid از payload فاکتور)."""
    inv_rial, hold = pr.hold_for_invoice(uid, svc, f"تست {svc}")
    assert inv_rial > 0
    charge = charge or f"ch-{uuid.uuid4().hex[:10]}"
    res = pr.finalize_paid(uid, hold["task_id"], svc, f"تست {svc}",
                           paid_rial, charge)
    return res


# ═══════════════════════════════════════════════════════════════════════════
# ۱) بازتولید حادثه (§۲ سند) — با کد جدید هیچ ثبت رایگانی وجود ندارد
# ═══════════════════════════════════════════════════════════════════════════

def test_scenario1_incident_reproduction_six_full_invoices():
    """کاربر free_credit=0. ۶ ثبت پشت‌سرهم: هر بار فاکتور «کامل» ۱٬۰۰۰٬۰۰۰ ریالی
    صادر می‌شود (نه ۱۰٬۰۰۰ و نه cover) ⇒ ۶ پرداخت و ۶ رزرو؛ مانده در انتها ۰."""
    prepay_rial = pr.get_prepay_amount_rial("lavayeh")
    assert prepay_rial == 1_000_000

    invoices, reservations = [], []
    for i in range(6):
        assert pr.get_free_credit_rial(UID) == 0
        inv_rial, hold = pr.hold_for_invoice(UID, "lavayeh", f"لایحه {i + 1}")
        # ⭐ فاکتور باید کامل باشد — رفع باگ فاکتور ۱۰٬۰۰۰ ریالی (§۳.۲)
        assert inv_rial == prepay_rial, f"فاکتور ثبت {i + 1} کامل نیست: {inv_rial}"
        res = pr.finalize_paid(UID, hold["task_id"], "lavayeh", f"لایحه {i + 1}",
                               prepay_rial, f"ch-incident-{i}")
        pr.mark_queued(UID, res["task_id"])
        invoices.append(inv_rial)
        reservations.append(res)

    assert len(_active_reservations(UID)) == 6
    assert all(r["status"] == "queued" for r in _active_reservations(UID))
    assert pr.get_free_credit_rial(UID) == 0
    # معیار پذیرش §۷: ۶ پرداخت/فاکتور — هیچ ثبت رایگان ساخته نشد
    assert sum(invoices) == 6 * prepay_rial


# ═══════════════════════════════════════════════════════════════════════════
# ۲) cover واقعی (رفع §۳.۳): مانده واقعاً کسر و قفل می‌شود
# ═══════════════════════════════════════════════════════════════════════════

def test_scenario2_real_cover_consumes_credit():
    _give_free_credit(UID, 3_000_000)
    prepay_rial = pr.get_prepay_amount_rial("lavayeh")

    task_ids = []
    for i in range(3):
        res = pr.reserve_from_credit(UID, "lavayeh", f"لایحه {i + 1}")
        assert res is not None, "ماندهٔ کافی بود ولی رزرو نشد (باگ §۳.۳)"
        assert res["reserved_rial"] == prepay_rial
        assert res["credit_used_rial"] == prepay_rial
        task_ids.append(res["task_id"])
        pr.mark_queued(UID, res["task_id"])

    assert pr.get_free_credit_rial(UID) == 0
    assert len(_active_reservations(UID)) == 3
    # ثبت چهارم ⇒ فاکتور (رزرو از مانده ممکن نیست)
    assert pr.reserve_from_credit(UID, "lavayeh", "لایحه ۴") is None
    inv_rial, hold = pr.hold_for_invoice(UID, "lavayeh", "لایحه ۴")
    assert inv_rial == prepay_rial


# ═══════════════════════════════════════════════════════════════════════════
# ۳) کلیک دوبل (رفع §۳.۶/§۴.۴): دو تایید همزمان ⇒ یک job و یک رزرو
# ═══════════════════════════════════════════════════════════════════════════

def test_scenario3_double_click_single_job(monkeypatch):
    import lavayeh_handlers as lh
    from states import Form

    _give_free_credit(UID, 1_000_000)   # دقیقاً یک پیش‌پرداخت

    class _State:
        def __init__(self):
            self.state = Form.lavayeh_confirm
            self.data = {"lavayeh_title": "لایحه", "lavayeh_tracking_code": "t1",
                         "lavayeh_persons": [], "lavayeh_attachments": []}

        async def get_data(self):
            await asyncio.sleep(0)      # اجازهٔ تعویض به کوروتین دیگر
            return dict(self.data)

        async def set_state(self, st):
            await asyncio.sleep(0)
            self.state = st

        async def clear(self):
            self.state = None

        async def update_data(self, **kw):
            self.data.update(kw)

    st = _State()

    class _Msg:
        text = "✅ تایید و شروع ثبت"
        from_user = MagicMock(id=UID)
        answer = AsyncMock()

    bot = MagicMock()
    bot.send_message = AsyncMock()

    # فاکتور پیش‌پرداخت بدون درخواست واقعی به بله — فقط رفتار True
    async def _fake_invoice(bot_, uid, svc, label):
        await asyncio.sleep(0)
        return True
    monkeypatch.setattr(pr, "send_prepay_invoice", _fake_invoice)

    async def _confirm_once():
        # شبیه‌سازی فیلتر روتر aiogram: هندلر فقط در state=confirm اجرا می‌شود
        if st.state != Form.lavayeh_confirm:
            return "rejected-by-state"
        await lh.lavayeh_confirm_handler(_Msg(), st, bot)
        return "handled"

    async def _two_clicks():
        return await asyncio.gather(_confirm_once(), _confirm_once())

    results = asyncio.run(_two_clicks())

    # ⭐ نتیجهٔ مورد نیاز سند (§۷-۳): «فقط یک job و یک رزرو» — حتی اگر هر دو
    # کلیک همزمان وارد هندلر شوند، قفل per-user + رزرو اتمیک مانع دوباره‌کاری
    # است؛ کلیک دومی حداکثر به فاکتور (بدون enqueue) می‌رسد.
    assert runtime_state.job_queue.qsize() == 1
    # کلیک سوم، بعد از پایان دومی: state دیگر confirm نیست → رد می‌شود (§۴.۴)
    async def _third_click():
        return await _confirm_once()
    assert asyncio.run(_third_click()) == "rejected-by-state"
    job = runtime_state.job_queue._queue[0]
    assert job["task_type"] == "LAVAYEH_SUBMIT"
    assert job.get("prepay_task_id")
    assert pr.get_free_credit_rial(UID) == 0
    cover_reservations = [r for r in _active_reservations(UID)
                          if r.get("credit_used_rial") > 0 and r.get("status") == "queued"]
    assert len(cover_reservations) == 1


# ═══════════════════════════════════════════════════════════════════════════
# ۴) پرداخت تکراری (§۴.۴): همان charge_id دوبار ⇒ فقط یک‌بار ثبت
# ═══════════════════════════════════════════════════════════════════════════

def test_scenario4_duplicate_charge_registered_once():
    charge = "ch-dup-1"
    res1 = pr.register_prepaid(UID, 100_000, "lavayeh", "لایحه", charge)
    assert res1.get("reserved_rial") == 1_000_000
    # بازپخش همان پرداخت (مثلاً تایید دوباره رسید کارت‌به‌کارت)
    res2 = pr.register_prepaid(UID, 100_000, "lavayeh", "لایحه", charge)
    # همان رزرو برگشت؛ رزرو جدیدی ساخته نشد
    assert res2.get("task_id") == res1.get("task_id")
    assert len(_active_reservations(UID)) == 1
    assert pr.get_total_exposure_rial(UID) == 1_000_000


# ═══════════════════════════════════════════════════════════════════════════
# ۵) مانده ناقص: فاکتور ۶۰۰٬۰۰۰ + hold ۴۰۰٬۰۰۰ (سند §۷-۵)
# ═══════════════════════════════════════════════════════════════════════════

def test_scenario5_partial_credit_hold_and_release():
    _give_free_credit(UID, 400_000)
    prepay_rial = pr.get_prepay_amount_rial("lavayeh")

    # فاکتور = پیش‌پرداخت − مانده = ۶۰۰٬۰۰۰ و hold ۴۰۰٬۰۰۰
    inv_rial, hold = pr.hold_for_invoice(UID, "lavayeh", "لایحه")
    assert inv_rial == 600_000
    assert hold["credit_used_rial"] == 400_000
    assert hold["status"] == "hold"
    assert pr.get_free_credit_rial(UID) == 0     # سهم مانده قفل شد

    # انصراف از همین فاکتور (§۵.۹) ⇒ سهم ماندهٔ hold به ماندهٔ آزاد برمی‌گردد
    assert pr.release_hold(UID, hold["task_id"]) == 1
    assert pr.get_free_credit_rial(UID) == 400_000
    assert all(r["status"] != "hold" for r in pr._rec(UID)["reservations"])

    # ثبت دوباره با همان مانده: فاکتور ۶۰۰٬۰۰۰ + hold ۴۰۰٬۰۰۰؛
    # پرداخت ⇒ رزرو ۱٬۰۰۰٬۰۰۰ (paid=600k + credit_used=400k)
    inv2_rial, hold2 = pr.hold_for_invoice(UID, "lavayeh", "لایحه")
    assert inv2_rial == 600_000 and hold2["credit_used_rial"] == 400_000
    res = pr.finalize_paid(UID, hold2["task_id"], "lavayeh", "لایحه",
                           600_000, "ch-partial")
    assert res["status"] == "reserved"
    assert res["reserved_rial"] == 1_000_000
    assert res["paid_rial"] == 600_000
    assert res["credit_used_rial"] == 400_000


# ═══════════════════════════════════════════════════════════════════════════
# ۶) پایان کار هم‌زمان چند تسک: هر تسک فقط رزرو خودش (رفع §۳.۴)
# ═══════════════════════════════════════════════════════════════════════════

def test_scenario6_each_task_consumes_only_its_reservation():
    r_lav = _paid_registration(UID, "lavayeh", 1_000_000, "ch-lav")
    r_tn = _paid_registration(UID, "tn", 2_000_000, "ch-tn")
    r_chk = _paid_registration(UID, "check", 2_000_000, "ch-chk")
    pr.mark_queued(UID, r_lav["task_id"])
    pr.mark_queued(UID, r_tn["task_id"])
    pr.mark_queued(UID, r_chk["task_id"])

    # هر فاکتور نهایی فقط رزرو خودش را کم می‌کند — حتی خارج از ترتیب
    adj_tn, info_tn = pr.adjust_final_fee_with_prepay(
        UID, 5_000_000, service_key="TAJDID_NAZAR", task_id=r_tn["task_id"])
    assert info_tn["applied_rial"] == 2_000_000 and adj_tn == 3_000_000

    adj_lav, info_lav = pr.adjust_final_fee_with_prepay(
        UID, 4_000_000, service_key="LAVAYEH", task_id=r_lav["task_id"])
    assert info_lav["applied_rial"] == 1_000_000 and adj_lav == 3_000_000

    adj_chk, info_chk = pr.adjust_final_fee_with_prepay(
        UID, 6_000_000, service_key="CHECK", task_id=r_chk["task_id"])
    assert info_chk["applied_rial"] == 2_000_000 and adj_chk == 4_000_000

    # جمع کسرها = جمع رزروها؛ هیچ دوبار‌شماری نیست
    assert (info_tn["applied_rial"] + info_lav["applied_rial"]
            + info_chk["applied_rial"]) == (r_tn["reserved_rial"]
                                            + r_lav["reserved_rial"]
                                            + r_chk["reserved_rial"])
    assert pr.get_total_exposure_rial(UID) == 0


def test_scenario6b_wrong_service_not_consumed():
    """رزرو tn در فاکتور لایحه کسر نمی‌شود (نگاشت گروه §۴.۳)."""
    r_tn = _paid_registration(UID, "tn", 2_000_000, "ch-tn-only")
    adj, info = pr.adjust_final_fee_with_prepay(UID, 5_000_000, service_key="LAVAYEH")
    assert info is None or info.get("service") != "tn"   # رزرو tn دست‌نخورده
    if info is None:
        assert adj == 5_000_000
    # رزرو tn همچنان فعال است
    active = _active_reservations(UID)
    assert len(active) == 1 and active[0]["service"] == "tn"


# ═══════════════════════════════════════════════════════════════════════════
# ۷) مازاد (§۷-۷): هزینه کمتر از رزرو ⇒ مازاد همان رزرو به صف بازگشت
# ═══════════════════════════════════════════════════════════════════════════

def test_scenario7_surplus_goes_to_refund_queue_once():
    res = _paid_registration(UID, "lavayeh", 1_000_000, "ch-surp")
    adj, info = pr.adjust_final_fee_with_prepay(
        UID, 300_000, service_key="LAVAYEH", task_id=res["task_id"])
    assert adj == 0 and info["applied_rial"] == 300_000
    assert info["leftover_rial"] == 700_000
    # مازاد به صف «بازگشت با تایید مدیر» رفت — فقط یک‌بار
    assert refund_approvals.pending_total_toman(UID) == 70_000
    assert len(refund_approvals.pending()) == 1
    # دوبار‌شمارش نیست: کسر مجدد/رزرو دیگری نیست
    adj2, info2 = pr.adjust_final_fee_with_prepay(UID, 300_000, service_key="LAVAYEH")
    assert info2 is None and adj2 == 300_000
    assert refund_approvals.pending_total_toman(UID) == 70_000


# ═══════════════════════════════════════════════════════════════════════════
# ۸) شکست تسک (§۵.۹): رزرو آزاد و پول به ماندهٔ آزاد برمی‌گردد
# ═══════════════════════════════════════════════════════════════════════════

def test_scenario8_task_failure_releases_reservation():
    _give_free_credit(UID, 300_000)
    res = _paid_registration(UID, "lavayeh", 700_000, "ch-fail")
    assert res["reserved_rial"] == 1_000_000    # 700k پرداختی + 300k از مانده
    assert pr.get_free_credit_rial(UID) == 0

    released = pr.release_reservation(UID, res["task_id"])
    assert released is not None
    # paid (700k) + credit_used (300k) به ماندهٔ آزاد برگشت (شکست خودکار §۵.۹)
    assert pr.get_free_credit_rial(UID) == 1_000_000
    # هیچ «رزرو فعالی» نماند — کل پول به ماندهٔ آزاد برگشته است
    assert all(r.get("status") in ("consumed", "released") for r in pr._rec(UID)["reservations"])
    # آزادسازی دوباره idempotent است
    assert pr.release_reservation(UID, res["task_id"]) is None
    assert pr.get_free_credit_rial(UID) == 1_000_000


# ═══════════════════════════════════════════════════════════════════════════
# ۹) مهاجرت v1→v2 (§۵.۸)
# ═══════════════════════════════════════════════════════════════════════════

def test_scenario9_v1_migration_and_fifo_consume():
    runtime_state.prepaid_registrations[UID] = {
        "amount_toman": 110_000,
        "amount_rial": 1_100_000,
        "prepay_paid_rial": 200_000,
        "service": "check",
        "service_label": "ثبت دادخواست",
        "charge_id": "ch-old",
        "paid_at": datetime.datetime.now(),
        "discount_rial": 0,
    }
    assert pr.migrate_all_to_v2() == 1
    rec = runtime_state.prepaid_registrations[UID]
    assert rec.get("version") == 2
    # prepay_paid → یک رزرو task_id=None (مصرف FIFO)؛ باقی‌مانده → ماندهٔ آزاد
    assert rec.get("free_credit_rial") == 900_000
    assert len(rec["reservations"]) == 1
    res = rec["reservations"][0]
    assert res["task_id"] is None and res["status"] == "reserved"
    assert res["reserved_rial"] == 200_000 and res["paid_rial"] == 200_000
    assert res["charge_id"] == "ch-old"
    # تکرار مهاجرت بی‌اثر است
    assert pr.migrate_all_to_v2() == 0

    # فاکتور نهایی همان سرویس ⇒ FIFO همان رزرو (۲۰۰k) مصرف می‌شود و
    # باقی فاکتور از ماندهٔ آزاد (§۴.۳ گام ۳ — مثل رفتار v1) می‌آید
    adj, info = pr.adjust_final_fee_with_prepay(UID, 500_000, service_key="check")
    assert info is not None
    assert info["prepay_paid_rial"] == 200_000          # رزرو (FIFO)
    assert info["extra_credit_rial"] == 300_000          # از ماندهٔ آزاد
    assert info["applied_rial"] == 500_000 and adj == 0
    assert pr.get_free_credit_rial(UID) == 600_000


def test_scenario9b_manual_record_becomes_free_credit():
    runtime_state.prepaid_registrations[UID] = {
        "amount_rial": 400_000, "amount_toman": 40_000, "manual": True,
    }
    pr.migrate_all_to_v2()
    assert pr.get_free_credit_rial(UID) == 400_000
    assert pr._rec(UID)["reservations"] == []


# ═══════════════════════════════════════════════════════════════════════════
# ۱۰) pay_reconcile (§۵.۷): queued هشدار نمی‌دهد؛ reserved بدون job هشدار می‌دهد
# ═══════════════════════════════════════════════════════════════════════════

def test_scenario10_pay_reconcile_v2(monkeypatch):
    import pay_reconcile

    pay_reconcile._alerted.clear()
    monkeypatch.setattr(pay_reconcile, "_user_has_followup", lambda uid: False)

    class _Bot:
        def __init__(self):
            self.sent = []

        async def send_message(self, chat_id, text, **kw):
            self.sent.append(text)

    # رزرو queued (تسک در صف) — نباید هشدار بدهد
    r1 = _paid_registration(UID, "lavayeh", 1_000_000, "ch-q1")
    pr.mark_queued(UID, r1["task_id"])
    bot = _Bot()
    assert asyncio.run(pay_reconcile.run_once(bot)) == 0

    # رزرو reserved بدون job و قدیمی ⇒ هشدار
    old = datetime.datetime.now() - datetime.timedelta(minutes=30)
    rec = pr._rec(UID)
    rec["reservations"].append({
        "task_id": "rsv-orphan", "service": "tn", "service_label": "تجدیدنظر",
        "reserved_rial": 2_000_000, "paid_rial": 2_000_000, "credit_used_rial": 0,
        "discount_rial": 0, "charge_id": "ch-orphan", "paid_at": old,
        "status": "reserved", "hold_expires_at": None,
    })
    bot = _Bot()
    assert asyncio.run(pay_reconcile.run_once(bot)) == 1
    assert any("ch-orphan" in t for t in bot.sent)
    # تکرار همان پرداخت ⇒ هشدار دوباره نیست (یک‌بار برای هر پرداخت)
    assert asyncio.run(pay_reconcile.run_once(_Bot())) == 0


# ═══════════════════════════════════════════════════════════════════════════
# ۱۱) lavayeh_entry (§۵.۲): کاربرِ دارای تسک در صف از active حذف نمی‌شود
# ═══════════════════════════════════════════════════════════════════════════

def test_scenario11_lavayeh_entry_keeps_active_user_with_queued_job(monkeypatch):
    import lavayeh_handlers as lh
    import pending_jobs

    runtime_state.active_lavayeh_users.add(UID)
    # کاربر تسک در دفتر ماندگار دارد (صف ثبت)
    monkeypatch.setattr(pending_jobs, "user_ids", lambda: {str(UID)})
    import sana_gate as sg
    monkeypatch.setattr(sg, "deferred_by_user", lambda: {})

    class _State:
        async def clear(self):
            await asyncio.sleep(0)

        async def update_data(self, **kw):
            pass

        async def set_state(self, st):
            pass

    msg = MagicMock()
    msg.text = "📝 ثبت لایحه"
    msg.from_user = MagicMock(id=UID)
    msg.answer = AsyncMock()

    asyncio.run(lh.lavayeh_entry(msg, _State()))
    # ⭐ کاربر هنوز active است (تسکش در صف است) — رفع هشدار کاذب §۳.۵
    assert UID in runtime_state.active_lavayeh_users


def test_scenario11b_lavayeh_entry_cleans_stale_active_user(monkeypatch):
    import lavayeh_handlers as lh
    import pending_jobs

    runtime_state.active_lavayeh_users.add(UID)
    # هیچ نشانه‌ای از تسک در جریان نیست → پاکسازی حالت گیرکرده مثل قبل
    monkeypatch.setattr(pending_jobs, "user_ids", lambda: set())
    import sana_gate as sg
    monkeypatch.setattr(sg, "deferred_by_user", lambda: {})
    import user_activity
    monkeypatch.setattr(user_activity, "is_busy", lambda uid: False)

    class _State:
        async def clear(self):
            await asyncio.sleep(0)

        async def update_data(self, **kw):
            pass

        async def set_state(self, st):
            pass

    msg = MagicMock()
    msg.text = "📝 ثبت لایحه"
    msg.from_user = MagicMock(id=UID)
    msg.answer = AsyncMock()

    asyncio.run(lh.lavayeh_entry(msg, _State()))
    assert UID not in runtime_state.active_lavayeh_users


# ═══════════════════════════════════════════════════════════════════════════
# معیارهای پذیرش §۷ — گارد enqueue و اتصال رزرو به job
# ═══════════════════════════════════════════════════════════════════════════

def test_acceptance_no_job_without_reservation():
    """هیچ job (غیر معاف/غیر دسته‌جمعی) بدون رزرو معتبر وارد job_queue نمی‌شود."""
    import lavayeh_handlers as lh

    data = {"lavayeh_title": "لایحه", "lavayeh_tracking_code": "t"}
    bot = MagicMock()
    bot.send_message = AsyncMock()

    ok = asyncio.run(lh._send_lavayeh_task_to_queue(data, UID, "لایحه", bot=bot))
    assert ok is False
    assert runtime_state.job_queue.qsize() == 0


def test_acceptance_job_carries_reservation_and_marks_queued():
    import lavayeh_handlers as lh

    _give_free_credit(UID, 1_000_000)
    res = pr.reserve_from_credit(UID, "lavayeh", "لایحه")
    data = {"lavayeh_title": "لایحه", "lavayeh_tracking_code": "t"}
    bot = MagicMock()
    bot.send_message = AsyncMock()

    ok = asyncio.run(lh._send_lavayeh_task_to_queue(
        data, UID, "لایحه", bot=bot, prepay_task_id=res["task_id"]))
    assert ok is True
    assert runtime_state.job_queue.qsize() == 1
    job = runtime_state.job_queue._queue[0]
    assert job["prepay_task_id"] == res["task_id"]
    # رزرو → queued (pay_reconcile هشدار نمی‌دهد)
    statuses = {r["task_id"]: r["status"] for r in _active_reservations(UID)}
    assert statuses[res["task_id"]] == "queued"


def test_acceptance_exempt_and_bulk_bypass_guard():
    import lavayeh_handlers as lh

    data_bulk = {"lavayeh_title": "لایحه", "_is_bulk": True,
                 "batch_tracking_code": "B1"}
    bot = MagicMock()
    bot.send_message = AsyncMock()

    # ردیف دسته‌جمعی: حساب بچ خودش را دارد (§۶.۴) — بدون رزرو هم عبور می‌کند
    assert asyncio.run(lh._send_lavayeh_task_to_queue(
        data_bulk, UID, "لایحه", bot=bot)) is True
    # کاربر معاف: بدون رزرو هم عبور می‌کند
    data2 = {"lavayeh_title": "لایحه ۲"}
    assert asyncio.run(lh._send_lavayeh_task_to_queue(
        data2, UID, "لایحه ۲", bot=bot, exempt=True)) is True
    assert runtime_state.job_queue.qsize() == 2


def test_acceptance_hold_expires_and_returns_credit():
    """hold منقضی‌شده سهم مانده را برمی‌گرداند (پرداخت‌نشده بماند)."""
    _give_free_credit(UID, 400_000)
    inv_rial, hold = pr.hold_for_invoice(UID, "lavayeh", "لایحه")
    assert inv_rial == 600_000 and pr.get_free_credit_rial(UID) == 0
    # انقضای hold را شبیه‌سازی می‌کنیم
    hold["hold_expires_at"] = datetime.datetime.now() - datetime.timedelta(minutes=1)
    assert pr.sweep_expired_holds(UID) == 1
    assert pr.get_free_credit_rial(UID) == 400_000
    assert all(r["status"] != "hold" for r in pr._rec(UID)["reservations"])
