"""
startup_data_fixes.py — اصلاح دادهٔ یک‌بارهٔ حادثهٔ پیش‌پرداخت (§۸ سند «پیش‌پرداخت ثبت / مانده»)
════════════════════════════════════════════════════════════════════════════════════════

حادثهٔ ۲۰۲۶-۱۱-۰۴ (کاربر ۲۷۲۶۶۰۵۴۹ — همان لاگی که سند تحلیل از آن نوشته شده):
  • کاربر در یک روز ۶ لایحهٔ واقعی ثبت کرد؛ ۸ تسک LAVAYEH_SUBMIT وارد صف ماندگار
    خارج از ساعت کاری شد که ۲ تای آن تکراری است (کلیک دوبل روی «تایید» — §۳.۶ سند).
  • پرداخت واقعی: ۱٬۰۰۰٬۰۰۰ ریال (charge=2123137169192148639 — ۵۰۰ هزار تومانی از
    کیف پول + ۵۰۰ هزار تومانی درگاه) و ۱۰٬۰۰۰ ریال (charge=7263473667848893627 —
    فاکتوری که به‌اشتباه ۱۰٬۰۰۰ ریالی صادر شد — §۳.۲ سند).
  • رکورد prepaid_registrations[272660549] به‌جای «یک پیش‌پرداخت کامل»، وضعیت معیوب
    {amount_rial=1,010,000, prepay_paid_rial=10,000} دارد؛ بدون اصلاح، اولین پایان کار
    کل ۱٬۰۱۰٬۰۰۰ ریال را می‌بلعد (§۳.۴ سند) و ۵ لایحهٔ دیگر بدون هیچ کسری می‌مانند.

تصمیم مدیر (§۸ سند + تأیید مالک پروژه، ۲۰۲۶-۱۱-۰۵):
  ۱. رکورد به «یک پیش‌پرداخت ۱٬۰۰۰٬۰۰۰ ریالی برای یک لایحه» تبدیل شود.
  ۲. ۱۰٬۰۰۰ ریالِ پرداخت دوم به‌عنوان اعتبار آزاد به کیف پول کاربر واریز شود.
  ۳. دو تسک تکراری (#5 و #8) قبل از شروع ساعت کاری از صف ماندگار sana_gate حذف
     شوند (خودکار + گزارش به مدیر).
  ۴. ۶ لایحهٔ واقعی در شروع ساعت کاری وارد سامانه می‌شوند (رفتار موجود sana_gate
     دست نمی‌خورد)؛ اولین پایان کار فقط ۱٬۰۰۰٬۰۰۰ ریال کسر می‌کند و ۵ فاکتور نهایی
     بعدی کامل (بدون کسر پیش‌پرداخت) صادر می‌شود.

نحوهٔ اجرا (bot.py — main):
  • apply_prepay_incident_fix() بلافاصله بعد از load_into_runtime_state() و
    «قبل از wallet.migrate_legacy_credits()» صدا زده می‌شود تا رکورد معیوبِ اصلی
    دیده شود، نه نسخهٔ تفکیک‌شدهٔ مهاجرت قدیمی.
  • dedup_deferred_queue() بعد از sana_gate.load() و قبل از راه‌اندازی gate_loop
    (که ابتدای ساعت کاری صف را آزاد می‌کند) اجرا می‌شود.
  • report_to_admin(bot) بعد از ساخته‌شدن bot، نتیجه را یک‌جا به مدیر می‌فرستد.

ایمنی‌ها:
  - کل اصلاح idempotent است: اجرای چندباره = یک‌بار اثر (نشانهٔ sec8_fixed روی
    رکورد، اثر انگشت charge_id پرداخت دوم، و بررسی تراکنش کیف پول با kind=sec8_credit).
  - اگر رکورد در وضعیت شناخته‌شدهٔ حادثه نباشد، هیچ تغییری داده نمی‌شود و فقط
    به مدیر گزارش می‌شود (تصمیم با مدیر).
  - ترتیب عملیات طوری است که کرش بین مراحل، در اجرای بعدی به‌صورت امن تکرار می‌شود
    (اول واریز idempotent کیف پول، بعد لغو درخواست بازگشت، آخر بازسازی رکورد + ذخیره).
  - تسک‌های حذف‌شده از صف حذف فیزیکی نمی‌شوند: نسخهٔ کاملشان در
    sana_gate_state.json (کلید sec8_removed) نگه داشته می‌شود تا در صورت لزوم
    قابل بازگردانی دستی باشد.
  - اگر مهاجرت قدیمی مانده‌ها (migrate_legacy_credits) قبلاً ۱٬۰۰۰٬۰۰۰ ریال را با
    «تأیید مدیر» به کیف پول کاربر منتقل کرده باشد، رکورد بازسازی نمی‌شود تا مبلغ
    دوبار حساب نشود؛ فقط گزارش داده می‌شود.
"""
import datetime
import json
import logging

import runtime_state

logger = logging.getLogger(__name__)

# ── ثابت‌های حادثه (از لاگ واقعی ۲۰۲۶-۱۱-۰۴) ─────────────────────────────
INCIDENT_USER_ID = 272660549
CHARGE_FULL_PREPAY = "2123137169192148639"   # پرداخت واقعی ۱٬۰۰۰٬۰۰۰ ریالی (۱۲:۰۹)
CHARGE_BUGGY_10K = "7263473667848893627"     # پرداخت ۱۰٬۰۰۰ ریالی — فاکتور اشتباه (۱۲:۴۵)
FULL_PREPAY_RIAL = 1_000_000                 # پیش‌پرداخت کامل لایحه (۱۰۰ هزار تومان)
BUGGY_PAY_RIAL = 10_000                      # مبلغ پرداخت دوم (۱ هزار تومان)
BUGGY_PAY_TOMAN = BUGGY_PAY_RIAL // 10
LEGACY_REFUND_KEY = f"legacy-prepaid:{INCIDENT_USER_ID}"   # کلید مهاجرت قدیمی این کاربر
WALLET_TX_KIND = "sec8_credit"               # kind تراکنش کیف پول (برای idempotency)
SEC8_MARKER = "sec8_fixed"                   # نشانهٔ «این رکورد قبلاً اصلاح شده»
SEC8_NOTED = "sec8_reported"                 # نشانهٔ «وضعیت بدون‌تغییر قبلاً گزارش شده»

# پنجرهٔ زمانی تشخیص تکراریِ کلیک‌دوبل: دو تسک با محتوای کاملاً یکسان که چند ثانیه
# فاصله وارد صف شده‌اند (در لاگ: ۲.۶ و ۱.۷ ثانیه). ۶۰ ثانیه حاشیهٔ امن است چون
# ثبت دوبارهٔ واقعی از طریق فرم چند دقیقه طول می‌کشد.
DUPLICATE_WINDOW_SECONDS = 60

# گزارش انباشتهٔ استارت — report_to_admin یک‌جا برای مدیر می‌فرستد
_report: list = []
_changed: bool = False


# ═════════════════════════════════════════════════════════════════════════
# بخش ۱ — اصلاح رکورد پیش‌پرداخت کاربر ۲۷۲۶۶۰۵۴۹
# ═════════════════════════════════════════════════════════════════════════

def _legacy_refund_items() -> list:
    """همهٔ درخواست‌های بازگشت وجهٔ «مهاجرت قدیمی» این کاربر (هر وضعیتی)."""
    try:
        import refund_approvals
        return [v for v in refund_approvals._store.get("items", {}).values()
                if v.get("dedupe_key") == LEGACY_REFUND_KEY]
    except Exception:
        return []


def _wallet_has_sec8_credit() -> bool:
    """آیا اعتبار §۸ قبلاً به کیف پول این کاربر واریز شده؟ (idempotency)"""
    try:
        import wallet
        txs = wallet._store.get("users", {}).get(str(INCIDENT_USER_ID), {}).get("tx", [])
        return any(t.get("kind") == WALLET_TX_KIND for t in txs)
    except Exception:
        return False


def _credit_wallet_10k() -> bool:
    """واریز ۱٬۰۰۰ تومان (۱۰٬۰۰۰ ریال) پرداخت دوم به کیف پول کاربر — یک‌بار."""
    if _wallet_has_sec8_credit():
        return False
    try:
        import wallet
        wallet.credit_nowait(
            INCIDENT_USER_ID, BUGGY_PAY_TOMAN, WALLET_TX_KIND,
            "اعتبار آزاد از پرداخت دوم حادثهٔ ۲۰۲۶-۱۱-۰۴ (فاکتور اشتباه ۱٬۰۰۰ تومانی) — §۸")
        return True
    except Exception as e:
        logger.error(f"[SEC8-FIX] واریز ۱٬۰۰۰ تومان به کیف پول ناموفق: {e}", exc_info=True)
        return False


def _rebuild_record(old_rec: dict) -> dict:
    """بازسازی رکورد به «یک پیش‌پرداخت کامل ۱٬۰۰۰٬۰۰۰ ریالی برای یک لایحه».

    ⭐️ v2 (سند §۴.۲/§۵.۸): خروجی ساختار نسخهٔ ۲ است — یک رزرو reserved با
    task_id=None (مصرف FIFO در اولین فاکتور پایان کارِ لایحه). مبنای رزرو همان
    پرداخت واقعی اول (charge=2123…) است؛ paid_at روز پرداخت (از رکورد قبلی)
    حفظ می‌شود تا سنی که pay_reconcile می‌بیند واقعی بماند.
    """
    paid_at = (old_rec or {}).get("paid_at")
    if not isinstance(paid_at, datetime.datetime):
        # از رزرو مهاجرت‌شدهٔ قدیمی هم paid_at بردار (در صورت وجود)
        _res_list = (old_rec or {}).get("reservations") or []
        paid_at = next((r.get("paid_at") for r in _res_list
                        if isinstance(r, dict) and isinstance(r.get("paid_at"), datetime.datetime)),
                       None) or datetime.datetime.now()
    new_rec = {
        "version": 2,
        "free_credit_rial": 0,
        "reservations": [{
            "task_id": None,
            "service": "lavayeh",
            "service_label": "لایحه (پیش‌پرداخت اصلاحی §۸)",
            "reserved_rial": FULL_PREPAY_RIAL,
            "paid_rial": FULL_PREPAY_RIAL,
            "credit_used_rial": 0,
            "discount_rial": 0,
            "charge_id": CHARGE_FULL_PREPAY,
            "paid_at": paid_at,
            "status": "reserved",
            "hold_expires_at": None,
        }],
        SEC8_MARKER: True,
    }
    runtime_state.prepaid_registrations[INCIDENT_USER_ID] = new_rec
    try:
        import persistence
        persistence.save_runtime_state()
    except Exception as e:
        logger.error(f"[SEC8-FIX] ذخیرهٔ وضعیت پس از اصلاح رکورد ناموفق: {e}", exc_info=True)
    return new_rec


def _v2_incident_state(rec: dict):
    """تشخیص وضعیت حادثه در رکورد مهاجرت‌شدهٔ v2.

    مهاجرت v1→v2 رکورد معیوب {amount=1,010,000, prepay_paid=10,000} را به
    «رزرو ۱۰٬۰۰۰ ریالی (charge فاکتور اشتباه) + ماندهٔ آزاد ۱٬۰۰۰٬۰۰۰ ریال»
    تبدیل می‌کند — همان وضعیت معیوب، در لباس جدید. خروجی:
      ("incident", None) — همین وضعیت حادثه است
      ("already", None)   — رکورد v2 اصلاح‌شدهٔ §۸ است
      ("other", توضیح)   — وضعیت دیگر
    """
    if rec.get(SEC8_MARKER):
        return "already", None
    res_list = [r for r in (rec.get("reservations") or [])
                if isinstance(r, dict) and r.get("status") in ("hold", "reserved", "queued")]
    if (len(res_list) == 1
            and int(res_list[0].get("paid_rial", 0) or 0) == BUGGY_PAY_RIAL
            and str(res_list[0].get("charge_id", "") or "") == CHARGE_BUGGY_10K
            and int(rec.get("free_credit_rial", 0) or 0) == FULL_PREPAY_RIAL):
        return "incident", None
    return "other", (
        f"free={int(rec.get('free_credit_rial', 0) or 0):,} ریال، "
        f"{len(res_list)} رزرو فعال "
        + "; ".join(f"{int(r.get('reserved_rial', 0) or 0):,}/{r.get('charge_id') or '—'}" for r in res_list))


def apply_prepay_incident_fix() -> str:
    """اصلاح یک‌بارهٔ رکورد prepaid_registrations[272660549] (§۸).

    خروجی (کد وضعیت):
      "fixed"                — رکورد معیوب به پیش‌پرداخت کامل تبدیل شد
      "already_fixed"        — قبلاً اصلاح شده؛ کاری لازم نیست
      "legacy_paid_to_wallet"— مهاجرت قدیمی قبلاً با تأیید مدیر مبلغ را به کیف پول
                               برده؛ رکورد دست نمی‌خورد (دوبار‌شمارش نشود)
      "no_record"            — رکوردی نیست (مصرف‌شده توسط فاکتور پایانی یا حذف دستی)
      "unknown_state"        — رکورد در وضعیت شناخته‌شدهٔ حادثه نیست؛ فقط گزارش
    """
    global _changed
    uid = INCIDENT_USER_ID
    rec = runtime_state.prepaid_registrations.get(uid)

    if rec and rec.get(SEC8_MARKER):
        logger.info(f"[SEC8-FIX] رکورد کاربر {uid} قبلاً اصلاح شده است — رد شد.")
        return "already_fixed"

    if not rec:
        _report.append(
            f"⚠️ رکورد پیش‌پرداختی برای کاربر {uid} یافت نشد.\n"
            "   احتمالاً پیش از استقرار این اصلاح، توسط اولین فاکتور پایان کار مصرف شده "
            "(و در آن صورت کل ۱٬۰۱۰٬۰۰۰ ریال کسر شده) یا دستی حذف شده است.\n"
            "   لطفاً /prepaid و فاکتورهای پایانی صادرشدهٔ این کاربر را بررسی کنید.")
        logger.warning(f"[SEC8-FIX] رکوردی برای کاربر {uid} یافت نشد — فقط گزارش.")
        return "no_record"

    charge = str(rec.get("charge_id", "") or "")
    amount = int(rec.get("amount_rial", 0) or 0)
    paid = int(rec.get("prepay_paid_rial", 0) or 0)

    # ⭐️ v2 — رکورد مهاجرت‌شده (مدل رزرو)؟ تشخیص جداگانه دارد.
    if rec.get("version") == 2:
        state, desc = _v2_incident_state(rec)
        if state == "already":
            logger.info(f"[SEC8-FIX] رکورد کاربر {uid} قبلاً اصلاح شده است — رد شد.")
            return "already_fixed"
        if state == "other":
            _report.append(
                f"⚠️ رکورد v2 کاربر {uid} در وضعیت مورد انتظار حادثهٔ ۲۰۲۶-۱۱-۰۴ نیست:\n"
                f"   {desc}\n"
                "   هیچ تغییری داده نشد — در صورت نیاز با /prepaid_set اصلاح دستی کنید.")
            logger.warning(f"[SEC8-FIX] وضعیت v2 ناشناخته برای کاربر {uid}: {desc}")
            return "unknown_state"
        old_state = f"v2: {desc}"
    else:
        # اثر انگشت حادثه (v1): آخرین register_prepaid این کاربر، پرداختِ اشتباه
        # ۱۰٬۰۰۰ ریالی بوده (charge دوم) — وگرنه وضعیت دست‌نخورده می‌ماند.
        if charge != CHARGE_BUGGY_10K or paid != BUGGY_PAY_RIAL:
            _report.append(
                f"⚠️ رکورد کاربر {uid} در وضعیت مورد انتظار حادثهٔ ۲۰۲۶-۱۱-۰۴ نیست:\n"
                f"   amount={amount:,} ریال | prepay_paid={paid:,} ریال | charge={charge or '—'}\n"
                "   هیچ تغییری داده نشد — در صورت نیاز با /prepaid_set اصلاح دستی کنید.")
            logger.warning(f"[SEC8-FIX] وضعیت ناشناخته برای کاربر {uid}: amount={amount}, paid={paid}, charge={charge}")
            return "unknown_state"
        old_state = f"amount={amount:,} | prepay_paid={paid:,} ریال (charge={charge})"

    # اگر مهاجرت قدیمی (wallet.migrate_legacy_credits) مبلغ را قبلاً با «تأیید مدیر»
    # به کیف پول برده، بازسازی رکورد = دوبار دادن پول به کاربر.
    refund_items = _legacy_refund_items()
    if any(it.get("status") == "approved" for it in refund_items):
        if not rec.get(SEC8_NOTED):
            rec[SEC8_NOTED] = True
            try:
                import persistence
                persistence.save_runtime_state()
            except Exception:
                pass
            _report.append(
                f"ℹ️ کاربر {uid}: مهاجرت قدیمی مانده‌ها قبلاً با تأیید مدیر، ۱۰۰٬۰۰۰ تومان "
                "را به کیف پول این کاربر واریز کرده است؛ برای جلوگیری از دوبار‌شمارش، "
                "رکورد بازسازی نشد (۱۰٬۰۰۰ ریالِ باقی‌ماندهٔ رکورد در اولین فاکتور پایان "
                "کار کسر می‌شود و موجودی کیف پول خودکار از فاکتورهای بعدی کم می‌گردد).")
        logger.info(f"[SEC8-FIX] مهاجرت قدیمیِ تأییدشده برای کاربر {uid} یافت شد — رکورد دست نخورد.")
        return "legacy_paid_to_wallet"

    old_state = f"amount={amount:,} | prepay_paid={paid:,} ریال (charge={charge})"

    # ۱) واریز idempotentِ ۱٬۰۰۰ تومان پرداخت دوم به کیف پول (اعتبار آزاد)
    credited = _credit_wallet_10k()

    # ۲) لغو درخواست بازگشتِ در انتظارِ مهاجرت قدیمی (اگر ری‌استارت قبلی ساخته باشد)
    cancelled = 0
    try:
        import refund_approvals
        cancelled = refund_approvals.cancel_pending(LEGACY_REFUND_KEY)
    except Exception as e:
        logger.warning(f"[SEC8-FIX] لغو درخواست بازگشت قدیمی ناموفق: {e}")

    # ۳) بازسازی رکورد: فقط یک پیش‌پرداخت کامل ۱٬۰۰۰٬۰۰۰ ریالی برای «یک» لایحه
    new_rec = _rebuild_record(rec)

    _changed = True
    _report.append(
        f"✅ رکورد پیش‌پرداخت کاربر {uid} (§۸) اصلاح شد:\n"
        f"   وضعیت معیوب: {old_state}\n"
        f"   وضعیت جدید (v2): یک رزرو ۱٬۰۰۰٬۰۰۰ ریالی برای یک لایحه "
        f"(charge={CHARGE_FULL_PREPAY}, قابل کسر فقط در اولین فاکتور پایان کار)\n"
        f"   {'👛 ۱٬۰۰۰ تومان پرداخت دوم به‌عنوان اعتبار آزاد به کیف پول کاربر واریز شد.' if credited else '👛 اعتبار ۱٬۰۰۰ تومانی قبلاً واریز شده بود (بدون واریز مجدد).'}"
        + (f"\n   🔄 درخواست بازگشتِ «مهاجرت قدیمی» (۱۰۰٬۰۰۰ تومان) لغو شد — مبلغ در همین رکورد پیش‌پرداخت حفظ شد."
           if cancelled else ""))
    logger.info(
        f"[SEC8-FIX] رکورد کاربر {uid} اصلاح شد: ({old_state}) → "
        f"پیش‌پرداخت ۱٬۰۰۰٬۰۰۰ ریالی واحد (charge={CHARGE_FULL_PREPAY}); "
        f"کیف پول +{BUGGY_PAY_TOMAN:,} تومان={'انجام شد' if credited else 'قبلاً انجام شده'}; "
        f"لغو بازگشت قدیمی={cancelled}")
    return "fixed"


# ═════════════════════════════════════════════════════════════════════════
# بخش ۲ — حذف تسک‌های تکراری (کلیک دوبل) از صف ماندگار sana_gate
# ═════════════════════════════════════════════════════════════════════════

# کلیدهای زودگذرِ job که برای مقایسهٔ محتوا نادیده گرفته می‌شوند
_VOLATILE_JOB_KEYS = {"_jid", "admin_forced", "_auto_retries"}


def _job_fingerprint(job: dict) -> str:
    """اثر انگشت محتوایی تسک — بدون شناسه‌های زودگذر. دو کلیک دوبل دقیقاً همین
    مقدار یکسان را می‌سازند (هر دو از همان دادهٔ FSM ساخته می‌شوند)."""
    j = {k: v for k, v in (job or {}).items() if k not in _VOLATILE_JOB_KEYS}
    return json.dumps(j, sort_keys=True, ensure_ascii=False, default=str)


def _deferred_ts(item: dict):
    try:
        return datetime.datetime.fromisoformat(str(item.get("deferred_at")))
    except Exception:
        return None


def dedup_deferred_queue() -> list:
    """حذف جفت‌های تکراریِ صف ماندگار خارج از ساعت کاری (§۸ — تسک‌های #5 و #8).

    معیار «تکراری»: همان کاربر + همان نوع تسک + محتوای کاملاً یکسان + فاصلهٔ
    ورود به صف حداکثر DUPLICATE_WINDOW_SECONDS ثانیه (نشانهٔ کلیک دوبل).
    از هر جفت، نسخهٔ دومی (تکراری) حذف می‌شود؛ نسخهٔ کامل در
    sana_gate_state.json → sec8_removed نگه داشته می‌شود.

    خروجی: فهرست آیتم‌های حذف‌شده (برای گزارش).
    """
    import sana_gate
    global _changed
    items = sana_gate._state.get("deferred") or []
    if not items:
        return []

    kept, removed = [], []
    for it in items:
        job = it.get("job") or {}
        fp, ts = _job_fingerprint(job), _deferred_ts(it)
        is_dup = False
        if ts is not None and job.get("user_id") is not None:
            for prev in kept:
                pjob = prev.get("job") or {}
                pts = _deferred_ts(prev)
                if (pts is not None
                        and str(pjob.get("user_id")) == str(job.get("user_id"))
                        and _job_fingerprint(pjob) == fp
                        and abs((ts - pts).total_seconds()) <= DUPLICATE_WINDOW_SECONDS):
                    is_dup = True
                    break
        (removed if is_dup else kept).append(it)

    if removed:
        sana_gate._state["deferred"] = kept
        stash = sana_gate._state.setdefault("sec8_removed", [])
        for it in removed:
            jid = (it.get("job") or {}).get("_jid")
            if jid:
                sana_gate.log_job_status(jid, "cancelled")
            stash.append({
                "job": it.get("job") or {},
                "deferred_at": it.get("deferred_at"),
                "reason": it.get("reason"),
                "removed_at": datetime.datetime.now().isoformat(timespec="seconds"),
                "why": "sec8-duplicate",
            })
        stash[:] = stash[-200:]     # سقف رشد
        sana_gate._save()

        _changed = True
        lines = [f"🧹 {len(removed)} تسک تکراری (کلیک دوبل) از صف خارج از ساعت کاری حذف شد:"]
        for it in removed:
            job = it.get("job") or {}
            lines.append(
                f"   • کاربر {job.get('user_id')} — {job.get('task_type') or job.get('query_type')} "
                f"— {it.get('deferred_at', '')[:19]} (jid={job.get('_jid', '—')})")
        lines.append("   نسخهٔ کامل حذف‌شده‌ها در sana_gate_state.json (کلید sec8_removed) نگه داشته شده است.")
        _report.append("\n".join(lines))
        logger.warning(
            f"[SEC8-FIX] {len(removed)} تسک تکراری از صف ماندگار حذف شد "
            f"(باقی‌مانده: {len(kept)}): "
            + ", ".join(f"uid={ (it.get('job') or {}).get('user_id') }/jid={(it.get('job') or {}).get('_jid')}" for it in removed))
    return removed


# ═════════════════════════════════════════════════════════════════════════
# بخش ۳ — گزارش یک‌جای مدیر
# ═════════════════════════════════════════════════════════════════════════

async def report_to_admin(bot) -> None:
    """ارسال گزارش اصلاحات استارت به مدیر — فقط وقتی خبری باشد."""
    if not _report:
        return
    from config import ADMIN_ID
    text = (
        "🛠 [SEC8-FIX] اصلاح دادهٔ حادثهٔ پیش‌پرداخت ۲۰۲۶-۱۱-۰۴ (§۸)\n\n"
        + "\n\n".join(_report)
        + "\n\nℹ️ رفتار مورد انتظار از این پس برای کاربر ۲۷۲۶۶۰۵۴۹:\n"
          "• ۶ لایحهٔ واقعی در شروع ساعت کاری به‌ترتیب وارد سامانه می‌شوند.\n"
          "• اولین پایان کار: ۱٬۰۰۰٬۰۰۰ ریال پیش‌پرداخت کسر و فاکتور مابقی صادر می‌شود.\n"
          "• ۵ فاکتور پایان کار بعدی: کامل و بدون کسر پیش‌پرداخت.\n"
          "• ۱٬۰۰۰ تومان اعتبار آزاد در کیف پول کاربر است."
    )
    try:
        await bot.send_message(ADMIN_ID, text)
    except Exception as e:
        logger.warning(f"[SEC8-FIX] ارسال گزارش به مدیر ناموفق: {e}")
