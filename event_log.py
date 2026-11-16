"""
event_log.py — ثبت یکنواخت رویدادها (فقط در لاگ ربات).

⭐ ۱۴۰۵/۰۸: اتصال به گوگل‌شیت به‌طور کامل حذف شد (کندی و timeout های مکرر
باعث بلاک شدن هندلرها و از دست رفتن پردازش پرداخت می‌شد). رویدادها اکنون فقط
در logs/bot.log ثبت می‌شوند و پرونده‌ها/پرداخت‌ها در پنل ادمین نگه‌داری می‌شوند.
امضای log_event برای سازگاری با فراخوانی‌های قبلی حفظ شده است.
"""
import logging

logger = logging.getLogger("events")


async def log_event(
    event_type: str,
    query_type: str,
    full_name: str,
    user_id,
    tracking_code: str = "",
    national_id: str = "",
    doc_name: str = "",
    payment_status: str = "-",
    note: str = ""):
    """ثبت رویداد در لاگ (بدون هیچ تماس شبکه‌ای). هرگز استثنا نمی‌دهد."""
    try:
        logger.info(
            f"[EVENT] {event_type} | {query_type} | user={user_id} | code={tracking_code} | "
            f"doc={doc_name} | pay={payment_status} | {note}")
    except Exception:
        pass
