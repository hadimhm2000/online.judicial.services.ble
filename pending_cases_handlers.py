"""
هندلرهای بخش «🖊 پرونده‌های در انتظار امضا و پرداخت» — گزینهٔ مستقل منوی اصلی.

  - فهرست پرونده‌های بدون امضای کاربر (pending_cases.open_cases)؛ لایحه و اعلام
    وکالت ۴ روز، سایر موارد ۳۰ روز
  - هر پرونده: 💳 پرداخت هزینه (اگر پرداخت نشده) / 🖊 درج امضا (فقط پس از پرداخت)
    / 📄 دریافت چاپ PDF
  - پرداخت با فاکتور payload {"type": "pending_case", "tc": ...}؛ پس از پرداخت
    همان هندلرهای موجود (lavayeh_successful_payment / tn_successful_payment)
    اجرا می‌شوند تا روند امضا دقیقاً مثل قبل ادامه یابد.

این روتر در bot.py قبل از روتر اصلی ثبت می‌شود (مثل history_router).
"""
import datetime
import json
import logging

import aiohttp
from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import final_print
import pending_cases
import runtime_state
from config import ADMIN_ID, BALE_API_BASE, BALE_SSL_CONTEXT, BALE_WALLET_TOKEN, BOT_TOKEN
from keyboards import PENDING_CASES_MENU_TEXT

logger = logging.getLogger(__name__)

pending_router = Router()

PAYLOAD_TYPE = "pending_case"

SERVICE_LABELS = {
    "LAVAYEH": "لایحه",
    "EZHHARNAMEH": "اظهارنامه",
    "EALAM_VAKALAHT": "اعلام وکالت",
    "TAJDID_NAZAR": "دعاوی اعتراضی",
    "CHECK": "دادخواست",
    "CONTRACT_FIX": "اصلاح قرارداد",
}

MAX_LIST = 20

# در این stateها کاربر وسط روند امضای پرونده‌ای است؛ شروع روند دیگر آن را خراب می‌کند
_SIGN_STATE_MARKERS = ("_sign_",)


def _label(it: dict) -> str:
    return SERVICE_LABELS.get(it.get("service_type"), it.get("service_type") or "پرونده")


def _fa_date(iso: str | None) -> str:
    try:
        from history_handlers import _fa_date as _hist_fa_date
        return _hist_fa_date(iso)
    except Exception:
        return (iso or "—")[:10]


async def _busy_with_sign(state: FSMContext) -> bool:
    raw = await state.get_state() or ""
    return any(m in raw for m in _SIGN_STATE_MARKERS)


_BUSY_TEXT = ("⏳ شما در حال حاضر در روند امضای پرونده‌ای هستید.\n"
              "لطفاً ابتدا همان امضا را تکمیل کنید، سپس از این بخش ادامه دهید.")


# ───────────────────────── فهرست پرونده‌ها ─────────────────────────

@pending_router.message(StateFilter("*"), F.text == PENDING_CASES_MENU_TEXT)
async def pending_entry(message: Message, state: FSMContext):
    user_id = message.from_user.id
    await pending_cases.sync_with_panel(user_id)
    items = pending_cases.open_cases(user_id)
    if not items:
        await message.answer("📭 پرونده‌ای در انتظار امضا یا پرداخت ندارید.")
        return
    rows = []
    for it in items[:MAX_LIST]:
        icon = "🖊" if it.get("paid") else "💳"
        text = f"{icon} {_label(it)} — {it['tracking_code']}"
        rows.append([InlineKeyboardButton(text=text[:60], callback_data=f"pc:v:{it['tracking_code']}")])
    await message.answer(
        "🖊 *پرونده‌های در انتظار امضا و پرداخت*\n\n"
        "💳 هزینه پرداخت نشده  |  🖊 پرداخت شده، در انتظار درج امضا\n\n"
        f"ℹ️ لایحه و اعلام وکالت {pending_cases.SHORT_VISIBLE_DAYS} روز و سایر موارد "
        f"{pending_cases.VISIBLE_DAYS} روز در این بخش می‌مانند.\n"
        "برای ادامهٔ مراحل روی پرونده بزنید:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


def _detail(it: dict) -> tuple[str, InlineKeyboardMarkup]:
    tc = it["tracking_code"]
    lines = [f"🔹 *{_label(it)}*" + (f" — {it['title']}" if it.get("title") else ""),
             f"🔢 کد رهگیری: `{tc}`",
             f"📅 ثبت: {_fa_date(it.get('registered_at'))}"]
    rows = []
    if it.get("paid"):
        lines.append("💳 هزینه: ✅ پرداخت شده")
        lines.append("🖊 امضا: ⏳ درج نشده")
        rows.append([InlineKeyboardButton(text="🖊 درج امضا", callback_data=f"pc:sign:{tc}")])
    else:
        fee_toman = int(it.get("final_fee") or 0) // 10
        lines.append(f"💳 هزینه: ⏳ پرداخت نشده ({fee_toman:,} تومان)")
        lines.append("🖊 امضا: پس از پرداخت هزینه فعال می‌شود")
        rows.append([InlineKeyboardButton(text=f"💳 پرداخت هزینه ({fee_toman:,} تومان)",
                                          callback_data=f"pc:pay:{tc}")])
        rows.append([InlineKeyboardButton(text="🔒 درج امضا (پس از پرداخت)", callback_data="pc:lock")])
    try:
        reg = datetime.datetime.fromisoformat(it.get("registered_at") or "")
        days = pending_cases.visible_days(it.get("service_type"))
        lines.append(f"⏳ تا {_fa_date((reg + datetime.timedelta(days=days)).isoformat())} در این بخش می‌ماند.")
    except ValueError:
        pass
    if it.get("doc_category"):
        rows.append([InlineKeyboardButton(text="📄 دریافت چاپ PDF", callback_data=f"pc:print:{tc}")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


@pending_router.callback_query(F.data.startswith("pc:v:"))
async def pending_view(callback: CallbackQuery):
    tc = callback.data.split(":", 2)[2]
    it = pending_cases.is_open(callback.from_user.id, tc)
    if not it:
        await callback.answer("این پرونده دیگر در انتظار امضا یا پرداخت نیست.", show_alert=True)
        return
    await callback.answer()
    text, kb = _detail(it)
    await callback.message.answer(text, reply_markup=kb)


@pending_router.callback_query(F.data == "pc:lock")
async def pending_sign_locked(callback: CallbackQuery):
    await callback.answer("🔒 درج امضا فقط پس از پرداخت هزینهٔ همین پرونده فعال می‌شود.", show_alert=True)


# ───────────────────────── پرداخت ─────────────────────────

async def _send_invoice(bot: Bot, it: dict) -> str:
    """فاکتور پرونده؛ خروجی "gateway" | "card" | "" (خطا)."""
    user_id = it["user_id"]
    amount = int(it.get("final_fee") or 0)
    label = _label(it)
    invoice_data = {
        "chat_id": user_id,
        "title": f"فاکتور {label}",
        "description": (f"هزینه خدمات {label} — کد رهگیری {it['tracking_code']}\n"
                        f"مبلغ: {amount // 10:,} تومان ({amount:,} ریال)"),
        "payload": json.dumps({"type": PAYLOAD_TYPE, "uid": user_id, "tc": it["tracking_code"]}),
        "provider_token": BALE_WALLET_TOKEN,
        "currency": "IRR",
        "prices": [{"label": label, "amount": amount}],
    }
    try:
        from wallet import prepare_invoice as _wl_prep
        invoice_data = _wl_prep(invoice_data)  # ⭐ کسر خودکار موجودی کیف پول
        # ⭐ همان قاعدهٔ فاکتور اصلی: دادخواست (چک) و دعاوی اعتراضی بالای سقف → فقط کارت‌به‌کارت
        from card_payment import card_only_required as _cp_card_only
        if (it.get("kind") == pending_cases.KIND_TN or it.get("service_type") == "CHECK") \
                and _cp_card_only(invoice_data):
            from card_payment import track_card_only_invoice as _cp_track_card
            _cp_track_card(invoice_data)
            return "card"
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=BALE_SSL_CONTEXT)) as session:
            async with session.post(f"{BALE_API_BASE}/bot{BOT_TOKEN}/sendInvoice", json=invoice_data) as resp:
                result = await resp.json()
        if not result.get("ok"):
            logger.error(f"[PENDING_CASES] خطای sendInvoice: {result}")
            return ""
        from card_payment import track_invoice as _cp_track
        _cp_track(invoice_data)  # ⭐ کارت‌به‌کارت پس از ۲۰ دقیقه
        return "gateway"
    except Exception as e:
        logger.error(f"[PENDING_CASES] خطا در ارسال فاکتور: {e}", exc_info=True)
        return ""


@pending_router.callback_query(F.data.startswith("pc:pay:"))
async def pending_pay(callback: CallbackQuery, state: FSMContext, bot: Bot):
    tc = callback.data.split(":", 2)[2]
    it = pending_cases.is_open(callback.from_user.id, tc)
    if not it:
        await callback.answer("این پرونده دیگر در انتظار پرداخت نیست.", show_alert=True)
        return
    if it.get("paid"):
        await callback.answer("هزینهٔ این پرونده قبلاً پرداخت شده است؛ «درج امضا» را بزنید.", show_alert=True)
        return
    if await _busy_with_sign(state):
        await callback.answer(_BUSY_TEXT, show_alert=True)
        return
    if int(it.get("final_fee") or 0) <= 0:
        await callback.answer("مبلغ این پرونده نامشخص است؛ لطفاً با پشتیبانی تماس بگیرید.", show_alert=True)
        return
    await callback.answer()
    sent = await _send_invoice(bot, it)
    if sent == "card":
        await callback.message.answer(
            "⏳ مشخصات کارت برای واریز ارسال می‌شود.\n\n"
            "پس از تایید رسید توسط پشتیبانی، مرحلهٔ درج امضا به‌صورت خودکار آغاز می‌شود.")
    elif sent:
        await callback.message.answer(
            "⏳ فاکتور پرداخت ارسال شد.\n\n"
            "پس از پرداخت موفق، مرحلهٔ درج امضا به‌صورت خودکار آغاز می‌شود.")
    else:
        await callback.message.answer("⚠️ خطا در ساخت فاکتور پرداخت. لطفاً کمی بعد دوباره تلاش کنید.")


def _is_pending_case_payment(message: Message) -> bool:
    sp = message.successful_payment
    if not sp:
        return False
    try:
        return json.loads(sp.invoice_payload or "{}").get("type") == PAYLOAD_TYPE
    except Exception:
        return False


@pending_router.message(_is_pending_case_payment)
async def pending_case_successful_payment(message: Message, state: FSMContext, bot: Bot):
    """پرداخت فاکتور پرونده — dict همان فاکتور بازسازی و هندلر پرداخت موجود صدا زده می‌شود."""
    user_id = message.from_user.id
    payload = json.loads(message.successful_payment.invoice_payload or "{}")
    tc = str(payload.get("tc") or "")
    it = pending_cases.get(user_id, tc)
    if not it:
        logger.error(f"[PENDING_CASES] پرداخت پرونده‌ای که در دفتر نیست: user={user_id} tc={tc}")
        await message.answer("✅ پرداخت شما دریافت شد.\n⚠️ اطلاعات پرونده یافت نشد؛ به مدیریت اطلاع داده شد.")
        try:
            await bot.send_message(
                ADMIN_ID,
                f"⚠️ [PENDING_CASES] پرداخت بدون پرونده — کاربر {user_id} — کد {tc} — "
                f"charge_id={message.successful_payment.telegram_payment_charge_id}")
        except Exception:
            pass
        return

    if it.get("kind") == pending_cases.KIND_TN:
        store = runtime_state.pending_tn_payments
        from tajdid_nazar_handlers import tn_successful_payment as _handler
    else:
        store = runtime_state.pending_lavayeh_payments
        from lavayeh_handlers import lavayeh_successful_payment as _handler

    # فاکتور باز دیگری که کاربر همین حالا دارد نباید گم شود
    prev = store.get(user_id)
    store[user_id] = pending_cases.payment_context(it)
    try:
        await _handler(message, state, bot)
    finally:
        if prev and str(prev.get("tracking_code")) != tc and user_id not in store:
            store[user_id] = prev
    pending_cases.mark_paid(user_id, tc)


# ───────────────────────── درج امضا ─────────────────────────

@pending_router.callback_query(F.data.startswith("pc:sign:"))
async def pending_sign(callback: CallbackQuery, state: FSMContext, bot: Bot):
    user_id = callback.from_user.id
    tc = callback.data.split(":", 2)[2]
    it = pending_cases.is_open(user_id, tc)
    if not it:
        await callback.answer("این پرونده دیگر در انتظار امضا نیست.", show_alert=True)
        return
    if not it.get("paid"):
        await callback.answer("🔒 درج امضا فقط پس از پرداخت هزینهٔ همین پرونده فعال می‌شود.", show_alert=True)
        return
    if await _busy_with_sign(state):
        await callback.answer(_BUSY_TEXT, show_alert=True)
        return
    await callback.answer()
    ctx = it.get("ctx") or {}
    try:
        if it.get("kind") == pending_cases.KIND_TN:
            from tajdid_nazar_handlers import _tn_start_sign_flow
            await _tn_start_sign_flow(bot, user_id, tc, ctx.get("case_type", ""),
                                      ctx.get("tn_persons") or [])
        else:
            from lavayeh_handlers import _go_to_sign_flow_after_prepaid
            await _go_to_sign_flow_after_prepaid(
                bot, user_id, bool(ctx.get("is_ezhharnameh")),
                ctx.get("lavayeh_title", "لایحه دفاعیه"), ctx.get("lavayeh_province", ""),
                ctx.get("lavayeh_row_number", 1), ctx.get("lavayeh_persons") or [],
                tc, ctx.get("national_ids", ""), int(ctx.get("court_total") or 0),
                service_type=it.get("service_type"), sign_menu_path=ctx.get("sign_menu_path"))
    except Exception as e:
        logger.error(f"[PENDING_CASES] خطا در شروع امضا برای {tc}: {e}", exc_info=True)
        await callback.message.answer("⚠️ شروع روند امضا ممکن نشد. لطفاً کمی بعد دوباره تلاش کنید.")


# ───────────────────────── چاپ PDF ─────────────────────────

async def send_print_request(message: Message, user_id: int, tracking_code: str, category) -> None:
    """درخواست چاپ PDF همین حالا (مشترک با «سوابق»)."""
    doc_category, doc_subcategory = category
    ok = await final_print.request_print(user_id, tracking_code, doc_category, doc_subcategory)
    if not ok:
        await message.answer("⏳ درخواست چاپ این پرونده قبلاً ثبت شده و در حال آماده‌سازی است.")
        return
    try:
        import sana_gate
        import working_hours
        is_open = sana_gate.is_open()
        next_start = working_hours.next_start_label()
    except Exception:
        is_open, next_start = True, ""
    if is_open:
        await message.answer("⏳ چاپ PDF در حال آماده‌سازی است و به‌زودی برایتان ارسال می‌شود.")
    else:
        await message.answer(
            "⏳ درخواست چاپ PDF ثبت شد.\n"
            f"سامانهٔ قضایی الان در دسترس نیست؛ چاپ پس از شروع ساعت کاری ({next_start}) ارسال می‌شود.")


@pending_router.callback_query(F.data.startswith("pc:print:"))
async def pending_print(callback: CallbackQuery):
    user_id = callback.from_user.id
    tc = callback.data.split(":", 2)[2]
    cat = pending_cases.print_category(user_id, tc) or final_print.queued_category(user_id, tc)
    if not cat or not cat[0]:
        await callback.answer("چاپ این پرونده از این بخش قابل دریافت نیست.", show_alert=True)
        return
    await callback.answer()
    await send_print_request(callback.message, user_id, tc, cat)
