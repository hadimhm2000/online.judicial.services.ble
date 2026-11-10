"""
دکمهٔ «⚖️ اتوماسیون ویژه خدمات حقوقی» — ورود به ربات دوم (ریپوی Legal-Automation).

  - دکمه فقط در ردیف اول منوی اصلی و فقط برای مدیر دیده می‌شود (keyboards.get_flow_type_kb).
  - چون ReplyKeyboard فقط متن می‌فرستد، شرط مدیر بودن اینجا (سمت سرور) دوباره بررسی می‌شود.
  - کاربر با یک دکمهٔ لینکی و توکن start امضاشده (HMAC، اعتبار ۵ دقیقه) به ربات دوم می‌رود.

هیچ چیزی از ربات دوم import نمی‌شود و ربات دوم هم چیزی از این ربات import نمی‌کند؛
فقط HANDOFF_SECRET در env هر دو یکسان است.
"""
import logging
import os

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import ADMIN_ID
from keyboards import LEGAL_AUTOMATION_TEXT, legal_automation_allowed
from legal_handoff import make_token

logger = logging.getLogger(__name__)

legal_automation_router = Router()


@legal_automation_router.message(StateFilter("*"), F.text == LEGAL_AUTOMATION_TEXT)
async def open_legal_automation(message: Message):
    uid = message.from_user.id
    if not legal_automation_allowed(uid):
        # متن دکمه را کسی دستی هم بفرستد، چیزی نشان داده نمی‌شود
        await message.answer("این بخش به‌زودی فعال می‌شود.")
        return
    username = (os.environ.get("LEGAL_BOT_USERNAME") or "").strip().lstrip("@")
    secret = os.environ.get("HANDOFF_SECRET") or ""
    if not username or not secret:
        await message.answer("⚠️ تنظیمات ربات دوم کامل نیست (LEGAL_BOT_USERNAME و HANDOFF_SECRET در .env).")
        return
    link = f"https://ble.ir/{username}?start={make_token(uid, secret)}"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⚖️ ورود به ربات اتوماسیون", url=link)]])
    await message.answer(
        "⚖️ اتوماسیون ویژه خدمات حقوقی\n"
        "پایش خودکار ابلاغیه‌ها، اطلاع‌رسانی پرونده و ثبت نوبت قضائی در یک ربات جداگانه.\n"
        "برای ورود روی دکمهٔ زیر بزنید (لینک ۵ دقیقه معتبر است).",
        reply_markup=kb)
    logger.info("[LEGAL-AUTO] handoff link issued for admin")
