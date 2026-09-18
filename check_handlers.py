
"""
هندلرهای بخش ثبت دعاوی چک — فلوی مکالمه تلگرام.

جریان:
  ۱. ورود به بخش دعاوی چک (تکی یا دسته‌جمعی)
  ۲. انتخاب عنوان خواسته (صدور اجرائیه / مطالبه وجه / مطالبه وجه بابت...)
  ۳. دریافت مبلغ چک
  ۳.۵ سوال تامین خواسته و توقیف اموال خوانده (بله/خیر)
  ۳.۶ سوال اعسار از هزینه دادرسی (بله/خیر)
  ۴. دریافت/ویرایش عنوان خواسته (متن پیشنهادی فقط برای «صدور اجرائیه چک»
     و «مطالبه وجه چک» — سایر عناوین بدون متن نمونه)
  ۵. اطلاعات خواهان (مانند اظهارکننده)
     ⭐ طلاق توافقی: حتماً دو نفر به‌عنوان «شخص حقیقی» (زوج و زوجه) و
        بخش خوانده کلاً حذف می‌شود (در سمت سناریو هم اسکیپ می‌شود)
  ۶. اطلاعات خوانده (مانند مخاطب) — به‌جز طلاق توافقی
  ۷. مطلع/گواه (در صورت اعسار: حداقل دو شخص حقیقی الزامی)
  ۸. شرح متن (متن پیشنهادی فقط برای اجرائیه/مطالبه وجه چک + فایل ورد)
  ۸.۵ تصاویر استشهادیه (فقط در صورت اعسار — الزامی)
  ۹. توضیحات اضافی
 ۱۰. تصاویر چک (به‌ازای هر فقره: کدرهگیری + دقیقاً ۳ تصویر)
 ۱۱. انتخاب صلاحیت دادگاه
 ۱۲. پیش‌نمایش و تایید

اصلاحات این نسخه:
  ۱. رفع TypeError جمع‌آوری متن: _on_check_text_final پارامتر was_editing
     را می‌پذیرد (text_collector آن را پاس می‌دهد) — قبلاً متن کاربر هرگز
     ذخیره نمی‌شد.
  ۲. نمونه‌متن فقط برای «صدور اجرائیه چک» و «مطالبه وجه چک» نمایش داده
     می‌شود؛ عناوین دیگر (طلاق، نفقه، تمکین، مهریه) بدون متن نمونه.
  ۳. طلاق توافقی: الزام دو شخص حقیقی در خواهان + حذف کامل بخش خوانده.

اصلاحات نسخهٔ جدید (طبق دستور کارفرما):
  ۱. شرح متن: فراخوانی صحیح collect_text_part (امضای user_id/chat_id/text/
     state/bot/on_complete) — قبلاً با آرگومان‌های نادرست صدا زده می‌شد و
     ارسال متن هیچ اکشنی نداشت. برای تمام عناوین (اجرائیه، مطالبه وجه،
     مطالبه وجه بابت...، خانواده) یکسان کار می‌کند.
  ۲. فایل ورد (.docx): پشتیبانی کامل — استخراج متن + HTML فرمت‌دار، ذخیرهٔ
     file_id/نام فایل، ارسال کپی به مدیر و انتقال HTML به سناریو. دکمهٔ
     «ارسال فایل ورد» با تطبیق امن متن (قبلاً «(docx)» بدون نقطه بود و
     هرگز مطابقت نمی‌کرد).
  ۳. خوانده: بعد از ثبت کدملی خوانده (شخص حقیقی یا وکیل)، دکمهٔ
     «اتمام و ادامه» در کیبورد نمایش داده می‌شود تا کاربر بتواند به
     مرحلهٔ بعد برود.
  ۴. مطلع/گواه: بعد از ارسال کدملی، نام دیگر پرسیده نمی‌شود — نام از
     استعلام ثنا خودکار در سامانه درج می‌شود.
  ۵. متن خواسته (check_khasteh_text) دیگر با شرح متن ترکیب نمی‌شود —
     سناریو این دو را در فیلدهای جداگانه ثبت می‌کند و ترکیب قبلی باعث
     تکرار دوبار متن خواسته در سامانه می‌شد.
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

# ⭐ عناوین جدید خانواده — ثبت عین «مطالبه وجه» طبق دستور کارفرما
CHECK_FAMILY_TITLES = ["دادخواست طلاق توافقی", "دادخواست طلاق به درخواست زوجه",
                       "دادخواست طلاق به درخواست زوج", "دادخواست نفقه",
                       "دادخواست الزام به تمکین", "دادخواست مهریه"]
# طلاق×۳ و «الزام به تمکین»: بدون مبلغ و همیشه دادخواست بدوی
CHECK_NO_AMOUNT_TITLES = ["دادخواست طلاق توافقی", "دادخواست طلاق به درخواست زوجه",
                          "دادخواست طلاق به درخواست زوج", "دادخواست الزام به تمکین"]
# تامین خواسته فقط برای این عناوین پرسیده می‌شود (نفقه و مهریه اضافه شدند)
CHECK_TAMIN_TITLES = ("مطالبه وجه چک", "مطالبه وجه بابت...", "دادخواست مهریه", "دادخواست نفقه")
# ⭐ نمونه‌متن فقط برای این دو عنوان نمایش داده می‌شود
CHECK_SAMPLE_TEXT_TITLES = ("صدور اجرائیه چک", "مطالبه وجه چک")
# ⭐ طلاق توافقی: دو شخص حقیقی در خواهان (زوج و زوجه) + بدون خوانده
CHECK_TALAGH_TOAFIGHI_TITLE = "دادخواست طلاق توافقی"
# ⭐ عناوین اعسار — روند ثبت عین «مطالبه وجه بابت...» با این تفاوت‌ها:
#   ۱. مبلغ / تامین خواسته / اعسار حذف می‌شود
#   ۲. در ابتدا نوع دادگاه (حقوقی / صلح) از کاربر پرسیده می‌شود
#   ۳. حتماً دو شاهد با کدملی الزامی است
#   ۴. تصویر استشهادیه (استشهاديه محلي) + لیست اموال + تصویر دادنامه/اجرائیه
#      (تصويردادنامه غيرمكانيزه با شماره دادنامه/تاریخ/نام دادگاه/شماره شعبه)
#      به‌صورت اجباری گرفته می‌شود
CHECK_AASAR_TITLES = ["اعسار از پرداخت هزینه دادرسی",
                      "اعسار از پرداخت محکوم به",
                      "اعسار از پرداخت مهریه"]
# ⭐ عناوین مجاز انتخاب عنوان خواسته (شامل عناوین اعسار)
CHECK_ALL_VALID_TITLES = CHECK_FAMILY_TITLES + list(CHECK_AASAR_TITLES) + [
    "صدور اجرائیه چک", "مطالبه وجه چک", "مطالبه وجه بابت..."]
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
    check_legal_rep_add_more_kb,
    check_rep_doc_images_kb,
    get_check_more_images_kb,
    create_check_cheque_count_kb,
    check_more_docs_kb,
    check_choice_kb,
    check_request_title_kb,
    check_court_type_kb,
    check_confirm_kb,
    check_edit_kb,
    check_yes_no_kb,
    check_extra_text_kb,
    check_more_images_kb,  # fallback ثابت
    check_attachment_title_kb_first,
    check_attachment_title_kb,
    check_attachment_more_kb,
    check_images_continue_kb,
    check_docx_option_kb,
    text_input_method_kb,
    bulk_input_method_kb,
    vakalat_ask_kb)  # ⭐ سوال وکالت پیش از بخش خواهان
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
from stamp_duty import calculate_stamp_duty

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
        check_court_type="",
        check_amount=0,
        check_tamin_khasteh=False,
        check_aasar=False,
        check_khasteh_text="",
        check_tracking_no="",
        check_plainiffs=[],
        check_defendants=[],
        check_witnesses=[],
        check_text="",
        check_text_html="",
        check_extra_text="",
        check_images=[],
        check_cheque_items=[],       # ⭐ فلو جدید چک: [{tracking_no, images}, ...]
        check_cheques_total=0,       # ⭐ تعداد فقرات چک (پرسش قبل از منضمات)
        check_tracking_list=[],
        _current_cheque_index=1,
        _current_cheque_tracking="",
        _current_cheque_images=[],
        check_esteshahadieh_images=[],
        check_marriage_cert_images=[],
        check_assets_list_images=[],
        check_judgment_images=[],
        check_judgment_no="",
        check_judgment_date="",
        check_judgment_court_name="",
        check_judgment_branch_no="",
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


# ── برگشت هوشمند به پیش‌نمایش (در صورت ویرایش) ─────────────────────────────
async def _check_maybe_return_to_preview(message: Message, state: FSMContext) -> bool:
    """
    اگر روی دکمه «تایید و ثبت نهایی» کلیک کرده باشیم (check_edit_mode=True)
    و اکنون روی یکی از مراحل میانی هستیم، پس از ذخیره مقدار جدید دوباره
    پیش‌نمایش نمایش داده می‌شود و مقدار True برمی‌گردد.
    """
    data = await state.get_data()
    if data.get("check_edit_mode") and data.get("check_preview_sent"):
        await _go_to_check_preview(message, state)
        return True
    return False


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۲ — عنوان خواسته
# ══════════════════════════════════════════════════════════════════════════════
@check_router.message(Form.check_request_title)
async def check_request_title_handler(message: Message, state: FSMContext):
    text = message.text.strip() if message.text else ""

    if text == "🔙 بازگشت":
        # ⭐ اصلاحیه: بازگشت به «همان مرحلهٔ قبل» یعنی انتخاب تکی/دسته‌جمعی —
        # قبلاً state.clear() شده و به منوی نحوهٔ ثبت (دو مرحله عقب‌تر)
        # برمی‌گشت و تمام داده‌های کاربر از بین می‌رفت.
        await message.answer(
            "🏦 *ثبت دعاوی چک*\n\n"
            "آیا قصد ثبت *یک مورد دادخواست چک* دارید یا *بیش از ۵ مورد (ثبت دسته‌جمعی)*؟",
            reply_markup=check_choice_kb)
        await state.set_state(Form.check_request_type)
        return

    if not text:
        await message.answer("⚠️ لطفاً از لیست، عنوان خواسته را انتخاب کنید:")
        return

    if text not in CHECK_ALL_VALID_TITLES:
        await message.answer("⚠️ لطفاً از لیست، عنوان خواسته را انتخاب کنید:")
        return

    await state.update_data(check_request_title=text)

    # ⭐ عناوین اعسار — ابتدا نوع دادگاه (حقوقی/صلح) پرسیده می‌شود؛
    # مبلغ / تامین خواسته / اعسار به‌کلی حذف می‌شود.
    # ⭐ صفرکردن صریح check_amount — اگر کاربر قبلاً برای عنوان دیگری مبلغ
    # وارد کرده و برگشته باشد، مبلغ کهنه نباید در قاعدهٔ «اول مبلغ»
    # محاسبهٔ تمبر (۱۴۰۵/۰۶) استفاده شود؛ عناوین اعسار همیشه ۲۰۰,۰۰۰ ریال.
    if text in CHECK_AASAR_TITLES:
        await state.update_data(check_amount=0)
        await message.answer(
            f"⭕ عنوان انتخاب‌شده: *{_escape_md(text)}*\n\n"
            "🏛 *مرحله ۲:* این دادخواست مربوط به کدام دادگاه است؟",
            reply_markup=check_court_type_kb)
        await state.set_state(Form.check_court_type)
        return

    # طلاق×۳ و «الزام به تمکین»: بدون مبلغ و همیشه دادخواست بدوی
    if text in CHECK_NO_AMOUNT_TITLES:
        await state.update_data(check_amount=0)
        await message.answer(
            "📄 *مرحله ۳:* عنوان خواسته\n\n"
            "لطفاً *متن خواسته* خود را وارد فرمایید:",
            reply_markup=back_only_kb)
        await state.set_state(Form.check_khasteh_title)
        return

    # عناوین خانوادهٔ بدون مبلغ — پیام بدون «مبلغ کل»
    if text in CHECK_FAMILY_TITLES:
        await message.answer(
            "💰 *مرحله ۲:* عنوان خواسته\n\n"
            f"⭕ عنوان انتخاب‌شده: *{_escape_md(text)}*\n\n"
            "لطفاً *مبلغ کل* را به *ریال* وارد فرمایید:\n"
            "_(فقط عدد)_",
            reply_markup=back_only_kb)
    else:
        await message.answer(
            "💰 *مرحله ۲:* عنوان خواسته\n\n"
            f"⭕ عنوان انتخاب‌شده: *{_escape_md(text)}*\n\n"
            "لطفاً *مبلغ کل چک* را به *ریال* وارد فرمایید:\n"
            "_(فقط عدد)_",
            reply_markup=back_only_kb)
    await state.set_state(Form.check_amount)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۱.۵ — نوع دادگاه (فقط عناوین اعسار: حقوقی / صلح)
# ══════════════════════════════════════════════════════════════════════════════
@check_router.message(Form.check_court_type)
async def check_court_type_handler(message: Message, state: FSMContext):
    text = (message.text or "").strip()

    if text == "🔙 بازگشت":
        # بازگشت به همان مرحلهٔ قبل — انتخاب عنوان خواسته
        await message.answer(
            "🏦 *ثبت دادخواست چک (روال تکی)*\n\n"
            "*مرحله ۱:* لطفاً *عنوان خواسته خود* را انتخاب فرمایید:",
            reply_markup=check_request_title_kb)
        await state.set_state(Form.check_request_title)
        return

    if text not in ("🏛 دادگاه حقوقی", "🕊 دادگاه صلح"):
        await message.answer(
            "⚠️ لطفاً با استفاده از دکمه‌ها، نوع دادگاه را انتخاب فرمایید:")
        return

    court_type = "حقوقی" if text == "🏛 دادگاه حقوقی" else "صلح"
    await state.update_data(check_court_type=court_type)

    # ⭐ عناوین اعسار بدون مبلغ — مستقیم به متن خواسته (عین «مطالبه وجه بابت...»)
    await message.answer(
        f"🏛 دادگاه انتخاب‌شده: *دادگاه {court_type}*\n\n"
        "📄 *مرحله ۳:* عنوان خواسته\n\n"
        "لطفاً *متن خواسته* خود را وارد فرمایید:",
        reply_markup=back_only_kb)
    await state.set_state(Form.check_khasteh_title)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۳ — مبلغ چک
# ══════════════════════════════════════════════════════════════════════════════
@check_router.message(Form.check_amount)
async def check_amount_handler(message: Message, state: FSMContext):
    text = _to_en(message.text or "")

    if "بازگشت" in text:
        await message.answer(
            "🏦 *ثبت دادخواست چک (روال تکی)*\n\n"
            "*مرحله ۱:* لطفاً *عنوان خواسته خود* را انتخاب فرمایید:",
            reply_markup=check_request_title_kb)
        await state.set_state(Form.check_request_title)
        return

    if not text.isdigit() or int(text) <= 0:
        await message.answer(
            "⚠️ مبلغ نامعتبر است. لطفاً فقط *عدد* (به ریال) وارد فرمایید:")
        return

    amount = int(text)
    await state.update_data(check_amount=amount)

    # ⭐ مرحله ۲.۵ — سوال تامین خواسته و توقیف اموال (بله/خیر)
    # فقط برای عناوینی که نیاز به تامین خواسته دارند
    data = await state.get_data()
    request_title = data.get("check_request_title", "")

    if request_title in CHECK_TAMIN_TITLES:
        kb_text = "توقیف اموال خوانده" if request_title.startswith("دادخواست") else "توقیف اموال صادرکننده چک"
        await message.answer(
            "⚖️ آیا درخواست *تامین خواسته* و "
            f"*{kb_text}* را دارید؟",
            reply_markup=check_yes_no_kb)
        await state.set_state(Form.check_tamin_khasteh)
        return

    if await _check_maybe_return_to_preview(message, state):
        return

    # مرحله ۳ — متن پیشنهادی عنوان خواسته (روال سابق — صدور اجرائیه چک)
    # ⭐ نمونه‌متن فقط برای «صدور اجرائیه چک» و «مطالبه وجه چک» نمایش داده می‌شود
    if request_title in CHECK_SAMPLE_TEXT_TITLES:
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
    else:
        # ⭐ سایر عناوین (طلاق، نفقه، تمکین، مهریه) — بدون متن نمونه
        await message.answer(
            "📄 *مرحله ۳:* عنوان خواسته\n\n"
            "لطفاً *متن خواسته* خود را وارد فرمایید:",
            reply_markup=back_only_kb)
    await state.set_state(Form.check_khasteh_title)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۳.۵ — سوال تامین خواسته (بله/خیر)
# ══════════════════════════════════════════════════════════════════════════════
@check_router.message(Form.check_tamin_khasteh)
async def check_tamin_khasteh_handler(message: Message, state: FSMContext):
    text = (message.text or "").strip()

    if text == "🔙 بازگشت":
        # ⭐ اصلاحیه: بازگشت به «همان مرحلهٔ قبل» یعنی وارد کردن مبلغ —
        # قبلاً به انتخاب عنوان (دو مرحله عقب‌تر) برمی‌گشت.
        await message.answer(
            "💰 *مرحله ۲:* عنوان خواسته\n\n"
            "لطفاً *مبلغ کل* را به *ریال* وارد فرمایید:\n"
            "_(فقط عدد)_",
            reply_markup=back_only_kb)
        await state.set_state(Form.check_amount)
        return

    if text not in ("✅ بله", "❌ خیر"):
        await message.answer("⚠️ لطفاً با استفاده از دکمه‌ها پاسخ دهید (بله / خیر).")
        return

    await state.update_data(check_tamin_khasteh=(text == "✅ بله"))

    # ⭐ مرحله ۲.۶ — سوال اعسار از هزینه دادرسی (بله/خیر)
    await message.answer(
        "📋 آیا درخواست *اعسار از هزینه دادرسی* را دارید؟",
        reply_markup=check_yes_no_kb)
    await state.set_state(Form.check_aasar)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۳.۶ — سوال اعسار (بله/خیر)
# ══════════════════════════════════════════════════════════════════════════════
@check_router.message(Form.check_aasar)
async def check_aasar_handler(message: Message, state: FSMContext):
    text = (message.text or "").strip()

    if text == "🔙 بازگشت":
        # ⭐ اصلاحیه: بازگشت به «همان مرحلهٔ قبل» یعنی سوال تامین خواسته —
        # قبلاً به انتخاب عنوان (سه مرحله عقب‌تر) برمی‌گشت.
        await message.answer(
            "⚖️ آیا درخواست *تامین خواسته* و *توقیف اموال خوانده* را دارید؟",
            reply_markup=check_yes_no_kb)
        await state.set_state(Form.check_tamin_khasteh)
        return

    if text not in ("✅ بله", "❌ خیر"):
        await message.answer("⚠️ لطفاً با استفاده از دکمه‌ها پاسخ دهید (بله / خیر).")
        return

    aasar = (text == "✅ بله")
    await state.update_data(check_aasar=aasar)

    if await _check_maybe_return_to_preview(message, state):
        return

    # مرحله ۳ — عنوان خواسته (متن)
    data = await state.get_data()
    request_title = data.get("check_request_title", "")

    if request_title == "مطالبه وجه بابت...":
        await message.answer(
            "📄 *مرحله ۳:* عنوان خواسته\n\n"
            "لطفاً *متن خواسته* خود را وارد فرمایید:",
            reply_markup=back_only_kb)
        await state.set_state(Form.check_khasteh_title)
        return

    # ⭐ نمونه‌متن فقط برای «صدور اجرائیه چک» و «مطالبه وجه چک»
    if request_title in CHECK_SAMPLE_TEXT_TITLES:
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
    else:
        # ⭐ سایر عناوین — بدون متن نمونه
        await message.answer(
            "📄 *مرحله ۳:* عنوان خواسته\n\n"
            "لطفاً *متن خواسته* خود را وارد فرمایید:",
            reply_markup=back_only_kb)
    await state.set_state(Form.check_khasteh_title)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۴ — عنوان خواسته (متن)
# ══════════════════════════════════════════════════════════════════════════════
@check_router.message(Form.check_khasteh_title)
async def check_khasteh_title_handler(message: Message, state: FSMContext):
    text = message.text.strip() if message.text else ""

    if text == "🔙 بازگشت":
        # ⭐ اصلاحیه: بازگشت به «همان مرحلهٔ قبل» بر اساس عنوان انتخاب‌شده:
        #   - عناوین اعسار → سوال نوع دادگاه
        #   - عناوین تامین‌دار (مطالبه وجه چک/بابت/مهریه/نفقه) → سوال اعسار
        #   - طلاق×۳ / تمکین (بدون مبلغ) → انتخاب عنوان
        #   - صدور اجرائیه چک → وارد کردن مبلغ
        data = await state.get_data()
        rt = data.get("check_request_title", "")
        if rt in CHECK_AASAR_TITLES:
            await message.answer(
                "🏛 *مرحله ۲:* این دادخواست مربوط به کدام دادگاه است؟",
                reply_markup=check_court_type_kb)
            await state.set_state(Form.check_court_type)
        elif rt in CHECK_TAMIN_TITLES:
            await message.answer(
                "📋 آیا درخواست *اعسار از هزینه دادرسی* را دارید؟",
                reply_markup=check_yes_no_kb)
            await state.set_state(Form.check_aasar)
        elif rt in CHECK_NO_AMOUNT_TITLES:
            await message.answer(
                "🏦 *ثبت دادخواست چک (روال تکی)*\n\n"
                "*مرحله ۱:* لطفاً *عنوان خواسته خود* را انتخاب فرمایید:",
                reply_markup=check_request_title_kb)
            await state.set_state(Form.check_request_title)
        else:
            await message.answer(
                "💰 *مرحله ۲:* عنوان خواسته\n\n"
                "لطفاً *مبلغ کل چک* را به *ریال* وارد فرمایید:\n"
                "_(فقط عدد)_",
                reply_markup=back_only_kb)
            await state.set_state(Form.check_amount)
        return

    if not text:
        await message.answer("⚠️ متن خواسته نمی‌تواند خالی باشد. لطفاً وارد فرمایید:")
        return

    await state.update_data(check_khasteh_text=text)

    if await _check_maybe_return_to_preview(message, state):
        return

    # ⭐ مرحله ۵ — پیش از بخش خواهان: سوال وکالت (طبق دستور کارفرما)
    # اگر ثبت «به وکالت» است، کاربر کدملی وکیل را وارد می‌کند (مراحل کامل
    # وکیل: کدملی + شماره قرارداد وکالت + تمبر خودکار)؛ در غیر این صورت «رد شدن»
    # و ادامهٔ مسیر عادیِ خواهان (حقیقی/حقوقی — گزینهٔ «وکیل» دیگر در کیبورد نیست).
    await message.answer(
        "👤 *مرحله ۵:* اطلاعات *خواهان*\n\n"
        "در صورتی که این دادخواست *به وکالت* ثبت می‌شود، گزینه *«وارد کردن کدملی وکیل»* را انتخاب کنید.\n"
        "در غیر این صورت، گزینه *«رد شدن»* را انتخاب کنید:",
        reply_markup=vakalat_ask_kb)
    await state.set_state(Form.check_plaintiff_vakalat_ask)


# ════════════════════════════════════════════════════════════════════════════
# مرحله ۴-الف — سوال وکالت پیش از خواهان (ثبت به وکالت یا عادی)
# ════════════════════════════════════════════════════════════════════════════
@check_router.message(Form.check_plaintiff_vakalat_ask)
async def check_plaintiff_vakalat_ask_handler(message: Message, state: FSMContext):
    """سوال وکالت قبل از بخش خواهان:
      - «وارد کردن کدملی وکیل» → دریافت کدملی وکیل → شماره قرارداد وکالت + تمبر
      - «رد شدن» → مسیر عادیِ انتخاب نوع شخصیت خواهان (حقیقی/حقوقی)
    """
    text = (message.text or "").strip()

    if text == "وارد کردن کدملی وکیل":
        await message.answer(
            "⚖️ ثبت *به وکالت* انتخاب شد.\n\n"
            "🆔 لطفاً *کد ملی وکیل* را وارد فرمایید:\n_(۱۰ رقمی)_",
            reply_markup=back_only_kb)
        await state.set_state(Form.check_plaintiff_vakalat_nid)
        return

    if text == "رد شدن":
        await message.answer(
            "👤 لطفاً *نوع شخصیت خواهان* را انتخاب فرمایید:",
            reply_markup=create_check_person_type_kb())
        await state.set_state(Form.check_plaintiff_person_type)
        return

    await message.answer(
        "⚠️ لطفاً یکی از گزینه‌های زیر را انتخاب کنید:\n"
        "_(اگر ثبت به وکالت است: «وارد کردن کدملی وکیل» — در غیر این صورت: «رد شدن»)_",
        reply_markup=vakalat_ask_kb)


@check_router.message(Form.check_plaintiff_vakalat_nid)
async def check_plaintiff_vakalat_nid_handler(message: Message, state: FSMContext):
    """دریافت کدملی وکیل خواهان — سپس شماره قرارداد وکالت (همان مراحل قبلیِ وکیل)."""
    text = _to_en(message.text or "")
    data = await state.get_data()

    if "بازگشت" in text:
        await message.answer(
            "👤 *مرحله ۵:* اطلاعات *خواهان*\n\n"
            "در صورتی که این دادخواست *به وکالت* ثبت می‌شود، گزینه *«وارد کردن کدملی وکیل»* را انتخاب کنید.\n"
            "در غیر این صورت، گزینه *«رد شدن»* را انتخاب کنید:",
            reply_markup=vakalat_ask_kb)
        await state.set_state(Form.check_plaintiff_vakalat_ask)
        return

    if not re.fullmatch(r"\d{10}", text):
        await message.answer("⚠️ کد ملی وکیل باید *۱۰ رقم* باشد. دوباره وارد فرمایید:")
        return

    await state.update_data(_check_current_plaintiff={
        "person_type": "وکیل",
        "national_id": text,
    })

    await message.answer(
        "📑 لطفاً *شماره قرارداد وکالت* را وارد فرمایید:\n_(دقیقاً ۱۶ رقمی)_",
        reply_markup=back_only_kb)
    await state.set_state(Form.check_plaintiff_vakalat_no)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۵ — اطلاعات خواهان (مانند اظهارکننده)
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

        # ⭐ طلاق توافقی: الزام دو شخص حقیقی (زوج و زوجه) + پرش از بخش خوانده
        if data.get("check_request_title") == CHECK_TALAGH_TOAFIGHI_TITLE:
            real_count = len([p for p in plaintiffs if p.get("person_type") == "شخص حقیقی"])
            if real_count != 2:
                await message.answer(
                    f"⚠️ در *طلاق توافقی* باید *دو نفر* (زوج و زوجه) به‌عنوان "
                    f"*شخص حقیقی* در خواهان وارد شوند.\n"
                    f"(تاکنون: {real_count} نفر از ۲)\n\n"
                    "لطفاً *کد ملی* شخص حقیقی بعدی را ارسال فرمایید:",
                    reply_markup=back_only_kb)
                return
            if await _check_maybe_return_to_preview(message, state):
                return
            await message.answer(
                "🔍 *مرحله ۶:* آیا *مطلع یا گواه* دارید؟\n\n"
                "در صورت وجود، *کدملی* مطلع/گواه را ارسال فرمایید.\n"
                "_(در غیر این صورت گزینه «اتمام» را انتخاب کنید)_",
                reply_markup=check_addressee_add_more_kb)
            await state.set_state(Form.check_witness_national_id)
            return

        # ⭐ مشابه اظهارنامه: اگر فقط «وکیل» داریم و هیچ حقیقی/حقوقی نیست، خطا
        has_lawyer = any(p.get("person_type") == "وکیل" for p in plaintiffs)
        has_real_or_legal = any(p.get("person_type") in ("شخص حقیقی", "شخص حقوقی") for p in plaintiffs)
        if has_lawyer and not has_real_or_legal:
            await message.answer(
                "⚠️ اگر خواهان *وکیل* است، باید حداقل یک خواهان *شخص حقیقی یا حقوقی* نیز ثبت شود.\n\n"
                "لطفاً نوع شخصیت خواهان بعدی را انتخاب کنید:")
            return

        if await _check_maybe_return_to_preview(message, state):
            return

        # رفتن به مرحله خوانده
        await message.answer(
            "👥 *مرحله ۵:* لطفاً *نوع شخصیت خوانده* را انتخاب فرمایید:",
            reply_markup=create_check_person_type_kb())
        await state.set_state(Form.check_defendant_person_type)
        return

    if text not in ["شخص حقیقی", "شخص حقوقی"]:
        # ⭐ گزینهٔ «وکیل» حذف شد — ثبت به وکالت از سوال وکالت قبلی
        # (check_plaintiff_vakalat_ask) انجام می‌شود.
        await message.answer("⚠️ لطفاً از لیست، نوع شخصیت را انتخاب کنید:")
        return

    # ⭐ طلاق توافقی: فقط شخص حقیقی و حداکثر دو نفر (زوج و زوجه)
    if data.get("check_request_title") == CHECK_TALAGH_TOAFIGHI_TITLE:
        if text != "شخص حقیقی":
            await message.answer(
                "⚠️ در *طلاق توافقی* فقط امکان انتخاب *شخص حقیقی* وجود دارد.\n\n"
                "لطفاً «شخص حقیقی» را انتخاب کنید:")
            return
        real_count = len([p for p in plaintiffs if p.get("person_type") == "شخص حقیقی"])
        if real_count >= 2:
            await message.answer(
                "⚠️ در *طلاق توافقی* حداکثر *دو نفر* (زوج و زوجه) به‌عنوان خواهان "
                "قابل ثبت است.\n\n"
                "لطفاً دکمهٔ *«اتمام و ادامه»* را بفشارید:")
            return

    await state.update_data(_check_current_plaintiff={"person_type": text})

    if text == "شخص حقوقی":
        await message.answer(
            "🏢 لطفاً *شناسه ملی* شخص حقوقی خواهان را وارد فرمایید:\n"
            "_(۱۱ رقم)_",
            reply_markup=back_only_kb)
        await state.set_state(Form.check_plaintiff_company_id)
        return

    # شخص حقیقی یا وکیل — کد ملی
    await message.answer(
        "🆔 لطفاً *کد ملی* خواهان را وارد فرمایید:",
        reply_markup=back_only_kb)
    await state.set_state(Form.check_plaintiff_national_id)


@check_router.message(Form.check_plaintiff_company_id)
async def check_plaintiff_company_id_handler(message: Message, state: FSMContext):
    text = _to_en(message.text or "")
    data = await state.get_data()

    if "بازگشت" in text:
        plaintiffs = data.get("check_plainiffs", [])
        used_types = [p.get("person_type") for p in plaintiffs]
        await message.answer(
            "👤 لطفاً نوع شخصیت خواهان را انتخاب کنید:",
            reply_markup=create_ezhhar_declarant_person_type_kb(exclude=used_types if plaintiffs else []))
        await state.set_state(Form.check_plaintiff_person_type)
        return

    if not re.fullmatch(r"\d{11}", text):
        await message.answer("⚠️ شناسه ملی باید *۱۱ رقم* باشد. دوباره وارد فرمایید:")
        return

    for p in data.get("check_plainiffs", []):
        if p.get("company_id") == text and p.get("person_type") == "شخص حقوقی":
            await message.answer("⚠️ این شناسه ملی قبلاً برای خواهان ثبت شده است. لطفاً شناسه دیگری وارد فرمایید:")
            return

    current = data.get("_check_current_plaintiff") or {}
    # ⚠️ کلید باید دقیقاً «company_id» باشد — check_scenario.py
    # (_fill_legal_person) شناسه ملی شرکت را از همین کلید می‌خوانَد؛
    # «national_id» برای کدملی شخصی نمایندگان (representatives[i]) رزرو است.
    current["company_id"] = text
    await state.update_data(_check_current_plaintiff=current)

    # ⭐ اصلاحیه (کارفرما — دور ۳): سوال «نام شرکت/موسسه» حذف شد — نام
    # شرکت بعد از استعلام شناسه ملی، خودکار از سامانه ثنا خوانده می‌شود
    # و پرسیدن آن از کاربر زائد بود. مستقیم «نوع نماینده» پرسیده می‌شود.
    await message.answer(
        "👥 لطفاً *نوع نماینده* شخص حقوقی را انتخاب کنید:",
        reply_markup=representative_type_kb)
    await state.set_state(Form.check_plaintiff_legal_rep_national_id)


# ⚠️ state «check_plaintiff_representative_type» (گرفتن نام شرکت) منسوخ شد —
# دیگر هیچ مسیری به آن نمی‌رود؛ هندلر فقط برای سازگاری با نشست‌های قدیمی
# (کاربرانی که وسط فلو بودند) باقی مانده است و نام را نادیده می‌گیرد.
@check_router.message(Form.check_plaintiff_representative_type)
async def check_plaintiff_representative_type_handler(message: Message, state: FSMContext):
    text = message.text or ""

    if "بازگشت" in text:
        await message.answer(
            "🏢 لطفاً *شناسه ملی* شخص حقوقی خواهان را وارد فرمایید:",
            reply_markup=back_only_kb)
        await state.set_state(Form.check_plaintiff_company_id)
        return

    # سوال نام شرکت حذف شده — هر متن دریافتی نادیده گرفته می‌شود و مستقیم
    # به انتخاب نوع نماینده می‌رویم.
    await message.answer(
        "👥 لطفاً *نوع نماینده* شخص حقوقی را انتخاب کنید:",
        reply_markup=representative_type_kb)
    await state.set_state(Form.check_plaintiff_legal_rep_national_id)


@check_router.message(Form.check_plaintiff_legal_rep_national_id)
async def check_plaintiff_legal_rep_national_id_handler(message: Message, state: FSMContext):
    """⚠️ دکمه‌های representative_type_kb متن ساده «مدیرعامل»/«نماینده»
    دارند (بدون ایموجی) — قبلاً اینجا با «👤 مدیرعامل»/«👤 نماینده» مقایسه
    می‌شد که هرگز True نمی‌شد و انتخاب کاربر همیشه رد می‌شد."""
    text = (message.text or "").strip()
    data = await state.get_data()

    if text == "مدیرعامل":
        await state.update_data(check_plaintiff_current_representative_type="مدیرعامل")
        await message.answer(
            "🆔 لطفاً *کد ملی مدیرعامل* را وارد فرمایید:",
            reply_markup=back_only_kb)
        await state.set_state(Form.check_plaintiff_legal_rep_name)
        return

    if text == "نماینده":
        await state.update_data(check_plaintiff_current_representative_type="نماینده")
        await message.answer(
            "🆔 لطفاً *کد ملی نماینده* را وارد فرمایید:",
            reply_markup=back_only_kb)
        await state.set_state(Form.check_plaintiff_legal_rep_name)
        return

    await message.answer("⚠️ لطفاً از لیست، نوع نماینده را انتخاب کنید:", reply_markup=representative_type_kb)


@check_router.message(Form.check_plaintiff_national_id)
async def check_plaintiff_national_id_handler(message: Message, state: FSMContext):
    text = _to_en(message.text or "")
    data = await state.get_data()

    if "بازگشت" in text:
        plaintiffs = data.get("check_plainiffs", [])
        used_types = [p.get("person_type") for p in plaintiffs]
        await message.answer(
            "👤 لطفاً نوع شخصیت خواهان را انتخاب کنید:",
            reply_markup=create_ezhhar_declarant_person_type_kb(exclude=used_types if plaintiffs else []))
        await state.set_state(Form.check_plaintiff_person_type)
        return

    if not re.fullmatch(r"\d{10}", text):
        await message.answer("⚠️ کد ملی باید *۱۰ رقم* باشد. دوباره وارد فرمایید:")
        return

    person_type = (data.get("_check_current_plaintiff") or {}).get("person_type", "شخص حقیقی")
    for p in data.get("check_plainiffs", []):
        if p.get("national_id") == text and p.get("person_type") == person_type:
            await message.answer("⚠️ این کد ملی قبلاً برای خواهان ثبت شده است. لطفاً کد ملی دیگری وارد فرمایید:")
            return

    # ⭐ مسیر وکیل از طریق همین state منسوخ شد — وکیل دیگر از بین گزینه‌های
    # نوع شخصیت انتخاب نمی‌شود؛ مسیر آن: check_plaintiff_vakalat_ask →
    # check_plaintiff_vakalat_nid → check_plaintiff_vakalat_no است.

    # مسیر شخص حقیقی — مثل اظهارنامه
    current = data.get("_check_current_plaintiff") or {}
    current["national_id"] = text
    plaintiffs = data.get("check_plainiffs", [])
    plaintiffs.append(current)
    await state.update_data(check_plainiffs=plaintiffs, _check_current_plaintiff={})

    # ⭐ طلاق توافقی: فقط شخص حقیقی، حداکثر دو نفر (زوج و زوجه)
    if data.get("check_request_title") == CHECK_TALAGH_TOAFIGHI_TITLE:
        if len(plaintiffs) >= 2:
            await message.answer(
                "✅ هر دو خواهان (زوج و زوجه) ثبت شدند.\n\n"
                "لطفاً دکمهٔ *«اتمام و ادامه»* را بفشارید:",
                reply_markup=check_addressee_add_more_kb)
        else:
            await message.answer(
                "➕ لطفاً *کد ملی* شخص حقیقی دوم (زوج/زوجه دیگر) را وارد فرمایید:",
                reply_markup=back_only_kb)
        await state.set_state(Form.check_plaintiff_national_id)
        return

    await message.answer(
        f"✅ *شخص حقیقی (خواهان)* با کدملی `{text}` ثبت شد.\n\n"
        "آیا خواهان دیگری نیز وجود دارد؟",
        reply_markup=create_ezhhar_declarant_person_type_kb())
    await state.set_state(Form.check_plaintiff_person_type)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۴-الف — شماره قرارداد وکالت و محاسبهٔ خودکار تمبر (فقط وکیل)
# ══════════════════════════════════════════════════════════════════════════════
@check_router.message(Form.check_plaintiff_vakalat_no)
async def check_plaintiff_vakalat_no_handler(message: Message, state: FSMContext):
    """دریافت شماره قرارداد وکالت (۱۶ رقمی) وکیلِ خواهان + محاسبهٔ خودکار تمبر.

    ⚠️ کلید ذخیره باید دقیقاً `contract_number` / `stamp_amount_value` باشد
    (نه `vakalat_no`) چون check_scenario.py مقدار وکالت‌نامهٔ الکترونیک را
    از همین دو کلید روی شیء «وکیل» می‌خوانَد.
    """
    text = (message.text or "").strip()
    data = await state.get_data()

    if "بازگشت" in text:
        # ⭐ بازگشت به کدملی وکیل (مسیر جدید سوال وکالت)
        await message.answer(
            "🆔 لطفاً *کد ملی وکیل* را وارد فرمایید:\n_(۱۰ رقمی)_",
            reply_markup=back_only_kb)
        await state.set_state(Form.check_plaintiff_vakalat_nid)
        return

    contract_no = _to_en(text)
    if not re.fullmatch(r"\d{16}", contract_no):
        await message.answer("⚠️ شماره قرارداد وکالت باید *دقیقاً ۱۶ رقمی* باشد:")
        return

    current = data.get("_check_current_plaintiff") or {}
    current["contract_number"] = contract_no

    # ⭐ محاسبهٔ خودکار تمبر — قاعدهٔ یکسان کارفرما (۱۴۰۵/۰۶) برای «کلیهٔ
    # عناوین ثبت دادخواست»: اگر مبلغ (بهای خواسته) وارد شده باشد ← تمبر
    # طبق همان مبلغ محاسبه می‌شود؛ اگر مبلغی وارد نشده باشد یا آن عنوان
    # کلاً مبلغی نداشته باشد ← تمبر ثابت ۲۰۰,۰۰۰ ریال (۲۰ تومان).
    # (تفکیک عنوانی قبلی حذف شد؛ چون عناوین بی‌مبلغ در فلو check_amount=0
    #  دارند و با قاعدهٔ «اول مبلغ» خودکار پوشش داده می‌شوند.)
    amount = int(data.get("check_amount", 0) or 0)
    if amount > 0:
        try:
            duty = calculate_stamp_duty(amount) or {}
            stamp_rial = int(duty.get("tamber_bedvi", 0) or 0)
            if stamp_rial <= 0:
                # محاسبه هرگز نباید صفر بدهد؛ سقف پایین: ۲۰۰,۰۰۰ ریال
                stamp_rial = 200_000
            stamp_text = f"{stamp_rial // 10:,} تومان ({stamp_rial:,} ریال)"
        except Exception as calc_err:
            logger.error(f"[CHECK] خطا در محاسبه تمبر وکالت: {calc_err}")
            stamp_rial = 200_000
            stamp_text = "۲۰,۰۰۰ تومان (۲۰۰,۰۰۰ ریال)"
    else:
        stamp_rial = 200_000
        stamp_text = "۲۰,۰۰۰ تومان (۲۰۰,۰۰۰ ریال)"

    current["stamp_amount_value"] = stamp_rial
    current["stamp_amount_text"] = stamp_text

    plaintiffs = data.get("check_plainiffs", [])
    plaintiffs.append(current)
    await state.update_data(check_plainiffs=plaintiffs, _check_current_plaintiff={})

    await message.answer(
        f"✅ *وکیل* با کدملی `{current.get('national_id', '')}` ثبت شد.\n"
        f"📑 شماره قرارداد وکالت: `{contract_no}`\n"
        f"💰 مبلغ تمبر وکالت (خودکار محاسبه شد): *{stamp_text}*\n\n"
        "⚠️ چون *وکیل* اضافه کردید، *خواهان* (شخص حقیقی یا حقوقی) نیز باید وارد شود.\n\n"
        "لطفاً نوع شخصیت خواهان بعدی را انتخاب فرمایید:",
        reply_markup=create_ezhhar_declarant_person_type_kb())
    await state.set_state(Form.check_plaintiff_person_type)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۴-ب — کد ملی نماینده/مدیرعامل شرکت خواهان (نه وکیل!)
# ══════════════════════════════════════════════════════════════════════════════
@check_router.message(Form.check_plaintiff_legal_rep_name)
async def check_plaintiff_legal_rep_name_handler(message: Message, state: FSMContext):
    """⚠️ نام این state گمراه‌کننده است ولی در واقعیت «کد ملی نماینده/مدیرعامل»
    شرکت خواهان را می‌گیرد — نه شماره وکالت‌نامه (آن مسیر جداست:
    Form.check_plaintiff_vakalat_no)."""
    text = _to_en((message.text or "").strip())
    data = await state.get_data()

    if "بازگشت" in text or "بازگشت" in (message.text or ""):
        await message.answer(
            "👥 لطفاً *نوع نماینده* شخص حقوقی را انتخاب کنید:",
            reply_markup=representative_type_kb)
        await state.set_state(Form.check_plaintiff_legal_rep_national_id)
        return

    if not re.fullmatch(r"\d{10}", text):
        await message.answer("⚠️ کد ملی باید *۱۰ رقم* باشد. دوباره وارد فرمایید:")
        return

    rep_type = data.get("check_plaintiff_current_representative_type", "نماینده")
    await state.update_data(_check_current_plaintiff_rep={
        "representative_type": rep_type,
        "national_id": text,
    })

    # ⭐ ارسال مدرک نمایندگی برای *هر دو* سمت (مدیرعامل و نماینده) الزامی
    # است — قبلاً فقط برای «نماینده» خواسته می‌شد.
    await message.answer(
        f"✅ *{rep_type}* با کدملی `{text}` دریافت شد.\n\n"
        "⚠️ ارسال تصویر *مدرک نمایندگی* الزامی است و در بخش منضمات ثبت خواهد شد.\n\n"
        "📸 لطفاً تصویر *مدرک نمایندگی* را ارسال فرمایید.\n"
        "_(مثلاً: روزنامه رسمی، آگهی تأسیس، وکالت‌نامه رسمی)_\n\n"
        "پس از ارسال همهٔ تصاویر، دکمه *«اتمام ارسال تصاویر»* را بفشارید.",
        reply_markup=check_rep_doc_images_kb)
    await state.set_state(Form.check_plaintiff_legal_rep_doc_image)


@check_router.message(Form.check_plaintiff_legal_rep_doc_image)
async def check_plaintiff_legal_rep_doc_image_handler(message: Message, state: FSMContext):
    """دریافت تصاویر مدرک نمایندگی خواهان حقوقی.

    ⭐ اصلاحیه (کارفرما — دور ۳ — باگ «دکمه اتمام ارسال تصویر کار نمی‌کند»):
    قبلاً بعد از دریافت هر عکس state تغییر نمی‌کرد و دکمهٔ «✅ اتمام ارسال
    تصاویر» (متن) توسط همین هندلر می‌افتاد و چون عکس نبود، همیشه اخطار
    «⚠️ لطفاً عکس مدرک نماینده را ارسال فرمایید» می‌گرفت — یعنی کاربر
    هرگز نمی‌توانست مرحله را تمام کند. حالا بعد از هر عکس state به
    check_plaintiff_legal_rep_doc_images_more می‌رود (جایی که منطق دکمهٔ
    اتمام/بازگشت است) و متن دکمه‌ها در همین state هم به همان هندلر
    هدایت می‌شود (الگوی گواهی ازدواج/استشهادیه).
    """
    if not message.photo:
        text = (message.text or "").strip()
        if text in ("✅ اتمام ارسال تصاویر", "🔙 بازگشت", "➕ افزودن تصویر دیگر"):
            # دکمه‌های کیبورد در حالت دریافت تصویر — هدایت به منطق هندلر «بیشتر»
            await check_plaintiff_legal_rep_doc_images_more_handler(message, state)
            return
        await message.answer("⚠️ لطفاً *عکس* مدرک نماینده را ارسال فرمایید.")
        return

    data = await state.get_data()
    images = data.get("check_plaintiff_legal_rep_doc_images", [])
    images.append(message.photo[-1].file_id)
    await state.update_data(check_plaintiff_legal_rep_doc_images=images)

    await message.answer(
        f"✅ تصویر شماره *{len(images)}* دریافت شد.\n\n"
        "می‌توانید تصویر دیگری ارسال کنید یا دکمه *«اتمام ارسال تصاویر»* را بفشارید:",
        reply_markup=check_rep_doc_images_kb)
    # ⭐ بعد از هر عکس به state «بیشتر» می‌رویم تا دکمهٔ اتمام کار کند
    await state.set_state(Form.check_plaintiff_legal_rep_doc_images_more)


@check_router.message(Form.check_plaintiff_legal_rep_doc_images_more)
async def check_plaintiff_legal_rep_doc_images_more_handler(message: Message, state: FSMContext):
    """این state دو نقش دارد: (۱) تأیید پایان ارسال تصاویرِ نمایندهٔ فعلی،
    (۲) پس از آن، تصمیم «نمایندهٔ دیگری اضافه کنم یا خواهان را نهایی کنم؟»
    — چون هر دو مرحله با یک ‌ست دکمهٔ متفاوت (اما همین state) پیش می‌روند.
    ⭐ هر خواهان (شخص حقوقی) می‌تواند حداکثر ۵ نماینده/مدیرعامل داشته باشد."""
    # ⭐ عکس در این state هم پذیرفته می‌شود — همان منطق هندلر تصویر اجرا
    # می‌شود (کاربر ممکن است بدون زدن دکمه، مستقیماً عکس بعدی را بفرستد).
    if message.photo:
        await check_plaintiff_legal_rep_doc_image_handler(message, state)
        return

    text = message.text.strip() if message.text else ""
    data = await state.get_data()

    if text == "🔙 بازگشت":
        images = data.get("check_plaintiff_legal_rep_doc_images", [])
        if images:
            images.pop()
            await state.update_data(check_plaintiff_legal_rep_doc_images=images)
        await message.answer(
            "📷 لطفاً *تصویر مدرک نمایندگی* را ارسال فرمایید:",
            reply_markup=check_rep_doc_images_kb)
        await state.set_state(Form.check_plaintiff_legal_rep_doc_image)
        return

    if text == "✅ اتمام ارسال تصاویر":
        images = data.get("check_plaintiff_legal_rep_doc_images", [])
        if not images:
            await message.answer(
                "⚠️ ارسال تصویر *مدرک نمایندگی* الزامی است.\n\n"
                "لطفاً حداقل یک تصویر ارسال فرمایید:",
                reply_markup=check_rep_doc_images_kb)
            return

        current = data.get("_check_current_plaintiff") or {}
        reps = list(current.get("representatives", []))
        rep_info = data.get("_check_current_plaintiff_rep") or {}
        rep_index = len(reps) + 1
        rep_type = rep_info.get("representative_type", "نماینده")

        reps.append({
            "representative_type": rep_type,
            "national_id": rep_info.get("national_id", ""),
        })
        current["representatives"] = reps

        attachment_groups = data.get("check_attachment_groups", [])
        attachment_groups.append({
            "title": f"مدرک نمایندگی ({rep_type} {rep_index})",
            "images": list(images),
        })

        await state.update_data(
            _check_current_plaintiff=current,
            check_attachment_groups=attachment_groups,
            check_plaintiff_legal_rep_doc_images=[],
            _check_current_plaintiff_rep={})

        if len(reps) >= 5:
            await message.answer(
                f"✅ نماینده/مدیرعامل شمارهٔ {rep_index} ثبت شد.\n\n"
                "⚠️ سقف ۵ نماینده/مدیرعامل به‌ازای هر خواهان (شخص حقوقی) تکمیل شد.")
            await _finalize_plaintiff_legal_person(message, state)
            return

        await message.answer(
            f"✅ نماینده/مدیرعامل شمارهٔ {rep_index} ثبت شد.\n\n"
            "آیا نماینده/مدیرعامل دیگری برای همین خواهان اضافه می‌کنید؟\n"
            f"_(حداکثر ۵ نفر — تا الان: {len(reps)} نفر)_",
            reply_markup=check_legal_rep_add_more_kb)
        return

    if text == "➕ افزودن شخص نماینده":
        await message.answer(
            "👥 لطفاً *نوع نماینده* بعدی را انتخاب کنید:",
            reply_markup=representative_type_kb)
        await state.set_state(Form.check_plaintiff_legal_rep_national_id)
        return

    if text == "✅ اتمام و ادامه":
        await _finalize_plaintiff_legal_person(message, state)
        return

    await message.answer("⚠️ لطفاً از دکمه‌ها استفاده کنید:")


async def _finalize_plaintiff_legal_person(message: Message, state: FSMContext):
    data = await state.get_data()
    current = data.get("_check_current_plaintiff") or {}
    # ⭐ نمایندهٔ اول باید علاوه بر لیست representatives، در فیلدهای تخت
    # (national_id/representative_type) هم باشد — _fill_legal_person در
    # check_scenario.py دقیقاً همین دو فیلد را برای پر کردن نمایندهٔ اول
    # همراه با خودِ مرحلهٔ «خواهان» می‌خواند (الزام سامانه سنا)؛ حلقهٔ تب
    # «نماينده» فقط از نمایندهٔ دوم به بعد را پردازش می‌کند تا تکراری ثبت
    # نشود.
    reps = current.get("representatives") or []
    if reps:
        current["national_id"] = reps[0].get("national_id", "")
        current["representative_type"] = reps[0].get("representative_type", "")
    plaintiffs = data.get("check_plainiffs", [])
    plaintiffs.append(current)
    await state.update_data(check_plainiffs=plaintiffs, _check_current_plaintiff={})

    await message.answer("✅ خواهان با موفقیت ثبت شد.")

    used_types = [p.get("person_type") for p in plaintiffs]
    await message.answer(
        "آیا خواهان دیگری اضافه می‌کنید؟",
        reply_markup=create_ezhhar_declarant_person_type_kb(exclude=used_types))
    await state.set_state(Form.check_plaintiff_person_type)


@check_router.message(Form.check_plaintiff_more, F.text == "✅ اتمام و ادامه")
async def check_plaintiff_more_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    plaintiffs = data.get("check_plainiffs", [])
    if not plaintiffs:
        await message.answer("⚠️ حداقل یک خواهان باید ثبت شود.")
        return

    await message.answer(
        "👥 *مرحله ۶:* لطفاً *نوع شخصیت خوانده* را انتخاب فرمایید:",
        reply_markup=create_check_person_type_kb())
    await state.set_state(Form.check_defendant_person_type)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۶ — اطلاعات خوانده (مانند مخاطب)
# ══════════════════════════════════════════════════════════════════════════════
@check_router.message(Form.check_defendant_person_type)
async def check_defendant_person_type_handler(message: Message, state: FSMContext):
    text = message.text or ""
    data = await state.get_data()
    defendants = data.get("check_defendants", [])
    used_types = [d.get("person_type") for d in defendants]

    if text == "✅ اتمام و ادامه":
        if not defendants:
            await message.answer("⚠️ حداقل یک خوانده باید اضافه شود.")
            return

        # ⭐ مشابه مخاطب: اگر فقط «وکیل» داریم و هیچ حقیقی/حقوقی نیست، خطا
        has_lawyer = any(d.get("person_type") == "وکیل" for d in defendants)
        has_real_or_legal = any(d.get("person_type") in ("شخص حقیقی", "شخص حقوقی") for d in defendants)
        if has_lawyer and not has_real_or_legal:
            await message.answer(
                "⚠️ اگر خوانده *وکیل* است، باید حداقل یک خوانده *شخص حقیقی یا حقوقی* نیز ثبت شود.\n\n"
                "لطفاً نوع شخصیت خوانده بعدی را انتخاب کنید:")
            return

        # ⭐ عناوین اعسار — دو شاهد (با کدملی) به‌صورت الزامی گرفته می‌شود
        if data.get("check_request_title") in CHECK_AASAR_TITLES:
            await message.answer(
                "🔍 *مرحله ۷:* ثبت شهود (الزامی — ۲ نفر)\n\n"
                "لطفاً *کدملی شاهد اول (۱ از ۲)* را وارد فرمایید:",
                reply_markup=back_only_kb)
            await state.set_state(Form.check_witness_national_id)
            return

        # رفتن به مرحله مطلع/گواه
        await message.answer(
            "🔍 *مرحله ۷:* آیا *مطلع یا گواه* دارید؟\n\n"
            "در صورت وجود، *کدملی* مطلع/گواه را ارسال فرمایید.\n"
            "_(در غیر این صورت گزینه «اتمام» را انتخاب کنید)_",
            reply_markup=check_addressee_add_more_kb)
        await state.set_state(Form.check_witness_national_id)
        return

    if text not in ["شخص حقیقی", "شخص حقوقی", "وکیل"]:
        await message.answer("⚠️ لطفاً از لیست، نوع شخصیت را انتخاب کنید:")
        return

    await state.update_data(_check_current_defendant={"person_type": text})

    if text == "شخص حقوقی":
        await message.answer(
            "🏢 لطفاً *شناسه ملی* شخص حقوقی خوانده را وارد فرمایید:\n"
            "_(۱۱ رقم)_",
            reply_markup=back_only_kb)
        await state.set_state(Form.check_defendant_company_id)
        return

    await message.answer(
        "🆔 لطفاً *کد ملی* خوانده را وارد فرمایید:",
        reply_markup=back_only_kb)
    await state.set_state(Form.check_defendant_national_id)


@check_router.message(Form.check_defendant_company_id)
async def check_defendant_company_id_handler(message: Message, state: FSMContext):
    text = _to_en(message.text or "")
    data = await state.get_data()

    if "بازگشت" in text:
        defendants = data.get("check_defendants", [])
        used_types = [d.get("person_type") for d in defendants]
        await message.answer(
            "👤 لطفاً نوع شخصیت خوانده را انتخاب کنید:",
            reply_markup=create_ezhhar_addressee_person_type_kb(exclude=used_types if defendants else []))
        await state.set_state(Form.check_defendant_person_type)
        return

    if not re.fullmatch(r"\d{11}", text):
        await message.answer("⚠️ شناسه ملی باید *۱۱ رقم* باشد. دوباره وارد فرمایید:")
        return

    for d in data.get("check_defendants", []):
        if d.get("company_id") == text and d.get("person_type") == "شخص حقوقی":
            await message.answer("⚠️ این شناسه ملی قبلاً برای خوانده ثبت شده است. لطفاً شناسه دیگری وارد فرمایید:")
            return

    current = data.get("_check_current_defendant") or {}
    # ⚠️ کلید باید دقیقاً «company_id» باشد — همان دلیل سمت خواهان.
    current["company_id"] = text
    # ⭐ اصلاحیه (کارفرما — دور ۳): برای خوانده حقوقی دیگر «نام شرکت»،
    # «نوع نماینده»، «کدملی مدیرعامل/نماینده» و «مدرک نمایندگی» پرسیده
    # نمی‌شود — عین الگوی مخاطبِ اظهارنامه و تجدیدنظرخوانده، فقط شناسه
    # ملی شرکت ثبت می‌شود (نام/اطلاعات شرکت در سامانه از استعلام ثنا
    # خودکار خوانده می‌شود؛ check_scenario._fill_legal_person مسیر بدون
    # نماینده را کامل پشتیبانی می‌کند).
    current["representative_type"] = ""
    current["national_id"] = ""
    defendants = data.get("check_defendants", [])
    defendants.append(current)
    await state.update_data(check_defendants=defendants, _check_current_defendant={})

    await message.answer(
        f"✅ *شخص حقوقی (خوانده)* با شناسه ملی `{text}` ثبت شد.\n\n"
        "آیا خوانده دیگری نیز وجود دارد؟\n"
        "_(در غیر این صورت دکمهٔ «اتمام و ادامه» را بفشارید)_",
        reply_markup=create_ezhhar_addressee_person_type_kb(show_finish=True))
    await state.set_state(Form.check_defendant_person_type)


# ⚠️ مسیر قدیمی «نوع نماینده / کدملی مدیرعامل / مدرک نمایندگی» برای خوانده
# حقوقی حذف شد (دستور کارفرما — دور ۳). stateهای check_defendant_representative_type
# و check_defendant_legal_rep_national_id دیگر از هیچ مسیری set نمی‌شوند؛ هندلرهای
# زیر فقط برای نشست‌های قدیمیِ وسطِ فلو باقی مانده‌اند و کاربر را به مسیر جدید
# هدایت می‌کنند.
@check_router.message(Form.check_defendant_representative_type)
async def check_defendant_representative_type_handler(message: Message, state: FSMContext):
    text = message.text or ""

    if "بازگشت" in text:
        await message.answer(
            "🏢 لطفاً *شناسه ملی* شخص حقوقی خوانده را وارد فرمایید:",
            reply_markup=back_only_kb)
        await state.set_state(Form.check_defendant_company_id)
        return

    # مسیر منسوخ — به ثبت مستقیم خوانده حقوقی برگردان
    await message.answer(
        "🏢 لطفاً *شناسه ملی* شخص حقوقی خوانده را وارد فرمایید:\n_(۱۱ رقم)_",
        reply_markup=back_only_kb)
    await state.set_state(Form.check_defendant_company_id)


@check_router.message(Form.check_defendant_legal_rep_national_id)
async def check_defendant_legal_rep_national_id_handler(message: Message, state: FSMContext):
    """⚠️ مسیر منسوخ (کارفرما — دور ۳): برای خوانده حقوقی دیگر نماینده/کدملی
    مدیرعامل پرسیده نمی‌شود. فقط برای نشست‌های قدیمی به شناسه ملی برمی‌گردد."""
    text = (message.text or "").strip()

    if text == "مدیرعامل" or text == "نماینده":
        await message.answer(
            "🏢 لطفاً *شناسه ملی* شخص حقوقی خوانده را وارد فرمایید:\n_(۱۱ رقم)_",
            reply_markup=back_only_kb)
        await state.set_state(Form.check_defendant_company_id)
        return

    await message.answer(
        "🏢 لطفاً *شناسه ملی* شخص حقوقی خوانده را وارد فرمایید:\n_(۱۱ رقم)_",
        reply_markup=back_only_kb)
    await state.set_state(Form.check_defendant_company_id)


@check_router.message(Form.check_defendant_national_id)
async def check_defendant_national_id_handler(message: Message, state: FSMContext):
    text = _to_en(message.text or "")
    data = await state.get_data()

    if "بازگشت" in text:
        defendants = data.get("check_defendants", [])
        used_types = [d.get("person_type") for d in defendants]
        await message.answer(
            "👤 لطفاً نوع شخصیت خوانده را انتخاب کنید:",
            reply_markup=create_ezhhar_addressee_person_type_kb(exclude=used_types if defendants else []))
        await state.set_state(Form.check_defendant_person_type)
        return

    if not re.fullmatch(r"\d{10}", text):
        await message.answer("⚠️ کد ملی باید *۱۰ رقم* باشد. دوباره وارد فرمایید:")
        return

    person_type = (data.get("_check_current_defendant") or {}).get("person_type", "شخص حقیقی")
    for d in data.get("check_defendants", []):
        if d.get("national_id") == text and d.get("person_type") == person_type:
            await message.answer("⚠️ این کد ملی قبلاً برای خوانده ثبت شده است. لطفاً کد ملی دیگری وارد فرمایید:")
            return

    # ⭐ مسیر وکیل — طبق دستور کارفرما: فقط شماره قرارداد وکالت گرفته
    # می‌شود؛ مقدار تمبر خودکار محاسبه می‌گردد (بدون تصویر — ثبت به‌صورت
    # «وکالت‌نامه الکترونیک» در سامانه انجام می‌شود، نه با آپلود تصویر).
    if person_type == "وکیل":
        current = data.get("_check_current_defendant") or {}
        current["national_id"] = text
        await state.update_data(_check_current_defendant=current)

        await message.answer(
            "📑 لطفاً *شماره قرارداد وکالت* را وارد فرمایید:\n_(دقیقاً ۱۶ رقمی)_",
            reply_markup=back_only_kb)
        await state.set_state(Form.check_defendant_vakalat_no)
        return

    # مسیر شخص حقیقی — مثل مخاطب
    current = data.get("_check_current_defendant") or {}
    current["national_id"] = text
    defendants = data.get("check_defendants", [])
    defendants.append(current)
    await state.update_data(check_defendants=defendants, _check_current_defendant={})

    # ⭐ اصلاحیه: کیبورد با دکمهٔ «اتمام و ادامه» — قبلاً بدون show_finish
    # بود و کاربر بعد از ثبت اولین خوانده راهی برای رفتن به مرحلهٔ بعد نداشت.
    await message.answer(
        f"✅ *شخص حقیقی (خوانده)* با کدملی `{text}` ثبت شد.\n\n"
        "آیا خوانده دیگری نیز وجود دارد؟\n"
        "_(در غیر این صورت دکمهٔ «اتمام و ادامه» را بفشارید)_",
        reply_markup=create_ezhhar_addressee_person_type_kb(show_finish=True))
    await state.set_state(Form.check_defendant_person_type)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۶-الف — شماره قرارداد وکالت و محاسبهٔ خودکار تمبر (فقط وکیل)
# ══════════════════════════════════════════════════════════════════════════════
@check_router.message(Form.check_defendant_vakalat_no)
async def check_defendant_vakalat_no_handler(message: Message, state: FSMContext):
    """دریافت شماره قرارداد وکالت (۱۶ رقمی) وکیلِ خوانده + محاسبهٔ خودکار تمبر.

    ⚠️ کلید ذخیره باید دقیقاً `contract_number` / `stamp_amount_value` باشد
    (نه `vakalat_no`) — check_scenario.py مقدار وکالت‌نامهٔ الکترونیک هر
    وکیل (خواهان یا خوانده) را از همین دو کلید می‌خوانَد.
    """
    text = (message.text or "").strip()
    data = await state.get_data()

    if "بازگشت" in text:
        await message.answer(
            "🆔 لطفاً *کد ملی* خوانده را وارد فرمایید:",
            reply_markup=back_only_kb)
        await state.set_state(Form.check_defendant_national_id)
        return

    contract_no = _to_en(text)
    if not re.fullmatch(r"\d{16}", contract_no):
        await message.answer("⚠️ شماره قرارداد وکالت باید *دقیقاً ۱۶ رقمی* باشد:")
        return

    current = data.get("_check_current_defendant") or {}
    current["contract_number"] = contract_no

    # ⭐ محاسبهٔ خودکار تمبر — قاعدهٔ یکسان کارفرما (۱۴۰۵/۰۶) برای «کلیهٔ
    # عناوین ثبت دادخواست» (سمت خوانده): مبلغ وارد شده ← تمبر طبق همان
    # مبلغ؛ بدون مبلغ / عنوان بی‌مبلغ ← تمبر ثابت ۲۰۰,۰۰۰ ریال (۲۰ تومان).
    amount = int(data.get("check_amount", 0) or 0)
    if amount > 0:
        try:
            duty = calculate_stamp_duty(amount) or {}
            stamp_rial = int(duty.get("tamber_bedvi", 0) or 0)
            if stamp_rial <= 0:
                # محاسبه هرگز نباید صفر بدهد؛ سقف پایین: ۲۰۰,۰۰۰ ریال
                stamp_rial = 200_000
            stamp_text = f"{stamp_rial // 10:,} تومان ({stamp_rial:,} ریال)"
        except Exception as calc_err:
            logger.error(f"[CHECK] خطا در محاسبه تمبر وکالت (خوانده): {calc_err}")
            stamp_rial = 200_000
            stamp_text = "۲۰,۰۰۰ تومان (۲۰۰,۰۰۰ ریال)"
    else:
        stamp_rial = 200_000
        stamp_text = "۲۰,۰۰۰ تومان (۲۰۰,۰۰۰ ریال)"

    current["stamp_amount_value"] = stamp_rial
    current["stamp_amount_text"] = stamp_text

    defendants = data.get("check_defendants", [])
    defendants.append(current)
    await state.update_data(check_defendants=defendants, _check_current_defendant={})

    # ⭐ اصلاحیه: کیبورد با دکمهٔ «اتمام و ادامه» — مثل مسیر شخص حقیقی خوانده
    # (اعتبارسنجیِ «حداقل یک خوانده حقیقی/حقوقی در کنار وکیل» داخل هندلر انجام می‌شود)
    await message.answer(
        f"✅ *وکیل* با کدملی `{current.get('national_id', '')}` ثبت شد.\n"
        f"📑 شماره قرارداد وکالت: `{contract_no}`\n"
        f"💰 مبلغ تمبر وکالت (خودکار محاسبه شد): *{stamp_text}*\n\n"
        "⚠️ چون *وکیل* اضافه کردید، *خوانده* (شخص حقیقی یا حقوقی) نیز باید وارد شود.\n\n"
        "لطفاً نوع شخصیت خوانده بعدی را انتخاب فرمایید:",
        reply_markup=create_ezhhar_addressee_person_type_kb(show_finish=True))
    await state.set_state(Form.check_defendant_person_type)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۶-ب — کد ملی نماینده/مدیرعامل شرکت خوانده (نه وکیل!)
# ══════════════════════════════════════════════════════════════════════════════
@check_router.message(Form.check_defendant_legal_rep_name)
async def check_defendant_legal_rep_name_handler(message: Message, state: FSMContext):
    """⚠️ نام این state گمراه‌کننده است ولی در واقعیت «کد ملی نماینده/مدیرعامل»
    شرکت خوانده را می‌گیرد — نه شماره وکالت‌نامه (آن مسیر جداست:
    Form.check_defendant_vakalat_no)."""
    text = _to_en((message.text or "").strip())
    data = await state.get_data()

    if "بازگشت" in text or "بازگشت" in (message.text or ""):
        await message.answer(
            "👥 لطفاً *نوع نماینده* شخص حقوقی را انتخاب کنید:",
            reply_markup=representative_type_kb)
        await state.set_state(Form.check_defendant_legal_rep_national_id)
        return

    if not re.fullmatch(r"\d{10}", text):
        await message.answer("⚠️ کد ملی باید *۱۰ رقم* باشد. دوباره وارد فرمایید:")
        return

    rep_type = data.get("check_defendant_current_representative_type", "نماینده")
    await state.update_data(_check_current_defendant_rep={
        "representative_type": rep_type,
        "national_id": text,
    })

    # ⭐ ارسال مدرک نمایندگی برای *هر دو* سمت (مدیرعامل و نماینده) الزامی
    # است — قبلاً فقط برای «نماینده» خواسته می‌شد.
    await message.answer(
        f"✅ *{rep_type}* با کدملی `{text}` دریافت شد.\n\n"
        "⚠️ ارسال تصویر *مدرک نمایندگی* الزامی است و در بخش منضمات ثبت خواهد شد.\n\n"
        "📸 لطفاً تصویر *مدرک نمایندگی* را ارسال فرمایید.\n"
        "_(مثلاً: روزنامه رسمی، آگهی تأسیس، وکالت‌نامه رسمی)_\n\n"
        "پس از ارسال همهٔ تصاویر، دکمه *«اتمام ارسال تصاویر»* را بفشارید.",
        reply_markup=check_rep_doc_images_kb)
    await state.set_state(Form.check_defendant_legal_rep_doc_image)


@check_router.message(Form.check_defendant_legal_rep_doc_image)
async def check_defendant_legal_rep_doc_image_handler(message: Message, state: FSMContext):
    if not message.photo:
        await message.answer("⚠️ لطفاً *عکس* مدرک نماینده را ارسال فرمایید.")
        return

    data = await state.get_data()
    images = data.get("check_defendant_legal_rep_doc_images", [])
    images.append(message.photo[-1].file_id)
    await state.update_data(check_defendant_legal_rep_doc_images=images)

    await message.answer(
        f"✅ تصویر شماره *{len(images)}* دریافت شد.\n\n"
        "می‌توانید تصویر دیگری ارسال کنید یا دکمه *«اتمام ارسال تصاویر»* را بفشارید:",
        reply_markup=check_rep_doc_images_kb)


@check_router.message(Form.check_defendant_legal_rep_doc_images_more)
async def check_defendant_legal_rep_doc_images_more_handler(message: Message, state: FSMContext):
    """این state دو نقش دارد: (۱) تأیید پایان ارسال تصاویرِ نمایندهٔ فعلی،
    (۲) پس از آن، تصمیم «نمایندهٔ دیگری اضافه کنم یا خوانده را نهایی کنم؟»
    ⭐ هر خوانده (شخص حقوقی) می‌تواند حداکثر ۵ نماینده/مدیرعامل داشته باشد."""
    text = message.text.strip() if message.text else ""
    data = await state.get_data()

    if text == "🔙 بازگشت":
        images = data.get("check_defendant_legal_rep_doc_images", [])
        if images:
            images.pop()
            await state.update_data(check_defendant_legal_rep_doc_images=images)
        await message.answer(
            "📷 لطفاً *تصویر مدرک نمایندگی* را ارسال فرمایید:",
            reply_markup=check_rep_doc_images_kb)
        await state.set_state(Form.check_defendant_legal_rep_doc_image)
        return

    if text == "✅ اتمام ارسال تصاویر":
        images = data.get("check_defendant_legal_rep_doc_images", [])
        if not images:
            await message.answer(
                "⚠️ ارسال تصویر *مدرک نمایندگی* الزامی است.\n\n"
                "لطفاً حداقل یک تصویر ارسال فرمایید:",
                reply_markup=check_rep_doc_images_kb)
            return

        current = data.get("_check_current_defendant") or {}
        reps = list(current.get("representatives", []))
        rep_info = data.get("_check_current_defendant_rep") or {}
        rep_index = len(reps) + 1
        rep_type = rep_info.get("representative_type", "نماینده")

        reps.append({
            "representative_type": rep_type,
            "national_id": rep_info.get("national_id", ""),
        })
        current["representatives"] = reps

        attachment_groups = data.get("check_attachment_groups", [])
        attachment_groups.append({
            "title": f"مدرک نمایندگی ({rep_type} {rep_index})",
            "images": list(images),
        })

        await state.update_data(
            _check_current_defendant=current,
            check_attachment_groups=attachment_groups,
            check_defendant_legal_rep_doc_images=[],
            _check_current_defendant_rep={})

        if len(reps) >= 5:
            await message.answer(
                f"✅ نماینده/مدیرعامل شمارهٔ {rep_index} ثبت شد.\n\n"
                "⚠️ سقف ۵ نماینده/مدیرعامل به‌ازای هر خوانده (شخص حقوقی) تکمیل شد.")
            await _finalize_defendant_legal_person(message, state)
            return

        await message.answer(
            f"✅ نماینده/مدیرعامل شمارهٔ {rep_index} ثبت شد.\n\n"
            "آیا نماینده/مدیرعامل دیگری برای همین خوانده اضافه می‌کنید؟\n"
            f"_(حداکثر ۵ نفر — تا الان: {len(reps)} نفر)_",
            reply_markup=check_legal_rep_add_more_kb)
        return

    if text == "➕ افزودن شخص نماینده":
        await message.answer(
            "👥 لطفاً *نوع نماینده* بعدی را انتخاب کنید:",
            reply_markup=representative_type_kb)
        await state.set_state(Form.check_defendant_legal_rep_national_id)
        return

    if text == "✅ اتمام و ادامه":
        await _finalize_defendant_legal_person(message, state)
        return

    await message.answer("⚠️ لطفاً از دکمه‌ها استفاده کنید:")


async def _finalize_defendant_legal_person(message: Message, state: FSMContext):
    data = await state.get_data()
    current = data.get("_check_current_defendant") or {}
    # ⭐ همان دلیل سمت خواهان — نمایندهٔ اول باید در فیلدهای تخت هم باشد.
    reps = current.get("representatives") or []
    if reps:
        current["national_id"] = reps[0].get("national_id", "")
        current["representative_type"] = reps[0].get("representative_type", "")
    defendants = data.get("check_defendants", [])
    defendants.append(current)
    await state.update_data(check_defendants=defendants, _check_current_defendant={})

    await message.answer("✅ خوانده با موفقیت ثبت شد.")

    used_types = [d.get("person_type") for d in defendants]
    await message.answer(
        "آیا خوانده دیگری اضافه می‌کنید؟",
        reply_markup=create_ezhhar_addressee_person_type_kb(exclude=used_types))
    await state.set_state(Form.check_defendant_person_type)


@check_router.message(Form.check_defendant_more, F.text == "✅ اتمام و ادامه")
async def check_defendant_more_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    defendants = data.get("check_defendants", [])
    if not defendants:
        await message.answer("⚠️ حداقل یک خوانده باید ثبت شود.")
        return

    # ⭐ عناوین اعسار — دو شاهد (با کدملی) به‌صورت الزامی گرفته می‌شود
    if data.get("check_request_title") in CHECK_AASAR_TITLES:
        await message.answer(
            "🔍 *مرحله ۷:* ثبت شهود (الزامی — ۲ نفر)\n\n"
            "لطفاً *کدملی شاهد اول (۱ از ۲)* را وارد فرمایید:",
            reply_markup=back_only_kb)
        await state.set_state(Form.check_witness_national_id)
        return

    await message.answer(
        "🔍 *مرحله ۷:* آیا *مطلع یا گواه* دارید؟",
        reply_markup=check_addressee_add_more_kb)
    await state.set_state(Form.check_witness_national_id)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۷ — مطلع/گواه (کدملی + نام)
# ══════════════════════════════════════════════════════════════════════════════
@check_router.message(Form.check_witness_national_id)
async def check_witness_national_id_handler(message: Message, state: FSMContext):
    text = _to_en(message.text or "")

    if "بازگشت" in text:
        data = await state.get_data()
        # ⭐ طلاق توافقی: بخش خوانده وجود ندارد — بازگشت به خواهان
        if data.get("check_request_title") == CHECK_TALAGH_TOAFIGHI_TITLE:
            plaintiffs = data.get("check_plainiffs", [])
            if plaintiffs:
                plaintiffs.pop()
                await state.update_data(check_plainiffs=plaintiffs)
            used_types = [p.get("person_type") for p in plaintiffs]
            await message.answer(
                "👤 *مرحله ۵:* لطفاً *نوع شخصیت خواهان* را انتخاب فرمایید:",
                reply_markup=create_ezhhar_declarant_person_type_kb(exclude=used_types if plaintiffs else []))
            await state.set_state(Form.check_plaintiff_person_type)
            return
        defendants = data.get("check_defendants", [])
        if defendants:
            defendants.pop()  # ⬅️ خط جاافتاده در نسخهٔ قبلی — حالا اصلاح شد
            await state.update_data(check_defendants=defendants)
        await message.answer(
            "👥 *مرحله ۶:* لطفاً *نوع شخصیت خوانده* را انتخاب فرمایید:",
            reply_markup=create_check_person_type_kb())
        await state.set_state(Form.check_defendant_person_type)
        return

    data = await state.get_data()
    is_aasar_title = data.get("check_request_title") in CHECK_AASAR_TITLES

    if "اتمام" in text:
        # بررسی: اگر اعسار=بله → حداقل دو شخص حقیقی در مطلع/گواه الزامی است
        witnesses = data.get("check_witnesses", [])
        aasar = data.get("check_aasar", False)
        if is_aasar_title:
            # ⭐ عناوین اعسار — دو شاهد الزامی است؛ اتمام مجاز نیست
            await message.answer(
                "⚠️ برای عناوین *اعسار*، ثبت *دو شاهد* (با کدملی) الزامی است.\n\n"
                f"_(تاکنون: {len(witnesses)} از ۲)_\n\n"
                "لطفاً *کدملی شاهد بعدی* را وارد فرمایید:",
                reply_markup=back_only_kb)
            return
        if aasar:
            real_witnesses = [w for w in witnesses if w.get("person_type") == "شخص حقیقی"]
            if len(real_witnesses) < 2:
                await message.answer(
                    "⚠️ با توجه به اینکه درخواست *اعسار از هزینه دادرسی* دارید، "
                    "حداقل *دو شخص حقیقی* باید در بخش مطلع/گواه وارد شوند.\n\n"
                    "لطفاً کد ملی شخص حقیقی دیگر را وارد فرمایید:",
                    reply_markup=check_addressee_add_more_kb)
                return

        await _ask_check_text(message, state)
        return

    if not re.fullmatch(r"\d{10}", text):
        await message.answer("⚠️ کد ملی باید *۱۰ رقم* باشد. دوباره وارد فرمایید:")
        return

    witnesses = data.get("check_witnesses", [])
    for w in witnesses:
        if w.get("national_id") == text:
            await message.answer(
                "⚠️ این کد ملی قبلاً برای مطلع/گواه ثبت شده است. لطفاً کد ملی دیگری وارد فرمایید:")
            return

    # ⭐ اصلاحیه طبق دستور کارفرما: نام مطلع/گواه دیگر پرسیده نمی‌شود —
    # سناریوی سامانه نام را خودکار از استعلام ثنا (بر اساس کدملی) برمی‌دارد.
    witnesses.append({
        "person_type": "شخص حقیقی",
        "national_id": text,
        "name": "",
    })
    await state.update_data(check_witnesses=witnesses)

    # ⭐ عناوین اعسار — حداقل دو شاهد الزامی؛ پس از شاهد دوم (و هر شاهد
    # بعدی) طبق دستور کارفرما (دور ۳) سوال «شاهد دیگری دارید؟» پرسیده می‌شود
    # تا کاربر در صورت وجود، شهود بیشتری اضافه کند (پاسخ منفی → شرح متن).
    if is_aasar_title:
        if len(witnesses) >= 2:
            await message.answer(
                f"✅ *شاهد {len(witnesses)}* با کدملی `{text}` ثبت شد.\n\n"
                "✅ هر دو شاهد الزامی ثبت شدند.\n\n"
                "آیا *شاهد دیگری* نیز دارید؟",
                reply_markup=check_addressee_add_more_kb)
            await state.set_state(Form.check_more_witnesses)
            return
        await message.answer(
            f"✅ *شاهد اول* با کدملی `{text}` ثبت شد.\n\n"
            "لطفاً *کدملی شاهد دوم (۲ از ۲)* را وارد فرمایید:",
            reply_markup=back_only_kb)
        return

    await message.answer(
        f"✅ *شخص حقیقی (مطلع/گواه)* با کدملی `{text}` ثبت شد.\n\n"
        "آیا مطلع یا گواه دیگری نیز وجود دارد؟",
        reply_markup=check_addressee_add_more_kb)
    await state.set_state(Form.check_more_witnesses)


# ⭐ اصلاحیه: هندلر «نام مطلع/گواه» حذف شد — طبق دستور کارفرما بعد از
# ارسال کدملی مطلع/گواه، نام دیگر پرسیده نمی‌شود (نام از استعلام ثنا
# خودکار در سامانه درج می‌شود). مستقیم به مرحلهٔ «مطلع/گواه دیگر؟» می‌رویم.


@check_router.message(Form.check_more_witnesses)
async def check_more_witnesses_handler(message: Message, state: FSMContext):
    text = message.text or ""
    data = await state.get_data()
    is_aasar_title = data.get("check_request_title") in CHECK_AASAR_TITLES

    if text == "➕ افزودن مطلع یا گواه دیگر":
        await message.answer(
            "🔍 *مرحله ۷:* آیا *مطلع یا گواه* دیگری دارید؟\n\n"
            "در صورت وجود، *کدملی* مطلع/گواه را ارسال فرمایید.",
            reply_markup=check_addressee_add_more_kb)
        await state.set_state(Form.check_witness_national_id)
        return

    if text == "✅ اتمام و ادامه":
        # بررسی: اگر اعسار=بله → حداقل دو شخص حقیقی در مطلع/گواه الزامی است
        witnesses = data.get("check_witnesses", [])
        aasar = data.get("check_aasar", False)
        if is_aasar_title:
            # ⭐ عناوین اعسار — دو شاهد الزامی؛ کمتر از آن مجاز نیست
            if len(witnesses) < 2:
                await message.answer(
                    "⚠️ برای عناوین *اعسار*، ثبت *دو شاهد* (با کدملی) الزامی است.\n\n"
                    f"_(تاکنون: {len(witnesses)} از ۲)_\n\n"
                    "لطفاً *کدملی شاهد بعدی* را وارد فرمایید:",
                    reply_markup=back_only_kb)
                await state.set_state(Form.check_witness_national_id)
                return
            await _ask_check_text(message, state)
            return
        if aasar:
            real_witnesses = [w for w in witnesses if w.get("person_type") == "شخص حقیقی"]
            if len(real_witnesses) < 2:
                await message.answer(
                    "⚠️ با توجه به اینکه درخواست *اعسار از هزینه دادرسی* دارید، "
                    "حداقل *دو شخص حقیقی* باید در بخش مطلع/گواه وارد شوند.\n\n"
                    "لطفاً کد ملی شخص حقیقی دیگر را وارد فرمایید:",
                    reply_markup=check_addressee_add_more_kb)
                await state.set_state(Form.check_witness_national_id)
                return

        await _ask_check_text(message, state)
        return

    if text == "🔙 بازگشت":
        witnesses = data.get("check_witnesses", [])
        if witnesses:
            witnesses.pop()
            await state.update_data(check_witnesses=witnesses)
        if is_aasar_title:
            # ⭐ عناوین اعسار — حذف شاهد آخر و درخواست مجدد همان
            await message.answer(
                f"📷 شاهد آخر حذف شد. _(تاکنون: {len(witnesses)} از ۲)_\n\n"
                "لطفاً *کدملی شاهد* را وارد فرمایید:",
                reply_markup=back_only_kb)
            await state.set_state(Form.check_witness_national_id)
            return
        await message.answer(
            "🔍 *مرحله ۷:* آیا *مطلع یا گواه* دارید؟",
            reply_markup=check_addressee_add_more_kb)
        await state.set_state(Form.check_witness_national_id)
        return

    await message.answer("⚠️ لطفاً از دکمه‌ها استفاده کنید:")


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۸ — شرح متن دادخواست (متن یا فایل ورد)
# ══════════════════════════════════════════════════════════════════════════════
async def _ask_check_text(message: Message, state: FSMContext):
    """⭐ دور ۳ (دستور کارفرما): در همهٔ بخش‌ها، قبل از دریافت متن/فایل ورد،
    ابتدا «روش ارسال متن» از کاربر پرسیده می‌شود (تایپ مستقیم یا فایل ورد)
    و فقط پس از انتخاب، متن/فایل دریافت می‌گردد — عین الگوی اظهارنامه/
    لایحه/تجدیدنظر (ezhhar_text_choice / lavayeh_text_choice / tn_text_choice).
    """
    await message.answer(
        "📄 *مرحله ۸:* شرح متن دادخواست\n\n"
        "لطفاً *روش ارسال متن* خود را انتخاب فرمایید:",
        reply_markup=text_input_method_kb)
    await state.set_state(Form.check_text_choice)


@check_router.message(Form.check_text_choice)
async def check_text_choice_handler(message: Message, state: FSMContext):
    """انتخاب روش ورود شرح متن دادخواست — تایپ مستقیم یا فایل ورد.

    ⭐ دور ۳: تا کاربر یکی از دو گزینه را انتخاب نکرده، متن/فایل او
    پذیرفته نمی‌شود و دوباره همان سوال تکرار می‌شود.
    """
    text = (message.text or "").strip()

    if text == "🔙 بازگشت":
        await message.answer(
            "🔍 *مرحله ۷:* آیا *مطلع یا گواه* دارید؟\n\n"
            "در صورت وجود، *کدملی* مطلع/گواه را ارسال فرمایید.\n"
            "_(در غیر این صورت گزینه «اتمام» را انتخاب کنید)_",
            reply_markup=check_addressee_add_more_kb)
        await state.set_state(Form.check_witness_national_id)
        return

    if text == "⌨️ تایپ مستقیم متن":
        await _prompt_check_text_typing(message, state)
        return

    if text == "📎 ارسال فایل ورد (.docx)":
        await message.answer(
            "📎 لطفاً *فایل ورد (.docx)* حاوی شرح متن دادخواست را ارسال فرمایید:\n\n"
            "💡 متن داخل فایل عیناً (با حفظ فرمت بولد و ...) در سامانه درج خواهد شد.",
            reply_markup=back_only_kb)
        await state.set_state(Form.check_text_input)
        return

    await message.answer(
        "⚠️ لطفاً ابتدا *روش ارسال متن* را انتخاب فرمایید:",
        reply_markup=text_input_method_kb)


async def _prompt_check_text_typing(message: Message, state: FSMContext):
    """نمایش اعلان تایپ متن (+ نمونه‌متن برای عناوین چک) بعد از «تایپ مستقیم»."""
    data = await state.get_data()
    request_title = data.get("check_request_title", "")

    # ⭐ نمونه‌متن فقط برای «صدور اجرائیه چک» و «مطالبه وجه چک»
    if request_title in CHECK_SAMPLE_TEXT_TITLES:
        if request_title == "صدور اجرائیه چک":
            suggested = (
                "ریاست محترم ........... به طرفیت ................. "
                "به موجب یک فقره چک به شماره ... مورخ ... به عهده بانک ملی به مبلغ ... ریال "
                "با کدرهگیری ... خواهان صدور اجرائیه میباشد به انضمام کلیه خسارات دادرسی و "
                "حق الوکاله وکیل و خسارات تاخیرتادیه از زمان سررسید لغایت زمان کامل اجرای حکم "
                "و حق الوکاله وکیل"
            )
        else:
            suggested = (
                "رياست محترم ................. به طرفيت ................... "
                "به موجب ........ فقره چک به شماره ......... مورخ ......... به عهده بانک ....... "
                "به انضمام کلیه هزینه های دادرسی و خسارات تاخیرتادیه از زمان سررسید "
                "لغایت زمان کامل اجرای حکم و حق الوکاله وکیل"
            )
        await message.answer(
            f"📝 *متن پیشنهادی:*\n\n{suggested}\n\n"
            "💡 می‌توانید متن فوق را *ویرایش* و ارسال فرمایید یا اگر متنی دارید، مستقیماً وارد کنید:\n"
            "_(می‌توانید متن را در چند پیام ارسال کنید)_",
            reply_markup=back_only_kb)
    else:
        # ⭐ سایر عناوین (طلاق، نفقه، تمکین، مهریه) — بدون متن نمونه
        await message.answer(
            "📝 لطفاً *شرح متن دادخواست* خود را ارسال فرمایید:\n"
            "_(می‌توانید در چند پیام ارسال کنید)_",
            reply_markup=back_only_kb)
    await state.set_state(Form.check_text)


async def _after_check_text(message: Message, state: FSMContext, final_text: str,
                             final_html: str = ""):
    """
    ذخیره متن نهایی + رفتن به مرحله بعد (توضیحات اضافی).

    ⭐ اصلاحیه: متن «عنوان خواسته» (check_khasteh_text) دیگر با شرح متن
    ترکیب نمی‌شود — سناریوی سامانه این دو را در دو فیلد جداگانه ثبت
    می‌کند (txtDescription برای خواسته، ادیتور شرح برای متن) و ترکیبِ
    قبلی باعث تکرار دوبار متن خواسته در سامانه می‌شد.
    """
    await state.update_data(
        check_text=final_text.strip(),
        check_text_html=final_html or "")

    # رفتن به مرحله توضیحات اضافی
    await message.answer(
        "📝 *مرحله ۹:* آیا *توضیحات اضافی* دارید؟",
        reply_markup=check_extra_text_kb)
    await state.set_state(Form.check_extra_text)


async def _ask_check_next_after_text(message: Message, state: FSMContext, final_text: str,
                                    final_html: str = ""):
    """
    ادامهٔ جریان بعد از ثبت متن (برای ویرایش: بازگشت به پیش‌نمایش).
    """
    if await _check_maybe_return_to_preview(message, state):
        return
    await _after_check_text(message, state, final_text, final_html)


async def _process_check_docx(message: Message, state: FSMContext, bot: Bot,
                              user_id: int, chat_id: int):
    """پردازش فایل ورد (.docx) شرح متن دادخواست — استخراج متن + HTML
    با فرمت، ذخیره file_id/نام فایل برای ارسال به مدیر و ادامهٔ جریان.

    ⭐ اصلاحیه: قبلاً هیچ هندلری برای فایل ورد در فلوی چک وجود نداشت و
    check_docx_file_id هرگز ذخیره نمی‌شد (فایل ورد کاربر عملاً گم می‌شد).
    """
    from text_collector import process_docx_input

    doc = message.document
    extra_updates = {
        "check_docx_file_id": doc.file_id,
        "check_docx_file_name": doc.file_name,
    }

    async def _on_check_docx_complete(final_text, final_html, st, b, cid,
                                      was_editing=False, char_count=0):
        await b.send_message(
            cid,
            f"✅ متن دادخواست از فایل ورد دریافت شد ({char_count} کاراکتر).")
        await _ask_check_next_after_text(message, state, final_text, final_html)

    await process_docx_input(
        message=message,
        user_id=user_id,
        chat_id=chat_id,
        state=state,
        bot=bot,
        on_complete=_on_check_docx_complete,
        text_state_key="check_text",
        html_state_key="check_text_html",
        extra_state_updates=extra_updates,
        processing_msg="⏳ در حال پردازش فایل ورد...")


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۸.۵ — ثبت گواهی ازدواج (فقط برای عناوین خانواده)
# ══════════════════════════════════════════════════════════════════════════════
@check_router.message(Form.check_marriage_cert_image)
async def check_marriage_cert_image_handler(message: Message, state: FSMContext):
    if not message.photo:
        text = (message.text or "").strip()
        if text in ("✅ ادامه", "➕ افزودن تصویر دیگر", "🔙 بازگشت"):
            # ⭐ دکمه‌های کیبورد در حالت دریافت تصویر — هدایت به منطق هندلر «بیشتر»
            await check_marriage_cert_more_handler(message, state)
            return
        await message.answer("⚠️ لطفاً *عکس* گواهی ازدواج را ارسال فرمایید.")
        return

    data = await state.get_data()
    images = data.get("check_marriage_cert_images", [])
    images.append(message.photo[-1].file_id)
    await state.update_data(check_marriage_cert_images=images)

    if len(images) == 1:
        await message.answer("✅ تصویر اول دریافت شد. تصویر دوم (صفحه پشت) را ارسال فرمایید:")
    else:
        # ⭐ اصلاحیه: قبلاً کیبورد check_more_docs_kb (دکمه‌های بی‌هندلر) نشان
        # داده می‌شد و state عوض نمی‌شد → بن‌بست. اکنون state درست + کیبورد
        # منطبق با هندلر check_marriage_cert_more نمایش داده می‌شود.
        await message.answer(
            "✅ تصاویر گواهی ازدواج دریافت شد.\n\n"
            "در صورت وجود تصویر دیگر، ارسال فرمایید یا *«ادامه»* را بفشارید:",
            reply_markup=check_images_continue_kb)
        await state.set_state(Form.check_marriage_cert_more)


@check_router.message(Form.check_marriage_cert_more)
async def check_marriage_cert_more_handler(message: Message, state: FSMContext):
    # ⭐ عکس در این state هم پذیرفته می‌شود — همان منطق هندلر تصویر اجرا می‌شود
    if message.photo:
        await check_marriage_cert_image_handler(message, state)
        return

    text = message.text.strip() if message.text else ""

    if text == "➕ افزودن تصویر دیگر":
        await message.answer(
            "📷 تصویر دیگر گواهی ازدواج را ارسال فرمایید:",
            reply_markup=check_images_continue_kb)
        await state.set_state(Form.check_marriage_cert_image)
        return

    if text == "✅ ادامه":
        # ⭐ قبل از ادامه، شماره سند ازدواج و تاریخ عقد دریافت می‌شود —
        # این دو فیلد برای ثبت «سند ازدواج» در بخش منضمات سامانه (txtNo /
        # txtIssueDate) لازم است.
        await message.answer(
            "🔢 لطفاً *شماره سند ازدواج* را وارد فرمایید:",
            reply_markup=back_only_kb)
        await state.set_state(Form.check_marriage_cert_no)
        return

    if text == "🔙 بازگشت":
        data = await state.get_data()
        images = data.get("check_marriage_cert_images", [])
        if images:
            images.pop()
            await state.update_data(check_marriage_cert_images=images)
        await message.answer(
            "📷 لطفاً تصاویر *گواهی ازدواج* را ارسال فرمایید:\n"
            "_(صفحه اول و دوم)_",
            reply_markup=check_images_continue_kb)
        await state.set_state(Form.check_marriage_cert_image)
        return

    await message.answer("⚠️ لطفاً از دکمه‌ها استفاده کنید:")


@check_router.message(Form.check_marriage_cert_no)
async def check_marriage_cert_no_input_handler(message: Message, state: FSMContext):
    text = (message.text or "").strip()

    if "بازگشت" in text:
        await message.answer(
            "✅ تصاویر گواهی ازدواج دریافت شد.",
            reply_markup=check_more_docs_kb)
        await state.set_state(Form.check_marriage_cert_more)
        return

    if not text:
        await message.answer("⚠️ لطفاً *شماره سند ازدواج* را وارد فرمایید:")
        return

    await state.update_data(check_marriage_cert_no=_to_en(text))
    await message.answer(
        "📅 لطفاً *تاریخ وقوع عقد* را به‌صورت `1403/06/15` وارد فرمایید:",
        reply_markup=back_only_kb)
    await state.set_state(Form.check_marriage_date)


@check_router.message(Form.check_marriage_date)
async def check_marriage_date_input_handler(message: Message, state: FSMContext):
    text = (message.text or "").strip()

    if "بازگشت" in text:
        await message.answer(
            "🔢 لطفاً *شماره سند ازدواج* را وارد فرمایید:",
            reply_markup=back_only_kb)
        await state.set_state(Form.check_marriage_cert_no)
        return

    normalized = _to_en(text).replace("-", "/")
    if not re.fullmatch(r"\d{4}/\d{1,2}/\d{1,2}", normalized):
        await message.answer(
            "⚠️ لطفاً تاریخ را به‌صورت صحیح (مثال: `1403/06/15`) وارد فرمایید:")
        return

    await state.update_data(check_marriage_date=normalized)
    # ⭐ اصلاحیه (کارفرما — دور ۳): سوال «مدرک یا تصویر دیگری دارید؟» باید
    # *قبل از انتخاب صلاحیت دادگاه* و درست بعد از اطلاعات سند ازدواج پرسیده
    # شود (قبلاً بعد از صلاحیت پرسیده می‌شد که جای اشتباهی بود).
    await _ask_check_extra_docs(message, state)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۸.۵ — تصاویر استشهادیه (اعسار=بله یا عناوین اعسار — الزامی)
# ══════════════════════════════════════════════════════════════════════════════
@check_router.message(Form.check_esteshahadieh_image)
async def check_esteshahadieh_image_handler(message: Message, state: FSMContext):
    if not message.photo:
        text = (message.text or "").strip()
        if text in ("✅ ادامه", "➕ افزودن تصویر دیگر", "🔙 بازگشت"):
            # ⭐ دکمه‌های کیبورد در حالت دریافت تصویر — هدایت به منطق هندلر «بیشتر»
            await check_esteshahadieh_more_handler(message, state)
            return
        await message.answer("⚠️ لطفاً *عکس* استشهادیه را ارسال فرمایید.")
        return

    data = await state.get_data()
    images = data.get("check_esteshahadieh_images", [])
    images.append(message.photo[-1].file_id)
    await state.update_data(check_esteshahadieh_images=images)

    # ⭐ اصلاحیه (دستور کارفرما): یک تصویر هم کافی است — قبلاً تصویر دوم
    # اجباری بود؛ حالا بعد از هر تصویر (حتی اولی) امکان «ادامه» وجود دارد.
    # (قبلاً کیبورد check_more_docs_kb هم دکمه‌های بی‌هندلر داشت و کاربر در
    # بن‌بست می‌افتاد.)
    await message.answer(
        f"✅ تصویر {len(images)} استشهادیه دریافت شد.\n\n"
        "در صورت وجود تصویر دیگر، ارسال فرمایید یا *«ادامه»* را بفشارید:",
        reply_markup=check_images_continue_kb)
    await state.set_state(Form.check_esteshahadieh_more)


@check_router.message(Form.check_esteshahadieh_more)
async def check_esteshahadieh_more_handler(message: Message, state: FSMContext):
    # ⭐ عکس در این state هم پذیرفته می‌شود — همان منطق هندلر تصویر اجرا می‌شود
    if message.photo:
        await check_esteshahadieh_image_handler(message, state)
        return

    text = message.text.strip() if message.text else ""

    if text == "➕ افزودن تصویر دیگر":
        await message.answer(
            "📷 تصویر استشهادیه بعدی را ارسال فرمایید:",
            reply_markup=check_images_continue_kb)
        await state.set_state(Form.check_esteshahadieh_image)
        return

    if text == "✅ ادامه":
        data = await state.get_data()
        images = data.get("check_esteshahadieh_images", [])
        # ⭐ اصلاحیه (دستور کارفرما): حداقل «یک» تصویر کافی است — قبلاً دو
        # تصویر الزامی بود.
        if not images:
            await message.answer(
                "⚠️ ارسال *حداقل یک تصویر* استشهادیه الزامی است. لطفاً تصویر آن را ارسال فرمایید:",
                reply_markup=check_images_continue_kb)
            await state.set_state(Form.check_esteshahadieh_image)
            return

        # ⭐ عناوین اعسار — پس از استشهادیه، لیست اموال گرفته می‌شود
        if data.get("check_request_title") in CHECK_AASAR_TITLES:
            await message.answer(
                "📋 *مرحله ۱۰:* لطفاً تصاویر *لیست اموال* را ارسال فرمایید:\n"
                "_(الزامی)_",
                reply_markup=check_images_continue_kb)
            await state.set_state(Form.check_assets_list_image)
            return

        # ادامه: تصاویر چک یا پیوست‌ها
        if await _check_maybe_return_to_preview(message, state):
            return
        await _ask_check_next_after_images(message, state)
        return

    if text == "🔙 بازگشت":
        data = await state.get_data()
        images = data.get("check_esteshahadieh_images", [])
        if images:
            images.pop()
            await state.update_data(check_esteshahadieh_images=images)
        await message.answer(
            "📷 لطفاً تصاویر *استشهادیه* را ارسال فرمایید:\n"
            "_(حداقل یک تصویر)_",
            reply_markup=check_images_continue_kb)
        await state.set_state(Form.check_esteshahadieh_image)
        return

    await message.answer("⚠️ لطفاً از دکمه‌ها استفاده کنید:")


# ══════════════════════════════════════════════════════════════════════════════
# ⭐ مرحله ۱۰ — تصاویر لیست اموال (فقط عناوین اعسار — الزامی)
# ══════════════════════════════════════════════════════════════════════════════
@check_router.message(Form.check_assets_list_image)
async def check_assets_list_image_handler(message: Message, state: FSMContext):
    if not message.photo:
        text = (message.text or "").strip()
        if text in ("✅ ادامه", "➕ افزودن تصویر دیگر", "🔙 بازگشت"):
            # ⭐ دکمه‌های کیبورد در حالت دریافت تصویر — هدایت به منطق هندلر «بیشتر»
            await check_assets_list_more_handler(message, state)
            return
        await message.answer("⚠️ لطفاً *عکس* لیست اموال را ارسال فرمایید.")
        return

    data = await state.get_data()
    images = data.get("check_assets_list_images", [])
    images.append(message.photo[-1].file_id)
    await state.update_data(check_assets_list_images=images)

    await message.answer(
        f"✅ تصویر {len(images)} لیست اموال دریافت شد.\n\n"
        "در صورت وجود تصویر دیگر، ارسال فرمایید یا *«ادامه»* را بفشارید:",
        reply_markup=check_images_continue_kb)
    await state.set_state(Form.check_assets_list_more)


@check_router.message(Form.check_assets_list_more)
async def check_assets_list_more_handler(message: Message, state: FSMContext):
    # ⭐ عکس در این state هم پذیرفته می‌شود — همان منطق هندلر تصویر اجرا می‌شود
    if message.photo:
        await check_assets_list_image_handler(message, state)
        return

    text = message.text.strip() if message.text else ""

    if text == "➕ افزودن تصویر دیگر":
        await message.answer(
            "📷 تصویر بعدی *لیست اموال* را ارسال فرمایید:",
            reply_markup=check_images_continue_kb)
        await state.set_state(Form.check_assets_list_image)
        return

    if text == "✅ ادامه":
        data = await state.get_data()
        images = data.get("check_assets_list_images", [])
        if not images:
            await message.answer(
                "⚠️ ارسال تصویر *لیست اموال* الزامی است. لطفاً حداقل یک تصویر ارسال فرمایید:",
                reply_markup=check_images_continue_kb)
            await state.set_state(Form.check_assets_list_image)
            return

        # ادامه: تصاویر دادنامه یا اجرائیه
        await message.answer(
            "📄 *مرحله ۱۱:* لطفاً تصاویر *دادنامه یا اجرائیه* را ارسال فرمایید:\n"
            "_(الزامی)_",
            reply_markup=check_images_continue_kb)
        await state.set_state(Form.check_judgment_image)
        return

    if text == "🔙 بازگشت":
        # بازگشت به همان مرحلهٔ قبل — تصاویر استشهادیه
        data = await state.get_data()
        await message.answer(
            "📷 لطفاً تصاویر *استشهادیه* را ارسال فرمایید:\n"
            "_(حداقل یک تصویر)_",
            reply_markup=check_images_continue_kb)
        await state.set_state(Form.check_esteshahadieh_image)
        return

    await message.answer("⚠️ لطفاً از دکمه‌ها استفاده کنید:")


# ══════════════════════════════════════════════════════════════════════════════
# ⭐ مرحله ۱۱ — تصاویر دادنامه/اجرائیه + فیلدهای سند (فقط عناوین اعسار — الزامی)
#   شماره دادنامه (فقط عدد) → تاریخ (فرمت تاریخ) → نام دادگاه → شماره شعبه (فقط عدد)
# ══════════════════════════════════════════════════════════════════════════════
@check_router.message(Form.check_judgment_image)
async def check_judgment_image_handler(message: Message, state: FSMContext):
    if not message.photo:
        text = (message.text or "").strip()
        if text in ("✅ ادامه", "➕ افزودن تصویر دیگر", "🔙 بازگشت"):
            # ⭐ دکمه‌های کیبورد در حالت دریافت تصویر — هدایت به منطق هندلر «بیشتر»
            await check_judgment_more_handler(message, state)
            return
        await message.answer("⚠️ لطفاً *عکس* دادنامه یا اجرائیه را ارسال فرمایید.")
        return

    data = await state.get_data()
    images = data.get("check_judgment_images", [])
    images.append(message.photo[-1].file_id)
    await state.update_data(check_judgment_images=images)

    await message.answer(
        f"✅ تصویر {len(images)} دادنامه/اجرائیه دریافت شد.\n\n"
        "در صورت وجود تصویر دیگر، ارسال فرمایید یا *«ادامه»* را بفشارید:",
        reply_markup=check_images_continue_kb)
    await state.set_state(Form.check_judgment_more)


@check_router.message(Form.check_judgment_more)
async def check_judgment_more_handler(message: Message, state: FSMContext):
    # ⭐ عکس در این state هم پذیرفته می‌شود — همان منطق هندلر تصویر اجرا می‌شود
    if message.photo:
        await check_judgment_image_handler(message, state)
        return

    text = message.text.strip() if message.text else ""

    if text == "➕ افزودن تصویر دیگر":
        await message.answer(
            "📷 تصویر بعدی *دادنامه/اجرائیه* را ارسال فرمایید:",
            reply_markup=check_images_continue_kb)
        await state.set_state(Form.check_judgment_image)
        return

    if text == "✅ ادامه":
        data = await state.get_data()
        images = data.get("check_judgment_images", [])
        if not images:
            await message.answer(
                "⚠️ ارسال تصویر *دادنامه یا اجرائیه* الزامی است. "
                "لطفاً حداقل یک تصویر ارسال فرمایید:",
                reply_markup=check_images_continue_kb)
            await state.set_state(Form.check_judgment_image)
            return

        # ⭐ اطلاعات سند دادنامه — شماره دادنامه (فقط عدد)
        await message.answer(
            "📄 *اطلاعات دادنامه/اجرائیه:*\n\n"
            "۱/۴ — لطفاً *شماره دادنامه* را وارد فرمایید:\n"
            "_(فقط عدد)_",
            reply_markup=back_only_kb)
        await state.set_state(Form.check_judgment_no)
        return

    if text == "🔙 بازگشت":
        # بازگشت به همان مرحلهٔ قبل — تصاویر لیست اموال
        await message.answer(
            "📋 لطفاً تصاویر *لیست اموال* را ارسال فرمایید:\n"
            "_(الزامی)_",
            reply_markup=check_images_continue_kb)
        await state.set_state(Form.check_assets_list_image)
        return

    await message.answer("⚠️ لطفاً از دکمه‌ها استفاده کنید:")


@check_router.message(Form.check_judgment_no)
async def check_judgment_no_handler(message: Message, state: FSMContext):
    text = (message.text or "").strip()

    if text == "🔙 بازگشت":
        # بازگشت به همان مرحلهٔ قبل — تصاویر دادنامه
        await message.answer(
            "📄 لطفاً تصاویر *دادنامه یا اجرائیه* را ارسال فرمایید:\n"
            "_(الزامی)_",
            reply_markup=check_images_continue_kb)
        await state.set_state(Form.check_judgment_more)
        return

    normalized = _to_en(text)
    # ⭐ شماره دادنامه حتماً باید عدد باشد
    if not normalized or not re.fullmatch(r"\d{1,20}", normalized):
        await message.answer(
            "⚠️ *شماره دادنامه* باید فقط *عدد* باشد. لطفاً مجدداً وارد فرمایید:")
        return

    await state.update_data(check_judgment_no=normalized)
    await message.answer(
        "۲/۴ — لطفاً *تاریخ دادنامه* را به‌صورت `1403/06/15` وارد فرمایید:",
        reply_markup=back_only_kb)
    await state.set_state(Form.check_judgment_date)


@check_router.message(Form.check_judgment_date)
async def check_judgment_date_handler(message: Message, state: FSMContext):
    text = (message.text or "").strip()

    if text == "🔙 بازگشت":
        # بازگشت به همان مرحلهٔ قبل — شماره دادنامه
        await message.answer(
            "۱/۴ — لطفاً *شماره دادنامه* را وارد فرمایید:\n"
            "_(فقط عدد)_",
            reply_markup=back_only_kb)
        await state.set_state(Form.check_judgment_no)
        return

    # ⭐ تاریخ حتماً باید فرمت تاریخ داشته باشد (۱۴۰۳/۰۶/۱۵)
    normalized = _to_en(text).replace("-", "/").replace(".", "/")
    if not re.fullmatch(r"\d{4}/\d{1,2}/\d{1,2}", normalized):
        await message.answer(
            "⚠️ *تاریخ* واردشده معتبر نیست. لطفاً به‌صورت صحیح "
            "(مثال: `1403/06/15`) وارد فرمایید:")
        return

    # اعتبارسنجی منطقی اعداد تاریخ
    try:
        parts = normalized.split("/")
        if not (1 <= int(parts[1]) <= 12 and 1 <= int(parts[2]) <= 31):
            raise ValueError
    except (ValueError, IndexError):
        await message.answer(
            "⚠️ *تاریخ* واردشده معتبر نیست. لطفاً به‌صورت صحیح "
            "(مثال: `1403/06/15`) وارد فرمایید:")
        return

    await state.update_data(check_judgment_date=normalized)
    await message.answer(
        "۳/۴ — لطفاً *نام دادگاه* صادرکنندهٔ دادنامه را وارد فرمایید:",
        reply_markup=back_only_kb)
    await state.set_state(Form.check_judgment_court_name)


@check_router.message(Form.check_judgment_court_name)
async def check_judgment_court_name_handler(message: Message, state: FSMContext):
    text = (message.text or "").strip()

    if text == "🔙 بازگشت":
        # بازگشت به همان مرحلهٔ قبل — تاریخ دادنامه
        await message.answer(
            "۲/۴ — لطفاً *تاریخ دادنامه* را به‌صورت `1403/06/15` وارد فرمایید:",
            reply_markup=back_only_kb)
        await state.set_state(Form.check_judgment_date)
        return

    if not text or len(text) > 80:
        await message.answer(
            "⚠️ *نام دادگاه* نمی‌تواند خالی یا بیش از ۸۰ نویسه باشد. "
            "لطفاً مجدداً وارد فرمایید:")
        return

    await state.update_data(check_judgment_court_name=text)
    await message.answer(
        "۴/۴ — لطفاً *شماره شعبه* را وارد فرمایید:\n"
        "_(فقط عدد)_",
        reply_markup=back_only_kb)
    await state.set_state(Form.check_judgment_branch_no)


@check_router.message(Form.check_judgment_branch_no)
async def check_judgment_branch_no_handler(message: Message, state: FSMContext):
    text = (message.text or "").strip()

    if text == "🔙 بازگشت":
        # بازگشت به همان مرحلهٔ قبل — نام دادگاه
        await message.answer(
            "۳/۴ — لطفاً *نام دادگاه* صادرکنندهٔ دادنامه را وارد فرمایید:",
            reply_markup=back_only_kb)
        await state.set_state(Form.check_judgment_court_name)
        return

    normalized = _to_en(text)
    # ⭐ شماره شعبه حتماً باید عدد باشد
    if not normalized or not re.fullmatch(r"\d{1,10}", normalized):
        await message.answer(
            "⚠️ *شماره شعبه* باید فقط *عدد* باشد. لطفاً مجدداً وارد فرمایید:")
        return

    await state.update_data(check_judgment_branch_no=normalized)

    if await _check_maybe_return_to_preview(message, state):
        return

    # ⭐ عناوین اعسار — طبق دستور کارفرما: بعد از تکمیل اطلاعات دادنامه،
    # سوال «مدرک دیگری دارید؟» پرسیده می‌شود (نه بعد از صلاحیت دادگاه)؛
    # سپس صلاحیت دادگاه → پیش‌نمایش. (از دور ۳ برای همهٔ عناوین یکسان است.)
    data = await state.get_data()
    if data.get("check_request_title") in CHECK_AASAR_TITLES:
        await _ask_check_extra_docs(message, state)
        return
    await _ask_check_branch(message, state)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۸ — شرح متن (پذیرش متن چندبخشی یا فایل ورد)
# ══════════════════════════════════════════════════════════════════════════════
@check_router.message(Form.check_text)
async def check_text_handler(message: Message, state: FSMContext, bot: Bot):
    if message.text == "🔙 بازگشت":
        await message.answer(
            "🔍 *مرحله ۷:* آیا *مطلع یا گواه* دارید؟",
            reply_markup=check_addressee_add_more_kb)
        await state.set_state(Form.check_witness_national_id)
        return

    user_id = message.from_user.id
    chat_id = message.chat.id

    # ── پشتیبانی فایل ورد (.docx) — استخراج متن + HTML ──────────
    if message.document and message.document.file_name and message.document.file_name.lower().endswith(".docx"):
        await _process_check_docx(message, state, bot, user_id, chat_id)
        return

    if not message.text:
        await message.answer(
            "⚠️ لطفاً شرح متن را به صورت متن ارسال فرمایید.\nیا فایل .docx ارسال نمایید.")
        return

    # دکمه ارسال فایل ورد — ⚠️ متن دکمه «📎 ارسال فایل ورد (.docx)» است؛
    # قبلاً با «(docx)» بدون نقطه مقایسه می‌شد و هرگز مطابقت نمی‌کرد.
    if "ارسال فایل ورد" in message.text:
        await message.answer(
            "📎 لطفاً *فایل ورد (.docx)* حاوی شرح متن دادخواست را ارسال فرمایید:\n\n"
            "💡 متن داخل فایل عیناً (با حفظ فرمت بولد و ...) در سامانه درج خواهد شد.",
            reply_markup=back_only_kb)
        await state.set_state(Form.check_text_input)
        return

    # دکمه تایپ مستقیم متن
    if "تایپ مستقیم" in message.text:
        await message.answer(
            "📝 لطفاً *شرح متن دادخواست* خود را ارسال فرمایید:\n"
            "_(می‌توانید در چند پیام ارسال کنید)_",
            reply_markup=check_docx_option_kb)
        return

    # ⭐ اصلاحیه مهم: امضای صحیح collect_text_part — قبلاً با آرگومان‌های
    # نادرست (field/done_button/prompt_text/allow_docx) صدا زده می‌شد که
    # TypeError می‌داد و متن کاربر هرگز ذخیره نمی‌شد (هیچ اکشنی رخ نمی‌داد).
    from text_collector import collect_text_part

    async def _on_check_text_final(final_text, st, b, cid, was_editing=False):
        # ⭐ پارامتر was_editing برای سازگاری با text_collector (۵ آرگومان)
        await _ask_check_next_after_text(message, state, final_text)

    await collect_text_part(
        user_id=user_id,
        chat_id=chat_id,
        text=message.text,
        state=state,
        bot=bot,
        on_complete=_on_check_text_final,
        first_part_reply="⏳ در حال دریافت متن دادخواست...")


@check_router.message(Form.check_text_input)
async def check_text_input_handler(message: Message, state: FSMContext, bot: Bot):
    if message.text == "🔙 بازگشت":
        await _ask_check_text(message, state)
        return

    user_id = message.from_user.id
    chat_id = message.chat.id

    # ── پشتیبانی فایل ورد (.docx) — استخراج متن + HTML ──────────
    if message.document and message.document.file_name and message.document.file_name.lower().endswith(".docx"):
        await _process_check_docx(message, state, bot, user_id, chat_id)
        return

    if not message.text:
        await message.answer(
            "⚠️ لطفاً *فایل ورد (.docx)* یا متن را ارسال فرمایید:")
        return

    from text_collector import collect_text_part

    async def _on_check_text_final(final_text, st, b, cid, was_editing=False):
        # ⭐ پارامتر was_editing برای سازگاری با text_collector (۵ آرگومان)
        await _ask_check_next_after_text(message, state, final_text)

    await collect_text_part(
        user_id=user_id,
        chat_id=chat_id,
        text=message.text,
        state=state,
        bot=bot,
        on_complete=_on_check_text_final,
        first_part_reply="⏳ در حال دریافت متن دادخواست...")


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۹ — توضیحات اضافی (دلخواه)
# ══════════════════════════════════════════════════════════════════════════════
@check_router.message(Form.check_extra_text)
async def check_extra_text_handler(message: Message, state: FSMContext):
    text = message.text.strip() if message.text else ""

    if text == "🔙 بازگشت":
        await _ask_check_text(message, state)
        return

    # ⭐ دکمه «خیر، ادامه بده» — بدون توضیحات اضافی ادامه بده
    # (قبلاً متن خودِ دکمه به‌عنوان توضیحات ذخیره می‌شد!)
    if text in ("❌ خیر، ادامه بده", "⏭ رد کردن", "⏭ بدون توضیحات اضافی",
                "❌ خیر، ادامه به انتخاب دادگاه"):
        await state.update_data(check_extra_text="")
        if await _check_maybe_return_to_preview(message, state):
            return
        # ادامه: تصاویر چک یا استشهادیه یا گواهی ازدواج
        await _ask_check_next_after_images(message, state)
        return

    # ⭐ دکمه «بله، توضیحات اضافی دارم» — درخواست متن توضیحات
    if text == "✅ بله، توضیحات اضافی دارم":
        await message.answer(
            "📝 لطفاً *توضیحات اضافی* خود را ارسال فرمایید:\n"
            "_(یا برای ادامه بدون توضیحات، دکمهٔ زیر را بفشارید)_",
            reply_markup=check_extra_text_kb)
        return

    if not text:
        await message.answer(
            "⚠️ لطفاً توضیحات را ارسال فرمایید یا دکمهٔ «خیر، ادامه بده» را بفشارید:")
        return

    await state.update_data(check_extra_text=text)

    if await _check_maybe_return_to_preview(message, state):
        return

    # ادامه: تصاویر چک یا استشهادیه یا گواهی ازدواج
    await _ask_check_next_after_images(message, state)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۱۰ — تصاویر چک (به‌ازای هر فقره: کدرهگیری + دقیقاً ۳ تصویر)
# ══════════════════════════════════════════════════════════════════════════════
async def _ask_check_extra_docs(message: Message, state: FSMContext):
    """⭐ سوال «مدرک دیگری دارید؟» — برای *همهٔ* عناوین دادخواست (دور ۳).

    طبق دستور کارفرما این سوال باید *قبل از انتخاب صلاحیت دادگاه* و درست
    بعد از اسناد اختصاصیِ همان نوع دادخواست پرسیده شود — نه بعد از صلاحیت:
      - اجرائیه چک / مطالبه وجه چک → بعد از تکمیل تصاویر فقرات چک
      - مهریه (و سایر عناوین خانواده) → بعد از تصاویر و اطلاعات سند ازدواج
      - عناوین اعسار → بعد از تکمیل اطلاعات دادنامه (۴/۴)
      - مطالبه وجه بابت... → بعد از توضیحات اضافی (سند اختصاصی ندارد)
    پاسخ مثبت → فلوی پیوست (عنوان + تصاویر) و پاسخ منفی → انتخاب صلاحیت
    دادگاه. (نام قدیمی این تابع _ask_check_aasar_extra_docs بود.)
    """
    await message.answer(
        "📎 آیا *مدرک یا تصویر دیگری* برای دادخواست خود دارید؟",
        reply_markup=check_attachment_title_kb_first)
    await state.set_state(Form.check_attachment_title)


# نام قدیمی — برای سازگاری با ارجاع‌های احتمالی باقی می‌ماند
async def _ask_check_aasar_extra_docs(message: Message, state: FSMContext):
    await _ask_check_extra_docs(message, state)


async def _ask_check_next_after_images(message: Message, state: FSMContext):
    """
    انتخاب مسیر بعد از متن/توضیحات:
      - عناوین اعسار → تصاویر استشهادیه (الزامی — سپس لیست اموال و دادنامه)
      - اعسار=بله  → تصاویر استشهادیه (الزامی)
      - عنوان خانواده → تصاویر گواهی ازدواج (الزامی)
      - «مطالبه وجه بابت...» → بدون سند اختصاصی — سوال «مدرک دیگری؟» → صلاحیت
      - سایر → تصاویر چک (به‌ازای هر فقره: کدرهگیری + دقیقاً ۳ تصویر)
    """
    data = await state.get_data()
    request_title = data.get("check_request_title", "")
    aasar = data.get("check_aasar", False)
    # ⭐ اصلاحیه: اگر استشهادیه/گواهی ازدواج قبلاً دریافت شده، دوباره درخواست
    # نشود — قبلاً پس از پایان استشهادیه، همین تابع دوباره استشهادیه می‌خواست
    # و کاربر در حلقهٔ بی‌پایان گیر می‌کرد و هرگز به تصاویر چک/انتخاب دادگاه
    # نمی‌رسید.
    esteshahadieh_done = bool(data.get("check_esteshahadieh_images"))
    marriage_done = bool(data.get("check_marriage_cert_images"))
    # ⭐ سوال «مدرک دیگری؟» فقط یک بار — برای همهٔ عناوین (فلگ عمومی دور ۳)
    att_done = bool(data.get("check_att_done") or data.get("check_aasar_att_done"))

    # ⭐ عناوین اعسار → زنجیرهٔ الزامی:
    #   استشهادیه → لیست اموال → دادنامه (تصاویر + ۴ فیلد) →
    #   «مدرک دیگری دارید؟» → صلاحیت دادگاه → پیش‌نمایش
    # (دستور کارفرما: سوال پیوست دیگر بعد از تکمیل اطلاعات دادنامه پرسیده
    # می‌شود، نه بعد از صلاحیت دادگاه)
    if request_title in CHECK_AASAR_TITLES:
        if not esteshahadieh_done:
            await message.answer(
                "📷 *مرحله ۹:* لطفاً تصاویر *استشهادیه* را ارسال فرمایید:\n"
                "_(حداقل یک تصویر — اجباری)_",
                reply_markup=check_images_continue_kb)
            await state.set_state(Form.check_esteshahadieh_image)
            return
        if not data.get("check_assets_list_images"):
            await message.answer(
                "📋 *مرحله ۱۰:* لطفاً تصاویر *لیست اموال* را ارسال فرمایید:\n"
                "_(الزامی)_",
                reply_markup=check_images_continue_kb)
            await state.set_state(Form.check_assets_list_image)
            return
        if not data.get("check_judgment_images"):
            await message.answer(
                "📄 *مرحله ۱۱:* لطفاً تصاویر *دادنامه یا اجرائیه* را ارسال فرمایید:\n"
                "_(الزامی)_",
                reply_markup=check_images_continue_kb)
            await state.set_state(Form.check_judgment_image)
            return
        # ⭐ اطلاعات سند دادنامه (۴ فیلد) — اگر ناقص باشد از همان فیلد ادامه
        if not data.get("check_judgment_no"):
            await message.answer(
                "📄 *اطلاعات دادنامه/اجرائیه:*\n\n"
                "۱/۴ — لطفاً *شماره دادنامه* را وارد فرمایید:\n"
                "_(فقط عدد)_",
                reply_markup=back_only_kb)
            await state.set_state(Form.check_judgment_no)
            return
        if not data.get("check_judgment_date"):
            await message.answer(
                "۲/۴ — لطفاً *تاریخ دادنامه* را به‌صورت `1403/06/15` وارد فرمایید:",
                reply_markup=back_only_kb)
            await state.set_state(Form.check_judgment_date)
            return
        if not data.get("check_judgment_court_name"):
            await message.answer(
                "۳/۴ — لطفاً *نام دادگاه* صادرکنندهٔ دادنامه را وارد فرمایید:",
                reply_markup=back_only_kb)
            await state.set_state(Form.check_judgment_court_name)
            return
        if not data.get("check_judgment_branch_no"):
            await message.answer(
                "۴/۴ — لطفاً *شماره شعبه* را وارد فرمایید:\n"
                "_(فقط عدد)_",
                reply_markup=back_only_kb)
            await state.set_state(Form.check_judgment_branch_no)
            return
        # ⭐ سوال «مدرک دیگری دارید؟» — قبل از صلاحیت دادگاه (فقط یک بار)
        if not att_done:
            await _ask_check_extra_docs(message, state)
            return
        await _ask_check_branch(message, state)
        return

    # ⭐ اعسار=بله → تصاویر استشهادیه الزامی (فقط اگر هنوز دریافت نشده)
    if aasar and not esteshahadieh_done:
        await message.answer(
            "📷 *مرحله ۹:* لطفاً تصاویر *استشهادیه* را ارسال فرمایید:\n"
            "_(حداقل یک تصویر — اجباری)_",
            reply_markup=check_images_continue_kb)
        await state.set_state(Form.check_esteshahadieh_image)
        return

    # ⭐ عناوین خانواده → تصاویر گواهی ازدواج الزامی (فقط اگر هنوز دریافت نشده)
    if request_title in CHECK_FAMILY_TITLES and not marriage_done:
        await message.answer(
            "💍 *مرحله ۹:* لطفاً تصاویر *گواهی ازدواج* را ارسال فرمایید:\n"
            "_(صفحه اول و دوم — اجباری)_",
            reply_markup=check_images_continue_kb)
        await state.set_state(Form.check_marriage_cert_image)
        return

    # ⭐ «مطالبه وجه بابت...» → بدون سند اختصاصی — سوال «مدرک دیگری؟» و سپس
    # انتخاب صلاحیت دادگاه (دور ۳: این سوال حالا برای همهٔ عناوین *قبل از*
    # صلاحیت پرسیده می‌شود، نه بعد از آن)
    if request_title == "مطالبه وجه بابت...":
        if not att_done:
            await _ask_check_extra_docs(message, state)
            return
        await _ask_check_branch(message, state)
        return

    # ⭐ سایر عناوین (صدور اجرائیه چک / مطالبه وجه چک) — فلوی جدید طبق دستور
    # کارفرما: قبل از ورود به منضمات، ابتدا «تعداد فقرات چک» پرسیده می‌شود؛
    # سپس به‌ازای هر فقره، ابتدا «کدرهگیری» و بعد «تصویر چک» (۳ تصویر) دریافت
    # می‌گردد. ساختار داده: check_cheque_items=[{tracking_no, images}, ...]
    # ⭐ اصلاحیهٔ دور ۳: اگر فقرات چک قبلاً کامل گرفته شده (مسیر بازگشت/
    # ویرایش)، دوباره از کاربر گرفته نمی‌شود — مستقیم سوال «مدرک دیگری؟»
    # (یا صلاحیت، اگر قبلاً جواب داده شده) نمایش داده می‌شود.
    cheque_items = data.get("check_cheque_items") or []
    if cheque_items:
        if not att_done:
            await _ask_check_extra_docs(message, state)
            return
        await _ask_check_branch(message, state)
        return

    await state.update_data(
        check_cheque_items=[],
        check_tracking_list=[],
        check_images=[],
        check_tracking_no="",
        check_cheques_total=0,
        _current_cheque_index=1,
        _current_cheque_tracking="",
        _current_cheque_images=[])
    await message.answer(
        "🔢 *مرحله ۱۰:* لطفاً *تعداد فقرات چک* را وارد یا انتخاب فرمایید:\n"
        "_(از ۱ تا ۳۰)_",
        reply_markup=create_check_cheque_count_kb())
    await state.set_state(Form.check_cheques_count)


@check_router.message(Form.check_cheques_count)
async def check_cheques_count_handler(message: Message, state: FSMContext):
    """
    دریافت *تعداد فقرات چک* (۱ تا ۳۰) — آغاز حلقهٔ فقرات:
    به‌ازای هر فقره: ابتدا کدرهگیری، سپس ۳ تصویر چک.
    """
    text = _to_en(message.text or "")

    if "بازگشت" in text:
        # بازگشت به سوال توضیحات اضافی (مرحله قبل)
        await message.answer(
            "📝 *مرحله ۹:* آیا *توضیحات اضافی* دارید؟",
            reply_markup=check_extra_text_kb)
        await state.set_state(Form.check_extra_text)
        return

    if not re.fullmatch(r"\d{1,2}", text) or not (1 <= int(text) <= 30):
        await message.answer(
            "⚠️ لطفاً *تعداد فقرات چک* را به‌صورت عدد (۱ تا ۳۰) وارد یا از "
            "کیبورد انتخاب فرمایید:",
            reply_markup=create_check_cheque_count_kb())
        return

    total = int(text)
    await state.update_data(
        check_cheques_total=total,
        check_cheque_items=[],
        check_tracking_list=[],
        check_images=[],
        check_tracking_no="",
        _current_cheque_index=1,
        _current_cheque_tracking="",
        _current_cheque_images=[])

    await message.answer(
        f"🔢 *فقره ۱ از {total}:*\n\n"
        "لطفاً *کدرهگیری چک* را وارد فرمایید:\n_(فقط عدد)_",
        reply_markup=back_only_kb)
    await state.set_state(Form.check_cheque_tracking)


@check_router.message(Form.check_cheque_tracking)
async def check_cheque_tracking_handler(message: Message, state: FSMContext):
    """
    دریافت *کدرهگیری فقرهٔ جاری* — سپس درخواست تصاویر همان فقره (۳ تصویر).
    ⭐ فلوی جدید: کدرهگیری برای هر فقره (از جمله فقرهٔ اول) پرسیده می‌شود.
    """
    text = _to_en(message.text or "")
    data = await state.get_data()

    if "بازگشت" in text:
        # بازگشت: اگر فقرهٔ قبلی‌ای ثبت شده، آخرین فقره را حذف و دوباره
        # کدرهگیری همان فقره پرسیده می‌شود؛ در غیر این صورت بازگشت به تعداد.
        items = data.get("check_cheque_items", [])
        if items:
            items.pop()
            await state.update_data(
                check_cheque_items=items,
                check_images=[img for it in items for img in it.get("images", [])],
                check_tracking_list=[it.get("tracking_no", "") for it in items],
                _current_cheque_index=len(items) + 1,
                _current_cheque_tracking="",
                _current_cheque_images=[])
            idx = len(items) + 1
            total = data.get("check_cheques_total", 1)
            await message.answer(
                f"↩️ فقرهٔ {idx} حذف شد تا دوباره ثبت شود.\n\n"
                f"🔢 *فقره {idx} از {total}:*\n\n"
                "لطفاً *کدرهگیری چک* را وارد فرمایید:\n_(فقط عدد)_",
                reply_markup=back_only_kb)
            return
        # هیچ فقره‌ای ثبت نشده → بازگشت به سوال تعداد فقرات
        await message.answer(
            "🔢 لطفاً *تعداد فقرات چک* را وارد یا انتخاب فرمایید:\n_(از ۱ تا ۳۰)_",
            reply_markup=create_check_cheque_count_kb())
        await state.set_state(Form.check_cheques_count)
        return

    if not text or not re.fullmatch(r"\d{4,40}", text):
        await message.answer(
            "⚠️ کدرهگیری چک معتبر نیست.\n"
            "_(کدرهگیری عددی است — لطفاً فقط عدد را وارد فرمایید)_")
        return

    await state.update_data(_current_cheque_tracking=text)

    current_idx = data.get("_current_cheque_index", 1)
    total = data.get("check_cheques_total", 1)

    await message.answer(
        f"✅ کدرهگیری فقره {current_idx} ثبت شد.\n\n"
        f"📷 *فقره {current_idx} از {total}:* لطفاً *تصویر چک* را ارسال فرمایید:\n"
        f"_(۳ تصویر — می‌توانید هر سه را یکجا هم ارسال کنید)_",
        reply_markup=check_more_images_kb)
    await state.set_state(Form.check_cheque_images)


# ⭐ قفل به‌ازای هر چت — برای پردازش امنِ گروه تصاویر (آلبوم):
# وقتی کاربر ۳ عکس را همزمان می‌فرستد، هر عکس یک update جداگانه است؛
# قفل تضمین می‌کند خواندن-تغییر-نوشتنِ check_images ترتیبی و بدون از
# دست رفتن عکس انجام شود.
_cheque_img_locks: dict = {}


def _get_cheque_img_lock(chat_id: int) -> asyncio.Lock:
    lock = _cheque_img_locks.get(chat_id)
    if lock is None:
        lock = asyncio.Lock()
        _cheque_img_locks[chat_id] = lock
    return lock


@check_router.message(Form.check_cheque_images)
async def check_cheque_images_handler(message: Message, state: FSMContext):
    """
    دریافت *تصاویر فقرهٔ جاری* (دقیقاً ۳ تصویر):
      - هر عکس ذخیره و تأیید می‌شود (پردازش امن آلبوم/ارسال همزمان)
      - تکمیل ۳ تصویر → ثبت فقره → فقرهٔ بعدی (کدرهگیری → تصاویر)
        یا در صورت اتمام همهٔ فقرات → انتخاب صلاحیت دادگاه
    """
    if message.photo:
        lock = _get_cheque_img_lock(message.chat.id)
        async with lock:
            data = await state.get_data()
            images = data.get("_current_cheque_images", [])
            images.append(message.photo[-1].file_id)
            await state.update_data(_current_cheque_images=images)

            current_idx = data.get("_current_cheque_index", 1)
            total = data.get("check_cheques_total", 1)

            if len(images) < MAX_CHECK_IMAGES:
                await message.answer(
                    f"✅ تصویر {len(images)} از {MAX_CHECK_IMAGES} دریافت شد.\n"
                    f"لطفاً تصویر {len(images) + 1} را ارسال فرمایید:",
                    reply_markup=get_check_more_images_kb(len(images)))
                return

            # ⭐ ۳ تصویر فقرهٔ جاری کامل شد → ثبت فقره
            tracking = data.get("_current_cheque_tracking", "")
            items = data.get("check_cheque_items", [])
            items.append({"tracking_no": tracking, "images": list(images)})

            # همگام‌سازی فیلدهای مسطح (سازگاری با سناریو/پیش‌نمایش/ادمین)
            flat_images = [img for it in items for img in it.get("images", [])]
            track_list = [it.get("tracking_no", "") for it in items]
            await state.update_data(
                check_cheque_items=items,
                check_images=flat_images,
                check_tracking_list=track_list,
                check_tracking_no=(track_list[0] if track_list else ""),
                _current_cheque_images=[],
                _current_cheque_tracking="")

            if current_idx < total:
                # فقرهٔ بعدی — ابتدا کدرهگیری
                await state.update_data(_current_cheque_index=current_idx + 1)
                await message.answer(
                    f"✅ ۳ تصویر فقره {current_idx} ثبت شد.\n\n"
                    f"🔢 *فقره {current_idx + 1} از {total}:*\n\n"
                    "لطفاً *کدرهگیری چک* را وارد فرمایید:\n_(فقط عدد)_",
                    reply_markup=back_only_kb)
                await state.set_state(Form.check_cheque_tracking)
            else:
                # تمام فقرات کامل شد → سوال «مدرک دیگری دارید؟» و سپس صلاحیت دادگاه
                # ⭐ اصلاحیه (کارفرما — دور ۳): این سوال بعد از تکمیل تصاویر چک
                # پرسیده می‌شود، نه بعد از انتخاب صلاحیت دادگاه.
                await message.answer(
                    f"✅ هر *{total}* فقره چک (کدرهگیری + ۳ تصویر) با موفقیت ثبت شد.")
                if await _check_maybe_return_to_preview(message, state):
                    return
                await _ask_check_extra_docs(message, state)
        return

    text = (message.text or "").strip()

    if text == "🔙 بازگشت":
        # حذف آخرین تصویر فقرهٔ جاری
        data = await state.get_data()
        images = data.get("_current_cheque_images", [])
        if images:
            images.pop()
            await state.update_data(_current_cheque_images=images)
        current_idx = data.get("_current_cheque_index", 1)
        total = data.get("check_cheques_total", 1)
        await message.answer(
            f"📷 *فقره {current_idx} از {total}:* لطفاً تصویر چک را ارسال فرمایید:\n"
            f"_(۳ تصویر — {len(images)} تصویر تاکنون)_",
            reply_markup=check_more_images_kb)
        return

    await message.answer(
        "⚠️ لطفاً *تصویر چک* را ارسال فرمایید (۳ تصویر برای هر فقره):",
        reply_markup=check_more_images_kb)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۱۱ — پیوست‌ها (اختیاری — مانند اظهارنامه)
# ══════════════════════════════════════════════════════════════════════════════
@check_router.message(Form.check_attachment_title)
async def check_attachment_title_handler(message: Message, state: FSMContext):
    text = message.text.strip() if message.text else ""
    data = await state.get_data()
    is_aasar_title = data.get("check_request_title") in CHECK_AASAR_TITLES
    request_title = data.get("check_request_title", "")

    if text == "🔙 بازگشت":
        # ⭐ دور ۳ — سوال پیوست حالا برای همهٔ عناوین *قبل از* صلاحیت دادگاه
        # پرسیده می‌شود؛ بازگشت به آخرین مرحلهٔ اختصاصی همان نوع دادخواست:
        #   اعسار → ۴/۴ شماره شعبه | خانواده → تاریخ عقد |
        #   بابت... → توضیحات اضافی | چک → فقرات چک (از ابتدا)
        if is_aasar_title:
            await message.answer(
                "۴/۴ — لطفاً *شماره شعبه* را وارد فرمایید:\n"
                "_(فقط عدد)_",
                reply_markup=back_only_kb)
            await state.set_state(Form.check_judgment_branch_no)
            return
        if request_title in CHECK_FAMILY_TITLES:
            await message.answer(
                "📅 لطفاً *تاریخ وقوع عقد* را به‌صورت `1403/06/15` وارد فرمایید:",
                reply_markup=back_only_kb)
            await state.set_state(Form.check_marriage_date)
            return
        if request_title == "مطالبه وجه بابت...":
            await message.answer(
                "📝 *مرحله ۹:* آیا *توضیحات اضافی* دارید؟",
                reply_markup=check_extra_text_kb)
            await state.set_state(Form.check_extra_text)
            return
        # عناوین چک — بازگشت به مرحلهٔ فقرات چک (فقرات قبلی حذف و از ابتدا)
        await state.update_data(
            check_cheque_items=[],
            check_tracking_list=[],
            check_images=[],
            check_tracking_no="",
            _current_cheque_index=1,
            _current_cheque_tracking="",
            _current_cheque_images=[])
        await message.answer(
            "🔢 لطفاً *تعداد فقرات چک* را وارد یا انتخاب فرمایید:\n_(از ۱ تا ۳۰)_",
            reply_markup=create_check_cheque_count_kb())
        await state.set_state(Form.check_cheques_count)
        return

    # ⭐ دکمه‌های شروع/ادامهٔ پیوست — رد کردن یا اتمام
    if text in ("✅ ادامه بدون پیوست", "✅ اتمام و ادامه",
                "⏭ رد کردن (بدون مدرک)", "⏭ رد کردن"):
        if await _check_maybe_return_to_preview(message, state):
            return
        # ⭐ دور ۳ — برای همهٔ عناوین (نه فقط اعسار): بعد از پایان پیوست‌ها
        # نوبت «صلاحیت دادگاه» است — چون این سوال حالا قبل از صلاحیت پرسیده
        # می‌شود؛ پس از انتخاب صلاحیت، مستقیم پیش‌نمایش نمایش داده خواهد شد.
        await state.update_data(check_att_done=True, check_aasar_att_done=True)
        await _ask_check_branch(message, state)
        return

    # ⭐ دکمهٔ افزودن پیوست جدید → درخواست عنوان
    if text in ("➕ افزودن پیوست", "➕ افزودن پیوست جدید"):
        await message.answer(
            "📎 *عنوان پیوست* را وارد فرمایید:",
            reply_markup=back_only_kb)
        return

    # ⭐ عنوان پیش‌فرض «سایر مستندات»
    if text == "🔹 عنوان مهم نیست (سایر مستندات)":
        text = "سایر مستندات"

    if not text:
        await message.answer("⚠️ عنوان پیوست نمی‌تواند خالی باشد. لطفاً وارد فرمایید:")
        return

    await state.update_data(_check_current_attachment_title=text)
    await message.answer(
        f"📎 *پیوست:* {text}\n\n"
        "لطفاً تصاویر این پیوست را ارسال فرمایید:",
        reply_markup=check_images_continue_kb)
    await state.set_state(Form.check_attachment_image)


@check_router.message(Form.check_attachment_image)
async def check_attachment_image_handler(message: Message, state: FSMContext):
    if not message.photo:
        text = (message.text or "").strip()
        if text in ("✅ ادامه", "➕ افزودن تصویر دیگر", "🔙 بازگشت"):
            # ⭐ دکمه‌های کیبورد در حالت دریافت تصویر — هدایت به منطق هندلر «بیشتر»
            await check_attachment_more_handler(message, state)
            return
        await message.answer("⚠️ لطفاً *عکس* پیوست را ارسال فرمایید.")
        return

    data = await state.get_data()
    images = data.get("_check_current_attachment_images", [])
    images.append(message.photo[-1].file_id)
    await state.update_data(_check_current_attachment_images=images)

    # ⭐ اصلاحیه: state باید به check_attachment_more برود — قبلاً state
    # تغییر نمی‌کرد و دکمه‌های کیبورد در همان هندلرِ «فقط عکس» گیر می‌کردند.
    count = len(images)
    await message.answer(
        f"✅ تصویر {count} دریافت شد.\n\n"
        "تصویر بعدی یا *«ادامه»*:",
        reply_markup=check_attachment_more_kb)
    await state.set_state(Form.check_attachment_more)


@check_router.message(Form.check_attachment_more)
async def check_attachment_more_handler(message: Message, state: FSMContext):
    # ⭐ عکس در این state هم پذیرفته می‌شود — همان منطق هندلر تصویر اجرا می‌شود
    if message.photo:
        await check_attachment_image_handler(message, state)
        return

    text = message.text.strip() if message.text else ""

    if text == "➕ افزودن تصویر دیگر":
        await message.answer(
            "📷 تصویر بعدی پیوست را ارسال فرمایید:",
            reply_markup=check_images_continue_kb)
        await state.set_state(Form.check_attachment_image)
        return

    if text == "✅ ادامه":
        # ذخیره گروه پیوست
        data = await state.get_data()
        title = data.get("_check_current_attachment_title", "")
        images = data.get("_check_current_attachment_images", [])

        if title and images:
            groups = data.get("check_attachment_groups", [])
            groups.append({"title": title, "images": images})
            await state.update_data(
                check_attachment_groups=groups,
                _check_current_attachment_title="",
                _check_current_attachment_images=[])

        # ادامه: پیوست بعدی یا پایان
        await message.answer(
            "📎 آیا پیوست دیگری دارید؟",
            reply_markup=check_attachment_title_kb)
        await state.set_state(Form.check_more_attachments)
        return

    if text == "🔙 بازگشت":
        data = await state.get_data()
        images = data.get("_check_current_attachment_images", [])
        if images:
            images.pop()
            await state.update_data(_check_current_attachment_images=images)
        await message.answer(
            "📷 لطفاً تصاویر پیوست را ارسال فرمایید:",
            reply_markup=check_images_continue_kb)
        await state.set_state(Form.check_attachment_image)
        return

    await message.answer("⚠️ لطفاً از دکمه‌ها استفاده کنید:")


@check_router.message(Form.check_more_attachments)
async def check_more_attachments_handler(message: Message, state: FSMContext):
    text = message.text.strip() if message.text else ""

    if text == "➕ افزودن پیوست جدید":
        await message.answer(
            "📎 *عنوان پیوست جدید* را وارد فرمایید:",
            reply_markup=back_only_kb)
        await state.set_state(Form.check_attachment_title)
        return

    if text in ("✅ اتمام و ادامه", "✅ خیر، ادامه به انتخاب دادگاه"):
        if await _check_maybe_return_to_preview(message, state):
            return
        # ⭐ دور ۳ — برای همهٔ عناوین (نه فقط اعسار): سوال پیوست قبل از صلاحیت
        # دادگاه پرسیده می‌شود، پس پس از اتمام پیوست‌ها نوبت انتخاب صلاحیت است.
        await state.update_data(check_att_done=True, check_aasar_att_done=True)
        await _ask_check_branch(message, state)
        return

    if text == "🔙 بازگشت":
        # ⭐ اصلاحیه: بازگشت به همان مرحلهٔ قبل — درخواست عنوان پیوست جدید
        await message.answer(
            "📎 *عنوان پیوست جدید* را وارد فرمایید:",
            reply_markup=back_only_kb)
        await state.set_state(Form.check_attachment_title)
        return

    await message.answer("⚠️ لطفاً از دکمه‌ها استفاده کنید:")


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۱۲ — انتخاب صلاحیت دادگاه (درختی)
# ══════════════════════════════════════════════════════════════════════════════
async def _ask_check_branch(message: Message, state: FSMContext):
    # ⭐ اصلاحیه: load_check_units تابعی «همگام» (sync) است و bool برمی‌گرداند —
    # قبلاً با await صدا زده می‌شد و TypeError:
    # "object bool can't be used in 'await' expression" می‌داد و کل مسیر
    # «خیر، ادامه بده» (و هر مسیری که به انتخاب دادگاه می‌رسید) کرش می‌کرد.
    if not load_check_units():
        await message.answer(
            "⚠️ لیست شعب دادگاه در دسترس نیست. لطفاً چند لحظه بعد دوباره تلاش کنید "
            "یا با پشتیبانی تماس بگیرید.")
        return
    kb = create_check_branch_keyboard(CHECK_ROOT_NODES)
    await message.answer(
        "⚖️ *مرحله ۱۲:* لطفاً *صلاحیت دادگاه* را انتخاب فرمایید:",
        reply_markup=kb)
    await state.set_state(Form.check_branch)


# ── پیش‌نمایش ─────────────────────────────────────────────────────────────────
async def _go_to_check_preview(message: Message, state: FSMContext):
    data = await state.get_data()
    request_title = data.get("check_request_title", "")
    amount = data.get("check_amount", 0)
    khasteh_text = data.get("check_khasteh_text", "")
    text = data.get("check_text", "")
    extra = data.get("check_extra_text", "")
    images = data.get("check_images", [])
    plaintiffs = data.get("check_plainiffs", [])
    defendants = data.get("check_defendants", [])
    witnesses = data.get("check_witnesses", [])
    attachments = data.get("check_attachment_groups", [])
    branch_name = data.get("check_branch_name", "")
    branch_code = data.get("check_branch_code", "")
    docx_name = data.get("check_docx_file_name", "")
    docx_id = data.get("check_docx_file_id")
    marriage_cert = data.get("check_marriage_cert_images", [])
    esteshahadieh = data.get("check_esteshahadieh_images", [])
    aasar = data.get("check_aasar", False)
    tamin = data.get("check_tamin_khasteh", False)
    # ⭐ عناوین اعسار — اطلاعات اختصاصی
    court_type = data.get("check_court_type", "")
    assets_list = data.get("check_assets_list_images", [])
    judgment_images = data.get("check_judgment_images", [])
    judgment_no = data.get("check_judgment_no", "")
    judgment_date = data.get("check_judgment_date", "")
    judgment_court = data.get("check_judgment_court_name", "")
    judgment_branch = data.get("check_judgment_branch_no", "")
    is_aasar_title = request_title in CHECK_AASAR_TITLES

    # ⭐ محاسبه خودکار مالیات دادرسی
    stamp = None
    if amount:
        try:
            stamp = calculate_stamp_duty(amount)
        except ValueError as e:
            logger.error(f"[CHECK] خطا در محاسبه مالیات دادرسی (پیش‌نمایش): {e}")

    # شمارش تصاویر هر گروه پیوست
    att_counts = []
    for g in attachments:
        imgs = g.get("images", [])
        att_counts.append(len(imgs))

    lines = []
    lines.append("📋 *پیش‌نمایش دادخواست چک*\n")
    lines.append(f"🎯 عنوان خواسته: {_escape_md(request_title)}")
    if is_aasar_title and court_type:
        lines.append(f"🏛 نوع دادگاه: دادگاه {_escape_md(court_type)}")
    if amount:
        lines.append(f"💰 مبلغ کل: {_fmt(amount)} ریال")
    if stamp:
        lines.append(f"🧾 مالیات دادرسی (تمبر کلی): {_fmt(stamp.get('tamber_kolli', 0))} ریال")
    lines.append(f"📄 عنوان خواسته (متن): {_escape_md(khasteh_text)}")
    lines.append(f"📄 متن دادخواست: {_escape_md(text[:500] + ('...' if len(text) > 500 else ''))}")
    if docx_name:
        lines.append(f"📎 فایل ورد: {_escape_md(docx_name)}")
    if extra:
        lines.append(f"📝 توضیحات: {_escape_md(extra)}")

    lines.append(f"\n👤 خواهان ({len(plaintiffs)} نفر):")
    for i, p in enumerate(plaintiffs, 1):
        pt = p.get("person_type", "")
        nid = p.get("company_id", "") if pt == "شخص حقوقی" else p.get("national_id", "")
        nm = p.get("name", "")
        lines.append(f"  {i}. {pt} — `{nid}` — {_escape_md(nm)}")
        for rep in p.get("representatives", []):
            lines.append(f"     نماینده: {rep.get('representative_type', '')} — "
                         f"`{rep.get('national_id', '')}`")

    if defendants:
        lines.append(f"\n👥 خوانده ({len(defendants)} نفر):")
        for i, d in enumerate(defendants, 1):
            pt = d.get("person_type", "")
            nid = d.get("company_id", "") if pt == "شخص حقوقی" else d.get("national_id", "")
            nm = d.get("name", "")
            lines.append(f"  {i}. {pt} — `{nid}` — {_escape_md(nm)}")
            for rep in d.get("representatives", []):
                lines.append(f"     نماینده: {rep.get('representative_type', '')} — "
                             f"`{rep.get('national_id', '')}`")

    if witnesses:
        lines.append(f"\n🔍 مطلع/گواه ({len(witnesses)} نفر):")
        for i, w in enumerate(witnesses, 1):
            w_name = (w.get("name") or "").strip()
            if w_name:
                lines.append(f"  {i}. `{(w.get('national_id') or '')}` — {_escape_md(w_name)}")
            else:
                lines.append(f"  {i}. `{(w.get('national_id') or '')}`")

    if aasar:
        lines.append(f"\n📷 استشهادیه: {len(esteshahadieh)} تصویر")
    if marriage_cert:
        lines.append(f"💍 گواهی ازدواج: {len(marriage_cert)} تصویر")
    # ⭐ فلوی جدید چک — نمایش فقرات (کدرهگیری + تعداد تصویر هر فقره)
    cheque_items = data.get("check_cheque_items", [])
    if cheque_items:
        lines.append(f"\n🧾 فقرات چک ({len(cheque_items)} فقره):")
        for i, q in enumerate(cheque_items, 1):
            lines.append(
                f"  {i}. کدرهگیری `{q.get('tracking_no', '')}` — "
                f"{len(q.get('images', []))} تصویر")
    elif images:
        lines.append(f"📷 تصاویر چک: {len(images)} تصویر")
    # ⭐ عناوین اعسار — مستندات الزامی
    if is_aasar_title:
        if esteshahadieh:
            lines.append(f"\n📷 استشهادیه: {len(esteshahadieh)} تصویر")
        if assets_list:
            lines.append(f"📋 لیست اموال: {len(assets_list)} تصویر")
        if judgment_images:
            lines.append(f"📄 دادنامه/اجرائیه: {len(judgment_images)} تصویر")
            lines.append(
                f"   شماره دادنامه: `{judgment_no}` | تاریخ: `{judgment_date}`\n"
                f"   دادگاه: {_escape_md(judgment_court)} | شماره شعبه: `{judgment_branch}`")
    if attachments:
        lines.append(f"\n📎 پیوست‌ها ({len(attachments)} مورد):")
        for i, g in enumerate(attachments, 1):
            lines.append(f"  {i}. {_escape_md(g.get('title', ''))} — {len(g.get('images', []))} تصویر")

    if tamin:
        lines.append("\n⚖️ تامین خواسته: ✅")
    if aasar:
        lines.append("⚖️ اعسار از هزینه دادرسی: ✅")

    lines.append(f"\n🏛 صلاحیت: {_escape_md(branch_name)}")
    if branch_code:
        lines.append(f"کد واحد: `{branch_code}`")

    await message.answer(
        "\n".join(lines),
        reply_markup=check_confirm_kb)
    await state.update_data(check_preview_sent=True)
    await state.set_state(Form.check_confirm)


# ── تایید و ارسال ─────────────────────────────────────────────────────────────
async def _submit_check_request(message: Message, state: FSMContext, bot: Bot):
    """ساخت تسک ثبت دادخواست و ارسال به صف پردازش + اطلاع به مدیر.

    (از check_confirm_handler جدا شد تا پس از «تایید و ثبت نهایی» بلافاصله و
    نیز پس از تایید خودکار پیش‌پرداخت — سکشن جدید کارفرما ۱۴۰۵/۰۶ — قابل
    فراخوانی باشد.)
    """
    data = await state.get_data()
    user_id = message.from_user.id
    request_title = data.get("check_request_title", "")
    plaintiffs = data.get("check_plainiffs", [])
    defendants = data.get("check_defendants", [])

    # ⭐ جمع‌بندی متن کامل — اصلاحیه: متن خواسته (khasteh) دیگر دوباره به
    # شرح متن اضافه نمی‌شود؛ سناریوی سامانه این دو را در فیلدهای جداگانه
    # (txtDescription برای خواسته / ادیتور شرح برای متن) ثبت می‌کند و
    # ترکیب قبلی باعث تکرار دوبار متن خواسته در سامانه می‌شد.
    full_text = (data.get("check_text") or "").strip()
    await state.update_data(check_text=full_text)

    # دانلود تصاویر چک — ⚠️ check_scenario.py خودش از روی file_id دانلود
    # می‌کند (_download_check_images)؛ اینجا فقط برای پیش‌نمایش/سازگاری
    # قدیمی نگه داشته شده و تغییری در معماری اصلی نمی‌دهد.
    check_image_paths = []
    check_images = data.get("check_images", [])
    if check_images:
        await message.answer("⏳ در حال آماده‌سازی تصاویر چک...")
        try:
            check_image_paths = await download_images_from_bale(bot, check_images, user_id, "check")
        except Exception as dl_err:
            logger.error(f"[CHECK] دانلود پیش‌نمایشی تصاویر چک ناموفق (ادامه بدون آن): {dl_err}")

    # ⚠️ مدارک نمایندگی (نماینده/مدیرعامل خواهان یا خوانده) دیگر اینجا
    # پردازش نمی‌شود — این تصاویر مستقیماً هنگام ثبتِ آن شخص، داخل
    # check_attachment_groups با عنوان «مدرک نمایندگی» قرار می‌گیرند
    # (نگاه کنید به check_plaintiff_legal_rep_doc_images_more_handler /
    # check_defendant_legal_rep_doc_images_more_handler) و check_scenario.py
    # آن‌ها را مثل هر پیوست دیگر خودش دانلود می‌کند.

    # ⭐ پیوست‌ها — check_scenario.py (مرحلهٔ «منضمات») خودش تصاویر هر گروه
    # را از روی file_id دانلود می‌کند (group.get("images") → _download_check_images)؛
    # بنابراین اینجا هیچ دانلودی انجام نمی‌شود و لیست با همان کلید «images»
    # (نه «paths») و با همان فلگ‌های is_esteshahadieh / is_marriage_cert پاس
    # می‌شود — دقیقاً همان ساختاری که «سند ازدواج» (_register_marriage_certificate)
    # و «استشهادیهٔ محلی» (_upload_esteshahadieh_attachment) در سمت سناریو
    # انتظار دارند.
    attachment_groups = list(data.get("check_attachment_groups", []))

    estesh_ids = data.get("check_esteshahadieh_images", [])
    if estesh_ids:
        attachment_groups.append({
            "title": "استشهاديه محلي",
            "images": estesh_ids,
            "is_esteshahadieh": True,
        })

    cert_ids = data.get("check_marriage_cert_images", [])
    if cert_ids:
        attachment_groups.append({
            "title": "سند ازدواج",
            "images": cert_ids,
            "is_marriage_cert": True,
            "cert_no": data.get("check_marriage_cert_no", ""),
            "cert_date": data.get("check_marriage_date", ""),
        })

    # ⭐ عناوین اعسار — لیست اموال (ساير ضمائم) و دادنامه (تصويردادنامه غيرمكانيزه)
    assets_ids = data.get("check_assets_list_images", [])
    if assets_ids:
        attachment_groups.append({
            "title": "لیست اموال",
            "images": assets_ids,
            "is_assets_list": True,
        })

    judgment_ids = data.get("check_judgment_images", [])
    if judgment_ids:
        attachment_groups.append({
            "title": "تصويردادنامه غيرمكانيزه",
            "images": judgment_ids,
            "is_dadnameh": True,
            "dadnameh_no": data.get("check_judgment_no", ""),
            "dadnameh_date": data.get("check_judgment_date", ""),
            "dadnameh_court": data.get("check_judgment_court_name", ""),
            "dadnameh_branch": data.get("check_judgment_branch_no", ""),
        })

    # دانلود فایل ورد
    docx_path = None
    docx_id = data.get("check_docx_file_id")
    if docx_id:
        try:
            file = await bot.get_file(docx_id)
            import tempfile
            suffix = ".docx"
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            await bot.download_file(file.file_path, tmp.name)
            docx_path = tmp.name
        except Exception as e:
            logger.error(f"[CHECK] دانلود فایل ورد ناموفق: {e}")

    amount = data.get("check_amount", 0)
    stamp = None
    if amount:
        try:
            stamp = calculate_stamp_duty(amount)
        except ValueError as e:
            logger.error(f"[CHECK] خطا در محاسبه مالیات دادرسی (ثبت نهایی): {e}")

    # ⭐ فقرات چک — ساخت check_cheque_items از دادهٔ فلو (file_id خام؛
    # check_scenario.py خودش هر فقره را با _download_check_images دانلود
    # می‌کند و کدرهگیری هر فقره را در منضمات درج/استعلام می‌نماید).
    # قبلاً این ساختار هرگز ساخته نمی‌شد و کدرهگیری‌های فقرات دوم به بعد
    # بی‌استفاده می‌ماندند (سناریو فقط یک فقرهٔ بدون کدرهگیری می‌ساخت).
    cheque_items = [
        {
            "tracking_no": (q.get("tracking_no") or "").strip(),
            "images": list(q.get("images") or []),
        }
        for q in data.get("check_cheque_items", [])
    ]

    item = {
        "user_id": user_id,
        "query_type": "دادخواست_چک",
        "task_type": "CHECK_SUBMIT",
        "check_request_title": request_title,
        "check_court_type": data.get("check_court_type", ""),  # ⭐ عناوین اعسار
        "check_amount": amount,
        "check_stamp_duty": stamp,
        "check_khasteh_text": data.get("check_khasteh_text", ""),
        "check_tamin_khasteh": data.get("check_tamin_khasteh", False),
        "check_aasar": data.get("check_aasar", False),
        "check_text": full_text,
        "check_text_html": data.get("check_text_html", ""),
        "check_extra_text": data.get("check_extra_text", ""),
        "check_tracking_no": data.get("check_tracking_no", ""),
        "check_tracking_list": data.get("check_tracking_list", []),
        "check_cheque_items": cheque_items,  # ⭐ فلو جدید فقرات چک
        "check_plainiffs": plaintiffs,
        "check_defendants": defendants,
        "check_witnesses": data.get("check_witnesses", []),
        "check_images": check_image_paths,
        "check_attachment_groups": attachment_groups,
        "check_branch_code": data.get("check_branch_code", ""),
        "check_branch_name": data.get("check_branch_name", ""),
        "check_branch_path": data.get("check_branch_path", ""),
        "check_docx_path": docx_path,
        "check_docx_file_id": data.get("check_docx_file_id"),
        "check_docx_file_name": data.get("check_docx_file_name", ""),
    }

    # ارسال اطلاعات به ادمین
    try:
        await send_check_submission_to_admin(item)
    except Exception as e:
        logger.error(f"Error sending check submission to admin: {e}")

    await runtime_state.job_queue.put(item)
    logger.info(f"[CHECK] Added CHECK_SUBMIT job for user {user_id}")

    await state.clear()
    await message.answer(
        "✅ درخواست شما با موفقیت ثبت شد.\n\n"
        "⏳ پس از تکمیل فرایند، نتیجه برایتان ارسال خواهد شد.",
        reply_markup=main_menu_kb)

    try:
        from sheets import log_event
        log_event(
            user_id=user_id,
            event_type="CHECK_SUBMIT",
            details=f"title={request_title}, amount={amount}, images={len(check_image_paths)}"
        )
    except Exception:
        pass


@check_router.message(Form.check_confirm, F.text.in_({"✅ تایید و ثبت نهایی", "✅ تایید و شروع ثبت"}))
async def check_confirm_handler(message: Message, state: FSMContext):
    """⭐ اصلاحیه: متن دکمهٔ check_confirm_kb «✅ تایید و شروع ثبت» بود ولی
    هندلر فقط «✅ تایید و ثبت نهایی» را می‌شناخت — دکمهٔ تایید عملاً هیچ
    واکنشی نداشت. اکنون هر دو متن پشتیبانی می‌شوند."""
    data = await state.get_data()

    # بررسی: حداقل یک خواهان و یک خوانده
    plaintiffs = data.get("check_plainiffs", [])
    defendants = data.get("check_defendants", [])
    if not plaintiffs:
        await message.answer("⚠️ حداقل یک خواهان باید ثبت شود.")
        return
    request_title = data.get("check_request_title", "")
    # ⭐ طلاق توافقی: خوانده ندارد
    if not defendants and request_title != CHECK_TALAGH_TOAFIGHI_TITLE:
        await message.answer("⚠️ حداقل یک خوانده باید ثبت شود.")
        return

    user_id = message.from_user.id
    bot: Bot = message.bot

    # ⭐ معافین از پرداخت → مستقیم ثبت (بدون پیش‌پرداخت)
    from exempt_users import is_exempt_user
    if await is_exempt_user(user_id):
        await _submit_check_request(message, state, bot)
        return

    # ⭐ سکشن جدید کارفرما (۱۴۰۵/۰۶): پیش‌پرداخت قبل از شروع ثبت —
    # فاکتور و درگاه پرداخت ارسال می‌شود؛ پس از تایید خودکار پرداخت،
    # ثبت آغاز خواهد شد (check_prepay_successful_payment).
    # ثبت دادخواست: ۲,۰۰۰ تومان (اصلاحیهٔ ۱۴۰۵/۰۶/۲۵ — حداقلِ مبلغ فاکتور API).
    from prepay_registration import send_prepay_invoice
    sent = await send_prepay_invoice(bot, user_id, "check",
                                     f"ثبت دادخواست ({request_title})")
    if sent:
        # داده‌های FSM دست‌نخورده می‌مانند تا پس از پرداخت ارسال شوند
        await state.set_state(Form.waiting_for_check_prepay)
    return


# ══════════════════════════════════════════════════════════════════════════════
# ⭐ سکشن جدید کارفرما (۱۴۰۵/۰۶): پرداخت پیش‌پرداخت ثبت دادخواست —
# پس از تایید خودکار پرداخت بله، ثبت در سامانه آغاز می‌شود.
# (علاوه بر decorated زیرین، از global_successful_payment_handler در
#  handlers.py نیز مستقیم فراخوانی می‌شود.)
# ══════════════════════════════════════════════════════════════════════════════
@check_router.message(Form.waiting_for_check_prepay, F.successful_payment)
async def check_prepay_successful_payment(message: Message, state: FSMContext, bot: Bot):
    """پرداخت موفق پیش‌پرداخت ثبت دادخواست — تشخیص خودکار توسط بله"""
    user_id = message.from_user.id
    payment = message.successful_payment
    data = await state.get_data()
    request_title = data.get("check_request_title", "")

    # مبلغ واقعی پرداخت‌شده (total_amount ریال است) — تعرفه: ۲,۰۰۰ تومان
    from prepay_registration import register_prepaid, get_prepay_amount_toman
    fee = int((getattr(payment, "total_amount", 0) or 0) // 10) \
        or get_prepay_amount_toman("check")

    logging.info(f"[CHECK-PREPAY] پرداخت خودکار تشخیص داده شد برای کاربر {user_id}")

    # ⚠️ داده‌های FSM از بین رفته — بدون ثبت؛ اطلاع به مدیر
    if not data.get("check_request_title"):
        logging.error(f"[CHECK-PREPAY] داده FSM یافت نشد — user={user_id}")
        await message.answer(
            "⚠️ اطلاعات درخواست شما یافت نشد؛ لطفاً دوباره ثبت را شروع کنید.\n"
            "پرداخت شما به مدیریت اطلاع داده شد و در هزینه ثبت بعدی لحاظ می‌گردد.")
        try:
            from config import ADMIN_ID
            await bot.send_message(
                ADMIN_ID,
                f"⚠️ [CHECK-PREPAY] پرداخت بدون داده FSM — user={user_id}\n"
                f"🎫 payment_id: {payment.telegram_payment_charge_id}\n"
                f"💰 مبلغ: {fee:,} تومان")
        except Exception:
            pass
        await state.clear()
        return

    # ⭐ ثبت پیش‌پرداخت برای کسر از هزینه کل در پایان کار
    register_prepaid(user_id, fee, "check",
                     f"ثبت دادخواست ({request_title})",
                     payment.telegram_payment_charge_id)

    await message.answer(
        "✅ *پرداخت پیش‌پرداخت تایید شد!*",
        parse_mode="Markdown")
    await message.answer(
        f"💰 مبلغ: *{fee:,} تومان*\n\n"
        f"📝 نوع: *ثبت دادخواست ({request_title})*\n\n"
        f"⏳ درخواست شما در حال ارسال به سامانه قضایی است...",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )

    # اطلاع‌رسانی به ادمین
    try:
        from config import ADMIN_ID
        await bot.send_message(
            ADMIN_ID,
            f"💰 پرداخت پیش‌پرداخت ثبت دادخواست (تشخیص خودکار):\n\n"
            f"👤 کاربر: {message.from_user.full_name} ({user_id})\n"
            f"📝 عنوان: {request_title}\n"
            f"💰 مبلغ: {fee:,} تومان\n"
            f"⏱ زمان: {__import__('datetime').datetime.now().strftime('%Y/%m/%d %H:%M')}\n"
            f"🎫 payment_id: {payment.telegram_payment_charge_id}")
    except Exception as e:
        logger.error(f"[CHECK-PREPAY] خطا در ارسال اطلاع به ادمین: {e}")

    # ⭐ شروع ثبت — ارسال تسک به صف پردازش
    await _submit_check_request(message, state, bot)


@check_router.message(Form.waiting_for_check_prepay)
async def check_prepay_waiting_message(message: Message):
    """در حال انتظار پرداخت پیش‌پرداخت — پرداخت از طریق فاکتور بله"""
    await message.answer(
        "⏳ لطفاً فاکتور پیش‌پرداخت ارسال‌شده را در چت پرداخت کنید تا ثبت "
        "درخواست شما آغاز گردد.")


# ── انصراف ────────────────────────────────────────────────────────────────────
@check_router.message(Form.check_confirm, F.text == "❌ انصراف")
async def check_cancel_handler(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "❌ فرایند ثبت دادخواست چک لغو شد.",
        reply_markup=main_menu_kb)


# ⭐ اصلاحیه: دکمهٔ «✏️ ویرایش اطلاعات» در کیبورد پیش‌نمایش وجود داشت ولی
# هیچ هندلری برای آن ثبت نشده بود (Form.check_edit_choice هرگز set نمی‌شد)
# و منوی ویرایش عملاً غیرقابل‌دسترس بود.
@check_router.message(Form.check_confirm, F.text == "✏️ ویرایش اطلاعات")
async def check_confirm_edit_handler(message: Message, state: FSMContext):
    await message.answer(
        "✏️ کدام بخش را ویرایش می‌کنید؟",
        reply_markup=check_edit_kb)
    await state.set_state(Form.check_edit_choice)


# ── بازگشت از انتخاب صلاحیت ───────────────────────────────────────────────────
@check_router.message(Form.check_branch)
async def check_branch_back_handler(message: Message, state: FSMContext):
    text = message.text.strip() if message.text else ""
    if text == "🔙 بازگشت":
        # ⭐ دور ۳ — برای همهٔ عناوین، مرحلهٔ قبل از صلاحیت دادگاه سوال
        # «مدرک دیگری دارید؟» است (بعد از اسناد اختصاصی همان نوع) — بازگشت
        # به همان سوال؛ کاربر می‌تواند پیوست دیگری اضافه کند یا با «رد کردن»
        # مجدد به انتخاب صلاحیت برگردد (فقرات چک هم دیگر در این مسیر حذف
        # نمی‌شوند چون مرحلهٔ تصاویر دو مرحله عقب‌تر است).
        await _ask_check_extra_docs(message, state)
        return
    await message.answer("⚠️ لطفاً از کیبورد زیر، صلاحیت دادگاه را انتخاب کنید:")


# ── انتخاب گره درخت صلاحیت ────────────────────────────────────────────────────
def _cbr_int(value) -> "int | None":
    """تبدیل امن متن به عدد — برای اجزای callback_data درخت صلاحیت."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def _cbr_show_level(callback: CallbackQuery, nodes: list, page: int = 0,
                          parent_path: str | None = None):
    """نمایش یک سطح از درخت صلاحیت با ویرایش کیبورد پیام موجود."""
    if not nodes:
        await callback.answer("⚠️ زیرشاخه‌ای برای این گزینه یافت نشد", show_alert=True)
        return False
    kb = create_check_branch_keyboard(nodes, page=page, parent_path=parent_path)
    try:
        await callback.message.edit_reply_markup(reply_markup=kb)
    except Exception:
        # پیام تغییر نکرد (مثلاً همان کیبورد) یا پیام قدیمی است — نادیده بگیر
        pass
    return True


@check_router.callback_query(F.data.startswith("cbr:"))
async def check_branch_callback(callback: CallbackQuery, state: FSMContext):
    """
    ناوبری درخت صلاحیت دادگاه (پیشوند cbr:).

    ⭐ اصلاحیه: کیبورد create_check_branch_keyboard مقادیر زیر را تولید
    می‌کند و قبلاً هندلر فقط `cbr:<idx>` را می‌فهمید — به همین دلیل «هر»
    دکمه با خطای «⚠️ انتخاب نامعتبر» رد می‌شد و کاربر در مرحلهٔ صلاحیت
    دادگاه گیر می‌کرد. اکنون تمام فرمت‌ها پشتیبانی می‌شوند:
      cbr:open:{idx}:{page}     → باز کردن پوشهٔ idx، صفحهٔ page
      cbr:sel:{idx}             → انتخاب گرهٔ نهایی (ذخیرهٔ صلاحیت)
      cbr:page:{parent}:{page}  → صفحه‌بندی (parent = root یا idx پوشه)
      cbr:back:{idx}:{page}     → بازگشت به فرزندانِ idx، صفحهٔ page
      cbr:root:{page}           → بازگشت به ریشه (لیست استان‌ها)
    """
    parts = (callback.data or "").split(":")
    if len(parts) < 3:
        await callback.answer("⚠️ انتخاب نامعتبر", show_alert=True)
        return

    action = parts[1]

    # ── بازگشت به ریشه (لیست استان‌ها) ─────────────────────────────────
    if action == "root":
        page = _cbr_int(parts[2]) or 0
        if await _cbr_show_level(callback, CHECK_ROOT_NODES, page=page):
            await callback.answer()
        return

    # ── باز کردن پوشه ──────────────────────────────────────────────────
    if action == "open":
        idx = _cbr_int(parts[2])
        page = _cbr_int(parts[3]) if len(parts) > 3 else 0
        path = CHECK_INDEX_TO_PATH.get(idx) if idx is not None else None
        if not path:
            await callback.answer("⚠️ گزینه نامعتبر است", show_alert=True)
            return
        # ⚠️ INDEX_TO_PATH مقدار «مسیرِ نرمال‌شده» (str) می‌دهد؛ get_children
        # همین مسیر را می‌پذیرد (برخلاف has_children که dict می‌خواهد).
        children = check_get_children(path)
        if not children:
            await callback.answer("⚠️ زیرشاخه‌ای وجود ندارد", show_alert=True)
            return
        if await _cbr_show_level(callback, children, page=page or 0, parent_path=path):
            await callback.answer()
        return

    # ── صفحه‌بندی (parent می‌تواند «root» یا idx عددی پوشه باشد) ────────
    if action == "page":
        parent = parts[2]
        page = _cbr_int(parts[3]) if len(parts) > 3 else 0
        if parent == "root":
            if await _cbr_show_level(callback, CHECK_ROOT_NODES, page=page or 0):
                await callback.answer()
            return
        idx = _cbr_int(parent)
        path = CHECK_INDEX_TO_PATH.get(idx) if idx is not None else None
        if not path:
            await callback.answer("⚠️ گزینه نامعتبر است", show_alert=True)
            return
        children = check_get_children(path)
        if await _cbr_show_level(callback, children, page=page or 0, parent_path=path):
            await callback.answer()
        return

    # ── بازگشت به سطح بالاتر (فرزندانِ پدربزرگ) ─────────────────────────
    if action == "back":
        idx = _cbr_int(parts[2])
        page = _cbr_int(parts[3]) if len(parts) > 3 else 0
        path = CHECK_INDEX_TO_PATH.get(idx) if idx is not None else None
        if not path:
            # مسیر نامعتبر → بازگشت امن به ریشه
            if await _cbr_show_level(callback, CHECK_ROOT_NODES, page=0):
                await callback.answer()
            return
        nodes = check_get_children(path)
        if not nodes:
            if await _cbr_show_level(callback, CHECK_ROOT_NODES, page=0):
                await callback.answer()
            return
        if await _cbr_show_level(callback, nodes, page=page or 0, parent_path=path):
            await callback.answer()
        return

    # ── انتخاب گره (نهایی یا پوشه‌ای) ──────────────────────────────────
    if action == "sel":
        idx = _cbr_int(parts[2])
        path = CHECK_INDEX_TO_PATH.get(idx) if idx is not None else None
        if not path:
            await callback.answer("⚠️ گزینه نامعتبر است", show_alert=True)
            return

        # اگر گره پوشه است → باز کن (⚠️ path رشتهٔ نرمال‌شده است؛ get_children
        # مستقیماً همین را می‌پذیرد)
        children = check_get_children(path)
        if children:
            if await _cbr_show_level(callback, children, page=0, parent_path=path):
                await callback.answer()
            return

        # گره نهایی — ذخیره صلاحیت
        row = CHECK_PATH_TO_ROW.get(path) or {}
        name = row.get("name", "")
        code = row.get("code", "")
        await state.update_data(
            check_branch_name=name,
            check_branch_code=code,
            check_branch_path=path)

        await callback.answer(f"✅ {name}")

        # ⭐ دور ۳ — برای همهٔ عناوین: سوال «مدرک دیگری دارید؟» حالا *قبل از*
        # انتخاب صلاحیت پرسیده می‌شود (بعد از اسناد اختصاصی همان نوع) — اگر
        # به هر دلیلی (مثلاً ورود مستقیم به ویرایش صلاحیت) هنوز پرسیده نشده
        # بود همین‌جا پرسیده می‌شود؛ وگرنه مستقیم پیش‌نمایش.
        data = await state.get_data()
        att_done = bool(data.get("check_att_done") or data.get("check_aasar_att_done"))
        if not att_done:
            await _ask_check_extra_docs(callback.message, state)
            return
        if await _check_maybe_return_to_preview(callback.message, state):
            return
        await _go_to_check_preview(callback.message, state)
        return

    await callback.answer("⚠️ انتخاب نامعتبر", show_alert=True)


# ── منوی ویرایش ───────────────────────────────────────────────────────────────
@check_router.message(Form.check_edit_choice)
async def check_edit_choice_handler(message: Message, state: FSMContext):
    text = message.text.strip() if message.text else ""
    data = await state.get_data()
    request_title = data.get("check_request_title", "")

    if text in ("🔙 بازگشت به پیش‌نمایش", "🔙 بازگشت"):
        await _go_to_check_preview(message, state)
        return

    await state.update_data(check_edit_mode=True)

    # ⭐ اصلاحیه: متن‌های دکمه عیناً با check_edit_kb هماهنگ شدند — قبلاً
    # بیشتر دکمه‌ها با هندلر مطابقت نداشتند و «ویرایش» عملاً کار نمی‌کرد.
    if text in ("🎯 ویرایش عنوان خواسته", "📝 ویرایش عنوان خواسته"):
        await message.answer(
            "🏦 *مرحله ۱:* لطفاً *عنوان خواسته جدید* را انتخاب فرمایید:",
            reply_markup=check_request_title_kb)
        await state.set_state(Form.check_request_title)
        return

    if text in ("💰 ویرایش مبلغ", "💰 ویرایش مبلغ چک"):
        await message.answer(
            "💰 لطفاً *مبلغ جدید* را به *ریال* وارد فرمایید:",
            reply_markup=back_only_kb)
        await state.set_state(Form.check_amount)
        return

    if text == "📄 ویرایش عنوان خواسته (متن)":
        # ⭐ نمونه‌متن فقط برای اجرائیه/مطالبه وجه چک
        if request_title in CHECK_SAMPLE_TEXT_TITLES:
            if request_title == "صدور اجرائیه چک":
                suggested = ("به موجب یک فقره چک به شماره ... مورخ ... به عهده بانک ملی "
                             "به مبلغ ... ریال با کدرهگیری ... به انضمام کلیه خسارات دادرسی و حق الوکاله وکیل "
                             "و خسارات تاخيرتاديه از زمان سررسيد لغايت زمان كامل اجراي حكم و حق الوكاله وكيل")
            else:
                suggested = ("به موجب ........ فقره چک به شماره ......... مورخ ......... به عهده بانک ....... "
                             "به انضمام کلیه هزینه های دادرسی و خسارات تاخیرتادیه از زمان سررسید "
                             "لغایت زمان کامل اجرای حکم و حق الوکاله وکیل")
            await message.answer(
                f"📝 *متن پیشنهادی:*\n\n{suggested}\n\n"
                "متن جدید را ارسال فرمایید:",
                reply_markup=back_only_kb)
        else:
            await message.answer(
                "📝 لطفاً *متن خواسته* جدید را ارسال فرمایید:",
                reply_markup=back_only_kb)
        await state.set_state(Form.check_khasteh_title)
        return

    if text in ("📝 ویرایش متن دادخواست", "📋 ویرایش شرح متن"):
        await _ask_check_text(message, state)
        return

    if text in ("👤 ویرایش خواهان", "👤 ویرایش خواهان(ها)"):
        await message.answer(
            "👤 لطفاً *نوع شخصیت خواهان* را انتخاب فرمایید:",
            reply_markup=create_check_person_type_kb())
        await state.set_state(Form.check_plaintiff_person_type)
        return

    if text in ("👥 ویرایش خوانده", "👥 ویرایش خوانده(ها)"):
        await message.answer(
            "👥 لطفاً *نوع شخصیت خوانده* را انتخاب فرمایید:",
            reply_markup=create_check_person_type_kb())
        await state.set_state(Form.check_defendant_person_type)
        return

    if text == "🔍 ویرایش مطلع/گواه":
        await message.answer(
            "🔍 آیا *مطلع یا گواه* دارید؟",
            reply_markup=check_addressee_add_more_kb)
        await state.set_state(Form.check_witness_national_id)
        return

    if text in ("📷 ویرایش تصاویر چک",
                "🧾 ویرایش فقرات چک (کدرهگیری و تصاویر)"):
        # ⭐ فلوی جدید: ویرایش فقرات از ابتدا — ابتدا تعداد، سپس به‌ازای هر
        # فقره کدرهگیری + ۳ تصویر (فقرات قبلی حذف می‌شوند)
        await state.update_data(
            check_cheque_items=[],
            check_tracking_list=[],
            check_images=[],
            check_tracking_no="",
            check_cheques_total=0,
            _current_cheque_index=1,
            _current_cheque_tracking="",
            _current_cheque_images=[])
        await message.answer(
            "🔢 لطفاً *تعداد فقرات چک* را وارد یا انتخاب فرمایید:\n_(از ۱ تا ۳۰)_",
            reply_markup=create_check_cheque_count_kb())
        await state.set_state(Form.check_cheques_count)
        return

    if text == "📎 ویرایش پیوست‌ها":
        await message.answer(
            "📎 *عنوان پیوست* را وارد فرمایید:",
            reply_markup=back_only_kb)
        await state.set_state(Form.check_attachment_title)
        return

    if text == "⚖️ ویرایش صلاحیت دادگاه":
        await _ask_check_branch(message, state)
        return

    await message.answer("⚠️ لطفاً از دکمه‌ها استفاده کنید:")


# ══════════════════════════════════════════════════════════════════════════════
# ⭐ پنجرهٔ ۳۰ دقیقه‌ای ویرایش کدملی دادخواست چک — پس از خطای ثنا
# («تاریخ تولد ارسالی مربوط به شماره ملی ... اشتباه است» / شناسه ملی ثبت نشده).
# پنجره و جریمهٔ نصف پیش‌پرداخت در nid_fix_window مدیریت و در persistence
# ذخیره می‌شود (حتی پس از کرش/قطعی ربات برای درخواست‌های بعدی کاربر محاسبه می‌گردد).
# ══════════════════════════════════════════════════════════════════════════════

import nid_fix_window as _chk_nfw
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import ADMIN_ID as _CHK_ADMIN_ID

# لیست‌های اشخاص دادخواست — برای یافتن و ویرایش کدملی
_CHECK_PERSON_LIST_KEYS = ("check_plainiffs", "check_defendants", "check_witnesses")


def _find_check_person_idx(task_data: dict, old_nid: str):
    """یافتن (لیست_کلید، ایندکس) شخص با کدملی مشخص در دادهٔ تسک چک."""
    if not old_nid:
        return None, None
    for list_key in _CHECK_PERSON_LIST_KEYS:
        for i, p in enumerate(task_data.get(list_key, []) or []):
            if str(p.get("national_id", "")) == str(old_nid):
                return list_key, i
    return None, None


@check_router.callback_query(F.data.startswith("chk_nid_fix:"))
async def chk_nid_fix_callback(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """کاربر دکمهٔ «ویرایش کدملی» را زد."""
    parts = callback.data.split(":")
    target_user_id = int(parts[1])

    if callback.from_user.id != target_user_id:
        await callback.answer("⚠️ این دکمه مربوط به شما نیست.")
        return

    win = _chk_nfw.get_window(target_user_id)
    if not win or win.get("flow") != _chk_nfw.FLOW_CHECK:
        await callback.answer(
            "⚠️ درخواستی برای ویرایش یافت نشد (مهلت ۳۰ دقیقه‌ای به پایان رسیده است).")
        return

    await callback.answer()

    task_data = win.get("task_data") or {}
    old_nid = win.get("national_id", "")
    list_key, person_idx = _find_check_person_idx(task_data, old_nid)

    if list_key is None:
        # شخص با کدملی خطادار در داده یافت نشد — شاید کدملی از متن پاپ‌آپ
        # استخراج نشده باشد؛ کاربر لیست اشخاص را می‌بیند
        persons_flat = []
        for lk in _CHECK_PERSON_LIST_KEYS:
            for i, p in enumerate(task_data.get(lk, []) or []):
                persons_flat.append((lk, i, p))
        if not persons_flat:
            await bot.send_message(
                target_user_id,
                "⚠️ فهرست اشخاص درخواست یافت نشد. لطفاً از منوی اصلی مجدداً اقدام فرمایید.",
                reply_markup=main_menu_kb)
            await state.clear()
            return
        await bot.send_message(
            target_user_id,
            "👥 لطفاً *شخصی را که کدملی اشتباه دارد* انتخاب فرمایید:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text=f"{i + 1}. {str(p.get('name') or p.get('national_id') or 'شخص ' + str(i + 1))[:40]}",
                    callback_data=f"chk_nid_pick:{target_user_id}:{lk}:{i}")]
                for i, (lk, idx, p) in enumerate(persons_flat)
            ]))
        await state.set_state(Form.check_nid_fix_select_person)
        return

    await state.update_data(_chk_nid_fix_list=list_key, _chk_nid_fix_index=person_idx)
    await bot.send_message(
        target_user_id,
        f"🔢 کدملی فعلی: `{old_nid}`\n\n"
        "لطفاً *کدملی صحیح* را ارسال فرمایید:\n_(۱۰ رقمی)_\n\n"
        "⚠️ اطلاعات قبلی دادخواست حفظ شده و فقط کدملی اصلاح می‌شود.",
        reply_markup=back_only_kb)
    await state.set_state(Form.check_nid_fix_new_nid)


@check_router.callback_query(F.data.startswith("chk_nid_pick:"))
async def chk_nid_pick_callback(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """کاربر شخصی را برای ویرایش کدملی انتخاب کرد."""
    parts = callback.data.split(":")
    target_user_id = int(parts[1])
    list_key = parts[2]
    person_idx = int(parts[3])

    if callback.from_user.id != target_user_id:
        await callback.answer("⚠️ این دکمه مربوط به شما نیست.")
        return

    win = _chk_nfw.get_window(target_user_id)
    if not win or win.get("flow") != _chk_nfw.FLOW_CHECK:
        await callback.answer("⚠️ مهلت ویرایش به پایان رسیده است.")
        return

    await callback.answer()
    await state.update_data(_chk_nid_fix_list=list_key, _chk_nid_fix_index=person_idx)

    old_nid = ((win.get("task_data") or {}).get(list_key, []) or [{}])[person_idx].get("national_id", "")
    await bot.send_message(
        target_user_id,
        f"🔢 کدملی فعلی: `{old_nid or '---'}`\n\n"
        "لطفاً *کدملی صحیح* را ارسال فرمایید:\n_(۱۰ رقمی)_\n\n"
        "⚠️ اطلاعات قبلی دادخواست حفظ شده و فقط کدملی اصلاح می‌شود.",
        reply_markup=back_only_kb)
    await state.set_state(Form.check_nid_fix_new_nid)


@check_router.callback_query(F.data.startswith("chk_nid_cancel:"))
async def chk_nid_cancel_callback(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """حذف درخواست — بستن پنجرهٔ ۳۰ دقیقه‌ای + اعمال جریمهٔ نصف پیش‌پرداخت."""
    parts = callback.data.split(":")
    target_user_id = int(parts[1])

    if callback.from_user.id != target_user_id:
        await callback.answer("⚠️ این دکمه مربوط به شما نیست.")
        return

    _chk_nfw.pop_window(target_user_id)
    await callback.answer("درخواست حذف شد.")

    # جریمه — نصف مبلغ پیش‌پرداخت برای موارد بعدی (عین دستور کارفرما)
    new_rial = _chk_nfw.halve_prepaid(target_user_id)
    penalty_line = (
        f"💰 نصف مبلغ پیش‌پرداخت شما ({new_rial // 10:,} تومان) برای موارد بعدی "
        "شما لحاظ شد و از هزینه کسر می‌گردد.\n" if new_rial > 0 else "")

    try:
        await callback.message.edit_text(
            (callback.message.text or "") + "\n\n🗑 _درخواست حذف شد._")
    except Exception:
        pass

    await bot.send_message(
        target_user_id,
        "🗑 *درخواست دادخواست حذف شد.*\n\n"
        f"{penalty_line}\n"
        "در صورت نیاز، از منوی اصلی مجدداً اقدام فرمایید.",
        reply_markup=main_menu_kb)
    await state.clear()


@check_router.message(Form.check_nid_fix_select_person)
async def chk_nid_select_person_message(message: Message, state: FSMContext):
    """در حالت انتخاب شخص، فقط دکمه‌های اینلاین معتبرند."""
    if message.text == "🔙 بازگشت":
        _chk_nfw.pop_window(message.from_user.id)
        await message.answer(
            "🗑 ویرایش لغو شد و درخواست حذف شد.", reply_markup=main_menu_kb)
        await state.clear()
        return
    await message.answer("⚠️ لطفاً شخص را از دکمه‌های بالا انتخاب فرمایید.")


@check_router.message(Form.check_nid_fix_new_nid)
async def chk_nid_receive_new_nid(message: Message, state: FSMContext, bot: Bot):
    """دریافت کدملی جدید و ادامهٔ ثبت دادخواست با همان اطلاعات سیو شده."""
    if not message.text:
        return

    user_id = message.from_user.id
    _fa_ar = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    nat_id = message.text.translate(_fa_ar).replace(" ", "").strip()

    if message.text == "🔙 بازگشت":
        _chk_nfw.pop_window(user_id)
        await message.answer(
            "🗑 ویرایش لغو شد و درخواست حذف شد.", reply_markup=main_menu_kb)
        await state.clear()
        return

    if not re.match(r"^[0-9]{10}$", nat_id):
        await message.answer("⚠️ کدملی باید *۱۰ رقمی* باشد:")
        return

    win = _chk_nfw.pop_window(user_id)
    if not win or win.get("flow") != _chk_nfw.FLOW_CHECK:
        await message.answer(
            "⚠️ درخواست منقضی شده است. لطفاً مجدداً اقدام فرمایید.",
            reply_markup=main_menu_kb)
        await state.clear()
        return

    fsm_data = await state.get_data()
    list_key = fsm_data.get("_chk_nid_fix_list")
    person_idx = fsm_data.get("_chk_nid_fix_index")

    task_data = win.get("task_data") or {}
    if list_key is None:
        list_key, person_idx = _find_check_person_idx(task_data, win.get("national_id", ""))

    if list_key is None or person_idx is None:
        await message.answer(
            "⚠️ شخص مورد نظر یافت نشد. لطفاً مجدداً اقدام فرمایید.",
            reply_markup=main_menu_kb)
        await state.clear()
        return

    persons = task_data.get(list_key, [])
    if person_idx >= len(persons):
        await message.answer(
            "⚠️ شخص مورد نظر یافت نشد. لطفاً مجدداً اقدام فرمایید.",
            reply_markup=main_menu_kb)
        await state.clear()
        return

    old_nid = persons[person_idx].get("national_id", "")
    persons[person_idx]["national_id"] = nat_id
    task_data[list_key] = persons
    task_data.pop("_sana_error_national_id", None)
    task_data.pop("_sana_error_role", None)
    task_data.pop("_sana_error_kind", None)

    logging.info(
        f"[CHECK] کدملی ({list_key}[{person_idx}]) کاربر {user_id} ویرایش شد: "
        f"{old_nid} → {nat_id} — ارسال مجدد به صف")
    try:
        await bot.send_message(
            _CHK_ADMIN_ID,
            f"✏️ [CHECK] کدملی کاربر {user_id} ویرایش شد ({old_nid} → {nat_id}) "
            "— درخواست مجدداً به صف ارسال شد.")
    except Exception:
        pass

    await message.answer(
        f"✅ کدملی به `{nat_id}` تغییر یافت.\n\n"
        "⏳ ثبت دادخواست با *همان اطلاعات سیو شده* ادامه می‌یابد...",
        reply_markup=main_menu_kb)

    # ارسال مجدد تسک — بدون طی مجدد سایر مراحل
    await runtime_state.job_queue.put(task_data)
    await state.clear()
