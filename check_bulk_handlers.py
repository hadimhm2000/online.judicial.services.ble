# -*- coding: utf-8 -*-
"""
check_bulk_handlers.py
──────────────────────────────────────────────────────────────────────────
جایگزین check_bulk_file_upload_handler فعلی در check_handlers.py (که با
ستون‌بندی واقعی فایل هماهنگ نیست) + مرحلهٔ جدید و اجباری پیوست‌گذاری:

  به ازای هر ردیفِ معتبرِ اکسل، کاربر باید حداقل یک‌بار «🧾 تصویر چک» را
  طی کند و دقیقاً ۳ تصویر (روی چک، پشت چک، گواهی عدم پرداخت) ارسال کند.
  بدون تکمیل این ۳ تصویر، امکان رد شدن از ردیف یا رسیدن به تایید نهایی وجود ندارد.

نحوهٔ نصب:
  1) این فایل را کنار check_handlers.py قرار دهید.
  2) در states.py، Stateهای states_check_bulk_patch.py را اضافه کنید.
  3) در bot.py (یا هرجا روترها include می‌شوند)، این روتر را هم include کنید:
        from check_bulk_handlers import check_bulk_router
        dp.include_router(check_bulk_router)
  4) در check_handlers.py تابع check_bulk_download_sample را طوری اصلاح کنید
     که فایل جدید «ثبت_دسته_جمعی_چک_هوشمند.xlsx» را بفرستد (نه sample_check.xlsx
     قدیمی که ستون‌بندی متفاوتی دارد) و توضیح متن راهنما را هم به‌روزرسانی کنید.
  5) تابع check_bulk_file_upload_handler موجود در check_handlers.py را با
     check_bulk_file_upload_handler همین فایل جایگزین کنید (امضا و state یکسان است:
     Form.check_bulk_file_upload).

نکتهٔ مهم دربارهٔ این نسخه:
  حالا این فایل «پیش‌بررسی اکسل + اجبار تصویر چک + صف‌بندی واقعی در
  BULK_TASKS/job_queue» را کامل انجام می‌دهد — دقیقاً با استفاده از همان
  BULK_TASKS، mark_bulk_item_done و finalize_bulk_batch که در
  bulk_submissions.py برای لایحه/اظهارنامه هست (این دو تابع سرویس‌مستقل
  نوشته شده‌اند و بدون تغییر برای چک هم کار می‌کنند). تنها بخشی که باید
  جداگانه در check_scenario.py پچ شود، دو نقطهٔ موفقیت/شکست process_check_task
  است — نگاه کنید به فایل check_scenario_bulk_patch.md.
"""

import logging
import os
import tempfile
from datetime import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

import runtime_state
from states import Form
from keyboards import back_only_kb
from check_bulk_validation import pre_validate_check_bulk_file, format_check_report_fa
from bulk_submissions import BULK_TASKS, generate_tracking_code, mark_bulk_item_done

logger = logging.getLogger(__name__)

check_bulk_router = Router()

MAX_CHECK_IMAGES = 3  # دقیقاً مطابق ثبت تکی چک (check_handlers.MAX_CHECK_IMAGES)


# ══════════════════════════════════════════════════════════════════════════
# تبدیل خواهان/خوانده به فرمتی که check_scenario.py انتظار دارد
# (همان شکلی که check_handlers.py::check_plaintiff_*/defendant_* در FSM data می‌سازد)
# ══════════════════════════════════════════════════════════════════════════
def _transform_check_persons(persons: list) -> list:
    out = []
    for p in persons:
        if p.get("type") == "شخص حقوقی":
            out.append({
                "person_type": "شخص حقوقی",
                "company_id": p.get("id", ""),
                "representative_type": p.get("company_rep_type", ""),
                "national_id": p.get("company_rep", ""),
            })
        else:
            out.append({
                "person_type": p.get("type", "شخص حقیقی"),
                "national_id": p.get("id", ""),
            })
    return out


def _build_check_job(item: dict, user_id: int, tracking_code: str, row_idx: int) -> dict:
    """دقیقاً همان شکل دیکشنری‌ای که check_handlers.py::check_confirm_handler
    برای ثبت تکی به job_queue می‌فرستد — به‌علاوهٔ فلگ‌های دسته‌جمعی."""
    return {
        "user_id": user_id,
        "query_type": "دادخواست_چک",
        "task_type": "CHECK_SUBMIT",
        "check_request_title": item.get("title", ""),
        "check_amount": int(item.get("amount") or 0),
        "check_khasteh_text": item.get("khasteh_text", ""),
        "check_tracking_no": item.get("tracking_code", ""),
        "check_plainiffs": _transform_check_persons(item.get("plaintiffs", [])),
        "check_defendants": _transform_check_persons(item.get("defendants", [])),
        "check_witnesses": [{"national_id": w} for w in item.get("witnesses", [])],
        "check_text": item.get("text", ""),
        "check_text_html": "",
        "check_extra_text": item.get("extra_text", ""),
        "check_images": item.get("check_images", []),
        "check_attachment_groups": item.get("extra_attachments", []),
        "check_branch_code": item.get("branch_code", ""),
        "check_branch_name": item.get("branch_name", ""),
        "check_branch_path": item.get("branch_path", ""),
        "check_docx_file_id": None,
        "check_docx_file_name": "",
        "_is_bulk_check": True,
        "batch_tracking_code": tracking_code,
        "_bulk_row_index": row_idx,
    }


# ══════════════════════════════════════════════════════════════════════════
# کیبوردها
# ══════════════════════════════════════════════════════════════════════════
def bulk_check_images_kb(count: int) -> ReplyKeyboardMarkup:
    """
    قبل از رسیدن به ۳ تصویر: فقط دکمه بازگشت.
    دقیقاً بعد از ۳ تصویر: دکمه ادامه (اجباری بودن یعنی تا این لحظه دکمهٔ
    ادامه/رد کردن اصلاً روی صفحه نیست).
    """
    if count >= MAX_CHECK_IMAGES:
        return ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="✅ ۳ تصویر ارسال شد - ادامه")]],
            resize_keyboard=True,
        )
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 بازگشت")]],
        resize_keyboard=True,
    )


bulk_check_extra_choice_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📎 بله، مدرک دیگری هم دارم")],
        [KeyboardButton(text="✅ خیر، برو به ردیف بعدی")],
    ],
    resize_keyboard=True,
)


# ══════════════════════════════════════════════════════════════════════════
# دریافت فایل اکسل و پیش‌بررسی
# ══════════════════════════════════════════════════════════════════════════
@check_bulk_router.message(Form.check_bulk_file_upload)
async def check_bulk_file_upload_handler(message: Message, state: FSMContext):
    if message.text and message.text == "🔙 بازگشت":
        from keyboards import bulk_input_method_kb
        await message.answer(
            "📊 *ثبت دسته‌جمعی دعاوی چک*\n\nلطفاً ابتدا فایل نمونه اکسل را دریافت و تکمیل نمایید:",
            reply_markup=bulk_input_method_kb,
        )
        await state.set_state(Form.check_bulk_input_method)
        return

    if not message.document:
        await message.answer("⚠️ لطفاً فایل اکسل (.xlsx) را ارسال فرمایید.", reply_markup=back_only_kb)
        return

    doc = message.document
    if not (doc.file_name and doc.file_name.endswith((".xlsx", ".xls"))):
        await message.answer("⚠️ لطفاً فقط فایل با پسوند اکسل (.xlsx) ارسال فرمایید.", reply_markup=back_only_kb)
        return

    await message.answer("⏳ در حال دانلود و پیش‌بررسی فایل...")

    try:
        tmp_dir = tempfile.mkdtemp()
        file_path = os.path.join(tmp_dir, doc.file_name or "bulk_check.xlsx")
        await message.bot.download_file((await message.bot.get_file(doc.file_id)).file_path, file_path)

        result = pre_validate_check_bulk_file(file_path)
    except Exception as e:
        logger.error(f"[CHECK-BULK] خطا در پردازش اکسل: {e}")
        await message.answer(
            "⚠️ خطا در خواندن فایل اکسل. لطفاً از فایل نمونهٔ جدید («ثبت_دسته_جمعی_چک_هوشمند.xlsx») استفاده کنید.",
            reply_markup=back_only_kb,
        )
        return

    for chunk in format_check_report_fa(result):
        await message.answer(chunk)

    valid_items = result["valid_items"]
    if not valid_items:
        await message.answer("⚠️ هیچ ردیف معتبری یافت نشد. فایل را اصلاح و دوباره ارسال کنید.", reply_markup=back_only_kb)
        return

    await state.update_data(
        check_bulk_items=valid_items,
        check_bulk_current_index=0,
    )
    await _prompt_check_images_for_row(message, state)


async def _prompt_check_images_for_row(message: Message, state: FSMContext):
    data = await state.get_data()
    items = data.get("check_bulk_items", [])
    idx = data.get("check_bulk_current_index", 0)
    item = items[idx]
    item.setdefault("check_images", [])
    await state.update_data(check_bulk_items=items)

    plaintiff1 = (item.get("plaintiffs") or [{}])[0].get("id", "-")
    defendant1 = (item.get("defendants") or [{}])[0].get("id", "-")

    await message.answer(
        f"🧾 *ردیف {idx + 1} از {len(items)}*\n"
        f"👤 خواهان نفر ۱: `{plaintiff1}`  |  👥 خوانده نفر ۱: `{defendant1}`\n"
        f"💰 مبلغ: {item.get('amount', '-')} ریال\n\n"
        f"لطفاً برای همین ردیف، *تصویر چک* را ارسال فرمایید.\n"
        f"دقیقاً {MAX_CHECK_IMAGES} تصویر لازم است: روی چک، پشت چک، گواهی عدم پرداخت.\n"
        f"({len(item['check_images'])}/{MAX_CHECK_IMAGES})",
        reply_markup=bulk_check_images_kb(len(item["check_images"])),
    )
    await state.set_state(Form.bulk_check_images_row)


@check_bulk_router.message(Form.bulk_check_images_row, F.photo)
async def bulk_check_images_photo_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    items = data.get("check_bulk_items", [])
    idx = data.get("check_bulk_current_index", 0)
    item = items[idx]
    images = item.setdefault("check_images", [])

    if len(images) >= MAX_CHECK_IMAGES:
        await message.answer(
            f"⚠️ حداکثر {MAX_CHECK_IMAGES} تصویر چک برای این ردیف مجاز است. لطفاً «ادامه» را بزنید.",
            reply_markup=bulk_check_images_kb(len(images)),
        )
        return

    # فرمت دقیقاً مثل check_images تکی (check_handlers.py::check_receive_photo):
    # لیستی از دیکشنری‌های {"file_id": ...} — نه رشتهٔ خام — چون check_scenario.py
    # (_download_check_images) همین فرمت را انتظار دارد.
    file_id = message.photo[-1].file_id
    images.append({"file_id": file_id})
    item["has_check_image_title"] = True  # گزینهٔ «تصویر چک» برای این ردیف حداقل یک‌بار طی شد
    await state.update_data(check_bulk_items=items)

    remaining = MAX_CHECK_IMAGES - len(images)
    if remaining > 0:
        await message.answer(
            f"✅ تصویر دریافت شد. ({len(images)}/{MAX_CHECK_IMAGES})\n"
            f"لطفاً {remaining} تصویر دیگر ارسال فرمایید:",
            reply_markup=bulk_check_images_kb(len(images)),
        )
    else:
        await message.answer(
            f"✅ هر {MAX_CHECK_IMAGES} تصویر چک دریافت شد.\n"
            f"می‌توانید ادامه دهید:",
            reply_markup=bulk_check_images_kb(len(images)),
        )


@check_bulk_router.message(Form.bulk_check_images_row, F.text == "✅ ۳ تصویر ارسال شد - ادامه")
async def bulk_check_images_done_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    items = data.get("check_bulk_items", [])
    idx = data.get("check_bulk_current_index", 0)
    item = items[idx]

    # قفل واقعی الزامی‌بودن — حتی اگر کیبورد دستکاری شده باشد
    if len(item.get("check_images", [])) < MAX_CHECK_IMAGES or not item.get("has_check_image_title"):
        await message.answer(
            f"⚠️ برای این ردیف هنوز {MAX_CHECK_IMAGES} تصویر چک ثبت نشده است. لطفاً ادامه دهید:",
            reply_markup=bulk_check_images_kb(len(item.get("check_images", []))),
        )
        return

    await message.answer(
        "📎 آیا مدرک دیگری (غیر از تصویر چک) برای این ردیف دارید؟",
        reply_markup=bulk_check_extra_choice_kb,
    )
    await state.set_state(Form.bulk_check_extra_attachment_choice)


@check_bulk_router.message(Form.bulk_check_images_row, F.text == "🔙 بازگشت")
async def bulk_check_images_back_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    items = data.get("check_bulk_items", [])
    idx = data.get("check_bulk_current_index", 0)
    item = items[idx]
    if item.get("check_images"):
        item["check_images"].pop()
        if not item["check_images"]:
            item["has_check_image_title"] = False
        await state.update_data(check_bulk_items=items)
    await _prompt_check_images_for_row(message, state)


@check_bulk_router.message(Form.bulk_check_images_row)
async def bulk_check_images_fallback(message: Message, state: FSMContext):
    data = await state.get_data()
    items = data.get("check_bulk_items", [])
    idx = data.get("check_bulk_current_index", 0)
    item = items[idx]
    await message.answer(
        "⚠️ لطفاً فقط *تصویر* ارسال کنید یا از دکمه‌های زیر استفاده کنید:",
        reply_markup=bulk_check_images_kb(len(item.get("check_images", []))),
    )


# ══════════════════════════════════════════════════════════════════════════
# مدارک اضافی (اختیاری) — دقیقاً مثل check_attachment_title/images تکی
# ══════════════════════════════════════════════════════════════════════════
@check_bulk_router.message(Form.bulk_check_extra_attachment_choice, F.text == "📎 بله، مدرک دیگری هم دارم")
async def bulk_check_extra_attachment_choice_yes(message: Message, state: FSMContext):
    await message.answer("📄 عنوان این مدرک را بنویسید (مثلاً «وکالتنامه»، «کارت ملی»):", reply_markup=back_only_kb)
    await state.set_state(Form.bulk_check_extra_attachment_title)


@check_bulk_router.message(Form.bulk_check_extra_attachment_choice, F.text == "✅ خیر، برو به ردیف بعدی")
async def bulk_check_extra_attachment_choice_no(message: Message, state: FSMContext):
    await _advance_to_next_row(message, state)


@check_bulk_router.message(Form.bulk_check_extra_attachment_title)
async def bulk_check_extra_attachment_title_handler(message: Message, state: FSMContext):
    if not message.text or message.text == "🔙 بازگشت":
        await message.answer("📎 آیا مدرک دیگری دارید؟", reply_markup=bulk_check_extra_choice_kb)
        await state.set_state(Form.bulk_check_extra_attachment_choice)
        return

    await state.update_data(_bulk_check_current_extra_title=message.text.strip())
    await message.answer("🖼 تصاویر این مدرک را ارسال کنید و در پایان «اتمام» را بزنید:", reply_markup=back_only_kb)
    await state.set_state(Form.bulk_check_extra_attachment_images)


@check_bulk_router.message(Form.bulk_check_extra_attachment_images, F.photo)
async def bulk_check_extra_attachment_images_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    file_id = message.photo[-1].file_id
    buf = data.get("_bulk_check_current_extra_images", [])
    buf.append(file_id)
    await state.update_data(_bulk_check_current_extra_images=buf)
    await message.answer(f"✅ دریافت شد. ({len(buf)} تصویر) — تصویر بعدی یا «اتمام»:", reply_markup=back_only_kb)


@check_bulk_router.message(Form.bulk_check_extra_attachment_images, F.text.in_({"اتمام", "پایان", "✅ اتمام"}))
async def bulk_check_extra_attachment_images_done(message: Message, state: FSMContext):
    data = await state.get_data()
    items = data.get("check_bulk_items", [])
    idx = data.get("check_bulk_current_index", 0)
    item = items[idx]

    title = data.get("_bulk_check_current_extra_title", "سایر مستندات")
    images = data.get("_bulk_check_current_extra_images", [])
    extra_attachments = item.setdefault("extra_attachments", [])
    extra_attachments.append({"title": title, "images": images})

    await state.update_data(
        check_bulk_items=items,
        _bulk_check_current_extra_title="",
        _bulk_check_current_extra_images=[],
    )
    await message.answer(
        f"✅ مدرک «{title}» ({len(images)} تصویر) ثبت شد.\nآیا مدرک دیگری هم دارید؟",
        reply_markup=bulk_check_extra_choice_kb,
    )
    await state.set_state(Form.bulk_check_extra_attachment_choice)


# ══════════════════════════════════════════════════════════════════════════
# رفتن به ردیف بعدی یا نهایی‌سازی
# ══════════════════════════════════════════════════════════════════════════
async def _advance_to_next_row(message: Message, state: FSMContext):
    data = await state.get_data()
    items = data.get("check_bulk_items", [])
    idx = data.get("check_bulk_current_index", 0)
    next_idx = idx + 1

    if next_idx >= len(items):
        await _finalize_check_bulk(message, state)
        return

    await state.update_data(check_bulk_current_index=next_idx)
    await _prompt_check_images_for_row(message, state)


async def _finalize_check_bulk(message: Message, state: FSMContext):
    data = await state.get_data()
    items = data.get("check_bulk_items", [])
    user_id = message.from_user.id

    # بررسی نهایی سخت‌گیرانه: هیچ ردیفی نباید بدون ۳ تصویر «تصویر چک» رد شده باشد.
    missing = [
        i + 1 for i, it in enumerate(items)
        if len(it.get("check_images", [])) < MAX_CHECK_IMAGES or not it.get("has_check_image_title")
    ]
    if missing:
        # این حالت نباید عملاً رخ دهد چون هر مرحله قفل دارد، ولی برای اطمینان کامل نگه داشته شده.
        await state.update_data(check_bulk_current_index=missing[0] - 1)
        await message.answer(f"⚠️ ردیف {missing[0]} هنوز تصویر چک کامل ندارد. برگردیم به آن ردیف:")
        await _prompt_check_images_for_row(message, state)
        return

    tracking_code = generate_tracking_code("CHK")
    total = len(items)

    # ⚠️ نکته: برخلاف bulk لایحه (که BULK_PREPAY_PER_ROW_TOMAN=200 تومان به‌ازای
    # هر ردیف پیش‌پرداخت می‌گیرد)، اینجا هیچ پیش‌پرداختی گرفته نمی‌شود، پس
    # task_data["prepaid_total_rial"] صفر می‌ماند و در پایان finalize_bulk_batch
    # کل هزینهٔ واقعی سامانه به‌عنوان «تسویه» فاکتور می‌شود. اگر می‌خواهید
    # مثل لایحه یک پیش‌پرداخت ثابت به‌ازای هر ردیف بگیرید، باید قبل از همین
    # حلقه یک مرحلهٔ invoice/pre-pay اضافه شود — بگویید تا در گام بعد اضافه کنم.
    BULK_TASKS[tracking_code] = {
        "items": items,
        "service_type": "CHECK",
        "status": "processing",
        "signable_items": [],
        "failures": [],
        "queued_count": 0,
        "completed_count": 0,
        "prepaid_total_rial": 0,
    }

    await message.answer(
        f"⏳ *در حال ارسال {total} ردیف به صف پردازش سامانه...*\n\n"
        f"🔒 کد پیگیری دسته‌جمعی: `{tracking_code}`",
        reply_markup=ReplyKeyboardRemove(),
    )

    queued = 0
    for idx, item in enumerate(items, start=1):
        try:
            job = _build_check_job(item, user_id, tracking_code, item.get("row_index", idx))
            await runtime_state.job_queue.put(job)
            queued += 1
            item["status"] = "queued"
        except Exception as e:
            logger.error(f"[CHECK-BULK] خطا در صف‌بندی ردیف {idx}: {e}", exc_info=True)
            BULK_TASKS[tracking_code]["failures"].append({
                "row_index": item.get("row_index", idx),
                "title": item.get("title", "?"),
                "error": str(e),
            })

        if queued % 5 == 0 or queued == total:
            try:
                await message.answer(f"📥 در صف ارسال: *{queued} از {total}*", parse_mode="Markdown")
            except Exception:
                pass

    BULK_TASKS[tracking_code]["queued_count"] = queued

    await message.answer(
        f"✅ *تمام {queued} ردیف در صف پردازش سامانه قرار گرفت.*\n\n"
        f"🔒 کد پیگیری: `{tracking_code}`\n\n"
        f"⏳ ردیف‌ها یکی‌یکی در ثنا ثبت خواهند شد و نتیجهٔ هر ردیف برایتان ارسال می‌شود.\n"
        f"📊 گزارش مالی نهایی فقط پس از پردازش *کامل همهٔ ردیف‌ها* ارسال خواهد شد.",
        parse_mode="Markdown",
    )
    await state.clear()

    # ⚠️ اگر queued == 0 (همهٔ ردیف‌ها موقع enqueue خطا دادند)، هیچ job ای
    # صف نشده تا mark_bulk_item_done را صدا بزند و finalize_bulk_batch هرگز
    # اجرا نمی‌شود. این حالت را همین‌جا صریح مدیریت می‌کنیم.
    if queued == 0:
        from bulk_submissions import finalize_bulk_batch
        await finalize_bulk_batch(message.bot, user_id, tracking_code)
