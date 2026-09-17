"""
⭐ اصلاحیهٔ کارفرما (۱۴۰۵/۰۶) — پنجرهٔ زمانی ویرایش کدملی/شناسه ملی + جریمهٔ پیش‌پرداخت
═══════════════════════════════════════════════════════════════════════════════════

این ماژول «منبع واحد حقیقت» برای دو پنجرهٔ زمانی است:

۱) پنجرهٔ ۳۰ دقیقه‌ای ویرایش کدملی (pending_nid_fix_windows)
   وقتی در هر یک از بخش‌های «ثبت لایحه»، «ثبت اظهارنامه»، «دعاوی اعتراضی»
   یا «ثبت دادخواست» خطای ثنا (کدملی اشتباه / تاریخ تولد ارسالی مربوط به
   شماره ملی ... اشتباه است / شخص ارائه‌کننده لایحه در فهرست اشخاص پرونده
   نیست) رخ می‌دهد:
     - متن خطا برای کاربر ارسال می‌شود
     - کاربر ۳۰ دقیقه فرصت دارد کدملی شخص را ویرایش کند
     - اگر ظرف ۳۰ دقیقه اقدام نکند → «نصف مبلغ پیش‌پرداخت» برای موارد بعدی
       او از هزینه کسر می‌گردد (مبلغ رکورد prepaid_registrations نصف می‌شود
       و در پایان کارِ درخواست بعدی به‌صورت خودکار اعمال می‌گردد)
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
NID_FIX_WINDOW_MINUTES = 30          # مهلت ویرایش کدملی
TN_RETRIEVE_FIX_MINUTES = 45         # مهلت ویرایش دادنامه/پرونده/تاریخ

FLOW_LAVAYEH = "lavayeh"
FLOW_EZHHARNAMEH = "ezhharnameh"
FLOW_TN = "tn"
FLOW_CHECK = "check"

_FLOW_LABELS = {
    FLOW_LAVAYEH: "ثبت لایحه",
    FLOW_EZHHARNAMEH: "ثبت اظهارنامه",
    FLOW_TN: "دعاوی اعتراضی",
    FLOW_CHECK: "ثبت دادخواست",
}


def flow_label(flow: str) -> str:
    return _FLOW_LABELS.get(flow, flow or "درخواست")


def nid_fix_deadline_text() -> str:
    """متن استاندارد اعلام مهلت ۳۰ دقیقه‌ای — عین دستور کارفرما."""
    return (
        f"⏰ شما *{NID_FIX_WINDOW_MINUTES} دقیقه* فرصت دارید کدملی شخص را ویرایش کنید؛ "
        f"در غیر این صورت پس از {NID_FIX_WINDOW_MINUTES} دقیقه، "
        "*نصف مبلغ پیش‌پرداخت* برای موارد بعدی شما از هزینه کسر می‌گردد."
    )


# ════════════════════════════════════════════════════════════════════════════
# ۱) پنجرهٔ ۳۰ دقیقه‌ای ویرایش کدملی
# ════════════════════════════════════════════════════════════════════════════

def start_window(user_id: int, flow: str, task_data: dict, error_text: str,
                 national_id: str = "", person_role: str = "",
                 person_index: int = -1) -> dict:
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
        "deadline": now + datetime.timedelta(minutes=NID_FIX_WINDOW_MINUTES),
        "penalty_applied": False,
    }
    runtime_state.pending_nid_fix_windows[user_id] = win
    logger.info(
        f"[NID-FIX] پنجرهٔ ۳۰ دقیقه‌ای شروع شد: user={user_id}, flow={flow}, "
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
    """نصف کردن مبلغ پیش‌پرداختِ باقی‌ماندهٔ کاربر (جریمه).

    خروجی: مبلغ جدید (ریال) — ۰ اگر پیش‌پرداختی وجود نداشت یا قبلاً مصرف شده.
    رکورد prepaid_registrations دست‌نخورده می‌ماند (فقط مبلغ نصف می‌شود) تا
    در پایان کارِ درخواست بعدی از طریق adjust_final_fee_with_prepay به‌صورت
    خودکار از هزینه کسر گردد. ماندگاری آن هم قبلاً در persistence تضمین شده.
    """
    prepaid = runtime_state.prepaid_registrations.get(user_id)
    if not prepaid:
        return 0
    old_rial = int(prepaid.get("amount_rial", 0) or 0)
    if old_rial <= 0:
        return 0
    new_rial = old_rial // 2
    prepaid["amount_rial"] = new_rial
    prepaid["amount_toman"] = new_rial // 10
    logger.info(
        f"[NID-FIX] جریمه: پیش‌پرداخت کاربر {user_id} نصف شد: "
        f"{old_rial:,} → {new_rial:,} ریال")
    return new_rial


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
# ۳) اسوئپر دوره‌ای — بستن پنجره‌های منقضی (پس از کرش/ری‌استارت هم کار می‌کند)
# ════════════════════════════════════════════════════════════════════════════

async def sweep_expired(bot) -> int:
    """بستن پنجره‌های منقضی + اعمال جریمه + اطلاع‌رسانی.

    خروجی: تعداد پنجره‌های بسته‌شده. از state_persister (هر ۶۰ ثانیه) صدا
    زده می‌شود؛ خطاها بی‌صدا swallowed می‌شوند تا حلقهٔ اصلی نپرد.
    """
    closed = 0
    now = datetime.datetime.now()

    # ── پنجره‌های ۳۰ دقیقه‌ای ویرایش کدملی ──────────────────────────────
    for uid in list(runtime_state.pending_nid_fix_windows.keys()):
        try:
            win = runtime_state.pending_nid_fix_windows.get(uid)
            if not win or not is_expired(win, now):
                continue
            flow = win.get("flow", "")
            runtime_state.pending_nid_fix_windows.pop(uid, None)
            _cleanup_aliases(uid)

            label = flow_label(flow)
            new_rial = halve_prepaid(uid)  # جریمه — نصف پیش‌پرداخت برای موارد بعدی

            penalty_line = (
                f"💰 نصف مبلغ پیش‌پرداخت شما "
                f"({new_rial // 10:,} تومان) برای موارد بعدی شما لحاظ شد و از "
                "هزینه کسر می‌گردد.\n" if new_rial > 0 else "")
            try:
                await bot.send_message(
                    uid,
                    f"⌛ *مهلت {NID_FIX_WINDOW_MINUTES} دقیقه‌ای ویرایش کدملی به پایان رسید.*\n\n"
                    f"درخواست {label} حذف شد.\n"
                    f"{penalty_line}\n"
                    "در صورت تمایل می‌توانید از منوی اصلی مجدداً اقدام فرمایید.",
                    parse_mode="Markdown")
            except Exception as e:
                logger.warning(f"[NID-FIX] خطا در اطلاع به کاربر {uid}: {e}")

            try:
                await bot.send_message(
                    ADMIN_ID,
                    f"⌛ [NID-FIX] مهلت ویرایش کدملی کاربر {uid} ({label}) به پایان "
                    f"رسید و جریمهٔ نصف پیش‌پرداخت اعمال شد "
                    f"({new_rial:,} ریال باقی‌مانده).")
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
                    f"⌛ *مهلت {TN_RETRIEVE_FIX_MINUTES} دقیقه‌ای ویرایش شماره دادنامه/"
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

    return closed
