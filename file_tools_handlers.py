"""
هندلرهای بخش «ابزار فایل» — گزینه‌ی مستقل در منوی اصلی.
شامل دو ابزار:
۱) کاهش حجم عکس (فشرده‌سازی هوشمند تا رسیدن به حجم هدف)
۲) تبدیل فایل PDF چندصفحه‌ای به عکس — هر صفحه به‌صورت یک عکس جداگانه ارسال می‌شود

🔧 اصلاحیه: هر صفحه با send_photo (نه answer_document) ارسال می‌شود تا واقعاً
به‌صورت عکس نمایش داده شود، و بین ارسال‌ها تأخیر کوتاهی گذاشته شده تا بله
پیام‌ها را در یک آلبوم بصری ادغام نکند.
"""
import asyncio
import io
import logging
import os
from aiogram import Bot, F, Router
from aiogram.types import Message, FSInputFile, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from PIL import Image
import numpy as np
import runtime_state
from config import ADMIN_ID, CARD_NUMBER, ACCOUNT_NAME
from states import Form
from keyboards import flow_type_kb, file_tools_menu_kb, file_tools_back_kb, subscription_kb, restart_kb

file_tools_router = Router()

# حداکثر تعداد صفحات مجاز برای تبدیل PDF (برای جلوگیری از فایل‌های خیلی حجیم/کند)
MAX_PDF_PAGES = 40
# حجم هدف برای فشرده‌سازی عکس (کیلوبایت)
TARGET_IMAGE_KB = 500
# فاصله‌ی زمانی بین ارسال هر صفحه (ثانیه) — از ادغام بصری پیام‌ها در بله جلوگیری می‌کند
PAGE_SEND_DELAY = 0.35

# اگر نسبت ارتفاع به عرض یک صفحه‌ی PDF از این مقدار بیشتر شود، آن را «صفحه‌ی بلند
# مشکوک» در نظر می‌گیریم (احتمالاً چند «کارت صفحه» بصری در یک صفحه‌ی PDF واقعی
# چسبیده‌اند، مثل رزومه‌هایی که از ابزارهای وب بدون Page Break واقعی گرفته شده‌اند)
TALL_PAGE_ASPECT_THRESHOLD = 1.6
# آستانه‌ی روشنایی برای تشخیص ردیف «سفید/خالی» (۰ تا ۲۵۵)
BLANK_ROW_BRIGHTNESS = 250
# حداقل ارتفاع یک شکاف سفید (به پیکسل) تا آن را مرز واقعی بین دو «کارت صفحه» بدانیم
MIN_GAP_PX = 25
# حداقل ارتفاع هر بخش خروجی پس از برش (برای رد کردن تکه‌های خیلی کوچک/بی‌معنی)
MIN_SEGMENT_PX = 150


def _split_tall_page(img: Image.Image) -> list:
    """
    اگر یک صفحه‌ی PDF غیرعادی بلند باشد (نسبت ارتفاع به عرض بالا)، شکاف‌های
    سفید/خالی افقی بین «کارت‌های صفحه» را پیدا کرده و تصویر را از وسط هر شکاف
    به چند تکه‌ی جداگانه برش می‌زند. اگر صفحه بلند نبود یا شکاف مناسبی پیدا
    نشد، همان تصویر اصلی را در یک لیست تک‌عضوی برمی‌گرداند.
    """
    if img.height / img.width < TALL_PAGE_ASPECT_THRESHOLD:
        return [img]

    gray = np.array(img.convert("L"))
    row_means = gray.mean(axis=1)
    is_blank_row = row_means >= BLANK_ROW_BRIGHTNESS

    gaps = []
    start = None
    for y, blank in enumerate(is_blank_row):
        if blank and start is None:
            start = y
        elif not blank and start is not None:
            if y - start >= MIN_GAP_PX:
                gaps.append((start, y))
            start = None
    if start is not None and len(is_blank_row) - start >= MIN_GAP_PX:
        gaps.append((start, len(is_blank_row)))

    if not gaps:
        return [img]

    cut_points = [0] + [(g_start + g_end) // 2 for g_start, g_end in gaps] + [img.height]

    segments = []
    for i in range(len(cut_points) - 1):
        top, bottom = cut_points[i], cut_points[i + 1]
        if bottom - top < MIN_SEGMENT_PX:
            continue
        segments.append(img.crop((0, top, img.width, bottom)))

    return segments if segments else [img]


SUBSCRIPTION_FEE = runtime_state.SUBSCRIPTION_FEE
MAX_FREE_USAGE = runtime_state.MAX_FREE_USAGE


def _subscription_required_message_tools(user_id: int) -> tuple:
    """ساخت پیام و کیبورد درخواست اشتراک برای بخش ابزار."""
    msg = (
        f"⚠️ *محدودیت استفاده رایگان تمام شد*\n\n"
        f"شما {MAX_FREE_USAGE} بار استفاده رایگان از بخش ابزار را مصرف کرده‌اید.\n\n"
        f"💰 جهت استفاده مجدد از بخش ابزار و محاسبه تمبر، *اشتراک ماهیانه* را فعال نمایید.\n\n"
        f"💳 مبلغ اشتراک ماهیانه: *{SUBSCRIPTION_FEE:,} ریال*\n\n"
        f"⏱ مدت اشتراک: *{runtime_state.SUBSCRIPTION_DURATION_DAYS} روز*"
    )
    return msg, subscription_kb


async def file_tools_entry(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id

    # بررسی محدودیت استفاده
    if not runtime_state.can_use_service(user_id, "tools"):
        msg, kb = _subscription_required_message_tools(user_id)
        await message.answer(msg, reply_markup=kb)
        return

    # نمایش وضعیت اشتراک
    remaining = runtime_state.get_remaining_free(user_id, "tools")
    if runtime_state.has_active_subscription(user_id):
        sub = runtime_state.user_subscriptions[user_id]
        end_str = sub["end_date"].strftime("%Y/%m/%d %H:%M")
        status = f"✅ اشتراک فعال تا {end_str}\n\n"
    else:
        status = f"📋 استفاده رایگان: {remaining} از {MAX_FREE_USAGE} دفعه باقی‌مانده\n\n"

    await message.answer(
        f"🛠 *ابزار فایل*\n\n"
        f"{status}"
        f"لطفاً یکی از ابزارهای زیر را انتخاب فرمایید:\n\n"
        f"🖼 *کاهش حجم عکس* — عکس را ارسال کنید تا حجم آن کاهش یابد.\n"
        f"📄➡️🖼 *تبدیل PDF به عکس* — فایل PDF چندصفحه‌ای را ارسال کنید تا هر صفحهٔ آن "
        f"به‌صورت یک عکس جداگانه ارسال شود.",
        reply_markup=file_tools_menu_kb)
    await state.set_state(Form.file_tools_menu)


@file_tools_router.message(Form.file_tools_menu)
async def file_tools_menu_handler(message: Message, state: FSMContext):
    text = message.text or ""
    if text == "🖼 کاهش حجم عکس":
        await message.answer(
            "🖼 لطفاً عکس مورد نظر را ارسال فرمایید (به صورت Photo یا فایل تصویری):",
            reply_markup=file_tools_back_kb
        )
        await state.set_state(Form.file_tools_waiting_image)
        return
    if text == "📄➡️🖼 تبدیل PDF به عکس":
        await message.answer(
            "📄 لطفاً فایل PDF مورد نظر را ارسال فرمایید:",
            reply_markup=file_tools_back_kb
        )
        await state.set_state(Form.file_tools_waiting_pdf)
        return
    if text == "🔙 بازگشت به منوی اصلی":
        await state.clear()
        await message.answer("بازگشت به منوی اصلی.", reply_markup=flow_type_kb)
        await state.set_state(Form.waiting_for_flow_type)
        return
    await message.answer("⚠️ لطفاً یکی از گزینه‌های منو را انتخاب فرمایید:", reply_markup=file_tools_menu_kb)


def _compress_image(src_path: str, dst_path: str, target_kb: int = TARGET_IMAGE_KB) -> int:
    """
    عکس را با کاهش تدریجی کیفیت/ابعاد فشرده می‌کند تا حجم آن به حدود target_kb برسد.
    خروجی: حجم نهایی فایل به بایت.
    """
    img = Image.open(src_path)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    quality = 90
    scale = 1.0
    target_bytes = target_kb * 1024
    while True:
        w, h = img.size
        resized = img
        if scale < 1.0:
            resized = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
        buf = io.BytesIO()
        resized.save(buf, format="JPEG", quality=quality, optimize=True)
        size = buf.tell()
        if size <= target_bytes or (quality <= 30 and scale <= 0.3):
            with open(dst_path, "wb") as f:
                f.write(buf.getvalue())
            return size
        if quality > 30:
            quality -= 10
        else:
            scale -= 0.15


@file_tools_router.message(Form.file_tools_waiting_image, F.text == "🔙 بازگشت")
async def file_tools_image_back(message: Message, state: FSMContext):
    await message.answer("🛠 بازگشت به منوی ابزار فایل:", reply_markup=file_tools_menu_kb)
    await state.set_state(Form.file_tools_menu)


@file_tools_router.message(Form.file_tools_waiting_image, F.photo | F.document)
async def file_tools_receive_image(message: Message, state: FSMContext, bot: Bot):
    is_photo = bool(message.photo)
    if not is_photo and not (message.document and (message.document.mime_type or "").startswith("image/")):
        await message.answer("⚠️ لطفاً یک فایل تصویری (عکس) ارسال فرمایید.")
        return

    await message.answer("⏳ در حال دریافت و فشرده‌سازی عکس...")

    file_id = message.photo[-1].file_id if is_photo else message.document.file_id
    user_id = message.from_user.id

    # افزایش شمارنده استفاده
    runtime_state.increment_usage(user_id, "tools")
    src_path = f"filetools_src_{user_id}.jpg"
    dst_path = f"filetools_compressed_{user_id}.jpg"

    try:
        file_info = await bot.get_file(file_id)
        await bot.download_file(file_info.file_path, src_path)
        original_size = os.path.getsize(src_path)

        final_size = _compress_image(src_path, dst_path)
        if final_size >= original_size:
            os.replace(src_path, dst_path)
            final_size = os.path.getsize(dst_path)

        await message.answer_document(
            FSInputFile(dst_path),
            caption=(
                f"✅ *کاهش حجم انجام شد.*\n\n"
                f"حجم اولیه: {original_size / 1024:.0f} کیلوبایت\n"
                f"حجم نهایی: {final_size / 1024:.0f} کیلوبایت"
            ))
    except Exception:
        logging.exception("file_tools image compress error")

        try:
            from bug_reporter import report_bug
            await report_bug(bot, where="file_tools_receive_image", error=e,
                             user_id=user_id,
                             page=getattr(runtime_state, "sana_page", None))
        except Exception:
            pass
        await message.answer("❌ خطایی در پردازش عکس رخ داد. لطفاً دوباره تلاش کنید.")
    finally:
        for p in (src_path, dst_path):
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass

    await message.answer(
        "می‌توانید عکس دیگری ارسال کنید یا بازگردید:",
        reply_markup=file_tools_back_kb
    )


@file_tools_router.message(Form.file_tools_waiting_pdf, F.text == "🔙 بازگشت")
async def file_tools_pdf_back(message: Message, state: FSMContext):
    await message.answer("🛠 بازگشت به منوی ابزار فایل:", reply_markup=file_tools_menu_kb)
    await state.set_state(Form.file_tools_menu)


@file_tools_router.message(Form.file_tools_waiting_pdf, F.document)
async def file_tools_receive_pdf(message: Message, state: FSMContext, bot: Bot):
    mime = (message.document.mime_type or "")
    fname = (message.document.file_name or "")
    if mime != "application/pdf" and not fname.lower().endswith(".pdf"):
        await message.answer("⚠️ لطفاً فقط فایل با فرمت PDF ارسال فرمایید.")
        return

    await message.answer(
        "⏳ در حال تبدیل فایل PDF به عکس...\n"
        "هر صفحه به‌صورت یک عکس جداگانه ارسال می‌شود."
    )
    try:
        import fitz  # PyMuPDF — تبدیل صفحات PDF به تصویر
    except ImportError:
        logging.exception("PyMuPDF (fitz) not installed")
        await message.answer("❌ کتابخانهٔ PyMuPDF نصب نیست.\nدستور نصب: pip install PyMuPDF")
        return

    user_id = message.from_user.id
    pdf_path = f"filetools_src_{user_id}.pdf"
    page_paths: list[str] = []  # مسیر هر صفحه به‌صورت جداگانه

    # افزایش شمارنده استفاده
    runtime_state.increment_usage(user_id, "tools")
    try:
        file_info = await bot.get_file(message.document.file_id)
        await bot.download_file(file_info.file_path, pdf_path)
        pdf = fitz.open(pdf_path)
        page_count = pdf.page_count
        if page_count == 0:
            await message.answer("❌ فایل PDF ارسالی خالی یا نامعتبر است.")
            pdf.close()
            return
        if page_count > MAX_PDF_PAGES:
            await message.answer(
                f"⚠️ این فایل {page_count} صفحه دارد و بیشتر از حد مجاز ({MAX_PDF_PAGES} صفحه) است.\n"
                f"لطفاً فایل را به بخش‌های کوچک‌تر تقسیم و مجدداً ارسال کنید."
            )
            pdf.close()
            return

        # کیفیت رندر بر اساس تعداد صفحات
        zoom = 2.0 if page_count <= 10 else (1.5 if page_count <= 20 else 1.0)
        matrix = fitz.Matrix(zoom, zoom)

        # مرحله‌ی اول: رندر هر صفحه‌ی واقعی PDF، و در صورت «بلند و مشکوک» بودن،
        # برش خودکار به چند تکه از روی شکاف‌های سفید (برای فایل‌هایی که خودشان
        # فاقد Page Break واقعی‌اند ولی بصری چند «کارت صفحه» دارند)
        for i in range(page_count):
            pix = pdf.load_page(i).get_pixmap(matrix=matrix)
            mode = "RGB" if pix.n < 4 else "RGBA"
            page_img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
            if mode == "RGBA":
                page_img = page_img.convert("RGB")

            sub_images = _split_tall_page(page_img)

            for sub_idx, sub_img in enumerate(sub_images):
                suffix = f"p{i + 1:03d}" if len(sub_images) == 1 else f"p{i + 1:03d}_{sub_idx + 1}"
                page_path = f"filetools_pdf2img_{user_id}_{suffix}.jpg"
                sub_img.save(page_path, format="JPEG", quality=85, optimize=True)
                if os.path.getsize(page_path) > 9 * 1024 * 1024:
                    _compress_image(page_path, page_path, target_kb=8000)
                page_paths.append(page_path)
        pdf.close()

        # تعداد واقعی تصاویر خروجی ممکن است بیش از تعداد صفحات PDF باشد
        # (وقتی صفحه‌ای بلند بوده و برش خورده است)
        output_count = len(page_paths)

        # مرحله‌ی دوم: ارسال هر صفحه به‌صورت یک پیام مستقل با send_photo
        # (send_photo → نمایش واقعی به‌صورت عکس، نه فایل ضمیمه)
        for idx, page_path in enumerate(page_paths):
            page_num = idx + 1
            try:
                # پیام متنی جداگانه پیش از هر عکس — برای جدایی بصری واضح‌تر بین صفحات
                await message.answer(f"📄 صفحه {page_num} از {output_count}")
                await bot.send_photo(
                    chat_id=message.chat.id,
                    photo=FSInputFile(page_path)
                )
            except Exception as send_err:
                logging.error(f"file_tools pdf2image send page {page_num} error: {send_err}")
                await message.answer(f"⚠️ ارسال صفحه {page_num} با خطا مواجه شد.")
            # تأخیر کوتاه بین صفحات تا بله آن‌ها را در یک آلبوم بصری ادغام نکند
            if output_count > 1:
                await asyncio.sleep(PAGE_SEND_DELAY)

        await message.answer(
            f"✅ تبدیل انجام شد. ({output_count} عکس جداگانه ارسال شد)"
        )
    except Exception:
        logging.exception("file_tools pdf2image error")  # چاپ کامل traceback

        try:
            from bug_reporter import report_bug
            await report_bug(bot, where="file_tools_receive_pdf", error=e,
                             user_id=user_id,
                             page=getattr(runtime_state, "sana_page", None))
        except Exception:
            pass
        await message.answer("❌ خطایی در تبدیل فایل PDF رخ داد. لطفاً لاگ را بررسی کنید.")
    finally:
        for p in [pdf_path] + page_paths:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass
        await message.answer(
            "می‌توانید فایل PDF دیگری ارسال کنید یا بازگردید:",
            reply_markup=file_tools_back_kb
        )


@file_tools_router.message(Form.file_tools_waiting_pdf)
async def file_tools_pdf_wrong_type(message: Message, state: FSMContext):
    await message.answer("⚠️ لطفاً فایل PDF را به صورت Document ارسال فرمایید.")


@file_tools_router.message(Form.file_tools_waiting_image)
async def file_tools_image_wrong_type(message: Message, state: FSMContext):
    await message.answer("⚠️ لطفاً یک فایل تصویری (عکس) ارسال فرمایید یا 🔙 بازگشت را بزنید.")
