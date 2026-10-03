"""
هندلرهای بخش محاسبه تمبر مالیاتی وکیل (مستقل از فلوی اعلام وکالت).

جریان:
  ۱. کاربر «محاسبه تمبر مالیاتی وکیل» را انتخاب می‌کند
  ۲. بررسی محدودیت استفاده (۲ دفعه رایگان، بعد نیاز به اشتراک)
  ۳. نوع دعوی را انتخاب می‌کند (مالی / غیر مالی)
  ۴. اگر مالی: مبلغ خواسته را وارد می‌کند → نتیجه محاسبه مستقیم نمایش داده می‌شود
  ۵. اگر غیر مالی: مبلغ 200,000 ریال اعلام می‌شود
"""
import logging

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

import runtime_state
from states import Form
from keyboards import restart_kb, stamp_calc_claim_type_kb, back_only_kb
from stamp_duty import calculate_stamp_duty, format_result_fa

stamp_calc_router = Router()

_FA_AR = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789"
)

def _to_en(text: str) -> str:
    return text.translate(_FA_AR).replace(" ", "").strip()

def _fmt(n: int) -> str:
    return f"{n:,}"

SUBSCRIPTION_FEE = runtime_state.SUBSCRIPTION_FEE
MAX_FREE_USAGE = runtime_state.MAX_FREE_USAGE


# ══════════════════════════════════════════════════════════════════════════════
# ورود به بخش محاسبه تمبر
# ══════════════════════════════════════════════════════════════════════════════
@stamp_calc_router.message(StateFilter("*"), F.text == "🧮 محاسبه تمبر مالیاتی وکیل")
async def stamp_calc_entry(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id

    # بررسی محدودیت استفاده — ⭐ پس از ۲ بار رایگان: اشتراک ماهیانه یا پرداخت تکی
    if not runtime_state.can_use_service(user_id, "stamp"):
        from single_pay_handlers import offer_subscription_or_single
        await offer_subscription_or_single(message, state, "stamp")
        return

    # نمایش تعداد دفعات باقی‌مانده
    status = runtime_state.usage_status_line(user_id, "stamp")

    await message.answer(
        f"🧮 *محاسبه تمبر مالیاتی وکیل*\n\n"
        f"{status}"
        f"لطفاً گزینه‌های زیر را انتخاب کنید:",
        reply_markup=stamp_calc_claim_type_kb)
    await state.set_state(Form.stamp_calc_claim_type)


# ══════════════════════════════════════════════════════════════════════════════
# انتخاب نوع دعوی
# ══════════════════════════════════════════════════════════════════════════════
@stamp_calc_router.message(Form.stamp_calc_claim_type)
async def stamp_calc_claim_type_handler(message: Message, state: FSMContext):
    text = message.text or ""

    if "2️⃣" in text or "غیر مالی" in text:
        # دعوی غیر مالی — بدون پرداخت
        await message.answer(
            "📋 *تمبر دعوی غیر مالی:*\n\n"
            "مبلغ *200,000 ریال* به ازای هر خواسته می‌باشد.\n\n"
            "⚠️ نیازی به پرداخت هزینه نمی‌باشد.",
            reply_markup=restart_kb)
        await state.clear()
        return

    if "1️⃣" in text or "مالی" in text:
        await message.answer(
            "💵 لطفاً *مبلغ خواسته* را به *ریال* وارد فرمایید:\n_(فقط عدد)_",
            reply_markup=back_only_kb)
        await state.set_state(Form.stamp_calc_claim_amount)
        return

    await message.answer("⚠️ لطفاً یکی از گزینه‌های موجود را انتخاب کنید:", reply_markup=stamp_calc_claim_type_kb)


# ══════════════════════════════════════════════════════════════════════════════
# دریافت مبلغ خواسته
# ══════════════════════════════════════════════════════════════════════════════
@stamp_calc_router.message(Form.stamp_calc_claim_amount)
async def stamp_calc_amount_handler(message: Message, state: FSMContext, bot: Bot):
    if not message.text:
        return
    if message.text == "🔙 بازگشت":
        await message.answer(
            "🧮 *محاسبه تمبر مالیاتی وکیل*\n\nلطفاً گزینه‌های زیر را انتخاب کنید:",
            reply_markup=stamp_calc_claim_type_kb)
        await state.set_state(Form.stamp_calc_claim_type)
        return

    amount_str = _to_en(message.text)
    if not amount_str.isdigit() or int(amount_str) <= 0:
        await message.answer("⚠️ لطفاً مبلغ را به *ریال* وارد کنید (فقط عدد):")
        return

    claim_amount = int(amount_str)
    try:
        result = calculate_stamp_duty(claim_amount)
    except ValueError as e:
        await message.answer(f"⚠️ خطا در محاسبه: {e}")
        return

    # افزایش شمارنده استفاده
    user_id = message.from_user.id
    runtime_state.increment_usage(user_id, "stamp")

    # نمایش مستقیم نتیجه محاسبه (بدون پرداخت)
    result_text = format_result_fa(claim_amount, result)
    await message.answer(
        f"✅ *نتیجه محاسبه تمبر مالیاتی:*\n\n{result_text}",
        reply_markup=restart_kb)
    await state.clear()


# ══════════════════════════════════════════════════════════════════════════════
# NOTE: بخش پرداخت و نظارت ۲ ساعته حذف شد — نتیجه محاسبه مستقیم نمایش داده می‌شود
# ══════════════════════════════════════════════════════════════════════════════
