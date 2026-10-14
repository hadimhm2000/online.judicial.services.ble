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
        "در صورت انصراف (یا پایان مهلت)، *۵۰ درصد مبلغ پیش‌پرداخت* به کیف پول "
        "شما بازگردانده می‌شود.")


def penalty_line(new_rial: int) -> str:
    """یک خط پیام جریمه (نصف پیش‌پرداخت به کیف پول برای موارد بعدی) — خالی اگر مبلغی نبود."""
    if new_rial <= 0:
        return ""
    return (f"💰 نصف مبلغ پیش‌پرداخت شما ({new_rial // 10:,} تومان) به کیف پول شما واریز شد "
            "و به‌صورت خودکار از هزینهٔ موارد بعدی کسر می‌گردد.\n")


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


def halve_prepaid(user_id: int) -> int:
    """جریمه: نصف پیش‌پرداختِ همین درخواست کسر و نیمهٔ دیگر برای موارد بعدی نگه داشته می‌شود.

    ⭐ (۱۴۰۵/۰۷) نیمهٔ نگه‌داشته‌شده به کیف پول کاربر واریز می‌شود تا قابل
    مشاهده باشد و به‌صورت خودکار از هزینهٔ موارد بعدی کسر گردد (قبلاً در رکورد
    prepaid_registrations می‌ماند و فقط در پایان کارِ درخواست بعدی کسر می‌شد).
    ماندهٔ قبلی (بستانکاری) کاربر کامل به کیف پول می‌رود و جریمه نمی‌شود.

    خروجی: مبلغ نگه‌داشته‌شدهٔ پیش‌پرداخت (ریال) — ۰ اگر پیش‌پرداختی نبود.
    """
    prepaid = runtime_state.prepaid_registrations.get(user_id)
    if not prepaid:
        return 0
    try:
        from prepay_registration import _split_record
        paid_rial, credit_rial = _split_record(prepaid)
    except Exception:
        paid_rial, credit_rial = int(prepaid.get("amount_rial", 0) or 0), 0
    if paid_rial + credit_rial <= 0:
        return 0
    new_rial = paid_rial // 2
    try:
        import wallet
        if new_rial >= 10:
            wallet.credit_nowait(user_id, new_rial // 10, "refund",
                                 "نصف پیش‌پرداخت (جریمهٔ عدم ویرایش کدملی)")
        if credit_rial >= 10:
            wallet.credit_nowait(user_id, credit_rial // 10, "refund",
                                 "مانده/بستانکاری قبلی")
    except Exception as e:
        # کیف پول در دسترس نیست → رفتار قبلی (نصف رکورد برای موارد بعدی)
        logger.error(f"[NID-FIX] واریز جریمه به کیف پول کاربر {user_id} ناموفق: {e}")
        prepaid["amount_rial"] = new_rial + credit_rial
        prepaid["amount_toman"] = prepaid["amount_rial"] // 10
        prepaid["prepay_paid_rial"] = new_rial
        return new_rial
    runtime_state.prepaid_registrations.pop(user_id, None)
    logger.info(
        f"[NID-FIX] جریمه: پیش‌پرداخت کاربر {user_id}: {paid_rial:,} ریال → "
        f"{new_rial:,} ریال به کیف پول؛ مانده قبلی {credit_rial:,} ریال هم به کیف پول")
    return new_rial


async def refund_half_prepay_to_wallet(user_id: int) -> int:
    """⭐ خطای «فوت کرده است»: بازگرداندن ۵۰٪ پیش‌پرداختِ همین درخواست به
    کیف پول کاربر. نیمهٔ دیگر کسر می‌شود؛ ماندهٔ قبلی (بستانکاری) کاربر
    کامل به کیف پول منتقل می‌شود.

    خروجی: مبلغ بازگردانده‌شده (تومان) — ۰ اگر پیش‌پرداختی نبود.
    """
    rec = runtime_state.prepaid_registrations.get(user_id)
    if not rec:
        return 0
    try:
        from prepay_registration import _split_record
        paid_rial, credit_rial = _split_record(rec)
    except Exception:
        paid_rial, credit_rial = int(rec.get("amount_rial", 0) or 0), 0
    if paid_rial <= 0:
        return 0
    refund_toman = (paid_rial // 2) // 10
    try:
        import wallet
        if refund_toman > 0:
            await wallet.credit(user_id, refund_toman, "refund",
                                "بازگشت ۵۰٪ پیش‌پرداخت (خطای فوت ثبت احوال)")
        # ⭐ ماندهٔ قبلی (بستانکاری) هم به کیف پول می‌رود
        if credit_rial >= 10:
            await wallet.credit(user_id, credit_rial // 10, "refund", "مانده/بستانکاری قبلی")
    except Exception as e:
        logger.error(f"[NID-FIX] خطا در واریز به کیف پول کاربر {user_id}: {e}")
        return 0
    runtime_state.prepaid_registrations.pop(user_id, None)
    logger.info(
        f"[NID-FIX] خطای فوت: {refund_toman:,} تومان (۵۰٪ پیش‌پرداخت) به کیف پول "
        f"کاربر {user_id} بازگشت؛ مانده قبلی={credit_rial:,} ریال")
    return refund_toman


def refund_line(refund_toman: int) -> str:
    if refund_toman <= 0:
        return ""
    return (f"💰 ۵۰ درصد مبلغ پیش‌پرداخت ({refund_toman:,} تومان) به کیف پول "
            "شما بازگردانده شد.\n")


async def settle_cancel(user_id: int, win) -> str:
    """تسویهٔ پیش‌پرداخت پس از «حذف درخواست/انصراف» در پنجرهٔ ویرایش کدملی.

    خطای «فوت کرده است» → ۵۰٪ به کیف پول؛ سایر خطاها → روند قبلی (نصف
    پیش‌پرداخت برای موارد بعدی). خروجی: یک خط پیام برای کاربر (یا خالی).
    """
    if is_deceased_kind((win or {}).get("kind")):
        return refund_line(await refund_half_prepay_to_wallet(user_id))
    return penalty_line(halve_prepaid(user_id))


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
            if deceased:
                # ⭐ خطای فوت — ۵۰٪ پیش‌پرداخت به کیف پول
                refund_toman = await refund_half_prepay_to_wallet(uid)
                new_rial = 0
                settle_text = refund_line(refund_toman)
            else:
                new_rial = halve_prepaid(uid)  # جریمه — نصف پیش‌پرداخت برای موارد بعدی
                settle_text = penalty_line(new_rial)
            try:
                await bot.send_message(
                    uid,
                    f"⌛ *مهلت {duration_adj(NID_FIX_WINDOW_MINUTES)} ویرایش کدملی به پایان رسید.*\n\n"
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
                     f"به پایان رسید؛ ۵۰٪ پیش‌پرداخت به کیف پول بازگشت.")
                    if deceased else
                    (f"⌛ [NID-FIX] مهلت ویرایش کدملی کاربر {uid} ({label}) به پایان "
                     f"رسید و جریمهٔ نصف پیش‌پرداخت اعمال شد "
                     f"({new_rial // 10:,} تومان به کیف پول کاربر رفت)."))
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

    return closed
