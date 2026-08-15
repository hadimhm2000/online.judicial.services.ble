"""
جمع‌آوری خودکار بخش‌های پیام طولانی تلگرام.

وقتی تلگرام پیام بلندی را به چند بخش تقسیم می‌کند،
این ماژول تمام بخش‌ها را جمع کرده و یک متن کامل تحویل می‌دهد.

کاربرد: هر handler متنی (لایحه، اظهارنامه، اعلام وکالت)
باید به جای ذخیره مستقیم message.text، از collect_text_part استفاده کند.
"""

import asyncio
import os
import time
import logging
from typing import Dict, Callable, Awaitable, Any

logger = logging.getLogger(__name__)

# ذخیره تایمرهای فعال: user_id -> asyncio.Task
_active_timers: Dict[int, asyncio.Task] = {}

# حداکثر تاخیر جمع‌آوری (ثانیه) — بعد از آخرین بخش پیام
COLLECT_DELAY = 3.0


MAX_IMAGES_PER_TITLE = 15
"""حداکثر تعداد تصویر مجاز در هر عنوان پیوست."""


def _cancel_timer(user_id: int):
    """لغو تایمر قبلی کاربر اگر وجود دارد."""
    task = _active_timers.pop(user_id, None)
    if task and not task.done():
        task.cancel()
        try:
            task.result()
        except (asyncio.CancelledError, Exception):
            pass


async def collect_text_part(
    user_id: int,
    chat_id: int,
    text: str,
    state,       # FSMContext
    bot,         # Bot
    on_complete: Callable[[str, Any, Any, int], Awaitable[None]],
    delay: float = COLLECT_DELAY,
    first_part_reply: str = None,
    is_editing: bool = False):
    """
    یک بخش از پیام را دریافت و جمع‌آوری می‌کند.

    وقتی هیچ بخش جدیدی برای مدت `delay` ثانیه دریافت نشود،
    تابع `on_complete` با متن کامل فراخوانی می‌شود.

    on_complete(final_text, state, bot, chat_id) -> None
    """
    if not text or not text.strip():
        return

    data = await state.get_data()
    existing = data.get("_pending_text", "")
    combined = (existing + "\n" + text) if existing else text.strip()

    await state.update_data(
        _pending_text=combined,
        _last_text_part_time=time.time(),
        _text_is_editing=is_editing)

    # لغو تایمر قبلی
    _cancel_timer(user_id)

    # فقط به بخش اول پاسخ دهیم
    if not existing and first_part_reply:
        try:
            await bot.send_message(chat_id, first_part_reply)
        except Exception as e:
            logger.warning(f"خطا در ارسال پاسخ بخش اول: {e}")

    # تایمر جدید برای نهایی‌سازی
    async def _finalize():
        await asyncio.sleep(delay)
        _active_timers.pop(user_id, None)

        try:
            # خواندن مجدد state برای اطمینان از آخرین مقدار
            data = await state.get_data()
            final_text = data.get("_pending_text", "")
            was_editing = data.get("_text_is_editing", False)

            if not final_text:
                return

            # پاکسازی فیلدهای موقت
            await state.update_data(
                _pending_text="",
                _last_text_part_time=0,
                _text_is_editing=False)

            # فراخوانی callback نهایی
            await on_complete(final_text, state, bot, chat_id, was_editing)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"خطا در نهایی‌سازی متن جمع‌آوری شده (user={user_id}): {e}", exc_info=True)
            try:
                await bot.send_message(
                    chat_id,
                    "⚠️ خطایی در پردازش متن رخ داد. لطفاً دوباره تلاش کنید."
                )
            except Exception:
                pass

    _active_timers[user_id] = asyncio.create_task(_finalize())


def check_image_limit(current_count: int) -> bool:
    """
    بررسی آیا تعداد تصاویر از حد مجاز عبور کرده یا خیر.
    بازگشت: True اگر هنوز جا دارد، False اگر پر شده.
    """
    return current_count < MAX_IMAGES_PER_TITLE


async def process_docx_input(
    message,
    user_id: int,
    chat_id: int,
    state,
    bot,
    on_complete: Callable,
    text_state_key: str = "",
    html_state_key: str = "",
    extra_state_updates: dict = None,
    processing_msg: str = "⏳ در حال پردازش فایل ورد..."):
    """
    دریافت فایل .docx از بله، استخراج متن و HTML،
    و فراخوانی on_complete با نتایج.

    on_complete(final_text: str, final_html: str, state, bot, chat_id, was_editing: bool)

    در state ذخیره می‌شود:
      - text_state_key: متن خام (برای پیش‌نمایش پیام‌رسان)
      - html_state_key: HTML با فرمت (برای ادیتور سامانه)
    """
    from docx_parser import (
        download_docx_from_bale,
        validate_docx,
        docx_to_html,
        docx_to_plain_text)

    await bot.send_message(chat_id, processing_msg)

    # دانلود فایل
    filepath = await download_docx_from_bale(bot, message.document.file_id, user_id)
    if not filepath:
        await bot.send_message(chat_id, "❌ خطا در دانلود فایل. لطفاً دوباره تلاش کنید.")
        return

    # اعتبارسنجی
    is_valid, error_msg = validate_docx(filepath)
    if not is_valid:
        await bot.send_message(chat_id, f"❌ {error_msg}")
        # حذف فایل نامعتبر
        try:
            os.remove(filepath)
        except OSError:
            pass
        return

    # استخراج HTML و متن خام
    try:
        html_content = docx_to_html(filepath)
        plain_text = docx_to_plain_text(filepath)
    except Exception as e:
        logger.error(f"خطا در پارس ورد (user={user_id}): {e}")
        await bot.send_message(chat_id, "❌ خطا در خواندن فایل ورد. لطفاً مطمئن شوید فایل معتبر است.")
        try:
            os.remove(filepath)
        except OSError:
            pass
        return

    # حذف فایل موقت
    try:
        os.remove(filepath)
    except OSError:
        pass

    if not plain_text.strip():
        await bot.send_message(chat_id, "❌ فایل ورد خالی است.")
        return

    # ذخیره در state
    state_updates = {}
    if text_state_key:
        state_updates[text_state_key] = plain_text
    if html_state_key:
        state_updates[html_state_key] = html_content
    if extra_state_updates:
        state_updates.update(extra_state_updates)
    await state.update_data(**state_updates)

    # فراخوانی callback
    char_count = len(plain_text)
    await on_complete(plain_text, html_content, state, bot, chat_id, False, char_count)
