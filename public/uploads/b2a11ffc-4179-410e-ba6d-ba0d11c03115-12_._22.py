"""
بررسی ساعت کاری ربات — به‌جای بازه‌ی ثابت (۱۲ الی ۲۲ برای همه‌ی روزها)،
این ماژول تنظیمات واقعی را از پنل ادمین (Next.js) می‌خواند تا مدیر بتواند
برای هر روز هفته یک بازه‌ی جداگانه (یا تعطیلی کامل آن روز) تعریف کند.

اگر پنل ادمین در دسترس نبود (مثلاً هنوز اجرا نشده یا شبکه قطع بود)،
به‌صورت امن روی آخرین مقدار دریافتی یا بازه‌ی پیش‌فرض قدیمی fallback می‌کند
تا ربات هیچ‌وقت به‌خاطر این مشکل کاملاً از کار نیفتد.
"""
import datetime
import logging

import aiohttp

from config import ADMIN_PANEL_URL

logger = logging.getLogger(__name__)

TEHRAN_TZ = datetime.timezone(datetime.timedelta(hours=3, minutes=30))

_CACHE_TTL_SECONDS = 60  # هر ۶۰ ثانیه یک‌بار از پنل ادمین می‌خواند، نه هر پیام
_cache = {"schedule": None, "fetched_at": None}

# شماره‌ی روز مطابق جدول WorkingHour در پنل ادمین: 0=شنبه ... 6=جمعه
DEFAULT_SCHEDULE = [
    {"dayOfWeek": d, "startHour": 12, "startMin": 0, "endHour": 22, "endMin": 0, "enabled": True}
    for d in range(7)
]


def _python_weekday_to_schema_day(py_weekday: int) -> int:
    """پایتون: دوشنبه=0 ... یکشنبه=6  →  اسکیمای پروژه: شنبه=0 ... جمعه=6"""
    return (py_weekday + 2) % 7


async def _fetch_schedule():
    now = datetime.datetime.now(TEHRAN_TZ)
    if (
        _cache["schedule"] is not None
        and _cache["fetched_at"] is not None
        and (now - _cache["fetched_at"]).total_seconds() < _CACHE_TTL_SECONDS
    ):
        return _cache["schedule"]

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{ADMIN_PANEL_URL}/api/admin/working-hours",
                timeout=aiohttp.ClientTimeout(total=5)) as resp:
                data = await resp.json()
                schedule = data.get("schedule") or DEFAULT_SCHEDULE
                _cache["schedule"] = schedule
                _cache["fetched_at"] = now
                return schedule
    except Exception as e:
        logger.warning(
            f"[WORKING_HOURS] دریافت ساعت کاری از پنل ادمین ({ADMIN_PANEL_URL}) ناموفق بود، "
            f"از مقدار پیش‌فرض/آخرین مقدار معتبر استفاده می‌شود: {e}"
        )
        return _cache["schedule"] or DEFAULT_SCHEDULE


async def is_within_working_hours():
    """
    برمی‌گرداند: (در_بازه‌ی_کاری: bool, تنظیمات_امروز: dict یا None)
    """
    schedule = await _fetch_schedule()
    tehran_time = datetime.datetime.now(TEHRAN_TZ)
    schema_day = _python_weekday_to_schema_day(tehran_time.weekday())

    today = next((s for s in schedule if s["dayOfWeek"] == schema_day), None)
    if today is None or not today.get("enabled", True):
        return False, today

    start_minutes = today["startHour"] * 60 + today["startMin"]
    end_minutes = today["endHour"] * 60 + today["endMin"]
    now_minutes = tehran_time.hour * 60 + tehran_time.minute

    return (start_minutes <= now_minutes < end_minutes), today
