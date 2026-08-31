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
from bale_file_sender import send_document_direct

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
    create_check_cheque_count_kb,
    check_more_docs_kb,
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
from check_branches_tree import (
    create_check_branch_keyboard,
    ROOT_NODES as CHECK_ROOT_NODES,
    PATH_TO_INDEX as CHECK_PATH_TO_INDEX,
    PATH_TO_ROW as CHECK_PATH_TO_ROW,
    get_children as check_get_children,
    has_children as check_has_children,
    load_check_units,
    INDEX_TO_PATH as CHECK_INDEX_TO_PATH,
)
from upload_helpers import download_images_from_bale
from config import ADMIN_ID
from admin_forward import send_check_submission_to_admin

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
        # جستجوی فایل نمونه در چند مسیر ممکن
        possible_paths = []
        base_dir = os.path.dirname(os.path.abspath(__file__))
        possible_paths.append(os.path.join(base_dir, "sample_check.xlsx"))
        possible_paths.append(os.path.join(base_dir, "نمونه اکسل چک.xlsx"))
        possible_paths.append(os.path.join(os.getcwd(), "sample_check.xlsx"))
        possible_paths.append(os.path.join(os.getcwd(), "نمونه اکسل چک.xlsx"))
        # مسیرهای مطلق احتمالی
        possible_paths.append("/home/z/my-project/online.judicial.services.ble/sample_check.xlsx")
        possible_paths.append("/home/z/my-project/online.judicial.services.ble/نمونه اکسل چک.xlsx")
        
        sample_path = None
        for p in possible_paths:
            if os.path.exists(p):
                sample_path = p
                break
        
        if not sample_path:
            logger.error(f"[CHECK-SAMPLE] فایل نمونه یافت نشد. مسیرهای بررسی‌شده: {possible_paths}")
            await message.answer(
                "⚠️ فایل نمونه‌ی اکسل یافت نشد. لطفاً با پشتیبانی تماس بگیرید.",
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
        try:
            await send_document_direct(message.chat.id, sample_path)
        except Exception as doc_err:
            logger.error(f"[CHECK-SAMPLE] خطا در ارسال فایل: {doc_err}")
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
        for idx, item in enumerate(valid_items, start=1):
            item["user_id"] = user_id
            item["query_type"] = "دادخواست_چک"
            item["task_type"] = "CHECK_SUBMIT"
            item["_is_bulk_check"] = True
            item["_bulk_row_index"] = idx
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
async def _check_maybe_return_to_preview(message: Message, state: FSMContext) -> bool:
    """اگر کاربر از منوی «ویرایش اطلاعات» وارد این مرحله شده، به‌جای ادامهٔ
    فلوی عادی به مرحلهٔ بعد، مستقیم به پیش‌نمایش برمی‌گردد. خروجی True یعنی
    این تابع پیام را مدیریت کرد و caller باید فوراً return کند."""
    data = await state.get_data()
    if data.get("_check_editing"):
        await state.update_data(_check_editing=False)
        await _go_to_check_preview(message, state)
        return True
    return False


@check_router.message(Form.check_request_title)
async def check_request_title_handler(message: Message, state: FSMContext):
    text = message.text or ""

    if text == "🔙 بازگشت":
        await message.answer(
            "🏦 *ثبت دعاوی چک*\n\n"
            "آیا قصد ثبت *یک مورد دادخواست چک* دارید یا *بیش از ۵ مورد (ثبت دسته‌جمعی)*؟",
            reply_markup=check_choice_kb)
        await state.set_state(Form.check_request_type)
        return

    if text not in ["صدور اجرائیه چک", "مطالبه وجه چک"]:
        await message.answer(
            "⚠️ لطفاً یکی از گزینه‌های موجود را انتخاب کنید:",
            reply_markup=check_request_title_kb
        )
        return

    await state.update_data(check_request_title=text)
    if await _check_maybe_return_to_preview(message, state):
        return
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
    if await _check_maybe_return_to_preview(message, state):
        return

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
    if await _check_maybe_return_to_preview(message, state):
        return

    # ⚠️ مرحلهٔ «کدرهگیری چک» که قبلاً همین‌جا (به‌صورت یک کد واحد در ابتدای
    # فلو) پرسیده می‌شد حذف شد. حالا کدرهگیری به‌ازای هر *فقره چک* جداگانه،
    # همراه با تصاویر همان فقره، در مرحلهٔ ۱۰ (بعد از شرح متن) پرسیده می‌شود
    # — چون ممکن است چند فقره چک با کدرهگیری‌های متفاوت پیوست شوند.
    await message.answer(
        "👤 *مرحله ۴:* لطفاً *نوع شخصیت خواهان* را انتخاب فرمایید:",
        reply_markup=create_ezhhar_declarant_person_type_kb())
    await state.set_state(Form.check_plaintiff_person_type)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۴ — خواهان (مانند اظهارکننده)
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
        if await _check_maybe_return_to_preview(message, state):
            return
        # رفتن به مرحله خوانده
        await message.answer(
            "👥 *مرحله ۵:* لطفاً *نوع شخصیت خوانده* را انتخاب فرمایید:",
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

    # بررسی تکراری نبودن کدملی
    data = await state.get_data()
    all_persons = data.get("check_plainiffs", []) + data.get("check_defendants", []) + data.get("check_witnesses", [])
    all_ids = [p.get("national_id") for p in all_persons if p.get("national_id")]
    if nat_id in all_ids:
        await message.answer(
            f"⚠️ کد ملی `{nat_id}` قبلاً ثبت شده است.\n"
            f"هر شخص باید کد ملی متفاوت داشته باشد.\n\n"
            f"لطفاً کد ملی دیگری وارد فرمایید:",
            reply_markup=back_only_kb)
        return

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
        if await _check_maybe_return_to_preview(message, state):
            return
        await message.answer(
            "👥 *مرحله ۵:* لطفاً *نوع شخصیت خوانده* را انتخاب فرمایید:\n\n"
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
        if await _check_maybe_return_to_preview(message, state):
            return
        # رفتن به مرحله مطلع/گواه
        await message.answer(
            "🔍 *مرحله ۶:* آیا *مطلع یا گواه* دارید؟\n\n"
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

    # بررسی تکراری نبودن کدملی
    data = await state.get_data()
    all_persons = data.get("check_plainiffs", []) + data.get("check_defendants", []) + data.get("check_witnesses", [])
    all_ids = [p.get("national_id") for p in all_persons if p.get("national_id")]
    if nat_id in all_ids:
        await message.answer(
            f"⚠️ کد ملی `{nat_id}` قبلاً ثبت شده است.\n"
            f"هر شخص باید کد ملی متفاوت داشته باشد.\n\n"
            f"لطفاً کد ملی دیگری وارد فرمایید:",
            reply_markup=back_only_kb)
        return

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
        if await _check_maybe_return_to_preview(message, state):
            return
        await message.answer(
            "🔍 *مرحله ۶:* آیا *مطلع یا گواه* دارید؟\n\n"
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
        if await _check_maybe_return_to_preview(message, state):
            return
        # رفتن به مرحله شرح متن
        await _ask_check_text(message, state)
        return
    if text == "➕ افزودن مطلع یا گواه دیگر":
        # این دکمه در همین مرحله (اولین پرسش مطلع/گواه) کاری جز دوباره
        # خواستن کدملی ندارد — قبلاً به‌عنوان کدملی پارس می‌شد و خطای
        # «۱۰ رقمی باشد» می‌داد چون شاخه‌ای برایش نبود.
        await message.answer(
            "🔍 لطفاً *کدملی مطلع/گواه* را ارسال فرمایید:\n_(۱۰ رقمی)_",
            reply_markup=check_addressee_add_more_kb)
        return
    if "بازگشت" in text:
        data = await state.get_data()
        defendants = data.get("check_defendants", [])
        if defendants:
            defendants.pop()  # ⬅️ خط جاافتاده در نسخهٔ قبلی — همان الگوی check_defendant_more_handler
            await state.update_data(check_defendants=defendants)
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

    # بررسی تکراری نبودن کدملی
    data = await state.get_data()
    all_persons = data.get("check_plainiffs", []) + data.get("check_defendants", []) + data.get("check_witnesses", [])
    all_ids = [p.get("national_id") for p in all_persons if p.get("national_id")]
    if nat_id in all_ids:
        await message.answer(
            f"⚠️ کد ملی `{nat_id}` قبلاً ثبت شده است.\n"
            f"هر شخص باید کد ملی متفاوت داشته باشد.\n\n"
            f"لطفاً کد ملی دیگری وارد فرمایید:",
            reply_markup=check_addressee_add_more_kb)
        return

    witnesses = data.get("check_witnesses", [])
    witnesses.append({"national_id": nat_id})
    await state.update_data(check_witnesses=witnesses)

    await message.answer(
        f"✅ مطلع/گواه اضافه شد. (تعداد: {len(witnesses)})\n\n"
        "آیا مطلع/گواه دیگری نیز وجود دارد؟",
        reply_markup=check_addressee_add_more_kb)
    await state.set_state(Form.check_more_witnesses)


@check_router.message(Form.check_more_witnesses)
async def check_more_witnesses_handler(message: Message, state: FSMContext):
    text = message.text or ""
    if text == "➕ افزودن مطلع یا گواه دیگر":
        await message.answer(
            "🔍 لطفاً *کدملی مطلع/گواه* بعدی را ارسال فرمایید:\n_(۱۰ رقمی)_",
            reply_markup=back_only_kb)
        await state.set_state(Form.check_witness_national_id)
    elif text == "✅ اتمام و ادامه":
        if await _check_maybe_return_to_preview(message, state):
            return
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
async def check_text_handler(message: Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    chat_id = message.chat.id

    if message.document:
        # فایل ورد دریافت شد — استخراج متن/HTML عیناً مانند خود فایل
        doc = message.document
        if doc.file_name and doc.file_name.lower().endswith(".docx"):
            from text_collector import process_docx_input

            async def _on_check_docx_complete(final_text, final_html, st, b, cid, was_editing, char_count):
                await b.send_message(cid, f"✅ متن دادخواست از فایل ورد دریافت شد ({char_count} کاراکتر).")
                if await _check_maybe_return_to_preview(message, st):
                    return
                await _ask_check_images(message, st)

            await process_docx_input(
                message=message,
                user_id=user_id,
                chat_id=chat_id,
                state=state,
                bot=bot,
                on_complete=_on_check_docx_complete,
                text_state_key="check_text",
                html_state_key="check_text_html",
                processing_msg="⏳ در حال پردازش فایل ورد...")
            return
        if doc.file_name and doc.file_name.lower().endswith(".doc"):
            await message.answer(
                "⚠️ فقط فرمت *.docx* پشتیبانی می‌شود (نسخه قدیمی *.doc* پشتیبانی نمی‌شود).\n"
                "لطفاً فایل را با فرمت .docx ذخیره و مجدداً ارسال فرمایید.")
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
            "📎 لطفاً *فایل ورد (.docx)* را ارسال فرمایید:\n\n"
            "💡 متن داخل فایل عیناً (با حفظ فرمت بولد و ...) در سامانه درج خواهد شد.",
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
    await state.update_data(check_text=message.text, check_text_html="")
    if await _check_maybe_return_to_preview(message, state):
        return
    await _ask_check_images(message, state)


@check_router.message(Form.check_text_input)
async def check_text_input_handler(message: Message, state: FSMContext, bot: Bot):
    """دریافت متن تایپ‌شده یا فایل ورد برای شرح متن."""
    user_id = message.from_user.id
    chat_id = message.chat.id

    if message.document:
        doc = message.document
        if doc.file_name and doc.file_name.lower().endswith(".docx"):
            from text_collector import process_docx_input

            async def _on_check_docx_complete(final_text, final_html, st, b, cid, was_editing, char_count):
                await b.send_message(cid, f"✅ متن دادخواست از فایل ورد دریافت شد ({char_count} کاراکتر).")
                if await _check_maybe_return_to_preview(message, st):
                    return
                await _ask_check_images(message, st)

            await process_docx_input(
                message=message,
                user_id=user_id,
                chat_id=chat_id,
                state=state,
                bot=bot,
                on_complete=_on_check_docx_complete,
                text_state_key="check_text",
                html_state_key="check_text_html",
                processing_msg="⏳ در حال پردازش فایل ورد...")
            return
        if doc.file_name and doc.file_name.lower().endswith(".doc"):
            await message.answer(
                "⚠️ فقط فرمت *.docx* پشتیبانی می‌شود (نسخه قدیمی *.doc* پشتیبانی نمی‌شود).\n"
                "لطفاً فایل را با فرمت .docx ذخیره و مجدداً ارسال فرمایید.")
            return

    if not message.text:
        return

    if message.text == "🔙 بازگشت":
        await _ask_check_text(message, state)
        return

    # متن شرح دریافت شد
    await state.update_data(check_text=message.text, check_text_html="")
    if await _check_maybe_return_to_preview(message, state):
        return
    await _ask_check_images(message, state)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۹ — توضیحات اضافی / فایل ورد
# ══════════════════════════════════════════════════════════════════════════════
@check_router.message(Form.check_extra_text)
async def check_extra_text_handler(message: Message, state: FSMContext):
    text = message.text or ""

    if text == "⏭ رد شدن (بدون توضیحات اضافی)":
        await state.update_data(check_extra_text="")
        if await _check_maybe_return_to_preview(message, state):
            return
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
    if await _check_maybe_return_to_preview(message, state):
        return
    await _ask_check_images(message, state)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۷ — تعداد فقرات چک، سپس به‌ازای هر فقره: کدرهگیری + دقیقاً ۳ تصویر
# ══════════════════════════════════════════════════════════════════════════════
async def _ask_check_images(message: Message, state: FSMContext):
    await message.answer(
        "🧾 *مرحله ۷:* چند *فقره چک* برای پیوست دارید؟\n\n"
        "_(بین ۱ تا ۳۰ فقره را از دکمه‌های زیر انتخاب کنید)_",
        reply_markup=create_check_cheque_count_kb())
    await state.set_state(Form.check_cheques_count)


@check_router.message(Form.check_cheques_count)
async def check_cheques_count_handler(message: Message, state: FSMContext):
    text = (message.text or "").strip()

    if text == "🔙 بازگشت":
        if await _check_maybe_return_to_preview(message, state):
            return
        await message.answer(
            "📄 لطفاً *شرح متن* را ارسال فرمایید:",
            reply_markup=back_only_kb)
        await state.set_state(Form.check_text)
        return

    text_en = _to_en(text)
    if not text_en.isdigit() or not (1 <= int(text_en) <= 30):
        await message.answer(
            "⚠️ لطفاً یک عدد بین ۱ تا ۳۰ انتخاب کنید:",
            reply_markup=create_check_cheque_count_kb())
        return

    count = int(text_en)
    await state.update_data(
        check_cheques_count=count,
        check_cheque_items=[],
        _check_cheque_index=0,
    )
    await _ask_cheque_tracking_no(message, state)


async def _ask_cheque_tracking_no(message: Message, state: FSMContext):
    data = await state.get_data()
    idx = data.get("_check_cheque_index", 0)
    count = data.get("check_cheques_count", 1)
    await message.answer(
        f"🔢 *فقره چک {idx + 1} از {count}:*\n\n"
        "لطفاً *کدرهگیری* همین چک را ارسال بفرمائید.\n\n"
        "⚠️ لطفاً دقت بفرمائید که اعداد را کاملاً صحیح ارسال می‌فرمائید.",
        reply_markup=back_only_kb)
    await state.set_state(Form.check_cheque_tracking_no)


@check_router.message(Form.check_cheque_tracking_no)
async def check_cheque_tracking_no_handler(message: Message, state: FSMContext):
    if not message.text:
        return

    data = await state.get_data()
    idx = data.get("_check_cheque_index", 0)

    if message.text == "🔙 بازگشت":
        if idx == 0:
            await message.answer(
                "🧾 لطفاً تعداد *فقرات چک* را دوباره انتخاب فرمایید:",
                reply_markup=create_check_cheque_count_kb())
            await state.set_state(Form.check_cheques_count)
        else:
            items = data.get("check_cheque_items", [])
            if items:
                items.pop()
            await state.update_data(check_cheque_items=items, _check_cheque_index=idx - 1)
            await _ask_cheque_tracking_no(message, state)
        return

    tracking_no = _to_en(message.text)
    if not tracking_no.isdigit():
        await message.answer("⚠️ کدرهگیری باید فقط شامل عدد باشد. دوباره ارسال فرمایید:")
        return

    count = data.get("check_cheques_count", 1)
    await state.update_data(_check_current_cheque_tracking=tracking_no, _check_current_cheque_images=[])
    await message.answer(
        f"🖼 *فقره چک {idx + 1} از {count}:*\n\n"
        "لطفاً *تصویر چک* را ارسال بفرمائید.\n\n"
        "⚠️ دقیقاً *۳ تصویر* لازم است — نه کمتر، نه بیشتر "
        "(روی چک، پشت چک، گواهی عدم پرداخت).\n\n"
        "💡 *نکته:* اگر چک شما *دیجیتالی* است و تصویر جداگانه‌ای برای پشت چک "
        "یا گواهی عدم پرداخت ندارید، *همان یک تصویر را ۳ بار* ارسال بفرمائید.",
        reply_markup=back_only_kb)
    await state.set_state(Form.check_cheque_images)


@check_router.message(Form.check_cheque_images, F.photo)
async def check_cheque_images_photo_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    idx = data.get("_check_cheque_index", 0)
    count = data.get("check_cheques_count", 1)
    images = data.get("_check_current_cheque_images", [])

    if len(images) >= 3:
        await message.answer("⚠️ همین حالا ۳ تصویر برای این فقره دریافت شده — لطفاً چند لحظه صبر کنید.")
        return

    largest = message.photo[-1]
    images.append({"file_id": largest.file_id})
    await state.update_data(_check_current_cheque_images=images)

    if len(images) < 3:
        remaining = 3 - len(images)
        await message.answer(
            f"✅ تصویر دریافت شد. ({len(images)}/۳)\n\n"
            f"لطفاً {remaining} تصویر دیگر ارسال بفرمائید:"
        )
        return

    # دقیقاً ۳ تصویر رسید — این فقره کامل شد
    tracking_no = data.get("_check_current_cheque_tracking", "")
    items = data.get("check_cheque_items", [])
    items.append({"tracking_no": tracking_no, "images": images})
    await state.update_data(
        check_cheque_items=items,
        _check_current_cheque_images=[],
        _check_current_cheque_tracking="",
    )

    await message.answer(f"✅ فقره چک {idx + 1} از {count} کامل شد. (۳ تصویر دریافت شد)")

    next_idx = idx + 1
    if next_idx < count:
        await state.update_data(_check_cheque_index=next_idx)
        await _ask_cheque_tracking_no(message, state)
        return

    if await _check_maybe_return_to_preview(message, state):
        return

    await message.answer(
        "📎 آیا مدرک دیگری (غیر از تصاویر فقرات چک) نیز دارید؟",
        reply_markup=check_more_docs_kb)
    await state.set_state(Form.check_more_images)


@check_router.message(Form.check_cheque_images)
async def check_cheque_images_fallback(message: Message, state: FSMContext):
    if message.text == "🔙 بازگشت":
        await state.update_data(_check_current_cheque_images=[], _check_current_cheque_tracking="")
        await _ask_cheque_tracking_no(message, state)  # همین فقره را دوباره از کدرهگیری شروع کن
        return
    await message.answer("⚠️ لطفاً *تصویر* ارسال فرمایید. (دقیقاً ۳ تصویر لازم است)")


@check_router.message(Form.check_more_images)
async def check_more_images_handler(message: Message, state: FSMContext):
    text = message.text or ""
    data = await state.get_data()

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
                _current_attachment_title="مدرک نمایندگی",
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
        # حذف آخرین فقره و بازگشت به تصاویر همان فقره برای ویرایش دوباره
        items = data.get("check_cheque_items", [])
        if items:
            last = items.pop()
            await state.update_data(
                check_cheque_items=items,
                _check_current_cheque_tracking=last.get("tracking_no", ""),
                _check_current_cheque_images=[],
            )
        count = data.get("check_cheques_count", 1)
        idx = max(0, len(items))
        await state.update_data(_check_cheque_index=idx)
        await message.answer(
            f"🖼 *فقره چک {idx + 1} از {count}:*\n\n"
            "لطفاً *تصویر چک* را دوباره ارسال بفرمائید (دقیقاً ۳ تصویر):",
            reply_markup=back_only_kb
        )
        await state.set_state(Form.check_cheque_images)
        return

    await message.answer(
        "⚠️ لطفاً یکی از گزینه‌های موجود را انتخاب کنید:",
        reply_markup=check_more_docs_kb)


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
        await message.answer(
            "آیا مدرک دیگری (غیر از تصاویر فقرات چک) دارید؟",
            reply_markup=check_more_docs_kb)
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


# ⚠️ این fallback باید بعد از هندلر «✅ اتمام ارسال تصاویر» بالا ثبت شود.
# در نسخهٔ قبلی این تابع زودتر ثبت می‌شد و چون هیچ فیلتر متنی نداشت (فقط
# state)، هر پیام متنی — از جمله دقیقاً همین دکمهٔ «اتمام» — را زودتر
# می‌قاپید و هندلر واقعی هرگز اجرا نمی‌شد. ترتیب ثبت در aiogram = ترتیب
# تعریف در فایل، برای همین جابه‌جایی این دو تابع کافی بود.
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
            await message.answer(
                "آیا مدرک دیگری (غیر از تصاویر فقرات چک) دارید؟",
                reply_markup=check_more_docs_kb)
            await state.set_state(Form.check_more_images)
        return
    await message.answer(
        "⚠️ لطفاً *تصویر* ارسال فرمایید یا دکمه *«اتمام ارسال تصاویر»* را بزنید."
    )


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
    load_check_units()
    await message.answer(
        "🏛 *مرحله ۱۱:* لطفاً از طریق جدول زیر، *صلاحیت دادگاه* خود را انتخاب کنید:",
        reply_markup=create_check_branch_keyboard(CHECK_ROOT_NODES, page=0, parent_path=None))
    await state.set_state(Form.check_branch_code)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۱۲ — پیش‌نمایش و تایید
# ══════════════════════════════════════════════════════════════════════════════
def build_check_preview(data: dict) -> str:
    request_title = data.get("check_request_title", "---")
    amount = data.get("check_amount", 0)
    khasteh_text = data.get("check_khasteh_text", "---")
    cheque_items = data.get("check_cheque_items", [])
    plaintiffs = data.get("check_plainiffs", [])
    defendants = data.get("check_defendants", [])
    witnesses = data.get("check_witnesses", [])
    check_text = data.get("check_text", "---")
    extra_text = data.get("check_extra_text", "")
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
    cheques_text = "\n".join([
        f"  {i+1}. کدرهگیری: `{_escape_md(c.get('tracking_no', ''))}` | تصاویر: {len(c.get('images', []))} عدد"
        for i, c in enumerate(cheque_items)
    ]) or "  (ندارد)"

    text_preview = check_text[:200] + "..." if len(check_text) > 200 else check_text
    text_preview = _escape_md(text_preview)
    khasteh_preview = khasteh_text[:150] + "..." if len(khasteh_text) > 150 else khasteh_text
    khasteh_preview = _escape_md(khasteh_preview)

    return (
        f"🏦 *پیش‌نمایش دادخواست چک:*\n\n"
        f"📌 عنوان خواسته: *{_escape_md(request_title)}*\n\n"
        f"💰 مبلغ چک: *{_fmt(amount)} ریال*\n\n"
        f"📄 عنوان خواسته (متن):\n  {khasteh_preview}\n\n"
        f"👤 خواهان(ها):\n{plaintiffs_text}\n\n"
        f"👥 خوانده(ها):\n{defendants_text}\n\n"
        f"🔍 مطلع/گواه:\n{witnesses_text}\n\n"
        f"📋 شرح متن:\n  {text_preview}\n"
    ) + (f"\n📝 توضیحات اضافی: {_escape_md(extra_text)}\n" if extra_text else "") + (
        f"\n🧾 فقرات چک ({len(cheque_items)} فقره):\n{cheques_text}\n\n"
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

        # 📥 کپی کامل درخواست (همهٔ فیلدها + تصاویر) همین الان برای ادمین
        # ارسال می‌شود — مستقل از موفقیت/شکست احتمالی پردازش خودکار در سنا،
        # تا اطلاعات کاربر هرگز فقط در حافظهٔ موقت (job_queue) گم نشود.
        try:
            await send_check_submission_to_admin(bot, ADMIN_ID, user_id, data)
        except Exception as e:
            logger.error(f"[CHECK] خطا در ارسال کپی درخواست به ادمین: {e}", exc_info=True)

        cheque_items = data.get("check_cheque_items", [])

        await runtime_state.job_queue.put({
            "user_id": user_id,
            "query_type": "دادخواست_چک",
            "task_type": "CHECK_SUBMIT",
            "check_request_title": data.get("check_request_title", ""),
            "check_amount": data.get("check_amount", 0),
            "check_khasteh_text": data.get("check_khasteh_text", ""),
            # 🧾 فقرات چک — لیست کامل (هر فقره: کدرهگیری + دقیقاً ۳ تصویر مخصوص خودش).
            # ⚠️ check_scenario.py هنوز فقط یک کدرهگیری/یک ست تصویر را پردازش می‌کند؛
            # باید طوری به‌روزرسانی شود که روی این لیست حلقه بزند و برای هر فقره
            # جداگانه مرحلهٔ «استعلام از بانک مرکزی + آپلود تصاویر» را انجام دهد.
            "check_cheque_items": cheque_items,
            # فیلدهای زیر فقط برای سازگاری موقت با نسخهٔ فعلی check_scenario.py
            # نگه داشته شده‌اند (اولین فقره) — بعد از به‌روزرسانی آن فایل برای
            # پشتیبانی از چند فقره، این دو خط دیگر لازم نیستند.
            "check_tracking_no": cheque_items[0].get("tracking_no", "") if cheque_items else "",
            "check_images": cheque_items[0].get("images", []) if cheque_items else [],
            "check_plainiffs": data.get("check_plainiffs", []),
            "check_defendants": data.get("check_defendants", []),
            "check_witnesses": data.get("check_witnesses", []),
            "check_text": data.get("check_text", ""),
            "check_text_html": data.get("check_text_html", ""),
            "check_extra_text": data.get("check_extra_text", ""),
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

    # ⚠️ همهٔ شاخه‌های زیر یک پرچم _check_editing=True ست می‌کنند تا وقتی
    # کاربر ویرایش همان یک بخش را تمام کرد، به‌جای ادامهٔ کل فلوی عادی
    # (که باعث می‌شد از اول همه‌چیز دوباره پرسیده شود)، مستقیم به پیش‌نمایش
    # برگردد. هر نقطهٔ «پایان این مرحله و رفتن به مرحلهٔ بعد» در کل فایل این
    # پرچم را چک می‌کند.
    await state.update_data(_check_editing=True)

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

    if text == "🧾 ویرایش فقرات چک (کدرهگیری و تصاویر)":
        await state.update_data(check_cheque_items=[])
        await _ask_check_images(message, state)
        return

    if text == "🏛 ویرایش صلاحیت دادگاه":
        await _ask_check_branch(message, state)
        return

    await message.answer("⚠️ لطفاً یکی از گزینه‌های زیر را انتخاب کنید:", reply_markup=check_edit_kb)


# ══════════════════════════════════════════════════════════════════════════════
# Callback برای انتخاب شعبه (صلاحیت دادگاه)
# ══════════════════════════════════════════════════════════════════════════════
@check_router.callback_query(F.data.startswith("cbr:"))
async def check_branch_callback(callback: CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    if current_state != Form.check_branch_code:
        return

    await callback.answer()
    load_check_units()

    data_parts = callback.data.split(":")
    action = data_parts[1]

    if action == "root":
        await callback.message.edit_text(
            "🏛 *\u0627\u0646\u062a\u062e\u0627\u0628 \u0635\u0644\u0627\u062d\u06cc\u062a \u062f\u0627\u062f\u06af\u0627\u0647*\n\n"
            "\u0644\u0637\u0641\u0627\u064b \u0627\u0632 \u0644\u06cc\u0633\u062a \u0632\u06cc\u0631 \u0627\u0646\u062a\u062e\u0627\u0628 \u06a9\u0646\u06cc\u062f:",
            reply_markup=create_check_branch_keyboard(CHECK_ROOT_NODES, page=0, parent_path=None))
        return

    idx = int(data_parts[2])
    norm_path = CHECK_INDEX_TO_PATH.get(idx)

    if not norm_path or norm_path not in CHECK_PATH_TO_ROW:
        await callback.message.edit_text("\u274c \u062e\u0637\u0627: \u0648\u0627\u062d\u062f \u0645\u0648\u0631\u062f \u0646\u0638\u0631 \u06cc\u0627\u0641\u062a \u0646\u0634\u062f.")
        return

    node = CHECK_PATH_TO_ROW[norm_path]

    if action == "open":
        children = check_get_children(norm_path)
        if not children:
            await callback.message.edit_text(
                f"\u2139\ufe0f \u0648\u0627\u062d\u062f \u00ab{node['name']}\u00bb \u0641\u0631\u0632\u0646\u062f\u06cc \u0646\u062f\u0627\u0631\u062f.")
            return
        page = int(data_parts[3]) if len(data_parts) > 3 else 0
        await callback.message.edit_text(
            f"\U0001f4c1 *{node['name']}*\n\n"
            "\u0644\u0637\u0641\u0627\u064b \u06cc\u06a9\u06cc \u0627\u0632 \u0645\u0648\u0627\u0631\u062f \u0632\u06cc\u0631 \u0631\u0627 \u0627\u0646\u062a\u062e\u0627\u0628 \u06a9\u0646\u06cc\u062f:",
            reply_markup=create_check_branch_keyboard(children, page=page, parent_path=norm_path))

    elif action == "page":
        page = int(data_parts[3]) if len(data_parts) > 3 else 0
        children = check_get_children(norm_path)
        await callback.message.edit_reply_markup(
            reply_markup=create_check_branch_keyboard(children, page=page, parent_path=norm_path)
        )

    elif action == "back":
        back_path = CHECK_INDEX_TO_PATH.get(idx)
        if not back_path or back_path not in CHECK_PATH_TO_ROW:
            await callback.message.edit_text(
                "\U0001f3db *\u0627\u0646\u062a\u062e\u0627\u0628 \u0635\u0644\u0627\u062d\u06cc\u062a \u062f\u0627\u062f\u06af\u0627\u0647*\n\n"
                "\u0644\u0637\u0641\u0627\u064b \u0627\u0632 \u0644\u06cc\u0633\u062a \u0632\u06cc\u0631 \u0627\u0646\u062a\u062e\u0627\u0628 \u06a9\u0646\u06cc\u062f:",
                reply_markup=create_check_branch_keyboard(CHECK_ROOT_NODES, page=0, parent_path=None))
            return
        parent_node = CHECK_PATH_TO_ROW[back_path]
        children = check_get_children(back_path)
        page = int(data_parts[3]) if len(data_parts) > 3 else 0
        await callback.message.edit_text(
            f"\U0001f4c1 *{parent_node['name']}*\n\n"
            "\u0644\u0637\u0641\u0627\u064b \u06cc\u06a9\u06cc \u0627\u0632 \u0645\u0648\u0627\u0631\u062f \u0632\u06cc\u0631 \u0631\u0627 \u0627\u0646\u062a\u062e\u0627\u0628 \u06a9\u0646\u06cc\u062f:",
            reply_markup=create_check_branch_keyboard(children, page=page, parent_path=back_path))

    elif action == "sel":
        branch_code = node.get("code", "")
        if not branch_code:
            await callback.answer(
                "\u26a0\ufe0f \u0627\u06cc\u0646 \u0648\u0627\u062d\u062f \u0641\u0627\u0642\u062f \u06a9\u062f \u0627\u0633\u062a \u0648 \u0642\u0627\u0628\u0644 \u0627\u0646\u062a\u062e\u0627\u0628 \u0646\u06cc\u0633\u062a.",
                show_alert=True
            )
            return

        branch_name = node.get("name", "")
        branch_path = node.get("path", "")

        await state.update_data(
            check_branch_name=branch_name,
            check_branch_code=branch_code,
            check_branch_path=branch_path
        )

        await callback.message.answer(
            f"\u2705 *\u062f\u0627\u062f\u06af\u0627\u0647 \u0627\u0646\u062a\u062e\u0627\u0628 \u0634\u062f:*\n\n"
            f"\U0001f4cb \u0646\u0627\u0645: *{branch_name}*\n"
            f"\U0001f522 \u06a9\u062f: `{branch_code}`")

        await _go_to_check_preview(callback.message, state)

    elif action == "info":
        await callback.answer(
            "\u26a0\ufe0f \u0627\u06cc\u0646 \u0648\u0627\u062d\u062f \u0641\u0627\u0642\u062f \u06a9\u062f \u0627\u0633\u062a \u0648 \u0642\u0627\u0628\u0644 \u0627\u0646\u062a\u062e\u0627\u0628 \u0646\u06cc\u0633\u062a.",
            show_alert=True
        )
