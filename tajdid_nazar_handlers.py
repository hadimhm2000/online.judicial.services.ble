"""
هندلرهای بخش دعاوی اعتراضی — فلوی مکالمه تلگرام.

۷ نوع دعوی:
  تجدیدنظرخواهی، واخواهی، فرجام‌خواهی،
  اعاده دادرسی مدنی، اعاده دادرسی کیفری،
  اعتراض ثالث، اعتراض به قرار دادسرا

جریان:
  ۱. انتخاب نوع دعوی
  ۲. دریافت اطلاعات دادنامه (شماره ۱۸ رقمی، شماره پرونده، تاریخ، استان)
  ۳. حکم/قرار و مبلغ
  ۴. اعسار
  ۵. اشخاص تجدیدنظرخواه ← همان الگوی اظهارکننده اظهارنامه
  ۶. اشخاص تجدیدنظرخوانده ← همان الگوی مخاطب اظهارنامه
  ۷. شهود/مطلع (فقط حقیقی)
  ۸. شرح متن
  ۹. توضیحات جداگانه (اختیاری)
  ۱۰. مدارک ← همان الگوی اظهارنامه
  ۱۱. جهات (فقط اعاده دادرسی مدنی/کیفری)
  ۱۲. پیش‌نمایش و تایید
"""

import asyncio
import logging
import re

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

import runtime_state
from states import Form
from keyboards import (
    back_only_kb, restart_kb,
    representative_type_kb,
    create_province_kb,
    lavayeh_attachment_more_kb,
    ezhhar_attachment_title_kb_first,
    ezhhar_attachment_title_kb,
    ezhhar_attachment_more_kb,
    text_input_method_kb,
    tn_case_type_kb, tn_doc_type_kb, tn_amount_type_kb,
    tn_insolvency_kb, tn_extra_text_kb,
    tn_more_witnesses_kb, tn_confirm_kb, tn_edit_kb,
    tn_reason_more_kb, tn_amount_confirm_kb,
    create_tn_appellant_person_type_kb,
    create_tn_appellee_person_type_kb,
    create_tn_reasons_kb,
    create_tn_edit_kb,
    tn_sign_ready_kb, tn_sign_resend_kb, tn_sign_later_kb, tn_sign_try_again_kb)

tajdid_nazar_router = Router()
logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# ثابت‌ها
# ══════════════════════════════════════════════════════════════════════════════

_FA_AR = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789"
)

def _to_en(text: str) -> str:
    return text.translate(_FA_AR).replace(" ", "").strip()


def _validate_judge_no(code: str):
    """اعتبارسنجی شماره دادنامه — ۱۴۰۰ به بعد ۱۸ رقمی، ۹۹ و قبل‌تر ۱۶ رقمی."""
    if not code.isdigit():
        return False, "⚠️ شماره دادنامه باید فقط شامل اعداد باشد."
    # تعیین سال از ۴ رقم ابتدایی
    prefix = int(code[:4]) if len(code) >= 4 else 0
    if prefix >= 1400:
        expected = 18
    else:
        expected = 16
    if len(code) != expected:
        return False, (
            f"⚠️ شماره دادنامه باید *{expected} رقمی* باشد.\n"
            f"_(۱۴۰۰ به بعد: ۱۸ رقمی | ۹۹ و قبل‌تر: ۱۶ رقمی)_\n\n"
            f"کد شما *{len(code)} رقمی* است. مجدداً وارد فرمایید:"
        )
    return True, code


def _validate_file_no(code: str):
    """اعتبارسنجی شماره پرونده — ۱۴۰۰ به بعد ۱۸ رقمی، ۹۹ و قبل‌تر ۱۶ رقمی."""
    if not code.isdigit():
        return False, "⚠️ شماره پرونده باید فقط شامل اعداد باشد."
    prefix = int(code[:4]) if len(code) >= 4 else 0
    if prefix >= 1400:
        expected = 18
    else:
        expected = 16
    if len(code) != expected:
        return False, (
            f"⚠️ شماره پرونده باید *{expected} رقمی* باشد.\n"
            f"_(۱۴۰۰ به بعد: ۱۸ رقمی | ۹۹ و قبل‌تر: ۱۶ رقمی)_\n\n"
            f"کد شما *{len(code)} رقمی* است. لطفاً شماره صحیح را وارد فرمایید:"
        )
    return True, code


def _fmt(n: int) -> str:
    return f"{n:,}"

def _escape_md(text: str) -> str:
    for ch in ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']:
        text = text.replace(ch, f'\\{ch}')
    return text


EADAH_MADANI_REASONS = [
    "موضوع حكم مورد ادعاي خواهان نبوده",
    "تضاد در مفاد حكم ناشي از استناد به اصول/مواد متضاد",
    "تضاد حكم صادره با حكم ديگر در همان دعوا",
    "حيله و تقلب طرف مقابل در دادرسی",
    "اسناد جديد بعد از صدور حكم به دست آمده",
    "حكم به ميزان بيشتر از خواسته صادر شده",
    "اسناد مستند حكم جعلي ثابت شده",
]

EADAH_KIFRI_REASONS = [
    "متهم به قتل محكوم و سپس زنده بودن محرز شود",
    "محكوميت چند نفر به جرم واحد",
    "تضاد مفاد دو حكم بي‌گناهي",
    "احكام متفاوت درباره شخص به اتهام واحد",
    "جعليت اسناد يا خلاف واقع بودن شهادت",
    "واقعه جديد يا ادله جديد بر بي‌گناهي",
    "عمل ارتكابي جرم نباشد يا مجازات بيش از مقرر",
]


def _get_labels(case_type: str) -> dict:
    """بر اساس نوع دعوی، برچسب‌های فارسی مربوطه را برمی‌گرداند."""
    mapping = {
        "تجدیدنظرخواهی": {"appellant": "تجدیدنظرخواه", "appellee": "تجدیدنظرخوانده", "witness_step": "مطلع/گواه"},
        "واخواهی": {"appellant": "واخواه", "appellee": "واخوانده", "witness_step": "مطلع/گواه"},
        "فرجام خواهی": {"appellant": "فرجام‌خواه", "appellee": "فرجام‌خوانده", "witness_step": "مطلع/گواه"},
        "اعاده دادرسی مدنی": {"appellant": "مقاضي اعاده دادرسي", "appellee": "طرف اعاده دادرسي", "witness_step": "مطلع/گواه"},
        "اعاده دادرسی کیفری": {"appellant": "محكوم عليه", "appellee": "طرف اعاده دادرسي", "witness_step": "سایر اشخاص"},
        "اعتراض ثالث": {"appellant": "معترض ثالث", "appellee": "طرف اعتراض ثالث", "witness_step": "مطلع/گواه"},
        "اعتراض به قرار دادسرا": {"appellant": "درخواست دهنده", "appellee": "—", "witness_step": "مطلع/گواه", "skip_appellee": True},
    }
    return mapping.get(case_type, mapping["تجدیدنظرخواهی"])



def _is_prosecutor_objection(case_type: str) -> bool:
    """آیا دعوی از نوع اعتراض به قرار دادسرا است"""
    return case_type == "اعتراض به قرار دادسرا"
def _needs_reasons(case_type: str) -> bool:
    return case_type in ("اعاده دادرسی مدنی", "اعاده دادرسی کیفری")


def _get_reasons_list(case_type: str) -> list:
    if case_type == "اعاده دادرسی مدنی":
        return list(EADAH_MADANI_REASONS)
    if case_type == "اعاده دادرسی کیفری":
        return list(EADAH_KIFRI_REASONS)
    return []


# ══════════════════════════════════════════════════════════════════════════════
# ورود به بخش دعاوی اعتراضی
# ══════════════════════════════════════════════════════════════════════════════
@tajdid_nazar_router.message(StateFilter("*"), F.text == "⚖️ دعاوی اعتراضی")
async def tajdid_nazar_entry(message: Message, state: FSMContext):
    await state.clear()
    await state.update_data(
        tn_appellants=[],
        tn_appellees=[],
        tn_witnesses=[],
        tn_attachments=[],
        tn_images=[],
        tn_text="",
        tn_extra_text="",
        tn_reasons=[])
    await message.answer(
        "⚖️ *دعاوی اعتراضی*\n\n"
        "لطفاً نوع دعوی خود را انتخاب فرمایید:",
        reply_markup=tn_case_type_kb)
    await state.set_state(Form.tn_case_type)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۱ — انتخاب نوع دعوی
# ══════════════════════════════════════════════════════════════════════════════
@tajdid_nazar_router.message(Form.tn_case_type)
async def tn_case_type_handler(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        return
    if text == "🔙 بازگشت به منوی اصلی":
        await state.clear()
        from handlers import get_flow_type_kb
        await message.answer("❓ *لطفاً نحوه ثبت درخواست خود را انتخاب فرمایید:*",
                             reply_markup=get_flow_type_kb(message.from_user.id))
        await state.set_state(Form.waiting_for_flow_type)
        return

    valid_types = [
        "تجدیدنظرخواهی", "واخواهی", "فرجام خواهی",
        "اعاده دادرسی مدنی", "اعاده دادرسی کیفری",
        "اعتراض ثالث", "اعتراض به قرار دادسرا"
    ]
    # تطبیق انعطاف‌پذیر
    matched = None
    for vt in valid_types:
        if vt in text or text in vt:
            matched = vt
            break
    if not matched:
        await message.answer("⚠️ لطفاً یکی از گزینه‌های موجود را انتخاب فرمایید:",
                             reply_markup=tn_case_type_kb)
        return

    labels = _get_labels(matched)
    await state.update_data(case_type=matched, tn_labels=labels)
    await message.answer(
        f"✅ *{matched}* انتخاب شد.\n\n"
        f"*مرحله ۱:* لطفاً *شماره دادنامه* را ارسال فرمایید:",
        reply_markup=back_only_kb)
    await state.set_state(Form.tn_judge_no)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۲ — شماره دادنامه
# ══════════════════════════════════════════════════════════════════════════════
@tajdid_nazar_router.message(Form.tn_judge_no)
async def tn_judge_no_handler(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == "🔙 بازگشت":
        await message.answer("⚖️ لطفاً نوع دعوی خود را انتخاب فرمایید:",
                             reply_markup=tn_case_type_kb)
        await state.set_state(Form.tn_case_type)
        return

    judge_no = _to_en(message.text)
    # اعتبارسنجی ۱۶/۱۸ رقمی — مشابه لایحه
    valid, result = _validate_judge_no(judge_no)
    if not valid:
        await message.answer(result,
                             reply_markup=back_only_kb)
        return
    judge_no = result

    await state.update_data(tn_judge_no=judge_no)
    await message.answer(
        f"✅ شماره دادنامه `{judge_no}` ثبت شد.\n\n"
        f"*مرحله ۲:* لطفاً *شماره پرونده* را ارسال کنید.\n\n"
        f"_(۱۴۰۰ به بعد: ۱۸ رقمی | ۹۹ و قبل‌تر: ۱۶ رقمی)_",
        reply_markup=back_only_kb)
    await state.set_state(Form.tn_file_no)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۳ — شماره پرونده
# ══════════════════════════════════════════════════════════════════════════════
@tajdid_nazar_router.message(Form.tn_file_no)
async def tn_file_no_handler(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == "🔙 بازگشت":
        await message.answer(
            "لطفاً *شماره دادنامه* را ارسال کنید:\n\n"
            "_(۱۴۰۰ به بعد: ۱۸ رقمی | ۹۹ و قبل‌تر: ۱۶ رقمی)_",
            reply_markup=back_only_kb)
        await state.set_state(Form.tn_judge_no)
        return

    file_no = _to_en(message.text)
    if not file_no or not file_no.isdigit():
        await message.answer("⚠️ شماره پرونده باید فقط شامل اعداد باشد:\n\nلطفاً مجدداً وارد فرمایید:",
                             reply_markup=back_only_kb)
        return
    # اعتبارسنجی ۱۶/۱۸ رقمی بر اساس سال
    valid, result = _validate_file_no(file_no)
    if not valid:
        await message.answer(result, reply_markup=back_only_kb)
        return
    file_no = result

    await state.update_data(tn_file_no=file_no)
    await message.answer(
        f"✅ شماره پرونده `{file_no}` ثبت شد.\n\n"
        f"*مرحله ۳:* لطفاً *تاریخ تنظیم دادنامه* را ارسال فرمایید:\n_(مثال: 1403/09/15)_",
        reply_markup=back_only_kb)
    await state.set_state(Form.tn_judge_date)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۴ — تاریخ تنظیم دادنامه
# ══════════════════════════════════════════════════════════════════════════════
@tajdid_nazar_router.message(Form.tn_judge_date)
async def tn_judge_date_handler(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == "🔙 بازگشت":
        await message.answer(
            "لطفاً *شماره پرونده* را ارسال فرمایید:",
            reply_markup=back_only_kb)
        await state.set_state(Form.tn_file_no)
        return

    date_text = message.text.strip()
    if "/" not in date_text:
        await message.answer(
            "⚠️ لطفاً تاریخ را با فرمت صحیح وارد کنید (مثال: 1403/09/15):",
            reply_markup=back_only_kb)
        return

    await state.update_data(tn_judge_date=date_text)
    await message.answer(
        f"✅ تاریخ `{date_text}` ثبت شد.\n\n"
        f"*مرحله ۴:* لطفاً *نام استان* را انتخاب فرمایید:",
        reply_markup=create_province_kb())
    await state.set_state(Form.tn_province)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۵ — استان
# ══════════════════════════════════════════════════════════════════════════════
@tajdid_nazar_router.message(Form.tn_province)
async def tn_province_handler(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        return
    if text == "🔙 بازگشت":
        data = await state.get_data()
        date = data.get("tn_judge_date", "")
        await message.answer(
            f"تاریخ فعلی: `{date}`\n\nلطفاً تاریخ جدید را وارد کنید:",
            reply_markup=back_only_kb)
        await state.set_state(Form.tn_judge_date)
        return

    from keyboards import PROVINCES
    matched_province = None
    for p in PROVINCES:
        if text in p or p in text:
            matched_province = p
            break
    if not matched_province:
        await message.answer("⚠️ لطفاً استان را از لیست انتخاب فرمایید:",
                             reply_markup=create_province_kb())
        return

    await state.update_data(tn_province=matched_province)
    data = await state.get_data()
    case_type = data.get("case_type", "")

    if _is_prosecutor_objection(case_type):
        await message.answer(
            f"✅ استان *{matched_province}* ثبت شد.\n\n"
            f"*مرحله ۵:* لطفاً *شماره قرار* را ارسال کنید.\n\n"
            f"نکته: شماره‌های *۱۴۰۰ تا ۱۴۰۷* باید *۱۸ رقمی* و شماره‌های *۹۹ و قبل‌تر* باید *۱۶ رقمی* باشند.",
            reply_markup=back_only_kb)
        await state.set_state(Form.tn_order_no)
    else:
        labels = data.get("tn_labels", {})
        await message.answer(
            f"✅ استان *{matched_province}* ثبت شد.\n\n"
            f"*مرحله ۵:* آیا دادنامه *حکم* صادر شده است یا *قرار*؟",
            reply_markup=tn_doc_type_kb)
        await state.set_state(Form.tn_doc_type)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۶ — حکم یا قرار
# ══════════════════════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۵ — شماره قرار (فقط اعتراض به قرار دادسرا)
# ══════════════════════════════════════════════════════════════════════════════
@tajdid_nazar_router.message(Form.tn_order_no)
async def tn_order_no_handler(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == "🔙 بازگشت":
        await message.answer(
            "لطفاً *نام استان* را انتخاب فرمایید:",
            reply_markup=create_province_kb())
        await state.set_state(Form.tn_province)
        return

    order_no = _to_en(message.text)
    valid, result = _validate_judge_no(order_no)
    if not valid:
        await message.answer(result,
                             reply_markup=back_only_kb)
        return
    order_no = result

    await state.update_data(tn_judge_no=order_no, tn_doc_type="", tn_amount=0, tn_insolvency=False)

    data = await state.get_data()
    labels = data.get("tn_labels", {})
    appellant_label = labels.get("appellant", "درخواست دهنده")

    await message.answer(
        f"✅ شماره قرار `{order_no}` ثبت شد.\n\n"
        f"*مرحله ۶:* لطفاً *نوع شخصیت {appellant_label}* را انتخاب فرمایید:\n\n"
        f"⚠️ توجه: اگر *وکیل* را انتخاب می‌کنید، باید حداقل یک *شخص حقیقی یا حقوقی* نیز اضافه کنید.",
        reply_markup=create_tn_appellant_person_type_kb())
    await state.set_state(Form.tn_appellant_person_type)


@tajdid_nazar_router.message(Form.tn_doc_type)
async def tn_doc_type_handler(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if text not in ("حکم", "قرار"):
        await message.answer("⚠️ لطفاً یکی از گزینه‌ها را انتخاب فرمایید:",
                             reply_markup=tn_doc_type_kb)
        return

    await state.update_data(tn_doc_type=text)
    await message.answer(
        f"✅ *{text}* ثبت شد.\n\n"
        f"*مرحله ۶:* مبلغ محکومیت یا خواسته را اعلام کنید:",
        reply_markup=tn_amount_type_kb)
    await state.set_state(Form.tn_amount_type)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۷ — مبلغ
# ══════════════════════════════════════════════════════════════════════════════
@tajdid_nazar_router.message(Form.tn_amount_type)
async def tn_amount_type_handler(message: Message, state: FSMContext):
    text = (message.text or "").strip()

    if "نمی‌دانم" in text or "نمیدانم" in text:
        await state.update_data(tn_amount=0)
        await _ask_insolvency(message, state)
        return
    if "غیر مالی" in text:
        await state.update_data(tn_amount=0)
        await _ask_insolvency(message, state)
        return
    if "می‌دانم" in text or "میدانم" in text:
        await message.answer(
            "💰 لطفاً *مبلغ دقیق را به ریال* وارد کنید:",
            reply_markup=tn_amount_confirm_kb)
        await state.set_state(Form.tn_amount)
        return

    await message.answer("⚠️ لطفاً یکی از گزینه‌های موجود را انتخاب فرمایید:",
                         reply_markup=tn_amount_type_kb)


@tajdid_nazar_router.message(Form.tn_amount)
async def tn_amount_handler(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if text == "✅ تایید":
        # shouldn't happen without entering amount
        await message.answer("⚠️ لطفاً ابتدا مبلغ را وارد کنید.")
        return

    amount_str = _to_en(text)
    if not amount_str.isdigit() or int(amount_str) <= 0:
        await message.answer(
            "⚠️ مبلغ باید یک عدد مثبت باشد (به ریال):\n\nلطفاً مجدداً وارد فرمایید:",
            reply_markup=tn_amount_confirm_kb)
        return

    await state.update_data(tn_amount=int(amount_str))
    await _ask_insolvency(message, state)


async def _ask_insolvency(message: Message, state: FSMContext):
    await message.answer(
        "*مرحله ۷:* آیا *درخواست اعسار* از هزینه دادرسی را دارید؟",
        reply_markup=tn_insolvency_kb)
    await state.set_state(Form.tn_insolvency)


@tajdid_nazar_router.message(Form.tn_insolvency)
async def tn_insolvency_handler(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    _is_yes = text.startswith("➕ بله") or text == "بله" or "شخص دیگری" in text
    _is_no = text.startswith("✅ خیر") or text == "خیر" or "ادامه مراحل" in text
    if not _is_yes and not _is_no:
        await message.answer("⚠️ لطفاً «بله» یا «خیر» را انتخاب فرمایید:",
                             reply_markup=tn_insolvency_kb)
        return

    await state.update_data(tn_insolvency=_is_yes)
    data = await state.get_data()
    labels = data.get("tn_labels", {})
    appellant_label = labels.get("appellant", "تجدیدنظرخواه")

    await message.answer(
        f"✅ ثبت شد.\n\n"
        f"*مرحله ۸:* لطفاً *نوع شخصیت {appellant_label}* را انتخاب فرمایید:\n\n"
        f"⚠️ توجه: اگر *وکیل* را انتخاب می‌کنید، باید حداقل یک *شخص حقیقی یا حقوقی* نیز اضافه کنید.",
        reply_markup=create_tn_appellant_person_type_kb())
    await state.set_state(Form.tn_appellant_person_type)

# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۸ — اشخاص تجدیدنظرخواه (شبیه اظهارکننده اظهارنامه)
# ══════════════════════════════════════════════════════════════════════════════
@tajdid_nazar_router.message(Form.tn_appellant_person_type)
async def tn_appellant_person_type_handler(message: Message, state: FSMContext):
    text = message.text or ""
    data = await state.get_data()
    appellants = data.get("tn_appellants", [])
    used_types = [p.get("person_type") for p in appellants]
    labels = data.get("tn_labels", {})
    appellant_label = labels.get("appellant", "تجدیدنظرخواه")

    if text == "✅ اتمام و ادامه":
        if not appellants and not data.get("tn_appellant_query_mode"):
            await message.answer(
                f"⚠️ حداقل یک {appellant_label} باید اضافه شود.",
                reply_markup=create_tn_appellant_person_type_kb())
            return

        # بررسی: اگر وکیل داشتیم، باید حقیقی یا حقوقی هم داشته باشیم
        has_lawyer = any(p.get("person_type") == "وکیل" for p in appellants)
        has_real_or_legal = any(
            p.get("person_type") in ("شخص حقیقی", "شخص حقوقی") for p in appellants
        )
        if has_lawyer and not has_real_or_legal and not data.get("tn_appellant_query_mode"):
            await message.answer(
                f"⚠️ *توجه مهم:*\n\n"
                f"چون *وکیل* اضافه کرده‌اید، باید حداقل یک *شخص حقیقی یا حقوقی* نیز وجود داشته باشد.\n\n"
                f"لطفاً نوع شخص دیگری انتخاب کنید:",
                reply_markup=create_tn_appellant_person_type_kb(exclude=used_types))
            return

        # بررسی حالت ویرایش
        if data.get("_tn_editing", False):
            await state.update_data(_tn_editing=False)
            await _go_to_tn_preview(message, state)
            return

        # بررسی آیا باید تجدیدنظرخوانده بپرسیم
        case_type = data.get("case_type", "")
        if _is_prosecutor_objection(case_type):
            witness_label = labels.get("witness_step", "مطلع/گواه")
            await message.answer(
                f"*مرحله ۹:* در صورتی که *{witness_label}* دارید، کدملی شخص حقیقی را وارد فرمایید.\n\n"
                f"⚠️ توجه: فقط *کدملی شخص حقیقی* قابل قبول است و شخص باید *ثبت‌نام ثنا* داشته باشد.\n\n"
                f"در صورتی که {witness_label} ندارید، گزینه «خیر» را انتخاب فرمایید:",
                reply_markup=tn_more_witnesses_kb)
            await state.set_state(Form.tn_more_witnesses)
        else:
            # بررسی حالت ویرایش
            if data.get("_tn_editing", False):
                await state.update_data(_tn_editing=False)
                await _go_to_tn_preview(message, state)
                return

            case_type = data.get("case_type", "")
            if _is_prosecutor_objection(case_type):
                witness_label = labels.get("witness_step", "مطلع/گواه")
                await message.answer(
                    f"*مرحله ۹:* در صورتی که *{witness_label}* دارید، کدملی شخص حقیقی را وارد فرمایید.\n\n"
                    f"در صورتی که {witness_label} ندارید، گزینه «خیر» را انتخاب فرمایید:",
                    reply_markup=tn_more_witnesses_kb)
                await state.set_state(Form.tn_more_witnesses)
            else:
                appellee_label = labels.get("appellee", "تجدیدنظرخوانده")
                await message.answer(
                f"*مرحله ۹:* لطفاً *نوع شخصیت {appellee_label}* را انتخاب فرمایید:\n\n"
                f"💡 در صورتی که کدملی افراد پرونده را ندارید، گزینه استعلام افراد موجود در پرونده را انتخاب کنید",
                reply_markup=create_tn_appellee_person_type_kb())
            await state.set_state(Form.tn_appellee_person_type)
        return

    if text == "🔙 بازگشت":
        await message.answer(
            "آیا *درخواست اعسار* از هزینه دادرسی را دارید؟",
            reply_markup=tn_insolvency_kb)
        await state.set_state(Form.tn_insolvency)
        return

    # ── گزینه استعلام افراد موجود در پرونده ──────────────────
    if text == "🔍 استعلام افراد موجود در پرونده":
        await _handle_query_persons(message, state, bot, "appellant")
        return

    if text not in ["شخص حقیقی", "شخص حقوقی", "وکیل"]:
        await message.answer(
            "⚠️ لطفاً یکی از گزینه‌های موجود را انتخاب کنید:",
            reply_markup=create_tn_appellant_person_type_kb(
                exclude=used_types if appellants else []
            ))
        return

    await state.update_data(_tn_current_appellant={"person_type": text})

    if text == "شخص حقوقی":
        await message.answer(
            f"🏢 لطفاً *شناسه ملی شرکت* {appellant_label} را وارد فرمایید:\n_(۱۱ رقمی)_",
            reply_markup=back_only_kb)
        await state.set_state(Form.tn_appellant_company_id)
    else:
        type_label = "وکیل" if text == "وکیل" else "شخص"
        await message.answer(
            f"🔢 لطفاً *کد ملی {type_label}* {appellant_label} را وارد کنید:\n_(۱۰ رقمی)_",
            reply_markup=back_only_kb)
        await state.set_state(Form.tn_appellant_national_id)


@tajdid_nazar_router.message(Form.tn_appellant_company_id)
async def tn_appellant_company_id_handler(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == "🔙 بازگشت":
        data = await state.get_data()
        appellants = data.get("tn_appellants", [])
        used_types = [p.get("person_type") for p in appellants]
        await message.answer(
            f"👤 لطفاً نوع شخص را انتخاب کنید:",
            reply_markup=create_tn_appellant_person_type_kb(
                exclude=used_types if appellants else []
            ))
        await state.set_state(Form.tn_appellant_person_type)
        return

    company_id = _to_en(message.text)
    if not company_id.isdigit() or len(company_id) != 11:
        await message.answer(
            "⚠️ شناسه ملی شرکت باید *۱۱ رقمی* باشد:\n\nلطفاً مجدداً وارد فرمایید:",
            reply_markup=back_only_kb)
        return

    data = await state.get_data()
    current = data.get("_tn_current_appellant", {})
    current["company_id"] = company_id
    await state.update_data(_tn_current_appellant=current)

    await message.answer(
        "👔 نماینده شرکت چه سمتی دارد؟",
        reply_markup=representative_type_kb)
    await state.set_state(Form.tn_appellant_representative_type)


@tajdid_nazar_router.message(Form.tn_appellant_representative_type)
async def tn_appellant_representative_type_handler(message: Message, state: FSMContext):
    text = message.text or ""
    if text not in ["مدیرعامل", "نماینده"]:
        await message.answer(
            "⚠️ لطفاً یکی از گزینه‌ها را انتخاب کنید:",
            reply_markup=representative_type_kb)
        return

    data = await state.get_data()
    current = data.get("_tn_current_appellant", {})
    current["representative_type"] = text
    await state.update_data(_tn_current_appellant=current)

    await message.answer(
        f"🔢 لطفاً *کد ملی {text}* شرکت را وارد کنید:\n_(۱۰ رقمی)_",
        reply_markup=back_only_kb)
    await state.set_state(Form.tn_appellant_national_id)


@tajdid_nazar_router.message(Form.tn_appellant_national_id)
async def tn_appellant_national_id_handler(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == "🔙 بازگشت":
        data = await state.get_data()
        appellants = data.get("tn_appellants", [])
        used_types = [p.get("person_type") for p in appellants]
        labels = data.get("tn_labels", {})
        appellant_label = labels.get("appellant", "تجدیدنظرخواه")
        await message.answer(
            f"👤 لطفاً *نوع شخصیت {appellant_label}* را انتخاب فرمایید:",
            reply_markup=create_tn_appellant_person_type_kb(
                exclude=used_types if appellants else []
            ))
        await state.set_state(Form.tn_appellant_person_type)
        return

    nat_id = _to_en(message.text)
    if not re.match(r"^[0-9]{10}$", nat_id):
        await message.answer(
            "⚠️ کد ملی باید *۱۰ رقمی* باشد:\n\nلطفاً مجدداً وارد فرمایید:",
            reply_markup=back_only_kb)
        return

    data = await state.get_data()
    # بررسی تکراری نبودن کدملی
    appellants = data.get("tn_appellants", [])
    appellees = data.get("tn_appellees", [])
    all_ids = [p.get("national_id") for p in appellants + appellees if p.get("national_id")]
    if nat_id in all_ids:
        await message.answer(
            f"⚠️ کد ملی `{nat_id}` قبلاً ثبت شده است.\n"
            f"هر شخص باید کد ملی متفاوت داشته باشد.\n\n"
            f"لطفاً کد ملی دیگری وارد فرمایید:",
            reply_markup=back_only_kb)
        return

    current = data.get("_tn_current_appellant", {})
    current["national_id"] = nat_id
    appellants.append(current)
    await state.update_data(tn_appellants=appellants, _tn_current_appellant={})

    person_type = current.get("person_type", "")
    labels = data.get("tn_labels", {})
    appellant_label = labels.get("appellant", "تجدیدنظرخواه")

    await message.answer(
        f"✅ *{person_type}* با کدملی `{nat_id}` ثبت شد.\n\n"
        f"آیا {appellant_label} دیگری نیز وجود دارد؟",
        reply_markup=create_tn_appellant_person_type_kb())
    await state.set_state(Form.tn_appellant_more)


@tajdid_nazar_router.message(Form.tn_appellant_more)
async def tn_appellant_more_handler(message: Message, state: FSMContext):
    """پاسخ به سوال آیا {appellant_label} دیگری دارد — تغییر مسیر به مرحله合适的."""
    text = message.text or ""
    data = await state.get_data()
    labels = data.get("tn_labels", {})
    appellant_label = labels.get("appellant", "تجدیدنظرخواه")
    appellants = data.get("tn_appellants", [])
    used_types = [p.get("person_type") for p in appellants]

    if text == "✅ اتمام و ادامه":
        if not appellants and not data.get("tn_appellant_query_mode"):
            await message.answer(
                f"⚠️ حداقل یک {appellant_label} باید اضافه شود.",
                reply_markup=create_tn_appellant_person_type_kb())
            return

        has_lawyer = any(p.get("person_type") == "وکیل" for p in appellants)
        has_real_or_legal = any(
            p.get("person_type") in ("شخص حقیقی", "شخص حقوقی") for p in appellants
        )
        if has_lawyer and not has_real_or_legal and not data.get("tn_appellant_query_mode"):
            await message.answer(
                "⚠️ *توجه مهم:*\n\n"
                "چون *وکیل* اضافه کرده‌اید، باید حداقل یک *شخص حقیقی یا حقوقی* نیز وجود داشته باشد.\n\n"
                "لطفاً نوع شخص دیگری انتخاب کنید:",
                reply_markup=create_tn_appellant_person_type_kb(exclude=used_types))
            return

        # بررسی حالت ویرایش
        if data.get("_tn_editing", False):
            await state.update_data(_tn_editing=False)
            await _go_to_tn_preview(message, state)
            return

        case_type = data.get("case_type", "")
        if _is_prosecutor_objection(case_type):
            witness_label = labels.get("witness_step", "مطلع/گواه")
            await message.answer(
                f"*مرحله ۹:* در صورتی که *{witness_label}* دارید، کدملی شخص حقیقی را وارد فرمایید.\n\n"
                f"در صورتی که {witness_label} ندارید، گزینه «خیر» را انتخاب فرمایید:",
                reply_markup=tn_more_witnesses_kb)
            await state.set_state(Form.tn_more_witnesses)
        else:
            appellee_label = labels.get("appellee", "تجدیدنظرخوانده")
            await message.answer(
                f"*مرحله ۹:* لطفاً *نوع شخصیت {appellee_label}* را انتخاب فرمایید:\n\n"
                f"💡 در صورتی که کدملی افراد پرونده را ندارید، گزینه استعلام افراد موجود در پرونده را انتخاب کنید",
                reply_markup=create_tn_appellee_person_type_kb())
            await state.set_state(Form.tn_appellee_person_type)
        return

    if text == "🔙 بازگشت":
        await message.answer(
            f"👤 لطفاً *نوع شخصیت {appellant_label}* را انتخاب فرمایید:",
            reply_markup=create_tn_appellant_person_type_kb(
                exclude=used_types if appellants else []
            ))
        await state.set_state(Form.tn_appellant_person_type)
        return

    # ── گزینه استعلام افراد موجود در پرونده ──────────────────
    if text == "🔍 استعلام افراد موجود در پرونده":
        await _handle_query_persons(message, state, bot, "appellant")
        return

    if text not in ["شخص حقیقی", "شخص حقوقی", "وکیل"]:
        await message.answer(
            "⚠️ لطفاً یکی از گزینه‌های موجود را انتخاب کنید:",
            reply_markup=create_tn_appellant_person_type_kb(
                exclude=used_types if appellants else []
            ))
        return

    await state.update_data(_tn_current_appellant={"person_type": text})

    if text == "شخص حقوقی":
        await message.answer(
            f"🏢 لطفاً *شناسه ملی شرکت* {appellant_label} را وارد فرمایید:\n_(۱۱ رقمی)_",
            reply_markup=back_only_kb)
        await state.set_state(Form.tn_appellant_company_id)
    else:
        type_label = "وکیل" if text == "وکیل" else "شخص"
        await message.answer(
            f"🔢 لطفاً *کد ملی {type_label}* {appellant_label} را وارد کنید:\n_(۱۰ رقمی)_",
            reply_markup=back_only_kb)
        await state.set_state(Form.tn_appellant_national_id)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۹ — اشخاص تجدیدنظرخوانده (شبیه مخاطب اظهارنامه)
# ══════════════════════════════════════════════════════════════════════════════
@tajdid_nazar_router.message(Form.tn_appellee_person_type)
async def tn_appellee_person_type_handler(message: Message, state: FSMContext):
    text = message.text or ""
    data = await state.get_data()
    appellees = data.get("tn_appellees", [])
    used_types = [p.get("person_type") for p in appellees]
    labels = data.get("tn_labels", {})
    appellee_label = labels.get("appellee", "تجدیدنظرخوانده")

    if text == "✅ اتمام و ادامه":
        if not appellees and not data.get("tn_appellee_query_mode"):
            await message.answer(
                f"⚠️ حداقل یک {appellee_label} باید اضافه شود.",
                reply_markup=create_tn_appellee_person_type_kb())
            return

        # بررسی حالت ویرایش
        if data.get("_tn_editing", False):
            await state.update_data(_tn_editing=False)
            await _go_to_tn_preview(message, state)
            return

        # رفتن به مرحله شهود/مطلع
        witness_label = labels.get("witness_step", "مطلع/گواه")
        await message.answer(
            f"*مرحله ۱۰:* در صورتی که *{witness_label}* دارید، کدملی شخص حقیقی را وارد فرمایید.\n\n"
            f"⚠️ توجه: فقط *کدملی شخص حقیقی* قابل قبول است و شخص باید *ثبت‌نام ثنا* داشته باشد.\n\n"
            f"در صورتی که {witness_label} ندارید، گزینه «خیر» را انتخاب فرمایید:",
            reply_markup=tn_more_witnesses_kb)
        await state.set_state(Form.tn_more_witnesses)
        return

    if text == "🔙 بازگشت":
        # بازگشت به مرحله تجدیدنظرخواه
        appellants = data.get("tn_appellants", [])
        used_appellant_types = [p.get("person_type") for p in appellants]
        appellant_label = labels.get("appellant", "تجدیدنظرخواه")
        await message.answer(
            f"👤 لطفاً *نوع شخصیت {appellant_label}* را انتخاب فرمایید:\n\n"
            f"آیا {appellant_label} دیگری نیز وجود دارد؟",
            reply_markup=create_tn_appellant_person_type_kb(
                exclude=used_appellant_types if appellants else []
            ))
        await state.set_state(Form.tn_appellant_more)
        return

    # ── گزینه استعلام افراد موجود در پرونده ──────────────────
    if text == "🔍 استعلام افراد موجود در پرونده":
        await _handle_query_persons(message, state, bot, "appellee")
        return

    if text not in ["شخص حقیقی", "شخص حقوقی"]:
        await message.answer(
            "⚠️ لطفاً یکی از گزینه‌های موجود را انتخاب کنید:",
            reply_markup=create_tn_appellee_person_type_kb(
                exclude=used_types if appellees else []
            ))
        return

    await state.update_data(_tn_current_appellee={"person_type": text})

    if text == "شخص حقوقی":
        await message.answer(
            f"🏢 لطفاً *شناسه ملی شرکت* {appellee_label} را وارد فرمایید:\n_(۱۱ رقمی)_",
            reply_markup=back_only_kb)
        await state.set_state(Form.tn_appellee_company_id)
    else:
        await message.answer(
            f"🔢 لطفاً *کد ملی {appellee_label}* را وارد کنید:\n_(۱۰ رقمی)_",
            reply_markup=back_only_kb)
        await state.set_state(Form.tn_appellee_national_id)


@tajdid_nazar_router.message(Form.tn_appellee_company_id)
async def tn_appellee_company_id_handler(message: Message, state: FSMContext):
    """دریافت شناسه ملی شرکت تجدیدنظرخوانده حقوقی — بدون سمت و کدملی نماینده."""
    if not message.text:
        return
    if message.text == "🔙 بازگشت":
        data = await state.get_data()
        appellees = data.get("tn_appellees", [])
        used_types = [p.get("person_type") for p in appellees]
        await message.answer(
            "👥 لطفاً نوع شخص را انتخاب کنید:",
            reply_markup=create_tn_appellee_person_type_kb(
                exclude=used_types if appellees else []
            ))
        await state.set_state(Form.tn_appellee_person_type)
        return

    company_id = _to_en(message.text)
    if not company_id.isdigit() or len(company_id) != 11:
        await message.answer(
            "⚠️ شناسه ملی شرکت باید *۱۱ رقمی* باشد:\n\nلطفاً مجدداً وارد فرمایید:",
            reply_markup=back_only_kb)
        return

    data = await state.get_data()
    current = data.get("_tn_current_appellee", {})
    current["company_id"] = company_id
    current["representative_type"] = ""
    current["national_id"] = ""
    appellees = data.get("tn_appellees", [])
    appellees.append(current)
    await state.update_data(tn_appellees=appellees, _tn_current_appellee={})

    labels = data.get("tn_labels", {})
    appellee_label = labels.get("appellee", "تجدیدنظرخوانده")
    await message.answer(
        f"✅ *مخاطب ({appellee_label} — شخص حقوقی)* با شناسه ملی `{company_id}` ثبت شد.\n\n"
        f"آیا {appellee_label} دیگری نیز وجود دارد؟",
        reply_markup=create_tn_appellee_person_type_kb(show_finish=True))
    await state.set_state(Form.tn_appellee_person_type)


@tajdid_nazar_router.message(Form.tn_appellee_national_id)
async def tn_appellee_national_id_handler(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == "🔙 بازگشت":
        data = await state.get_data()
        appellees = data.get("tn_appellees", [])
        used_types = [p.get("person_type") for p in appellees]
        await message.answer(
            "👥 لطفاً نوع شخص را انتخاب کنید:",
            reply_markup=create_tn_appellee_person_type_kb(
                exclude=used_types if appellees else []
            ))
        await state.set_state(Form.tn_appellee_person_type)
        return

    nat_id = _to_en(message.text)
    if not re.match(r"^[0-9]{10}$", nat_id):
        await message.answer(
            "⚠️ کد ملی باید *۱۰ رقمی* باشد:\n\nلطفاً مجدداً وارد فرمایید:",
            reply_markup=back_only_kb)
        return

    data = await state.get_data()
    # بررسی تکراری نبودن کدملی
    appellants = data.get("tn_appellants", [])
    appellees = data.get("tn_appellees", [])
    all_ids = [p.get("national_id") for p in appellants + appellees if p.get("national_id")]
    if nat_id in all_ids:
        await message.answer(
            f"⚠️ کد ملی `{nat_id}` قبلاً ثبت شده است.\n"
            f"هر شخص باید کد ملی متفاوت داشته باشد.\n\n"
            f"لطفاً کد ملی دیگری وارد فرمایید:",
            reply_markup=back_only_kb)
        return

    current = data.get("_tn_current_appellee", {})
    current["national_id"] = nat_id
    appellees.append(current)
    await state.update_data(tn_appellees=appellees, _tn_current_appellee={})

    labels = data.get("tn_labels", {})
    appellee_label = labels.get("appellee", "تجدیدنظرخوانده")
    await message.answer(
        f"✅ *{appellee_label} (شخص حقیقی)* با کدملی `{nat_id}` ثبت شد.\n\n"
        f"آیا {appellee_label} دیگری نیز وجود دارد؟",
        reply_markup=create_tn_appellee_person_type_kb(show_finish=True))
    await state.set_state(Form.tn_appellee_person_type)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۱۰ — شهود/مطلع (فقط حقیقی)
# ══════════════════════════════════════════════════════════════════════════════
@tajdid_nazar_router.message(Form.tn_more_witnesses)
async def tn_more_witnesses_handler(message: Message, state: FSMContext):
    text = message.text or ""
    data = await state.get_data()
    labels = data.get("tn_labels", {})
    witness_label = labels.get("witness_step", "مطلع/گواه")

    if text.startswith("✅ خیر") or text == "خیر" or "ادامه مراحل" in text:
        # رفتن به مرحله شرح متن — ابتدا انتخاب روش ورود
        await message.answer(
            "*مرحله ۱۱:* لطفاً روش ورود *شرح متن* را انتخاب فرمایید:\n\n"
            "⚠️ *توجه:* متن پس از ارسال قابل ویرایش نمی‌باشد.",
            reply_markup=text_input_method_kb)
        await state.set_state(Form.tn_text_choice)
        return

    if text == "🔙 بازگشت":
        # بازگشت به مرحله تجدیدنظرخوانده
        appellees = data.get("tn_appellees", [])
        used_types = [p.get("person_type") for p in appellees]
        appellee_label = labels.get("appellee", "تجدیدنظرخوانده")
        await message.answer(
            f"👥 لطفاً *نوع شخصیت {appellee_label}* را انتخاب فرمایید:",
            reply_markup=create_tn_appellee_person_type_kb(
                exclude=used_types if appellees else [], show_finish=bool(appellees)
            ))
        await state.set_state(Form.tn_appellee_person_type)
        return

    if text.startswith("➕ بله") or text == "بله" or "شخص دیگری" in text:
        await message.answer(
            f"🔢 لطفاً *کدملی {witness_label}* (شخص حقیقی) را وارد فرمایید:\n_(۱۰ رقمی)_\n\n"
            f"⚠️ شخص باید *ثبت‌نام ثنا* داشته باشد.",
            reply_markup=back_only_kb)
        await state.set_state(Form.tn_witness_national_id)
        return

    await message.answer(
        "⚠️ لطفاً یکی از گزینه‌های موجود را انتخاب فرمایید:",
        reply_markup=tn_more_witnesses_kb)


@tajdid_nazar_router.message(Form.tn_witness_national_id)
async def tn_witness_national_id_handler(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == "🔙 بازگشت":
        data = await state.get_data()
        labels = data.get("tn_labels", {})
        witness_label = labels.get("witness_step", "مطلع/گواه")
        await message.answer(
            f"در صورتی که *{witness_label}* دیگری دارید، کدملی را وارد فرمایید.\n\n"
            f"در غیر اینصورت «خیر» را انتخاب فرمایید:",
            reply_markup=tn_more_witnesses_kb)
        await state.set_state(Form.tn_more_witnesses)
        return

    nat_id = _to_en(message.text)
    if not re.match(r"^[0-9]{10}$", nat_id):
        await message.answer(
            "⚠️ کد ملی باید *۱۰ رقمی* باشد:\n\nلطفاً مجدداً وارد فرمایید:",
            reply_markup=back_only_kb)
        return

    data = await state.get_data()
    witnesses = data.get("tn_witnesses", [])
    all_ids = [w.get("national_id") for w in witnesses]
    # همچنین چک در appellants و appellees
    appellants = data.get("tn_appellants", [])
    appellees = data.get("tn_appellees", [])
    all_ids += [p.get("national_id") for p in appellants + appellees if p.get("national_id")]
    if nat_id in all_ids:
        await message.answer(
            f"⚠️ کد ملی `{nat_id}` قبلاً ثبت شده است.\n\n"
            f"لطفاً کد ملی دیگری وارد فرمایید:",
            reply_markup=back_only_kb)
        return

    witnesses.append({"person_type": "شخص حقیقی", "national_id": nat_id})
    await state.update_data(tn_witnesses=witnesses)

    labels = data.get("tn_labels", {})
    witness_label = labels.get("witness_step", "مطلع/گواه")
    await message.answer(
        f"✅ {witness_label} با کدملی `{nat_id}` ثبت شد.\n\n"
        f"آیا {witness_label} دیگری نیز وجود دارد؟",
        reply_markup=tn_more_witnesses_kb)
    await state.set_state(Form.tn_more_witnesses)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۱۱ — انتخاب روش ورود متن (تایپ مستقیم / فایل ورد)
# ══════════════════════════════════════════════════════════════════════════════
@tajdid_nazar_router.message(Form.tn_text_choice)
async def tn_text_choice_handler(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if text == "⌨️ تایپ مستقیم متن":
        await message.answer(
            "📝 لطفاً *شرح متن* دادخواست را ارسال فرمایید:",
            reply_markup=back_only_kb)
        await state.set_state(Form.tn_text)
    elif text == "📎 ارسال فایل ورد (.docx)":
        await message.answer(
            "📎 لطفاً *فایل ورد (.docx)* را ارسال فرمایید:",
            reply_markup=back_only_kb)
        await state.set_state(Form.tn_text)
    elif text == "🔙 بازگشت":
        data = await state.get_data()
        labels = data.get("tn_labels", {})
        prosecutor = data.get("case_type", "") == "اعتراض به قرار دادسرا"
        if prosecutor:
            await message.answer(
                "🔍 آیا *مطلع یا گواه* دیگری دارید؟",
                reply_markup=tn_more_witnesses_kb)
            await state.set_state(Form.tn_more_witnesses)
        else:
            appellees = data.get("tn_appellees", [])
            used_types = [p.get("person_type") for p in appellees]
            appellee_label = labels.get("appellee", "تجدیدنظرخوانده")
            await message.answer(
                f"👥 لطفاً *نوع شخصیت {appellee_label}* را انتخاب فرمایید:",
                reply_markup=create_tn_appellee_person_type_kb(exclude=used_types))
            await state.set_state(Form.tn_appellee_person_type)
    else:
        await message.answer(
            "⚠️ لطفاً یکی از گزینه‌های موجود را انتخاب فرمایید:",
            reply_markup=text_input_method_kb)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۱۱ — شرح متن (با text_collector)
# ══════════════════════════════════════════════════════════════════════════════
@tajdid_nazar_router.message(Form.tn_text)
async def tn_text_handler(message: Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    chat_id = message.chat.id

    # ── پشتیبانی فایل ورد ──────────────────────────────────────
    if message.document and message.document.file_name and message.document.file_name.lower().endswith(".docx"):
        from text_collector import process_docx_input

        async def _on_tn_docx_complete(final_text, final_html, st, b, cid, was_editing, char_count):
            await st.update_data(tn_text=final_text, tn_text_html=final_html, tn_attachments=[], tn_images=[])

            data = await st.get_data()
            appellants = data.get("tn_appellants", [])
            appellees = data.get("tn_appellees", [])
            has_legal = any(p.get("person_type") == "شخص حقوقی" for p in appellants + appellees)

            if has_legal:
                await b.send_message(
                    cid,
                    "*مرحله ۱۲ — مدارک:*\n\n"
                    "⚠️ *توجه مهم:* چون شخص *حقوقی* دارید، ارسال تصویر *مدرک نمایندگی اجباری* است.\n\n"
                    "📸 لطفاً تصویر *مدرک نمایندگی* را ارسال فرمایید.\n"
                    "_(مثلاً: روزنامه رسمی، آگهی تأسیس، وکالت‌نامه رسمی)_")
                await st.update_data(
                    _tn_mandatory_proxy_sent=False,
                    tn_images=[],
                    _tn_current_attachment_title="مدرک نمایندگی")
                await st.set_state(Form.tn_attachment_images)
            else:
                await _ask_tn_attachment(message, st, is_first=True)

        await process_docx_input(
            message=message,
            user_id=user_id,
            chat_id=chat_id,
            state=state,
            bot=bot,
            on_complete=_on_tn_docx_complete,
            text_state_key="tn_text",
            html_state_key="tn_text_html",
            extra_state_updates={"tn_attachments": [], "tn_images": []},
            processing_msg="⏳ در حال پردازش فایل ورد...")
        return

    if not message.text:
        await message.answer("⚠️ لطفاً شرح متن را به صورت متن ارسال فرمایید.\nیا فایل .docx ارسال نمایید.")
        return

    from text_collector import collect_text_part

    async def _on_tn_text_complete(final_text, st, b, cid, was_editing):
        await st.update_data(tn_text=final_text, tn_text_html="", tn_attachments=[], tn_images=[])

        data = await st.get_data()
        appellants = data.get("tn_appellants", [])
        appellees = data.get("tn_appellees", [])
        has_legal = any(p.get("person_type") == "شخص حقوقی" for p in appellants + appellees)

        if has_legal:
            await b.send_message(
                cid,
                "*مرحله ۱۲ — مدارک:*\n\n"
                "⚠️ *توجه مهم:* چون شخص *حقوقی* دارید، ارسال تصویر *مدرک نمایندگی اجباری* است.\n\n"
                "📸 لطفاً تصویر *مدرک نمایندگی* را ارسال فرمایید.\n"
                "_(مثلاً: روزنامه رسمی، آگهی تأسیس، وکالت‌نامه رسمی)_")
            await st.update_data(
                _tn_mandatory_proxy_sent=False,
                tn_images=[],
                _tn_current_attachment_title="مدرک نمایندگی")
            await st.set_state(Form.tn_attachment_images)
        else:
            await _ask_tn_attachment(message, st, is_first=True)

    await collect_text_part(
        user_id=user_id,
        chat_id=chat_id,
        text=message.text,
        state=state,
        bot=bot,
        on_complete=_on_tn_text_complete,
        first_part_reply="⏳ در حال دریافت متن...")


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۱۲ — مدارک (پیوست‌ها) — شبیه اظهارنامه
# ══════════════════════════════════════════════════════════════════════════════
async def _ask_tn_attachment(message: Message, state: FSMContext, is_first: bool):
    await state.update_data(tn_images=[])
    intro = "✅ متن ثبت شد.\n\n" if is_first else ""
    await message.answer(
        f"{intro}📄 *عنوان مدرک:*\n\n"
        "در صورتی که تصویری برای ضمیمه دارید، عنوان آن را تایپ کنید\n"
        "یا یکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=ezhhar_attachment_title_kb_first if is_first else ezhhar_attachment_title_kb)
    await state.set_state(Form.tn_attachment_title)


@tajdid_nazar_router.message(Form.tn_attachment_title)
async def tn_attachment_title_handler(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        await message.answer("⚠️ لطفاً عنوان را وارد کنید.")
        return

    data = await state.get_data()
    attachments = data.get("tn_attachments", [])
    mandatory_sent = data.get("_tn_mandatory_proxy_sent", True)

    if text == "⏭ رد کردن (بدون مدرک)":
        if not mandatory_sent and not attachments:
            await message.answer(
                "⚠️ ارسال تصویر *مدرک نمایندگی* برای شخص حقوقی اجباری است.\n\n"
                "لطفاً تصویر مدرک را ارسال فرمایید.")
            return
        await state.update_data(tn_attachments=[])
        await _ask_tn_extra_text(message, state)
        return

    if text == "🔙 بازگشت":
        await message.answer(
            "*مرحله ۱۱:* لطفاً روش ورود *شرح متن* را انتخاب فرمایید:\n\n"
            "⚠️ *توجه:* متن پس از ارسال قابل ویرایش نمی‌باشد.",
            reply_markup=text_input_method_kb)
        await state.set_state(Form.tn_text_choice)
        return

    if text == "🔹 عنوان مهم نیست (صرفا درج شود مستندات)":
        title = "مستندات"
    else:
        title = text

    await state.update_data(_tn_current_att_title=title)
    await message.answer(
        f"✅ عنوان «*{title}*» ثبت شد.\n\n"
        "🖼 لطفاً تصاویر مربوط به این مدرک را ارسال فرمایید.\n"
        "⚠️ فقط فرمت *JPG / JPEG* قابل قبول است.\n\n"
        "پس از ارسال همه تصاویر، دکمه *«اتمام ارسال تصاویر»* را بفشارید.",
        reply_markup=lavayeh_attachment_more_kb)
    await state.set_state(Form.tn_images)


@tajdid_nazar_router.message(Form.tn_images, F.photo)
async def tn_receive_image(message: Message, state: FSMContext, bot: Bot):
    from text_collector import check_image_limit, MAX_IMAGES_PER_TITLE

    data = await state.get_data()
    images = data.get("tn_images", [])

    if not check_image_limit(len(images)):
        await message.reply(
            f"⛔ حداکثر *{MAX_IMAGES_PER_TITLE} تصویر* در هر عنوان مجاز است.\n\n"
            f"اگر مدرک بیشتری دارید، ابتدا دکمه «اتمام ارسال تصاویر» را بزنید\n"
            f"و سپس عنوان جدیدی انتخاب کنید.")
        return

    file_id = message.photo[-1].file_id
    images.append(file_id)
    await state.update_data(tn_images=images)

    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    manage_kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ اتمام ارسال تصاویر")],
            [KeyboardButton(text="➕ افزودن مدرک دیگر")],
            [KeyboardButton(text="🗑 حذف تصویر")],
        ],
        resize_keyboard=True)
    await message.reply(
        f"✅ تصویر شماره *{len(images)}* دریافت شد.\\n"
        f"مجموع تصاویر: *{len(images)} تصویر*\\n\\n"
        "می‌توانید تصاویر بیشتری ارسال کنید یا یکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=manage_kb)


@tajdid_nazar_router.message(Form.tn_images, F.text == "✅ اتمام ارسال تصاویر")
async def tn_finish_images(message: Message, state: FSMContext):
    data = await state.get_data()
    images = data.get("tn_images", [])

    if not images:
        await message.answer("⚠️ حداقل یک تصویر باید ارسال کنید.")
        return

    title = data.get("_tn_current_att_title", "مستندات")
    attachments = data.get("tn_attachments", [])
    mandatory_sent = data.get("_tn_mandatory_proxy_sent", True)

    attachments.append({"title": title, "images": list(images)})

    if title == "مدرک نمایندگی":
        mandatory_sent = True

    await state.update_data(
        tn_attachments=attachments,
        _tn_mandatory_proxy_sent=mandatory_sent,
        tn_images=[])

    await message.answer(
        f"✅ مدرک *{title}* با *{len(images)} تصویر* ثبت شد.\\n\\n"
        "آیا مدرک دیگری نیز می‌خواهید ارسال کنید؟",
        reply_markup=lavayeh_attachment_more_kb)
    await state.set_state(Form.tn_attachment_more)


@tajdid_nazar_router.message(Form.tn_images, F.text == "➕ افزودن مدرک دیگر")
async def tn_add_more_images(message: Message, state: FSMContext):
    data = await state.get_data()
    images = data.get("tn_images", [])

    if not images:
        await message.answer("⚠️ حداقل یک تصویر باید ارسال کنید.")
        return

    title = data.get("_tn_current_att_title", "مستندات")
    attachments = data.get("tn_attachments", [])
    mandatory_sent = data.get("_tn_mandatory_proxy_sent", True)

    attachments.append({"title": title, "images": list(images)})

    if title == "مدرک نمایندگی":
        mandatory_sent = True

    await state.update_data(
        tn_attachments=attachments,
        _tn_mandatory_proxy_sent=mandatory_sent,
        tn_images=[])

    await _ask_tn_attachment(message, state, is_first=False)


@tajdid_nazar_router.message(Form.tn_images, F.text == "🗑 حذف تصویر")
async def tn_delete_image(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    images = data.get("tn_images", [])
    if not images:
        await message.answer("⚠️ لیست تصاویر خالی است.")
        return
    await message.answer("🗑 *حذف تصویر:*\\n\\nعکس‌های ارسالی:")
    for i, file_id in enumerate(images):
        await bot.send_photo(message.chat.id, photo=file_id, caption=f"تصویر شماره {i + 1}")
    await message.answer(
        "لطفاً *شماره تصویر* برای حذف را ارسال فرمایید:",
        reply_markup=ReplyKeyboardRemove())
    await state.update_data(_tn_deleting_image=True)


@tajdid_nazar_router.message(Form.tn_images)
async def tn_images_text_fallback(message: Message, state: FSMContext):
    text = message.text or ""
    data = await state.get_data()
    images = data.get("tn_images", [])
    deleting = data.get("_tn_deleting_image", False)

    if deleting:
        num_str = _to_en(text)
        if num_str.isdigit():
            idx = int(num_str) - 1
            if 0 <= idx < len(images):
                images.pop(idx)
                await state.update_data(tn_images=images, _tn_deleting_image=False)
                from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
                if images:
                    manage_kb = ReplyKeyboardMarkup(
                        keyboard=[
                            [KeyboardButton(text="✅ اتمام ارسال تصاویر")],
                            [KeyboardButton(text="➕ افزودن مدرک دیگر")],
                            [KeyboardButton(text="🗑 حذف تصویر")],
                        ],
                        resize_keyboard=True)
                    await message.answer(
                        f"✅ تصویر شماره *{idx + 1}* حذف شد.\\n"
                        f"تعداد تصاویر باقی‌مانده: *{len(images)} تصویر*",
                        reply_markup=manage_kb)
                else:
                    await message.answer(
                        "⚠️ همه تصاویر حذف شدند. لطفاً دوباره تصویر ارسال کنید:",
                        reply_markup=ReplyKeyboardRemove())
            else:
                await message.answer("⚠️ شماره نامعتبر.")
        else:
            await message.answer("⚠️ لطفاً فقط عدد ارسال کنید.")
    else:
        await message.answer("⚠️ لطفاً تصویر ارسال کنید یا یکی از گزینه‌های موجود را انتخاب کنید.")


@tajdid_nazar_router.message(Form.tn_attachment_more)
async def tn_attachment_more_handler(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if text == "✅ خیر، ادامه بده":
        await _ask_tn_extra_text(message, state)
        return
    if text == "➕ بله، عنوان و مدرک دیگر دارم":
        await _ask_tn_attachment(message, state, is_first=False)
        return
    await message.answer(
        "⚠️ لطفاً یکی از گزینه‌های موجود را انتخاب فرمایید:",
        reply_markup=lavayeh_attachment_more_kb)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۱۳ — توضیحات جداگانه (اختیاری)
# ══════════════════════════════════════════════════════════════════════════════
async def _ask_tn_extra_text(message: Message, state: FSMContext):
    data = await state.get_data()
    case_type = data.get("case_type", "")
    if _needs_reasons(case_type):
        # برای اعاده دادرسی، اول جهات بعد توضیحات
        await _ask_tn_reasons(message, state)
    else:
        await message.answer(
            "💡 در صورتی که *توضیحات جداگانه‌ای* می‌خواهید به مقام قضائی ارائه دهید\n"
            "یا درخواست استعلام یا موارد دیگری دارید، در قسمت زیر تایپ بفرمایید.\n\n"
            "در غیر اینصورت گزینه «رد کردن» را انتخاب کنید:",
            reply_markup=tn_extra_text_kb)
        await state.set_state(Form.tn_extra_text)


@tajdid_nazar_router.message(Form.tn_extra_text)
async def tn_extra_text_handler(message: Message, state: FSMContext, bot: Bot):
    text = (message.text or "").strip()

    if text == "⏭ رد کردن":
        await state.update_data(tn_extra_text="")
        await _go_to_tn_preview(message, state)
        return

    if not text:
        await message.answer(
            "⚠️ لطفاً توضیحات را تایپ کنید یا «رد کردن» را انتخاب فرمایید:",
            reply_markup=tn_extra_text_kb)
        return

    from text_collector import collect_text_part

    async def _on_tn_extra_complete(final_text, st, b, cid, was_editing):
        await st.update_data(tn_extra_text=final_text)
        await _go_to_tn_preview(message, st)

    await collect_text_part(
        user_id=message.from_user.id,
        chat_id=message.chat.id,
        text=text,
        state=state,
        bot=bot,
        on_complete=_on_tn_extra_complete,
        first_part_reply="⏳ در حال دریافت توضیحات...")


# ══════════════════════════════════════════════════════════════════════════════
# مرحله اضافی — جهات (فقط اعاده دادرسی مدنی/کیفری)
# ══════════════════════════════════════════════════════════════════════════════
async def _ask_tn_reasons(message: Message, state: FSMContext):
    data = await state.get_data()
    case_type = data.get("case_type", "")
    all_reasons = _get_reasons_list(case_type)
    selected = data.get("tn_reasons", [])
    remaining = [r for r in all_reasons if r not in selected]

    if not remaining:
        # همه جهات انتخاب شده
        await _ask_tn_extra_text(message, state)
        return

    await message.answer(
        f"⚖️ *جهات درخواست {case_type}:*\n\n"
        f"لطفاً یکی از جهات زیر را انتخاب فرمایید:\n\n"
        f"_(جهات انتخاب‌شده: {len(selected)} مورد)_",
        reply_markup=create_tn_reasons_kb(remaining, selected))
    await state.set_state(Form.tn_reason_select)


@tajdid_nazar_router.message(Form.tn_reason_select)
async def tn_reason_select_handler(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    data = await state.get_data()
    case_type = data.get("case_type", "")
    all_reasons = _get_reasons_list(case_type)
    selected = data.get("tn_reasons", [])

    if text == "✅ اتمام انتخاب جهات":
        await _ask_tn_extra_text(message, state)
        return

    # دکمه ادامه مراحل در کیبورد انتخاب جهات
    if text.startswith("✅ خیر") or "ادامه مراحل" in text:
        await _ask_tn_extra_text(message, state)
        return

    if text == "🔙 بازگشت":
        await _ask_tn_extra_text(message, state)
        return

    # پیدا کردن جهتی که کاربر انتخاب کرد
    matched_reason = None
    for r in all_reasons:
        if text in r or r in text:
            matched_reason = r
            break

    if not matched_reason or matched_reason in selected:
        await message.answer(
            "⚠️ لطفاً یکی از جهات موجود را انتخاب فرمایید:",
            reply_markup=create_tn_reasons_kb(
                [r for r in all_reasons if r not in selected], selected
            ))
        return

    selected.append(matched_reason)
    await state.update_data(tn_reasons=selected)

    remaining = [r for r in all_reasons if r not in selected]

    if not remaining:
        await message.answer(
            f"✅ همه جهات انتخاب شدند.\n\n"
            f"آیا جهات دیگری وجود دارد؟",
            reply_markup=tn_reason_more_kb)
        await state.set_state(Form.tn_more_reasons)
    else:
        await message.answer(
            f"✅ جهتی ثبت شد. (مجموع: {len(selected)} مورد)\n\n"
            f"آیا جهت دیگری نیز وجود دارد؟",
            reply_markup=tn_reason_more_kb)
        await state.set_state(Form.tn_more_reasons)


@tajdid_nazar_router.message(Form.tn_more_reasons)
async def tn_more_reasons_handler(message: Message, state: FSMContext):
    text = (message.text or "").strip()

    if text.startswith("➕ بله") or text == "بله" or "مورد دیگری" in text:
        await _ask_tn_reasons(message, state)
        return

    if text.startswith("✅ خیر") or text == "خیر" or "ادامه مراحل" in text or text == "✅ اتمام انتخاب جهات":
        await _ask_tn_extra_text(message, state)
        return

    await message.answer(
        "⚠️ لطفاً «بله» یا «خیر» را انتخاب فرمایید:",
        reply_markup=tn_reason_more_kb)


# ══════════════════════════════════════════════════════════════════════════════
# توابع کمکی برای استعلام و انتخاب افراد از پرونده
# ══════════════════════════════════════════════════════════════════════════════

async def _handle_query_persons(message: Message, state: FSMContext, bot: Bot, section: str):
    """مدیریت گزینه استعلام افراد موجود در پرونده.

    این تابع:
    ۱. به کاربر اعلام می‌کند در حال استعلام است
    ۲. تابع pre_query_tn_persons را فراخوانی می‌کند
    ۳. نتایج را در runtime_state ذخیره می‌کند
    ۴. لیست انتخاب را با اینلاین کیبورد نمایش می‌دهد

    Args:
        message: پیام کاربر
        state: حالت FSM
        bot: نمونه ربات
        section: "appellant" یا "appellee"
    """
    user_id = message.from_user.id
    data = await state.get_data()
    labels = data.get("tn_labels", {})
    section_label = labels.get(section, "تجدیدنظرخواه" if section == "appellant" else "تجدیدنظرخوانده")

    # نام step در سامانه
    from tajdid_nazar_scenario import (
        APPELLANT_STEP_MAP, APPELLEE_STEP_MAP,
        pre_query_tn_persons, TajdidFatalError,
    )
    case_type = data.get("case_type", "")
    if section == "appellant":
        step_name = APPELLANT_STEP_MAP.get(case_type, "تجديدنظرخواه")
    else:
        step_name = APPELLEE_STEP_MAP.get(case_type, "تجديدنظرخوانده")

    # اطلاع‌رسانی به کاربر
    await message.answer(
        "⏳ *در حال استعلام پرونده برای شناسایی افراد موجود در پرونده می‌باشیم...*",
        reply_markup=ReplyKeyboardRemove())

    try:
        # فراخوانی تابع استعلام
        query_data = {
            "case_type": case_type,
            "tn_judge_no": data.get("tn_judge_no", ""),
            "tn_file_no": data.get("tn_file_no", ""),
            "tn_judge_date": data.get("tn_judge_date", ""),
            "tn_province": data.get("tn_province", ""),
            "user_id": user_id,
        }
        names = await pre_query_tn_persons(query_data, bot, step_name)

        if not names:
            await message.answer(
                "⚠️ هیچ فردی در پرونده یافت نشد.\n\n"
                "لطفاً از روش ورود دستی کدملی استفاده فرمایید:")
            if section == "appellant":
                await message.answer(
                    f"👤 لطفاً *نوع شخصیت {section_label}* را انتخاب فرمایید:",
                    reply_markup=create_tn_appellant_person_type_kb())
                await state.set_state(Form.tn_appellant_person_type)
            else:
                await message.answer(
                    f"👥 لطفاً *نوع شخصیت {section_label}* را انتخاب فرمایید:",
                    reply_markup=create_tn_appellee_person_type_kb())
                await state.set_state(Form.tn_appellee_person_type)
            return

        # ذخیره نتایج در runtime_state
        runtime_state.tn_queried_persons[user_id] = {
            "all_names": names,
            "section": section,
            "selected_indices": [],
        }

        # تنظیم state
        if section == "appellant":
            await state.set_state(Form.tn_appellant_select_from_list)
        else:
            await state.set_state(Form.tn_appellee_select_from_list)

        # نمایش لیست انتخاب
        await _show_person_selection_list(bot, user_id, names, [], section, data)

    except TajdidFatalError as e:
        logger.error(f"[TN] خطای استعلام افراد: {e}")
        await message.answer(
            f"❌ خطا در استعلام: {e}\\n\\n"
            "لطفاً از روش ورود دستی کدملی استفاده فرمایید:")
        if section == "appellant":
            await message.answer(
                f"👤 لطفاً *نوع شخصیت {section_label}* را انتخاب فرمایید:",
                reply_markup=create_tn_appellant_person_type_kb())
            await state.set_state(Form.tn_appellant_person_type)
        else:
            await message.answer(
                f"👥 لطفاً *نوع شخصیت {section_label}* را انتخاب فرمایید:",
                reply_markup=create_tn_appellee_person_type_kb())
            await state.set_state(Form.tn_appellee_person_type)
    except Exception as e:
        logger.error(f"[TN] خطای عمومی استعلام افراد: {e}", exc_info=True)
        await message.answer(
            "❌ خطایی در استعلام رخ داد. لطفاً مجدداً تلاش فرمایید یا از روش ورود دستی کدملی استفاده کنید:")
        if section == "appellant":
            await message.answer(
                f"👤 لطفاً *نوع شخصیت {section_label}* را انتخاب فرمایید:",
                reply_markup=create_tn_appellant_person_type_kb())
            await state.set_state(Form.tn_appellant_person_type)
        else:
            await message.answer(
                f"👥 لطفاً *نوع شخصیت {section_label}* را انتخاب فرمایید:",
                reply_markup=create_tn_appellee_person_type_kb())
            await state.set_state(Form.tn_appellee_person_type)


async def _show_person_selection_list(bot: Bot, user_id: int, all_names: list,
                                     selected_indices: list, section: str, data: dict):
    """نمایش لیست نام‌ها با اینلاین کیبورد برای انتخاب.

    هر نام انتخاب‌شده از لیست موجود حذف و به لیست انتخاب‌شده‌ها اضافه می‌شود.
    دکمه ریست برای شروع مجدد انتخاب وجود دارد.

    Args:
        bot: نمونه ربات
        user_id: آیدی کاربر
        all_names: لیست کامل نام‌ها [{"index": int, "name": str}, ...]
        selected_indices: لیست ایندکس‌های انتخاب‌شده
        section: "appellant" یا "appellee"
        data: داده‌های state
    """
    labels = data.get("tn_labels", {})
    section_label = labels.get(section, "تجدیدنظرخواه" if section == "appellant" else "تجدیدنظرخوانده")

    # تفکیک انتخاب‌شده‌ها و موجود
    available = [n for i, n in enumerate(all_names) if i not in selected_indices]
    selected = [all_names[i] for i in selected_indices if i < len(all_names)]

    # ساخت متن پیام
    text = f"📋 *لیست افراد پرونده — {section_label}*\n\n"

    if selected:
        text += "✅ *انتخاب شده‌اند: *\n"
        for i, n in enumerate(selected, 1):
            text += f"  {i}. {n['name']}\n"
        text += "\n"

    if available:
        text += "👤 *در انتظار انتخاب — روی نام مورد نظر کلیک کنید: *\n"
        text += "_(هر نامی که انتخاب کنید از لیست حذف می‌شود)_\n\n"
    else:
        text += "✅ *تمام افراد انتخاب شده‌اند.*\n\n"

    # ساخت اینلاین کیبورد
    prefix = "tnq_a" if section == "appellant" else "tnq_p"
    keyboard = []

    # دکمه‌های انتخاب نام‌های موجود
    for n in available:
        # حذف فاصله‌های اضافی برای callback data
        safe_name = n["name"][:40]
        keyboard.append([InlineKeyboardButton(
            text=f"➕ {safe_name}",
            callback_data=f"{prefix}_sel:{n['index']}"
        )])

    # دکمه‌های حذف از انتخاب‌شده‌ها
    if selected:
        for n in selected:
            safe_name = n["name"][:40]
            keyboard.append([InlineKeyboardButton(
                text=f"❌ {safe_name}",
                callback_data=f"{prefix}_rm:{all_names.index(n)}"
            )])

    # دکمه‌های ریست و تایید
    nav_row = []
    if selected:
        nav_row.append(InlineKeyboardButton(
            text="🔄 ریست انتخاب‌ها",
            callback_data=f"{prefix}_reset:0"
        ))
        nav_row.append(InlineKeyboardButton(
            text="✅ تایید و ادامه",
            callback_data=f"{prefix}_done:0"
        ))
        keyboard.append(nav_row)

    # دکمه بازگشت
    keyboard.append([InlineKeyboardButton(
        text="🔙 بازگشت به انتخاب دستی",
        callback_data=f"{prefix}_back:0"
    )])

    kb = InlineKeyboardMarkup(inline_keyboard=keyboard)
    await bot.send_message(user_id, text, reply_markup=kb)


async def _handle_person_select_callback(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """هندلر کلی callback های انتخاب/حذف/ریست/تایید افراد.

    فرمت callback_data:
        tnq_a_sel:{index}  — انتخاب تجدیدنظرخواه
        tnq_a_rm:{index}   — حذف از انتخاب تجدیدنظرخواه
        tnq_a_reset:0      — ریست انتخاب تجدیدنظرخواه
        tnq_a_done:0       — تایید انتخاب تجدیدنظرخواه
        tnq_a_back:0       — بازگشت
        tnq_p_sel:{index}  — انتخاب تجدیدنظرخوانده
        tnq_p_rm:{index}   — حذف از انتخاب تجدیدنظرخوانده
        tnq_p_reset:0      — ریست
        tnq_p_done:0       — تایید
        tnq_p_back:0       — بازگشت
    """
    user_id = callback.from_user.id
    parts = callback.data.split(":")
    prefix = parts[0]  # مثلاً tnq_a یا tnq_p
    action = parts[1]  # sel, rm, reset, done, back
    index = int(parts[2]) if len(parts) > 2 else 0

    section = "appellant" if prefix == "tnq_a" else "appellee"

    # دریافت اطلاعات ذخیره‌شده
    queried = runtime_state.tn_queried_persons.get(user_id)
    if not queried:
        await callback.answer("⚠️ اطلاعات منقضی شده است. لطفاً مجدداً شروع کنید.", show_alert=True)
        return

    all_names = queried["all_names"]
    selected_indices = queried["selected_indices"]
    data = await state.get_data()

    if action == "back":
        # بازگشت به انتخاب دستی
        runtime_state.tn_queried_persons.pop(user_id, None)
        await callback.answer()
        labels = data.get("tn_labels", {})
        if section == "appellant":
            section_label = labels.get("appellant", "تجدیدنظرخواه")
            await bot.send_message(
                user_id,
                f"👤 لطفاً *نوع شخصیت {section_label}* را انتخاب فرمایید:\n\n"
                f"💡 در صورتی که کدملی افراد پرونده را ندارید، گزینه استعلام افراد موجود در پرونده را انتخاب کنید",
                reply_markup=create_tn_appellant_person_type_kb())
            await state.set_state(Form.tn_appellant_person_type)
        else:
            section_label = labels.get("appellee", "تجدیدنظرخوانده")
            await bot.send_message(
                user_id,
                f"👥 لطفاً *نوع شخصیت {section_label}* را انتخاب فرمایید:\n\n"
                f"💡 در صورتی که کدملی افراد پرونده را ندارید، گزینه استعلام افراد موجود در پرونده را انتخاب کنید",
                reply_markup=create_tn_appellee_person_type_kb())
            await state.set_state(Form.tn_appellee_person_type)
        return

    if action == "reset":
        # ریست انتخاب‌ها
        queried["selected_indices"] = []
        await callback.answer("ریست انجام شد.")
        # حذف پیام قبلی و ارسال پیام جدید
        try:
            await callback.message.delete()
        except Exception:
            pass
        await _show_person_selection_list(bot, user_id, all_names, [], section, data)
        return

    if action == "sel":
        # انتخاب یک نام
        if index not in selected_indices:
            selected_indices.append(index)
            name = all_names[index]["name"] if index < len(all_names) else ""
            await callback.answer(f"✅ {name} انتخاب شد.")
        else:
            await callback.answer("این نام قبلاً انتخاب شده.")

        queried["selected_indices"] = selected_indices
        # حذف پیام قبلی و ارسال پیام جدید
        try:
            await callback.message.delete()
        except Exception:
            pass
        await _show_person_selection_list(bot, user_id, all_names, selected_indices, section, data)
        return

    if action == "rm":
        # حذف از انتخاب‌ها
        if index in selected_indices:
            selected_indices.remove(index)
            name = all_names[index]["name"] if index < len(all_names) else ""
            await callback.answer(f"❌ {name} از انتخاب حذف شد.")
        else:
            await callback.answer("این نام در لیست انتخاب نیست.")

        queried["selected_indices"] = selected_indices
        try:
            await callback.message.delete()
        except Exception:
            pass
        await _show_person_selection_list(bot, user_id, all_names, selected_indices, section, data)
        return

    if action == "done":
        # تایید انتخاب نهایی
        if not selected_indices:
            await callback.answer("⚠️ حداقل یک فرد باید انتخاب کنید!", show_alert=True)
            return

        selected_names = [all_names[i]["name"] for i in selected_indices if i < len(all_names)]
        labels = data.get("tn_labels", {})
        section_label = labels.get(section, "تجدیدنظرخواه" if section == "appellant" else "تجدیدنظرخوانده")

        await callback.answer(f"✅ {len(selected_names)} نفر به عنوان {section_label} انتخاب شد.")

        # پاکسازی
        runtime_state.tn_queried_persons.pop(user_id, None)

        # ذخیره در state
        if section == "appellant":
            appellants = []
            for i in selected_indices:
                name = all_names[i]["name"] if i < len(all_names) else ""
                appellants.append({
                    "person_type": "شخص حقیقی",
                    "national_id": "",
                    "name": name,
                    "query_mode": True,
                })
            await state.update_data(
                tn_appellants=appellants,
                tn_appellant_query_mode=True,
                tn_appellant_selected_names=selected_names,
            )

            # رفتن به مرحله بعد
            case_type = data.get("case_type", "")
            if _is_prosecutor_objection(case_type):
                witness_label = labels.get("witness_step", "مطلع/گواه")
                await bot.send_message(
                    user_id,
                    f"✅ *{len(selected_names)} نفر* به عنوان {section_label} انتخاب شد.\n\n"
                    f"*مرحله ۹:* در صورتی که *{witness_label}* دارید، کدملی شخص حقیقی را وارد فرمایید.\n\n"
                    f"در صورتی که {witness_label} ندارید، گزینه «خیر» را انتخاب فرمایید:",
                    reply_markup=tn_more_witnesses_kb)
                await state.set_state(Form.tn_more_witnesses)
            else:
                appellee_label = labels.get("appellee", "تجدیدنظرخوانده")
                await bot.send_message(
                    user_id,
                    f"✅ *{len(selected_names)} نفر* به عنوان {section_label} انتخاب شد.\n\n"
                    f"*مرحله ۹:* لطفاً *نوع شخصیت {appellee_label}* را انتخاب فرمایید:\n\n"
                    f"💡 در صورتی که کدملی افراد پرونده را ندارید، گزینه استعلام افراد موجود در پرونده را انتخاب کنید",
                    reply_markup=create_tn_appellee_person_type_kb())
                await state.set_state(Form.tn_appellee_person_type)
        else:
            appellees = []
            for i in selected_indices:
                name = all_names[i]["name"] if i < len(all_names) else ""
                appellees.append({
                    "person_type": "شخص حقیقی",
                    "national_id": "",
                    "name": name,
                    "query_mode": True,
                })
            await state.update_data(
                tn_appellees=appellees,
                tn_appellee_query_mode=True,
                tn_appellee_selected_names=selected_names,
            )

            # رفتن به مرحله شهود
            witness_label = labels.get("witness_step", "مطلع/گواه")
            await bot.send_message(
                user_id,
                f"✅ *{len(selected_names)} نفر* به عنوان {section_label} انتخاب شد.\n\n"
                f"*مرحله ۱۰:* در صورتی که *{witness_label}* دارید، کدملی شخص حقیقی را وارد فرمایید.\n\n"
                f"در صورتی که {witness_label} ندارید، گزینه «خیر» را انتخاب فرمایید:",
                reply_markup=tn_more_witnesses_kb)
            await state.set_state(Form.tn_more_witnesses)
        return


# ثبت callback handler ها
@tajdid_nazar_router.callback_query(F.data.startswith("tnq_a_"))
async def tn_query_appellant_callback(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """callback handler برای انتخاب تجدیدنظرخواه از لیست استعلام"""
    await _handle_person_select_callback(callback, state, bot)


@tajdid_nazar_router.callback_query(F.data.startswith("tnq_p_"))
async def tn_query_appellee_callback(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """callback handler برای انتخاب تجدیدنظرخوانده از لیست استعلام"""
    await _handle_person_select_callback(callback, state, bot)


# هندلر پیام در حالت انتخاب — فقط اطلاع‌رسانی
@tajdid_nazar_router.message(Form.tn_appellant_select_from_list)
async def tn_appellant_select_from_list_msg(message: Message, state: FSMContext):
    """در حالت انتخاب از لیست، فقط از دکمه‌ها استفاده کنید"""
    await message.answer(
        "⚠️ لطفاً از دکمه‌های موجود در پیام لیست استفاده کنید.\n\n"
        "برای انتخاب یک نفر، روی نام آن کلیک کنید.\n"
        "برای حذف از انتخاب شده‌ها، روی دکمه ❌ کلیک کنید.\n"
        "برای ریست، روی 🔄 کلیک کنید.")


@tajdid_nazar_router.message(Form.tn_appellee_select_from_list)
async def tn_appellee_select_from_list_msg(message: Message, state: FSMContext):
    """در حالت انتخاب از لیست، فقط از دکمه‌ها استفاده کنید"""
    await message.answer(
        "⚠️ لطفاً از دکمه‌های موجود در پیام لیست استفاده کنید.\n\n"
        "برای انتخاب یک نفر، روی نام آن کلیک کنید.\n"
        "برای حذف از انتخاب شده‌ها، روی دکمه ❌ کلیک کنید.\n"
        "برای ریست، روی 🔄 کلیک کنید.")


# ══════════════════════════════════════════════════════════════════════════════
# مرحله نهایی — پیش‌نمایش و تایید
# ══════════════════════════════════════════════════════════════════════════════
def _person_line(p: dict, idx: int) -> str:
    pt = p.get("person_type", "")
    nid = p.get("national_id", "")
    cid = p.get("company_id", "")
    rep = p.get("representative_type", "")
    name = p.get("name", "")

    if p.get("query_mode"):
        return f"  {idx}. {name} _(استعلام از پرونده)_"

    if pt == "شخص حقوقی":
        line = f"  {idx}. {pt} — شناسه ملی: `{cid}`"
        if rep:
            line += f" ({rep}: `{nid}`)"
        return line
    else:
        return f"  {idx}. {pt} — کدملی: `{nid}`"


def build_tn_preview(data: dict) -> str:
    case_type = data.get("case_type", "")
    labels = data.get("tn_labels", {})
    appellant_label = labels.get("appellant", "تجدیدنظرخواه")
    appellee_label = labels.get("appellee", "تجدیدنظرخوانده")
    witness_label = labels.get("witness_step", "مطلع/گواه")

    judge_no = data.get("tn_judge_no", "")
    file_no = data.get("tn_file_no", "")
    # ردیف فرعی حذف شد
    judge_date = data.get("tn_judge_date", "")
    province = data.get("tn_province", "")
    doc_type = data.get("tn_doc_type", "")
    amount = data.get("tn_amount", 0)
    insolvency = data.get("tn_insolvency", False)

    appellants = data.get("tn_appellants", [])
    appellees = data.get("tn_appellees", [])
    witnesses = data.get("tn_witnesses", [])
    tn_text = data.get("tn_text", "")
    extra_text = data.get("tn_extra_text", "")
    attachments = data.get("tn_attachments", [])
    reasons = data.get("tn_reasons", [])

    appellants_text = "\\n".join([_person_line(p, i + 1) for i, p in enumerate(appellants)]) or "  (ندارد)"
    appellees_text = "\\n".join([_person_line(p, i + 1) for i, p in enumerate(appellees)]) or "  (ندارد)"
    witnesses_text = "\\n".join(
        [f"  {i + 1}. کدملی: `{w.get('national_id', '')}`" for i, w in enumerate(witnesses)]
    ) or "  (ندارد)"

    text_preview = tn_text[:300] + "..." if len(tn_text) > 300 else tn_text
    text_preview = _escape_md(text_preview)

    att_text = ""
    total_imgs = 0
    for i, att in enumerate(attachments, 1):
        n = len(att.get("images", []))
        total_imgs += n
        att_text += f"  {i}. {_escape_md(att.get('title', 'مستندات'))} — {n} تصویر\\n"
    if not att_text:
        att_text = "  (بدون مدرک)\\n"

    reasons_text = ""
    if reasons:
        reasons_text = "\\n".join([f"  {i + 1}. {_escape_md(r)}" for i, r in enumerate(reasons)])
        reasons_text = f"\\n⚖️ *جهات:*\\n{reasons_text}\\n"

    extra_text_line = ""
    if extra_text:
        extra_preview = extra_text[:150] + "..." if len(extra_text) > 150 else extra_text
        extra_text_line = f"\\n📝 *توضیحات جداگانه:*\\n  {_escape_md(extra_preview)}\\n"

    is_prosec = _is_prosecutor_objection(case_type)
    amount_str = f"{_fmt(amount)} ریال" if amount > 0 else "خیر"
    insolvency_str = "بله" if insolvency else "خیر"

    if is_prosec:
        info_section = (
            f"📋 *اطلاعات قرار:*\\n"
            f"  شماره قرار: `{judge_no}`\\n"
            f"  شماره پرونده: `{file_no}`\\n"
            f"  تاریخ: `{judge_date}`\\n"
            f"  استان: {province}\\n"
        )
    else:
        info_section = (
            f"📋 *اطلاعات دادنامه:*\\n"
            f"  شماره دادنامه: `{judge_no}`\\n"
            f"  شماره پرونده: `{file_no}`\\n"
            f"  تاریخ: `{judge_date}`\\n"
            f"  استان: {province}\\n"
            f"  نوع: *{doc_type}*\\n"
            f"  مبلغ: {amount_str}\\n"
            f"  اعسار: {insolvency_str}\\n"
        )

    appellee_section = "" if is_prosec else f"\\n👥 *{appellee_label}(ها):*\\n{appellees_text}\\n"

    return (
        f"⚖️ *پیش‌نمایش {case_type}:*\\n\\n"
        f"{info_section}\\n"
        f"👤 *{appellant_label}(ها):*\\n{appellants_text}\\n\\n"
        f"{appellee_section}\\n"
        f"👁 *{witness_label}(ها):*\\n{witnesses_text}\\n\\n"
        f"📄 *شرح متن:*\\n  {text_preview}\\n"
        f"{extra_text_line}"
        f"🖼 *مدارک ({total_imgs} تصویر در {len(attachments)} عنوان):*\\n{att_text}"
        f"{reasons_text}"
        f"\\nآیا اطلاعات فوق صحیح است؟"
    )


async def _go_to_tn_preview(message: Message, state: FSMContext):
    data = await state.get_data()
    preview = build_tn_preview(data)
    data = await state.get_data()
    labels = data.get("tn_labels", {})
    case_type = data.get("case_type", "")
    has_reasons = _needs_reasons(case_type)
    has_appellee = not _is_prosecutor_objection(case_type)
    labels_with_case = {**labels, "case_type": case_type}
    # Fix 6: نمایش کیبورد تایید/ویرایش (نه کیبورد ویرایش مستقیم)
    try:
        await message.answer(preview, reply_markup=tn_confirm_kb)
    except Exception:
        await message.answer(preview, reply_markup=tn_confirm_kb)
    await state.set_state(Form.tn_confirm)


# ══════════════════════════════════════════════════════════════════════════════
# تایید یا ویرایش
# ══════════════════════════════════════════════════════════════════════════════
@tajdid_nazar_router.message(Form.tn_confirm)
async def tn_confirm_handler(message: Message, state: FSMContext, bot: Bot):
    text = message.text or ""

    if text == "✅ تایید و شروع ثبت":
        data = await state.get_data()
        user_id = message.from_user.id
        case_type = data.get("case_type", "")

        # تعیین task_type
        TASK_TYPE_MAP = {
            "تجدیدنظرخواهی": "TN_APPEAL",
            "واخواهی": "TN_REHEARING",
            "فرجام خواهی": "TN_SUPREME",
            "اعاده دادرسی مدنی": "TN_CIVIL_REVIEW",
            "اعاده دادرسی کیفری": "TN_CRIMINAL_REVIEW",
            "اعتراض ثالث": "TN_THIRD_PARTY",
            "اعتراض به قرار دادسرا": "TN_PROSECUTOR_OBJECTION",
        }
        task_type = TASK_TYPE_MAP.get(case_type, "TN_APPEAL")

        # FIX: ارسال مستقیم به صف پردازش (job_queue) به جای ذخیره در state
        # قبلاً تسک فقط در FSM state ذخیره می‌شد و هرگز پردازش نمی‌شد
        # همچنین پیام امضای الکترونیک بلافاصله نمایش داده می‌شد که اشتباه بود
        # امضا فقط پس از چاپ، پرداخت و تایید پرداخت باید نمایش داده شود
        job_data = {
            "user_id": user_id,
            "query_type": f"دعاوی_اعتراضی_{case_type}",
            "task_type": task_type,
            "case_type": case_type,
            "tn_judge_no": data.get("tn_judge_no", ""),
            "tn_file_no": data.get("tn_file_no", ""),
            "tn_judge_date": data.get("tn_judge_date", ""),
            "tn_province": data.get("tn_province", ""),
            "tn_doc_type": data.get("tn_doc_type", ""),
            "tn_amount": data.get("tn_amount", 0),
            "tn_insolvency": data.get("tn_insolvency", False),
            "tn_appellants": data.get("tn_appellants", []),
            "tn_appellees": data.get("tn_appellees", []),
            "tn_witnesses": data.get("tn_witnesses", []),
            "tn_text": data.get("tn_text", ""),
            "tn_text_html": data.get("tn_text_html", ""),
            "tn_extra_text": data.get("tn_extra_text", ""),
            "tn_attachments": data.get("tn_attachments", []),
            "tn_reasons": data.get("tn_reasons", []),
            "tn_labels": data.get("tn_labels", {}),
            "tn_appellant_query_mode": data.get("tn_appellant_query_mode", False),
            "tn_appellant_selected_names": data.get("tn_appellant_selected_names", []),
            "tn_appellee_query_mode": data.get("tn_appellee_query_mode", False),
            "tn_appellee_selected_names": data.get("tn_appellee_selected_names", []),
        }

        # 📥 کپی کامل درخواست برای ادمین — همین لحظه، مستقل از موفقیت/شکست
        # پردازش خودکار بعدی در سنا.
        try:
            from admin_forward import send_generic_submission_to_admin
            from config import ADMIN_ID
            await send_generic_submission_to_admin(
                bot, ADMIN_ID, user_id, f"دعاوی اعتراضی ({case_type})", job_data,
                image_keys=["tn_attachments"],
            )
        except Exception as e:
            logging.error(f"[TN] خطا در ارسال کپی درخواست به ادمین: {e}", exc_info=True)

        await runtime_state.job_queue.put(job_data)

        try:
            from panel_sync import upsert_case_to_panel
            await upsert_case_to_panel(
                bale_user_id=user_id, full_name=str(user_id),
                service_type="TAJDID_NAZAR", status="PROCESSING",
                document_category=case_type,
                result_summary="در حال ثبت در سامانه سنا",
            )
        except Exception as panel_err:
            logging.warning(f"[TN] خطا در ثبت اولیه پرونده در پنل: {panel_err}")

        await message.answer(
            f"✅ *درخواست {case_type} تایید شد و به صف پردازش ارسال شد.*\n\n"
            f"⏳ ثبت در سامانه قضایی در حال انجام است."
            f" پس از آماده‌سازی و محاسبه هزینه، مبلغ پرداخت و رسید آن ارسال خواهد شد.",
            reply_markup=ReplyKeyboardRemove())
        await state.clear()
        return

    if text == "✏️ ویرایش اطلاعات":
        data = await state.get_data()
        labels = data.get("tn_labels", {})
        case_type = data.get("case_type", "")
        has_reasons = _needs_reasons(case_type)
        has_appellee = not _is_prosecutor_objection(case_type)
        # FIX: استفاده از کیبورد داینامیک با برچسب‌های صحیح (مثلاً «معترض ثالث»
        # به جای «تجدیدنظرخواه» برای اعتراض ثالث)
        dynamic_edit_kb = create_tn_edit_kb(
            labels=labels, has_reasons=has_reasons, has_appellee=has_appellee
        )
        await message.answer(
            "✏️ *ویرایش اطلاعات:*\n\nکدام بخش را می‌خواهید ویرایش کنید؟",
            reply_markup=dynamic_edit_kb)
        await state.set_state(Form.tn_edit_choice)
        return

    await message.answer(
        "⚠️ لطفاً یکی از گزینه‌های زیر را انتخاب فرمایید:",
        reply_markup=tn_confirm_kb)


# ══════════════════════════════════════════════════════════════════════════════
# منوی ویرایش
# ══════════════════════════════════════════════════════════════════════════════
@tajdid_nazar_router.message(Form.tn_edit_choice)
async def tn_edit_choice_handler(message: Message, state: FSMContext):
    text = message.text or ""
    data = await state.get_data()
    labels = data.get("tn_labels", {})
    await state.update_data(_tn_editing=True)
    appellant_label = labels.get("appellant", "تجدیدنظرخواه")
    appellee_label = labels.get("appellee", "تجدیدنظرخوانده")
    case_type = data.get("case_type", "")

    if text == "🔙 بازگشت به پیش‌نمایش":
        await _go_to_tn_preview(message, state)
        return

    if text == "📋 ویرایش اطلاعات دادنامه":
        await state.update_data(tn_judge_no="")
        await message.answer(
            "📋 لطفاً *شماره دادنامه* جدید را ارسال فرمایید:\n\n_(۱۴۰۰ تا ۱۴۰۷: ۱۸ رقمی | ۹۹ و قبل‌تر: ۱۶ رقمی)_",
            reply_markup=back_only_kb)
        await state.set_state(Form.tn_judge_no)
        return

    if text == f"👤 ویرایش {appellant_label}":
        await state.update_data(tn_appellants=[], _tn_current_appellant={})
        await message.answer(
            f"👤 لیست {appellant_label} پاک شد.\n"
            f"لطفاً مجدداً *نوع شخصیت {appellant_label}* را انتخاب فرمایید:",
            reply_markup=create_tn_appellant_person_type_kb())
        await state.set_state(Form.tn_appellant_person_type)
        return

    if text == f"👥 ویرایش {appellee_label}":
        await state.update_data(tn_appellees=[], _tn_current_appellee={})
        await message.answer(
            f"👥 لیست {appellee_label} پاک شد.\n"
            f"لطفاً مجدداً *نوع شخصیت {appellee_label}* را انتخاب فرمایید:",
            reply_markup=create_tn_appellee_person_type_kb())
        await state.set_state(Form.tn_appellee_person_type)
        return

    if text == "👀 ویرایش شهود/مطلع":
        await state.update_data(tn_witnesses=[])
        labels = data.get("tn_labels", {})
        witness_label = labels.get("witness_step", "مطلع/گواه")
        await message.answer(
            f"👀 لیست {witness_label} پاک شد.\n"
            f"در صورتی که {witness_label} دارید، کدملی را وارد فرمایید:\n\n"
            f"در غیر اینصورت «خیر» را انتخاب فرمایید:",
            reply_markup=tn_more_witnesses_kb)
        await state.set_state(Form.tn_more_witnesses)
        return

    if text == "📄 ویرایش شرح متن":
        await message.answer(
            "📄 لطفاً متن جدید را ارسال فرمایید:",
            reply_markup=ReplyKeyboardRemove())
        await state.set_state(Form.tn_text)
        return

    if text == "🖼 ویرایش مدارک":
        await state.update_data(tn_attachments=[], _tn_mandatory_proxy_sent=False)
        data = await state.get_data()
        appellants = data.get("tn_appellants", [])
        appellees = data.get("tn_appellees", [])
        has_legal = any(p.get("person_type") == "شخص حقوقی" for p in appellants + appellees)
        if has_legal:
            await message.answer(
                "⚠️ چون شخص *حقوقی* دارید، ارسال *مدرک نمایندگی اجباری* است.\n\n"
                "لطفاً ابتدا عنوان مدرک نمایندگی را وارد کنید:",
                reply_markup=ReplyKeyboardRemove())
            await state.set_state(Form.tn_attachment_title)
        else:
            await _ask_tn_attachment(message, state, is_first=True)
        return

    if text == "📝 ویرایش توضیحات جداگانه":
        await message.answer(
            "📝 لطفاً توضیحات جدید را تایپ فرمایید یا «رد کردن» را انتخاب کنید:",
            reply_markup=tn_extra_text_kb)
        await state.set_state(Form.tn_extra_text)
        return

    if _needs_reasons(case_type) and text == "⚖️ ویرایش جهات":
        await state.update_data(tn_reasons=[])
        await _ask_tn_reasons(message, state)
        return

    # FIX: کیبورد داینامیک با برچسب‌های صحیح
    dynamic_edit_kb = create_tn_edit_kb(
        labels=labels, has_reasons=_needs_reasons(case_type),
        has_appellee=not _is_prosecutor_objection(case_type)
    )
    await message.answer(
        "⚠️ لطفاً یکی از گزینه‌های موجود را انتخاب فرمایید:",
        reply_markup=dynamic_edit_kb)


# ══════════════════════════════════════════════════════════════════════════════
# هندلرهای خطای استعلام ثنا — ویرایش شناسه ملی یا حذف درخواست
# ══════════════════════════════════════════════════════════════════════════════
@tajdid_nazar_router.callback_query(F.data.startswith("tn_fix_nid:"))
async def tn_fix_national_id_callback(callback: CallbackQuery, state: FSMContext, bot: Bot):
    parts = callback.data.split(":")
    target_user_id = int(parts[1])

    if callback.from_user.id != target_user_id:
        await callback.answer("⚠️ این دکمه مربوط به شما نیست.")
        return

    pending = runtime_state.pending_tn_sana_fix.get(target_user_id)
    if not pending:
        await callback.answer("⚠️ درخواستی برای ویرایش یافت نشد. ممکن است منقضی شده باشد.")
        return

    await callback.answer()

    try:
        await callback.message.edit_text(
            callback.message.text + "\\n\\n✏️ _در انتظار شناسه ملی جدید..._")
    except Exception:
        pass

    await bot.send_message(
        target_user_id,
        "🔢 لطفاً *شناسه ملی صحیح* را ارسال فرمایید:\n_(۱۰ رقمی)_\n\n"
        "⚠️ اطلاعات قبلی حفظ شده و فقط شناسه ملی اصلاح خواهد شد.",
        reply_markup=back_only_kb)
    await state.set_state(Form.tn_sana_error_new_national_id)


@tajdid_nazar_router.callback_query(F.data.startswith("tn_del_req:"))
async def tn_delete_request_callback(callback: CallbackQuery, state: FSMContext, bot: Bot):
    parts = callback.data.split(":")
    target_user_id = int(parts[1])

    if callback.from_user.id != target_user_id:
        await callback.answer("⚠️ این دکمه مربوط به شما نیست.")
        return

    runtime_state.pending_tn_sana_fix.pop(target_user_id, None)
    await callback.answer("درخواست حذف شد.")

    try:
        await callback.message.edit_text(
            callback.message.text + "\\n\\n🗑 _درخواست حذف شد._")
    except Exception:
        pass

    await bot.send_message(
        target_user_id,
        "🗑 *درخواست حذف شد.*\n\nدر صورت نیاز، از منوی اصلی مجدداً اقدام فرمایید.",
        reply_markup=restart_kb)
    await state.clear()


@tajdid_nazar_router.message(Form.tn_sana_error_new_national_id)
async def tn_sana_error_new_national_id_handler(message: Message, state: FSMContext, bot: Bot):
    if not message.text:
        return

    if message.text == "🔙 بازگشت":
        pending = runtime_state.pending_tn_sana_fix.get(message.from_user.id)
        if not pending:
            await message.answer(
                "⚠️ درخواست منقضی شده است. لطفاً مجدداً اقدام فرمایید.",
                reply_markup=restart_kb)
            await state.clear()
            return

        task_data = pending["task_data"]
        old_nid = task_data.get("_sana_error_national_id", "")
        person_role = task_data.get("_sana_error_person_role", "")
        role_label = "تجدیدنظرخواه" if person_role == "appellant" else "تجدیدنظرخوانده"

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✏️ ویرایش شناسه ملی", callback_data=f"tn_fix_nid:{message.from_user.id}")],
            [InlineKeyboardButton(text="🗑 حذف درخواست", callback_data=f"tn_del_req:{message.from_user.id}")],
        ])
        await message.answer(
            f"⚠️ شناسه ملی `{old_nid}` ({role_label}) ثبت‌نام ثنا ندارد یا اشتباه است.\n\n"
            "لطفاً یکی از گزینه‌های زیر را انتخاب کنید:",
            reply_markup=kb)
        return

    nat_id = _to_en(message.text)
    if not re.match(r"^[0-9]{10}$", nat_id):
        await message.answer(
            "⚠️ شناسه ملی باید *۱۰ رقمی* باشد:")
        return

    pending = runtime_state.pending_tn_sana_fix.pop(message.from_user.id, None)
    if not pending:
        await message.answer(
            "⚠️ درخواست منقضی شده است. لطفاً مجدداً اقدام فرمایید.",
            reply_markup=restart_kb)
        await state.clear()
        return

    task_data = pending["task_data"]
    person_role = task_data.get("_sana_error_person_role", "")
    person_index = task_data.get("_sana_error_person_index", 0)

    # جایگزینی شناسه ملی
    if person_role == "appellant":
        appellants = task_data.get("tn_appellants", [])
        if person_index < len(appellants):
            appellants[person_index]["national_id"] = nat_id
            task_data["tn_appellants"] = appellants
    elif person_role == "appellee":
        appellees = task_data.get("tn_appellees", [])
        if person_index < len(appellees):
            appellees[person_index]["national_id"] = nat_id
            task_data["tn_appellees"] = appellees

    # پاکسازی فیلدهای خطا
    task_data.pop("_sana_error_national_id", None)
    task_data.pop("_sana_error_person_role", None)
    task_data.pop("_sana_error_person_index", None)

    await message.answer(
        f"✅ شناسه ملی به `{nat_id}` تغییر یافت.\n\n"
        "⏳ در حال ارسال مجدد درخواست به صف پردازش...",
        reply_markup=restart_kb)

    await runtime_state.job_queue.put(task_data)
    await state.clear()