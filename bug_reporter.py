"""
مسیر شناسایی و گزارش باگ + لاگ فایل مقاوم (Bug reporting & resilient logging).

اهداف:
  ۱. هر زمان ربات به باگ/استثناء خورد، گزارش کامل (دلیل + جزئیات + traceback +
     اسکرین‌شات صفحه + URL فعلی + کاربر/کد رهگیری + زمینه) برای مدیر ارسال شود.
  ۲. همه‌ی خطاها و هشدارها به‌صورت مداوم در فایل لاگ نوشته شوند تا قابل آپلود
     مستمر باشند (RotatingFileHandler → logs/bot.log و logs/bugs.log).
  ۳. یک گاردِ مقاوم (`guard`) که هر استثنائی را می‌گیرد، گزارش می‌کند و اجازه
     می‌دهد ربات بدون کرش مسیر خود را ادامه دهد.

این ماژول هرگز نباید خودش باعث کرش شود؛ همه‌ی مسیرها در try/except امن‌اند.
"""

import os
import sys
import time
import json
import asyncio
import logging
import traceback
import datetime
from logging.handlers import RotatingFileHandler
from typing import Optional, Callable, Any

try:
    from config import ADMIN_ID
except Exception:  # pragma: no cover - در تست‌ها config ممکن است نباشد
    ADMIN_ID = None


# =========================================================
# پیکربندی مسیر لاگ‌ها
# =========================================================
LOG_DIR = os.environ.get("BOT_LOG_DIR", "logs")
MAIN_LOG_FILE = os.path.join(LOG_DIR, "bot.log")
BUG_LOG_FILE = os.path.join(LOG_DIR, "bugs.log")

_file_logging_ready = False

# جلوگیری از اسپم مدیر با خطاهای تکراری (dedupe در بازه‌ی زمانی)
_last_report_at: dict = {}
_REPORT_MIN_INTERVAL = 45  # ثانیه — گزارش تکراریِ یک محل/نوع خطا حداکثر هر ۴۵ ثانیه


# =========================================================
# ۱. لاگ فایل چرخشی (قابل آپلود مستمر)
# =========================================================
def init_file_logging(level: int = logging.INFO) -> None:
    """
    اتصال RotatingFileHandler به ریشه‌ی logger تا همه‌ی لاگ‌ها (INFO/WARNING/ERROR)
    در فایل ذخیره شوند. یک فایل مجزا فقط برای WARNING به بالا (bugs.log) نگه می‌داریم
    تا خطاها به‌راحتی و به‌صورت مستمر قابل آپلود باشند.

    این تابع باید یک‌بار از bot.main() فراخوانی شود.
    """
    global _file_logging_ready
    if _file_logging_ready:
        return
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        root = logging.getLogger()

        # فایل لاگ کامل
        main_h = RotatingFileHandler(
            MAIN_LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=10, encoding="utf-8"
        )
        main_h.setLevel(level)
        main_h.setFormatter(fmt)
        root.addHandler(main_h)

        # فایل جداگانه فقط خطاها/هشدارها
        bug_h = RotatingFileHandler(
            BUG_LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=20, encoding="utf-8"
        )
        bug_h.setLevel(logging.WARNING)
        bug_h.setFormatter(fmt)
        root.addHandler(bug_h)

        _file_logging_ready = True
        logging.info(f"[BUG_REPORTER] لاگ فایل فعال شد → {MAIN_LOG_FILE} | {BUG_LOG_FILE}")
    except Exception as e:
        logging.error(f"[BUG_REPORTER] فعال‌سازی لاگ فایل ناموفق: {e}")


# =========================================================
# ۲. کمکی‌ها
# =========================================================
async def capture_screenshot_bytes(page) -> Optional[bytes]:
    """گرفتن اسکرین‌شات از صفحه‌ی Playwright — هرگز استثناء نمی‌دهد."""
    if page is None:
        return None
    try:
        return await page.screenshot(full_page=False)
    except Exception as e:
        logging.debug(f"[BUG_REPORTER] گرفتن اسکرین‌شات ناموفق: {e}")
        return None


def _safe_url(page) -> str:
    try:
        return page.url if page is not None else ""
    except Exception:
        return ""


def _build_traceback(error) -> tuple:
    """(etype, ename, tb_text) را از یک استثناء یا از استثنای جاری استخراج می‌کند."""
    etype = ename = tb = ""
    if isinstance(error, BaseException):
        etype = type(error).__name__
        ename = str(error)
        try:
            tb = "".join(traceback.format_exception(type(error), error, error._traceback_))
        except Exception:
            tb = ""
    elif error:
        ename = str(error)
    else:
        ei = sys.exc_info()
        if ei and ei[0]:
            etype = ei[0].__name__
            ename = str(ei[1])
            try:
                tb = "".join(traceback.format_exception(*ei))
            except Exception:
                tb = ""
    return etype, ename, tb


def _should_report(key: str) -> bool:
    """جلوگیری از اسپم: گزارش تکراریِ یک محل/نوع خطا محدود می‌شود."""
    now = time.time()
    last = _last_report_at.get(key, 0)
    if now - last < _REPORT_MIN_INTERVAL:
        return False
    _last_report_at[key] = now
    return True


async def _send_admin_text(bot, text: str) -> None:
    if not (bot and ADMIN_ID):
        return
    MAX = 3500
    for i in range(0, len(text), MAX):
        chunk = text[i:i + MAX]
        try:
            # بدون parse_mode تا کاراکترهای خاص باعث خطای پارس نشوند
            await bot.send_message(ADMIN_ID, chunk)
        except Exception as e:
            logging.debug(f"[BUG_REPORTER] ارسال متن گزارش ناموفق: {e}")
            break


# =========================================================
# ۳. گزارش کامل باگ
# =========================================================
async def report_bug(
    bot,
    *,
    where: str,
    error: Any = None,
    user_id: Optional[int] = None,
    bill_no: Optional[str] = None,
    page=None,
    context: Optional[dict] = None,
    level: str = "error",
    notify_admin: bool = True,
    with_screenshot: bool = True) -> None:
    """
    گزارش کامل یک باگ:
      - نوشتن در فایل لاگ (bugs.log) + کنسول
      - ارسال متن کامل (خطا + traceback + کاربر + کد + URL + زمینه) به مدیر
      - ارسال اسکرین‌شات صفحه به مدیر (در صورت وجود page)

    این تابع هرگز استثناء پرتاب نمی‌کند.
    """
    try:
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        etype, ename, tb = _build_traceback(error)
        url = _safe_url(page)

        # ── متن گزارش ──
        lines = [
            f"🐞 گزارش باگ [{level.upper()}]",
            f"📍 محل: {where}",
            f"🕒 {ts}",
        ]
        if etype or ename:
            lines.append(f"❗️ خطا: {etype}: {ename}" if etype else f"❗️ خطا: {ename}")
        if user_id is not None:
            lines.append(f"👤 کاربر: {user_id}")
        if bill_no:
            lines.append(f"🧾 کد رهگیری/پرونده: {bill_no}")
        if url:
            lines.append(f"🔗 URL: {url}")
        if context:
            try:
                ctx = json.dumps(context, ensure_ascii=False, default=str)[:1200]
            except Exception:
                ctx = str(context)[:1200]
            lines.append(f"🧩 زمینه: {ctx}")
        head = "\n".join(lines)
        full_text = head + (f"\n\n🧵 Traceback:\n{tb}" if tb else "")

        # ── فایل + کنسول ──
        log_fn = logging.error if level in ("error", "critical") else logging.warning
        log_fn(f"[BUG] {where} | {etype}: {ename} | user={user_id} bill={bill_no} url={url}")
        if tb:
            log_fn(f"[BUG-TB] {where}\n{tb}")

        # ── ارسال به مدیر (با محدودیت اسپم) ──
        if not (bot and notify_admin and ADMIN_ID):
            return
        dedupe_key = f"{where}|{etype}|{ename[:80]}"
        if not _should_report(dedupe_key):
            return

        await _send_admin_text(bot, full_text)

        if with_screenshot and page is not None:
            shot = await capture_screenshot_bytes(page)
            if shot:
                try:
                    from aiogram.types import BufferedInputFile
                    await bot.send_photo(
                        ADMIN_ID,
                        BufferedInputFile(shot, filename=f"bug_{int(time.time())}.png"),
                        caption=f"📸 اسکرین‌شات لحظه‌ی خطا | {where} | کاربر {user_id}")
                except Exception as e:
                    logging.debug(f"[BUG_REPORTER] ارسال اسکرین‌شات ناموفق: {e}")
    except Exception as e:
        # این تابع تحت هیچ شرایطی نباید خودش کرش کند
        try:
            logging.error(f"[BUG_REPORTER] خطا در خودِ report_bug: {e}")
        except Exception:
            pass


# =========================================================
# ۴. گارد مقاوم — ربات هرگز نباید کرش کند
# =========================================================
async def guard(
    func_or_awaitable,
    *,
    bot=None,
    where: str = "نامشخص",
    user_id: Optional[int] = None,
    bill_no: Optional[str] = None,
    page=None,
    context: Optional[dict] = None,
    reraise: bool = False,
    default: Any = None,
    level: str = "error"):
    """
    اجرای مقاوم یک coroutine/کالبک. هر استثنائی را می‌گیرد، گزارش کامل می‌دهد و
    اجازه می‌دهد ربات مسیر خود را ادامه دهد (بدون کرش).

    - func_or_awaitable: یک coroutine، یا یک callable بدون آرگومان که coroutine می‌سازد.
    - reraise: اگر True باشد، پس از گزارش، دوباره پرتاب می‌شود.
    بازگشت: نتیجه‌ی تابع در صورت موفقیت؛ در غیر این صورت `default`.
    """
    try:
        res = func_or_awaitable() if callable(func_or_awaitable) else func_or_awaitable
        if asyncio.iscoroutine(res) or asyncio.isfuture(res):
            res = await res
        return res
    except asyncio.CancelledError:
        # لغو تسک نباید به‌عنوان باگ گزارش شود
        raise
    except Exception as e:
        await report_bug(
            bot, where=where, error=e, user_id=user_id, bill_no=bill_no,
            page=page, context=context, level=level)
        if reraise:
            raise
        return default


def safe_background_task(coro, *, bot=None, where: str = "background-task"):
    """
    ایجاد یک تسک پس‌زمینه‌ی مقاوم که در صورت استثناء کرش نمی‌کند و گزارش می‌دهد.
    مانند asyncio.create_task ولی با گاردِ خطا.
    """
    async def _runner():
        await guard(coro, bot=bot, where=where)
    return asyncio.create_task(_runner())


# =========================================================
# ۵. آپلود مستمر فایل لاگ خطاها به مدیر
# =========================================================
async def upload_logs(bot, chat_id: Optional[int] = None, which: str = "bugs") -> bool:
    """
    آپلود فایل لاگ به مدیر/چت مشخص. `which`: "bugs" (فقط خطاها) یا "all" (کامل).
    برای «آپلود مستمر خطاها» قابل فراخوانی از یک کامند مدیر یا حلقه‌ی زمان‌بندی است.
    """
    target = chat_id if chat_id is not None else ADMIN_ID
    if not (bot and target):
        return False
    path = BUG_LOG_FILE if which == "bugs" else MAIN_LOG_FILE
    try:
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            await bot.send_message(target, f"ℹ️ فایل لاگ «{which}» خالی/موجود نیست.")
            return False
        from aiogram.types import FSInputFile
        caption = (
            "🐞 لاگ خطاها/هشدارها" if which == "bugs" else "📄 لاگ کامل ربات"
        ) + f" — {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
        await bot.send_document(target, FSInputFile(path), caption=caption)
        return True
    except Exception as e:
        logging.error(f"[BUG_REPORTER] آپلود لاگ ناموفق: {e}")
        try:
            await bot.send_message(target, f"❌ آپلود لاگ ناموفق: {str(e)[:200]}")
        except Exception:
            pass
        return False
