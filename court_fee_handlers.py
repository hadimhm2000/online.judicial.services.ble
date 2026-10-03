"""
هندلرهای بخش «محاسبه هزینه دادرسی» — گزینهٔ مستقل منوی اصلی (۱۴۰۵/۰۷).

کاملاً رایگان، بدون اشتراک و مستقل از ساعت کاری (هیچ درخواستی به سامانه
قضایی نمی‌فرستد). جریان: مبلغ خواسته/محکوم‌به (ریال) → انتخاب یکی از سه
مرحلهٔ دادرسی → نتیجه. پس از نتیجه همان سه گزینه باقی می‌ماند تا کاربر
مرحلهٔ دیگری را هم برای همان مبلغ ببیند.

این روتر در bot.py قبل از روتر اصلی ثبت می‌شود (مثل damages_router).
"""
from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

import court_fee as cf
from damages_calc import parse_amount
from keyboards import BACK_TO_MAIN_TEXT, COURT_FEE_MENU_TEXT, get_flow_type_kb
from states import Form

court_fee_router = Router()

NEW_AMOUNT_TEXT = "🔢 مبلغ جدید"

_CATEGORY_BUTTONS = {
    f"1️⃣ {cf.CATEGORY_TITLES[cf.CAT_FIRST]}": cf.CAT_FIRST,
    f"2️⃣ {cf.CATEGORY_TITLES[cf.CAT_APPEAL]}": cf.CAT_APPEAL,
    f"3️⃣ {cf.CATEGORY_TITLES[cf.CAT_RETRIAL]}": cf.CAT_RETRIAL,
}

category_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=t)] for t in _CATEGORY_BUTTONS]
    + [[KeyboardButton(text=NEW_AMOUNT_TEXT)], [KeyboardButton(text=BACK_TO_MAIN_TEXT)]],
    resize_keyboard=True)

amount_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=BACK_TO_MAIN_TEXT)]], resize_keyboard=True)

AMOUNT_PROMPT = (
    "⚖️ *محاسبه هزینه دادرسی* (رایگان)\n\n"
    "💵 بهای خواسته یا محکوم‌به را به *ریال* وارد کنید:\n_(فقط عدد — مثال: 500000000)_"
)


def _is_restart(text: str) -> bool:
    return "شروع مجدد" in text and len(text) <= 20


async def _back_to_main(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "❓ *لطفاً نحوه ثبت درخواست خود را انتخاب فرمایید:*",
        reply_markup=get_flow_type_kb(message.from_user.id))
    await state.set_state(Form.waiting_for_flow_type)


@court_fee_router.message(StateFilter("*"), F.text == COURT_FEE_MENU_TEXT)
async def court_fee_entry(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(AMOUNT_PROMPT, reply_markup=amount_kb)
    await state.set_state(Form.court_fee_waiting_amount)


@court_fee_router.message(Form.court_fee_waiting_amount)
async def court_fee_amount(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if text == BACK_TO_MAIN_TEXT or _is_restart(text):
        await _back_to_main(message, state)
        return
    amount = parse_amount(text)
    if not amount:
        await message.answer("⚠️ مبلغ را فقط به‌صورت عدد و به *ریال* وارد کنید (مثال: 500000000):",
                             reply_markup=amount_kb)
        return
    await state.update_data(court_fee_amount=amount)
    await message.answer(
        f"💵 مبلغ: {amount:,} ریال ({amount // 10:,} تومان)\n\n"
        "مرحلهٔ دادرسی را انتخاب کنید:",
        reply_markup=category_kb)
    await state.set_state(Form.court_fee_waiting_category)


@court_fee_router.message(Form.court_fee_waiting_category)
async def court_fee_category(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if text == BACK_TO_MAIN_TEXT or _is_restart(text):
        await _back_to_main(message, state)
        return
    if text == NEW_AMOUNT_TEXT:
        await message.answer(AMOUNT_PROMPT, reply_markup=amount_kb)
        await state.set_state(Form.court_fee_waiting_amount)
        return
    category = _CATEGORY_BUTTONS.get(text)
    data = await state.get_data()
    amount = data.get("court_fee_amount")
    if not category or not amount:
        await message.answer("لطفاً یکی از گزینه‌های زیر را انتخاب کنید:", reply_markup=category_kb)
        return
    result = cf.calc_court_fee(int(amount), category)
    await message.answer(
        cf.format_result_fa(result) + "\n\nبرای مرحلهٔ دیگر، گزینهٔ آن را بزنید:",
        reply_markup=category_kb)
