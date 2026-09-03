"""
هندلرهای تلگرام برای مرحله اخذ امضای الکترونیک لایحه.

جریان جدید (مشابه اظهارنامه):
  ۱. پس از پرداخت موفق، پیام «آمادگی برای ارسال کد» ارسال می‌شود
  ۲. کاربر «آماده‌ام» می‌زند → ناوبری به صفحه امضا → نمایش لیست اشخاص
  ۳. کاربر یک شخص را انتخاب می‌کند → کد موقت برای آن شخص ارسال می‌شود
  ۴. کاربر کد را ارسال می‌کند → امضا ثبت می‌شود
  ۵. اگر موفق بود → شخص از لیست حذف می‌شود → نفر بعدی
  ۶. اگر رمز اشتباه بود → ۲۰ دقیقه صبر → سپس امکان ارسال مجدد
  ۷. اگر ۶ دقیقه از ارسال کد گذشت و کد نفرستاد → مهلت تمام
  ۸. اگر ۶۰ دقیقه بدون اقدام گذشت → پیام واتساپ
"""

import asyncio
import datetime
import logging

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove, ReplyKeyboardMarkup, KeyboardButton

import runtime_state
from config import ADMIN_ID
from panel_sync import mark_case_ready_to_send_by_tracking
from keyboards import (
    lavayeh_sign_ready_kb,
    lavayeh_sign_resend_kb,
    lavayeh_sign_later_kb,
    lavayeh_sign_try_again_kb,
    restart_kb,
    ezhhar_sign_ready_kb,
    ezhhar_sign_resend_kb,
    ezhhar_sign_later_kb,
    ezhhar_sign_try_again_kb)
from states import Form

lavayeh_sign_router = Router()

# تایم‌اوت‌ها
LAVAYEH_SIGN_CODE_TIMEOUT = 6 * 60     # ۶ دقیقه مهلت ارسال کد
LAVAYEH_SIGN_WRONG_CODE_WAIT = 20 * 60  # ۲۰ دقیقه صبر بعد از کد اشتباه
LAVAYEH_SIGN_NO_ACTION_TIMEOUT = 60 * 60  # ۶۰ دقیقه بدون اقدام


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۱ — آمادگی کاربر برای ارسال کد
# ══════════════════════════════════════════════════════════════════════════════

@lavayeh_sign_router.message(Form.lavayeh_sign_ready, F.text == "✅ آماده‌ام، کد امضا ارسال شود")
async def sign_ready_handler(message: Message, state: FSMContext, bot: Bot):
    """کاربر آمادگی خود را اعلام کرد — ناوبری به صفحه امضا و نمایش لیست اشخاص"""
    user_id = message.from_user.id

    sign_info = runtime_state.pending_lavayeh_sign.get(user_id)
    if not sign_info:
        await message.answer(
            "⚠️ اطلاعات لایحه برای ارسال کد امضا یافت نشد. لطفاً مجدداً شروع کنید.",
            reply_markup=restart_kb
        )
        await state.clear()
        return

    await message.answer(
        "⏳ *در حال اتصال به سامانه...*",
        reply_markup=ReplyKeyboardRemove())

    # ثبت زمان شروع برای ۶۰ دقیقه بدون اقدام
    sign_info["total_no_action_start"] = datetime.datetime.now()
    runtime_state.pending_lavayeh_sign[user_id] = sign_info

    # ارسال تسک ناوبری به صفحه امضا
    # ⭐ sign_menu_path (مسیر منوی سامانه برای همین سند — برای چک متفاوت از
    # لایحه است) پاس می‌شود تا navigate_to_sign_page از مسیر درست برود.
    await runtime_state.job_queue.put({
        "user_id": user_id,
        "task_type": "LAVAYEH_SEND_SIGN_CODE",
        "tracking_code": sign_info["tracking_code"],
        "phase": "navigate",  # فقط ناوبری و دریافت لیست اشخاص
        "sign_menu_path": sign_info.get("sign_menu_path"),
    })

    # شروع تایمر ۶۰ دقیقه بدون اقدام
    asyncio.create_task(_lavayeh_no_action_60min_watcher(bot, user_id, state))


@lavayeh_sign_router.message(Form.lavayeh_sign_ready)
async def sign_ready_invalid(message: Message):
    await message.answer(
        "لطفاً از دکمه زیر استفاده کنید:",
        reply_markup=lavayeh_sign_ready_kb
    )


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۲ — انتخاب شخص جهت ارسال کد
# ══════════════════════════════════════════════════════════════════════════════

@lavayeh_sign_router.message(Form.lavayeh_sign_person_select)
async def lavayeh_sign_person_select_handler(message: Message, state: FSMContext, bot: Bot):
    """کاربر شخصی را برای ارسال کد انتخاب کرد"""
    user_id = message.from_user.id
    text = (message.text or "").strip()

    sign_info = runtime_state.pending_lavayeh_sign.get(user_id)
    if not sign_info:
        await message.answer("⚠️ اطلاعات یافت نشد.", reply_markup=restart_kb)
        await state.clear()
        return

    all_persons = sign_info.get("sign_persons", [])
    persons_awaiting = sign_info.get("persons_awaiting_sign", [])

    # یافتن شخص انتخاب‌شده
    selected_idx = None
    for idx in persons_awaiting:
        person = next((p for p in all_persons if p["idx"] == idx), None)
        if person:
            name = person.get("name", "")
            person_type = person.get("personType", "")
            expected = f"ارسال کد برای {name}"
            if text == expected or name in text:
                selected_idx = idx
                break

    if selected_idx is None:
        await message.answer(
            "⚠️ لطفاً یکی از اشخاص لیست‌شده را انتخاب کنید."
        )
        return

    person = next((p for p in all_persons if p["idx"] == selected_idx), {})
    person_name = person.get("name", f"شخص {selected_idx + 1}")

    await message.answer(
        "⏳ *در حال ارسال رمز موقت امضا...*\n\n"
        "کد تا دقایق دیگر ارسال می‌گردد.\n"
        "⚠️ توجه داشته باشید مهلت کد کلاً *۶ دقیقه* می‌باشد.",
        reply_markup=ReplyKeyboardRemove())

    sign_info["current_person_idx"] = selected_idx
    sign_info["sign_sent_time"] = datetime.datetime.now()
    sign_info["code_sent_announce_time"] = datetime.datetime.now()
    runtime_state.pending_lavayeh_sign[user_id] = sign_info

    # ارسال تسک به صف
    await runtime_state.job_queue.put({
        "user_id": user_id,
        "task_type": "LAVAYEH_SEND_SIGN_CODE",
        "tracking_code": sign_info["tracking_code"],
        "phase": "send_code",
        "target_row_indices": [selected_idx],
    })

    await state.set_state(Form.lavayeh_sign_code_input)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۳ — دریافت کد امضا از کاربر
# ══════════════════════════════════════════════════════════════════════════════

@lavayeh_sign_router.message(Form.lavayeh_sign_code_input)
async def sign_code_input_handler(message: Message, state: FSMContext, bot: Bot):
    """دریافت کد امضا از کاربر"""
    user_id = message.from_user.id
    text = (message.text or "").strip()

    sign_info = runtime_state.pending_lavayeh_sign.get(user_id)
    if not sign_info:
        await message.answer("⚠️ اطلاعات لایحه یافت نشد.", reply_markup=restart_kb)
        await state.clear()
        return

    # تبدیل اعداد فارسی/عربی
    _FA_AR = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    code = text.translate(_FA_AR).replace(" ", "").strip()

    if not code.isdigit() or not (3 <= len(code) <= 6):
        await message.answer(
            "⚠️ لطفاً *کد امضای دریافتی* را ارسال فرمایید:\n"
            "_(کد معمولاً ۵ رقمی است)_")
        return

    current_idx = sign_info.get("current_person_idx", 0)
    await message.answer(
        f"✅ کد `{code}` دریافت شد.\n⏳ در حال ثبت امضا در سامانه...",
        reply_markup=ReplyKeyboardRemove()
    )

    # ارسال تسک امضا به صف
    await runtime_state.job_queue.put({
        "user_id": user_id,
        "task_type": "LAVAYEH_SUBMIT_SIGN",
        "tracking_code": sign_info["tracking_code"],
        "row_idx": current_idx,
        "code": code,
    })


# ══════════════════════════════════════════════════════════════════════════════
# کال‌بک‌های موفقیت/خطا از سمت scenarios.py برای لایحه
# ══════════════════════════════════════════════════════════════════════════════

async def on_lavayeh_sign_persons_loaded(bot: Bot, user_id: int, persons: list, state: FSMContext):
    """
    پس از ناوبری موفق به صفحه امضا — لیست اشخاص نمایش داده می‌شود.
    persons: لیست اشخاص قابل امضا [{idx, name, personType, canSend, divVisible}]
    """
    sign_info = runtime_state.pending_lavayeh_sign.get(user_id, {})

    # ذخیره لیست اشخاص
    sendable = [p for p in persons if p.get("divVisible")]
    # اعمال قوانین مسیریابی کد: اگر وکیل وجود داشت فقط برای وکیل؛
    # در غیر این صورت اگر نماینده/مدیرعامل بود فقط برای آن‌ها؛ وگرنه همه.
    sendable = _filter_ezhhar_signable_persons(sendable)
    sign_info["sign_persons"] = sendable
    sign_info["persons_awaiting_sign"] = [p["idx"] for p in sendable]
    runtime_state.pending_lavayeh_sign[user_id] = sign_info

    if not sendable:
        await bot.send_message(
            user_id,
            "⚠️ *در جدول امضا، شخصی برای ارسال کد موقت یافت نشد.*\n\n"
            "احتمالاً همه اشخاص قبلاً امضا کرده‌اند یا نوع امضا متفاوت است.\n"
            "📲 چاپ لایحه خود را جهت ادامه تکمیل نمودن به واتساپ به شماره "
            "*09306186888* ارسال فرمائید.",
            reply_markup=restart_kb
        )
        runtime_state.pending_lavayeh_sign.pop(user_id, None)
        await state.clear()
        return

    # اگر فقط یک نفر هست، مستقیم کدش را ارسال کن
    if len(sendable) == 1:
        person = sendable[0]
        person_name = person.get("name", f"شخص {person['idx'] + 1}")
        sign_info["current_person_idx"] = person["idx"]
        sign_info["sign_sent_time"] = datetime.datetime.now()
        sign_info["code_sent_announce_time"] = datetime.datetime.now()
        runtime_state.pending_lavayeh_sign[user_id] = sign_info

        await bot.send_message(
            user_id,
            "⏳ *در حال ارسال رمز موقت امضا...*\n\n"
            "کد تا دقایق دیگر ارسال می‌گردد.\n"
            "⚠️ توجه داشته باشید مهلت کد کلاً *۶ دقیقه* می‌باشد.",
            reply_markup=ReplyKeyboardRemove())

        # ارسال تسک برای ارسال کد
        await runtime_state.job_queue.put({
            "user_id": user_id,
            "task_type": "LAVAYEH_SEND_SIGN_CODE",
            "tracking_code": sign_info["tracking_code"],
            "phase": "send_code",
            "target_row_indices": [person["idx"]],
        })

        await state.set_state(Form.lavayeh_sign_code_input)
        # شروع تایمر ۶ دقیقه
        asyncio.create_task(_lavayeh_code_entry_timeout_watcher(bot, user_id, state))
    else:
        # چند نفر هستند — نمایش لیست انتخاب
        person_buttons = []
        for p in sendable:
            name = p.get("name", f"شخص {p['idx'] + 1}")
            person_type = p.get("personType", "")
            label = f"ارسال کد برای {name}"
            person_buttons.append([KeyboardButton(text=label)])

        person_select_kb = ReplyKeyboardMarkup(keyboard=person_buttons, resize_keyboard=True)

        names_text = "\n".join([f"• {p.get('name', 'نامشخص')}" for p in sendable])

        await bot.send_message(
            user_id,
            f"📝 *انتخاب شخص جهت ارسال کد امضا:*\n\n"
            f"اشخاص قابل امضا:\n{names_text}\n\n"
            "لطفاً شخصی که در دسترس است و آماده دریافت کد می‌باشد را انتخاب کنید:\n"
            "_(فقط یک نفر انتخاب کنید)_",
            reply_markup=person_select_kb)
        await state.set_state(Form.lavayeh_sign_person_select)


async def on_lavayeh_sign_code_sent_success(bot: Bot, user_id: int, persons: list, state: FSMContext):
    """پس از ارسال موفق کد از سامانه — اطلاع به کاربر و انتظار کد"""
    sign_info = runtime_state.pending_lavayeh_sign.get(user_id, {})

    for person in persons:
        name = person.get("name", "نامشخص")
        await bot.send_message(
            user_id,
            "✅ *رمز موقت امضا ارسال شد.*\n\n"
            "⏰ مهلت استفاده از این کد *۶ دقیقه* می‌باشد.\n"
            "لطفاً کد دریافتی را هرچه سریع‌تر ارسال کنید.")

    sign_info["sign_sent_time"] = datetime.datetime.now()
    sign_info["code_sent_announce_time"] = datetime.datetime.now()
    runtime_state.pending_lavayeh_sign[user_id] = sign_info

    # شروع تایمر ۶ دقیقه از زمان ارسال کد
    asyncio.create_task(_lavayeh_code_entry_timeout_watcher(bot, user_id, state))


async def on_lavayeh_sign_code_sent_failure(bot: Bot, user_id: int, state: FSMContext):
    """ارسال کد ناموفق بود"""
    await bot.send_message(
        user_id,
        "⚠️ *سامانه در ارسال کد موقت با مشکل مواجه شد.*\n\n"
        "📲 لطفاً جهت ثبت امضا به شماره *09306186888* در واتساپ پیام دهید.",
        reply_markup=restart_kb
    )
    runtime_state.pending_lavayeh_sign.pop(user_id, None)
    await state.clear()


async def on_lavayeh_sign_submit_success(bot: Bot, user_id: int, row_idx: int, state: FSMContext):
    """امضای شخص با موفقیت انجام شد — حذف از لیست و ادامه"""
    sign_info = runtime_state.pending_lavayeh_sign.get(user_id)
    if not sign_info:
        return

    persons_awaiting = sign_info.get("persons_awaiting_sign", [])
    if row_idx in persons_awaiting:
        persons_awaiting.remove(row_idx)
    sign_info["persons_awaiting_sign"] = persons_awaiting
    runtime_state.pending_lavayeh_sign[user_id] = sign_info

    await bot.send_message(
        user_id,
        "✅ *امضای الکترونیک با موفقیت درج شد و مورد شما ارسال گردید.*\n\n"
        "باتشکر از همراهی شما 🙏")

    if not persons_awaiting:
        # همه امضا کردند
        runtime_state.pending_lavayeh_sign.pop(user_id, None)
        await bot.send_message(
            ADMIN_ID, f"✅ [SIGN] امضای لایحه کاربر {user_id} کامل شد."
        )
        try:
            tracking_code = sign_info.get("tracking_code", "")
            if tracking_code:
                svc_type = sign_info.get("service_type", "LAVAYEH")
                await mark_case_ready_to_send_by_tracking(user_id, svc_type, tracking_code)
        except Exception as panel_err:
            logging.warning(f"[SIGN] خطا در انتقال پرونده لایحه به آماده‌ارسال: {panel_err}")
        await state.clear()
    else:
        # اشخاص دیگری هم باید امضا کنند
        all_persons = sign_info.get("sign_persons", [])
        remaining_names = []
        for idx in persons_awaiting:
            person = next((p for p in all_persons if p["idx"] == idx), None)
            if person:
                remaining_names.append(person.get("name", f"شخص {idx + 1}"))

        remaining_text = "\n".join([f"• {n}" for n in remaining_names])

        person_buttons = []
        for idx in persons_awaiting:
            person = next((p for p in all_persons if p["idx"] == idx), None)
            if person:
                name = person.get("name", f"شخص {idx + 1}")
                person_type = person.get("personType", "")
                label = f"ارسال کد برای {name}"
                person_buttons.append([KeyboardButton(text=label)])

        person_select_kb = ReplyKeyboardMarkup(keyboard=person_buttons, resize_keyboard=True)

        await bot.send_message(
            user_id,
            f"افراد باقی‌مانده جهت امضا:\n{remaining_text}\n\n"
            "لطفاً شخص بعدی که در دسترس است را انتخاب کنید:",
            reply_markup=person_select_kb)
        await state.set_state(Form.lavayeh_sign_person_select)


async def on_lavayeh_sign_wrong_code(bot: Bot, user_id: int, row_idx: int, state: FSMContext):
    """رمز موقت اشتباه بود — ۲۰ دقیقه صبر و سپس امکان ارسال مجدد"""
    sign_info = runtime_state.pending_lavayeh_sign.get(user_id)
    if not sign_info:
        return

    sign_info["wrong_code_time"] = datetime.datetime.now()
    runtime_state.pending_lavayeh_sign[user_id] = sign_info

    await bot.send_message(
        user_id,
        "⚠️ *رمز موقت اشتباه است.*\n\n"
        "لطفاً *۲۰ دقیقه* دیگر امتحان کنید.\n"
        "بعد از ۲۰ دقیقه می‌توانید درخواست کد جدید بدهید.",
        reply_markup=ReplyKeyboardRemove())

    await state.set_state(Form.lavayeh_sign_wrong_code_wait)
    asyncio.create_task(_lavayeh_wrong_code_waiter(bot, user_id, state))


async def on_lavayeh_sign_submit_failure(bot: Bot, user_id: int, state: FSMContext):
    """امضا ناموفق بود — سوال ارسال مجدد"""
    await bot.send_message(
        user_id,
        "⚠️ *خطا در ثبت امضا.*\n\n"
        "آیا می‌خواهید کد جدید ارسال شود؟",
        reply_markup=lavayeh_sign_try_again_kb)
    await state.set_state(Form.lavayeh_sign_resend_prompt)


async def on_lavayeh_sign_sana_not_registered(bot: Bot, user_id: int, error_text: str, state: FSMContext):
    """امضای شخص در سامانه ثنا ثبت نیست — ارجاع به دفاتر خدمات قضایی (لایحه)"""
    await bot.send_message(
        user_id,
        f"⚠️ *خطا در ثبت امضا:*\n\n"
        f"{error_text}\n\n"
        "امضا در سامانه ثنا ثبت نیست، ابتدا به یکی از دفاتر خدمات قضائی مراجعه کنند و پس از تایید امضا "
        "با شماره *09306186888* در واتساپ هماهنگ کنید، جهت ارسال کد مجدد.\n"
        "باتشکر",
        reply_markup=restart_kb
    )
    runtime_state.pending_lavayeh_sign.pop(user_id, None)
    await state.clear()


# ══════════════════════════════════════════════════════════════════════════════
# هندلرهای تایم‌اوت و ارسال مجدد لایحه
# ══════════════════════════════════════════════════════════════════════════════

async def _lavayeh_code_entry_timeout_watcher(bot: Bot, user_id: int, state: FSMContext):
    """۶ دقیقه از زمان ارسال کد موقت — اگر کاربر کد نفرست، مهلت تمام شده"""
    await asyncio.sleep(LAVAYEH_SIGN_CODE_TIMEOUT)

    sign_info = runtime_state.pending_lavayeh_sign.get(user_id)
    if not sign_info:
        return

    current_state = await state.get_state()
    if current_state not in (Form.lavayeh_sign_person_select, Form.lavayeh_sign_code_input):
        return

    try:
        await bot.send_message(
            user_id,
            "⏰ *مهلت رمز موقت به پایان رسید.*\n\n"
            "لطفاً *۲۰ دقیقه* دیگر امتحان کنید.\n"
            "بعد از ۲۰ دقیقه می‌توانید مجدداً آمادگی خود را اعلام فرمایید.",
            reply_markup=ReplyKeyboardRemove())
        await state.set_state(Form.lavayeh_sign_wrong_code_wait)
        asyncio.create_task(_lavayeh_wrong_code_waiter(bot, user_id, state))
    except Exception as e:
        logging.error(f"[SIGN] خطا در code_entry_timeout_watcher: {e}")


async def _lavayeh_wrong_code_waiter(bot: Bot, user_id: int, state: FSMContext):
    """۲۰ دقیقه صبر بعد از کد اشتباه یا انقضای مهلت — سپس اجازه ارسال مجدد"""
    await asyncio.sleep(LAVAYEH_SIGN_WRONG_CODE_WAIT)

    sign_info = runtime_state.pending_lavayeh_sign.get(user_id)
    if not sign_info:
        return

    current_state = await state.get_state()
    if current_state != Form.lavayeh_sign_wrong_code_wait:
        return

    try:
        all_persons = sign_info.get("sign_persons", [])
        persons_awaiting = sign_info.get("persons_awaiting_sign", [])
        current_idx = sign_info.get("current_person_idx")

        # اگر هنوز این شخص در لیست انتظار هست
        if current_idx in persons_awaiting:
            person = next((p for p in all_persons if p["idx"] == current_idx), {})
            person_name = person.get("name", "شخص")

            person_buttons = []
            for idx in persons_awaiting:
                person = next((p for p in all_persons if p["idx"] == idx), None)
                if person:
                    name = person.get("name", f"شخص {idx + 1}")
                    person_type = person.get("personType", "")
                    label = f"ارسال کد برای {name}"
                    person_buttons.append([KeyboardButton(text=label)])

            person_select_kb = ReplyKeyboardMarkup(keyboard=person_buttons, resize_keyboard=True)

            await bot.send_message(
                user_id,
                f"⏰ *۲۰ دقیقه گذشت.*\n\n"
                "اگر در دسترس می‌باشید، لطفاً گزینه زیر را مجدداً انتخاب کنید تا کد جدید ارسال شود:",
                reply_markup=person_select_kb)
            await state.set_state(Form.lavayeh_sign_person_select)
        else:
            await bot.send_message(
                user_id,
                "⏰ *۲۰ دقیقه گذشت.*\n\n"
                "لطفاً مجدداً آمادگی خود را اعلام فرمایید.",
                reply_markup=lavayeh_sign_ready_kb)
            await state.set_state(Form.lavayeh_sign_ready)

    except Exception as e:
        logging.error(f"[SIGN] خطا در wrong_code_waiter: {e}")


async def _lavayeh_no_action_60min_watcher(bot: Bot, user_id: int, state: FSMContext):
    """۶۰ دقیقه بدون هیچ اقدامی — ارسال پیام واتساپ"""
    await asyncio.sleep(LAVAYEH_SIGN_NO_ACTION_TIMEOUT)

    sign_info = runtime_state.pending_lavayeh_sign.get(user_id)
    if not sign_info:
        return

    try:
        await bot.send_message(
            user_id,
            "⏰ *مهلت امضا به پایان رسید.*\n\n"
            "لطفاً جهت ثبت امضا به شماره *09306186888* در واتساپ "
            "پیام دهید تا امور شما تکمیل گردد.",
            reply_markup=restart_kb)
        await bot.send_message(
            ADMIN_ID,
            f"⏰ [SIGN] کاربر {user_id} پس از ۶۰ دقیقه اقدامی نکرد."
        )
    except Exception as e:
        logging.error(f"[SIGN] خطا در 60min watcher: {e}")

    runtime_state.pending_lavayeh_sign.pop(user_id, None)
    try:
        await state.clear()
    except Exception:
        pass


@lavayeh_sign_router.message(Form.lavayeh_sign_resend_prompt, F.text == "بله، کد جدید ارسال شود")
async def lavayeh_sign_resend_yes(message: Message, state: FSMContext, bot: Bot):
    """کاربر خواست کد جدید ارسال شود — بازگشت به انتخاب شخص"""
    user_id = message.from_user.id
    sign_info = runtime_state.pending_lavayeh_sign.get(user_id)
    if not sign_info:
        await message.answer("⚠️ اطلاعات یافت نشد.", reply_markup=restart_kb)
        await state.clear()
        return

    all_persons = sign_info.get("sign_persons", [])
    persons_awaiting = sign_info.get("persons_awaiting_sign", [])

    person_buttons = []
    for idx in persons_awaiting:
        person = next((p for p in all_persons if p["idx"] == idx), None)
        if person:
            name = person.get("name", f"شخص {idx + 1}")
            person_type = person.get("personType", "")
            label = f"ارسال کد برای {name}"
            person_buttons.append([KeyboardButton(text=label)])

    person_select_kb = ReplyKeyboardMarkup(keyboard=person_buttons, resize_keyboard=True)

    await message.answer(
        "📝 *انتخاب شخص جهت ارسال کد جدید:*\n\n"
        "لطفاً شخصی که در دسترس است را انتخاب کنید:",
        reply_markup=person_select_kb)
    await state.set_state(Form.lavayeh_sign_person_select)


@lavayeh_sign_router.message(Form.lavayeh_sign_resend_prompt, F.text == "خیر")
async def lavayeh_sign_resend_no(message: Message, state: FSMContext):
    """کاربر نمی‌خواهد کد جدید — سوال اقدام بعدی"""
    await message.answer(
        "آیا بعداً اقدام می‌کنید؟",
        reply_markup=lavayeh_sign_later_kb
    )
    await state.set_state(Form.lavayeh_sign_later_prompt)


@lavayeh_sign_router.message(Form.lavayeh_sign_later_prompt, F.text == "بله")
async def lavayeh_sign_later_yes(message: Message, state: FSMContext):
    await message.answer(
        "✅ *لایحه ثبتی تا ۲۴ ساعت آینده قابلیت تکمیل شدن را دارد.*\n\n"
        "📲 لطفاً جهت ثبت امضا به شماره *09306186888* در واتساپ پیام دهید.",
        reply_markup=restart_kb)
    runtime_state.pending_lavayeh_sign.pop(message.from_user.id, None)
    await state.clear()


@lavayeh_sign_router.message(Form.lavayeh_sign_later_prompt, F.text == "خیر")
async def lavayeh_sign_later_no(message: Message, state: FSMContext):
    await message.answer(
        "📲 لطفاً جهت ثبت امضا به شماره *09306186888* در واتساپ پیام دهید.",
        reply_markup=restart_kb)
    runtime_state.pending_lavayeh_sign.pop(message.from_user.id, None)
    await state.clear()


# ══════════════════════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════════════════════
# بخش اخذ امضای الکترونیک اظهارنامه (رویکرد دو فازی — اصلاح شده)
# ══════════════════════════════════════════════════════════════════════════════

# تایم‌اوت‌ها
EZHHAR_SIGN_CODE_TIMEOUT = 6 * 60     # ۶ دقیقه مهلت ارسال کد
EZHHAR_SIGN_WRONG_CODE_WAIT = 20 * 60  # ۲۰ دقیقه صبر بعد از کد اشتباه
EZHHAR_SIGN_NO_ACTION_TIMEOUT = 60 * 60  # ۶۰ دقیقه بدون اقدام

EZHHAR_CODE_ENTRY_TIMEOUT = 6 * 60


def _filter_ezhhar_signable_persons(persons: list) -> list:
    """
    فیلتر اشخاص قابل امضا بر اساس قوانین:
      - اگر وکیل (PersonType==6) وجود داشت → فقط وکیل
      - اگر نماینده/مدیرعامل داشت → همه آن‌ها (نماینده و مدیرعامل)
      - در غیر این صورت → همه اشخاص قابل ارسال
    """
    has_lawyer = any(p.get("personType") == "وکیل" for p in persons)
    if has_lawyer:
        return [p for p in persons if p.get("personType") == "وکیل"]

    reps = [p for p in persons if p.get("personType") in ("نماینده", "مدیرعامل")]
    if reps:
        return reps

    return persons


@lavayeh_sign_router.message(Form.ezhhar_sign_ready, F.text == "✅ آماده‌ام، کد امضا ارسال شود")
async def ezhhar_sign_ready_handler(message: Message, state: FSMContext, bot: Bot):
    """کاربر آمادگی خود را اعلام کرد — ناوبری به صفحه امضا و نمایش لیست اشخاص"""
    user_id = message.from_user.id
    sign_info = runtime_state.pending_ezhhar_sign.get(user_id)
    if not sign_info:
        await message.answer(
            "⚠️ اطلاعات اظهارنامه برای ارسال کد امضا یافت نشد. لطفاً مجدداً شروع کنید.",
            reply_markup=restart_kb
        )
        await state.clear()
        return

    await message.answer(
        "⏳ *در حال اتصال به سامانه...*",
        reply_markup=ReplyKeyboardRemove())

    # ثبت زمان شروع برای ۶۰ دقیقه بدون اقدام
    sign_info["total_no_action_start"] = datetime.datetime.now()
    runtime_state.pending_ezhhar_sign[user_id] = sign_info

    # ارسال تسک ناوبری به صفحه امضا (فاز ۱)
    await runtime_state.job_queue.put({
        "user_id": user_id,
        "task_type": "EZHHARNAMEH_SEND_SIGN_CODE",
        "tracking_code": sign_info["tracking_code"],
        "phase": "navigate",  # فقط ناوبری و دریافت لیست اشخاص
    })

    # شروع تایمر ۶۰ دقیقه بدون اقدام
    asyncio.create_task(_ezhhar_no_action_60min_watcher(bot, user_id, state))


@lavayeh_sign_router.message(Form.ezhhar_sign_ready)
async def ezhhar_sign_ready_invalid(message: Message):
    await message.answer(
        "لطفاً از دکمه زیر استفاده کنید:",
        reply_markup=ezhhar_sign_ready_kb
    )


@lavayeh_sign_router.message(Form.ezhhar_sign_person_select)
async def ezhhar_sign_person_select_handler(message: Message, state: FSMContext, bot: Bot):
    """کاربر شخصی را برای ارسال کد انتخاب کرد"""
    user_id = message.from_user.id
    text = (message.text or "").strip()

    sign_info = runtime_state.pending_ezhhar_sign.get(user_id)
    if not sign_info:
        await message.answer("⚠️ اطلاعات یافت نشد.", reply_markup=restart_kb)
        await state.clear()
        return

    all_persons = sign_info.get("sign_persons", [])
    persons_awaiting = sign_info.get("persons_awaiting_sign", [])

    # یافتن شخص انتخاب‌شده
    selected_idx = None
    for idx in persons_awaiting:
        person = next((p for p in all_persons if p["idx"] == idx), None)
        if person:
            name = person.get("name", "")
            person_type = person.get("personType", "")
            expected = f"ارسال کد برای {name}"
            if text == expected or name in text:
                selected_idx = idx
                break

    if selected_idx is None:
        await message.answer(
            "⚠️ لطفاً یکی از اشخاص لیست‌شده را انتخاب کنید."
        )
        return

    person = next((p for p in all_persons if p["idx"] == selected_idx), {})
    person_name = person.get("name", f"شخص {selected_idx + 1}")

    await message.answer(
        "⏳ *در حال ارسال رمز موقت امضا...*\n\n"
        "کد تا دقایق دیگر ارسال می‌گردد.\n"
        "⚠️ توجه داشته باشید مهلت کد کلاً *۶ دقیقه* می‌باشد.",
        reply_markup=ReplyKeyboardRemove())

    sign_info["current_person_idx"] = selected_idx
    sign_info["sign_sent_time"] = datetime.datetime.now()
    sign_info["sign_codes_received"] = {}
    runtime_state.pending_ezhhar_sign[user_id] = sign_info

    # ارسال تسک به صف (فاز ۲: ارسال کد)
    await runtime_state.job_queue.put({
        "user_id": user_id,
        "task_type": "EZHHARNAMEH_SEND_SIGN_CODE",
        "tracking_code": sign_info["tracking_code"],
        "phase": "send_code",
        "target_row_indices": [selected_idx],
    })

    await state.set_state(Form.ezhhar_sign_code_input)


@lavayeh_sign_router.message(Form.ezhhar_sign_code_input)
async def ezhhar_sign_code_input_handler(message: Message, state: FSMContext, bot: Bot):
    """دریافت کد امضا از کاربر برای اظهارنامه"""
    user_id = message.from_user.id
    text = (message.text or "").strip()

    sign_info = runtime_state.pending_ezhhar_sign.get(user_id)
    if not sign_info:
        await message.answer("⚠️ اطلاعات اظهارنامه یافت نشد.", reply_markup=restart_kb)
        await state.clear()
        return

    # تبدیل اعداد فارسی/عربی
    _FA_AR = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧۸۹", "01234567890123456789")
    code = text.translate(_FA_AR).replace(" ", "").strip()

    if not code.isdigit() or not (3 <= len(code) <= 6):
        await message.answer(
            "⚠️ لطفاً *کد امضای دریافتی* را ارسال فرمایید:\n"
            "_(کد معمولاً ۵ رقمی است)_")
        return

    current_idx = sign_info.get("current_person_idx", 0)
    await message.answer(
        f"✅ کد `{code}` دریافت شد.\n⏳ در حال ثبت امضا در سامانه...",
        reply_markup=ReplyKeyboardRemove()
    )

    # ارسال تسک امضا به صف
    await runtime_state.job_queue.put({
        "user_id": user_id,
        "task_type": "EZHHARNAMEH_SUBMIT_SIGN",
        "tracking_code": sign_info["tracking_code"],
        "row_idx": current_idx,
        "code": code,
    })


# ══════════════════════════════════════════════════════════════════════════════
# کال‌بک‌های موفقیت/خطا از سمت scenarios.py برای اظهارنامه
# ══════════════════════════════════════════════════════════════════════════════

async def on_ezhhar_sign_persons_loaded(bot: Bot, user_id: int, persons: list, state: FSMContext):
    """
    پس از ناوبری موفق به صفحه امضا — لیست اشخاص نمایش داده می‌شود.
    persons: لیست اشخاص قابل امضا [{idx, name, personType, canSend, divVisible}]
    """
    sign_info = runtime_state.pending_ezhhar_sign.get(user_id, {})

    # فیلتر اشخاص قابل ارسال
    sendable = [p for p in persons if p.get("divVisible")]
    sendable = _filter_ezhhar_signable_persons(sendable)

    # جایگزینی نام‌های خالی با نام پیش‌فرض
    for p in sendable:
        if not p.get("name", "").strip():
            fallback_name = f"شخص {p.get('idx', 0) + 1}"
            p["name"] = fallback_name
            logging.warning(f"[EZHHAR_SIGN] نام خالی برای ردیف {p.get('idx')} — از '{fallback_name}' استفاده شد")

    # ذخیره لیست اشخاص
    sign_info["sign_persons"] = sendable
    sign_info["persons_awaiting_sign"] = [p["idx"] for p in sendable]
    runtime_state.pending_ezhhar_sign[user_id] = sign_info

    if not sendable:
        await bot.send_message(
            user_id,
            "⚠️ *در جدول امضا اظهارنامه، شخصی برای ارسال کد موقت یافت نشد.*\n\n"
            "احتمالاً همه اشخاص قبلاً امضا کرده‌اند.\n"
            "لطفاً جهت ثبت امضا به شماره *09306186888* در واتساپ پیام دهید.",
            reply_markup=restart_kb
        )
        runtime_state.pending_ezhhar_sign.pop(user_id, None)
        await state.clear()
        return

    # اگر فقط یک نفر هست، مستقیم کدش را ارسال کن
    if len(sendable) == 1:
        person = sendable[0]
        person_name = person.get("name", f"شخص {person['idx'] + 1}")
        sign_info["current_person_idx"] = person["idx"]
        sign_info["sign_sent_time"] = datetime.datetime.now()
        sign_info["code_sent_announce_time"] = datetime.datetime.now()
        runtime_state.pending_ezhhar_sign[user_id] = sign_info

        await bot.send_message(
            user_id,
            "⏳ *در حال ارسال رمز موقت امضا...*\n\n"
            "کد تا دقایق دیگر ارسال می‌گردد.\n"
            "⚠️ توجه داشته باشید مهلت کد کلاً *۶ دقیقه* می‌باشد.",
            reply_markup=ReplyKeyboardRemove())

        # ارسال تسک برای ارسال کد (فاز ۲)
        await runtime_state.job_queue.put({
            "user_id": user_id,
            "task_type": "EZHHARNAMEH_SEND_SIGN_CODE",
            "tracking_code": sign_info["tracking_code"],
            "phase": "send_code",
            "target_row_indices": [person["idx"]],
        })

        await state.set_state(Form.ezhhar_sign_code_input)
        asyncio.create_task(_ezhhar_code_entry_timeout_watcher(bot, user_id, state))
    else:
        # چند نفر هستند — نمایش لیست انتخاب
        person_buttons = []
        for p in sendable:
            name = p.get("name", f"شخص {p['idx'] + 1}")
            person_type = p.get("personType", "")
            label = f"ارسال کد برای {name}"
            person_buttons.append([KeyboardButton(text=label)])

        person_select_kb = ReplyKeyboardMarkup(keyboard=person_buttons, resize_keyboard=True)

        await bot.send_message(
            user_id,
            "📝 *انتخاب شخص جهت ارسال کد امضا:*\n\n"
            "لطفاً شخصی که در دسترس است و آماده دریافت کد می‌باشد را انتخاب کنید:\n"
            "_(فقط یک نفر انتخاب کنید)_",
            reply_markup=person_select_kb)
        await state.set_state(Form.ezhhar_sign_person_select)


async def on_ezhhar_sign_code_sent_success(bot: Bot, user_id: int, persons: list, state: FSMContext):
    """پس از ارسال موفق کد از سامانه — اطلاع به کاربر و انتظار کد"""
    sign_info = runtime_state.pending_ezhhar_sign.get(user_id, {})
    sent_persons = [p for p in persons if p.get("sent")]

    for person in sent_persons:
        name = person.get("name", "نامشخص")
        await bot.send_message(
            user_id,
            "✅ *رمز موقت امضا ارسال شد.*\n\n"
            "⏰ مهلت استفاده از این کد *۶ دقیقه* می‌باشد.\n"
            "لطفاً کد دریافتی را هرچه سریع‌تر ارسال کنید.")

    sign_info["sign_sent_time"] = datetime.datetime.now()
    sign_info["code_sent_announce_time"] = datetime.datetime.now()
    runtime_state.pending_ezhhar_sign[user_id] = sign_info

    asyncio.create_task(_ezhhar_code_entry_timeout_watcher(bot, user_id, state))


async def on_ezhhar_sign_code_sent_failure(bot: Bot, user_id: int, state: FSMContext):
    """ارسال کد ناموفق بود"""
    await bot.send_message(
        user_id,
        "⚠️ *سامانه در ارسال کد موقت با مشکل مواجه شد.*\n\n"
        "📲 لطفاً جهت ثبت امضا به شماره *09306186888* در واتساپ پیام دهید.",
        reply_markup=restart_kb
    )
    runtime_state.pending_ezhhar_sign.pop(user_id, None)
    await state.clear()


async def on_ezhhar_sign_submit_success(bot: Bot, user_id: int, row_idx: int, state: FSMContext):
    """امضای شخص با موفقیت انجام شد — حذف از لیست و ادامه"""
    sign_info = runtime_state.pending_ezhhar_sign.get(user_id)
    if not sign_info:
        return

    persons_awaiting = sign_info.get("persons_awaiting_sign", [])
    if row_idx in persons_awaiting:
        persons_awaiting.remove(row_idx)
    sign_info["persons_awaiting_sign"] = persons_awaiting
    runtime_state.pending_ezhhar_sign[user_id] = sign_info

    if not persons_awaiting:
        runtime_state.pending_ezhhar_sign.pop(user_id, None)
        await bot.send_message(
            user_id,
            "✅ *امضای الکترونیک با موفقیت درج شد و مورد شما ارسال گردید.*\n\n"
            "باتشکر از همراهی شما 🙏",
            reply_markup=restart_kb)
        await bot.send_message(ADMIN_ID, f"✅ [EZHHAR_SIGN] امضای اظهارنامه کاربر {user_id} کامل شد.")
        try:
            tracking_code = sign_info.get("tracking_code", "")
            if tracking_code:
                svc_type = sign_info.get("service_type", "EZHHARNAMEH")
                await mark_case_ready_to_send_by_tracking(user_id, svc_type, tracking_code)
        except Exception as panel_err:
            logging.warning(f"[EZHHAR_SIGN] خطا در انتقال پرونده اظهارنامه به آماده‌ارسال: {panel_err}")
        await state.clear()
    else:
        all_persons = sign_info.get("sign_persons", [])
        remaining_names = []
        for idx in persons_awaiting:
            person = next((p for p in all_persons if p["idx"] == idx), None)
            if person:
                remaining_names.append(person.get("name", f"شخص {idx + 1}"))

        remaining_text = "\n".join([f"• {n}" for n in remaining_names])

        person_buttons = []
        for idx in persons_awaiting:
            person = next((p for p in all_persons if p["idx"] == idx), None)
            if person:
                name = person.get("name", f"شخص {idx + 1}")
                person_type = person.get("personType", "")
                label = f"ارسال کد برای {name}"
                person_buttons.append([KeyboardButton(text=label)])

        person_select_kb = ReplyKeyboardMarkup(keyboard=person_buttons, resize_keyboard=True)

        await bot.send_message(
            user_id,
            f"✅ *امضای الکترونیک با موفقیت درج شد و مورد شما ارسال گردید.*\n\n"
            f"افراد باقی‌مانده جهت امضا:\n{remaining_text}\n\n"
            "لطفاً شخص بعدی که در دسترس است را انتخاب کنید:",
            reply_markup=person_select_kb)
        await state.set_state(Form.ezhhar_sign_person_select)


async def on_ezhhar_sign_wrong_code(bot: Bot, user_id: int, row_idx: int, state: FSMContext):
    """رمز موقت اشتباه بود — ۲۰ دقیقه صبر و سپس امکان ارسال مجدد"""
    sign_info = runtime_state.pending_ezhhar_sign.get(user_id)
    if not sign_info:
        return

    sign_info["wrong_code_time"] = datetime.datetime.now()
    runtime_state.pending_ezhhar_sign[user_id] = sign_info

    await bot.send_message(
        user_id,
        "⚠️ *رمز موقت اشتباه است.*\n\n"
        "لطفاً *۲۰ دقیقه* دیگر امتحان کنید.\n"
        "بعد از ۲۰ دقیقه می‌توانید درخواست کد جدید بدهید.",
        reply_markup=ReplyKeyboardRemove())

    await state.set_state(Form.ezhhar_sign_wrong_code_wait)
    asyncio.create_task(_ezhhar_wrong_code_waiter(bot, user_id, state))


async def on_ezhhar_sign_sana_not_registered(bot: Bot, user_id: int, error_text: str, state: FSMContext):
    """امضای شخص در سامانه ثنا ثبت نیست — ارجاع به دفاتر خدمات قضایی"""
    await bot.send_message(
        user_id,
        f"⚠️ *خطا در ثبت امضا:*\n\n"
        f"{error_text}\n\n"
        "امضا در سامانه ثنا ثبت نیست، ابتدا به یکی از دفاتر خدمات قضائی مراجعه کنند و پس از تایید امضا "
        "با شماره *09306186888* در واتساپ هماهنگ کنید، جهت ارسال کد مجدد.\n"
        "باتشکر",
        reply_markup=restart_kb
    )
    runtime_state.pending_ezhhar_sign.pop(user_id, None)
    await state.clear()


async def on_ezhhar_sign_submit_failure(bot: Bot, user_id: int, state: FSMContext):
    """امضا ناموفق بود — سوال ارسال مجدد"""
    await bot.send_message(
        user_id,
        "⚠️ *خطا در ثبت امضا.*\n\n"
        "آیا می‌خواهید کد جدید ارسال شود؟",
        reply_markup=ezhhar_sign_try_again_kb)
    await state.set_state(Form.ezhhar_sign_resend_prompt)


# ══════════════════════════════════════════════════════════════════════════════
# هندلرهای تایم‌اوت و ارسال مجدد اظهارنامه
# ══════════════════════════════════════════════════════════════════════════════

async def _ezhhar_code_entry_timeout_watcher(bot: Bot, user_id: int, state: FSMContext):
    """۶ دقیقه از زمان ارسال کد موقت — اگر کاربر کد نفرست، مهلت تمام شده"""
    await asyncio.sleep(EZHHAR_CODE_ENTRY_TIMEOUT)

    sign_info = runtime_state.pending_ezhhar_sign.get(user_id)
    if not sign_info:
        return

    current_state = await state.get_state()
    if current_state not in (Form.ezhhar_sign_person_select, Form.ezhhar_sign_code_input):
        return

    try:
        await bot.send_message(
            user_id,
            "⏰ *مهلت رمز موقت به پایان رسیده است.*\n\n"
            "لطفاً *۲۰ دقیقه* دیگر امتحان کنید.",
            reply_markup=ezhhar_sign_ready_kb)
        await state.set_state(Form.ezhhar_sign_ready)
    except Exception as e:
        logging.error(f"[EZHHAR_SIGN] خطا در code_entry_timeout_watcher: {e}")


async def _ezhhar_wrong_code_waiter(bot: Bot, user_id: int, state: FSMContext):
    """۲۰ دقیقه صبر بعد از کد اشتباه — سپس اجازه ارسال مجدد"""
    await asyncio.sleep(EZHHAR_SIGN_WRONG_CODE_WAIT)

    sign_info = runtime_state.pending_ezhhar_sign.get(user_id)
    if not sign_info:
        return

    current_state = await state.get_state()
    if current_state != Form.ezhhar_sign_wrong_code_wait:
        return

    try:
        all_persons = sign_info.get("sign_persons", [])
        persons_awaiting = sign_info.get("persons_awaiting_sign", [])
        current_idx = sign_info.get("current_person_idx")

        if current_idx in persons_awaiting:
            person = next((p for p in all_persons if p["idx"] == current_idx), {})
            person_name = person.get("name", "شخص")

            person_buttons = []
            for idx in persons_awaiting:
                person = next((p for p in all_persons if p["idx"] == idx), None)
                if person:
                    name = person.get("name", f"شخص {idx + 1}")
                    person_type = person.get("personType", "")
                    label = f"ارسال کد برای {name}"
                    person_buttons.append([KeyboardButton(text=label)])

            person_select_kb = ReplyKeyboardMarkup(keyboard=person_buttons, resize_keyboard=True)

            await bot.send_message(
                user_id,
                f"⏰ *۲۰ دقیقه گذشت.*\n\n"
                "اگر در دسترس می‌باشید، لطفاً گزینه زیر را مجدداً انتخاب کنید تا کد جدید ارسال شود:",
                reply_markup=person_select_kb)
            await state.set_state(Form.ezhhar_sign_person_select)
        else:
            await bot.send_message(
                user_id,
                "⏰ *۲۰ دقیقه گذشت.*\n\n"
                "لطفاً مجدداً آمادگی خود را اعلام فرمایید.",
                reply_markup=ezhhar_sign_ready_kb)
            await state.set_state(Form.ezhhar_sign_ready)

    except Exception as e:
        logging.error(f"[EZHHAR_SIGN] خطا در wrong_code_waiter: {e}")


async def _ezhhar_no_action_60min_watcher(bot: Bot, user_id: int, state: FSMContext):
    """۶۰ دقیقه بدون هیچ اقدامی — ارسال پیام واتساپ"""
    await asyncio.sleep(EZHHAR_SIGN_NO_ACTION_TIMEOUT)

    sign_info = runtime_state.pending_ezhhar_sign.get(user_id)
    if not sign_info:
        return

    try:
        await bot.send_message(
            user_id,
            "⏰ *مهلت امضا به پایان رسید.*\n\n"
            "لطفاً جهت ثبت امضا به شماره *09306186888* در واتساپ "
            "پیام دهید تا امور شما تکمیل گردد.",
            reply_markup=restart_kb)
        await bot.send_message(
            ADMIN_ID,
            f"⏰ [EZHHAR_SIGN] کاربر {user_id} پس از ۶۰ دقیقه اقدامی نکرد."
        )
    except Exception as e:
        logging.error(f"[EZHHAR_SIGN] خطا در 60min watcher: {e}")

    runtime_state.pending_ezhhar_sign.pop(user_id, None)
    try:
        await state.clear()
    except Exception:
        pass


@lavayeh_sign_router.message(Form.ezhhar_sign_resend_prompt, F.text == "بله، کد جدید ارسال شود")
async def ezhhar_sign_resend_yes(message: Message, state: FSMContext, bot: Bot):
    """کاربر خواست کد جدید ارسال شود — بازگشت به انتخاب شخص"""
    user_id = message.from_user.id
    sign_info = runtime_state.pending_ezhhar_sign.get(user_id)
    if not sign_info:
        await message.answer("⚠️ اطلاعات یافت نشد.", reply_markup=restart_kb)
        await state.clear()
        return

    all_persons = sign_info.get("sign_persons", [])
    persons_awaiting = sign_info.get("persons_awaiting_sign", [])

    person_buttons = []
    for idx in persons_awaiting:
        person = next((p for p in all_persons if p["idx"] == idx), None)
        if person:
            name = person.get("name", f"شخص {idx + 1}")
            person_type = person.get("personType", "")
            label = f"ارسال کد برای {name}"
            person_buttons.append([KeyboardButton(text=label)])

    person_select_kb = ReplyKeyboardMarkup(keyboard=person_buttons, resize_keyboard=True)

    await message.answer(
        "📝 *انتخاب شخص جهت ارسال کد جدید:*\n\n"
        "لطفاً شخصی که در دسترس است را انتخاب کنید:",
        reply_markup=person_select_kb)
    await state.set_state(Form.ezhhar_sign_person_select)


@lavayeh_sign_router.message(Form.ezhhar_sign_resend_prompt, F.text == "خیر")
async def ezhhar_sign_resend_no(message: Message, state: FSMContext):
    """کاربر نمی‌خواهد کد جدید — سوال اقدام بعدی"""
    await message.answer(
        "آیا بعداً اقدام می‌کنید؟",
        reply_markup=ezhhar_sign_later_kb
    )
    await state.set_state(Form.ezhhar_sign_later_prompt)


@lavayeh_sign_router.message(Form.ezhhar_sign_later_prompt, F.text == "بله")
async def ezhhar_sign_later_yes(message: Message, state: FSMContext):
    await message.answer(
        "✅ *اظهارنامه تا ۲۴ ساعت آینده قابلیت تکمیل شدن را دارد.*\n\n"
        "📲 لطفاً جهت ثبت امضا به شماره *09306186888* در واتساپ پیام دهید.",
        reply_markup=restart_kb)
    runtime_state.pending_ezhhar_sign.pop(message.from_user.id, None)
    await state.clear()


@lavayeh_sign_router.message(Form.ezhhar_sign_later_prompt, F.text == "خیر")
async def ezhhar_sign_later_no(message: Message, state: FSMContext):
    await message.answer(
        "📲 لطفاً جهت ثبت امضا به شماره *09306186888* در واتساپ پیام دهید.",
        reply_markup=restart_kb)
    runtime_state.pending_ezhhar_sign.pop(message.from_user.id, None)
    await state.clear()
