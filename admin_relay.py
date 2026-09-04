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
import datetime
import json
import logging
import os
import tempfile

import aiohttp

from aiogram import Bot, Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

from config import ADMIN_ID, ADMIN_API_BASE, BALE_API_BASE, BOT_TOKEN, BALE_WALLET_TOKEN

logger = logging.getLogger(__name__)

admin_relay_router = Router()


class AdminRelayStates(StatesGroup):
    waiting_for_content = State()
    # ⭐ فلوی «هزینهٔ ارسال پیام مدیر» (/send): بعد از ارسال محتوا، فاکتور اختیاری
    send_ask_fee = State()
    send_fee_enter_amount = State()
    send_fee_enter_tracking = State()
    case_choose_service = State()
    case_upload_pdf = State()
    case_ask_amount_choice = State()
    case_enter_amount = State()
    case_enter_tracking = State()
    # ⭐ فلوی «هزینه دستی مدیر» (/fee): مبلغ ← فاکتور ← پرداخت خودکار ← امضا
    fee_choose_service = State()
    fee_enter_amount = State()
    fee_enter_tracking = State()
    fee_check_menu = State()
    fee_tn_casetype = State()


# ══════════════════════════════════════════════════════════════════════════
# ۱) /send — ارسال خام + ⭐ بخش هزینه (فاکتور اختیاری پس از ارسال)
# ⭐ کیبورد سؤال هزینه پس از ارسال محتوا به کاربر:
send_fee_choice_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="💰 بله، فاکتور می‌فرستم")],
        [KeyboardButton(text="⏭ خیر، بدون هزینه")],
    ],
    resize_keyboard=True
)
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
            "💰 *بخش هزینه:* پس از ارسال محتوا، می‌توانید برای همین ارسال فاکتور"
            "(کیف پول بله) برای کاربر صادر کنید.\n\n"
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
        f"💰 پس از ارسال، امکان صدور فاکتور هزینه برای این ارسال وجود دارد.\n"
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

        await message.answer(
            f"✅ با موفقیت برای کاربر `{target_user_id}` ارسال شد.\n\n"
            f"💰 آیا برای این ارسال هزینه‌ای از کاربر دریافت شود؟",
            reply_markup=send_fee_choice_kb)
        await state.set_state(AdminRelayStates.send_ask_fee)
    except Exception as e:
        logger.error(f"[ADMIN-RELAY] خطا در ارسال به {target_user_id}: {e}", exc_info=True)
        await message.answer(
            f"❌ خطا در ارسال به کاربر `{target_user_id}`:\n{e}\n\n"
            f"(ممکن است کاربر هرگز ربات را استارت نکرده یا آن را بلاک کرده باشد)"
        )
        await state.clear()


# ── ⭐ بخش هزینهٔ /send: انتخاب ← مبلغ ← کد پیگیری ← فاکتور ─────────────

@admin_relay_router.message(AdminRelayStates.send_ask_fee, F.text == "⏭ خیر، بدون هزینه")
async def admin_send_fee_skip_handler(message: Message, state: FSMContext):
    """مدیر هزینه نمی‌خواهد — پایان فلوی /send (رفتار قبلی)."""
    if message.from_user.id != ADMIN_ID:
        return
    await state.clear()
    await message.answer(
        "✅ ارسال بدون هزینه انجام و عملیات تمام شد.",
        reply_markup=ReplyKeyboardRemove())


@admin_relay_router.message(AdminRelayStates.send_ask_fee, F.text == "💰 بله، فاکتور می‌فرستم")
async def admin_send_fee_yes_handler(message: Message, state: FSMContext):
    """مدیر می‌خواهد برای این ارسال فاکتور صادر کند — دریافت مبلغ."""
    if message.from_user.id != ADMIN_ID:
        return
    data = await state.get_data()
    if not data.get("_admin_relay_target"):
        await state.clear()
        await message.answer("⚠️ خطا: آیدی مقصد یافت نشد. دوباره با /send شروع کنید.")
        return
    await message.answer(
        "💰 لطفاً *مبلغ* را به *ریال* وارد کنید:\n"
        "_(فقط عدد — مثال: `500000`)_",
        reply_markup=ReplyKeyboardRemove())
    await state.set_state(AdminRelayStates.send_fee_enter_amount)


@admin_relay_router.message(AdminRelayStates.send_ask_fee)
async def admin_send_fee_choice_fallback(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer(
        "⚠️ لطفاً یکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=send_fee_choice_kb)


@admin_relay_router.message(AdminRelayStates.send_fee_enter_amount)
async def admin_send_fee_amount_handler(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    text = (message.text or "").strip().translate(
        str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    if not text.isdigit() or int(text) <= 0:
        await message.answer("⚠️ لطفاً فقط عدد مثبت (به ریال) ارسال کنید:")
        return

    await state.update_data(_send_fee_amount=int(text))
    await message.answer(
        "🔢 کد پیگیری/بایگانی این ارسال را وارد کنید:\n"
        "_(اگر ندارید، عدد ۰ را بفرستید)_")
    await state.set_state(AdminRelayStates.send_fee_enter_tracking)


@admin_relay_router.message(AdminRelayStates.send_fee_enter_tracking)
async def admin_send_fee_tracking_handler(message: Message, state: FSMContext, bot: Bot):
    if message.from_user.id != ADMIN_ID:
        return
    text = (message.text or "").strip()
    tracking_code = "" if text == "0" else text
    await state.update_data(_send_fee_tracking=tracking_code)
    await _finalize_send_fee_invoice(message, state)


async def _finalize_send_fee_invoice(message: Message, state: FSMContext):
    """صدور و ارسال فاکتور کیف پول بله برای هزینهٔ ارسال پیام مدیر (/send).

    پس از پرداخت خودکار توسط کاربر، هندلر admin_fee_successful_payment با
    service_type=ADMIN_SEND ادامه می‌دهد (بدون ناوبری امضا — فقط ثبت پنل،
    لاگ شیت و اطلاع به مدیر).
    """
    import runtime_state
    from states import Form

    data = await state.get_data()
    target_user_id = data.get("_admin_relay_target")
    amount = data.get("_send_fee_amount", 0)
    tracking_code = data.get("_send_fee_tracking", "")

    try:
        invoice_payload = json.dumps({"type": "admin_fee", "uid": target_user_id, "source": "send"})
        url = f"{BALE_API_BASE.rstrip('/')}/bot{BOT_TOKEN}/sendInvoice"
        invoice_data = {
            "chat_id": target_user_id,
            "title": "فاکتور ارسال پیام",
            "description": (
                f"هزینه دریافت پیام/فایل از مدیریت\n"
                f"مبلغ: {amount // 10:,} تومان ({amount:,} ریال)"
            ),
            "payload": invoice_payload,
            "provider_token": BALE_WALLET_TOKEN,
            "currency": "IRR",
            "prices": [{"label": "ارسال پیام", "amount": amount}],
        }
        logger.info(
            f"[ADMIN-SEND-FEE] ارسال sendInvoice به chat_id={target_user_id}, "
            f"مبلغ={amount:,} ریال, source=send")
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
            async with session.post(url, json=invoice_data, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                result = await resp.json()
                if not result.get("ok"):
                    logger.error(f"[ADMIN-SEND-FEE] خطای sendInvoice: {result}")
                    await message.answer(
                        f"❌ خطا در ارسال فاکتور برای کاربر `{target_user_id}`:\n"
                        f"`{result.get('description', 'نامشخص')}`\n\n"
                        f"(مطمئن شوید کاربر ربات را استارت کرده باشد)")
                    await state.clear()
                    return
    except Exception as e:
        logger.error(f"[ADMIN-SEND-FEE] خطا در ارسال فاکتور: {e}", exc_info=True)
        await message.answer(f"❌ خطا در ارسال فاکتور:\n{e}")
        await state.clear()
        return

    # ذخیره context پرداخت برای هندلر successful_payment (مثل /fee)
    runtime_state.pending_admin_fee_payments[target_user_id] = {
        "invoice_time": datetime.datetime.now(),
        "final_fee": amount,
        "service_type": "ADMIN_SEND",
        "tracking_code": tracking_code,
        "sign_menu_path": None,
        "admin_id": ADMIN_ID,
        "source": "send",
    }

    # ست کردن state کاربر (نه ادمین) به حالت انتظار پرداخت فاکتور مدیر
    try:
        user_state = runtime_state.dp.fsm.resolve_context(message.bot, target_user_id, target_user_id)
        await user_state.set_state(Form.admin_fee_waiting_payment)
    except Exception as e:
        logger.warning(f"[ADMIN-SEND-FEE] ست کردن state کاربر {target_user_id} ناموفق بود: {e}")

    await message.answer(
        f"✅ فاکتور *{amount:,} ریالی* هزینهٔ ارسال پیام برای کاربر `{target_user_id}` ارسال شد.\n\n"
        f"💳 پس از پرداخت خودکار توسط کاربر، پرداخت ثبت می‌شود و به شما اطلاع داده می‌شود."
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


@admin_relay_router.message(AdminRelayStates.send_ask_fee, F.text == "/cancel")
@admin_relay_router.message(AdminRelayStates.send_fee_enter_amount, F.text == "/cancel")
@admin_relay_router.message(AdminRelayStates.send_fee_enter_tracking, F.text == "/cancel")
@admin_relay_router.message(AdminRelayStates.case_choose_service, F.text == "/cancel")
@admin_relay_router.message(AdminRelayStates.case_upload_pdf, F.text == "/cancel")
@admin_relay_router.message(AdminRelayStates.case_ask_amount_choice, F.text == "/cancel")
@admin_relay_router.message(AdminRelayStates.case_enter_amount, F.text == "/cancel")
@admin_relay_router.message(AdminRelayStates.case_enter_tracking, F.text == "/cancel")
@admin_relay_router.message(AdminRelayStates.fee_choose_service, F.text == "/cancel")
@admin_relay_router.message(AdminRelayStates.fee_enter_amount, F.text == "/cancel")
@admin_relay_router.message(AdminRelayStates.fee_enter_tracking, F.text == "/cancel")
@admin_relay_router.message(AdminRelayStates.fee_check_menu, F.text == "/cancel")
@admin_relay_router.message(AdminRelayStates.fee_tn_casetype, F.text == "/cancel")
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


# ══════════════════════════════════════════════════════════════════════════
# ۳) ⭐ /fee — وارد کردن هزینه توسط مدیر ← فاکتور بله ← پرداخت خودکار ←
#     ناوبری امضا (به‌جز استعلام که مرحله امضا ندارد)
# ══════════════════════════════════════════════════════════════════════════
# مراحل:
#   /fee <آیدی کاربر> ← انتخاب نوع سرویس ← وارد کردن مبلغ (ریال) ←
#   وارد کردن کد پیگیری (یا ۰) ← [فقط چک: انتخاب مسیر امضا] ←
#   [فقط تجدیدنظر: انتخاب نوع دعوی] ← ارسال فاکتور بله برای کاربر ←
#   پس از پرداخت خودکار توسط کاربر:
#     - استعلام → فقط ثبت پرداخت (بدون امضا)
#     - اظهارنامه → فلوی امضای اظهارنامه
#     - بقیه → فلوی امضای لایحه با مسیر منوی مناسب (ناوبری امضا)
FEE_SERVICE_LABELS = {
    "📄 لایحه": {"service_type": "LAVAYEH", "label": "لایحه", "is_ezhharnameh": False, "ask_menu": None},
    "📋 اظهارنامه": {"service_type": "EZHHARNAMEH", "label": "اظهارنامه", "is_ezhharnameh": True, "ask_menu": None},
    "⚖️ دعاوی اعتراضی (تجدیدنظر)": {"service_type": "TAJDID_NAZAR", "label": "دعاوی اعتراضی", "is_ezhharnameh": False, "ask_menu": "tn"},
    "🏦 چک": {"service_type": "CHECK", "label": "دادخواست چک", "is_ezhharnameh": False, "ask_menu": "check"},
    "🔍 استعلام (پس از پرداخت، امضا ندارد)": {"service_type": "INQUIRY", "label": "استعلام", "is_ezhharnameh": False, "ask_menu": None},
}

# ⭐ برچسب سرویس فاکتور هزینهٔ ارسال پیام مدیر (/send) — جدا از FEE_SERVICE_LABELS
# تا به‌عنوان دکمه در کیبورد /fee ظاهر نشود؛ فقط برای label lookup استفاده می‌شود.
ADMIN_SEND_SERVICE_LABEL = "ارسال پیام مدیریت"

# مسیر منوی سامانه برای امضای چک (مطابق check_scenario.py)
FEE_CHECK_MENU_PATHS = {
    "⚖️ دادخواست بدوی (چک بیش از ۱ میلیارد ریال)": ["ارایه و پیگیری دادخواست", "دادخواست بدوی"],
    "🏛 دعاوی دادگاههای صلح (چک تا ۱ میلیارد ریال)": ["دعاوی دادگاههای صلح", "دعاوی حقوقی"],
}

# انواع دعاوی اعتراضی (مطابق tn_case_type_kb در keyboards.py)
FEE_TN_CASE_TYPES = [
    "تجدیدنظرخواهی", "واخواهی", "فرجام خواهی",
    "اعاده دادرسی مدنی", "اعاده دادرسی کیفری",
    "اعتراض ثالث", "اعتراض به قرار دادسرا",
]

fee_service_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=k)] for k in FEE_SERVICE_LABELS.keys()] + [[KeyboardButton(text="/cancel")]],
    resize_keyboard=True
)

fee_check_menu_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=k)] for k in FEE_CHECK_MENU_PATHS.keys()] + [[KeyboardButton(text="/cancel")]],
    resize_keyboard=True
)

fee_tn_casetype_kb = ReplyKeyboardMarkup(
    keyboard=(
        [[KeyboardButton(text=t)] for t in FEE_TN_CASE_TYPES[:3]] +
        [[KeyboardButton(text=t)] for t in FEE_TN_CASE_TYPES[3:5]] +
        [[KeyboardButton(text=FEE_TN_CASE_TYPES[5])], [KeyboardButton(text=FEE_TN_CASE_TYPES[6])]] +
        [[KeyboardButton(text="/cancel")]]
    ),
    resize_keyboard=True
)


@admin_relay_router.message(F.text.startswith("/fee"))
async def admin_fee_command(message: Message, state: FSMContext):
    """شروع فلوی هزینه دستی: /fee <آیدی عددی کاربر>"""
    if message.from_user.id != ADMIN_ID:
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().lstrip("-").isdigit():
        await message.answer(
            "⚠️ فرمت صحیح:\n`/fee <آیدی عددی کاربر>`\n\n"
            "مثال: `/fee 123456789`\n\n"
            "بعد از این کامند:\n"
            "۱️⃣ نوع سرویس را انتخاب می‌کنید (لایحه/اظهارنامه/تجدیدنظر/چک/استعلام)\n"
            "۲️⃣ مبلغ را به ریال وارد می‌کنید\n"
            "۳️⃣ کد پیگیری را وارد می‌کنید (یا ۰)\n\n"
            "سپس فاکتور بله طبق مبلغ برای کاربر ارسال می‌شود و پس از پرداخت خودکار، "
            "به‌جز استعلام (که امضا ندارد)، ناوبری امضا برای کاربر آغاز می‌شود."
        )
        return

    target_user_id = int(parts[1].strip())
    await state.update_data(_fee_target=target_user_id)
    await message.answer(
        f"💰 ثبت هزینه دستی برای کاربر `{target_user_id}`\n\n"
        f"لطفاً *نوع سرویس* را انتخاب کنید:",
        reply_markup=fee_service_kb)
    await state.set_state(AdminRelayStates.fee_choose_service)


@admin_relay_router.message(AdminRelayStates.fee_choose_service)
async def admin_fee_service_handler(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    text = message.text or ""
    if text not in FEE_SERVICE_LABELS:
        await message.answer("⚠️ لطفاً از دکمه‌های زیر انتخاب کنید:", reply_markup=fee_service_kb)
        return

    cfg = FEE_SERVICE_LABELS[text]
    await state.update_data(_fee_service=text, _fee_cfg=cfg)
    await message.answer(
        f"✅ نوع سرویس: *{cfg['label']}*\n\n"
        f"💰 لطفاً *مبلغ* را به *ریال* وارد کنید:\n_(فقط عدد — مثال: `1990000`)_",
        reply_markup=ReplyKeyboardRemove())
    await state.set_state(AdminRelayStates.fee_enter_amount)


@admin_relay_router.message(AdminRelayStates.fee_enter_amount)
async def admin_fee_amount_handler(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    text = (message.text or "").strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    if not text.isdigit() or int(text) <= 0:
        await message.answer("⚠️ لطفاً فقط عدد مثبت (به ریال) ارسال کنید:")
        return

    await state.update_data(_fee_amount=int(text))
    await message.answer(
        "🔢 کد پیگیری/بایگانی این پرونده را وارد کنید:\n"
        "_(این کد برای ناوبری امضا در سامانه استفاده می‌شود؛ اگر ندارید عدد ۰ را بفرستید)_")
    await state.set_state(AdminRelayStates.fee_enter_tracking)


@admin_relay_router.message(AdminRelayStates.fee_enter_tracking)
async def admin_fee_tracking_handler(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    text = (message.text or "").strip()
    tracking_code = "" if text == "0" else text
    await state.update_data(_fee_tracking=tracking_code)

    data = await state.get_data()
    cfg = data.get("_fee_cfg", {})

    # فقط چک و تجدیدنظر به سوال «مسیر امضا» نیاز دارند
    if cfg.get("ask_menu") == "check":
        await message.answer(
            "🏦 مسیر سامانه برای *امضای این چک* کدام است؟",
            reply_markup=fee_check_menu_kb)
        await state.set_state(AdminRelayStates.fee_check_menu)
        return
    if cfg.get("ask_menu") == "tn":
        await message.answer(
            "⚖️ نوع *دعوی اعتراضی* این پرونده کدام است؟\n"
            "_(برای مسیر ناوبری امضا در سامانه لازم است)_",
            reply_markup=fee_tn_casetype_kb)
        await state.set_state(AdminRelayStates.fee_tn_casetype)
        return

    await _finalize_admin_fee_invoice(message, state)


@admin_relay_router.message(AdminRelayStates.fee_check_menu)
async def admin_fee_check_menu_handler(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    text = message.text or ""
    if text not in FEE_CHECK_MENU_PATHS:
        await message.answer("⚠️ لطفاً یکی از گزینه‌های زیر را انتخاب کنید:", reply_markup=fee_check_menu_kb)
        return
    await state.update_data(_fee_sign_menu_path=FEE_CHECK_MENU_PATHS[text])
    await _finalize_admin_fee_invoice(message, state)


@admin_relay_router.message(AdminRelayStates.fee_tn_casetype)
async def admin_fee_tn_casetype_handler(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    text = message.text or ""
    if text not in FEE_TN_CASE_TYPES:
        await message.answer("⚠️ لطفاً یکی از انواع دعوی را انتخاب کنید:", reply_markup=fee_tn_casetype_kb)
        return
    # مطابق tajdid_nazar_handlers.py: مسیر امضای تجدیدنظر = [نوع دعوی]
    await state.update_data(_fee_sign_menu_path=[text])
    await _finalize_admin_fee_invoice(message, state)


async def _finalize_admin_fee_invoice(message: Message, state: FSMContext):
    """ساخت و ارسال فاکتور بله طبق مبلغ واردشده توسط مدیر + آماده‌سازی فلوی پس از پرداخت."""
    import runtime_state
    from states import Form

    data = await state.get_data()
    target_user_id = data.get("_fee_target")
    cfg = data.get("_fee_cfg", {})
    amount = data.get("_fee_amount", 0)
    tracking_code = data.get("_fee_tracking", "")
    sign_menu_path = data.get("_fee_sign_menu_path")
    svc = cfg.get("service_type", "LAVAYEH")
    label = cfg.get("label", "سرویس")

    try:
        invoice_payload = json.dumps({"type": "admin_fee", "uid": target_user_id})
        url = f"{BALE_API_BASE.rstrip('/')}/bot{BOT_TOKEN}/sendInvoice"
        invoice_data = {
            "chat_id": target_user_id,
            "title": f"فاکتور {label}",
            "description": (
                f"هزینه خدمات {label} (ثبت توسط مدیریت)\n"
                f"مبلغ: {amount // 10:,} تومان ({amount:,} ریال)"
            ),
            "payload": invoice_payload,
            "provider_token": BALE_WALLET_TOKEN,
            "currency": "IRR",
            "prices": [{"label": label, "amount": amount}],
        }
        logger.info(f"[ADMIN-FEE] ارسال sendInvoice به chat_id={target_user_id}, مبلغ={amount:,} ریال, سرویس={svc}")
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
            async with session.post(url, json=invoice_data, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                result = await resp.json()
                if not result.get("ok"):
                    logger.error(f"[ADMIN-FEE] خطای sendInvoice: {result}")
                    await message.answer(
                        f"❌ خطا در ارسال فاکتور برای کاربر `{target_user_id}`:\n"
                        f"`{result.get('description', 'نامشخص')}`\n\n"
                        f"(مطمئن شوید کاربر ربات را استارت کرده باشد)")
                    await state.clear()
                    return
    except Exception as e:
        logger.error(f"[ADMIN-FEE] خطا در ارسال فاکتور: {e}", exc_info=True)
        await message.answer(f"❌ خطا در ارسال فاکتور:\n{e}")
        await state.clear()
        return

    # ذخیره context پرداخت برای هندلر successful_payment
    runtime_state.pending_admin_fee_payments[target_user_id] = {
        "invoice_time": datetime.datetime.now(),
        "final_fee": amount,
        "service_type": svc,
        "tracking_code": tracking_code,
        "sign_menu_path": sign_menu_path,
        "admin_id": ADMIN_ID,
    }

    # ست کردن state کاربر (نه ادمین) به حالت انتظار پرداخت فاکتور مدیر
    try:
        user_state = runtime_state.dp.fsm.resolve_context(message.bot, target_user_id, target_user_id)
        await user_state.set_state(Form.admin_fee_waiting_payment)
    except Exception as e:
        logger.warning(f"[ADMIN-FEE] ست کردن state کاربر {target_user_id} ناموفق بود: {e}")

    await message.answer(
        f"✅ فاکتور *{amount:,} ریالی* ({label}) برای کاربر `{target_user_id}` ارسال شد.\n\n"
        + (
            "💳 پس از پرداخت خودکار، پرداخت ثبت می‌شود و کاربر به روند استعلام ادامه می‌دهد (امضا ندارد)."
            if svc == "INQUIRY" else
            "💳 پس از پرداخت خودکار، ناوبری امضا برای کاربر آغاز می‌شود."
        )
    )
    await state.clear()


async def admin_fee_successful_payment(message: Message, state: FSMContext, bot: Bot):
    """پرداخت موفق فاکتور «هزینه دستی مدیر» — تشخیص خودکار توسط بله.

    پس از پرداخت:
      - ⭐ ارسال پیام مدیریت (ADMIN_SEND) → فقط ثبت پرداخت + اطلاع مدیر (امضا ندارد)
      - استعلام (INQUIRY) → فقط ثبت پرداخت (امضا ندارد)
      - اظهارنامه → فلوی امضای اظهارنامه
      - بقیه (لایحه/چک/تجدیدنظر) → فلوی امضای لایحه با مسیر منوی مناسب
        (ناوبری امضا توسط navigate_to_sign_page انجام می‌شود)
    """
    import runtime_state
    from states import Form
    from sheets import log_event

    user_id = message.from_user.id
    pending = runtime_state.pending_admin_fee_payments.get(user_id)
    if not pending:
        await message.answer("⚠️ فاکتور فعالی برای شما ثبت نشده است.")
        await state.clear()
        return

    payment = message.successful_payment
    svc = pending.get("service_type", "LAVAYEH")
    amount = pending.get("final_fee", 0)
    tracking_code = pending.get("tracking_code", "")
    sign_menu_path = pending.get("sign_menu_path")
    if svc == "ADMIN_SEND":
        label = ADMIN_SEND_SERVICE_LABEL
    else:
        label = next((c["label"] for c in FEE_SERVICE_LABELS.values() if c["service_type"] == svc), "سرویس")

    # ۱) تایید به کاربر
    await message.answer(
        f"✅ *پرداخت شما ثبت شد!*\n\n"
        f"📄 نوع: *{label}*\n"
        f"💰 مبلغ: *{amount // 10:,} تومان* ({amount:,} ریال)\n\n"
        + (
            "✅ از پرداخت شما متشکریم. هیچ اقدام دیگری از سمت شما لازم نیست."
            if svc == "ADMIN_SEND" else
            "🔔 مراحل بعدی به زودی ارسال می‌شود."
        ),
        reply_markup=ReplyKeyboardRemove()
    )

    # ۲) لاگ رویداد
    try:
        await log_event(
            "پرداخت", label, message.from_user.full_name, user_id,
            tracking_code=tracking_code,
            doc_name=label,
            payment_status=(
                "پرداخت شده (فاکتور ارسال پیام مدیر)"
                if svc == "ADMIN_SEND" else
                "پرداخت شده (فاکتور دستی مدیر)"
            ),
            note=f"مبلغ: {amount:,} ریال | payment_id: {payment.telegram_payment_charge_id}"
        )
    except Exception as e:
        logger.warning(f"[ADMIN-FEE] خطا در log_event: {e}")

    # ۳) اطلاع به مدیر
    try:
        await bot.send_message(
            ADMIN_ID,
            f"💰 پرداخت فاکتور دستی ({label}):\n\n"
            f"👤 کاربر: {message.from_user.full_name} ({user_id})\n"
            f"💰 مبلغ: {amount // 10:,} تومان ({amount:,} ریال)\n"
            f"🔢 کد پیگیری: {tracking_code or '—'}\n"
            f"⏱ زمان: {datetime.datetime.now().strftime('%Y/%m/%d %H:%M')}\n"
            f"🎫 payment_id: {payment.telegram_payment_charge_id}"
        )
    except Exception as e:
        logger.error(f"[ADMIN-FEE] خطا در اطلاع‌رسانی به ادمین: {e}", exc_info=True)

    # ۴) ثبت در پنل ادمین
    try:
        from panel_sync import upsert_case_to_panel
        await upsert_case_to_panel(
            bale_user_id=user_id,
            full_name=message.from_user.full_name,
            service_type=svc,
            status=(
                "COMPLETED" if svc in ("INQUIRY", "ADMIN_SEND") else "PROCESSING"
            ),
            tracking_code=tracking_code or None,
            document_category=label,
            # ⭐ amount ریال است؛ فیلد fee پنل به «تومان» است (مثل استعلام‌ها)
            fee=amount // 10,
            fee_status="PAID",
            result_summary=(
                "پرداخت فاکتور هزینهٔ ارسال پیام مدیر انجام شد"
                if svc == "ADMIN_SEND" else
                "پرداخت فاکتور دستی مدیر انجام شد؛ استعلام بدون امضا"
                if svc == "INQUIRY" else
                "پرداخت فاکتور دستی مدیر انجام شد؛ در انتظار امضای الکترونیک"
            ),
        )
    except Exception as e:
        logger.warning(f"[ADMIN-FEE] خطا در ثبت پرونده در پنل: {e}")

    runtime_state.pending_admin_fee_payments.pop(user_id, None)

    # ۵) ادامه روند — به‌جز استعلام و ارسال پیام مدیریت که امضا ندارند
    if svc == "ADMIN_SEND":
        # ⭐ هزینهٔ ارسال پیام مدیر — پیام/فایل قبلاً ارسال شده؛ فقط ثبت نهایی
        await state.clear()
        return

    if svc == "INQUIRY":
        await bot.send_message(
            user_id,
            "✅ پرداخت شما ثبت شد.\n\n"
            "🔎 روند استعلام شما توسط مدیریت ادامه داده می‌شود و نتیجه به‌زودی ارسال می‌گردد."
        )
        try:
            await bot.send_message(
                ADMIN_ID,
                f"ℹ️ فاکتور دستی استعلام کاربر {user_id} پرداخت شد — استعلام امضا ندارد؛ "
                f"نتیجه را با /send {user_id} ارسال کنید."
            )
        except Exception:
            pass
        await state.clear()
        return

    if svc == "EZHHARNAMEH":
        # فلوی امضای اظهارنامه — دقیقاً مثل بعد از پرداخت خودکار اظهارنامه
        runtime_state.pending_ezhhar_sign[user_id] = {
            "tracking_code": tracking_code,
            "is_ezhharnameh": True,
            "service_type": svc,
            "sign_persons": [],
            "persons_awaiting_sign": [],
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
            "هر موقع آمادگی دارید که کد امضا ارسال شود، گزینه زیر را انتخاب کنید:",
            reply_markup=ezhhar_sign_ready_kb)
        await state.set_state(Form.ezhhar_sign_ready)
        return

    # لایحه / چک / تجدیدنظر → فلوی امضای لایحه (ناوبری امضا با sign_menu_path)
    runtime_state.pending_lavayeh_sign[user_id] = {
        "tracking_code": tracking_code,
        "lavayeh_title": label,
        "province": "",
        "row_number": 1,
        "persons": [],
        "service_type": svc,
        "sign_menu_path": sign_menu_path,
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
    from keyboards import lavayeh_sign_ready_kb
    await bot.send_message(
        user_id,
        "🖊 *مرحله اخذ امضای الکترونیک:*\n\n"
        "هر موقع آمادگی دارید که کد امضا ارسال شود، گزینه زیر را انتخاب کنید:",
        reply_markup=lavayeh_sign_ready_kb)
    await state.set_state(Form.lavayeh_sign_ready)


# ══════════════════════════════════════════════════════════════════════════
# ۴) ⭐ پیام پنل ادمین — پرداخت موفق فاکتور {"type": "panel_message", "mid": ...}
# ══════════════════════════════════════════════════════════════════════════

# برچسب انواع سند «پیام پنل» — هماهنگ با src/lib/service-types.ts در پنل ادمین
PANEL_MESSAGE_SERVICE_LABELS = {
    "LAVAYEH": "لایحه",
    "EZHHARNAMEH": "اظهارنامه",
    "TAJDID_NAZAR": "تجدیدنظرخواهی",
    "VAKHAVI": "واخواهی",
    "FARQAM": "فرجام‌خواهی",
    "DADKHAST_BEDAVI": "دادخواست بدوی",
    "SOHL": "دعاوی صلح",
    "CHECK_BEDAVI": "چک (دادخواست بدوی)",
    "CHECK_SOHL": "چک (دعاوی صلح)",
    "INQUIRY": "استعلام",
}

# سرویس‌هایی که پس از پرداخت «امضا ندارند» — فقط ارسال پیام/فایل
PANEL_MESSAGE_NO_SIGN_SERVICES = {"", "NONE", "ADMIN_SEND", "INQUIRY"}


async def panel_message_successful_payment(message: Message, state: FSMContext, bot: Bot):
    """پرداخت موفق فاکتور «پیام مدیر از پنل ادمین».

    payload فاکتور: {"type": "panel_message", "mid": "<messageId>"}

    این هندلر توسط successful_payment_handler و global_successful_payment_handler
    در handlers.py صدا زده می‌شود (مستقل از state فعلی کاربر — چون فاکتور از
    پنل ارسال شده و به FSM ربات وصل نیست).

    کارها:
      ۱) POST به پنل: {ADMIN_API_BASE}/admin/bot-messages/{mid}/paid
         → پنل costStatus را PAID می‌کند و «متن + فایل پیام» را برای کاربر
           ارسال می‌کند (رفع باگ: قبلاً فقط فاکتور می‌رفت و پس از پرداخت
           هیچ‌چیز ارسال نمی‌شد، چون این تابع اصلاً وجود نداشت و import
           در handlers.py با ImportError شکست می‌خورد).
      ۲) اگر مدیر برای پیام «نوع سند» انتخاب کرده باشد (لایحه/واخواهی/
         تجدیدنظرخواهی/دادخواست بدوی/صلح/اظهارنامه/چک/...) → شروع خودکار
         «روند درج امضا» برای همان نوع سند — دقیقاً مثل /fee.
      ۳) لاگ شیت + اطلاع‌رسانی به مدیر.
    """
    import asyncio
    import runtime_state
    from states import Form
    from sheets import log_event

    user_id = message.from_user.id
    payment = message.successful_payment
    payment_id = str(getattr(payment, "telegram_payment_charge_id", "") or "")
    amount_rial = int(getattr(payment, "total_amount", 0) or 0)

    try:
        _pl = json.loads(getattr(payment, "invoice_payload", "") or "{}")
    except Exception:
        _pl = {}
    mid = str(_pl.get("mid") or "").strip()

    if not mid:
        logger.error(f"[PANEL-MSG-PAY] invoice_payload بدون mid است: {_pl}")
        await message.answer(
            "✅ پرداخت شما ثبت شد.\n\n"
            "⚠️ اما شناسهٔ پیام مدیریت در فاکتور یافت نشد؛ لطفاً با پشتیبانی در تماس باشید.",
            reply_markup=ReplyKeyboardRemove())
        try:
            await bot.send_message(
                ADMIN_ID,
                f"⚠️ فاکتور پیام پنل با payload نامعتبر پرداخت شد!\n\n"
                f"👤 کاربر: {message.from_user.full_name} ({user_id})\n"
                f"💰 مبلغ: {amount_rial:,} ریال\n"
                f"🎫 payment_id: {payment_id}")
        except Exception:
            pass
        await state.clear()
        return

    # ── ۱) اطلاع به پنل: پرداخت انجام شد → پنل پیام/فایل را ارسال می‌کند ──
    # ۳ تلاش با تاخیر (پنل ممکن است موقتاً در دسترس نباشد؛ پیام/فایل فقط
    # در DB پنل است، پس retry تا کاربر پیامش را از دست ندهد ضروری است.)
    url = f"{ADMIN_API_BASE.rstrip('/')}/admin/bot-messages/{mid}/paid"
    panel_ok = False
    panel_msg_info: dict = {}
    last_err = ""
    for attempt in range(1, 4):
        try:
            async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
                async with session.post(
                    url,
                    json={"paymentId": payment_id},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        panel_ok = bool(result.get("ok"))
                        panel_msg_info = result.get("message") or {}
                        if panel_ok:
                            break
                        last_err = "پاسخ ok=false از پنل"
                    else:
                        body_text = (await resp.text())[:300]
                        last_err = f"HTTP {resp.status}: {body_text}"
        except Exception as e:
            last_err = str(e)
        if attempt < 3:
            await asyncio.sleep(attempt)

    if not panel_ok:
        logger.error(
            f"[PANEL-MSG-PAY] خطا در تماس با پنل پس از ۳ تلاش ({url}): {last_err}")

    # اطلاعات نوع سند از پاسخ پنل
    svc = str(panel_msg_info.get("serviceType") or "").strip()
    sign_menu_path = None
    try:
        _smp = panel_msg_info.get("signMenuPath")
        if _smp:
            _parsed = json.loads(_smp)
            if isinstance(_parsed, list):
                sign_menu_path = _parsed
    except Exception:
        sign_menu_path = None
    tracking_code = str(panel_msg_info.get("trackingCode") or "").strip()
    doc_label = PANEL_MESSAGE_SERVICE_LABELS.get(svc, "")
    has_sign = svc not in PANEL_MESSAGE_NO_SIGN_SERVICES

    # ── ۲) تایید پرداخت به کاربر ──
    if panel_ok:
        await message.answer(
            "✅ پرداخت شما ثبت شد!\n\n"
            f"💰 مبلغ: {amount_rial // 10:,} تومان"
            + (f"\n📄 نوع سند: {doc_label}" if doc_label else "")
            + "\n\n📨 پیام/فایل مدیریت همین حالا برای شما ارسال می‌شود."
            + ("\n🖊 سپس مرحلهٔ درج امضای الکترونیک آغاز خواهد شد." if has_sign else ""),
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        await message.answer(
            "✅ پرداخت شما ثبت شد!\n\n"
            f"💰 مبلغ: {amount_rial // 10:,} تومان\n\n"
            "⚠️ ارسال پیام مدیریت با اختلال موقت مواجه شد؛ مدیریت مطلع شد و "
            "پیام شما به‌زودی ارسال می‌گردد.",
            reply_markup=ReplyKeyboardRemove()
        )

    # ── ۳) لاگ رویداد ──
    try:
        await log_event(
            "پرداخت", doc_label or "ارسال پیام مدیریت", message.from_user.full_name, user_id,
            tracking_code=tracking_code,
            doc_name=doc_label or "ارسال پیام مدیریت",
            payment_status="پرداخت شده (فاکتور پیام پنل ادمین)",
            note=f"مبلغ: {amount_rial:,} ریال | payment_id: {payment_id} | mid: {mid}",
        )
    except Exception as e:
        logger.warning(f"[PANEL-MSG-PAY] خطا در log_event: {e}")

    # ── ۴) اطلاع‌رسانی به مدیر ──
    try:
        await bot.send_message(
            ADMIN_ID,
            f"💰 پرداخت فاکتور «پیام پنل ادمین»:\n\n"
            f"👤 کاربر: {message.from_user.full_name} ({user_id})\n"
            f"💰 مبلغ: {amount_rial // 10:,} تومان ({amount_rial:,} ریال)\n"
            f"📄 نوع سند: {doc_label or 'بدون امضا (فقط ارسال پیام)'}\n"
            f"🆔 پیام پنل: {mid}\n"
            + (f"🔢 کد رهگیری: {tracking_code or '—'}\n" if has_sign else "")
            + f"📨 ارسال پیام توسط پنل: "
            + ("موفق ✅" if panel_ok else "ناموفق ❌ — نیازمند پیگیری دستی (دکمهٔ ارسال در تاریخچه پنل)")
            + f"\n⏱ زمان: {datetime.datetime.now().strftime('%Y/%m/%d %H:%M')}\n"
            f"🎫 payment_id: {payment_id}"
        )
    except Exception as e:
        logger.error(f"[PANEL-MSG-PAY] خطا در اطلاع‌رسانی به ادمین: {e}", exc_info=True)

    # ── ۵) شروع خودکار «روند درج امضا» برای نوع سند انتخابی ──
    if not (panel_ok and has_sign):
        await state.clear()
        return

    if svc == "EZHHARNAMEH":
        # فلوی امضای اظهارنامه — دقیقاً مثل /fee و پرداخت خودکار اظهارنامه
        runtime_state.pending_ezhhar_sign[user_id] = {
            "tracking_code": tracking_code,
            "is_ezhharnameh": True,
            "service_type": svc,
            "sign_persons": [],
            "persons_awaiting_sign": [],
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
            "هر موقع آمادگی دارید که کد امضا ارسال شود، گزینه زیر را انتخاب کنید:",
            reply_markup=ezhhar_sign_ready_kb)
        await state.set_state(Form.ezhhar_sign_ready)
        return

    # لایحه / واخواهی / تجدیدنظر / دادخواست بدوی / صلح / چک / فرجام →
    # فلوی امضای لایحه با مسیر منوی مناسب (ناوبری امضا)
    runtime_state.pending_lavayeh_sign[user_id] = {
        "tracking_code": tracking_code,
        "lavayeh_title": doc_label or "سند",
        "province": "",
        "row_number": 1,
        "persons": [],
        "service_type": svc,
        "sign_menu_path": sign_menu_path,
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
    from keyboards import lavayeh_sign_ready_kb
    await bot.send_message(
        user_id,
        "🖊 *مرحله اخذ امضای الکترونیک:*\n\n"
        "هر موقع آمادگی دارید که کد امضا ارسال شود، گزینه زیر را انتخاب کنید:",
        reply_markup=lavayeh_sign_ready_kb)
    await state.set_state(Form.lavayeh_sign_ready)

