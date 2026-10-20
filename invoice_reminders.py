"""
invoice_reminders.py — یادآوری فاکتورهای پرداخت‌نشده (۱۴۰۵/۰۷)
══════════════════════════════════════════════════════════════════════════════

هدف: پولی که کاربر برای پرداختش آمده ولی فاکتور را رها کرده، برگردد.

منبع: دفتر «پرونده‌های در انتظار امضا و پرداخت» (pending_cases.json) — همان
پرونده‌هایی که فاکتورشان ارسال شده و هنوز پرداخت نشده (لایحه، اظهارنامه، چک،
اعلام وکالت، اصلاح قرارداد، دعاوی اعتراضی).

دو یادآوری برای هر پرونده، هر کدام فقط یک بار:
  ۱) first: «reminder.first_hours» ساعت (پیش‌فرض ۱) پس از ارسال فاکتور
     (فقط تا ۲۴ ساعت اول؛ پرونده‌های قدیمی‌تر یادآوری اول نمی‌گیرند).
  ۲) last : در ۲۴ ساعت آخر پیش از حذف پرونده از منوی پرونده‌های در انتظار
     (لایحه و اعلام وکالت ۴ روز، سایر موارد ۳۰ روز — pending_cases.visible_days).

دکمهٔ پیام همان «pc:pay:<کد رهگیری>» منوی پرونده‌های در انتظار است؛ یعنی فاکتور
با همان مسیر موجود (کیف پول، کارت‌به‌کارت، ادامهٔ خودکار درج امضا) ساخته می‌شود.

پیام‌ها فقط بین QUIET_END_HOUR و QUIET_START_HOUR به وقت تهران ارسال می‌شوند.
خاموش/روشن: reminder.enabled در تنظیمات پنل.
"""
import asyncio
import datetime
import json
import logging
import os

from aiogram import Bot
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import bot_settings
import pending_cases
import runtime_state
from config import ADMIN_ID
from final_print import TEHRAN_TZ

logger = logging.getLogger(__name__)

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "invoice_reminders_state.json")

CHECK_INTERVAL_SECONDS = 600
FIRST_HOURS_DEFAULT = 1
FIRST_MAX_HOURS = 24          # یادآوری اول برای فاکتورهای قدیمی‌تر از این ارسال نمی‌شود
LAST_WINDOW_HOURS = 24        # یادآوری آخر در این بازه پیش از حذف از منو
QUIET_START_HOUR = 21         # از این ساعت ...
QUIET_END_HOUR = 9            # ... تا این ساعت پیامی ارسال نمی‌شود
SEND_GAP_SECONDS = 0.2

STAGE_FIRST = "first"
STAGE_LAST = "last"

_SERVICE_LABELS = {
    "LAVAYEH": "لایحه",
    "EZHHARNAMEH": "اظهارنامه",
    "EALAM_VAKALAHT": "اعلام وکالت",
    "TAJDID_NAZAR": "دعاوی اعتراضی",
    "CHECK": "دادخواست",
    "CONTRACT_FIX": "اصلاح قرارداد",
}

# در این stateها کاربر وسط روند امضاست — پیام پرداخت پرونده‌ای دیگر گیجش می‌کند
_SIGN_STATE_MARKERS = ("_sign_",)


def _now() -> datetime.datetime:
    return datetime.datetime.now(TEHRAN_TZ)


def _load_state() -> dict:
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_state(data: dict):
    try:
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, STATE_FILE)
    except Exception as e:
        logger.error(f"[INVOICE_REMINDER] خطا در ذخیرهٔ وضعیت: {e}")


def _key(it: dict) -> str:
    return f"{it.get('user_id')}:{it.get('tracking_code')}"


def _is_quiet(now: datetime.datetime) -> bool:
    return now.hour >= QUIET_START_HOUR or now.hour < QUIET_END_HOUR


def _unpaid_open_items(now: datetime.datetime) -> list:
    """پرونده‌های پرداخت‌نشدهٔ قابل نمایش در منو با مبلغ مشخص."""
    with pending_cases._lock:
        items = [dict(it) for it in pending_cases._load()["items"]]
    return [it for it in items
            if pending_cases._is_visible(it, now)
            and not it.get("paid")
            and int(it.get("final_fee") or 0) > 0
            and it.get("user_id") != ADMIN_ID]


def due_stage(it: dict, now: datetime.datetime, sent: list, first_hours: int) -> str | None:
    """کدام یادآوری برای این پرونده موعدش رسیده (یا None)."""
    age = now - pending_cases._registered(it)
    expires = pending_cases._registered(it) + datetime.timedelta(
        days=pending_cases.visible_days(it.get("service_type")))
    left = expires - now
    if STAGE_LAST not in sent and datetime.timedelta(0) < left <= datetime.timedelta(hours=LAST_WINDOW_HOURS):
        return STAGE_LAST
    if STAGE_FIRST not in sent and STAGE_LAST not in sent \
            and datetime.timedelta(hours=first_hours) <= age < datetime.timedelta(hours=FIRST_MAX_HOURS):
        return STAGE_FIRST
    return None


def _fa_time(dt: datetime.datetime) -> str:
    try:
        from history_handlers import _fa_date
        day = _fa_date(dt.isoformat())
    except Exception:
        day = dt.strftime("%Y-%m-%d")
    return f"{day} ساعت {dt.strftime('%H:%M')}"


def build_message(it: dict, stage: str) -> tuple[str, InlineKeyboardMarkup]:
    tc = it["tracking_code"]
    label = _SERVICE_LABELS.get(it.get("service_type"), "پرونده")
    toman = int(it.get("final_fee") or 0) // 10
    head = f"فاکتور {label} شما (کد رهگیری `{tc}`) به مبلغ *{toman:,} تومان* هنوز پرداخت نشده است."
    if stage == STAGE_LAST:
        expires = pending_cases._registered(it) + datetime.timedelta(
            days=pending_cases.visible_days(it.get("service_type")))
        text = (f"⏳ *آخرین یادآوری پرداخت*\n\n{head}\n\n"
                f"این پرونده فقط تا {_fa_time(expires)} قابل پرداخت است و پس از آن از بخش "
                f"«پرونده‌های در انتظار امضا و پرداخت» حذف می‌شود.")
    else:
        text = (f"💳 *یادآوری پرداخت*\n\n{head}\n\n"
                "برای ادامهٔ روند، روی دکمهٔ زیر بزنید؛ پس از پرداخت، مرحلهٔ درج امضا "
                "به‌صورت خودکار آغاز می‌شود.")
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"💳 پرداخت ({toman:,} تومان)", callback_data=f"pc:pay:{tc}")]])
    return text, kb


async def _busy(bot: Bot, uid: int) -> bool:
    """کاربر وسط امضا یا رسیدش در بررسی مدیر است."""
    if uid in (getattr(runtime_state, "pending_admin_payment_review", None) or {}):
        return True
    try:
        dp = getattr(runtime_state, "dp", None)
        if dp is not None and getattr(bot, "id", None):
            raw = await dp.storage.get_state(StorageKey(bot_id=bot.id, chat_id=uid, user_id=uid)) or ""
            return any(m in raw for m in _SIGN_STATE_MARKERS)
    except Exception as e:
        logger.warning(f"[INVOICE_REMINDER] خواندن state کاربر {uid}: {e}")
    return False


async def run_once(bot: Bot, now: datetime.datetime | None = None) -> int:
    """یک دور بررسی؛ تعداد یادآوری‌های ارسال‌شده."""
    now = now or _now()
    if not bot_settings.get_bool("reminder.enabled", True) or _is_quiet(now):
        return 0
    first_hours = max(1, bot_settings.get_int("reminder.first_hours", FIRST_HOURS_DEFAULT))
    state = _load_state()
    items = _unpaid_open_items(now)

    due = [(it, st) for it in items
           if (st := due_stage(it, now, state.get(_key(it), []), first_hours))]
    # پرداخت‌های تأییدشده در پنل پیش از ارسال اعمال شوند
    for uid in {it["user_id"] for it, _ in due}:
        await pending_cases.sync_with_panel(uid)

    sent_count = 0
    for it, stage in due:
        uid = it["user_id"]
        fresh = pending_cases.is_open(uid, it["tracking_code"])
        if not fresh or fresh.get("paid") or await _busy(bot, uid):
            continue
        text, kb = build_message(fresh, stage)
        try:
            await bot.send_message(uid, text, reply_markup=kb, parse_mode="Markdown")
            sent_count += 1
        except Exception as e:
            logger.warning(f"[INVOICE_REMINDER] ارسال به {uid} ناموفق: {e}")
        # موفق یا ناموفق (مثلاً ربات مسدود شده) — تکرار نمی‌شود
        state.setdefault(_key(it), []).append(stage)
        await asyncio.sleep(SEND_GAP_SECONDS)

    # کلیدهای پرونده‌های بسته‌شده پاک شوند
    open_keys = {_key(it) for it in items}
    state = {k: v for k, v in state.items() if k in open_keys}
    _save_state(state)
    if sent_count:
        logger.info(f"[INVOICE_REMINDER] {sent_count} یادآوری پرداخت ارسال شد.")
    return sent_count


async def invoice_reminder_loop(bot: Bot, first_delay_seconds: int = 240):
    await asyncio.sleep(first_delay_seconds)   # پس از گرم شدن پنل
    while True:
        try:
            await run_once(bot)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[INVOICE_REMINDER] خطا در حلقه: {e}", exc_info=True)
        try:
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            break
