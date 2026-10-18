"""
تخفیف اختصاصی کاربران — درصد تخفیفی که مدیر در پنل ادمین (UserDiscount)
برای یک شناسهٔ بله ثبت می‌کند.

⚠️ تخفیف فقط روی «سود» اعمال می‌شود، نه روی هزینهٔ سامانه/دفتر خدمات:
    سود       = مبلغ نهایی − هزینهٔ خام سامانه
    تخفیف     = سود × درصد ÷ ۱۰۰   (رند به پایین تا هزار ریال)
    مبلغ جدید = مبلغ نهایی − تخفیف
بنابراین مبلغ جدید هیچ‌وقت از هزینهٔ سامانه کمتر نمی‌شود.

مثل exempt_users.py، لیست از API پنل خوانده و ۶۰ ثانیه کش می‌شود؛ اگر پنل
در دسترس نبود به‌صورت امن «بدون تخفیف» در نظر گرفته می‌شود.

هزینهٔ خام سامانه در اغلب سناریوها همان مبلغی است که به
capture_and_report_payment_ids پاس داده می‌شود؛ آن تابع با
remember_system_cost مقدار را نگه می‌دارد تا send_lavayeh_result (که فقط
مبلغ نهایی را می‌گیرد) بتواند سود را محاسبه کند — بدون تغییر در سناریوها.
"""
import datetime
import logging

import aiohttp

from config import ADMIN_PANEL_URL, PANEL_AUTH_HEADERS

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 60
_cache = {"map": None, "fetched_at": None}

# هزینهٔ خام سامانه به تفکیک کاربر — {user_id: {"amount", "tracking", "at"}}
_system_costs: dict = {}
_SYSTEM_COST_TTL_SECONDS = 30 * 60

# تخفیف به ریال تا هزار ریال به پایین رند می‌شود
_ROUND_STEP_RIAL = 1000


async def _fetch_discounts() -> dict:
    now = datetime.datetime.now()
    if (
        _cache["map"] is not None
        and _cache["fetched_at"] is not None
        and (now - _cache["fetched_at"]).total_seconds() < _CACHE_TTL_SECONDS
    ):
        return _cache["map"]

    try:
        async with aiohttp.ClientSession(headers=PANEL_AUTH_HEADERS) as session:
            async with session.get(
                f"{ADMIN_PANEL_URL}/api/admin/user-discounts",
                timeout=aiohttp.ClientTimeout(total=5)) as resp:
                data = await resp.json()
                mapping = {}
                for r in data.get("records", []):
                    try:
                        pct = int(r.get("percent") or 0)
                    except (TypeError, ValueError):
                        continue
                    if 0 < pct <= 100:
                        mapping[str(r["baleUserId"])] = pct
                _cache["map"] = mapping
                _cache["fetched_at"] = now
                return mapping
    except Exception as e:
        logger.warning(
            f"[USER_DISCOUNT] دریافت لیست تخفیف از پنل ادمین ({ADMIN_PANEL_URL}) ناموفق بود: {e}"
        )
        return _cache["map"] if _cache["map"] is not None else {}


async def get_profit_discount_percent(bale_user_id) -> int:
    """درصد تخفیف سود کاربر (۰ یعنی بدون تخفیف)."""
    mapping = await _fetch_discounts()
    return mapping.get(str(bale_user_id), 0)


def remember_system_cost(user_id, amount, tracking_code: str = "") -> None:
    """نگه‌داشتن هزینهٔ خام سامانه (ریال) برای محاسبهٔ سود در فاکتور نهایی."""
    try:
        amount = int(amount or 0)
    except (TypeError, ValueError):
        return
    if amount <= 0:
        return
    _system_costs[int(user_id)] = {
        "amount": amount,
        "tracking": str(tracking_code or ""),
        "at": datetime.datetime.now(),
    }


def pop_system_cost(user_id, tracking_code: str = ""):
    """برداشتن هزینهٔ خام سامانهٔ ثبت‌شده برای کاربر (یا None)."""
    rec = _system_costs.pop(int(user_id), None)
    if not rec:
        return None
    if (datetime.datetime.now() - rec["at"]).total_seconds() > _SYSTEM_COST_TTL_SECONDS:
        return None
    saved, given = rec["tracking"], str(tracking_code or "")
    # اعلام وکالت کد ترکیبی می‌فرستد؛ پس شمول کافی است
    if saved and given and saved not in given and given not in saved:
        return None
    return rec["amount"]


async def apply_profit_discount(user_id, final_fee_rial: int, system_cost_rial):
    """اعمال تخفیف اختصاصی کاربر روی سود.

    خروجی: (final_fee_جدید, info) — info=None یعنی تخفیفی اعمال نشد؛
    وگرنه {"percent", "discount_rial", "profit_rial", "original_rial"}.
    هیچ‌وقت exception نمی‌دهد.
    """
    try:
        final_fee_rial = int(final_fee_rial or 0)
        system_cost_rial = int(system_cost_rial or 0)
        if final_fee_rial <= 0 or system_cost_rial <= 0:
            return final_fee_rial, None
        percent = await get_profit_discount_percent(user_id)
        if percent <= 0:
            return final_fee_rial, None
        profit = final_fee_rial - system_cost_rial
        if profit <= 0:
            logger.info(
                f"[USER_DISCOUNT] کاربر {user_id}: سود صفر/منفی "
                f"(نهایی={final_fee_rial:,}, سامانه={system_cost_rial:,}) — تخفیف اعمال نشد")
            return final_fee_rial, None
        discount = (profit * percent // 100) // _ROUND_STEP_RIAL * _ROUND_STEP_RIAL
        if discount <= 0:
            return final_fee_rial, None
        logger.info(
            f"[USER_DISCOUNT] کاربر {user_id}: {percent}% از سود {profit:,} = "
            f"{discount:,} ریال | {final_fee_rial:,} → {final_fee_rial - discount:,}")
        return final_fee_rial - discount, {
            "percent": percent,
            "discount_rial": discount,
            "profit_rial": profit,
            "original_rial": final_fee_rial,
        }
    except Exception as e:
        logger.error(f"[USER_DISCOUNT] خطا در اعمال تخفیف کاربر {user_id}: {e}")
        return int(final_fee_rial or 0), None


def build_discount_line(info: dict) -> str:
    """یک خط توضیح تخفیف برای پیام فاکتور."""
    return (
        f"🎁 تخفیف اختصاصی شما ({info['percent']}٪) اعمال شد: "
        f"{info['discount_rial']:,} ریال"
    )
