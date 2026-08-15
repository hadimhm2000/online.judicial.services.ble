"""
بررسی معافیت پرداخت — تعیین اینکه آیا یک شناسه تلگرام در لیست معافیت
پنل ادمین (ExemptUser) ثبت شده است یا نه، تا آن کاربر بدون پرداخت هزینه
از خدمات ربات استفاده کند.

مثل working_hours.py، نتیجه از API پنل ادمین خوانده می‌شود و برای ۶۰
ثانیه کش می‌شود تا هر پیام کاربر یک درخواست HTTP جدید ایجاد نکند. اگر
پنل ادمین در دسترس نبود، به‌صورت امن «معاف نیست» در نظر گرفته می‌شود
(یعنی مشکل شبکه هیچ‌وقت باعث معافیت ناخواسته یا قطع کامل ربات نمی‌شود).
"""
import datetime
import logging

import aiohttp

from config import ADMIN_PANEL_URL

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 60
_cache = {"ids": None, "fetched_at": None}


async def _fetch_exempt_ids():
    now = datetime.datetime.now()
    if (
        _cache["ids"] is not None
        and _cache["fetched_at"] is not None
        and (now - _cache["fetched_at"]).total_seconds() < _CACHE_TTL_SECONDS
    ):
        return _cache["ids"]

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{ADMIN_PANEL_URL}/api/admin/exempt-users",
                timeout=aiohttp.ClientTimeout(total=5)) as resp:
                data = await resp.json()
                ids = {str(r["baleUserId"]) for r in data.get("records", [])}
                _cache["ids"] = ids
                _cache["fetched_at"] = now
                return ids
    except Exception as e:
        logger.warning(
            f"[EXEMPT_USERS] دریافت لیست معافیت از پنل ادمین ({ADMIN_PANEL_URL}) ناموفق بود: {e}"
        )
        # اگر مقدار قبلی معتبری داریم همان را برمی‌گردانیم، وگرنه لیست خالی
        # (یعنی «معاف نیست») — امن‌ترین حالت پیش‌فرض.
        return _cache["ids"] if _cache["ids"] is not None else set()


async def is_exempt_user(bale_user_id) -> bool:
    ids = await _fetch_exempt_ids()
    return str(bale_user_id) in ids
"""
بررسی معافیت پرداخت — ایدی 509108833 برای همیشه معاف است.
"""

EXEMPT_BALE_IDS = {"509108833"}


async def is_exempt_user(bale_user_id) -> bool:
    return str(bale_user_id) in EXEMPT_BALE_IDS