# -*- coding: utf-8 -*-
"""
admin_relay.py
──────────────────────────────────────────────────────────────────────────
دو قابلیت مستقل برای مدیر (ADMIN_ID)، هر دو با FSM مجزا از Form کاربران:

۱) /send <آیدی کاربر>
   ارسال خام (relay) هر پیامی (متن/عکس/فایل/ویدیو/صدا) عیناً برای همان کاربر.

۲) /case <آیدی کاربر>
   برای وقتی که مدیر خودش (مثلاً به‌خاطر کرش ربات یا رفع دستی مشکل) یک
   پرونده (لایحه/اظهارنامه/دعاوی اعتراضی/چک) را در سامانهٔ ثنا تکمیل کرده
   و می‌خواهد PDF نتیجه را — دقیقاً مثل حالتی که خود ربات موفق شده باشد —
   برای کاربر بفرستد:
     الف) نوع سرویس را انتخاب می‌کند (لایحه/اظهارنامه/دعاوی اعتراضی/چک)
     ب) فایل PDF نتیجه را ارسال می‌کند
     ج) اگر بخواهد، مبلغی وارد می‌کند → همان مسیر فاکتور + پرداخت + ورود
        خودکار به ناوبری امضا که برای ثبت خودکار هم استفاده می‌شود
        (send_lavayeh_result با service_type مناسب) طی می‌شود.
        اگر مبلغی وارد نکند، فقط فایل مستقیماً برای کاربر فرستاده می‌شود
        (بدون فاکتور/امضا).

نصب:
    در bot.py:
        from admin_relay import admin_relay_router
        dp.include_router(admin_relay_router)
    ⚠️ قبل از include شدن روتر اصلی کاربران (handlers.py) اضافه شود.
"""
import logging
import os
import tempfile

from aiogram import Bot, Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

from config import ADMIN_ID

logger = logging.getLogger(__name__)

admin_relay_router = Router()


class AdminRelayStates(StatesGroup):
    waiting_for_content = State()
    case_choose_service = State()
    case_upload_pdf = State()
    case_ask_amount_choice = State()
    case_enter_amount = State()
    case_enter_tracking = State()


# ══════════════════════════════════════════════════════════════════════════
# ۱) /send — ارسال خام
# ══════════════════════════════════════════════════════════════════════════
@admin_relay_router.message(F.text.startswith("/send"))
async def admin_send_command(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return  # کاربران عادی این کامند را نمی‌بینند؛ کاملاً بی‌صدا نادیده گرفته می‌شود

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().lstrip("-").isdigit():
        await message.answer(
            "⚠️ فرمت صحیح:\n`/send <آیدی عددی کاربر>`\n\n"
            "مثال: `/send 123456789`\n\n"
            "بعد از این کامند، پیام یا فایل موردنظر را ارسال کنید تا برای همان کاربر فرستاده شود.\n\n"
            "💡 برای ارسال نتیجهٔ یک پرونده (با فاکتور و امضای خودکار)، به‌جای این از "
            "`/case <آیدی کاربر>` استفاده کنید."
        )
        return

    target_user_id = int(parts[1].strip())
    await state.update_data(_admin_relay_target=target_user_id)
    await state.set_state(AdminRelayStates.waiting_for_content)
    await message.answer(
        f"✅ آیدی مقصد ثبت شد: `{target_user_id}`\n\n"
        f"حالا پیام متنی، عکس، یا فایل موردنظر را ارسال کنید تا عیناً برای این کاربر فرستاده شود.\n"
        f"برای لغو: /cancel"
    )


@admin_relay_router.message(AdminRelayStates.waiting_for_content, F.text == "/cancel")
async def admin_send_cancel(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.clear()
    await message.answer("❌ ارسال لغو شد.")


@admin_relay_router.message(AdminRelayStates.waiting_for_content)
async def admin_send_content(message: Message, state: FSMContext, bot: Bot):
    if message.from_user.id != ADMIN_ID:
        return

    data = await state.get_data()
    target_user_id = data.get("_admin_relay_target")
    if not target_user_id:
        await state.clear()
        await message.answer("⚠️ خطا: آیدی مقصد یافت نشد. دوباره با /send شروع کنید.")
        return

    try:
        if message.photo:
            await bot.send_photo(target_user_id, message.photo[-1].file_id, caption=message.caption or None)
        elif message.document:
            await bot.send_document(target_user_id, message.document.file_id, caption=message.caption or None)
        elif message.video:
            await bot.send_video(target_user_id, message.video.file_id, caption=message.caption or None)
        elif message.voice:
            await bot.send_voice(target_user_id, message.voice.file_id, caption=message.caption or None)
        elif message.audio:
            await bot.send_audio(target_user_id, message.audio.file_id, caption=message.caption or None)
        elif message.text:
            await bot.send_message(target_user_id, message.text)
        else:
            await message.answer("⚠️ نوع این پیام پشتیبانی نمی‌شود. لطفاً متن/عکس/فایل/ویدیو/صدا ارسال کنید.")
            return

        await message.answer(f"✅ با موفقیت برای کاربر `{target_user_id}` ارسال شد.")
    except Exception as e:
        logger.error(f"[ADMIN-RELAY] خطا در ارسال به {target_user_id}: {e}", exc_info=True)
        await message.answer(
            f"❌ خطا در ارسال به کاربر `{target_user_id}`:\n{e}\n\n"
            f"(ممکن است کاربر هرگز ربات را استارت نکرده یا آن را بلاک کرده باشد)"
        )

    await state.clear()


# ══════════════════════════════════════════════════════════════════════════
# ۲) /case — ارسال نتیجهٔ پرونده (با فاکتور و ورود خودکار به امضا)
# ══════════════════════════════════════════════════════════════════════════
SERVICE_LABELS = {
    "📄 لایحه": {"is_ezhharnameh": False, "service_type": None, "title": "لایحه"},
    "📋 اظهارنامه": {"is_ezhharnameh": True, "service_type": None, "title": "اظهارنامه"},
    "⚖️ دعاوی اعتراضی (تجدیدنظر)": {"is_ezhharnameh": False, "service_type": "TAJDID_NAZAR", "title": "دعاوی اعتراضی"},
    "🏦 چک": {"is_ezhharnameh": False, "service_type": "CHECK", "title": "دادخواست چک"},
}

case_service_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=k)] for k in SERVICE_LABELS.keys()] + [[KeyboardButton(text="/cancel")]],
    resize_keyboard=True
)

case_amount_choice_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="💰 بله، مبلغ وارد می‌کنم")],
        [KeyboardButton(text="⏭ خیر، فقط فایل را بفرست")],
    ],
    resize_keyboard=True
)


@admin_relay_router.message(F.text.startswith("/case"))
async def admin_case_command(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().lstrip("-").isdigit():
        await message.answer(
            "⚠️ فرمت صحیح:\n`/case <آیدی عددی کاربر>`\n\n"
            "مثال: `/case 123456789`"
        )
        return

    target_user_id = int(parts[1].strip())
    await state.update_data(_case_target=target_user_id)
    await message.answer(
        f"📁 ارسال نتیجهٔ پرونده برای کاربر `{target_user_id}`.\n\n"
        f"لطفاً نوع سرویس را انتخاب کنید:",
        reply_markup=case_service_kb)
    await state.set_state(AdminRelayStates.case_choose_service)


@admin_relay_router.message(AdminRelayStates.case_choose_service, F.text == "/cancel")
@admin_relay_router.message(AdminRelayStates.case_upload_pdf, F.text == "/cancel")
@admin_relay_router.message(AdminRelayStates.case_ask_amount_choice, F.text == "/cancel")
@admin_relay_router.message(AdminRelayStates.case_enter_amount, F.text == "/cancel")
@admin_relay_router.message(AdminRelayStates.case_enter_tracking, F.text == "/cancel")
async def admin_case_cancel(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    data = await state.get_data()
    tmp_path = data.get("_case_pdf_path")
    if tmp_path and os.path.exists(tmp_path):
        try:
            os.remove(tmp_path)
        except Exception:
            pass
    await state.clear()
    await message.answer("❌ لغو شد.")


@admin_relay_router.message(AdminRelayStates.case_choose_service)
async def admin_case_service_handler(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    text = message.text or ""
    if text not in SERVICE_LABELS:
        await message.answer("⚠️ لطفاً از دکمه‌های زیر انتخاب کنید:", reply_markup=case_service_kb)
        return

    await state.update_data(_case_service=text)
    await message.answer(
        f"✅ نوع سرویس: *{SERVICE_LABELS[text]['title']}*\n\n"
        f"لطفاً فایل *PDF* نتیجهٔ پرونده را ارسال کنید:",
        reply_markup=ReplyKeyboardRemove())
    await state.set_state(AdminRelayStates.case_upload_pdf)


@admin_relay_router.message(AdminRelayStates.case_upload_pdf, F.document)
async def admin_case_pdf_handler(message: Message, state: FSMContext, bot: Bot):
    if message.from_user.id != ADMIN_ID:
        return

    doc = message.document
    try:
        tmp_dir = tempfile.mkdtemp()
        tmp_path = os.path.join(tmp_dir, doc.file_name or "case_result.pdf")
        file_info = await bot.get_file(doc.file_id)
        await bot.download_file(file_info.file_path, tmp_path)
    except Exception as e:
        logger.error(f"[ADMIN-CASE] خطا در دانلود فایل: {e}", exc_info=True)
        await message.answer(f"❌ خطا در دانلود فایل:\n{e}")
        return

    await state.update_data(_case_pdf_path=tmp_path, _case_pdf_name=doc.file_name or "")
    await message.answer(
        "📎 فایل دریافت شد.\n\n"
        "آیا می‌خواهید مبلغی برای این پرونده فاکتور شود؟\n"
        "_(در صورت انتخاب «بله»، پس از پرداخت کاربر، به‌صورت خودکار وارد بخش امضا می‌شود — "
        "دقیقاً مثل ثبت خودکار موفق)_",
        reply_markup=case_amount_choice_kb)
    await state.set_state(AdminRelayStates.case_ask_amount_choice)


@admin_relay_router.message(AdminRelayStates.case_upload_pdf)
async def admin_case_pdf_fallback(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("⚠️ لطفاً فایل *PDF* را به‌صورت Document ارسال کنید (نه عکس).")


@admin_relay_router.message(AdminRelayStates.case_ask_amount_choice)
async def admin_case_amount_choice_handler(message: Message, state: FSMContext, bot: Bot):
    if message.from_user.id != ADMIN_ID:
        return
    text = message.text or ""

    if text == "⏭ خیر، فقط فایل را بفرست":
        await _finalize_case_without_invoice(message, state, bot)
        return

    if text == "💰 بله، مبلغ وارد می‌کنم":
        await message.answer(
            "💰 لطفاً مبلغ نهایی قابل‌پرداخت را به *ریال* وارد کنید:\n_(فقط عدد)_",
            reply_markup=ReplyKeyboardRemove())
        await state.set_state(AdminRelayStates.case_enter_amount)
        return

    await message.answer("⚠️ لطفاً یکی از گزینه‌های زیر را انتخاب کنید:", reply_markup=case_amount_choice_kb)


@admin_relay_router.message(AdminRelayStates.case_enter_amount)
async def admin_case_amount_handler(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    text = (message.text or "").strip()
    if not text.isdigit() or int(text) <= 0:
        await message.answer("⚠️ لطفاً فقط عدد مثبت (به ریال) ارسال کنید:")
        return

    await state.update_data(_case_amount=int(text))
    await message.answer(
        "🔢 کد پیگیری/بایگانی این پرونده را وارد کنید:\n"
        "_(اگر ندارید، عدد ۰ را بفرستید)_")
    await state.set_state(AdminRelayStates.case_enter_tracking)


@admin_relay_router.message(AdminRelayStates.case_enter_tracking)
async def admin_case_tracking_handler(message: Message, state: FSMContext, bot: Bot):
    if message.from_user.id != ADMIN_ID:
        return
    text = (message.text or "").strip()
    tracking_code = "" if text == "0" else text
    await state.update_data(_case_tracking=tracking_code)
    await _finalize_case_with_invoice(message, state, bot)


async def _finalize_case_without_invoice(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    target_user_id = data.get("_case_target")
    tmp_path = data.get("_case_pdf_path")
    service_label = data.get("_case_service", "")
    title = SERVICE_LABELS.get(service_label, {}).get("title", "پرونده")

    try:
        # ⚠️ از send_document_direct استفاده می‌کنیم (نه bot.send_document با
        # FSInputFile) — طبق یادداشت خود پروژه در bale_file_sender.py،
        # FSInputFile گاهی با API بله ناسازگار است.
        from bale_file_sender import send_document_direct
        ok = await send_document_direct(
            target_user_id, tmp_path,
            caption=f"📄 نتیجهٔ {title} شما ثبت شد.")
        if ok:
            await message.answer(f"✅ فایل بدون فاکتور برای کاربر `{target_user_id}` ارسال شد.")
        else:
            await message.answer(f"❌ ارسال فایل برای کاربر `{target_user_id}` ناموفق بود (جزئیات در لاگ سرور).")
    except Exception as e:
        logger.error(f"[ADMIN-CASE] خطا در ارسال بدون فاکتور: {e}", exc_info=True)
        await message.answer(f"❌ خطا در ارسال:\n{e}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        await state.clear()


async def _finalize_case_with_invoice(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    target_user_id = data.get("_case_target")
    tmp_path = data.get("_case_pdf_path")
    service_label = data.get("_case_service", "")
    amount = data.get("_case_amount", 0)
    tracking_code = data.get("_case_tracking", "")
    cfg = SERVICE_LABELS.get(service_label, {})
    title = cfg.get("title", "پرونده")

    try:
        # همان تابعی که خود ربات هم برای ثبت خودکار موفق استفاده می‌کند —
        # فاکتور می‌فرستد، منتظر پرداخت می‌ماند، و بعد از پرداخت خودکار وارد
        # ناوبری امضا (بخش مشترک لایحه/اظهارنامه/تجدیدنظر/چک) می‌شود.
        from lavayeh_handlers import send_lavayeh_result
        await send_lavayeh_result(
            bot, target_user_id, tmp_path, amount,
            tracking_code=tracking_code,
            national_ids="",
            lavayeh_title=f"{title} (ثبت دستی توسط مدیر)",
            lavayeh_province="",
            lavayeh_row_number=1,
            lavayeh_persons=[],
            skip_fee_calc=True,
            is_ezhharnameh=cfg.get("is_ezhharnameh", False),
            service_type=cfg.get("service_type"))
        await message.answer(
            f"✅ فاکتور {amount:,} ریالی برای کاربر `{target_user_id}` ارسال شد.\n"
            f"پس از پرداخت، کاربر به‌صورت خودکار وارد بخش امضا می‌شود."
        )
    except Exception as e:
        logger.error(f"[ADMIN-CASE] خطا در ارسال فاکتور: {e}", exc_info=True)
        await message.answer(f"❌ خطا در ارسال فاکتور:\n{e}")
        # در صورت خطا، فایل توسط send_lavayeh_result حذف نشده — خودمان پاک می‌کنیم
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
    finally:
        await state.clear()

