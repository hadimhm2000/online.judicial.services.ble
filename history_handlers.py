"""
هندلرهای بخش «📂 سوابق و فاکتورهای من» — گزینهٔ مستقل منوی اصلی.

  📋 درخواست‌های اخیر: آخرین پرونده‌های کاربر از پنل (نوع خدمت، کد رهگیری،
     وضعیت، مبلغ پرداختی و تاریخ) — panel_sync.get_user_cases
  📎 فایل‌های ارسالی: آخرین فایل‌هایی که ربات برای کاربر فرستاده (user_files.py)
     با دکمهٔ دریافت دوباره (فقط با file_id بله — بدون آپلود مجدد)
  📄 دریافت دوبارهٔ چاپ PDF: برای همهٔ درخواست‌های اخیر به‌جز استعلام‌ها
     (final_print.request_print — همان مسیر چاپ نهایی) — ۱۴۰۵/۰۷

این روتر در bot.py قبل از روتر اصلی ثبت می‌شود و به سامانهٔ قضایی درخواستی
نمی‌فرستد.
"""
import datetime
import logging

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import final_print
import pending_cases
import user_files
from keyboards import HISTORY_MENU_TEXT
from panel_sync import get_user_cases

logger = logging.getLogger(__name__)

history_router = Router()

SERVICE_LABELS = {
    "INQUIRY": "استعلام",
    "LAVAYEH": "لایحه",
    "EZHHARNAMEH": "اظهارنامه",
    "EALAM_VAKALAHT": "اعلام وکالت",
    "TAJDID_NAZAR": "دعاوی اعتراضی",
    "CHECK": "دادخواست",
    "STAMP_CALC": "محاسبه تمبر",
    "REGIONAL_VALUE": "ارزش منطقه‌ای",
    "CONTRACT_FIX": "اصلاح قرارداد",
}

STATUS_LABELS = {
    "PENDING_PAYMENT": "⏳ در انتظار پرداخت",
    "INCOMPLETE": "⚠️ ناقص",
    "PROCESSING": "🔄 در حال ثبت",
    "READY_TO_SEND": "📤 آمادهٔ ارسال",
    "COMPLETED": "✅ انجام شد",
    "FAILED": "❌ ناموفق",
    "CANCELLED": "🚫 لغو شده",
}

FEE_LABELS = {"PAID": "پرداخت شده", "MANUAL_APPROVED": "پرداخت شده", "UNPAID": "پرداخت نشده"}

_MENU_KB = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="📋 درخواست‌های اخیر", callback_data="hist:cases")],
    [InlineKeyboardButton(text="📎 فایل‌های ارسالی", callback_data="hist:files")],
])


def _fa_date(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
        dt = dt.astimezone(datetime.timezone(datetime.timedelta(hours=3, minutes=30)))
        try:
            import jdatetime
            j = jdatetime.date.fromgregorian(date=dt.date())
            return f"{j.year}/{j.month:02d}/{j.day:02d}"
        except ImportError:
            from regional_value_pdf import _gregorian_to_jalali
            y, m, d = _gregorian_to_jalali(dt.year, dt.month, dt.day)
            return f"{y}/{m:02d}/{d:02d}"
    except Exception:
        return iso[:10]


def format_case(c: dict) -> str:
    service = SERVICE_LABELS.get(c.get("serviceType"), c.get("serviceType") or "—")
    title = c.get("title") or c.get("subCategory") or c.get("documentCategory") or ""
    head = f"🔹 *{service}*" + (f" — {title}" if title and title != service else "")
    lines = [head, f"📅 {_fa_date(c.get('createdAt'))}"]
    if c.get("trackingCode"):
        lines.append(f"🔢 کد رهگیری: {c['trackingCode']}")
    lines.append(f"وضعیت: {STATUS_LABELS.get(c.get('status'), c.get('status') or '—')}")
    total = int(c.get("fee") or 0) + int(c.get("prepayAmount") or 0)
    if total:
        fee_state = FEE_LABELS.get(c.get("feeStatus"), "")
        lines.append(f"💳 مبلغ: {total:,} تومان" + (f" ({fee_state})" if fee_state else ""))
    return "\n".join(lines)


@history_router.message(StateFilter("*"), F.text == HISTORY_MENU_TEXT)
async def history_entry(message: Message, state: FSMContext):
    await message.answer("📂 *سوابق و فاکتورهای من*\n\nکدام بخش را می‌خواهید ببینید؟", reply_markup=_MENU_KB)


@history_router.callback_query(F.data == "hist:cases")
async def history_cases(callback: CallbackQuery):
    await callback.answer()
    cases = await get_user_cases(callback.from_user.id, limit=10)
    if cases is None:
        await callback.message.answer("⚠️ دریافت سوابق در حال حاضر ممکن نیست. لطفاً کمی بعد دوباره تلاش کنید.")
        return
    if not cases:
        await callback.message.answer("📭 هنوز درخواستی از شما ثبت نشده است.")
        return
    body = "\n\n".join(format_case(c) for c in cases)
    rows = []
    for c in cases:
        if print_category(callback.from_user.id, c):
            service = SERVICE_LABELS.get(c.get("serviceType"), c.get("serviceType") or "")
            rows.append([InlineKeyboardButton(
                text=f"📄 چاپ PDF — {service} {c['trackingCode']}"[:60],
                callback_data=f"hist:print:{c['trackingCode']}")])
    if rows:
        body += "\n\n📄 برای دریافت دوبارهٔ چاپ PDF روی پرونده بزنید:"
    await callback.message.answer(
        f"📋 *{len(cases)} درخواست اخیر شما*\n\n{body}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows) if rows else None)


def print_category(user_id: int, c: dict):
    """(doc_category, doc_subcategory) منوی استعلام برای چاپ دوبارهٔ یک پرونده؛
    None برای استعلام‌ها، پرونده بدون کد رهگیری یا دسته‌بندی نامشخص."""
    tc = str(c.get("trackingCode") or "")
    svc = c.get("serviceType") or ""
    if not tc or svc in ("INQUIRY", "ADMIN_SEND"):
        return None
    # ۱) دفترهای خود ربات — دسته‌بندی دقیق هنگام ثبت ذخیره شده
    cat = pending_cases.print_category(user_id, tc) or final_print.queued_category(user_id, tc)
    if cat and cat[0]:
        return cat
    # ۲) پرونده‌های قدیمی‌تر — از نوع سرویس پنل (چک بدون مسیر منو حدس زده نمی‌شود)
    if svc == "TAJDID_NAZAR":
        case_type = (c.get("documentCategory") or "").split("—")[0].strip()
        if case_type not in final_print._OBJECTION_SUB_MENUS:
            return None
        return final_print.category_for(svc, case_type=case_type)
    if svc in ("LAVAYEH", "EZHHARNAMEH", "EALAM_VAKALAHT"):
        return final_print.category_for(svc)
    return None


@history_router.callback_query(F.data.startswith("hist:print:"))
async def history_print(callback: CallbackQuery):
    user_id = callback.from_user.id
    tc = callback.data.split(":", 2)[2]
    cases = await get_user_cases(user_id, limit=30)
    case = next((c for c in (cases or []) if str(c.get("trackingCode") or "") == tc), None)
    cat = print_category(user_id, case) if case else (
        pending_cases.print_category(user_id, tc) or final_print.queued_category(user_id, tc))
    if not cat or not cat[0]:
        await callback.answer("چاپ این پرونده قابل دریافت نیست.", show_alert=True)
        return
    await callback.answer()
    from pending_cases_handlers import send_print_request
    await send_print_request(callback.message, user_id, tc, cat)


@history_router.callback_query(F.data == "hist:files")
async def history_files(callback: CallbackQuery):
    await callback.answer()
    items = user_files.recent(callback.from_user.id, limit=10)
    if not items:
        await callback.message.answer("📭 فایلی در سوابق شما ثبت نشده است.")
        return
    rows = []
    for idx, item in enumerate(items):
        name = item.get("filename") or "فایل"
        label = f"📄 {_fa_date(item.get('sent_at'))} — {name}"[:60]
        rows.append([InlineKeyboardButton(text=label, callback_data=f"hist:file:{idx}")])
    await callback.message.answer(
        "📎 *فایل‌های ارسالی اخیر*\nبرای دریافت دوباره روی هر فایل بزنید:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@history_router.callback_query(F.data.startswith("hist:file:"))
async def history_file_resend(callback: CallbackQuery):
    try:
        idx = int(callback.data.rsplit(":", 1)[1])
    except ValueError:
        await callback.answer()
        return
    items = user_files.recent(callback.from_user.id, limit=10)
    if idx >= len(items):
        await callback.answer("این فایل دیگر در سوابق نیست.", show_alert=True)
        return
    await callback.answer()
    item = items[idx]
    try:
        await callback.message.answer_document(item["file_id"], caption=item.get("caption") or None)
    except Exception as e:
        logger.warning(f"[HISTORY] ارسال دوبارهٔ فایل ناموفق: {e}")
        await callback.message.answer("⚠️ ارسال دوبارهٔ این فایل ممکن نشد.")
