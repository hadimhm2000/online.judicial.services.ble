"""
هندلرهای بخش ثبت اظهارنامه — فلوی مکالمه تلگرام.

جریان:
  ۱. ورود به بخش اظهارنامه
  ۲. دریافت نوع شخصیت اظهارکننده(ها)  ← مانند بخش لایحه
     ⚠ اگر وکیل انتخاب شد، حتماً باید حقیقی یا حقوقی هم باشد
  ۳. دریافت نوع شخصیت مخاطب(ها)
     ← گزینه استعلام شماره تماس هم وجود دارد
  ۴. عنوان (موضوع) اظهارنامه
  ۵. شرح متن
  ۶. مدارک (پیوست‌ها) — مانند بخش لایحه
     ⚠ اگر اظهارکننده حقوقی داشت: مدرک نمایندگی اجباری است
  ۷. پیش‌نمایش و تایید
"""

import asyncio
import logging
import re

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

import runtime_state
from states import Form
from keyboards import (
    main_menu_kb, restart_kb, back_only_kb,
    representative_type_kb,
    lavayeh_attachment_more_kb,
    ezhhar_confirm_kb, ezhhar_edit_kb,
    ezhhar_subject_kb,
    ezhhar_declarant_add_more_kb,
    ezhhar_addressee_add_more_kb,
    ezhhar_attachment_title_kb_first,
    ezhhar_attachment_title_kb,
    ezhhar_attachment_more_kb,
    create_ezhhar_declarant_person_type_kb,
    create_ezhhar_addressee_person_type_kb,
    bulk_choice_kb,
    bulk_input_method_kb,
    bulk_confirm_kb)
from bulk_submissions import (
    generate_sample_excel,
    parse_excel_file,
    parse_text_or_image_input,
    generate_tracking_code,
    BULK_TASKS,
    run_bulk_processing_task)

ezhharnameh_router = Router()

_FA_AR = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789"
)

def _to_en(text: str) -> str:
    return text.translate(_FA_AR).replace(" ", "").strip()

def _fmt(n: int) -> str:
    return f"{n:,}"


# ══════════════════════════════════════════════════════════════════════════════
# ورود به بخش اظهارنامه
# ══════════════════════════════════════════════════════════════════════════════
@ezhharnameh_router.message(StateFilter("*"), F.text == "🔙 بازگشت به منوی اصلی")
async def ezhharnameh_back_to_main(message: Message, state: FSMContext):
    """بازگشت به منوی اصلی از هر مرحله‌ای از اظهارنامه"""
    await state.clear()
    from keyboards import get_flow_type_kb
    await message.answer(
        "❓ *لطفاً نحوه ثبت درخواست خود را انتخاب فرمایید:*",
        reply_markup=get_flow_type_kb(message.from_user.id))
    await state.set_state(Form.waiting_for_flow_type)


@ezhharnameh_router.message(StateFilter("*"), F.text == "📋 ثبت اظهارنامه")
async def ezhharnameh_entry(message: Message, state: FSMContext):
    await state.clear()
    await state.update_data(
        ezhhar_declarants=[],        # لیست اظهارکنندگان
        ezhhar_addressees=[],        # لیست مخاطبین
        ezhhar_subject="",
        ezhhar_text="",
        ezhhar_attachments=[],       # پیوست‌ها
        ezhhar_images=[],
        service_type="ezhharnameh")
    await message.answer(
        "📋 *ثبت اظهارنامه*\n\n"
        "آیا قصد ثبت *یک مورد اظهارنامه* دارید یا *بیش از ۵ مورد ثبتی (ثبت دسته‌جمعی)*؟\n\n"
        "💡 *توجه:* در صورتی که تعداد اظهارنامه‌های شما زیاد است (بیش از ۵ مورد)، برای صرفه‌جویی در زمان و جلوگیری از معطلی سایر مراجعان ربات، لطفاً گزینه *«⚡️ ثبت دسته‌جمعی سریع»* را انتخاب نمایید تا تمامی موارد در پس‌زمینه و بدون اختلال زمانی ثبت شوند.",
        reply_markup=bulk_choice_kb)
    await state.set_state(Form.ezhhar_declarant_person_type)


@ezhharnameh_router.message(Form.ezhhar_declarant_person_type, F.text == "⚡️ ثبت دسته‌جمعی سریع (بدون معطلی - فایل اکسل)")
async def ezhhar_bulk_choice_handler(message: Message, state: FSMContext):
    await message.answer(
        "⚡️ *ثبت دسته‌جمعی سریع اظهارنامه*\n\n"
        "در این روش می‌توانید اطلاعات بیش از ۵ اظهارنامه را با *فایل اکسل* ارسال فرمایید.\n"
        "✅ سیستم به صورت خودکار حتی در صورت بروز خطا یا نقص در برخی ردیف‌ها، ثبت را متوقف نکرده و با انعطاف‌پذیری کامل پردازش را ادامه می‌دهد.\n\n"
        "لطفاً فایل اکسل نمونه را دریافت و تکمیل نمایید:",
        reply_markup=bulk_input_method_kb)
    await state.set_state(Form.bulk_input_method)


@ezhharnameh_router.message(Form.ezhhar_declarant_person_type, F.text == "1️⃣ ثبت تکی (روال عادی)")
async def ezhhar_single_choice_handler(message: Message, state: FSMContext):
    await message.answer(
        "📋 *ثبت اظهارنامه (روال تکی)*\n\n"
        "*مرحله ۱:* لطفاً *نوع شخصیت اظهارکننده* را انتخاب فرمایید:\n\n"
        "⚠️ توجه: اگر *وکیل* را انتخاب می‌کنید، باید حداقل یک *شخص حقیقی یا حقوقی* نیز اضافه کنید.",
        reply_markup=create_ezhhar_declarant_person_type_kb())
    # باقی ماندن در همین استیت برای دریافت نوع شخص اظهارکننده
    await state.set_state(Form.ezhhar_declarant_person_type)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۱ — نوع شخصیت اظهارکننده
# ══════════════════════════════════════════════════════════════════════════════
@ezhharnameh_router.message(Form.ezhhar_declarant_person_type)
async def ezhhar_declarant_person_type_handler(message: Message, state: FSMContext):
    text = message.text or ""
    data = await state.get_data()
    declarants = data.get("ezhhar_declarants", [])
    used_types = [p.get("person_type") for p in declarants]

    if text == "✅ اتمام و ادامه":
        if not declarants:
            await message.answer("⚠️ حداقل یک اظهارکننده باید اضافه شود.")
            return

        # بررسی: اگر وکیل داشتیم، باید حقیقی یا حقوقی هم داشته باشیم
        has_lawyer = any(p.get("person_type") == "وکیل" for p in declarants)
        has_real_or_legal = any(p.get("person_type") in ("شخص حقیقی", "شخص حقوقی") for p in declarants)
        if has_lawyer and not has_real_or_legal:
            await message.answer(
                "⚠️ *توجه مهم:*\n\n"
                "چون *وکیل* اضافه کرده‌اید، باید حداقل یک *شخص حقیقی یا حقوقی* نیز وجود داشته باشد.\n\n"
                "لطفاً نوع شخص دیگری انتخاب کنید:",
                reply_markup=create_ezhhar_declarant_person_type_kb(exclude=used_types))
            return

        # رفتن به مرحله مخاطب
        await message.answer(
            "*مرحله ۲:* لطفاً *نوع شخصیت مخاطب* اظهارنامه را انتخاب فرمایید:\n\n"
            "📌 درصورتی که کدملی مخاطب را ندارید و صرفاً شماره تماس شخص مورد نظر را دارید، "
            "می‌توانید از گزینه *«استعلام شماره تماس»* استفاده کنید.",
            reply_markup=create_ezhhar_addressee_person_type_kb())
        await state.set_state(Form.ezhhar_addressee_person_type)
        return

    if text not in ["شخص حقیقی", "شخص حقوقی", "وکیل"]:
        await message.answer(
            "⚠️ لطفاً یکی از گزینه‌های موجود را انتخاب کنید:",
            reply_markup=create_ezhhar_declarant_person_type_kb(exclude=used_types if declarants else [])
        )
        return

    await state.update_data(_ezhhar_current_declarant={"person_type": text})

    if text == "شخص حقوقی":
        await message.answer(
            "🏢 لطفاً *شناسه ملی شرکت* اظهارکننده را وارد فرمایید:\n_(۱۱ رقمی)_",
            reply_markup=back_only_kb)
        await state.set_state(Form.ezhhar_declarant_company_id)
    else:
        type_label = "وکیل" if text == "وکیل" else "شخص"
        await message.answer(
            f"🔢 لطفاً *کد ملی {type_label}* اظهارکننده را وارد کنید:\n_(۱۰ رقمی)_",
            reply_markup=back_only_kb)
        await state.set_state(Form.ezhhar_declarant_national_id)


@ezhharnameh_router.message(Form.ezhhar_declarant_company_id)
async def ezhhar_declarant_company_id_handler(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == "🔙 بازگشت":
        data = await state.get_data()
        declarants = data.get("ezhhar_declarants", [])
        used_types = [p.get("person_type") for p in declarants]
        await message.answer(
            "👤 لطفاً نوع شخص اظهارکننده را انتخاب کنید:",
            reply_markup=create_ezhhar_declarant_person_type_kb(exclude=used_types if declarants else [])
        )
        await state.set_state(Form.ezhhar_declarant_person_type)
        return

    company_id = _to_en(message.text)
    if not company_id.isdigit() or len(company_id) != 11:
        await message.answer("⚠️ شناسه ملی شرکت باید *۱۱ رقمی* باشد:")
        return

    data = await state.get_data()
    current = data.get("_ezhhar_current_declarant", {})
    current["company_id"] = company_id
    await state.update_data(_ezhhar_current_declarant=current)

    await message.answer("👔 نماینده شرکت چه سمتی دارد؟", reply_markup=representative_type_kb)
    await state.set_state(Form.ezhhar_declarant_representative_type)


@ezhharnameh_router.message(Form.ezhhar_declarant_representative_type)
async def ezhhar_declarant_representative_type_handler(message: Message, state: FSMContext):
    text = message.text or ""
    if text not in ["مدیرعامل", "نماینده"]:
        await message.answer("⚠️ لطفاً یکی از گزینه‌ها را انتخاب کنید:", reply_markup=representative_type_kb)
        return

    data = await state.get_data()
    current = data.get("_ezhhar_current_declarant", {})
    current["representative_type"] = text
    await state.update_data(_ezhhar_current_declarant=current)

    await message.answer(
        f"🔢 لطفاً *کد ملی {text}* شرکت اظهارکننده را وارد کنید:\n_(۱۰ رقمی)_",
        reply_markup=back_only_kb)
    await state.set_state(Form.ezhhar_declarant_national_id)


@ezhharnameh_router.message(Form.ezhhar_declarant_national_id)
async def ezhhar_declarant_national_id_handler(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == "🔙 بازگشت":
        data = await state.get_data()
        declarants = data.get("ezhhar_declarants", [])
        used_types = [p.get("person_type") for p in declarants]
        await message.answer(
            "👤 لطفاً نوع شخص اظهارکننده را انتخاب کنید:",
            reply_markup=create_ezhhar_declarant_person_type_kb(exclude=used_types if declarants else [])
        )
        await state.set_state(Form.ezhhar_declarant_person_type)
        return

    nat_id = _to_en(message.text)
    if not re.match(r"^[0-9]{10}$", nat_id):
        await message.answer("⚠️ کد ملی باید *۱۰ رقمی* باشد:")
        return

    data = await state.get_data()
    # ── بررسی تکراری نبودن کدملی (هم در اظهارکننده‌ها و هم در مخاطبین) ──
    declarants = data.get("ezhhar_declarants", [])
    addressees = data.get("ezhhar_addressees", [])
    all_ids = [p.get("national_id") for p in declarants + addressees if p.get("national_id")]
    if nat_id in all_ids:
        await message.answer(
            f"⚠️ کد ملی `{nat_id}` قبلاً ثبت شده است.\n"
            f"هر شخص باید کد ملی متفاوت داشته باشد.\n\n"
            f"لطفاً کد ملی دیگری وارد فرمایید:")
        return

    current = data.get("_ezhhar_current_declarant", {})
    current["national_id"] = nat_id
    declarants.append(current)
    await state.update_data(ezhhar_declarants=declarants, _ezhhar_current_declarant={})

    person_type = current.get("person_type", "")
    used_types = [p.get("person_type") for p in declarants]

    await message.answer(
        f"✅ *{person_type}* با کدملی `{nat_id}` ثبت شد.\n\n"
        f"آیا اظهارکننده دیگری نیز وجود دارد؟",
        reply_markup=create_ezhhar_declarant_person_type_kb())
    await state.set_state(Form.ezhhar_declarant_person_type)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۲ — نوع شخصیت مخاطب
# ══════════════════════════════════════════════════════════════════════════════
@ezhharnameh_router.message(Form.ezhhar_addressee_person_type)
async def ezhhar_addressee_person_type_handler(message: Message, state: FSMContext):
    text = message.text or ""
    data = await state.get_data()
    addressees = data.get("ezhhar_addressees", [])
    used_types = [p.get("person_type") for p in addressees]

    # استعلام شماره تماس — متوقف کردن اظهارنامه
    if text == "📞 استعلام شماره تماس":
        await message.answer(
            "📞 *فرایند اظهارنامه متوقف گردید.*\n\n"
            "در حال انتقال به بخش استعلام شماره تماس...\n"
            "پس از دریافت نتیجه استعلام، می‌توانید مجدداً ثبت اظهارنامه را آغاز کنید.",
            reply_markup=ReplyKeyboardRemove())
        await state.clear()
        # راه‌اندازی فلوی استعلام شماره تماس
        await message.answer(
            "📞 لطفاً شماره تماس مورد نظر را ارسال فرمایید:\n(با فرمت 09 آغاز شود)",
            reply_markup=back_only_kb
        )
        await state.set_state(Form.waiting_for_phone_number)
        return

    if text == "✅ اتمام و ادامه":
        if not addressees:
            await message.answer(
                "⚠️ حداقل یک مخاطب باید اضافه شود.",
                reply_markup=create_ezhhar_addressee_person_type_kb()
            )
            return
        # رفتن به مرحله عنوان
        await message.answer(
            "*مرحله ۳:* لطفاً *عنوان (موضوع) اظهارنامه* را وارد فرمایید:\n\n"
            "یا از گزینه زیر استفاده کنید اگر عنوان مهم نیست:",
            reply_markup=ezhhar_subject_kb)
        await state.set_state(Form.ezhhar_subject)
        return

    if text not in ["شخص حقیقی", "شخص حقوقی"]:
        await message.answer(
            "⚠️ لطفاً یکی از گزینه‌های موجود را انتخاب کنید:",
            reply_markup=create_ezhhar_addressee_person_type_kb(exclude=used_types if addressees else [])
        )
        return

    await state.update_data(_ezhhar_current_addressee={"person_type": text})

    if text == "شخص حقوقی":
        await message.answer(
            "🏢 لطفاً *شناسه ملی شرکت* مخاطب را وارد فرمایید:\n_(۱۱ رقمی)_",
            reply_markup=back_only_kb)
        await state.set_state(Form.ezhhar_addressee_company_id_no_rep)
    else:
        await message.answer(
            "🔢 لطفاً *کد ملی مخاطب* را وارد کنید:\n_(۱۰ رقمی)_",
            reply_markup=back_only_kb)
        await state.set_state(Form.ezhhar_addressee_national_id)


@ezhharnameh_router.message(Form.ezhhar_addressee_company_id_no_rep)
async def ezhhar_addressee_company_id_no_rep_handler(message: Message, state: FSMContext):
    """دریافت شناسه ملی شرکت مخاطب حقوقی — بدون پرسیدن سمت و کدملی نماینده."""
    if not message.text:
        return
    if message.text == "🔙 بازگشت":
        data = await state.get_data()
        addressees = data.get("ezhhar_addressees", [])
        used_types = [p.get("person_type") for p in addressees]
        await message.answer(
            "👥 لطفاً نوع شخص مخاطب را انتخاب کنید:",
            reply_markup=create_ezhhar_addressee_person_type_kb(exclude=used_types if addressees else [])
        )
        await state.set_state(Form.ezhhar_addressee_person_type)
        return

    company_id = _to_en(message.text)
    if not company_id.isdigit() or len(company_id) != 11:
        await message.answer("⚠️ شناسه ملی شرکت باید *۱۱ رقمی* باشد:")
        return

    data = await state.get_data()
    current = data.get("_ezhhar_current_addressee", {})
    current["company_id"] = company_id
    current["representative_type"] = ""
    current["national_id"] = ""
    addressees = data.get("ezhhar_addressees", [])
    addressees.append(current)
    await state.update_data(ezhhar_addressees=addressees, _ezhhar_current_addressee={})

    person_type = current.get("person_type", "")

    await message.answer(
        f"✅ *مخاطب ({person_type})* با شناسه ملی `{company_id}` ثبت شد.\n\n"
        f"آیا مخاطب دیگری نیز وجود دارد؟\n\n"
        f"📌 اگر کدملی مخاطب بعدی را ندارید، می‌توانید «استعلام شماره تماس» را انتخاب کنید.",
        reply_markup=create_ezhhar_addressee_person_type_kb(show_finish=True))
    await state.set_state(Form.ezhhar_addressee_person_type)


@ezhharnameh_router.message(Form.ezhhar_addressee_national_id)
async def ezhhar_addressee_national_id_handler(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == "🔙 بازگشت":
        data = await state.get_data()
        addressees = data.get("ezhhar_addressees", [])
        used_types = [p.get("person_type") for p in addressees]
        await message.answer(
            "👥 لطفاً نوع شخص مخاطب را انتخاب کنید:",
            reply_markup=create_ezhhar_addressee_person_type_kb(exclude=used_types if addressees else [])
        )
        await state.set_state(Form.ezhhar_addressee_person_type)
        return

    nat_id = _to_en(message.text)
    if not re.match(r"^[0-9]{10}$", nat_id):
        await message.answer("⚠️ کد ملی باید *۱۰ رقمی* باشد:")
        return

    data = await state.get_data()
    # ── بررسی تکراری نبودن کدملی (هم در مخاطبین و هم در اظهارکننده‌ها) ──
    addressees = data.get("ezhhar_addressees", [])
    declarants = data.get("ezhhar_declarants", [])
    all_ids = [p.get("national_id") for p in addressees + declarants if p.get("national_id")]
    if nat_id in all_ids:
        await message.answer(
            f"⚠️ کد ملی `{nat_id}` قبلاً ثبت شده است.\n"
            f"هر شخص باید کد ملی متفاوت داشته باشد.\n\n"
            f"لطفاً کد ملی دیگری وارد فرمایید:")
        return

    current = data.get("_ezhhar_current_addressee", {})
    current["national_id"] = nat_id
    addressees.append(current)
    await state.update_data(ezhhar_addressees=addressees, _ezhhar_current_addressee={})

    person_type = current.get("person_type", "")
    used_types = [p.get("person_type") for p in addressees]

    await message.answer(
        f"✅ *مخاطب ({person_type})* با کدملی `{nat_id}` ثبت شد.\n\n"
        f"آیا مخاطب دیگری نیز وجود دارد؟\n\n"
        f"📌 اگر کدملی مخاطب بعدی را ندارید، می‌توانید «استعلام شماره تماس» را انتخاب کنید.",
        reply_markup=create_ezhhar_addressee_person_type_kb(show_finish=True))
    await state.set_state(Form.ezhhar_addressee_person_type)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۳ — عنوان اظهارنامه
# ══════════════════════════════════════════════════════════════════════════════
@ezhharnameh_router.message(Form.ezhhar_subject)
async def ezhhar_subject_handler(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        await message.answer("⚠️ لطفاً عنوان را وارد کنید یا از گزینه زیر استفاده کنید:", reply_markup=ezhhar_subject_kb)
        return

    if text == "🔙 بازگشت":
        # بازگشت به مرحله مخاطبین
        data = await state.get_data()
        addressees = data.get("ezhhar_addressees", [])
        await message.answer(
            "*مرحله ۲:* لطفاً *نوع شخصیت مخاطب* اظهارنامه را انتخاب فرمایید:",
            reply_markup=create_ezhhar_addressee_person_type_kb(show_finish=bool(addressees)))
        await state.set_state(Form.ezhhar_addressee_person_type)
        return

    if text == "🔹 عنوان مهم نیست (ادامه مراحل)":
        subject = "سایر"
    else:
        subject = text

    await state.update_data(ezhhar_subject=subject)

    await message.answer(
        f"✅ عنوان «*{subject}*» ثبت شد.\n\n"
        "*مرحله ۴:* لطفاً *شرح متن اظهارنامه* را به صورت کامل و تایپ‌شده ارسال فرمایید:\n\n"
        "⚠️ *توجه:* متن پس از ارسال قابل ویرایش نمی‌باشد.",
        reply_markup=ReplyKeyboardRemove())
    await state.set_state(Form.ezhhar_text)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۴ — شرح متن اظهارنامه
# ══════════════════════════════════════════════════════════════════════════════
@ezhharnameh_router.message(Form.ezhhar_text)
async def ezhhar_text_handler(message: Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    chat_id = message.chat.id

    # ── پشتیبانی فایل ورد ──────────────────────────────────────
    if message.document and message.document.file_name and message.document.file_name.lower().endswith(".docx"):
        from text_collector import process_docx_input

        async def _on_ezhhar_docx_complete(final_text, final_html, st, b, cid, was_editing, char_count):
            await st.update_data(ezhhar_text=final_text, ezhhar_text_html=final_html, ezhhar_attachments=[], ezhhar_images=[])

            data = await st.get_data()
            declarants = data.get("ezhhar_declarants", [])
            has_legal = any(p.get("person_type") == "شخص حقوقی" for p in declarants)

            if has_legal:
                await b.send_message(
                    cid,
                    "*مرحله ۵ — مدارک:*\n\n"
                    "⚠️ *توجه مهم:* چون اظهارکننده شخص *حقوقی* دارید، ارسال تصویر *مدرک نمایندگی اجباری* است.\n\n"
                    "📸 لطفاً تصویر *مدرک نمایندگی* را ارسال فرمایید.\n"
                    "_(مثلاً: روزنامه رسمی، آگهی تأسیس، وکالت‌نامه رسمی)_")
                await st.update_data(
                    _ezhhar_mandatory_proxy_sent=False,
                    ezhhar_images=[],
                    _ezhhar_current_attachment_title="مدرک نمایندگی"
                )
                await st.set_state(Form.ezhhar_attachment_images)
            else:
                await _ask_ezhhar_attachment(message, st, is_first=True)

        await process_docx_input(
            message=message,
            user_id=user_id,
            chat_id=chat_id,
            state=state,
            bot=bot,
            on_complete=_on_ezhhar_docx_complete,
            text_state_key="ezhhar_text",
            html_state_key="ezhhar_text_html",
            extra_state_updates={"ezhhar_attachments": [], "ezhhar_images": []},
            processing_msg="⏳ در حال پردازش فایل ورد...")
        return

    if not message.text:
        await message.answer("⚠️ لطفاً شرح متن را به صورت متن ارسال فرمایید.\nیا فایل .docx ارسال نمایید.")
        return

    from text_collector import collect_text_part

    async def _on_ezhhar_text_complete(final_text, st, b, cid, was_editing):
        await st.update_data(ezhhar_text=final_text, ezhhar_text_html="", ezhhar_attachments=[], ezhhar_images=[])

        data = await st.get_data()
        declarants = data.get("ezhhar_declarants", [])
        has_legal = any(p.get("person_type") == "شخص حقوقی" for p in declarants)

        if has_legal:
            await b.send_message(
                cid,
                "*مرحله ۵ — مدارک:*\n\n"
                "⚠️ *توجه مهم:* چون اظهارکننده شخص *حقوقی* دارید، ارسال تصویر *مدرک نمایندگی اجباری* است.\n\n"
                "📸 لطفاً تصویر *مدرک نمایندگی* را ارسال فرمایید.\n"
                "_(مثلاً: روزنامه رسمی، آگهی تأسیس، وکالت‌نامه رسمی)_")
            await st.update_data(
                _ezhhar_mandatory_proxy_sent=False,
                ezhhar_images=[],
                _ezhhar_current_attachment_title="مدرک نمایندگی"
            )
            await st.set_state(Form.ezhhar_attachment_images)
        else:
            await _ask_ezhhar_attachment(message, st, is_first=True)

    await collect_text_part(
        user_id=user_id,
        chat_id=chat_id,
        text=message.text,
        state=state,
        bot=bot,
        on_complete=_on_ezhhar_text_complete,
        first_part_reply="⏳ در حال دریافت متن اظهارنامه...")


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۵ — پیوست‌ها (مدارک)
# ══════════════════════════════════════════════════════════════════════════════
async def _ask_ezhhar_attachment(message: Message, state: FSMContext, is_first: bool):
    await state.update_data(ezhhar_images=[])
    kb = ezhhar_attachment_title_kb_first if is_first else ezhhar_attachment_title_kb
    intro = "✅ متن اظهارنامه ثبت شد.\n\n" if is_first else ""
    await message.answer(
        f"{intro}📄 *عنوان مدرک:*\n\n"
        "در صورتی که تصویری برای ضمیمه دارید، عنوان آن را تایپ کنید\n"
        "یا یکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=kb)
    await state.set_state(Form.ezhhar_attachment_title)


@ezhharnameh_router.message(Form.ezhhar_attachment_title)
async def ezhhar_attachment_title_handler(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        await message.answer("⚠️ لطفاً عنوان را وارد کنید.")
        return

    data = await state.get_data()
    attachments = data.get("ezhhar_attachments", [])
    mandatory_sent = data.get("_ezhhar_mandatory_proxy_sent", True)

    # رد کردن — بدون ارسال مدرک (فقط اگر مدرک نمایندگی اجباری قبلاً ارسال شده یا نیاز نبود)
    if text == "⏭ رد کردن (بدون مدرک)":
        if not mandatory_sent and not attachments:
            # مدرک نمایندگی اجباری هنوز ارسال نشده — نباید رد کند
            await message.answer(
                "⚠️ ارسال تصویر *مدرک نمایندگی* برای شخص حقوقی اجباری است.\n\n"
                "لطفاً تصویر مدرک را ارسال فرمایید.")
            return
        await state.update_data(ezhhar_attachments=[])
        await _go_to_ezhhar_preview(message, state)
        return

    if text == "🔙 بازگشت":
        # بازگشت به مرحله متن اظهارنامه
        await message.answer(
            "*مرحله ۴:* لطفاً *شرح متن اظهارنامه* را به صورت کامل ارسال فرمایید:",
            reply_markup=ReplyKeyboardRemove())
        await state.set_state(Form.ezhhar_text)
        return

    if text == "🔹 عنوان مهم نیست (صرفا درج شود مستندات)":
        title = "مستندات"
    else:
        title = text

    await state.update_data(_ezhhar_current_att_title=title)

    await message.answer(
        f"✅ عنوان «*{title}*» ثبت شد.\n\n"
        "🖼 لطفاً تصاویر مربوط به این مدرک را به صورت *عکس (Photo)* ارسال فرمایید.\n"
        "⚠️ فقط فرمت *JPG / JPEG* قابل قبول است.\n\n"
        "پس از ارسال همه تصاویر، دکمه *«اتمام ارسال تصاویر»* را بفشارید.",
        reply_markup=ReplyKeyboardRemove())
    await state.set_state(Form.ezhhar_images)


@ezhharnameh_router.message(Form.ezhhar_images, F.photo)
async def ezhhar_receive_image(message: Message, state: FSMContext, bot: Bot):
    from text_collector import check_image_limit, MAX_IMAGES_PER_TITLE

    data = await state.get_data()
    images = data.get("ezhhar_images", [])

    # بررسی محدودیت تعداد تصویر
    if not check_image_limit(len(images)):
        await message.reply(
            f"⛔ حداکثر *{MAX_IMAGES_PER_TITLE} تصویر* در هر عنوان مجاز است.\n\n"
            f"اگر مدرک بیشتری دارید، ابتدا دکمه «اتمام ارسال تصاویر» را بزنید\n"
            f"و سپس عنوان جدیدی انتخاب کنید و تصاویر باقیمانده را ارسال نمایید.")
        return

    images.append(message.photo[-1].file_id)
    await state.update_data(ezhhar_images=images)

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
        f"مجموع تصاویر این مدرک: *{len(images)}* از {MAX_IMAGES_PER_TITLE}\n"
        f"({remaining} جای باقیمانده)",
        reply_markup=manage_kb)


@ezhharnameh_router.message(Form.ezhhar_images, F.document)
async def ezhhar_reject_document(message: Message, state: FSMContext):
    await message.answer(
        "⚠️ لطفاً تصاویر را به صورت *عکس (Photo)* ارسال کنید، نه فایل.")


@ezhharnameh_router.message(Form.ezhhar_images, F.text == "🗑 حذف تصویر")
async def ezhhar_ask_delete_image(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    images = data.get("ezhhar_images", [])
    if not images:
        await message.answer("⚠️ لیست تصاویر خالی است.")
        return
    await message.answer("🗑 *حذف تصویر:*\n\nعکس‌های ارسالی:")
    for i, file_id in enumerate(images):
        await bot.send_photo(message.chat.id, photo=file_id, caption=f"تصویر شماره {i + 1}")
    await message.answer(
        "لطفاً *شماره تصویر* برای حذف را ارسال فرمایید:",
        reply_markup=ReplyKeyboardRemove())
    await state.update_data(_ezhhar_deleting_image=True)


@ezhharnameh_router.message(Form.ezhhar_images)
async def ezhhar_images_text(message: Message, state: FSMContext):
    text = message.text or ""
    data = await state.get_data()
    images = data.get("ezhhar_images", [])
    deleting = data.get("_ezhhar_deleting_image", False)

    if deleting:
        num_str = _to_en(text)
        if num_str.isdigit():
            idx = int(num_str) - 1
            if 0 <= idx < len(images):
                images.pop(idx)
                await state.update_data(ezhhar_images=images, _ezhhar_deleting_image=False)
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
            await state.update_data(_ezhhar_deleting_image=False)

    if text == "✅ اتمام ارسال تصاویر":
        if not images:
            # کاربر بدون ارسال تصویر، اتمام را زده — مستقیم به سوال مدرک دیگر برو
            await state.update_data(ezhhar_images=[])
            await message.answer(
                "آیا مدرک دیگری نیز دارید؟",
                reply_markup=ezhhar_attachment_more_kb)
            await state.set_state(Form.ezhhar_attachment_more)
            return

        attachments = data.get("ezhhar_attachments", [])
        title = data.get("_ezhhar_current_att_title", "مستندات")
        attachments.append({"title": title, "images": images})
        await state.update_data(
            ezhhar_attachments=attachments,
            ezhhar_images=[],
            _ezhhar_mandatory_proxy_sent=True
        )

        await message.answer(
            f"✅ مدرک «*{title}*» با *{len(images)} تصویر* ثبت شد.\n\nآیا مدرک دیگری دارید؟",
            reply_markup=ezhhar_attachment_more_kb)
        await state.set_state(Form.ezhhar_attachment_more)
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


@ezhharnameh_router.message(Form.ezhhar_attachment_more)
async def ezhhar_attachment_more_handler(message: Message, state: FSMContext):
    text = message.text or ""
    if text == "➕ بله، عنوان و مدرک دیگر دارم":
        await _ask_ezhhar_attachment(message, state, is_first=False)
        return
    if text == "✅ خیر، ادامه بده":
        await _go_to_ezhhar_preview(message, state)
        return
    if text == "🔙 بازگشت":
        # حذف آخرین مدرک و بازگشت
        data = await state.get_data()
        attachments = data.get("ezhhar_attachments", [])
        if attachments:
            attachments.pop()
            await state.update_data(ezhhar_attachments=attachments)
        await _ask_ezhhar_attachment(message, state, is_first=len(attachments) == 0)
        return
    await message.answer("⚠️ لطفاً یکی از گزینه‌های زیر را انتخاب کنید:", reply_markup=ezhhar_attachment_more_kb)


# ══════════════════════════════════════════════════════════════════════════════
# ساخت پیش‌نمایش اظهارنامه
# ══════════════════════════════════════════════════════════════════════════════
def _escape_md(text: str) -> str:
    """Escape کاراکترهای خاص Markdown برای جلوگیری از خطای پارس تلگرام."""
    for ch in ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']:
        text = text.replace(ch, f'\\{ch}')
    return text


def build_ezhhar_preview(data: dict) -> str:
    declarants = data.get("ezhhar_declarants", [])
    addressees = data.get("ezhhar_addressees", [])
    subject = data.get("ezhhar_subject", "---")
    ezhhar_text = data.get("ezhhar_text", "---")
    attachments = data.get("ezhhar_attachments", [])

    def _person_line(p, idx):
        ptype = p.get("person_type", "")
        nat_id = p.get("national_id", "")
        if ptype == "شخص حقوقی":
            company_id = p.get("company_id", "")
            rep = p.get("representative_type", "")
            return f"  {idx}. {ptype} | شناسه: `{company_id}` | {rep}: `{nat_id}`"
        return f"  {idx}. {ptype} | کدملی: `{nat_id}`"

    declarants_text = "\n".join([_person_line(p, i+1) for i, p in enumerate(declarants)]) or "  (ندارد)"
    addressees_text = "\n".join([_person_line(p, i+1) for i, p in enumerate(addressees)]) or "  (ندارد)"

    text_preview = ezhhar_text[:200] + "..." if len(ezhhar_text) > 200 else ezhhar_text
    text_preview = _escape_md(text_preview)
    subject_escaped = _escape_md(subject)

    att_text = ""
    total_imgs = 0
    for i, att in enumerate(attachments, 1):
        n = len(att.get("images", []))
        total_imgs += n
        att_text += f"  {i}. {_escape_md(att.get('title', 'مستندات'))} — {n} تصویر\n"
    if not att_text:
        att_text = "  (بدون مدرک)\n"

    return (
        f"📋 *پیش‌نمایش اظهارنامه:*\n\n"
        f"👤 اظهارکننده(ها):\n{declarants_text}\n\n"
        f"👥 مخاطب(ها):\n{addressees_text}\n\n"
        f"📌 موضوع: *{subject_escaped}*\n\n"
        f"📄 شرح متن:\n{text_preview}\n\n"
        f"🖼 مدارک ({total_imgs} تصویر در {len(attachments)} عنوان):\n{att_text}\n"
        f"آیا اطلاعات فوق صحیح است؟"
    )


async def _go_to_ezhhar_preview(message: Message, state: FSMContext):
    data = await state.get_data()
    preview = build_ezhhar_preview(data)
    try:
        await message.answer(preview, reply_markup=ezhhar_confirm_kb)
    except Exception:
        # fallback: ارسال بدون Markdown اگر پارس خطا داد
        await message.answer(preview, reply_markup=ezhhar_confirm_kb)
    await state.set_state(Form.ezhhar_confirm)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۶ — تایید یا ویرایش
# ══════════════════════════════════════════════════════════════════════════════
@ezhharnameh_router.message(Form.ezhhar_confirm)
async def ezhhar_confirm_handler(message: Message, state: FSMContext, bot: Bot):
    text = message.text or ""

    if text == "✅ تایید و شروع ثبت":
        data = await state.get_data()
        user_id = message.from_user.id

        await message.answer(
            "⏳ *درخواست اظهارنامه تایید شد.*\n\nدر حال ارسال به صف پردازش...",
            reply_markup=ReplyKeyboardRemove())

        await runtime_state.job_queue.put({
            "user_id": user_id,
            "query_type": "اظهارنامه_ثبت",
            "task_type": "EZHHARNAMEH_SUBMIT",
            "ezhhar_declarants": data.get("ezhhar_declarants", []),
            "ezhhar_addressees": data.get("ezhhar_addressees", []),
            "ezhhar_subject": data.get("ezhhar_subject", "سایر"),
            "ezhhar_text": data.get("ezhhar_text", ""),
            "ezhhar_text_html": data.get("ezhhar_text_html", ""),
            "ezhhar_attachments": data.get("ezhhar_attachments", []),
        })

        await state.clear()
        return

    if text == "✏️ ویرایش اطلاعات":
        await message.answer(
            "✏️ *ویرایش اطلاعات:*\n\nکدام بخش را می‌خواهید ویرایش کنید؟",
            reply_markup=ezhhar_edit_kb)
        await state.set_state(Form.ezhhar_edit_choice)
        return

    await message.answer("⚠️ لطفاً یکی از گزینه‌های زیر را انتخاب کنید:", reply_markup=ezhhar_confirm_kb)


# ══════════════════════════════════════════════════════════════════════════════
# منوی ویرایش
# ══════════════════════════════════════════════════════════════════════════════
@ezhharnameh_router.message(Form.ezhhar_edit_choice)
async def ezhhar_edit_choice_handler(message: Message, state: FSMContext):
    text = message.text or ""

    if text == "🔙 بازگشت به پیش‌نمایش":
        await _go_to_ezhhar_preview(message, state)
        return

    if text == "👤 ویرایش اظهارکننده(ها)":
        await state.update_data(ezhhar_declarants=[], _ezhhar_current_declarant={})
        await message.answer(
            "👤 لیست اظهارکنندگان پاک شد.\nلطفاً مجدداً *نوع شخصیت اظهارکننده* را انتخاب فرمایید:",
            reply_markup=create_ezhhar_declarant_person_type_kb()
        )
        await state.set_state(Form.ezhhar_declarant_person_type)
        return

    if text == "👥 ویرایش مخاطب(ها)":
        await state.update_data(ezhhar_addressees=[], _ezhhar_current_addressee={})
        await message.answer(
            "👥 لیست مخاطبین پاک شد.\nلطفاً مجدداً *نوع شخصیت مخاطب* را انتخاب فرمایید:",
            reply_markup=create_ezhhar_addressee_person_type_kb()
        )
        await state.set_state(Form.ezhhar_addressee_person_type)
        return

    if text == "📌 ویرایش عنوان اظهارنامه":
        await message.answer(
            "📌 لطفاً عنوان جدید اظهارنامه را وارد کنید:",
            reply_markup=ezhhar_subject_kb
        )
        await state.set_state(Form.ezhhar_subject)
        return

    if text == "📄 ویرایش شرح متن":
        await message.answer("📄 لطفاً متن جدید را ارسال فرمایید:", reply_markup=ReplyKeyboardRemove())
        await state.set_state(Form.ezhhar_text)
        return

    if text == "🖼 ویرایش مدارک":
        await state.update_data(ezhhar_attachments=[], _ezhhar_mandatory_proxy_sent=False)
        await message.answer("🖼 مدارک قبلی پاک شدند.")
        data = await state.get_data()
        declarants = data.get("ezhhar_declarants", [])
        has_legal = any(p.get("person_type") == "شخص حقوقی" for p in declarants)
        if has_legal:
            await message.answer(
                "⚠️ چون اظهارکننده شخص *حقوقی* دارید، ارسال *مدرک نمایندگی اجباری* است.\n\n"
                "لطفاً ابتدا عنوان مدرک نمایندگی را وارد کنید:",
                reply_markup=ReplyKeyboardRemove())
            await state.set_state(Form.ezhhar_attachment_title)
        else:
            await _ask_ezhhar_attachment(message, state, is_first=True)
        return

    await message.answer("⚠️ لطفاً یکی از گزینه‌های موجود را انتخاب کنید:", reply_markup=ezhhar_edit_kb)


# ══════════════════════════════════════════════════════════════════════════════
# دریافت تصاویر مدرک نمایندگی (برای شخص حقوقی)
# ══════════════════════════════════════════════════════════════════════════════
@ezhharnameh_router.message(Form.ezhhar_attachment_images, F.photo)
async def ezhhar_receive_proxy_image(message: Message, state: FSMContext, bot: Bot):
    """دریافت تصاویر مدرک نمایندگی"""
    from text_collector import check_image_limit, MAX_IMAGES_PER_TITLE

    data = await state.get_data()
    images = data.get("ezhhar_images", [])

    # بررسی محدودیت تعداد تصویر
    if not check_image_limit(len(images)):
        await message.reply(
            f"⛔ حداکثر *{MAX_IMAGES_PER_TITLE} تصویر* در هر عنوان مجاز است.\n\n"
            f"اگر مدرک بیشتری دارید، ابتدا دکمه «اتمام ارسال تصاویر» را بزنید\n"
            f"و سپس عنوان جدیدی انتخاب کنید.")
        return

    file_id = message.photo[-1].file_id
    images.append(file_id)
    await state.update_data(ezhhar_images=images)

    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    manage_kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ اتمام ارسال تصاویر")],
            [KeyboardButton(text="➕ افزودن مدرک دیگر")],
            [KeyboardButton(text="🗑 حذف تصویر")]
        ],
        resize_keyboard=True
    )
    await message.reply(
        f"✅ تصویر شماره *{len(images)}* دریافت شد.\\n"
        f"مجموع تصاویر مدرک نمایندگی: *{len(images)} تصویر*\\n\\n"
        "می‌توانید تصاویر بیشتری ارسال کنید یا یکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=manage_kb)


@ezhharnameh_router.message(Form.ezhhar_attachment_images, F.text == "✅ اتمام ارسال تصاویر")
async def ezhhar_finish_proxy_images(message: Message, state: FSMContext):
    """اتمام ارسال تصاویر مدرک نمایندگی"""
    data = await state.get_data()
    images = data.get("ezhhar_images", [])
    
    if not images:
        await message.answer("⚠️ حداقل یک تصویر باید ارسال کنید.")
        return

    title = data.get("_ezhhar_current_attachment_title", "مدرک نمایندگی")
    attachments = data.get("ezhhar_attachments", [])
    attachments.append({"title": title, "images": images})
    
    await state.update_data(
        ezhhar_attachments=attachments,
        _ezhhar_mandatory_proxy_sent=True,
        ezhhar_images=[]
    )

    await message.answer(
        f"✅ مدرک *{title}* با *{len(images)} تصویر* ثبت شد.\\n\\n"
        "آیا مدرک دیگری نیز می‌خواهید ارسال کنید؟",
        reply_markup=lavayeh_attachment_more_kb)
    await state.set_state(Form.ezhhar_attachment_more)


@ezhharnameh_router.message(Form.ezhhar_attachment_images, F.text == "➕ افزودن مدرک دیگر")
async def ezhhar_add_more_after_proxy(message: Message, state: FSMContext):
    """افزودن مدرک دیگر بعد از مدرک نمایندگی"""
    data = await state.get_data()
    images = data.get("ezhhar_images", [])
    
    if not images:
        await message.answer("⚠️ حداقل یک تصویر باید برای مدرک نمایندگی ارسال کنید.")
        return

    title = data.get("_ezhhar_current_attachment_title", "مدرک نمایندگی")
    attachments = data.get("ezhhar_attachments", [])
    attachments.append({"title": title, "images": images})
    
    await state.update_data(
        ezhhar_attachments=attachments,
        _ezhhar_mandatory_proxy_sent=True,
        ezhhar_images=[]
    )

    await _ask_ezhhar_attachment(message, state, is_first=False)


@ezhharnameh_router.message(Form.ezhhar_attachment_images, F.text == "🗑 حذف تصویر")
async def ezhhar_proxy_delete_image(message: Message, state: FSMContext, bot: Bot):
    """حذف تصویر از مدرک نمایندگی"""
    data = await state.get_data()
    images = data.get("ezhhar_images", [])
    if not images:
        await message.answer("⚠️ لیست تصاویر خالی است.")
        return
    await message.answer("🗑 *حذف تصویر:*\\n\\nعکس‌های ارسالی:")
    for i, file_id in enumerate(images):
        await bot.send_photo(message.chat.id, photo=file_id, caption=f"تصویر شماره {i + 1}")
    await message.answer(
        "لطفاً *شماره تصویر* برای حذف را ارسال فرمایید:",
        reply_markup=ReplyKeyboardRemove())
    await state.update_data(_ezhhar_deleting_proxy_image=True)


@ezhharnameh_router.message(Form.ezhhar_attachment_images)
async def ezhhar_proxy_images_text(message: Message, state: FSMContext):
    """پردازش متن در حالت مدرک نمایندگی"""
    text = message.text or ""
    data = await state.get_data()
    images = data.get("ezhhar_images", [])
    deleting = data.get("_ezhhar_deleting_proxy_image", False)

    if deleting:
        num_str = _to_en(text)
        if num_str.isdigit():
            idx = int(num_str) - 1
            if 0 <= idx < len(images):
                images.pop(idx)
                await state.update_data(ezhhar_images=images, _ezhhar_deleting_proxy_image=False)
                from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
                if images:
                    manage_kb = ReplyKeyboardMarkup(
                        keyboard=[
                            [KeyboardButton(text="✅ اتمام ارسال تصاویر")],
                            [KeyboardButton(text="➕ افزودن مدرک دیگر")],
                            [KeyboardButton(text="🗑 حذف تصویر")]
                        ],
                        resize_keyboard=True
                    )
                    await message.answer(
                        f"✅ تصویر شماره *{idx + 1}* حذف شد.\\n"
                        f"تعداد تصاویر باقی‌مانده: *{len(images)} تصویر*",
                        reply_markup=manage_kb)
                else:
                    await message.answer(
                        "⚠️ همه تصاویر حذف شدند. لطفاً دوباره تصویر ارسال کنید:",
                        reply_markup=ReplyKeyboardRemove()
                    )
            else:
                await message.answer("⚠️ شماره نامعتبر.")
        else:
            await message.answer("⚠️ لطفاً فقط عدد ارسال کنید.")
    else:
        await message.answer("⚠️ لطفاً تصویر ارسال کنید یا یکی از گزینه‌های موجود را انتخاب کنید.")


# ══════════════════════════════════════════════════════════════════════════════
# هندلرهای خطای استعلام ثنا — ویرایش شناسه ملی یا حذف درخواست
# ══════════════════════════════════════════════════════════════════════════════

@ezhharnameh_router.callback_query(F.data.startswith("ezhhar_fix_nid:"))
async def ezhhar_fix_national_id_callback(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """کاربر گزینه «ویرایش شناسه ملی» را انتخاب کرده"""
    parts = callback.data.split(":")
    target_user_id = int(parts[1])

    if callback.from_user.id != target_user_id:
        await callback.answer("⚠️ این دکمه مربوط به شما نیست.")
        return

    pending = runtime_state.pending_ezhhar_sana_fix.get(target_user_id)
    if not pending:
        await callback.answer("⚠️ درخواستی برای ویرایش یافت نشد. ممکن است منقضی شده باشد.")
        return

    await callback.answer()

    # ویرایش پیام اصلی
    try:
        await callback.message.edit_text(
            callback.message.text + "\n\n✏️ _در انتظار شناسه ملی جدید..._")
    except Exception:
        pass

    await bot.send_message(
        target_user_id,
        "🔢 لطفاً *شناسه ملی صحیح* را ارسال فرمایید:\n_(۱۰ رقمی)_\n\n"
        "⚠️ اطلاعات قبلی اظهارنامه حفظ شده و فقط شناسه ملی اصلاح خواهد شد.",
        reply_markup=back_only_kb)
    await state.set_state(Form.ezhhar_sana_error_new_national_id)


@ezhharnameh_router.callback_query(F.data.startswith("ezhhar_del_req:"))
async def ezhhar_delete_request_callback(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """کاربر گزینه «حذف درخواست» را انتخاب کرده"""
    parts = callback.data.split(":")
    target_user_id = int(parts[1])

    if callback.from_user.id != target_user_id:
        await callback.answer("⚠️ این دکمه مربوط به شما نیست.")
        return

    # حذف از pending
    runtime_state.pending_ezhhar_sana_fix.pop(target_user_id, None)
    await callback.answer("درخواست حذف شد.")

    try:
        await callback.message.edit_text(
            callback.message.text + "\n\n🗑 _درخواست حذف شد._")
    except Exception:
        pass

    await bot.send_message(
        target_user_id,
        "🗑 *درخواست اظهارنامه حذف شد.*\n\n"
        "در صورت نیاز، از منوی اصلی مجدداً اقدام فرمایید.",
        reply_markup=restart_kb)
    await state.clear()


@ezhharnameh_router.message(Form.ezhhar_sana_error_new_national_id)
async def ezhhar_receive_new_national_id(message: Message, state: FSMContext, bot: Bot):
    """دریافت شناسه ملی جدید از کاربر و ادامه فرآیند ثبت اظهارنامه"""
    if not message.text:
        return

    if message.text == "🔙 بازگشت":
        # بازگشت — نمایش مجدد گزینه‌ها
        pending = runtime_state.pending_ezhhar_sana_fix.get(message.from_user.id)
        if not pending:
            await message.answer(
                "⚠️ درخواست اظهارنامه منقضی شده است. لطفاً مجدداً اقدام فرمایید.",
                reply_markup=restart_kb
            )
            await state.clear()
            return

        task_data = pending["task_data"]
        old_nid = task_data.get("_sana_error_national_id", "")
        person_role = task_data.get("_sana_error_person_role", "")
        role_label = "اظهارکننده" if person_role == "declarant" else "مخاطب"

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✏️ ویرایش شناسه ملی", callback_data=f"ezhhar_fix_nid:{message.from_user.id}")],
            [InlineKeyboardButton(text="🗑 حذف درخواست", callback_data=f"ezhhar_del_req:{message.from_user.id}")],
        ])
        await message.answer(
            f"⚠️ شناسه ملی `{old_nid}` ({role_label}) ثبت‌نام ثنا ندارد یا اشتباه است.\n\n"
            "لطفاً یکی از گزینه‌های زیر را انتخاب کنید:",
            reply_markup=kb)
        return

    nat_id = _to_en(message.text)
    if not re.match(r"^[0-9]{10}$", nat_id):
        await message.answer("⚠️ شناسه ملی باید *۱۰ رقمی* باشد:")
        return

    pending = runtime_state.pending_ezhhar_sana_fix.pop(message.from_user.id, None)
    if not pending:
        await message.answer(
            "⚠️ درخواست اظهارنامه منقضی شده است. لطفاً مجدداً اقدام فرمایید.",
            reply_markup=restart_kb
        )
        await state.clear()
        return

    task_data = pending["task_data"]
    person_role = task_data.get("_sana_error_person_role", "")
    person_index = task_data.get("_sana_error_person_index", 0)

    # جایگزینی شناسه ملی در اطلاعات تسک
    if person_role == "declarant":
        declarants = task_data.get("ezhhar_declarants", [])
        if person_index < len(declarants):
            declarants[person_index]["national_id"] = nat_id
            task_data["ezhhar_declarants"] = declarants
    elif person_role == "addressee":
        addressees = task_data.get("ezhhar_addressees", [])
        if person_index < len(addressees):
            addressees[person_index]["national_id"] = nat_id
            task_data["ezhhar_addressees"] = addressees

    # پاکسازی فیلدهای داخلی خطا
    task_data.pop("_sana_error_national_id", None)
    task_data.pop("_sana_error_person_role", None)
    task_data.pop("_sana_error_person_index", None)

    await message.answer(
        f"✅ شناسه ملی به `{nat_id}` تغییر یافت.\n\n"
        "⏳ در حال ارسال مجدد درخواست اظهارنامه به صف پردازش...",
        reply_markup=restart_kb)

    # ارسال مجدد تسک به صف
    await runtime_state.job_queue.put(task_data)
    await state.clear()
