"""
⭐ اصلاحیهٔ کارفرما (۱۴۰۵/۰۶) — پنجرهٔ زمانی ویرایش کدملی/شناسه ملی + جریمهٔ پیش‌پرداخت
═══════════════════════════════════════════════════════════════════════════════════

این ماژول «منبع واحد حقیقت» برای دو پنجرهٔ زمانی است:

۱) پنجرهٔ ۴۵ دقیقه‌ای ویرایش کدملی (pending_nid_fix_windows)
   وقتی در هر یک از بخش‌های «ثبت لایحه»، «ثبت اظهارنامه»، «دعاوی اعتراضی»
   یا «ثبت دادخواست» خطای ثنا (کدملی اشتباه / تاریخ تولد ارسالی مربوط به
   شماره ملی ... اشتباه است / شخص ارائه‌کننده لایحه در فهرست اشخاص پرونده
   نیست) رخ می‌دهد:
     - متن خطا برای کاربر ارسال می‌شود
     - کاربر ۴۵ دقیقه فرصت دارد کدملی شخص را ویرایش کند
     - اگر ظرف ۴۵ دقیقه اقدام نکند → «نصف مبلغ پیش‌پرداخت» برای موارد بعدی
       او نگه داشته می‌شود: به کیف پول کاربر واریز و به‌صورت خودکار از
       هزینهٔ موارد بعدی کسر می‌گردد (۱۴۰۵/۰۷)
     - ⚠️ همه‌چیز در فایل ماندگار (persistence.py) ذخیره می‌شود؛ بنابراین
       حتی پس از کرش یا قطعی ربات، جریمه برای هر درخواست بعدیِ همان کاربر
       مورد محاسبه قرار می‌گیرد.

۲) پنجرهٔ ۴۵ دقیقه‌ای ویرایش شماره دادنامه/پرونده/تاریخ دعاوی اعتراضی
   (pending_tn_retrieve_fix)
   وقتی در حین ثبتِ (بعد از پرداخت پیش‌پرداخت) خطای
   «شماره تصمیم نهایی یا شماره پرونده اشتباه می باشد» رخ می‌دهد:
     - کاربر ۴۵ دقیقه فرصت دارد سه مقدار یادشده را ویرایش کند
     - پس از ویرایش، ثبت با «همان اطلاعات سیو شده» و بدون طی سایر مراحل
       از نو آغاز می‌شود
     - مبلغ پیش‌پرداخت دست‌نخورده می‌ماند (کسر کامل در پایان کار)

اسوئپر (sweep_expired) به‌صورت دوره‌ای از state_persister در bot.py
فراخوانی می‌شود تا پنجره‌های منقضی‌شده — حتی پس از ری‌استارت — بسته شوند.
"""

import datetime
import logging

import runtime_state
from config import ADMIN_ID

logger = logging.getLogger(__name__)

# ── ثابت‌ها ────────────────────────────────────────────────────────────────
NID_FIX_WINDOW_MINUTES = 180         # مهلت ویرایش کدملی (۳ ساعت)
TN_RETRIEVE_FIX_MINUTES = 180        # مهلت ویرایش دادنامه/پرونده/تاریخ (۳ ساعت)

_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def duration_label(minutes: int) -> str:
    """«۳ ساعت» / «۴۵ دقیقه» — متن مهلت برای پیام‌های کاربر."""
    if minutes % 60 == 0:
        return f"{minutes // 60} ساعت".translate(_FA_DIGITS)
    return f"{minutes} دقیقه".translate(_FA_DIGITS)


def duration_adj(minutes: int) -> str:
    """«۳ ساعته» / «۴۵ دقیقه‌ای» — صفت مهلت («مهلت ۳ ساعته»)."""
    if minutes % 60 == 0:
        return f"{minutes // 60} ساعته".translate(_FA_DIGITS)
    return f"{minutes} دقیقه‌ای".translate(_FA_DIGITS)

FLOW_LAVAYEH = "lavayeh"
FLOW_EZHHARNAMEH = "ezhharnameh"
FLOW_TN = "tn"
FLOW_CHECK = "check"
FLOW_EALAM = "ealam"

_FLOW_LABELS = {
    FLOW_LAVAYEH: "ثبت لایحه",
    FLOW_EZHHARNAMEH: "ثبت اظهارنامه",
    FLOW_TN: "دعاوی اعتراضی",
    FLOW_CHECK: "ثبت دادخواست",
    FLOW_EALAM: "اعلام وکالت",
}


def flow_label(flow: str) -> str:
    return _FLOW_LABELS.get(flow, flow or "درخواست")


def nid_fix_deadline_text() -> str:
    """متن استاندارد اعلام مهلت ویرایش کدملی — عین دستور کارفرما."""
    return (
        f"⏰ شما *{duration_label(NID_FIX_WINDOW_MINUTES)}* فرصت دارید "
        f"کدملی شخص را ویرایش کنید؛ در غیر این صورت پس از {duration_label(NID_FIX_WINDOW_MINUTES)} "
        "*نصف مبلغ پیش‌پرداخت* برای موارد بعدی شما از هزینه کسر می‌گردد."
    )


# ── ⭐ خطای «طبق اطلاعات ثبت احوال ... فوت کرده است» (اصلاحیه ۱۴۰۵/۰۷) ──
# در تمام بخش‌ها: متن خطا + درخواست کدملی جدید (۴۵ دقیقه) + گزینهٔ انصراف؛
# در صورت انصراف (یا پایان مهلت) ۵۰٪ مبلغ پیش‌پرداخت به کیف پول کاربر
# بازگردانده می‌شود (نه نگه‌داری برای موارد بعدی).
KIND_DECEASED = "deceased"
DECEASED_FIX_BUTTON = "✏️ وارد کردن کدملی جدید"
DECEASED_CANCEL_BUTTON = "❌ انصراف"


def is_deceased_kind(kind) -> bool:
    return kind == KIND_DECEASED


def deceased_message(error_text: str) -> str:
    """پیام استاندارد خطای «فوت کرده است» برای کاربر — در همهٔ بخش‌ها."""
    return (
        f"⚠️ *خطای استعلام ثنا:*\n\n«{(error_text or '').strip()[:300]}»\n\n"
        "لطفاً *شماره کدملی جدید* را وارد کنید.\n\n"
        f"⏰ شما *{duration_label(NID_FIX_WINDOW_MINUTES)}* فرصت دارید کدملی جدید را وارد کنید. "
        "در صورت انصراف (یا پایان مهلت)، *۵۰ درصد مبلغ پیش‌پرداخت* پس از تایید مدیریت "
        "به کیف پول شما بازگردانده می‌شود.")


def penalty_line(new_rial: int) -> str:
    """یک خط پیام جریمه (نصف پیش‌پرداخت به کیف پول برای موارد بعدی) — خالی اگر مبلغی نبود."""
    if new_rial <= 0:
        return ""
    return (f"💰 نصف مبلغ پیش‌پرداخت شما ({new_rial // 10:,} تومان) پس از تایید مدیریت به "
            "کیف پول شما واریز می‌شود و به‌صورت خودکار از هزینهٔ موارد بعدی کسر می‌گردد.\n")


# ════════════════════════════════════════════════════════════════════════════
# ۱) پنجرهٔ ۴۵ دقیقه‌ای ویرایش کدملی
# ════════════════════════════════════════════════════════════════════════════

def start_window(user_id: int, flow: str, task_data: dict, error_text: str,
                 national_id: str = "", person_role: str = "",
                 person_index: int = -1, kind: str = "") -> dict:
    """شروع پنجرهٔ ۳۰ دقیقه‌ای برای کاربر و بازگرداندن رکورد پنجره.

    رکوردِ بازگشتی همان دیکشنری‌ای است که می‌توان به‌عنوان مقدار
    pending_*_sana_fix (سازگاری با هندلرهای قبلی) نیز ذخیره کرد — کلیدهای
    قبلی (task_data / _sana_error_*) حفظ شده‌اند.
    """
    now = datetime.datetime.now()
    win = {
        # ── کلیدهای سازگار با pending_*_sana_fix قبلی ──
        "task_data": task_data,
        "created_at": now,
        # ── کلیدهای جدید پنجره ──
        "flow": flow,
        "error_text": error_text or "",
        "national_id": national_id or "",
        "person_role": person_role or "",
        "person_index": person_index if isinstance(person_index, int) else -1,
        "kind": kind or "",
        "deadline": now + datetime.timedelta(minutes=NID_FIX_WINDOW_MINUTES),
        "penalty_applied": False,
    }
    runtime_state.pending_nid_fix_windows[user_id] = win
    logger.info(
        f"[NID-FIX] پنجرهٔ {duration_adj(NID_FIX_WINDOW_MINUTES)} شروع شد: user={user_id}, flow={flow}, "
        f"nid={national_id}, deadline={win['deadline'].strftime('%H:%M:%S')}")
    return win


def get_window(user_id: int):
    return runtime_state.pending_nid_fix_windows.get(user_id)


def pop_window(user_id: int):
    win = runtime_state.pending_nid_fix_windows.pop(user_id, None)
    if win:
        logger.info(f"[NID-FIX] پنجره بسته شد (ویرایش موفق/حذف): user={user_id}")
    return win


def is_expired(win: dict, now: datetime.datetime = None) -> bool:
    if not win:
        return False
    deadline = win.get("deadline")
    if not isinstance(deadline, datetime.datetime):
        return False
    return (now or datetime.datetime.now()) >= deadline


def _active_reservation(user_id: int):
    """قدیمی‌ترین رزرو فعال کاربر (FIFO) — یا None. (v2 — سند §۵.۶)"""
    try:
        import prepay_registration as _pr
        rec = _pr._rec(user_id)
        if not rec:
            return None
        _pr.sweep_expired_holds(user_id)
        active = [r for r in rec.get("reservations", [])
                  if r.get("status") in ("reserved", "queued")]
        active.sort(key=lambda r: r.get("paid_at") or datetime.datetime.min)
        return active[0] if active else None
    except Exception:
        return None


def halve_prepaid(user_id: int) -> int:
    """جریمه: نصف پیش‌پرداختِ همین درخواست کسر و نیمهٔ دیگر برای موارد بعدی نگه داشته می‌شود.

    ⭐ (۱۴۰۵/۰۷) نیمهٔ نگه‌داشته‌شده به کیف پول کاربر واریز می‌شود تا قابل
    مشاهده باشد و به‌صورت خودکار از هزینهٔ موارد بعدی کسر گردد (قبلاً در رکورد
    prepaid_registrations می‌ماند و فقط در پایان کارِ درخواست بعدی کسر می‌شد).
    ماندهٔ قبلی (بستانکاری) کاربر کامل به کیف پول می‌رود و جریمه نمی‌شود.

    ⭐️ v2 (سند §۵.۶): روی «رزرو همین درخواست» کار می‌کند (نه کل رکورد کاربر)؛
    نصف بخش پرداخت‌شدهٔ رزرو برمی‌گردد و نصف دیگر در همان رزرو برای ادامهٔ
    ثبت (ارسال مجدد پس از ویرایش کدملی) نگه داشته می‌شود.

    خروجی: مبلغ نگه‌داشته‌شدهٔ پیش‌پرداخت (ریال) — ۰ اگر پیش‌پرداختی نبود.
    """
    res = _active_reservation(user_id)
    if not res:
        return 0
    paid_rial = int(res.get("paid_rial", 0) or 0)
    credit_rial = int(res.get("credit_used_rial", 0) or 0)
    # ⭐️ v2: «ماندهٔ قبلی» کاربر (free_credit) هم طبق رفتار قبلی کامل به کیف
    # پول می‌رود (پس از تایید مدیر) — همان‌طور که در v1 کل بخش بستانکاریِ رکورد
    # می‌رفت.
    try:
        import prepay_registration as _pr
        free_avail = _pr.get_free_credit_rial(user_id)
    except Exception:
        free_avail = 0
    if paid_rial + credit_rial + free_avail <= 0:
        return 0
    new_rial = paid_rial // 2
    try:
        # ⭐ واریز فقط پس از تایید مدیر (refund_approvals)؛ نصف پیش‌پرداخت + مانده‌ها
        import refund_approvals
        total_toman = (new_rial // 10 if new_rial >= 10 else 0) \
                      + (credit_rial // 10 if credit_rial >= 10 else 0) \
                      + (free_avail // 10 if free_avail >= 10 else 0)
        if total_toman > 0:
            refund_approvals.request_refund_nowait(
                user_id, total_toman,
                "نصف پیش‌پرداخت (جریمهٔ عدم ویرایش کدملی)"
                + (" + مانده/بستانکاری قبلی" if credit_rial + free_avail >= 10 else ""),
                source="nid_fix_penalty")
    except Exception as e:
        # کیف پول در دسترس نیست → رفتار قبلی (نصف در همان رزرو می‌ماند)
        logger.error(f"[NID-FIX] واریز جریمه به کیف پول کاربر {user_id} ناموفق: {e}")
        res["paid_rial"] = new_rial
        res["reserved_rial"] = new_rial + credit_rial
        return new_rial
    # نصف دیگر در همان رزرو برای ادامهٔ همان ثبت می‌ماند (بدون سهم مانده)
    res["paid_rial"] = new_rial
    res["credit_used_rial"] = 0
    res["reserved_rial"] = new_rial
    try:
        import prepay_registration as _pr
        rec = _pr._rec(user_id)
        if rec is not None:
            rec["free_credit_rial"] = 0     # به کیف پول منتقل شد (پس از تایید مدیر)
            _pr._persist()
    except Exception:
        pass
    logger.info(
        f"[NID-FIX] جریمه: پیش‌پرداخت کاربر {user_id}: {paid_rial:,} ریال → "
        f"{new_rial:,} ریال به کیف پول (پس از تایید مدیر)؛ مانده قبلی {credit_rial:,} ریال هم به کیف پول")
    return new_rial


async def refund_half_prepay_to_wallet(user_id: int) -> int:
    """⭐ خطای «فوت کرده است»: بازگرداندن ۵۰٪ پیش‌پرداختِ همین درخواست به
    کیف پول کاربر. نیمهٔ دیگر کسر می‌شود؛ ماندهٔ قبلی (بستانکاری) کاربر
    کامل به کیف پول منتقل می‌شود.

    ⭐️ v2 (سند §۵.۶): روی «رزرو همین درخواست» کار می‌کند؛ نیمهٔ دیگر
    «مصرف دستی» علامت می‌خورد (consumed_manual) تا در فاکتور بعدی دوباره
    کسر نشود.

    خروجی: مبلغ بازگردانده‌شده (تومان) — ۰ اگر پیش‌پرداختی نبود.
    """
    res = _active_reservation(user_id)
    if not res:
        return 0
    paid_rial = int(res.get("paid_rial", 0) or 0)
    credit_rial = int(res.get("credit_used_rial", 0) or 0)
    if paid_rial <= 0:
        return 0
    refund_toman = (paid_rial // 2) // 10
    # ⭐️ v2: ماندهٔ آزاد کاربر هم طبق رفتار قبلی کامل به کیف پول می‌رود
    try:
        import prepay_registration as _pr
        free_avail = _pr.get_free_credit_rial(user_id)
    except Exception:
        free_avail = 0
    try:
        # ⭐ واریز فقط پس از تایید مدیر (refund_approvals)
        import refund_approvals
        total_toman = max(0, refund_toman) \
                      + (credit_rial // 10 if credit_rial >= 10 else 0) \
                      + (free_avail // 10 if free_avail >= 10 else 0)
        if total_toman > 0:
            refund_approvals.request_refund_nowait(
                user_id, total_toman,
                "بازگشت ۵۰٪ پیش‌پرداخت (خطای فوت ثبت احوال)"
                + (" + مانده/بستانکاری قبلی" if credit_rial + free_avail >= 10 else ""),
                source="nid_fix_deceased")
    except Exception as e:
        logger.error(f"[NID-FIX] خطا در واریز به کیف پول کاربر {user_id}: {e}")
        return 0
    # نیمهٔ دیگر: مصرف دستی (کسرشده) — سهم مانده‌ها از مسیر کیف پول برمی‌گردد
    res["status"] = "consumed_manual"
    res["consumed_at"] = datetime.datetime.now()
    res["release_reason"] = "nid_fix_deceased"
    try:
        import prepay_registration as _pr
        rec = _pr._rec(user_id)
        if rec is not None:
            rec["free_credit_rial"] = 0     # به کیف پول منتقل شد (پس از تایید مدیر)
            _pr._persist()
    except Exception:
        pass
    logger.info(
        f"[NID-FIX] خطای فوت: {refund_toman:,} تومان (۵۰٪ پیش‌پرداخت) به کیف پول "
        f"کاربر {user_id} بازگشت؛ مانده قبلی={credit_rial:,} ریال")
    return refund_toman


def refund_line(refund_toman: int) -> str:
    if refund_toman <= 0:
        return ""
    return (f"💰 ۵۰ درصد مبلغ پیش‌پرداخت ({refund_toman:,} تومان) پس از تایید مدیریت به "
            "کیف پول شما بازگردانده می‌شود.\n")


async def settle_cancel(user_id: int, win) -> str:
    """تسویهٔ پیش‌پرداخت پس از «حذف درخواست/انصراف» در پنجرهٔ ویرایش کدملی.

    خطای «فوت کرده است» → ۵۰٪ به کیف پول؛ سایر خطاها → روند قبلی (نصف
    پیش‌پرداخت برای موارد بعدی). خروجی: یک خط پیام برای کاربر (یا خالی).
    """
    if is_deceased_kind((win or {}).get("kind")):
        return refund_line(await refund_half_prepay_to_wallet(user_id))
    return penalty_line(halve_prepaid(user_id))


# ════════════════════════════════════════════════════════════════════════════
# ⭐ انصراف در فلوی «انتخاب ارائه‌دهنده از فهرست اشخاص پرونده» (اصلاحیهٔ
# کارفرما) — پس از خطای «شخص ارائه‌کننده لایحه ... در فهرست اشخاص پرونده
# نیست» هنگام ثبت موقت، ربات فهرست اشخاص پرونده را از خود سامانه ثنا
# می‌خواند و کاربر ارائه‌دهنده(های) لایحه را صرفاً از همین لیست انتخاب
# می‌کند. اگر کاربر به‌جای انتخاب، «انصراف» بزند: ۳۰,۰۰۰ تومان از مبلغ
# پیش‌پرداختِ همین درخواست (پس از تایید مدیر) به کیف پول کاربر برمی‌گردد
# و باقی پیش‌پرداخت مصرف (جریمهٔ انصراف) می‌شود.
# ════════════════════════════════════════════════════════════════════════════

CASE_PICK_CANCEL_REFUND_TOMAN = 30_000   # بازگشت وجه بابت انصراف (تومان)


def is_case_pick_kind(win) -> bool:
    """آیا این پنجره از نوع «انتخاب ارائه‌دهنده از فهرست اشخاص پرونده» است؟

    (پنجره‌های این فلو، فهرست استخراج‌شدهٔ اشخاص پرونده را در کلید
    case_persons نگه می‌دارند.)
    """
    return bool((win or {}).get("case_persons"))


async def settle_case_pick_cancel(user_id: int) -> str:
    """انصراف در فلوی «انتخاب از فهرست اشخاص پرونده» — تسویهٔ پیش‌پرداخت.

    ۳۰,۰۰۰ تومان (یا کل مبلغ پیش‌پرداخت اگر کمتر باشد) از پیش‌پرداختِ همین
    درخواست پس از تایید مدیر به کیف پول کاربر برمی‌گردد؛ باقی پیش‌پرداخت
    مصرف می‌شود (رزرو → consumed_manual). ماندهٔ آزاد قبلی کاربر هم کامل
    به کیف پول برمی‌گردد (جریمه نمی‌شود).

    خروجی: یک خط پیام برای کاربر (یا خالی اگر پیش‌پرداخت/رزروی نبود).
    """
    res = _active_reservation(user_id)
    if not res:
        logger.info(f"[NID-FIX] انصرافِ انتخاب از فهرست: رزرو فعالی برای user={user_id} یافت نشد")
        return ""
    paid_rial = int(res.get("paid_rial", 0) or 0)
    credit_rial = int(res.get("credit_used_rial", 0) or 0)
    prepay_toman = (paid_rial + credit_rial) // 10
    refund_toman = min(CASE_PICK_CANCEL_REFUND_TOMAN, prepay_toman)
    try:
        import prepay_registration as _pr
        free_avail = _pr.get_free_credit_rial(user_id)
    except Exception:
        free_avail = 0
    try:
        # ⭐ واریز فقط پس از تایید مدیر (refund_approvals)
        import refund_approvals
        total_toman = max(0, refund_toman) \
                      + (free_avail // 10 if free_avail >= 10 else 0)
        if total_toman > 0:
            refund_approvals.request_refund_nowait(
                user_id, total_toman,
                f"بازگشت {refund_toman:,} تومان از پیش‌پرداخت "
                "(انصراف — انتخاب ارائه‌دهنده لایحه از فهرست اشخاص پرونده)"
                + (" + ماندهٔ آزاد کیف پول" if free_avail >= 10 else ""),
                source="lavayeh_case_pick_cancel")
    except Exception as e:
        logger.error(f"[NID-FIX] خطا در ثبت درخواست بازگشت ۳۰,۰۰۰ تومان برای کاربر {user_id}: {e}")
        return ""
    # باقی پیش‌پرداخت مصرف می‌شود (جریمهٔ انصراف)
    res["status"] = "consumed_manual"
    res["consumed_at"] = datetime.datetime.now()
    res["release_reason"] = "lavayeh_case_pick_cancel"
    try:
        import prepay_registration as _pr
        rec = _pr._rec(user_id)
        if rec is not None:
            rec["free_credit_rial"] = 0     # به کیف پول منتقل شد (پس از تایید مدیر)
            _pr._persist()
    except Exception:
        pass
    logger.info(
        f"[NID-FIX] انصرافِ انتخاب از فهرست اشخاص پرونده: {refund_toman:,} تومان از "
        f"پیش‌پرداخت کاربر {user_id} (پس از تایید مدیر) به کیف پول برمی‌گردد؛ باقی مصرف شد")
    if refund_toman > 0:
        return (f"💰 {refund_toman:,} تومان از مبلغ پیش‌پرداخت پس از تایید مدیریت به "
                "کیف پول شما بازگردانده می‌شود.\n")
    return ""


def case_pick_deadline_text() -> str:
    """متن مهلت انتخاب ارائه‌دهنده از فهرست اشخاص پرونده (مطابق قواعد پنجرهٔ ویرایش کدملی)."""
    return (
        f"⏰ مهلت انتخاب: *{duration_label(NID_FIX_WINDOW_MINUTES)}* — پس از پایان مهلت، "
        "*نصف مبلغ پیش‌پرداخت* برای موارد بعدی شما از هزینه کسر می‌گردد."
    )


def _cleanup_aliases(user_id: int):
    """حذف رکوردهای هم‌خانواده (سازگاری با pending_*_sana_fix قدیمی)."""
    for alias in ("pending_tn_sana_fix", "pending_ezhhar_sana_fix",
                  "pending_lavayeh_sana_fix"):
        store = getattr(runtime_state, alias, None)
        if isinstance(store, dict):
            store.pop(user_id, None)


# ════════════════════════════════════════════════════════════════════════════
# ۲) پنجرهٔ ۴۵ دقیقه‌ای ویرایش دادنامه/پرونده/تاریخ (دعاوی اعتراضی)
# ════════════════════════════════════════════════════════════════════════════

def start_tn_retrieve_fix(user_id: int, task_data: dict, error_text: str) -> dict:
    """شروع پنجرهٔ ۴۵ دقیقه‌ای ویرایش سه‌گانه پس از خطای بازیابی دادنامه."""
    now = datetime.datetime.now()
    win = {
        "task_data": task_data,
        "error_text": error_text or "",
        "created_at": now,
        "deadline": now + datetime.timedelta(minutes=TN_RETRIEVE_FIX_MINUTES),
    }
    runtime_state.pending_tn_retrieve_fix[user_id] = win
    logger.info(
        f"[TN-RTV-FIX] پنجرهٔ ۴۵ دقیقه‌ای شروع شد: user={user_id}, "
        f"deadline={win['deadline'].strftime('%H:%M:%S')}")
    return win


def get_tn_retrieve_fix(user_id: int):
    return runtime_state.pending_tn_retrieve_fix.get(user_id)


def pop_tn_retrieve_fix(user_id: int):
    return runtime_state.pending_tn_retrieve_fix.pop(user_id, None)


# ════════════════════════════════════════════════════════════════════════════
# ۴) ⭐ پنجرهٔ ۴۵ دقیقه‌ای ویرایش «شماره قرارداد وکالت» (اصلاحیه ۱۴۰۵/۰۶)
# ════════════════════════════════════════════════════════════════════════════
# وقتی در بخش منضمات (ثبت لایحه / اعلام وکالت / اظهارنامه / دادخواست /
# دعاوی اعتراضی) پس از درج شماره قرارداد و مبلغ حق‌الوکاله و کلیک
# «ثبت و ویرایش پیوست»، پاپ‌آپ «شماره قرارداد الکترونیک وکالت «...»
# معتبر نمی باشد» نمایش داده شود:
#   - مرحلهٔ ثبت قرارداد اسکیپ و سایر پیوست‌ها انجام می‌شود
#   - به کاربر اعلام می‌شود شماره قرارداد اشتباه است و ۴۵ دقیقه فرصت دارد
#     کد قرارداد جدید را ارسال کند
#   - پس از ارسال کد جدید: با کدرهگیری ثبت‌شده (bill_no) همان پرونده
#     استعلام، در منضمات فقط شماره قرارداد درج و پس از پیام تایید،
#     آماده‌سازی/هزینه/چاپ و ادامهٔ مراحل انجام می‌شود
#   (contract_fix_scenario.py — تسک CONTRACT_FIX_SUBMIT)

CONTRACT_FIX_MINUTES = 180            # مهلت ارسال کد قرارداد جدید (۳ ساعت)


def start_contract_fix(user_id: int, flow: str, task_data: dict, bill_no: str,
                       old_contract: str, stamp_amount_value: int = 0,
                       error_text: str = "") -> dict:
    """شروع پنجرهٔ ۴۵ دقیقه‌ای ارسال کد قرارداد جدید."""
    now = datetime.datetime.now()
    win = {
        "flow": flow,
        "task_data": task_data or {},
        "bill_no": str(bill_no or ""),
        "old_contract": str(old_contract or ""),
        "stamp_amount_value": int(stamp_amount_value or 0),
        "error_text": error_text or "",
        "created_at": now,
        "deadline": now + datetime.timedelta(minutes=CONTRACT_FIX_MINUTES),
    }
    runtime_state.pending_contract_fix[user_id] = win
    logger.info(
        f"[CONTRACT-FIX] پنجرهٔ {duration_adj(CONTRACT_FIX_MINUTES)} شماره قرارداد شروع شد: "
        f"user={user_id}, flow={flow}, bill_no={bill_no}, old={old_contract}, "
        f"deadline={win['deadline'].strftime('%H:%M:%S')}")
    return win


def get_contract_fix(user_id: int):
    return runtime_state.pending_contract_fix.get(user_id)


def pop_contract_fix(user_id: int):
    return runtime_state.pending_contract_fix.pop(user_id, None)


def contract_fix_deadline_text() -> str:
    """متن استاندارد اعلام مهلت ۴۵ دقیقه‌ای — عین دستور کارفرما."""
    return (
        f"⏰ شما *{duration_label(CONTRACT_FIX_MINUTES)}* فرصت دارید کد قرارداد جدید را ارسال فرمائید."
    )


# ════════════════════════════════════════════════════════════════════════════
# ۶) ⭐ پنجرهٔ ۳ ساعته اصلاح اطلاعات پرونده لایحه
# ════════════════════════════════════════════════════════════════════════════
# وقتی در ثبت لایحه (پس از پیش‌پرداخت) صحت‌سنجی اطلاعات پرونده ناموفق
# می‌ماند («با اطلاعات ارسالی پرونده یافت نشد»):
#   - کاربر ۳ ساعت فرصت دارد شماره پرونده/استان/ردیف فرعی یا شماره
#     بایگانی/شعبه را اصلاح کند — یا روش ورود پرونده را عوض کند
#   - پس از اصلاح، ثبت با «همان اطلاعات سیو شده» (اشخاص، متن، پیوست‌ها)
#     و بدون پرداخت مجدد از نو آغاز می‌شود
#   - بدون جریمه — پیش‌پرداخت دست‌نخورده می‌ماند (کسر در پایان کار یا
#     ثبت بعدی)

LAVAYEH_CASE_FIX_MINUTES = 180        # مهلت اصلاح اطلاعات پرونده (۳ ساعت)
LAVAYEH_CASE_FIX_MAX_ROUNDS = 3       # سقف دفعات اصلاح برای یک درخواست


def start_lavayeh_case_fix(user_id: int, task_data: dict, error_text: str = "") -> dict:
    """شروع پنجرهٔ اصلاح اطلاعات پرونده لایحه."""
    now = datetime.datetime.now()
    win = {
        "task_data": task_data or {},
        "error_text": error_text or "",
        "created_at": now,
        "deadline": now + datetime.timedelta(minutes=LAVAYEH_CASE_FIX_MINUTES),
    }
    runtime_state.pending_lavayeh_case_fix[user_id] = win
    logger.info(
        f"[LAV-CASE-FIX] پنجرهٔ {duration_adj(LAVAYEH_CASE_FIX_MINUTES)} شروع شد: user={user_id}, "
        f"deadline={win['deadline'].strftime('%H:%M:%S')}")
    return win


def get_lavayeh_case_fix(user_id: int):
    return runtime_state.pending_lavayeh_case_fix.get(user_id)


def pop_lavayeh_case_fix(user_id: int):
    return runtime_state.pending_lavayeh_case_fix.pop(user_id, None)


def lavayeh_case_fix_prepay_line(user_id: int) -> str:
    """یک خط «پیش‌پرداخت حفظ شد» — خالی اگر رزرو فعالی ندارد (مثلاً معاف)."""
    if _active_reservation(user_id) is None:
        return ""
    return "💰 مبلغ پیش‌پرداخت شما حفظ شده و در هزینه ثبت بعدی شما لحاظ می‌گردد.\n"


# ════════════════════════════════════════════════════════════════════════════
# ۵) اسوئپر دوره‌ای — بستن پنجره‌های منقضی (پس از کرش/ری‌استارت هم کار می‌کند)
# ════════════════════════════════════════════════════════════════════════════

async def sweep_expired(bot) -> int:
    """بستن پنجره‌های منقضی + اعمال جریمه + اطلاع‌رسانی.

    خروجی: تعداد پنجره‌های بسته‌شده. از state_persister (هر ۶۰ ثانیه) صدا
    زده می‌شود؛ خطاها بی‌صدا swallowed می‌شوند تا حلقهٔ اصلی نپرد.
    """
    closed = 0
    now = datetime.datetime.now()

    # ── پنجره‌های ۴۵ دقیقه‌ای ویرایش کدملی ──────────────────────────────
    for uid in list(runtime_state.pending_nid_fix_windows.keys()):
        try:
            win = runtime_state.pending_nid_fix_windows.get(uid)
            if not win or not is_expired(win, now):
                continue
            flow = win.get("flow", "")
            runtime_state.pending_nid_fix_windows.pop(uid, None)
            _cleanup_aliases(uid)

            label = flow_label(flow)
            deceased = is_deceased_kind(win.get("kind"))
            case_pick = is_case_pick_kind(win)   # پنجرهٔ «انتخاب از فهرست اشخاص پرونده»
            if deceased:
                # ⭐ خطای فوت — ۵۰٪ پیش‌پرداخت به کیف پول
                refund_toman = await refund_half_prepay_to_wallet(uid)
                new_rial = 0
                settle_text = refund_line(refund_toman)
            else:
                new_rial = halve_prepaid(uid)  # جریمه — نصف پیش‌پرداخت برای موارد بعدی
                settle_text = penalty_line(new_rial)
            if case_pick:
                expired_head = (f"⌛ *مهلت {duration_adj(NID_FIX_WINDOW_MINUTES)} انتخاب "
                                "ارائه‌دهنده لایحه از فهرست اشخاص پرونده به پایان رسید.*")
                admin_expired = (f"⌛ [NID-FIX] مهلت انتخاب ارائه‌دهنده از فهرست اشخاص پروندهٔ "
                                 f"کاربر {uid} ({label}) به پایان رسید و جریمهٔ نصف پیش‌پرداخت "
                                 f"اعمال شد (درخواست بازگشت {new_rial // 10:,} تومان منتظر تایید شماست).")
            else:
                expired_head = f"⌛ *مهلت {duration_adj(NID_FIX_WINDOW_MINUTES)} ویرایش کدملی به پایان رسید.*"
                admin_expired = (f"⌛ [NID-FIX] مهلت ویرایش کدملی کاربر {uid} ({label}) به پایان "
                                 f"رسید و جریمهٔ نصف پیش‌پرداخت اعمال شد "
                                 f"(درخواست بازگشت {new_rial // 10:,} تومان منتظر تایید شماست).")
            try:
                await bot.send_message(
                    uid,
                    f"{expired_head}\n\n"
                    f"درخواست {label} حذف شد.\n"
                    f"{settle_text}\n"
                    "در صورت تمایل می‌توانید از منوی اصلی مجدداً اقدام فرمایید.",
                    parse_mode="Markdown")
            except Exception as e:
                logger.warning(f"[NID-FIX] خطا در اطلاع به کاربر {uid}: {e}")

            try:
                await bot.send_message(
                    ADMIN_ID,
                    (f"⌛ [NID-FIX] مهلت ورود کدملی جدید کاربر {uid} ({label}، خطای فوت) "
                     f"به پایان رسید؛ درخواست بازگشت ۵۰٪ پیش‌پرداخت ثبت شد (منتظر تایید شما).")
                    if deceased else admin_expired)
            except Exception:
                pass
            closed += 1
        except Exception as e:
            logger.error(f"[NID-FIX] خطا در sweep پنجرهٔ کاربر {uid}: {e}")

    # ── پنجرهٔ ۴۵ دقیقه‌ای ویرایش دادنامه/پرونده/تاریخ TN ────────────────
    for uid in list(runtime_state.pending_tn_retrieve_fix.keys()):
        try:
            win = runtime_state.pending_tn_retrieve_fix.get(uid)
            if not win or not is_expired(win, now):
                continue
            runtime_state.pending_tn_retrieve_fix.pop(uid, None)
            try:
                await bot.send_message(
                    uid,
                    f"⌛ *مهلت {duration_adj(TN_RETRIEVE_FIX_MINUTES)} ویرایش شماره دادنامه/"
                    "شماره پرونده/تاریخ دادنامه به پایان رسید.*\n\n"
                    "درخواست دعاوی اعتراضی حذف شد.\n"
                    "💰 مبلغ پیش‌پرداخت شما حفظ شده و در هزینه ثبت بعدی شما "
                    "لحاظ می‌گردد.\n\n"
                    "در صورت تمایل می‌توانید از منوی اصلی مجدداً اقدام فرمایید.",
                    parse_mode="Markdown")
            except Exception as e:
                logger.warning(f"[TN-RTV-FIX] خطا در اطلاع به کاربر {uid}: {e}")
            try:
                await bot.send_message(
                    ADMIN_ID,
                    f"⌛ [TN-RTV-FIX] مهلت ویرایش دادنامه کاربر {uid} به پایان رسید؛ "
                    "درخواست حذف شد (پیش‌پرداخت دست‌نخورده ماند).")
            except Exception:
                pass
            closed += 1
        except Exception as e:
            logger.error(f"[TN-RTV-FIX] خطا در sweep پنجرهٔ کاربر {uid}: {e}")

    # ── ⭐ پنجرهٔ ۴۵ دقیقه‌ای ارسال کد قرارداد جدید (اصلاحیه ۱۴۰۵/۰۶) ─────
    # بدون جریمه — ثبت موقت پرونده در سامانه انجام شده و پیش‌پرداخت دست‌نخورده
    # می‌ماند؛ فقط پنجره بسته و به کاربر/مدیر اطلاع داده می‌شود.
    for uid in list(runtime_state.pending_contract_fix.keys()):
        try:
            win = runtime_state.pending_contract_fix.get(uid)
            if not win or not is_expired(win, now):
                continue
            runtime_state.pending_contract_fix.pop(uid, None)
            flow = win.get("flow", "")
            bill_no = win.get("bill_no", "")
            label = flow_label(flow)
            try:
                await bot.send_message(
                    uid,
                    f"⌛ *مهلت {duration_adj(CONTRACT_FIX_MINUTES)} ارسال کد قرارداد جدید به پایان رسید.*\n\n"
                    f"امکان ثبت خودکار قرارداد برای درخواست «{label}» با کد رهگیری "
                    f"`{bill_no}` وجود ندارد.\n\n"
                    "برای ثبت شماره قرارداد و ادامهٔ مراحل، با پشتیبانی در تماس باشید.",
                    parse_mode="Markdown")
            except Exception as e:
                logger.warning(f"[CONTRACT-FIX] خطا در اطلاع به کاربر {uid}: {e}")
            try:
                await bot.send_message(
                    ADMIN_ID,
                    f"⌛ [CONTRACT-FIX] مهلت ارسال کد قرارداد کاربر {uid} ({label}) "
                    f"به پایان رسید | کد رهگیری: {bill_no} | "
                    f"قرارداد نامعتبر: {win.get('old_contract', '')} — پیگیری دستی لازم است.")
            except Exception:
                pass
            closed += 1
        except Exception as e:
            logger.error(f"[CONTRACT-FIX] خطا در sweep پنجرهٔ کاربر {uid}: {e}")

    # ── ⭐ پنجرهٔ اصلاح اطلاعات پرونده لایحه — بدون جریمه ─────────────────
    for uid in list(runtime_state.pending_lavayeh_case_fix.keys()):
        try:
            win = runtime_state.pending_lavayeh_case_fix.get(uid)
            if not win or not is_expired(win, now):
                continue
            runtime_state.pending_lavayeh_case_fix.pop(uid, None)
            try:
                await bot.send_message(
                    uid,
                    f"⌛ *مهلت {duration_adj(LAVAYEH_CASE_FIX_MINUTES)} اصلاح اطلاعات پرونده به پایان رسید.*\n\n"
                    "درخواست ثبت لایحه حذف شد.\n"
                    f"{lavayeh_case_fix_prepay_line(uid)}\n"
                    "در صورت تمایل می‌توانید از منوی اصلی مجدداً اقدام فرمایید.",
                    parse_mode="Markdown")
            except Exception as e:
                logger.warning(f"[LAV-CASE-FIX] خطا در اطلاع به کاربر {uid}: {e}")
            try:
                await bot.send_message(
                    ADMIN_ID,
                    f"⌛ [LAV-CASE-FIX] مهلت اصلاح اطلاعات پرونده لایحه کاربر {uid} به پایان رسید؛ "
                    "درخواست حذف شد (پیش‌پرداخت دست‌نخورده ماند).")
            except Exception:
                pass
            closed += 1
        except Exception as e:
            logger.error(f"[LAV-CASE-FIX] خطا در sweep پنجرهٔ کاربر {uid}: {e}")

    return closed
