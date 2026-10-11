"""
sana_gate.py — دروازهٔ ورود به سامانهٔ قضایی (صف خارج از ساعت کاری + حالت قطعی سامانه)
══════════════════════════════════════════════════════════════════════════════

دو قاعدهٔ کارفرما (۱۴۰۵/۰۷):

۱) صف خارج از ساعت کاری
   - خارج از ساعت کاری (working_hours.py) ربات مثل همیشه اطلاعات و پرداخت را
     از کاربر می‌گیرد، ولی هیچ درخواستی وارد سامانه نمی‌شود.
   - تسک‌های ثبت در صف ماندگار (deferred) می‌مانند و ابتدای ساعت کاری بعدی
     به‌ترتیب ثبت، دوباره وارد job_queue می‌شوند.
   - مدیر فقط خارج از ساعت کاری می‌تواند با /browser_close مرورگر را ببندد تا
     هیچ درخواستی به سامانه نرود (جلوگیری از مسدود شدن IP). ابتدای ساعت کاری
     بعدی مرورگر خودکار دوباره باز می‌شود.

۲) حالت «قطعی سامانه» (دستی، فقط با دستور مدیر)
   - /outage_on : از این لحظه ربات اطلاعات و پرداخت را مثل قبل می‌گیرد؛ هر
     وقت نوبت ورود به سامانه برسد، تسک در صف ماندگار می‌رود و به کاربر اعلام
     می‌شود «سامانه قطع می‌باشد و موارد شما در نوبت می‌باشد و بلافاصله پس از
     رفع قطعی ثبت می‌گردد».
   - /outage_off : صف آزاد می‌شود و ثبت‌ها به‌ترتیب انجام می‌شوند.

استعلام‌ها (که همان لحظه به سامانه نیاز دارند) وقتی دروازه بسته است شروع
نمی‌شوند — is_inquiry_context را ببینید.

تسک‌های امضا (SIGN_TASK_TYPES) هرگز در صف نمی‌روند: کد امضای موقت مهلت کوتاهی
دارد و در sign dispatcher جداگانه پردازش می‌شود.

همهٔ وضعیت (حالت قطعی، بسته‌بودن مرورگر، صف ماندگار) در sana_gate_state.json
ذخیره می‌شود تا ری‌استارت/کرش ربات صف را پاک نکند.
"""
import asyncio
import datetime
import json
import logging
import os
import random

from aiogram import Bot, F, Router, types
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

import runtime_state
from config import ADMIN_ID
import working_hours
from working_hours import TEHRAN_TZ

logger = logging.getLogger(__name__)

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sana_gate_state.json")

_state = {
    "outage": False,
    "outage_since": None,
    "browser_closed": False,
    # ⭐ ۱۴۰۵/۰۷: بسته‌شدن خودکار مرورگر خارج از ساعت کاری / حالت قطعی
    #   browser_closed_reason: "admin" (/browser_close) | "auto" (gate_loop)
    #   admin_open: مدیر خارج از ساعت کاری /browser_open زده — تا شروع ساعت
    #   کاری بعدی خودکار بسته نمی‌شود
    "browser_closed_reason": None,
    "admin_open": False,
    "deferred": [],   # [{"job": {...}, "deferred_at": iso, "reason": "offhours"|"outage"}]
    # ⭐ سابقهٔ درخواست‌های خارج از ساعت کاری (برای /offhours) — ۷ روز اخیر
    "offhours_log": [],  # [{"uid": int, "type": str, "at": iso, "status": "queued"|"released"|"admin_submitted"}]
}

OFFHOURS_LOG_DAYS = 7

# متن‌های کاربر — در صورت تعریف در تنظیمات پنل (bot_settings) از آن‌جا خوانده می‌شوند
DEFAULT_TEXTS = {
    "gate.outage_queued": (
        "⚠️ *سامانه قضایی در حال حاضر قطع می‌باشد.*\n\n"
        "موارد شما در نوبت می‌باشد و بلافاصله پس از رفع قطعی، ثبت می‌گردد.\n"
        "نیازی به ارسال مجدد اطلاعات یا پرداخت نیست. باتشکر"
    ),
    "gate.offhours_queued": (
        "🕑 *درخواست شما خارج از ساعت کاری ثبت شد.*\n\n"
        "موارد شما در نوبت می‌باشد و ابتدای ساعت کاری بعدی (ساعت {start}) "
        "به‌صورت خودکار در سامانه ثبت می‌گردد.\n"
        "نیازی به ارسال مجدد اطلاعات یا پرداخت نیست. باتشکر"
    ),
    "gate.released": "▶️ ثبت موارد شما در سامانه آغاز شد.",
    "gate.sign_offhours": (
        "🕑 *خارج از ساعت کاری*\n\n"
        "امضای الکترونیک فقط در ساعت کاری انجام می‌شود. روند امضای شما محفوظ "
        "است و ابتدای ساعت کاری بعدی (ساعت {start}) خودکار ادامه می‌یابد؛ "
        "آن زمان لطفاً پیام‌های ربات را دنبال کنید. نیازی به ارسال مجدد اطلاعات نیست."
    ),
    "gate.inquiry_closed_offhours": (
        "⛔️ *خارج از ساعت کاری*\n\n"
        "استعلام فقط در ساعت کاری ({start} الی {end}) انجام می‌شود.\n"
        "ثبت لایحه، اظهارنامه، دادخواست و سایر خدمات همچنان فعال است و "
        "ابتدای ساعت کاری بعدی ثبت می‌گردد."
    ),
    "gate.inquiry_closed_outage": (
        "⚠️ *سامانه قضایی در حال حاضر قطع می‌باشد.*\n\n"
        "استعلام پس از رفع قطعی امکان‌پذیر است.\n"
        "ثبت لایحه، اظهارنامه، دادخواست و سایر خدمات همچنان فعال است و "
        "بلافاصله پس از رفع قطعی ثبت می‌گردد."
    ),
}

# دکمه‌های ورود به استعلام (منوی اصلی) و stateهایی که فقط در استعلام استفاده می‌شوند
INQUIRY_ENTRY_TEXTS = frozenset({"🔍 استعلام", "📦 استعلام (چند مورد همزمان)"})

# ⭐ ۱۴۰۵/۰۷: Form.main_menu (صفحهٔ انتخاب نوع استعلام) مقصد بسیاری از مسیرهای
# «بازگشت» هم هست و کاربر در آن دکمه‌های منوی اصلی را می‌زند. این دکمه‌ها
# استعلام نیستند و خارج از ساعت کاری نباید مسدود شوند (مثلاً ابزار فایل،
# محاسبه تمبر، خسارت تأخیر). تطبیق با «زیررشته» مثل process_main_menu.
NON_INQUIRY_MENU_KEYWORDS = (
    "محاسبه تمبر", "ابزار فایل", "خسارت تأخیر", "هزینه دادرسی", "دیه و ارث",
    "ثبت لایحه", "ثبت اظهارنامه", "دعاوی اعتراضی", "🏦 ثبت دادخواست",
    "ارزش منطقه‌ای", "سوابق و فاکتور", "کیف پول", "اشتراک ماهیانه",
    "بازگشت به منوی اصلی",
)
INQUIRY_STATES = frozenset({
    "Form:main_menu",
    "Form:waiting_for_tracking_code",
    "Form:waiting_for_corrected_tracking_code",
    "Form:waiting_for_corrected_doc_category",
    "Form:waiting_for_corrected_doc_subcategory",
    "Form:waiting_for_phone_number",
    "Form:waiting_for_national_id",
    "Form:waiting_for_doc_category",
    "Form:waiting_for_doc_subcategory",
    "Form:waiting_for_attachments_opt",
    "Form:confirm_opt",
    "Form:bulk_inquiry_file_upload",
    "Form:bulk_inquiry_confirm",
})


# ── ماندگاری ─────────────────────────────────────────────────────────────

def _json_default(obj):
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    if isinstance(obj, (set, frozenset)):
        return list(obj)
    return str(obj)


def _save():
    tmp = STATE_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_state, f, ensure_ascii=False, default=_json_default, indent=2)
        os.replace(tmp, STATE_FILE)
    except Exception as e:
        logger.error(f"[SANA_GATE] خطا در ذخیرهٔ وضعیت: {e}")


def load():
    """بارگذاری وضعیت ماندگار — یک‌بار در استارت ربات (bot.py)."""
    if not os.path.exists(STATE_FILE):
        return
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        for key in _state:
            if key in data:
                _state[key] = data[key]
        logger.info(
            f"[SANA_GATE] بارگذاری شد — قطعی: {_state['outage']} | "
            f"مرورگر بسته: {_state['browser_closed']} | صف: {len(_state['deferred'])}")
    except Exception as e:
        logger.error(f"[SANA_GATE] خطا در بارگذاری وضعیت: {e}")


# ── وضعیت دروازه ──────────────────────────────────────────────────────────

def _text(key: str) -> str:
    try:
        import bot_settings
        value = bot_settings.get_text(key)
        if value:
            return value
    except Exception:
        pass
    return DEFAULT_TEXTS[key]


def _fmt(key: str, **kw) -> str:
    """متن با {start}/{end}؛ متن‌های قدیمی پنل که «{start}:00» دارند هم درست می‌شوند
    (ساعت کاری پنل می‌تواند دقیقه داشته باشد، مثلاً 8:30)."""
    text = _text(key).replace("{start}:00", "{start}").replace("{end}:00", "{end}")
    try:
        return text.format(**kw)
    except (KeyError, IndexError, ValueError):
        return text


def is_working_hours(now: datetime.datetime | None = None) -> bool:
    """ساعت کاری تعریف‌شده در پنل ادمین (working_hours.py)."""
    return working_hours.is_working_hours(now)


def is_outage() -> bool:
    return bool(_state["outage"])


def browser_closed() -> bool:
    """مرورگر عمداً بسته است (توسط مدیر یا خودکار خارج از ساعت کاری) — نباید خودکار باز شود."""
    return bool(_state["browser_closed"])


# نام قدیمی (scenarios.py و …)
browser_closed_by_admin = browser_closed


def is_open() -> bool:
    """آیا الان اجازهٔ ورود به سامانه هست؟"""
    return not is_outage() and is_working_hours()


def deferred_count() -> int:
    return len(_state["deferred"])


def _is_admin_job(job: dict) -> bool:
    uid = job.get("user_id")
    return bool(ADMIN_ID) and uid is not None and str(uid) == str(ADMIN_ID)


def should_defer(job: dict) -> bool:
    if not isinstance(job, dict):
        return False
    if job.get("task_type") in runtime_state.SIGN_TASK_TYPES:
        return False
    if is_open():
        return False
    # ⭐ ۱۴۰۵/۰۷: درخواست‌های خود مدیر و درخواستی که مدیر با /offhours_submit
    # انتخاب کرده، خارج از ساعت کاری هم ثبت می‌شوند — مگر سامانه قطع باشد یا
    # مدیر مرورگر را بسته باشد (/browser_close).
    if _is_admin_job(job) or job.get("admin_forced"):
        return is_outage() or browser_closed()
    return True


def is_inquiry_context(message: types.Message, raw_state: str | None) -> bool:
    """پیام مربوط به شروع/ادامهٔ استعلام است؟ (استعلام همان لحظه به سامانه نیاز دارد)"""
    text = (message.text or "").strip()
    if text in INQUIRY_ENTRY_TEXTS:
        return True
    if raw_state == "Form:main_menu" and any(k in text for k in NON_INQUIRY_MENU_KEYWORDS):
        return False
    return raw_state in INQUIRY_STATES


def closed_inquiry_text() -> str:
    if is_outage():
        return _text("gate.inquiry_closed_outage")
    start, end = working_hours.today_bounds()
    if start == "—":
        return _fmt("gate.inquiry_closed_offhours", start=working_hours.next_start_label(), end="—")
    return _fmt("gate.inquiry_closed_offhours", start=start, end=end)


# ── صف ماندگار ────────────────────────────────────────────────────────────

async def defer(job: dict, bot: Bot):
    """تسک را به صف ماندگار می‌برد و به کاربر اطلاع می‌دهد."""
    reason = "outage" if is_outage() else "offhours"
    now_iso = datetime.datetime.now(TEHRAN_TZ).isoformat()
    _state["deferred"].append({
        "job": job,
        "deferred_at": now_iso,
        "reason": reason,
    })
    if reason == "offhours" and job.get("user_id"):
        _log_offhours(job.get("user_id"), _job_label(job), now_iso, job.get("_jid"))
    _save()
    _forget_journal(job)
    uid = job.get("user_id")
    logger.info(
        f"[SANA_GATE] تسک {job.get('task_type') or job.get('query_type')} کاربر {uid} "
        f"به صف رفت ({reason}) — اندازهٔ صف: {deferred_count()}")
    if not uid:
        return
    if reason == "outage":
        text = _text("gate.outage_queued")
    else:
        text = _fmt("gate.offhours_queued", start=working_hours.next_start_label())
    try:
        await bot.send_message(uid, text)
    except Exception as e:
        logger.warning(f"[SANA_GATE] خطا در اطلاع به کاربر {uid}: {e}")


def _forget_journal(job: dict):
    """تسک حالا در sana_gate_state.json نگهداری می‌شود، نه در pending_jobs.json."""
    try:
        import pending_jobs
        pending_jobs.forget(job)
    except Exception:
        pass


# ── ⭐ تسک‌های امضا خارج از ساعت کاری (۱۴۰۵/۰۷) ────────────────────────────
#
# امضا قبلاً همیشه (حتی نیمه‌شب) وارد سامانه می‌شد. حالا وقتی دروازه بسته است:
#   - *_SUBMIT_SIGN (کاربر کد موقتِ از قبل ارسال‌شده را فرستاده) اگر مرورگر باز
#     است اجرا می‌شود تا کد هدر نرود؛
#   - ناوبری/ارسال کد امضا وارد سامانه نمی‌شود: به‌صورت «ناوبری» در صف ماندگار
#     می‌رود و ابتدای ساعت کاری بعدی روند امضا از همان‌جا ادامه می‌یابد.
# درخواست‌های خود مدیر و حالتی که مدیر خارج از ساعت کاری /browser_open زده
# (admin_open) مستثنی‌اند.

_SUBMIT_SIGN_TYPES = frozenset({"LAVAYEH_SUBMIT_SIGN", "TN_SUBMIT_SIGN", "EZHHARNAMEH_SUBMIT_SIGN"})


def sign_should_defer(job: dict) -> bool:
    if not isinstance(job, dict) or job.get("task_type") not in runtime_state.SIGN_TASK_TYPES:
        return False
    if is_open():
        return False
    if _is_admin_job(job) or job.get("admin_forced"):
        return is_outage() or browser_closed()
    if _state.get("admin_open") and not browser_closed():
        return False
    if job.get("task_type") in _SUBMIT_SIGN_TYPES and not browser_closed():
        return False
    return job.get("task_type") not in _SUBMIT_SIGN_TYPES


async def defer_sign(job: dict, bot: Bot):
    """ناوبری/ارسال کد امضا → صف ماندگار به‌صورت «ناوبری» (ادامه در ساعت کاری)."""
    nav = {k: v for k, v in job.items() if k not in ("target_row_indices", "code", "row_idx")}
    nav["phase"] = "navigate"
    reason = "outage" if is_outage() else "offhours"
    uid = job.get("user_id")
    # یک ناوبری امضا برای هر کاربر/پرونده کافی است
    _state["deferred"] = [
        it for it in _state["deferred"]
        if not ((it.get("job") or {}).get("task_type") == nav.get("task_type")
                and (it.get("job") or {}).get("user_id") == uid
                and (it.get("job") or {}).get("tracking_code") == nav.get("tracking_code"))
    ]
    _state["deferred"].append({
        "job": nav,
        "deferred_at": datetime.datetime.now(TEHRAN_TZ).isoformat(),
        "reason": reason,
    })
    _save()
    logger.info(f"[SANA_GATE] امضای کاربر {uid} ({job.get('task_type')}/{job.get('phase')}) "
                f"به ساعت کاری بعدی موکول شد ({reason})")
    if not uid:
        return
    if reason == "outage":
        text = _text("gate.outage_queued")
    else:
        text = _fmt("gate.sign_offhours", start=working_hours.next_start_label())
    try:
        await bot.send_message(uid, text)
    except Exception as e:
        logger.warning(f"[SANA_GATE] خطا در اطلاع به کاربر {uid}: {e}")


_TASK_LABELS = {
    "LAVAYEH_SUBMIT": "لایحه",
    "EALAM_VAKALAHT_SUBMIT": "اعلام وکالت",
    "EZHHARNAMEH_SUBMIT": "اظهارنامه",
    "CHECK_SUBMIT": "دادخواست",
    "CONTRACT_FIX_SUBMIT": "اصلاح قرارداد",
    "PRE_CHECK": "استعلام",
    "LAVAYEH_SEND_SIGN_CODE": "امضای لایحه",
    "EZHHARNAMEH_SEND_SIGN_CODE": "امضای اظهارنامه",
    "TN_SEND_SIGN_CODE": "امضای دعوی اعتراضی",
    "CLEARANCE_SEND_CODE": "گواهی عدم سوءپیشینه",
    "CLEARANCE_FINALIZE": "گواهی عدم سوءپیشینه",
}


def _job_label(job: dict) -> str:
    tt = job.get("task_type")
    if tt:
        return _TASK_LABELS.get(tt, str(tt).replace("_", " "))
    return str(job.get("query_type") or "نامشخص")


def _log_offhours(uid, label: str, at_iso: str, jid: str | None = None):
    """ثبت در سابقهٔ خارج از ساعت کاری و حذف موارد قدیمی‌تر از OFFHOURS_LOG_DAYS روز.
    همان درخواست (همان _jid) که دوباره به صف برگشته، ردیف تازه نمی‌سازد."""
    log = _state.setdefault("offhours_log", [])
    existing = next((e for e in log if jid and e.get("jid") == jid), None)
    if existing is not None:
        existing["status"] = "queued"
    else:
        log.append({"uid": uid, "type": label, "at": at_iso, "status": "queued", "jid": jid})
    cutoff = datetime.datetime.now(TEHRAN_TZ) - datetime.timedelta(days=OFFHOURS_LOG_DAYS)
    kept = []
    for e in log:
        try:
            if datetime.datetime.fromisoformat(e["at"]) >= cutoff:
                kept.append(e)
        except Exception:
            pass
    _state["offhours_log"] = kept[-1000:]


def _mark_log(uid, status: str):
    for e in _state.get("offhours_log", []):
        if str(e.get("uid")) == str(uid) and e.get("status") == "queued":
            e["status"] = status


def log_job_status(jid: str | None, status: str):
    """⭐ وضعیت واقعی درخواست در سابقهٔ خارج از ساعت کاری (pending_jobs.py صدا می‌زند).

    قبلاً همین که صف آزاد می‌شد (یا مدیر «ثبت در سامانه» می‌زد) درخواست «ثبت‌شده»
    نمایش داده می‌شد؛ اگر ربات/مرورگر پیش از ثبت واقعی قطع می‌شد، موردی که هرگز
    ثبت نشده بود ثبت‌شده به نظر می‌رسید. حالا فقط پس از پایان واقعی پردازش
    «done» و در صورت شکست «failed» می‌شود."""
    if not jid:
        return
    changed = False
    for e in _state.get("offhours_log", []):
        if e.get("jid") == jid and e.get("status") != status:
            e["status"] = status
            changed = True
    if changed:
        _save()


def deferred_by_user() -> dict:
    """{user_id: [item, ...]} برای درخواست‌های در صف."""
    out: dict = {}
    for item in _state["deferred"]:
        uid = (item.get("job") or {}).get("user_id")
        out.setdefault(uid, []).append(item)
    return out


async def submit_user_now(uid) -> int:
    """⭐ دستور مدیر: درخواست‌های در صف یک کاربر را همین الان وارد سامانه می‌کند
    (فقط ثبت در سامانه — بدون پرداخت یا پیام اضافه). تعداد تسک‌ها را برمی‌گرداند."""
    mine = [it for it in _state["deferred"] if str((it.get("job") or {}).get("user_id")) == str(uid)]
    if not mine:
        return 0
    mine_ids = {id(it) for it in mine}
    _state["deferred"] = [it for it in _state["deferred"] if id(it) not in mine_ids]
    _mark_log(uid, "admin_submitted")
    _save()
    for item in mine:
        job = dict(item.get("job") or {})
        job["admin_forced"] = True
        await runtime_state.job_queue.put(job)
    logger.info(f"[SANA_GATE] مدیر {len(mine)} درخواست کاربر {uid} را خارج از نوبت وارد سامانه کرد.")
    return len(mine)


async def submit_all_now() -> tuple:
    """⭐ دستور مدیر: کل صف خارج از ساعت کاری را (کاربر به کاربر، به‌ترتیب صف)
    همین الان وارد سامانه می‌کند. (تعداد کاربران، تعداد تسک‌ها) را برمی‌گرداند."""
    uids = [uid for uid in deferred_by_user() if uid is not None]
    total = 0
    for uid in uids:
        total += await submit_user_now(uid)
    return len(uids), total


async def release(bot: Bot) -> int:
    """همهٔ تسک‌های صف را به‌ترتیب به job_queue برمی‌گرداند."""
    items = list(_state["deferred"])
    if not items:
        return 0
    _state["deferred"] = []
    for e in _state.get("offhours_log", []):
        if e.get("status") == "queued":
            e["status"] = "released"
    _save()
    notified = set()
    for item in items:
        job = item.get("job") or {}
        await runtime_state.job_queue.put(job)
        uid = job.get("user_id")
        if uid and uid not in notified:
            notified.add(uid)
            try:
                await bot.send_message(uid, _text("gate.released"))
            except Exception:
                pass
    logger.info(f"[SANA_GATE] {len(items)} تسک از صف آزاد شد.")
    try:
        await bot.send_message(ADMIN_ID, f"▶️ {len(items)} درخواست در صف، وارد پردازش سامانه شد.")
    except Exception:
        pass
    return len(items)


# ── ⭐ چرخهٔ عمر خودکار مرورگر (۱۴۰۵/۰۷) ──────────────────────────────────
#
# دستور کارفرما پس از مسدود شدن IP سرور توسط سامانه:
#   - خارج از ساعت کاری یا در حالت قطعی (/outage_on) مرورگر خودکار بسته شود،
#     مگر مدیر با /browser_open صریحاً بازش کرده باشد (تا شروع ساعت کاری بعدی).
#   - در ساعت کاری مرورگر حتی وقتی بیکار است باز بماند (لاگین حفظ شود) ولی
#     هیچ درخواست پس‌زمینه‌ای به سامانه نرود — بستن فقط وقتی هیچ تسکی در جریان
#     نیست (ثبت، استعلام، امضا، انتخاب واحد) انجام می‌شود.

_busy = 0
RECENT_SIGN_MINUTES = 10


# ⭐ فاصلهٔ تصادفی بین درخواست‌های پشت‌سرهم به سامانه — صف انباشته (ابتدای
# ساعت کاری، چاپ نهایی، پس از رفع قطعی) یکجا و با الگوی ثابت وارد سامانه
# نشود. مقدارها از .env قابل تغییرند (ثانیه).
PACE_MIN_SECONDS = float(os.environ.get("SANA_PACE_MIN_SECONDS", "5"))
PACE_MAX_SECONDS = float(os.environ.get("SANA_PACE_MAX_SECONDS", "20"))
_last_task_at = 0.0


async def pace():
    """قبل از شروع هر تسک صف اصلی: اگر تسک قبلی همین الان شروع شده، تا یک فاصلهٔ
    تصادفی (PACE_MIN..PACE_MAX ثانیه) صبر کن. وقتی صف خالی بوده، صبری نیست."""
    global _last_task_at
    loop = asyncio.get_event_loop()
    gap = random.uniform(PACE_MIN_SECONDS, max(PACE_MIN_SECONDS, PACE_MAX_SECONDS))
    wait = _last_task_at + gap - loop.time()
    if wait > 0:
        await asyncio.sleep(wait)
    _last_task_at = loop.time()


def job_started():
    global _busy
    _busy += 1


def job_finished():
    global _busy
    _busy = max(0, _busy - 1)


def _recent_sign_users(minutes: int = RECENT_SIGN_MINUTES) -> set:
    """کاربرانی که در چند دقیقهٔ اخیر کد امضا برایشان ارسال شده (ممکن است کد بفرستند)."""
    now = datetime.datetime.now()
    limit = datetime.timedelta(minutes=minutes)
    out = set()
    for name in ("pending_lavayeh_sign", "pending_ezhhar_sign", "pending_tn_sign"):
        for uid, info in list((getattr(runtime_state, name, None) or {}).items()):
            if not isinstance(info, dict):
                continue
            for f in ("sign_sent_time", "code_sent_announce_time"):
                ts = info.get(f)
                if isinstance(ts, datetime.datetime):
                    ts = ts.replace(tzinfo=None) if ts.tzinfo else ts
                    if now - ts < limit:
                        out.add(uid)
    return out


def browser_busy() -> str | None:
    """دلیل مشغول بودن مرورگر (برای عدم بستن خودکار) یا None."""
    if _busy:
        return f"{_busy} تسک در حال پردازش"
    for qname in ("job_queue", "priority_job_queue", "sign_job_queue"):
        q = getattr(runtime_state, qname, None)
        if q is not None and q.qsize():
            return "تسک در صف"
    try:
        import sign_tab
        if sign_tab._sign_line:
            return "امضا در جریان"
    except Exception:
        pass
    try:
        import org_unit_picker
        if org_unit_picker._parked_pages or org_unit_picker._sessions:
            return "انتظار انتخاب واحد سازمانی"
    except Exception:
        pass
    if _recent_sign_users():
        return "کد امضای تازه ارسال‌شده"
    return None


def _browser_is_up() -> bool:
    browser = runtime_state.browser
    try:
        return browser is not None and browser.is_connected()
    except Exception:
        return False


async def _auto_close_if_idle(bot: Bot):
    if _state.get("admin_open") or browser_closed():
        return
    if not _browser_is_up():
        # مرورگری باز نیست؛ فقط علامت بزن تا واچ‌داگ آن را باز نکند
        _state["browser_closed"] = True
        _state["browser_closed_reason"] = "auto"
        _save()
        return
    reason = browser_busy()
    if reason:
        logger.info(f"[SANA_GATE] خارج از ساعت کاری — بستن مرورگر تا پایان کار به تعویق افتاد ({reason})")
        return
    await close_browser(reason="auto")
    why = "حالت قطعی سامانه" if is_outage() else "پایان ساعت کاری"
    logger.info(f"[SANA_GATE] مرورگر خودکار بسته شد ({why}).")
    try:
        await bot.send_message(
            ADMIN_ID,
            f"🔒 مرورگر به‌دلیل {why} خودکار بسته شد تا هیچ درخواستی به سامانه نرود.\n"
            f"باز شدن خودکار: ساعت {working_hours.next_start_label()} — "
            "باز کردن زودتر (فقط در صورت نیاز): /browser_open")
    except Exception:
        pass


async def _auto_open(bot: Bot):
    """شروع ساعت کاری / رفع قطعی: مرورگر بسته (خودکار یا مدیر) دوباره باز می‌شود."""
    _state["browser_closed"] = False
    _state["browser_closed_reason"] = None
    _state["admin_open"] = False
    _save()
    try:
        await bot.send_message(
            ADMIN_ID,
            "🟢 ساعت کاری شروع شد — مرورگر دوباره باز می‌شود. "
            "لطفاً منتظر درخواست لاگین بمانید.\n"
            f"درخواست‌های در صف ({deferred_count()}) پس از لاگین به‌ترتیب ثبت می‌شوند.")
    except Exception:
        pass
    try:
        from scenarios import ensure_browser_alive
        # ensure_browser_alive تا لاگین دستی مدیر منتظر می‌ماند — حلقه را معطل نکند
        asyncio.create_task(ensure_browser_alive(bot, notify_admin=False))
    except Exception as e:
        logger.error(f"[SANA_GATE] خطا در باز کردن مرورگر: {e}")


async def gate_loop(bot: Bot, interval_seconds: int = 30):
    """تسک پس‌زمینه: بستن/باز کردن خودکار مرورگر و آزادسازی صف ابتدای ساعت کاری."""
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            if not is_open():
                await _auto_close_if_idle(bot)
                continue
            if browser_closed():
                await _auto_open(bot)
            elif _state.get("admin_open"):
                _state["admin_open"] = False
                _save()
            if _state["deferred"]:
                await release(bot)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[SANA_GATE] خطا در gate_loop: {e}")


def should_launch_on_startup() -> bool:
    """browser_worker هنگام استارت مرورگر را باز کند؟ خارج از ساعت کاری خیر."""
    if browser_closed():
        return False
    if not is_open():
        _state["browser_closed"] = True
        _state["browser_closed_reason"] = "auto"
        _save()
        return False
    return True


# ── بستن مرورگر توسط مدیر ─────────────────────────────────────────────────

def _pending_sign_users() -> set:
    users = set()
    for name in ("pending_lavayeh_sign", "pending_ezhhar_sign", "pending_tn_sign"):
        store = getattr(runtime_state, name, None)
        if isinstance(store, dict):
            users.update(store.keys())
    return users


async def close_browser(reason: str = "admin"):
    """مرورگر پلی‌رایت را می‌بندد (بدون ری‌استارت ربات)."""
    async with runtime_state.browser_relaunch_lock:
        _state["browser_closed"] = True
        _state["browser_closed_reason"] = reason
        _state["admin_open"] = False
        _save()
        try:
            import sign_tab
            for uid in list(runtime_state.sign_pages.keys()):
                await sign_tab.close_sign_page(uid)
        except Exception:
            pass
        browser = runtime_state.browser
        runtime_state.sana_page = None
        runtime_state.browser_context = None
        runtime_state.browser = None
        if browser is not None:
            try:
                if browser.is_connected():
                    await browser.close()
            except Exception as e:
                logger.warning(f"[SANA_GATE] خطا در بستن مرورگر: {e}")


# ── دستورات مدیر ─────────────────────────────────────────────────────────

gate_router = Router()


def _is_admin(message: types.Message) -> bool:
    return bool(message.from_user and message.from_user.id == ADMIN_ID)


def _browser_status_label() -> str:
    if browser_closed():
        return ("بسته‌شده توسط مدیر 🔒" if _state.get("browser_closed_reason") == "admin"
                else "بسته (خودکار، خارج از ساعت کاری/قطعی) 🔒")
    if _state.get("admin_open"):
        return "باز به دستور مدیر (تا شروع ساعت کاری بعدی) 🔓"
    return "فعال" if _browser_is_up() else "در انتظار باز شدن/لاگین"


def _journal_status_line() -> str:
    try:
        import pending_jobs
        return (f"درخواست‌های ثبت در دفتر ماندگار: {pending_jobs.queued_count()} — "
                f"ناموفق/قطع‌شده: {len(pending_jobs.failed_items())}")
    except Exception:
        return ""


def _status_text() -> str:
    lines = [
        "📟 *وضعیت ورود به سامانه*",
        f"ساعت کاری امروز: {working_hours.today_label()} — "
        + ("داخل ساعت کاری ✅" if is_working_hours() else
           f"خارج از ساعت کاری 🌙 (شروع بعدی: {working_hours.next_start_label()})"),
        "منبع ساعت کاری: " + {"panel": "پنل ادمین ✅", "cache": "آخرین برنامهٔ ذخیره‌شدهٔ پنل",
                              "default": "پیش‌فرض ۱۴ الی ۲۲ (پنل در دسترس نبود) ⚠️"}.get(
            working_hours.source(), working_hours.source()),
        "حالت قطعی سامانه: " + ("روشن ⚠️" if is_outage() else "خاموش ✅"),
        "مرورگر: " + _browser_status_label(),
        f"درخواست‌های در صف خارج از ساعت کاری: {deferred_count()}",
        _journal_status_line(),
        "",
        "دستورات: /outage_on  /outage_off  /browser_close  /browser_open  /gate",
        "خارج از ساعت کاری: /offhours  /offhours_submit <آیدی کاربر>  /offhours_submit_all",
        "درخواست‌های معوق و ناموفق: /pending",
    ]
    return "\n".join(lines)


@gate_router.message(Command("gate"), _is_admin)
async def gate_status_cmd(message: types.Message):
    await message.answer(_status_text())


@gate_router.message(Command("outage_on"), _is_admin)
async def outage_on_cmd(message: types.Message):
    _state["outage"] = True
    _state["outage_since"] = datetime.datetime.now(TEHRAN_TZ).isoformat()
    _save()
    await message.answer(
        "⚠️ حالت «قطعی سامانه» روشن شد.\n\n"
        "ربات اطلاعات و پرداخت را مثل قبل می‌گیرد؛ هر درخواستی که نوبت ورودش به "
        "سامانه برسد در صف می‌ماند و به کاربر اعلام می‌شود سامانه قطع است.\n"
        "استعلام‌ها تا رفع قطعی بسته‌اند.\n\n"
        "پس از رفع قطعی: /outage_off")


@gate_router.message(Command("outage_off"), _is_admin)
async def outage_off_cmd(message: types.Message, bot: Bot):
    _state["outage"] = False
    _state["outage_since"] = None
    _save()
    if is_working_hours():
        released = await release(bot)
        await message.answer(f"✅ حالت قطعی خاموش شد. {released} درخواست در صف وارد پردازش شد.")
    else:
        await message.answer(
            f"✅ حالت قطعی خاموش شد. چون خارج از ساعت کاری هستیم، {deferred_count()} "
            f"درخواست در صف ابتدای ساعت کاری بعدی ثبت می‌شوند.")


@gate_router.message(Command("browser_close"), _is_admin)
async def browser_close_cmd(message: types.Message):
    if is_working_hours():
        await message.answer(
            "⛔️ بستن مرورگر فقط خارج از ساعت کاری مجاز است "
            f"(ساعت کاری امروز {working_hours.today_label()}).")
        return
    force = "force" in (message.text or "")
    signing = _pending_sign_users()
    if signing and not force:
        await message.answer(
            f"⚠️ {len(signing)} کاربر هنوز در مرحلهٔ امضا هستند و با بستن مرورگر "
            "امضایشان ناتمام می‌ماند.\n\nاگر مطمئن هستید: /browser_close force")
        return
    await close_browser(reason="admin")
    await message.answer(
        "🔒 مرورگر بسته شد. تا ابتدای ساعت کاری بعدی هیچ درخواستی وارد سامانه "
        "نمی‌شود و درخواست‌ها در صف می‌مانند.\n"
        f"ساعت {working_hours.next_start_label()} مرورگر خودکار باز می‌شود (یا زودتر: /browser_open).")


@gate_router.message(Command("browser_open"), _is_admin)
async def browser_open_cmd(message: types.Message, bot: Bot):
    _state["browser_closed"] = False
    _state["browser_closed_reason"] = None
    # خارج از ساعت کاری/قطعی: باز به دستور مدیر تا شروع ساعت کاری بعدی (بستن خودکار نمی‌شود)
    _state["admin_open"] = not is_open()
    _save()
    note = ""
    if _state["admin_open"]:
        note = ("\n\n⚠️ خارج از ساعت کاری هستیم: مرورگر تا شروع ساعت کاری بعدی باز می‌ماند. "
                "درخواست‌های کاربران همچنان در صف می‌مانند (برای ثبت یک کاربر: /offhours). "
                "پس از اتمام کار: /browser_close")
    await message.answer("🔓 مرورگر در حال باز شدن است — لطفاً منتظر درخواست لاگین بمانید." + note)
    try:
        from scenarios import ensure_browser_alive
        ok = await ensure_browser_alive(bot, notify_admin=False)
        if not ok:
            await message.answer("❌ باز کردن مرورگر ناموفق بود؛ لاگ ربات را بررسی کنید.")
    except Exception as e:
        await message.answer(f"❌ خطا در باز کردن مرورگر: {str(e)[:200]}")


# ── ⭐ درخواست‌های خارج از ساعت کاری (۱۴۰۵/۰۷) ─────────────────────────────

_STATUS_FA = {
    "queued": "در صف خارج از ساعت کاری",
    "released": "در صف ثبت (هنوز ثبت نشده)",
    "admin_submitted": "در صف ثبت به دستور مدیر (هنوز ثبت نشده)",
    "done": "پردازش شد ✅",
    "failed": "ناموفق/قطع‌شده — /pending",
}


def _fmt_at(iso: str) -> str:
    try:
        return datetime.datetime.fromisoformat(iso).strftime("%m/%d %H:%M")
    except Exception:
        return str(iso)[:16]


def offhours_report() -> tuple:
    """متن گزارش /offhours و کیبورد دکمه‌های «ثبت در سامانه» برای هر کاربر در صف."""
    by_user = deferred_by_user()
    lines = [f"🌙 *درخواست‌های خارج از ساعت کاری* (ساعت کاری امروز: {working_hours.today_label()})", ""]
    if by_user:
        lines.append(f"⏳ *در صف ثبت — {len(by_user)} کاربر، {deferred_count()} درخواست:*")
        for uid, items in by_user.items():
            types_ = "، ".join(sorted({_job_label(it.get("job") or {}) for it in items}))
            first = min((it.get("deferred_at") or "") for it in items)
            lines.append(f"• `{uid}` — {len(items)} مورد ({types_}) — از {_fmt_at(first)}")
    else:
        lines.append("⏳ هیچ درخواستی در صف خارج از ساعت کاری نیست.")

    log = _state.get("offhours_log", [])
    users = {}
    for e in log:
        users.setdefault(e.get("uid"), []).append(e)
    lines.append("")
    lines.append(f"📊 *{OFFHOURS_LOG_DAYS} روز اخیر — {len(users)} کاربر، {len(log)} درخواست خارج از ساعت کاری:*")
    for uid, entries in list(users.items())[-50:]:
        last = entries[-1]
        lines.append(f"• `{uid}` — {len(entries)} مورد — آخرین: {_fmt_at(last.get('at', ''))} "
                     f"({_STATUS_FA.get(last.get('status'), last.get('status'))})")
    lines.append("")
    lines.append("برای ثبت فوری درخواست یک کاربر در سامانه: دکمهٔ زیر یا /offhours_submit <آیدی کاربر>")
    lines.append("برای ثبت فوری همهٔ صف: /offhours_submit_all")

    rows = [[InlineKeyboardButton(text=f"▶️ ثبت در سامانه: {uid} ({len(items)})",
                                  callback_data=f"ohs:{uid}")]
            for uid, items in list(by_user.items())[:30] if uid is not None]
    if rows:
        rows.insert(0, [InlineKeyboardButton(text=f"⏩ ثبت همهٔ صف ({deferred_count()})",
                                             callback_data="ohsall")])
    kb = InlineKeyboardMarkup(inline_keyboard=rows) if rows else None
    return "\n".join(lines), kb


async def _submit_and_report(uid_text: str) -> str:
    uid_text = (uid_text or "").strip()
    if not uid_text.lstrip("-").isdigit():
        return "⚠️ آیدی کاربر نامعتبر است. مثال: /offhours_submit 123456789"
    if is_outage():
        return "⚠️ حالت «قطعی سامانه» روشن است؛ ابتدا /outage_off را بزنید."
    if browser_closed():
        return "⚠️ مرورگر توسط مدیر بسته شده است؛ ابتدا /browser_open را بزنید."
    count = await submit_user_now(int(uid_text))
    if not count:
        return f"ℹ️ درخواستی از کاربر `{uid_text}` در صف خارج از ساعت کاری نیست."
    return f"▶️ {count} درخواست کاربر `{uid_text}` برای ثبت در سامانه وارد صف پردازش شد."


async def _submit_all_and_report() -> str:
    if is_outage():
        return "⚠️ حالت «قطعی سامانه» روشن است؛ ابتدا /outage_off را بزنید."
    if browser_closed():
        return "⚠️ مرورگر توسط مدیر بسته شده است؛ ابتدا /browser_open را بزنید."
    users, count = await submit_all_now()
    if not count:
        return "ℹ️ هیچ درخواستی در صف خارج از ساعت کاری نیست."
    return f"▶️ {count} درخواست از {users} کاربر برای ثبت در سامانه وارد صف پردازش شد."


@gate_router.message(Command("offhours"), _is_admin)
async def offhours_cmd(message: types.Message):
    text, kb = offhours_report()
    await message.answer(text, reply_markup=kb)


@gate_router.message(Command("offhours_submit"), _is_admin)
async def offhours_submit_cmd(message: types.Message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        text, kb = offhours_report()
        await message.answer("آیدی کاربر را بعد از دستور بنویسید یا از دکمه‌ها انتخاب کنید.\n\n" + text,
                             reply_markup=kb)
        return
    await message.answer(await _submit_and_report(parts[1]))


@gate_router.callback_query(F.data.startswith("ohs:"))
async def offhours_submit_cb(callback: CallbackQuery):
    if not (callback.from_user and callback.from_user.id == ADMIN_ID):
        await callback.answer()
        return
    await callback.answer()
    await callback.message.answer(await _submit_and_report(callback.data.split(":", 1)[1]))


@gate_router.message(Command("offhours_submit_all"), _is_admin)
async def offhours_submit_all_cmd(message: types.Message):
    await message.answer(await _submit_all_and_report())


@gate_router.callback_query(F.data == "ohsall")
async def offhours_submit_all_cb(callback: CallbackQuery):
    if not (callback.from_user and callback.from_user.id == ADMIN_ID):
        await callback.answer()
        return
    await callback.answer()
    await callback.message.answer(await _submit_all_and_report())



# ── ⭐ درخواست‌های معوق و ناموفق (pending_jobs.py) ──────────────────────────

def pending_report() -> tuple:
    import pending_jobs
    failed = pending_jobs.failed_items()
    lines = [
        "🗂 *درخواست‌های ثبت در سامانه*",
        "",
        f"⏳ در صف پردازش (دفتر ماندگار): {pending_jobs.queued_count()}",
        f"🌙 در صف خارج از ساعت کاری/قطعی: {deferred_count()}  (جزئیات: /offhours)",
        "",
    ]
    if failed:
        lines.append(f"❌ *ناموفق یا قطع‌شده حین پردازش — {len(failed)} مورد* "
                     "(خودکار تکرار نمی‌شوند تا ثبت تکراری ساخته نشود؛ ابتدا در سامانه "
                     "بررسی کنید که ثبت نشده باشند):")
        for it in failed[-30:]:
            tc = (it.get("job") or {}).get("tracking_code")
            lines.append(f"• `{it.get('user_id')}` — {it.get('label')}"
                         + (f" — کد رهگیری `{tc}`" if tc else "")
                         + f" — {_fmt_at(it.get('failed_at', ''))}\n   علت: {str(it.get('error', ''))[:120]}")
    else:
        lines.append("✅ درخواست ناموفق/قطع‌شده‌ای نیست.")
    rows = []
    for it in failed[-15:]:
        jid = it.get("jid")
        rows.append([
            InlineKeyboardButton(text=f"🔁 ثبت مجدد {it.get('user_id')} ({it.get('label')})",
                                 callback_data=f"pjr:{jid}"),
            InlineKeyboardButton(text="🗑 حذف", callback_data=f"pjd:{jid}"),
        ])
    kb = InlineKeyboardMarkup(inline_keyboard=rows) if rows else None
    return "\n".join(lines), kb


@gate_router.message(Command("pending"), _is_admin)
async def pending_cmd(message: types.Message):
    text, kb = pending_report()
    await message.answer(text, reply_markup=kb)


@gate_router.callback_query(F.data.startswith("pjr:") | F.data.startswith("pjd:"))
async def pending_action_cb(callback: CallbackQuery):
    if not (callback.from_user and callback.from_user.id == ADMIN_ID):
        await callback.answer()
        return
    import pending_jobs
    action, jid = callback.data.split(":", 1)
    job = pending_jobs.pop_failed(jid)
    await callback.answer()
    if job is None:
        await callback.message.answer("ℹ️ این مورد دیگر در فهرست ناموفق نیست.")
        return
    if action == "pjd":
        await callback.message.answer(f"🗑 درخواست کاربر `{job.get('user_id')}` از فهرست ناموفق حذف شد.")
        return
    await runtime_state.job_queue.put(job)
    where = ("وارد صف پردازش شد." if is_open() else
             "چون خارج از ساعت کاری/قطعی هستیم در صف ماندگار می‌رود "
             "(ثبت فوری: /offhours_submit " + str(job.get("user_id")) + ").")
    await callback.message.answer(f"🔁 درخواست کاربر `{job.get('user_id')}` ({pending_jobs.label(job)}) {where}")
