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

تعرفه (تومان) — پس از اصلاحیهٔ ۱۴۰۵/۰۶/۲۵ (حداقلِ مبلغ فاکتور API):
  - لایحه و اظهارنامه: ۱,۰۰۰ تومان (۱۰,۰۰۰ ریال)
  - سایر موارد (ثبت دادخواست، دعاوی اعتراضی، اعلام وکالت و ...): ۲,۰۰۰ تومان

  ⚠️ تعرفهٔ اولیهٔ دستور کارفرما ۱۰۰/۲۰۰ تومان بود؛ API بله/تلگرام
  مبالغ زیر ۱۰,۰۰۰ ریال را با خطای 400 «total price must be at
  least 10000» رد می‌کند، لذا با حفظ نسبت ۱۰۰:۲۰۰ ده‌برابر شد.
  تابع get_prepay_amount_toman به‌طور خودکار حداقلِ مجاز را اعمال
  می‌کند (MIN_INVOICE_AMOUNT_RIAL) تا فاکتور، پیام‌های کاربر/مدیر و
  کسرِ پایان کار همیشه روی یک عدد بمانند و خطای 400 برگردد نکند.

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
    BALE_WALLET_TOKEN, BOT_TOKEN, BALE_API_BASE, ADMIN_ID, BALE_SSL_CONTEXT,
    PREPAY_LAYEHE_EIZARNAMEH_TOMAN, PREPAY_OTHER_SERVICES_TOMAN,
)

# سرویس‌های مشمول تعرفهٔ لایحه/اظهارنامه (۱,۰۰۰ تومان)
_LAYEHE_EIZAR_SERVICES = {"lavayeh", "ezhharnameh"}

# ═══ حداقلِ مبلغ مجاز فاکتور در API بله/تلگرام (۱۰,۰۰۰ ریال) ═══
# خطای مرجع (لاگ کارفرما ۱۴۰۵/۰۶/۲۵):
#   "Bad Request: prices: total price must be at least 10000."
# این گارد در get_prepay_amount_toman اعمال می‌شود تا هر مسیری که مبلغ
# می‌سازد (فاکتور، پیام کاربر/مدیر، fallback ثبت پس از پرداخت) همیشه
# منطبق بر یک عددِ مجاز باشد.
MIN_INVOICE_AMOUNT_RIAL = 10_000

# کلید payload فاکتور — برای تشخیص قطعی نوع پرداخت در هندلر سراسری
PREPAY_INVOICE_TYPE = "reg_prepay"


# ═══ ⭐ مانده/بستانکاری کاربر (مبالغ قابل بازگشت/کسر) ═══
# رکورد runtime_state.prepaid_registrations[user_id] می‌تواند شامل دو بخش باشد:
#   - prepay_paid_rial: پیش‌پرداختِ پرداخت‌شده برای همین پرونده
#   - مابقی (credit): مانده/بستانکاری قبلی — ثبت‌شده توسط مدیر
#     (/prepaid_set) یا باقی‌ماندهٔ پیش‌پرداختِ پرونده‌های قبلی
# هر دو بخش در فاکتور نهایی از هزینه کل کسر و به کاربر اعلام می‌شوند؛ مانده
# در پیام/فاکتور پیش‌پرداخت هم درج می‌شود.

def _split_record(rec: dict):
    """(prepay_paid_rial, credit_rial) یک رکورد — سازگار با رکوردهای قدیمی
    (بدون prepay_paid_rial: رکورد دستی مدیر = تماماً مانده، وگرنه تماماً
    پیش‌پرداخت)."""
    if not rec:
        return 0, 0
    amount = max(0, int(rec.get("amount_rial", 0) or 0))
    if "prepay_paid_rial" in rec:
        paid = int(rec.get("prepay_paid_rial", 0) or 0)
    else:
        paid = 0 if rec.get("manual") else amount
    paid = max(0, min(paid, amount))
    return paid, amount - paid


def get_credit_rial(user_id: int) -> int:
    """کل مانده/بستانکاری فعلی کاربر (ریال) — ۰ اگر نداشته باشد."""
    rec = runtime_state.prepaid_registrations.get(user_id)
    return max(0, int((rec or {}).get("amount_rial", 0) or 0))


def get_prepay_amount_toman(service_key: str) -> int:
    """مبلغ پیش‌پرداخت (تومان) بر اساس نوع سرویس.

    لایحه و اظهارنامه → ۱,۰۰۰ تومان؛ سایر موارد → ۲,۰۰۰ تومان.
    (تعرفهٔ اولیهٔ ۱۰۰/۲۰۰ تومان بود؛ API بله مبالغ زیر ۱۰,۰۰۰ ریال را
    می‌رَد، لذا ×۱۰ شد — نسبت ۱۰۰:۲۰۰ حفظ شده است.)

    ⚠️ گارد API: اگر مقدار کانفیگ (عمدی یا اشتباه) زیر حداقلِ مجاز
    بیفتد، همین‌جا به حداقل (۱,۰۰۰ تومان = ۱۰,۰۰۰ ریال) بالا برده
    می‌شود تا sendInvoice هرگز با خطای «total price must be at least
    10000» رد نشود. چون همهٔ مسیرها از همین تابع مبلغ می‌گیرند،
    فاکتور، پیام‌ها و کسرِ پایان کار همیشه یک عدد را می‌بینند.
    """
    # ⭐ مبلغ از تنظیمات پنل (bot_settings) — در نبود آن، همان مقدار config
    import bot_settings
    if service_key in _LAYEHE_EIZAR_SERVICES:
        base = bot_settings.get_int("prepay.lavayeh_ezhhar_toman", PREPAY_LAYEHE_EIZARNAMEH_TOMAN)
    else:
        base = bot_settings.get_int("prepay.other_toman", PREPAY_OTHER_SERVICES_TOMAN)
    if base * 10 < MIN_INVOICE_AMOUNT_RIAL:
        base = MIN_INVOICE_AMOUNT_RIAL // 10
    return base


def get_prepay_amount_rial(service_key: str) -> int:
    """مبلغ پیش‌پرداخت (ریال) — همیشه ≥ حداقلِ مجاز فاکتور API."""
    return get_prepay_amount_toman(service_key) * 10


async def send_prepay_invoice(bot, user_id: int, service_key: str,
                              service_label: str) -> bool:
    """ارسال فاکتور پیش‌پرداخت + درگاه پرداخت بله و پیام راهنما.

    خروجی: True اگر فاکتور با موفقیت ارسال شد (در این صورت فراخواننده
    باید state را روی waiting_for_*_prepay بگذارد)، False در خطا.
    """
    amount_toman = get_prepay_amount_toman(service_key)
    amount_rial = amount_toman * 10  # تضمین‌شده ≥ MIN_INVOICE_AMOUNT_RIAL

    # ═══ ارسال فاکتور بله (sendInvoice) — الگوی اثبات‌شده پروژه ═══
    try:
        invoice_payload = _json.dumps({
            "type": PREPAY_INVOICE_TYPE,
            "svc": service_key,
            "uid": user_id,
        })
        async with aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(ssl=BALE_SSL_CONTEXT)) as session:
            invoice_url = f"{BALE_API_BASE}/bot{BOT_TOKEN}/sendInvoice"
            invoice_data = {
                "chat_id": user_id,
                "title": f"پیش پرداخت {service_label}",
                "description": (
                    f"این مبلغ پیش پرداخت {service_label} می باشد\n"
                    f"مبلغ: {amount_toman:,} تومان ({amount_rial:,} ریال)"
                    + (f"\nمانده/بستانکاری شما: {get_credit_rial(user_id):,} ریال "
                       f"(در فاکتور نهایی کسر می‌شود)"
                       if get_credit_rial(user_id) > 0 else "")
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
                from card_payment import track_invoice as _cp_track; _cp_track(invoice_data)  # ⭐ کارت‌به‌کارت پس از ۲۰ دقیقه
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

    # ⭐ مانده/بستانکاری کاربر (مبالغ قابل بازگشت/کسر) در پیام پیش‌پرداخت درج می‌شود
    credit_rial = get_credit_rial(user_id)
    credit_line = (
        f"💵 مانده/بستانکاری شما: *{credit_rial:,} ریال* — این مبلغ همراه با "
        f"پیش‌پرداخت، در فاکتور نهایی از هزینهٔ کل کسر می‌گردد.\n\n"
        if credit_rial > 0 else "")

    # ═══ پیام راهنما — عیناً متن دستور کارفرما ═══
    try:
        await bot.send_message(
            user_id,
            f"🧾 *فاکتور پیش پرداخت*\n"
            f"💰 مبلغ: *{amount_toman:,} تومان*\n\n"
            f"{credit_line}"
            f"این مبلغ پیش پرداخت می باشد لطفا پرداخت تا موارد شما شروع به ثبت گردد. باتشکر",
            parse_mode="Markdown")
    except Exception:
        # بعضی پارس‌های Markdown در بله سخت‌گیر است — نسخه ساده
        await bot.send_message(
            user_id,
            f"🧾 فاکتور پیش پرداخت\n"
            f"💰 مبلغ: {amount_toman:,} تومان\n\n"
            f"{credit_line.replace('*', '')}"
            f"این مبلغ پیش پرداخت می باشد لطفا پرداخت تا موارد شما شروع به ثبت گردد. باتشکر")

    # اطلاع به مدیر
    try:
        await bot.send_message(
            ADMIN_ID,
            f"🧾 [PREPAY] فاکتور پیش‌پرداخت {service_label} ارسال شد\n"
            f"👤 کاربر: {user_id}\n"
            f"💰 مبلغ: {amount_toman:,} تومان — در انتظار پرداخت"
            + (f"\n💵 مانده/بستانکاری کاربر: {credit_rial:,} ریال (در فاکتور نهایی کسر می‌شود)"
               if credit_rial > 0 else ""))
    except Exception:
        pass

    return True


async def cover_prepay_from_credit(bot, user_id: int, service_key: str,
                                   service_label: str) -> bool:
    """⭐ دستور کارفرما: اگر مانده/بستانکاری کاربر کل مبلغ پیش‌پرداخت را
    پوشش دهد، مرحلهٔ پرداخت پیش‌پرداخت کلاً حذف و ثبت مستقیم آغاز می‌شود.

    رکورد مانده دست‌نخورده می‌ماند: در فاکتور نهایی کل مانده از هزینه کسر
    می‌شود — دقیقاً معادل حالتی که کاربر پیش‌پرداخت را بپردازد و همان مبلغ
    در پایان کسر شود (مبلغ نهایی پرداختی کاربر یکسان است).

    خروجی: True → پیش‌پرداخت پوشش داده شد و پیام‌ها ارسال شدند؛ فراخوان
    باید بلافاصله ثبت را شروع کند (مثل مسیر کاربران معاف). False → فاکتور
    پیش‌پرداخت طبق روال ارسال شود.
    """
    try:
        rec = runtime_state.prepaid_registrations.get(user_id)
        _paid, credit_rial = _split_record(rec)
        prepay_rial = get_prepay_amount_rial(service_key)
        if credit_rial < prepay_rial:
            return False
    except Exception as e:
        logging.warning(f"[REG-PREPAY] بررسی پوشش پیش‌پرداخت با مانده ناموفق: {e}")
        return False

    logging.info(
        f"[REG-PREPAY] پیش‌پرداخت با مانده پوشش داده شد: user={user_id}, "
        f"svc={service_key}, پیش‌پرداخت={prepay_rial:,}, مانده={credit_rial:,} ریال")
    try:
        await bot.send_message(
            user_id,
            f"✅ *پیش‌پرداخت نیاز نیست*\n\n"
            f"💵 مانده/بستانکاری شما (*{credit_rial:,} ریال*) مبلغ پیش‌پرداخت "
            f"{service_label} را پوشش می‌دهد.\n"
            f"این مانده در فاکتور نهایی از هزینهٔ کل کسر می‌گردد.\n\n"
            f"⏳ درخواست شما در حال ارسال به سامانه قضایی است...",
            parse_mode="Markdown")
    except Exception:
        try:
            await bot.send_message(
                user_id,
                f"✅ پیش‌پرداخت نیاز نیست — مانده/بستانکاری شما ({credit_rial:,} ریال) "
                f"مبلغ پیش‌پرداخت را پوشش می‌دهد و در فاکتور نهایی کسر می‌گردد.\n"
                f"⏳ درخواست شما در حال ارسال به سامانه قضایی است...")
        except Exception:
            pass
    try:
        await bot.send_message(
            ADMIN_ID,
            f"💵 [PREPAY] پیش‌پرداخت {service_label} کاربر {user_id} با مانده/"
            f"بستانکاری ({credit_rial:,} ریال) پوشش داده شد — ثبت بدون پرداخت "
            f"پیش‌پرداخت آغاز شد (مانده در فاکتور نهایی کسر می‌شود).")
    except Exception:
        pass
    try:
        from sheets import log_event
        await log_event(
            "پرداخت", service_label, str(user_id), user_id,
            doc_name=f"پیش‌پرداخت {service_label}",
            payment_status="پوشش از محل مانده/بستانکاری",
            note=f"پیش‌پرداخت {prepay_rial:,} ریال — مانده {credit_rial:,} ریال")
    except Exception:
        pass
    return True


def register_prepaid(user_id: int, amount_toman: int, service_key: str,
                     service_label: str, charge_id: str = "") -> None:
    """ثبت پیش‌پرداخت کاربر برای کسر در پایان کار.

    ⭐ رفع باگ: قبلاً رکورد قبلی کاربر بازنویسی می‌شد و مانده/بستانکاری
    ثبت‌شده توسط مدیر (/prepaid_set) یا باقی‌ماندهٔ پرونده‌های قبلی با
    پرداخت پیش‌پرداخت جدید بی‌صدا از بین می‌رفت. حالا پیش‌پرداخت جدید به
    ماندهٔ موجود افزوده می‌شود و هر دو در فاکتور نهایی کسر می‌شوند.
    """
    existing = runtime_state.prepaid_registrations.get(user_id)
    _old_paid, old_credit = _split_record(existing)
    # پیش‌پرداختِ پرداخت‌نشدهٔ قبلی هم (اگر مصرف نشده) جزو مانده حساب می‌شود
    carried = _old_paid + old_credit
    paid_rial = int(amount_toman) * 10
    total_rial = paid_rial + carried
    runtime_state.prepaid_registrations[user_id] = {
        "amount_toman": total_rial // 10,
        "amount_rial": total_rial,
        "prepay_paid_rial": paid_rial,
        "service": service_key,
        "service_label": service_label,
        "charge_id": charge_id,
        "paid_at": datetime.datetime.now(),
    }
    logging.info(
        f"[REG-PREPAY] پیش‌پرداخت ثبت شد: user={user_id}, svc={service_key}, "
        f"مبلغ={amount_toman:,} تومان, مانده قبلی={carried:,} ریال, "
        f"جمع قابل کسر={total_rial:,} ریال, charge={charge_id}")


def pop_prepaid(user_id: int):
    """برداشتن رکورد پیش‌پرداخت (یک‌بار مصرف) — None اگر وجود نداشت.

    ⭐ v1.7 — رکورد مصرف‌شده در runtime_state.consumed_prepay_for_panel هم
    نگه داشته می‌شود تا panel_sync در اولین ثبت/آپدیت پروندهٔ همین کاربر،
    مبلغ پیش‌پرداخت را روی پرونده (prepayAmount) ثبت کند — مبنای سود پنل.
    """
    prepay = runtime_state.prepaid_registrations.pop(user_id, None)
    if prepay:
        try:
            stash = getattr(runtime_state, "consumed_prepay_for_panel", None)
            if not isinstance(stash, dict):
                stash = {}
                runtime_state.consumed_prepay_for_panel = stash
            # مبنای سود پنل فقط پیش‌پرداختِ واقعاً پرداخت‌شده است (نه مانده)
            amount_rial = _split_record(prepay)[0] if "prepay_paid_rial" in prepay \
                else int(prepay.get("amount_rial", 0) or 0)
            stash[user_id] = {
                "amount_toman": amount_rial // 10,
                "paid_at": prepay.get("paid_at"),
                "service": prepay.get("service"),
                "consumed_at": datetime.datetime.now(),
            }
        except Exception as ex:
            logging.warning(f"[REG-PREPAY] ذخیرهٔ پیش‌پرداخت برای پنل ناموفق: {ex}")
    return prepay


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
    paid_rial, credit_rial = _split_record(prepay)
    available = paid_rial + credit_rial
    fee = max(0, int(final_fee_rial))
    applied = min(available, fee)
    adjusted = fee - applied
    leftover = available - applied
    prepay = dict(prepay)
    prepay["prepay_paid_rial"] = paid_rial
    prepay["credit_rial"] = credit_rial
    prepay["applied_rial"] = applied
    prepay["leftover_rial"] = leftover
    # ⭐ رفع باگ: اگر مانده بیشتر از هزینه بود، باقی‌مانده حفظ می‌شود تا در
    # پروندهٔ بعدی کسر گردد (قبلاً کل رکورد حذف و مازاد از بین می‌رفت).
    if leftover > 0:
        runtime_state.prepaid_registrations[user_id] = {
            "amount_toman": leftover // 10,
            "amount_rial": leftover,
            "prepay_paid_rial": 0,
            "service": "leftover",
            "service_label": "باقی‌ماندهٔ مانده از پروندهٔ قبلی",
            "charge_id": "",
            "paid_at": datetime.datetime.now(),
        }
    logging.info(
        f"[REG-PREPAY] کسر مانده/پیش‌پرداخت: user={user_id}, کل={fee:,}, "
        f"پیش‌پرداخت={paid_rial:,}, مانده={credit_rial:,}, کسرشده={applied:,} → "
        f"قابل پرداخت={adjusted:,} ریال, باقی‌ماندهٔ مانده={leftover:,} "
        f"(svc={prepay.get('service')})")
    return adjusted, prepay


def build_prepay_fee_text(final_fee_rial: int, prepay_info: dict,
                          total_fee_rial: int) -> str:
    """پیام هزینه پایان کار وقتی کاربر پیش‌پرداخت داشته است.

    طبق دستور کارفرما: هزینه کل اعلام می‌شود، ذکر می‌شود که فلان مبلغ به
    عنوان پیش پرداخت پرداخت شده، مابقی به‌عنوان «مبلغ قابل پرداخت شما»
    اعلام می‌گردد (فاکتورِ همین مبلغ ارسال می‌شود).
    """
    info = prepay_info or {}
    if "credit_rial" in info:
        paid_rial = int(info.get("prepay_paid_rial", 0) or 0)
        credit_rial = int(info.get("credit_rial", 0) or 0)
    else:
        paid_rial, credit_rial = _split_record(info)
    leftover = int(info.get("leftover_rial", 0) or 0)
    lines = [f"💰 *مبلغ کل: {total_fee_rial:,} ریال*"]
    if paid_rial > 0:
        lines.append(f"💵 مبلغ *{paid_rial:,} ریال* به عنوان پیش پرداخت، پرداخت شده است.")
    # فقط بخشی از مانده که واقعاً در این فاکتور مصرف شد (پیش‌پرداخت اول کسر می‌شود)
    applied = int(info.get("applied_rial", paid_rial + credit_rial) or 0)
    credit_used = max(0, min(credit_rial, applied - min(paid_rial, applied)))
    if credit_used > 0:
        lines.append(f"💵 مبلغ *{credit_used:,} ریال* از مانده/بستانکاری قبلی شما کسر گردید.")
    lines.append(f"💳 *مبلغ قابل پرداخت شما: {final_fee_rial:,} ریال*")
    if leftover > 0:
        lines.append(
            f"ℹ️ مبلغ *{leftover:,} ریال* از مانده/بستانکاری شما باقی ماند و در "
            f"پروندهٔ بعدی کسر خواهد شد.")
    return "\n".join(lines)
