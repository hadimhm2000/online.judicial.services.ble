# -*- coding: utf-8 -*-
"""
check_bulk_handlers.py
──────────────────────────────────────────────────────────────────────────
مرحلهٔ اجباری تصویر چک در ثبت دسته‌جمعی چک.

بعد از اینکه check_handlers.check_bulk_file_upload_handler فایل اکسل را
خواند و ردیف‌های معتبر را ساخت، start_check_bulk_images صدا زده می‌شود:

  • برای هر ردیف دقیقاً ۳ تصویر (روی چک، پشت چک، گواهی عدم پرداخت) گرفته
    می‌شود؛ بدون ۳ تصویر امکان رفتن به ردیف بعد نیست.
  • بعد از ۳ تصویر، کاربر می‌تواند مدرک اضافی (عنوان + تصاویر) هم بفرستد.
  • پس از آخرین ردیف، یک فاکتور پیش‌پرداخت برای همهٔ ردیف‌ها (هر ردیف به
    اندازهٔ پیش‌پرداخت ثبت تکی چک) صادر می‌شود. پس از پرداخت، ردیف‌ها با یک
    کد پیگیری دسته‌جمعی در BULK_TASKS ثبت و در job_queue قرار می‌گیرند؛ check_scenario نتیجهٔ هر
    ردیف را با send_bulk_item_result / mark_bulk_item_done گزارش می‌کند و
    finalize_bulk_batch در پایان گزارش مالی، فاکتور تسویه و منوی امضا را
    یک‌جا می‌فرستد (مثل لایحه/اظهارنامهٔ دسته‌جمعی).

آیتم‌ها از قبل به همان شکل job ثبت تکی چک هستند (check_plainiffs،
check_defendants، check_images، check_attachment_groups، ...).
"""

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

import runtime_state
from states import Form
from bulk_submissions import BULK_TASKS, generate_tracking_code

logger = logging.getLogger(__name__)

check_bulk_router = Router()

MAX_CHECK_IMAGES = 3  # مطابق ثبت تکی چک: روی چک، پشت چک، گواهی عدم پرداخت

BTN_IMAGES_DONE = "✅ ۳ تصویر ارسال شد - ادامه"
BTN_UNDO = "↩️ حذف آخرین تصویر"
BTN_CANCEL = "❌ انصراف از ثبت دسته‌جمعی"
BTN_EXTRA_YES = "📎 بله، مدرک دیگری هم دارم"
BTN_EXTRA_NO = "✅ خیر، برو به ردیف بعدی"
BTN_EXTRA_DONE = "✅ اتمام این مدرک"
BTN_BACK = "🔙 بازگشت"


def bulk_check_images_kb(count: int) -> ReplyKeyboardMarkup:
    """تا ۳ تصویر کامل نشده، دکمهٔ ادامه نمایش داده نمی‌شود."""
    rows = []
    if count >= MAX_CHECK_IMAGES:
        rows.append([KeyboardButton(text=BTN_IMAGES_DONE)])
    if count:
        rows.append([KeyboardButton(text=BTN_UNDO)])
    rows.append([KeyboardButton(text=BTN_CANCEL)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


bulk_check_extra_choice_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=BTN_EXTRA_YES)],
        [KeyboardButton(text=BTN_EXTRA_NO)],
    ],
    resize_keyboard=True,
)

bulk_check_extra_title_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=BTN_BACK)]],
    resize_keyboard=True,
)

bulk_check_extra_images_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=BTN_EXTRA_DONE)], [KeyboardButton(text=BTN_BACK)]],
    resize_keyboard=True,
)


def _person_id(p: dict) -> str:
    return (p or {}).get("company_id") or (p or {}).get("national_id") or "-"


async def _current(state: FSMContext):
    data = await state.get_data()
    items = data.get("check_bulk_items", [])
    idx = data.get("check_bulk_current_index", 0)
    return data, items, idx


# ══════════════════════════════════════════════════════════════════════════
# شروع (از check_handlers بعد از خواندن اکسل)
# ══════════════════════════════════════════════════════════════════════════
async def start_check_bulk_images(message: Message, state: FSMContext, items: list):
    for it in items:
        it["check_images"] = []
        it.setdefault("check_attachment_groups", [])
    await state.update_data(
        check_bulk_items=items,
        check_bulk_current_index=0,
        _bulk_check_extra_title="",
        _bulk_check_extra_images=[],
    )
    await message.answer(
        f"🧾 حالا برای هر ردیف باید *{MAX_CHECK_IMAGES} تصویر* بفرستید:\n"
        f"روی چک، پشت چک، گواهی عدم پرداخت.\n"
        f"ردیف‌ها به ترتیب فایل اکسل پرسیده می‌شوند.",
        parse_mode="Markdown",
    )
    await _prompt_row(message, state)


async def _prompt_row(message: Message, state: FSMContext):
    _, items, idx = await _current(state)
    item = items[idx]
    images = item.get("check_images", [])
    plaintiff = (item.get("check_plainiffs") or [{}])[0]
    defendant = (item.get("check_defendants") or [{}])[0]
    amount = item.get("check_amount") or 0
    try:
        amount_txt = f"{int(amount):,}"
    except (TypeError, ValueError):
        amount_txt = str(amount)

    row_no = item.get("_bulk_row_index", idx + 1)
    if len(images) >= MAX_CHECK_IMAGES:
        text = f"🧾 ردیف {row_no}: هر {MAX_CHECK_IMAGES} تصویر دریافت شد."
    else:
        text = (
            f"🧾 ردیف {row_no} ({idx + 1} از {len(items)})\n"
            f"📝 {item.get('check_request_title', '-')}\n"
            f"🔢 کد رهگیری چک: {item.get('check_tracking_no') or '-'}\n"
            f"💰 مبلغ: {amount_txt} ریال\n"
            f"👤 خواهان: {_person_id(plaintiff)}  |  👥 خوانده: {_person_id(defendant)}\n\n"
            f"📷 تصویر {len(images) + 1} از {MAX_CHECK_IMAGES} را ارسال کنید."
        )
    await message.answer(text, reply_markup=bulk_check_images_kb(len(images)))
    await state.set_state(Form.bulk_check_images_row)


# ══════════════════════════════════════════════════════════════════════════
# تصاویر چک (اجباری)
# ══════════════════════════════════════════════════════════════════════════
@check_bulk_router.message(Form.bulk_check_images_row, F.photo)
async def bulk_check_images_photo_handler(message: Message, state: FSMContext):
    _, items, idx = await _current(state)
    images = items[idx].setdefault("check_images", [])

    if len(images) >= MAX_CHECK_IMAGES:
        await message.answer(
            f"⚠️ این ردیف {MAX_CHECK_IMAGES} تصویر دارد. «ادامه» را بزنید "
            f"یا با «حذف آخرین تصویر» یکی را عوض کنید.",
            reply_markup=bulk_check_images_kb(len(images)),
        )
        return

    # همان فرمت ثبت تکی: {"file_id": ...}
    images.append({"file_id": message.photo[-1].file_id})
    await state.update_data(check_bulk_items=items)

    remaining = MAX_CHECK_IMAGES - len(images)
    if remaining:
        await message.answer(
            f"✅ تصویر {len(images)} از {MAX_CHECK_IMAGES} دریافت شد. تصویر بعدی را بفرستید.",
            reply_markup=bulk_check_images_kb(len(images)),
        )
    else:
        await message.answer(
            f"✅ هر {MAX_CHECK_IMAGES} تصویر این ردیف دریافت شد.",
            reply_markup=bulk_check_images_kb(len(images)),
        )


@check_bulk_router.message(Form.bulk_check_images_row, F.text == BTN_IMAGES_DONE)
async def bulk_check_images_done_handler(message: Message, state: FSMContext):
    _, items, idx = await _current(state)
    count = len(items[idx].get("check_images", []))
    if count < MAX_CHECK_IMAGES:
        await message.answer(
            f"⚠️ این ردیف هنوز {MAX_CHECK_IMAGES - count} تصویر کم دارد.",
            reply_markup=bulk_check_images_kb(count),
        )
        return
    await message.answer(
        "📎 مدرک دیگری (غیر از تصاویر چک) برای این ردیف دارید؟",
        reply_markup=bulk_check_extra_choice_kb,
    )
    await state.set_state(Form.bulk_check_extra_attachment_choice)


@check_bulk_router.message(Form.bulk_check_images_row, F.text == BTN_UNDO)
async def bulk_check_images_undo_handler(message: Message, state: FSMContext):
    _, items, idx = await _current(state)
    if items[idx].get("check_images"):
        items[idx]["check_images"].pop()
        await state.update_data(check_bulk_items=items)
    await _prompt_row(message, state)


@check_bulk_router.message(Form.bulk_check_images_row, F.text == BTN_CANCEL)
async def bulk_check_cancel_handler(message: Message, state: FSMContext):
    await state.clear()
    from keyboards import flow_type_kb
    await message.answer(
        "❌ ثبت دسته‌جمعی چک لغو شد. هیچ ردیفی ثبت نشد.",
        reply_markup=flow_type_kb,
    )


@check_bulk_router.message(Form.bulk_check_images_row)
async def bulk_check_images_fallback(message: Message, state: FSMContext):
    _, items, idx = await _current(state)
    await message.answer(
        "⚠️ لطفاً تصویر چک را به‌صورت *عکس* بفرستید یا از دکمه‌ها استفاده کنید.",
        parse_mode="Markdown",
        reply_markup=bulk_check_images_kb(len(items[idx].get("check_images", []))),
    )


# ══════════════════════════════════════════════════════════════════════════
# مدارک اضافی (اختیاری)
# ══════════════════════════════════════════════════════════════════════════
@check_bulk_router.message(Form.bulk_check_extra_attachment_choice, F.text == BTN_EXTRA_YES)
async def bulk_check_extra_yes(message: Message, state: FSMContext):
    await message.answer(
        "📄 عنوان این مدرک را بنویسید (مثلاً «وکالتنامه»):",
        reply_markup=bulk_check_extra_title_kb,
    )
    await state.set_state(Form.bulk_check_extra_attachment_title)


@check_bulk_router.message(Form.bulk_check_extra_attachment_choice, F.text == BTN_EXTRA_NO)
async def bulk_check_extra_no(message: Message, state: FSMContext):
    await _advance_to_next_row(message, state)


@check_bulk_router.message(Form.bulk_check_extra_attachment_choice)
async def bulk_check_extra_choice_fallback(message: Message, state: FSMContext):
    await message.answer("لطفاً یکی از دکمه‌ها را انتخاب کنید:", reply_markup=bulk_check_extra_choice_kb)


@check_bulk_router.message(Form.bulk_check_extra_attachment_title)
async def bulk_check_extra_title_handler(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if text == BTN_BACK:
        await message.answer("📎 مدرک دیگری دارید؟", reply_markup=bulk_check_extra_choice_kb)
        await state.set_state(Form.bulk_check_extra_attachment_choice)
        return
    if not text:
        await message.answer("⚠️ لطفاً عنوان مدرک را به‌صورت متن بنویسید:", reply_markup=bulk_check_extra_title_kb)
        return

    await state.update_data(_bulk_check_extra_title=text[:100], _bulk_check_extra_images=[])
    await message.answer(
        f"🖼 تصاویر «{text[:100]}» را بفرستید و در پایان «{BTN_EXTRA_DONE}» را بزنید.",
        reply_markup=bulk_check_extra_images_kb,
    )
    await state.set_state(Form.bulk_check_extra_attachment_images)


@check_bulk_router.message(Form.bulk_check_extra_attachment_images, F.photo)
async def bulk_check_extra_images_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    buf = list(data.get("_bulk_check_extra_images", []))
    buf.append(message.photo[-1].file_id)
    await state.update_data(_bulk_check_extra_images=buf)
    await message.answer(
        f"✅ تصویر {len(buf)} دریافت شد. تصویر بعدی یا «{BTN_EXTRA_DONE}»:",
        reply_markup=bulk_check_extra_images_kb,
    )


@check_bulk_router.message(Form.bulk_check_extra_attachment_images, F.text == BTN_EXTRA_DONE)
async def bulk_check_extra_images_done(message: Message, state: FSMContext):
    data, items, idx = await _current(state)
    title = data.get("_bulk_check_extra_title") or "سایر مستندات"
    images = list(data.get("_bulk_check_extra_images", []))
    if not images:
        await message.answer("⚠️ حداقل یک تصویر بفرستید یا «بازگشت» را بزنید.",
                             reply_markup=bulk_check_extra_images_kb)
        return

    items[idx].setdefault("check_attachment_groups", []).append({"title": title, "images": images})
    await state.update_data(
        check_bulk_items=items,
        _bulk_check_extra_title="",
        _bulk_check_extra_images=[],
    )
    await message.answer(
        f"✅ مدرک «{title}» ({len(images)} تصویر) ثبت شد.\nمدرک دیگری هم دارید؟",
        reply_markup=bulk_check_extra_choice_kb,
    )
    await state.set_state(Form.bulk_check_extra_attachment_choice)


@check_bulk_router.message(Form.bulk_check_extra_attachment_images, F.text == BTN_BACK)
async def bulk_check_extra_images_back(message: Message, state: FSMContext):
    await state.update_data(_bulk_check_extra_title="", _bulk_check_extra_images=[])
    await message.answer("📎 مدرک دیگری دارید؟", reply_markup=bulk_check_extra_choice_kb)
    await state.set_state(Form.bulk_check_extra_attachment_choice)


@check_bulk_router.message(Form.bulk_check_extra_attachment_images)
async def bulk_check_extra_images_fallback(message: Message, state: FSMContext):
    await message.answer(
        f"⚠️ لطفاً تصویر بفرستید یا «{BTN_EXTRA_DONE}» را بزنید.",
        reply_markup=bulk_check_extra_images_kb,
    )


# ══════════════════════════════════════════════════════════════════════════
# ردیف بعدی / ارسال کل دسته به صف
# ══════════════════════════════════════════════════════════════════════════
async def _advance_to_next_row(message: Message, state: FSMContext):
    _, items, idx = await _current(state)
    if idx + 1 >= len(items):
        await _finalize_check_bulk(message, state)
        return
    await state.update_data(check_bulk_current_index=idx + 1)
    await _prompt_row(message, state)


def build_check_bulk_job(item: dict, user_id: int, tracking_code: str, row_index: int) -> dict:
    job = dict(item)
    job.pop("row_index", None)
    job.update({
        "user_id": user_id,
        "query_type": "دادخواست_چک",
        "task_type": "CHECK_SUBMIT",
        "_is_bulk_check": True,
        "batch_tracking_code": tracking_code,
        "_bulk_row_index": row_index,
    })
    return job


async def _send_invoice(invoice_data: dict):
    from config import BALE_API_BASE, BOT_TOKEN, BALE_SSL_CONTEXT
    import aiohttp
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=BALE_SSL_CONTEXT)) as session:
        async with session.post(f"{BALE_API_BASE}/bot{BOT_TOKEN}/sendInvoice", json=invoice_data) as resp:
            result = await resp.json()
            if not result.get("ok"):
                raise Exception(result.get("description", "خطا در ارسال فاکتور"))


def _prepay_per_row_rial() -> int:
    """پیش‌پرداخت هر ردیف = همان پیش‌پرداخت ثبت تکی چک (تنظیم پنل / config)."""
    from prepay_registration import get_prepay_amount_rial
    return get_prepay_amount_rial("check")


async def _finalize_check_bulk(message: Message, state: FSMContext):
    """بعد از آخرین ردیف: یک فاکتور پیش‌پرداخت برای همهٔ ردیف‌ها؛ پس از پرداخت
    (check_bulk_prepay_successful_payment) ردیف‌ها به صف می‌روند."""
    _, items, _ = await _current(state)
    user = message.from_user
    user_id = user.id

    missing = [i for i, it in enumerate(items) if len(it.get("check_images", [])) < MAX_CHECK_IMAGES]
    if missing:
        await state.update_data(check_bulk_current_index=missing[0])
        await message.answer("⚠️ یک ردیف هنوز تصاویر کامل ندارد. برگردیم به همان ردیف:")
        await _prompt_row(message, state)
        return

    tracking_code = generate_tracking_code("CHK")
    total = len(items)

    try:
        from exempt_users import is_exempt_user
        exempt = await is_exempt_user(user_id)
    except Exception as e:
        logger.warning(f"[CHECK-BULK] بررسی معافیت ناموفق (فرض: معاف نیست): {e}")
        exempt = False

    prepay_rial = 0 if exempt else total * _prepay_per_row_rial()
    BULK_TASKS[tracking_code] = {
        "user_id": user_id,
        "username": user.username or user.first_name,
        "items": items,
        "service_type": "CHECK",
        "status": "awaiting_prepay",
        "signable_items": [],
        "failures": [],
        "queued_count": 0,
        "completed_count": 0,
        # در پایان بچ از هزینهٔ واقعی سامانه کسر می‌شود (finalize_bulk_batch)
        "prepaid_total_rial": prepay_rial,
    }
    await state.clear()

    if exempt:
        await queue_check_bulk(message.bot, user_id, tracking_code)
        return

    from config import BALE_WALLET_TOKEN
    import json as _json

    per_row_toman = _prepay_per_row_rial() // 10
    invoice_data = {
        "chat_id": user_id,
        "title": "پیش‌پرداخت ثبت دسته‌جمعی چک",
        "description": (f"پیش‌پرداخت {total} ردیف چک ({per_row_toman:,} تومان برای هر ردیف)\n"
                        f"مبلغ: {prepay_rial // 10:,} تومان ({prepay_rial:,} ریال)"),
        "payload": _json.dumps({"type": "bulk_prepay", "svc": "check", "uid": user_id,
                                "tracking_code": tracking_code}),
        "provider_token": BALE_WALLET_TOKEN,
        "currency": "IRR",
        "prices": [{"label": f"پیش‌پرداخت {total} ردیف چک", "amount": prepay_rial}],
    }
    try:
        await _send_invoice(invoice_data)
        logger.info(f"[CHECK-BULK-PREPAY] فاکتور: user={user_id}, {total} ردیف, {prepay_rial:,} ریال, {tracking_code}")
    except Exception as e:
        logger.error(f"[CHECK-BULK-PREPAY] خطا در صدور فاکتور: {e}", exc_info=True)
        BULK_TASKS.pop(tracking_code, None)
        from keyboards import flow_type_kb
        await message.answer(
            "⚠️ خطا در ساخت فاکتور پیش‌پرداخت. هیچ ردیفی ثبت نشد؛ لطفاً کمی بعد دوباره فایل را بفرستید.",
            reply_markup=flow_type_kb)
        return

    await state.set_state(Form.bulk_prepay_wait)
    await state.update_data(bulk_prepay_tracking_code=tracking_code)
    try:
        from card_payment import track_invoice as _cp_track
        _cp_track(invoice_data)   # کارت‌به‌کارت و پیشنهاد کیف پول
    except Exception as e:
        logger.warning(f"[CHECK-BULK-PREPAY] track_invoice ناموفق: {e}")

    await message.answer(
        f"🧾 *فاکتور پیش‌پرداخت ارسال شد.*\n\n"
        f"📦 تعداد ردیف: *{total}*\n"
        f"💰 مبلغ: *{prepay_rial // 10:,} تومان* ({per_row_toman:,} تومان برای هر ردیف)\n"
        f"🔹 کد پیگیری: `{tracking_code}`\n\n"
        f"پس از پرداخت، ثبت ردیف‌ها شروع می‌شود. این مبلغ در پایان از هزینهٔ سامانه کسر می‌شود.",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )


async def check_bulk_prepay_successful_payment(message: Message, state: FSMContext, bot):
    """پرداخت پیش‌پرداخت دسته‌جمعی چک (از global_successful_payment_handler)."""
    import json as _json
    user_id = message.from_user.id
    payment = message.successful_payment
    try:
        payload = _json.loads(payment.invoice_payload or "{}")
    except Exception:
        payload = {}
    data = await state.get_data()
    tracking_code = payload.get("tracking_code") or data.get("bulk_prepay_tracking_code", "")
    task = BULK_TASKS.get(tracking_code)

    from config import ADMIN_ID
    if not task or task.get("user_id") != user_id or task.get("status") != "awaiting_prepay":
        logger.error(f"[CHECK-BULK-PREPAY] بچ معتبر یافت نشد: user={user_id}, tc={tracking_code}, "
                     f"status={(task or {}).get('status')}")
        await message.answer("✅ پرداخت شما دریافت شد.\n⚠️ اطلاعات این دسته پیدا نشد؛ به مدیریت اطلاع داده شد.")
        try:
            await bot.send_message(
                ADMIN_ID,
                f"⚠️ [CHECK-BULK-PREPAY] پرداخت بدون بچ معتبر — user={user_id}, کد={tracking_code}, "
                f"مبلغ={payment.total_amount:,} ریال, payment_id={payment.telegram_payment_charge_id}")
        except Exception:
            pass
        await state.clear()
        return

    await state.clear()
    task["prepaid_total_rial"] = int(payment.total_amount or task.get("prepaid_total_rial", 0))
    total = len(task.get("items", []))
    await message.answer(
        f"✅ *پرداخت پیش‌پرداخت تایید شد* ({task['prepaid_total_rial'] // 10:,} تومان).",
        parse_mode="Markdown")

    try:
        from sheets import log_event
        await log_event(
            "پرداخت", "پیش‌پرداخت دسته‌جمعی چک", message.from_user.full_name, user_id,
            doc_name=f"پیش‌پرداخت دسته‌جمعی {total} ردیف چک", payment_status="پرداخت شده",
            note=f"مبلغ: {task['prepaid_total_rial']:,} ریال | tracking: {tracking_code} | "
                 f"payment_id: {payment.telegram_payment_charge_id}")
    except Exception as e:
        logger.warning(f"[CHECK-BULK-PREPAY] log_event ناموفق: {e}")
    try:
        await bot.send_message(
            ADMIN_ID,
            f"💰 پیش‌پرداخت دسته‌جمعی چک پرداخت شد\n\n"
            f"👤 کاربر: {message.from_user.full_name} ({user_id})\n"
            f"📦 {total} ردیف | کد: {tracking_code}\n"
            f"💰 مبلغ: {task['prepaid_total_rial'] // 10:,} تومان\n"
            f"🎫 payment_id: {payment.telegram_payment_charge_id}")
    except Exception as e:
        logger.warning(f"[CHECK-BULK-PREPAY] اطلاع به مدیر ناموفق: {e}")

    await queue_check_bulk(bot, user_id, tracking_code)


async def queue_check_bulk(bot, user_id: int, tracking_code: str):
    """همهٔ ردیف‌های بچ را (با کپی برای ادمین) در صف ثبت می‌گذارد."""
    task = BULK_TASKS[tracking_code]
    task["status"] = "processing"
    items = task["items"]
    total = len(items)

    from config import ADMIN_ID
    from admin_forward import send_check_submission_to_admin

    queued = 0
    for idx, item in enumerate(items, start=1):
        row_index = item.get("_bulk_row_index") or item.get("row_index") or idx
        try:
            job = build_check_bulk_job(item, user_id, tracking_code, row_index)
            try:
                await send_check_submission_to_admin(bot, ADMIN_ID, user_id, job)
            except Exception as e:
                logger.error(f"[CHECK-BULK] خطا در ارسال کپی ردیف {row_index} به ادمین: {e}", exc_info=True)
            await runtime_state.job_queue.put(job)
            queued += 1
        except Exception as e:
            logger.error(f"[CHECK-BULK] خطا در صف‌بندی ردیف {row_index}: {e}", exc_info=True)
            task["failures"].append({
                "row_index": row_index,
                "title": item.get("check_request_title", "?"),
                "error": str(e),
            })

    task["queued_count"] = queued

    from keyboards import flow_type_kb
    await bot.send_message(
        user_id,
        f"✅ *{queued} از {total} ردیف چک در صف ثبت قرار گرفت.*\n\n"
        f"🔒 کد پیگیری دسته‌جمعی: `{tracking_code}`\n\n"
        f"⏳ ردیف‌ها یکی‌یکی ثبت می‌شوند و نتیجهٔ هر ردیف برایتان ارسال می‌شود.\n"
        f"💳 پس از پایان همهٔ ردیف‌ها، گزارش مالی و فاکتور تسویهٔ باقیماندهٔ هزینهٔ سامانه ارسال می‌شود.",
        parse_mode="Markdown",
        reply_markup=flow_type_kb,
    )

    if queued == 0:
        from bulk_submissions import finalize_bulk_batch
        await finalize_bulk_batch(bot, user_id, tracking_code)
