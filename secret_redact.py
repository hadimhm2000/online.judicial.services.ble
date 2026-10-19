"""
secret_redact.py — پنهان کردن توکن ربات در لاگ‌ها و پیام‌های خروجی
════════════════════════════════════════════════════════════════════

آدرس‌های API بله توکن ربات را در خود دارند (…/bot<TOKEN>/sendInvoice). متن خطای
aiohttp/aiogram همین آدرس را نشان می‌دهد و این متن هم در فایل‌های لاگ ذخیره
می‌شد و هم در پیام‌هایی مثل «خطا در دانلود فایل: {e}» برای کاربر فرستاده می‌شد.

  - TokenRedactFilter: روی handlerهای لاگ نصب می‌شود (install_log_filter).
  - TokenRedactRequestMiddleware: روی session ربات نصب می‌شود و text/caption
    هر پیام خروجی را پیش از ارسال پاک می‌کند.

هیچ‌کدام جز جایگزینی خود توکن با <BOT_TOKEN> رفتاری را تغییر نمی‌دهند.
"""
import logging

from aiogram.client.session.middlewares.base import BaseRequestMiddleware

from config import BOT_TOKEN

MASK = "<BOT_TOKEN>"


def redact(text):
    """توکن ربات را از رشته حذف می‌کند؛ ورودی غیررشته‌ای دست‌نخورده برمی‌گردد."""
    if not BOT_TOKEN or not isinstance(text, str) or BOT_TOKEN not in text:
        return text
    return text.replace(BOT_TOKEN, MASK)


class TokenRedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
            clean = redact(msg)
            if clean is not msg:
                record.msg, record.args = clean, None
            if record.exc_info and not record.exc_text:
                record.exc_text = logging.Formatter().formatException(record.exc_info)
            if record.exc_text:
                record.exc_text = redact(record.exc_text)
        except Exception:
            pass
        return True


def install_log_filter() -> None:
    """روی همهٔ handlerهای فعلی logger ریشه (کنسول + فایل‌های لاگ) نصب می‌شود."""
    for h in logging.getLogger().handlers:
        if not any(isinstance(f, TokenRedactFilter) for f in h.filters):
            h.addFilter(TokenRedactFilter())


class TokenRedactRequestMiddleware(BaseRequestMiddleware):
    async def __call__(self, make_request, bot, method):
        try:
            for field in ("text", "caption"):
                value = getattr(method, field, None)
                clean = redact(value)
                if clean is not value:
                    setattr(method, field, clean)
        except Exception:
            pass
        return await make_request(bot, method)
