"""
بررسی ساعت کاری ربات — ۲۴ ساعته (بدون محدودیت ساعت)
تمام روز‌های هفته فعال.
"""
import datetime

TEHRAN_TZ = datetime.timezone(datetime.timedelta(hours=3, minutes=30))


async def is_within_working_hours():
    """
    برمی‌گرداند: (در_بازه‌ی_کاری: bool, تنظیمات_امروز: dict یا None)
    همیشه True برمی‌گرداند.
    """
    return True, {
        "startHour": 0,
        "endHour": 24,
        "enabled": True,
    }
