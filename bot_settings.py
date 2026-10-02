"""
bot_settings.py — تعرفه‌ها و متن‌های ربات، قابل ویرایش از پنل ادمین
══════════════════════════════════════════════════════════════════════════════

پنل (دیالوگ «تنظیمات ربات») مقادیر را در جدول BotSetting ذخیره می‌کند؛ ربات هر
REFRESH_SECONDS ثانیه آن‌ها را از GET /api/admin/bot-settings می‌خواند و در حافظه
نگه می‌دارد. تغییر قیمت یا متن بدون دیپلوی، حداکثر ظرف یک دقیقه اعمال می‌شود.

اگر کلیدی در پنل تعریف نشده باشد یا پنل در دسترس نباشد، همان مقدار پیش‌فرض کد
استفاده می‌شود؛ یعنی ربات هرگز به پنل وابسته نمی‌شود.

کلیدهای فعلی (فهرست کامل با توضیح: src/lib/bot-settings.ts):
  fee.inquiry.phone / fee.inquiry.nid / fee.inquiry.tracking /
  fee.inquiry.tracking_attach      → config.FEES (تومان)، درجا جایگزین می‌شود
  prepay.lavayeh_ezhhar_toman / prepay.other_toman → prepay_registration
  rating.enabled                   → نظرسنجی پس از تحویل (feedback.py)
  report.hour                      → ساعت گزارش شبانهٔ مدیر (daily_report.py)
  gate.*                           → متن‌های صف خارج از ساعت کاری/قطعی سامانه
"""
import asyncio
import logging

logger = logging.getLogger(__name__)

REFRESH_SECONDS = 60

_values: dict[str, str] = {}

# کلیدهای تعرفهٔ استعلام → کلید دیکشنری config.FEES
_FEE_KEYS = {
    "fee.inquiry.phone": "شماره تماس",
    "fee.inquiry.nid": "کد ملی",
    "fee.inquiry.tracking": "کد رهگیری ساده",
    "fee.inquiry.tracking_attach": "کد رهگیری با منضمات",
}
_fee_defaults: dict[str, int] = {}


def get(key: str, default: str | None = None) -> str | None:
    value = _values.get(key)
    return value if value not in (None, "") else default


def get_text(key: str) -> str | None:
    """متن تعریف‌شده در پنل یا None (فراخوان پیش‌فرض خودش را دارد)."""
    return get(key)


def get_int(key: str, default: int) -> int:
    raw = get(key)
    if raw is None:
        return default
    try:
        return int(str(raw).replace(",", "").strip())
    except ValueError:
        logger.warning(f"[BOT_SETTINGS] مقدار عددی نامعتبر برای {key}: {raw!r}")
        return default


def get_bool(key: str, default: bool) -> bool:
    raw = get(key)
    if raw is None:
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on", "بله")


def _apply_fee_overrides():
    """config.FEES درجا به‌روز می‌شود تا همهٔ ماژول‌هایی که FEES را import کرده‌اند مقدار جدید را ببینند."""
    import config
    if not _fee_defaults:
        _fee_defaults.update({k: config.FEES[v] for k, v in _FEE_KEYS.items() if v in config.FEES})
    for key, fee_name in _FEE_KEYS.items():
        if key in _fee_defaults:
            config.FEES[fee_name] = get_int(key, _fee_defaults[key])


async def refresh() -> bool:
    from panel_sync import get_bot_settings
    data = await get_bot_settings()
    if data is None:
        return False
    _values.clear()
    _values.update({str(k): str(v) for k, v in data.items()})
    _apply_fee_overrides()
    return True


async def refresh_loop():
    while True:
        try:
            await refresh()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[BOT_SETTINGS] خطا در به‌روزرسانی تنظیمات: {e}")
        await asyncio.sleep(REFRESH_SECONDS)
