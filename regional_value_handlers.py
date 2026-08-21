# -*- coding: utf-8 -*-
"""
هندلرهای بخش استعلام ارزش منطقه‌ای ملک.

فلو:
  ۱. انتخاب استان
  ۲. ورود آدرس دقیق
  ۳. ورود متراژ عرصه
  ۴. انتخاب کاربری (مسکونی/تجاری/اداری)
  ۵. نمایش فاکتور پرداخت (۲۰۰,۰۰۰ تومان)
  ۶. پس از پرداخت موفق → استعلام → تولید PDF → ارسال
"""

import asyncio
import logging
import os

import aiohttp
from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Message, ReplyKeyboardRemove, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery,
)

import runtime_state
from bale_file_sender import send_document_direct
from config import ADMIN_ID, BALE_WALLET_TOKEN, BOT_TOKEN, BALE_API_BASE, REGIONAL_VALUE_FEE
from keyboards import back_only_kb, get_main_menu_kb
from states import Form
from tax_geolocation_query import get_province_list, find_land_use_value, extract_all_land_use_values

logger = logging.getLogger(__name__)

regional_value_router = Router()

LAND_USES = ["مسکونی", "تجاری", "اداری"]


# ══════════════════════════════════════════════════════════════════
# نقطه ورود — از handlers.py فراخوانی می‌شود
# ══════════════════════════════════════════════════════════════════
async def regional_value_entry(message: Message, state: FSMContext):
    """شروع فرآیند استعلام ارزش منطقه‌ای."""
    provinces = get_province_list()
    # ساخت کیبورد استان‌ها (هر ردیف ۳ استان)
    rows = []
    for i in range(0, len(provinces), 3):
        row = [KeyboardButton(text=p) for p in provinces[i:i+3]]
        rows.append(row)
    rows.append([KeyboardButton(text="🔙 بازگشت")])
    kb = ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

    await message.answer(
        "🗺️ *استعلام ارزش منطقه‌ای ملک*\n\n"
        "لطفاً استان مربوطه را انتخاب کنید:",
        reply_markup=kb,
    )
    await state.set_state(Form.rv_waiting_province)


# ══════════════════════════════════════════════════════════════════
# مرحله ۱: انتخاب استان
# ══════════════════════════════════════════════════════════════════
@regional_value_router.message(Form.rv_waiting_province)
async def process_province(message: Message, state: FSMContext):
    if not message.text:
        return

    if message.text == "🔙 بازگشت":
        await message.answer(
            "لطفاً نحوه ثبت درخواست خود را انتخاب فرمایید:",
            reply_markup=get_main_menu_kb(message.from_user.id),
        )
        await state.set_state(Form.waiting_for_flow_type)
        return

    provinces = get_province_list()
    selected = message.text.strip()
    if selected not in provinces:
        await message.answer("⚠️ لطفاً یکی از استان‌های لیست را انتخاب کنید.")
        return

    await state.update_data(rv_province=selected)
    await message.answer(
        f"✅ استان انتخاب‌شده: *{selected}*\n\n"
        f"📍 لطفاً آدرس دقیق را با ذکر نام شهر اعلام کنید:\n"
        f"(مثال: تهران، خیابان ولیعصر، نرسیده به میدان ونک)",
        reply_markup=back_only_kb,
    )
    await state.set_state(Form.rv_waiting_address)


# ══════════════════════════════════════════════════════════════════
# مرحله ۲: ورود آدرس
# ══════════════════════════════════════════════════════════════════
@regional_value_router.message(Form.rv_waiting_address)
async def process_address(message: Message, state: FSMContext):
    if not message.text:
        return

    if message.text == "🔙 بازگشت":
        from regional_value_handlers import regional_value_entry
        await regional_value_entry(message, state)
        return

    address = message.text.strip()
    if len(address) < 5:
        await message.answer("⚠️ آدرس بسیار کوتاه است. لطفاً آدرس دقیق‌تری وارد کنید.")
        return

    await state.update_data(rv_address=address)
    await message.answer(
        f"✅ آدرس ثبت شد.\n\n"
        f"📐 لطفاً متراژ دقیق عرصه را به متر مربع وارد کنید:\n"
        f"(مثال: 250)",
        reply_markup=back_only_kb,
    )
    await state.set_state(Form.rv_waiting_area)


# ══════════════════════════════════════════════════════════════════
# مرحله ۳: ورود متراژ
# ══════════════════════════════════════════════════════════════════
@regional_value_router.message(Form.rv_waiting_area)
async def process_area(message: Message, state: FSMContext):
    if not message.text:
        return

    if message.text == "🔙 بازگشت":
        data = await state.get_data()
        province = data.get("rv_province", "")
        await state.update_data(rv_address="")
        await message.answer(
            f"📍 لطفاً آدرس دقیق را با ذکر نام شهر اعلام کنید:\n"
            f"(مثال: {province}، خیابان اصلی، ...)",
            reply_markup=back_only_kb,
        )
        await state.set_state(Form.rv_waiting_address)
        return

    # نرمال‌سازی اعداد فارسی به انگلیسی
    area_text = message.text.strip()
    area_text = area_text.translate(
        str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
    )
    area_text = area_text.replace(",", "").replace(" ", "")

    try:
        area = float(area_text)
        if area <= 0 or area > 1000000:
            raise ValueError
    except (ValueError, TypeError):
        await message.answer(
            "⚠️ متراژ نامعتبر است. لطفاً یک عدد مثبت (متر مربع) وارد کنید."
        )
        return

    await state.update_data(rv_area=area)

    # کیبورد انتخاب کاربری
    rows = [
        [KeyboardButton(text="۱. مسکونی"), KeyboardButton(text="۲. تجاری")],
        [KeyboardButton(text="۳. اداری")],
        [KeyboardButton(text="🔙 بازگشت")],
    ]
    kb = ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

    await message.answer(
        f"✅ متراژ: *{area:,.0f} متر مربع*\n\n"
        f"🏢 لطفاً کاربری زمین را انتخاب کنید:",
        reply_markup=kb,
    )
    await state.set_state(Form.rv_waiting_land_use)


# ══════════════════════════════════════════════════════════════════
# مرحله ۴: انتخاب کاربری
# ══════════════════════════════════════════════════════════════════
LAND_USE_KEY_MAP = {
    "۱. مسکونی": "مسکونی",
    "مسکونی": "مسکونی",
    "۲. تجاری": "تجاری",
    "تجاری": "تجاری",
    "۳. اداری": "اداری",
    "اداری": "اداری",
}


@regional_value_router.message(Form.rv_waiting_land_use)
async def process_land_use(message: Message, state: FSMContext, bot: Bot):
    if not message.text:
        return

    if message.text == "🔙 بازگشت":
        await message.answer(
            "📐 لطفاً متراژ دقیق عرصه را به متر مربع وارد کنید:",
            reply_markup=back_only_kb,
        )
        await state.set_state(Form.rv_waiting_area)
        return

    land_use = LAND_USE_KEY_MAP.get(message.text.strip())
    if not land_use:
        await message.answer("⚠️ لطفاً یکی از گزینه‌های کاربری را انتخاب کنید.")
        return

    await state.update_data(rv_land_use=land_use)

    # ═══ ارسال فاکتور پرداخت ═══
    fee_rial = REGIONAL_VALUE_FEE * 10  # تومان به ریال

    try:
        import json as _json
        invoice_payload = _json.dumps({"type": "regional_value", "uid": message.from_user.id})
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
            invoice_url = f"{BALE_API_BASE}/bot{BOT_TOKEN}/sendInvoice"
            invoice_data = {
                "chat_id": message.from_user.id,
                "title": "فاکتور استعلام ارزش منطقه‌ای",
                "description": f"استعلام ارزش منطقه‌ای: {REGIONAL_VALUE_FEE:,} تومان ({fee_rial:,} ریال)",
                "payload": invoice_payload,
                "provider_token": BALE_WALLET_TOKEN,
                "currency": "IRR",
                "prices": [{"label": "استعلام ارزش منطقه‌ای", "amount": fee_rial}],
            }
            logging.info(f"[RV-PAY] ارسال sendInvoice به chat_id={message.from_user.id}, مبلغ={fee_rial:,} ریال")
            async with session.post(invoice_url, json=invoice_data) as resp:
                result = await resp.json()
                logging.info(f"[RV-PAY] پاسخ sendInvoice: {result}")
                if not result.get("ok"):
                    logging.error(f"[RV-PAY] خطای sendInvoice: {result}")
                    raise Exception(result.get("description", "خطا در ارسال فاکتور"))
    except Exception as e:
        logging.error(f"[RV-PAY] خطا در ارسال فاکتور: {e}", exc_info=True)
        await message.answer("⚠️ خطا در ساخت فاکتور. لطفاً کمی بعد دوباره تلاش کنید.")
        return

    pay_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ پرداخت انجام شد", callback_data="pay_done")],
        [InlineKeyboardButton(text="❌ انصراف", callback_data="pay_cancel")],
    ])
    await message.answer(
        "⏳ فاکتور ارسال شد.\n"
        "پس از پرداخت موفق در کیف پول بله، استعلام ارزش منطقه‌ای به‌صورت خودکار پردازش و ارسال می‌شود.",
        reply_markup=pay_kb,
    )
    await state.set_state(Form.rv_waiting_payment)


# ══════════════════════════════════════════════════════════════════
# مرحله ۵: پرداخت موفق — استعلام + تولید PDF + ارسال
# ══════════════════════════════════════════════════════════════════
async def regional_value_successful_payment(message: Message, state: FSMContext, bot: Bot):
    """پردازش پس از پرداخت موفق: استعلام + PDF + ارسال به کاربر."""
    user_id = message.from_user.id
    data = await state.get_data()

    province = data.get("rv_province", "")
    address = data.get("rv_address", "")
    area = data.get("rv_area", 0)
    land_use = data.get("rv_land_use", "مسکونی")

    await message.answer("⏳ در حال استعلام ارزش منطقه‌ای... لطفاً چند لحظه صبر کنید.")

    try:
        # ── اجرای پایپ‌لاین استعلام (در thread جدا) ──
        loop = asyncio.get_running_loop()

        def _do_query():
            from geocode_and_query import full_pipeline
            return full_pipeline(address=address, province_hint=province)

        result = await loop.run_in_executor(None, _do_query)

        # tax_info حالا دیکشنری ساختاریافته است:
        # {"سال": "1405", "فیلدهای_ساختاریافته": {...}, "همه_فیلدهای_خام_صفحه": {...}, "فیلدهای_پیدا_نشده": [...]}
        tax_result = result.get("tax_info", {})

        if not tax_result.get("فیلدهای_ساختاریافته"):
            await message.answer(
                "⚠️ متاسفانه نتیجه‌ای از سامانه مالیاتی دریافت نشد.\n\n"
                "ممکن است آدرس دقیق نباشد یا مختصات خارج از محدوده تعریف‌شده باشد.\n"
                "لطفاً از ابتدا تلاش کنید.",
                reply_markup=get_main_menu_kb(user_id),
            )
            await state.clear()
            return

        # ── استخراج هر ۳ ارزش معاملاتی ──
        all_lu_values = extract_all_land_use_values(tax_result)

        # ── استخراج ارزش بر اساس کاربری انتخاب‌شده ──
        unit_value = find_land_use_value(tax_result, land_use)

        if unit_value is None:
            available = []
            for lu in LAND_USES:
                v = find_land_use_value(tax_result, lu)
                if v is not None:
                    available.append(f"{lu}: {v:,} ریال")
            avail_text = "\n".join(available) if available else "هیچ مقداری یافت نشد"

            await message.answer(
                f"⚠️ کاربری *{land_use}* برای این موقعیت در سامانه تعریف نشده است.\n\n"
                f"ارزش‌های موجود:\n{avail_text}\n\n"
                f"لطفاً از ابتدا با کاربری متفاوت تلاش کنید.",
                reply_markup=get_main_menu_kb(user_id),
            )
            await state.clear()
            return

        total_value = int(unit_value * area)

        # ── تولید PDF ──
        def _build_pdf():
            from regional_value_pdf import build_regional_value_pdf
            pdf_path = f"/tmp/regional_value_{user_id}_{message.message_id}.pdf"

            header_img = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "tax_header.jpg"
            )

            ok = build_regional_value_pdf(
                tax_result=tax_result,
                province=province,
                address=address,
                area=area,
                land_use=land_use,
                total_value=total_value,
                output_path=pdf_path,
                header_image_path=header_img,
                all_land_use_values=all_lu_values,
            )
            return pdf_path, ok

        pdf_path, pdf_ok = await loop.run_in_executor(None, _build_pdf)

        if pdf_ok and os.path.exists(pdf_path):
            await send_document_direct(
                user_id, pdf_path,
                filename=f"ارزش_منطقه_ای_{province}.pdf",
                caption=(
                    f"📄 گزارش ارزش منطقه‌ای ملک\n\n"
                    f"📍 استان: {province}\n"
                    f"🏗 کاربری: {land_use}\n"
                    f"📐 متراژ: {area:,.0f} متر مربع\n"
                    f"💰 ارزش کل: {total_value:,} ریال"
                ),
            )
            try:
                os.remove(pdf_path)
            except Exception:
                pass
        else:
            # فال‌بک متنی
            structured = tax_result.get("فیلدهای_ساختاریافته", {})
            info_text = "\n".join(f"  {k}: {v}" for k, v in structured.items() if v)
            await message.answer(
                f"📊 *نتیجه استعلام ارزش منطقه‌ای*\n\n"
                f"📍 استان: {province}\n"
                f"🗺 آدرس: {address}\n"
                f"🏗 کاربری: {land_use}\n"
                f"📐 متراژ: {area:,.0f} متر مربع\n\n"
                f"{info_text}\n\n"
                f"💰 *ارزش واحد: {unit_value:,} ریال*\n"
                f"💰 *ارزش کل: {total_value:,} ریال*\n\n"
                f"⚠️ خطا در ساخت PDF. نتایج به صورت متنی ارسال شد.",
                reply_markup=get_main_menu_kb(user_id),
            )

        # ── اطلاع به ادمین ──
        try:
            import datetime
            await bot.send_message(
                ADMIN_ID,
                f"💰 پرداخت ارزش منطقه‌ای:\n"
                f"👤 کاربر: {message.from_user.full_name} ({user_id})\n"
                f"📍 استان: {province}\n"
                f"🗺 آدرس: {address}\n"
                f"🏗 کاربری: {land_use}\n"
                f"📐 متراژ: {area:,.0f} متر مربع\n"
                f"💰 ارزش کل: {total_value:,} ریال\n"
                f"💵 هزینه: {REGIONAL_VALUE_FEE:,} تومان\n"
                f"⏱ زمان: {datetime.datetime.now().strftime('%Y/%m/%d %H:%M')}",
            )
        except Exception as e:
            logging.error(f"[RV] خطا در ارسال اطلاع به ادمین: {e}")

    except ValueError as e:
        await message.answer(
            f"⚠️ خطا در استعلام: {e}\n\n"
            f"لطفاً آدرس و استان را بررسی و از ابتدا تلاش کنید.",
            reply_markup=get_main_menu_kb(user_id),
        )
    except Exception as e:
        logging.error(f"[RV] خطا در پردازش استعلام ارزش منطقه‌ای: {e}", exc_info=True)
        await message.answer(
            "⚠️ خطایی در پردازش استعلام رخ داد. لطفاً چند دقیقه دیگر تلاش کنید.\n"
            "اگر مشکل ادامه داشت، با پشتیبانی تماس بگیرید.",
            reply_markup=get_main_menu_kb(user_id),
        )

    await state.clear()
