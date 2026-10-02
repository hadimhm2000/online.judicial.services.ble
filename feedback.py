"""
feedback.py — نظرسنجی ۱ تا ۵ ستاره پس از تحویل نتیجه به کاربر
══════════════════════════════════════════════════════════════════════════════

هر بار ربات فایلی (چاپ لایحه، اظهارنامه، نتیجهٔ استعلام و ...) برای کاربر
می‌فرستد، bale_file_sender ثبتش می‌کند و این ماژول ASK_DELAY_SECONDS بعد از
آخرین فایل، یک پیام کوتاه «از خدمات ما راضی بودید؟» با دکمه‌های ۱ تا ۵ ستاره
می‌فرستد. به هر کاربر حداکثر یک‌بار در MIN_GAP_HOURS ساعت سؤال می‌شود.

امتیاز در پنل (مدل Feedback) ثبت می‌شود. امتیاز ۱ یا ۲ همان لحظه به مدیر
اطلاع داده می‌شود تا با /send پیگیری کند.

خاموش‌کردن از پنل: تنظیم rating.enabled = false
"""
import asyncio
import json
import logging
import os
import time

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

import bot_settings
from config import ADMIN_ID

logger = logging.getLogger(__name__)

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "feedback_state.json")
ASK_DELAY_SECONDS = 10 * 60
MIN_GAP_HOURS = 24
LOW_RATING = 2

_state = {"pending": {}, "last_asked": {}}

feedback_router = Router()


def _load():
    global _state
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            _state = {"pending": data.get("pending", {}), "last_asked": data.get("last_asked", {})}
        except Exception as e:
            logger.error(f"[FEEDBACK] خطا در خواندن وضعیت: {e}")


def _save():
    tmp = STATE_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_state, f, ensure_ascii=False)
        os.replace(tmp, STATE_FILE)
    except Exception as e:
        logger.error(f"[FEEDBACK] خطا در ذخیرهٔ وضعیت: {e}")


def schedule(uid, context: str = ""):
    """پس از تحویل فایل صدا زده می‌شود؛ هرگز استثنا نمی‌دهد."""
    try:
        if not bot_settings.get_bool("rating.enabled", True):
            return
        key = str(uid)
        last = _state["last_asked"].get(key, 0)
        if time.time() - last < MIN_GAP_HOURS * 3600:
            return
        _state["pending"][key] = {"due": time.time() + ASK_DELAY_SECONDS, "context": (context or "")[:200]}
        _save()
    except Exception as e:
        logger.error(f"[FEEDBACK] schedule ناموفق: {e}")


def _stars_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"{n}⭐", callback_data=f"fb:{n}") for n in range(5, 0, -1)
    ]])


async def feedback_loop(bot: Bot, interval_seconds: int = 60):
    _load()
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            now = time.time()
            due = [(uid, p) for uid, p in list(_state["pending"].items()) if p.get("due", 0) <= now]
            for uid, p in due:
                _state["pending"].pop(uid, None)
                _state["last_asked"][uid] = now
                try:
                    await bot.send_message(
                        int(uid),
                        "🙏 از اینکه از خدمات ما استفاده کردید سپاسگزاریم.\n"
                        "میزان رضایت شما از این خدمت چقدر بود؟",
                        reply_markup=_stars_kb())
                except Exception as e:
                    logger.warning(f"[FEEDBACK] ارسال نظرسنجی به {uid} ناموفق: {e}")
                _state.setdefault("asked_context", {})[uid] = p.get("context", "")
            if due:
                cutoff = now - 30 * 86400
                _state["last_asked"] = {k: v for k, v in _state["last_asked"].items() if v >= cutoff}
                _save()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[FEEDBACK] خطا در حلقهٔ نظرسنجی: {e}")


@feedback_router.callback_query(F.data.regexp(r"^fb:[1-5]$"))
async def on_rating(callback: CallbackQuery, bot: Bot):
    rating = int(callback.data.split(":")[1])
    uid = callback.from_user.id
    context = _state.get("asked_context", {}).pop(str(uid), "")
    _save()
    await callback.answer("ممنون از نظر شما 🌹")
    try:
        await callback.message.edit_text(f"🙏 امتیاز شما ({rating} از ۵) ثبت شد. سپاسگزاریم.")
    except Exception:
        pass
    from panel_sync import submit_feedback
    submit_feedback(uid, callback.from_user.full_name, rating, context)
    if rating <= LOW_RATING:
        try:
            await bot.send_message(
                ADMIN_ID,
                f"⚠️ امتیاز پایین ({rating} از ۵)\n"
                f"کاربر: {callback.from_user.full_name} — {uid}\n"
                + (f"آخرین فایل تحویلی: {context}\n" if context else "")
                + f"\nپیگیری: /send {uid}")
        except Exception:
            pass
