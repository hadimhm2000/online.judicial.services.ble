"""
هندلرهای بخش اشتراک ماهیانه.

جریان:
  ۱. کاربر «فعال‌سازی اشتراک ماهیانه» را انتخاب می‌کند
  ۲. اطلاعات اشتراک و شماره کارت نمایش داده می‌شود
  ۳. کاربر عکس رسید واریزی را ارسال می‌کند
  ۴. رسید به ادمین ارسال می‌شود
  ۵. ادمین تایید/رد می‌کند
  ۶. در صورت تایید، اشتراک ۳۰ روزه فعال می‌شود
  ۷. پس از انقضای اشتراک، اعلان خودکار به کاربر ارسال می‌شود
"""
import asyncio
import datetime
import logging
import os

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Message, InlineKeyboardMarkup,
    InlineKeyboardButton, CallbackQuery
)

import runtime_state
from bale_file_sender import send_photo_direct
from config import ADMIN_ID, CARD_NUMBER, ACCOUNT_NAME
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

    await message.answer(
        f"💳 *فعال‌سازی اشتراک ماهیانه*\n\n"
        f"با فعال‌سازی اشتراک ماهیانه، از تمامی خدمات بخش *محاسبه تمبر* و *ابزار فایل* "
        f"بدون محدودیت استفاده خواهید کرد.\n\n"
        f"💰 مبلغ اشتراک: *{SUBSCRIPTION_FEE:,} ریال*\n"
        f"⏱ مدت اشتراک: *{SUBSCRIPTION_DURATION_DAYS} روز*\n\n"
        f"💳 شماره کارت: `{CARD_NUMBER}`\n"
        f"👤 بنام: *{ACCOUNT_NAME}*\n\n"
        f"👇 پس از واریز، *عکس فیش* را ارسال فرمایید.",
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
# دریافت رسید پرداخت اشتراک
# ══════════════════════════════════════════════════════════════════════════════
@subscription_router.message(Form.subscription_waiting_payment, F.photo)
async def subscription_payment_receipt(message: Message, state: FSMContext, bot: Bot):
    import os
    from ocr import verify_payment_receipt

    user_id = message.from_user.id

    # ذخیره عکس رسید
    photo = message.photo[-1]
    photo_file = await bot.get_file(photo.file_id)
    photo_path = f"sub_receipt_{user_id}_{int(datetime.datetime.now().timestamp())}.jpg"
    await bot.download_file(photo_file.file_path, photo_path)

    # بررسی OCR
    expected_amount_toman = SUBSCRIPTION_FEE // 10
    is_valid, ocr_msg = verify_payment_receipt(photo_path, expected_amount_toman, CARD_NUMBER)

    if is_valid:
        # پاکسازی فایل
        if os.path.exists(photo_path):
            try:
                os.remove(photo_path)
            except Exception:
                pass

        # فعال‌سازی اشتراک
        runtime_state.activate_subscription(user_id)
        # همگام‌سازی با پنل ادمین
        try:
            import aiohttp as _aiohttp
            async def _sync_sub():
                async with _aiohttp.ClientSession() as s:
                    from config import ADMIN_API_BASE
                    await s.post(f"{ADMIN_API_BASE}/subscriptions/activate", json={"user_id": user_id})
            asyncio.create_task(_sync_sub())
        except Exception:
            pass
        sub = runtime_state.user_subscriptions[user_id]
        end_str = sub["end_date"].strftime("%Y/%m/%d %H:%M")

        await message.answer(
            f"✅ *پرداخت تایید شد و اشتراک فعال گردید!*\n\n"
            f"🎉 اشتراک ماهیانه شما با موفقیت فعال شد.\n"
            f"📅 تاریخ پایان اشتراک: *{end_str}*\n\n"
            f"اکنون می‌توانید از بخش *محاسبه تمبر* و *ابزار فایل* بدون محدودیت استفاده نمایید.",
            reply_markup=flow_type_kb)
        await state.clear()
    else:
        # ارسال به ادمین برای تایید دستی
        inline_kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ تایید اشتراک",
                    callback_data=f"ok_sub:{user_id}"
                ),
                InlineKeyboardButton(
                    text="❌ رد درخواست",
                    callback_data=f"no_sub:{user_id}"
                )
            ]
        ])

        # ذخیره در pending
        runtime_state.pending_subscription_payments[user_id] = {
            "photo_path": photo_path,
            "created_at": datetime.datetime.now(),
        }

        sent_result = await send_photo_direct(
            ADMIN_ID, photo_path,
            caption=(
                f"📥 *درخواست اشتراک ماهیانه جدید:*\n\n"
                f"👤 کاربر: {message.from_user.full_name} (`{user_id}`)\n"
                f"💰 مبلغ: {SUBSCRIPTION_FEE:,} ریال\n"
                f"⏱ مدت: {SUBSCRIPTION_DURATION_DAYS} روز\n\n"
                f"موتور OCR تایید نکرد. لطفاً دستی بررسی فرمایید."
            ),
            reply_markup=inline_kb)
        msg_id = sent_result.get('message_id') if isinstance(sent_result, dict) else None
        runtime_state.pending_subscription_payments[user_id]["message_id"] = msg_id

        await message.answer(
            "⏳ رسید پرداخت برای بررسی به مدیریت ارسال شد.\n"
            "نتیجه تایید/رد به زودی اعلام می‌شود.",
            reply_markup=flow_type_kb)
        await state.clear()


@subscription_router.message(Form.subscription_waiting_payment)
async def subscription_waiting_text(message: Message):
    await message.answer(
        "⚠️ لطفاً *عکس فیش واریزی* را ارسال فرمایید یا از گزینه‌های زیر استفاده کنید:",
        reply_markup=subscription_kb)


# ══════════════════════════════════════════════════════════════════════════════
# کال‌بک‌های تایید/رد اشتراک توسط ادمین
# ══════════════════════════════════════════════════════════════════════════════
@subscription_router.callback_query(F.data.startswith("ok_sub:"))
async def admin_approve_subscription(callback: CallbackQuery, bot: Bot):
    user_id_str = callback.data.split(":")[1]
    user_id = int(user_id_str)

    # فعال‌سازی اشتراک
    runtime_state.activate_subscription(user_id)
    # همگام‌سازی با پنل ادمین
    try:
        import aiohttp as _aiohttp
        async def _sync_sub():
            async with _aiohttp.ClientSession() as s:
                from config import ADMIN_API_BASE
                await s.post(f"{ADMIN_API_BASE}/subscriptions/activate", json={"user_id": user_id})
        asyncio.create_task(_sync_sub())
    except Exception:
        pass
    sub = runtime_state.user_subscriptions[user_id]
    end_str = sub["end_date"].strftime("%Y/%m/%d %H:%M")

    # پاکسازی pending
    pending = runtime_state.pending_subscription_payments.pop(user_id, None)
    if pending:
        photo_path = pending.get("photo_path")
        if photo_path and os.path.exists(photo_path):
            try:
                os.remove(photo_path)
            except Exception:
                pass

    # ویرایش پیام مدیر
    try:
        await bot.edit_message_caption(
            chat_id=ADMIN_ID,
            message_id=pending["message_id"] if pending else callback.message.message_id,
            caption=(
                f"✅ *اشتراک تایید شد*\n\n"
                f"👤 کاربر: `{user_id}`\n"
                f"📅 پایان اشتراک: {end_str}"
            ))
    except Exception:
        pass

    # اعلان به کاربر
    try:
        await bot.send_message(
            user_id,
            f"✅ *اشتراک ماهیانه شما تایید و فعال شد!*\n\n"
            f"🎉 اشتراک شما با موفقیت توسط مدیریت تایید گردید.\n"
            f"📅 تاریخ پایان اشتراک: *{end_str}*\n\n"
            f"اکنون می‌توانید از بخش *محاسبه تمبر* و *ابزار فایل* بدون محدودیت استفاده نمایید.")
    except Exception:
        logging.warning(f"[SUBSCRIPTION] نتوانستیم پیام تایید را به کاربر {user_id} ارسال کنیم")

    await callback.answer("✅ اشتراک تایید و فعال شد")


@subscription_router.callback_query(F.data.startswith("no_sub:"))
async def admin_reject_subscription(callback: CallbackQuery, bot: Bot):
    user_id_str = callback.data.split(":")[1]
    user_id = int(user_id_str)

    # پاکسازی pending
    pending = runtime_state.pending_subscription_payments.pop(user_id, None)
    if pending:
        photo_path = pending.get("photo_path")
        if photo_path and os.path.exists(photo_path):
            try:
                os.remove(photo_path)
            except Exception:
                pass

    # ویرایش پیام مدیر
    try:
        await bot.edit_message_caption(
            chat_id=ADMIN_ID,
            message_id=pending["message_id"] if pending else callback.message.message_id,
            caption=(
                f"❌ *درخواست اشتراک رد شد*\n\n"
                f"👤 کاربر: `{user_id}`"
            ))
    except Exception:
        pass

    # اعلان به کاربر
    try:
        await bot.send_message(
            user_id,
            "❌ *درخواست اشتراک ماهیانه شما رد شد.*\n\n"
            "لطفاً در صورت نیاز مجدداً از طریق بخش اشتراک اقدام فرمایید.")
    except Exception:
        logging.warning(f"[SUBSCRIPTION] نتوانستیم پیام رد را به کاربر {user_id} ارسال کنیم")

    await callback.answer("❌ درخواست اشتراک رد شد")


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
