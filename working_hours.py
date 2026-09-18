"""
بررسی ساعت کاری ربات — بازه ۱۴ الی ۲۲ (ساعت ۲ ظهر تا ۱۰ شب)
تمام روز‌های هفته یکسان.
"""
import datetime

TEHRAN_TZ = datetime.timezone(datetime.timedelta(hours=3, minutes=30))

START_HOUR = 14
END_HOUR = 22


async def is_within_working_hours():
    """
    برمی‌گرداند: (در_بازه‌ی_کاری: bool, تنظیمات_امروز: dict یا None)
    """
    tehran_time = datetime.datetime.now(TEHRAN_TZ)
    return (START_HOUR <= tehran_time.hour < END_HOUR), {
        "startHour": START_HOUR,
        "endHour": END_HOUR,
        "enabled": True,
    }
