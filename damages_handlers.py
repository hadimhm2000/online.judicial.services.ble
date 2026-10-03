"""
هندلرهای بخش «خسارت تأخیر تأدیه و مهریه به نرخ روز» — گزینهٔ مستقل منوی اصلی.

جریان کاربر:
  خسارت تأخیر: مبلغ اصل → تاریخ سررسید → تاریخ پرداخت (یا «تا امروز») → نتیجه
  مهریه:       مبلغ مهریه → سال وقوع عقد → نتیجه

بخش مدیر (شاخص بانک مرکزی، damages_calc.py — همهٔ مقادیر با پایهٔ ۱۳۹۵=۱۰۰):
  /cpi                        نمایش وضعیت داده و آخرین ماه موجود
  /cpi_fetch                  دریافت فوری آخرین PDF از سایت بانک مرکزی
  ارسال PDF ماهانهٔ بانک مرکزی با کپشن /cpi_pdf
                              (وقتی سرور به cbi.ir دسترسی ندارد)
  /cpi 1405/06 3453.5         ثبت/اصلاح دستی شاخص یک ماه
  /cpi_year 1365 0.85         ثبت شاخص سالانهٔ یک سال (برای مهریه‌های قبل از ۱۳۷۵)
  ارسال فایل اکسل با کپشن /cpi_import
      ستون‌ها: سال | ماه (برای شاخص سالانه خالی) | شاخص
      کپشن «/cpi_import replace» اصلاحات دستی قبلی را پاک می‌کند.
  دریافت خودکار ماهانه (cpi_reminder_loop): از روز اول هر ماه شمسی تا وقتی شاخص
  ماه قبل موجود نشده، روزی یک‌بار PDF جدید از cbi.ir/simplelist/1611.aspx
  دریافت می‌شود؛ اگر موفق نشد، به مدیر یادآوری می‌شود.

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

import cpi_fetcher
import damages_calc as dc
import damages_pdf
import runtime_state
from bale_file_sender import send_document_direct
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


async def _send_result(message: Message, build, filename: str, caption: str, fallback_text: str):
    """
    نتیجه را به‌صورت PDF رسمی (damages_pdf.py) برای کاربر می‌فرستد؛ اگر ساخت یا
    ارسال PDF ناموفق بود، همان نتیجهٔ متنی قبلی ارسال می‌شود.
    build: تابعی که مسیر خروجی می‌گیرد و True/False برمی‌گرداند.
    """
    path = temp_path(f"damages_{message.from_user.id}_{message.message_id}.pdf")
    sent = False
    try:
        ok = await asyncio.get_running_loop().run_in_executor(None, build, path)
        if ok and os.path.exists(path):
            sent = bool(await send_document_direct(
                message.chat.id, path, filename=filename, caption=caption))
    except Exception as e:
        logger.error(f"[DAMAGES] خطا در ساخت/ارسال PDF: {e}", exc_info=True)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    if sent:
        await message.answer("برای محاسبهٔ دیگر، نوع محاسبه را انتخاب کنید:", reply_markup=dmg_type_kb)
    else:
        await message.answer(fallback_text, reply_markup=dmg_type_kb)


async def _back_to_main(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "❓ *لطفاً نحوه ثبت درخواست خود را انتخاب فرمایید:*",
        reply_markup=get_flow_type_kb(message.from_user.id))
    await state.set_state(Form.waiting_for_flow_type)


# ══════════════════════════════════════════════════════════════════════════
# ورود و انتخاب نوع محاسبه
# ══════════════════════════════════════════════════════════════════════════
# شمارندهٔ استفادهٔ رایگان این بخش (مشترک برای خسارت تأخیر و مهریه) — مثل
# «محاسبه تمبر» و «ابزار فایل»: ۲ بار رایگان، سپس اشتراک ماهیانهٔ مشترک.
USAGE_KEY = "damages"


async def _require_subscription(message: Message, state: FSMContext) -> bool:
    """اگر سهمیهٔ رایگان تمام شده و اشتراک فعال نیست، کاربر را به پرداخت اشتراک
    می‌برد و True برمی‌گرداند."""
    if runtime_state.can_use_service(message.from_user.id, USAGE_KEY):
        return False
    # ⭐ ۱۴۰۵/۰۷: دو گزینه — اشتراک ماهیانه یا پرداخت تکی همین مورد
    from single_pay_handlers import offer_subscription_or_single
    await offer_subscription_or_single(message, state, USAGE_KEY)
    return True


@damages_router.message(StateFilter("*"), F.text == DAMAGES_MENU_TEXT)
async def damages_entry(message: Message, state: FSMContext):
    await state.clear()
    if await _require_subscription(message, state):
        return
    status = runtime_state.usage_status_line(message.from_user.id, USAGE_KEY)
    await message.answer(
        "📈 *محاسبهٔ خسارت تأخیر تأدیه و مهریه به نرخ روز*\n\n"
        f"{status}"
        "نوع محاسبه را انتخاب کنید:",
        reply_markup=dmg_type_kb)
    await state.set_state(Form.dmg_waiting_type)


@damages_router.message(Form.dmg_waiting_type)
async def damages_type(message: Message, state: FSMContext):
    text = message.text or ""
    if text == BACK_TO_MAIN_TEXT:
        await _back_to_main(message, state)
        return
    if text in (DMG_LATE_TEXT, DMG_MAHR_TEXT) and await _require_subscription(message, state):
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
        "📅 تاریخ پرداخت (خسارت تا چه تاریخی محاسبه شود؟)\n"
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

    runtime_state.increment_usage(message.from_user.id, USAGE_KEY)
    note = ""
    if r["used_latest_available"]:
        note = (f"\n🔸 شاخص ماه پرداخت ({r['pay_key']}) هنوز منتشر نشده؛ از نزدیک‌ترین "
                f"شاخص موجود ({r['target_key']}) استفاده شد. پس از انتشار شاخص، برای "
                "نتیجهٔ دقیق‌تر دوباره محاسبه کنید.\n")
    due = tuple(data["dmg_due"])
    pay = tuple(calc_date)
    caption = (
        "📄 گزارش محاسبهٔ خسارت تأخیر تأدیه\n\n"
        f"💵 مبلغ دین: {_fmt(r['amount'])} ریال\n"
        f"📈 اصل دین و خسارت: {_fmt(r['updated_amount'])} ریال\n"
        f"💸 خسارت به تنهایی: {_fmt(r['damages'])} ریال\n"
        + (f"🔸 شاخص ماه پرداخت هنوز منتشر نشده؛ شاخص {r['target_key']} استفاده شد.\n"
           if r["used_latest_available"] else ""))
    await _send_result(
        message,
        lambda path: damages_pdf.build_late_payment_pdf(path, r, due, pay),
        "خسارت_تاخیر_تادیه.pdf", caption,
        "📊 *نتیجهٔ محاسبهٔ خسارت تأخیر تأدیه*\n\n"
        f"💵 مبلغ دین: {_fmt(r['amount'])} ریال\n"
        f"📅 زمان سررسید یا مطالبه: {_jdate(tuple(data['dmg_due']))}  "
        f"(شاخص {r['due_key']}: {r['base_index']:g})\n"
        f"📅 زمان پرداخت: {_jdate(tuple(calc_date))}  "
        f"(شاخص {r['target_key']}: {r['target_index']:g})\n\n"
        f"📈 اصل دین و خسارت: *{_fmt(r['updated_amount'])} ریال*\n"
        f"💸 خسارت به تنهایی: *{_fmt(r['damages'])} ریال*\n"
        f"{note}\n"
        f"فرمول: مبلغ × (شاخص {r['target_key']} ÷ شاخص {r['due_key']})\n"
        f"شاخص بانک مرکزی با سال پایهٔ {r['cpi_base']}\n\n"
        f"{DISCLAIMER}")
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

    runtime_state.increment_usage(message.from_user.id, USAGE_KEY)
    caption = (
        "📄 گزارش محاسبهٔ مهریه به نرخ روز\n\n"
        f"💵 مبلغ مهریه: {_fmt(r['amount'])} ریال (سال عقد {r['marriage_year']})\n"
        f"💍 مهریه به نرخ روز: {_fmt(r['updated_amount'])} ریال\n")
    await _send_result(
        message,
        lambda path: damages_pdf.build_mahrieh_pdf(path, r),
        "مهریه_به_نرخ_روز.pdf", caption,
        "📊 *نتیجهٔ محاسبهٔ مهریه به نرخ روز*\n\n"
        f"💵 مبلغ مهریه: {_fmt(r['amount'])} ریال\n"
        f"📅 سال عقد: {r['marriage_year']}  (شاخص سالانه: {r['base_index']:g})\n"
        f"📅 سال مبنا (سال قبل از تأدیه): {r['target_year']}  (شاخص سالانه: {r['target_index']:g})\n\n"
        f"💍 مهریه به نرخ روز: *{_fmt(r['updated_amount'])} ریال*\n\n"
        f"فرمول: مبلغ × (شاخص سال {r['target_year']} ÷ شاخص سال {r['marriage_year']})\n\n"
        f"{DISCLAIMER}")
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
            "دریافت از بانک مرکزی: /cpi_fetch\n"
            "ثبت دستی (پایهٔ ۱۳۹۵): /cpi سال/ماه مقدار   یا   /cpi_year سال مقدار")
    except Exception:
        pass


def _is_admin(message: Message) -> bool:
    return bool(message.from_user and message.from_user.id == ADMIN_ID)


def _cpi_status() -> str:
    data = dc.load_cpi()
    series, chained, link = dc.judicial_series(data)
    latest = dc.latest_month(data)
    missing = dc.missing_required_month()
    c1400 = data["monthly_1400"]
    lines = [
        "📈 *وضعیت شاخص تورم (بانک مرکزی)*",
        f"سال پایه: {dc.CPI_BASE}",
        f"ماه‌های موجود: {len(series)} ({min(series) if series else '—'} تا "
        f"{dc.month_key(*latest) if latest else '—'})",
        f"اصلاحات دستی: {len(data['overrides'])} ماه، {len(data['annual_1395'])} سال",
        f"جدول ۱۴۰۰=۱۰۰ بانک مرکزی: تا {max(c1400) if c1400 else '—'}"
        + (f" (ماه پیوند {link}، {len(chained)} ماه زنجیره‌ای)" if link else ""),
        f"آخرین دریافت: {data.get('fetched_at') or '—'}",
        f"منبع: {data.get('source_pdf') or '—'}",
    ]
    if chained:
        lines.append("آخرین شاخص‌ها: " + "، ".join(
            f"{k}={series[k]:g}" for k in sorted(chained)[-3:]))
    if missing:
        lines.append(f"⚠️ شاخص ماه {dc.month_key(*missing)} هنوز موجود نیست.")
    lines += [
        "",
        "دریافت فوری از بانک مرکزی: /cpi_fetch",
        "یا ارسال PDF ماهانهٔ بانک مرکزی با کپشن /cpi_pdf",
        "ثبت دستی یک ماه (پایهٔ ۱۳۹۵): /cpi 1405/06 3453.5",
        "ثبت سالانه (مهریه): /cpi_year 1365 0.85",
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
        await message.answer("فرمت: /cpi 1405/06 3453.5")
        return
    ym = parts[1].replace("-", "/").split("/")
    try:
        year, month, value = int(ym[0]), int(ym[1]), float(parts[2])
        assert 1300 <= year <= 1500 and 1 <= month <= 12 and value > 0
    except Exception:
        await message.answer("⚠️ ورودی نامعتبر. فرمت: /cpi 1405/06 3453.5")
        return
    dc.set_monthly(year, month, value)
    await message.answer(f"✅ شاخص ماه {dc.month_key(year, month)} = {value:g} (پایهٔ ۱۳۹۵) ثبت شد.")


async def _fetch_from_cbi() -> list[str]:
    """آخرین PDF بانک مرکزی را می‌گیرد و ذخیره می‌کند. خروجی: ماه‌های تازه‌اضافه‌شده."""
    values, url = await asyncio.to_thread(cpi_fetcher.fetch_latest)
    added = dc.set_monthly_1400(values, url)
    logger.info(f"[CPI] دریافت از بانک مرکزی: {url} — ماه‌های جدید: {added}")
    return added


def _added_text(added: list[str]) -> str:
    if not added:
        return "ماه جدیدی اضافه نشد (آخرین PDF بانک مرکزی قبلاً دریافت شده بود)."
    series = dc.judicial_series()[0]
    return "ماه‌های جدید: " + "، ".join(f"{k}={series[k]:g}" for k in added)


@damages_router.message(Command("cpi_fetch"), _is_admin)
async def cpi_fetch_cmd(message: Message):
    await message.answer("⏳ در حال دریافت از سایت بانک مرکزی...")
    try:
        added = await _fetch_from_cbi()
    except Exception as e:
        logger.error(f"[CPI] خطا در دریافت از بانک مرکزی: {e}", exc_info=True)
        await message.answer(
            f"❌ دریافت از بانک مرکزی ناموفق بود: {str(e)[:300]}\n"
            "می‌توانید PDF ماهانه را از cbi.ir/simplelist/1611.aspx دانلود و با کپشن /cpi_pdf بفرستید.")
        return
    await message.answer(f"✅ {_added_text(added)}\n\n{_cpi_status()}")


@damages_router.message(F.document, F.caption.startswith("/cpi_pdf"), _is_admin)
async def cpi_pdf_cmd(message: Message, bot: Bot):
    path = temp_path(f"cpi_pdf_{message.message_id}.pdf")
    try:
        await bot.download(message.document, destination=path)
        with open(path, "rb") as f:
            values = cpi_fetcher.parse_cpi_pdf(f.read())
        added = dc.set_monthly_1400(values, f"PDF ارسالی مدیر ({message.document.file_name or ''})")
        await message.answer(f"✅ {_added_text(added)}\n\n{_cpi_status()}")
    except Exception as e:
        logger.error(f"[CPI] خطا در خواندن PDF: {e}", exc_info=True)
        await message.answer(f"❌ خطا در خواندن PDF: {str(e)[:300]}")
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


@damages_router.message(Command("cpi_year"), _is_admin)
async def cpi_year_cmd(message: Message):
    parts = normalize_digits(message.text or "").split()
    try:
        year, value = int(parts[1]), float(parts[2])
        assert 1300 <= year <= 1500 and value > 0
    except Exception:
        await message.answer("⚠️ فرمت: /cpi_year 1365 0.85")
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
    """
    از روز اول هر ماه شمسی تا موجود شدن شاخص ماه قبل، روزی یک‌بار (ساعت ۱۰ به بعد)
    آخرین PDF را از سایت بانک مرکزی دریافت می‌کند؛ اگر نشد، به مدیر یادآوری می‌کند.
    """
    last_checked_day = None
    tehran = datetime.timezone(datetime.timedelta(hours=3, minutes=30))
    while True:
        try:
            await asyncio.sleep(check_every_seconds)
            now = datetime.datetime.now(tehran)
            if now.hour < 10 or last_checked_day == now.date():
                continue
            missing = dc.missing_required_month()
            if not missing:
                continue
            last_checked_day = now.date()
            key = dc.month_key(*missing)
            error = ""
            try:
                added = await _fetch_from_cbi()
                if key in added or not dc.missing_required_month():
                    await bot.send_message(
                        ADMIN_ID, f"📈 شاخص تورم از سایت بانک مرکزی دریافت شد. {_added_text(added)}")
                    continue
            except Exception as e:
                error = f"\nخطای دریافت خودکار: {str(e)[:200]}"
                logger.error(f"[CPI] خطا در دریافت خودکار: {e}")
            await bot.send_message(
                ADMIN_ID,
                f"📈 یادآوری ماهانه: شاخص تورم ماه {key} هنوز در ربات موجود نیست "
                f"(احتمالاً بانک مرکزی هنوز منتشر نکرده).{error}\n"
                "فردا دوباره خودکار بررسی می‌شود. دریافت فوری: /cpi_fetch\n"
                "یا PDF را از cbi.ir/simplelist/1611.aspx با کپشن /cpi_pdf بفرستید.")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[CPI] خطا در دریافت/یادآوری ماهانه: {e}")
