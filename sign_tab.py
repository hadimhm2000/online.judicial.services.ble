"""
sign_tab.py — اجرای اولویت‌دار «ناوبری امضا» در تب اختصاصی هر کاربر.

طبق دستور کارفرما: ناوبری امضا در تمام بخش‌ها (لایحه/چک/اعسار، اظهارنامه،
دعاوی اعتراضی) اولویت دارد — درست مانند «استعلام پیوست‌های لایحه»
(PRE_CHECK) که در تب جدید و بدون انتظار برای تسک در حال اجرا انجام می‌شود.

روال:
  ۱. browser_worker تسک‌های امضا (SIGN_TASK_TYPES) را با asyncio.create_task
     و بدون معطل‌شدن پشت ثبت‌های طولانی روی sana_page اجرا می‌کند.
  ۲. هر کاربر در روند امضا یک تب اختصاصی دارد (runtime_state.sign_pages)؛
     بین فاز «انتخاب شخص» و «ارسال کد» و «ثبت کد» صفحه عوض نمی‌شود.
  ۳. برای جلوگیری از تداخل، در هر لحظه فقط یک عملیات امضا اجرا می‌شود
     (sign_semaphore). اگر کسی در حال امضا یا در نوبت باشد، به کاربر پیام
     «اشخاص دیگری در نوبت امضا هستند ... لطفاً در دسترس باشید» ارسال می‌شود.
  ۴. تب کاربر وقتی دیگر روند امضای فعالی ندارد یا SIGN_TAB_IDLE_SECONDS
     بی‌اقدام مانده، توسط sweeper بسته می‌شود.

توابع سناریوهای امضا (lavayeh_sign_scenario / ezhharnameh_sign_scenario)
به‌جای runtime_state.sana_page از active_page() استفاده می‌کنند که داخل
تسک امضا تب اختصاصی و در سایر موارد (سازگاری با قبل) همان sana_page است.
"""

import asyncio
import contextvars
import logging
import time

from aiogram import Bot

import runtime_state

# انواع تسکی که در تب اختصاصی و با اولویت اجرا می‌شوند (تعریف در runtime_state)
SIGN_TASK_TYPES = runtime_state.SIGN_TASK_TYPES

# بستن تب امضای بی‌اقدام پس از ۶۰ دقیقه (هم‌راستا با مهلت ۶۰ دقیقه‌ای امضا)
SIGN_TAB_IDLE_SECONDS = 60 * 60
SWEEP_INTERVAL_SECONDS = 120

# در هر لحظه فقط یک عملیات امضا روی سامانه
_sign_semaphore = asyncio.Semaphore(1)

# کاربرانی که تسک امضایشان در حال اجرا/انتظار است (به ترتیب ورود)
_sign_line: list = []

# تب فعال تسک امضای جاری (per-asyncio-task)
_active_sign_page: contextvars.ContextVar = contextvars.ContextVar(
    "active_sign_page", default=None)

# آخرین زمان استفاده از تب هر کاربر
_last_used: dict = {}

_sweeper_started = False

QUEUE_NOTICE = (
    "⏳ *در حال حاضر اشخاص دیگری در نوبت امضا هستند.*\n\n"
    "{ahead_line}"
    "مورد شما در کمتر از چند دقیقهٔ دیگر انجام خواهد شد؛ "
    "لطفاً در دسترس باشید. 🙏"
)


def active_page():
    """صفحهٔ مرورگرِ عملیات امضای جاری — تب اختصاصی کاربر داخل تسک امضا،
    وگرنه (برای سازگاری با فراخوانی‌های قدیمی) همان sana_page مشترک."""
    page = _active_sign_page.get()
    if page is not None:
        try:
            if not page.is_closed():
                return page
        except Exception:
            pass
    return runtime_state.sana_page


def _page_usable(page) -> bool:
    if page is None:
        return False
    try:
        if page.is_closed():
            return False
        # بعد از بازسازی مرورگر، تب‌های کانتکست قبلی دیگر معتبر نیستند
        return page.context is runtime_state.browser_context
    except Exception:
        return False


async def get_sign_page(user_id: int):
    """تب اختصاصی امضای کاربر (در صورت نبود یا بسته‌بودن، تب جدید باز
    می‌شود). اگر باز کردن تب ممکن نبود، sana_page مشترک برگردانده می‌شود."""
    pages = runtime_state.sign_pages
    page = pages.get(user_id)
    if _page_usable(page):
        _last_used[user_id] = time.monotonic()
        return page

    pages.pop(user_id, None)
    ctx = runtime_state.browser_context
    if ctx is None:
        return runtime_state.sana_page
    try:
        page = await ctx.new_page()
        pages[user_id] = page
        _last_used[user_id] = time.monotonic()
        logging.info(f"[SIGN_TAB] تب اختصاصی امضا برای کاربر {user_id} باز شد")
        return page
    except Exception as e:
        logging.warning(f"[SIGN_TAB] باز کردن تب امضا ناموفق ({e}) — استفاده از تب اصلی")
        return runtime_state.sana_page


async def close_sign_page(user_id: int):
    page = runtime_state.sign_pages.pop(user_id, None)
    _last_used.pop(user_id, None)
    if page is None or page is runtime_state.sana_page:
        return
    try:
        if not page.is_closed():
            await page.close()
        logging.info(f"[SIGN_TAB] تب امضای کاربر {user_id} بسته شد")
    except Exception:
        pass


def _has_active_sign(user_id: int) -> bool:
    return (user_id in runtime_state.pending_lavayeh_sign
            or user_id in runtime_state.pending_ezhhar_sign
            or user_id in runtime_state.pending_tn_sign
            or user_id in _sign_line)


async def _sweeper():
    while True:
        await asyncio.sleep(SWEEP_INTERVAL_SECONDS)
        try:
            now = time.monotonic()
            for uid in list(runtime_state.sign_pages.keys()):
                if uid in _sign_line:
                    continue  # در حال اجرا/انتظار
                idle = now - _last_used.get(uid, now)
                if not _has_active_sign(uid) or idle > SIGN_TAB_IDLE_SECONDS:
                    await close_sign_page(uid)
        except Exception as e:
            logging.warning(f"[SIGN_TAB] خطا در پاکسازی تب‌های امضا: {e}")


def _ensure_sweeper():
    global _sweeper_started
    if not _sweeper_started:
        _sweeper_started = True
        asyncio.create_task(_sweeper())


async def run_sign_task(data: dict, bot: Bot, handler):
    """اجرای یک تسک امضا با اولویت، در تب اختصاصی کاربر و به‌صورت نوبتی.

    handler: coroutine function(data, bot) — همان _process_*_sign_* موجود.
    """
    _ensure_sweeper()
    user_id = data.get("user_id")

    ahead = len(_sign_line)  # افراد در حال امضا/در نوبتِ جلوتر
    _sign_line.append(user_id)
    try:
        if ahead > 0 or _sign_semaphore.locked():
            ahead_line = (f"👥 تعداد نفرات جلوتر از شما: *{max(ahead, 1)}*\n\n")
            try:
                await bot.send_message(
                    user_id, QUEUE_NOTICE.format(ahead_line=ahead_line),
                    parse_mode="Markdown")
            except Exception:
                pass
            logging.info(f"[SIGN_TAB] کاربر {user_id} در نوبت امضا ({ahead} نفر جلوتر)")

        async with _sign_semaphore:
            page = await get_sign_page(user_id)
            token = _active_sign_page.set(page)
            try:
                await handler(data, bot)
            finally:
                _active_sign_page.reset(token)
                _last_used[user_id] = time.monotonic()
    finally:
        try:
            _sign_line.remove(user_id)
        except ValueError:
            pass
