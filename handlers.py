"""
لایه‌ی پیام‌رسان: تمام هندلرهای مکالمه (FSM) و کال‌بک‌های ادمین.
"""
import aiohttp
import asyncio
import datetime
import json as _json
import logging
import os
import re

from aiogram import Bot, F, Router, BaseMiddleware, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    ReplyKeyboardRemove, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery,
    PreCheckoutQuery, LabeledPrice
)

from bale_file_sender import send_document_direct

import runtime_state
from config import ADMIN_ID, CARD_NUMBER, ACCOUNT_NAME, BALE_WALLET_TOKEN, BOT_TOKEN, BALE_API_BASE, get_fee, FEES
from exempt_users import is_exempt_user
from working_hours import is_within_working_hours
from states import Form
from sheets import append_to_sheet, log_event
from api_direct import (
    fast_pre_check, FastCheckError, SessionExpiredError as FastSessionExpiredError,
    PetitionNotFoundError as FastPetitionNotFoundError,
    InvalidTrackingCodeError as FastInvalidTrackingCodeError)
from keyboards import (
    restart_kb, accept_rules_kb, flow_type_kb, get_flow_type_kb, get_main_menu_kb, main_menu_kb, doc_category_kb,
    attachments_kb, cart_kb, pay_kb, confirm_single_kb, confirm_cart_kb, bulk_inquiry_confirm_kb,
    cart_main_menu_kb,
    admin_login_kb, SUB_MENUS, create_submenu_kb, back_only_kb, new_lavayeh_request_kb,
    payment_cancel_kb, disrupted_retry_kb, test_mode_doc_type_kb, test_mode_section_kb,
    test_mode_att_title_kb_first, test_mode_att_title_kb, test_mode_att_more_kb,
    test_mode_ealam_representative_kb, test_mode_ealam_stamp_kb, test_mode_ealam_stamp_type_kb,
    TEST_VISIBLE_USER_ID)
from lavayeh_handlers import lavayeh_router
from stamp_calc_handlers import stamp_calc_router
from ezhharnameh_handlers import ezhharnameh_router
from tajdid_nazar_handlers import tajdid_nazar_router
from file_tools_handlers import file_tools_router, file_tools_entry
from subscription_handlers import subscription_router, subscription_expiry_checker
from check_handlers import check_router
from regional_value_handlers import regional_value_router

logger = logging.getLogger(__name__)

# بازه‌ی سال‌های معتبر برای ۷ رقم ابتدایی کد رهگیری (۱۳۹۴ تا ۱۴۰۶)
TRACKING_CODE_PREFIX_MIN = 1394220
TRACKING_CODE_PREFIX_MAX = 1406220
TRACKING_CODE_LENGTH = 16

# ───────────────────────────────────────────────────────────────
# ثابت‌های محدودیت تلاش و قطعی
# ───────────────────────────────────────────────────────────────
MAX_INQUIRY_ATTEMPTS = 2  # حداکثر تلاش ناموفق قبل از توقف
DISRUPTED_RETRY_MINUTES = 45  # فرصت تکرار بدون پرداخت (دقیقه)

# پیام خطایی که سامانه قضایی نمایش می‌دهد وقتی نوع سند اشتباه انتخاب شود
SAMANEH_WRONG_TYPE_ERROR = "کد دفتر، مبلغ پرونده یا دسترسی تقویم مربوط به این شعبه و قاضی نیست."


def _is_valid_tracking_code(code: str) -> bool:
    """کد رهگیری باید ۱۶ رقمی باشد و ۷ رقم ابتدایی آن در بازه‌ی معتبر باشد."""
    if len(code) != TRACKING_CODE_LENGTH or not code.isdigit():
        return False
    prefix = int(code[:7])
    return TRACKING_CODE_PREFIX_MIN <= prefix <= TRACKING_CODE_PREFIX_MAX


def _record_failed_inquiry(user_id: int) -> int:
    """ثبت یک تلاش ناموفق استعلام. خروجی: تعداد تلاش فعلی."""
    now = datetime.datetime.now().isoformat()
    info = runtime_state.inquiry_attempts.get(user_id, {"count": 0, "last_attempt": now})
    info["count"] += 1
    info["last_attempt"] = now
    runtime_state.inquiry_attempts[user_id] = info
    return info["count"]


def _reset_inquiry_attempts(user_id: int):
    """پاکسازی شمارنده‌ی تلاش‌های ناموفق (مثلاً وقتی کاربر از اول شروع می‌کند)."""
    runtime_state.inquiry_attempts.pop(user_id, None)


def _check_inquiry_limit(user_id: int) -> bool:
    """بررسی آیا کاربر به محدودیت تلاش رسیده است. True = محدود شده."""
    info = runtime_state.inquiry_attempts.get(user_id)
    if not info:
        return False
    # پاکسازی خودکار اگر آخرین تلاش بیش از ۲ ساعت پیش بوده
    try:
        last = datetime.datetime.fromisoformat(info["last_attempt"])
        if (datetime.datetime.now() - last) > datetime.timedelta(hours=2):
            runtime_state.inquiry_attempts.pop(user_id, None)
            return False
    except (ValueError, TypeError):
        pass
    return info["count"] >= MAX_INQUIRY_ATTEMPTS

router = Router()

# ── include کردن روترها ───────────────────────────────────────────────────────
router.include_router(lavayeh_router)
router.include_router(stamp_calc_router)
router.include_router(ezhharnameh_router)
router.include_router(tajdid_nazar_router)
router.include_router(file_tools_router)
router.include_router(subscription_router)
router.include_router(check_router)
router.include_router(regional_value_router)


# ── نگهبان: مسدودسازی کاربرانی که فاکتور لایحه کنسل‌شده را پرداخت نکرده‌اند ──
async def _is_blocked_lavayeh_user(message: types.Message) -> bool:
    # ادمین هرگز مشمول این مسدودسازی نمی‌شود
    if message.from_user and message.from_user.id == ADMIN_ID:
        return False
    pending = runtime_state.pending_lavayeh_payments.get(message.from_user.id)
    return bool(pending and pending.get("blocked"))

@router.message(StateFilter("*"), _is_blocked_lavayeh_user, ~F.photo, ~F.successful_payment)
async def block_unpaid_cancelled_lavayeh_user(message: types.Message):
    await message.answer(
        "لطفا هزینه ثبت لایحه‌ای که کنسل شده است را پرداخت بفرمائید، "
        "پس از پرداخت، ربات مجددا فعال خواهد شد.\nباتشکر",
        reply_markup=ReplyKeyboardRemove()
    )

# ================= نگهبان ساعات کاری =================
class WorkingHoursMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: types.Message, data: dict):
        if event.from_user and event.from_user.id == ADMIN_ID:
            return await handler(event, data)

        within, today_config = await is_within_working_hours()
        if within:
            return await handler(event, data)
        else:
            if today_config and not today_config.get("enabled", True):
                await event.answer("⛔️ *تعطیل*\n\nامروز تعطیل می‌باشد.")
            else:
                sh = today_config.get("startHour", 12)
                sm = today_config.get("startMin", 0)
                eh = today_config.get("endHour", 22)
                em = today_config.get("endMin", 0)
                await event.answer(
                    f"⛔️ *خارج از ساعت کاری*\n\n"
                    f"ساعت کاری امروز: {sh:02d}:{sm:02d} الی {eh:02d}:{em:02d}"
                )
            return

router.message.middleware(WorkingHoursMiddleware())



# callback تایید دستی محاسبه تمبر

# ================= هندلر pre_checkout_query — تایید خودکار پرداخت بله =================
@router.pre_checkout_query()
async def pre_checkout_query_handler(pre_checkout_query: PreCheckoutQuery, bot: Bot):
    """تایید خودکار تمام درخواست‌های پیش‌پرداخت فاکتور بله"""
    try:
        await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)
        logging.info(f"[PRE-CHECKOUT] تایید شد برای کاربر {pre_checkout_query.from_user.id}")
    except Exception as e:
        logging.error(f"[PRE-CHECKOUT] خطا در answer_pre_checkout_query: {e}", exc_info=True)


# ================= هندلر successful_payment — پرداخت موفق فاکتور بله =================
# هندلر با فیلتر حالت — فقط در حالت انتظار پرداخت
@router.message(Form.waiting_for_payment_receipt, F.successful_payment)
async def successful_payment_handler(message: types.Message, state: FSMContext, bot: Bot):
    """پرداخت موفق سبد/تک‌موردی از طریق فاکتور بله — بدون نیاز به فیش"""
    user_id = message.from_user.id
    data = await state.get_data()
    cart = data.get("cart", [])
    full_name = message.from_user.full_name
    payment = message.successful_payment

    # ⭐ فاکتور «هزینه دستی مدیر» (/fee) — حتی اگر کاربر در state استعلام باشد،
    # باید به هندلر اختصاصی خودش برود (payload متمایز: {"type": "admin_fee"})
    try:
        _pl = _json.loads(getattr(payment, "invoice_payload", "") or "{}")
    except Exception:
        _pl = {}
    if _pl.get("type") == "admin_fee":
        from admin_relay import admin_fee_successful_payment as _admin_fee_pay
        await _admin_fee_pay(message, state, bot)
        return

    # ── تشخیص فلوی تک‌موردی vs سبد خرید ──
    if cart:
        # فلوی سبد خرید
        total_fee = data.get('total_payment_sum', 0)
        queue_position = runtime_state.job_queue.qsize()
        queue_note = f"\n📊 موقعیت شما در صف: {queue_position + 1}" if queue_position > 0 else "\n▶️ پردازش بلافاصله آغاز می‌شود."

        for item in cart:
            q_type = item['query_type']
            tracking_code = item['tracking_code']
            doc_category = item.get('doc_category')
            doc_subcategory = item.get('doc_subcategory')
            need_attachments = item.get('need_attachments', False)
            doc_name = f"{doc_category} - {doc_subcategory}" if doc_subcategory else doc_category

            await log_event(
                "پرداخت", q_type, full_name, user_id,
                tracking_code=tracking_code, doc_name=doc_name,
                payment_status="پرداخت شده (کیف پول بله)"
            )
            await runtime_state.job_queue.put({
                'user_id': user_id,
                'query_type': q_type,
                'tracking_code': tracking_code,
                'doc_category': doc_category,
                'doc_subcategory': doc_subcategory,
                'doc_type': doc_name,
                'need_attachments': need_attachments,
                'full_name': full_name,
                'payment_fee': item.get('fee', 0),
            })

        await message.answer(
            f"✅ پرداخت شما ثبت شد!\n\n"
            f"🛒 تعداد: {len(cart)} استعلام"
            f"{queue_note}\n\n"
            f"🔔 نتایج استعلام به صورت خودکار پردازش و ارسال می‌گردد.",
            reply_markup=restart_kb
        )

        # اطلاع‌رسانی به ادمین — بدون parse_mode
        try:
            items_detail = "\n".join(
                f"  • {it['query_type']} | کد: {it['tracking_code']} | "
                f"دسته: {it.get('doc_category','-')}" +
                (f" / {it.get('doc_subcategory')}" if it.get('doc_subcategory') else "") +
                (" | با پیوست" if it.get('need_attachments') else " | بدون پیوست")
                for it in cart
            )
            admin_msg = (
                f"💰 پرداخت سبد خرید از طریق کیف پول بله:\n"
                f"👤 کاربر: {full_name} ({user_id})\n"
                f"(برای پاسخ مستقیم: /send {user_id})\n"
                f"🛒 تعداد استعلام: {len(cart)} مورد\n"
                f"{items_detail}\n"
                f"💵 مجموع فاکتور: {total_fee:,} تومان\n"
                f"⏱ زمان: {datetime.datetime.now().strftime('%Y/%m/%d %H:%M')}\n"
                f"🎫 payment_id: {payment.telegram_payment_charge_id}"
            )
            logging.info(f"[PAYMENT] تلاش ارسال پیام به ادمین ADMIN_ID={ADMIN_ID} (نوع: {type(ADMIN_ID).__name__})")
            admin_result = await bot.send_message(ADMIN_ID, admin_msg)
            logging.info(f"[PAYMENT] اطلاع‌رسانی ادمین سبد خرید موفق. message_id={getattr(admin_result, 'message_id', '?')}")
        except Exception as e:
            logging.error(f"[PAYMENT] خطا در ارسال اطلاع به ادمین (ADMIN_ID={ADMIN_ID}): {e}", exc_info=True)

    elif data.get("bulk_inquiry_items"):
        # فلوی استعلام دسته‌جمعی (اکسل)
        # ⚠️ اصلاحیه: قبلاً این حالت اصلاً بررسی نمی‌شد — چون cart خالی بود،
        # پرداخت موفق استعلام دسته‌جمعی به شاخهٔ «تک‌موردی» زیر می‌افتاد که
        # query_type/tracking_code را از data می‌خواند (که برای این فلو
        # اصلاً پر نیستند، چون آیتم‌ها زیر کلید bulk_inquiry_items بودند نه
        # فیلدهای تخت) — نتیجه: یک job تقریباً خالی به صف اضافه می‌شد و همهٔ
        # آیتم‌های واقعی استعلام دسته‌جمعی هرگز پردازش نمی‌شدند.
        bulk_items = data.get("bulk_inquiry_items", [])
        total_fee = data.get('bulk_inquiry_total', 0)
        queue_position = runtime_state.job_queue.qsize()
        queue_note = f"\n📊 موقعیت شما در صف: {queue_position + 1}" if queue_position > 0 else "\n▶️ پردازش بلافاصله آغاز می‌شود."

        for item in bulk_items:
            q_type = item['query_type']
            tracking_code = item['tracking_code']
            doc_category = item.get('doc_category')
            doc_subcategory = item.get('doc_subcategory')
            need_attachments = item.get('need_attachments', False)
            doc_name = f"{doc_category} - {doc_subcategory}" if doc_subcategory else doc_category

            await log_event(
                "پرداخت", q_type, full_name, user_id,
                tracking_code=tracking_code, doc_name=doc_name,
                payment_status="پرداخت شده (کیف پول بله - دسته‌جمعی)"
            )
            await runtime_state.job_queue.put({
                'user_id': user_id,
                'query_type': q_type,
                'tracking_code': tracking_code,
                'doc_category': doc_category,
                'doc_subcategory': doc_subcategory,
                'doc_type': doc_name,
                'need_attachments': need_attachments,
                'full_name': full_name,
                'payment_fee': item.get('fee', 0),
            })

        await message.answer(
            f"✅ پرداخت شما ثبت شد!\n\n"
            f"🛒 تعداد: {len(bulk_items)} استعلام دسته‌جمعی"
            f"{queue_note}\n\n"
            f"🔔 نتایج استعلام به صورت خودکار پردازش و ارسال می‌گردد.",
            reply_markup=restart_kb
        )

        # اطلاع‌رسانی به ادمین — بدون parse_mode
        try:
            items_detail = "\n".join(
                f"  • {it['query_type']} | کد: {it['tracking_code']} | "
                f"دسته: {it.get('doc_category','-')}" +
                (f" / {it.get('doc_subcategory')}" if it.get('doc_subcategory') else "") +
                (" | با پیوست" if it.get('need_attachments') else " | بدون پیوست")
                for it in bulk_items
            )
            admin_msg = (
                f"💰 پرداخت استعلام دسته‌جمعی (اکسل) از طریق کیف پول بله:\n"
                f"👤 کاربر: {full_name} ({user_id})\n"
                f"(برای پاسخ مستقیم: /send {user_id})\n"
                f"🛒 تعداد استعلام: {len(bulk_items)} مورد\n"
                f"{items_detail}\n"
                f"💵 مجموع فاکتور: {total_fee:,} تومان\n"
                f"⏱ زمان: {datetime.datetime.now().strftime('%Y/%m/%d %H:%M')}\n"
                f"🎫 payment_id: {payment.telegram_payment_charge_id}"
            )
            admin_result = await bot.send_message(ADMIN_ID, admin_msg)
            logging.info(f"[PAYMENT] اطلاع‌رسانی ادمین استعلام دسته‌جمعی موفق. message_id={getattr(admin_result, 'message_id', '?')}")
        except Exception as e:
            logging.error(f"[PAYMENT] خطا در ارسال اطلاع به ادمین (ADMIN_ID={ADMIN_ID}): {e}", exc_info=True)

    else:
        # فلوی تک‌موردی
        fee = data.get('payment_fee', 0)
        query_type = data.get('query_type', '')
        tracking_code = data.get('tracking_code', '')
        doc_category = data.get('doc_category')
        doc_subcategory = data.get('doc_subcategory')
        need_attachments = data.get('need_attachments', False)
        doc_name = f"{doc_category} - {doc_subcategory}" if doc_subcategory else doc_category

        queue_position = runtime_state.job_queue.qsize()
        queue_note = f"\n📊 موقعیت شما در صف: {queue_position + 1}" if queue_position > 0 else "\n▶️ پردازش بلافاصله آغاز می‌شود."

        await log_event(
            "پرداخت", query_type, full_name, user_id,
            tracking_code=tracking_code, doc_name=doc_name,
            payment_status="پرداخت شده (کیف پول بله)"
        )
        await runtime_state.job_queue.put({
            'user_id': user_id,
            'query_type': query_type,
            'tracking_code': tracking_code,
            'doc_category': doc_category,
            'doc_subcategory': doc_subcategory,
            'doc_type': doc_name,
            'need_attachments': need_attachments,
            'full_name': full_name,
            'payment_fee': fee,
        })

        user_msg = f"✅ پرداخت شما ثبت شد!\n\n🔹 نوع: {query_type}\n"
        if tracking_code:
            user_msg += f"📋 کدرهگیری: {tracking_code}\n"
        user_msg += f"💰 مبلغ: {fee:,} تومان{queue_note}\n\n🔔 نتیجه استعلام به زودی ارسال می‌شود."
        await message.answer(user_msg, reply_markup=restart_kb)

        # اطلاع‌رسانی به ادمین — بدون parse_mode
        try:
            admin_msg = (
                f"💰 پرداخت تک‌موردی از طریق کیف پول بله:\n"
                f"👤 کاربر: {full_name} ({user_id})\n"
                f"(برای پاسخ مستقیم: /send {user_id})\n"
                f"🔹 نوع: {query_type}\n"
            )
            if tracking_code:
                admin_msg += f"📋 کدرهگیری: {tracking_code}\n"
            if doc_category:
                admin_msg += f"📂 دسته سند: {doc_category}"
                if doc_subcategory:
                    admin_msg += f" / {doc_subcategory}"
                admin_msg += "\n"
            admin_msg += f"📎 نیاز به پیوست: {'بله' if need_attachments else 'خیر'}\n"
            admin_msg += (
                f"💵 مبلغ: {fee:,} تومان\n"
                f"⏱ زمان: {datetime.datetime.now().strftime('%Y/%m/%d %H:%M')}\n"
                f"🎫 payment_id: {payment.telegram_payment_charge_id}"
            )
            logging.info(f"[PAYMENT] تلاش ارسال پیام به ادمین ADMIN_ID={ADMIN_ID} (نوع: {type(ADMIN_ID).__name__})")
            admin_result = await bot.send_message(ADMIN_ID, admin_msg)
            logging.info(f"[PAYMENT] اطلاع‌رسانی ادمین تک‌موردی موفق. message_id={getattr(admin_result, 'message_id', '?')}")
        except Exception as e:
            logging.error(f"[PAYMENT] خطا در ارسال اطلاع به ادمین (ADMIN_ID={ADMIN_ID}): {e}", exc_info=True)

    await state.clear()


# ================= هندلر global successful_payment — بدون فیلتر حالت (برای دیباگ بله) =================
@router.message(F.successful_payment)
async def global_successful_payment_handler(message: types.Message, state: FSMContext, bot: Bot):
    """هندلر سراسری — اگر بله successful_payment بفرسته ولی حالت FSM نامطبق باشن"""
    current_state = await state.get_state()
    logging.warning(f"[GLOBAL-PAYMENT] successful_payment دریافت شد. user={message.from_user.id}, state={current_state}")

    # ⭐ فاکتور «هزینه دستی مدیر» (/fee) — پردازش اختصاصی:
    # استعلام → فقط ثبت پرداخت؛ بقیه سرویس‌ها → ناوبری امضا شروع می‌شود
    try:
        _pl = _json.loads(getattr(message.successful_payment, "invoice_payload", "") or "{}")
    except Exception:
        _pl = {}
    if current_state == Form.admin_fee_waiting_payment or _pl.get("type") == "admin_fee":
        from admin_relay import admin_fee_successful_payment as _admin_fee_pay
        await _admin_fee_pay(message, state, bot)
        return

    # ── حالت‌های پرداخت لایحه/اظهارنامه — پردازش مستقیم (چون ممکن است روتر فرعی دریافت نکند) ──
    if current_state == Form.waiting_for_lavayeh_payment_receipt:
        from lavayeh_handlers import lavayeh_successful_payment as _lavayeh_pay
        await _lavayeh_pay(message, state, bot)
        return

    # ── پرداخت ارزش منطقه‌ای — پردازش مستقیم و خودکار ──
    if current_state == Form.rv_waiting_payment:
        from regional_value_handlers import regional_value_successful_payment as _rv_pay
        logging.info(f"[RV-PAY] successful_payment دریافت شد و به regional_value_successful_payment ارجاع داده شد. user={message.from_user.id}")
        await _rv_pay(message, state, bot)
        return

    # ── سایر حالت‌های اختصاصی — بدون مداخله ──
    if current_state in (Form.waiting_for_lavayeh_prepay,
                         Form.waiting_for_ezhhar_prepay,
                         Form.waiting_for_ealam_payment_receipt,
                         Form.stamp_calc_waiting_payment,
                         Form.bulk_prepay_wait,
                         Form.bulk_settlement_wait):
        return

    # ── پرداخت اشتراک ماهیانه ──
    if current_state and "subscription" in str(current_state).lower():
        user_id = message.from_user.id
        payment = message.successful_payment
        logging.info(f"[SUB-PAY-SUCCESS] پرداخت اشتراک موفق: user={user_id}, charge_id={payment.telegram_payment_charge_id}")

        # فعال‌سازی اشتراک
        runtime_state.activate_subscription(user_id)
        # همگام‌سازی با پنل ادمین
        try:
            async def _sync_sub():
                async with aiohttp.ClientSession() as s:
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
            reply_markup=get_flow_type_kb(message.from_user.id))
        await state.clear()
        return

    await successful_payment_handler(message, state, bot)


# ================= دکمه «پرداخت انجام شد» — حذف کامل =================
# ⛔ این دکمه و هندلرهای pay_done / pay_done_confirm / _process_pay_done
# به‌کلی حذف شدند چون اجازه می‌دادند کاربر *بدون پرداخت واقعی*، استعلام را
# به صف پردازش بیندازد (دور زدن پرداخت). تشخیص پرداخت از این پس «فقط» از
# طریق پیام successful_payment خود بله انجام می‌شود که پس از پرداخت موفق
# در کیف پول بله ارسال می‌گردد (هندلر successful_payment_handler بالا).
# برای اطمینان، اگر callback_data قدیمی pay_done از پیام‌های قبلی برسد،
# فقط پیام راهنما نشان داده می‌شود و هیچ پردازشی انجام نمی‌گیرد.
@router.callback_query(F.data.startswith("pay_done"))
async def pay_done_legacy_reject(callback: CallbackQuery):
    """دکمه قدیمی و حذف‌شده — بدون هیچ پردازشی رد می‌شود"""
    logging.warning(
        f"[PAY-DONE-REJECTED] کاربر {callback.from_user.id} دکمه حذف‌شده "
        f"'{callback.data}' را زد — پردازشی انجام نشد (پرداخت فقط توسط بله تایید می‌شود)"
    )
    await callback.answer(
        "⛔ این دکمه حذف شده است.\nپرداخت فقط از طریق فاکتور کیف پول بله انجام و "
        "به‌صورت خودکار توسط بله تایید می‌شود.", show_alert=True)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass



@router.callback_query(F.data == "pay_cancel")
async def pay_cancel_callback(callback: CallbackQuery, state: FSMContext):
    """کاربر انصراف از پرداخت"""
    await callback.answer()
    data = await state.get_data()
    cart = data.get("cart", [])
    await log_event(
        "کنسل", "پرداخت", callback.from_user.full_name, callback.from_user.id,
        tracking_code=None, doc_name=f"{len(cart)} مورد" if cart else None,
        payment_status="کنسل شده توسط کاربر (دکمه انصراف)"
    )
    await state.clear()
    await callback.message.answer(
        "لغو گردید. لطفاً مجدداً شروع کنید:",
        reply_markup=get_main_menu_kb(callback.from_user.id)
    )
    await state.set_state(Form.waiting_for_flow_type)


@router.message(Form.waiting_for_payment_receipt)
async def process_payment_receipt_text_only(message: types.Message, state: FSMContext):
    if not message.text:
        return
    if "انصراف" in message.text:
        data = await state.get_data()
        cart = data.get("cart", [])
        await log_event(
            "کنسل", "پرداخت", message.from_user.full_name, message.from_user.id,
            tracking_code=None, doc_name=f"{len(cart)} مورد" if cart else None,
            payment_status="کنسل شده توسط کاربر (مرحله پرداخت)"
        )
        await state.clear()
        await message.answer("لغو گردید. لطفاً مجدداً شروع کنید:", reply_markup=get_main_menu_kb(message.from_user.id))
        await state.set_state(Form.waiting_for_flow_type)
        return
    if "بازگشت" in message.text:
        await state.set_state(Form.main_menu)
        await message.answer(
            "🛒 لطفاً یکی از گزینه‌های زیر را انتخاب فرمایید:",
            reply_markup=cart_kb
        )
        return
    await message.answer("⚠️ لطفاً فاکتور ارسال‌شده را در چت پرداخت کنید.")


# ================= هندلرهای تایید/رد ثبت دسته‌جمعی توسط مدیر =================
@router.message(F.from_user.id == ADMIN_ID, F.text.startswith("/approve_bulk"))
async def admin_approve_bulk(message: types.Message, bot: Bot):
    """تایید درخواست ثبت دسته‌جمعی توسط مدیر"""
    from bulk_submissions import BULK_TASKS, run_bulk_processing_task
    import asyncio
    
    try:
        parts = message.text.split()
        if len(parts) < 2:
            await message.answer("⚠️ فرمت صحیح: `/approve_bulk #CODE-123456`")
            return
        
        tracking_code = parts[1]
        
        if tracking_code not in BULK_TASKS:
            await message.answer(f"⚠️ کد رهگیری `{tracking_code}` یافت نشد.")
            return
        
        task_data = BULK_TASKS[tracking_code]
        if task_data.get("status") != "pending_admin":
            await message.answer(f"⚠️ این درخواست قبلاً پردازش شده است. وضعیت: {task_data.get('status')}")
            return
        
        # تغییر وضعیت به در حال پردازش
        task_data["status"] = "processing"
        user_id = task_data.get("user_id")
        service_type = task_data.get("service_type", "lavayeh")
        service_fa = "لایحه" if service_type == "lavayeh" else "اظهارنامه"
        items = task_data.get("items", [])
        
        # ارسال پیام به کاربر
        try:
            await bot.send_message(
                user_id,
                f"✅ *درخواست ثبت دسته‌جمعی شما تایید شد!*\n\n"
                f"🔖 کد رهگیری: `{tracking_code}`\n"
                f"📦 تعداد موارد: *{len(items)} {service_fa}*\n\n"
                f"⏳ پردازش خودکار در پس‌زمینه آغاز شد. گزارش پیشرفت به صورت خودکار ارسال می‌شود.")
        except Exception as e:
            logging.error(f"Error notifying user about bulk approval: {e}")
        
        await message.answer(
            f"✅ *درخواست `{tracking_code}` تایید شد.*\n"
            f"پردازش پس‌زمینه آغاز شد.")
        
        # شروع پردازش پس‌زمینه
        asyncio.create_task(run_bulk_processing_task(bot, user_id, tracking_code))
        
    except Exception as e:
        logging.error(f"[ADMIN_APPROVE_BULK] خطا: {e}")
        await message.answer(f"⚠️ خطا در تایید درخواست: {e}")


@router.message(F.from_user.id == ADMIN_ID, F.text.startswith("/reject_bulk"))
async def admin_reject_bulk(message: types.Message, bot: Bot):
    """رد درخواست ثبت دسته‌جمعی توسط مدیر"""
    from bulk_submissions import BULK_TASKS
    
    try:
        parts = message.text.split(maxsplit=2)
        if len(parts) < 2:
            await message.answer("⚠️ فرمت صحیح: `/reject_bulk #CODE-123456 [دلیل رد]`")
            return
        
        tracking_code = parts[1]
        reason = parts[2] if len(parts) > 2 else "دلیل مشخص نشده"
        
        if tracking_code not in BULK_TASKS:
            await message.answer(f"⚠️ کد رهگیری `{tracking_code}` یافت نشد.")
            return
        
        task_data = BULK_TASKS[tracking_code]
        if task_data.get("status") != "pending_admin":
            await message.answer(f"⚠️ این درخواست قبلاً پردازش شده است. وضعیت: {task_data.get('status')}")
            return
        
        # تغییر وضعیت به رد شده
        task_data["status"] = "rejected"
        task_data["reject_reason"] = reason
        user_id = task_data.get("user_id")
        service_type = task_data.get("service_type", "lavayeh")
        service_fa = "لایحه" if service_type == "lavayeh" else "اظهارنامه"
        
        # ارسال پیام به کاربر
        try:
            await bot.send_message(
                user_id,
                f"❌ *درخواست ثبت دسته‌جمعی شما رد شد.*\n\n"
                f"🔖 کد رهگیری: `{tracking_code}`\n"
                f"📝 دلیل: {reason}\n\n"
                f"لطفاً اطلاعات را اصلاح کرده و مجدداً ارسال نمایید.")
        except Exception as e:
            logging.error(f"Error notifying user about bulk rejection: {e}")
        
        await message.answer(
            f"❌ *درخواست `{tracking_code}` رد شد.*\n"
            f"دلیل: {reason}")
        
    except Exception as e:
        logging.error(f"[ADMIN_REJECT_BULK] خطا: {e}")
        await message.answer(f"⚠️ خطا در رد درخواست: {e}")


# ================= بخش مکالمات تلگرام =================

# ================= دستورات مدیر: مشاهده و ادامه تسک‌های ناقص =================
@router.message(F.from_user.id == ADMIN_ID, F.text == "/incomplete_tasks")
async def admin_show_incomplete_tasks(message: types.Message, bot: Bot):
    """نمایش لیست تسک‌های ناقص با امکان ادامه"""
    tasks = runtime_state.incomplete_tasks
    if not tasks:
        await message.answer("✅ هیچ تسک ناقصی وجود ندارد.")
        return

    lines = ["📋 *تسک‌های ناقص:*\n"]
    for key, info in tasks.items():
        task_type = "اظهارنامه" if info["type"] == "ezhhar" else "لایحه"
        lines.append(
            f"🔢 کد: `{info['bill_no']}` | {task_type}\n"
            f"👤 کاربر: {info['user_id']}\n"
            f"📍 آخرین مرحله: {info['last_completed_step']}\n"
            f"▶️ ادامه از: {info['next_step']}\n"
            f"💡 `/resume {key}` برای ادامه\n"
        )

    await message.answer("\n".join(lines))


@router.message(F.from_user.id == ADMIN_ID, F.text.startswith("/logs"))
async def admin_upload_logs(message: types.Message, bot: Bot):
    """آپلود فایل لاگ به مدیر (آپلود مستمر خطاها).
    استفاده: `/logs` → فقط خطاها/هشدارها | `/logs all` → لاگ کامل"""
    from bug_reporter import upload_logs
    parts = message.text.strip().split(maxsplit=1)
    which = "all" if (len(parts) > 1 and parts[1].strip().lower() == "all") else "bugs"
    await message.answer(f"⏳ در حال آپلود لاگ «{'کامل' if which == 'all' else 'خطاها/هشدارها'}»...")
    ok = await upload_logs(bot, chat_id=message.chat.id, which=which)
    if not ok:
        await message.answer("ℹ️ لاگی برای ارسال نبود یا آپلود ناموفق شد.")


@router.message(F.from_user.id == ADMIN_ID, Command("rv_check"))
async def admin_rv_check(message: types.Message):
    """بررسی سلامت سرویس استعلام ارزش منطقه‌ای — فقط مدیر"""
    import subprocess, sys
    try:
        result = subprocess.run(
            [sys.executable, "admin_rv_check.py"],
            capture_output=True, text=True, timeout=60, cwd=os.path.dirname(os.path.abspath(__file__)))
        output = result.stdout + result.stderr
        # حداکثر ۴۰۰۰ کاراکتر برای بله
        if len(output) > 4000:
            output = output[:4000] + "\n... (متن کامل در لاگ)"
        msg_header = "🔍 *بررسی سلامت ارزش منطقه‌ای*\n\n"
        await message.answer(msg_header + "`" + output + "`")
    except Exception as e:
        await message.answer(f"❌ خطا در اجرای بررسی: {e}")

@router.message(F.from_user.id == ADMIN_ID, Command("resume"))
async def admin_resume_task(message: types.Message, bot: Bot):
    """مدیر می‌تواند ادامه تسک ناقص را از مرحله مشخص‌شده شروع کند"""
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("❌ لطفاً کد تسک را بفرستید:\n`/resume ezhhar:1400...` یا `/resume lavayeh:1400...`")
        return

    task_key = parts[1].strip()
    info = runtime_state.incomplete_tasks.get(task_key)

    if not info:
        await message.answer(f"❌ تسک `{task_key}` یافت نشد.\n`/incomplete_tasks` را ببینید.")
        return

    task_type = "اظهارنامه" if info["type"] == "ezhhar" else "لایحه"
    await message.answer(
        f"🔄 *ادامه تسک {task_type}*\n"
        f"🔢 کد رهگیری: `{info['bill_no']}`\n"
        f"👤 کاربر: {info['user_id']}\n"
        f"📍 ادامه از مرحله: *{info['next_step']}*\n\n"
        f"⏳ در حال شروع ادامه فرآیند...")

    # ارسال تسک به job_queue برای ادامه
    resume_data = {
        "action": "resume",
        "task_type": info["type"],
        "bill_no": info["bill_no"],
        "from_step": info["next_step"],
        "task_data": info["task_data"],
    }
    await runtime_state.job_queue.put(("resume", resume_data))
    logging.info(f"[ADMIN] مدیر ادامه تسک {task_key} را از مرحله {info['next_step']} شروع کرد.")

@router.message(StateFilter("*"), Command("fixbrowser"), F.from_user.id == ADMIN_ID)
async def cmd_fix_browser(message: types.Message, state: FSMContext):
    """
    دستور دستی ادمین برای بازسازی فوری مرورگر پلی‌رایت — بدون ری‌استارت
    کل ربات. معمولاً نیازی به این دستور نیست چون واچ‌داگ پس‌زمینه خودش
    خودکار تشخیص می‌دهد و بازسازی می‌کند؛ این فقط برای اطمینان/دستی است.
    """
    from scenarios import ensure_browser_alive, _is_browser_dead
    if not _is_browser_dead():
        await message.reply("✅ مرورگر سالم است؛ نیازی به بازسازی نیست.")
        return
    await message.reply("🔄 در حال بازسازی مرورگر... لطفاً منتظر درخواست لاگین بمانید.")
    ok = await ensure_browser_alive(message.bot, notify_admin=False)
    if ok:
        await message.reply("✅ مرورگر با موفقیت بازسازی شد.")
    else:
        await message.reply("❌ بازسازی مرورگر ناموفق بود؛ جزئیات در لاگ ثبت شد.")


@router.message(StateFilter("*"), F.from_user.id == ADMIN_ID, F.text == "✅ ورودم تکمیل شد")
async def confirm_login_from_admin_global(message: types.Message, state: FSMContext):
    if not runtime_state.login_event.is_set():
        runtime_state.login_event.set()
        await message.reply("✅ *لاگین تایید شد.*", reply_markup=ReplyKeyboardRemove())
    else:
        await message.reply("شما قبلاً تایید نموده‌اید.", reply_markup=ReplyKeyboardRemove())

@router.message(StateFilter("*"), Command("start"))
@router.message(StateFilter("*"), F.text == "🔄 ثبت درخواست جدید (شروع)")
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id

    # ── بررسی آیا کاربر در وضعیت disrupted (پرداخت شده ولی سامانه قطع) هست ──
    disrupted_info = runtime_state.disrupted_users.get(user_id)
    if disrupted_info:
        elapsed = datetime.datetime.now() - disrupted_info["timestamp"]
        if elapsed < datetime.timedelta(minutes=DISRUPTED_RETRY_MINUTES):
            remaining = DISRUPTED_RETRY_MINUTES - int(elapsed.total_seconds() / 60)
            await message.answer(
                f"⚠️ *شما یک استعلام پرداخت‌شده دارید که به‌دلیل اختلال سامانه کامل نشد.*\n\n"
                f"🔧 شما {remaining} دقیقه دیگر فرصت دارید بدون پرداخت مجدد، تلاش کنید.\n\n"
                f"آیا مایلید تلاش مجدد انجام دهید؟",
                reply_markup=disrupted_retry_kb)
            await state.set_state(Form.waiting_for_disrupted_retry)
            return
        else:
            # بازه‌ی ۴۵ دقیقه تمام شده
            del runtime_state.disrupted_users[user_id]

    # ── بررسی آیا ربات اخیراً کرش کرده (بازیابی) — با تفکیک ثبت‌شده/ثبت‌نشده ──
    if hasattr(runtime_state, '_crash_recovered_users'):
        if user_id in runtime_state._crash_recovered_users:
            recovery_type = runtime_state._crash_recovered_users[user_id]
            if recovery_type == "submitted":
                # کاربر درخواستش ثبت شده — اطمینان‌بخش
                await message.answer(
                    "🤖 *بابت اختلال پیش‌آمده در سامانه صمیمانه پوزش می‌طلبیم.*\n\n"
                    "درخواست شما قبلاً در سامانه ثبت شده و در حال پردازش است.\n"
                    "مطمئن باشید که موارد شما در روند ثبت قرار گرفته است.\n\n"
                    "در صورتی که تا ۴۵ دقیقه دیگر موارد شما ارسال نشد، لطفاً به شماره "
                    "09306186888 در بله یا واتس‌اپ پیام ارسال فرمایید.")
            else:
                # کاربر هنوز ثبت نکرده — عذرخواهی و درخواست تلاش مجدد
                await message.answer(
                    "🤖 *بابت اختلال پیش‌آمده در سامانه صمیمانه پوزش می‌طلبیم.*\n\n"
                    "متاسفانه فرآیند شما پیش از ثبت نهایی قطع شد.\n"
                    "لطفاً مجدداً از ابتدا اقدام فرمایید.\n"
                    "اگر قبلاً پرداخت کرده‌اید، فرصت تکرار بدون پرداخت به شما داده می‌شود.")
            # حذف از لیست بازیابی تا پیام تکرار نشود
            runtime_state._crash_recovered_users.pop(user_id, None)

    welcome_text = "با درود و احترام\n🟢 لطفاً پیش از هرگونه اقدام، آیین‌نامه را مطالعه فرمایید:\n🔗 https://forms.gle/UeevWfg5YiDkC5F37\n\n👇 آیا قوانین را تایید می‌نمایید؟"
    await message.answer(welcome_text, reply_markup=accept_rules_kb)
    await state.set_state(Form.waiting_for_rule_acceptance)


# هندلر ثبت درخواست جدید حذف شد — خطا در سامانه


# ================= هندلر تلاش مجدد بدون پرداخت (disrupted retry) =================
@router.message(Form.waiting_for_disrupted_retry)
async def process_disrupted_retry(message: types.Message, state: FSMContext, bot: Bot):
    """کاربر disrupted می‌تواند یک‌بار بدون پرداخت تلاش مجدد کند."""
    user_id = message.from_user.id

    if message.text and "انصراف" in message.text:
        del runtime_state.disrupted_users[user_id]
        await message.answer(
            "❌ درخواست تلاش مجدد لغو شد.\nلطفاً مجدداً شروع کنید:",
            reply_markup=get_main_menu_kb(message.from_user.id)
        )
        await state.set_state(Form.main_menu)
        return

    if message.text and "تلاش مجدد" in message.text:
        info = runtime_state.disrupted_users.get(user_id)
        if not info:
            await message.answer("⚠️ وضعیت تلاش مجدد یافت نشد. لطفاً از اول شروع کنید.", reply_markup=get_main_menu_kb(message.from_user.id))
            await state.set_state(Form.main_menu)
            return

        elapsed = datetime.datetime.now() - info["timestamp"]
        if elapsed >= datetime.timedelta(minutes=DISRUPTED_RETRY_MINUTES):
            del runtime_state.disrupted_users[user_id]
            await message.answer(
                f"⏰ بازه‌ی {DISRUPTED_RETRY_MINUTES} دقیقه‌ای تلاش مجدد تمام شده است.\n"
                f"لطفاً مجدداً شروع کنید:",
                reply_markup=get_main_menu_kb(message.from_user.id)
            )
            await state.set_state(Form.main_menu)
            return

        # تلاش مجدد — ارسال مجدد job به صف بدون نیاز به پرداخت
        job_data = info["job_data"]
        queue_pos = runtime_state.job_queue.qsize()
        queue_note = f"\n📊 موقعیت شما در صف: *{queue_pos + 1}*" if queue_pos > 0 else "\n▶️ پردازش بلافاصله آغاز می‌شود."

        await message.answer(
            f"🔄 *تلاش مجدد بدون پرداخت ...*\n{queue_note}",
            reply_markup=restart_kb)
        await runtime_state.job_queue.put(job_data)

        # حذف از disrupted — فقط یک‌بار اجازه تلاش مجدد
        del runtime_state.disrupted_users[user_id]
        await state.clear()

        # اطلاع به مدیر — بدون فرمت Markdown
        try:
            await bot.send_message(
                ADMIN_ID,
                f"🔄 تلاش مجدد disrupted:\n"
                f"👤 کاربر: {user_id}\n"
                f"کد رهگیری: {job_data.get('tracking_code', 'N/A')}\n"
                f"نوع: {job_data.get('query_type', 'N/A')}")
            logging.info(f"[DISRUPTED] اطلاع به مدیر ارسال شد.")
        except Exception as e:
            logging.error(f"[DISRUPTED] خطا در ارسال اطلاع به مدیر: {e}", exc_info=True)

@router.message(Form.waiting_for_rule_acceptance, F.text == "✅ قوانین و مقررات را تایید می‌نمایم")
async def rules_accepted(message: types.Message, state: FSMContext):
    await message.answer("❓ *لطفاً نحوه ثبت درخواست خود را انتخاب فرمایید:*", reply_markup=get_flow_type_kb(message.from_user.id))
    await state.set_state(Form.waiting_for_flow_type)

@router.message(Form.waiting_for_flow_type)
async def process_flow_type(message: types.Message, state: FSMContext):
    if not message.text: return
    if ("تک‌درخواست" in message.text or "تک درخواست" in message.text or ("استعلام" in message.text and "چند" not in message.text)):
        await state.update_data(flow_type="single", cart=[], full_name=message.from_user.full_name)
        await message.answer("سپاسگزاریم.\nلطفاً نوع خدمت را انتخاب نمایید:", reply_markup=main_menu_kb)
        await state.set_state(Form.main_menu)
    elif "چند مورد همزمان" in message.text or "سبد خرید" in message.text:
        await state.update_data(flow_type="cart", cart=[], full_name=message.from_user.full_name)
        await message.answer(
            "📦 *حالت استعلام چند موردی فعال شد.*\n"
            "لطفاً نوع استعلام اول خود را انتخاب نمایید:\n\n"
            "💡 اگر تعداد استعلام‌های شما بیش از ۵ مورد است، به‌جای وارد کردن "
            "تک‌به‌تک، گزینه‌ی «4️⃣ استعلام دسته‌جمعی (فایل اکسل)» را انتخاب کنید.",
            reply_markup=cart_main_menu_kb)
        await state.set_state(Form.main_menu)
    elif "ثبت لایحه" in message.text:
        from lavayeh_handlers import lavayeh_entry
        await lavayeh_entry(message, state)
    elif "ثبت اظهارنامه" in message.text:
        from ezhharnameh_handlers import ezhharnameh_entry
        await ezhharnameh_entry(message, state)
    elif "محاسبه تمبر" in message.text:
        from stamp_calc_handlers import stamp_calc_entry
        await stamp_calc_entry(message, state)
    elif "دعاوی اعتراضی" in message.text:
        if message.from_user.id != ADMIN_ID:
            await message.answer(
                "⏳ *بخش دعاوی اعتراضی در حال توسعه است.*\n\n"
                "این سرویس به‌زودی برای استفاده عمومی فعال خواهد شد.\n"
                "برای پیگیری اخبار به کانال ما مراجعه کنید:\n"
                "https://ble.ir/onlinejudicialservice",
                reply_markup=get_main_menu_kb(message.from_user.id))
            return
        from tajdid_nazar_handlers import tajdid_nazar_entry
        await tajdid_nazar_entry(message, state)
    elif "دادخواست چک" in message.text:
        if message.from_user.id != ADMIN_ID:
            await message.answer(
                "⏳ *بخش ثبت دادخواست چک در حال توسعه است.*\n\n"
                "این سرویس به‌زودی برای استفاده عمومی فعال خواهد شد.\n"
                "برای پیگیری اخبار به کانال ما مراجعه کنید:\n"
                "https://ble.ir/onlinejudicialservice",
                reply_markup=get_main_menu_kb(message.from_user.id))
            return
        from check_handlers import check_entry
        await check_entry(message, state)
    elif "ارزش منطقه‌ای" in message.text:
        from regional_value_handlers import regional_value_entry
        await regional_value_entry(message, state)
    elif "ابزار فایل" in message.text:
        await file_tools_entry(message, state)
    elif "تست" in message.text and message.from_user.id == TEST_VISIBLE_USER_ID:
        await message.answer(
            "🧪 *حالت تست مدیر*\n\n"
            "برای جلوگیری از ایجاد کدرهگیری اضافی در سامانه، مستقیماً به بخش مورد نظر می‌روید.\n\n"
            "لطفاً کدرهگیری را جهت ثبت وارد کنید:",
            reply_markup=back_only_kb)
        await state.set_state(Form.test_mode_tracking_code)

async def _show_cart(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cart = data.get("cart", [])
    if not cart:
        await message.answer("🛒 سبد شما خالی است.", reply_markup=get_main_menu_kb(message.from_user.id))
        return

    cart_text = "🛒 *سبد استعلام‌های شما:*\n\n"
    total_sum = 0
    for idx, item in enumerate(cart):
        q_type = item['query_type']
        code = item['tracking_code']
        fee = item['fee']

        if q_type == "شماره تماس":
            desc = f"📞 استعلام شماره همراه `{code}`"
        elif q_type == "کد ملی":
            desc = f"👤 استعلام کد ملی `{code}`"
        else:
            att_desc = f" (همراه با {item['total_attachments']} پیوست)" if item['need_attachments'] else " (بدون پیوست)"
            desc = f"📄 کدرهگیری `{code}`" + att_desc

        cart_text += f"{idx+1}. {desc} — *{fee:,} تومان*\n"
        total_sum += fee

    cart_text += f"\n💰 *مجموع: {total_sum:,} تومان*"
    await message.answer(cart_text, reply_markup=pay_kb)


@router.message(Form.main_menu)
async def process_main_menu(message: types.Message, state: FSMContext):
    if not message.text: return
    
    if "🔙 بازگشت به منوی اصلی" in message.text:
        await message.answer("❓ *لطفاً نحوه ثبت درخواست خود را انتخاب فرمایید:*", reply_markup=get_flow_type_kb(message.from_user.id))
        await state.set_state(Form.waiting_for_flow_type)
        return

    if "تست" in message.text and message.from_user.id == TEST_VISIBLE_USER_ID:
        await message.answer(
            "🧪 *حالت تست مدیر*\n\n"
            "برای جلوگیری از ایجاد کدرهگیری اضافی در سامانه، مستقیماً به بخش مورد نظر می‌رویم.\n\n"
            "لطفاً کدرهگیری را جهت ثبت وارد کنید:",
            reply_markup=back_only_kb)
        await state.set_state(Form.test_mode_tracking_code)
        return

    if "➕ ثبت استعلام جدید" in message.text:
        await message.answer("لطفاً نوع خدمت جدید را انتخاب نمایید:", reply_markup=main_menu_kb)
        return
        
    elif "🧹 خالی کردن سبد" in message.text:
        await state.update_data(cart=[])
        await message.answer("🧹 سبد استعلام‌های شما خالی شد.", reply_markup=main_menu_kb)
        return
        
    elif "📊 استعلام دسته‌جمعی" in message.text:
        await _bulk_inquiry_start(message, state)
        return
        
    elif "🛒 مشاهده سبد خرید" in message.text:
        await _show_cart(message, state)
        return
        
    elif "❌ انصراف" in message.text:
        await state.update_data(cart=[])
        await state.clear()
        await message.answer("❌ انصراف از سبد خرید. لطفاً مجدداً شروع کنید:", reply_markup=get_main_menu_kb(message.from_user.id))
        await state.set_state(Form.waiting_for_flow_type)
        return
        
    elif "💳 پرداخت و تسویه حساب" in message.text:
        data = await state.get_data()
        cart = data.get("cart", [])
        if not cart:
            await message.answer("🛒 سبد خرید شما خالی است.", reply_markup=get_main_menu_kb(message.from_user.id))
            return

        # بررسی معافیت از پرداخت
        if await is_exempt_user(message.from_user.id):
            total_sum = sum(item['fee'] for item in cart)
            await state.update_data(total_payment_sum=total_sum)
            queue_position = runtime_state.job_queue.qsize()
            queue_note = f"\n📊 موقعیت شما در صف: *{queue_position + 1}*" if queue_position > 0 else "\n▶️ پردازش بلافاصله آغاز می‌شود."
            await message.answer(
                f"✅ *معافیت از پرداخت*\n\n"
                f"شما در لیست کاربران معاف هستید."
                f"\nتعداد {len(cart)} استعلام در صف پردازش قرار گرفت.{queue_note}",
                reply_markup=restart_kb
            )
            for item in cart:
                await log_event(
                    "پرداخت", item['query_type'], message.from_user.full_name, message.from_user.id,
                    tracking_code=item['tracking_code'],
                    doc_name=f"{item.get('doc_category')} - {item.get('doc_subcategory')}" if item.get('doc_subcategory') else item.get('doc_category'),
                    payment_status="معاف از پرداخت"
                )
                await runtime_state.job_queue.put({
                    'user_id': message.from_user.id,
                    'query_type': item['query_type'],
                    'tracking_code': item['tracking_code'],
                    'doc_category': item.get('doc_category'),
                    'doc_subcategory': item.get('doc_subcategory'),
                    'doc_type': f"{item.get('doc_category')} - {item.get('doc_subcategory')}" if item.get('doc_subcategory') else item.get('doc_category'),
                    'need_attachments': item.get('need_attachments', False),
                    'full_name': message.from_user.full_name,
                    'payment_fee': item.get('fee', 0),
                })
            await state.clear()
            return

        total_sum = sum(item['fee'] for item in cart)
        await state.update_data(total_payment_sum=total_sum)

        # ═══ ارسال فاکتور بله با استفاده از sendInvoice API ═══
        total_rial = total_sum * 10  # تومان به ریال
        try:
            invoice_payload = _json.dumps({"type": "cart", "uid": message.from_user.id})
            async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
                invoice_url = f"{BALE_API_BASE}/bot{BOT_TOKEN}/sendInvoice"
                invoice_data = {
                    "chat_id": message.from_user.id,
                    "title": "فاکتور سبد خرید",
                    "description": f"مجموع سبد خرید: {total_sum:,} تومان ({total_rial:,} ریال)",
                    "payload": invoice_payload,
                    "provider_token": BALE_WALLET_TOKEN,
                    "currency": "IRR",
                    "prices": [{"label": f"{len(cart)} استعلام", "amount": total_rial}],
                }
                logging.info(f"[CART-PAY] ارسال sendInvoice به chat_id={message.from_user.id}, مبلغ={total_rial:,} ریال")
                async with session.post(invoice_url, json=invoice_data) as resp:
                    result = await resp.json()
                    logging.info(f"[CART-PAY] پاسخ sendInvoice: {result}")
                    if not result.get("ok"):
                        logging.error(f"[CART-PAY] خطای sendInvoice: {result}")
                        raise Exception(result.get("description", "خطا در ارسال فاکتور"))
        except Exception as e:
            logging.error(f"[CART-PAY] خطا در ارسال فاکتور: {e}", exc_info=True)
            await message.answer("⚠️ خطا در ساخت فاکتور. لطفاً کمی بعد دوباره تلاش کنید.")
            return

        # ⛔ دکمه «پرداخت انجام شد» حذف شد — پرداخت فقط توسط بله (successful_payment)
        # تایید می‌شود؛ کاربر صرفاً می‌تواند انصراف دهد.
        pay_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ انصراف", callback_data="pay_cancel")],
        ])
        warning = ""
        if message.from_user.id == ADMIN_ID:
            warning = (
                "\n\n⚠️ _توجه: اگر کیف پول خودتان را شارژ کرده‌اید و اکنون می‌خواهید "
                "از همان کیف پول پرداخت کنید، پرداخت انجام نخواهد شد (خطای مبدأ و مقصد یکسان). "
                "لطفاً با یک حساب بله دیگر تست کنید._\n\n"
            )
        await message.answer(
            f"⏳ فاکتور ارسال شد."
            f"{warning}"
            f"پس از پرداخت موفق در کیف پول بله، استعلام‌ها به‌صورت خودکار پردازش می‌شوند.\n"
            f"💳 پرداخت را در همان فاکتور انجام دهید — تایید پرداخت فقط توسط خود بله صورت می‌گیرد.",
            reply_markup=pay_kb
        )
        await state.set_state(Form.waiting_for_payment_receipt)
        return
        
    elif "🔙 بازگشت" in message.text:
        await message.answer(
            "🛒 لطفاً یکی از گزینه‌های زیر را انتخاب فرمایید:",
            reply_markup=cart_kb
        )
        return
        
    if "1️⃣" in message.text:
        await message.answer("لطفاً کد رهگیری خود را ارسال فرمایید:", reply_markup=back_only_kb)
        await state.set_state(Form.waiting_for_tracking_code)
    elif "2️⃣" in message.text:
        await message.answer("📞 لطفاً شماره تماس مورد نظر را ارسال فرمایید:\n(با فرمت 09 آغاز شود)", reply_markup=back_only_kb)
        await state.set_state(Form.waiting_for_phone_number)
    elif "3️⃣" in message.text:
        await message.answer("👤 لطفاً کد ملی مورد نظر را ارسال فرمایید:\n(یک عدد ۱۰ رقمی)", reply_markup=back_only_kb)
        await state.set_state(Form.waiting_for_national_id)
    elif "4️⃣" in message.text or "استعلام دسته‌جمعی" in message.text:
        await _bulk_inquiry_start(message, state)

@router.message(Form.waiting_for_tracking_code)
async def process_tracking_code(message: types.Message, state: FSMContext):
    if not message.text: return
    if message.text == "🔙 بازگشت":
        await message.answer("لطفاً نوع خدمت را انتخاب نمایید:", reply_markup=get_main_menu_kb(message.from_user.id))
        await state.set_state(Form.main_menu)
        return
    clean_code = message.text.translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')).replace(" ", "").strip()
    if not re.match(r'^[0-9]+$', clean_code):
        await message.answer("⚠️ فرمت نامعتبر است. فقط عدد ارسال کنید:")
        return
    if not _is_valid_tracking_code(clean_code):
        await message.answer(
            "⚠️ کد رهگیری نامعتبر است.\n"
            "کد رهگیری باید ۱۶ رقم باشد و با یکی از سال‌های ۱۳۹۴ تا ۱۴۰۶ (یعنی اعداد ۱۳۹۴۲۲۰ الی ۱۴۰۶۲۲۰) شروع شود.\n"
            "لطفاً کد را دوباره بررسی و ارسال فرمایید:"
        )
        return
    # ── بررسی محدودیت تلاش قبل از ادامه ──
    if _check_inquiry_limit(message.from_user.id):
        await message.answer(
            f"❌ {SAMANEH_WRONG_TYPE_ERROR}\n\n"
            f"⚠️ *تعداد دفعات تلاش شما به حداکثر ({MAX_INQUIRY_ATTEMPTS} بار) رسیده است.*\n\n"
            f"لطفاً کدرهگیری و نوع سند (لایحه، اظهارنامه، شکواییه و ...) را به‌دقت بررسی فرمایید و مجدداً از منوی اصلی شروع کنید.",
            reply_markup=get_main_menu_kb(message.from_user.id))
        await state.clear()
        return
    # پاکسازی شمارنده‌ها وقتی کاربر کد معتبر وارد می‌کند
    _reset_inquiry_attempts(message.from_user.id)
    await state.update_data(query_type="کد رهگیری", tracking_code=clean_code)
    await message.answer("مربوط به کدام دسته است؟", reply_markup=doc_category_kb)
    await state.set_state(Form.waiting_for_doc_category)

@router.message(Form.waiting_for_doc_category)
async def process_doc_category(message: types.Message, state: FSMContext):
    category = message.text
    if category == "🔙 بازگشت به منوی قبل" or category == "🔙 بازگشت":
        await message.answer("کد رهگیری را ارسال کنید:", reply_markup=back_only_kb)
        await state.set_state(Form.waiting_for_tracking_code)
        return
    await state.update_data(doc_category=category)
    if category in SUB_MENUS:
        await message.answer(f"نوع دقیق «{category}» را مشخص کنید:", reply_markup=create_submenu_kb(category))
        await state.set_state(Form.waiting_for_doc_subcategory)
    else:
        await state.update_data(doc_subcategory=None)
        await message.answer("📋 آیا نیاز به دریافت فایل‌های پیوست (منضمات) دارید؟", reply_markup=attachments_kb)
        await state.set_state(Form.waiting_for_attachments_opt)

@router.message(Form.waiting_for_doc_subcategory)
async def process_doc_subcategory(message: types.Message, state: FSMContext):
    if message.text == "🔙 بازگشت به منوی قبل":
        await message.answer("دسته‌بندی اصلی را انتخاب کنید:", reply_markup=doc_category_kb)
        await state.set_state(Form.waiting_for_doc_category)
        return
    await state.update_data(doc_subcategory=message.text)
    await message.answer("📋 آیا نیاز به دریافت فایل‌های پیوست (منضمات) دارید؟", reply_markup=attachments_kb)
    await state.set_state(Form.waiting_for_attachments_opt)

@router.message(Form.waiting_for_attachments_opt)
async def process_attachments_opt(message: types.Message, state: FSMContext):
    if not message.text: return
    if message.text == "🔙 بازگشت":
        data = await state.get_data()
        category = data.get('doc_category', '')
        if category in SUB_MENUS:
            await message.answer(f"نوع دقیق «{category}» را مشخص کنید:", reply_markup=create_submenu_kb(category))
            await state.set_state(Form.waiting_for_doc_subcategory)
        else:
            await message.answer("مربوط به کدام دسته است؟", reply_markup=doc_category_kb)
            await state.set_state(Form.waiting_for_doc_category)
        return
    need_attachments = "بله" in message.text
    await state.update_data(need_attachments=need_attachments)
    
    data = await state.get_data()
    flow_type = data.get('flow_type', 'single')
    
    if need_attachments:
        await message.answer("⏳ در حال استعلام تعداد پیوست‌های پرونده... لطفاً صبور باشید.", reply_markup=ReplyKeyboardRemove())
        
        doc_name = data.get('doc_subcategory') or data['doc_category']
        flow_type = data.get('flow_type', 'single')
        
        # ── تلاش سریع (خارج از صف) ──────────────────────────────
        fast_success = False
        try:
            total_attachments_count = await fast_pre_check(
                tracking_code=data['tracking_code'],
                category=data['doc_category'],
                subcategory=data.get('doc_subcategory'),
                user_id=message.from_user.id,
                bot=message.bot
            )
            fast_success = True
        except FastPetitionNotFoundError:
            attempts = _record_failed_inquiry(message.from_user.id)
            if attempts >= MAX_INQUIRY_ATTEMPTS:
                await message.answer(
                    f"❌ {SAMANEH_WRONG_TYPE_ERROR}\n\n"
                    f"⚠️ *تعداد دفعات تلاش شما به حداکثر ({MAX_INQUIRY_ATTEMPTS} بار) رسیده است.*\n\n"
                    f"لطفاً کدرهگیری و نوع سند (لایحه، اظهارنامه، شکواییه و ...) را به‌دقت بررسی فرمایید و مجدداً از منوی اصلی شروع کنید.",
                    reply_markup=get_main_menu_kb(message.from_user.id))
                await state.clear()
            else:
                remaining = MAX_INQUIRY_ATTEMPTS - attempts
                await message.answer(
                    f"❌ پرونده‌ای با کد `{data['tracking_code']}` یافت نگردید.\n\n"
                    f"⚠️ لطفاً کدرهگیری و نوع سند خود را بررسی کنید.\n"
                    f"(تلاش {attempts} از {MAX_INQUIRY_ATTEMPTS})")
            return
        except FastInvalidTrackingCodeError:
            attempts = _record_failed_inquiry(message.from_user.id)
            if attempts >= MAX_INQUIRY_ATTEMPTS:
                await message.answer(
                    f"❌ {SAMANEH_WRONG_TYPE_ERROR}\n\n"
                    f"⚠️ *تعداد دفعات تلاش شما به حداکثر ({MAX_INQUIRY_ATTEMPTS} بار) رسیده است.*\n\n"
                    f"لطفاً کدرهگیری و نوع سند (لایحه، اظهارنامه، شکواییه و ...) را به‌دقت بررسی فرمایید و مجدداً از منوی اصلی شروع کنید.",
                    reply_markup=get_main_menu_kb(message.from_user.id))
                await state.clear()
            else:
                remaining = MAX_INQUIRY_ATTEMPTS - attempts
                await message.answer(
                    f"❌ کدرهگیری یا نوع خدمت را اشتباه وارد نموده‌اید.\n\n"
                    f"⚠️ لطفاً کدرهگیری و نوع سند خود را بررسی کنید.\n"
                    f"(تلاش {attempts} از {MAX_INQUIRY_ATTEMPTS})")
            return
        except FastSessionExpiredError:
            logger.warning("[FAST-CHECK] نشست منقضی — فال‌بک به صف مرورگر")
        except FastCheckError as e:
            logger.warning(f"[FAST-CHECK] شکست: {e} — فال‌بک به صف مرورگر")
        
        if fast_success:
            # ✅ استعلام سریع موفق — نمایش فاکتور بدون صف
            calculated_fee = FEES["کد رهگیری با منضمات"] + total_attachments_count * 5000
            await state.update_data(
                payment_fee=calculated_fee,
                need_attachments=True,
                total_attachments=total_attachments_count
            )
            
            kb = confirm_single_kb if flow_type == "single" else confirm_cart_kb
            action_text = (
                "تایید نهایی و دریافت فاکتور پرداخت"
                if flow_type == "single"
                else "تایید و افزودن این مورد به سبد خرید"
            )
            
            confirm_msg = (
                f"📋 *اطلاعات استعلام با منضمات:*\n\n"
                f"کد پیگیری: `{data['tracking_code']}`\n"
                f"سند: *{doc_name}*\n"
                f"📎 تعداد پیوست: *{total_attachments_count} برگ*\n"
                f"💰 فاکتور: ۵۰,۰۰۰ + ({total_attachments_count} × ۵,۰۰۰) = *{calculated_fee:,} تومان*\n\n"
                f"آیا {action_text} فرمایید؟"
            )
            await message.answer(confirm_msg, reply_markup=kb)
            await state.set_state(Form.confirm_opt)
        else:
            # ❌ فال‌بک به روش قبلی (صف مرورگر)
            logger.info("[FAST-CHECK] فال‌بک به job_queue برای PRE_CHECK")
            await runtime_state.job_queue.put({
                'user_id': message.from_user.id,
                'query_type': data['query_type'],
                'task_type': 'PRE_CHECK',
                'tracking_code': data['tracking_code'],
                'doc_category': data['doc_category'],
                'doc_subcategory': data.get('doc_subcategory')
            })
    else:
        doc_name = f"{data['doc_category']} - {data['doc_subcategory']}" if data.get('doc_subcategory') else data['doc_category']
        fee = get_fee("کد رهگیری", False)
        await state.update_data(payment_fee=fee)
        
        kb = confirm_single_kb if flow_type == "single" else confirm_cart_kb
        action_text = "تایید نهایی و دریافت فاکتور پرداخت" if flow_type == "single" else "تایید و افزودن این مورد به سبد خرید"
        
        await message.answer(
            f"📋 *مشخصات استعلام (بدون پیوست):*\n\n"
            f"کد پیگیری: `{data['tracking_code']}`\n"
            f"سند: *{doc_name}*\n"
            f"💰 هزینه: *{fee:,} تومان*\n\n"
            f"آیا مایلید این درخواست را {action_text} فرمایید؟",
            reply_markup=kb)
        await state.set_state(Form.confirm_opt)

@router.message(Form.waiting_for_phone_number)
async def process_phone_number(message: types.Message, state: FSMContext):
    if not message.text: return
    if message.text == "🔙 بازگشت":
        await message.answer("لطفاً نوع خدمت را انتخاب نمایید:", reply_markup=get_main_menu_kb(message.from_user.id))
        await state.set_state(Form.main_menu)
        return
    clean_phone = message.text.translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')).replace(" ", "").strip()
    if not re.match(r'^09[0-9]{9}$', clean_phone):
        await message.answer("⚠️ شماره نامعتبر است (مثال: 09123456789):")
        return
    
    fee = get_fee("شماره تماس", False)
    await state.update_data(payment_fee=fee, query_type="شماره تماس", tracking_code=clean_phone, doc_category="شماره تماس", doc_subcategory=None, need_attachments=False)
    
    data = await state.get_data()
    flow_type = data.get('flow_type', 'single')
    kb = confirm_single_kb if flow_type == "single" else confirm_cart_kb
    action_text = "تایید نهایی و دریافت فاکتور پرداخت" if flow_type == "single" else "تایید و افزودن این مورد به سبد خرید"
    
    await message.answer(
        f"📋 *مشخصات استعلام شماره تماس:*\n\n"
        f"📞 شماره همراه: `{clean_phone}`\n"
        f"💰 هزینه: *{fee:,} تومان*\n\n"
        f"آیا مایلید این درخواست را {action_text} فرمایید؟",
        reply_markup=kb)
    await state.set_state(Form.confirm_opt)

@router.message(Form.waiting_for_national_id)
async def process_national_id(message: types.Message, state: FSMContext):
    if not message.text: return
    if message.text == "🔙 بازگشت":
        await message.answer("لطفاً نوع خدمت را انتخاب نمایید:", reply_markup=get_main_menu_kb(message.from_user.id))
        await state.set_state(Form.main_menu)
        return
    clean_id = message.text.translate(str.maketrans('۰۱۲۳۴۵6۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')).replace(" ", "").strip()
    if not re.match(r'^[0-9]{10}$', clean_id):
        await message.answer("⚠️ کد ملی نامعتبر است. لطفاً یک عدد ۱۰ رقمی وارد نمایید:")
        return
    
    fee = get_fee("کد ملی", False)
    await state.update_data(payment_fee=fee, query_type="کد ملی", tracking_code=clean_id, doc_category="کد ملی", doc_subcategory=None, need_attachments=False)
    
    data = await state.get_data()
    flow_type = data.get('flow_type', 'single')
    kb = confirm_single_kb if flow_type == "single" else confirm_cart_kb
    action_text = "تایید نهایی و دریافت فاکتور پرداخت" if flow_type == "single" else "تایید و افزودن این مورد به سبد خرید"
    
    await message.answer(
        f"📋 *مشخصات استعلام کد ملی:*\n\n"
        f"👤 کد ملی: `{clean_id}`\n"
        f"💰 هزینه: *{fee:,} تومان*\n\n"
        f"آیا مایلید این درخواست را {action_text} فرمایید؟",
        reply_markup=kb)
    await state.set_state(Form.confirm_opt)

@router.message(Form.confirm_opt)
async def confirm_opt_process(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    flow_type = data.get('flow_type', 'single')
    
    if "تایید و دریافت فاکتور" in message.text:
        fee = data.get('payment_fee', 0)
        await state.update_data(total_payment_sum=fee)
        
        item = {
            'query_type': data.get('query_type'),
            'tracking_code': data.get('tracking_code'),
            'doc_category': data.get('doc_category'),
            'doc_subcategory': data.get('doc_subcategory'),
            'need_attachments': data.get('need_attachments', False),
            'fee': fee,
            'total_attachments': data.get('total_attachments', 0)
        }
        await state.update_data(cart=[item])

        # بررسی معافیت از پرداخت (تک‌موردی)
        if await is_exempt_user(message.from_user.id):
            queue_position = runtime_state.job_queue.qsize()
            queue_note = f"\n📊 موقعیت شما در صف: *{queue_position + 1}*" if queue_position > 0 else "\n▶️ پردازش بلافاصله آغاز می‌شود."
            await message.answer(
                f"✅ *معافیت از پرداخت*\n\n"
                f"شما در لیست کاربران معاف هستید."
                f"\nاستعلام در صف پردازش قرار گرفت.{queue_note}",
                reply_markup=restart_kb
            )
            await log_event(
                "پرداخت", data.get('query_type'), message.from_user.full_name, message.from_user.id,
                tracking_code=data.get('tracking_code'),
                doc_name=f"{data.get('doc_category')} - {data.get('doc_subcategory')}" if data.get('doc_subcategory') else data.get('doc_category'),
                payment_status="معاف از پرداخت"
            )
            await runtime_state.job_queue.put({
                'user_id': message.from_user.id,
                'query_type': data.get('query_type'),
                'tracking_code': data.get('tracking_code'),
                'doc_category': data.get('doc_category'),
                'doc_subcategory': data.get('doc_subcategory'),
                'doc_type': f"{data.get('doc_category')} - {data.get('doc_subcategory')}" if data.get('doc_subcategory') else data.get('doc_category'),
                'need_attachments': data.get('need_attachments', False),
                'full_name': message.from_user.full_name,
                'payment_fee': fee,
            })
            await state.clear()
            return

        # ═══ ارسال فاکتور بله با استفاده از sendInvoice API ═══
        fee_rial = fee * 10  # تومان به ریال
        try:
            invoice_payload = _json.dumps({"type": "single", "uid": message.from_user.id})
            async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
                invoice_url = f"{BALE_API_BASE}/bot{BOT_TOKEN}/sendInvoice"
                invoice_data = {
                    "chat_id": message.from_user.id,
                    "title": f"فاکتور {data.get('query_type', 'استعلام')}",
                    "description": f"استعلام {data.get('query_type', '')}: {fee:,} تومان ({fee_rial:,} ریال)",
                    "payload": invoice_payload,
                    "provider_token": BALE_WALLET_TOKEN,
                    "currency": "IRR",
                    "prices": [{"label": data.get('query_type', 'استعلام'), "amount": fee_rial}],
                }
                logging.info(f"[SINGLE-PAY] ارسال sendInvoice به chat_id={message.from_user.id}, مبلغ={fee_rial:,} ریال")
                async with session.post(invoice_url, json=invoice_data) as resp:
                    result = await resp.json()
                    logging.info(f"[SINGLE-PAY] پاسخ sendInvoice: {result}")
                    if not result.get("ok"):
                        logging.error(f"[SINGLE-PAY] خطای sendInvoice: {result}")
                        raise Exception(result.get("description", "خطا در ارسال فاکتور"))
        except Exception as e:
            logging.error(f"[SINGLE-PAY] خطا در ارسال فاکتور: {e}", exc_info=True)
            await message.answer("⚠️ خطا در ساخت فاکتور. لطفاً کمی بعد دوباره تلاش کنید.")
            return

        # ⛔ دکمه «پرداخت انجام شد» حذف شد — پرداخت فقط توسط بله (successful_payment)
        # تایید می‌شود؛ کاربر صرفاً می‌تواند انصراف دهد.
        pay_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ انصراف", callback_data="pay_cancel")],
        ])
        warning = ""
        if message.from_user.id == ADMIN_ID:
            warning = (
                "\n\n⚠️ _توجه: اگر کیف پول خودتان را شارژ کرده‌اید و اکنون می‌خواهید "
                "از همان کیف پول پرداخت کنید، پرداخت انجام نخواهد شد (خطای مبدأ و مقصد یکسان). "
                "لطفاً با یک حساب بله دیگر تست کنید._\n\n"
            )
        await message.answer(
            f"⏳ فاکتور ارسال شد."
            f"{warning}"
            f"پس از پرداخت موفق در کیف پول بله، استعلام به‌صورت خودکار پردازش می‌شود.\n"
            f"💳 پرداخت را در همان فاکتور انجام دهید — تایید پرداخت فقط توسط خود بله صورت می‌گیرد.",
            reply_markup=pay_kb
        )
        await state.set_state(Form.waiting_for_payment_receipt)
        
    elif "افزودن به سبد خرید" in message.text:
        cart = data.get("cart", [])
        
        item = {
            'query_type': data.get('query_type'),
            'tracking_code': data.get('tracking_code'),
            'doc_category': data.get('doc_category'),
            'doc_subcategory': data.get('doc_subcategory'),
            'need_attachments': data.get('need_attachments', False),
            'fee': data.get('payment_fee', 0),
            'total_attachments': data.get('total_attachments', 0)
        }
        
        cart.append(item)
        await state.update_data(cart=cart)
        await state.update_data(
            query_type=None, tracking_code=None, doc_category=None, 
            doc_subcategory=None, need_attachments=None, payment_fee=None, total_attachments=None
        )
        
        await message.answer(
            f"🛒 *به سبد خرید اضافه شد!*\n"
            f"تعداد: *{len(cart)} مورد*\n\n"
            f"لطفاً یکی از گزینه‌های زیر را انتخاب فرمایید:",
            reply_markup=cart_kb
        )
        await state.set_state(Form.main_menu)
        
    elif "انصراف و اصلاح" in message.text:
        q_type = data.get('query_type')
        doc_category = data.get('doc_category')
        doc_subcategory = data.get('doc_subcategory')
        doc_name = f"{doc_category} - {doc_subcategory}" if doc_subcategory else doc_category
        await log_event(
            "کنسل", q_type, message.from_user.full_name, message.from_user.id,
            tracking_code=data.get('tracking_code'), doc_name=doc_name,
            payment_status="کنسل شده توسط کاربر (قبل از پرداخت)"
        )
        await message.answer("لغو گردید. لطفاً مجدداً شروع کنید:", reply_markup=get_main_menu_kb(message.from_user.id))
        await state.set_state(Form.main_menu)


# ================= بخش تست مدیر (منضمات / امضا) =================

@router.message(Form.test_mode_tracking_code)
async def test_mode_receive_tracking_code(message: types.Message, state: FSMContext):
    """دریافت کدرهگیری از مدیر در حالت تست."""
    if not message.text:
        return

    if message.text == "🔙 بازگشت":
        await message.answer("❓ *لطفاً نحوه ثبت درخواست خود را انتخاب فرمایید:*", reply_markup=get_flow_type_kb(message.from_user.id))
        await state.set_state(Form.waiting_for_flow_type)
        return

    clean_code = message.text.translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')).replace(" ", "").strip()

    if not re.match(r'^[0-9]+$', clean_code) or not _is_valid_tracking_code(clean_code):
        await message.answer("⚠️ کدرهگیری نامعتبر است. لطفاً یک کدرهگیری ۱۶ رقمی معتبر ارسال فرمایید:")
        return

    await state.update_data(
        test_tracking_code=clean_code,
        test_attachments=[],
        test_images=[])
    await message.answer(
        f"✅ کدرهگیری `{clean_code}` دریافت شد.\n\n"
        f"🧪 *حالت تست* — تست بابت کدام مورد است؟",
        reply_markup=test_mode_doc_type_kb)
    await state.set_state(Form.test_mode_doc_type)


@router.message(Form.test_mode_doc_type)
async def test_mode_doc_type(message: types.Message, state: FSMContext):
    """انتخاب نوع سند: لایحه یا اظهارنامه."""
    if not message.text:
        return

    if "انصراف" in message.text:
        await message.answer("❓ *لطفاً نحوه ثبت درخواست خود را انتخاب فرمایید:*", reply_markup=get_flow_type_kb(message.from_user.id))
        await state.set_state(Form.waiting_for_flow_type)
        return

    if "لایحه" in message.text:
        doc_type = "لایحه"
    elif "اظهارنامه" in message.text:
        doc_type = "اظهارنامه"
    elif "اعتراضی" in message.text:
        doc_type = "دعاوی اعتراضی"
    elif "اعلام وکالت" in message.text:
        doc_type = "اعلام وکالت"
    else:
        await message.answer("لطفاً یکی از گزینه‌های بالا را انتخاب کنید:", reply_markup=test_mode_doc_type_kb)
        return

    await state.update_data(test_doc_type=doc_type)
    data = await state.get_data()
    tracking_code = data['test_tracking_code']

    await message.answer(
        f"🔖 کدرهگیری: `{tracking_code}`\n"
        f"📂 نوع: *{doc_type}*\n\n"
        f"آیا می‌خواهید کدام بخش را تست کنید؟",
        reply_markup=test_mode_section_kb)
    await state.set_state(Form.test_mode_section_select)


@router.message(Form.test_mode_section_select)
async def test_mode_section_select(message: types.Message, state: FSMContext):
    """انتخاب بخش تست: منضمات یا امضا."""
    if not message.text:
        return

    if "انصراف" in message.text:
        await message.answer("🧪 *حالت تست* — تست بابت کدام مورد است؟", reply_markup=test_mode_doc_type_kb)
        await state.set_state(Form.test_mode_doc_type)
        return

    data = await state.get_data()
    tracking_code = data['test_tracking_code']
    doc_type = data['test_doc_type']
    user_id = message.from_user.id

    if "منضمات" in message.text:
        # شروع حلقه جمع‌آوری منضمات
        await state.update_data(test_attachments=[], test_images=[])

        # اگر نوع اعلام وکالت باشد، ابتدا حلقه نماینده حقوقی طی شود
        if doc_type == "اعلام وکالت":
            await message.answer(
                "👔 *سمت نماینده حقوقی* در اعلام وکالت را انتخاب کنید:",
                reply_markup=test_mode_ealam_representative_kb)
            await state.set_state(Form.test_mode_ealam_representative_type)
        else:
            await message.answer(
                "📎 مدارک و نام عنوان را ارسال کنید:",
                reply_markup=test_mode_att_title_kb_first)
            await state.set_state(Form.test_mode_attachment_title)

    elif "ثبت کامل" in message.text and "اعتراضی" in message.text:
        # تست ثبت کامل دعوی اعتراضی — ورود به فلوی دعاوی اعتراضی
        from tajdid_nazar_handlers import tajdid_nazar_entry
        await tajdid_nazar_entry(message, state)

    elif "امضا" in message.text:
        await message.answer(
            f"🧪 *تست امضا شروع شد...*\n\n"
            f"🔖 کدرهگیری: `{tracking_code}`\n"
            f"📂 نوع: *{doc_type}*\n\n"
            f"⏳ در حال ناوبری به بخش امضا...")

        if doc_type == "لایحه":
            sign_task_type = "LAVAYEH_SEND_SIGN_CODE"
            runtime_state.pending_lavayeh_sign[user_id] = {
                "tracking_code": tracking_code,
                "is_test": True,
            }
        elif doc_type == "اعلام وکالت":
            # اعلام وکالت امضای جداگانه ندارد — مستقیم به منضمات می‌رود
            await message.answer(
                "⚠️ اعلام وکالت بخش امضای جداگانه ندارد.\n"
                "لطفاً از گزینه *تست بخش منضمات* استفاده کنید.",
                reply_markup=test_mode_section_kb)
            return
        else:
            sign_task_type = "EZHHARNAMEH_SEND_SIGN_CODE"
            runtime_state.pending_ezhhar_sign[user_id] = {
                "tracking_code": tracking_code,
                "is_test": True,
                "is_ezhharnameh": True,
            }

        await runtime_state.job_queue.put({
            'user_id': user_id,
            'task_type': sign_task_type,
            'tracking_code': tracking_code,
            'phase': 'navigate',
            'doc_category': doc_type,
        })
        await state.clear()

    elif "هزینه" in message.text:
        # تست بخش هزینه — ارسال به صف مرورگر
        await message.answer(
            f"🧪 *تست هزینه شروع شد...*\n\n"
            f"🔖 کدرهگیری: `{tracking_code}`\n"
            f"📂 نوع: *{doc_type}*\n\n"
            f"⏳ در حال ناوبری و محاسبه هزینه...")

        await runtime_state.job_queue.put({
            'user_id': user_id,
            'task_type': 'TEST_COST',
            'tracking_code': tracking_code,
            'doc_category': doc_type,
        })
        await state.clear()


# ── حلقه نماینده حقوقی در تست اعلام وکالت ──────────────

@router.message(Form.test_mode_ealam_representative_type)
async def test_mode_ealam_representative(message: types.Message, state: FSMContext):
    """دریافت سمت نماینده حقوقی در تست اعلام وکالت."""
    text = message.text or ""
    if not text:
        return

    if "انصراف" in text:
        data = await state.get_data()
        tracking_code = data['test_tracking_code']
        doc_type = data['test_doc_type']
        await message.answer(
            f"🔖 کدرهگیری: `{tracking_code}`\n"
            f"📂 نوع: *{doc_type}*\n\n"
            f"آیا می‌خواهید کدام بخش را تست کنید؟",
            reply_markup=test_mode_section_kb)
        await state.set_state(Form.test_mode_section_select)
        return

    # ثبت سمت نماینده حقوقی
    await state.update_data(test_ealam_representative_type=text)
    await message.answer(
        f"✅ سمت نماینده حقوقی «*{text}*» ثبت شد.\n\n"
        f"🔢 لطفاً *شماره قرارداد وکالت* را وارد فرمایید:\n"
        f"_(۱۶ رقمی)_",
        reply_markup=back_only_kb)
    await state.set_state(Form.test_mode_ealam_contract_number)


@router.message(Form.test_mode_ealam_contract_number)
async def test_mode_ealam_contract(message: types.Message, state: FSMContext):
    """دریافت شماره قرارداد وکالت در تست اعلام وکالت."""
    text = (message.text or "").strip()
    if not text:
        return

    if text == "🔙 بازگشت":
        await message.answer(
            "👔 *سمت نماینده حقوقی* در اعلام وکالت را انتخاب کنید:",
            reply_markup=test_mode_ealam_representative_kb)
        await state.set_state(Form.test_mode_ealam_representative_type)
        return

    clean = text.translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')).replace(" ", "").strip()

    if not clean.isdigit() or len(clean) != 16:
        await message.answer(
            "⚠️ شماره قرارداد وکالت باید *دقیقاً ۱۶ رقمی* باشد.\n"
            f"شماره وارد شده *{len(clean)} رقمی* است. مجدداً وارد کنید:")
        return

    await state.update_data(test_ealam_contract_number=clean)
    await message.answer(
        f"✅ شماره قرارداد `{clean}` ثبت شد.\n\n"
        f"💰 *مقدار تمبر ابطالی:*\n\n"
        f"اگر مقدار تمبر را به ریال می‌دانید، عدد را وارد کنید.\n"
        f"در غیر این صورت از گزینه‌های زیر استفاده کنید:",
        reply_markup=test_mode_ealam_stamp_kb)
    await state.set_state(Form.test_mode_ealam_stamp_amount)


@router.message(Form.test_mode_ealam_stamp_amount)
async def test_mode_ealam_stamp(message: types.Message, state: FSMContext):
    """دریافت مقدار تمبر در تست اعلام وکالت."""
    text = (message.text or "").strip()
    if not text:
        return

    if "انصراف" in text:
        data = await state.get_data()
        tracking_code = data['test_tracking_code']
        doc_type = data['test_doc_type']
        await message.answer(
            f"🔖 کدرهگیری: `{tracking_code}`\n"
            f"📂 نوع: *{doc_type}*\n\n"
            f"آیا می‌خواهید کدام بخش را تست کنید؟",
            reply_markup=test_mode_section_kb)
        await state.set_state(Form.test_mode_section_select)
        return

    if "بدون تمبر" in text:
        await state.update_data(test_ealam_stamp_amount=0, test_ealam_stamp_type="بدون تمبر")
        await _test_mode_ealam_goto_attachments(message, state)
        return

    # کاربر عدد وارد کرده
    amount_str = text.translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789'))
    if amount_str.isdigit() and int(amount_str) > 0:
        stamp_amount = int(amount_str)
        await state.update_data(test_ealam_stamp_amount=stamp_amount, test_ealam_stamp_type="مشخص")
        await message.answer(
            f"✅ مقدار تمبر *{stamp_amount:,} ریال* ثبت شد.")
        await _test_mode_ealam_goto_attachments(message, state)
        return

    await message.answer(
        "⚠️ لطفاً مقدار تمبر را به *ریال* وارد کنید یا از گزینه‌های زیر استفاده کنید:",
        reply_markup=test_mode_ealam_stamp_kb)


async def _test_mode_ealam_goto_attachments(message: types.Message, state: FSMContext):
    """پس از ثبت نماینده حقوقی و قرارداد، ورود به حلقه منضمات."""
    data = await state.get_data()
    representative_type = data.get('test_ealam_representative_type', '')
    contract_number = data.get('test_ealam_contract_number', '')
    stamp_amount = data.get('test_ealam_stamp_amount', 0)

    await message.answer(
        f"📋 *خلاصه اطلاعات اعلام وکالت:*\n\n"
        f"👔 سمت نماینده: *{representative_type}*\n"
        f"📑 شماره قرارداد: `{contract_number}`\n"
        f"💰 تمبر: *{stamp_amount:,} ریال*\n\n"
        f"📎 حالا مدارک و نام عنوان را ارسال کنید:",
        reply_markup=test_mode_att_title_kb_first)
    await state.set_state(Form.test_mode_attachment_title)


# ── حلقه جمع‌آوری منضمات (همان حلقه لایحه/اظهارنامه) ──────────────

@router.message(Form.test_mode_attachment_title)
async def test_mode_att_title(message: types.Message, state: FSMContext):
    """دریافت عنوان مدرک در حالت تست."""
    text = (message.text or "").strip()
    if not text:
        return

    data = await state.get_data()
    attachments = data.get('test_attachments', [])

    # رد کردن — بدون مدرک
    if "رد کردن" in text:
        if not attachments:
            # هیچ مدرکی جمع‌آوری نشده → مستقیم ارسال به صف
            await _test_mode_send_attachments_task(message, state)
            return
        # مدرکهایی وجود دارد → ادامه به مرحله بعد
        await _test_mode_send_attachments_task(message, state)
        return

    # انصراف
    if "انصراف" in text:
        data = await state.get_data()
        tracking_code = data['test_tracking_code']
        doc_type = data['test_doc_type']
        await message.answer(
            f"🔖 کدرهگیری: `{tracking_code}`\n"
            f"📂 نوع: *{doc_type}*\n\n"
            f"آیا می‌خواهید کدام بخش را تست کنید؟",
            reply_markup=test_mode_section_kb)
        await state.set_state(Form.test_mode_section_select)
        return

    # ثبت عنوان
    if "عنوان مهم نیست" in text:
        title = "مستندات"
    else:
        title = text

    await state.update_data(_test_current_att_title=title, test_images=[])
    await message.answer(
        f"✅ عنوان «*{title}*» ثبت شد.\n\n"
        f"🖼 لطفاً تصاویر مربوط به این مدرک را به صورت *عکس (Photo)* ارسال فرمایید.\n"
        f"پس از ارسال همه تصاویر، دکمه *«اتمام ارسال تصاویر»* را بفشارید.",
        reply_markup=ReplyKeyboardRemove())
    await state.set_state(Form.test_mode_attachment_images)


@router.message(Form.test_mode_attachment_images, F.photo)
async def test_mode_receive_image(message: types.Message, state: FSMContext):
    """دریافت تصاویر مدرک در حالت تست."""
    from text_collector import check_image_limit, MAX_IMAGES_PER_TITLE

    data = await state.get_data()
    images = data.get('test_images', [])

    if not check_image_limit(len(images)):
        await message.reply(
            f"⛔ حداکثر *{MAX_IMAGES_PER_TITLE} تصویر* در هر عنوان مجاز است.")
        return

    file_id = message.photo[-1].file_id
    images.append(file_id)
    await state.update_data(test_images=images)

    manage_kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ اتمام ارسال تصاویر")],
            [KeyboardButton(text="🗑 حذف تصویر")],
        ],
        resize_keyboard=True
    )
    remaining = MAX_IMAGES_PER_TITLE - len(images)
    await message.reply(
        f"✅ تصویر شماره *{len(images)}* دریافت شد.\n"
        f"مجموع تصاویر این مدرک: *{len(images)}* از {MAX_IMAGES_PER_TITLE}\n\n"
        f"می‌توانید تصاویر بیشتری ارسال کنید ({remaining} جای باقیمانده)\n"
        f"یا دکمه «اتمام ارسال تصاویر» را بزنید.",
        reply_markup=manage_kb)


@router.message(Form.test_mode_attachment_images, F.document)
async def test_mode_reject_document(message: types.Message, state: FSMContext):
    await message.answer(
        "⚠️ لطفاً تصاویر را به صورت *عکس (Photo)* ارسال کنید، نه فایل.")


@router.message(Form.test_mode_attachment_images, F.text == "🗑 حذف تصویر")
async def test_mode_ask_delete_image(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    images = data.get('test_images', [])
    if not images:
        await message.answer("⚠️ لیست تصاویر خالی است.")
        return
    for i, fid in enumerate(images):
        await bot.send_photo(message.chat.id, photo=fid, caption=f"تصویر شماره {i + 1}")
    await message.answer(
        "لطفاً *شماره تصویر* برای حذف را ارسال فرمایید:",
        reply_markup=ReplyKeyboardRemove())
    await state.update_data(_test_deleting_image=True)


@router.message(Form.test_mode_attachment_images)
async def test_mode_images_text(message: types.Message, state: FSMContext):
    """هدلر متنی در حالت دریافت تصاویر — اتمام / حذف."""
    text = message.text or ""
    data = await state.get_data()
    images = data.get('test_images', [])
    deleting = data.get('_test_deleting_image', False)

    if deleting:
        num_str = text.translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789'))
        if num_str.isdigit():
            idx = int(num_str) - 1
            if 0 <= idx < len(images):
                images.pop(idx)
                await state.update_data(test_images=images, _test_deleting_image=False)
                if images:
                    manage_kb = ReplyKeyboardMarkup(
                        keyboard=[
                            [KeyboardButton(text="✅ اتمام ارسال تصاویر")],
                            [KeyboardButton(text="🗑 حذف تصویر")],
                        ],
                        resize_keyboard=True
                    )
                else:
                    manage_kb = ReplyKeyboardRemove()
                await message.answer(
                    f"✅ تصویر شماره *{idx+1}* حذف شد.\n"
                    f"مجموع باقیمانده: *{len(images)} تصویر*",
                    reply_markup=manage_kb)
                return
        await state.update_data(_test_deleting_image=False)
        await message.answer("⚠️ شماره نامعتبر بود. لطفاً دوباره تلاش کنید.")
        return

    if "اتمام" in text:
        title = data.get('_test_current_att_title', 'مستندات')
        attachments = data.get('test_attachments', [])
        attachments.append({'title': title, 'images': list(images)})
        await state.update_data(test_attachments=attachments, test_images=[])

        await message.answer(
            f"✅ مدرک «*{title}*» با *{len(images)}* تصویر ثبت شد.\n\n"
            f"آیا مدرک دیگری هم دارید؟",
            reply_markup=test_mode_att_more_kb)
        await state.set_state(Form.test_mode_attachment_more)
        return

    await message.answer("لطفاً تصاویر را ارسال کنید یا دکمه «اتمام ارسال تصاویر» را بزنید.")


@router.message(Form.test_mode_attachment_more)
async def test_mode_attachment_more(message: types.Message, state: FSMContext):
    """آیا مدرک دیگری هست؟"""
    text = message.text or ""

    if "بله" in text and "مدرک" in text:
        await state.update_data(test_images=[])
        await message.answer(
            "📄 *عنوان مدرک بعدی:*\n\n"
            "در صورتی که تصویری برای ضمیمه دارید، عنوان آن را تایپ کنید\n"
            "یا یکی از گزینه‌های زیر را انتخاب کنید:",
            reply_markup=test_mode_att_title_kb)
        await state.set_state(Form.test_mode_attachment_title)
        return

    if "خیر" in text and "ادامه" in text:
        await _test_mode_send_attachments_task(message, state)
        return

    if "انصراف" in text:
        data = await state.get_data()
        tracking_code = data['test_tracking_code']
        doc_type = data['test_doc_type']
        await message.answer(
            f"🔖 کدرهگیری: `{tracking_code}`\n"
            f"📂 نوع: *{doc_type}*\n\n"
            f"آیا می‌خواهید کدام بخش را تست کنید؟",
            reply_markup=test_mode_section_kb)
        await state.set_state(Form.test_mode_section_select)
        return

    await message.answer("لطفاً یکی از گزینه‌های زیر را انتخاب کنید:", reply_markup=test_mode_att_more_kb)


async def _test_mode_send_attachments_task(message: types.Message, state: FSMContext):
    """ارسال تسک تست منضمات به صف مرورگر — از همان حلقه آپلود منضمات."""
    data = await state.get_data()
    tracking_code = data['test_tracking_code']
    doc_type = data['test_doc_type']
    attachments = data.get('test_attachments', [])
    user_id = message.from_user.id

    # نمایش خلاصه مدارک جمع‌آوری شده
    summary_lines = []
    total_images = 0
    for i, att in enumerate(attachments):
        img_count = len(att.get('images', []))
        total_images += img_count
        summary_lines.append(f"  {i+1}. *{att['title']}* — {img_count} تصویر")

    if not summary_lines:
        summary = "(بدون مدرک)"
    else:
        summary = "\n".join(summary_lines)

    # اطلاعات ویژه اعلام وکالت
    ealam_info = ""
    task_type = 'TEST_ATTACHMENTS'
    job_data = {
        'user_id': user_id,
        'task_type': task_type,
        'tracking_code': tracking_code,
        'doc_category': doc_type,
        'test_attachments': attachments,
    }

    if doc_type == "اعلام وکالت":
        representative_type = data.get('test_ealam_representative_type', '')
        contract_number = data.get('test_ealam_contract_number', '')
        stamp_amount = data.get('test_ealam_stamp_amount', 0)
        stamp_type = data.get('test_ealam_stamp_type', '')

        ealam_info = (
            f"\n👔 سمت نماینده: *{representative_type}*\n"
            f"📑 شماره قرارداد: `{contract_number}`\n"
            f"💰 تمبر: *{stamp_amount:,} ریال* ({stamp_type})\n"
        )
        job_data['test_ealam_representative_type'] = representative_type
        job_data['test_ealam_contract_number'] = contract_number
        job_data['test_ealam_stamp_amount'] = stamp_amount
        job_data['test_ealam_stamp_type'] = stamp_type

    await message.answer(
        f"🧪 *تست منضمات شروع شد...*\n\n"
        f"🔖 کدرهگیری: `{tracking_code}`\n"
        f"📂 نوع: *{doc_type}*\n"
        f"📎 تعداد مدارک: *{len(attachments)}* ({total_images} تصویر)\n"
        f"{ealam_info}\n"
        f"*لیست مدارک:*\n{summary}\n\n"
        f"⏳ در حال اجرای حلقه منضمات...")

    await runtime_state.job_queue.put(job_data)
    await state.clear()


# ══════════════════════════════════════════════════════════════════
# بخش استعلام دسته‌جمعی (فایل اکسل)
# ══════════════════════════════════════════════════════════════════

async def _bulk_inquiry_start(message: types.Message, state: FSMContext):
    """شروع فرآیند استعلام دسته‌جمعی — ارسال نمونه اکسل."""
    sample_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "templates", "sample_bulk_inquiry.xlsx"
    )
    if os.path.exists(sample_path):
        try:
            from bale_file_sender import send_document_direct
            await send_document_direct(message.chat.id, sample_path)
        except Exception as e:
            logger.warning(f"[BULK-INQ] خطا در ارسال فایل نمونه: {e}")

    await message.answer(
        "📊 *استعلام دسته‌جمعی از طریق فایل اکسل*\n\n"
        "💡 این گزینه مخصوص زمانی است که *بیش از ۵ استعلام* هم‌زمان دارید.\n\n"
        "📎 همین الان یک *فایل اکسل نمونه* برای شما ارسال شد.\n\n"
        "⚠️ *یک قانون ساده، حتماً رعایت کنید:*\n"
        "قبل از هر عدد در این سه ستون، همیشه یک حرف بگذارید (دقیقاً مثل "
        "سرستون‌های خودِ فایل):\n"
        "   • کدرهگیری → با حرف *T*:  `T1405220948201280`\n"
        "   • موبایل → با حرف *M*:  `M09123456789`\n"
        "   • کدملی → با حرف *N*:  `N0012345678`\n"
        "اگر این حرف را نگذارید، اکسل/گوگل‌شیت (حتی پیش‌نمایش بله) عدد را "
        "خراب می‌کند (رقم آخر گم می‌شود یا صفر اول حذف می‌شود). با این "
        "حرف، هیچ برنامه‌ای دیگر عدد را به‌هم نمی‌ریزد.\n\n"
        "⚠️ فایل را مستقیم داخل پیش‌نمایش بله ادیت نکنید (پیامی مثل «Read Only "
        "- Save a copy to edit» یعنی در حالت پیش‌نمایش هستید). اول:\n"
        "   • روی «Save a copy» بزنید، یا\n"
        "   • فایل را دانلود کنید و با Google Sheets / Excel / WPS Office باز کنید\n\n"
        "📋 *راهنما:*\n"
        "۱. همان فایل ارسال‌شده را تکمیل کنید (شیت «راهنما» را هم ببینید)\n"
        "۲. در هر ردیف فقط همان ستونی را که لازم دارید پر کنید\n"
        "۳. برای کدرهگیری با منضمات، «دریافت پیوست‌ها؟» را بله و «نوع سند» "
        "را حتماً از لیست کشویی انتخاب کنید (برای محاسبه‌ی دقیق تعداد برگ)\n\n"
        "✅ سپس همین فایل تکمیل‌شده را اینجا ارسال کنید:",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(Form.bulk_inquiry_file_upload)


@router.message(Form.bulk_inquiry_file_upload)
async def bulk_inquiry_file_handler(message: types.Message, state: FSMContext, bot: Bot):
    """دریافت و پردازش فایل اکسل استعلام دسته‌جمعی."""
    from bulk_inquiry_excel import (
        build_bulk_inquiry_items, enrich_bulk_inquiry_items, build_invoice_text
    )

    if message.text and message.text == "🔙 بازگشت":
        await message.answer("بازگشت به منو.", reply_markup=cart_kb)
        await state.set_state(Form.main_menu)
        return

    if not message.document:
        await message.answer("⚠️ لطفاً فایل اکسل (.xlsx) را ارسال فرمایید.")
        return

    doc = message.document
    if not (doc.file_name and doc.file_name.lower().endswith(('.xlsx', '.xls'))):
        await message.answer("⚠️ لطفاً فقط فایل با پسوند اکسل (.xlsx) ارسال فرمایید.")
        return

    await message.answer("⏳ در حال خواندن فایل اکسل...", reply_markup=ReplyKeyboardRemove())

    import tempfile
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, doc.file_name or "bulk_inquiry.xlsx")
    try:
        file_info = await bot.get_file(doc.file_id)
        await bot.download_file(file_info.file_path, file_path)
    except Exception as e:
        await message.answer(f"⚠️ خطا در دانلود فایل: {e}", reply_markup=cart_kb)
        await state.set_state(Form.main_menu)
        return

    try:
        parsed = build_bulk_inquiry_items(file_path)
    except Exception as e:
        logger.error(f"[BULK-INQ] خطا در خواندن فایل اکسل: {e}", exc_info=True)
        await message.answer(f"⚠️ خطا در خواندن فایل اکسل: {e}", reply_markup=cart_kb)
        await state.set_state(Form.main_menu)
        return

    valid_items = parsed["valid_items"]
    invalid_cells = parsed["invalid_cells"]

    if not valid_items:
        error_msg = "⚠️ هیچ استعلام معتبری در فایل یافت نشد."
        if invalid_cells:
            error_msg += "\n\n📋 *خطاهای یافت‌شده:*\n"
            for c in invalid_cells[:15]:
                error_msg += f"  • ردیف {c['row_index']} ({c['field']}): {c['error']}\n"
        await message.answer(error_msg, reply_markup=cart_kb)
        await state.set_state(Form.main_menu)
        return

    # ── استعلام تعداد منضمات (فقط برای مواردی که واقعاً بله زده‌اند) ──
    n_attachment_checks = sum(
        1 for it in valid_items if it["kind"] == "tracking" and it["need_attachments"]
    )
    if n_attachment_checks:
        await message.answer(
            f"⏳ در حال استعلام تعداد منضمات {n_attachment_checks} کدرهگیری از سامانه...\n"
            f"لطفاً صبور باشید."
        )

    cart_items, failed_items = await enrich_bulk_inquiry_items(
        valid_items, user_id=message.from_user.id, bot=bot
    )

    if not cart_items:
        await message.answer(
            "⚠️ هیچ‌کدام از موارد قابل استعلام نبودند. لطفاً فایل را اصلاح و دوباره ارسال کنید.",
            reply_markup=cart_kb)
        await state.set_state(Form.main_menu)
        return

    invoice_text, total_sum = build_invoice_text(cart_items, invalid_cells, failed_items)

    # نکته مهم: کلیدهای این آیتم‌ها (query_type/tracking_code/...) دقیقاً
    # هم‌ساختار سبد خرید موجود است — successful_payment_handler و
    # _process_pay_done مستقیماً از همین ساختار می‌خوانند. تغییر نام کلیدها
    # باعث KeyError در لحظه‌ی پرداخت واقعی می‌شود.
    await state.update_data(
        bulk_inquiry_items=cart_items,
        bulk_inquiry_total=total_sum,
    )

    await message.answer(invoice_text, reply_markup=bulk_inquiry_confirm_kb)
    await state.set_state(Form.bulk_inquiry_confirm)


@router.message(Form.bulk_inquiry_confirm)
async def bulk_inquiry_confirm_handler(message: types.Message, state: FSMContext, bot: Bot):
    """تایید یا انصراف از فاکتور استعلام دسته‌جمعی."""
    data = await state.get_data()
    items = data.get("bulk_inquiry_items", [])
    total_sum = data.get("bulk_inquiry_total", 0)

    if not message.text:
        return

    if "❌ انصراف" in message.text:
        await state.update_data(bulk_inquiry_items=None, bulk_inquiry_total=None)
        await message.answer("❌ انصراف از استعلام دسته‌جمعی.", reply_markup=cart_kb)
        await state.set_state(Form.main_menu)
        return

    if "✅ تایید" not in message.text:
        return

    if not items:
        await message.answer("⚠️ موردی برای پردازش وجود ندارد.", reply_markup=cart_kb)
        await state.set_state(Form.main_menu)
        return

    # ── بررسی معافیت از پرداخت (دقیقاً هم‌ساختار فلوی سبد خرید معمولی) ──
    if await is_exempt_user(message.from_user.id):
        queue_position = runtime_state.job_queue.qsize()
        queue_note = (
            f"\n📊 موقعیت شما در صف: *{queue_position + 1}*"
            if queue_position > 0 else "\n▶️ پردازش بلافاصله آغاز می‌شود."
        )
        await message.answer(
            f"✅ *معافیت از پرداخت*\n\n"
            f"شما در لیست کاربران معاف هستید."
            f"\nتعداد {len(items)} استعلام در صف پردازش قرار گرفت.{queue_note}",
            reply_markup=restart_kb)
        for item in items:
            await log_event(
                "پرداخت", item['query_type'], message.from_user.full_name, message.from_user.id,
                tracking_code=item['tracking_code'],
                doc_name=(f"{item.get('doc_category')} - {item.get('doc_subcategory')}"
                          if item.get('doc_subcategory') else item.get('doc_category')),
                payment_status="معاف از پرداخت")
            await runtime_state.job_queue.put({
                'user_id': message.from_user.id,
                'query_type': item['query_type'],
                'tracking_code': item['tracking_code'],
                'doc_category': item.get('doc_category'),
                'doc_subcategory': item.get('doc_subcategory'),
                'doc_type': (f"{item.get('doc_category')} - {item.get('doc_subcategory')}"
                             if item.get('doc_subcategory') else item.get('doc_category')),
                'need_attachments': item.get('need_attachments', False),
                'full_name': message.from_user.full_name,
                'payment_fee': item.get('fee', 0),
            })
        await state.clear()
        return

    # ═══ ارسال فاکتور بله با sendInvoice API — دقیقاً مطابق فلوی سبد خرید ═══
    total_rial = total_sum * 10
    try:
        invoice_payload = _json.dumps({"type": "bulk_inquiry", "uid": message.from_user.id})
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
            invoice_url = f"{BALE_API_BASE}/bot{BOT_TOKEN}/sendInvoice"
            invoice_data = {
                "chat_id": message.from_user.id,
                "title": f"فاکتور استعلام دسته‌جمعی ({len(items)} مورد)",
                "description": f"مجموع: {total_sum:,} تومان ({total_rial:,} ریال)",
                "payload": invoice_payload,
                "provider_token": BALE_WALLET_TOKEN,
                "currency": "IRR",
                "prices": [{"label": f"{len(items)} استعلام دسته‌جمعی", "amount": total_rial}],
            }
            logging.info(f"[BULK-INQ-PAY] sendInvoice chat_id={message.from_user.id}, amount={total_rial:,}")
            async with session.post(invoice_url, json=invoice_data) as resp:
                result = await resp.json()
                if not result.get("ok"):
                    raise Exception(result.get("description", "خطا در ارسال فاکتور"))
    except Exception as e:
        logging.error(f"[BULK-INQ-PAY] خطا: {e}", exc_info=True)
        await message.answer("⚠️ خطا در ساخت فاکتور. لطفاً کمی بعد دوباره تلاش کنید.", reply_markup=cart_kb)
        await state.set_state(Form.main_menu)
        return

    warning = ""
    if message.from_user.id == ADMIN_ID:
        warning = (
            "\n\n⚠️ _توجه: اگر کیف پول خودتان را شارژ کرده‌اید و اکنون می‌خواهید "
            "از همان کیف پول پرداخت کنید، پرداخت انجام نخواهد شد._\n\n"
        )
    # ⛔ کیبورد قبلی (pay_kb) دکمه «💳 پرداخت و تسویه حساب» داشت که باعث
    # ارسال مجدد فاکتور می‌شد؛ جای آن کیبورد فقط-انصراف نمایش داده می‌شود.
    # پرداخت فقط در همان فاکتور و تایید فقط توسط بله انجام می‌گیرد.
    await message.answer(
        f"⏳ فاکتور ارسال شد."
        f"{warning}"
        f"پس از پرداخت موفق، {len(items)} استعلام به‌صورت خودکار پردازش می‌شوند.\n"
        f"💳 پرداخت را در همان فاکتور انجام دهید — تایید پرداخت فقط توسط خود بله صورت می‌گیرد.",
        reply_markup=payment_cancel_kb)
    await state.set_state(Form.waiting_for_payment_receipt)

    # ذخیره‌ی سبد در همان کلید 'cart' — تا successful_payment_handler
    # این آیتم‌ها را بدون هیچ تغییری پردازش کند.
    await state.update_data(
        cart=items,
        total_payment_sum=total_sum,
    )
