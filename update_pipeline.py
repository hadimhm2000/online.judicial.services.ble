"""
update_pipeline.py — نظم و شفافیت پردازش آپدیت‌های بله (۱۴۰۵/۰۸)
══════════════════════════════════════════════════════════════════════════════

دو میان‌افزار سطح Update که در bot.py بلافاصله پس از ساخت Dispatcher
ثبت می‌شوند (بیرونی‌ترین لایه — قبل از همهٔ روترها و میان‌افزارهای دیگر):

۱) UserSerialMiddleware — سریال‌سازی آپدیت‌های «هر کاربر»
   ریشهٔ مسئله (لاگ ۱۴۰۵/۰۸/۰۶): آپدیت ۳۵۱۵۱ قبل از ۳۵۱۵۰ پردازش شد
   (aiogram هر آپدیت را در تسک جداگانه اجرا می‌کند) و روی FSM همان کاربر
   شرط رقابتی (race) ساخت. حالا آپدیت‌های هر کاربر به ترتیب رسیدن و
   «یکی‌یکی» پردازش می‌شوند؛ کاربران مختلف همچنان موازی‌اند و کندی یک
   کاربر بقیه را نگه نمی‌دارد.

   ایمنی‌ها:
   - بازپخش‌های مصنوعی (کیف پول WALLET-… و کارت‌به‌کارت CARD-…) با
     dp.feed_update «درون همان تسکِ» هندلر جاری اجرا می‌شوند؛ قفل برای
     همان تسک re-entrant است (بن‌بست/DEADLOCK ندارد).
   - اگر ربات هنوز به اولین آپدیتِ یک کاربر مشغول باشد، آپدیت بعدی همان
     کاربر فقط «صف» می‌شود. توجه: پاسخ سریع به کاربر (مثل callback.answer)
     هم «درون هندلر» صدا زده می‌شود و بنابراین همان‌قدر صف می‌شود.
   - ⭐ pre_checkout_query بدون قفل و خارج از این صف پردازش می‌شود:
     مهلت پاسخ بله به آن حدود ۱۰ ثانیه است و اگر پشت یک هندلر کندِ همان
     کاربر (مثلاً ۴۶ ثانیه‌ای) صف شود، پنجرهٔ تأیید پرداخت می‌گذرد و
     پرداخت کاربر بی‌دلیل لغو می‌شود. هندلر pre_checkout فقط payload را
     اعتبارسنجی می‌کند و state کاربر را تغییر نمی‌دهد؛ عبور موازی امن است.
   - هیچ state، داده یا پرداختی تغییر نمی‌کند؛ فقط ترتیب اجراست.

۲) SlowUpdateLogMiddleware — لاگ زمان پردازش آپدیت‌ها
   ریشهٔ مسئله: آپدیت ۱۶۳۲۲۲۵۰۲۶ چهل‌وشش ثانیه طول کشید و چون لاگ
   زمان‌سنجی aiogram در سطح DEBUG است، چیزی در لاگ دیده نمی‌شد. حالا:
   - بیش از ۵ ثانیه → INFO با شناسهٔ آپدیت، کاربر و نوع آپدیت
   - بیش از ۳۰ ثانیه → WARNING (نیازمند بررسی فراخوانی بی‌timeout)
"""
import asyncio
import logging
import time

from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram.types import Update

logger = logging.getLogger(__name__)

SLOW_INFO_SECONDS = 5.0      # از این زمان به بعد → INFO
SLOW_WARNING_SECONDS = 30.0  # از این زمان به بعد → WARNING

# حداکثر تعداد قفلهای نگه‌داشته‌شده (کاربران غیرفعال پاک‌سازی می‌شوند)
_MAX_LOCKS = 5000


def _user_of_update(update: Update):
    """کاربرِ آپدیت (message / callback_query / pre_checkout_query / ...)."""
    for attr in ("message", "edited_message", "callback_query",
                 "pre_checkout_query", "channel_post", "my_chat_member"):
        evt = getattr(update, attr, None)
        if evt is not None:
            user = getattr(evt, "from_user", None)
            if user is not None and getattr(user, "id", None):
                return user.id
    return None


def _update_type(update: Update) -> str:
    for attr in ("message", "edited_message", "callback_query",
                 "pre_checkout_query", "channel_post", "my_chat_member",
                 "poll", "poll_answer"):
        if getattr(update, attr, None) is not None:
            return attr
    return "unknown"


class UserSerialMiddleware(BaseMiddleware):
    """آپدیت‌های هر کاربر را به ترتیب رسیدن و پشت‌سرهم پردازش می‌کند.

    re-entrant برای همان تسک: بازپخش‌های مصنوعی (wallet/card_payment با
    dp.feed_update) درون تسکِ در حال اجرا بدون قفل دوباره عبور می‌کنند.

    ⭐ pre_checkout_query مستثناست و بدون قفل عبور می‌کند: مهلت پاسخ بله
    به آن حدود ۱۰ ثانیه است و نباید پشت هندلر کندِ همان کاربر صف شود.
    """

    # آپدیت‌هایی که بدون صف سریال‌سازی عبور می‌کنند — فقط موارد حساس به
    # زمان که state کاربر را تغییر نمی‌دهند (اعتبارسنجی + پاسخ فوری).
    BYPASS_UPDATE_ATTRS = ("pre_checkout_query",)

    def __init__(self):
        super().__init__()
        self._locks: dict = {}
        self._holders: dict = {}   # uid -> id(task) دارندهٔ قفل

    def _get_lock(self, uid: int) -> asyncio.Lock:
        lock = self._locks.get(uid)
        if lock is None:
            if len(self._locks) >= _MAX_LOCKS:
                # پاکسازی قفلهای آزاد — قفلهای نگه‌داشته دست نمی‌خورند
                for k in [k for k, v in self._locks.items()
                          if not v.locked() and self._holders.get(k) is None]:
                    self._locks.pop(k, None)
            lock = self._locks.setdefault(uid, asyncio.Lock())
        return lock

    async def __call__(self, handler, event: Update, data: dict):
        uid = _user_of_update(event)
        if uid is None:
            return await handler(event, data)
        # ⭐ آپدیت‌های حساس به زمان (pre_checkout_query): بدون قفل و بدون
        # صف — مهلت ~۱۰ ثانیه‌ای تأیید پرداخت پشت هندلر کندِ همان کاربر
        # نمی‌گذرد. هندلرش فقط payload را اعتبارسنجی می‌کند (بدون تغییر state).
        if any(getattr(event, attr, None) is not None for attr in self.BYPASS_UPDATE_ATTRS):
            return await handler(event, data)
        lock = self._get_lock(uid)
        if self._holders.get(uid) == id(asyncio.current_task()):
            # همان تسکِ دارندهٔ قفل (بازپخش مصنوعی) → بن‌بست نمی‌سازیم
            return await handler(event, data)
        async with lock:
            self._holders[uid] = id(asyncio.current_task())
            try:
                return await handler(event, data)
            finally:
                self._holders.pop(uid, None)


class SlowUpdateLogMiddleware(BaseMiddleware):
    """زمان پردازش هر آپدیت را می‌سنجد و کندی‌ها را لاگ می‌کند."""

    async def __call__(self, handler, event: Update, data: dict):
        t0 = time.monotonic()
        try:
            return await handler(event, data)
        finally:
            elapsed = time.monotonic() - t0
            if elapsed >= SLOW_INFO_SECONDS:
                uid = _user_of_update(event)
                level = logging.WARNING if elapsed >= SLOW_WARNING_SECONDS else logging.INFO
                logger.log(
                    level,
                    "[UPDATE-TIMING] آپدیت #%s (type=%s, user=%s) در %.1f ثانیه پردازش شد%s",
                    getattr(event, "update_id", "?"), _update_type(event),
                    uid, elapsed,
                    " — بررسی فراخوانی خارجی بدون timeout توصیه می‌شود"
                    if elapsed >= SLOW_WARNING_SECONDS else "")
