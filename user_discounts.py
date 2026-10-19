"""
تخفیف اختصاصی کاربران — درصدی که مدیر در پنل ادمین (UserDiscount) برای یک
شناسهٔ بله ثبت می‌کند.

محل اعمال (طبق دستور کارفرما):
  - استعلام‌ها (تکی، سبد خرید، دسته‌جمعی): درصد از کل مبلغ فاکتور کم می‌شود.
    → apply_to_invoice، که wallet.prepare_invoice پیش از هر sendInvoice صدا
    می‌زند؛ پس به handlers.py دست زده نمی‌شود.
  - بقیهٔ بخش‌ها (لایحه، اظهارنامه، چک، اعلام وکالت، تجدیدنظر): درصد فقط از
    «پیش‌پرداخت» کم می‌شود (prepay_registration.send_prepay_invoice). کاربر
    مبلغ کمتری می‌پردازد ولی در فاکتور نهایی کل پیش‌پرداخت کسر می‌گردد؛ یعنی
    تخفیف واقعاً به کاربر می‌رسد. فاکتور نهایی خودش تخفیفی ندارد.

مثل working_hours.py، لیست با refresh_loop هر ۶۰ ثانیه از پنل خوانده و کش
می‌شود (prepare_invoice همگام است و نمی‌تواند منتظر شبکه بماند). اگر پنل در
دسترس نبود، آخرین لیست معتبر — یا «بدون تخفیف» — استفاده می‌شود.
"""
import asyncio
import json
import logging

import aiohttp

from config import ADMIN_PANEL_URL, PANEL_AUTH_HEADERS

logger = logging.getLogger(__name__)

REFRESH_SECONDS = 60

# نوع payload فاکتورهای استعلام — فقط همین‌ها در apply_to_invoice تخفیف می‌گیرند
INQUIRY_INVOICE_TYPES = ("single", "cart", "bulk_inquiry")

# API بله فاکتور زیر ۱۰,۰۰۰ ریال را رد می‌کند
MIN_INVOICE_RIAL = 10_000

_percents: dict = {}


async def refresh() -> None:
    global _percents
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
        _percents = mapping
    except Exception as e:
        logger.warning(
            f"[USER_DISCOUNT] دریافت لیست تخفیف از پنل ادمین ({ADMIN_PANEL_URL}) ناموفق بود: {e}")


async def refresh_loop():
    while True:
        try:
            await refresh()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[USER_DISCOUNT] خطا در به‌روزرسانی تخفیف‌ها: {e}")
        await asyncio.sleep(REFRESH_SECONDS)


def get_percent(bale_user_id) -> int:
    """درصد تخفیف کاربر از کش (۰ یعنی بدون تخفیف)."""
    return _percents.get(str(bale_user_id), 0)


def discount_amount(bale_user_id, amount_rial: int) -> int:
    """مبلغ تخفیف (ریال) برای یک مبلغ — رند به پایین تا ۱۰ ریال، و طوری که
    مبلغ باقی‌مانده از حداقلِ فاکتور بله کمتر نشود."""
    pct = get_percent(bale_user_id)
    amount_rial = int(amount_rial or 0)
    if pct <= 0 or amount_rial <= MIN_INVOICE_RIAL:
        return 0
    disc = (amount_rial * pct // 100) // 10 * 10
    return max(0, min(disc, amount_rial - MIN_INVOICE_RIAL))


def apply_to_invoice(invoice_data: dict) -> dict:
    """تخفیف استعلام روی invoice_data — هرگز exception نمی‌دهد.

    علامت "disc" در payload گذاشته می‌شود تا ارسال دوبارهٔ همان فاکتور
    (یادآوری/کارت‌به‌کارت) دوباره تخفیف نخورد.
    """
    try:
        payload = json.loads(str(invoice_data.get("payload") or "{}"))
        if payload.get("type") not in INQUIRY_INVOICE_TYPES or "disc" in payload:
            return invoice_data
        uid = int(invoice_data.get("chat_id"))
        prices = invoice_data.get("prices") or []
        amount = sum(int(p.get("amount", 0)) for p in prices)
        disc = discount_amount(uid, amount)
        if disc <= 0:
            return invoice_data
        pct = get_percent(uid)
        new_amount = amount - disc
        label = str((prices[0] if prices else {}).get("label") or invoice_data.get("title") or "استعلام")
        payload["disc"] = pct
        new_data = dict(invoice_data)
        new_data["payload"] = json.dumps(payload)
        new_data["prices"] = [{"label": label, "amount": new_amount}]
        line = (f"\n🎁 تخفیف اختصاصی شما ({pct}٪): {disc // 10:,} تومان — "
                f"مبلغ: {new_amount // 10:,} تومان")
        desc = str(invoice_data.get("description") or "")
        if len(desc) + len(line) <= 255:
            new_data["description"] = desc + line
        logger.info(
            f"[USER_DISCOUNT] فاکتور {payload.get('type')} کاربر {uid}: {pct}% → "
            f"{amount:,} → {new_amount:,} ریال")
        return new_data
    except Exception as e:
        logger.error(f"[USER_DISCOUNT] خطا در اعمال تخفیف روی فاکتور: {e}")
        return invoice_data
