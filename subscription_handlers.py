"""
هندلرهای بخش اشتراک ماهیانه.

جریان:
  ۱. کاربر «فعال‌سازی اشتراک ماهیانه» را انتخاب می‌کند
  ۲. اطلاعات اشتراک نمایش داده می‌شود
  ۳. کاربر دکمه «پرداخت آنلاین (کیف پول بله)» را می‌زند
  ۴. فاکتور بله ارسال می‌شود
  ۵. پس از پرداخت موفق، اشتراک ۳۰ روزه فعال می‌شود
  ۶. پس از انقضای اشتراک، اعلان خودکار به کاربر ارسال می‌شود
"""
import asyncio
import datetime
import logging

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Message, InlineKeyboardMarkup,
    InlineKeyboardButton, CallbackQuery
)

import json as _json
import aiohttp

import runtime_state
from config import ADMIN_ID, BALE_API_BASE, BALE_WALLET_TOKEN, BOT_TOKEN
from states import Form
from keyboards import subscription_kb, flow_type_kb, restart_kb

subscription_router = Router()

SUBSCRIPTION_FEE = runtime_state.SUBSCRIPTION_FEE
SUBSCRIPTION_DURATION_DAYS = runtime_state.SUBSCRIPTION_DURATION_DAYS


# ══════════════════════════════════════════════════════════════════════════════
# ورود به بخش اشتراک — دکمه «💳 فعال‌سازی اشتراک ماهیانه»
# ══════════════════════════════════════════════════════════════════════════════
@subscription_router.message(F.text == "💳 فعال‌سازی اشتراک ماهیانه")
async def subscription_entry(message: Message, state: FSMContext):
    user_id = message.from_user.id

    # اگر اشتراک فعال دارد، وضعیت را نشان بده
    if runtime_state.has_active_subscription(user_id):
        sub = runtime_state.user_subscriptions[user_id]
        start_str = sub["start_date"].strftime("%Y/%m/%d %H:%M")
        end_str = sub["end_date"].strftime("%Y/%m/%d %H:%M")
        remaining_days = (sub["end_date"] - datetime.datetime.now()).days
        await message.answer(
            f"✅ *اشتراک شما فعال است*\n\n"
            f"📅 تاریخ شروع: {start_str}\n"
            f"📅 تاریخ پایان: {end_str}\n"
            f"⏱ روزهای باقی‌مانده: *{remaining_days} روز*\n\n"
            f"پس از انقضای اشتراک، می‌توانید تمدید نمایید.",
            reply_markup=flow_type_kb)
        return

    # اگر در انتظار تایید ادمین است
    if user_id in runtime_state.pending_subscription_payments:
        await message.answer(
            "⏳ *درخواست اشتراک شما قبلاً ثبت شده و در انتظار تایید مدیریت است.*\n\n"
            "لطفاً منتظر تایید مدیریت باشید.",
            reply_markup=flow_type_kb)
        return

    # ذخیره مبلغ اشتراک در state برای ارسال فاکتور
    await state.update_data(subscription_fee=SUBSCRIPTION_FEE)

    await message.answer(
        f"💳 *فعال‌سازی اشتراک ماهیانه*\n\n"
        f"با فعال‌سازی اشتراک ماهیانه، از تمامی خدمات بخش *محاسبه تمبر* و *ابزار فایل* "
        f"بدون محدودیت استفاده خواهید کرد.\n\n"
        f"💰 مبلغ اشتراک: *{SUBSCRIPTION_FEE:,} ریال*\n"
        f"⏱ مدت اشتراک: *{SUBSCRIPTION_DURATION_DAYS} روز*\n\n"
        f"👉 برای پرداخت، دکمه زیر را بزنید:",
        reply_markup=subscription_kb)
    await state.set_state(Form.subscription_waiting_payment)


# ══════════════════════════════════════════════════════════════════════════════
# بازگشت به منوی اصلی از بخش اشتراک
# ══════════════════════════════════════════════════════════════════════════════
@subscription_router.message(Form.subscription_main, F.text == "🔙 بازگشت به منوی اصلی")
async def subscription_back_to_main(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("بازگشت به منوی اصلی.", reply_markup=flow_type_kb)
    await state.set_state(Form.waiting_for_flow_type)





# ══════════════════════════════════════════════════════════════════════════════
# پرداخت آنلاین اشتراک از طریق کیف پول بله
# ══════════════════════════════════════════════════════════════════════════════
@subscription_router.message(Form.subscription_waiting_payment, F.text == "💳 پرداخت آنلاین (کیف پول بله)")
async def subscription_online_payment(message: Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    data = await state.get_data()
    fee = data.get("subscription_fee", SUBSCRIPTION_FEE)
    fee_rial = fee  # SUBSCRIPTION_FEE is already in Rial

    try:
        invoice_payload = _json.dumps({"type": "subscription", "uid": user_id})
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
            invoice_url = f"{BALE_API_BASE}/bot{BOT_TOKEN}/sendInvoice"
            invoice_data = {
                "chat_id": user_id,
                "title": f"فاکتور اشتراک ماهیانه",
                "description": f"اشتراک ماهیانه خدمات قضایی: {fee:,} ریال — مدت {SUBSCRIPTION_DURATION_DAYS} روز",
                "payload": invoice_payload,
                "provider_token": BALE_WALLET_TOKEN,
                "currency": "IRR",
                "prices": [{"label": "اشتراک ماهیانه", "amount": fee_rial}],
            }
            logging.info(f"[SUB-PAY] ارسال sendInvoice به chat_id={user_id}, مبلغ={fee_rial:,} ریال")
            async with session.post(invoice_url, json=invoice_data) as resp:
                result = await resp.json()
                logging.info(f"[SUB-PAY] پاسخ sendInvoice: {result}")
                if not result.get("ok"):
                    logging.error(f"[SUB-PAY] خطای sendInvoice: {result}")
                    raise Exception(result.get("description", "خطا در ارسال فاکتور"))
    except Exception as e:
        logging.error(f"[SUB-PAY] خطا در ارسال فاکتور اشتراک: {e}", exc_info=True)
        await message.answer("⚠️ خطا در ساخت فاکتور. لطفاً کمی بعد دوباره تلاش کنید.")
        return

    await message.answer(
        "⏳ فاکتور اشتراک ارسال شد.\n\n"
        "پس از پرداخت موفق، اشتراک شما به‌صورت خودکار فعال می‌شود.",
        reply_markup=subscription_kb)


@subscription_router.message(Form.subscription_waiting_payment, F.text == "🔙 بازگشت به منوی اصلی")
async def subscription_cancel_and_back(message: Message, state: FSMContext):
    """انصراف از پرداخت اشتراک و بازگشت به منوی اصلی"""
    await state.clear()
    await message.answer("✅ انصراف از فعال‌سازی اشتراک.\nبازگشت به منوی اصلی.", reply_markup=flow_type_kb)
    await state.set_state(Form.waiting_for_flow_type)


@subscription_router.message(Form.subscription_waiting_payment)
async def subscription_waiting_text(message: Message):
    await message.answer(
        "⚠️ لطفاً از گزینه *«💳 پرداخت آنلاین (کیف پول بله)»* استفاده فرمایید.",
        reply_markup=subscription_kb)


# ══════════════════════════════════════════════════════════════════════════════
# حلقه بررسی انقضای اشتراک و اعلان خودکار
# ══════════════════════════════════════════════════════════════════════════════
async def subscription_expiry_checker(bot: Bot):
    """
    هر ۱۰ دقیقه بررسی می‌کند آیا اشتراک کاربری منقضی شده یا خیر.
    در صورت انقضا، پیام تمدید اشتراک به کاربر ارسال می‌شود.
    """
    while True:
        await asyncio.sleep(600)  # هر ۱۰ دقیقه

        try:
            expired_users = runtime_state.get_expired_subscriptions()
            for user_id in expired_users:
                runtime_state.mark_expiry_notified(user_id)
                try:
                    await bot.send_message(
                        user_id,
                        f"🔔 *اعلام تمدید اشتراک*\n\n"
                        f"اشتراک ماهیانه شما به پایان رسیده است.\n\n"
                        f"💰 جهت استفاده مجدد از بخش *محاسبه تمبر* و *ابزار فایل*، "
                        f"لطفاً *اشتراک ماهیانه* را مجدداً پرداخت نمایید.\n\n"
                        f"💳 مبلغ اشتراک: *{SUBSCRIPTION_FEE:,} ریال*\n"
                        f"⏱ مدت اشتراک: *{SUBSCRIPTION_DURATION_DAYS} روز*\n\n"
                        f"برای فعال‌سازی، از گزینه «💳 فعال‌سازی اشتراک ماهیانه» استفاده فرمایید.")
                    logging.info(f"[SUBSCRIPTION] اعلان انقضا ارسال شد به کاربر {user_id}")
                except Exception as e:
                    logging.error(f"[SUBSCRIPTION] خطا در ارسال اعلان انقضا به {user_id}: {e}")
        except Exception as e:
            logging.error(f"[SUBSCRIPTION] خطا در حلقه بررسی انقضا: {e}")
            try:
                from bug_reporter import report_bug
                await report_bug(None, where="subscription_expiry_checker", error=e, notify_admin=False)
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════════════
# کال‌بک‌های تایید/رد قدیمی تمبر (compatibility — در صورت وجود callback قدیمی)
# ══════════════════════════════════════════════════════════════════════════════
# این کال‌بک‌ها قبلاً در stamp_calc_handlers بودند، حالا به اینجا منتقل شده‌اند
# تا فایل stamp_calc_handlers تمیزتر باشد. البته ممکن است در handlers.py هم
# کال‌بک‌هایی وجود داشته باشند که باید با این‌ها تداخل نداشته باشند.
