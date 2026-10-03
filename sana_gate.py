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

from aiogram import Bot, F, Router, types
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

import runtime_state
from config import ADMIN_ID
from working_hours import TEHRAN_TZ, START_HOUR, END_HOUR

logger = logging.getLogger(__name__)

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sana_gate_state.json")

_state = {
    "outage": False,
    "outage_since": None,
    "browser_closed": False,
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
        "موارد شما در نوبت می‌باشد و ابتدای ساعت کاری بعدی (ساعت {start}:00) "
        "به‌صورت خودکار در سامانه ثبت می‌گردد.\n"
        "نیازی به ارسال مجدد اطلاعات یا پرداخت نیست. باتشکر"
    ),
    "gate.released": "▶️ ثبت موارد شما در سامانه آغاز شد.",
    "gate.inquiry_closed_offhours": (
        "⛔️ *خارج از ساعت کاری*\n\n"
        "استعلام فقط در ساعت کاری ({start}:00 الی {end}:00) انجام می‌شود.\n"
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
    "محاسبه تمبر", "ابزار فایل", "خسارت تأخیر", "هزینه دادرسی",
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


def is_working_hours(now: datetime.datetime | None = None) -> bool:
    now = now or datetime.datetime.now(TEHRAN_TZ)
    return START_HOUR <= now.hour < END_HOUR


def is_outage() -> bool:
    return bool(_state["outage"])


def browser_closed_by_admin() -> bool:
    return bool(_state["browser_closed"])


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
        return is_outage() or browser_closed_by_admin()
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
    return _text("gate.inquiry_closed_offhours").format(start=START_HOUR, end=END_HOUR)


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
        _log_offhours(job.get("user_id"), _job_label(job), now_iso)
    _save()
    uid = job.get("user_id")
    logger.info(
        f"[SANA_GATE] تسک {job.get('task_type') or job.get('query_type')} کاربر {uid} "
        f"به صف رفت ({reason}) — اندازهٔ صف: {deferred_count()}")
    if not uid:
        return
    if reason == "outage":
        text = _text("gate.outage_queued")
    else:
        text = _text("gate.offhours_queued").format(start=START_HOUR, end=END_HOUR)
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
}


def _job_label(job: dict) -> str:
    tt = job.get("task_type")
    if tt:
        return _TASK_LABELS.get(tt, str(tt).replace("_", " "))
    return str(job.get("query_type") or "نامشخص")


def _log_offhours(uid, label: str, at_iso: str):
    """ثبت در سابقهٔ خارج از ساعت کاری و حذف موارد قدیمی‌تر از OFFHOURS_LOG_DAYS روز."""
    log = _state.setdefault("offhours_log", [])
    log.append({"uid": uid, "type": label, "at": at_iso, "status": "queued"})
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


async def gate_loop(bot: Bot, interval_seconds: int = 30):
    """تسک پس‌زمینه: ابتدای ساعت کاری (یا پس از رفع قطعی) صف را آزاد می‌کند."""
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            if not is_open():
                continue
            if browser_closed_by_admin():
                # ساعت کاری شروع شد — مرورگر بستهٔ مدیر دوباره مجاز به باز شدن است
                _state["browser_closed"] = False
                _save()
                try:
                    await bot.send_message(
                        ADMIN_ID,
                        "🟢 ساعت کاری شروع شد — مرورگر دوباره باز می‌شود. "
                        "لطفاً منتظر درخواست لاگین بمانید.")
                except Exception:
                    pass
                try:
                    from scenarios import ensure_browser_alive
                    await ensure_browser_alive(bot, notify_admin=False)
                except Exception as e:
                    logger.error(f"[SANA_GATE] خطا در باز کردن مرورگر: {e}")
            if _state["deferred"]:
                await release(bot)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[SANA_GATE] خطا در gate_loop: {e}")


# ── بستن مرورگر توسط مدیر ─────────────────────────────────────────────────

def _pending_sign_users() -> set:
    users = set()
    for name in ("pending_lavayeh_sign", "pending_ezhhar_sign", "pending_tn_sign"):
        store = getattr(runtime_state, name, None)
        if isinstance(store, dict):
            users.update(store.keys())
    return users


async def close_browser():
    """مرورگر پلی‌رایت را می‌بندد (بدون ری‌استارت ربات)."""
    async with runtime_state.browser_relaunch_lock:
        _state["browser_closed"] = True
        _save()
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


def _status_text() -> str:
    lines = [
        "📟 *وضعیت ورود به سامانه*",
        f"ساعت کاری: {START_HOUR}:00 الی {END_HOUR}:00 — "
        + ("داخل ساعت کاری ✅" if is_working_hours() else "خارج از ساعت کاری 🌙"),
        "حالت قطعی سامانه: " + ("روشن ⚠️" if is_outage() else "خاموش ✅"),
        "مرورگر: " + ("بسته‌شده توسط مدیر 🔒" if browser_closed_by_admin() else "فعال"),
        f"درخواست‌های در صف: {deferred_count()}",
        "",
        "دستورات: /outage_on  /outage_off  /browser_close  /browser_open  /gate",
        "خارج از ساعت کاری: /offhours  /offhours_submit <آیدی کاربر>",
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
            f"(ساعت کاری {START_HOUR}:00 الی {END_HOUR}:00).")
        return
    force = "force" in (message.text or "")
    signing = _pending_sign_users()
    if signing and not force:
        await message.answer(
            f"⚠️ {len(signing)} کاربر هنوز در مرحلهٔ امضا هستند و با بستن مرورگر "
            "امضایشان ناتمام می‌ماند.\n\nاگر مطمئن هستید: /browser_close force")
        return
    await close_browser()
    await message.answer(
        "🔒 مرورگر بسته شد. تا ابتدای ساعت کاری بعدی هیچ درخواستی وارد سامانه "
        "نمی‌شود و درخواست‌ها در صف می‌مانند.\n"
        f"ساعت {START_HOUR}:00 مرورگر خودکار باز می‌شود (یا زودتر: /browser_open).")


@gate_router.message(Command("browser_open"), _is_admin)
async def browser_open_cmd(message: types.Message, bot: Bot):
    _state["browser_closed"] = False
    _save()
    await message.answer("🔓 مرورگر در حال باز شدن است — لطفاً منتظر درخواست لاگین بمانید.")
    try:
        from scenarios import ensure_browser_alive
        await ensure_browser_alive(bot, notify_admin=False)
    except Exception as e:
        await message.answer(f"❌ خطا در باز کردن مرورگر: {str(e)[:200]}")


# ── ⭐ درخواست‌های خارج از ساعت کاری (۱۴۰۵/۰۷) ─────────────────────────────

_STATUS_FA = {"queued": "در صف", "released": "ثبت‌شده در ساعت کاری", "admin_submitted": "ثبت توسط مدیر"}


def _fmt_at(iso: str) -> str:
    try:
        return datetime.datetime.fromisoformat(iso).strftime("%m/%d %H:%M")
    except Exception:
        return str(iso)[:16]


def offhours_report() -> tuple:
    """متن گزارش /offhours و کیبورد دکمه‌های «ثبت در سامانه» برای هر کاربر در صف."""
    by_user = deferred_by_user()
    lines = [f"🌙 *درخواست‌های خارج از ساعت کاری* ({START_HOUR}:00 الی {END_HOUR}:00 ساعت کاری)", ""]
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

    rows = [[InlineKeyboardButton(text=f"▶️ ثبت در سامانه: {uid} ({len(items)})",
                                  callback_data=f"ohs:{uid}")]
            for uid, items in list(by_user.items())[:30] if uid is not None]
    kb = InlineKeyboardMarkup(inline_keyboard=rows) if rows else None
    return "\n".join(lines), kb


async def _submit_and_report(uid_text: str) -> str:
    uid_text = (uid_text or "").strip()
    if not uid_text.lstrip("-").isdigit():
        return "⚠️ آیدی کاربر نامعتبر است. مثال: /offhours_submit 123456789"
    if is_outage():
        return "⚠️ حالت «قطعی سامانه» روشن است؛ ابتدا /outage_off را بزنید."
    if browser_closed_by_admin():
        return "⚠️ مرورگر توسط مدیر بسته شده است؛ ابتدا /browser_open را بزنید."
    count = await submit_user_now(int(uid_text))
    if not count:
        return f"ℹ️ درخواستی از کاربر `{uid_text}` در صف خارج از ساعت کاری نیست."
    return f"▶️ {count} درخواست کاربر `{uid_text}` برای ثبت در سامانه وارد صف پردازش شد."


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
