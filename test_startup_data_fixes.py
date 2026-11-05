"""تست startup_data_fixes — اصلاح دادهٔ §۸ (حادثهٔ ۲۰۲۶-۱۱-۰۴ کاربر ۲۷۲۶۶۰۵۴۹).

بازتولید سناریوی لاگ واقعی:
  • ۸ تسک LAVAYEH_SUBMIT در صف ماندگار (۶ واقعی + ۲ تکراریِ کلیک‌دوبل)
  • رکورد معیوب {amount=1,010,000, prepay_paid=10,000}
  • پرداخت واقعی: ۱٬۰۰۰٬۰۰۰ + ۱۰٬۰۰۰ ریال

پس از اصلاح باید:
  ۱. رکورد = یک پیش‌پرداخت ۱٬۰۰۰٬۰۰۰ ریالی (charge پرداخت اول) + sec8_fixed
  ۲. ۱٬۰۰۰ تومان پرداخت دوم در کیف پول (اعتبار آزاد)
  ۳. ۲ تسک تکراری از صف حذف و ۶ تسک واقعی به‌ترتیب باقی بمانند
  ۴. اولین «پایان کار» فقط ۱٬۰۰۰٬۰۰۰ ریال کسر کند؛ ۵ فاکتور بعدی کامل صادر شود
  ۵. فاکتور پیش‌پرداختِ ثبتِ جدید این کاربر، کامل (۱٬۰۰۰٬۰۰۰ ریالی) باشد — نه ۱۰٬۰۰۰

اجرا: BOT_TOKEN=1:x ADMIN_ID=1 ADMIN_API_SECRET=x python -m pytest test_startup_data_fixes.py -v
"""
import asyncio
import datetime
import os
import uuid

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("ADMIN_API_SECRET", "x")
os.environ.setdefault("BALE_API_BASE", "https://tapi.bale.ai")

import pytest

import runtime_state
import startup_data_fixes as s8
import sana_gate
import prepay_registration
import wallet
import refund_approvals
import persistence

UID = s8.INCIDENT_USER_ID


# ── ایزوله‌سازی فایل‌های وضعیت و فروشگاه‌ها ───────────────────────────────

@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(sana_gate, "STATE_FILE", str(tmp_path / "gate.json"))
    sana_gate._state.update({
        "outage": False, "outage_since": None, "browser_closed": False,
        "deferred": [], "offhours_log": [], "sec8_removed": [],
    })
    # persistence.save_state پیش‌فرضِ خودش در زمان def به STATE_FILE اصلی گره خورده؛
    # مستقیماً جایگزین می‌شود تا فایل واقعی پروژه دست نخورد.
    monkeypatch.setattr(persistence, "save_state", lambda data, filepath=None: None)
    monkeypatch.setattr(persistence, "load_state", lambda filepath=None: {})
    monkeypatch.setattr(wallet, "STORE_FILE", str(tmp_path / "wallet.json"))
    wallet._store = {"users": {}, "offers": {}, "holds": {}, "autopaid": {}}
    monkeypatch.setattr(refund_approvals, "STORE_FILE", str(tmp_path / "refund.json"))
    refund_approvals._store = {"items": {}}
    # ایزوله‌سازی کامل prepaid_registrations (تست‌ها کاربر ۷۷۷ هم می‌سازند)
    _saved_prepaid = dict(runtime_state.prepaid_registrations)
    runtime_state.prepaid_registrations.clear()
    runtime_state.consumed_prepay_for_panel = {}
    s8._report.clear()
    s8._changed = False
    yield
    runtime_state.prepaid_registrations.clear()
    runtime_state.prepaid_registrations.update(_saved_prepaid)


# ── سازنده‌های دادهٔ حادثه ────────────────────────────────────────────────

def _incident_record_state_a():
    """رکورد معیوب همان‌طور که register_prepaid بعد از پرداخت دوم ساخته (۱۲:۴۵)."""
    return {
        "amount_toman": 101_000,
        "amount_rial": 1_010_000,
        "prepay_paid_rial": 10_000,
        "service": "lavayeh",
        "service_label": "لایحه (x)",
        "charge_id": s8.CHARGE_BUGGY_10K,
        "paid_at": datetime.datetime(2026, 11, 4, 12, 45, 4),
        "discount_rial": 0,
    }


def _incident_record_state_b():
    """رکورد پس از یک ری‌استارت: migrate_legacy_credits بخش مانده (۱٬۰۰۰٬۰۰۰) را
    به درخواست بازگشت منتقل و رکورد را به ۱۰٬۰۰۰ ریال تقلیل داده است."""
    rec = _incident_record_state_a()
    rec.update({"amount_toman": 1_000, "amount_rial": 10_000, "prepay_paid_rial": 10_000})
    return rec


def _legacy_refund_item(status="pending"):
    return {
        "id": "r1", "uid": UID, "toman": 100_000,
        "note": "انتقال مانده/بستانکاری قدیمی به کیف پول (مهاجرت یک‌باره)",
        "source": "legacy_migration", "dedupe_key": s8.LEGACY_REFUND_KEY,
        "status": status, "created_at": 1_900_000_000.0, "notified": True,
    }


def _lavayeh_job(user_id=UID, title="لایحه ۱", tracking="111"):
    return {
        "user_id": user_id, "query_type": "لایحه_ثبت", "task_type": "LAVAYEH_SUBMIT",
        "lavayeh_title": title, "lavayeh_tracking_code": tracking,
        "lavayeh_province": "تهران", "lavayeh_row_number": 1,
        "lavayeh_persons": [{"name": "علی"}], "lavayeh_text": "متن لایحه",
        "lavayeh_text_html": "<p>متن لایحه</p>", "lavayeh_attachments": [],
        "tracking_method": "case_number", "lavayeh_archive_number": "",
        "lavayeh_branch_name": "", "lavayeh_branch_code": "",
        "_jid": uuid.uuid4().hex[:12],
    }


def _defer(job, at: datetime.datetime, reason="offhours"):
    return {"job": job, "deferred_at": at.isoformat(), "reason": reason}


# بازهٔ صف حادثه بر اساس لاگ واقعی ۲۰۲۶-۱۱-۰۴ (۱۲:۰۹ تا ۱۵:۴۶)
_T0 = datetime.datetime(2026, 11, 4, 12, 9, 9)


def _incident_deferred_queue():
    """۸ تسک صف حادثه: #1..#8 — #5 تکرارِ #4 و #8 تکرارِ #7 (کلیک دوبل)."""
    jobs = [
        _lavayeh_job(title="لایحه ۱", tracking="111"),   # ۱۲:۰۹ — با پیش‌پرداخت کامل
        _lavayeh_job(title="لایحه ۲", tracking="222"),   # ۱۲:۴۵
        _lavayeh_job(title="لایحه ۳", tracking="333"),   # ۱۴:۳۳
        _lavayeh_job(title="لایحه ۴", tracking="444"),   # ۱۴:۵۹:۳۰
        _lavayeh_job(title="لایحه ۴", tracking="444"),   # ۱۴:۵۹:۳۳ — تکراری #5
        _lavayeh_job(title="لایحه ۵", tracking="555"),   # ۱۵:۳۷
        _lavayeh_job(title="لایحه ۶", tracking="666"),   # ۱۵:۴۶:۰۰
        _lavayeh_job(title="لایحه ۶", tracking="666"),   # ۱۵:۴۶:۰۲ — تکراری #8
    ]
    times = [
        _T0,
        _T0.replace(hour=12, minute=45, second=31),
        _T0.replace(hour=14, minute=33, second=34),
        _T0.replace(hour=14, minute=59, second=30),
        _T0.replace(hour=14, minute=59, second=33),
        _T0.replace(hour=15, minute=37, second=15),
        _T0.replace(hour=15, minute=46, second=0),
        _T0.replace(hour=15, minute=46, second=2),
    ]
    return [_defer(j, t) for j, t in zip(jobs, times)]


# ═════════════════════════════════════════════════════════════════════════
# ۱) اصلاح رکورد — وضعیت‌های مختلف
# ═════════════════════════════════════════════════════════════════════════

def test_state_a_record_fixed_and_idempotent():
    """وضعیت A (بدون ری‌استارت): رکورد ۱٬۰۱۰٬۰۰۰/۱۰٬۰۰۰ → پیش‌پرداخت کامل + کیف پول."""
    runtime_state.prepaid_registrations[UID] = _incident_record_state_a()

    assert s8.apply_prepay_incident_fix() == "fixed"

    # ⭐️ v2: خروجی ساختار رزرو است — یک رزرو ۱٬۰۰۰٬۰۰۰ ریالی برای یک لایحه
    rec = runtime_state.prepaid_registrations[UID]
    assert rec.get("version") == 2 and rec.get("free_credit_rial") == 0
    assert len(rec["reservations"]) == 1
    res = rec["reservations"][0]
    assert res["reserved_rial"] == 1_000_000
    assert res["paid_rial"] == 1_000_000
    assert res["charge_id"] == s8.CHARGE_FULL_PREPAY
    assert res["service"] == "lavayeh"
    assert res["status"] == "reserved"
    assert res["task_id"] is None            # مصرف FIFO در اولین فاکتور پایان کار
    assert rec[s8.SEC8_MARKER] is True
    assert res["paid_at"] == datetime.datetime(2026, 11, 4, 12, 45, 4)  # حفظ زمان پرداخت
    # اعتبار آزاد: ۱٬۰۰۰ تومان در کیف پول
    assert wallet.balance(UID) == 1_000

    # idempotent — اجرای دوم هیچ چیزی تغییر نمی‌دهد
    assert s8.apply_prepay_incident_fix() == "already_fixed"
    assert wallet.balance(UID) == 1_000
    assert prepay_registration.get_total_exposure_rial(UID) == 1_000_000


def test_v2_migrated_incident_state_also_fixed():
    """ترتیب واقعی bot.py: migrate_all_to_v2 قبل از §۸ — رکورد معیوب در لباس v2
    (رزرو ۱۰٬۰۰۰ + ماندهٔ آزاد ۱٬۰۰۰٬۰۰۰) هم شناخته و اصلاح می‌شود."""
    runtime_state.prepaid_registrations[UID] = _incident_record_state_a()
    assert prepay_registration.migrate_all_to_v2() == 1
    rec = runtime_state.prepaid_registrations[UID]
    assert rec.get("version") == 2 and rec.get("free_credit_rial") == 1_000_000

    assert s8.apply_prepay_incident_fix() == "fixed"

    rec = runtime_state.prepaid_registrations[UID]
    assert rec.get("free_credit_rial") == 0
    assert len(rec["reservations"]) == 1
    res = rec["reservations"][0]
    assert res["reserved_rial"] == 1_000_000 and res["paid_rial"] == 1_000_000
    assert res["charge_id"] == s8.CHARGE_FULL_PREPAY
    assert wallet.balance(UID) == 1_000
    # idempotent
    assert s8.apply_prepay_incident_fix() == "already_fixed"


def test_state_b_pending_legacy_refund_cancelled_and_record_rebuilt():
    """وضعیت B (ری‌استارت با درخواست بازگشت در انتظار): لغو درخواست + بازسازی رکورد."""
    runtime_state.prepaid_registrations[UID] = _incident_record_state_b()
    refund_approvals._store["items"]["r1"] = _legacy_refund_item("pending")

    assert s8.apply_prepay_incident_fix() == "fixed"

    assert refund_approvals._store["items"]["r1"]["status"] == "cancelled"
    rec = runtime_state.prepaid_registrations[UID]
    assert rec.get("version") == 2
    assert len(rec["reservations"]) == 1
    assert rec["reservations"][0]["reserved_rial"] == 1_000_000
    assert rec["reservations"][0]["paid_rial"] == 1_000_000
    assert wallet.balance(UID) == 1_000


def test_state_c_approved_legacy_refund_left_untouched():
    """وضعیت C (مدیر قبلاً بازگشت را تأیید کرده): رکورد بازسازی نمی‌شود (بدون دوبار‌شمارش)."""
    runtime_state.prepaid_registrations[UID] = _incident_record_state_b()
    refund_approvals._store["items"]["r1"] = _legacy_refund_item("approved")

    assert s8.apply_prepay_incident_fix() == "legacy_paid_to_wallet"

    # رکورد و کیف پول دست‌نخورده
    rec = runtime_state.prepaid_registrations[UID]
    assert rec.get("amount_rial") == 10_000 and rec.get("prepay_paid_rial") == 10_000
    assert wallet.balance(UID) == 0
    assert refund_approvals._store["items"]["r1"]["status"] == "approved"
    # گزارش فقط یک‌بار برای این وضعیت پایدار ثبت می‌شود
    assert s8.apply_prepay_incident_fix() == "legacy_paid_to_wallet"
    assert len([r for r in s8._report if "تأیید مدیر" in r]) == 1


def test_no_record_reported_only():
    assert s8.apply_prepay_incident_fix() == "no_record"
    assert UID not in runtime_state.prepaid_registrations
    assert any("یافت نشد" in r for r in s8._report)


def test_unknown_record_untouched():
    """رکوردی که اثر انگشت حادثه را ندارد، دست نمی‌خورد (تصمیم با مدیر)."""
    runtime_state.prepaid_registrations[UID] = {
        "amount_rial": 500_000, "prepay_paid_rial": 500_000,
        "service": "tn", "charge_id": "zzz", "paid_at": datetime.datetime.now(),
    }
    assert s8.apply_prepay_incident_fix() == "unknown_state"
    rec = runtime_state.prepaid_registrations[UID]
    assert rec.get("amount_rial") == 500_000 and "sec8_fixed" not in rec
    assert wallet.balance(UID) == 0


# ═════════════════════════════════════════════════════════════════════════
# ۲) حذف تسک‌های تکراری از صف ماندگار
# ═════════════════════════════════════════════════════════════════════════

def test_dedup_removes_two_duplicate_pairs_keeps_order():
    """سناریوی §۸: از ۸ تسک، ۲ تکراری حذف و ۶ واقعی به‌ترتیب باقی می‌مانند."""
    sana_gate._state["deferred"] = _incident_deferred_queue()

    removed = s8.dedup_deferred_queue()

    assert len(removed) == 2
    assert sana_gate.deferred_count() == 6
    # ترتیب ثبت حفظ شده: ۶ لایحهٔ واقعی به‌ترتیب #1..#4،#6،#7
    remaining = [it["job"]["lavayeh_title"] for it in sana_gate._state["deferred"]]
    assert remaining == ["لایحه ۱", "لایحه ۲", "لایحه ۳", "لایحه ۴", "لایحه ۵", "لایحه ۶"]
    # نسخهٔ حذف‌شده‌ها برای بازگردانی دستی نگه داشته شده
    assert len(sana_gate._state["sec8_removed"]) == 2
    assert sana_gate._state["sec8_removed"][0]["job"]["lavayeh_title"] == "لایحه ۴"
    # اجرای دوم: هیچ چیز جدید حذف نمی‌شود
    assert s8.dedup_deferred_queue() == []
    assert sana_gate.deferred_count() == 6


def test_removed_duplicates_survive_restart():
    """نسخهٔ حذف‌شده‌ها و صف باقی‌مانده پس از ری‌استارت (sana_gate.load) حفظ می‌شوند."""
    sana_gate._state["deferred"] = _incident_deferred_queue()
    assert len(s8.dedup_deferred_queue()) == 2

    # شبیه‌سازی ری‌استارت: پاک‌سازی حافظه و بارگذاری مجدد از دیسک
    sana_gate._state.update({"deferred": [], "sec8_removed": [], "offhours_log": []})
    sana_gate.load()

    assert sana_gate.deferred_count() == 6
    assert len(sana_gate._state["sec8_removed"]) == 2
    assert sana_gate._state["sec8_removed"][0]["why"] == "sec8-duplicate"


def test_dedup_far_apart_and_different_content_kept():
    """محتوای متفاوت یا فاصلهٔ زیاد (ثبت واقعی مجدد) حذف نمی‌شود."""
    t = datetime.datetime(2026, 11, 4, 16, 0, 0)
    sana_gate._state["deferred"] = [
        _defer(_lavayeh_job(title="لایحه", tracking="777"), t),
        # همان محتوا ولی ۱۰ دقیقه بعد (ثبت واقعی مجدد، نه کلیک دوبل) → حفظ
        _defer(_lavayeh_job(title="لایحه", tracking="777"), t.replace(minute=10)),
        # محتوای متفاوت چند ثانیه بعد → حفظ
        _defer(_lavayeh_job(title="لایحه دیگر", tracking="888"), t.replace(second=3)),
    ]
    assert s8.dedup_deferred_queue() == []
    assert sana_gate.deferred_count() == 3


def test_dedup_triple_click_removes_two():
    """کلیک سه‌بار: فقط نسخهٔ اول می‌ماند."""
    t = datetime.datetime(2026, 11, 4, 16, 0, 0)
    j = lambda: _lavayeh_job(title="لایحه", tracking="999")
    sana_gate._state["deferred"] = [
        _defer(j(), t), _defer(j(), t.replace(second=2)), _defer(j(), t.replace(second=4)),
    ]
    removed = s8.dedup_deferred_queue()
    assert len(removed) == 2
    assert sana_gate.deferred_count() == 1


# ═════════════════════════════════════════════════════════════════════════
# ۳) معیار پذیرش §۸ — پایان کارِ ۶ لایحه
# ═════════════════════════════════════════════════════════════════════════

def test_section8_acceptance_six_final_invoices():
    """هستهٔ §۸: اولین پایان کار فقط ۱٬۰۰۰٬۰۰۰ ریال کسر می‌کند؛ ۵ فاکتور بعدی کامل."""
    runtime_state.prepaid_registrations[UID] = _incident_record_state_a()
    assert s8.apply_prepay_incident_fix() == "fixed"

    final_fee = 3_000_000  # مثلاً هزینهٔ نهایی هر لایحه
    results = [prepay_registration.adjust_final_fee_with_prepay(UID, final_fee)
               for _ in range(6)]

    # اولین پایان کار: ۱٬۰۰۰٬۰۰۰ ریال کسر شد
    first_adj, first_info = results[0]
    assert first_adj == 2_000_000
    assert first_info["applied_rial"] == 1_000_000
    assert first_info["prepay_paid_rial"] == 1_000_000
    assert first_info["leftover_rial"] == 0

    # ۵ پایان کار بعدی: فاکتور کامل، بدون هیچ کسر پیش‌پرداخت
    for adj, info in results[1:]:
        assert info is None
        assert adj == final_fee

    # ⭐️ v2: رزرو مصرف شد (consumed) — دیگر هیچ کسری باقی نماند؛
    # کیف پول همچنان ۱٬۰۰۰ تومان اعتبار آزاد دارد
    assert prepay_registration.get_total_exposure_rial(UID) == 0
    rec = runtime_state.prepaid_registrations.get(UID)
    assert rec is not None
    assert all(r.get("status") in ("consumed", "released") for r in rec.get("reservations", []))
    assert wallet.balance(UID) == 1_000


def test_new_prepay_invoice_full_after_fix():
    """رفع §۳.۲: پس از اصلاح، فاکتور پیش‌پرداختِ ثبتِ جدیدِ همین کاربر کامل است."""
    runtime_state.prepaid_registrations[UID] = _incident_record_state_a()
    assert s8.apply_prepay_incident_fix() == "fixed"

    # ماندهٔ آزاد صفر است → فاکتور جدید = کل پیش‌پرداخت (نه ۱۰٬۰۰۰ ریال)
    assert prepay_registration.get_free_credit_rial(UID) == 0
    base_rial = prepay_registration.get_prepay_amount_rial("lavayeh")
    invoice = max(base_rial - prepay_registration.get_free_credit_rial(UID),
                  prepay_registration.MIN_INVOICE_AMOUNT_RIAL)
    assert invoice == 1_000_000

    # رکورد دستیِ مدیر (ماندهٔ آزاد واقعی) همچنان از فاکتور کم می‌شود
    runtime_state.prepaid_registrations[777] = {
        "amount_rial": 400_000, "amount_toman": 40_000, "manual": True,
        "paid_at": datetime.datetime.now(),
    }
    assert prepay_registration.get_free_credit_rial(777) == 400_000


def test_pay_reconcile_no_false_alarm_while_deferred():
    """§۳.۵ (حداقلی): کاربرِ دارای تسک در صف ماندگار، «بی‌پیگیری» تلقی نمی‌شود."""
    import pay_reconcile
    runtime_state.prepaid_registrations[UID] = {
        "amount_rial": 1_000_000, "amount_toman": 100_000,
        "prepay_paid_rial": 1_000_000, "service": "lavayeh",
        "service_label": "لایحه", "charge_id": s8.CHARGE_FULL_PREPAY,
        "paid_at": datetime.datetime.now() - datetime.timedelta(minutes=30),
    }
    sana_gate._state["deferred"] = _incident_deferred_queue()
    assert pay_reconcile._user_has_followup(UID) is True


def test_full_startup_path_e2e():
    """مسیر کامل استارت ربات (bot.py main) تا ۶ فاکتور پایان کار — بازتولید §۸.

    توالی واقعی: load → SEC8-FIX → migrate_legacy_credits → sana_gate.load →
    dedup → (شروع ساعت کاری) آزادسازی صف → ۶ پایان کار.
    """
    # ۱) رکورد معیوب همان‌طور که از دیسک بارگذاری می‌شود
    runtime_state.prepaid_registrations[UID] = _incident_record_state_a()

    # ۲) اصلاح §۸ (قبل از مهاجرت قدیمی — مثل bot.py)
    assert s8.apply_prepay_incident_fix() == "fixed"

    # ۳) مهاجرت قدیمی مانده‌ها نباید رکورد اصلاح‌شده را دست بزند
    moved = wallet.migrate_legacy_credits()
    assert moved == 0
    rec = runtime_state.prepaid_registrations[UID]
    assert rec.get("version") == 2 and rec.get("free_credit_rial") == 0
    assert len(rec["reservations"]) == 1
    assert rec["reservations"][0]["reserved_rial"] == 1_000_000
    assert refund_approvals.pending_total_toman(UID) == 0   # درخواست بازگشتی ساخته نشد

    # ۴) صف ۸تایی حادثه پس از sana_gate.load → حذف ۲ تکراری
    sana_gate._state["deferred"] = _incident_deferred_queue()
    assert len(s8.dedup_deferred_queue()) == 2
    assert sana_gate.deferred_count() == 6

    # ۵) شروع ساعت کاری: صف به‌ترتیب آزاد می‌شود و ۶ تسک وارد پردازش می‌شوند
    import asyncio as _aio
    from unittest.mock import AsyncMock, MagicMock

    async def _release():
        bot = MagicMock()
        bot.send_message = AsyncMock()
        return await sana_gate.release(bot)

    released = _aio.run(_release())
    assert released == 6
    assert sana_gate.deferred_count() == 0

    # ۶) پایان کارِ ۶ لایحه: اولی ۱٬۰۰۰٬۰۰۰ کسر؛ ۵ تای بعدی فاکتور کامل
    final_fee = 2_500_000
    adjs, infos = [], []
    for _ in range(6):
        adj, info = prepay_registration.adjust_final_fee_with_prepay(UID, final_fee)
        adjs.append(adj)
        infos.append(info)
    assert adjs == [1_500_000] + [2_500_000] * 5
    assert infos[0] is not None and all(i is None for i in infos[1:])
    assert wallet.balance(UID) == 1_000          # اعتبار آزاد پرداخت دوم حفظ شد
    assert prepay_registration.get_total_exposure_rial(UID) == 0   # رزرو مصرف شد


def test_admin_report_sent_once():
    """گزارش یک‌جا برای مدیر ارسال می‌شود (فقط وقتی خبری باشد)."""

    class _FakeBot:
        def __init__(self):
            self.sent = []

        async def send_message(self, chat_id, text, **kw):
            self.sent.append((chat_id, text))

    runtime_state.prepaid_registrations[UID] = _incident_record_state_a()
    sana_gate._state["deferred"] = _incident_deferred_queue()
    s8.apply_prepay_incident_fix()
    s8.dedup_deferred_queue()

    bot = _FakeBot()
    asyncio.run(s8.report_to_admin(bot))
    assert len(bot.sent) == 1
    chat_id, text = bot.sent[0]
    assert chat_id == 1  # ADMIN_ID تست
    assert "۲۷۲۶۶۰۵۴۹" in text or "272660549" in text
    assert "1,000,000" in text or "۱٬۰۰۰٬۰۰۰" in text
    assert "تکراری" in text

    # بدون تغییر، گزارشی ارسال نمی‌شود
    bot2 = _FakeBot()
    s8._report.clear()
    asyncio.run(s8.report_to_admin(bot2))
    assert bot2.sent == []
