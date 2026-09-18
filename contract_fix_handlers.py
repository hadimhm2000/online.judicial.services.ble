# -*- coding: utf-8 -*-
"""
⭐ اصلاحیه ۱۴۰۵/۰۶ — هندلرهای پنجرهٔ ۴۵ دقیقه‌ای «کد قرارداد وکالت جدید»
═══════════════════════════════════════════════════════════════════════════════

وقتی در بخش منضمات خطای «شماره قرارداد الکترونیک وکالت «...» معتبر نمی باشد»
رخ دهد، سناریوی اصلی به کاربر اعلام می‌کند شماره قرارداد اشتباه است و
۴۵ دقیقه فرصت دارد کد قرارداد جدید را ارسال فرماید (پنجرهٔ
nid_fix_window.start_contract_fix).

این ماژول دریافت کد جدید را هندل می‌کند:
  ۱. دکمهٔ «🔢 ارسال کد قرارداد جدید» (callback contract_fix:<uid>) —
     سوال کد و ورود به state
  ۲. دریافت کد ۱۶ رقمی در state (Form.contract_fix_code) و شروع تسک
     CONTRACT_FIX_SUBMIT (استعلام کدرهگیری → منضمات → فقط شماره قرارداد
     → پیام تایید → آماده‌سازی → هزینه → چاپ → ادامهٔ مراحل)
  ۳. فال‌بک: اگر کاربر بدون زدن دکمه، یک عدد ۱۶ رقمی بفرستد و پنجرهٔ
     فعالی داشته باشد، همان کد پذیرفته می‌شود.
"""
import logging

from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton)

import runtime_state
import nid_fix_window
from states import Form
from keyboards import restart_kb, back_only_kb

logger = logging.getLogger(__name__)

contract_fix_router = Router(name="contract_fix")


def contract_fix_inline_kb(user_id: int) -> InlineKeyboardMarkup:
    """کیبورد اینلاین پیام اعلام ۴۵ دقیقه‌ای — دکمهٔ «ارسال کد قرارداد جدید»."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="🔢 ارسال کد قرارداد جدید",
            callback_data=f"contract_fix:{user_id}")
    ]])


# ── ۱. کاربر دکمهٔ «ارسال کد قرارداد جدید» را زد ─────────────────────────────
@contract_fix_router.callback_query(F.data.startswith("contract_fix:"))
async def contract_fix_start_callback(callback: CallbackQuery, state, bot):
    parts = callback.data.split(":")
    target_user_id = int(parts[1])

    if callback.from_user.id != target_user_id:
        await callback.answer("⚠️ این دکمه مربوط به شما نیست.")
        return

    pending = nid_fix_window.get_contract_fix(target_user_id)
    if not pending:
        await callback.answer(
            "⚠️ درخواستی برای ارسال کد قرارداد یافت نشد (مهلت ۴۵ دقیقه‌ای به پایان رسیده است).")
        return

    await callback.answer()

    flow_labels = {
        "lavayeh": "لایحه", "ealam": "اعلام وکالت", "ezhharnameh": "اظهارنامه",
        "check": "دادخواست", "tn": "دعاوی اعتراضی",
    }
    flow_label = flow_labels.get(pending.get("flow", ""), "")

    await bot.send_message(
        target_user_id,
        f"🔢 لطفاً *کد قرارداد جدید* را ارسال فرمایید:\n"
        f"_(دقیقاً ۱۶ رقمی — عین قرارداد وکالت الکترونیک سامانه ثنا)_\n\n"
        f"📋 سرویس: {flow_label} | کد رهگیری: `{pending.get('bill_no', '')}`",
        parse_mode="Markdown",
        reply_markup=back_only_kb)
    await state.set_state(Form.contract_fix_code)


# ── ۲. دریافت کد قرارداد جدید در state ────────────────────────────────────────
@contract_fix_router.message(Form.contract_fix_code, F.text)
async def contract_fix_code_handler(message: Message, state, bot):
    text = (message.text or "").strip()

    if text == "🔙 بازگشت":
        # بستن پنجره — درخواست ادامهٔ خودکار لغو شد (پنجره تا پایان مهلت
        # ۴۵ دقیقه‌ای خودکار توسط اسوئپر بسته می‌شود؛ اینجا فقط از state
        # خارج می‌شویم)
        await message.answer(
            "🔙 بازگشت انجام شد.\n"
            "⏰ توجه: تا پایان مهلت ۴۵ دقیقه‌ای می‌توانید با زدن دکمهٔ "
            "«🔢 ارسال کد قرارداد جدید» اقدام فرمایید.",
            reply_markup=restart_kb)
        await state.clear()
        return

    # ارقام لاتین/فارسی → لاتین
    normalized = text.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
    digits = "".join(ch for ch in normalized if ch.isdigit())

    if len(digits) != 16:
        await message.answer(
            "⚠️ شماره قرارداد وکالت باید *دقیقاً ۱۶ رقمی* باشد.\n"
            "لطفاً مجدداً ارسال فرمایید:",
            parse_mode="Markdown")
        return

    user_id = message.from_user.id
    pending = nid_fix_window.pop_contract_fix(user_id)
    if not pending:
        await message.answer(
            "⚠️ درخواست منقضی شده است. لطفاً از منوی اصلی مجدداً اقدام فرمایید.",
            reply_markup=restart_kb)
        await state.clear()
        return

    task_data = pending.get("task_data") or {}
    fix_job = {
        "task_type": "CONTRACT_FIX_SUBMIT",
        "user_id": user_id,
        "flow": pending.get("flow", "lavayeh"),
        "bill_no": pending.get("bill_no", ""),
        "contract_number": digits,
        "stamp_amount_value": int(pending.get("stamp_amount_value", 0) or 0),
        "task_data": task_data,
    }

    await message.answer(
        f"✅ کد قرارداد `{digits}` دریافت شد.\n\n"
        f"⏳ در حال استعلام کد رهگیری `{pending.get('bill_no', '')}` و ثبت "
        f"قرارداد در بخش منضمات... پس از پیام تایید، آماده‌سازی، هزینه، "
        f"چاپ و ادامهٔ مراحل به‌صورت خودکار انجام می‌شود.",
        parse_mode="Markdown",
        reply_markup=restart_kb)

    await state.clear()
    await runtime_state.job_queue.put(fix_job)


# ── ۳. فال‌بک — کاربر بدون زدن دکمه، عدد ۱۶ رقمی فرستاد ──────────────────────
# ⚠️ این حالت در fallback_router (handlers.py) هندل می‌شود — چون fallback_router
# آخرین روتر است، بررسی پنجرهٔ کد قرارداد در ابتدای همان هندلر انجام می‌شود
# تا هیچ پیامی سایه‌انداز نشود.

async def try_handle_stateless_contract_code(message: Message, state) -> bool:
    """اگر پیام عدد ۱۶ رقمی باشد و کاربر پنجرهٔ فعال کد قرارداد داشته باشد،
    آن را به‌عنوان کد قرارداد جدید پردازش می‌کند.

    خروجی: True اگر پیام هندل شد (فراخواننده نباید ادامه دهد).
    """
    text = (message.text or "").strip()
    if not text:
        return False

    normalized = text.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
    if not normalized.isdigit() or len(normalized) != 16:
        return False

    user_id = message.from_user.id
    pending = nid_fix_window.get_contract_fix(user_id)
    if not pending:
        return False

    logger.info(
        f"[CONTRACT-FIX] دریافت کد قرارداد بدون دکمه از کاربر {user_id} — "
        f"پردازش به‌عنوان کد قرارداد جدید")

    pending = nid_fix_window.pop_contract_fix(user_id)
    task_data = pending.get("task_data") or {}
    fix_job = {
        "task_type": "CONTRACT_FIX_SUBMIT",
        "user_id": user_id,
        "flow": pending.get("flow", "lavayeh"),
        "bill_no": pending.get("bill_no", ""),
        "contract_number": normalized,
        "stamp_amount_value": int(pending.get("stamp_amount_value", 0) or 0),
        "task_data": task_data,
    }

    await message.answer(
        f"✅ کد قرارداد `{normalized}` دریافت شد.\n\n"
        f"⏳ در حال استعلام کد رهگیری `{pending.get('bill_no', '')}` و ثبت "
        f"قرارداد در بخش منضمات... پس از پیام تایید، آماده‌سازی، هزینه، "
        f"چاپ و ادامهٔ مراحل به‌صورت خودکار انجام می‌شود.",
        parse_mode="Markdown",
        reply_markup=restart_kb)
    try:
        await state.clear()
    except Exception:
        pass
    await runtime_state.job_queue.put(fix_job)
    return True
