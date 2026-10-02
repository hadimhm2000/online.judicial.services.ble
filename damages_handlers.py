"""
هندلرهای بخش «خسارت تأخیر تأدیه و مهریه به نرخ روز» — گزینهٔ مستقل منوی اصلی.

جریان کاربر:
  خسارت تأخیر: مبلغ اصل → تاریخ سررسید → تاریخ محاسبه (یا «تا امروز») → نتیجه
  مهریه:       مبلغ مهریه → سال وقوع عقد → نتیجه

بخش مدیر (شاخص بانک مرکزی، damages_calc.py):
  /cpi                        نمایش وضعیت داده و آخرین ماه واردشده
  /cpi 1405/06 352.4          ثبت/اصلاح شاخص یک ماه
  /cpi_year 1365 0.21         ثبت شاخص سالانهٔ یک سال (برای مهریه‌های قدیمی)
  ارسال فایل اکسل با کپشن /cpi_import
      ستون‌ها: سال | ماه (برای شاخص سالانه خالی) | شاخص
      کپشن «/cpi_import replace» کل دادهٔ قبلی را جایگزین می‌کند.
  یادآوری ماهانه: از روز اول هر ماه شمسی تا وقتی شاخص ماه قبل وارد نشده،
  روزی یک‌بار به مدیر یادآوری می‌شود (cpi_reminder_loop).

این روتر در bot.py قبل از روتر اصلی ثبت می‌شود و از ساعت کاری مستقل است
(هیچ درخواستی به سامانه قضایی نمی‌فرستد).
"""
import asyncio
import datetime
import logging
import os

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

import damages_calc as dc
from config import ADMIN_ID, temp_path
from id_validation import normalize_digits
from keyboards import (
    BACK_TO_MAIN_TEXT, DAMAGES_MENU_TEXT, DMG_LATE_TEXT, DMG_MAHR_TEXT, DMG_TODAY_TEXT,
    back_only_kb, dmg_calc_date_kb, dmg_type_kb, get_flow_type_kb)
from states import Form

logger = logging.getLogger(__name__)

damages_router = Router()

DISCLAIMER = (
    "ℹ️ این محاسبه بر اساس شاخص تورم بانک مرکزی و صرفاً جهت اطلاع است؛ "
    "ملاک نهایی، محاسبهٔ دادگاه یا واحد اجرای احکام می‌باشد."
)


def _fmt(n: int) -> str:
    return f"{n:,}"


def _jdate(t: tuple) -> str:
    return f"{t[0]:04d}/{t[1]:02d}/{t[2]:02d}"


async def _back_to_main(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "❓ *لطفاً نحوه ثبت درخواست خود را انتخاب فرمایید:*",
        reply_markup=get_flow_type_kb(message.from_user.id))
    await state.set_state(Form.waiting_for_flow_type)


# ══════════════════════════════════════════════════════════════════════════
# ورود و انتخاب نوع محاسبه
# ══════════════════════════════════════════════════════════════════════════
@damages_router.message(StateFilter("*"), F.text == DAMAGES_MENU_TEXT)
async def damages_entry(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "📈 *محاسبهٔ خسارت تأخیر تأدیه و مهریه به نرخ روز*\n\n"
        "نوع محاسبه را انتخاب کنید:",
        reply_markup=dmg_type_kb)
    await state.set_state(Form.dmg_waiting_type)


@damages_router.message(Form.dmg_waiting_type)
async def damages_type(message: Message, state: FSMContext):
    text = message.text or ""
    if text == BACK_TO_MAIN_TEXT:
        await _back_to_main(message, state)
        return
    if text == DMG_LATE_TEXT:
        await message.answer(
            "💸 مبلغ اصل خواسته (مبلغ چک/سفته/بدهی) را به *ریال* وارد کنید:",
            reply_markup=back_only_kb)
        await state.set_state(Form.dmg_waiting_amount)
        return
    if text == DMG_MAHR_TEXT:
        await message.answer(
            "💍 مبلغ مهریهٔ مندرج در عقدنامه را به *ریال* وارد کنید:",
            reply_markup=back_only_kb)
        await state.set_state(Form.mahr_waiting_amount)
        return
    await message.answer("لطفاً یکی از گزینه‌های زیر را انتخاب کنید:", reply_markup=dmg_type_kb)


async def _back_to_type(message: Message, state: FSMContext):
    await message.answer("نوع محاسبه را انتخاب کنید:", reply_markup=dmg_type_kb)
    await state.set_state(Form.dmg_waiting_type)


# ══════════════════════════════════════════════════════════════════════════
# خسارت تأخیر تأدیه
# ══════════════════════════════════════════════════════════════════════════
@damages_router.message(Form.dmg_waiting_amount)
async def dmg_amount(message: Message, state: FSMContext):
    if message.text == "🔙 بازگشت":
        await _back_to_type(message, state)
        return
    amount = dc.parse_amount(message.text)
    if not amount:
        await message.answer("⚠️ مبلغ را فقط به‌صورت عدد و به ریال وارد کنید (مثال: 500000000):")
        return
    await state.update_data(dmg_amount=amount)
    await message.answer(
        "📅 تاریخ سررسید را به شمسی وارد کنید (مثال: 1402/08/15):",
        reply_markup=back_only_kb)
    await state.set_state(Form.dmg_waiting_due_date)


@damages_router.message(Form.dmg_waiting_due_date)
async def dmg_due_date(message: Message, state: FSMContext):
    if message.text == "🔙 بازگشت":
        await message.answer("💸 مبلغ اصل خواسته را به *ریال* وارد کنید:", reply_markup=back_only_kb)
        await state.set_state(Form.dmg_waiting_amount)
        return
    due = dc.parse_jalali_date(message.text)
    if not due:
        await message.answer("⚠️ تاریخ نامعتبر است. به شکل سال/ماه/روز وارد کنید (مثال: 1402/08/15):")
        return
    await state.update_data(dmg_due=list(due))
    await message.answer(
        "📅 خسارت تا چه تاریخی محاسبه شود؟\n"
        "تاریخ را به شمسی وارد کنید یا «تا امروز» را بزنید:",
        reply_markup=dmg_calc_date_kb)
    await state.set_state(Form.dmg_waiting_calc_date)


@damages_router.message(Form.dmg_waiting_calc_date)
async def dmg_calc_date(message: Message, state: FSMContext):
    if message.text == "🔙 بازگشت":
        await message.answer("📅 تاریخ سررسید را به شمسی وارد کنید:", reply_markup=back_only_kb)
        await state.set_state(Form.dmg_waiting_due_date)
        return
    if message.text == DMG_TODAY_TEXT:
        calc_date = dc.today_jalali()
    else:
        calc_date = dc.parse_jalali_date(message.text)
        if not calc_date:
            await message.answer("⚠️ تاریخ نامعتبر است. به شکل سال/ماه/روز وارد کنید یا «تا امروز» را بزنید:")
            return
    data = await state.get_data()
    try:
        r = dc.calc_late_payment(data["dmg_amount"], tuple(data["dmg_due"]), tuple(calc_date))
    except dc.CpiMissing as e:
        logger.warning(f"[DAMAGES] شاخص ناقص: {e}")
        await message.answer(
            "⚠️ شاخص تورم لازم برای این محاسبه هنوز در ربات ثبت نشده است.\n"
            "مدیر مطلع شد؛ لطفاً کمی بعد دوباره تلاش کنید.",
            reply_markup=dmg_type_kb)
        await _notify_admin_missing(message.bot, str(e))
        await state.set_state(Form.dmg_waiting_type)
        return
    except ValueError as e:
        await message.answer(f"⚠️ {e}")
        return

    note = ""
    if r["used_latest_available"]:
        note = (f"\n🔸 شاخص ماه قبل از تاریخ محاسبه هنوز منتشر نشده؛ "
                f"آخرین شاخص موجود ({r['target_key']}) استفاده شد.")
    await message.answer(
        "📊 *نتیجهٔ محاسبهٔ خسارت تأخیر تأدیه*\n\n"
        f"💵 مبلغ اصل: {_fmt(r['amount'])} ریال\n"
        f"📅 سررسید: {_jdate(tuple(data['dmg_due']))}  (شاخص {r['due_key']}: {r['base_index']:g})\n"
        f"📅 محاسبه تا: {_jdate(tuple(calc_date))}  (شاخص {r['target_key']}: {r['target_index']:g})\n\n"
        f"📈 مبلغ به‌روز‌شده: *{_fmt(r['updated_amount'])} ریال*\n"
        f"💸 خسارت تأخیر تأدیه: *{_fmt(r['damages'])} ریال*\n"
        f"{note}\n\n"
        f"فرمول: مبلغ × (شاخص {r['target_key']} ÷ شاخص {r['due_key']})\n\n"
        f"{DISCLAIMER}",
        reply_markup=dmg_type_kb)
    await state.set_state(Form.dmg_waiting_type)


# ══════════════════════════════════════════════════════════════════════════
# مهریه به نرخ روز
# ══════════════════════════════════════════════════════════════════════════
@damages_router.message(Form.mahr_waiting_amount)
async def mahr_amount(message: Message, state: FSMContext):
    if message.text == "🔙 بازگشت":
        await _back_to_type(message, state)
        return
    amount = dc.parse_amount(message.text)
    if not amount:
        await message.answer("⚠️ مبلغ را فقط به‌صورت عدد و به ریال وارد کنید:")
        return
    await state.update_data(mahr_amount=amount)
    await message.answer(
        "📅 سال وقوع عقد را به شمسی وارد کنید (مثال: 1385):",
        reply_markup=back_only_kb)
    await state.set_state(Form.mahr_waiting_year)


@damages_router.message(Form.mahr_waiting_year)
async def mahr_year(message: Message, state: FSMContext):
    if message.text == "🔙 بازگشت":
        await message.answer("💍 مبلغ مهریه را به *ریال* وارد کنید:", reply_markup=back_only_kb)
        await state.set_state(Form.mahr_waiting_amount)
        return
    raw = normalize_digits(message.text or "")
    if not raw.isdigit() or not (1300 <= int(raw) <= 1500):
        await message.answer("⚠️ سال را به‌صورت چهار رقمی شمسی وارد کنید (مثال: 1385):")
        return
    data = await state.get_data()
    try:
        r = dc.calc_mahrieh(data["mahr_amount"], int(raw))
    except dc.CpiMissing as e:
        logger.warning(f"[MAHRIEH] شاخص ناقص: {e}")
        await message.answer(
            "⚠️ شاخص تورم لازم برای این سال هنوز در ربات ثبت نشده است.\n"
            "مدیر مطلع شد؛ لطفاً کمی بعد دوباره تلاش کنید.",
            reply_markup=dmg_type_kb)
        await _notify_admin_missing(message.bot, str(e))
        await state.set_state(Form.dmg_waiting_type)
        return
    except ValueError as e:
        await message.answer(f"⚠️ {e}", reply_markup=dmg_type_kb)
        await state.set_state(Form.dmg_waiting_type)
        return

    await message.answer(
        "📊 *نتیجهٔ محاسبهٔ مهریه به نرخ روز*\n\n"
        f"💵 مبلغ مهریه: {_fmt(r['amount'])} ریال\n"
        f"📅 سال عقد: {r['marriage_year']}  (شاخص سالانه: {r['base_index']:g})\n"
        f"📅 سال مبنا (سال قبل از تأدیه): {r['target_year']}  (شاخص سالانه: {r['target_index']:g})\n\n"
        f"💍 مهریه به نرخ روز: *{_fmt(r['updated_amount'])} ریال*\n\n"
        f"فرمول: مبلغ × (شاخص سال {r['target_year']} ÷ شاخص سال {r['marriage_year']})\n\n"
        f"{DISCLAIMER}",
        reply_markup=dmg_type_kb)
    await state.set_state(Form.dmg_waiting_type)


# ══════════════════════════════════════════════════════════════════════════
# بخش مدیر — ورود شاخص بانک مرکزی
# ══════════════════════════════════════════════════════════════════════════
_last_missing_alert: dict = {}


async def _notify_admin_missing(bot: Bot, detail: str):
    """هشدار کمبود شاخص به مدیر — هر مورد حداکثر یک‌بار در ۶ ساعت."""
    now = datetime.datetime.now()
    last = _last_missing_alert.get(detail)
    if last and (now - last).total_seconds() < 6 * 3600:
        return
    _last_missing_alert[detail] = now
    try:
        await bot.send_message(
            ADMIN_ID,
            f"📈 کاربری محاسبهٔ خسارت/مهریه انجام داد ولی {detail}\n"
            "ثبت شاخص: /cpi سال/ماه مقدار   یا   /cpi_year سال مقدار")
    except Exception:
        pass


def _is_admin(message: Message) -> bool:
    return bool(message.from_user and message.from_user.id == ADMIN_ID)


def _cpi_status() -> str:
    data = dc.load_cpi()
    latest = dc.latest_month(data)
    missing = dc.missing_required_month()
    lines = [
        "📈 *وضعیت شاخص تورم (بانک مرکزی)*",
        f"سال پایه: {data.get('base') or 'نامشخص'}",
        f"تعداد ماه‌های ثبت‌شده: {len(data['monthly'])}",
        f"تعداد سال‌های سالانه: {len(data['annual'])}",
        f"آخرین ماه: {dc.month_key(*latest) if latest else '—'}",
        f"آخرین به‌روزرسانی: {data.get('updated_at') or '—'}",
    ]
    if missing:
        lines.append(f"⚠️ شاخص ماه {dc.month_key(*missing)} هنوز وارد نشده است.")
    lines += [
        "",
        "ثبت یک ماه: /cpi 1405/06 352.4",
        "ثبت سالانه: /cpi_year 1365 0.21",
        "ورود دسته‌ای: فایل اکسل (سال | ماه | شاخص) با کپشن /cpi_import",
    ]
    return "\n".join(lines)


@damages_router.message(Command("cpi"), _is_admin)
async def cpi_cmd(message: Message):
    parts = normalize_digits(message.text or "").split()
    if len(parts) == 1:
        await message.answer(_cpi_status())
        return
    if len(parts) != 3:
        await message.answer("فرمت: /cpi 1405/06 352.4")
        return
    ym = parts[1].replace("-", "/").split("/")
    try:
        year, month, value = int(ym[0]), int(ym[1]), float(parts[2])
        assert 1300 <= year <= 1500 and 1 <= month <= 12 and value > 0
    except Exception:
        await message.answer("⚠️ ورودی نامعتبر. فرمت: /cpi 1405/06 352.4")
        return
    dc.set_monthly(year, month, value)
    await message.answer(f"✅ شاخص ماه {dc.month_key(year, month)} = {value:g} ثبت شد.")


@damages_router.message(Command("cpi_year"), _is_admin)
async def cpi_year_cmd(message: Message):
    parts = normalize_digits(message.text or "").split()
    try:
        year, value = int(parts[1]), float(parts[2])
        assert 1300 <= year <= 1500 and value > 0
    except Exception:
        await message.answer("⚠️ فرمت: /cpi_year 1365 0.21")
        return
    dc.import_rows([(year, None, value)])
    await message.answer(f"✅ شاخص سالانهٔ {year} = {value:g} ثبت شد.")


def _read_cpi_excel(path: str) -> list[tuple]:
    """سطرهای (سال، ماه یا None، شاخص) از اکسل؛ سطرهای سرتیتر/نامعتبر نادیده گرفته می‌شوند."""
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows = []
    for row in ws.iter_rows(values_only=True):
        cells = [c for c in row[:3]]
        if len(cells) < 3:
            continue
        try:
            year = int(float(normalize_digits(str(cells[0]))))
            month_raw = normalize_digits(str(cells[1] or "")).strip()
            month = int(float(month_raw)) if month_raw not in ("", "None") else None
            value = float(normalize_digits(str(cells[2])).replace(",", ""))
        except (TypeError, ValueError):
            continue
        if not (1300 <= year <= 1500) or value <= 0:
            continue
        if month is not None and not (1 <= month <= 12):
            continue
        rows.append((year, month, value))
    wb.close()
    return rows


@damages_router.message(F.document, F.caption.startswith("/cpi_import"), _is_admin)
async def cpi_import_cmd(message: Message, bot: Bot):
    path = temp_path(f"cpi_import_{message.message_id}.xlsx")
    try:
        await bot.download(message.document, destination=path)
        rows = _read_cpi_excel(path)
        if not rows:
            await message.answer("⚠️ هیچ سطر معتبری پیدا نشد. ستون‌ها: سال | ماه | شاخص")
            return
        replace = "replace" in (message.caption or "")
        n_month, n_year = dc.import_rows(rows, replace=replace)
        await message.answer(
            f"✅ ورود شاخص انجام شد: {n_month} ماه و {n_year} سال"
            + (" (دادهٔ قبلی جایگزین شد)" if replace else "") + "\n\n" + _cpi_status())
    except Exception as e:
        logger.error(f"[CPI] خطا در ورود اکسل: {e}", exc_info=True)
        await message.answer(f"❌ خطا در خواندن فایل: {str(e)[:200]}")
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


async def cpi_reminder_loop(bot: Bot, check_every_seconds: int = 3600):
    """از روز اول هر ماه شمسی تا ثبت شاخص ماه قبل، روزی یک‌بار (ساعت ۱۰ به بعد) به مدیر یادآوری می‌کند."""
    last_reminded_day = None
    tehran = datetime.timezone(datetime.timedelta(hours=3, minutes=30))
    while True:
        try:
            await asyncio.sleep(check_every_seconds)
            now = datetime.datetime.now(tehran)
            if now.hour < 10 or last_reminded_day == now.date():
                continue
            missing = dc.missing_required_month()
            if not missing:
                continue
            last_reminded_day = now.date()
            await bot.send_message(
                ADMIN_ID,
                f"📈 یادآوری ماهانه: شاخص تورم ماه {dc.month_key(*missing)} هنوز در ربات ثبت نشده است.\n"
                "پس از انتشار توسط بانک مرکزی ثبت کنید:\n"
                f"/cpi {dc.month_key(*missing)} مقدار")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[CPI] خطا در یادآوری ماهانه: {e}")
