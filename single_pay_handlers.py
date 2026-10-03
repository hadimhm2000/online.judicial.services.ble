"""
پرداخت تکی بخش‌های «محاسبه تمبر» و «خسارت تأخیر تأدیه / مهریه» (۱۴۰۵/۰۷).

وقتی ۲ استفادهٔ رایگان کاربر در یکی از این دو بخش تمام شده و اشتراک فعال
ندارد، دو گزینه نمایش داده می‌شود:
  ۱. دریافت اشتراک ماهیانه (همان فلوی subscription_handlers)
  ۲. پرداخت تکی همین مورد — تمبر ۲۰,۰۰۰ تومان، خسارت تأخیر/مهریه ۴۵,۰۰۰ تومان

پس از پرداخت موفق فاکتور تکی (payload: {"type": "single_use", "svc": ...})
یک اعتبار برای همان بخش ثبت می‌شود (runtime_state.add_single_use_credit) و
کاربر مستقیم وارد همان بخش می‌شود؛ اعتبار با اولین محاسبهٔ موفق مصرف می‌شود.
بخش «ابزار فایل» پرداخت تکی ندارد و مثل قبل فقط اشتراک ماهیانه دارد.
"""
import json as _json
import logging

import aiohttp
from aiogram import Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

import runtime_state
from config import BALE_API_BASE, BALE_SSL_CONTEXT, BALE_WALLET_TOKEN, BOT_TOKEN
from keyboards import BACK_TO_MAIN_TEXT, get_flow_type_kb
from states import Form

logger = logging.getLogger(__name__)

single_pay_router = Router()

SUBSCRIBE_CHOICE_TEXT = "💳 دریافت اشتراک ماهیانه"

SERVICE_LABELS = {
    "stamp": "محاسبه تمبر",
    "damages": "محاسبهٔ خسارت تأخیر تأدیه / مهریه",
}


def single_fee_rial(service: str) -> int:
    return runtime_state.SINGLE_USE_FEES[service]


def single_choice_text(service: str) -> str:
    return f"💵 پرداخت تکی همین مورد ({single_fee_rial(service) // 10:,} تومان)"


def _choice_kb(service: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=SUBSCRIBE_CHOICE_TEXT)],
        [KeyboardButton(text=single_choice_text(service))],
        [KeyboardButton(text=BACK_TO_MAIN_TEXT)],
    ], resize_keyboard=True)


_waiting_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=BACK_TO_MAIN_TEXT)]], resize_keyboard=True)


async def offer_subscription_or_single(message: Message, state: FSMContext, service: str):
    """پیام «سهمیهٔ رایگان تمام شد» با دو گزینهٔ اشتراک ماهیانه / پرداخت تکی."""
    label = SERVICE_LABELS[service]
    sub_fee = runtime_state.SUBSCRIPTION_FEE
    await state.clear()
    await state.update_data(single_pay_service=service)
    await state.set_state(Form.single_pay_choice)
    await message.answer(
        f"⚠️ *محدودیت استفاده رایگان تمام شد*\n\n"
        f"شما {runtime_state.MAX_FREE_USAGE} بار استفاده رایگان از بخش {label} را مصرف کرده‌اید.\n"
        f"برای ادامه یکی از دو گزینهٔ زیر را انتخاب کنید:\n\n"
        f"1️⃣ *اشتراک ماهیانه* — {sub_fee // 10:,} تومان برای "
        f"{runtime_state.SUBSCRIPTION_DURATION_DAYS} روز، معتبر برای همهٔ بخش‌های زیر:\n"
        f"{runtime_state.SUBSCRIPTION_FEATURES_TEXT}\n\n"
        f"2️⃣ *پرداخت تکی* — فقط همین یک مورد {label}: "
        f"*{single_fee_rial(service) // 10:,} تومان*",
        reply_markup=_choice_kb(service))


async def _back_to_main(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("بازگشت به منوی اصلی.", reply_markup=get_flow_type_kb(message.from_user.id))
    await state.set_state(Form.waiting_for_flow_type)


@single_pay_router.message(Form.single_pay_choice)
async def single_pay_choice_handler(message: Message, state: FSMContext, bot: Bot):
    text = message.text or ""
    data = await state.get_data()
    service = data.get("single_pay_service")
    if text == BACK_TO_MAIN_TEXT or service not in runtime_state.SINGLE_USE_FEES:
        await _back_to_main(message, state)
        return
    if text == SUBSCRIBE_CHOICE_TEXT:
        from subscription_handlers import subscription_entry
        await state.clear()
        await subscription_entry(message, state)
        return
    if text == single_choice_text(service):
        await _send_single_invoice(message, state, bot, service)
        return
    await message.answer("لطفاً یکی از گزینه‌های زیر را انتخاب کنید:", reply_markup=_choice_kb(service))


async def _send_single_invoice(message: Message, state: FSMContext, bot: Bot, service: str):
    user_id = message.from_user.id
    fee_rial = single_fee_rial(service)
    label = SERVICE_LABELS[service]
    try:
        invoice_data = {
            "chat_id": user_id,
            "title": f"پرداخت تکی {label}",
            "description": f"پرداخت تکی یک مورد {label}: {fee_rial // 10:,} تومان ({fee_rial:,} ریال)",
            "payload": _json.dumps({"type": "single_use", "svc": service, "uid": user_id}),
            "provider_token": BALE_WALLET_TOKEN,
            "currency": "IRR",
            "prices": [{"label": f"پرداخت تکی {label}", "amount": fee_rial}],
        }
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=BALE_SSL_CONTEXT)) as session:
            async with session.post(f"{BALE_API_BASE}/bot{BOT_TOKEN}/sendInvoice", json=invoice_data) as resp:
                result = await resp.json()
        logger.info(f"[SINGLE-USE] sendInvoice user={user_id} svc={service} amount={fee_rial:,}: {result}")
        if not result.get("ok"):
            raise Exception(result.get("description", "خطا در ارسال فاکتور"))
        from card_payment import track_invoice as _cp_track; _cp_track(invoice_data)  # کارت‌به‌کارت پس از ۲۰ دقیقه
    except Exception as e:
        logger.error(f"[SINGLE-USE] خطا در ارسال فاکتور تکی: {e}", exc_info=True)
        await message.answer("⚠️ خطا در ساخت فاکتور. لطفاً کمی بعد دوباره تلاش کنید.")
        return
    await state.update_data(single_pay_service=service)
    await state.set_state(Form.single_pay_waiting_payment)
    await message.answer(
        "⏳ فاکتور پرداخت تکی ارسال شد.\n\n"
        f"پس از پرداخت موفق، بلافاصله وارد بخش {label} می‌شوید.",
        reply_markup=_waiting_kb)


@single_pay_router.message(Form.single_pay_waiting_payment)
async def single_pay_waiting_handler(message: Message, state: FSMContext):
    if message.successful_payment:
        return
    if (message.text or "") == BACK_TO_MAIN_TEXT:
        await _back_to_main(message, state)
        return
    await message.answer("⚠️ لطفاً فاکتور ارسال‌شده را پرداخت کنید یا به منوی اصلی بازگردید.",
                         reply_markup=_waiting_kb)


async def single_use_successful_payment(message: Message, state: FSMContext, bot: Bot, payload: dict):
    """پرداخت موفق فاکتور تکی — از global_successful_payment_handler صدا زده می‌شود."""
    user_id = message.from_user.id
    service = payload.get("svc")
    if service not in runtime_state.SINGLE_USE_FEES:
        data = await state.get_data()
        service = data.get("single_pay_service")
    if service not in runtime_state.SINGLE_USE_FEES:
        logger.error(f"[SINGLE-USE] پرداخت بدون سرویس معتبر — user={user_id}, payload={payload}")
        await message.answer("✅ پرداخت شما دریافت شد.\n⚠️ در پردازش خودکار مشکلی پیش آمد؛ به مدیریت اطلاع داده شد.")
        try:
            from config import ADMIN_ID
            await bot.send_message(ADMIN_ID, f"⚠️ [SINGLE-USE] پرداخت تکی بدون سرویس — user={user_id}, payload={payload}")
        except Exception:
            pass
        return
    runtime_state.add_single_use_credit(user_id, service)
    logger.info(f"[SINGLE-USE] پرداخت موفق user={user_id} svc={service} "
                f"charge_id={getattr(message.successful_payment, 'telegram_payment_charge_id', '')}")
    await message.answer(f"✅ *پرداخت تایید شد.*\nاکنون می‌توانید یک مورد {SERVICE_LABELS[service]} انجام دهید.")
    await state.clear()
    if service == "stamp":
        from stamp_calc_handlers import stamp_calc_entry
        await stamp_calc_entry(message, state)
    else:
        from damages_handlers import damages_entry
        await damages_entry(message, state)
