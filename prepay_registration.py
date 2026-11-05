"""
⭐ سکشن جدید کارفرما (۱۴۰۵/۰۶) — «پیش‌پرداخت ثبت»

برای تمام بخش‌های ربات **به‌جز استعلامات**، بلافاصله پس از «تایید اطلاعات»:
  ۱. فاکتور و درگاه پرداخت (کیف پول بله) برای کاربر ارسال می‌شود
     همراه پیام: «این مبلغ پیش پرداخت می باشد لطفا پرداخت تا موارد شما
     شروع به ثبت گردد. باتشکر»
  ۲. پس از تایید خودکار پرداخت (successful_payment بله)، ثبت در سامانه
     (ارسال تسک به صف پردازش) آغاز می‌شود.
  ۳. در پایان کار، هزینه مثل همیشه محاسبه می‌شود؛ مبلغ کل اعلام می‌گردد،
     پیش‌پرداخت از آن کسر می‌شود و فاکتور «مابقی» برای کاربر ارسال می‌شود.

تعرفه (تومان) — تأیید کارفرما (۱۴۰۵/۰۸):
  - لایحه و اظهارنامه: ۱۰۰,۰۰۰ تومان (۱,۰۰۰,۰۰۰ ریال)
  - سایر موارد (ثبت دادخواست، دعاوی اعتراضی، اعلام وکالت و ...): ۲۰۰,۰۰۰ تومان

  ⚠️ تعرفه‌های قدیمی (۱۰۰/۲۰۰ تومان و سپس ۱,۰۰۰/۲,۰۰۰ تومان) منسوخ شده‌اند؛
  مقادیر معتبر در config.py (PREPAY_*) و پیش‌فرض پنل (bot-settings.ts)
  نگه‌داری می‌شوند و باید همیشه با هم هماهنگ باشند.
  تابع get_prepay_amount_toman به‌طور خودکار حداقلِ مجاز را اعمال
  می‌کند (MIN_INVOICE_AMOUNT_RIAL) تا فاکتور، پیام‌های کاربر/مدیر و
  کسرِ پایان کار همیشه روی یک عدد بمانند و خطای 400 برگردد نکند.

⭐️ نسخهٔ ۲ (سند «پیش‌پرداخت ثبت / مانده» — ۱۴۰۵/۱۱، §۴ و §۵.۱):
  هر ثبت = یک رزرو جداگانه. هیچ تسکی بدون رزرو معتبر وارد صف نمی‌شود
  (مگر کاربر معاف باشد یا ردیف دسته‌جمعی باشد). رزرو فقط یک بار مصرف
  می‌شود و فقط توسط همان تسک (task_id یکتا در job و رزرو).
  ساختار رکورد (runtime_state.prepaid_registrations[user_id]):
      {
        "version": 2,
        "free_credit_rial": int,          # ماندهٔ آزاد (دستی مدیر / بازگشتی‌ها)
        "reservations": [ {task_id, service, service_label, reserved_rial,
                           paid_rial, credit_used_rial, discount_rial,
                           charge_id, paid_at, status, hold_expires_at}, ... ],
      }
  وضعیت رزرو: hold → reserved → queued → consumed | released
  (hold: فاکتور صادر شده و بخشی از مانده نگه داشته شده؛ released: لغو/انقضا
  ⇒ سهم مانده به free_credit برگشته).

نکته معماری: هندلر successful_payment در aiogram با روتر مادر
(global_successful_payment_handler در handlers.py) مسیریابی می‌شود؛ هندلرهای decorated روی روترهای فرعی هرگز فراخوانی نمی‌شوند (رفتار
اثبات‌شدهٔ aiogram 3.x: هندلرهای خودِ روتر مادر زودتر از sub-routerها
بررسی می‌شوند). بنابراین هندلر سراسری، توابع همین ماژول و هندلرهای
پرداخت هر بخش را مستقیم فراخوانی می‌کند.
"""

import asyncio
import datetime
import logging
import secrets

import aiohttp
import json as _json

import runtime_state
from config import (
    BALE_WALLET_TOKEN, BOT_TOKEN, BALE_API_BASE, ADMIN_ID, BALE_SSL_CONTEXT,
    PREPAY_LAYEHE_EIZARNAMEH_TOMAN, PREPAY_OTHER_SERVICES_TOMAN,
)

# سرویس‌های مشمول تعرفهٔ لایحه/اظهارنامه (۱۰۰,۰۰۰ تومان)
_LAYEHE_EIZAR_SERVICES = {"lavayeh", "ezhharnameh"}

# ═══ حداقلِ مبلغ مجاز فاکتور در API بله/تلگرام (۱۰,۰۰۰ ریال) ═══
# خطای مرجع (لاگ کارفرما ۱۴۰۵/۰۶/۲۵):
#   "Bad Request: prices: total price must be at least 10000."
MIN_INVOICE_AMOUNT_RIAL = 10_000

# کلید payload فاکتور — برای تشخیص قطعی نوع پرداخت در هندلر سراسری
PREPAY_INVOICE_TYPE = "reg_prepay"

# تخفیف اختصاصیِ کم‌شده از آخرین فاکتور پیش‌پرداخت هر کاربر (ریال) —
# register_prepaid آن را برمی‌دارد و جزو پیش‌پرداخت ثبت می‌کند
_pending_discounts: dict = {}


# ═══════════════════════════════════════════════════════════════════════════
# ⭐️ نسخهٔ ۲ — مدل رزرو (سند §۴.۲ تا §۴.۴)
# ═══════════════════════════════════════════════════════════════════════════

RECORD_VERSION = 2
HOLD_EXPIRE_MINUTES = 30          # مهلت نگه‌داشتن سهم مانده برای فاکتور پرداخت‌نشده
MAX_PROCESSED_CHARGES = 5000      # سقف مجموعهٔ charge_id های پردازش‌شده (FIFO)

# وضعیت‌های رزرو
ST_HOLD = "hold"                  # فاکتور صادر شده؛ سهم مانده نگه داشته شده
ST_RESERVED = "reserved"          # پرداخت/رزرو کامل؛ هنوز job ساخته نشده
ST_QUEUED = "queued"              # job وارد صف ثبت شد
ST_CONSUMED = "consumed"          # در فاکتور نهایی مصرف شد
ST_CONSUMED_MANUAL = "consumed_manual"   # مصرف دستی (مثلاً cost_error دعاوی اعتراضی)
ST_RELEASED = "released"          # لغو/انقضا/شکست ⇒ سهم مانده برگشت

_ACTIVE_STATUSES = (ST_HOLD, ST_RESERVED, ST_QUEUED)

# نگاشت service_type نهایی فاکتور → گروه رزرو (سند §۴.۳)
_SERVICE_GROUPS = {
    "LAVAYEH": ("lavayeh", "ealam"),
    "EALAM_VAKALAHT": ("lavayeh", "ealam"),
    "lavayeh": ("lavayeh", "ealam"),
    "ealam": ("lavayeh", "ealam"),
    "EZHHARNAMEH": ("ezhharnameh",),
    "ezhharnameh": ("ezhharnameh",),
    "CHECK": ("check",),
    "check": ("check",),
    "TAJDID_NAZAR": ("tn",),
    "tn": ("tn",),
}

# قفل per-user — کل توالی «cover/hold → ساخت job → enqueue» زیر این قفل (سند §۴.۴)
_locks: dict = {}


def user_lock(user_id: int) -> asyncio.Lock:
    """قفل اتمیک per-user برای توالی‌های چندمرحله‌ای (confirm → enqueue)."""
    lock = _locks.get(int(user_id))
    if lock is None:
        lock = asyncio.Lock()
        _locks[int(user_id)] = lock
    return lock


def _persist():
    """ذخیرهٔ وضعیت پس از هر تغییر پولی (سند §۴.۳)."""
    try:
        import persistence
        persistence.save_runtime_state()
    except Exception:
        pass   # state_persister هر ۶۰ ثانیه ذخیره می‌کند؛ خطا اینجا مهلک نیست


def _group_of(service_key) -> tuple:
    """گروه رزرو برای service_key/استثنا None (بدون فیلتر گروه)."""
    if not service_key:
        return ()
    return _SERVICE_GROUPS.get(str(service_key), (str(service_key),))


# ── دسترسی به رکورد v2 + مهاجرت تنبل v1→v2 (سند §۵.۸) ───────────────────

def _migrate_v1_record(rec: dict) -> dict:
    """تبدیل رکورد قدیمی (v1) به ساختار نسخهٔ ۲.

    قواعد (سند §۵.۸):
      - prepay_paid_rial > 0 (رکورد غیردستی) ⇒ یک رزرو reserved با
        task_id=None (مصرف FIFO)، reserved=paid، service از رکورد.
      - باقی‌مانده (amount − prepay_paid) ⇒ free_credit_rial.
      - رکورد دستی مدیر (/prepaid_set قدیمی، بدون prepay_paid_rial) ⇒
        تماماً free_credit_rial.
      - نشانگرهای اصلاح §۸ (sec8_fixed/…) حفظ می‌شوند.
    """
    now = datetime.datetime.now()
    paid, credit = _split_record_v1(rec)
    new_rec = {
        "version": RECORD_VERSION,
        "free_credit_rial": credit,
        "reservations": [],
    }
    if paid > 0:
        new_rec["reservations"].append({
            "task_id": None,
            "service": str(rec.get("service", "") or ""),
            "service_label": str(rec.get("service_label", "") or ""),
            "reserved_rial": paid,
            "paid_rial": paid,
            "credit_used_rial": 0,
            "discount_rial": int(rec.get("discount_rial", 0) or 0),
            "charge_id": str(rec.get("charge_id", "") or ""),
            "paid_at": rec.get("paid_at") if isinstance(rec.get("paid_at"), datetime.datetime) else now,
            "status": ST_RESERVED,
            "hold_expires_at": None,
        })
    # حفظ نشانگرهای اصلاح §۸ و کلیدهای اطلاعاتی
    for marker in ("sec8_fixed", "sec8_reported"):
        if rec.get(marker):
            new_rec[marker] = True
    return new_rec


def _rec(user_id: int, create: bool = False) -> dict | None:
    """رکورد v2 کاربر — در صورت لزوم مهاجرت تنبل v1→v2 انجام می‌شود."""
    uid = int(user_id)
    rec = runtime_state.prepaid_registrations.get(uid)
    if rec is None:
        if not create:
            return None
        rec = {"version": RECORD_VERSION, "free_credit_rial": 0, "reservations": []}
        runtime_state.prepaid_registrations[uid] = rec
        return rec
    if not isinstance(rec, dict) or rec.get("version") != RECORD_VERSION:
        rec = _migrate_v1_record(rec if isinstance(rec, dict) else {})
        runtime_state.prepaid_registrations[uid] = rec
    rec.setdefault("reservations", [])
    rec.setdefault("free_credit_rial", 0)
    return rec


def migrate_all_to_v2() -> int:
    """مهاجرت همهٔ رکوردهای v1 → v2 (اجرا در شروع ربات، قبل از اصلاح §۸
    و wallet.migrate_legacy_credits). خروجی: تعداد رکوردهای تبدیل‌شده.
    idempotent است — رکوردهای v2 دست نمی‌خورند."""
    n = 0
    for uid in list(runtime_state.prepaid_registrations.keys()):
        try:
            rec = runtime_state.prepaid_registrations.get(uid)
            if rec is None:
                continue
            if isinstance(rec, dict) and rec.get("version") == RECORD_VERSION:
                continue
            runtime_state.prepaid_registrations[uid] = _migrate_v1_record(rec)
            n += 1
        except Exception as e:
            logging.warning(f"[REG-PREPAY] مهاجرت v2 رکورد کاربر {uid} ناموفق: {e}")
    if n:
        logging.info(f"[REG-PREPAY] {n} رکورد قدیمی پیش‌پرداخت به ساختار نسخهٔ ۲ تبدیل شد")
        _persist()
    return n


# ── نگهداری مجموعهٔ charge_id های پردازش‌شده (ایدمپوتنسی پرداخت — سند §۴.۴) ──

def charge_processed(charge_id: str) -> bool:
    """آیا این پرداخت (charge_id) قبلاً ثبت/پردازش شده؟ (جلوی ثبت دوباره)"""
    if not charge_id:
        return False
    seen = getattr(runtime_state, "processed_charge_ids", None)
    if not isinstance(seen, set):
        return False
    return str(charge_id) in seen


def mark_charge_processed(charge_id: str) -> None:
    """ثبت charge_id به‌عنوان پردازش‌شده (ماندگار از طریق persistence)."""
    if not charge_id:
        return
    seen = getattr(runtime_state, "processed_charge_ids", None)
    if not isinstance(seen, set):
        seen = set()
        runtime_state.processed_charge_ids = seen
    seen.add(str(charge_id))
    if len(seen) > MAX_PROCESSED_CHARGES:   # سقف رشد — قدیمی‌ها حذف می‌شوند
        for c in list(seen)[:len(seen) - MAX_PROCESSED_CHARGES]:
            seen.discard(c)
    _persist()


# ── انقضای hold ها (سهم ماندهٔ نگه‌داشته‌شده برای فاکتور پرداخت‌نشده) ──────

def sweep_expired_holds(user_id: int | None = None) -> int:
    """بستن hold های منقضی: سهم مانده (credit_used) به free_credit برمی‌گردد.

    اگر user_id بدهید فقط همان کاربر جارو می‌شود؛ وگرنه همهٔ کاربران.
    خروجی: تعداد hold های بسته‌شده."""
    now = datetime.datetime.now()
    uids = [int(user_id)] if user_id is not None else list(runtime_state.prepaid_registrations.keys())
    closed = 0
    for uid in uids:
        rec = _rec(uid)
        if not rec:
            continue
        for r in rec.get("reservations", []):
            if r.get("status") != ST_HOLD:
                continue
            exp = r.get("hold_expires_at")
            if isinstance(exp, datetime.datetime) and now >= exp:
                r["status"] = ST_RELEASED
                r["released_at"] = now
                back = int(r.get("credit_used_rial", 0) or 0)
                if back > 0:
                    rec["free_credit_rial"] = int(rec.get("free_credit_rial", 0) or 0) + back
                closed += 1
        if closed:
            _persist()
    return closed


def _active_reservations(rec: dict) -> list:
    return [r for r in (rec or {}).get("reservations", [])
            if r.get("status") in _ACTIVE_STATUSES]


# ── توابع خواندن (سند §۵.۱.۱) ─────────────────────────────────────────────

def get_free_credit_rial(user_id: int) -> int:
    """ماندهٔ آزاد/بستانکاری کاربر (ریال) — فقط بخش قابل مصرف برای ثبت جدید.

    ⭐ رفع باگ فاکتور ۱۰٬۰۰۰ ریالی (§۳.۲ سند): پیش‌پرداختِ پرونده‌های در
    جریان داخل «رزرو»های همان پرونده‌هاست و از فاکتور ثبت جدید کم نمی‌شود.
    """
    rec = _rec(user_id)
    if not rec:
        return 0
    sweep_expired_holds(user_id)
    return max(0, int(rec.get("free_credit_rial", 0) or 0))


def get_total_exposure_rial(user_id: int) -> int:
    """جمع ماندهٔ آزاد + رزروهای فعال — برای نمایش به کاربر/مدیر."""
    rec = _rec(user_id)
    if not rec:
        return 0
    sweep_expired_holds(user_id)
    reserved = sum(int(r.get("reserved_rial", 0) or 0) for r in _active_reservations(rec))
    return max(0, int(rec.get("free_credit_rial", 0) or 0)) + reserved


def get_credit_rial(user_id: int) -> int:
    """(سازگاری قدیمی) کل مبلغ قابل کسر کاربر = ماندهٔ آزاد + رزروهای فعال."""
    return get_total_exposure_rial(user_id)


def _split_record_v1(rec: dict):
    """(داخلی/سازگاری) تفکیک رکورد قدیمی v1 به (prepay_paid, credit)."""
    if not rec:
        return 0, 0
    amount = max(0, int(rec.get("amount_rial", 0) or 0))
    if "prepay_paid_rial" in rec:
        paid = int(rec.get("prepay_paid_rial", 0) or 0)
    else:
        paid = 0 if rec.get("manual") else amount
    paid = max(0, min(paid, amount))
    return paid, amount - paid


def _split_record(rec: dict):
    """(سازگاری قدیمی) — روی رکورد v2: (جمع پرداخت‌شدهٔ رزروهای فعال، ماندهٔ آزاد)."""
    if not isinstance(rec, dict):
        return 0, 0
    if rec.get("version") == RECORD_VERSION:
        active = [r for r in rec.get("reservations", []) if r.get("status") in _ACTIVE_STATUSES]
        return (sum(int(r.get("paid_rial", 0) or 0) for r in active),
                max(0, int(rec.get("free_credit_rial", 0) or 0)))
    return _split_record_v1(rec)


# ── عملیات رزرو (سند §۵.۱.۳ و §۴.۳) ──────────────────────────────────────

def reserve_from_credit(user_id: int, service_key: str, service_label: str = "") -> dict | None:
    """پوشش کامل پیش‌پرداخت از ماندهٔ آزاد — رزرو اتمیک (کسر واقعی).

    خروجی: دیکشنری رزرو (status=reserved) یا None اگر مانده کافی نبود.
    ⭐️ رفع باگ اصلی §۳.۳: قبلاً رکورد «دست‌نخورده» می‌ماند و هر تعداد ثبت
    پشت‌سرهم همان مانده را می‌دیدند؛ حالا مانده واقعاً کسر و در رزرو قفل
    می‌شود و فقط در فاکتور نهایی همین ثبت مصرف خواهد شد."""
    uid = int(user_id)
    rec = _rec(uid, create=True)
    sweep_expired_holds(uid)
    prepay_rial = get_prepay_amount_rial(service_key)
    if int(rec.get("free_credit_rial", 0) or 0) < prepay_rial:
        return None
    rec["free_credit_rial"] = int(rec["free_credit_rial"]) - prepay_rial
    res = {
        "task_id": secrets.token_hex(6),
        "service": str(service_key),
        "service_label": str(service_label or service_key),
        "reserved_rial": prepay_rial,
        "paid_rial": 0,
        "credit_used_rial": prepay_rial,
        "discount_rial": 0,
        "charge_id": "",
        "paid_at": datetime.datetime.now(),
        "status": ST_RESERVED,
        "hold_expires_at": None,
    }
    rec["reservations"].append(res)
    _persist()
    return res


def hold_for_invoice(user_id: int, service_key: str, service_label: str = "",
                     discount_rial: int = 0) -> tuple:
    """ساخت hold برای فاکتور پیش‌پرداخت (سند §۴.۳ hold_for_invoice).

    سهم ماندهٔ آزاد (تا سقف پیش‌پرداخت) همین‌جا از free_credit کسر و در
    hold نگه داشته می‌شود؛ مبلغ فاکتور = پیش‌پرداخت − مانده − تخفیف
    (حداقل MIN_INVOICE_AMOUNT_RIAL). خروجی: (مبلغ فاکتور ریال، رزرو hold).
    اگر کاربر نپردازد، hold بعد از HOLD_EXPIRE_MINUTES منقضی و سهم مانده
    برمی‌گردد (sweep_expired_holds)."""
    uid = int(user_id)
    rec = _rec(uid, create=True)
    sweep_expired_holds(uid)
    base_rial = get_prepay_amount_rial(service_key)
    credit_avail = min(max(0, int(rec.get("free_credit_rial", 0) or 0)), base_rial)
    discount = max(0, int(discount_rial or 0))
    invoice_rial = max(base_rial - credit_avail - discount, MIN_INVOICE_AMOUNT_RIAL)
    invoice_rial = (invoice_rial // 10) * 10
    # سهم ماندهٔ واقعاً نگه‌داشته‌شده = پیش‌پرداخت − تخفیف − مبلغ فاکتور
    credit_used = max(0, min(credit_avail, base_rial - discount - invoice_rial))
    if credit_used > 0:
        rec["free_credit_rial"] = int(rec["free_credit_rial"]) - credit_used
    res = {
        "task_id": secrets.token_hex(6),
        "service": str(service_key),
        "service_label": str(service_label or service_key),
        "reserved_rial": base_rial,
        "paid_rial": 0,
        "credit_used_rial": credit_used,
        "discount_rial": discount,
        "charge_id": "",
        "paid_at": datetime.datetime.now(),
        "status": ST_HOLD,
        "hold_expires_at": datetime.datetime.now() + datetime.timedelta(minutes=HOLD_EXPIRE_MINUTES),
    }
    rec["reservations"].append(res)
    _persist()
    return invoice_rial, res


def finalize_paid(user_id: int, task_id: str | None, service_key: str,
                  service_label: str, paid_rial: int, charge_id: str = "",
                  discount_rial: int = 0) -> dict:
    """پس از successful_payment: hold → reserved با مبلغ پرداخت‌شده (سند §۴.۳).

    اگر hold متناظر (task_id از payload فاکتور) نبود/منقضی شده بود، یک رزوی
    تازه با همان مبلغ پرداخت ساخته می‌شود (سهم ماندهٔ hold منقضی به
    free_credit برگشته و در فاکتور نهایی از همان‌جا کسر خواهد شد)."""
    uid = int(user_id)
    rec = _rec(uid, create=True)
    sweep_expired_holds(uid)
    paid_rial = max(0, int(paid_rial or 0))
    discount_rial = max(0, int(discount_rial or 0))

    hold = None
    if task_id:
        hold = next((r for r in rec["reservations"]
                     if r.get("task_id") == task_id and r.get("status") == ST_HOLD), None)
    if hold is None:
        # fallback: جدیدترین hold همان سرویس (فاکتور‌های قدیمی بدون tid)
        holds = [r for r in rec["reservations"]
                 if r.get("status") == ST_HOLD
                 and (not service_key or r.get("service") == service_key)]
        hold = holds[-1] if holds else None

    if hold is not None:
        hold.update({
            "status": ST_RESERVED,
            "paid_rial": paid_rial,
            "discount_rial": max(discount_rial, int(hold.get("discount_rial", 0) or 0)),
            "charge_id": str(charge_id or ""),
            "paid_at": datetime.datetime.now(),
            "hold_expires_at": None,
        })
        hold["reserved_rial"] = (paid_rial + int(hold.get("credit_used_rial", 0) or 0)
                                 + int(hold.get("discount_rial", 0) or 0))
        # تخفیف این فاکتور در همین رزرو لحاظ شد — از جدول موقت پاک شود
        _pending_discounts.pop(uid, None)
        res = hold
    else:
        res = {
            "task_id": task_id or secrets.token_hex(6),
            "service": str(service_key),
            "service_label": str(service_label or service_key),
            "reserved_rial": paid_rial + discount_rial,
            "paid_rial": paid_rial,
            "credit_used_rial": 0,
            "discount_rial": discount_rial,
            "charge_id": str(charge_id or ""),
            "paid_at": datetime.datetime.now(),
            "status": ST_RESERVED,
            "hold_expires_at": None,
        }
        rec["reservations"].append(res)
    _persist()
    return res


def release_hold(user_id: int, task_id: str | None = None,
                 service_key: str | None = None) -> int:
    """لغو hold (انصراف کاربر از فاکتور): سهم مانده به free_credit برمی‌گردد.

    اگر task_id ندهید، همهٔ hold های فعال همان سرویس (یا همهٔ hold ها،
    وقتی service_key هم نباشد) لغو می‌شوند. خروجی: تعداد."""
    uid = int(user_id)
    rec = _rec(uid)
    if not rec:
        return 0
    n = 0
    for r in rec.get("reservations", []):
        if r.get("status") != ST_HOLD:
            continue
        if task_id and r.get("task_id") != task_id:
            continue
        if service_key and r.get("service") not in _group_of(service_key) + (str(service_key),):
            continue
        r["status"] = ST_RELEASED
        r["released_at"] = datetime.datetime.now()
        back = int(r.get("credit_used_rial", 0) or 0)
        if back > 0:
            rec["free_credit_rial"] = int(rec.get("free_credit_rial", 0) or 0) + back
        n += 1
    if n:
        _persist()
    return n


def mark_queued(user_id: int, task_id: str | None) -> bool:
    """reserved → queued (هنگام enqueue تسک؛ برای pay_reconcile — سند §۵.۷)."""
    if not task_id:
        return False
    rec = _rec(user_id)
    if not rec:
        return False
    for r in rec.get("reservations", []):
        if r.get("task_id") == task_id and r.get("status") == ST_RESERVED:
            r["status"] = ST_QUEUED
            r["queued_at"] = datetime.datetime.now()
            _persist()
            return True
    return False


def has_active_reservation(user_id: int, task_id: str | None) -> bool:
    """آیا رزرو فعالی (reserved/queued) با این task_id وجود دارد؟ (گارد enqueue)"""
    if not task_id:
        return False
    rec = _rec(user_id)
    if not rec:
        return False
    return any(r.get("task_id") == task_id and r.get("status") in (ST_RESERVED, ST_QUEUED)
               for r in rec.get("reservations", []))


def consume_reservation(user_id: int, service_key=None, task_id: str | None = None) -> dict | None:
    """برداشتن رزرو برای فاکتور نهایی (سند §۴.۳ consume_reservation).

    اگر task_id باشد همان رزرو (در صورت فعال بودن)؛ وگرنه FIFO قدیمی‌ترین
    رزروِ فعالِ همان گروه سرویس. رزرو mark می‌شود consumed و برگردانده
    می‌شود؛ اگر نبود None."""
    uid = int(user_id)
    rec = _rec(uid)
    if not rec:
        return None
    sweep_expired_holds(uid)
    group = _group_of(service_key)

    def _take(r):
        r["status"] = ST_CONSUMED
        r["consumed_at"] = datetime.datetime.now()
        return r

    if task_id:
        for r in rec.get("reservations", []):
            if r.get("task_id") == task_id and r.get("status") in (ST_RESERVED, ST_QUEUED):
                _persist()
                return _take(r)
    cands = [r for r in rec.get("reservations", [])
             if r.get("status") in (ST_RESERVED, ST_QUEUED)
             and (not group or r.get("service") in group)]
    # ⭐️ نگاشت گروه (سند §۴.۳/تست §۷-۶): رزرو سرویس دیگر هرگز در فاکتور این
    # سرویس کسر نمی‌شود — بدون fallback بین‌گروهی.
    if not cands:
        return None
    cands.sort(key=lambda r: r.get("paid_at") or datetime.datetime.min)
    _persist()
    return _take(cands[0])


def release_reservation(user_id: int, task_id: str | None,
                        to_free_credit: bool = True) -> dict | None:
    """آزادسازی رزرو در شکست/لغو تسک (سند §۵.۹).

    سهم مانده همیشه به free_credit برمی‌گردد. بخش پرداخت‌شده:
      to_free_credit=True  ⇒ به free_credit برمی‌گردد (شکست خودکار —
                             سند §۵.۹) و به مدیر گزارش می‌شود.
      to_free_credit=False ⇒ فقط وضعیت released می‌شود؛ خودِ پول از مسیر
                             دیگری (مثلاً refund_approvals با تایید مدیر)
                             به کاربر برمی‌گردد."""
    if not task_id:
        return None
    uid = int(user_id)
    rec = _rec(uid)
    if not rec:
        return None
    for r in rec.get("reservations", []):
        if r.get("task_id") == task_id and r.get("status") in (ST_RESERVED, ST_QUEUED):
            r["status"] = ST_RELEASED
            r["released_at"] = datetime.datetime.now()
            back = int(r.get("credit_used_rial", 0) or 0)
            if to_free_credit:
                back += int(r.get("paid_rial", 0) or 0)
            if back > 0:
                rec["free_credit_rial"] = int(rec.get("free_credit_rial", 0) or 0) + back
                r["released_to_free_rial"] = back
            _persist()
            logging.info(
                f"[REG-PREPAY] رزرو آزاد شد: user={uid}, task={task_id}, "
                f"svc={r.get('service')}, بازگشت به ماندهٔ آزاد={back:,} ریال")
            return r
    return None


def mark_consumed_manual(user_id: int, service_key=None, task_id: str | None = None) -> dict | None:
    """نشانه‌گذاری رزرو به‌عنوان «مصرف دستی» (سند §۵.۵ — حالت cost_error
    دعاوی اعتراضی): رکورد حذف نمی‌شود؛ مبلغ در پیام مدیر هم می‌آید تا
    محاسبهٔ دستی انجام شود."""
    res = consume_reservation(user_id, service_key=service_key, task_id=task_id)
    if res is not None:
        res["status"] = ST_CONSUMED_MANUAL
        _persist()
    return res


def release_for_failed_job(job: dict) -> dict | None:
    """میزان امن برای مسیرهای شکست (§۵.۹): اگر job رزروی دارد، آزادش کن."""
    if not isinstance(job, dict) or job.get("_is_bulk"):
        return None
    return release_reservation(job.get("user_id"), job.get("prepay_task_id"))


# ═══════════════════════════════════════════════════════════════════════════
# تعرفه
# ═══════════════════════════════════════════════════════════════════════════

def get_prepay_amount_toman(service_key: str) -> int:
    """مبلغ پیش‌پرداخت (تومان) بر اساس نوع سرویس.

    لایحه و اظهارنامه → ۱۰۰,۰۰۰ تومان؛ سایر موارد → ۲۰۰,۰۰۰ تومان
    (تعرفهٔ تأییدشدهٔ کارفرما ۱۴۰۵/۰۸ — مقادیر پایه در config.py و
    قابل تغییر از تنظیمات پنل).

    ⚠️ گارد API: اگر مقدار کانفیگ (عمدی یا اشتباه) زیر حداقلِ مجاز
    بیفتد، همین‌جا به حداقل (۱,۰۰۰ تومان = ۱۰,۰۰۰ ریال) بالا برده
    می‌شود تا sendInvoice هرگز با خطای «total price must be at least
    10000» رد نشود. چون همهٔ مسیرها از همین تابع مبلغ می‌گیرند،
    فاکتور، پیام‌ها و کسرِ پایان کار همیشه یک عدد را می‌بینند.
    """
    # ⭐ مبلغ از تنظیمات پنل (bot_settings) — در نبود آن، همان مقدار config
    import bot_settings
    if service_key in _LAYEHE_EIZAR_SERVICES:
        base = bot_settings.get_int("prepay.lavayeh_ezhhar_toman", PREPAY_LAYEHE_EIZARNAMEH_TOMAN)
    else:
        base = bot_settings.get_int("prepay.other_toman", PREPAY_OTHER_SERVICES_TOMAN)
    if base * 10 < MIN_INVOICE_AMOUNT_RIAL:
        base = MIN_INVOICE_AMOUNT_RIAL // 10
    return base


def get_prepay_amount_rial(service_key: str) -> int:
    """مبلغ پیش‌پرداخت (ریال) — همیشه ≥ حداقلِ مجاز فاکتور API."""
    return get_prepay_amount_toman(service_key) * 10


# ═══════════════════════════════════════════════════════════════════════════
# فاکتور پیش‌پرداخت و پوشش با مانده
# ═══════════════════════════════════════════════════════════════════════════

async def send_prepay_invoice(bot, user_id: int, service_key: str,
                              service_label: str) -> bool:
    """ارسال فاکتور پیش‌پرداخت + درگاه پرداخت بله و پیام راهنما.

    ⭐️ v2 (سند §۵.۱.۲): پیش از ارسال، سهم ماندهٔ آزاد با hold_for_invoice
    اتمیک نگه داشته می‌شود و task_id همین hold در payload فاکتور می‌نشیند
    تا successful_payment بتواند همان hold را به رزرو تبدیل کند
    (finalize_paid). حساب note_invoice_deduction حفظ شده است.

    خروجی: True اگر فاکتور با موفقیت ارسال شد (فراخواننده باید state را
    روی waiting_for_*_prepay بگذارد)، False در خطا (hold هم آزاد می‌شود).
    """
    # ⭐ تخفیف اختصاصی کاربر (پنل ادمین) — فقط روی پیش‌پرداخت. کاربر کمتر
    # می‌پردازد ولی رزرو مبلغ تخفیف را هم شامل می‌شود تا در فاکتور نهایی
    # کل پیش‌پرداخت کسر شود و تخفیف واقعاً به کاربر برسد.
    import user_discounts
    base_toman = get_prepay_amount_toman(service_key)
    credit_rial = get_free_credit_rial(user_id)
    probe_rial = max(base_toman * 10 - credit_rial, MIN_INVOICE_AMOUNT_RIAL)
    discount_rial = user_discounts.discount_amount(user_id, probe_rial)
    discount_pct = user_discounts.get_percent(user_id)

    amount_rial, hold = hold_for_invoice(user_id, service_key, service_label,
                                         discount_rial=discount_rial)
    credit_used_rial = int(hold.get("credit_used_rial", 0) or 0)
    if discount_rial > 0:
        _pending_discounts[user_id] = discount_rial
    else:
        _pending_discounts.pop(user_id, None)
    amount_toman = amount_rial // 10
    if credit_used_rial > 0:
        # ⭐ اگر کارت‌به‌کارت پرداخت شود، کسر در رسید برای مدیر نمایش داده می‌شود
        try:
            from card_payment import note_invoice_deduction
            note_invoice_deduction(user_id, (PREPAY_INVOICE_TYPE,), base_toman * 10,
                                   credit_used_rial, "مانده/بستانکاری کاربر")
        except Exception:
            pass

    # ═══ ارسال فاکتور بله (sendInvoice) — الگوی اثبات‌شده پروژه ═══
    try:
        invoice_payload = _json.dumps({
            "type": PREPAY_INVOICE_TYPE,
            "svc": service_key,
            "uid": user_id,
            "tid": hold.get("task_id"),   # ⭐️ v2 — اتصال فاکتور به hold
        })
        async with aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(ssl=BALE_SSL_CONTEXT),
                timeout=aiohttp.ClientTimeout(total=40)) as session:
            invoice_url = f"{BALE_API_BASE}/bot{BOT_TOKEN}/sendInvoice"
            invoice_data = {
                "chat_id": user_id,
                "title": f"پیش پرداخت {service_label}",
                "description": (
                    f"این مبلغ پیش پرداخت {service_label} می باشد\n"
                    + (f"پیش‌پرداخت: {base_toman:,} تومان − مانده/بستانکاری شما: "
                       f"{credit_used_rial // 10:,} تومان\n"
                       if credit_used_rial > 0 else "")
                    + (f"تخفیف اختصاصی شما ({discount_pct}٪): {discount_rial // 10:,} تومان\n"
                       if discount_rial > 0 else "")
                    + f"مبلغ: {amount_toman:,} تومان ({amount_rial:,} ریال)"
                ),
                "payload": invoice_payload,
                "provider_token": BALE_WALLET_TOKEN,
                "currency": "IRR",
                "prices": [{
                    "label": f"پیش پرداخت {service_label}",
                    "amount": amount_rial,
                }],
            }
            logging.info(
                f"[REG-PREPAY] ارسال فاکتور پیش‌پرداخت: user={user_id}, "
                f"svc={service_key}, مبلغ={amount_rial:,} ریال "
                f"(نگه‌داشته از مانده: {credit_used_rial:,} ریال)")
            from wallet import prepare_invoice as _wl_prep; invoice_data = _wl_prep(invoice_data)  # ⭐ کسر خودکار موجودی کیف پول
            async with session.post(invoice_url, json=invoice_data) as resp:
                result = await resp.json()
                if not result.get("ok"):
                    logging.error(f"[REG-PREPAY] خطای sendInvoice: {result}")
                    raise Exception(result.get("description", "خطا در ارسال فاکتور"))
                from card_payment import track_invoice as _cp_track; _cp_track(invoice_data)  # ⭐ کارت‌به‌کارت پس از ۲۰ دقیقه
    except Exception as e:
        logging.error(f"[REG-PREPAY] خطا در ارسال فاکتور پیش‌پرداخت: {e}",
                      exc_info=True)
        # فاکتور ارسال نشد → hold آزاد شود تا مانده کاربر قفل نماند
        release_hold(user_id, hold.get("task_id"))
        try:
            await bot.send_message(
                user_id,
                "⚠️ خطا در ساخت فاکتور پیش‌پرداخت. لطفاً کمی بعد دوباره "
                "گزینه تایید را انتخاب کنید.")
        except Exception:
            pass
        return False

    # ⭐ مانده/بستانکاری کاربر (مبالغ قابل بازگشت/کسر) در پیام پیش‌پرداخت درج می‌شود
    credit_line = (
        f"💵 مبلغ پیش‌پرداخت {base_toman:,} تومان است؛ "
        f"{credit_used_rial // 10:,} تومان از مانده/بستانکاری شما از آن کسر شد.\n\n"
        if credit_used_rial > 0 else "")
    if discount_rial > 0:
        credit_line += (f"🎁 تخفیف اختصاصی شما ({discount_pct}٪): {discount_rial // 10:,} تومان؛ "
                        f"در فاکتور نهایی کل پیش‌پرداخت ({base_toman:,} تومان) از هزینه کسر می‌شود.\n\n")

    # ═══ پیام راهنما — عیناً متن دستور کارفرما ═══
    try:
        await bot.send_message(
            user_id,
            f"🧾 *فاکتور پیش پرداخت*\n"
            f"💰 مبلغ: *{amount_toman:,} تومان*\n\n"
            f"{credit_line}"
            f"این مبلغ پیش پرداخت می باشد لطفا پرداخت تا موارد شما شروع به ثبت گردد. باتشکر",
            parse_mode="Markdown")
    except Exception:
        # بعضی پارس‌های Markdown در بله سخت‌گیر است — نسخه ساده
        await bot.send_message(
            user_id,
            f"🧾 فاکتور پیش پرداخت\n"
            f"💰 مبلغ: {amount_toman:,} تومان\n\n"
            f"{credit_line.replace('*', '')}"
            f"این مبلغ پیش پرداخت می باشد لطفا پرداخت تا موارد شما شروع به ثبت گردد. باتشکر")

    # اطلاع به مدیر
    try:
        await bot.send_message(
            ADMIN_ID,
            f"🧾 [PREPAY] فاکتور پیش‌پرداخت {service_label} ارسال شد\n"
            f"👤 کاربر: {user_id}\n"
            f"💰 مبلغ: {amount_toman:,} تومان — در انتظار پرداخت"
            + (f"\n💵 {credit_used_rial // 10:,} تومان از مانده/بستانکاری کاربر "
               f"از پیش‌پرداخت {base_toman:,} تومانی کسر شد"
               if credit_used_rial > 0 else "")
            + (f"\n🎁 تخفیف اختصاصی {discount_pct}٪: {discount_rial // 10:,} تومان"
               if discount_rial > 0 else ""))
    except Exception:
        pass

    return True


async def cover_prepay_from_credit(bot, user_id: int, service_key: str,
                                   service_label: str) -> str | None:
    """⭐ دستور کارفرما: اگر مانده/بستانکاری کاربر کل مبلغ پیش‌پرداخت را
    پوشش دهد، مرحلهٔ پرداخت پیش‌پرداخت کلاً حذف و ثبت مستقیم آغاز می‌شود.

    ⭐️ v2 (سند §۵.۱.۳ — رفع باگ اصلی §۳.۳): مانده واقعاً کسر و در یک رزرو
    «reserved» قفل می‌شود؛ در فاکتور نهایی همین رزرو (فقط همین ثبت) کسر
    خواهد شد و دیگر هر تعداد ثبت پشت‌سرهم نمی‌توانند همان مانده را ببینند.

    خروجی: task_id رزرو (truthy) → پیش‌پرداخت پوشش داده شد؛ فراخوان باید
    بلافاصله ثبت را با همین task_id شروع کند. None → فاکتور پیش‌پرداخت
    طبق روال ارسال شود.
    """
    reservation = reserve_from_credit(user_id, service_key, service_label)
    if reservation is None:
        return None
    prepay_rial = int(reservation["reserved_rial"])
    credit_rial = prepay_rial
    task_id = reservation["task_id"]

    logging.info(
        f"[REG-PREPAY] پیش‌پرداخت با مانده پوشش داده شد: user={user_id}, "
        f"svc={service_key}, پیش‌پرداخت={prepay_rial:,}, مانده={credit_rial:,} ریال "
        f"(رزرو task={task_id})")
    try:
        await bot.send_message(
            user_id,
            f"✅ *پیش‌پرداخت نیاز نیست*\n\n"
            f"💵 مانده/بستانکاری شما (*{credit_rial:,} ریال*) مبلغ پیش‌پرداخت "
            f"{service_label} را پوشش می‌دهد.\n"
            f"این مانده در فاکتور نهایی از هزینهٔ کل کسر می‌گردد.\n\n"
            f"⏳ درخواست شما در حال ارسال به سامانه قضایی است...",
            parse_mode="Markdown")
    except Exception:
        try:
            await bot.send_message(
                user_id,
                f"✅ پیش‌پرداخت نیاز نیست — مانده/بستانکاری شما ({credit_rial:,} ریال) "
                f"مبلغ پیش‌پرداخت را پوشش می‌دهد و در فاکتور نهایی کسر می‌گردد.\n"
                f"⏳ درخواست شما در حال ارسال به سامانه قضایی است...")
        except Exception:
            pass
    try:
        await bot.send_message(
            ADMIN_ID,
            f"💵 [PREPAY] پیش‌پرداخت {service_label} کاربر {user_id} با مانده/"
            f"بستانکاری ({credit_rial:,} ریال) پوشش داده شد — ثبت بدون پرداخت "
            f"پیش‌پرداخت آغاز شد (مانده در فاکتور نهایی همین پرونده کسر می‌شود؛ "
            f"رزرو task={task_id}).")
    except Exception:
        pass
    try:
        from sheets import log_event
        await log_event(
            "پرداخت", service_label, str(user_id), user_id,
            doc_name=f"پیش‌پرداخت {service_label}",
            payment_status="پوشش از محل مانده/بستانکاری",
            note=f"پیش‌پرداخت {prepay_rial:,} ریال — مانده {credit_rial:,} ریال")
    except Exception:
        pass
    return task_id


# ═══════════════════════════════════════════════════════════════════════════
# ثبت پرداخت‌های بی‌داده / بازیافتی
# ═══════════════════════════════════════════════════════════════════════════

def register_orphan_prepay(user_id: int, amount_toman: int, service_key: str,
                           charge_id: str = "") -> None:
    """⭐ ثبت امن پرداختِ پیش‌پرداختی که داده‌های FSM آن از بین رفته است.

    ⭐️ v2 (سند §۵.۱.۴): پرداخت بی-state به free_credit_rial اضافه می‌شود
    (نه رزرو) — چون مشخص نیست برای کدام ثبت است؛ از فاکتور ثبت بعدی یا
    با تأیید مدیر (refund_approvals) به کاربر برمی‌گردد. هیچ پولی گم
    نمی‌شود و هیچ فلویی تغییر نمی‌کند.
    """
    if charge_processed(charge_id):
        logging.info(
            f"[REG-PREPAY] پرداخت تکراری (charge={charge_id}) نادیده گرفته شد — "
            f"user={user_id}")
        return
    mark_charge_processed(charge_id)
    uid = int(user_id)
    rec = _rec(uid, create=True)
    add_rial = max(0, int(amount_toman) * 10)
    rec["free_credit_rial"] = int(rec.get("free_credit_rial", 0) or 0) + add_rial
    _persist()
    logging.info(
        f"[REG-PREPAY] پرداخت بدون داده FSM به‌عنوان اعتبار آزاد ثبت شد: "
        f"user={user_id}, svc={service_key}, مبلغ={add_rial:,} ریال, "
        f"charge={charge_id} — از فاکتور ثبت بعدی کسر می‌شود")


async def credit_orphan_prepay_payment(message, bot, service_key: str) -> None:
    """پرداخت پیش‌پرداختی که به state فعلی کاربر تعلق ندارد (بازپخش فاکتور
    قدیمی در حالی که کاربر در فلوی دیگری است) → فقط ثبت به‌عنوان اعتبار.

    برخلاف مسیر «داده FSM یافت نشد» در هندلرهای سرویس، state و داده‌های
    فلوی جاری کاربر دست نمی‌خورد (state.clear() صدا زده نمی‌شود).
    """
    payment = message.successful_payment
    user_id = message.from_user.id
    charge_id = str(getattr(payment, "telegram_payment_charge_id", "") or "")
    amount_toman = int((getattr(payment, "total_amount", 0) or 0) // 10) \
        or get_prepay_amount_toman(service_key)
    register_orphan_prepay(user_id, amount_toman, service_key, charge_id)
    try:
        await message.answer(
            "✅ پرداخت شما دریافت شد اما مربوط به مرحلهٔ فعلی درخواست شما نبود.\n"
            "💵 مبلغ به‌عنوان اعتبار شما ثبت شد و به‌صورت خودکار از فاکتور ثبت "
            "بعدی شما کسر می‌شود.")
    except Exception:
        pass
    try:
        await bot.send_message(
            ADMIN_ID,
            f"⚠️ [REG-PREPAY] پرداخت پیش‌پرداخت «{service_key}» در مرحلهٔ نامربوط — "
            f"user={user_id}\n🎫 payment_id: {charge_id}\n"
            f"💰 مبلغ: {amount_toman:,} تومان\n"
            f"✅ به‌عنوان اعتبار آزاد کاربر ثبت شد (فلوی جاری کاربر دست نخورد).")
    except Exception:
        pass


def register_prepaid(user_id: int, amount_toman: int, service_key: str,
                     service_label: str, charge_id: str = "") -> dict:
    """ثبت پیش‌پرداخت کاربر برای کسر در پایان کار.

    ⭐️ v2 (سند §۵.۱.۴): به‌جای بازنویسی/جمع رکورد، یک «رزرو جدید»
    reserved ساخته می‌شود (paid + تخفیف). اگر hold فعالی برای همین
    پرداخت هست (tid از payload)، finalize_paid آن را تبدیل می‌کند؛
    این تابع مسیر سازگاری قدیمی است (بدون tid).
    """
    if charge_processed(charge_id):
        logging.info(
            f"[REG-PREPAY] پرداخت تکراری (charge={charge_id}) ثبت نشد — "
            f"user={user_id}, svc={service_key}")
        rec = _rec(user_id)
        if rec:
            for r in rec.get("reservations", []):
                if str(r.get("charge_id", "") or "") == str(charge_id):
                    return r
        return {}
    mark_charge_processed(charge_id)
    discount_rial = _pending_discounts.pop(user_id, 0)
    paid_rial = max(0, int(amount_toman) * 10)
    res = finalize_paid(user_id, None, service_key, service_label,
                        paid_rial, charge_id, discount_rial=discount_rial)
    logging.info(
        f"[REG-PREPAY] پیش‌پرداخت ثبت شد: user={user_id}, svc={service_key}, "
        f"مبلغ={paid_rial:,} ریال, تخفیف={discount_rial:,} ریال, "
        f"رزرو={res.get('reserved_rial'):,} ریال (task={res.get('task_id')}), "
        f"charge={charge_id}")
    return res


# ═══════════════════════════════════════════════════════════════════════════
# کسر پایان کار (سند §۴.۳ و §۵.۱.۵)
# ═══════════════════════════════════════════════════════════════════════════

# نوع payload فاکتورهای نهایی که پس از adjust_final_fee_with_prepay ارسال می‌شوند
_FINAL_INVOICE_TYPES = ("lavayeh", "tajdid_nazar")


def pop_prepaid(user_id: int, service_key=None):
    """(سازگاری قدیمی) برداشتن قدیمی‌ترین رزرو فعال — یک‌بار مصرف.

    ⭐️ v2: روی مدل رزرو کار می‌کند؛ خروجی شکل v1-مانند دارد
    (amount_rial/prepay_paid_rial/...) تا مصرف‌کننده‌های قدیمی نشکنند.
    مبنای سود پنل (consumed_prepay_for_panel) هم مثل قبل پر می‌شود."""
    res = consume_reservation(user_id, service_key=service_key)
    if not res:
        return None
    try:   # رزرو مصرف شد → درخواست بازگشتِ شکست قبلی دیگر معتبر نیست
        import refund_approvals
        refund_approvals.cancel_pending_for_user(user_id, "service_fail")
    except Exception:
        pass
    _stash_for_panel(user_id, res, applied_rial=int(res.get("reserved_rial", 0) or 0))
    return {
        "amount_toman": int(res.get("reserved_rial", 0)) // 10,
        "amount_rial": int(res.get("reserved_rial", 0)),
        "prepay_paid_rial": int(res.get("paid_rial", 0) or 0),
        "credit_rial": int(res.get("credit_used_rial", 0) or 0),
        "discount_rial": int(res.get("discount_rial", 0) or 0),
        "service": res.get("service"),
        "service_label": res.get("service_label"),
        "charge_id": res.get("charge_id"),
        "paid_at": res.get("paid_at"),
        "task_id": res.get("task_id"),
    }


def _stash_for_panel(user_id: int, res: dict, applied_rial: int) -> None:
    """مبنای سود پنل: مبلغی که واقعاً از هزینهٔ همین پرونده کسر شد."""
    try:
        stash = getattr(runtime_state, "consumed_prepay_for_panel", None)
        if not isinstance(stash, dict):
            stash = {}
            runtime_state.consumed_prepay_for_panel = stash
        amount_rial = max(0, int(applied_rial) - int(res.get("discount_rial", 0) or 0))
        stash[user_id] = {
            "amount_toman": amount_rial // 10,
            "paid_at": res.get("paid_at"),
            "service": res.get("service"),
            "consumed_at": datetime.datetime.now(),
        }
    except Exception as ex:
        logging.warning(f"[REG-PREPAY] ذخیرهٔ پیش‌پرداخت برای پنل ناموفق: {ex}")


def adjust_final_fee_with_prepay(user_id: int, final_fee_rial: int,
                                 service_key=None, task_id: str | None = None):
    """اعمال کسر پیش‌پرداخت از هزینه کل (سند §۴.۳).

    ⭐️ v2: رزروِ همین ثبت (task_id) یا قدیمی‌ترین رزرو همان گروه سرویس
    (FIFO) مصرف می‌شود — دیگر کل رکورد کاربر با اولین پایان کار بلعیده
    نمی‌شود (رفع §۳.۴). اگر بعد از رزرو هنوز مبلغی از فاکتور مانده و
    ماندهٔ آزاد کاربر مثبت باشد، از ماندهٔ آزاد هم کسر می‌شود (حفظ رفتار
    فعلی کسب‌وکار — §۴.۳ گام ۳).

    خروجی: (final_fee_adjusted, prepay_info)
      - prepay_info=None → رزروی نبود؛ مبلغ بدون تغییر.
      - در غیر این صورت مبلغ جدید = max(0, کل − کسرشده) برگردانده می‌شود.
    """
    res = consume_reservation(user_id, service_key=service_key, task_id=task_id)
    fee = max(0, int(final_fee_rial))
    paid_rial = credit_rial = discount_rial = applied = leftover = 0
    label = None
    if res is not None:
        paid_rial = int(res.get("paid_rial", 0) or 0)
        credit_rial = int(res.get("credit_used_rial", 0) or 0)
        discount_rial = int(res.get("discount_rial", 0) or 0)
        available = int(res.get("reserved_rial", 0) or 0)
        applied = min(available, fee)
        leftover = available - applied
        label = res.get("service_label")
        try:   # رزرو مصرف شد → درخواست بازگشتِ شکست قبلی دیگر معتبر نیست
            import refund_approvals
            refund_approvals.cancel_pending_for_user(user_id, "service_fail")
        except Exception:
            pass

    # ⭐ حفظ رفتار فعلی: ماندهٔ آزاد هم (بعد از رزرو) از فاکتور کسر می‌شود
    extra_credit_rial = 0
    remaining_fee = fee - applied
    if remaining_fee > 0:
        sweep_expired_holds(user_id)
        rec = _rec(user_id)
        free_avail = min(max(0, int((rec or {}).get("free_credit_rial", 0) or 0)), remaining_fee)
        if free_avail > 0:
            rec["free_credit_rial"] = int(rec["free_credit_rial"]) - free_avail
            extra_credit_rial = free_avail
            applied += free_avail

    adjusted = fee - applied
    prepay_info = None
    if res is not None or extra_credit_rial > 0:
        prepay_info = {
            "prepay_paid_rial": paid_rial,
            "credit_rial": credit_rial + extra_credit_rial,
            "applied_rial": applied,
            "leftover_rial": leftover,
            "discount_rial": discount_rial,
            "service": (res or {}).get("service"),
            "service_label": label or "مانده/بستانکاری",
            "task_id": (res or {}).get("task_id"),
            "extra_credit_rial": extra_credit_rial,
        }
        # ⭐ مبنای سود پنل = مبلغی که واقعاً از هزینهٔ این پرونده کسر شد
        if res is not None:
            _stash_for_panel(user_id, res, applied_rial=applied)

    if leftover > 0:
        # ⭐ مازادِ همان رزرو فقط پس از تایید مدیر به کیف پول کاربر واریز
        # می‌شود (refund_approvals) — دوبار حساب نمی‌شود چون رزرو consumed شد.
        try:
            import refund_approvals
            if leftover >= 10:
                refund_approvals.request_refund_nowait(
                    user_id, leftover // 10,
                    f"مازاد پیش‌پرداخت {label or ''}".strip(),
                    source="prepay_surplus")
        except Exception as ex:
            logging.error(f"[REG-PREPAY] واریز مازاد به کیف پول ناموفق — مبلغ به ماندهٔ آزاد برگشت: {ex}")
            rec = _rec(user_id, create=True)
            rec["free_credit_rial"] = int(rec.get("free_credit_rial", 0) or 0) + leftover

    if applied > 0 and adjusted > 0:
        # ⭐ اگر فاکتور نهایی کارت‌به‌کارت پرداخت شود، کسر برای مدیر نمایش داده می‌شود
        try:
            from card_payment import note_invoice_deduction
            parts = []
            if paid_rial > 0:
                parts.append("پیش‌پرداخت")
            if credit_rial + extra_credit_rial > 0:
                parts.append("مانده/بستانکاری")
            note_invoice_deduction(user_id, _FINAL_INVOICE_TYPES, fee, applied,
                                   " + ".join(parts))
        except Exception:
            pass
    if applied > 0 or extra_credit_rial > 0:
        logging.info(
            f"[REG-PREPAY] کسر مانده/پیش‌پرداخت: user={user_id}, کل={fee:,}, "
            f"پیش‌پرداخت={paid_rial:,}, مانده={credit_rial + extra_credit_rial:,}, "
            f"کسرشده={applied:,} → قابل پرداخت={adjusted:,} ریال, "
            f"باقی‌ماندهٔ رزرو={leftover:,} "
            f"(svc={(res or {}).get('service')}, task={task_id or '—'})")
        _persist()
    return adjusted, prepay_info


def build_prepay_fee_text(final_fee_rial: int, prepay_info: dict,
                          total_fee_rial: int) -> str:
    """پیام هزینه پایان کار وقتی کاربر پیش‌پرداخت داشته است.

    طبق دستور کارفرما: هزینه کل اعلام می‌شود، ذکر می‌شود که فلان مبلغ به
    عنوان پیش پرداخت پرداخت شده، مابقی به‌عنوان «مبلغ قابل پرداخت شما»
    اعلام می‌گردد (فاکتورِ همین مبلغ ارسال می‌شود).
    """
    info = prepay_info or {}
    paid_rial = int(info.get("prepay_paid_rial", 0) or 0)
    credit_rial = int(info.get("credit_rial", 0) or 0)
    leftover = int(info.get("leftover_rial", 0) or 0)
    lines = [f"💰 *مبلغ کل: {total_fee_rial:,} ریال*"]
    if paid_rial > 0:
        lines.append(f"💵 مبلغ *{paid_rial:,} ریال* به عنوان پیش پرداخت، پرداخت شده است.")
    # فقط بخشی از مانده که واقعاً در این فاکتور مصرف شد (پیش‌پرداخت اول کسر می‌شود)
    applied = int(info.get("applied_rial", paid_rial + credit_rial) or 0)
    credit_used = max(0, min(credit_rial, applied - min(paid_rial, applied)))
    if credit_used > 0:
        lines.append(f"💵 مبلغ *{credit_used:,} ریال* از مانده/بستانکاری قبلی شما کسر گردید.")
    lines.append(f"💳 *مبلغ قابل پرداخت شما: {final_fee_rial:,} ریال*")
    if leftover > 0:
        lines.append(
            f"👛 مبلغ *{leftover:,} ریال* باقی ماند و پس از تایید مدیریت به کیف پول شما واریز می‌شود؛ "
            f"سپس به‌صورت خودکار از هزینه‌های بعدی شما کسر خواهد شد.")
    return "\n".join(lines)
