"""
⭐ سکشن جدید کارفرما (۱۴۰۵/۰۶) — «پیش‌پرداخت ثبت»

برای تمام بخش‌های ربات **به‌جز استعلامات**، بلافاصله پس از «تایید اطلاعات»:
  ۱. فاکتور و درگاه پرداخت (کیف پول بله) برای کاربر ارسال می‌شود
     همراه پیام: «این مبلغ پیش پرداخت می باشد لطفا پرداخت تا موارد شما
     شروع به ثبت گردد. باتشکر»
  ۲. پس از تایید خودکار پرداخت (successful_payment بله)، ثبت در سامانه
     (ارسال تسک به صف پردازش) آغاز می‌شود.
  ۳. در پایان کار، هزینه مثل همیشه محاسبه می‌شود؛ مبلغ کل اعلام می‌گردد،
     پیش‌پرداخت از آن کسر می‌شود و فاکتور «مابقی» برای کاربر ارسال می‌شود.

تعرفه (تومان):
  - لایحه و اظهارنامه: ۱۰۰ تومان
  - سایر موارد (ثبت دادخواست، دعاوی اعتراضی، اعلام وکالت و ...): ۲۰۰ تومان

نکته معماری: هندلر successful_payment در aiogram با روتر مادر
(global_successful_payment_handler در handlers.py) مسیریابی می‌شود؛
هندلرهای decorated روی روترهای فرعی هرگز فراخوانی نمی‌شوند (رفتار
اثبات‌شدهٔ aiogram 3.x: هندلرهای خودِ روتر مادر زودتر از sub-routerها
بررسی می‌شوند). بنابراین هندلر سراسری، توابع همین ماژول و هندلرهای
پرداخت هر بخش را مستقیم فراخوانی می‌کند.
"""

import datetime
import logging

import aiohttp
import json as _json

import runtime_state
from config import (
    BALE_WALLET_TOKEN, BOT_TOKEN, BALE_API_BASE, ADMIN_ID,
    PREPAY_LAYEHE_EIZARNAMEH_TOMAN, PREPAY_OTHER_SERVICES_TOMAN,
)

# سرویس‌های مشمول تعرفه ۱۰۰ تومانی (لایحه و اظهارنامه)
_LAYEHE_EIZAR_SERVICES = {"lavayeh", "ezhharnameh"}

# کلید payload فاکتور — برای تشخیص قطعی نوع پرداخت در هندلر سراسری
PREPAY_INVOICE_TYPE = "reg_prepay"


def get_prepay_amount_toman(service_key: str) -> int:
    """مبلغ پیش‌پرداخت (تومان) بر اساس نوع سرویس.

    لایحه و اظهارنامه → ۱۰۰ تومان؛ سایر موارد → ۲۰۰ تومان.
    """
    if service_key in _LAYEHE_EIZAR_SERVICES:
        return PREPAY_LAYEHE_EIZARNAMEH_TOMAN
    return PREPAY_OTHER_SERVICES_TOMAN


async def send_prepay_invoice(bot, user_id: int, service_key: str,
                              service_label: str) -> bool:
    """ارسال فاکتور پیش‌پرداخت + درگاه پرداخت بله و پیام راهنما.

    خروجی: True اگر فاکتور با موفقیت ارسال شد (در این صورت فراخواننده
    باید state را روی waiting_for_*_prepay بگذارد)، False در خطا.
    """
    amount_toman = get_prepay_amount_toman(service_key)
    amount_rial = amount_toman * 10

    # ═══ ارسال فاکتور بله (sendInvoice) — الگوی اثبات‌شده پروژه ═══
    try:
        invoice_payload = _json.dumps({
            "type": PREPAY_INVOICE_TYPE,
            "svc": service_key,
            "uid": user_id,
        })
        async with aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(ssl=False)) as session:
            invoice_url = f"{BALE_API_BASE}/bot{BOT_TOKEN}/sendInvoice"
            invoice_data = {
                "chat_id": user_id,
                "title": f"پیش پرداخت {service_label}",
                "description": (
                    f"این مبلغ پیش پرداخت {service_label} می باشد\n"
                    f"مبلغ: {amount_toman:,} تومان ({amount_rial:,} ریال)"
                ),
                "payload": invoice_payload,
                "provider_token": BALE_WALLET_TOKEN,
                "currency": "IRR",
                "prices": [{
                    "label": f"پیش پرداخت {service_label}",
                    "amount": amount_rial,
                }],
            }
            logging.info(
                f"[REG-PREPAY] ارسال فاکتور پیش‌پرداخت: user={user_id}, "
                f"svc={service_key}, مبلغ={amount_rial:,} ریال")
            async with session.post(invoice_url, json=invoice_data) as resp:
                result = await resp.json()
                if not result.get("ok"):
                    logging.error(f"[REG-PREPAY] خطای sendInvoice: {result}")
                    raise Exception(result.get("description", "خطا در ارسال فاکتور"))
    except Exception as e:
        logging.error(f"[REG-PREPAY] خطا در ارسال فاکتور پیش‌پرداخت: {e}",
                      exc_info=True)
        try:
            await bot.send_message(
                user_id,
                "⚠️ خطا در ساخت فاکتور پیش‌پرداخت. لطفاً کمی بعد دوباره "
                "گزینه تایید را انتخاب کنید.")
        except Exception:
            pass
        return False

    # ═══ پیام راهنما — عیناً متن دستور کارفرما ═══
    try:
        await bot.send_message(
            user_id,
            f"🧾 *فاکتور پیش پرداخت*\n"
            f"💰 مبلغ: *{amount_toman:,} تومان*\n\n"
            f"این مبلغ پیش پرداخت می باشد لطفا پرداخت تا موارد شما شروع به ثبت گردد. باتشکر",
            parse_mode="Markdown")
    except Exception:
        # بعضی پارس‌های Markdown در بله سخت‌گیر است — نسخه ساده
        await bot.send_message(
            user_id,
            f"🧾 فاکتور پیش پرداخت\n"
            f"💰 مبلغ: {amount_toman:,} تومان\n\n"
            f"این مبلغ پیش پرداخت می باشد لطفا پرداخت تا موارد شما شروع به ثبت گردد. باتشکر")

    # اطلاع به مدیر
    try:
        await bot.send_message(
            ADMIN_ID,
            f"🧾 [PREPAY] فاکتور پیش‌پرداخت {service_label} ارسال شد\n"
            f"👤 کاربر: {user_id}\n"
            f"💰 مبلغ: {amount_toman:,} تومان — در انتظار پرداخت")
    except Exception:
        pass

    return True


def register_prepaid(user_id: int, amount_toman: int, service_key: str,
                     service_label: str, charge_id: str = "") -> None:
    """ثبت پیش‌پرداخت کاربر برای کسر در پایان کار (یک‌بار مصرف)."""
    runtime_state.prepaid_registrations[user_id] = {
        "amount_toman": amount_toman,
        "amount_rial": amount_toman * 10,
        "service": service_key,
        "service_label": service_label,
        "charge_id": charge_id,
        "paid_at": datetime.datetime.now(),
    }
    logging.info(
        f"[REG-PREPAY] پیش‌پرداخت ثبت شد: user={user_id}, svc={service_key}, "
        f"مبلغ={amount_toman:,} تومان, charge={charge_id}")


def pop_prepaid(user_id: int):
    """برداشتن رکورد پیش‌پرداخت (یک‌بار مصرف) — None اگر وجود نداشت."""
    return runtime_state.prepaid_registrations.pop(user_id, None)


def adjust_final_fee_with_prepay(user_id: int, final_fee_rial: int):
    """اعمال کسر پیش‌پرداخت از هزینه کل.

    خروجی: (final_fee_adjusted, prepay_info)
      - prepay_info=None → کاربر پیش‌پرداختی نداشته؛ مبلغ بدون تغییر.
      - در غیر این صورت مبلغ جدید = max(0, کل − پیش‌پرداخت) برگردانده می‌شود
        و رکورد مصرف می‌گردد.
    """
    prepay = pop_prepaid(user_id)
    if not prepay:
        return final_fee_rial, None
    prepay_rial = int(prepay.get("amount_rial", 0))
    adjusted = max(0, int(final_fee_rial) - prepay_rial)
    logging.info(
        f"[REG-PREPAY] کسر پیش‌پرداخت: user={user_id}, "
        f"کل={final_fee_rial:,}, پیش‌پرداخت={prepay_rial:,} → "
        f"مابقی={adjusted:,} ریال (svc={prepay.get('service')})")
    return adjusted, prepay


def build_prepay_fee_text(final_fee_rial: int, prepay_info: dict,
                          total_fee_rial: int) -> str:
    """پیام هزینه پایان کار وقتی کاربر پیش‌پرداخت داشته است.

    طبق دستور کارفرما: هزینه کل اعلام می‌شود، ذکر می‌شود که فلان مبلغ به
    عنوان پیش پرداخت پرداخت شده، مابقی به‌عنوان «مبلغ قابل پرداخت شما»
    اعلام می‌گردد (فاکتورِ همین مبلغ ارسال می‌شود).
    """
    prepay_rial = int((prepay_info or {}).get("amount_rial", 0))
    return (
        f"💰 *مبلغ کل: {total_fee_rial:,} ریال*\n"
        f"💵 مبلغ *{prepay_rial:,} ریال* به عنوان پیش پرداخت، پرداخت شده است.\n"
        f"💳 *مبلغ قابل پرداخت شما: {final_fee_rial:,} ریال*"
    )
