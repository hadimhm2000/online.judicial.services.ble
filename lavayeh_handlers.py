"""
هندلرهای بخش ثبت لایحه — فقط فلوی مکالمه تلگرام.
شامل پشتیبانی از عنوان «اعلام وکالت» با جریان خاص خود.
"""
import asyncio
import datetime
import logging
import os
import re

import aiohttp
import json as _json

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, PreCheckoutQuery, LabeledPrice

import runtime_state
from bale_file_sender import send_document_direct
from config import ADMIN_ID, CARD_NUMBER, ACCOUNT_NAME, BALE_WALLET_TOKEN, BOT_TOKEN, BALE_API_BASE, calculate_lavayeh_fee, format_lavayeh_fee_explanation, LAVAYEH_SERVICE_FEE, EZHHARNAMEH_SERVICE_FEE
from exempt_users import is_exempt_user
from sheets import log_event

from states import Form
from keyboards import (
    flow_type_kb, main_menu_kb, restart_kb, back_only_kb,
    lavayeh_title_kb, LAVAYEH_TITLES,
    lavayeh_tracking_method_kb,
    lavayeh_branch_input_method_kb,
    create_province_kb, PROVINCES,
    create_person_type_kb, representative_type_kb,
    add_or_finish_kb, lavayeh_confirm_kb, lavayeh_edit_kb,
    lavayeh_attachment_title_kb_first, lavayeh_attachment_title_kb,
    lavayeh_attachment_more_kb, lavayeh_cancel_reminder_kb,
    lavayeh_sign_ready_kb,
    # کیبوردهای اعلام وکالت
    ealam_more_lawyers_kb,
    ealam_more_contracts_kb,
    ealam_stamp_amount_kb,
    ealam_claim_type_kb,
    ealam_stamp_type_kb,
    continue_kb,
    bulk_choice_kb,
    bulk_input_method_kb,
    bulk_confirm_kb)
from stamp_duty import calculate_stamp_duty, format_result_fa
from bulk_submissions import (
    generate_sample_excel,
    parse_excel_file,
    parse_text_or_image_input,
    generate_tracking_code,
    BULK_TASKS,
    run_bulk_processing_task)

lavayeh_router = Router()

# ── include کردن روتر امضا ──────────────────────────────────────────────────
from lavayeh_sign_handlers import lavayeh_sign_router
lavayeh_router.include_router(lavayeh_sign_router)

# ── include کردن روتر شعب ──────────────────────────────────────────────────
from branches import branches_router
lavayeh_router.include_router(branches_router)

_FA_AR = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789"
)

def _to_en(text: str) -> str:
    return text.translate(_FA_AR).replace(" ", "").strip()

def _fmt(n: int) -> str:
    return f"{n:,}"


async def _maybe_return_to_preview(data: dict, message: Message, state: FSMContext) -> bool:
    if data.get("_is_editing"):
        await state.update_data(_is_editing=False)
        await _go_to_preview(message, state)
        return True
    return False


def validate_tracking_code(code: str):
    if not code.isdigit():
        return False, "⚠️ شماره پرونده باید فقط شامل عدد باشد."
    
    # بررسی ۴ رقم اول برای سال‌های ۱۴۰۰ تا ۱۴۰۷
    if len(code) >= 4:
        first_four = int(code[:4])
        if 1400 <= first_four <= 1407:
            if len(code) == 18:
                return True, code
            return False, (
                f"⚠️ شماره پرونده با سال *{code[:4]}* باید *۱۸ رقمی* باشد.\n"
                f"کد شما *{len(code)} رقمی* است. مجدداً وارد کنید:"
            )
    
    # بررسی دو رقم اول برای سال‌های ۱۳۹۹ و قبل‌تر
    if len(code) >= 2:
        first_two = int(code[:2])
        if 0 <= first_two <= 99:
            if len(code) == 16:
                return True, code
            return False, (
                f"⚠️ شماره پرونده باید *۱۶ رقمی* باشد.\n"
                f"کد شما *{len(code)} رقمی* است. مجدداً وارد کنید:"
            )
    
    return False, "⚠️ شماره پرونده نامعتبر است. مجدداً وارد کنید:"


def validate_archive_number(archive_num: str):
    """
    اعتبارسنجی شماره بایگانی:
    - اگر دو رقم اول ۰۰ تا ۰۷ باشد → باید ۷ رقمی باشد
    - اگر دو رقم اول ۹۳ تا ۹۹ باشد → باید ۶ رقمی باشد
    """
    if not archive_num.isdigit():
        return False, "⚠️ شماره بایگانی باید فقط شامل عدد باشد."
    
    if len(archive_num) < 2:
        return False, "⚠️ شماره بایگانی نامعتبر است. حداقل ۲ رقم وارد کنید."
    
    first_two = int(archive_num[:2])
    
    # بررسی دو رقم اول ۰۰ تا ۰۷
    if 0 <= first_two <= 7:
        if len(archive_num) == 7:
            return True, archive_num
        return False, (
            f"⚠️ شماره بایگانی با دو رقم اول *{archive_num[:2]}* باید *۷ رقمی* باشد.\n"
            f"شماره شما *{len(archive_num)} رقمی* است. مجدداً وارد کنید:"
        )
    
    # بررسی دو رقم اول ۹۳ تا ۹۹
    elif 93 <= first_two <= 99:
        if len(archive_num) == 6:
            return True, archive_num
        return False, (
            f"⚠️ شماره بایگانی با دو رقم اول *{archive_num[:2]}* باید *۶ رقمی* باشد.\n"
            f"شماره شما *{len(archive_num)} رقمی* است. مجدداً وارد کنید:"
        )
    
    else:
        return False, (
            f"⚠️ دو رقم اول شماره بایگانی (*{archive_num[:2]}*) نامعتبر است.\n"
            "باید بین *۰۰ تا ۰۷* (۷ رقمی) یا *۹۳ تا ۹۹* (۶ رقمی) باشد."
        )


def build_preview(data: dict) -> str:
    # بررسی عنوان اعلام وکالت
    if data.get("lavayeh_title") == "اعلام وکالت":
        return _build_ealam_preview(data)

    persons = data.get("lavayeh_persons", [])
    persons_text = ""
    for i, p in enumerate(persons, 1):
        ptype = p.get("person_type", "")
        if ptype == "شخص حقوقی":
            rep = p.get("representative_type", "")
            company_id = p.get("company_id", "")
            nat_id = p.get("national_id", "")
            persons_text += (
                f"  {i}. شخص حقوقی | شناسه شرکت: `{company_id}` | "
                f"نوع نماینده: {rep} | کدملی: `{nat_id}`\n"
            )
        else:
            nat_id = p.get("national_id", "")
            persons_text += f"  {i}. {ptype} | کدملی: `{nat_id}`\n"

    attachments = data.get("lavayeh_attachments", [])
    attachments_text = ""
    total_images = 0
    for i, att in enumerate(attachments, 1):
        n = len(att.get("images", []))
        total_images += n
        attachments_text += f"  {i}. {att.get('title', 'مستندات')} — {n} تصویر\n"
    if not attachments_text:
        attachments_text = "  (بدون مدرک)\n"

    text_preview = data.get("lavayeh_text", "")
    if len(text_preview) > 200:
        text_preview = text_preview[:200] + "..."

    # بررسی اینکه کدام روش برای ثبت استفاده شده
    tracking_method = data.get("tracking_method", "case_number")
    
    
    if tracking_method == "archive_number":
        # نمایش اطلاعات برای شماره بایگانی
        branch_code_str = f" (کد: `{data.get('lavayeh_branch_code', '---')}`)" if data.get('lavayeh_branch_code') else ""
        archive_info = (
            f"🔢 شماره بایگانی: `{data.get('lavayeh_archive_number', '---')}`\n"
            f"🏛 نام شعبه: *{data.get('lavayeh_branch_name', '---')}*{branch_code_str}\n"
            f"🏙 استان: *{data.get('lavayeh_province', '---')}*\n\n"
        )
    else:
        # نمایش اطلاعات برای شماره پرونده
        archive_info = (
            f"🔢 شماره پرونده: `{data.get('lavayeh_tracking_code', '---')}`\n"
            f"🏙 استان: *{data.get('lavayeh_province', '---')}*\n"
            f"🔢 ردیف فرعی: *{data.get('lavayeh_row_number', '---')}*\n\n"
        )

    return (
        f"📋 *پیش‌نمایش لایحه شما:*\n\n"
        f"📌 عنوان: *{data.get('lavayeh_title', '---')}*\n"
        f"{archive_info}"
        f"👥 اشخاص ارائه‌دهنده ({len(persons)} نفر):\n{persons_text}\n"
        f"📄 شرح متن:\n{text_preview}\n\n"
        f"🖼 مدارک ({total_images} تصویر در {len(attachments)} عنوان):\n{attachments_text}\n"
        f"آیا اطلاعات فوق صحیح است؟"
    )


def _build_ealam_preview(data: dict) -> str:
    lawyers = data.get("ealam_lawyers", [])
    contracts = data.get("ealam_contracts", [])
    stamp_amount = data.get("ealam_stamp_amount", 0)
    stamp_type = data.get("ealam_stamp_type", "")
    lavayeh_text = data.get("lavayeh_text", "")
    attachments = data.get("lavayeh_attachments", [])

    lawyers_text = "\n".join([f"  {i+1}. `{l}`" for i, l in enumerate(lawyers)]) or "  (ندارد)"
    contracts_text = "\n".join([f"  {i+1}. `{c}`" for i, c in enumerate(contracts)]) or "  (ندارد)"

    if stamp_type == "بدون تمبر":
        stamp_text = "بدون نیاز به تمبر"
    elif stamp_amount > 0:
        stamp_text = f"{_fmt(stamp_amount)} ریال ({stamp_type})"
    else:
        stamp_text = "بدون تمبر"

    text_preview = lavayeh_text[:200] + "..." if len(lavayeh_text) > 200 else lavayeh_text

    att_text = ""
    total_imgs = 0
    for i, att in enumerate(attachments, 1):
        n = len(att.get("images", []))
        total_imgs += n
        att_text += f"  {i}. {att.get('title', 'مستندات')} — {n} تصویر\n"
    if not att_text:
        att_text = "  (بدون مدرک)\n"

    # بررسی اینکه کدام روش برای ثبت استفاده شده
    tracking_method = data.get("tracking_method", "case_number")
    
    if tracking_method == "archive_number":
        # نمایش اطلاعات برای شماره بایگانی
        case_info = (
            f"🔢 شماره بایگانی: `{data.get('lavayeh_archive_number', '---')}`\n"
            f"🏛 نام شعبه: *{data.get('lavayeh_branch_name', '---')}*\n"
            f"🏙 استان: *{data.get('lavayeh_province', '---')}*\n\n"
        )
    else:
        # نمایش اطلاعات برای شماره پرونده
        case_info = (
            f"🔢 شماره پرونده: `{data.get('lavayeh_tracking_code', '---')}`\n"
            f"🏙 استان: *{data.get('lavayeh_province', '---')}*\n"
            f"🔢 ردیف فرعی: *{data.get('lavayeh_row_number', '---')}*\n\n"
        )

    return (
        f"📋 *پیش‌نمایش اعلام وکالت:*\n\n"
        f"{case_info}"
        f"👤 وکیل(ها):\n{lawyers_text}\n\n"
        f"📑 شماره(های) قرارداد:\n{contracts_text}\n\n"
        f"💰 تمبر: *{stamp_text}*\n\n"
        f"📄 شرح متن:\n{text_preview}\n\n"
        f"🖼 مدارک ({total_imgs} تصویر):\n{att_text}\n"
        f"آیا اطلاعات فوق صحیح است؟"
    )


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۱ — ورود به بخش لایحه
# ══════════════════════════════════════════════════════════════════════════════
@lavayeh_router.message(StateFilter("*"), F.text == "📝 ثبت لایحه")
async def lavayeh_entry(message: Message, state: FSMContext):
    user_id = message.from_user.id
    active = runtime_state.active_lavayeh_users if hasattr(runtime_state, "active_lavayeh_users") else set()
    if user_id in active:
        # پاکسازی حالت گیرکرده (مثلاً بعد از قطعی/کرش ربات)
        active.discard(user_id)
        await state.clear()
        logging.warning(f"[LAVAYEH] پاکسازی active_lavayeh_users گیرکرده برای user={user_id}")

    await state.clear()
    await state.update_data(lavayeh_persons=[], lavayeh_attachments=[], service_type="lavayeh")
    await message.answer(
        "📝 *ثبت لایحه*\n\n"
        "آیا قصد ثبت *یک مورد لایحه* دارید یا *بیش از ۵ مورد ثبتی (ثبت دسته‌جمعی)*؟\n\n"
        "💡 *توجه:* در صورتی که تعداد لوایح شما زیاد است (بیش از ۵ مورد)، برای صرفه‌جویی در زمان و جلوگیری از معطلی سایر مراجعان ربات، لطفاً گزینه *«⚡️ ثبت دسته‌جمعی سریع»* را انتخاب نمایید تا تمامی موارد در پس‌زمینه و بدون اختلال زمانی ثبت شوند.",
        reply_markup=bulk_choice_kb)
    await state.set_state(Form.bulk_mode_select)


@lavayeh_router.message(Form.bulk_mode_select)
async def bulk_mode_select_handler(message: Message, state: FSMContext):
    text = message.text or ""
    if text == "1️⃣ ثبت تکی (روال عادی)":
        await message.answer(
            "📝 *ثبت لایحه (روال تکی)*\n\nلطفاً عنوان لایحه خود را انتخاب فرمایید:",
            reply_markup=lavayeh_title_kb)
        await state.set_state(Form.lavayeh_title)
        return
    elif text == "⚡️ ثبت دسته‌جمعی سریع (بدون معطلی - فایل اکسل)":
        await message.answer(
            "⚡️ *ثبت دسته‌جمعی سریع لوایح*\n\n"
            "در این روش می‌توانید اطلاعات بیش از ۵ لایحه را با *فایل اکسل* ارسال فرمایید.\n"
            "✅ سیستم به صورت خودکار حتی در صورت بروز خطا در برخی ردیف‌ها، ثبت را متوقف نکرده و با انعطاف‌پذیری کامل پردازش را ادامه می‌دهد.\n\n"
            "لطفاً فایل اکسل نمونه را دریافت و تکمیل نمایید:",
            reply_markup=bulk_input_method_kb)
        await state.set_state(Form.bulk_input_method)
        return
    elif text == "🔙 بازگشت به منوی اصلی":
        await state.clear()
        await message.answer("بازگشت به منوی اصلی.", reply_markup=flow_type_kb)
        await state.set_state(Form.waiting_for_flow_type)
        return
    else:
        await message.answer("⚠️ لطفاً یکی از گزینه‌های منو را انتخاب فرمایید:", reply_markup=bulk_choice_kb)


@lavayeh_router.message(Form.bulk_input_method)
async def bulk_input_method_handler(message: Message, state: FSMContext):
    text = message.text or ""
    data = await state.get_data()
    service_type = data.get("service_type", "lavayeh")

    if text == "📊 دانلود نمونه اکسل و آپلود فایل":
        # import حذف شد — از send_document_direct استفاده می‌شود
        
        # انتخاب نام و مسیر فایل بر اساس نوع سرویس
        if service_type == "ezhharnameh":
            sample_path = "/tmp/sample_ezhharnameh_bulk.xlsx"
            generate_sample_excel("ezhharnameh", sample_path)
            file_name = "نمونه_ثبت_دسته_جمعی_اظهارنامه.xlsx"
            caption_text = (
                "📎 *فایل اکسل نمونه ثبت دسته‌جمعی اظهارنامه*\n\n"
                "📌 لطفاً فایل اکسل فوق را دانلود کرده و ستون‌ها را تکمیل فرمایید.\n"
                "💡 *نگران نباشید!* حتی اگر بعضی موارد (مثل فرمت کد ملی یا شناسه ملی) را هم درست یا کامل انتخاب نکنید، سیستم با پردازش هوشمند و جایگزینی مقادیر پیش‌فرض، مانع از اختلال یا توقف در روند ثبت خواهد شد.\n\n"
                "✅ اکنون فایل اکسل تکمیل‌شده خود را ارسال (آپلود) فرمایید:"
            )
        else:
            sample_path = "/tmp/sample_lavayeh_bulk.xlsx"
            generate_sample_excel("lavayeh", sample_path)
            file_name = "نمونه_ثبت_دسته_جمعی_لوایح.xlsx"
            caption_text = (
                "📎 *فایل اکسل نمونه ثبت دسته‌جمعی لوایح*\n\n"
                "📌 لطفاً فایل اکسل فوق را دانلود کرده و ستون‌ها را تکمیل فرمایید.\n"
                "💡 *نگران نباشید!* حتی اگر بعضی موارد (مثل فرمت کد ملی یا شناسه شعبه) را هم درست یا کامل انتخاب نکنید، سیستم با پردازش هوشمند و جایگزینی مقادیر پیش‌فرض، مانع از اختلال یا توقف در روند ثبت خواهد شد.\n\n"
                "✅ اکنون فایل اکسل تکمیل‌شده خود را ارسال (آپلود) فرمایید:"
            )
        
        try:
            await send_document_direct(
                message.chat.id, sample_path,
                filename=file_name,
                caption=caption_text,
                reply_markup=back_only_kb)
        except Exception as doc_err:
            logging.error(f"[BULK-SAMPLE] خطا در ارسال فایل نمونه: {doc_err}")
            await message.answer(
                "⚠️ خطا در ارسال فایل نمونه. لطفاً دوباره تلاش کنید.",
                reply_markup=bulk_input_method_kb)
            return
        await state.set_state(Form.bulk_file_upload)
        return
    elif text == "🔙 بازگشت":
        await message.answer(
            "آیا قصد ثبت تکی دارید یا دسته‌جمعی؟",
            reply_markup=bulk_choice_kb
        )
        await state.set_state(Form.bulk_mode_select)
        return
    else:
        await message.answer("⚠️ لطفاً یکی از گزینه‌های کیبورد را انتخاب فرمایید.", reply_markup=bulk_input_method_kb)


@lavayeh_router.message(Form.bulk_file_upload)
async def bulk_file_upload_handler(message: Message, state: FSMContext):
    from keyboards import bulk_attachment_row_kb
    data = await state.get_data()
    service_type = data.get("service_type", "lavayeh")
    items = []

    if message.text and message.text == "🔙 بازگشت":
        await message.answer("انتخاب روش ارسال دسته‌جمعی:", reply_markup=bulk_input_method_kb)
        await state.set_state(Form.bulk_input_method)
        return

    # ۱. بررسی فایل اکسل
    if message.document:
        doc = message.document
        if not (doc.file_name and doc.file_name.endswith(('.xlsx', '.xls'))):
            await message.answer("⚠️ لطفاً فقط فایل با پسوند اکسل (.xlsx) ارسال فرمایید.")
            return
        bot = message.bot
        file_id = doc.file_id
        file_info = await bot.get_file(file_id)
        local_path = f"/tmp/{doc.file_name}"
        await bot.download_file(file_info.file_path, local_path)
        items = parse_excel_file(local_path, service_type)
        if not items:
            await message.answer("⚠️ فایلی که ارسال کردید خالی بود یا قابل خواندن نبود. لطفاً مجدداً تلاش کنید.")
            return

    else:
        await message.answer("⚠️ لطفاً فقط فایل اکسل (.xlsx) معتبر ارسال فرمایید.")
        return

    tracking_code = generate_tracking_code("LYH" if service_type == "lavayeh" else "EZH")
    
    # ذخیره آیتم‌ها با لیست خالی پیوست برای هر ردیف
    for item in items:
        item["attachments"] = []
    
    await state.update_data(
        bulk_items=items, 
        bulk_tracking_code=tracking_code,
        bulk_current_row_index=0,  # شروع از ردیف اول برای پیوست‌گذاری
        bulk_current_row_attachments=[]
    )

    service_fa = "لایحه" if service_type == "lavayeh" else "اظهارنامه"
    preview_text = (
        f"✅ *خلاصه موارد دریافت‌شده برای ثبت دسته‌جمعی {service_fa}*\n\n"
        f"🔖 کد رهگیری اختصاصی: `{tracking_code}`\n"
        f"📦 تعداد کل موارد: *{len(items)} {service_fa}*\n"
        f"🛡 وضعیت بررسی نقص: *تایید شده*\n\n"
        f"📎 *مرحله پیوست‌گذاری:*\n"
        f"اکنون می‌توانید برای هر ردیف از فایل اکسل، پیوست‌های مربوطه را ارسال نمایید.\n\n"
        f"🔢 *ردیف ۱ از {len(items)}:*\n"
    )
    
    # نمایش اطلاعات ردیف اول
    if items:
        first_item = items[0]
        if service_type == "lavayeh":
            preview_text += f"📋 شماره پرونده: `{first_item.get('tracking_code', '-')}`\n"
            preview_text += f"📝 عنوان: {first_item.get('title', '-')}\n"
        else:
            preview_text += f"👤 اظهارکننده: `{first_item.get('declarant_id', '-')}`\n"
            preview_text += f"📝 عنوان: {first_item.get('subject', '-')}\n"
    
    preview_text += "\nآیا می‌خواهید پیوستی برای این ردیف ارسال کنید؟"
    
    await message.answer(preview_text, reply_markup=bulk_attachment_row_kb)
    await state.set_state(Form.bulk_attachment_row)


# ══════════════════════════════════════════════════════════════════════════════
# هندلرهای پیوست‌گذاری برای ثبت دسته‌جمعی
# ══════════════════════════════════════════════════════════════════════════════

@lavayeh_router.message(Form.bulk_attachment_row)
async def bulk_attachment_row_handler(message: Message, state: FSMContext):
    from keyboards import bulk_attachment_row_kb, bulk_attachment_more_kb
    text = message.text or ""
    data = await state.get_data()
    items = data.get("bulk_items", [])
    current_index = data.get("bulk_current_row_index", 0)
    service_type = data.get("service_type", "lavayeh")
    
    if text == "📎 افزودن پیوست برای این ردیف":
        # رفتن به مرحله انتخاب عنوان پیوست
        await message.answer(
            f"📄 *عنوان پیوست برای ردیف {current_index + 1}:*\n\n"
            "لطفاً عنوان پیوست را وارد کنید (مثلاً «کارت ملی»، «وکالتنامه»، «مستندات»):\n\n"
            "یا بنویسید: *مستندات* (برای عنوان پیش‌فرض)",
            reply_markup=back_only_kb)
        await state.set_state(Form.bulk_attachment_title)
        return
    
    elif text == "⏭ رد شدن از این ردیف (بدون پیوست)":
        # ذخیره پیوست‌های ردیف فعلی (که خالی است) و رفتن به ردیف بعدی
        current_attachments = data.get("bulk_current_row_attachments", [])
        if current_index < len(items):
            items[current_index]["attachments"] = current_attachments
        
        next_index = current_index + 1
        if next_index >= len(items):
            # همه ردیف‌ها بررسی شدند، رفتن به مرحله تایید
            await state.update_data(bulk_items=items)
            await _go_to_bulk_confirm(message, state)
            return
        
        # رفتن به ردیف بعدی
        await state.update_data(
            bulk_items=items,
            bulk_current_row_index=next_index,
            bulk_current_row_attachments=[]
        )
        
        # نمایش اطلاعات ردیف بعدی
        next_item = items[next_index]
        service_fa = "لایحه" if service_type == "lavayeh" else "اظهارنامه"
        row_text = f"🔢 *ردیف {next_index + 1} از {len(items)}:*\n"
        
        if service_type == "lavayeh":
            row_text += f"📋 شماره پرونده: `{next_item.get('tracking_code', '-')}`\n"
            row_text += f"📝 عنوان: {next_item.get('title', '-')}\n"
        else:
            row_text += f"👤 اظهارکننده: `{next_item.get('declarant_id', '-')}`\n"
            row_text += f"📝 عنوان: {next_item.get('subject', '-')}\n"
        
        row_text += "\nآیا می‌خواهید پیوستی برای این ردیف ارسال کنید؟"
        
        await message.answer(row_text, reply_markup=bulk_attachment_row_kb)
        return
    
    elif text == "✅ اتمام پیوست‌گذاری و ادامه":
        # ذخیره پیوست‌های ردیف فعلی و رفتن به تایید نهایی
        current_attachments = data.get("bulk_current_row_attachments", [])
        if current_index < len(items):
            items[current_index]["attachments"] = current_attachments
        await state.update_data(bulk_items=items)
        await _go_to_bulk_confirm(message, state)
        return
    
    elif text == "❌ انصراف":
        await state.clear()
        await message.answer("عملیات لغو شد. بازگشت به منوی اصلی.", reply_markup=flow_type_kb)
        await state.set_state(Form.waiting_for_flow_type)
        return
    
    else:
        await message.answer("⚠️ لطفاً یکی از گزینه‌های منو را انتخاب فرمایید:", reply_markup=bulk_attachment_row_kb)


@lavayeh_router.message(Form.bulk_attachment_title)
async def bulk_attachment_title_handler(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    
    if text == "🔙 بازگشت":
        from keyboards import bulk_attachment_row_kb
        await message.answer("انتخاب نوع عملیات:", reply_markup=bulk_attachment_row_kb)
        await state.set_state(Form.bulk_attachment_row)
        return
    
    if not text:
        await message.answer("⚠️ لطفاً عنوان پیوست را وارد کنید:")
        return
    
    title = "مستندات" if text.lower() in ["مستندات", "مدارک", "پیوست"] else text
    await state.update_data(
        bulk_current_attachment_title=title,
        bulk_current_attachment_images=[]
    )
    
    await message.answer(
        f"✅ عنوان «*{title}*» ثبت شد.\n\n"
        "🖼 لطفاً تصاویر مربوط به این پیوست را به صورت *عکس (Photo)* ارسال فرمایید.\n"
        "⚠️ فقط فرمت *JPG / JPEG* قابل قبول است.\n\n"
        "پس از ارسال همه تصاویر، دکمه *«✅ اتمام ارسال تصاویر»* را بفشارید.",
        reply_markup=ReplyKeyboardRemove())
    await state.set_state(Form.bulk_attachment_images)


@lavayeh_router.message(Form.bulk_attachment_images, F.photo)
async def bulk_attachment_images_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    images = data.get("bulk_current_attachment_images", [])
    file_id = message.photo[-1].file_id
    images.append(file_id)
    await state.update_data(bulk_current_attachment_images=images)
    
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    manage_kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ اتمام ارسال تصاویر")],
        ],
        resize_keyboard=True
    )
    
    await message.reply(
        f"✅ تصویر شماره *{len(images)}* دریافت شد.\n"
        f"مجموع تصاویر این پیوست: *{len(images)} تصویر*\n\n"
        "می‌توانید تصاویر بیشتری ارسال کنید یا «اتمام» را بزنید.",
        reply_markup=manage_kb)


@lavayeh_router.message(Form.bulk_attachment_images, F.text == "✅ اتمام ارسال تصاویر")
async def bulk_attachment_images_done_handler(message: Message, state: FSMContext):
    from keyboards import bulk_attachment_more_kb
    data = await state.get_data()
    images = data.get("bulk_current_attachment_images", [])
    title = data.get("bulk_current_attachment_title", "مستندات")
    current_attachments = data.get("bulk_current_row_attachments", [])
    
    if not images:
        await message.answer("⚠️ هیچ تصویری ارسال نشده است. لطفاً حداقل یک تصویر ارسال کنید یا بازگشت بزنید.")
        return
    
    # افزودن این پیوست به لیست پیوست‌های ردیف
    current_attachments.append({
        "title": title,
        "images": images
    })
    
    await state.update_data(
        bulk_current_row_attachments=current_attachments,
        bulk_current_attachment_images=[],
        bulk_current_attachment_title=""
    )
    
    await message.answer(
        f"✅ پیوست «{title}» با {len(images)} تصویر ثبت شد.\n\n"
        "آیا پیوست دیگری برای این ردیف دارید؟",
        reply_markup=bulk_attachment_more_kb)
    await state.set_state(Form.bulk_attachment_more)


@lavayeh_router.message(Form.bulk_attachment_images)
async def bulk_attachment_images_text_handler(message: Message, state: FSMContext):
    await message.answer(
        "⚠️ لطفاً تصاویر را به صورت *عکس (Photo)* ارسال کنید.\n"
        "یا «اتمام ارسال تصاویر» را بزنید.")


@lavayeh_router.message(Form.bulk_attachment_more)
async def bulk_attachment_more_handler(message: Message, state: FSMContext):
    from keyboards import bulk_attachment_row_kb
    text = message.text or ""
    data = await state.get_data()
    items = data.get("bulk_items", [])
    current_index = data.get("bulk_current_row_index", 0)
    service_type = data.get("service_type", "lavayeh")
    
    if text == "➕ افزودن پیوست دیگر برای این ردیف":
        await message.answer(
            f"📄 *عنوان پیوست جدید برای ردیف {current_index + 1}:*\n\n"
            "لطفاً عنوان پیوست را وارد کنید:",
            reply_markup=back_only_kb)
        await state.set_state(Form.bulk_attachment_title)
        return
    
    elif text == "✅ اتمام پیوست این ردیف و رفتن به ردیف بعدی":
        # ذخیره پیوست‌های ردیف فعلی
        current_attachments = data.get("bulk_current_row_attachments", [])
        if current_index < len(items):
            items[current_index]["attachments"] = current_attachments
        
        next_index = current_index + 1
        if next_index >= len(items):
            # همه ردیف‌ها بررسی شدند
            await state.update_data(bulk_items=items)
            await _go_to_bulk_confirm(message, state)
            return
        
        # رفتن به ردیف بعدی
        await state.update_data(
            bulk_items=items,
            bulk_current_row_index=next_index,
            bulk_current_row_attachments=[]
        )
        
        next_item = items[next_index]
        service_fa = "لایحه" if service_type == "lavayeh" else "اظهارنامه"
        row_text = f"🔢 *ردیف {next_index + 1} از {len(items)}:*\n"
        
        if service_type == "lavayeh":
            row_text += f"📋 شماره پرونده: `{next_item.get('tracking_code', '-')}`\n"
            row_text += f"📝 عنوان: {next_item.get('title', '-')}\n"
        else:
            row_text += f"👤 اظهارکننده: `{next_item.get('declarant_id', '-')}`\n"
            row_text += f"📝 عنوان: {next_item.get('subject', '-')}\n"
        
        row_text += "\nآیا می‌خواهید پیوستی برای این ردیف ارسال کنید؟"
        
        await message.answer(row_text, reply_markup=bulk_attachment_row_kb)
        await state.set_state(Form.bulk_attachment_row)
        return
    
    elif text == "❌ انصراف":
        await state.clear()
        await message.answer("عملیات لغو شد. بازگشت به منوی اصلی.", reply_markup=flow_type_kb)
        await state.set_state(Form.waiting_for_flow_type)
        return
    
    else:
        from keyboards import bulk_attachment_more_kb
        await message.answer("⚠️ لطفاً یکی از گزینه‌های منو را انتخاب فرمایید:", reply_markup=bulk_attachment_more_kb)


async def _go_to_bulk_confirm(message: Message, state: FSMContext):
    """رفتن به مرحله تایید نهایی ثبت دسته‌جمعی"""
    data = await state.get_data()
    items = data.get("bulk_items", [])
    tracking_code = data.get("bulk_tracking_code", "")
    service_type = data.get("service_type", "lavayeh")
    service_fa = "لایحه" if service_type == "lavayeh" else "اظهارنامه"
    
    # شمارش پیوست‌ها
    total_attachments = sum(len(item.get("attachments", [])) for item in items)
    
    preview_text = (
        f"✅ *خلاصه نهایی ثبت دسته‌جمعی {service_fa}*\n\n"
        f"🔖 کد رهگیری: `{tracking_code}`\n"
        f"📦 تعداد موارد: *{len(items)} {service_fa}*\n"
        f"📎 تعداد پیوست‌ها: *{total_attachments} پیوست*\n\n"
        f"⚠️ *توجه مهم:*\n"
        f"پس از تایید، فایل اکسل و پیوست‌ها برای *تایید مدیر* ارسال می‌شود.\n"
        f"پس از تایید مدیر، پردازش خودکار آغاز خواهد شد.\n\n"
        f"آیا تایید می‌کنید؟"
    )
    
    await message.answer(preview_text, reply_markup=bulk_confirm_kb)
    await state.set_state(Form.bulk_confirm)


@lavayeh_router.message(Form.bulk_confirm)
async def bulk_confirm_handler(message: Message, state: FSMContext):
    text = message.text or ""
    data = await state.get_data()
    tracking_code = data.get("bulk_tracking_code", generate_tracking_code("LYH"))
    items = data.get("bulk_items", [])
    service_type = data.get("service_type", "lavayeh")

    if text == "✅ تایید و ارسال برای مدیر":
        service_fa = "لایحه" if service_type == "lavayeh" else "اظهارنامه"
        total_attachments = sum(len(item.get("attachments", [])) for item in items)
        
        # ذخیره در BULK_TASKS
        BULK_TASKS[tracking_code] = {
            "user_id": message.from_user.id,
            "username": message.from_user.username or message.from_user.first_name,
            "service_type": service_type,
            "items": items,
            "status": "pending_admin",  # در انتظار تایید مدیر
            "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # ارسال پیام به مدیر برای تایید — بدون فرمت Markdown
        admin_message = (
            f"📋 درخواست جدید ثبت دسته‌جمعی {service_fa}\n\n"
            f"🔖 کد رهگیری: {tracking_code}\n"
            f"👤 کاربر: @{message.from_user.username or message.from_user.first_name} (ID: {message.from_user.id})\n"
            f"📦 تعداد موارد: {len(items)} {service_fa}\n"
            f"📎 تعداد پیوست‌ها: {total_attachments} پیوست\n"
            f"⏰ زمان درخواست: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"📄 جزئیات ردیف‌ها:\n"
        )
        
        # نمایش جزئیات چند ردیف اول
        for i, item in enumerate(items[:5], 1):
            if service_type == "lavayeh":
                admin_message += f"• ردیف {i}: پرونده {item.get('tracking_code', '-')} - {item.get('title', '-')}\n"
            else:
                admin_message += f"• ردیف {i}: اظهارکننده {item.get('declarant_id', '-')} - {item.get('subject', '-')}\n"
        
        if len(items) > 5:
            admin_message += f"... و {len(items) - 5} ردیف دیگر\n"
        
        admin_message += (
            f"\n⚠️ برای تایید یا رد این درخواست، لطفاً دستورات زیر را ارسال کنید:\n"
            f"✅ تایید: /approve_bulk {tracking_code}\n"
            f"❌ رد: /reject_bulk {tracking_code}"
        )
        
        try:
            await message.bot.send_message(ADMIN_ID, admin_message)
            logging.info(f"[BULK] اطلاع به مدیر ارسال شد برای {tracking_code}.")
        except Exception as e:
            logging.error(f"[BULK] خطا در ارسال به مدیر: {e}", exc_info=True)
        
        await state.clear()
        await message.answer(
            f"✅ *درخواست شما برای تایید مدیر ارسال شد!*\n\n"
            f"🔖 کد رهگیری: `{tracking_code}`\n"
            f"📦 تعداد موارد: *{len(items)} {service_fa}*\n\n"
            f"⏳ پس از تایید مدیر، پردازش خودکار آغاز خواهد شد و نتیجه برای شما ارسال می‌گردد.\n\n"
            f"شما می‌توانید به منوی اصلی بازگردید و سایر امور خود را انجام دهید.",
            reply_markup=flow_type_kb)
        await state.set_state(Form.waiting_for_flow_type)
        return
    elif text == "🔄 ارسال مجدد فایل / اصلاح":
        await message.answer("لطفاً روش ارسال اطلاعات را مجدداً انتخاب کنید:", reply_markup=bulk_input_method_kb)
        await state.set_state(Form.bulk_input_method)
        return
    elif text == "❌ انصراف و بازگشت" or text == "🔙 بازگشت به منوی اصلی":
        await state.clear()
        await message.answer("عملیات لغو شد. بازگشت به منوی اصلی.", reply_markup=flow_type_kb)
        await state.set_state(Form.waiting_for_flow_type)
        return
    else:
        await message.answer("⚠️ لطفاً یکی از گزینه‌های منو را انتخاب فرمایید:", reply_markup=bulk_confirm_kb)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۱ — انتخاب عنوان لایحه
# ══════════════════════════════════════════════════════════════════════════════
@lavayeh_router.message(Form.lavayeh_title)
async def lavayeh_get_title(message: Message, state: FSMContext):
    text = message.text or ""

    if text == "🔙 بازگشت به منوی اصلی":
        await state.clear()
        await message.answer("بازگشت به منوی اصلی.", reply_markup=flow_type_kb)
        await state.set_state(Form.waiting_for_flow_type)
        return

    if text not in LAVAYEH_TITLES:
        await message.answer("⚠️ لطفاً یکی از گزینه‌های موجود را انتخاب کنید:", reply_markup=lavayeh_title_kb)
        return

    system_title = "لایحه دفاعیه" if text == "سایر عناوین" else text
    await state.update_data(
        lavayeh_title=text,
        lavayeh_system_title=system_title,
        ealam_lawyers=[],
        ealam_contracts=[],
        ealam_stamp_amount=0,
        ealam_stamp_type="")

    data = await state.get_data()
    if await _maybe_return_to_preview(data, message, state):
        return

    await message.answer(
        f"✅ عنوان «*{text}*» انتخاب شد.\n\n"
        "🔢 لطفاً روش ثبت شماره پرونده را انتخاب فرمایید:",
        reply_markup=lavayeh_tracking_method_kb)
    await state.set_state(Form.lavayeh_tracking_method)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۱.۵ — انتخاب روش: شماره پرونده یا شماره بایگانی
# ══════════════════════════════════════════════════════════════════════════════
@lavayeh_router.message(Form.lavayeh_tracking_method)
async def lavayeh_get_tracking_method(message: Message, state: FSMContext):
    text = message.text or ""
    
    if text == "🔙 بازگشت":
        await message.answer("📝 لطفاً عنوان لایحه را دوباره انتخاب کنید:", reply_markup=lavayeh_title_kb)
        await state.set_state(Form.lavayeh_title)
        return
    
    if text == "1️⃣ شماره پرونده و ردیف فرعی":
        # مسیر فعلی - شماره پرونده
        await state.update_data(tracking_method="case_number")
        await message.answer(
            "🔢 لطفاً *شماره پرونده* را ارسال فرمایید:\n\n"
            "_(پرونده‌های ۱۴۰۰ تا ۱۴۰۷: ۱۸ رقمی | پرونده‌های ۹۹ و قبل‌تر: ۱۶ رقمی)_",
            reply_markup=back_only_kb)
        await state.set_state(Form.lavayeh_tracking_code)
        return
    
    if text == "2️⃣ شعبه رسیدگی کننده و شماره بایگانی":
        # مسیر جدید - شماره بایگانی
        await state.update_data(tracking_method="archive_number")
        await message.answer(
            "🔢 لطفاً *شماره بایگانی* را ارسال فرمایید:\n\n"
            "📌 *توجه:*\n"
            "• اگر دو رقم اول شماره بایگانی *۰۰ تا ۰۷* است، باید *۷ رقمی* باشد\n"
            "• اگر دو رقم اول شماره بایگانی *۹۳ تا ۹۹* است، باید *۶ رقمی* باشد",
            reply_markup=back_only_kb)
        await state.set_state(Form.lavayeh_archive_number)
        return
    
    await message.answer("⚠️ لطفاً یکی از گزینه‌های موجود را انتخاب کنید:", reply_markup=lavayeh_tracking_method_kb)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۲.۱ — دریافت شماره بایگانی (مسیر جدید)
# ══════════════════════════════════════════════════════════════════════════════
@lavayeh_router.message(Form.lavayeh_archive_number)
async def lavayeh_get_archive_number(message: Message, state: FSMContext):
    if not message.text:
        return
    
    if message.text == "🔙 بازگشت":
        await message.answer("🔢 لطفاً روش ثبت شماره پرونده را دوباره انتخاب کنید:", reply_markup=lavayeh_tracking_method_kb)
        await state.set_state(Form.lavayeh_tracking_method)
        return
    
    archive_num = _to_en(message.text)
    valid, result = validate_archive_number(archive_num)
    
    if not valid:
        await message.answer(result)
        return
    
    await state.update_data(lavayeh_archive_number=archive_num)
    
    # import کیبورد جدید
    from keyboards import lavayeh_branch_input_method_kb
    
    await message.answer(
        "✅ شماره بایگانی ثبت شد.\n\n"
        "🏛 لطفاً نحوه ورود *نام شعبه* را انتخاب کنید:",
        reply_markup=lavayeh_branch_input_method_kb)
    await state.set_state(Form.lavayeh_branch_input_method)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۲.۱.۵ — انتخاب نحوه ورود نام شعبه (مسیر جدید)
# ══════════════════════════════════════════════════════════════════════════════
@lavayeh_router.message(Form.lavayeh_branch_input_method)
async def lavayeh_get_branch_input_method(message: Message, state: FSMContext):
    text = message.text or ""
    
    if text == "🔙 بازگشت":
        await message.answer(
            "🔢 لطفاً شماره بایگانی را مجدداً ارسال فرمایید:",
            reply_markup=back_only_kb
        )
        await state.set_state(Form.lavayeh_archive_number)
        return
    
    from keyboards import lavayeh_branch_input_method_kb, back_only_kb
    from branches import UNITS_DATA, create_branches_keyboard, ROOT_NODES
    
    if text == "🔍 انتخاب شعبه از لیست" or text == "🔍 انتخاب از لیست شعب":
        # انتخاب از لیست - بدون گزینه ورود دستی
        if not UNITS_DATA:
            await message.answer(
                "⚠️ متأسفانه لیست شعب در دسترس نیست.\n"
                "لطفاً با پشتیبانی تماس بگیرید.",
                reply_markup=back_only_kb
            )
            await state.set_state(Form.lavayeh_archive_number)
            return
        
        # حذف کیبورد معمولی و نمایش کیبورد inline
        await message.answer(
            "🏛 *سامانه انتخاب شعبه قضایی*\n\n"
            "لطفاً از لیست زیر شروع کنید و تا رسیدن به واحد نهایی (شعبه) ادامه دهید:\n\n"
            "ℹ️ فقط واحدهای نهایی که دارای کد هستند قابل انتخاب می‌باشند.",
            reply_markup=ReplyKeyboardRemove())
        
        await message.answer(
            "📂 *قوه قضائیه - سطح اول*",
            reply_markup=create_branches_keyboard(ROOT_NODES, page=0, parent_id=None))
        # state را به lavayeh_branch_name تغییر می‌دهیم تا callback handler آن را بگیرد
        await state.set_state(Form.lavayeh_branch_name)
        return
    
    await message.answer(
        "⚠️ لطفاً گزینه «انتخاب شعبه از لیست» را انتخاب کنید:",
        reply_markup=lavayeh_branch_input_method_kb
    )


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۲.۲ — دریافت نام شعبه (فقط از طریق callback - ورود دستی حذف شده)
# ══════════════════════════════════════════════════════════════════════════════
@lavayeh_router.message(Form.lavayeh_branch_name)
async def lavayeh_get_branch_name(message: Message, state: FSMContext):
    """
    این handler فقط برای پیام‌های بازگشت است.
    انتخاب شعبه از طریق callback در branches.py انجام می‌شود.
    """
    text = message.text or ""
    
    if text == "🔙 بازگشت":
        from keyboards import lavayeh_branch_input_method_kb
        await message.answer(
            "🔢 لطفاً شماره بایگانی را مجدداً ارسال فرمایید:",
            reply_markup=back_only_kb
        )
        await state.set_state(Form.lavayeh_archive_number)
        return
    
    # اگر متن دیگری ارسال شد، پیام راهنما نمایش می‌دهیم
    await message.answer(
        "⚠️ لطفاً از دکمه‌های روی صفحه برای انتخاب شعبه استفاده کنید.\n\n"
        "در صورتی که می‌خواهید انصراف دهید، /start را بزنید.")


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۲ — شماره پرونده (مسیر اصلی)
# ══════════════════════════════════════════════════════════════════════════════
@lavayeh_router.message(Form.lavayeh_tracking_code)
async def lavayeh_get_tracking_code(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == "🔙 بازگشت":
        await message.answer("🔢 لطفاً روش ثبت شماره پرونده را دوباره انتخاب کنید:", reply_markup=lavayeh_tracking_method_kb)
        await state.set_state(Form.lavayeh_tracking_method)
        return
    code = _to_en(message.text)
    valid, result = validate_tracking_code(code)
    if not valid:
        await message.answer(result)
        return
    await state.update_data(lavayeh_tracking_code=code)
    data = await state.get_data()
    if await _maybe_return_to_preview(data, message, state):
        return
    await message.answer(
        "🏙 لطفاً *استان* مربوط به پرونده را انتخاب فرمایید:",
        reply_markup=create_province_kb())
    await state.set_state(Form.lavayeh_province)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۲.۵ — انتخاب استان
# ══════════════════════════════════════════════════════════════════════════════
@lavayeh_router.message(Form.lavayeh_province)
async def lavayeh_get_province(message: Message, state: FSMContext):
    text = message.text or ""
    data = await state.get_data()
    tracking_method = data.get("tracking_method", "case_number")
    
    if text == "🔙 بازگشت":
        # بازگشت به مرحله قبل بستگی به روش انتخاب شده دارد
        if tracking_method == "archive_number":
            await message.answer(
                "🏛 لطفاً نام شعبه خود را مجدداً تعیین کنید:",
                reply_markup=back_only_kb
            )
            await state.set_state(Form.lavayeh_branch_name)
        else:
            await message.answer("🔢 لطفاً شماره پرونده را مجدداً ارسال فرمایید:", reply_markup=ReplyKeyboardRemove())
            await state.set_state(Form.lavayeh_tracking_code)
        return
    
    if text not in PROVINCES:
        await message.answer("⚠️ لطفاً استان را از لیست انتخاب کنید:", reply_markup=create_province_kb())
        return
    
    await state.update_data(lavayeh_province=text)
    data = await state.get_data()
    
    if await _maybe_return_to_preview(data, message, state):
        return
    
    # اگر از شماره بایگانی استفاده شده، نیازی به ردیف فرعی نیست
    if tracking_method == "archive_number":
        # رفتن مستقیم به بخش اشخاص یا مرحله بعد
        title = data.get("lavayeh_title", "")
        if title == "اعلام وکالت":
            await message.answer(
                f"✅ استان «*{text}*» ثبت شد.\n\n"
                "👤 لطفاً *کدملی وکیل* را ارسال فرمایید:",
                reply_markup=back_only_kb)
            await state.set_state(Form.ealam_vakalaht_national_id)
        else:
            await message.answer(
                f"✅ استان «*{text}*» ثبت شد.\n\n"
                "👥 لطفاً نوع شخصیت ارائه‌دهنده لایحه را انتخاب کنید:",
                reply_markup=create_person_type_kb())
            await state.set_state(Form.lavayeh_person_type)
    else:
        # درخواست ردیف فرعی
        await message.answer(
            f"✅ استان «*{text}*» ثبت شد.\n\n"
            "🔢 لطفاً *ردیف فرعی پرونده* را وارد فرمایید:\n_(عدد بین ۱ تا ۳۰)_",
            reply_markup=back_only_kb)
        await state.set_state(Form.lavayeh_row_number)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۳ — ردیف فرعی
# ══════════════════════════════════════════════════════════════════════════════
@lavayeh_router.message(Form.lavayeh_row_number)
async def lavayeh_get_row_number(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == "🔙 بازگشت":
        await message.answer("🏙 لطفاً استان را دوباره انتخاب کنید:", reply_markup=create_province_kb())
        await state.set_state(Form.lavayeh_province)
        return
    num_str = _to_en(message.text)
    if not num_str.isdigit():
        await message.answer("⚠️ لطفاً یک عدد وارد کنید (۱ تا ۳۰):")
        return
    num = int(num_str)
    if not (1 <= num <= 30):
        await message.answer("⚠️ ردیف فرعی باید بین *۱ تا ۳۰* باشد:")
        return
    await state.update_data(lavayeh_row_number=num)
    data = await state.get_data()
    if await _maybe_return_to_preview(data, message, state):
        return

    # ── اگر عنوان «اعلام وکالت» بود، جریان خاص ─────────────────────────
    if data.get("lavayeh_title") == "اعلام وکالت":
        await message.answer(
            "🔢 لطفاً *کد ملی وکیل* را وارد فرمایید:\n_(۱۰ رقمی)_",
            reply_markup=back_only_kb)
        await state.set_state(Form.ealam_vakalaht_national_id)
        return

    # جریان عادی
    await state.update_data(lavayeh_persons=[], _current_person_index=0)
    await message.answer(
        "👤 لطفاً مشخص فرمایید ارائه‌دهنده لایحه *جزو کدام دسته* می‌باشد:",
        reply_markup=create_person_type_kb())
    await state.set_state(Form.lavayeh_person_type)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۴ — نوع شخص (جریان عادی)
# ══════════════════════════════════════════════════════════════════════════════
@lavayeh_router.message(Form.lavayeh_person_type)
async def lavayeh_get_person_type(message: Message, state: FSMContext):
    text = message.text or ""
    data = await state.get_data()
    persons = data.get("lavayeh_persons", [])

    if text == "✅ خیر، ادامه مراحل":
        if not persons:
            await message.answer("⚠️ حداقل یک شخص باید ارائه‌دهنده لایحه باشد.")
            return
        if await _maybe_return_to_preview(data, message, state):
            return
        await message.answer(
            "📄 *شرح متن لایحه:*\n\nلطفاً متن کامل لایحه خود را ارسال فرمایید.\n\n💡 همچنین می‌توانید فایل .docx را ارسال کنید (با حفظ فرمت بولد و ...).",
            reply_markup=ReplyKeyboardRemove())
        await state.set_state(Form.lavayeh_text)
        return

    if text not in ["شخص حقیقی", "شخص حقوقی", "وکیل"]:
        first_types = [p.get("person_type") for p in persons]
        await message.answer(
            "⚠️ لطفاً یکی از گزینه‌های موجود را انتخاب کنید:",
            reply_markup=create_person_type_kb(exclude=first_types if persons else [])
        )
        return

    await state.update_data(_current_person={"person_type": text})

    if text == "شخص حقوقی":
        await message.answer(
            "🏢 لطفاً *شناسه ملی شرکت* را ارسال فرمایید:\n_(۱۱ رقمی)_",
            reply_markup=back_only_kb)
        await state.set_state(Form.lavayeh_company_id)
    else:
        await message.answer(
            f"🔢 لطفاً *کد ملی* {'وکیل' if text == 'وکیل' else 'شخص'} ارائه‌دهنده را وارد کنید:\n_(۱۰ رقمی)_",
            reply_markup=back_only_kb)
        await state.set_state(Form.lavayeh_national_id)


@lavayeh_router.message(Form.lavayeh_company_id)
async def lavayeh_get_company_id(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == "🔙 بازگشت":
        data = await state.get_data()
        persons = data.get("lavayeh_persons", [])
        first_types = [p.get("person_type") for p in persons]
        await message.answer(
            "👤 لطفاً نوع شخص را دوباره انتخاب کنید:",
            reply_markup=create_person_type_kb(exclude=first_types if persons else [])
        )
        await state.set_state(Form.lavayeh_person_type)
        return
    company_id = _to_en(message.text)
    if not company_id.isdigit() or len(company_id) != 11:
        await message.answer("⚠️ شناسه ملی شرکت باید *۱۱ رقمی* باشد:")
        return
    data = await state.get_data()
    current_person = data.get("_current_person", {})
    current_person["company_id"] = company_id
    await state.update_data(_current_person=current_person)
    await message.answer("👔 لایحه توسط چه کسی ارائه می‌گردد؟", reply_markup=representative_type_kb)
    await state.set_state(Form.lavayeh_representative_type)


@lavayeh_router.message(Form.lavayeh_representative_type)
async def lavayeh_get_representative_type(message: Message, state: FSMContext):
    text = message.text or ""
    if text not in ["مدیرعامل", "نماینده"]:
        await message.answer("⚠️ لطفاً یکی از گزینه‌ها را انتخاب کنید:", reply_markup=representative_type_kb)
        return
    data = await state.get_data()
    current_person = data.get("_current_person", {})
    current_person["representative_type"] = text
    await state.update_data(_current_person=current_person)
    await message.answer(
        f"🔢 لطفاً *کد ملی {text}* را وارد کنید:\n_(۱۰ رقمی)_",
        reply_markup=back_only_kb)
    await state.set_state(Form.lavayeh_national_id)


@lavayeh_router.message(Form.lavayeh_national_id)
async def lavayeh_get_national_id(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == "🔙 بازگشت":
        data = await state.get_data()
        persons = data.get("lavayeh_persons", [])
        first_types = [p.get("person_type") for p in persons]
        await message.answer(
            "👤 لطفاً نوع شخص را دوباره انتخاب کنید:",
            reply_markup=create_person_type_kb(exclude=first_types if persons else [])
        )
        await state.set_state(Form.lavayeh_person_type)
        return
    nat_id = _to_en(message.text)
    if not re.match(r"^[0-9]{10}$", nat_id):
        await message.answer("⚠️ کد ملی باید *۱۰ رقمی* باشد:")
        return
    data = await state.get_data()
    current_person = data.get("_current_person", {})
    current_person["national_id"] = nat_id
    persons = data.get("lavayeh_persons", [])
    persons.append(current_person)
    await state.update_data(lavayeh_persons=persons, _current_person={})
    person_type = current_person.get("person_type", "")
    await message.answer(
        f"✅ کد ملی `{nat_id}` ({person_type}) ثبت شد.\n\n➕ آیا شخص دیگری نیز ارائه‌دهنده لایحه می‌باشد؟",
        reply_markup=add_or_finish_kb)
    await state.set_state(Form.lavayeh_more_persons)


@lavayeh_router.message(Form.lavayeh_more_persons)
async def lavayeh_more_persons(message: Message, state: FSMContext):
    text = message.text or ""
    data = await state.get_data()
    persons = data.get("lavayeh_persons", [])

    if text == "➕ افزودن کدملی دیگر":
        used_types = [p.get("person_type") for p in persons]
        await message.answer(
            "👤 لطفاً نوع شخص جدید را انتخاب کنید:",
            reply_markup=create_person_type_kb(exclude=used_types)
        )
        await state.set_state(Form.lavayeh_person_type)
        return

    if text == "✅ اتمام و ادامه":
        if await _maybe_return_to_preview(data, message, state):
            return
        await message.answer(
            "📄 *شرح متن لایحه:*\n\nلطفاً متن کامل لایحه خود را ارسال فرمایید.\n\n"
            "⚠️ *توجه مهم:* متن پس از ارسال *قابل ویرایش نمی‌باشد*.",
            reply_markup=ReplyKeyboardRemove())
        await state.set_state(Form.lavayeh_text)
        return

    if text == "🔙 بازگشت":
        # حذف آخرین شخص و بازگشت به مرحله قبل
        if persons:
            persons.pop()
            await state.update_data(lavayeh_persons=persons)
        
        if not persons:
            # اگر دیگر شخصی نمانده، به انتخاب نوع شخص برگرد
            await message.answer(
                "👤 لطفاً مشخص فرمایید ارائه‌دهنده لایحه *جزو کدام دسته* می‌باشد:",
                reply_markup=create_person_type_kb())
            await state.set_state(Form.lavayeh_person_type)
        else:
            # نمایش مجدد صفحه افزودن یا ادامه
            await message.answer(
                "➕ آیا شخص دیگری نیز ارائه‌دهنده لایحه می‌باشد؟",
                reply_markup=add_or_finish_kb
            )
        return

    await message.answer("⚠️ لطفاً یکی از گزینه‌های زیر را انتخاب کنید:", reply_markup=add_or_finish_kb)


# ══════════════════════════════════════════════════════════════════════════════
# مراحل اعلام وکالت — کدملی وکیل (در فلوی ثبت لایحه)
# ══════════════════════════════════════════════════════════════════════════════
@lavayeh_router.message(Form.ealam_vakalaht_national_id)
async def ealam_in_lavayeh_get_national_id(message: Message, state: FSMContext):
    if not message.text:
        return
    data = await state.get_data()
    lawyers = data.get("ealam_lawyers", [])
    if message.text == "🔙 بازگشت":
        if lawyers:
            await message.answer("آیا وکیل دیگری نیز در این پرونده وکالت دارد؟", reply_markup=ealam_more_lawyers_kb)
            await state.set_state(Form.ealam_vakalaht_more_lawyers)
        else:
            tracking_method = data.get("tracking_method", "case_number")
            if tracking_method == "archive_number":
                # این مسیر از طریق انتخاب شعبه از لیست به اینجا رسیده،
                # نه از ردیف فرعی - پس باید به لیست شعب برگردیم
                from branches import UNITS_DATA, create_branches_keyboard, ROOT_NODES
                from keyboards import back_only_kb as _back_kb
                await message.answer(
                    "🏛 لطفاً شعبه را دوباره از لیست انتخاب کنید:",
                    reply_markup=ReplyKeyboardRemove()
                )
                await message.answer(
                    "📂 *قوه قضائیه - سطح اول*",
                    reply_markup=create_branches_keyboard(ROOT_NODES, page=0, parent_id=None))
                await state.set_state(Form.lavayeh_branch_name)
            else:
                await message.answer("🔢 لطفاً ردیف فرعی را دوباره وارد کنید:", reply_markup=back_only_kb)
                await state.set_state(Form.lavayeh_row_number)
        return
    nat_id = _to_en(message.text)
    if not re.match(r"^[0-9]{10}$", nat_id):
        await message.answer("⚠️ کد ملی باید *۱۰ رقمی* باشد:")
        return
    lawyers.append(nat_id)
    await state.update_data(ealam_lawyers=lawyers)
    await message.answer(
        f"✅ کد ملی وکیل `{nat_id}` ثبت شد.\n\nآیا *وکیل دیگری* نیز در این پرونده وکالت دارد؟",
        reply_markup=ealam_more_lawyers_kb)
    await state.set_state(Form.ealam_vakalaht_more_lawyers)


@lavayeh_router.message(Form.ealam_vakalaht_more_lawyers)
async def ealam_in_lavayeh_more_lawyers(message: Message, state: FSMContext):
    text = message.text or ""
    if text == "➕ بله، وکیل دیگری هم هست":
        await message.answer(
            "🔢 لطفاً *کد ملی وکیل بعدی* را وارد فرمایید:\n_(۱۰ رقمی)_",
            reply_markup=back_only_kb)
        await state.set_state(Form.ealam_vakalaht_national_id)
        return
    if text == "✅ خیر، ادامه مراحل":
        await message.answer(
            "🔢 لطفاً *شماره قرارداد وکالت* را وارد فرمایید:\n_(دقیقاً ۱۶ رقمی)_",
            reply_markup=back_only_kb)
        await state.set_state(Form.ealam_vakalaht_contract_number)
        return
    if text == "🔙 بازگشت":
        data = await state.get_data()
        lawyers = data.get("ealam_lawyers", [])
        if lawyers:
            # حذف آخرین وکیل و بازگشت به صفحه قبل
            lawyers.pop()
            await state.update_data(ealam_lawyers=lawyers)
        await message.answer(
            "🔢 لطفاً *کد ملی وکیل* را وارد فرمایید:\n_(۱۰ رقمی)_",
            reply_markup=back_only_kb)
        await state.set_state(Form.ealam_vakalaht_national_id)
        return
    await message.answer("⚠️ لطفاً یکی از گزینه‌های زیر را انتخاب کنید:", reply_markup=ealam_more_lawyers_kb)


@lavayeh_router.message(Form.ealam_vakalaht_contract_number)
async def ealam_in_lavayeh_get_contract(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == "🔙 بازگشت":
        await message.answer("آیا وکیل دیگری نیز در این پرونده وکالت دارد؟", reply_markup=ealam_more_lawyers_kb)
        await state.set_state(Form.ealam_vakalaht_more_lawyers)
        return
    contract = _to_en(message.text)
    if not contract.isdigit() or len(contract) != 16:
        await message.answer(
            f"⚠️ شماره قرارداد باید *دقیقاً ۱۶ رقمی* باشد.\n"
            f"شماره وارد شده *{len(contract)} رقمی* است. مجدداً وارد کنید:")
        return
    data = await state.get_data()
    contracts = data.get("ealam_contracts", [])
    contracts.append(contract)
    await state.update_data(ealam_contracts=contracts)
    await message.answer(
        f"✅ شماره قرارداد `{contract}` ثبت شد.\n\nآیا *شماره قرارداد دیگری* نیز وجود دارد؟",
        reply_markup=ealam_more_contracts_kb)
    await state.set_state(Form.ealam_vakalaht_more_contracts)


@lavayeh_router.message(Form.ealam_vakalaht_more_contracts)
async def ealam_in_lavayeh_more_contracts(message: Message, state: FSMContext):
    text = message.text or ""
    if text == "➕ افزودن شماره قرارداد دیگر":
        await message.answer(
            "🔢 لطفاً *شماره قرارداد بعدی* را وارد فرمایید:\n_(۱۶ رقمی)_",
            reply_markup=back_only_kb)
        await state.set_state(Form.ealam_vakalaht_contract_number)
        return
    if text == "🔙 بازگشت":
        data = await state.get_data()
        contracts = data.get("ealam_contracts", [])
        if contracts:
            # حذف آخرین قرارداد و بازگشت به صفحه قبل
            contracts.pop()
            await state.update_data(ealam_contracts=contracts)
        await message.answer(
            "🔢 لطفاً *شماره قرارداد وکالت* را وارد فرمایید:\n_(دقیقاً ۱۶ رقمی)_",
            reply_markup=back_only_kb)
        await state.set_state(Form.ealam_vakalaht_contract_number)
        return
    if text == "✅ ادامه مراحل":
        await message.answer(
            "💰 *مقدار تمبر ابطالی:*\n\n"
            "اگر مقدار تمبر را به ریال می‌دانید، عدد را وارد کنید.\n"
            "در غیر این صورت از گزینه‌های زیر استفاده کنید:",
            reply_markup=ealam_stamp_amount_kb)
        await state.set_state(Form.ealam_vakalaht_stamp_amount)
        return
    await message.answer("⚠️ لطفاً یکی از گزینه‌های زیر را انتخاب کنید:", reply_markup=ealam_more_contracts_kb)


@lavayeh_router.message(Form.ealam_vakalaht_stamp_amount)
async def ealam_in_lavayeh_stamp_amount(message: Message, state: FSMContext):
    text = (message.text or "").strip()

    if text == "🚫 نیاز به ابطال تمبر ندارد":
        await state.update_data(ealam_stamp_amount=0, ealam_stamp_type="بدون تمبر")
        await _ask_lavayeh_text_ealam(message, state)
        return

    if text == "❓ نمیدانم، نیاز به محاسبه دارم":
        await message.answer(
            "🔍 *محاسبه تمبر:*\n\n"
            "لطفاً گزینه‌های زیر را انتخاب کنید.\n"
            "اگر گزینه‌های زیر کمکی نکرد، «عدم نیاز به تمبر» را انتخاب کنید "
            "(بعداً در شعبه قابلیت پرداخت تمبر را خواهید داشت) :",
            reply_markup=ealam_claim_type_kb)
        await state.set_state(Form.ealam_vakalaht_claim_type)
        return

    if text == "🔙 بازگشت":
        await message.answer("آیا شماره قرارداد دیگری وجود دارد؟", reply_markup=ealam_more_contracts_kb)
        await state.set_state(Form.ealam_vakalaht_more_contracts)
        return

    amount_str = _to_en(text)
    if not amount_str.isdigit() or int(amount_str) <= 0:
        await message.answer(
            "⚠️ لطفاً مقدار تمبر را به *ریال* وارد کنید یا از گزینه‌های زیر استفاده کنید:",
            reply_markup=ealam_stamp_amount_kb)
        return

    stamp_amount = int(amount_str)
    await state.update_data(ealam_stamp_amount=stamp_amount, ealam_stamp_type="مشخص")
    await message.answer(f"✅ مقدار تمبر *{_fmt(stamp_amount)} ریال* ثبت شد.")
    await _ask_lavayeh_text_ealam(message, state)


@lavayeh_router.message(Form.ealam_vakalaht_claim_type)
async def ealam_in_lavayeh_claim_type(message: Message, state: FSMContext):
    text = message.text or ""

    if "3️⃣" in text or "عدم نیاز" in text:
        await state.update_data(ealam_stamp_amount=0, ealam_stamp_type="بدون تمبر")
        await _ask_lavayeh_text_ealam(message, state)
        return

    if "2️⃣" in text or "غیر مالی" in text:
        stamp_amount = 200_000
        await state.update_data(ealam_stamp_amount=stamp_amount, ealam_stamp_type="غیر مالی")
        await message.answer(
            f"💰 مبلغ *{_fmt(stamp_amount)} ریال* تمبر ابطال می‌گردد.",
            reply_markup=continue_kb)
        await state.set_state(Form.ealam_vakalaht_text)
        return

    if "1️⃣" in text or "مالی" in text:
        await message.answer(
            "💵 لطفاً *مبلغ خواسته* را به *ریال* وارد فرمایید:\n_(فقط عدد)_",
            reply_markup=back_only_kb)
        await state.set_state(Form.ealam_vakalaht_claim_amount)
        return

    if text == "🔙 بازگشت":
        await message.answer(
            "💰 *مقدار تمبر ابطالی:*\n\n"
            "اگر مقدار تمبر را به ریال می‌دانید، عدد را وارد کنید.\n"
            "در غیر این صورت از گزینه‌های زیر استفاده کنید:",
            reply_markup=ealam_stamp_amount_kb)
        await state.set_state(Form.ealam_vakalaht_stamp_amount)
        return

    await message.answer("⚠️ لطفاً یکی از گزینه‌ها را انتخاب کنید:", reply_markup=ealam_claim_type_kb)


@lavayeh_router.message(Form.ealam_vakalaht_claim_amount)
async def ealam_in_lavayeh_claim_amount(message: Message, state: FSMContext):
    if not message.text:
        return
    
    if message.text == "🔙 بازگشت":
        await message.answer(
            "🔍 *محاسبه تمبر:*\n\n"
            "لطفاً گزینه‌های زیر را انتخاب کنید.\n"
            "اگر گزینه‌های زیر کمکی نکرد، «عدم نیاز به تمبر» را انتخاب کنید "
            "(بعداً در شعبه قابلیت پرداخت تمبر را خواهید داشت) :",
            reply_markup=ealam_claim_type_kb)
        await state.set_state(Form.ealam_vakalaht_claim_type)
        return
    
    amount_str = _to_en(message.text)
    if not amount_str.isdigit() or int(amount_str) <= 0:
        await message.answer("⚠️ لطفاً مبلغ خواسته را به *ریال* وارد کنید (فقط عدد):")
        return

    claim_amount = int(amount_str)
    try:
        result = calculate_stamp_duty(claim_amount)
    except ValueError as e:
        await message.answer(f"⚠️ خطا در محاسبه: {e}")
        return

    result_text = format_result_fa(claim_amount, result)
    await state.update_data(ealam_claim_amount=claim_amount, ealam_stamp_result=result)

    await message.answer(
        f"📊 *نتیجه محاسبه تمبر:*\n\n{result_text}\n\n"
        "لطفاً انتخاب کنید *کدام نوع تمبر* در پرونده قرار داده شود:",
        reply_markup=ealam_stamp_type_kb)
    await state.set_state(Form.ealam_vakalaht_stamp_type)


@lavayeh_router.message(Form.ealam_vakalaht_stamp_type)
async def ealam_in_lavayeh_stamp_type(message: Message, state: FSMContext):
    text = message.text or ""
    data = await state.get_data()
    result = data.get("ealam_stamp_result", {})

    if "بدوی" in text:
        stamp_amount = result.get("tamber_bedvi", 0)
        stamp_type = "بدوی"
    elif "تجدیدنظر" in text:
        stamp_amount = result.get("tamber_tajdidnazar", 0)
        stamp_type = "تجدیدنظر"
    elif "کلی" in text:
        stamp_amount = result.get("tamber_kolli", 0)
        stamp_type = "کلی"
    elif text == "🔙 بازگشت":
        await message.answer(
            "💵 لطفاً *مبلغ خواسته* را به *ریال* وارد فرمایید:\n_(فقط عدد)_",
            reply_markup=back_only_kb)
        await state.set_state(Form.ealam_vakalaht_claim_amount)
        return
    else:
        await message.answer("⚠️ لطفاً یکی از گزینه‌های موجود را انتخاب کنید:", reply_markup=ealam_stamp_type_kb)
        return

    await state.update_data(ealam_stamp_amount=stamp_amount, ealam_stamp_type=stamp_type)
    await message.answer(
        f"✅ *تمبر {stamp_type}* به مبلغ *{_fmt(stamp_amount)} ریال* انتخاب شد.")
    await _ask_lavayeh_text_ealam(message, state)


async def _ask_lavayeh_text_ealam(message: Message, state: FSMContext):
    await message.answer(
        "📄 *شرح متن لایحه اعلام وکالت:*\n\n"
        "لطفاً متن لایحه را ارسال فرمایید.\n"
        "⚠️ *توجه:* متن پس از ارسال قابل ویرایش نمی‌باشد.",
        reply_markup=ReplyKeyboardRemove())
    await state.set_state(Form.ealam_vakalaht_text)


@lavayeh_router.message(Form.ealam_vakalaht_text)
async def ealam_in_lavayeh_get_text(message: Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    chat_id = message.chat.id

    # ── پشتیبانی فایل ورد ──────────────────────────────────────
    if message.document and message.document.file_name and message.document.file_name.lower().endswith(".docx"):
        from text_collector import process_docx_input

        async def _on_ealam_docx_complete(final_text, final_html, st, b, cid, was_editing, char_count):
            await st.update_data(lavayeh_text=final_text, lavayeh_text_html=final_html, lavayeh_attachments=[])
            await b.send_message(cid, f"✅ متن لایحه اعلام وکالت از فایل ورد دریافت شد ({char_count} کاراکتر).")
            await _ask_attachment_title(message, st, is_first=True)

        await process_docx_input(
            message=message,
            user_id=user_id,
            chat_id=chat_id,
            state=state,
            bot=bot,
            on_complete=_on_ealam_docx_complete,
            text_state_key="lavayeh_text",
            html_state_key="lavayeh_text_html",
            extra_state_updates={"lavayeh_attachments": []},
            processing_msg="⏳ در حال پردازش فایل ورد...")
        return

    text = message.text or ""
    if text == "✅ ادامه مراحل":
        # کاربر دکمه «ادامه مراحل» را زده (از مرحله تمبر غیرمالی آمده)
        # باید ابتدا متن لایحه را بپرسیم
        await _ask_lavayeh_text_ealam(message, state)
        return
    if not text:
        await message.answer("⚠️ لطفاً متن را به صورت متن ارسال فرمایید \nیا فایل .docx ارسال نمایید.")
        return

    from text_collector import collect_text_part

    async def _on_ealam_text_complete(final_text, st, b, cid, was_editing):
        await st.update_data(lavayeh_text=final_text, lavayeh_text_html="", lavayeh_attachments=[])
        await b.send_message(
            cid,
            f"✅ متن لایحه اعلام وکالت دریافت شد ({len(final_text)} کاراکتر).")
        await _ask_attachment_title(message, st, is_first=True)

    await collect_text_part(
        user_id=user_id,
        chat_id=chat_id,
        text=text,
        state=state,
        bot=bot,
        on_complete=_on_ealam_text_complete,
        first_part_reply="⏳ در حال دریافت متن لایحه اعلام وکالت...")


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۵ — شرح متن لایحه (جریان عادی)
# ══════════════════════════════════════════════════════════════════════════════
@lavayeh_router.message(Form.lavayeh_text)
async def lavayeh_get_text(message: Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    chat_id = message.chat.id

    # ── پشتیبانی فایل ورد ──────────────────────────────────────
    if message.document and message.document.file_name and message.document.file_name.lower().endswith(".docx"):
        from text_collector import process_docx_input

        async def _on_docx_complete(final_text, final_html, st, b, cid, was_editing, char_count):
            await st.update_data(lavayeh_text=final_text, lavayeh_text_html=final_html, lavayeh_attachments=[])
            await b.send_message(cid, f"✅ متن لایحه از فایل ورد دریافت شد ({char_count} کاراکتر).")
            await _ask_attachment_title(message, st, is_first=True)

        await process_docx_input(
            message=message,
            user_id=user_id,
            chat_id=chat_id,
            state=state,
            bot=bot,
            on_complete=_on_docx_complete,
            text_state_key="lavayeh_text",
            html_state_key="lavayeh_text_html",
            extra_state_updates={"lavayeh_attachments": []},
            processing_msg="⏳ در حال پردازش فایل ورد...")
        return

    if not message.text:
        await message.answer("⚠️ لطفاً شرح متن لایحه را به صورت متن ارسال فرمایید \nیا فایل .docx ارسال نمایید.")
        return

    from text_collector import collect_text_part

    data = await state.get_data()
    is_editing = data.get("_is_editing")

    async def _on_text_complete(final_text, st, b, cid, was_editing):
        """بعد از جمع‌آوری کامل متن، ادامه جریان را انجام می‌دهد."""
        if was_editing:
            await st.update_data(lavayeh_text=final_text, lavayeh_text_html="")
            d = await st.get_data()
            if await _maybe_return_to_preview(d, message, st):
                return
        else:
            await st.update_data(lavayeh_text=final_text, lavayeh_text_html="", lavayeh_attachments=[])

        await b.send_message(
            cid,
            f"✅ متن لایحه دریافت شد ({len(final_text)} کاراکتر).")
        await _ask_attachment_title(message, st, is_first=True)

    await collect_text_part(
        user_id=user_id,
        chat_id=chat_id,
        text=message.text,
        state=state,
        bot=bot,
        on_complete=_on_text_complete,
        is_editing=bool(is_editing),
        first_part_reply="⏳ در حال دریافت متن لایحه..." if not is_editing else None)


async def _ask_attachment_title(message: Message, state: FSMContext, is_first: bool):
    await state.update_data(lavayeh_images=[])
    kb = lavayeh_attachment_title_kb_first if is_first else lavayeh_attachment_title_kb
    intro = "✅ متن لایحه ثبت شد.\n\n" if is_first else ""
    await message.answer(
        f"{intro}📄 *عنوان مدرک بعدی:*\n\n"
        "در صورتی که تصویری برای ضمیمه در لایحه دارید، ابتدا عنوان تصویر مدرک را تایپ کنید (مثلاً «کارت ملی»)،\n"
        "یا یکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=kb)
    await state.set_state(Form.lavayeh_attachment_title)


@lavayeh_router.message(Form.lavayeh_attachment_title)
async def lavayeh_get_attachment_title(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        await message.answer("⚠️ لطفاً عنوان را به صورت متن ارسال فرمایید.")
        return
    data = await state.get_data()
    attachments = data.get("lavayeh_attachments", [])

    if text == "⏭ رد کردن (بدون مدرک)" and not attachments:
        await state.update_data(lavayeh_attachments=[])
        data = await state.get_data()
        if await _maybe_return_to_preview(data, message, state):
            return
        await _go_to_preview(message, state)
        return

    if text == "🔙 بازگشت":
        # بازگشت به مرحله متن لایحه
        await message.answer(
            "📄 *شرح متن لایحه:*\n\nلطفاً متن کامل لایحه خود را ارسال فرمایید.\n\n💡 همچنین می‌توانید فایل .docx را ارسال کنید (با حفظ فرمت بولد و ...).",
            reply_markup=ReplyKeyboardRemove())
        await state.set_state(Form.lavayeh_text)
        return

    title = "مستندات" if text == "🔹 عنوان مهم نیست (صرفا درج شود مستندات)" else text
    await state.update_data(_current_attachment_title=title)
    await message.answer(
        f"✅ عنوان «*{title}*» ثبت شد.\n\n"
        "🖼 لطفاً تصاویر مربوط به این مدرک را به صورت *عکس (Photo)* ارسال فرمایید.\n"
        "⚠️ فقط فرمت *JPG / JPEG* قابل قبول است.\n\n"
        "پس از ارسال همه تصاویر، دکمه *«اتمام ارسال تصاویر»* را بفشارید.",
        reply_markup=ReplyKeyboardRemove())
    await state.set_state(Form.lavayeh_images)


@lavayeh_router.message(Form.lavayeh_images, F.photo)
async def lavayeh_receive_image(message: Message, state: FSMContext, bot: Bot):
    from text_collector import check_image_limit, MAX_IMAGES_PER_TITLE

    data = await state.get_data()
    images = data.get("lavayeh_images", [])

    # بررسی محدودیت تعداد تصویر
    if not check_image_limit(len(images)):
        await message.reply(
            f"⛔ حداکثر *{MAX_IMAGES_PER_TITLE} تصویر* در هر عنوان مجاز است.\n\n"
            f"اگر مدرک بیشتری دارید، ابتدا دکمه «اتمام ارسال تصاویر» را بزنید\n"
            f"و سپس عنوان جدیدی انتخاب کنید و تصاویر باقیمانده را ارسال نمایید.")
        return

    file_id = message.photo[-1].file_id
    images.append(file_id)
    await state.update_data(lavayeh_images=images)

    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    manage_kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ اتمام ارسال تصاویر")],
            [KeyboardButton(text="🗑 حذف تصویر")]
        ],
        resize_keyboard=True
    )
    remaining = MAX_IMAGES_PER_TITLE - len(images)
    await message.reply(
        f"✅ تصویر شماره *{len(images)}* دریافت شد.\n"
        f"مجموع تصاویر این مدرک: *{len(images)}* از {MAX_IMAGES_PER_TITLE}\n\n"
        f"می‌توانید تصاویر بیشتری ارسال کنید ({remaining} جای باقیمانده)\n"
        f"یا دکمه «اتمام ارسال تصاویر» را بزنید.",
        reply_markup=manage_kb)


@lavayeh_router.message(Form.lavayeh_images, F.document)
async def lavayeh_reject_document(message: Message, state: FSMContext):
    await message.answer(
        "⚠️ لطفاً تصاویر را به صورت *عکس (Photo)* ارسال کنید، نه فایل.")


@lavayeh_router.message(Form.lavayeh_images, F.text == "🗑 حذف تصویر")
async def lavayeh_ask_delete_image(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    images = data.get("lavayeh_images", [])
    if not images:
        await message.answer("⚠️ لیست تصاویر خالی است.")
        return
    await message.answer("🗑 *حذف تصویر:*\n\nعکس‌های ارسالی:")
    for i, file_id in enumerate(images):
        await bot.send_photo(message.chat.id, photo=file_id, caption=f"تصویر شماره {i + 1}")
    await message.answer(
        "لطفاً *شماره تصویر* برای حذف را ارسال فرمایید:",
        reply_markup=ReplyKeyboardRemove())
    await state.update_data(_deleting_image=True)


@lavayeh_router.message(Form.lavayeh_images)
async def lavayeh_images_text(message: Message, state: FSMContext):
    text = message.text or ""
    data = await state.get_data()
    images = data.get("lavayeh_images", [])
    deleting = data.get("_deleting_image", False)

    if deleting:
        num_str = _to_en(text)
        if num_str.isdigit():
            idx = int(num_str) - 1
            if 0 <= idx < len(images):
                images.pop(idx)
                await state.update_data(lavayeh_images=images, _deleting_image=False)
                from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
                if images:
                    manage_kb = ReplyKeyboardMarkup(
                        keyboard=[
                            [KeyboardButton(text="✅ اتمام ارسال تصاویر")],
                            [KeyboardButton(text="🗑 حذف تصویر")]
                        ],
                        resize_keyboard=True
                    )
                else:
                    manage_kb = ReplyKeyboardRemove()
                await message.answer(
                    f"✅ تصویر شماره *{idx+1}* حذف شد.\n"
                    f"مجموع باقیمانده: *{len(images)} تصویر*",
                    reply_markup=manage_kb)
                return
            else:
                await message.answer(f"⚠️ شماره نامعتبر. لطفاً عددی بین ۱ تا {len(images)} وارد کنید:")
                return
        else:
            await state.update_data(_deleting_image=False)

    if text == "✅ اتمام ارسال تصاویر":
        if not images:
            await message.answer("⚠️ حداقل یک تصویر برای این مدرک ارسال کنید.")
            return
        attachments = data.get("lavayeh_attachments", [])
        title = data.get("_current_attachment_title", "مستندات")
        attachments.append({"title": title, "images": images})
        await state.update_data(lavayeh_attachments=attachments, lavayeh_images=[])
        await message.answer(
            f"✅ مدرک «*{title}*» با *{len(images)} تصویر* ثبت شد.\n\nآیا مدرک دیگری دارید؟",
            reply_markup=lavayeh_attachment_more_kb)
        await state.set_state(Form.lavayeh_attachment_more)
        return

    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    if images:
        kb = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="✅ اتمام ارسال تصاویر")],
                [KeyboardButton(text="🗑 حذف تصویر")]
            ],
            resize_keyboard=True
        )
    else:
        kb = None
    await message.answer("⚠️ لطفاً تصویر این مدرک را ارسال کنید:", reply_markup=kb)


@lavayeh_router.message(Form.lavayeh_attachment_more)
async def lavayeh_attachment_more(message: Message, state: FSMContext):
    text = message.text or ""
    if text == "➕ بله، عنوان و مدرک دیگر دارم":
        await _ask_attachment_title(message, state, is_first=False)
        return
    if text == "✅ خیر، ادامه بده":
        data = await state.get_data()
        if await _maybe_return_to_preview(data, message, state):
            return
        await _go_to_preview(message, state)
        return
    if text == "🔙 بازگشت":
        # حذف آخرین مدرک و بازگشت به مرحله قبل
        data = await state.get_data()
        attachments = data.get("lavayeh_attachments", [])
        if attachments:
            attachments.pop()
            await state.update_data(lavayeh_attachments=attachments)
        await _ask_attachment_title(message, state, is_first=len(attachments) == 0)
        return
    await message.answer("لطفاً یکی از گزینه‌های زیر را انتخاب کنید:", reply_markup=lavayeh_attachment_more_kb)


async def _go_to_preview(message: Message, state: FSMContext):
    data = await state.get_data()
    preview_text = build_preview(data)
    await message.answer(preview_text, reply_markup=lavayeh_confirm_kb)
    await state.set_state(Form.lavayeh_confirm)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۷ — تایید یا ویرایش
# ══════════════════════════════════════════════════════════════════════════════
@lavayeh_router.message(Form.lavayeh_confirm)
async def lavayeh_confirm_handler(message: Message, state: FSMContext, bot: Bot):
    text = message.text or ""

    if text == "✅ تایید و شروع ثبت":
        data = await state.get_data()
        user_id = message.from_user.id
        title = data.get("lavayeh_title", "")

        # بررسی معافیت از پرداخت خدمات
        if await is_exempt_user(user_id):
            if not hasattr(runtime_state, "active_lavayeh_users"):
                runtime_state.active_lavayeh_users = set()
            runtime_state.active_lavayeh_users.add(user_id)

            await message.answer(
                "✅ *معافیت از پرداخت خدمات*\n\n"
                "شما در لیست کاربران معاف هستید."
                "\nدرخواست لایحه در حال ارسال به صف پردازش...",
                reply_markup=ReplyKeyboardRemove())
            # ارسال مستقیم به صف بدون پرداخت
            await _send_lavayeh_task_to_queue(data, user_id, title)
            await state.clear()
            return

        # ═══ ارسال فاکتور بله با استفاده از sendInvoice API ═══
        fee = LAVAYEH_SERVICE_FEE
        fee_rial = fee * 10  # تومان به ریال
        try:
            invoice_payload = _json.dumps({"type": "lavayeh_prepay", "uid": user_id})
            async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
                invoice_url = f"{BALE_API_BASE}/bot{BOT_TOKEN}/sendInvoice"
                invoice_data = {
                    "chat_id": user_id,
                    "title": f"فاکتور خدمات ثبت لایحه",
                    "description": f"هزینه خدمات ثبت لایحه\nمبلغ: {fee:,} تومان ({fee_rial:,} ریال)",
                    "payload": invoice_payload,
                    "provider_token": BALE_WALLET_TOKEN,
                    "currency": "IRR",
                    "prices": [{"label": "خدمات ثبت لایحه", "amount": fee_rial}],
                }
                logging.info(f"[LAVAYEH-PREPAY] ارسال sendInvoice به chat_id={user_id}, مبلغ={fee_rial:,} ریال")
                async with session.post(invoice_url, json=invoice_data) as resp:
                    result = await resp.json()
                    logging.info(f"[LAVAYEH-PREPAY] پاسخ sendInvoice: {result}")
                    if not result.get("ok"):
                        logging.error(f"[LAVAYEH-PREPAY] خطای sendInvoice: {result}")
                        raise Exception(result.get("description", "خطا در ارسال فاکتور"))
        except Exception as e:
            logging.error(f"[LAVAYEH-PREPAY] خطا در ارسال فاکتور: {e}", exc_info=True)
            await message.answer("⚠️ خطا در ساخت فاکتور. لطفاً کمی بعد دوباره تلاش کنید.", reply_markup=lavayeh_confirm_kb)
            return

        pay_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ پرداخت انجام شد", callback_data="lavayeh_prepay_done")],
            [InlineKeyboardButton(text="❌ انصراف", callback_data="lavayeh_prepay_cancel")],
        ])
        await message.answer(
            f"⏳ فاکتور پرداخت ارسال شد.\n\n"
            f"💰 هزینه خدمات ثبت لایحه: *{fee:,} تومان*\n\n"
            f"پس از پرداخت موفق در کیف پول بله، ثبت لایحه به‌صورت خودکار انجام می‌شود.",
            reply_markup=pay_kb
        )
        await state.set_state(Form.waiting_for_lavayeh_prepay)
        return

    if text == "✏️ ویرایش اطلاعات":
        await message.answer(
            "✏️ *ویرایش اطلاعات:*\n\nکدام بخش را می‌خواهید ویرایش کنید؟",
            reply_markup=lavayeh_edit_kb)
        await state.set_state(Form.lavayeh_edit_choice)
        return

    await message.answer("⚠️ لطفاً یکی از گزینه‌های زیر را انتخاب کنید:", reply_markup=lavayeh_confirm_kb)


# ══════════════════════════════════════════════════════════════════════════════
# تابع کمکی: ارسال تسک لایحه به صف پردازش
# ══════════════════════════════════════════════════════════════════════════════
async def _send_lavayeh_task_to_queue(data: dict, user_id: int, title: str):
    """ارسال تسک لایحه به صف پردازش بر اساس داده‌های ذخیره‌شده."""
    if title == "اعلام وکالت":
        await runtime_state.job_queue.put({
            "user_id": user_id,
            "query_type": "اعلام_وکالت",
            "task_type": "EALAM_VAKALAHT_SUBMIT",
            "prepaid": True,
            "ealam_lawyers": data.get("ealam_lawyers", []),
            "ealam_contracts": data.get("ealam_contracts", []),
            "ealam_stamp_amount": data.get("ealam_stamp_amount", 0),
            "ealam_stamp_type": data.get("ealam_stamp_type", ""),
            "ealam_lavayeh_text": data.get("lavayeh_text", ""),
            "ealam_lavayeh_text_html": data.get("lavayeh_text_html", ""),
            "ealam_attachments": data.get("lavayeh_attachments", []),
            "lavayeh_tracking_code": data.get("lavayeh_tracking_code", ""),
            "lavayeh_province": data.get("lavayeh_province", ""),
            "lavayeh_row_number": data.get("lavayeh_row_number", 1),
            "tracking_method": data.get("tracking_method", "case_number"),
            "lavayeh_archive_number": data.get("lavayeh_archive_number", ""),
            "lavayeh_branch_name": data.get("lavayeh_branch_name", ""),
            "lavayeh_branch_code": data.get("lavayeh_branch_code", ""),
        })
    else:
        await runtime_state.job_queue.put({
            "user_id": user_id,
            "query_type": "لایحه_ثبت",
            "task_type": "LAVAYEH_SUBMIT",
            "prepaid": True,
            "lavayeh_title": data.get("lavayeh_title"),
            "lavayeh_system_title": data.get("lavayeh_system_title"),
            "lavayeh_tracking_code": data.get("lavayeh_tracking_code"),
            "lavayeh_province": data.get("lavayeh_province"),
            "lavayeh_row_number": data.get("lavayeh_row_number"),
            "lavayeh_persons": data.get("lavayeh_persons", []),
            "lavayeh_text": data.get("lavayeh_text"),
            "lavayeh_text_html": data.get("lavayeh_text_html", ""),
            "lavayeh_attachments": data.get("lavayeh_attachments", []),
            "tracking_method": data.get("tracking_method", "case_number"),
            "lavayeh_archive_number": data.get("lavayeh_archive_number", ""),
            "lavayeh_branch_name": data.get("lavayeh_branch_name", ""),
            "lavayeh_branch_code": data.get("lavayeh_branch_code", ""),
        })


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۷-ج — پرداخت خدمات قبل از ثبت لایحه (BLE wallet)
# ══════════════════════════════════════════════════════════════════════════════

# هندلر pre_checkout_query برای پرداخت پیش‌ثبت لایحه — تایید خودکار
@lavayeh_router.pre_checkout_query()
async def lavayeh_prepay_pre_checkout(pre_checkout_query: PreCheckoutQuery, bot: Bot):
    """تایید خودکار درخواست پیش‌پرداخت خدمات لایحه"""
    try:
        await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)
        logging.info(f"[LAVAYEH-PREPAY] pre_checkout تایید شد برای کاربر {pre_checkout_query.from_user.id}")
    except Exception as e:
        logging.error(f"[LAVAYEH-PREPAY] خطا در answer_pre_checkout_query: {e}")


# هندلر successful_payment برای پرداخت پیش‌ثبت لایحه — تشخیص خودکار
@lavayeh_router.message(Form.waiting_for_lavayeh_prepay, F.successful_payment)
async def lavayeh_prepay_successful_payment(message: Message, state: FSMContext, bot: Bot):
    """پرداخت موفق خدمات لایحه — تشخیص خودکار توسط بله"""
    user_id = message.from_user.id
    data = await state.get_data()
    title = data.get("lavayeh_title", "لایحه")
    payment = message.successful_payment
    fee = LAVAYEH_SERVICE_FEE

    logging.info(f"[LAVAYEH-PREPAY] پرداخت خودکار تشخیص داده شد برای کاربر {user_id}")

    await message.answer(
        f"✅ *پرداخت تایید شد!*",
        parse_mode="Markdown"
    )
    await message.answer(
        f"💰 مبلغ: *{fee:,} تومان*\n\n"
        f"📝 نوع: *ثبت {title}*\n\n"
        f"⏳ درخواست شما در حال ارسال به سامانه قضایی است...",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )

    await log_event(
        "پرداخت", title, message.from_user.full_name, user_id,
        doc_name=f"خدمات ثبت {title}", payment_status="پرداخت شده (کیف پول بله - پیش‌ثبت)",
        note=f"مبلغ: {fee:,} تومان | Bale payment_id: {payment.telegram_payment_charge_id}"
    )

    # اطلاع‌رسانی به ادمین
    try:
        admin_msg = (
            f"💰 پرداخت خدمات ثبت لایحه (تشخیص خودکار):\n\n"
            f"👤 کاربر: {message.from_user.full_name} ({user_id})\n"
            f"📄 عنوان: {title}\n"
            f"💰 مبلغ: {fee:,} تومان\n"
            f"⏱ زمان: {datetime.datetime.now().strftime('%Y/%m/%d %H:%M')}\n"
            f"🎫 payment_id: {payment.telegram_payment_charge_id}"
        )
        await bot.send_message(ADMIN_ID, admin_msg)
    except Exception as e:
        logging.error(f"[LAVAYEH-PREPAY] خطا در ارسال اطلاع به ادمین: {e}", exc_info=True)

    # ارسال به صف پردازش
    if not hasattr(runtime_state, "active_lavayeh_users"):
        runtime_state.active_lavayeh_users = set()
    runtime_state.active_lavayeh_users.add(user_id)
    await _send_lavayeh_task_to_queue(data, user_id, title)
    await state.clear()


# هندلر دکمه «پرداخت انجام شد» — فال‌بک
@lavayeh_router.callback_query(F.data == "lavayeh_prepay_done", Form.waiting_for_lavayeh_prepay)
async def lavayeh_prepay_done_callback(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """کاربر دکمه تایید پرداخت را زده — تایید مجدد"""
    await callback.answer()
    user_id = callback.from_user.id

    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ بله، پرداخت موفق بود", callback_data="lavayeh_prepay_done_confirm")],
        [InlineKeyboardButton(text="❌ خیر، انصراف", callback_data="lavayeh_prepay_cancel")],
    ])
    await callback.message.answer(
        "❓ آیا مطمئن هستید که پرداخت با موفقیت انجام شد؟\n\n"
        "اگر پیام «پرداخت با موفقیت انجام شد» را در کیف پول بله دیده‌اید، «بله» را بزنید.",
        reply_markup=confirm_kb
    )


@lavayeh_router.callback_query(F.data == "lavayeh_prepay_done_confirm", Form.waiting_for_lavayeh_prepay)
async def lavayeh_prepay_done_confirm_callback(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """تایید نهایی — ارسال به صف پردازش"""
    await callback.answer()
    user_id = callback.from_user.id
    data = await state.get_data()
    title = data.get("lavayeh_title", "لایحه")
    fee = LAVAYEH_SERVICE_FEE

    logging.info(f"[LAVAYEH-PREPAY] تایید نهایی پرداخت برای کاربر {user_id}")

    await callback.message.answer(
        f"✅ *پرداخت تایید شد!*\n\n"
        f"💰 مبلغ: {fee:,} تومان\n\n"
        f"⏳ درخواست شما در حال ارسال به سامانه قضایی است...",
        reply_markup=ReplyKeyboardRemove()
    )

    await log_event(
        "پرداخت", title, callback.from_user.full_name, user_id,
        doc_name=f"خدمات ثبت {title}", payment_status="پرداخت شده (تایید دستی کاربر - پیش‌ثبت)",
        note=f"مبلغ: {fee:,} تومان"
    )

    try:
        admin_msg = (
            f"💰 پرداخت خدمات ثبت لایحه (تایید دستی):\n\n"
            f"👤 کاربر: {callback.from_user.full_name} ({user_id})\n"
            f"📄 عنوان: {title}\n"
            f"💰 مبلغ: {fee:,} تومان\n"
            f"⏱ زمان: {datetime.datetime.now().strftime('%Y/%m/%d %H:%M')}"
        )
        await bot.send_message(ADMIN_ID, admin_msg)
    except Exception as e:
        logging.error(f"[LAVAYEH-PREPAY] خطا در ارسال اطلاع به ادمین: {e}")

    if not hasattr(runtime_state, "active_lavayeh_users"):
        runtime_state.active_lavayeh_users = set()
    runtime_state.active_lavayeh_users.add(user_id)
    await _send_lavayeh_task_to_queue(data, user_id, title)
    await state.clear()


@lavayeh_router.callback_query(F.data == "lavayeh_prepay_cancel", Form.waiting_for_lavayeh_prepay)
async def lavayeh_prepay_cancel_callback(callback: CallbackQuery, state: FSMContext):
    """انصراف از پرداخت خدمات"""
    await callback.answer()
    await callback.message.answer(
        "لغو گردید. لطفاً مجدداً شروع کنید:",
        reply_markup=flow_type_kb
    )
    await state.clear()
    await state.set_state(Form.waiting_for_flow_type)


@lavayeh_router.message(Form.waiting_for_lavayeh_prepay)
async def lavayeh_prepay_waiting_message(message: Message):
    """در حال انتظار پرداخت — پرداخت از طریق فاکتور بله انجام می‌شود"""
    if message.text and "انصراف" in message.text:
        pass
    else:
        await message.answer("⏳ لطفاً فاکتور ارسال شده را در چت پرداخت کنید. نیازی به ارسال عکس رسید نیست.")


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۷-ب — منوی ویرایش
# ══════════════════════════════════════════════════════════════════════════════
@lavayeh_router.message(Form.lavayeh_edit_choice)
async def lavayeh_edit_choice_handler(message: Message, state: FSMContext):
    text = message.text or ""

    if text == "🔙 بازگشت به پیش‌نمایش":
        data = await state.get_data()
        await message.answer(build_preview(data), reply_markup=lavayeh_confirm_kb)
        await state.set_state(Form.lavayeh_confirm)
        return

    if text == "📝 ویرایش عنوان لایحه":
        await state.update_data(_is_editing=True)
        await message.answer("📝 لطفاً عنوان جدید را انتخاب کنید:", reply_markup=lavayeh_title_kb)
        await state.set_state(Form.lavayeh_title)
        return

    if text == "🔢 ویرایش شماره پرونده":
        await state.update_data(_is_editing=True)
        await message.answer("🔢 لطفاً شماره پرونده جدید را ارسال فرمایید:", reply_markup=ReplyKeyboardRemove())
        await state.set_state(Form.lavayeh_tracking_code)
        return

    if text == "🏙 ویرایش استان":
        await state.update_data(_is_editing=True)
        await message.answer("🏙 لطفاً استان جدید را انتخاب کنید:", reply_markup=create_province_kb())
        await state.set_state(Form.lavayeh_province)
        return

    if text == "🔢 ویرایش ردیف فرعی":
        await state.update_data(_is_editing=True)
        await message.answer("🔢 لطفاً ردیف فرعی جدید را وارد کنید (۱ تا ۳۰):", reply_markup=ReplyKeyboardRemove())
        await state.set_state(Form.lavayeh_row_number)
        return

    if text == "👤 ویرایش اشخاص ارائه‌دهنده":
        data = await state.get_data()
        if data.get("lavayeh_title") == "اعلام وکالت":
            await state.update_data(ealam_lawyers=[], _is_editing=True)
            await message.answer(
                "👤 لیست وکلا پاک شد.\nلطفاً *کد ملی وکیل اول* را وارد فرمایید:\n_(۱۰ رقمی)_",
                reply_markup=ReplyKeyboardRemove())
            await state.set_state(Form.ealam_vakalaht_national_id)
            return
        await state.update_data(lavayeh_persons=[], _current_person={}, _is_editing=True)
        await message.answer(
            "👤 لیست اشخاص پاک شد.\nلطفاً مشخص فرمایید اولین ارائه‌دهنده جزو کدام دسته می‌باشد:",
            reply_markup=create_person_type_kb()
        )
        await state.set_state(Form.lavayeh_person_type)
        return

    if text == "📄 ویرایش شرح متن لایحه":
        await state.update_data(_is_editing=True)
        await message.answer("📄 لطفاً متن جدید لایحه را ارسال فرمایید:", reply_markup=ReplyKeyboardRemove())
        await state.set_state(Form.lavayeh_text)
        return

    if text == "🖼 ویرایش تصاویر مدارک":
        await state.update_data(lavayeh_attachments=[], _is_editing=True)
        await message.answer("🖼 مدارک قبلی پاک شدند.")
        await _ask_attachment_title(message, state, is_first=True)
        return

    await message.answer("⚠️ لطفاً یکی از گزینه‌های موجود را انتخاب کنید:", reply_markup=lavayeh_edit_kb)


# ══════════════════════════════════════════════════════════════════════════════
# تابع کمکی: انتقال مستقیم به فلوی امضای الکترونیک (پس از پرداخت از قبل)
# ══════════════════════════════════════════════════════════════════════════════
async def _go_to_sign_flow_after_prepaid(
    bot: Bot,
    user_id: int,
    is_ezhharnameh: bool,
    lavayeh_title: str,
    lavayeh_province: str,
    lavayeh_row_number: int,
    lavayeh_persons: list,
    tracking_code: str,
    national_ids: str,
    court_total: int,
):
    """انتقال مستقیم به فلوی امضای الکترونیک بدون نیاز به پرداخت.

    پس از اینکه کاربر قبلاً هزینه خدمات را پرداخت کرده و سند با موفقیت
    در سامانه ثبت شده، این تابع فلوی امضا را آغاز می‌کند.
    """
    user_state = runtime_state.dp.fsm.resolve_context(bot, user_id, user_id)

    if is_ezhharnameh:
        sign_persons = []
        for i, p in enumerate(lavayeh_persons):
            sign_persons.append({
                "idx": i,
                "name": p.get("name", p.get("national_id", f"شخص {i+1}")),
                "person_type": p.get("person_type", ""),
                "national_id": p.get("national_id", ""),
            })
        runtime_state.pending_ezhhar_sign[user_id] = {
            "tracking_code": tracking_code,
            "is_ezhharnameh": True,
            "sign_persons": sign_persons,
            "persons_awaiting_sign": list(range(len(sign_persons))),
            "current_person_idx": 0,
            "sign_codes_received": {},
            "sign_sent_time": None,
            "wrong_code_time": None,
            "code_sent_announce_time": None,
            "resend_notified": False,
            "total_no_action_start": datetime.datetime.now(),
        }
        from keyboards import ezhhar_sign_ready_kb
        await bot.send_message(
            user_id,
            "🖊 *مرحله اخذ امضای الکترونیک اظهارنامه:*\n\n"
            "آیا برای ارسال کد امضا آماده هستید؟",
            reply_markup=ezhhar_sign_ready_kb)
        await user_state.set_state(Form.ezhhar_sign_ready)
    else:
        runtime_state.pending_lavayeh_sign[user_id] = {
            "tracking_code": tracking_code,
            "lavayeh_title": lavayeh_title,
            "province": lavayeh_province,
            "row_number": lavayeh_row_number,
            "persons": lavayeh_persons,
            "sign_persons": [],
            "persons_awaiting_sign": [],
            "current_person_idx": None,
            "sign_sent_time": None,
            "sign_codes_received": {},
            "wrong_code_time": None,
            "code_sent_announce_time": None,
            "resend_notified": False,
            "total_no_action_start": None,
        }
        await bot.send_message(
            user_id,
            "🖊 *مرحله اخذ امضای الکترونیک:*\n\n"
            "آیا برای ارسال کد امضا آماده هستید؟",
            reply_markup=lavayeh_sign_ready_kb)
        await user_state.set_state(Form.lavayeh_sign_ready)


# ══════════════════════════════════════════════════════════════════════════════
# ارسال نتیجه ثبت لایحه به کاربر + شروع فلوی امضا
# ══════════════════════════════════════════════════════════════════════════════
async def send_lavayeh_result(
    bot: Bot,
    user_id: int,
    pdf_path: str,
    court_total: int,
    tracking_code: str = "",
    national_ids: str = "",
    lavayeh_title: str = "لایحه دفاعیه",
    lavayeh_province: str = "",
    lavayeh_row_number: int = 1,
    lavayeh_persons: list = None,
    skip_fee_calc: bool = False,
    is_ezhharnameh: bool = False,
    prepaid: bool = False):
    if lavayeh_persons is None:
        lavayeh_persons = []

    if not hasattr(runtime_state, "active_lavayeh_users"):
        runtime_state.active_lavayeh_users = set()

    if os.path.exists(pdf_path):
        doc_caption = (
            "📄 *نسخه ثبت‌شده اظهارنامه شما در سامانه قضایی*"
            if is_ezhharnameh else
            "📄 *نسخه ثبت‌شده لایحه شما در سامانه قضایی*"
        )
        await send_document_direct(user_id, pdf_path, caption=doc_caption)
        os.remove(pdf_path)

    if skip_fee_calc:
        # مبلغ نهایی از قبل محاسبه شده (مثلاً در اعلام وکالت)
        final_fee = court_total
        fee_text = f"💳 *مبلغ نهایی قابل پرداخت: {final_fee:,} ریال*"
    else:
        fee_text = format_lavayeh_fee_explanation(court_total)
        final_fee = calculate_lavayeh_fee(court_total)

    await bot.send_message(user_id, fee_text)

    service_label = "اظهارنامه" if is_ezhharnameh else "لایحه"
    doc_type = "اظهارنامه" if is_ezhharnameh else "لایحه"

    # بررسی معافیت از پرداخت
    if await is_exempt_user(user_id):
        await log_event(
            "ثبت", doc_type, str(user_id), user_id,
            tracking_code=tracking_code, national_id=national_ids,
            doc_name=doc_type, payment_status="معاف از پرداخت",
            note=f"مبلغ فاکتور: {final_fee:,} ریال (معاف)"
        )
        # ادامه فرآیند بدون نیاز به فیش پرداخت
        runtime_state.pending_lavayeh_payments[user_id] = {
            "invoice_time": datetime.datetime.now(),
            "final_fee": 0,
            "court_total": court_total,
            "tracking_code": tracking_code,
            "national_ids": national_ids,
            "reminder_sent": False,
            "blocked": False,
            "lavayeh_title": lavayeh_title,
            "lavayeh_province": lavayeh_province,
            "lavayeh_row_number": lavayeh_row_number,
            "lavayeh_persons": lavayeh_persons,
            "is_ezhharnameh": is_ezhharnameh,
        }
        await bot.send_message(
            user_id,
            f"✅ *معافیت از پرداخت*\n\n"
            f"شما در لیست کاربران معاف هستید."
            f"\nثبت {service_label} بدون نیاز به پرداخت انجام شد.")
        # رفتن مستقیم به فلوی امضا
        await _go_to_sign_flow_after_prepaid(
            bot, user_id, is_ezhharnameh, lavayeh_title,
            lavayeh_province, lavayeh_row_number, lavayeh_persons,
            tracking_code, national_ids, court_total
        )
        return

    # ═══ اگر قبلاً پرداخت خدمات انجام شده — مستقیم به امضا ═══
    if prepaid:
        logging.info(f"[LAVAYEH] prepaid=True — رد شدن فاکتور و رفتن مستقیم به امضا (user={user_id})")
        await bot.send_message(
            user_id,
            f"✅ *{service_label} با موفقیت در سامانه قضایی ثبت شد.*\n\n"
            f"💳 هزینه سامانه: *{court_total:,} ریال*\n\n"
            f"✅ پرداخت خدمات شما قبلاً تایید شده است.",
            reply_markup=ReplyKeyboardRemove()
        )
        # رفتن مستقیم به فلوی امضا
        await _go_to_sign_flow_after_prepaid(
            bot, user_id, is_ezhharnameh, lavayeh_title,
            lavayeh_province, lavayeh_row_number, lavayeh_persons,
            tracking_code, national_ids, court_total
        )
        return

    # ═══ ارسال فاکتور بله با استفاده از sendInvoice API ═══
    final_fee_toman = final_fee // 10

    try:
        invoice_payload = _json.dumps({"type": "lavayeh", "uid": user_id})
        # استفاده از API مستقیم بله (sendInvoice) — طبق مستندات بله
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
            invoice_url = f"{BALE_API_BASE}/bot{BOT_TOKEN}/sendInvoice"
            invoice_data = {
                "chat_id": user_id,
                "title": f"فاکتور {service_label}",
                "description": f"هزینه خدمات {service_label}\nمبلغ: {final_fee_toman:,} تومان ({final_fee:,} ریال)",
                "payload": invoice_payload,
                "provider_token": BALE_WALLET_TOKEN,
                "currency": "IRR",
                "prices": [{"label": service_label, "amount": final_fee}],
            }
            logging.info(f"[LAVAYEH] ارسال sendInvoice به chat_id={user_id}, مبلغ={final_fee:,} ریال, provider_token={BALE_WALLET_TOKEN[:15]}...")
            async with session.post(invoice_url, json=invoice_data) as resp:
                result = await resp.json()
                logging.info(f"[LAVAYEH] پاسخ sendInvoice: {result}")
                if not result.get("ok"):
                    logging.error(f"[LAVAYEH] خطای sendInvoice: {result}")
                    raise Exception(result.get("description", "خطا در ارسال فاکتور"))
    except Exception as e:
        logging.error(f"[LAVAYEH] خطا در ارسال فاکتور بله: {e}", exc_info=True)
        await bot.send_message(user_id, "⚠️ خطا در ساخت فاکتور پرداخت. لطفاً کمی بعد دوباره تلاش کنید.")
        runtime_state.active_lavayeh_users.discard(user_id)
        return

    # دکمه‌های تایید پرداخت و انصراف
    pay_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ پرداخت انجام شد", callback_data="lavayeh_pay_done")],
        [InlineKeyboardButton(text="❌ انصراف از درخواست", callback_data="lavayeh_pay_cancel")],
    ])
    warning = ""
    if user_id == ADMIN_ID:
        warning = (
            "\n\n⚠️ توجه: اگر کیف پول خودتان را شارژ کرده‌اید و اکنون می‌خواهید "
            "از همان کیف پول پرداخت کنید، پرداخت انجام نخواهد شد (خطای مبدأ و مقصد یکسان). "
            "لطفاً با یک حساب بله دیگر تست کنید.\n\n"
        )
    await bot.send_message(
        user_id,
        f"⏳ فاکتور پرداخت ارسال شد."
        f"{warning}"
        f"پس از پرداخت موفق و مشاهده پیام «پرداخت با موفقیت انجام شد»، "
        f"دکمه «پرداخت انجام شد» را بزنید.\n\n"
        f"❗ اگر خطایی در پرداخت دیدید، دکمه «پرداخت انجام شد» را نزنید و از «انصراف» استفاده کنید.",
        reply_markup=pay_kb
    )

    await log_event(
        "ثبت", doc_type, str(user_id), user_id,
        tracking_code=tracking_code, national_id=national_ids,
        doc_name=doc_type, payment_status="در انتظار پرداخت",
        note=f"مبلغ فاکتور: {final_fee:,} ریال (هزینه سامانه: {court_total:,} ریال)"
    )

    runtime_state.pending_lavayeh_payments[user_id] = {
        "invoice_time": datetime.datetime.now(),
        "final_fee": final_fee,
        "court_total": court_total,
        "tracking_code": tracking_code,
        "national_ids": national_ids,
        "reminder_sent": False,
        "blocked": False,
        "lavayeh_title": lavayeh_title,
        "lavayeh_province": lavayeh_province,
        "lavayeh_row_number": lavayeh_row_number,
        "lavayeh_persons": lavayeh_persons,
        "is_ezhharnameh": is_ezhharnameh,
    }

    user_state = runtime_state.dp.fsm.resolve_context(bot, user_id, user_id)
    await user_state.set_state(Form.waiting_for_lavayeh_payment_receipt)

    runtime_state.active_lavayeh_users.discard(user_id)


# ══════════════════════════════════════════════════════════════════════════════
# پرداخت هزینه لایحه
# ══════════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════════
# هندلر pre_checkout_query برای لایحه/اظهارنامه — تایید خودکار
# ══════════════════════════════════════════════════════════════════════════════
@lavayeh_router.pre_checkout_query()
async def lavayeh_pre_checkout_query(pre_checkout_query: PreCheckoutQuery, bot: Bot):
    """تایید خودکار درخواست پیش‌پرداخت فاکتور لایحه/اظهارنامه"""
    try:
        await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)
    except Exception as e:
        logging.error(f"[LAVAYEH] خطا در answer_pre_checkout_query: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# هندلر successful_payment لایحه/اظهارنامه — پرداخت خودکار پس از فاکتور بله
# ══════════════════════════════════════════════════════════════════════════════
@lavayeh_router.message(Form.waiting_for_lavayeh_payment_receipt, F.successful_payment)
async def lavayeh_successful_payment(message: Message, state: FSMContext, bot: Bot):
    """پرداخت موفق لایحه/اظهارنامه از طریق فاکتور بله — بدون نیاز به فیش"""
    user_id = message.from_user.id
    pending = runtime_state.pending_lavayeh_payments.get(user_id)
    if not pending:
        await message.answer("⚠️ فاکتور فعالی برای شما ثبت نشده است.")
        await state.clear()
        return

    payment = message.successful_payment
    is_ezhhar = pending.get("is_ezhharnameh", False)
    doc_type = "اظهارنامه" if is_ezhhar else "لایحه"
    final_fee_toman = pending["final_fee"] // 10

    await message.answer(
        f"✅ *پرداخت شما ثبت شد!*\n\n"
        f"📄 نوع: *{doc_type}*\n"
        f"💰 مبلغ: *{final_fee_toman:,} تومان*\n\n"
        f"🔔 مراحل بعدی به زودی ارسال می‌شود.",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )

    await log_event(
        "پرداخت", doc_type, message.from_user.full_name, user_id,
        tracking_code=pending.get("tracking_code", ""), national_id=pending.get("national_ids", ""),
        doc_name=doc_type, payment_status="پرداخت شده (کیف پول بله)",
        note=f"مبلغ: {pending['final_fee']:,} ریال | Bale payment_id: {payment.telegram_payment_charge_id}"
    )

    # اطلاع‌رسانی به ادمین — بدون parse_mode برای جلوگیری از خطا در بله
    try:
        admin_msg = (
            f"💰 پرداخت {doc_type} از طریق کیف پول بله:\n\n"
            f"👤 کاربر: {message.from_user.full_name} ({user_id})\n"
            f"📄 عنوان: {pending.get('lavayeh_title', doc_type)}\n"
            f"💰 مبلغ: {final_fee_toman:,} تومان\n"
            f"⏱ زمان: {datetime.datetime.now().strftime('%Y/%m/%d %H:%M')}\n"
            f"🎫 payment_id: {payment.telegram_payment_charge_id}"
        )
        logging.info(f"[LAVAYEH-PAYMENT] تلاش ارسال پیام به ادمین ADMIN_ID={ADMIN_ID} (نوع: {type(ADMIN_ID).__name__})")
        admin_result = await bot.send_message(ADMIN_ID, admin_msg)
        logging.info(f"[LAVAYEH-PAYMENT] اطلاع‌رسانی به ادمین موفق. result={admin_result}")
    except Exception as e:
        logging.error(f"[LAVAYEH-PAYMENT] خطا در ارسال اطلاع به ادمین (ADMIN_ID={ADMIN_ID}): {e}", exc_info=True)

    # ── انتقال به مرحله امضای الکترونیک ──
    if is_ezhhar:
        raw_persons = pending.get("lavayeh_persons", [])
        sign_persons = []
        for i, p in enumerate(raw_persons):
            sign_persons.append({
                "idx": i,
                "name": p.get("name", p.get("national_id", f"شخص {i+1}")),
                "person_type": p.get("person_type", ""),
                "national_id": p.get("national_id", ""),
            })
        runtime_state.pending_ezhhar_sign[user_id] = {
            "tracking_code": pending.get("tracking_code", ""),
            "is_ezhharnameh": True,
            "sign_persons": sign_persons,
            "persons_awaiting_sign": list(range(len(sign_persons))),
            "current_person_idx": 0,
            "sign_codes_received": {},
            "sign_sent_time": None,
            "wrong_code_time": None,
            "code_sent_announce_time": None,
            "resend_notified": False,
            "total_no_action_start": datetime.datetime.now(),
        }
        runtime_state.pending_lavayeh_payments.pop(user_id, None)

        from keyboards import ezhhar_sign_ready_kb
        await bot.send_message(
            user_id,
            "🖊 *مرحله اخذ امضای الکترونیک اظهارنامه:*\n\n"
            "هر موقع آمادگی دارید که کد امضا ارسال شود، گزینه زیر را انتخاب کنید:",
            reply_markup=ezhhar_sign_ready_kb)
        await state.set_state(Form.ezhhar_sign_ready)
    else:
        runtime_state.pending_lavayeh_sign[user_id] = {
            "tracking_code": pending.get("tracking_code", ""),
            "lavayeh_title": pending.get("lavayeh_title", "لایحه دفاعیه"),
            "province": pending.get("lavayeh_province", ""),
            "row_number": pending.get("lavayeh_row_number", 1),
            "persons": pending.get("lavayeh_persons", []),
            "sign_persons": [],
            "persons_awaiting_sign": [],
            "current_person_idx": None,
            "sign_sent_time": None,
            "sign_codes_received": {},
            "wrong_code_time": None,
            "code_sent_announce_time": None,
            "resend_notified": False,
            "total_no_action_start": None,
        }
        runtime_state.pending_lavayeh_payments.pop(user_id, None)

        await bot.send_message(
            user_id,
            "🖊 *مرحله اخذ امضای الکترونیک:*\n\n"
            "هر موقع آمادگی دارید که کد امضا ارسال شود، گزینه زیر را انتخاب کنید:",
            reply_markup=lavayeh_sign_ready_kb)
        await state.set_state(Form.lavayeh_sign_ready)


@lavayeh_router.callback_query(F.data == "lavayeh_pay_done", Form.waiting_for_lavayeh_payment_receipt)
async def lavayeh_pay_done_callback(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """کاربر دکمه تایید را زده — ابتدا تایید مجدد می‌خواهد"""
    await callback.answer()
    user_id = callback.from_user.id
    pending = runtime_state.pending_lavayeh_payments.get(user_id)
    if not pending:
        await callback.message.answer("⚠️ فاکتور فعالی برای شما ثبت نشده است.")
        await state.clear()
        return

    logging.info(f"[LAVAYEH-PAY-DONE] کاربر {user_id} دکمه پرداخت انجام شد را زد (درخواست تایید)")

    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ بله، پرداخت موفق بود", callback_data="lavayeh_pay_done_confirm")],
        [InlineKeyboardButton(text="❌ خیر، انصراف", callback_data="lavayeh_pay_cancel")],
    ])
    await callback.message.answer(
        "❓ آیا مطمئن هستید که پرداخت با موفقیت انجام شد؟\n\n"
        "اگر پیام «پرداخت با موفقیت انجام شد» را در کیف پول بله دیده‌اید، «بله» را بزنید.\n"
        "اگر خطایی دیدید، «خیر» را بزنید.",
        reply_markup=confirm_kb
    )


@lavayeh_router.callback_query(F.data == "lavayeh_pay_done_confirm", Form.waiting_for_lavayeh_payment_receipt)
async def lavayeh_pay_done_confirm_callback(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """تایید نهایی — پردازش واقعی فلوی پرداخت لایحه/اظهارنامه"""
    await callback.answer()
    user_id = callback.from_user.id
    pending = runtime_state.pending_lavayeh_payments.get(user_id)
    if not pending:
        await callback.message.answer("⚠️ فاکتور فعالی برای شما ثبت نشده است.")
        await state.clear()
        return

    logging.info(f"[LAVAYEH-PAY-DONE-CONFIRMED] کاربر {user_id} تایید نهایی پرداخت لایحه")

    is_ezhhar = pending.get("is_ezhharnameh", False)
    doc_type = "اظهارنامه" if is_ezhhar else "لایحه"
    final_fee_toman = pending["final_fee"] // 10

    await callback.message.answer(
        f"✅ پرداخت شما ثبت شد!\n\n"
        f"📄 نوع: {doc_type}\n"
        f"💰 مبلغ: {final_fee_toman:,} تومان\n\n"
        f"🔔 مراحل بعدی به زودی ارسال می‌شود.",
        reply_markup=ReplyKeyboardRemove()
    )

    await log_event(
        "پرداخت", doc_type, callback.from_user.full_name, user_id,
        tracking_code=pending.get("tracking_code", ""), national_id=pending.get("national_ids", ""),
        doc_name=doc_type, payment_status="پرداخت شده (کیف پول بله - تایید کاربر)",
        note=f"مبلغ: {pending['final_fee']:,} ریال"
    )

    # اطلاع‌رسانی به ادمین
    try:
        admin_msg = (
            f"💰 پرداخت {doc_type} (دکمه تایید کاربر):\n\n"
            f"👤 کاربر: {callback.from_user.full_name} ({user_id})\n"
            f"📄 عنوان: {pending.get('lavayeh_title', doc_type)}\n"
            f"💰 مبلغ: {final_fee_toman:,} تومان\n"
            f"⏱ زمان: {datetime.datetime.now().strftime('%Y/%m/%d %H:%M')}"
        )
        logging.info(f"[LAVAYEH-PAY-DONE] تلاش ارسال پیام به ادمین ADMIN_ID={ADMIN_ID}")
        await bot.send_message(ADMIN_ID, admin_msg)
        logging.info(f"[LAVAYEH-PAY-DONE] اطلاع‌رسانی به ادمین موفق.")
    except Exception as e:
        logging.error(f"[LAVAYEH-PAY-DONE] خطا در ارسال اطلاع به ادمین: {e}", exc_info=True)

    # ── انتقال به مرحله امضای الکترونیک (همان فلوی successful_payment) ──
    if is_ezhhar:
        raw_persons = pending.get("lavayeh_persons", [])
        sign_persons = []
        for i, p in enumerate(raw_persons):
            sign_persons.append({
                "idx": i,
                "name": p.get("name", p.get("national_id", f"شخص {i+1}")),
                "person_type": p.get("person_type", ""),
                "national_id": p.get("national_id", ""),
            })
        runtime_state.pending_ezhhar_sign[user_id] = {
            "tracking_code": pending.get("tracking_code", ""),
            "is_ezhharnameh": True,
            "sign_persons": sign_persons,
            "persons_awaiting_sign": list(range(len(sign_persons))),
            "current_person_idx": 0,
            "sign_codes_received": {},
            "sign_sent_time": None,
            "wrong_code_time": None,
            "code_sent_announce_time": None,
            "resend_notified": False,
            "total_no_action_start": datetime.datetime.now(),
        }
        runtime_state.pending_lavayeh_payments.pop(user_id, None)

        from keyboards import ezhhar_sign_ready_kb
        await bot.send_message(
            user_id,
            "🖊 مرحله اخذ امضای الکترونیک اظهارنامه:\n\n"
            "هر موقع آمادگی دارید که کد امضا ارسال شود، گزینه زیر را انتخاب کنید:",
            reply_markup=ezhhar_sign_ready_kb)
        await state.set_state(Form.ezhhar_sign_ready)
    else:
        runtime_state.pending_lavayeh_sign[user_id] = {
            "tracking_code": pending.get("tracking_code", ""),
            "lavayeh_title": pending.get("lavayeh_title", "لایحه دفاعیه"),
            "province": pending.get("lavayeh_province", ""),
            "row_number": pending.get("lavayeh_row_number", 1),
            "persons": pending.get("lavayeh_persons", []),
            "sign_persons": [],
            "persons_awaiting_sign": [],
            "current_person_idx": None,
            "sign_sent_time": None,
            "sign_codes_received": {},
            "wrong_code_time": None,
            "code_sent_announce_time": None,
            "resend_notified": False,
            "total_no_action_start": None,
        }
        runtime_state.pending_lavayeh_payments.pop(user_id, None)

        await bot.send_message(
            user_id,
            "🖊 مرحله اخذ امضای الکترونیک:\n\n"
            "هر موقع آمادگی دارید که کد امضا ارسال شود، گزینه زیر را انتخاب کنید:",
            reply_markup=lavayeh_sign_ready_kb)
        await state.set_state(Form.lavayeh_sign_ready)


@lavayeh_router.callback_query(F.data == "lavayeh_pay_cancel")
async def lavayeh_pay_cancel_callback(callback: CallbackQuery, state: FSMContext):
    """کاربر انصراف از پرداخت لایحه"""
    await callback.answer()
    user_id = callback.from_user.id
    pending = runtime_state.pending_lavayeh_payments.get(user_id)
    if pending:
        pending["blocked"] = False  # رفع مسدودیت
        runtime_state.pending_lavayeh_payments.pop(user_id, None)
    await state.clear()
    await callback.message.answer(
        "لغو گردید. لطفاً مجدداً شروع کنید:",
        reply_markup=main_menu_kb
    )
    await state.set_state(Form.main_menu)


@lavayeh_router.message(Form.waiting_for_lavayeh_payment_receipt)
async def lavayeh_payment_waiting_message(message: Message):
    """در حال انتظار پرداخت — پرداخت از طریق فاکتور بله انجام می‌شود"""
    if message.text and "انصراف" in message.text:
        pass  # هندلر انصراف جداگانه مدیریت می‌شود
    else:
        await message.answer("⏳ لطفاً فاکتور ارسال شده را در چت پرداخت کنید. نیازی به ارسال عکس رسید نیست.")


@lavayeh_router.callback_query(F.data.startswith("oklav:"))
async def admin_approve_lavayeh_receipt(callback: CallbackQuery, bot: Bot):
    user_id = int(callback.data.split(":")[1])
    review = runtime_state.pending_admin_payment_review.pop(user_id, None)
    if not review:
        await callback.answer("⚠️ درخواست یافت نشد.", show_alert=True)
        return

    await callback.answer("✅ تایید شد", show_alert=False)
    try:
        await bot.edit_message_reply_markup(ADMIN_ID, review["message_id"], reply_markup=None)
    except Exception:
        pass

    pending = runtime_state.pending_lavayeh_payments.get(user_id)
    if not pending:
        await bot.send_message(user_id, "⚠️ فاکتور فعالی یافت نشد. لطفاً با پشتیبانی تماس بگیرید.")
        return

    is_ezhhar = pending.get("is_ezhharnameh", False)
    doc_type = "اظهارنامه" if is_ezhhar else "لایحه"
    await bot.send_message(user_id, f"✅ *رسید شما توسط مدیریت تایید شد.*\n\nهزینه {doc_type} تایید شد. متشکریم 🙏", reply_markup=ReplyKeyboardRemove())
    await log_event(
        "پرداخت", doc_type, "تایید دستی مدیر", user_id,
        tracking_code=pending.get("tracking_code", ""), national_id=pending.get("national_ids", ""),
        doc_name=doc_type, payment_status="پرداخت شده (تایید دستی)",
        note=f"مبلغ: {review['expected_amount']:,} ریال"
    )

    user_state = runtime_state.dp.fsm.resolve_context(bot, user_id, user_id)

    # ── تمایز بین لایحه و اظهارنامه برای فلوی امضا (تایید دستی مدیر) ──
    if is_ezhhar:
        raw_persons = pending.get("lavayeh_persons", [])
        sign_persons = []
        for i, p in enumerate(raw_persons):
            sign_persons.append({
                "idx": i,
                "name": p.get("name", p.get("national_id", f"شخص {i+1}")),
                "person_type": p.get("person_type", ""),
                "national_id": p.get("national_id", ""),
            })
        runtime_state.pending_ezhhar_sign[user_id] = {
            "tracking_code": pending.get("tracking_code", ""),
            "is_ezhharnameh": True,
            "sign_persons": sign_persons,
            "persons_awaiting_sign": list(range(len(sign_persons))),
            "current_person_idx": 0,
            "sign_codes_received": {},
            "sign_sent_time": None,
            "wrong_code_time": None,
            "code_sent_announce_time": None,
            "resend_notified": False,
            "total_no_action_start": datetime.datetime.now(),
        }
        runtime_state.pending_lavayeh_payments.pop(user_id, None)

        from keyboards import ezhhar_sign_ready_kb
        await bot.send_message(
            user_id,
            "🖊 *مرحله اخذ امضای الکترونیک اظهارنامه:*\n\n"
            "هر موقع آمادگی دارید که کد امضا ارسال شود، گزینه زیر را انتخاب کنید:",
            reply_markup=ezhhar_sign_ready_kb)
        await user_state.set_state(Form.ezhhar_sign_ready)
    else:
        runtime_state.pending_lavayeh_sign[user_id] = {
            "tracking_code": pending.get("tracking_code", ""),
            "lavayeh_title": pending.get("lavayeh_title", "لایحه دفاعیه"),
            "province": pending.get("lavayeh_province", ""),
            "row_number": pending.get("lavayeh_row_number", 1),
            "persons": pending.get("lavayeh_persons", []),
            "sign_persons": [],
            "persons_awaiting_sign": [],
            "current_person_idx": None,
            "sign_sent_time": None,
            "sign_codes_received": {},
            "wrong_code_time": None,
            "code_sent_announce_time": None,
            "resend_notified": False,
            "total_no_action_start": None,
        }
        runtime_state.pending_lavayeh_payments.pop(user_id, None)

        await bot.send_message(
            user_id,
            "🖊 *مرحله اخذ امضای الکترونیک:*\n\n"
            "هر موقع آمادگی دارید که کد امضا ارسال شود، گزینه زیر را انتخاب کنید:",
            reply_markup=lavayeh_sign_ready_kb)
        await user_state.set_state(Form.lavayeh_sign_ready)


    # حذف فایل رسید
    photo_path = review.get("photo_path")
    if photo_path and os.path.exists(photo_path):
        try:
            os.remove(photo_path)
        except Exception:
            pass


@lavayeh_router.callback_query(F.data.startswith("nolav:"))
async def admin_reject_lavayeh_receipt(callback: CallbackQuery, bot: Bot):
    user_id = int(callback.data.split(":")[1])
    review = runtime_state.pending_admin_payment_review.pop(user_id, None)
    if not review:
        await callback.answer("⚠️ درخواست یافت نشد.", show_alert=True)
        return

    await callback.answer("❌ رد شد", show_alert=False)
    try:
        await bot.edit_message_reply_markup(ADMIN_ID, review["message_id"], reply_markup=None)
    except Exception:
        pass

    await bot.send_message(
        user_id,
        "❌ رسید پرداخت شما توسط مدیریت تایید نشد.\n\nلطفاً تصویر رسید معتبر مجدداً ارسال فرمایید."
    )

    # حذف فایل رسید
    photo_path = review.get("photo_path")
    if photo_path and os.path.exists(photo_path):
        try:
            os.remove(photo_path)
        except Exception:
            pass


@lavayeh_router.message(Form.waiting_for_lavayeh_payment_receipt)
async def lavayeh_payment_receipt_text_only(message: Message):
    # دیگر نیازی به ارسال عکس فیش نیست — کاربر باید از دکمه «پرداخت کردم» استفاده کند
    if message.text and "انصراف" in message.text:
        pass  # هندلر انصراف جداگانه مدیریت می‌شود
    else:
        await message.answer("⚠️ لطفاً از دکمه «پرداخت» در فاکتور ارسال‌شده استفاده فرمایید. نیازی به ارسال عکس رسید نیست.")


# ══════════════════════════════════════════════════════════════════════════════
# یادآوری ۲۴ ساعته + مسدودسازی
# ══════════════════════════════════════════════════════════════════════════════
async def lavayeh_payment_reminder_loop(bot: Bot):
    while True:
        try:
            now = datetime.datetime.now()
            for user_id, info in list(runtime_state.pending_lavayeh_payments.items()):
                if info.get("reminder_sent") or info.get("blocked"):
                    continue
                age = now - info["invoice_time"]
                if age >= datetime.timedelta(days=1):
                    try:
                        await bot.send_message(
                            user_id,
                            "با درود\nآیا مورد ثبتی شما کنسل می‌باشد؟",
                            reply_markup=lavayeh_cancel_reminder_kb
                        )
                        info["reminder_sent"] = True
                        user_state = runtime_state.dp.fsm.resolve_context(bot, user_id, user_id)
                        await user_state.set_state(Form.lavayeh_payment_reminder_response)
                    except Exception as e:
                        logging.error(f"[LAVAYEH] خطا در ارسال یادآوری به کاربر {user_id}: {e}")
        except Exception as e:
            logging.error(f"[LAVAYEH] خطا در حلقه یادآوری: {e}")
        await asyncio.sleep(1800)


@lavayeh_router.message(Form.lavayeh_payment_reminder_response, F.text == "خیر")
async def lavayeh_reminder_no(message: Message, state: FSMContext):
    await message.answer(
        "مورد ثبتی شما تا پایان فردا ابطال خواهد شد؛ هرچه سریع‌تر پرداخت فرمایید.",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(Form.waiting_for_lavayeh_payment_receipt)


@lavayeh_router.message(Form.lavayeh_payment_reminder_response, F.text == "بله")
async def lavayeh_reminder_yes(message: Message, state: FSMContext):
    user_id = message.from_user.id
    pending = runtime_state.pending_lavayeh_payments.get(user_id)
    if not pending:
        await message.answer("⚠️ فاکتور فعالی برای شما ثبت نشده است.", reply_markup=ReplyKeyboardRemove())
        return
    reduced_amount = pending["final_fee"] - pending["court_total"]
    pending["blocked"] = True
    pending["final_fee"] = reduced_amount
    await message.answer(
        f"لطفاً هزینه ثبت لایحه را پرداخت بفرمائید.\n"
        f"مبلغ: *{reduced_amount:,} ریال*\n\nباتشکر",
        reply_markup=ReplyKeyboardRemove())
    await state.set_state(Form.waiting_for_lavayeh_payment_receipt)


@lavayeh_router.message(Form.lavayeh_payment_reminder_response)
async def lavayeh_reminder_invalid(message: Message):
    await message.answer(
        "لطفاً یکی از گزینه‌های «بله» یا «خیر» را انتخاب فرمایید:",
        reply_markup=lavayeh_cancel_reminder_kb
    )
