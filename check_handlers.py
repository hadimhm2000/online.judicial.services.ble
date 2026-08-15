"""
هندلرهای بخش ثبت دعاوی چک — فلوی مکالمه تلگرام.

جریان:
  ۱. ورود به بخش دعاوی چک (تکی یا دسته‌جمعی)
  ۲. انتخاب عنوان خواسته (صدور اجرائیه / مطالبه وجه)
  ۳. دریافت مبلغ چک
  ۴. دریافت/ویرایش عنوان خواسته (متن پیشنهادی)
  ۵. کدرهگیری چک
  ۶. اطلاعات خواهان (مانند اظهارکننده)
  ۷. اطلاعات خوانده (مانند مخاطب)
  ۸. مطلع/گواه
  ۹. شرح متن (متن پیشنهادی + امکان ارسال فایل ورد)
 ۱۰. توضیحات اضافی
  ۱۱. تصاویر چک (حداکثر ۳ + ادامه مدارک)
  ۱۲. انتخاب صلاحیت دادگاه
  ۱۳. پیش‌نمایش و تایید
"""

import asyncio
import logging
import os
import re

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove, CallbackQuery
from aiogram.types import FSInputFile

import runtime_state
from states import Form
from keyboards import (
    main_menu_kb, back_only_kb,
    representative_type_kb,
    create_ezhhar_declarant_person_type_kb,
    create_ezhhar_addressee_person_type_kb,
    create_check_person_type_kb,
    ezhhar_declarant_add_more_kb,
    ezhhar_addressee_add_more_kb,
    check_addressee_add_more_kb,
    get_check_more_images_kb,
    check_choice_kb,
    check_request_title_kb,
    check_confirm_kb,
    check_edit_kb,
    check_extra_text_kb,
    check_more_images_kb,  # fallback ثابت
    check_attachment_title_kb_first,
    check_attachment_title_kb,
    check_attachment_more_kb,
    check_docx_option_kb,
    bulk_input_method_kb)
from branches import create_branches_keyboard, ROOT_NODES, ID_TO_INDEX
from upload_helpers import download_images_from_bale

check_router = Router()

logger = logging.getLogger(__name__)

MAX_CHECK_IMAGES = 3
MAX_ATTACHMENT_IMAGES = 15

_FA_AR = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789"
)

def _to_en(text: str) -> str:
    return text.translate(_FA_AR).replace(" ", "").strip()

def _fmt(n: int) -> str:
    return f"{n:,}"

def _escape_md(text: str) -> str:
    return (text.replace("\\", "\\\\")
               .replace("_", "\\_")
               .replace("*", "\\*")
               .replace("[", "\\[")
               .replace("`", "\\`"))


# ══════════════════════════════════════════════════════════════════════════════
# ورود به بخش دعاوی چک
# ══════════════════════════════════════════════════════════════════════════════
async def check_entry(message: Message, state: FSMContext):
    await state.clear()
    await state.update_data(
        check_request_title="",
        check_amount=0,
        check_khasteh_text="",
        check_tracking_no="",
        check_plainiffs=[],
        check_defendants=[],
        check_witnesses=[],
        check_text="",
        check_text_html="",
        check_extra_text="",
        check_images=[],
        check_attachment_groups=[],
        check_branch_code="",
        check_branch_name="",
        check_branch_path="",
        check_docx_file_id=None,
        service_type="check")
    await message.answer(
        "🏦 *ثبت دعاوی چک*\n\n"
        "آیا قصد ثبت *یک مورد دادخواست چک* دارید یا *بیش از ۵ مورد (ثبت دسته‌جمعی)*؟",
        reply_markup=check_choice_kb)
    await state.set_state(Form.check_request_type)


# ── بازگشت به منوی اصلی از انتخاب نوع ثبت ──────────────────────────────
@check_router.message(Form.check_request_type, F.text == "🔙 بازگشت")
async def check_back_to_main(message: Message, state: FSMContext):
    await state.clear()
    from keyboards import get_flow_type_kb
    await message.answer(
        "❓ *لطفاً نحوه ثبت درخواست خود را انتخاب فرمایید:*",
        reply_markup=get_flow_type_kb(message.from_user.id))


# ── دسته‌جمعی ─────────────────────────────────────────────────────────────────
@check_router.message(Form.check_request_type, F.text == "📊 دانلود فایل اکسل و ثبت دسته‌جمعی")
async def check_bulk_choice_handler(message: Message, state: FSMContext):
    await message.answer(
        "📊 *ثبت دسته‌جمعی دعاوی چک*\n\n"
        "در این روش می‌توانید اطلاعات چندین دادخواست چک را با *فایل اکسل* ارسال فرمایید.\n\n"
        "لطفاً ابتدا فایل نمونه اکسل را دریافت و تکمیل نمایید:",
        reply_markup=bulk_input_method_kb)
    await state.set_state(Form.check_bulk_input_method)


@check_router.message(Form.check_bulk_input_method, F.text == "🔙 بازگشت")
async def check_bulk_back_to_choice(message: Message, state: FSMContext):
    await message.answer(
        "🏦 *ثبت دعاوی چک*\n\n"
        "آیا قصد ثبت *یک مورد دادخواست چک* دارید یا *بیش از ۵ مورد (ثبت دسته‌جمعی)*؟",
        reply_markup=check_choice_kb)
    await state.set_state(Form.check_request_type)


@check_router.message(Form.check_bulk_input_method, F.text == "📊 دانلود نمونه اکسل و آپلود فایل")
async def check_bulk_download_sample(message: Message, state: FSMContext):
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        sample_path = os.path.join(base_dir, "sample_check.xlsx")
        if not os.path.exists(sample_path):
            sample_path = os.path.join(os.getcwd(), "sample_check.xlsx")
        if not os.path.exists(sample_path):
            await message.answer("⚠️ فایل نمونه‌ی اکسل یافت نشد. لطفاً با پشتیبانی تماس بگیرید.",
                                reply_markup=bulk_input_method_kb)
            return
        await message.answer(
            "📥 *فایل نمونه اکسل دعاوی چک:*\n\n"
            "⚠️ *راهنمای تکمیل فایل:*\n\n"
            "۱. ستون *نوع خواسته*: `صدور اجرائیه چک` یا `مطالبه وجه چک`\n"
            "۲. ستون *مبلغ چک (ریال)*: فقط عدد به ریال\n"
            "۳. ستون *کدرهگیری*: شماره کدرهگیری چک\n"
            "۴. ستون *کدملی خواهان*: کد ملی ۱۰ رقمی\n"
            "۵. ستون *نام خواهان*: نام و نام خانوادگی\n"
            "۶. ستون *کدملی خوانده*: کد ملی ۱۰ رقمی\n"
            "۷. ستون *نام خوانده*: نام و نام خانوادگی\n"
            "۸. ستون *تعداد چک*: تعداد فقره چک\n"
            "۹. ستون *شماره چک*: شماره چک\n"
            "۱۰. ستون *تاریخ چک*: تاریخ سررسید\n"
            "۱۱. ستون *نام بانک*: نام بانک\n"
            "۱۲. ستون *کد صلاحیت دادگاه*: کد ۵ رقمی واحد قضایی\n")
        await message.answer_document(FSInputFile(sample_path))
        await message.answer(
            "📤 لطفاً فایل تکمیل‌شده را ارسال فرمایید:\n"
            "_(فرمت‌های پشتیبانی: xlsx)_",
            reply_markup=back_only_kb)
        await state.set_state(Form.check_bulk_file_upload)
    except Exception as e:
        logger.error(f"Error sending check sample excel: {e}")
        await message.answer(
            "⚠️ خطا در ارسال فایل نمونه. لطفاً دوباره تلاش کنید.",
            reply_markup=bulk_input_method_kb
        )


# ── پردازش فایل اکسل دسته‌جمعی چک ─────────────────────────────────────────
@check_router.message(Form.check_bulk_file_upload)
async def check_bulk_file_upload_handler(message: Message, state: FSMContext):
    # بررسی دکمه بازگشت
    if message.text and message.text == "🔙 بازگشت":
        await message.answer(
            "📊 *ثبت دسته‌جمعی دعاوی چک*\n\n"
            "در این روش می‌توانید اطلاعات چندین دادخواست چک را با *فایل اکسل* ارسال فرمایید.\n\n"
            "لطفاً ابتدا فایل نمونه اکسل را دریافت و تکمیل نمایید:",
            reply_markup=bulk_input_method_kb)
        await state.set_state(Form.check_bulk_input_method)
        return

    if not message.document:
        await message.answer(
            "⚠️ لطفاً فایل اکسل (.xlsx) را ارسال فرمایید.",
            reply_markup=back_only_kb
        )
        return

    doc = message.document
    if not (doc.file_name and doc.file_name.endswith(('.xlsx', '.xls'))):
        await message.answer(
            "⚠️ لطفاً فقط فایل با پسوند اکسل (.xlsx) ارسال فرمایید.",
            reply_markup=back_only_kb
        )
        return

    await message.answer("⏳ در حال دانلود و پردازش فایل...")

    try:
        import tempfile
        import openpyxl

        # دانلود فایل
        tmp_dir = tempfile.mkdtemp()
        file_path = os.path.join(tmp_dir, doc.file_name or "bulk_check.xlsx")
        await message.document.bot.download_file(doc.file_id, file_path)

        # پارس اکسل
        wb = openpyxl.load_workbook(file_path, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))

        if len(rows) < 2:
            await message.answer(
                "⚠️ فایل اکسل خالی است یا فقط هدر دارد. لطفاً حداقل یک ردیف داده وارد کنید.",
                reply_markup=back_only_kb
            )
            return

        # هدر (ردیف اول)
        header = [str(c or "").strip() for c in rows[0]]
        data_rows = rows[1:]

        # مپ کردن ستون‌ها
        col_map = {}
        for i, h in enumerate(header):
            if "نوع خواسته" in h:
                col_map["request_title"] = i
            elif "مبلغ" in h:
                col_map["amount"] = i
            elif "کدرهگیری" in h or "رهگیری" in h:
                col_map["tracking_no"] = i
            elif "کدملی خواهان" in h or "خواهان" in h and "کدملی" in h:
                col_map["plaintiff_nat_id"] = i
            elif "نام خواهان" in h:
                col_map["plaintiff_name"] = i
            elif "کدملی خوانده" in h or "خوانده" in h and "کدملی" in h:
                col_map["defendant_nat_id"] = i
            elif "نام خوانده" in h:
                col_map["defendant_name"] = i
            elif "صلاحیت" in h or "دادگاه" in h:
                col_map["branch_code"] = i

        required_cols = ["request_title", "amount", "tracking_no", "plaintiff_nat_id", "defendant_nat_id", "branch_code"]
        missing = [c for c in required_cols if c not in col_map]
        if missing:
            await message.answer(
                f"⚠️ ستون‌های الزامی یافت نشدند: {', '.join(missing)}\n\n"
                "لطفاً فایل نمونه را دریافت و مطابق آن تکمیل کنید.",
                reply_markup=back_only_kb
            )
            return

        # پردازش ردیف‌ها
        valid_items = []
        errors = []

        for idx, row in enumerate(data_rows, start=1):
            if not any(row):
                continue

            def _get(col_key):
                ci = col_map.get(col_key, -1)
                return str(row[ci]).strip() if ci >= 0 and ci < len(row) and row[ci] is not None else ""

            request_title = _get("request_title")
            amount_str = _to_en(_get("amount"))
            tracking_no = _to_en(_get("tracking_no"))
            plaintiff_nat_id = _to_en(_get("plaintiff_nat_id"))
            plaintiff_name = _get("plaintiff_name")
            defendant_nat_id = _to_en(_get("defendant_nat_id"))
            defendant_name = _get("defendant_name")
            branch_code = _to_en(_get("branch_code"))

            # اعتبارسنجی
            if request_title not in ["صدور اجرائیه چک", "مطالبه وجه چک"]:
                errors.append(f"ردیف {idx}: نوع خواسته نامعتبر ({request_title})")
                continue

            if not amount_str.isdigit() or int(amount_str) <= 0:
                errors.append(f"ردیف {idx}: مبلغ نامعتبر")
                continue

            if not tracking_no:
                errors.append(f"ردیف {idx}: کدرهگیری خالی است")
                continue

            if not branch_code:
                errors.append(f"ردیف {idx}: کد صلاحیت دادگاه خالی است")
                continue

            # ساخت متن پیشنهادی عنوان خواسته
            if request_title == "صدور اجرائیه چک":
                khasteh_text = (
                    "به موجب یک فقره چک به شماره ... مورخ ... به عهده بانک ملی "
                    "به مبلغ ... ریال با کدرهگیری ... به انضمام کلیه خسارات دادرسی و حق الوکاله وکیل "
                    "و خسارات تاخيرتاديه از زمان سررسيد لغايت زمان كامل اجراي حكم و حق الوكاله وكيل"
                )
            else:
                khasteh_text = (
                    "به موجب ........ فقره چک به شماره ......... مورخ ......... به عهده بانک ....... "
                    "به انضمام کلیه هزینه های دادرسی و خسارات تاخیرتادیه از زمان سررسید "
                    "لغایت زمان کامل اجرای حکم و حق الوکاله وکیل"
                )

            item = {
                "check_request_title": request_title,
                "check_amount": int(amount_str),
                "check_khasteh_text": khasteh_text,
                "check_tracking_no": tracking_no,
                "check_plainiffs": [{
                    "person_type": "شخص حقیقی",
                    "national_id": plaintiff_nat_id,
                    "name": plaintiff_name or "---",
                    "representative_type": "",
                }],
                "check_defendants": [{
                    "person_type": "شخص حقیقی",
                    "national_id": defendant_nat_id,
                    "name": defendant_name or "---",
                    "representative_type": "",
                }],
                "check_witnesses": [],
                "check_text": "",
                "check_text_html": "",
                "check_extra_text": "",
                "check_images": [],
                "check_attachment_groups": [],
                "check_branch_code": branch_code,
                "check_branch_name": "",
                "check_branch_path": "",
                "check_docx_file_id": None,
                "check_docx_file_name": "",
            }
            valid_items.append(item)

        if not valid_items:
            err_text = "\n".join(errors[:10]) if errors else "هیچ ردیف معتبری یافت نشد."
            await message.answer(
                f"❌ *خطا در پردازش فایل:*\n\n{err_text}",
                reply_markup=back_only_kb)
            return

        # ارسال به صف پردازش
        user_id = message.from_user.id
        for item in valid_items:
            item["user_id"] = user_id
            item["query_type"] = "دادخواست_چک"
            item["task_type"] = "CHECK_SUBMIT"
            await runtime_state.job_queue.put(item)

        summary = (
            f"✅ *فایل دسته‌جمعی با موفقیت پردازش شد!*\n\n"
            f"📊 تعداد کل ردیف‌ها: {len(data_rows)}\n"
            f"✅ ردیف‌های معتبر: *{len(valid_items)}* مورد\n"
        )
        if errors:
            summary += f"❌ ردیف‌های خطادار: *{len(errors)}* مورد\n"
            summary += "\n📋 *خطاها:*\n" + "\n".join(errors[:10])
            if len(errors) > 10:
                summary += f"\n... و {len(errors) - 10} خطای دیگر"

        summary += (
            f"\n\n⏳ تمامی موارد معتبر به *صف پردازش* ارسال شدند."
            f"\n📋 نتایج به صورت خودکار برایتان ارسال خواهد شد."
        )

        await state.clear()
        from keyboards import flow_type_kb
        try:
            await message.answer(summary, reply_markup=flow_type_kb)
        except Exception:
            await message.answer(summary, reply_markup=flow_type_kb)

        # لاگ
        try:
            from sheets import log_event
            log_event(
                user_id=user_id,
                event_type="CHECK_BULK_SUBMIT",
                details=f"{len(valid_items)} items from Excel"
            )
        except Exception:
            pass

    except Exception as e:
        logger.error(f"Error processing bulk check Excel: {e}", exc_info=True)
        await message.answer(
            f"⚠️ خطا در پردازش فایل: {str(e)[:200]}",
            reply_markup=back_only_kb
        )


# ── ثبت تکی ───────────────────────────────────────────────────────────────────
@check_router.message(Form.check_request_type, F.text == "1️⃣ ثبت تکی (روال عادی)")
async def check_single_choice_handler(message: Message, state: FSMContext):
    await message.answer(
        "🏦 *ثبت دادخواست چک (روال تکی)*\n\n"
        "*مرحله ۱:* لطفاً *عنوان خواسته خود* را انتخاب فرمایید:",
        reply_markup=check_request_title_kb)
    await state.set_state(Form.check_request_title)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۱ — عنوان خواسته
# ══════════════════════════════════════════════════════════════════════════════
@check_router.message(Form.check_request_title)
async def check_request_title_handler(message: Message, state: FSMContext):
    text = message.text or ""
    if text not in ["صدور اجرائیه چک", "مطالبه وجه چک"]:
        await message.answer(
            "⚠️ لطفاً یکی از گزینه‌های موجود را انتخاب کنید:",
            reply_markup=check_request_title_kb
        )
        return

    await state.update_data(check_request_title=text)
    await message.answer(
        "💰 *مرحله ۲:* لطفاً *مبلغ چک* را به *ریال* وارد فرمایید:\n"
        "_(فقط عدد، بدون کاراکتر اضافی)_",
        reply_markup=back_only_kb)
    await state.set_state(Form.check_amount)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۲ — مبلغ چک
# ══════════════════════════════════════════════════════════════════════════════
@check_router.message(Form.check_amount)
async def check_amount_handler(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == "🔙 بازگشت":
        await message.answer(
            "*مرحله ۱:* لطفاً *عنوان خواسته خود* را انتخاب فرمایید:",
            reply_markup=check_request_title_kb)
        await state.set_state(Form.check_request_title)
        return

    amount_str = _to_en(message.text)
    if not amount_str.isdigit():
        await message.answer(
            "⚠️ مبلغ باید فقط شامل اعداد باشد. لطفاً مجدداً وارد کنید:",
            reply_markup=back_only_kb
        )
        return

    amount = int(amount_str)
    await state.update_data(check_amount=amount)

    # مرحله ۳ — متن پیشنهادی عنوان خواسته
    data = await state.get_data()
    request_title = data.get("check_request_title", "")

    if request_title == "صدور اجرائیه چک":
        suggested = (
            "به موجب یک فقره چک به شماره ... مورخ ... به عهده بانک ملی "
            "به مبلغ ... ریال با کدرهگیری ... به انضمام کلیه خسارات دادرسی و حق الوکاله وکیل "
            "و خسارات تاخيرتاديه از زمان سررسيد لغايت زمان كامل اجراي حكم و حق الوكاله وكيل"
        )
    else:
        suggested = (
            "به موجب ........ فقره چک به شماره ......... مورخ ......... به عهده بانک ....... "
            "به انضمام کلیه هزینه های دادرسی و خسارات تاخیرتادیه از زمان سررسید "
            "لغایت زمان کامل اجرای حکم و حق الوکاله وکیل"
        )

    await message.answer(
        "📄 *مرحله ۳:* عنوان خواسته\n\n"
        f"📝 *متن پیشنهادی:*\n\n{suggested}\n\n"
        "💡 می‌توانید متن فوق را *ویرایش* و ارسال فرمایید یا اگر متنی دارید، مستقیماً وارد کنید:",
        reply_markup=back_only_kb)
    await state.set_state(Form.check_khasteh_title)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۳ — عنوان خواسته (متن)
# ══════════════════════════════════════════════════════════════════════════════
@check_router.message(Form.check_khasteh_title)
async def check_khasteh_title_handler(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == "🔙 بازگشت":
        await message.answer(
            "💰 لطفاً *مبلغ چک* را به *ریال* وارد فرمایید:",
            reply_markup=back_only_kb)
        await state.set_state(Form.check_amount)
        return

    await state.update_data(check_khasteh_text=message.text)
    await message.answer(
        "🔢 *مرحله ۴:* لطفاً *کدرهگیری چک* را ارسال بفرمائید.\n\n"
        "⚠️ لطفاً دقت بفرمائید که اعداد را کاملاً صحیح ارسال می‌فرمائید.",
        reply_markup=back_only_kb)
    await state.set_state(Form.check_tracking_no)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۴ — کدرهگیری چک
# ══════════════════════════════════════════════════════════════════════════════
@check_router.message(Form.check_tracking_no)
async def check_tracking_no_handler(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == "🔙 بازگشت":
        data = await state.get_data()
        request_title = data.get("check_request_title", "")
        if request_title == "صدور اجرائیه چک":
            suggested = (
                "به موجب یک فقره چک به شماره ... مورخ ... به عهده بانک ملی "
                "به مبلغ ... ریال با کدرهگیری ... به انضمام کلیه خسارات دادرسی و حق الوکاله وکیل "
                "و خسارات تاخيرتاديه از زمان سررسيد لغايت زمان كامل اجراي حكم و حق الوكاله وكيل"
            )
        else:
            suggested = (
                "به موجب ........ فقره چک به شماره ......... مورخ ......... به عهده بانک ....... "
                "به انضمام کلیه هزینه های دادرسی و خسارات تاخیرتادیه از زمان سررسید "
                "لغایت زمان کامل اجرای حکم و حق الوکاله وکیل"
            )
        await message.answer(
            "📝 *متن پیشنهادی عنوان خواسته:*\n\n"
            f"{suggested}\n\n"
            "متن را ویرایش و ارسال فرمایید:",
            reply_markup=back_only_kb)
        await state.set_state(Form.check_khasteh_title)
        return

    tracking_no = _to_en(message.text)
    await state.update_data(check_tracking_no=tracking_no)

    # مرحله ۵ — خواهان
    await message.answer(
        "👤 *مرحله ۵:* لطفاً *نوع شخصیت خواهان* را انتخاب فرمایید:",
        reply_markup=create_ezhhar_declarant_person_type_kb())
    await state.set_state(Form.check_plaintiff_person_type)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۵ — خواهان (مانند اظهارکننده)
# ══════════════════════════════════════════════════════════════════════════════
@check_router.message(Form.check_plaintiff_person_type)
async def check_plaintiff_person_type_handler(message: Message, state: FSMContext):
    text = message.text or ""
    data = await state.get_data()
    plaintiffs = data.get("check_plainiffs", [])
    used_types = [p.get("person_type") for p in plaintiffs]

    if text == "✅ اتمام و ادامه":
        if not plaintiffs:
            await message.answer("⚠️ حداقل یک خواهان باید اضافه شود.")
            return
        # رفتن به مرحله خوانده
        await message.answer(
            "👥 *مرحله ۶:* لطفاً *نوع شخصیت خوانده* را انتخاب فرمایید:",
            reply_markup=create_check_person_type_kb())
        await state.set_state(Form.check_defendant_person_type)
        return

    if text not in ["شخص حقیقی", "شخص حقوقی", "وکیل"]:
        await message.answer(
            "⚠️ لطفاً یکی از گزینه‌های موجود را انتخاب کنید:",
            reply_markup=create_ezhhar_declarant_person_type_kb(exclude=used_types if plaintiffs else [])
        )
        return

    await state.update_data(_check_current_plaintiff={"person_type": text})

    if text == "شخص حقوقی":
        await message.answer(
            "🏢 لطفاً *شناسه ملی شرکت* خواهان را وارد فرمایید:\n_(۱۱ رقمی)_",
            reply_markup=back_only_kb)
        await state.set_state(Form.check_plaintiff_company_id)
    else:
        type_label = "وکیل" if text == "وکیل" else "شخص"
        await message.answer(
            f"🔢 لطفاً *کد ملی {type_label}* خواهان را وارد فرمایید:\n_(۱۰ رقمی)_",
            reply_markup=back_only_kb)
        await state.set_state(Form.check_plaintiff_national_id)


@check_router.message(Form.check_plaintiff_company_id)
async def check_plaintiff_company_id_handler(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == "🔙 بازگشت":
        data = await state.get_data()
        plaintiffs = data.get("check_plainiffs", [])
        used_types = [p.get("person_type") for p in plaintiffs]
        await message.answer(
            "👤 لطفاً نوع شخصیت خواهان را انتخاب کنید:",
            reply_markup=create_ezhhar_declarant_person_type_kb(exclude=used_types if plaintiffs else [])
        )
        await state.set_state(Form.check_plaintiff_person_type)
        return

    company_id = _to_en(message.text)
    if not company_id.isdigit() or len(company_id) != 11:
        await message.answer("⚠️ شناسه ملی شرکت باید *۱۱ رقمی* باشد:")
        return

    data = await state.get_data()
    current = data.get("_check_current_plaintiff", {})
    current["company_id"] = company_id
    await state.update_data(_check_current_plaintiff=current)

    await message.answer("👔 نماینده شرکت چه سمتی دارد؟", reply_markup=representative_type_kb)
    await state.set_state(Form.check_plaintiff_representative_type)


@check_router.message(Form.check_plaintiff_representative_type)
async def check_plaintiff_representative_type_handler(message: Message, state: FSMContext):
    text = message.text or ""
    if text not in ["مدیرعامل", "نماینده"]:
        await message.answer("⚠️ لطفاً یکی از گزینه‌ها را انتخاب کنید:", reply_markup=representative_type_kb)
        return

    data = await state.get_data()
    current = data.get("_check_current_plaintiff", {})
    current["representative_type"] = text
    await state.update_data(_check_current_plaintiff=current)

    await message.answer(
        f"🔢 لطفاً *کد ملی {text}* شرکت خواهان را وارد فرمایید:\n_(۱۰ رقمی)_",
        reply_markup=back_only_kb)
    await state.set_state(Form.check_plaintiff_national_id)


@check_router.message(Form.check_plaintiff_national_id)
async def check_plaintiff_national_id_handler(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == "🔙 بازگشت":
        data = await state.get_data()
        plaintiffs = data.get("check_plainiffs", [])
        used_types = [p.get("person_type") for p in plaintiffs]
        await message.answer(
            "👤 لطفاً نوع شخصیت خواهان را انتخاب کنید:",
            reply_markup=create_ezhhar_declarant_person_type_kb(exclude=used_types if plaintiffs else [])
        )
        await state.set_state(Form.check_plaintiff_person_type)
        return

    nat_id = _to_en(message.text)
    if not re.match(r"^[0-9]{10}$", nat_id):
        await message.answer("⚠️ کد ملی باید *۱۰ رقمی* باشد:")
        return

    data = await state.get_data()
    current = data.get("_check_current_plaintiff", {})
    current["national_id"] = nat_id

    plaintiffs = data.get("check_plainiffs", [])
    plaintiffs.append(current)
    await state.update_data(check_plainiffs=plaintiffs, _check_current_plaintiff={})

    await message.answer(
        f"✅ خواهان اضافه شد. (تعداد: {len(plaintiffs)})\n\n"
        "آیا خواهان دیگری نیز وجود دارد؟",
        reply_markup=ezhhar_declarant_add_more_kb)
    await state.set_state(Form.check_plaintiff_more)


@check_router.message(Form.check_plaintiff_more)
async def check_plaintiff_more_handler(message: Message, state: FSMContext):
    text = message.text or ""
    if text == "➕ افزودن شخص اظهارکننده دیگر":
        # متن دکمه از اظهارنامه استفاده می‌شود ولی منطق درست کار می‌کند
        data = await state.get_data()
        plaintiffs = data.get("check_plainiffs", [])
        used_types = [p.get("person_type") for p in plaintiffs]
        await message.answer(
            "👤 لطفاً نوع شخصیت خواهان جدید را انتخاب فرمایید:",
            reply_markup=create_ezhhar_declarant_person_type_kb(exclude=used_types)
        )
        await state.set_state(Form.check_plaintiff_person_type)
    elif text == "✅ اتمام و ادامه":
        await message.answer(
            "👥 *مرحله ۶:* لطفاً *نوع شخصیت خوانده* را انتخاب فرمایید:\n\n"
            "📌 درصورتی که کدملی خوانده را ندارید و صرفاً شماره تماس شخص مورد نظر را دارید، "
            "می‌توانید از گزینه *«استعلام شماره تماس»* استفاده کنید.",
            reply_markup=create_check_person_type_kb())
        await state.set_state(Form.check_defendant_person_type)
    elif "بازگشت" in text:
        data = await state.get_data()
        plaintiffs = data.get("check_plainiffs", [])
        if plaintiffs:
            # حذف آخرین شخص اضافه‌شده
            plaintiffs.pop()
            await state.update_data(check_plainiffs=plaintiffs)
        used_types = [p.get("person_type") for p in plaintiffs]
        await message.answer(
            "👤 لطفاً نوع شخصیت خواهان را انتخاب فرمایید:",
            reply_markup=create_ezhhar_declarant_person_type_kb(exclude=used_types if plaintiffs else [])
        )
        await state.set_state(Form.check_plaintiff_person_type)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۶ — خوانده (مانند مخاطب)
# ══════════════════════════════════════════════════════════════════════════════
@check_router.message(Form.check_defendant_person_type)
async def check_defendant_person_type_handler(message: Message, state: FSMContext):
    text = message.text or ""
    data = await state.get_data()
    defendants = data.get("check_defendants", [])
    used_types = [p.get("person_type") for p in defendants]

    if text == "✅ اتمام و ادامه":
        if not defendants:
            await message.answer("⚠️ حداقل یک خوانده باید اضافه شود.")
            return
        # رفتن به مرحله مطلع/گواه
        await message.answer(
            "🔍 *مرحله ۷:* آیا *مطلع یا گواه* دارید؟\n\n"
            "در صورت وجود، *کدملی* مطلع/گواه را ارسال فرمایید.\n"
            "_(در غیر این صورت گزینه «اتمام» را انتخاب کنید)_",
            reply_markup=check_addressee_add_more_kb)
        await state.set_state(Form.check_witness_national_id)
        return

    if text == "📞 استعلام شماره تماس":
        # TODO: Implement phone lookup for defendants if needed
        await message.answer(
            "⚠️ این قابلیت فعلاً در بخش دعاوی چک فعال نیست.\n"
            "لطفاً نوع شخصیت خوانده را انتخاب فرمایید:",
            reply_markup=create_check_person_type_kb(show_finish=bool(defendants))
        )
        return

    if text not in ["شخص حقیقی", "شخص حقوقی"]:
        await message.answer(
            "⚠️ لطفاً یکی از گزینه‌های موجود را انتخاب کنید:",
            reply_markup=create_check_person_type_kb()
        )
        return

    await state.update_data(_check_current_defendant={"person_type": text})

    if text == "شخص حقوقی":
        await message.answer(
            "🏢 لطفاً *شناسه ملی شرکت* خوانده را وارد فرمایید:\n_(۱۱ رقمی)_",
            reply_markup=back_only_kb)
        await state.set_state(Form.check_defendant_company_id)
    else:
        await message.answer(
            "🔢 لطفاً *کد ملی خوانده* را وارد فرمایید:\n_(۱۰ رقمی)_",
            reply_markup=back_only_kb)
        await state.set_state(Form.check_defendant_national_id)


@check_router.message(Form.check_defendant_company_id)
async def check_defendant_company_id_handler(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == "🔙 بازگشت":
        data = await state.get_data()
        defendants = data.get("check_defendants", [])
        used_types = [p.get("person_type") for p in defendants]
        await message.answer(
            "👥 لطفاً نوع شخصیت خوانده را انتخاب فرمایید:",
            reply_markup=create_check_person_type_kb()
        )
        await state.set_state(Form.check_defendant_person_type)
        return

    company_id = _to_en(message.text)
    if not company_id.isdigit() or len(company_id) != 11:
        await message.answer("⚠️ شناسه ملی شرکت باید *۱۱ رقمی* باشد:")
        return

    data = await state.get_data()
    current = data.get("_check_current_defendant", {})
    current["company_id"] = company_id
    await state.update_data(_check_current_defendant=current)

    await message.answer("👔 نماینده شرکت چه سمتی دارد؟", reply_markup=representative_type_kb)
    await state.set_state(Form.check_defendant_representative_type)


@check_router.message(Form.check_defendant_representative_type)
async def check_defendant_representative_type_handler(message: Message, state: FSMContext):
    text = message.text or ""
    if text not in ["مدیرعامل", "نماینده"]:
        await message.answer("⚠️ لطفاً یکی از گزینه‌ها را انتخاب کنید:", reply_markup=representative_type_kb)
        return

    data = await state.get_data()
    current = data.get("_check_current_defendant", {})
    current["representative_type"] = text
    await state.update_data(_check_current_defendant=current)

    await message.answer(
        f"🔢 لطفاً *کد ملی {text}* شرکت خوانده را وارد فرمایید:\n_(۱۰ رقمی)_",
        reply_markup=back_only_kb)
    await state.set_state(Form.check_defendant_national_id)


@check_router.message(Form.check_defendant_national_id)
async def check_defendant_national_id_handler(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == "🔙 بازگشت":
        data = await state.get_data()
        defendants = data.get("check_defendants", [])
        used_types = [p.get("person_type") for p in defendants]
        await message.answer(
            "👥 لطفاً نوع شخصیت خوانده را انتخاب فرمایید:",
            reply_markup=create_check_person_type_kb()
        )
        await state.set_state(Form.check_defendant_person_type)
        return

    nat_id = _to_en(message.text)
    if not re.match(r"^[0-9]{10}$", nat_id):
        await message.answer("⚠️ کد ملی باید *۱۰ رقمی* باشد:")
        return

    data = await state.get_data()
    current = data.get("_check_current_defendant", {})
    current["national_id"] = nat_id

    defendants = data.get("check_defendants", [])
    defendants.append(current)
    await state.update_data(check_defendants=defendants, _check_current_defendant={})

    await message.answer(
        f"✅ خوانده اضافه شد. (تعداد: {len(defendants)})\n\n"
        "آیا خوانده دیگری نیز وجود دارد؟",
        reply_markup=ezhhar_addressee_add_more_kb)
    await state.set_state(Form.check_defendant_more)


@check_router.message(Form.check_defendant_more)
async def check_defendant_more_handler(message: Message, state: FSMContext):
    text = message.text or ""
    if text == "➕ افزودن خوانده دیگر":
        data = await state.get_data()
        defendants = data.get("check_defendants", [])
        used_types = [p.get("person_type") for p in defendants]
        await message.answer(
            "👥 لطفاً نوع شخصیت خوانده جدید را انتخاب فرمایید:",
            reply_markup=create_check_person_type_kb()
        )
        await state.set_state(Form.check_defendant_person_type)
    elif text == "✅ اتمام و ادامه":
        await message.answer(
            "🔍 *مرحله ۷:* آیا *مطلع یا گواه* دارید؟\n\n"
            "در صورت وجود، *کدملی* مطلع/گواه را ارسال فرمایید.",
            reply_markup=check_addressee_add_more_kb)
        await state.set_state(Form.check_witness_national_id)
    elif "بازگشت" in text:
        data = await state.get_data()
        defendants = data.get("check_defendants", [])
        if defendants:
            defendants.pop()
            await state.update_data(check_defendants=defendants)
        used_types = [p.get("person_type") for p in defendants]
        await message.answer(
            "👥 لطفاً نوع شخصیت خوانده را انتخاب فرمایید:",
            reply_markup=create_check_person_type_kb()
        )
        await state.set_state(Form.check_defendant_person_type)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۷ — مطلع/گواه
# ══════════════════════════════════════════════════════════════════════════════
@check_router.message(Form.check_witness_national_id)
async def check_witness_national_id_handler(message: Message, state: FSMContext):
    text = message.text or ""
    if text == "✅ اتمام و ادامه":
        # رفتن به مرحله شرح متن
        await _ask_check_text(message, state)
        return
    if "بازگشت" in text:
        data = await state.get_data()
        defendants = data.get("check_defendants", [])
        used_types = [p.get("person_type") for p in defendants]
        await message.answer(
            "👥 لطفاً نوع شخصیت خوانده را انتخاب فرمایید:",
            reply_markup=create_check_person_type_kb()
        )
        await state.set_state(Form.check_defendant_person_type)
        return

    nat_id = _to_en(text)
    if not re.match(r"^[0-9]{10}$", nat_id):
        await message.answer(
            "⚠️ کد ملی باید *۱۰ رقمی* باشد. لطفاً مجدداً وارد کنید:\n"
            "_(یا گزینه «اتمام و ادامه» را بزنید)_",
            reply_markup=check_addressee_add_more_kb)
        return

    data = await state.get_data()
    witnesses = data.get("check_witnesses", [])
    witnesses.append({"national_id": nat_id})
    await state.update_data(check_witnesses=witnesses)

    await message.answer(
        f"✅ مطلع/گواه اضافه شد. (تعداد: {len(witnesses)})\n\n"
        "آیا مطلع/گواه دیگری نیز وجود دارد؟",
        reply_markup=ezhhar_addressee_add_more_kb)
    await state.set_state(Form.check_more_witnesses)


@check_router.message(Form.check_more_witnesses)
async def check_more_witnesses_handler(message: Message, state: FSMContext):
    text = message.text or ""
    if text == "➕ افزودن خوانده دیگر":
        await message.answer(
            "🔍 لطفاً *کدملی مطلع/گواه* بعدی را ارسال فرمایید:\n_(۱۰ رقمی)_",
            reply_markup=back_only_kb)
        await state.set_state(Form.check_witness_national_id)
    elif text == "✅ اتمام و ادامه":
        await _ask_check_text(message, state)
    elif "بازگشت" in text:
        data = await state.get_data()
        witnesses = data.get("check_witnesses", [])
        if witnesses:
            witnesses.pop()
            await state.update_data(check_witnesses=witnesses)
        await message.answer(
            "🔍 لطفاً *کدملی مطلع/گواه* را ارسال فرمایید:\n_(۱۰ رقمی)_\n"
            "_(یا گزینه «اتمام و ادامه» را بزنید)_",
            reply_markup=check_addressee_add_more_kb)
        await state.set_state(Form.check_witness_national_id)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۸ — شرح متن
# ══════════════════════════════════════════════════════════════════════════════
async def _ask_check_text(message: Message, state: FSMContext):
    data = await state.get_data()
    request_title = data.get("check_request_title", "")

    if request_title == "صدور اجرائیه چک":
        suggested = (
            "ریاست محترم دادگاه عمومی حقوقی شهرستان یزد \n"
            "باسلام\n"
            "احتراما به وکالت از خواهان به استحضار می رساند : \n"
            "نظر به اينكه به موجب ..... فقره چک \n"
            "................ بلحاظ فقدان موجودي كافي پرداخت نشده است "
            "لذا درخواست صدور اجرائيه عليه خوانده/ خواندگان فوق را دارم.\n"
            "با تشكر و تجديد احترام"
        )
    else:
        suggested = (
            "رياست محترم ..................\n"
            "باسلام\n"
            "احتراما به وکالت از خواهان به استحضار می رساند :\n"
            "به موجب كپي مصدق ............................. موكل اينجانب "
            "مبلغ ............... ريال از خوانده/خواندگان طلبكار است كه "
            "نامبرده /نامبردگان با وصف مراجعات مكرر و حلول اجل وسر رسيد از تاديه "
            "و پرداخت آن خودداري مي كنند فلها مستندا به مواد ۱۹۸ قانون آئين دادرسي "
            "دادگاههاي عمومي وانقلاب در امور مدني و ۳۱۰ قانون تجارت رسيدگي و "
            "صدور حكم محكوميت خوانده /خواندگان به پرداخت مبلغ خواسته به ميزان "
            "............ ريال به انضمام کلیه هزینه های دادرسی و خسارات تاخیرتادیه "
            "از زمان سررسید لغایت زمان کامل اجرای حکم و حق الوکاله وکیل در حق "
            "موكل اينجانب مورد استدعاست.\nباتشکر"
        )

    await message.answer(
        "📄 *مرحله ۸:* شرح متن دادخواست\n\n"
        f"📝 *متن پیشنهادی:*\n\n{suggested}\n\n"
        "💡 می‌توانید متن فوق را *ویرایش* و ارسال فرمایید یا اگر متنی دارید، مستقیماً وارد کنید:",
        reply_markup=check_docx_option_kb)
    await state.set_state(Form.check_text)


@check_router.message(Form.check_text)
async def check_text_handler(message: Message, state: FSMContext):
    if message.document:
        # فایل ورد دریافت شد
        doc = message.document
        if doc.file_name and doc.file_name.endswith((".doc", ".docx")):
            await state.update_data(check_docx_file_id=doc.file_id, check_docx_file_name=doc.file_name)
            # مستقیماً به مرحله تصاویر برو
            await _ask_check_images(message, state)
            return

    if not message.text:
        return

    text = message.text or ""
    if text == "⌨️ تایپ مستقیم متن":
        await message.answer(
            "📄 لطفاً *شرح متن* دادخواست را ارسال فرمایید:",
            reply_markup=back_only_kb)
        await state.set_state(Form.check_text_input)
        return

    if text == "📎 ارسال فایل ورد (.docx)":
        await message.answer(
            "📎 لطفاً *فایل ورد (.docx)* را ارسال فرمایید:",
            reply_markup=back_only_kb)
        await state.set_state(Form.check_text_input)
        return

    if text == "🔙 بازگشت":
        data = await state.get_data()
        witnesses = data.get("check_witnesses", [])
        await message.answer(
            "🔍 لطفاً *کدملی مطلع/گواه* را ارسال فرمایید:\n"
            "_(یا گزینه «اتمام و ادامه» را بزنید)_",
            reply_markup=check_addressee_add_more_kb)
        await state.set_state(Form.check_witness_national_id)
        return

    # متن شرح دریافت شد — مستقیماً به تصاویر برو
    await state.update_data(check_text=message.text)
    await _ask_check_images(message, state)


@check_router.message(Form.check_text_input)
async def check_text_input_handler(message: Message, state: FSMContext):
    """دریافت متن تایپ‌شده یا فایل ورد برای شرح متن."""
    if message.document:
        doc = message.document
        if doc.file_name and doc.file_name.endswith((".doc", ".docx")):
            await state.update_data(check_docx_file_id=doc.file_id, check_docx_file_name=doc.file_name)
            await _ask_check_images(message, state)
            return

    if not message.text:
        return

    if message.text == "🔙 بازگشت":
        await _ask_check_text(message, state)
        return

    # متن شرح دریافت شد
    await state.update_data(check_text=message.text)
    await _ask_check_images(message, state)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۹ — توضیحات اضافی / فایل ورد
# ══════════════════════════════════════════════════════════════════════════════
@check_router.message(Form.check_extra_text)
async def check_extra_text_handler(message: Message, state: FSMContext):
    text = message.text or ""

    if text == "⏭ رد شدن (بدون توضیحات اضافی)":
        await state.update_data(check_extra_text="")
        await _ask_check_images(message, state)
        return

    if text == "🔙 بازگشت":
        data = await state.get_data()
        request_title = data.get("check_request_title", "")
        if request_title == "صدور اجرائیه چک":
            suggested = "ریاست محترم دادگاه عمومی حقوقی..."
        else:
            suggested = "رياست محترم .................."
        await message.answer(
            "📄 لطفاً *شرح متن* را ارسال فرمایید:",
            reply_markup=back_only_kb
        )
        await state.set_state(Form.check_text)
        return

    # توضیحات اضافی دریافت شد
    await state.update_data(check_extra_text=message.text)
    await _ask_check_images(message, state)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۱۰ — تصاویر چک
# ══════════════════════════════════════════════════════════════════════════════
async def _ask_check_images(message: Message, state: FSMContext):
    await message.answer(
        "🖼 *مرحله ۱۰:* لطفاً *تصویر چک و پشت چک و گواهی عدم پرداخت* را ارسال فرمایید.\n\n"
        "⚠️ حداکثر *۳ تصویر* می‌توانید ارسال کنید.",
        reply_markup=back_only_kb)
    await state.set_state(Form.check_images)


@check_router.message(Form.check_images, F.photo)
async def check_receive_photo(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    images = data.get("check_images", [])

    if len(images) >= MAX_CHECK_IMAGES:
        await message.answer(
            f"⚠️ حداکثر {MAX_CHECK_IMAGES} تصویر چک مجاز است. لطفاً گزینه ادامه را انتخاب کنید:",
            reply_markup=get_check_more_images_kb(len(images), MAX_CHECK_IMAGES)
        )
        return

    # ذخیره file_id تصویر
    if message.photo:
        largest = message.photo[-1]
        images.append({"file_id": largest.file_id})
        await state.update_data(check_images=images)

    count = len(images)
    remaining = MAX_CHECK_IMAGES - count
    if remaining > 0:
        await message.answer(
            f"✅ تصویر دریافت شد. ({count}/{MAX_CHECK_IMAGES})\n\n"
            f"می‌توانید تصویر دیگری ارسال کنید ({remaining} تصویر باقیمانده)\n"
            "یا گزینه ادامه را بزنید:",
            reply_markup=get_check_more_images_kb(count, MAX_CHECK_IMAGES))
        # Fix: تغییر state به check_more_images تا دکمه‌ها کار کنند
        await state.set_state(Form.check_more_images)
    else:
        await message.answer(
            f"✅ {MAX_CHECK_IMAGES} تصویر دریافت شد.\n\n"
            "آیا تصویر یا مدرک دیگری نیز دارید؟",
            reply_markup=get_check_more_images_kb(count, MAX_CHECK_IMAGES))
        # Fix: تغییر state به check_more_images تا دکمه‌ها کار کنند
        await state.set_state(Form.check_more_images)


@check_router.message(Form.check_images)
async def check_images_text_fallback(message: Message, state: FSMContext):
    if message.text and "بازگشت" in message.text:
        data = await state.get_data()
        if data.get("check_docx_file_id"):
            await message.answer(
                "📎 آیا فایل ورد دیگری دارید؟",
                reply_markup=check_docx_option_kb
            )
            await state.set_state(Form.check_extra_text)
        else:
            await message.answer(
                "📄 لطفاً *شرح متن* را ارسال فرمایید:",
                reply_markup=back_only_kb
            )
            await state.set_state(Form.check_text)
        return
    await message.answer(
        "⚠️ لطفاً *تصویر* ارسال فرمایید. (حداکثر ۳ تصویر)"
    )


@check_router.message(Form.check_more_images)
async def check_more_images_handler(message: Message, state: FSMContext):
    text = message.text or ""
    data = await state.get_data()
    check_images = data.get("check_images", [])

    if text == "➕ تصویر چک بعدی":
        count = len(check_images)
        if count >= MAX_CHECK_IMAGES:
            await message.answer(
                f"⚠️ حداکثر {MAX_CHECK_IMAGES} تصویر چک مجاز است.",
                reply_markup=get_check_more_images_kb(count, MAX_CHECK_IMAGES))
            return
        await message.answer(
            "🖼 لطفاً *تصویر چک بعدی* را ارسال فرمایید:",
            reply_markup=back_only_kb)
        await state.set_state(Form.check_images)
        return

    if text == "📎 تصویر یا مدرک دیگر دارم":
        # بررسی شخص حقوقی — مدرک نمایندگی اجباری
        persons = data.get("check_plainiffs", []) + data.get("check_defendants", [])
        has_legal = any(p.get("person_type") == "شخص حقوقی" for p in persons)
        if has_legal:
            await message.answer(
                "*مرحله مدارک:*\n\n"
                "⚠️ *توجه:* چون شخص *حقوقی* دارید، ارسال تصویر *مدرک نمایندگی* اجباری است.\n\n"
                "📸 لطفاً ابتدا تصویر *مدرک نمایندگی* را ارسال فرمایید.\n"
                "_(مثلاً: روزنامه رسمی، آگهی تأسیس، وکالت‌نامه رسمی)_")
            await state.update_data(
                _mandatory_proxy_sent=False,
                _current_attachment_title="مدرک نمایندی",
                _current_attachment_images=[])
            from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
            manage_kb = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ اتمام ارسال تصاویر")],
                    [KeyboardButton(text="🔙 بازگشت")],
                ], resize_keyboard=True
            )
            await message.answer(
                "🖼 لطفاً تصویر *مدرک نمایندگی* را ارسال فرمایید:",
                reply_markup=manage_kb)
            await state.set_state(Form.check_attachment_images)
        else:
            await message.answer(
                "📎 لطفاً *عنوان مدرک* را وارد فرمایید:\n\n"
                "_(مثلاً: گواهی عدم پرداخت، قرارداد و ...)_",
                reply_markup=check_attachment_title_kb_first)
            await state.set_state(Form.check_attachment_title)
        return

    if text == "✅ خیر، ادامه به انتخاب دادگاه":
        await _ask_check_branch(message, state)
        return

    if "بازگشت" in text:
        await message.answer(
            "🖼 لطفاً تصاویر چک را ارسال فرمایید (حداکثر ۳ عکس):",
            reply_markup=back_only_kb
        )
        await state.set_state(Form.check_images)
        return


@check_router.message(Form.check_attachment_title)
async def check_attachment_title_handler(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    data = await state.get_data()
    mandatory_sent = data.get("_mandatory_proxy_sent", True)

    if text == "⏭ رد کردن (بدون مدرک)":
        if not mandatory_sent:
            await message.answer(
                "⚠️ ارسال تصویر *مدرک نمایندگی* برای شخص حقوقی اجباری است.\n\n"
                "لطفاً تصویر مدرک را ارسال فرمایید.")
            return
        await _ask_check_branch(message, state)
        return

    if text == "🔙 بازگشت":
        data2 = await state.get_data()
        count = len(data2.get("check_images", []))
        await message.answer(
            "آیا تصویر یا مدرک دیگری دارید؟",
            reply_markup=get_check_more_images_kb(count, MAX_CHECK_IMAGES))
        await state.set_state(Form.check_more_images)
        return

    if text == "🔹 عنوان مهم نیست (سایر مستندات)":
        title = "مستندات"
    else:
        title = text

    await state.update_data(_current_attachment_title=title, _current_attachment_images=[])
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    manage_kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ اتمام ارسال تصاویر")],
            [KeyboardButton(text="🔙 بازگشت")],
        ], resize_keyboard=True
    )
    await message.answer(
        f"✅ عنوان «*{title}*» ثبت شد.\n\n"
        "🖼 لطفاً تصاویر مربوط به این مدرک را به صورت *عکس (Photo)* ارسال فرمایید.\n"
        "⚠️ فقط فرمت *JPG / JPEG* قابل قبول است.\n\n"
        f"پس از ارسال همه تصاویر، دکمه *«اتمام ارسال تصاویر»* را بفشارید.\n"
        f"(حداکثر {MAX_ATTACHMENT_IMAGES} تصویر)",
        reply_markup=manage_kb)
    await state.set_state(Form.check_attachment_images)


@check_router.message(Form.check_attachment_images, F.photo)
async def check_receive_attachment_photo(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    att_images = data.get("_current_attachment_images", [])

    if len(att_images) >= MAX_ATTACHMENT_IMAGES:
        await message.answer(
            f"⛔ حداکثر *{MAX_ATTACHMENT_IMAGES} تصویر* در هر عنوان مجاز است.\n\n"
            f"اگر مدرک بیشتری دارید، ابتدا دکمه «اتمام ارسال تصاویر» را بزنید\n"
            f"و سپس عنوان جدیدی انتخاب کنید.")
        return

    file_id = message.photo[-1].file_id
    att_images.append(file_id)
    await state.update_data(_current_attachment_images=att_images)

    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    manage_kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ اتمام ارسال تصاویر")],
            [KeyboardButton(text="🔙 بازگشت")],
        ], resize_keyboard=True)
    remaining = MAX_ATTACHMENT_IMAGES - len(att_images)
    await message.answer(
        f"✅ تصویر شماره *{len(att_images)}* دریافت شد.\n"
        f"مجموع تصاویر این مدرک: *{len(att_images)}* از {MAX_ATTACHMENT_IMAGES}\n\n"
        f"({remaining} جای باقیمانده)",
        reply_markup=manage_kb)


@check_router.message(Form.check_attachment_images)
async def check_attachment_images_text_fallback(message: Message, state: FSMContext):
    """هدلر متنی fallback برای مرحله ارسال تصاویر پیوست."""
    if message.text and "بازگشت" in message.text:
        data = await state.get_data()
        mandatory_sent = data.get("_mandatory_proxy_sent", True)
        if mandatory_sent:
            await message.answer(
                "📎 لطفاً *عنوان مدرک* را وارد فرمایید:\n\n"
                "_(مثلاً: گواهی عدم پرداخت، قرارداد و ...)_",
                reply_markup=check_attachment_title_kb)
            await state.set_state(Form.check_attachment_title)
        else:
            check_images = data.get("check_images", [])
            await message.answer(
                "آیا تصویر یا مدرک دیگری دارید؟",
                reply_markup=get_check_more_images_kb(len(check_images), MAX_CHECK_IMAGES))
            await state.set_state(Form.check_more_images)
        return
    await message.answer(
        "⚠️ لطفاً *تصویر* ارسال فرمایید یا دکمه *«اتمام ارسال تصاویر»* را بزنید."
    )


@check_router.message(Form.check_attachment_images, F.text == "✅ اتمام ارسال تصاویر")
async def check_finish_attachment_images(message: Message, state: FSMContext):
    data = await state.get_data()
    att_images = data.get("_current_attachment_images", [])
    title = data.get("_current_attachment_title", "مستندات")
    mandatory_sent = data.get("_mandatory_proxy_sent", True)

    if not att_images:
        await message.answer("⚠️ حداقل یک تصویر باید ارسال کنید.")
        return

    attachment_groups = data.get("check_attachment_groups", [])
    attachment_groups.append({"title": title, "images": list(att_images)})

    if title == "مدرک نمایندگی":
        mandatory_sent = True

    await state.update_data(
        check_attachment_groups=attachment_groups,
        _mandatory_proxy_sent=mandatory_sent,
        _current_attachment_images=[])

    await message.answer(
        f"✅ مدرک *{title}* با *{len(att_images)} تصویر* ثبت شد.\n\n"
        "آیا مدرک دیگری نیز دارید؟",
        reply_markup=check_attachment_more_kb)
    await state.set_state(Form.check_attachment_more)


@check_router.message(Form.check_attachment_more)
async def check_attachment_more_handler(message: Message, state: FSMContext):
    text = message.text or ""
    if text == "➕ بله، عنوان و مدرک دیگر دارم":
        await message.answer(
            "📎 لطفاً *عنوان مدرک* بعدی را وارد فرمایید:",
            reply_markup=check_attachment_title_kb)
        await state.set_state(Form.check_attachment_title)
    elif text == "✅ خیر، ادامه به انتخاب دادگاه":
        await _ask_check_branch(message, state)
    elif "بازگشت" in text:
        await message.answer(
            "آیا مدرک دیگری دارید؟",
            reply_markup=check_attachment_more_kb)
        await state.set_state(Form.check_attachment_more)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۱۱ — انتخاب صلاحیت دادگاه
# ══════════════════════════════════════════════════════════════════════════════
async def _ask_check_branch(message: Message, state: FSMContext):
    await message.answer(
        "🏛 *مرحله ۱۱:* لطفاً از طریق جدول زیر، *صلاحیت دادگاه* خود را انتخاب کنید:",
        reply_markup=create_branches_keyboard(ROOT_NODES, page=0, parent_id=None))
    await state.set_state(Form.check_branch_code)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۱۲ — پیش‌نمایش و تایید
# ══════════════════════════════════════════════════════════════════════════════
def build_check_preview(data: dict) -> str:
    request_title = data.get("check_request_title", "---")
    amount = data.get("check_amount", 0)
    khasteh_text = data.get("check_khasteh_text", "---")
    tracking_no = data.get("check_tracking_no", "---")
    plaintiffs = data.get("check_plainiffs", [])
    defendants = data.get("check_defendants", [])
    witnesses = data.get("check_witnesses", [])
    check_text = data.get("check_text", "---")
    extra_text = data.get("check_extra_text", "")
    images = data.get("check_images", [])
    branch_name = data.get("check_branch_name", "---")
    branch_code = data.get("check_branch_code", "---")

    def _person_line(p, idx):
        ptype = p.get("person_type", "")
        nat_id = p.get("national_id", "")
        if ptype == "شخص حقوقی":
            company_id = p.get("company_id", "")
            rep = p.get("representative_type", "")
            return f"  {idx}. {ptype} | شناسه: `{company_id}` | {rep}: `{nat_id}`"
        return f"  {idx}. {ptype} | کدملی: `{nat_id}`"

    plaintiffs_text = "\n".join([_person_line(p, i+1) for i, p in enumerate(plaintiffs)]) or "  (ندارد)"
    defendants_text = "\n".join([_person_line(p, i+1) for i, p in enumerate(defendants)]) or "  (ندارد)"
    witnesses_text = "\n".join([f"  {i+1}. کدملی: `{w.get('national_id', '')}`" for i, w in enumerate(witnesses)]) or "  (ندارد)"

    text_preview = check_text[:200] + "..." if len(check_text) > 200 else check_text
    text_preview = _escape_md(text_preview)
    khasteh_preview = khasteh_text[:150] + "..." if len(khasteh_text) > 150 else khasteh_text
    khasteh_preview = _escape_md(khasteh_preview)

    return (
        f"🏦 *پیش‌نمایش دادخواست چک:*\n\n"
        f"📌 عنوان خواسته: *{_escape_md(request_title)}*\n\n"
        f"💰 مبلغ چک: *{_fmt(amount)} ریال*\n\n"
        f"📄 عنوان خواسته (متن):\n  {khasteh_preview}\n\n"
        f"🔢 کدرهگیری: `{_escape_md(tracking_no)}`\n\n"
        f"👤 خواهان(ها):\n{plaintiffs_text}\n\n"
        f"👥 خوانده(ها):\n{defendants_text}\n\n"
        f"🔍 مطلع/گواه:\n{witnesses_text}\n\n"
        f"📋 شرح متن:\n  {text_preview}\n"
    ) + (f"\n📝 توضیحات اضافی: {_escape_md(extra_text)}\n" if extra_text else "") + (
        f"🖼 تصاویر: {len(images)} تصویر\n\n"
    ) + (
        f"🏛 صلاحیت دادگاه: *{_escape_md(branch_name)}* (کد: `{branch_code}`)\n\n"
        f"آیا اطلاعات فوق صحیح است؟"
    )


async def _go_to_check_preview(message: Message, state: FSMContext):
    data = await state.get_data()
    preview = build_check_preview(data)
    try:
        await message.answer(preview, reply_markup=check_confirm_kb)
    except Exception:
        await message.answer(preview, reply_markup=check_confirm_kb)
    await state.set_state(Form.check_confirm)



@check_router.message(Form.check_confirm)
async def check_confirm_handler(message: Message, state: FSMContext, bot: Bot):
    text = message.text or ""

    if text == "✅ تایید و شروع ثبت":
        data = await state.get_data()
        user_id = message.from_user.id

        await message.answer(
            "⏳ *درخواست دادخواست چک تایید شد.*\n\n"
            "در حال ارسال به صف پردازش...",
            reply_markup=ReplyKeyboardRemove())

        await runtime_state.job_queue.put({
            "user_id": user_id,
            "query_type": "دادخواست_چک",
            "task_type": "CHECK_SUBMIT",
            "check_request_title": data.get("check_request_title", ""),
            "check_amount": data.get("check_amount", 0),
            "check_khasteh_text": data.get("check_khasteh_text", ""),
            "check_tracking_no": data.get("check_tracking_no", ""),
            "check_plainiffs": data.get("check_plainiffs", []),
            "check_defendants": data.get("check_defendants", []),
            "check_witnesses": data.get("check_witnesses", []),
            "check_text": data.get("check_text", ""),
            "check_text_html": data.get("check_text_html", ""),
            "check_extra_text": data.get("check_extra_text", ""),
            "check_images": data.get("check_images", []),
            "check_attachment_groups": data.get("check_attachment_groups", []),
            "check_branch_code": data.get("check_branch_code", ""),
            "check_branch_name": data.get("check_branch_name", ""),
            "check_branch_path": data.get("check_branch_path", ""),
            "check_docx_file_id": data.get("check_docx_file_id"),
            "check_docx_file_name": data.get("check_docx_file_name", ""),
        })

        await state.clear()
        return

    if text == "✏️ ویرایش اطلاعات":
        await message.answer(
            "✏️ *ویرایش اطلاعات:*\n\n"
            "کدام بخش را می‌خواهید ویرایش کنید؟\n\n"
            "⚠️ پس از ویرایش هر بخش، به *پیش‌نمایش* بازمی‌گردید.",
            reply_markup=check_edit_kb)
        await state.set_state(Form.check_edit_choice)
        return

    await message.answer("⚠️ لطفاً یکی از گزینه‌های زیر را انتخاب کنید:", reply_markup=check_confirm_kb)


@check_router.message(Form.check_confirm, F.text == "❌ انصراف")
async def check_cancel_handler(message: Message, state: FSMContext):
    await state.clear()
    from keyboards import flow_type_kb
    await message.answer(
        "❌ ثبت دادخواست چک لغو شد.",
        reply_markup=flow_type_kb)


# ══════════════════════════════════════════════════════════════════════════════
# منوی ویرایش
# ══════════════════════════════════════════════════════════════════════════════
@check_router.message(Form.check_edit_choice)
async def check_edit_choice_handler(message: Message, state: FSMContext):
    text = message.text or ""

    if text == "🔙 بازگشت به پیش‌نمایش":
        await _go_to_check_preview(message, state)
        return

    if text == "📝 ویرایش عنوان خواسته":
        await message.answer(
            "📝 لطفاً *عنوان خواسته* جدید را انتخاب فرمایید:",
            reply_markup=check_request_title_kb)
        await state.set_state(Form.check_request_title)
        return

    if text == "💰 ویرایش مبلغ چک":
        await message.answer(
            "💰 لطفاً *مبلغ چک* جدید را به *ریال* وارد فرمایید:\n_(فقط عدد)_",
            reply_markup=back_only_kb)
        await state.set_state(Form.check_amount)
        return

    if text == "📄 ویرایش عنوان خواسته (متن)":
        data = await state.get_data()
        request_title = data.get("check_request_title", "")
        if request_title == "صدور اجرائیه چک":
            suggested = "به موجب یک فقره چک به شماره ..."
        else:
            suggested = "به موجب ........ فقره چک..."
        await message.answer(
            f"📝 *متن پیشنهادی:*\n\n{suggested}\n\n"
            "متن جدید را ارسال فرمایید:",
            reply_markup=back_only_kb)
        await state.set_state(Form.check_khasteh_title)
        return

    if text == "🔢 ویرایش کدرهگیری":
        await message.answer(
            "🔢 لطفاً *کدرهگیری چک* جدید را ارسال بفرمائید:",
            reply_markup=back_only_kb)
        await state.set_state(Form.check_tracking_no)
        return

    if text == "👤 ویرایش خواهان(ها)":
        await state.update_data(check_plainiffs=[], _check_current_plaintiff={})
        await message.answer(
            "👤 لیست خواهان پاک شد.\n"
            "لطفاً مجدداً *نوع شخصیت خواهان* را انتخاب فرمایید:",
            reply_markup=create_ezhhar_declarant_person_type_kb())
        await state.set_state(Form.check_plaintiff_person_type)
        return

    if text == "👥 ویرایش خوانده(ها)":
        await state.update_data(check_defendants=[], _check_current_defendant={})
        await message.answer(
            "👥 لیست خوانده پاک شد.\n"
            "لطفاً مجدداً *نوع شخصیت خوانده* را انتخاب فرمایید:",
            reply_markup=create_check_person_type_kb())
        await state.set_state(Form.check_defendant_person_type)
        return

    if text == "🔍 ویرایش مطلع/گواه":
        await state.update_data(check_witnesses=[])
        await message.answer(
            "🔍 لیست مطلع/گواه پاک شد.\n"
            "لطفاً *کدملی مطلع/گواه* را ارسال فرمایید:\n"
            "_(یا گزینه «اتمام و ادامه» را بزنید)_",
            reply_markup=check_addressee_add_more_kb)
        await state.set_state(Form.check_witness_national_id)
        return

    if text == "📋 ویرایش شرح متن":
        await message.answer(
            "📋 لطفاً *شرح متن* جدید را ارسال فرمایید:",
            reply_markup=back_only_kb)
        await state.set_state(Form.check_text)
        return

    if text == "🖼 ویرایش تصاویر چک":
        await state.update_data(check_images=[])
        await _ask_check_images(message, state)
        return

    if text == "🏛 ویرایش صلاحیت دادگاه":
        await _ask_check_branch(message, state)
        return

    await message.answer("⚠️ لطفاً یکی از گزینه‌های زیر را انتخاب کنید:", reply_markup=check_edit_kb)


# ══════════════════════════════════════════════════════════════════════════════
# Callback برای انتخاب شعبه (صلاحیت دادگاه)
# ══════════════════════════════════════════════════════════════════════════════
@check_router.callback_query(F.data.startswith("br:"))
async def check_branch_callback(callback: CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    if current_state != Form.check_branch_code:
        return

    await callback.answer()

    data_parts = callback.data.split(":")
    action = data_parts[1]

    from branches import ID_TO_NODE, get_children, INDEX_TO_ID

    if action == "root":
        await callback.message.edit_text(
            "🏛 *انتخاب صلاحیت دادگاه*\n\n"
            "لطفاً از لیست زیر انتخاب کنید:",
            reply_markup=create_branches_keyboard(ROOT_NODES, page=0, parent_id=None))
        return

    idx = int(data_parts[2])
    node_id = INDEX_TO_ID.get(idx)

    if not node_id or node_id not in ID_TO_NODE:
        await callback.message.edit_text("❌ خطا: واحد مورد نظر یافت نشد.")
        return

    node = ID_TO_NODE[node_id]

    if action == "open":
        children = get_children(node_id)
        if not children:
            await callback.message.edit_text(
                f"ℹ️ واحد «{node.get('UnitName')}» فرزندی ندارد.")
            return
        page = int(data_parts[3]) if len(data_parts) > 3 else 0
        await callback.message.edit_text(
            f"📁 *{node.get('UnitName')}*\n\n"
            "لطفاً یکی از موارد زیر را انتخاب کنید:",
            reply_markup=create_branches_keyboard(children, page=page, parent_id=node_id))

    elif action == "page":
        page = int(data_parts[3]) if len(data_parts) > 3 else 0
        children = get_children(node_id)
        await callback.message.edit_reply_markup(
            reply_markup=create_branches_keyboard(children, page=page, parent_id=node_id)
        )

    elif action == "back":
        parent_id = INDEX_TO_ID.get(idx)
        if not parent_id or parent_id not in ID_TO_NODE:
            await callback.message.edit_text(
                "🏛 *انتخاب صلاحیت دادگاه*\n\n"
                "لطفاً از لیست زیر انتخاب کنید:",
                reply_markup=create_branches_keyboard(ROOT_NODES, page=0, parent_id=None))
            return
        parent_node = ID_TO_NODE[parent_id]
        children = get_children(parent_id)
        page = int(data_parts[3]) if len(data_parts) > 3 else 0
        await callback.message.edit_text(
            f"📁 *{parent_node.get('UnitName')}*\n\n"
            "لطفاً یکی از موارد زیر را انتخاب کنید:",
            reply_markup=create_branches_keyboard(children, page=page, parent_id=parent_id))

    elif action == "sel":
        branch_code = node.get("Code", "")
        if not branch_code:
            await callback.answer(
                "⚠️ این واحد فاقد کد است و قابل انتخاب نیست.",
                show_alert=True
            )
            return

        branch_name = node.get("UnitName", "")
        branch_path = node.get("Path", "")

        await state.update_data(
            check_branch_name=branch_name,
            check_branch_code=branch_code,
            check_branch_path=branch_path
        )

        await callback.message.answer(
            f"✅ *دادگاه انتخاب شد:*\n\n"
            f"📋 نام: *{branch_name}*\n"
            f"🔢 کد: `{branch_code}`")

        # رفتن به پیش‌نمایش
        await _go_to_check_preview(callback.message, state)

    elif action == "info":
        await callback.answer(
            "⚠️ این واحد فاقد کد است و قابل انتخاب نیست.",
            show_alert=True
        )
