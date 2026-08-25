"""
بررسی معافیت پرداخت — تعیین اینکه آیا یک شناسه تلگرام در لیست معافیت
پنل ادمین (ExemptUser) ثبت شده است یا نه، تا آن کاربر بدون پرداخت هزینه
از خدمات ربات استفاده کند.

مثل working_hours.py، نتیجه از API پنل ادمین خوانده می‌شود و برای ۶۰
ثانیه کش می‌شود تا هر پیام کاربر یک درخواست HTTP جدید ایجاد نکند. اگر
پنل ادمین در دسترس نبود، به‌صورت امن «معاف نیست» در نظر گرفته می‌شود
(یعنی مشکل شبکه هیچ‌وقت باعث معافیت ناخواسته یا قطع کامل ربات نمی‌شود).
"""
"""
بررسی معافیت پرداخت — تعیین اینکه آیا یک شناسه بله باید بدون پرداخت
هزینه از خدمات ربات استفاده کند.

سه منبع معافیت (هر سه با هم ترکیب می‌شوند، نه جایگزین هم):
  ۱. ADMIN_ID (از config.py) — مدیر ربات همیشه و به‌صورت قطعی معاف است،
     مستقل از دردسترس بودن پنل یا هر تنظیم دیگر.
  ۲. لیست ثابت EXEMPT_BALE_IDS در همین فایل — برای حساب‌های آزمایشی/مورد
     اعتماد که می‌خواهید همیشه معاف باشند، بدون نیاز به تنظیم در پنل.
  ۳. لیست پویای پنل مدیریت (ADMIN_PANEL_URL/api/admin/exempt-users) —
     نتیجه برای ۶۰ ثانیه کش می‌شود تا هر پیام کاربر یک درخواست HTTP جدید
     ایجاد نکند. اگر پنل ادمین در دسترس نبود، این بخش به‌صورت امن «خالی»
     در نظر گرفته می‌شود (یعنی مشکل شبکه هیچ‌وقت باعث معافیت ناخواسته یا
     قطع کامل ربات نمی‌شود) — ولی منابع ۱ و ۲ همچنان کار می‌کنند.

⚠️ نکتهٔ مهم: قبلاً این فایل دو تعریف جداگانه و ناسازگار از is_exempt_user
داشت که دومی بی‌صدا اولی را بی‌اثر می‌کرد (تعریف دوم در پایتون همیشه برنده
است) — یعنی فیچر معافیت پویا از پنل مدیریت عملاً مرده بود و فقط دو شناسهٔ
هاردکد معاف بودند. این نسخه هر سه منبع را با هم ترکیب می‌کند.
"""
import datetime
import logging

import aiohttp

from config import ADMIN_PANEL_URL, ADMIN_ID

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 60
_cache = {"ids": None, "fetched_at": None}

# حساب‌های همیشه‌معاف (مثلاً حساب آزمایشی خود مدیر) — مستقل از پنل
EXEMPT_BALE_IDS = {"509108833", "164366255"}


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
        # (یعنی «معاف نیست») — امن‌ترین حالت پیش‌فرض. توجه: این فقط منبع
        # پویای پنل را تحت تاثیر قرار می‌دهد، نه ADMIN_ID یا EXEMPT_BALE_IDS.
        return _cache["ids"] if _cache["ids"] is not None else set()


async def is_exempt_user(bale_user_id) -> bool:
    bale_user_id_str = str(bale_user_id)

    # منبع ۱: مدیر ربات همیشه معاف است
    if ADMIN_ID and bale_user_id_str == str(ADMIN_ID):
        return True

    # منبع ۲: لیست ثابت داخل کد
    if bale_user_id_str in EXEMPT_BALE_IDS:
        return True

    # منبع ۳: لیست پویای پنل مدیریت
    panel_ids = await _fetch_exempt_ids()
    return bale_user_id_str in panel_ids