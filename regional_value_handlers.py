# -*- coding: utf-8 -*-
"""
هندلرهای بخش استعلام ارزش منطقه‌ای ملک (عرصه + اعیانی).

فلو:
  ۱. انتخاب استان
  ۲. ورود آدرس دقیق / موقعیت روی نقشه
  ۳. ورود متراژ عرصه
  ۴. انتخاب کاربری زمین (مسکونی/تجاری/اداری/سایر)
     ↳ سایر: ۵ زیرگزینه با ضریب تعدیل (۰٫۷/۰٫۵/۰٫۴/۰٫۲/۰٫۱)
  ۵. اعیانی: کاربری (مسکونی/تجاری/اداری/سایر ← ۲ زیرگزینه) → نوع سازه →
     متراژ → تکمیل شده؟
       خیر → مرحلهٔ ساخت (فونداسیون/اسکلت/سفت‌کاری/نازک‌کاری)
       بله → پارکینگ و انباری (متراژ) → طبقه → قدمت
  ۶. نمایش فاکتور پرداخت
  ۷. پس از پرداخت موفق → استعلام عرصه از سامانه مالیاتی + تعیین شهرستان از
     روی نقشه + محاسبهٔ اعیانی (ayani_calc) → PDF دو صفحه‌ای (ayani_pdf) → ارسال
"""

import asyncio
import logging
import os

import aiohttp
from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Message, ReplyKeyboardRemove, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery,
)

import ayani_calc
import runtime_state
from bale_file_sender import send_document_direct
from config import ADMIN_ID, BALE_WALLET_TOKEN, BOT_TOKEN, BALE_API_BASE, REGIONAL_VALUE_FEE, temp_path
from exempt_users import is_exempt_user
from keyboards import back_only_kb, get_main_menu_kb
from panel_sync import register_case_to_panel, update_case_in_panel
from states import Form
from tax_geolocation_query import get_province_list, find_land_use_value, extract_all_land_use_values

logger = logging.getLogger(__name__)

regional_value_router = Router()

LAND_USES = ["مسکونی", "تجاری", "اداری"]

# کیبورد مرحلهٔ آدرس: هم تایپ آدرس امکان‌پذیر است، هم دکمهٔ ارسال موقعیت
# روی نقشه (کاربر با زدن این دکمه، صفحهٔ انتخاب نقطه روی نقشه را می‌بیند
# و مختصات همان نقطه مستقیماً برای استعلام استفاده می‌شود).
address_or_location_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📍 ارسال موقعیت روی نقشه", request_location=True)],
        [KeyboardButton(text="🔙 بازگشت")],
    ],
    resize_keyboard=True,
)


# ══════════════════════════════════════════════════════════════════
# موتور مراحل سناریو (جدول‌محور)
#
#  - هر مرحله: نام، کلیدهای داده، شرط لازم‌بودن، تابع پرسش.
#  - _advance: اولین مرحلهٔ لازمِ بی‌پاسخ را می‌پرسد؛ اگر همه پر بودند
#    پیش‌نمایش نمایش داده می‌شود.
#  - بازگشت: دادهٔ مرحلهٔ قبلی (و همهٔ مراحل بعد از آن) پاک و همان مرحله
#    دوباره پرسیده می‌شود.
#  - ویرایش از پیش‌نمایش: از داده‌ها عکس (snapshot) گرفته می‌شود، فیلد
#    انتخابی (و وابسته‌هایش) پاک و دوباره پرسیده می‌شود؛ بعد از پاسخ،
#    اگر مرحلهٔ تازه‌ای لازم شده باشد پرسیده و سپس به پیش‌نمایش برمی‌گردد.
#    «بازگشت» در حالت ویرایش = انصراف از ویرایش و برگشت به پیش‌نمایش.
# ══════════════════════════════════════════════════════════════════
_BACK = "🔙 بازگشت"
_YES, _NO = "✅ بله", "❌ خیر"
_CONFIRM, _EDIT = "✅ تایید و پرداخت", "✏️ ویرایش"


def _to_fa(n) -> str:
    return str(n).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def _to_en(text: str) -> str:
    return (text or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))


def _num_kb(count: int, per_row: int = 5) -> ReplyKeyboardMarkup:
    """کیبورد شماره‌ای ۱..count + بازگشت."""
    nums = [KeyboardButton(text=_to_fa(i)) for i in range(1, count + 1)]
    rows = [nums[i:i + per_row] for i in range(0, len(nums), per_row)]
    rows.append([KeyboardButton(text=_BACK)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


_yes_no_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=_YES), KeyboardButton(text=_NO)], [KeyboardButton(text=_BACK)]],
    resize_keyboard=True,
)

_preview_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=_CONFIRM), KeyboardButton(text=_EDIT)], [KeyboardButton(text=_BACK)]],
    resize_keyboard=True,
)


def _parse_choice(text: str, count: int):
    """«۲» / «2» / «۲. ...» → ایندکس صفر-مبنا، یا None."""
    t = _to_en(text).strip()
    digits = ""
    for ch in t:
        if ch.isdigit():
            digits += ch
        else:
            break
    if not digits:
        return None
    n = int(digits)
    return n - 1 if 1 <= n <= count else None


def _parse_number(text: str, *, integer=False, allow_negative=False, min_value=None, max_value=None):
    t = _to_en(text).strip().replace(",", "").replace("٬", "").replace("٫", ".").replace(" ", "")
    t = t.replace("−", "-").replace("–", "-").replace("‎", "").replace("‏", "")
    # «۱-» (منفی نوشته‌شده در سمت راست) هم پذیرفته می‌شود
    if t.endswith("-") and t.count("-") == 1:
        t = "-" + t[:-1]
    try:
        v = int(t) if integer else float(t)
    except (ValueError, TypeError):
        return None
    if not allow_negative and v < 0:
        return None
    if min_value is not None and v < min_value:
        return None
    if max_value is not None and v > max_value:
        return None
    return v


def _numbered(options: list) -> str:
    return "\n".join(f"{_to_fa(i)}. {o}" for i, o in enumerate(options, 1))


def _floor_applies(d: dict) -> bool:
    """سؤال طبقه فقط برای مسکونی/تجاری/اداریِ تکمیل‌شده (نه صنعتی/کشاورزی)."""
    return d.get("rv_bld_complete") is True and d.get("rv_bld_use") in ayani_calc.BUILDING_MAIN_KEYS


# (نام مرحله، کلیدهای داده، شرط لازم‌بودن) — ترتیب = ترتیب پرسش
_STEPS = [
    ("province", ["rv_province"], lambda d: True),
    ("address", ["rv_address", "rv_lat", "rv_lng"], lambda d: True),
    ("area", ["rv_area"], lambda d: True),
    ("land_use", ["rv_land_use"], lambda d: True),
    ("land_other", ["rv_land_other_idx"], lambda d: d.get("rv_land_use") == "سایر"),
    ("bld_use", ["rv_bld_use", "rv_bld_use_other_pending"], lambda d: True),
    ("bld_structure", ["rv_bld_structure"], lambda d: True),
    ("bld_area", ["rv_bld_area"], lambda d: True),
    ("bld_complete", ["rv_bld_complete"], lambda d: True),
    ("bld_stage", ["rv_bld_stage"], lambda d: d.get("rv_bld_complete") is False),
    ("bld_parking", ["rv_bld_has_parking"], lambda d: d.get("rv_bld_complete") is True),
    ("bld_parking_area", ["rv_bld_parking_area"], lambda d: d.get("rv_bld_has_parking") is True),
    ("bld_floor", ["rv_bld_floor"], _floor_applies),
    ("bld_age", ["rv_bld_age"], lambda d: d.get("rv_bld_complete") is True),
]
_STEP_INDEX = {name: i for i, (name, _, _) in enumerate(_STEPS)}
_ALL_KEYS = [k for _, keys, _ in _STEPS for k in keys]

# فیلدهای قابل ویرایش در پیش‌نمایش: (عنوان، مراحلی که پاک و دوباره پرسیده می‌شوند، شرط نمایش)
_EDIT_FIELDS = [
    ("استان", ["province", "address"], lambda d: True),
    ("آدرس / موقعیت روی نقشه", ["address"], lambda d: True),
    ("متراژ عرصه", ["area"], lambda d: True),
    ("کاربری زمین", ["land_use", "land_other"], lambda d: True),
    ("کاربری اعیانی", ["bld_use"], lambda d: True),
    ("نوع سازه", ["bld_structure"], lambda d: True),
    ("متراژ اعیانی", ["bld_area"], lambda d: True),
    ("وضعیت تکمیل ساختمان", ["bld_complete", "bld_stage", "bld_parking", "bld_parking_area",
                              "bld_floor", "bld_age"], lambda d: True),
    ("مرحلهٔ ساخت", ["bld_stage"], lambda d: d.get("rv_bld_complete") is False),
    ("پارکینگ و انباری", ["bld_parking", "bld_parking_area"], lambda d: d.get("rv_bld_complete") is True),
    ("طبقه", ["bld_floor"], _floor_applies),
    ("قدمت ساختمان", ["bld_age"], lambda d: d.get("rv_bld_complete") is True),
]


def _step_keys(names) -> dict:
    out = {}
    for n in names:
        for k in _STEPS[_STEP_INDEX[n]][1]:
            out[k] = None
    return out


def _first_missing(d: dict):
    for name, keys, required in _STEPS:
        if required(d) and d.get(keys[0]) is None:
            return name
    return None


async def _advance(message: Message, state: FSMContext):
    """اولین مرحلهٔ لازمِ بی‌پاسخ را بپرس؛ اگر همه کامل است → پیش‌نمایش."""
    d = await state.get_data()
    step = _first_missing(d)
    if step is None:
        await state.update_data(rv_edit_snapshot=None)
        await _show_preview(message, state)
        return
    await _ASK[step](message, state)


async def _go_back(message: Message, state: FSMContext, current: str):
    """
    بازگشت از مرحلهٔ فعلی به مرحلهٔ لازمِ قبلی؛ دادهٔ آن مرحله و همهٔ
    مراحل بعد از آن پاک می‌شود. در حالت ویرایش = انصراف و برگشت به پیش‌نمایش.
    """
    d = await state.get_data()
    snapshot = d.get("rv_edit_snapshot")
    if snapshot:
        await state.update_data(**snapshot, rv_edit_snapshot=None)
        await _show_preview(message, state)
        return

    idx = _STEP_INDEX[current]
    prev = None
    for i in range(idx - 1, -1, -1):
        name, _, required = _STEPS[i]
        if required(d):
            prev = i
            break
    if prev is None:
        await state.update_data(**{k: None for k in _ALL_KEYS})
        await message.answer(
            "لطفاً نحوه ثبت درخواست خود را انتخاب فرمایید:",
            reply_markup=get_main_menu_kb(message.from_user.id),
        )
        await state.set_state(Form.waiting_for_flow_type)
        return
    await state.update_data(**_step_keys([n for n, _, _ in _STEPS[prev:]]))
    await _advance(message, state)


# ══════════════════════════════════════════════════════════════════
# نقطه ورود — از handlers.py فراخوانی می‌شود
# ══════════════════════════════════════════════════════════════════
async def regional_value_entry(message: Message, state: FSMContext):
    """شروع فرآیند استعلام ارزش منطقه‌ای (همهٔ داده‌های قبلی این بخش پاک می‌شود)."""
    await state.update_data(**{k: None for k in _ALL_KEYS}, rv_edit_snapshot=None,
                            rv_panel_case_id=None)
    await _advance(message, state)


# ══════════════════════════════════════════════════════════════════
# مرحله ۱: انتخاب استان
# ══════════════════════════════════════════════════════════════════
async def _ask_province(message: Message, state: FSMContext):
    provinces = get_province_list()
    rows = []
    for i in range(0, len(provinces), 3):
        rows.append([KeyboardButton(text=p) for p in provinces[i:i + 3]])
    rows.append([KeyboardButton(text=_BACK)])
    kb = ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)
    await message.answer(
        "🗺️ *استعلام ارزش منطقه‌ای ملک*\n\n"
        "لطفاً استان مربوطه را انتخاب کنید:",
        reply_markup=kb,
    )
    await state.set_state(Form.rv_waiting_province)


@regional_value_router.message(Form.rv_waiting_province)
async def process_province(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == _BACK:
        await _go_back(message, state, "province")
        return
    selected = message.text.strip()
    if selected not in get_province_list():
        await message.answer("⚠️ لطفاً یکی از استان‌های لیست را انتخاب کنید.")
        return
    await state.update_data(rv_province=selected)
    await _advance(message, state)


# ══════════════════════════════════════════════════════════════════
# مرحله ۲: ورود آدرس (متنی یا موقعیت مکانی روی نقشه)
# ══════════════════════════════════════════════════════════════════
async def _ask_address(message: Message, state: FSMContext):
    d = await state.get_data()
    await message.answer(
        f"✅ استان: *{d.get('rv_province', '')}*\n\n"
        f"📍 لطفاً آدرس دقیق را با ذکر نام شهر تایپ کنید،\n"
        f"یا با دکمهٔ زیر، نقطهٔ مورد نظر را روی نقشه انتخاب و ارسال کنید:\n"
        f"(مثال: تهران، خیابان ولیعصر، نرسیده به میدان ونک)",
        reply_markup=address_or_location_kb,
    )
    await state.set_state(Form.rv_waiting_address)


@regional_value_router.message(Form.rv_waiting_address, F.content_type == "text")
async def process_address(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == _BACK:
        await _go_back(message, state, "address")
        return
    address = message.text.strip()
    if len(address) < 5:
        await message.answer("⚠️ آدرس بسیار کوتاه است. لطفاً آدرس دقیق‌تری وارد کنید.")
        return
    await state.update_data(rv_address=address, rv_lat=None, rv_lng=None)
    await message.answer("✅ آدرس ثبت شد.")
    await _advance(message, state)


@regional_value_router.message(Form.rv_waiting_address, F.content_type == "location")
async def process_address_location(message: Message, state: FSMContext):
    """کاربر به‌جای تایپ آدرس، نقطه‌ای را روی نقشه انتخاب و ارسال کرده است."""
    loc = message.location
    lat, lng = loc.latitude, loc.longitude

    # آدرس‌خوانی معکوس فقط برای نمایش در گزارش/پیام‌ها — اگر شکست بخورد
    # مشکلی نیست، چون خودِ استعلام مستقیماً روی مختصات انجام می‌شود.
    try:
        from geocode_and_query import reverse_geocode
        display_address = reverse_geocode(lat, lng)
    except Exception:
        display_address = None
    if not display_address:
        display_address = f"مختصات انتخاب‌شده روی نقشه ({lat:.6f}, {lng:.6f})"

    await state.update_data(rv_address=display_address, rv_lat=lat, rv_lng=lng)
    await message.answer(f"✅ موقعیت مکانی دریافت شد.\n📍 {display_address}")
    await _advance(message, state)


# ══════════════════════════════════════════════════════════════════
# مرحله ۳: متراژ عرصه
# ══════════════════════════════════════════════════════════════════
async def _ask_area(message: Message, state: FSMContext):
    await message.answer(
        "📐 لطفاً متراژ دقیق عرصه را به متر مربع وارد کنید:\n(مثال: 250)",
        reply_markup=back_only_kb,
    )
    await state.set_state(Form.rv_waiting_area)


@regional_value_router.message(Form.rv_waiting_area)
async def process_area(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == _BACK:
        await _go_back(message, state, "area")
        return
    area = _parse_number(message.text, min_value=0.01, max_value=1_000_000)
    if area is None:
        await message.answer("⚠️ متراژ نامعتبر است. لطفاً یک عدد مثبت (متر مربع) وارد کنید.")
        return
    d = await state.get_data()
    bld_area = d.get("rv_bld_area")
    if bld_area is not None and bld_area > area:
        # (در حالت ویرایش) عرصهٔ جدید از اعیانیِ قبلی کوچک‌تر است → اعیانی دوباره پرسیده می‌شود
        await message.answer(
            f"ℹ️ متراژ اعیانی قبلی ({bld_area:,.0f} متر مربع) از عرصهٔ جدید بیشتر است؛ "
            f"لطفاً متراژ اعیانی را دوباره وارد کنید."
        )
        await state.update_data(rv_area=area, rv_bld_area=None)
    else:
        await state.update_data(rv_area=area)
    await _advance(message, state)


# ══════════════════════════════════════════════════════════════════
# مرحله ۴: کاربری زمین (عرصه) + زیرگزینه‌های «سایر» (ضریب تعدیل)
# ══════════════════════════════════════════════════════════════════
LAND_USE_KEY_MAP = {
    "۱. مسکونی": "مسکونی", "مسکونی": "مسکونی",
    "۲. تجاری": "تجاری", "تجاری": "تجاری",
    "۳. اداری": "اداری", "اداری": "اداری",
    "۴. سایر": "سایر", "سایر": "سایر",
}


async def _ask_land_use(message: Message, state: FSMContext):
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="۱. مسکونی"), KeyboardButton(text="۲. تجاری")],
        [KeyboardButton(text="۳. اداری"), KeyboardButton(text="۴. سایر")],
        [KeyboardButton(text=_BACK)],
    ], resize_keyboard=True)
    await message.answer("🏢 لطفاً کاربری زمین را انتخاب کنید:", reply_markup=kb)
    await state.set_state(Form.rv_waiting_land_use)


@regional_value_router.message(Form.rv_waiting_land_use)
async def process_land_use(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == _BACK:
        await _go_back(message, state, "land_use")
        return
    land_use = LAND_USE_KEY_MAP.get(message.text.strip())
    if not land_use:
        idx = _parse_choice(message.text, 4)
        land_use = ["مسکونی", "تجاری", "اداری", "سایر"][idx] if idx is not None else None
    if not land_use:
        await message.answer("⚠️ لطفاً یکی از گزینه‌های کاربری را انتخاب کنید.")
        return
    await state.update_data(rv_land_use=land_use, rv_land_other_idx=None)
    await _advance(message, state)


async def _ask_land_other(message: Message, state: FSMContext):
    await message.answer(
        "📋 نوع کاربری زمین را انتخاب کنید:\n\n"
        f"{_numbered([o['title'] for o in ayani_calc.LAND_OTHER_OPTIONS])}\n\n"
        "👇 شمارهٔ گزینهٔ مورد نظر را از دکمه‌های زیر انتخاب کنید:",
        reply_markup=_num_kb(len(ayani_calc.LAND_OTHER_OPTIONS)),
    )
    await state.set_state(Form.rv_waiting_land_other)


@regional_value_router.message(Form.rv_waiting_land_other)
async def process_land_other(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == _BACK:
        await _go_back(message, state, "land_other")
        return
    idx = _parse_choice(message.text, len(ayani_calc.LAND_OTHER_OPTIONS))
    if idx is None:
        await message.answer("⚠️ لطفاً فقط یکی از شماره‌های ۱ تا ۵ را انتخاب کنید.")
        return
    await state.update_data(rv_land_other_idx=idx)
    await _advance(message, state)


# ══════════════════════════════════════════════════════════════════
# مرحله ۵: اعیانی — کاربری، نوع سازه، متراژ، وضعیت ساخت، پارکینگ، طبقه، قدمت
# ══════════════════════════════════════════════════════════════════
_BLD_MAIN = [("۱. مسکونی", "residential"), ("۲. تجاری", "commercial"),
             ("۳. اداری", "administrative"), ("۴. سایر", None)]


async def _ask_bld_use(message: Message, state: FSMContext):
    d = await state.get_data()
    if d.get("rv_bld_use_other_pending"):
        titles = [ayani_calc.BUILDING_USES[k] for k in ayani_calc.BUILDING_OTHER_KEYS]
        await message.answer(
            "📋 کاربری ساختمان را انتخاب کنید:\n\n"
            f"{_numbered(titles)}\n\n"
            "👇 شمارهٔ گزینهٔ مورد نظر را از دکمه‌های زیر انتخاب کنید:",
            reply_markup=_num_kb(len(titles)),
        )
        await state.set_state(Form.rv_waiting_bld_use_other)
        return
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=_BLD_MAIN[0][0]), KeyboardButton(text=_BLD_MAIN[1][0])],
        [KeyboardButton(text=_BLD_MAIN[2][0]), KeyboardButton(text=_BLD_MAIN[3][0])],
        [KeyboardButton(text=_BACK)],
    ], resize_keyboard=True)
    await message.answer("🏗 *اعیانی*\n\nکاربری ساختمان (اعیانی) را انتخاب کنید:", reply_markup=kb)
    await state.set_state(Form.rv_waiting_bld_use)


@regional_value_router.message(Form.rv_waiting_bld_use)
async def process_bld_use(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == _BACK:
        await _go_back(message, state, "bld_use")
        return
    idx = _parse_choice(message.text, len(_BLD_MAIN))
    if idx is None:
        by_title = {t.split(". ", 1)[1]: i for i, (t, _) in enumerate(_BLD_MAIN)}
        idx = by_title.get(message.text.strip())
    if idx is None:
        await message.answer("⚠️ لطفاً یکی از گزینه‌های کاربری را انتخاب کنید.")
        return
    use_key = _BLD_MAIN[idx][1]
    if use_key is None:
        await state.update_data(rv_bld_use=None, rv_bld_use_other_pending=True)
    else:
        await state.update_data(rv_bld_use=use_key, rv_bld_use_other_pending=None)
    await _advance(message, state)


@regional_value_router.message(Form.rv_waiting_bld_use_other)
async def process_bld_use_other(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == _BACK:
        d = await state.get_data()
        if d.get("rv_edit_snapshot"):
            await _go_back(message, state, "bld_use")
            return
        # بازگشت به منوی اصلی کاربری اعیانی (انتخاب «سایر» پاک می‌شود)
        await state.update_data(rv_bld_use=None, rv_bld_use_other_pending=None)
        await _advance(message, state)
        return
    idx = _parse_choice(message.text, len(ayani_calc.BUILDING_OTHER_KEYS))
    if idx is None:
        await message.answer("⚠️ لطفاً فقط شمارهٔ ۱ یا ۲ را انتخاب کنید.")
        return
    await state.update_data(rv_bld_use=ayani_calc.BUILDING_OTHER_KEYS[idx], rv_bld_use_other_pending=None)
    await _advance(message, state)


async def _ask_structure(message: Message, state: FSMContext):
    await message.answer(
        "🧱 نوع سازه را انتخاب کنید:\n\n"
        f"{_numbered([ayani_calc.STRUCTURES['concrete'], ayani_calc.STRUCTURES['other']])}",
        reply_markup=_num_kb(2),
    )
    await state.set_state(Form.rv_waiting_bld_structure)


@regional_value_router.message(Form.rv_waiting_bld_structure)
async def process_bld_structure(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == _BACK:
        await _go_back(message, state, "bld_structure")
        return
    idx = _parse_choice(message.text, 2)
    if idx is None:
        await message.answer("⚠️ لطفاً فقط شمارهٔ ۱ یا ۲ را انتخاب کنید.")
        return
    await state.update_data(rv_bld_structure=["concrete", "other"][idx])
    await _advance(message, state)


async def _ask_bld_area(message: Message, state: FSMContext):
    await message.answer(
        "📐 لطفاً متراژ اعیانی (زیربنا) را به متر مربع وارد کنید:\n"
        "(حداکثر برابر متراژ عرصه — مثال: 120)",
        reply_markup=back_only_kb,
    )
    await state.set_state(Form.rv_waiting_bld_area)


@regional_value_router.message(Form.rv_waiting_bld_area)
async def process_bld_area(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == _BACK:
        await _go_back(message, state, "bld_area")
        return
    area = _parse_number(message.text, min_value=0.01, max_value=1_000_000)
    if area is None:
        await message.answer("⚠️ متراژ نامعتبر است. لطفاً یک عدد مثبت (متر مربع) وارد کنید.")
        return
    land_area = (await state.get_data()).get("rv_area")
    if land_area is not None and area > land_area:
        await message.answer(
            f"⚠️ متراژ اعیانی نمی‌تواند از متراژ عرصه ({land_area:,.0f} متر مربع) بیشتر باشد.\n"
            f"لطفاً متراژ اعیانی را دوباره وارد کنید."
        )
        return
    await state.update_data(rv_bld_area=area)
    await _advance(message, state)


async def _ask_complete(message: Message, state: FSMContext):
    await message.answer("🏠 آیا ساختمان تکمیل شده است؟", reply_markup=_yes_no_kb)
    await state.set_state(Form.rv_waiting_bld_complete)


@regional_value_router.message(Form.rv_waiting_bld_complete)
async def process_bld_complete(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == _BACK:
        await _go_back(message, state, "bld_complete")
        return
    if message.text in (_YES, "بله"):
        await state.update_data(rv_bld_complete=True, rv_bld_stage=None)
    elif message.text in (_NO, "خیر"):
        await state.update_data(rv_bld_complete=False, rv_bld_has_parking=None,
                                rv_bld_parking_area=None, rv_bld_floor=None, rv_bld_age=None)
    else:
        await message.answer("⚠️ لطفاً «بله» یا «خیر» را انتخاب کنید.")
        return
    await _advance(message, state)


async def _ask_stage(message: Message, state: FSMContext):
    titles = [s["title"] for s in ayani_calc.CONSTRUCTION_STAGES]
    await message.answer(
        "🚧 ساختمان در کدام مرحله از ساخت قرار دارد؟\n\n"
        f"{_numbered(titles)}",
        reply_markup=_num_kb(len(titles), per_row=4),
    )
    await state.set_state(Form.rv_waiting_bld_stage)


@regional_value_router.message(Form.rv_waiting_bld_stage)
async def process_bld_stage(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == _BACK:
        await _go_back(message, state, "bld_stage")
        return
    idx = _parse_choice(message.text, len(ayani_calc.CONSTRUCTION_STAGES))
    if idx is None:
        await message.answer("⚠️ لطفاً فقط یکی از شماره‌های ۱ تا ۴ را انتخاب کنید.")
        return
    await state.update_data(rv_bld_stage=ayani_calc.CONSTRUCTION_STAGES[idx]["key"])
    await _advance(message, state)


async def _ask_parking(message: Message, state: FSMContext):
    await message.answer(
        "🚗 آیا پارکینگ و انباری متعلق به هر واحد ساختمانی نسبت به ملک موجود می‌باشد؟",
        reply_markup=_yes_no_kb,
    )
    await state.set_state(Form.rv_waiting_bld_parking)


@regional_value_router.message(Form.rv_waiting_bld_parking)
async def process_bld_parking(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == _BACK:
        await _go_back(message, state, "bld_parking")
        return
    if message.text in (_YES, "بله"):
        await state.update_data(rv_bld_has_parking=True, rv_bld_parking_area=None)
    elif message.text in (_NO, "خیر"):
        await state.update_data(rv_bld_has_parking=False, rv_bld_parking_area=None)
    else:
        await message.answer("⚠️ لطفاً «بله» یا «خیر» را انتخاب کنید.")
        return
    await _advance(message, state)


async def _ask_parking_area(message: Message, state: FSMContext):
    await message.answer(
        "📐 متراژ پارکینگ و انباری را به متر مربع وارد کنید:\n(مجموع هر دو — مثال: 18)",
        reply_markup=back_only_kb,
    )
    await state.set_state(Form.rv_waiting_bld_parking_area)


@regional_value_router.message(Form.rv_waiting_bld_parking_area)
async def process_bld_parking_area(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == _BACK:
        await _go_back(message, state, "bld_parking_area")
        return
    p_area = _parse_number(message.text, min_value=0.01, max_value=1_000_000)
    if p_area is None:
        await message.answer("⚠️ متراژ نامعتبر است. لطفاً یک عدد مثبت (متر مربع) وارد کنید.")
        return
    await state.update_data(rv_bld_parking_area=p_area)
    await _advance(message, state)


async def _ask_floor(message: Message, state: FSMContext):
    await message.answer(
        "🏢 طبقهٔ واحد را وارد کنید (فقط عدد):\n\n"
        "• همکف = ۰\n"
        "• اگر طبقه زیر همکف می‌باشد، نماد منفی (-) را کنار عدد قرار دهید؛ مثلاً ‎-1\n"
        "(طبقات بدون احتساب زیرزمین و پیلوت شمرده می‌شوند)",
        reply_markup=back_only_kb,
    )
    await state.set_state(Form.rv_waiting_bld_floor)


@regional_value_router.message(Form.rv_waiting_bld_floor)
async def process_bld_floor(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == _BACK:
        await _go_back(message, state, "bld_floor")
        return
    floor = _parse_number(message.text, integer=True, allow_negative=True, min_value=-10, max_value=200)
    if floor is None:
        await message.answer("⚠️ لطفاً فقط یک عدد صحیح وارد کنید (مثلاً ۳، ۰ یا ‎-1).")
        return
    await state.update_data(rv_bld_floor=floor)
    await _advance(message, state)


async def _ask_age(message: Message, state: FSMContext):
    await message.answer("📅 قدمت ساختمان چند سال است؟ (فقط عدد — مثلاً ۵)", reply_markup=back_only_kb)
    await state.set_state(Form.rv_waiting_bld_age)


@regional_value_router.message(Form.rv_waiting_bld_age)
async def process_bld_age(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == _BACK:
        await _go_back(message, state, "bld_age")
        return
    age = _parse_number(message.text, integer=True, min_value=0, max_value=300)
    if age is None:
        await message.answer("⚠️ لطفاً فقط یک عدد صحیح وارد کنید (مثلاً ۰ برای نوساز).")
        return
    await state.update_data(rv_bld_age=age)
    await _advance(message, state)


_ASK = {
    "province": _ask_province, "address": _ask_address, "area": _ask_area,
    "land_use": _ask_land_use, "land_other": _ask_land_other,
    "bld_use": _ask_bld_use, "bld_structure": _ask_structure, "bld_area": _ask_bld_area,
    "bld_complete": _ask_complete, "bld_stage": _ask_stage, "bld_parking": _ask_parking,
    "bld_parking_area": _ask_parking_area, "bld_floor": _ask_floor, "bld_age": _ask_age,
}


# ══════════════════════════════════════════════════════════════════
# مرحله ۶: پیش‌نمایش (تایید / ویرایش)
# ══════════════════════════════════════════════════════════════════
def _floor_text(f) -> str:
    if f is None:
        return "-"
    return "همکف" if f == 0 else (f"زیرزمین {abs(f)} (‎{f})" if f < 0 else str(f))


def _inputs_summary(data: dict) -> str:
    """خلاصهٔ ورودی‌های کاربر (پیش‌نمایش و پیام ادمین)."""
    land_use = data.get("rv_land_use") or "-"
    if land_use == "سایر" and data.get("rv_land_other_idx") is not None:
        land_use = f"سایر — {ayani_calc.LAND_OTHER_OPTIONS[data['rv_land_other_idx']]['title']}"
    use_key = data.get("rv_bld_use")
    lines = [
        f"📍 استان: {data.get('rv_province') or '-'}",
        f"🗺 آدرس: {data.get('rv_address') or '-'}",
        f"📐 متراژ عرصه: {(data.get('rv_area') or 0):,.0f} متر مربع",
        f"🏢 کاربری زمین: {land_use}",
        f"🏗 کاربری اعیانی: {ayani_calc.BUILDING_USES.get(use_key, '-')}",
        f"🧱 نوع سازه: {ayani_calc.STRUCTURES.get(data.get('rv_bld_structure'), '-')}",
        f"📐 متراژ اعیانی: {(data.get('rv_bld_area') or 0):,.0f} متر مربع",
    ]
    if data.get("rv_bld_complete"):
        p = data.get("rv_bld_parking_area") or 0
        lines.append("✅ وضعیت ساختمان: تکمیل‌شده")
        lines.append(f"🚗 پارکینگ و انباری: {p:,.0f} متر مربع" if p else "🚗 پارکینگ و انباری: ندارد")
        if _floor_applies(data):
            lines.append(f"🏢 طبقه: {_floor_text(data.get('rv_bld_floor'))}")
        lines.append(f"📅 قدمت: {data.get('rv_bld_age') or 0} سال")
    else:
        stage = next((s["title"] for s in ayani_calc.CONSTRUCTION_STAGES
                      if s["key"] == data.get("rv_bld_stage")), "-")
        lines.append(f"🚧 وضعیت ساختمان: ناتمام — مرحلهٔ {stage}")
    return "\n".join(lines)


async def _show_preview(message: Message, state: FSMContext):
    d = await state.get_data()
    await message.answer(
        "📝 *پیش‌نمایش اطلاعات ملک*\n\n"
        f"{_inputs_summary(d)}\n\n"
        "در صورت صحت اطلاعات «تایید و پرداخت» و در غیر این صورت «ویرایش» را بزنید.",
        reply_markup=_preview_kb,
    )
    await state.set_state(Form.rv_waiting_preview)


@regional_value_router.message(Form.rv_waiting_preview)
async def process_preview(message: Message, state: FSMContext, bot: Bot):
    if not message.text:
        return
    if message.text == _BACK:
        # بازگشت از پیش‌نمایش = بازگشت به آخرین مرحله (دادهٔ آن پاک می‌شود)
        d = await state.get_data()
        last = [n for n, keys, req in _STEPS if req(d)][-1]
        await state.update_data(**_step_keys([last]))
        await _advance(message, state)
        return
    if message.text == _CONFIRM:
        await _rv_start_payment(message, state, bot)
        return
    if message.text == _EDIT:
        await _ask_edit_choice(message, state)
        return
    await message.answer("⚠️ لطفاً یکی از گزینه‌های «تایید و پرداخت» یا «ویرایش» را انتخاب کنید.")


def _edit_options(d: dict) -> list:
    return [(title, steps) for title, steps, cond in _EDIT_FIELDS if cond(d)]


async def _ask_edit_choice(message: Message, state: FSMContext):
    d = await state.get_data()
    opts = _edit_options(d)
    await message.answer(
        "✏️ کدام مورد را می‌خواهید ویرایش کنید؟\n\n"
        f"{_numbered([t for t, _ in opts])}",
        reply_markup=_num_kb(len(opts), per_row=4),
    )
    await state.set_state(Form.rv_waiting_edit_choice)


@regional_value_router.message(Form.rv_waiting_edit_choice)
async def process_edit_choice(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == _BACK:
        await _show_preview(message, state)
        return
    d = await state.get_data()
    opts = _edit_options(d)
    idx = _parse_choice(message.text, len(opts))
    if idx is None:
        await message.answer("⚠️ لطفاً شمارهٔ یکی از موارد را انتخاب کنید.")
        return
    snapshot = {k: d.get(k) for k in _ALL_KEYS}
    await state.update_data(**_step_keys(opts[idx][1]), rv_edit_snapshot=snapshot)
    await _advance(message, state)


# ══════════════════════════════════════════════════════════════════
# مرحله ۷: ثبت پرونده + فاکتور پرداخت (پس از تایید پیش‌نمایش)
# ══════════════════════════════════════════════════════════════════
async def _rv_start_payment(message: Message, state: FSMContext, bot: Bot):

    # ── ثبت پرونده در پنل ادمین (از همون ابتدا، قبل از پرداخت) ──
    # wait=True: به case_id برگشتی برای آپدیت‌های بعدی نیاز داریم —
    # (این تنها نقطه‌ای است که منتظر پنل می‌مانیم؛ بقیه عملیات پنل پس‌زمینه است)
    data_so_far = await state.get_data()
    # ⭐ رفع باگ: هزینه/cost پرونده‌هایی که با آیدی ادمین ثبت می‌شوند باید
    # همیشه صفر باشد — قبلاً fee همیشه با REGIONAL_VALUE_FEE ثبت می‌شد و فقط
    # feeStatus بعداً روی MANUAL_APPROVED تنظیم می‌شد (نه خودِ مبلغ fee)، پس
    # هزینه‌ی غیرصفر برای ادمین در پنل باقی می‌ماند. از exempt_users.is_exempt_user
    # استفاده می‌شود تا هر سه منبع معافیت (ADMIN_ID، لیست هاردکد، جدول
    # ExemptUser پنل) یکسان اعمال شوند — نه فقط مقایسه‌ی مستقیم ADMIN_ID.
    is_exempt = await is_exempt_user(message.from_user.id)
    try:
        case = await register_case_to_panel(
            bale_user_id=message.from_user.id,
            full_name=message.from_user.full_name,
            service_type="REGIONAL_VALUE",
            status="PENDING_PAYMENT",
            document_category="ارزش منطقه‌ای",
            province=data_so_far.get("rv_province", ""),
            fee=0 if is_exempt else REGIONAL_VALUE_FEE,
            fee_status="MANUAL_APPROVED" if is_exempt else "UNPAID",
            wait=True,
        )
        panel_case_id = case.get("id") if case else None
        if panel_case_id:
            await state.update_data(rv_panel_case_id=panel_case_id)
    except Exception as panel_err:
        logger.warning(f"[RV] خطا در ثبت اولیه پرونده در پنل: {panel_err}")

    # ═══ معافیت ادمین/کاربران معاف از پرداخت ═══
    if is_exempt:
        await message.answer(
            "✅ *معافیت از پرداخت (ادمین)*\n\n"
            "در حال استعلام ارزش منطقه‌ای...",
            reply_markup=ReplyKeyboardRemove(),
        )
        await state.set_state(Form.rv_waiting_payment)
        await regional_value_successful_payment(message, state, bot)
        return

    # ═══ ارسال فاکتور پرداخت ═══
    fee_rial = REGIONAL_VALUE_FEE * 10  # تومان به ریال

    try:
        import json as _json
        invoice_payload = _json.dumps({"type": "regional_value", "uid": message.from_user.id})
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
            invoice_url = f"{BALE_API_BASE}/bot{BOT_TOKEN}/sendInvoice"
            invoice_data = {
                "chat_id": message.from_user.id,
                "title": "فاکتور استعلام ارزش منطقه‌ای",
                "description": f"استعلام ارزش منطقه‌ای: {REGIONAL_VALUE_FEE:,} تومان ({fee_rial:,} ریال)",
                "payload": invoice_payload,
                "provider_token": BALE_WALLET_TOKEN,
                "currency": "IRR",
                "prices": [{"label": "استعلام ارزش منطقه‌ای", "amount": fee_rial}],
            }
            logging.info(f"[RV-PAY] ارسال sendInvoice به chat_id={message.from_user.id}, مبلغ={fee_rial:,} ریال")
            async with session.post(invoice_url, json=invoice_data) as resp:
                result = await resp.json()
                logging.info(f"[RV-PAY] پاسخ sendInvoice: {result}")
                if not result.get("ok"):
                    logging.error(f"[RV-PAY] خطای sendInvoice: {result}")
                    raise Exception(result.get("description", "خطا در ارسال فاکتور"))
    except Exception as e:
        logging.error(f"[RV-PAY] خطا در ارسال فاکتور: {e}", exc_info=True)
        await message.answer("⚠️ خطا در ساخت فاکتور. لطفاً کمی بعد دوباره تلاش کنید.")
        return

    # ⭐ طبق دستور کارفرما: بعد از ارسال فاکتور هیچ منویی برای کاربر
    # نمایش داده نمی‌شود — کیبورد صفحه حذف می‌شود و فقط یک گزینهٔ
    # «انصراف» می‌ماند که کاربر را به منوی اصلی برمی‌گرداند.
    await message.answer(
        "⏳ فاکتور پرداخت ارسال شد.\n"
        "پس از پرداخت موفق در کیف پول بله، استعلام ارزش منطقه‌ای به‌صورت *کاملاً خودکار* پردازش و ارسال می‌شود "
        "و نیازی به تایید دستی نیست.",
        reply_markup=ReplyKeyboardRemove(),
    )

    pay_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ انصراف", callback_data="pay_cancel")],
    ])
    await message.answer(
        "در صورت انصراف از پرداخت، دکمهٔ زیر را بزنید:",
        reply_markup=pay_kb,
    )
    await state.set_state(Form.rv_waiting_payment)


# ══════════════════════════════════════════════════════════════════
# مرحله ۵-الف: پیام‌های متنی در انتظار پرداخت — یادآوری پرداخت/انصراف
# ══════════════════════════════════════════════════════════════════
@regional_value_router.message(Form.rv_waiting_payment)
async def rv_payment_waiting_message(message: Message):
    """در حال انتظار پرداخت — تشخیص خودکار توسط بله (successful_payment)."""
    await message.answer(
        "⏳ لطفاً فاکتور ارسال‌شده را در همین چت پرداخت کنید.\n"
        "پس از پرداخت موفق، استعلام به‌صورت خودکار انجام می‌شود.\n"
        "برای انصراف، دکمهٔ *«❌ انصراف»* زیر فاکتور را بزنید.")


# ══════════════════════════════════════════════════════════════════
# مرحله ۵: پرداخت موفق — استعلام + تولید PDF + ارسال
# ══════════════════════════════════════════════════════════════════
async def regional_value_successful_payment(message: Message, state: FSMContext, bot: Bot):
    """پردازش پس از پرداخت موفق: استعلام + PDF + ارسال به کاربر."""
    user_id = message.from_user.id
    data = await state.get_data()

    province = data.get("rv_province", "")
    address = data.get("rv_address", "")
    rv_lat = data.get("rv_lat")
    rv_lng = data.get("rv_lng")
    area = data.get("rv_area", 0)
    land_use = data.get("rv_land_use", "مسکونی")
    panel_case_id = data.get("rv_panel_case_id")
    is_admin_exempt_early = await is_exempt_user(user_id)

    try:
        # ⭐ همراه با feeStatus، خودِ fee هم صفر می‌شود تا هزینه‌ی نمایش‌داده‌شده
        # در پنل برای پرونده‌های ثبت‌شده با آیدی ادمین همیشه صفر بماند.
        await update_case_in_panel(
            panel_case_id,
            status="PROCESSING",
            feeStatus="MANUAL_APPROVED" if is_admin_exempt_early else "PAID",
            fee=0 if is_admin_exempt_early else REGIONAL_VALUE_FEE,
        )
    except Exception as panel_err:
        logger.warning(f"[RV] خطا در آپدیت پرداخت پرونده در پنل: {panel_err}")

    await message.answer("⏳ در حال استعلام ارزش منطقه‌ای... لطفاً چند لحظه صبر کنید.")

    try:
        # ── اجرای پایپ‌لاین استعلام (در thread جدا) ──
        loop = asyncio.get_running_loop()

        def _do_query():
            if rv_lat is not None and rv_lng is not None:
                # کاربر موقعیت را مستقیماً روی نقشه انتخاب کرده — Geocoding
                # نشان کاملاً حذف می‌شود و استعلام روی همان مختصات انجام می‌شود.
                from geocode_and_query import query_by_coordinates
                return query_by_coordinates(rv_lat, rv_lng, province_hint=province)
            from geocode_and_query import full_pipeline
            return full_pipeline(address=address, province_hint=province)

        result = await loop.run_in_executor(None, _do_query)

        # tax_info حالا دیکشنری ساختاریافته است:
        # {"سال": "1405", "فیلدهای_ساختاریافته": {...}, "همه_فیلدهای_خام_صفحه": {...}, "فیلدهای_پیدا_نشده": [...]}
        tax_result = result.get("tax_info", {})

        if not tax_result.get("فیلدهای_ساختاریافته"):
            await message.answer(
                "⚠️ متاسفانه نتیجه‌ای از سامانه مالیاتی دریافت نشد.\n\n"
                "ممکن است آدرس دقیق نباشد یا مختصات خارج از محدوده تعریف‌شده باشد.\n"
                "لطفاً از ابتدا تلاش کنید.",
                reply_markup=get_main_menu_kb(user_id),
            )
            try:
                await update_case_in_panel(
                    panel_case_id, status="FAILED",
                    errorDetails="نتیجه‌ای از سامانه مالیاتی دریافت نشد",
                    errorStep="tax_query",
                )
            except Exception as panel_err:
                logger.warning(f"[RV] خطا در آپدیت شکست پرونده در پنل: {panel_err}")
            await state.clear()
            return

        # ── استخراج هر ۳ ارزش معاملاتی ──
        all_lu_values = extract_all_land_use_values(tax_result)

        # ── بررسی: آیا اصلاً هیچ ارزشی ثبت نشده؟ ──
        any_value_found = any(v is not None for v in all_lu_values.values())

        if not any_value_found:
            await message.answer(
                "\U0001f6d1 منطقه مورد نظر شما در سایت اداره امور مالیاتی، ارزش منطقه‌ای ثبت نشده است.\n\n"
                "لطفاً برای اخذ گواهی ارزش منطقه‌ای به یکی از دفاتر خدمات قضائی منطقه خود "
                "یا اداره مالیات مراجعه فرمائید.\n\n"
                "\U0001f4b0 ضمناً نصف مبلغ هزینه به شما عودت داده می‌شود "
                "که به شماره زیر پیام دهید:\n"
                "\n\U0001f4de 09306186888",
                reply_markup=get_main_menu_kb(user_id),
            )
            try:
                await update_case_in_panel(
                    panel_case_id, status="FAILED",
                    errorDetails="هیچ ارزش منطقه‌ای برای این موقعیت ثبت نشده",
                    errorStep="no_value_found",
                )
            except Exception as panel_err:
                logger.warning(f"[RV] خطا در آپدیت شکست پرونده در پنل: {panel_err}")
            await state.clear()
            return

        # ── عرصه: ارزش واحد از سامانه (برای «سایر» مبنای مسکونی × ضریب تعدیل) ──
        land = ayani_calc.compute_land_value(
            area, land_use, all_lu_values, other_index=data.get("rv_land_other_idx"),
        )

        if not land["ok"]:
            available = []
            for lu in LAND_USES:
                v = find_land_use_value(tax_result, lu)
                if v is not None:
                    available.append(f"{lu}: {v:,} ریال")
            avail_text = "\n".join(available) if available else "هیچ مقداری یافت نشد"

            await message.answer(
                f"⚠️ کاربری *{land_use}* برای این موقعیت در سامانه تعریف نشده است.\n\n"
                f"ارزش‌های موجود:\n{avail_text}\n\n"
                f"لطفاً از ابتدا با کاربری متفاوت تلاش کنید.",
                reply_markup=get_main_menu_kb(user_id),
            )
            try:
                await update_case_in_panel(
                    panel_case_id, status="FAILED",
                    errorDetails=f"کاربری {land_use} برای این موقعیت تعریف نشده",
                    errorStep="land_use_not_found",
                )
            except Exception as panel_err:
                logger.warning(f"[RV] خطا در آپدیت شکست پرونده در پنل: {panel_err}")
            await state.clear()
            return

        # ── اعیانی: تعیین شهرستان از روی نقشه (هرگز «یافت نشد» نمی‌دهد) ──
        geo = result.get("geocoded") or {}
        g_lat = rv_lat if rv_lat is not None else geo.get("lat")
        g_lng = rv_lng if rv_lng is not None else geo.get("lng")

        def _resolve():
            hints = []
            if g_lat is not None and g_lng is not None:
                hints = ayani_calc.detect_location_names(g_lat, g_lng)
            if geo.get("city"):
                hints.append(geo["city"])
            return ayani_calc.resolve_county(province, g_lat, g_lng, hints)

        county_info = await loop.run_in_executor(None, _resolve)
        logger.info(f"[RV] شهرستان اعیانی: {county_info['county']} "
                    f"(روش={county_info['method']}, نقشه={county_info.get('hint')})")

        building = ayani_calc.compute_building_value(
            county_info["rates"],
            use_key=data.get("rv_bld_use") or "residential",
            structure=data.get("rv_bld_structure") or "concrete",
            area=data.get("rv_bld_area") or 0,
            complete=bool(data.get("rv_bld_complete")),
            stage_key=data.get("rv_bld_stage") or "foundation",
            parking_area=data.get("rv_bld_parking_area") or 0,
            floor=data.get("rv_bld_floor"),
            age=data.get("rv_bld_age") or 0,
        )
        calc = ayani_calc.compute_all(land, building)
        land_value, building_value, total_value = land["value"], building["value"], calc["total"]
        # به کاربر نام شهرستانِ واقعی نقطه (از نقشه) نمایش داده می‌شود؛ اگر نرخ از
        # شهرستان همسایه گرفته شده باشد، فقط در لاگ/پیام ادمین ثبت می‌شود.
        county_label = county_info["county"]
        if county_info["method"] != "name" and county_info.get("hint"):
            county_label = county_info["hint"].replace("شهرستان ", "").strip()

        values_text = (
            f"1️⃣ ارزش عرصه: *{land_value:,} ریال*\n"
            f"2️⃣ ارزش اعیانی: *{building_value:,} ریال*\n"
            f"3️⃣ ارزش منطقه‌ای کل: *{total_value:,} ریال*"
        )

        # ── تولید PDF (صفحهٔ ۱ خلاصه، صفحهٔ ۲ نحوهٔ محاسبه) ──
        def _build_pdf():
            from ayani_pdf import build_ayani_pdf
            pdf_path = temp_path(f"regional_value_{user_id}_{message.message_id}.pdf")
            ok = build_ayani_pdf(
                pdf_path, province=province, county=county_label, address=address,
                tax_result=tax_result, result=calc,
            )
            return pdf_path, ok

        pdf_path, pdf_ok = await loop.run_in_executor(None, _build_pdf)

        await message.answer(
            f"📊 *نتیجهٔ محاسبهٔ ارزش منطقه‌ای*\n\n"
            f"📍 {province} — {county_label}\n\n"
            f"{values_text}",
            reply_markup=get_main_menu_kb(user_id),
        )

        if pdf_ok and os.path.exists(pdf_path):
            await send_document_direct(
                user_id, pdf_path,
                filename=f"ارزش_منطقه_ای_{province}.pdf",
                caption=(
                    f"📄 گزارش ارزش منطقه‌ای ملک (عرصه و اعیانی)\n\n"
                    f"💰 ارزش عرصه: {land_value:,} ریال\n"
                    f"🏗 ارزش اعیانی: {building_value:,} ریال\n"
                    f"🧾 ارزش منطقه‌ای کل: {total_value:,} ریال"
                ),
            )
            try:
                os.remove(pdf_path)
            except Exception:
                pass
        else:
            # فال‌بک متنی — نحوهٔ محاسبه به‌صورت متن
            steps = ayani_calc.explain_steps(calc)
            steps_text = "\n".join(
                f"• {t}: {f'{a:,} ریال' if a is not None else ''}" + (f"\n   {f}" if f else "")
                for t, f, a in steps
            )
            await message.answer(
                f"🧮 *نحوهٔ محاسبه*\n\n{steps_text}\n\n"
                f"⚠️ خطا در ساخت PDF. نتایج به صورت متنی ارسال شد.",
                reply_markup=get_main_menu_kb(user_id),
            )

        # ── اطلاع به ادمین ──
        try:
            import datetime
            is_admin_exempt = await is_exempt_user(user_id)
            fee_line = "معاف از پرداخت (ادمین)" if is_admin_exempt else f"{REGIONAL_VALUE_FEE:,} تومان"
            title = "🆓 استعلام ارزش منطقه‌ای (معاف - ادمین)" if is_admin_exempt else "💰 پرداخت ارزش منطقه‌ای"
            await bot.send_message(
                ADMIN_ID,
                f"{title}:\n"
                f"👤 کاربر: {message.from_user.full_name} ({user_id})\n"
                f"🏙 شهرستان مبنای اعیانی: {county_info['county']} ({county_info['method']})\n"
                f"{_inputs_summary(data)}\n"
                f"💰 عرصه: {land_value:,} | اعیانی: {building_value:,} | کل: {total_value:,} ریال\n"
                f"💵 هزینه: {fee_line}\n"
                f"⏱ زمان: {datetime.datetime.now().strftime('%Y/%m/%d %H:%M')}",
            )
        except Exception as e:
            logging.error(f"[RV] خطا در ارسال اطلاع به ادمین: {e}")

        try:
            await update_case_in_panel(
                panel_case_id,
                status="COMPLETED",
                resultSummary=(
                    f"عرصه: {land_value:,} | اعیانی: {building_value:,} | "
                    f"کل: {total_value:,} ریال ({county_info['county']})"
                ),
            )
        except Exception as panel_err:
            logger.warning(f"[RV] خطا در آپدیت موفقیت پرونده در پنل: {panel_err}")

    except ValueError as e:
        await message.answer(
            f"⚠️ خطا در استعلام: {e}\n\n"
            f"لطفاً آدرس و استان را بررسی و از ابتدا تلاش کنید.",
            reply_markup=get_main_menu_kb(user_id),
        )
        try:
            await update_case_in_panel(
                panel_case_id, status="FAILED",
                errorDetails=str(e), errorStep="value_error",
            )
        except Exception as panel_err:
            logger.warning(f"[RV] خطا در آپدیت شکست پرونده در پنل: {panel_err}")
    except Exception as e:
        logging.error(f"[RV] خطا در پردازش استعلام ارزش منطقه‌ای: {e}", exc_info=True)
        await message.answer(
            "⚠️ خطایی در پردازش استعلام رخ داد. لطفاً چند دقیقه دیگر تلاش کنید.\n"
            "اگر مشکل ادامه داشت، با پشتیبانی تماس بگیرید.",
            reply_markup=get_main_menu_kb(user_id),
        )
        try:
            await update_case_in_panel(
                panel_case_id, status="FAILED",
                errorDetails=str(e), errorStep="unhandled_exception",
            )
        except Exception as panel_err:
            logger.warning(f"[RV] خطا در آپدیت شکست پرونده در پنل: {panel_err}")

    await state.clear()
