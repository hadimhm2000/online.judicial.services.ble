"""
هندلرهای بخش اعلام وکالت — فلوی مکالمه تلگرام.

جریان:
  ۱. ورود به بخش اعلام وکالت
  ۲. دریافت کدملی وکیل(ها)
  ۳. دریافت شماره(های) قرارداد وکالت (۱۶ رقمی)
  ۴. دریافت مقدار تمبر (عدد / محاسبه / بدون تمبر)
  ۵. دریافت متن لایحه
  ۶. دریافت تصاویر مدارک (اختیاری)
  ۷. تایید نهایی و ارسال به صف
"""
import asyncio
import datetime
import logging
import re

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove

import runtime_state
from config import ADMIN_ID, CARD_NUMBER, ACCOUNT_NAME
from sheets import log_event
from states import Form
from keyboards import (
    main_menu_kb, restart_kb, back_only_kb, text_input_method_kb,
    ealam_more_lawyers_kb,
    ealam_more_contracts_kb,
    ealam_stamp_amount_kb,
    ealam_claim_type_kb,
    ealam_stamp_type_kb,
    continue_kb,
    ealam_confirm_kb,
    lavayeh_attachment_title_kb_first,
    lavayeh_attachment_title_kb,
    lavayeh_attachment_more_kb,
    create_province_kb, PROVINCES)
from stamp_duty import calculate_stamp_duty, format_result_fa

ealam_router = Router()

_FA_AR = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789"
)

def _to_en(text: str) -> str:
    return text.translate(_FA_AR).replace(" ", "").strip()

def _fmt(n: int) -> str:
    """قالب‌بندی عدد با جداساز هزار"""
    return f"{n:,}"


# ══════════════════════════════════════════════════════════════════════════════
# ورود به بخش اعلام وکالت
# ══════════════════════════════════════════════════════════════════════════════
@ealam_router.message(StateFilter("*"), F.text == "⚖️ اعلام وکالت")
async def ealam_vakalaht_entry(message: Message, state: FSMContext):
    await state.clear()
    await state.update_data(
        ealam_lawyers=[],
        ealam_contracts=[],
        ealam_stamp_amount=0,
        ealam_stamp_type="",
        ealam_attachments=[])
    await message.answer(
        "⚖️ *ثبت اعلام وکالت*\n\n"
        "🔢 لطفاً *کد ملی وکیل* را وارد فرمایید:\n_(۱۰ رقمی)_",
        reply_markup=ReplyKeyboardRemove())
    await state.set_state(Form.ealam_vakalaht_national_id)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۱ — دریافت کدملی وکیل
# ══════════════════════════════════════════════════════════════════════════════
@ealam_router.message(Form.ealam_vakalaht_national_id)
async def ealam_get_national_id(message: Message, state: FSMContext):
    if not message.text:
        return

    nat_id = _to_en(message.text)
    if not re.match(r"^[0-9]{10}$", nat_id):
        await message.answer("⚠️ کد ملی باید *۱۰ رقمی* باشد:")
        return

    data = await state.get_data()
    lawyers = data.get("ealam_lawyers", [])
    lawyers.append(nat_id)
    await state.update_data(ealam_lawyers=lawyers)

    await message.answer(
        f"✅ کد ملی `{nat_id}` ثبت شد.\n\n"
        f"آیا *وکیل دیگری* نیز در این پرونده وکالت دارد؟",
        reply_markup=ealam_more_lawyers_kb)
    await state.set_state(Form.ealam_vakalaht_more_lawyers)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۲ — آیا وکیل دیگری هم هست؟
# ══════════════════════════════════════════════════════════════════════════════
@ealam_router.message(Form.ealam_vakalaht_more_lawyers)
async def ealam_more_lawyers(message: Message, state: FSMContext):
    text = message.text or ""

    if text == "➕ بله، وکیل دیگری هم هست":
        await message.answer(
            "🔢 لطفاً *کد ملی وکیل بعدی* را وارد فرمایید:\n_(۱۰ رقمی)_",
            reply_markup=ReplyKeyboardRemove())
        await state.set_state(Form.ealam_vakalaht_national_id)
        return

    if text == "✅ خیر، ادامه مراحل":
        await message.answer(
            "🔢 لطفاً *شماره قرارداد وکالت* را وارد فرمایید:\n"
            "_(باید دقیقاً ۱۶ رقمی باشد)_",
            reply_markup=ReplyKeyboardRemove())
        await state.set_state(Form.ealam_vakalaht_contract_number)
        return

    await message.answer("⚠️ لطفاً یکی از گزینه‌های زیر را انتخاب کنید:", reply_markup=ealam_more_lawyers_kb)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۳ — دریافت شماره قرارداد وکالت
# ══════════════════════════════════════════════════════════════════════════════
@ealam_router.message(Form.ealam_vakalaht_contract_number)
async def ealam_get_contract_number(message: Message, state: FSMContext):
    if not message.text:
        return

    contract = _to_en(message.text)
    if not contract.isdigit() or len(contract) != 16:
        await message.answer(
            "⚠️ شماره قرارداد وکالت باید *دقیقاً ۱۶ رقمی* باشد.\n"
            f"شماره وارد شده *{len(contract)} رقمی* است. مجدداً وارد کنید:")
        return

    data = await state.get_data()
    contracts = data.get("ealam_contracts", [])
    contracts.append(contract)
    await state.update_data(ealam_contracts=contracts)

    await message.answer(
        f"✅ شماره قرارداد `{contract}` ثبت شد.\n\n"
        "آیا *شماره قرارداد دیگری* نیز وجود دارد؟",
        reply_markup=ealam_more_contracts_kb)
    await state.set_state(Form.ealam_vakalaht_more_contracts)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۳-ب — آیا شماره قرارداد دیگری هم هست؟
# ══════════════════════════════════════════════════════════════════════════════
@ealam_router.message(Form.ealam_vakalaht_more_contracts)
async def ealam_more_contracts(message: Message, state: FSMContext):
    text = message.text or ""

    if text == "➕ افزودن شماره قرارداد دیگر":
        await message.answer(
            "🔢 لطفاً *شماره قرارداد بعدی* را وارد فرمایید:\n_(۱۶ رقمی)_",
            reply_markup=ReplyKeyboardRemove())
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


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۴ — دریافت مقدار تمبر
# ══════════════════════════════════════════════════════════════════════════════
@ealam_router.message(Form.ealam_vakalaht_stamp_amount)
async def ealam_get_stamp_amount(message: Message, state: FSMContext):
    text = (message.text or "").strip()

    if text == "🚫 نیاز به ابطال تمبر ندارد":
        await state.update_data(ealam_stamp_amount=0, ealam_stamp_type="بدون تمبر")
        await _ask_lavayeh_text(message, state)
        return

    if text == "❓ نمیدانم، نیاز به محاسبه دارم":
        await message.answer(
            "🔍 *محاسبه تمبر:*\n\n"
            "لطفاً گزینه‌های زیر را انتخاب کنید.\n"
            "⚠️ اگر گزینه‌های زیر کمکی به شما نکرد، گزینه «عدم نیاز به تمبر» "
            "را انتخاب کنید و بعداً در شعبه می‌توانید تمبر را انتخاب کنید.",
            reply_markup=ealam_claim_type_kb)
        await state.set_state(Form.ealam_vakalaht_claim_type)
        return

    # کاربر عدد وارد کرده
    amount_str = _to_en(text)
    if not amount_str.isdigit() or int(amount_str) <= 0:
        await message.answer(
            "⚠️ لطفاً مقدار تمبر را به *ریال* وارد کنید یا از گزینه‌های زیر استفاده کنید:",
            reply_markup=ealam_stamp_amount_kb)
        return

    stamp_amount = int(amount_str)
    await state.update_data(ealam_stamp_amount=stamp_amount, ealam_stamp_type="مشخص")
    await message.answer(
        f"✅ مقدار تمبر *{_fmt(stamp_amount)} ریال* ثبت شد.")
    await _ask_lavayeh_text(message, state)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۴-ب — انتخاب نوع دعوی برای محاسبه تمبر
# ══════════════════════════════════════════════════════════════════════════════
@ealam_router.message(Form.ealam_vakalaht_claim_type)
async def ealam_get_claim_type(message: Message, state: FSMContext):
    text = message.text or ""

    if "3️⃣" in text or "عدم نیاز" in text:
        await state.update_data(ealam_stamp_amount=0, ealam_stamp_type="بدون تمبر")
        await _ask_lavayeh_text(message, state)
        return

    if "2️⃣" in text or "غیر مالی" in text:
        stamp_amount = 200_000
        await state.update_data(ealam_stamp_amount=stamp_amount, ealam_stamp_type="غیر مالی")
        await message.answer(
            f"💰 *مبلغ تمبر دعوی غیر مالی:*\n\n"
            f"مبلغ *{_fmt(stamp_amount)} ریال* تمبر ابطال می‌گردد.",
            reply_markup=continue_kb)
        await state.set_state(Form.ealam_vakalaht_text)
        return

    if "1️⃣" in text or "مالی" in text:
        await message.answer(
            "💵 لطفاً *مبلغ خواسته* را به *ریال* وارد فرمایید:\n_(فقط عدد)_",
            reply_markup=ReplyKeyboardRemove())
        await state.set_state(Form.ealam_vakalaht_claim_amount)
        return

    await message.answer("⚠️ لطفاً یکی از گزینه‌های موجود را انتخاب کنید:", reply_markup=ealam_claim_type_kb)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۴-ج — مبلغ خواسته برای دعوی مالی
# ══════════════════════════════════════════════════════════════════════════════
@ealam_router.message(Form.ealam_vakalaht_claim_amount)
async def ealam_get_claim_amount(message: Message, state: FSMContext):
    if not message.text:
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
    await state.update_data(
        ealam_claim_amount=claim_amount,
        ealam_stamp_result=result)

    await message.answer(
        f"📊 *نتیجه محاسبه تمبر:*\n\n{result_text}\n\n"
        "لطفاً انتخاب کنید که *کدام نوع تمبر* در پرونده قرار داده شود:",
        reply_markup=ealam_stamp_type_kb)
    await state.set_state(Form.ealam_vakalaht_stamp_type)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۴-د — انتخاب نوع تمبر
# ══════════════════════════════════════════════════════════════════════════════
@ealam_router.message(Form.ealam_vakalaht_stamp_type)
async def ealam_get_stamp_type(message: Message, state: FSMContext):
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
    else:
        await message.answer("⚠️ لطفاً یکی از گزینه‌های موجود را انتخاب کنید:", reply_markup=ealam_stamp_type_kb)
        return

    await state.update_data(ealam_stamp_amount=stamp_amount, ealam_stamp_type=stamp_type)
    await message.answer(
        f"✅ *تمبر {stamp_type}* به مبلغ *{_fmt(stamp_amount)} ریال* انتخاب شد.")
    await _ask_lavayeh_text(message, state)


async def _ask_lavayeh_text(message: Message, state: FSMContext):
    """پرسیدن روش ورود متن لایحه (تایپ مستقیم / فایل ورد)"""
    await message.answer(
        "📄 *شرح متن لایحه اعلام وکالت:*\n\n"
        "لطفاً روش ورود متن را انتخاب فرمایید.\n"
        "⚠️ *توجه:* متن پس از ارسال قابل ویرایش نمی‌باشد.",
        reply_markup=text_input_method_kb)
    await state.set_state(Form.ealam_vakalaht_text_choice)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۵ — انتخاب روش ورود متن لایحه (تایپ مستقیم / فایل ورد)
# ══════════════════════════════════════════════════════════════════════════════
@ealam_router.message(Form.ealam_vakalaht_text_choice)
async def ealam_text_choice_handler(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if text == "⌨️ تایپ مستقیم متن":
        await message.answer(
            "📝 لطفاً *متن لایحه اعلام وکالت* را ارسال فرمایید:",
            reply_markup=back_only_kb)
        await state.set_state(Form.ealam_vakalaht_text)
        return
    if text == "📎 ارسال فایل ورد (.docx)":
        await message.answer(
            "📎 لطفاً *فایل ورد (.docx)* را ارسال فرمایید:\n\n"
            "💡 متن داخل فایل عیناً (با حفظ فرمت بولد و ...) در سامانه درج خواهد شد.",
            reply_markup=back_only_kb)
        await state.set_state(Form.ealam_vakalaht_text)
        return
    if text == "🔙 بازگشت":
        data = await state.get_data()
        stamp_type = data.get("ealam_stamp_type", "")
        if stamp_type == "غیر مالی":
            await message.answer(
                "💰 *مبلغ تمبر دعوی غیر مالی:*\n\nبرای ادامه، دکمه زیر را بزنید:",
                reply_markup=continue_kb)
            await state.set_state(Form.ealam_vakalaht_text)
        else:
            await message.answer(
                "🏷 لطفاً انتخاب کنید که *کدام نوع تمبر* در پرونده قرار داده شود:",
                reply_markup=ealam_stamp_type_kb)
            await state.set_state(Form.ealam_vakalaht_stamp_type)
        return
    await message.answer(
        "⚠️ لطفاً یکی از گزینه‌های موجود را انتخاب فرمایید:",
        reply_markup=text_input_method_kb)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۵ — متن لایحه + شروع بخش پیوست‌ها
# ══════════════════════════════════════════════════════════════════════════════
@ealam_router.message(Form.ealam_vakalaht_text)
async def ealam_get_text(message: Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    chat_id = message.chat.id

    # ── پشتیبانی فایل ورد ──────────────────────────────────────
    if message.document and message.document.file_name and message.document.file_name.lower().endswith(".docx"):
        from text_collector import process_docx_input

        async def _on_ealam_docx_complete(final_text, final_html, st, b, cid, was_editing, char_count):
            await st.update_data(ealam_lavayeh_text=final_text, ealam_lavayeh_text_html=final_html, ealam_attachments=[])
            await b.send_message(cid, f"✅ متن اعلام وکالت از فایل ورد دریافت شد ({char_count} کاراکتر).")
            await _ask_attachment(message, st, is_first=True)

        await process_docx_input(
            message=message,
            user_id=user_id,
            chat_id=chat_id,
            state=state,
            bot=bot,
            on_complete=_on_ealam_docx_complete,
            text_state_key="ealam_lavayeh_text",
            html_state_key="ealam_lavayeh_text_html",
            extra_state_updates={"ealam_attachments": []},
            processing_msg="⏳ در حال پردازش فایل ورد...")
        return

    text = message.text or ""

    # دکمه «ادامه مراحل» برای دعوی غیر مالی
    if text == "✅ ادامه مراحل":
        await _ask_attachment(message, state, is_first=True)
        return

    if text.strip() == "🔙 بازگشت":
        await _ask_lavayeh_text(message, state)
        return

    if not text:
        await message.answer("⚠️ لطفاً متن لایحه را به صورت متن ارسال فرمایید.\nیا فایل .docx ارسال نمایید.")
        return

    from text_collector import collect_text_part

    async def _on_ealam_text_complete(final_text, st, b, cid, was_editing):
        await st.update_data(ealam_lavayeh_text=final_text, ealam_lavayeh_text_html="", ealam_attachments=[])
        await b.send_message(
            cid,
            f"✅ متن اعلام وکالت دریافت شد ({len(final_text)} کاراکتر).")
        await _ask_attachment(message, st, is_first=True)

    await collect_text_part(
        user_id=user_id,
        chat_id=chat_id,
        text=text,
        state=state,
        bot=bot,
        on_complete=_on_ealam_text_complete,
        first_part_reply="⏳ در حال دریافت متن اعلام وکالت...")


async def _ask_attachment(message: Message, state: FSMContext, is_first: bool):
    await state.update_data(ealam_images=[])
    kb = lavayeh_attachment_title_kb_first if is_first else lavayeh_attachment_title_kb
    await message.answer(
        "📄 *عنوان مدرک:*\n\n"
        "اگر تصویر مدارک دارید، عنوان آن را تایپ کنید یا از دکمه زیر استفاده کنید.\n"
        "اگر مدرکی ندارید، گزینه «رد کردن» را انتخاب کنید:",
        reply_markup=kb)
    await state.set_state(Form.ealam_vakalaht_attachment_title)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۶ — عنوان پیوست
# ══════════════════════════════════════════════════════════════════════════════
@ealam_router.message(Form.ealam_vakalaht_attachment_title)
async def ealam_get_attachment_title(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        await message.answer("⚠️ لطفاً عنوان را به صورت متن ارسال فرمایید.")
        return

    data = await state.get_data()
    attachments = data.get("ealam_attachments", [])

    if text == "⏭ رد کردن (بدون مدرک)" and not attachments:
        await state.update_data(ealam_attachments=[])
        await _go_to_preview(message, state)
        return

    title = "مستندات" if text == "🔹 عنوان مهم نیست (صرفا درج شود مستندات)" else text
    await state.update_data(_ealam_current_att_title=title)

    await message.answer(
        f"✅ عنوان «*{title}*» ثبت شد.\n\n"
        "🖼 لطفاً تصاویر را به صورت *عکس (Photo)* ارسال فرمایید.\n"
        "پس از ارسال همه، دکمه *«اتمام ارسال»* را بزنید.",
        reply_markup=ReplyKeyboardRemove())
    await state.set_state(Form.ealam_vakalaht_images)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۶-ب — دریافت تصاویر
# ══════════════════════════════════════════════════════════════════════════════
@ealam_router.message(Form.ealam_vakalaht_images, F.photo)
async def ealam_receive_image(message: Message, state: FSMContext, bot: Bot):
    from text_collector import check_image_limit, MAX_IMAGES_PER_TITLE

    data = await state.get_data()
    images = data.get("ealam_images", [])

    # بررسی محدودیت تعداد تصویر
    if not check_image_limit(len(images)):
        await message.reply(
            f"⛔ حداکثر *{MAX_IMAGES_PER_TITLE} تصویر* در هر عنوان مجاز است.\n\n"
            f"اگر مدرک بیشتری دارید، ابتدا دکمه «اتمام ارسال تصاویر» را بزنید\n"
            f"و سپس عنوان جدیدی انتخاب کنید و تصاویر باقیمانده را ارسال نمایید.")
        return

    images.append(message.photo[-1].file_id)
    await state.update_data(ealam_images=images)

    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ اتمام ارسال تصاویر")],
            [KeyboardButton(text="🗑 حذف تصویر")]
        ],
        resize_keyboard=True
    )
    remaining = MAX_IMAGES_PER_TITLE - len(images)
    await message.reply(
        f"✅ تصویر شماره *{len(images)}* دریافت شد. مجموع: *{len(images)}* از {MAX_IMAGES_PER_TITLE} ({remaining} جای باقیمانده)",
        reply_markup=kb)


@ealam_router.message(Form.ealam_vakalaht_images, F.text == "✅ اتمام ارسال تصاویر")
async def ealam_finish_images(message: Message, state: FSMContext):
    data = await state.get_data()
    images = data.get("ealam_images", [])

    if not images:
        await message.answer("⚠️ حداقل یک تصویر ارسال کنید.")
        return

    attachments = data.get("ealam_attachments", [])
    title = data.get("_ealam_current_att_title", "مستندات")
    attachments.append({"title": title, "images": images})
    await state.update_data(ealam_attachments=attachments, ealam_images=[])

    await message.answer(
        f"✅ مدرک «*{title}*» با *{len(images)} تصویر* ثبت شد.\n\nآیا مدرک دیگری دارید؟",
        reply_markup=lavayeh_attachment_more_kb)
    await state.set_state(Form.ealam_vakalaht_attachment_more)


@ealam_router.message(Form.ealam_vakalaht_images)
async def ealam_images_text(message: Message, state: FSMContext):
    text = message.text or ""
    data = await state.get_data()
    images = data.get("ealam_images", [])

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
        kb = ReplyKeyboardRemove()
    await message.answer("⚠️ لطفاً تصویر مدرک را ارسال کنید:", reply_markup=kb)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۶-ج — آیا مدرک دیگری هم هست؟
# ══════════════════════════════════════════════════════════════════════════════
@ealam_router.message(Form.ealam_vakalaht_attachment_more)
async def ealam_attachment_more(message: Message, state: FSMContext):
    text = message.text or ""

    if text == "➕ بله، عنوان و مدرک دیگر دارم":
        await _ask_attachment(message, state, is_first=False)
        return

    if text == "✅ خیر، ادامه بده":
        await _go_to_preview(message, state)
        return

    await message.answer("⚠️ لطفاً یکی از گزینه‌های زیر را انتخاب کنید:", reply_markup=lavayeh_attachment_more_kb)


# ══════════════════════════════════════════════════════════════════════════════
# ساخت پیش‌نمایش
# ══════════════════════════════════════════════════════════════════════════════
def build_ealam_preview(data: dict) -> str:
    lawyers = data.get("ealam_lawyers", [])
    contracts = data.get("ealam_contracts", [])
    stamp_amount = data.get("ealam_stamp_amount", 0)
    stamp_type = data.get("ealam_stamp_type", "")
    lavayeh_text = data.get("ealam_lavayeh_text", "")
    attachments = data.get("ealam_attachments", [])

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

    return (
        f"📋 *پیش‌نمایش اعلام وکالت:*\n\n"
        f"👤 وکیل(ها):\n{lawyers_text}\n\n"
        f"📑 شماره(های) قرارداد:\n{contracts_text}\n\n"
        f"💰 تمبر: *{stamp_text}*\n\n"
        f"📄 متن لایحه:\n{text_preview}\n\n"
        f"🖼 مدارک ({total_imgs} تصویر):\n{att_text}\n"
        f"آیا اطلاعات فوق صحیح است؟"
    )


async def _go_to_preview(message: Message, state: FSMContext):
    data = await state.get_data()
    preview = build_ealam_preview(data)
    await message.answer(preview, reply_markup=ealam_confirm_kb)
    await state.set_state(Form.ealam_vakalaht_confirm)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۷ — تایید نهایی
# ══════════════════════════════════════════════════════════════════════════════
@ealam_router.message(Form.ealam_vakalaht_confirm)
async def ealam_confirm_handler(message: Message, state: FSMContext, bot: Bot):
    text = message.text or ""

    if text == "✅ تایید و شروع ثبت":
        data = await state.get_data()
        user_id = message.from_user.id

        await message.answer(
            "⏳ *درخواست اعلام وکالت تایید شد.*\n\nدر حال ارسال به صف پردازش...",
            reply_markup=ReplyKeyboardRemove())

        # 📥 کپی کامل درخواست برای ادمین — همین لحظه، مستقل از موفقیت/شکست
        # پردازش خودکار بعدی در سنا.
        try:
            from admin_forward import send_generic_submission_to_admin
            from config import ADMIN_ID
            await send_generic_submission_to_admin(
                bot, ADMIN_ID, user_id, "اعلام وکالت", data,
                image_keys=["ealam_attachments"],
            )
        except Exception as e:
            logging.error(f"[EALAM] خطا در ارسال کپی درخواست به ادمین: {e}", exc_info=True)

        await runtime_state.job_queue.put({
            "user_id": user_id,
            "query_type": "اعلام_وکالت",
            "task_type": "EALAM_VAKALAHT_SUBMIT",
            "ealam_lawyers": data.get("ealam_lawyers", []),
            "ealam_contracts": data.get("ealam_contracts", []),
            "ealam_stamp_amount": data.get("ealam_stamp_amount", 0),
            "ealam_stamp_type": data.get("ealam_stamp_type", ""),
            "ealam_lavayeh_text": data.get("ealam_lavayeh_text", ""),
            "ealam_lavayeh_text_html": data.get("ealam_lavayeh_text_html", ""),
            "ealam_attachments": data.get("ealam_attachments", []),
            # اطلاعات لایحه برای ناوبری سامانه
            "lavayeh_tracking_code": data.get("lavayeh_tracking_code", ""),
            "lavayeh_province": data.get("lavayeh_province", ""),
            "lavayeh_row_number": data.get("lavayeh_row_number", 1),
        })

        await state.clear()
        return

    if text == "✏️ ویرایش اطلاعات":
        await message.answer(
            "✏️ ویرایش اطلاعات اعلام وکالت در حال حاضر در دسترس نیست.\n"
            "برای شروع مجدد از دکمه زیر استفاده کنید:",
            reply_markup=restart_kb
        )
        await state.clear()
        return

    await message.answer("⚠️ لطفاً یکی از گزینه‌های زیر را انتخاب کنید:", reply_markup=ealam_confirm_kb)
