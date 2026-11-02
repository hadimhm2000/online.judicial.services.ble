"""
clearance_handlers.py — بخش «درخواست گواهی عدم سوءپیشینه» (گزینهٔ منوی اصلی، ۱۴۰۵/۰۷)
══════════════════════════════════════════════════════════════════════════════

جریان کاربر:
  ۱. کدملی → تاریخ تولد → توضیحات → پیش‌نمایش (تایید / ویرایش)
  ۲. پرداخت ۱۵۰,۰۰۰ تومان (فاکتور بله / کیف پول / کارت‌به‌کارت) — کاربران معاف بدون فاکتور
  ۳. تسک «ارسال رمز موقت» در نوبت (job_queue) → «۷ دقیقه فرصت دارید کد را بفرستید»
  ۴. کاربر کد ۵ رقمی را می‌فرستد → ⭐ خارج از نوبت: ورود کد، دریافت مشخصات از ثنا،
     ثبت موقت، محاسبه هزینه → شناسهٔ پرداخت *فقط برای مدیر* + دکمهٔ «✅ پرداخت کردم»
  ۵. مدیر «پرداخت کردم» → تسک در نوبت: جستجو، تایید نهایی، چاپ رسید → ارسال چاپ به
     کاربر + «نتیجه طی روزهای آتی به سامانه ابلاغ شما پیامک خواهد شد»

خطاها:
  - «اطلاعاتی بااین شماره ملی وتاریخ تولد پیدا نشد» → ۴۵ دقیقه مهلت ویرایش کدملی و
    تاریخ تولد؛ پس از پایان مهلت درخواست لغو و ۵۰٪ مبلغ به کیف پول برمی‌گردد.
  - «زمان اعتبار رمز موقت منقضی شده است» → ۳۰ دقیقه بعد رمز موقت دوباره ارسال می‌شود.
  - خطای پایدار هر مرحله → اطلاع به مدیر با دکمهٔ «🔁 تلاش مجدد» همان مرحله.

سود: از ۱۵۰,۰۰۰ تومان، ۴۲,۰۰۰ تومان هزینهٔ سامانه و ۱۰۸,۰۰۰ تومان سود است — پرونده
با serviceType=CLEARANCE_CERT، fee=150000، systemCost=42000 در پنل ثبت می‌شود.

وضعیت درخواست‌ها در data/clearance_requests.json ماندگار است (کرش/ری‌استارت).
"""
import asyncio
import datetime
import json
import logging
import os
import secrets
import time

import aiohttp
from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, Message,
    ReplyKeyboardMarkup)

import runtime_state
from config import ADMIN_ID, BALE_API_BASE, BALE_SSL_CONTEXT, BALE_WALLET_TOKEN, BOT_TOKEN
from damages_calc import parse_jalali_date
from id_validation import is_valid_national_id, normalize_digits
from nid_fix_window import duration_adj, duration_label
from keyboards import BACK_TO_MAIN_TEXT, CLEARANCE_MENU_TEXT, get_flow_type_kb
from states import Form

logger = logging.getLogger(__name__)

clearance_router = Router()

SERVICE_TYPE = "CLEARANCE_CERT"
SERVICE_LABEL = "گواهی عدم سوءپیشینه"
FEE_TOMAN = 150_000
SITE_COST_TOMAN = 42_000          # سود = ۱۰۸,۰۰۰ تومان
CODE_WINDOW_MINUTES = 7
FIX_WINDOW_MINUTES = 180  # مهلت اصلاح اطلاعات (۳ ساعت)
RESEND_AFTER_MINUTES = 30
TIMEOUT_REFUND_PERCENT = 50       # لغو پس از پایان مهلت ویرایش کدملی

STORE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "clearance_requests.json")

CONFIRM_TEXT = "✅ تایید و پرداخت"
EDIT_TEXT = "✏️ ویرایش اطلاعات"

# وضعیت‌ها
ST_AWAIT_PAY = "awaiting_payment"
ST_QUEUED = "queued_send"
ST_SENDING = "sending_code"
ST_WAIT_CODE = "waiting_code"
ST_CHECK_CODE = "checking_code"
ST_FIX = "fix_nid"
ST_RESEND = "resend_wait"
ST_REGISTER = "registering"
ST_ADMIN_PAY = "waiting_admin_pay"
ST_FINALIZE = "finalizing"
ST_ERROR = "error"
ST_DONE = "done"
ST_CANCELLED = "cancelled"
_CLOSED = (ST_DONE, ST_CANCELLED)

_store: dict = {}
_loaded = False
_loop_started = False


# ════════════════════════════════════════════════════════════════════════════
# ذخیره‌سازی
# ════════════════════════════════════════════════════════════════════════════

def _load():
    global _store, _loaded
    _loaded = True
    try:
        if os.path.exists(STORE_FILE):
            with open(STORE_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f) or {}
            _store = {k: v for k, v in raw.items() if isinstance(v, dict)}
    except Exception as e:
        logger.error(f"[CLEARANCE] خطا در بارگذاری {STORE_FILE}: {e}", exc_info=True)
        _store = {}


def _save():
    try:
        os.makedirs(os.path.dirname(STORE_FILE), exist_ok=True)
        tmp = STORE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_store, f, ensure_ascii=False, indent=1)
        os.replace(tmp, STORE_FILE)
    except Exception as e:
        logger.error(f"[CLEARANCE] خطا در ذخیرهٔ {STORE_FILE}: {e}", exc_info=True)


def _requests() -> dict:
    if not _loaded:
        _load()
    return _store


def get_request(rid) -> dict | None:
    return _requests().get(rid) if rid else None


def _update(rid: str, **fields) -> dict | None:
    req = _requests().get(rid)
    if req is None:
        return None
    req.update(fields)
    req["updated_at"] = time.time()
    _save()
    return req


def active_request(uid: int) -> dict | None:
    """درخواست پرداخت‌شده و باز کاربر (حداکثر یکی)."""
    for req in _requests().values():
        if req.get("uid") == uid and req.get("paid") and req.get("status") not in _CLOSED:
            return req
    return None


# ════════════════════════════════════════════════════════════════════════════
# کیبوردها و پیام‌ها
# ════════════════════════════════════════════════════════════════════════════

_back_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=BACK_TO_MAIN_TEXT)]], resize_keyboard=True)
_confirm_kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text=CONFIRM_TEXT)],
    [KeyboardButton(text=EDIT_TEXT)],
    [KeyboardButton(text=BACK_TO_MAIN_TEXT)],
], resize_keyboard=True)


def _admin_kb(rid: str, paid_button: bool = False, retry: bool = False) -> InlineKeyboardMarkup:
    rows = []
    if paid_button:
        rows.append([InlineKeyboardButton(text="✅ پرداخت کردم", callback_data=f"clr:paid:{rid}")])
    if retry:
        rows.append([InlineKeyboardButton(text="🔁 تلاش مجدد همین مرحله", callback_data=f"clr:retry:{rid}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _fmt_birth(t: tuple) -> str:
    return f"{t[0]:04d}/{t[1]:02d}/{t[2]:02d}"


def _summary(nid: str, birth: str, desc: str) -> str:
    return (
        f"📜 *{SERVICE_LABEL}*\n\n"
        f"🆔 کدملی: `{nid}`\n"
        f"🎂 تاریخ تولد: {birth}\n"
        f"📝 توضیحات: {desc}\n\n"
        f"💳 هزینه: *{FEE_TOMAN:,} تومان*"
    )


def _who(req: dict) -> str:
    return f"{req.get('full_name') or ''} (آیدی {req.get('uid')}) — کدملی {req.get('nid')}"


async def _notify_admin(bot: Bot, text: str, reply_markup=None):
    try:
        await bot.send_message(ADMIN_ID, text, reply_markup=reply_markup)
    except Exception as e:
        logger.warning(f"[CLEARANCE] ارسال پیام به مدیر ناموفق: {e}")


async def _notify_user(bot: Bot, uid: int, text: str, reply_markup=None):
    try:
        await bot.send_message(uid, text, reply_markup=reply_markup)
    except Exception as e:
        logger.warning(f"[CLEARANCE] ارسال پیام به کاربر {uid} ناموفق: {e}")


async def _set_user_state(bot: Bot, uid: int, state, data: dict | None = None):
    dp = runtime_state.dp
    if dp is None:
        return
    try:
        ctx = dp.fsm.resolve_context(bot, uid, uid)
        await ctx.set_state(state)
        if data is not None:
            await ctx.set_data(data)
    except Exception as e:
        logger.warning(f"[CLEARANCE] تنظیم state کاربر {uid} ناموفق: {e}")


async def _back_to_main(message: Message, state: FSMContext, text: str = "❓ *لطفاً نحوه ثبت درخواست خود را انتخاب فرمایید:*"):
    await state.clear()
    await message.answer(text, reply_markup=get_flow_type_kb(message.from_user.id))
    await state.set_state(Form.waiting_for_flow_type)


def _enqueue(job: dict) -> int:
    pos = runtime_state.job_queue.qsize()
    runtime_state.job_queue.put_nowait(job)
    return pos


def _enqueue_send_code(rid: str, uid: int) -> int:
    _update(rid, status=ST_QUEUED, failed_phase=None)
    return _enqueue({"task_type": "CLEARANCE_SEND_CODE", "user_id": uid, "rid": rid})


# ════════════════════════════════════════════════════════════════════════════
# ورود و دریافت اطلاعات
# ════════════════════════════════════════════════════════════════════════════

@clearance_router.message(StateFilter("*"), F.text == CLEARANCE_MENU_TEXT)
async def clearance_entry(message: Message, state: FSMContext):
    uid = message.from_user.id
    req = active_request(uid)
    if req:
        await state.clear()
        status = req.get("status")
        if status == ST_WAIT_CODE:
            await state.set_state(Form.clr_waiting_code)
            await state.update_data(clr_rid=req["rid"])
            await message.answer(
                "🔐 درخواست قبلی شما منتظر *رمز موقت* است.\n"
                "لطفاً کد ۵ رقمی پیامک‌شده را ارسال کنید:", reply_markup=_back_kb)
            return
        if status == ST_FIX:
            await state.set_state(Form.clr_fix_nid)
            await state.update_data(clr_rid=req["rid"])
            await message.answer("✏️ لطفاً *کدملی* صحیح را وارد کنید:", reply_markup=_back_kb)
            return
        await message.answer(
            f"⏳ درخواست {SERVICE_LABEL} شما در حال انجام است؛ نتیجه به همین‌جا ارسال می‌شود.",
            reply_markup=get_flow_type_kb(uid))
        await state.set_state(Form.waiting_for_flow_type)
        return
    await state.clear()
    await state.set_state(Form.clr_waiting_nid)
    await message.answer(
        f"📜 *{SERVICE_LABEL}*\n\n"
        f"💳 هزینه: {FEE_TOMAN:,} تومان\n\n"
        "🆔 *کدملی* متقاضی را وارد کنید:", reply_markup=_back_kb)


def _is_back(message: Message) -> bool:
    return (message.text or "").strip() == BACK_TO_MAIN_TEXT


def _parse_nid(text: str) -> str | None:
    value = normalize_digits((text or "").strip())
    return value if is_valid_national_id(value) else None


def _parse_birth(text: str) -> str | None:
    t = parse_jalali_date(text or "")
    if not t or not (1290 <= t[0] <= 1410):
        return None
    return _fmt_birth(t)


_NID_ERROR = "⚠️ کدملی معتبر نیست. لطفاً کدملی ۱۰ رقمی صحیح را وارد کنید:"
_BIRTH_PROMPT = "🎂 *تاریخ تولد* را به شمسی وارد کنید:\n_(مثال: 1370/05/12)_"
_BIRTH_ERROR = "⚠️ تاریخ تولد معتبر نیست. لطفاً به شکل 1370/05/12 وارد کنید:"


@clearance_router.message(Form.clr_waiting_nid)
async def clr_nid(message: Message, state: FSMContext):
    if _is_back(message):
        await _back_to_main(message, state)
        return
    nid = _parse_nid(message.text)
    if not nid:
        await message.answer(_NID_ERROR, reply_markup=_back_kb)
        return
    await state.update_data(clr_nid=nid)
    await state.set_state(Form.clr_waiting_birth)
    await message.answer(_BIRTH_PROMPT, reply_markup=_back_kb)


@clearance_router.message(Form.clr_waiting_birth)
async def clr_birth(message: Message, state: FSMContext):
    if _is_back(message):
        await _back_to_main(message, state)
        return
    birth = _parse_birth(message.text)
    if not birth:
        await message.answer(_BIRTH_ERROR, reply_markup=_back_kb)
        return
    await state.update_data(clr_birth=birth)
    await state.set_state(Form.clr_waiting_desc)
    await message.answer(
        "📝 *توضیحات* درخواست را بنویسید:\n"
        "_(مثلاً مرجع یا دلیل ارائهٔ گواهی)_", reply_markup=_back_kb)


@clearance_router.message(Form.clr_waiting_desc)
async def clr_desc(message: Message, state: FSMContext):
    if _is_back(message):
        await _back_to_main(message, state)
        return
    desc = (message.text or "").strip()
    if len(desc) < 3:
        await message.answer("⚠️ لطفاً توضیحات را به‌صورت متن (حداقل ۳ حرف) بنویسید:", reply_markup=_back_kb)
        return
    desc = desc[:500]
    await state.update_data(clr_desc=desc)
    data = await state.get_data()
    await state.set_state(Form.clr_confirm)
    await message.answer(
        _summary(data["clr_nid"], data["clr_birth"], desc) + "\n\nدر صورت صحت اطلاعات، تایید و پرداخت کنید:",
        reply_markup=_confirm_kb)


@clearance_router.message(Form.clr_confirm)
async def clr_confirm(message: Message, state: FSMContext, bot: Bot):
    text = (message.text or "").strip()
    if text == BACK_TO_MAIN_TEXT:
        await _back_to_main(message, state)
        return
    if text == EDIT_TEXT:
        await state.set_state(Form.clr_waiting_nid)
        await message.answer("🆔 *کدملی* متقاضی را وارد کنید:", reply_markup=_back_kb)
        return
    if text != CONFIRM_TEXT:
        await message.answer("لطفاً یکی از گزینه‌های زیر را انتخاب کنید:", reply_markup=_confirm_kb)
        return
    uid = message.from_user.id
    if active_request(uid):
        await _back_to_main(message, state, f"⏳ یک درخواست {SERVICE_LABEL} شما هنوز در حال انجام است.")
        return
    data = await state.get_data()
    rid = f"CLR{secrets.token_hex(4).upper()}"
    _requests()[rid] = {
        "rid": rid, "uid": uid, "full_name": message.from_user.full_name,
        "nid": data["clr_nid"], "birth": data["clr_birth"], "desc": data["clr_desc"],
        "status": ST_AWAIT_PAY, "paid": False, "paid_toman": 0,
        "created_at": time.time(), "updated_at": time.time(),
    }
    _save()

    from exempt_users import is_exempt_user
    if await is_exempt_user(uid):
        await state.clear()
        await _start_after_payment(bot, rid, paid_toman=0, exempt=True)
        return
    await _send_invoice(message, state, rid)


async def _send_invoice(message: Message, state: FSMContext, rid: str):
    uid = message.from_user.id
    fee_rial = FEE_TOMAN * 10
    try:
        invoice_data = {
            "chat_id": uid,
            "title": f"درخواست {SERVICE_LABEL}",
            "description": f"هزینهٔ ثبت درخواست {SERVICE_LABEL}: {FEE_TOMAN:,} تومان ({fee_rial:,} ریال)",
            "payload": json.dumps({"type": "clearance", "rid": rid, "uid": uid, "tracking_code": rid}),
            "provider_token": BALE_WALLET_TOKEN,
            "currency": "IRR",
            "prices": [{"label": f"درخواست {SERVICE_LABEL}", "amount": fee_rial}],
        }
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=BALE_SSL_CONTEXT)) as session:
            from wallet import prepare_invoice as _wl_prep; invoice_data = _wl_prep(invoice_data)  # ⭐ کسر خودکار موجودی کیف پول
            async with session.post(f"{BALE_API_BASE}/bot{BOT_TOKEN}/sendInvoice", json=invoice_data) as resp:
                result = await resp.json()
        logger.info(f"[CLEARANCE] sendInvoice user={uid} rid={rid}: {result}")
        if not result.get("ok"):
            raise Exception(result.get("description", "خطا در ارسال فاکتور"))
        from card_payment import track_invoice as _cp_track
        _cp_track(invoice_data)  # کارت‌به‌کارت پس از ۲۰ دقیقه + کیف پول
    except Exception as e:
        logger.error(f"[CLEARANCE] خطا در ارسال فاکتور: {e}", exc_info=True)
        await message.answer("⚠️ خطا در ساخت فاکتور. لطفاً کمی بعد دوباره تلاش کنید.", reply_markup=_confirm_kb)
        return
    await state.set_state(Form.clr_waiting_payment)
    await state.update_data(clr_rid=rid)
    await message.answer(
        "⏳ فاکتور پرداخت ارسال شد.\n\n"
        "پس از پرداخت موفق، ثبت درخواست در سامانه آغاز می‌شود.", reply_markup=_back_kb)


@clearance_router.message(Form.clr_waiting_payment, ~F.successful_payment)
async def clr_waiting_payment(message: Message, state: FSMContext):
    if _is_back(message):
        await _back_to_main(message, state)
        return
    await message.answer("⚠️ لطفاً فاکتور ارسال‌شده را پرداخت کنید یا به منوی اصلی بازگردید.",
                         reply_markup=_back_kb)


def _is_clearance_payment(message: Message) -> bool:
    sp = message.successful_payment
    if not sp:
        return False
    try:
        return json.loads(sp.invoice_payload or "{}").get("type") == "clearance"
    except Exception:
        return False


@clearance_router.message(_is_clearance_payment)
async def clr_successful_payment(message: Message, state: FSMContext, bot: Bot):
    sp = message.successful_payment
    payload = json.loads(sp.invoice_payload or "{}")
    rid = payload.get("rid")
    uid = message.from_user.id
    paid_toman = int(sp.total_amount or 0) // 10
    req = get_request(rid)
    logger.info(f"[CLEARANCE] پرداخت موفق user={uid} rid={rid} amount={paid_toman:,} "
                f"charge={getattr(sp, 'telegram_payment_charge_id', '')}")
    if not req or req.get("paid") or (active_request(uid) and active_request(uid).get("rid") != rid):
        # پرداخت تکراری/بدون درخواست معتبر — مبلغ به کیف پول برمی‌گردد
        import wallet
        await wallet.credit(uid, paid_toman, "refund", f"پرداخت تکراری {SERVICE_LABEL} {rid}")
        await message.answer(
            f"✅ پرداخت دریافت شد، ولی درخواست معتبری برای آن پیدا نشد؛ مبلغ {paid_toman:,} تومان "
            "به کیف پول شما برگشت.", reply_markup=get_flow_type_kb(uid))
        await _notify_admin(bot, f"⚠️ [گواهی عدم سوءپیشینه] پرداخت بدون درخواست معتبر — کاربر {uid}، "
                                 f"rid={rid}، {paid_toman:,} تومان به کیف پول برگشت.")
        return
    await state.clear()
    await state.set_state(Form.waiting_for_flow_type)
    await _start_after_payment(bot, rid, paid_toman=paid_toman, exempt=False)


async def _start_after_payment(bot: Bot, rid: str, paid_toman: int, exempt: bool):
    req = _update(rid, paid=True, paid_toman=paid_toman, exempt=exempt, paid_at=time.time())
    uid = req["uid"]
    asyncio.create_task(_panel_register(rid))
    pos = _enqueue_send_code(rid, uid)
    queue_note = f"\n📊 موقعیت شما در صف: {pos + 1}" if pos > 0 else ""
    await _notify_user(
        bot, uid,
        ("✅ *پرداخت تایید شد.*\n\n" if not exempt else "")
        + f"ثبت درخواست {SERVICE_LABEL} آغاز شد. به‌زودی *رمز موقت* به شماره همراه صاحب کدملی "
        "پیامک می‌شود؛ لطفاً در دسترس باشید." + queue_note,
        reply_markup=get_flow_type_kb(uid))
    await _notify_admin(bot, f"📜 [گواهی عدم سوءپیشینه] درخواست جدید {rid}\n{_who(req)}"
                             + ("\n(کاربر معاف — بدون پرداخت)" if exempt else f"\nپرداخت: {paid_toman:,} تومان"))


async def _panel_register(rid: str):
    req = get_request(rid)
    if not req:
        return
    try:
        from panel_sync import register_case_to_panel
        exempt = req.get("exempt")
        case = await register_case_to_panel(
            bale_user_id=req["uid"], full_name=req.get("full_name") or str(req["uid"]),
            service_type=SERVICE_TYPE, status="PROCESSING", tracking_code=rid,
            document_category=SERVICE_LABEL,
            fee=0 if exempt else FEE_TOMAN,
            fee_status="MANUAL_APPROVED" if exempt else "PAID",
            system_cost=SITE_COST_TOMAN,
            result_summary=f"کدملی {req['nid']} — تاریخ تولد {req['birth']}",
            wait=True)
        if case and case.get("id"):
            _update(rid, case_id=case["id"])
    except Exception as e:
        logger.warning(f"[CLEARANCE] ثبت پرونده در پنل ناموفق (rid={rid}): {e}")


async def _panel_update(rid: str, **fields):
    req = get_request(rid)
    if not req or not req.get("case_id"):
        return
    try:
        from panel_sync import update_case_in_panel
        await update_case_in_panel(req["case_id"], **fields)
    except Exception as e:
        logger.warning(f"[CLEARANCE] به‌روزرسانی پنل ناموفق (rid={rid}): {e}")


# ════════════════════════════════════════════════════════════════════════════
# رمز موقت (خارج از نوبت) و ویرایش کدملی
# ════════════════════════════════════════════════════════════════════════════

@clearance_router.message(Form.clr_waiting_code)
async def clr_code(message: Message, state: FSMContext, bot: Bot):
    if _is_back(message):
        await _back_to_main(message, state)
        return
    uid = message.from_user.id
    req = active_request(uid)
    if not req or req.get("status") != ST_WAIT_CODE:
        await _back_to_main(message, state, f"⏳ درخواست {SERVICE_LABEL} شما در حال انجام است.")
        return
    code = normalize_digits((message.text or "").strip())
    if not (code.isdigit() and len(code) == 5):
        await message.answer("⚠️ رمز موقت باید *۵ رقم* باشد. لطفاً کد پیامک‌شده را ارسال کنید:",
                             reply_markup=_back_kb)
        return
    from scenarios import ensure_browser_alive
    if not await ensure_browser_alive(bot, notify_admin=True):
        await message.answer("⚠️ ارتباط با سامانه فعلاً برقرار نیست. لطفاً چند دقیقهٔ دیگر کد را دوباره بفرستید.",
                             reply_markup=_back_kb)
        return
    _update(req["rid"], status=ST_CHECK_CODE)
    await state.clear()
    await state.set_state(Form.waiting_for_flow_type)
    await message.answer("⏳ رمز موقت دریافت شد؛ در حال ثبت در سامانه...",
                         reply_markup=get_flow_type_kb(uid))
    from clearance_scenario import run_code_task
    asyncio.create_task(run_code_task(req["rid"], code, bot))


@clearance_router.message(Form.clr_fix_nid)
async def clr_fix_nid(message: Message, state: FSMContext):
    if _is_back(message):
        await _back_to_main(message, state)
        return
    req = active_request(message.from_user.id)
    if not req or req.get("status") != ST_FIX:
        await _back_to_main(message, state)
        return
    nid = _parse_nid(message.text)
    if not nid:
        await message.answer(_NID_ERROR, reply_markup=_back_kb)
        return
    await state.update_data(clr_rid=req["rid"], clr_fix_nid=nid)
    await state.set_state(Form.clr_fix_birth)
    await message.answer(_BIRTH_PROMPT, reply_markup=_back_kb)


@clearance_router.message(Form.clr_fix_birth)
async def clr_fix_birth(message: Message, state: FSMContext, bot: Bot):
    if _is_back(message):
        await _back_to_main(message, state)
        return
    uid = message.from_user.id
    req = active_request(uid)
    if not req or req.get("status") != ST_FIX:
        await _back_to_main(message, state)
        return
    birth = _parse_birth(message.text)
    if not birth:
        await message.answer(_BIRTH_ERROR, reply_markup=_back_kb)
        return
    data = await state.get_data()
    rid = req["rid"]
    _update(rid, nid=data.get("clr_fix_nid") or req["nid"], birth=birth, fix_deadline=None)
    pos = _enqueue_send_code(rid, uid)
    await state.clear()
    await state.set_state(Form.waiting_for_flow_type)
    queue_note = f"\n📊 موقعیت شما در صف: {pos + 1}" if pos > 0 else ""
    await message.answer("✅ اطلاعات ویرایش شد؛ رمز موقت دوباره درخواست می‌شود. لطفاً در دسترس باشید."
                         + queue_note, reply_markup=get_flow_type_kb(uid))
    await _panel_update(rid, resultSummary=f"کدملی {get_request(rid)['nid']} — تاریخ تولد {birth}")


# ════════════════════════════════════════════════════════════════════════════
# دکمه‌های مدیر
# ════════════════════════════════════════════════════════════════════════════

@clearance_router.callback_query(F.data.startswith("clr:"))
async def clr_admin_callback(callback: CallbackQuery, bot: Bot):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("فقط مدیر", show_alert=True)
        return
    try:
        _, action, rid = callback.data.split(":", 2)
    except ValueError:
        await callback.answer()
        return
    req = get_request(rid)
    if not req or req.get("status") in _CLOSED:
        await callback.answer("این درخواست دیگر فعال نیست.", show_alert=True)
        return
    status, phase = req.get("status"), req.get("failed_phase")

    if action == "paid":
        if status != ST_ADMIN_PAY and not (status == ST_ERROR and phase == "finalize"):
            await callback.answer("درخواست در مرحلهٔ پرداخت نیست.", show_alert=True)
            return
        _enqueue_finalize(rid, req["uid"])
        await callback.answer("ثبت شد ✅")
        await _drop_buttons(callback, "\n\n✅ پرداخت اعلام شد — جستجو، تایید نهایی و چاپ در نوبت است.")
        return

    if action == "retry":
        if status != ST_ERROR:
            await callback.answer("این درخواست خطای فعالی ندارد.", show_alert=True)
            return
        if phase == "finalize":
            _enqueue_finalize(rid, req["uid"])
        elif phase == "register":
            _update(rid, status=ST_REGISTER, failed_phase=None)
            from clearance_scenario import run_register_task
            asyncio.create_task(run_register_task(rid, bot))
        else:
            _enqueue_send_code(rid, req["uid"])
        await callback.answer("تلاش مجدد آغاز شد 🔁")
        await _drop_buttons(callback, "\n\n🔁 تلاش مجدد آغاز شد.")
        return
    await callback.answer()


def _enqueue_finalize(rid: str, uid: int):
    _update(rid, status=ST_FINALIZE, failed_phase=None)
    # مدیر هزینهٔ سامانه را پرداخت کرده — حتی خارج از ساعت کاری ادامه یابد
    _enqueue({"task_type": "CLEARANCE_FINALIZE", "user_id": uid, "rid": rid, "admin_forced": True})


async def _drop_buttons(callback: CallbackQuery, suffix: str):
    try:
        await callback.message.edit_text((callback.message.text or "") + suffix, reply_markup=None)
    except Exception:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass


async def _fail(bot: Bot, rid: str, phase: str, where: str, info: str, user_text: str | None):
    req = _update(rid, status=ST_ERROR, failed_phase=phase, last_error=(info or "")[:500])
    if not req:
        return
    # ⭐ ثبت ناموفق/ناقص: درخواست بازگشت کل مبلغ پرداختی با تایید مدیر (واریز خودکار نیست).
    # اگر مدیر دوباره تلاش کند و موفق شود، درخواست خودکار لغو می‌شود.
    try:
        _paid = int(req.get("paid_toman") or 0)
        if req.get("paid") and not req.get("exempt") and _paid > 0:
            import refund_approvals
            refund_approvals.request_refund_nowait(
                req["uid"], _paid, f"ثبت ناموفق {SERVICE_LABEL} {rid} (مرحلهٔ {phase})",
                source="clearance_fail", dedupe_key=f"clr-fail:{rid}")
    except Exception as _re:
        logger.error(f"[CLEARANCE] ثبت درخواست بازگشت برای {rid} ناموفق: {_re}")
    await _notify_admin(
        bot,
        f"🚨 [گواهی عدم سوءپیشینه] خطا در «{where}» — درخواست {rid}\n{_who(req)}\n\n"
        f"پیام سامانه/خطا: {info or '—'}",
        reply_markup=_admin_kb(rid, paid_button=(phase == "finalize"), retry=True))
    if user_text:
        await _notify_user(bot, req["uid"], user_text)


_USER_SUPPORT_TEXT = (
    "⚠️ در ثبت درخواست گواهی عدم سوءپیشینه مشکلی پیش آمد؛ موضوع به پشتیبانی اعلام شد و "
    "پس از بررسی، ادامهٔ کار انجام می‌شود. نیازی به اقدام شما نیست."
)


# ════════════════════════════════════════════════════════════════════════════
# نتیجهٔ فازها (فراخوانی از clearance_scenario)
# ════════════════════════════════════════════════════════════════════════════

async def on_phase_started(bot: Bot, rid: str, phase: str):
    if phase == "send_code":
        _update(rid, status=ST_SENDING)
    elif phase == "finalize":
        _update(rid, status=ST_FINALIZE)


async def on_send_code_result(bot: Bot, rid: str, kind: str, info: str):
    from clearance_scenario import OK, WRONG_ID
    req = get_request(rid)
    if not req:
        return
    uid = req["uid"]
    if kind == OK:
        _update(rid, status=ST_WAIT_CODE, code_sent_at=time.time())
        await _set_user_state(bot, uid, Form.clr_waiting_code, {"clr_rid": rid})
        await _notify_user(
            bot, uid,
            "🔐 *رمز موقت* به شماره همراه صاحب کدملی ارسال شد.\n\n"
            f"⏰ شما *{CODE_WINDOW_MINUTES} دقیقه* فرصت دارید کد ۵ رقمی را همین‌جا ارسال کنید:",
            reply_markup=_back_kb)
        return
    if kind == WRONG_ID:
        from clearance_scenario import close_tab_only
        await close_tab_only(rid)
        _update(rid, status=ST_FIX, fix_deadline=time.time() + FIX_WINDOW_MINUTES * 60)
        await _set_user_state(bot, uid, Form.clr_fix_nid, {"clr_rid": rid})
        await _notify_user(
            bot, uid,
            "❌ *کدملی و تاریخ تولد اشتباه است.*\n"
            f"پیام سامانه: «{info}»\n\n"
            f"⏰ شما *{duration_label(FIX_WINDOW_MINUTES)}* مهلت دارید تا اطلاعات را ویرایش کنید؛ در غیر این صورت "
            f"درخواست لغو و {TIMEOUT_REFUND_PERCENT}٪ مبلغ پرداختی پس از تایید مدیریت به کیف پول شما برمی‌گردد.\n\n"
            "✏️ لطفاً *کدملی* صحیح را وارد کنید:",
            reply_markup=_back_kb)
        await _notify_admin(bot, f"ℹ️ [گواهی عدم سوءپیشینه] {rid}: کدملی/تاریخ تولد اشتباه — "
                                 f"{duration_label(FIX_WINDOW_MINUTES)} مهلت ویرایش به کاربر داده شد.\n{_who(req)}")
        return
    await _fail(bot, rid, "send_code", "ارسال رمز موقت", info, _USER_SUPPORT_TEXT)


async def on_code_result(bot: Bot, rid: str, kind: str, info: str):
    from clearance_scenario import CODE_EXPIRED, OK, TAB_LOST
    req = get_request(rid)
    if not req:
        return
    uid = req["uid"]
    if kind == OK:
        _update(rid, status=ST_REGISTER)
        await _notify_user(bot, uid, "✅ مشخصات از ثنا دریافت شد؛ در حال ثبت درخواست...")
        return
    if kind == CODE_EXPIRED:
        _update(rid, status=ST_RESEND, resend_at=time.time() + RESEND_AFTER_MINUTES * 60)
        await _notify_user(
            bot, uid,
            "⏰ *زمان اعتبار رمز موقت منقضی شده است.*\n\n"
            f"{RESEND_AFTER_MINUTES} دقیقهٔ دیگر مجدداً رمز موقت برای شما ارسال خواهد شد؛ "
            "لطفاً در دسترس باشید.")
        return
    if kind == TAB_LOST:
        await _fail(bot, rid, "send_code", "ورود رمز موقت (تب درخواست از دست رفته)", info, _USER_SUPPORT_TEXT)
        return
    # رمز پذیرفته نشد — کاربر دوباره کد را بفرستد
    _update(rid, status=ST_WAIT_CODE)
    await _set_user_state(bot, uid, Form.clr_waiting_code, {"clr_rid": rid})
    await _notify_user(
        bot, uid,
        "❌ سامانه رمز موقت را نپذیرفت."
        + (f"\nپیام سامانه: «{info}»" if info else "")
        + "\n\nلطفاً کد ۵ رقمی را بررسی و دوباره ارسال کنید:",
        reply_markup=_back_kb)


async def on_register_result(bot: Bot, rid: str, kind: str, info: str):
    from clearance_scenario import OK, TAB_LOST
    req = get_request(rid)
    if not req:
        return
    if kind == OK:
        _update(rid, status=ST_ADMIN_PAY, payment_id=info)
        await _notify_admin(
            bot,
            f"💳 [گواهی عدم سوءپیشینه] شناسه پرداخت — درخواست {rid}\n{_who(req)}\n\n"
            f"شناسه پرداخت:\n`{info}`\n\n"
            "پس از پرداخت، دکمهٔ زیر را بزنید تا جستجو، تایید نهایی و چاپ رسید انجام شود.",
            reply_markup=_admin_kb(rid, paid_button=True))
        await _notify_user(
            bot, req["uid"],
            "✅ درخواست شما در سامانه ثبت موقت شد.\n"
            "پس از پرداخت هزینهٔ سامانه، تایید نهایی انجام و رسید درخواست برایتان ارسال می‌شود.")
        await _panel_update(rid, paymentId=info)
        return
    phase = "send_code" if kind == TAB_LOST else "register"
    await _fail(bot, rid, phase, "ثبت موقت / محاسبه هزینه", info, _USER_SUPPORT_TEXT)


async def on_finalize_result(bot: Bot, rid: str, kind: str, info: str):
    from clearance_scenario import OK, TAB_LOST, close_tab
    req = get_request(rid)
    if not req:
        return
    uid = req["uid"]
    if kind == OK:
        from bale_file_sender import send_document_direct
        ext = os.path.splitext(info)[1] or ".pdf"
        sent = False
        try:
            sent = bool(await send_document_direct(
                uid, info, filename=f"رسید-درخواست-گواهی-عدم-سوءپیشینه{ext}",
                caption="🧾 رسید درخواست گواهی عدم سوءپیشینه"))
        except Exception as e:
            logger.error(f"[CLEARANCE] ارسال چاپ به کاربر ناموفق (rid={rid}): {e}", exc_info=True)
        if not sent:
            await _fail(bot, rid, "finalize", "ارسال چاپ رسید به کاربر", f"فایل: {info}", None)
            return
        _update(rid, status=ST_DONE, done_at=time.time())
        try:   # ثبت با موفقیت کامل شد → درخواست بازگشتِ ناشی از خطای قبلی دیگر لازم نیست
            import refund_approvals
            refund_approvals.cancel_pending(f"clr-fail:{rid}")
        except Exception:
            pass
        await _notify_user(
            bot, uid,
            "✅ *درخواست گواهی عدم سوءپیشینه با موفقیت ثبت و تایید نهایی شد.*\n\n"
            "📩 نتیجه طی روزهای آتی به سامانه ابلاغ شما پیامک خواهد شد.",
            reply_markup=get_flow_type_kb(uid))
        await _notify_admin(bot, f"✅ [گواهی عدم سوءپیشینه] {rid} تکمیل شد و رسید برای کاربر ارسال شد.\n{_who(req)}")
        await _panel_update(rid, status="COMPLETED")
        try:
            os.remove(info)
        except OSError:
            pass
        await close_tab(rid)
        return
    if kind == TAB_LOST:
        await _fail(bot, rid, "finalize", "جستجو / تایید نهایی",
                    f"{info}\nلطفاً مراحل جستجو، تایید نهایی و چاپ را دستی انجام دهید و رسید را برای کاربر بفرستید "
                    "(یا پس از اطمینان از باز بودن تب، تلاش مجدد کنید).", None)
        return
    await _fail(bot, rid, "finalize", "جستجو / تایید نهایی / چاپ رسید", info, None)


async def on_unexpected_error(bot: Bot, rid: str, task_type: str, error: Exception, page=None):
    req = get_request(rid)
    if not req:
        return
    try:
        from bug_reporter import report_bug
        await report_bug(bot, where=f"clearance:{task_type}", error=error, user_id=req.get("uid"),
                         bill_no=rid, page=page, notify_admin=False)
    except Exception:
        pass
    phase = {"CLEARANCE_FINALIZE": "finalize", "CLEARANCE_REGISTER": "register"}.get(task_type, "send_code")
    await _fail(bot, rid, phase, task_type, f"{type(error).__name__}: {str(error)[:300]}",
                None if phase == "finalize" else _USER_SUPPORT_TEXT)


# ════════════════════════════════════════════════════════════════════════════
# حلقهٔ زمان‌بندی: پایان مهلت ویرایش، ارسال مجدد رمز پس از ۳۰ دقیقه، پاکسازی
# ════════════════════════════════════════════════════════════════════════════

async def _expire_fix_window(bot: Bot, rid: str):
    req = _update(rid, status=ST_CANCELLED, fix_deadline=None, cancelled_at=time.time())
    if not req:
        return
    uid = req["uid"]
    refund = int(req.get("paid_toman") or 0) * TIMEOUT_REFUND_PERCENT // 100
    if refund > 0:
        # ⭐ واریز فقط پس از تایید مدیر
        import refund_approvals
        refund_approvals.request_refund_nowait(
            uid, refund, f"لغو {SERVICE_LABEL} {rid} (پایان مهلت ویرایش)",
            source="clearance_timeout", dedupe_key=f"clr-timeout:{rid}")
    await _notify_user(
        bot, uid,
        f"⌛ مهلت {duration_adj(FIX_WINDOW_MINUTES)} ویرایش کدملی و تاریخ تولد به پایان رسید و درخواست "
        f"{SERVICE_LABEL} لغو شد."
        + (f"\n👛 مبلغ {refund:,} تومان پس از تایید مدیریت به کیف پول شما واریز می‌شود." if refund else ""),
        reply_markup=get_flow_type_kb(uid))
    await _set_user_state(bot, uid, Form.waiting_for_flow_type, {})
    await _notify_admin(bot, f"⌛ [گواهی عدم سوءپیشینه] {rid} پس از پایان مهلت ویرایش لغو شد"
                             + (f"؛ درخواست بازگشت {refund:,} تومان منتظر تایید شماست." if refund else ".")
                             + f"\n{_who(req)}")
    kept = int(req.get("paid_toman") or 0) - refund
    await _panel_update(rid, status="CANCELLED", fee=kept, systemCost=0,
                        errorDetails="کدملی/تاریخ تولد اشتباه — پایان مهلت ویرایش")


async def _tick(bot: Bot):
    now = time.time()
    changed = False
    for rid, req in list(_requests().items()):
        status = req.get("status")
        if status == ST_FIX and req.get("fix_deadline") and now >= req["fix_deadline"]:
            await _expire_fix_window(bot, rid)
        elif status == ST_RESEND and req.get("resend_at") and now >= req["resend_at"]:
            _update(rid, resend_at=None)
            _enqueue_send_code(rid, req["uid"])
            logger.info(f"[CLEARANCE] ارسال مجدد رمز موقت پس از {RESEND_AFTER_MINUTES} دقیقه — {rid}")
        elif status == ST_AWAIT_PAY and now - req.get("created_at", now) > 3 * 86400:
            _requests().pop(rid, None)
            changed = True
        elif status in _CLOSED and now - req.get("updated_at", now) > 30 * 86400:
            _requests().pop(rid, None)
            changed = True
    if changed:
        _save()


async def _recover_after_restart(bot: Bot):
    """صف کارها و تب‌ها در حافظه‌اند؛ درخواستی که هنگام ری‌استارت وسط کار بود
    دوباره در نوبت قرار می‌گیرد (یا با دکمهٔ «تلاش مجدد» به مدیر اعلام می‌شود)."""
    for rid, req in list(_requests().items()):
        status = req.get("status")
        if not req.get("paid") or status in _CLOSED:
            continue
        if status in (ST_QUEUED, ST_SENDING):
            _enqueue_send_code(rid, req["uid"])
        elif status == ST_FINALIZE:
            _enqueue_finalize(rid, req["uid"])
        elif status in (ST_CHECK_CODE, ST_REGISTER):
            await _fail(bot, rid, "send_code", "ری‌استارت ربات حین ثبت",
                        "تب درخواست با ری‌استارت بسته شد؛ با «تلاش مجدد» رمز موقت دوباره ارسال می‌شود.", None)


async def clearance_loop(bot: Bot, interval: int = 30):
    """از bot.py در پس‌زمینه اجرا می‌شود؛ پس از ری‌استارت هم مهلت‌ها را رعایت می‌کند."""
    global _loop_started
    if _loop_started:
        return
    _loop_started = True
    try:
        await _recover_after_restart(bot)
    except Exception as e:
        logger.error(f"[CLEARANCE] خطا در بازیابی درخواست‌ها پس از ری‌استارت: {e}", exc_info=True)
    while True:
        try:
            await _tick(bot)
        except Exception as e:
            logger.error(f"[CLEARANCE] خطا در حلقهٔ زمان‌بندی: {e}", exc_info=True)
        await asyncio.sleep(interval)
