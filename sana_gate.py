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

from aiogram import Bot, Router, types
from aiogram.filters import Command

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
}

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


def should_defer(job: dict) -> bool:
    if not isinstance(job, dict):
        return False
    if job.get("task_type") in runtime_state.SIGN_TASK_TYPES:
        return False
    return not is_open()


def is_inquiry_context(message: types.Message, raw_state: str | None) -> bool:
    """پیام مربوط به شروع/ادامهٔ استعلام است؟ (استعلام همان لحظه به سامانه نیاز دارد)"""
    if (message.text or "").strip() in INQUIRY_ENTRY_TEXTS:
        return True
    return raw_state in INQUIRY_STATES


def closed_inquiry_text() -> str:
    if is_outage():
        return _text("gate.inquiry_closed_outage")
    return _text("gate.inquiry_closed_offhours").format(start=START_HOUR, end=END_HOUR)


# ── صف ماندگار ────────────────────────────────────────────────────────────

async def defer(job: dict, bot: Bot):
    """تسک را به صف ماندگار می‌برد و به کاربر اطلاع می‌دهد."""
    reason = "outage" if is_outage() else "offhours"
    _state["deferred"].append({
        "job": job,
        "deferred_at": datetime.datetime.now(TEHRAN_TZ).isoformat(),
        "reason": reason,
    })
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


async def release(bot: Bot) -> int:
    """همهٔ تسک‌های صف را به‌ترتیب به job_queue برمی‌گرداند."""
    items = list(_state["deferred"])
    if not items:
        return 0
    _state["deferred"] = []
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
