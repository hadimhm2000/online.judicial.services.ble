"""
card_payment.py — پرداخت جایگزین «کارت‌به‌کارت» برای فاکتورهای پرداخت‌نشده
============================================================================

جریان کار
---------
۱) هر جا ربات فاکتور بله (sendInvoice) می‌فرستد، بلافاصله پس از ارسال موفق
   یک خط اضافه می‌شود:

       from card_payment import track_invoice; track_invoice(invoice_data)

   (invoice_data همان دیکشنری‌ای است که به sendInvoice پست شده است.)

۲) اگر تا CARD_PAY_DELAY_MINUTES دقیقه (پیش‌فرض ۲۰) پرداخت موفقی برای آن
   فاکتور نرسد، برای کاربر ارسال می‌شود:
     - تصویر «کارت بانکی» (شماره کارت، صاحب حساب، بانک، مبلغ)
     - متن: «در صورتی که از طریق درگاه پرداخت موفق به واریز نشده‌اید …»
     - دکمه‌های «کپی شماره کارت»، «کپی مبلغ»، «ارسال تصویر رسید»

۳) کاربر تصویر رسید (عکس یا فایل تصویر/PDF) را می‌فرستد → رسید با نوع
   درخواست، عنوان فاکتور، مبلغ (تومان و ریال) و مشخصات کاربر برای مدیر
   ارسال می‌شود با دکمه‌های «✅ تایید» / «❌ رد».

۴) مدیر «تایید» را می‌زند → ربات دقیقاً همان رویداد successful_payment را
   (با همان payload و مبلغ فاکتور اصلی) از مسیر Dispatcher بازپخش می‌کند؛
   بنابراین همان فلوی پرداخت کیف پول بله برای آن سرویس اجرا می‌شود (شروع
   ثبت، امضا، ثبت پرونده در پنل و …) و «درآمد» و «سود» پنل دقیقاً مثل
   پرداخت درگاه محاسبه می‌شوند. هیچ فلوی سرویسی تغییر نمی‌کند.
   همزمان یک رکورد CardPayment (با تصویر رسید) در پنل ثبت می‌شود.

۵) اگر مبلغ واریزی کمتر از فاکتور باشد، مدیر «کسری» را می‌زند و مبلغ کمبود
   (تومان) را تایپ می‌کند → فقط همان کسری از کاربر خواسته می‌شود؛ رسید
   باقی‌مانده دوباره برای تایید نزد مدیر می‌آید و با تایید، مرحلهٔ ۴ اجرا
   می‌شود. اگر از مبلغ فاکتور چیزی کسر شده باشد (پیش‌پرداخت/مانده)، در
   پیام رسید برای مدیر درج می‌شود (note_invoice_deduction).

ایمنی
-----
- اگر کاربر در این فاصله از درگاه پرداخت کند، ورودی بسته می‌شود؛ اگر رسید
  کارت‌به‌کارت هم در انتظار بررسی باشد، به مدیر هشدار «پرداخت تکراری» داده
  می‌شود و دکمهٔ تایید دیگر عمل نمی‌کند.
- تایید/رد فقط توسط ADMIN_ID پذیرفته می‌شود و هر ورودی فقط یک‌بار تایید
  می‌شود.
- عکس فقط وقتی «رسید» حساب می‌شود که کاربر هنوز در همان state انتظار
  پرداخت باشد یا دکمهٔ «ارسال تصویر رسید» را زده باشد — تا عکس‌های پیوست
  سرویس‌های دیگر اشتباهی رسید تلقی نشوند.
- ورودی‌ها در data/card_payments.json ذخیره می‌شوند و ری‌استارت ربات را
  تحمل می‌کنند.

اتصال در bot.py (سه خط — به docstring تابع setup_card_payment مراجعه کنید).
"""

from __future__ import annotations

import asyncio
import datetime
import io
import json
import logging
import os
import secrets
import time
from typing import Any

import aiohttp
from aiogram import Bot, F, Router
from aiogram.filters import Filter
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import (
    CallbackQuery,
    Chat,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    SuccessfulPayment,
    Update,
    User,
)

import runtime_state
from config import (
    ADMIN_API_BASE,
    ADMIN_ID,
    PANEL_AUTH_HEADERS,
    BALE_API_BASE,
    BALE_SSL_CONTEXT,
    BOT_TOKEN,
    CARD_PAY_BANK,
    CARD_PAY_BRAND,
    CARD_PAY_COPY_MODE,
    CARD_PAY_DELAY_MINUTES,
    CARD_PAY_ENABLED,
    CARD_PAY_EXPIRE_HOURS,
    CARD_PAY_HOLDER,
    CARD_PAY_NUMBER,
    CARD_ONLY_ABOVE_TOMAN,
    BASE_DIR,
)

logger = logging.getLogger(__name__)

card_router = Router(name="card_payment")

# ── ثابت‌ها ─────────────────────────────────────────────────────────────
_STORE_FILE = os.path.join(BASE_DIR, "data", "card_payments.json")
_LOOP_INTERVAL = 30            # ثانیه — فاصلهٔ بررسی سررسید یادآورها
_ARM_SECONDS = 15 * 60         # اعتبار دکمهٔ «ارسال تصویر رسید»
_FAKE_CHARGE_PREFIX = "CARD-"  # شناسهٔ پرداخت‌های تاییدشدهٔ کارت‌به‌کارت
_CARD_ONLY_FIRST_DELAY = 5     # ثانیه — فاکتور فقط‌کارت پس از ست‌شدن state پرداخت ارسال شود
_CARD_ONLY_STATE_WAIT = 5 * 60  # تا این مدت منتظر state انتظار پرداخت کاربر می‌مانیم

# وضعیت‌ها
S_INVOICE = "invoice"          # فاکتور ارسال شد، منتظر پرداخت درگاه
S_CARD_SENT = "card_sent"      # پیام کارت‌به‌کارت ارسال شد، منتظر رسید
S_REVIEW = "review"            # رسید رسید، منتظر تصمیم مدیر
S_APPROVED = "approved"
S_REJECTED = "rejected"        # (موقت) — بلافاصله به S_CARD_SENT برمی‌گردد
S_PAID_GATEWAY = "paid_gateway"
S_EXPIRED = "expired"
S_SKIPPED = "skipped"          # کاربر فلوی پرداخت را ترک کرده بود
S_SHORTFALL = "shortfall"      # مدیر کسری اعلام کرد، منتظر رسید باقی‌ماندهٔ مبلغ
_ACTIVE = (S_INVOICE, S_CARD_SENT, S_REVIEW, S_SHORTFALL)
_SHORTFALL_INPUT_SECONDS = 15 * 60   # مهلت مدیر برای وارد کردن مبلغ کسری
_DEDUCTION_TTL = 30 * 60             # اعتبار اطلاعات «کسر از فاکتور» تا ارسال فاکتور

# payloadهایی که هندلر پرداختشان مستقل از state کاربر مسیریابی می‌شود
# (global_successful_payment_handler در handlers.py از روی payload تصمیم می‌گیرد)
_PAYLOAD_ROUTED_TYPES = {"admin_fee", "panel_message", "reg_prepay", "single_use", "clearance"}

# نوع payload → نام فارسی درخواست (برای پیام مدیر و پنل)
_TYPE_LABELS = {
    "cart": "استعلام (سبد خرید)",
    "single": "استعلام",
    "bulk_inquiry": "استعلام دسته‌جمعی",
    "lavayeh": "لایحه / اعلام وکالت",
    "tajdid_nazar": "دعوی اعتراضی",
    "regional_value": "استعلام ارزش منطقه‌ای",
    "subscription": "اشتراک ماهیانه",
    "admin_fee": "هزینه ثبت‌شده توسط مدیر",
    "panel_message": "پیام مدیر از پنل",
    "bulk_prepay": "پیش‌پرداخت ثبت دسته‌جمعی",
    "bulk_settlement": "تسویه هزینه سامانه (دسته‌جمعی)",
    "reg_prepay": "پیش‌پرداخت ثبت",
    "single_use": "پرداخت تکی (تمبر / خسارت تأخیر و مهریه)",
    "clearance": "درخواست گواهی عدم سوءپیشینه",
}
_SVC_LABELS = {
    "lavayeh": "لایحه",
    "ealam": "اعلام وکالت",
    "ezhharnameh": "اظهارنامه",
    "tn": "دعاوی اعتراضی / اعاده دادرسی",
    "check": "ثبت دادخواست",
}
# نوع payload → serviceType پنل (برای گزارش‌گیری CardPayment)
_TYPE_TO_PANEL_SERVICE = {
    "cart": "INQUIRY", "single": "INQUIRY", "bulk_inquiry": "INQUIRY",
    "lavayeh": "LAVAYEH", "tajdid_nazar": "TAJDID_NAZAR",
    "regional_value": "REGIONAL_VALUE", "subscription": "SUBSCRIPTION",
    "admin_fee": "ADMIN_FEE", "panel_message": "ADMIN_SEND",
    "bulk_prepay": "BULK", "bulk_settlement": "BULK",
    "single_use": "SINGLE_USE",
    "clearance": "CLEARANCE_CERT",
}
_SVC_TO_PANEL_SERVICE = {
    "lavayeh": "LAVAYEH", "ealam": "EALAM_VAKALAHT", "ezhharnameh": "EZHHARNAMEH",
    "tn": "TAJDID_NAZAR", "check": "CHECK",
}

_REJECT_REASONS = {
    "amt": "مبلغ واریزی با مبلغ فاکتور مطابقت ندارد",
    "bad": "تصویر رسید نامعتبر یا ناخوانا است",
    "nf": "واریزی با این مشخصات در حساب یافت نشد",
    "oth": "رسید توسط پشتیبانی تایید نشد",
}

# ── حافظه ────────────────────────────────────────────────────────────────
_store: dict[str, dict] = {}
_lock = asyncio.Lock()
_dirty = False
_copy_text_supported: bool | None = None  # None = هنوز امتحان نشده
# مدیر دکمهٔ «کسری مبلغ» را زده و باید مبلغ کسری را تایپ کند
_shortfall_wait: dict | None = None
# کسر از فاکتور (پیش‌پرداخت/مانده) — توسط prepay_registration ثبت و در
# track_invoice به ورودی همان کاربر چسبانده می‌شود: uid → {...}
_pending_deductions: dict[int, dict] = {}


def _now() -> float:
    return time.time()


def _fmt_dt(ts: float | None) -> str:
    if not ts:
        return "—"
    return datetime.datetime.fromtimestamp(ts).strftime("%Y/%m/%d %H:%M")


def _load_store() -> None:
    global _store
    try:
        if os.path.exists(_STORE_FILE):
            with open(_STORE_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
            _store = {k: v for k, v in (raw or {}).items() if isinstance(v, dict)}
            logger.info(f"[CARD-PAY] {len(_store)} ورودی کارت‌به‌کارت بارگذاری شد")
    except Exception as e:
        logger.error(f"[CARD-PAY] خطا در بارگذاری {_STORE_FILE}: {e}", exc_info=True)
        _store = {}


def _save_store() -> None:
    global _dirty
    try:
        os.makedirs(os.path.dirname(_STORE_FILE), exist_ok=True)
        tmp = _STORE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_store, f, ensure_ascii=False, indent=1, default=str)
        os.replace(tmp, _STORE_FILE)
        _dirty = False
    except Exception as e:
        logger.error(f"[CARD-PAY] خطا در ذخیرهٔ {_STORE_FILE}: {e}", exc_info=True)


def _mark_dirty() -> None:
    global _dirty
    _dirty = True


def _parse_payload(payload: Any) -> dict:
    if isinstance(payload, dict):
        return payload
    try:
        return json.loads(payload or "{}")
    except Exception:
        return {}


def _service_label(entry: dict) -> str:
    pl = entry.get("payload_obj") or {}
    ptype = pl.get("type", "")
    if ptype == "reg_prepay":
        return f"پیش‌پرداخت {_SVC_LABELS.get(pl.get('svc', ''), 'ثبت')}"
    return _TYPE_LABELS.get(ptype, ptype or "نامشخص")


def _panel_service_type(entry: dict) -> str:
    pl = entry.get("payload_obj") or {}
    if pl.get("svc") in _SVC_TO_PANEL_SERVICE:
        return _SVC_TO_PANEL_SERVICE[pl["svc"]]
    return _TYPE_TO_PANEL_SERVICE.get(pl.get("type", ""), "UNKNOWN")


def _find_active(uid: int, payload: str) -> dict | None:
    for e in _store.values():
        if e.get("uid") == uid and e.get("payload") == payload and e.get("status") in _ACTIVE:
            return e
    return None


def _entries_for_user(uid: int, statuses=_ACTIVE) -> list[dict]:
    return sorted(
        (e for e in _store.values() if e.get("uid") == uid and e.get("status") in statuses),
        key=lambda e: e.get("updated_at", 0), reverse=True)


# ═════════════════════════════════════════════════════════════════════════
# ۱) API عمومی — ثبت فاکتور
# ═════════════════════════════════════════════════════════════════════════
def _invoice_rial(invoice_data: dict) -> int:
    try:
        return int(sum(int(p.get("amount", 0)) for p in (invoice_data.get("prices") or [])))
    except Exception:
        return 0


def card_only_required(invoice_data: dict) -> bool:
    """⭐ آیا این فاکتور (پس از کسر کیف پول) از سقف CARD_ONLY_ABOVE_TOMAN بیشتر است؟
    در این صورت درگاه بله ارسال نمی‌شود و فقط کارت‌به‌کارت فعال است."""
    if not CARD_PAY_ENABLED or CARD_ONLY_ABOVE_TOMAN <= 0:
        return False
    return _invoice_rial(invoice_data) > CARD_ONLY_ABOVE_TOMAN * 10


def track_card_only_invoice(invoice_data: dict) -> None:
    """⭐ به‌جای sendInvoice صدا زده می‌شود: کارت‌به‌کارت چند ثانیه بعد (پس از ست‌شدن
    state انتظار پرداخت توسط فراخوان) ارسال می‌شود، نه پس از ۲۰ دقیقه."""
    track_invoice(invoice_data, card_only=True)


def track_invoice(invoice_data: dict, card_only: bool = False) -> None:
    """پس از هر sendInvoice موفق صدا زده می‌شود. هرگز exception پرتاب نمی‌کند.

    Args:
        invoice_data: همان دیکشنری ارسالی به sendInvoice
                      (chat_id, title, description, payload, prices, ...)
        card_only: فاکتور درگاه ارسال نشده (مبلغ بالای سقف) — کارت‌به‌کارت فوری
    """
    # ⭐ ثبت آخرین مبلغ فاکتور برای رد پرداخت فاکتورهای قدیمی‌تر/ارزان‌تر (invoice_guard)
    try:
        import invoice_guard
        invoice_guard.record(invoice_data)
    except Exception as e:
        logger.error(f"[CARD-PAY] ثبت فاکتور در invoice_guard ناموفق: {e}")
    # ⭐ کیف پول: اگر موجودی کافی باشد، دکمهٔ «پرداخت از کیف پول» زیر فاکتور
    try:
        import wallet
        wallet.on_invoice(invoice_data)
    except Exception as e:
        logger.error(f"[CARD-PAY] پیشنهاد کیف پول ناموفق: {e}")
    if not CARD_PAY_ENABLED:
        return
    try:
        uid = int(invoice_data.get("chat_id"))
        payload = str(invoice_data.get("payload") or "")
        prices = invoice_data.get("prices") or []
        amount_rial = int(sum(int(p.get("amount", 0)) for p in prices))
        if amount_rial <= 0:
            return
        now = _now()
        existing = _find_active(uid, payload)
        if existing and existing.get("status") in (S_REVIEW, S_SHORTFALL):
            # رسید در حال بررسی مدیر است (یا کاربر بخشی را واریز کرده و منتظر
            # رسید باقی‌مانده هستیم) — فاکتور جدید (مثلاً یادآوری) آن را بازنویسی نکند
            logger.info(f"[CARD-PAY] فاکتور تکراری در حین بررسی رسید نادیده گرفته شد: uid={uid}")
            return
        if (not card_only and existing and existing.get("status") == S_CARD_SENT
                and existing.get("amount_rial") == amount_rial):
            # یادآوری همان فاکتور (مثلاً حلقهٔ یادآوری لایحه) — پیام کارت قبلاً
            # ارسال شده و هنوز معتبر است؛ دوباره ارسال نمی‌کنیم تا اسپم نشود.
            return
        entry = existing or {
            "id": secrets.token_hex(4),
            "uid": uid,
            "payload": payload,
            "created_at": now,
        }
        entry.update({
            "payload_obj": _parse_payload(payload),
            "title": str(invoice_data.get("title") or ""),
            "description": str(invoice_data.get("description") or ""),
            "amount_rial": amount_rial,
            "invoice_at": now,
            "status": S_INVOICE,
            "updated_at": now,
            "card_only": bool(card_only),
        })
        if card_only:
            # سررسید حلقه: invoice_at + delay → چند ثانیه بعد
            entry["invoice_at"] = now - CARD_PAY_DELAY_MINUTES * 60 + _CARD_ONLY_FIRST_DELAY
        ded = _take_deduction(uid, entry["payload_obj"].get("type", ""))
        if ded:
            entry["deduction"] = ded
        _store[entry["id"]] = entry
        _mark_dirty()
        logger.info(
            f"[CARD-PAY] فاکتور ثبت شد id={entry['id']} uid={uid} مبلغ={amount_rial:,} ریال "
            f"— یادآور کارت‌به‌کارت پس از {CARD_PAY_DELAY_MINUTES} دقیقه")
    except Exception as e:
        logger.error(f"[CARD-PAY] track_invoice ناموفق: {e}", exc_info=True)


def note_invoice_deduction(uid: int, invoice_types, total_rial: int,
                           deducted_rial: int, detail: str) -> None:
    """ثبت «کسر از فاکتور» برای فاکتور بعدیِ همین کاربر (هرگز exception نمی‌دهد).

    prepay_registration پیش از ارسال فاکتوری که مبلغش با پیش‌پرداخت/مانده
    کم شده صدا می‌زند؛ اگر کاربر آن فاکتور را کارت‌به‌کارت بپردازد، کسر در
    پیام رسید برای مدیر نمایش داده می‌شود.
    """
    try:
        if int(deducted_rial) <= 0:
            return
        _pending_deductions[int(uid)] = {
            "types": list(invoice_types),
            "total_rial": int(total_rial),
            "deducted_rial": int(deducted_rial),
            "detail": str(detail or ""),
            "at": _now(),
        }
    except Exception as e:
        logger.error(f"[CARD-PAY] ثبت کسر فاکتور ناموفق: {e}")


def _take_deduction(uid: int, ptype: str) -> dict | None:
    ded = _pending_deductions.get(uid)
    if not ded:
        return None
    if _now() - ded.get("at", 0) > _DEDUCTION_TTL:
        _pending_deductions.pop(uid, None)
        return None
    if ptype not in ded.get("types", ()):
        return None
    _pending_deductions.pop(uid, None)
    return {k: v for k, v in ded.items() if k != "types"}


# ═════════════════════════════════════════════════════════════════════════
# ۲) ناظر پرداخت واقعی درگاه (outer middleware)
# ═════════════════════════════════════════════════════════════════════════
class GatewayPaymentObserver(BaseMiddleware):
    """هر successful_payment واقعی بله را می‌بیند و ورودی کارت‌به‌کارت
    متناظرش را می‌بندد. پرداخت‌های بازپخش‌شدهٔ خود این ماژول (CARD-…) رد می‌شوند."""

    async def __call__(self, handler, event, data: dict):
        sp = getattr(event, "successful_payment", None)
        if sp is not None:
            charge = str(getattr(sp, "telegram_payment_charge_id", "") or "")
            if not charge.startswith(_FAKE_CHARGE_PREFIX):
                try:
                    await _on_gateway_payment(data.get("bot"), event.from_user.id,
                                              str(sp.invoice_payload or ""))
                except Exception as e:
                    logger.error(f"[CARD-PAY] خطا در ناظر پرداخت درگاه: {e}", exc_info=True)
        return await handler(event, data)


async def _on_gateway_payment(bot: Bot | None, uid: int, payload: str) -> None:
    async with _lock:
        entry = _find_active(uid, payload)
        if not entry:
            return
        prev = entry["status"]
        entry["status"] = S_PAID_GATEWAY
        entry["updated_at"] = _now()
        _mark_dirty()
    logger.info(f"[CARD-PAY] پرداخت درگاه برای id={entry['id']} رسید — ورودی بسته شد (قبلی: {prev})")
    if prev in (S_REVIEW, S_SHORTFALL) and bot is not None:
        why = ("منتظر بررسی بود" if prev == S_REVIEW
               else "بخشی از مبلغ را کارت‌به‌کارت واریز کرده و منتظر رسید باقی‌مانده بودیم")
        try:
            await bot.send_message(
                ADMIN_ID,
                f"⚠️ هشدار پرداخت تکراری\n\nکاربر {uid} فاکتور «{entry.get('title')}» را "
                f"از طریق درگاه بله پرداخت کرد، در حالی که رسید کارت‌به‌کارت او "
                f"(کد {entry['id']}) {why}.\n"
                f"❗️ رسید کارت‌به‌کارت را تایید نکنید؛ در صورت واریز، مبلغ را عودت دهید.")
        except Exception:
            pass
    _sync_panel(entry)


# ═════════════════════════════════════════════════════════════════════════
# ۳) حلقهٔ پس‌زمینه — ارسال پیام کارت‌به‌کارت پس از ۲۰ دقیقه
# ═════════════════════════════════════════════════════════════════════════
async def _get_state(bot: Bot, uid: int) -> tuple[str | None, dict]:
    dp = getattr(runtime_state, "dp", None)
    if dp is None:
        return None, {}
    key = StorageKey(bot_id=bot.id, chat_id=uid, user_id=uid)
    try:
        st = await dp.storage.get_state(key)
        data = await dp.storage.get_data(key)
        return st, dict(data or {})
    except Exception:
        return None, {}


def _is_payment_wait_state(raw_state) -> bool:
    try:
        from user_activity import _is_payment_wait_state as _chk
        return _chk(raw_state)
    except Exception:
        low = str(raw_state or "").lower()
        return any(k in low for k in ("prepay", "payment", "settlement", "receipt"))


async def card_payment_loop(bot: Bot) -> None:
    """حلقهٔ دائمی؛ در main() با asyncio.create_task اجرا می‌شود."""
    if not CARD_PAY_ENABLED:
        logger.info("[CARD-PAY] غیرفعال است (CARD_PAY_ENABLED=0)")
        return
    delay = CARD_PAY_DELAY_MINUTES * 60
    expire = CARD_PAY_EXPIRE_HOURS * 3600
    logger.info(f"[CARD-PAY] حلقه فعال شد — تاخیر {CARD_PAY_DELAY_MINUTES} دقیقه")
    while True:
        try:
            now = _now()
            due = [e for e in list(_store.values())
                   if e.get("status") == S_INVOICE and now - e.get("invoice_at", now) >= delay]
            for entry in due:
                await _send_card_offer(bot, entry)

            # انقضای ورودی‌های رها‌شده
            for e in list(_store.values()):
                if e.get("status") in (S_INVOICE, S_CARD_SENT) and now - e.get("invoice_at", now) > expire:
                    e["status"] = S_EXPIRED
                    e["updated_at"] = now
                    _mark_dirty()
            # پاک‌سازی ورودی‌های بستهٔ قدیمی (بیش از ۱۴ روز)
            for k, e in list(_store.items()):
                if e.get("status") not in _ACTIVE and now - e.get("updated_at", now) > 14 * 86400:
                    _store.pop(k, None)
                    _mark_dirty()

            if _dirty:
                _save_store()
        except asyncio.CancelledError:
            if _dirty:
                _save_store()
            raise
        except Exception as e:
            logger.error(f"[CARD-PAY] خطا در حلقه: {e}", exc_info=True)
        await asyncio.sleep(_LOOP_INTERVAL)


async def _send_card_offer(bot: Bot, entry: dict) -> None:
    uid = entry["uid"]
    ptype = (entry.get("payload_obj") or {}).get("type", "")
    raw_state, fsm_data = await _get_state(bot, uid)

    # اگر کاربر دیگر در انتظار پرداخت نیست (انصراف/شروع فلوی دیگر)، پیام نده —
    # مگر برای فاکتورهایی که پرداختشان از روی payload مسیریابی می‌شود.
    if ptype not in _PAYLOAD_ROUTED_TYPES and not _is_payment_wait_state(raw_state):
        if entry.get("card_only") and _now() - entry.get("created_at", 0) < _CARD_ONLY_STATE_WAIT:
            # فراخوان هنوز state انتظار پرداخت را ست نکرده — دور بعدی حلقه
            return
        entry["status"] = S_SKIPPED
        entry["updated_at"] = _now()
        _mark_dirty()
        logger.info(f"[CARD-PAY] id={entry['id']} رد شد — کاربر {uid} دیگر در انتظار پرداخت نیست "
                    f"(state={raw_state})")
        return

    entry["state_snapshot"] = raw_state
    entry["data_snapshot"] = json.loads(json.dumps(fsm_data, default=str, ensure_ascii=False))
    amount_toman = entry["amount_rial"] // 10

    if entry.get("card_only"):
        caption = (
            "💳 *پرداخت از طریق کارت به کارت*\n\n"
            f"مبلغ فاکتور «{entry.get('title') or _service_label(entry)}» بیش از "
            f"{CARD_ONLY_ABOVE_TOMAN:,} تومان است و پرداخت آن از طریق درگاه امکان‌پذیر نیست.\n\n"
            "لطفاً مبلغ را به شماره کارت زیر واریز نمایید:\n\n"
            f"🔢 شماره کارت:\n`{CARD_PAY_NUMBER}`\n"
            f"👤 به نام: *{CARD_PAY_HOLDER}*\n"
            + (f"🏦 {CARD_PAY_BANK}\n" if CARD_PAY_BANK else "")
            + f"\n💰 مبلغ: *{amount_toman:,} تومان*  (`{entry['amount_rial']}` ریال)\n\n"
            "📸 پس از واریز، *تصویر رسید* را همین‌جا ارسال کنید تا پس از تایید "
            "پشتیبانی، درخواست شما ادامه پیدا کند."
        )
    else:
        caption = (
            "💳 *پرداخت از طریق کارت به کارت*\n\n"
            f"فاکتور «{entry.get('title') or _service_label(entry)}» هنوز پرداخت نشده است.\n\n"
            "⚠️ در صورتی که از طریق درگاه پرداخت، موفق به واریز نشده‌اید، "
            "لطفاً مبلغ خود را از طریق شماره کارت زیر واریز نمایید:\n\n"
            f"🔢 شماره کارت:\n`{CARD_PAY_NUMBER}`\n"
            f"👤 به نام: *{CARD_PAY_HOLDER}*\n"
            + (f"🏦 {CARD_PAY_BANK}\n" if CARD_PAY_BANK else "")
            + f"\n💰 مبلغ: *{amount_toman:,} تومان*  (`{entry['amount_rial']}` ریال)\n\n"
            "📸 پس از واریز، *تصویر رسید* را همین‌جا ارسال کنید تا پس از تایید "
            "پشتیبانی، درخواست شما ادامه پیدا کند.\n"
            "_(اگر همچنان مایل به پرداخت از درگاه هستید، همان فاکتور قبلی معتبر است.)_"
        )
    try:
        from card_payment_image import render_card_image
        image = await asyncio.to_thread(
            render_card_image, CARD_PAY_NUMBER, CARD_PAY_HOLDER, amount_toman,
            CARD_PAY_BANK or None, CARD_PAY_BRAND)
    except Exception as e:
        logger.error(f"[CARD-PAY] ساخت تصویر کارت ناموفق: {e}", exc_info=True)
        image = None

    ok = await _send_offer_message(uid, entry, caption, image)
    if not ok:
        # کاربر ربات را بلاک کرده/خطای شبکه — دوباره تلاش نمی‌کنیم تا اسپم نشود
        entry["status"] = S_EXPIRED
        entry["updated_at"] = _now()
        _mark_dirty()
        return
    entry["status"] = S_CARD_SENT
    entry["card_sent_at"] = _now()
    entry["updated_at"] = _now()
    _mark_dirty()
    logger.info(f"[CARD-PAY] پیام کارت‌به‌کارت برای uid={uid} ارسال شد (id={entry['id']})")


def _due_rial(entry: dict) -> int:
    """مبلغی که کاربر اکنون باید واریز کند — در حالت کسری، فقط باقی‌مانده."""
    if entry.get("status") == S_SHORTFALL and entry.get("shortfall_rial"):
        return int(entry["shortfall_rial"])
    return int(entry["amount_rial"])


def _offer_keyboard(entry: dict, use_copy_text: bool, amount_rial: int | None = None) -> dict:
    eid = entry["id"]
    if use_copy_text:
        row1 = [
            {"text": "📋 کپی شماره کارت", "copy_text": {"text": CARD_PAY_NUMBER}},
            {"text": "💰 کپی مبلغ (ریال)",
             "copy_text": {"text": str(amount_rial or entry["amount_rial"])}},
        ]
    else:
        row1 = [
            {"text": "📋 کپی شماره کارت", "callback_data": f"cpay:cc:{eid}"},
            {"text": "💰 کپی مبلغ", "callback_data": f"cpay:ca:{eid}"},
        ]
    return {"inline_keyboard": [
        row1,
        [{"text": "📸 ارسال تصویر رسید", "callback_data": f"cpay:up:{eid}"}],
    ]}


async def _bale_call(method: str, data: aiohttp.FormData | dict) -> dict:
    url = f"{BALE_API_BASE.rstrip('/')}/bot{BOT_TOKEN}/{method}"
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=BALE_SSL_CONTEXT)) as session:
        kw = {"json": data} if isinstance(data, dict) else {"data": data}
        async with session.post(url, timeout=aiohttp.ClientTimeout(total=40), **kw) as resp:
            try:
                return await resp.json(content_type=None)
            except Exception:
                return {"ok": False, "description": f"HTTP {resp.status}"}


async def _send_offer_message(uid: int, entry: dict, caption: str, image: bytes | None,
                              amount_rial: int | None = None) -> bool:
    """ارسال پیام کارت‌به‌کارت با API مستقیم بله (برای کنترل دکمه‌ها).

    اگر CARD_PAY_COPY_MODE=copy_text باشد اول دکمهٔ کپی مستقیم امتحان
    می‌شود و در صورت رد شدن توسط بله، به حالت callback برمی‌گردد.
    """
    global _copy_text_supported
    modes = [False]
    if CARD_PAY_COPY_MODE == "copy_text" and _copy_text_supported is not False:
        modes = [True, False]

    for use_copy in modes:
        kb = json.dumps(_offer_keyboard(entry, use_copy, amount_rial), ensure_ascii=False)
        if image:
            form = aiohttp.FormData()
            form.add_field("chat_id", str(uid))
            form.add_field("caption", caption)
            form.add_field("parse_mode", "Markdown")
            form.add_field("reply_markup", kb)
            form.add_field("photo", image, filename="card.png", content_type="image/png")
            res = await _bale_call("sendPhoto", form)
        else:
            res = await _bale_call("sendMessage", {
                "chat_id": uid, "text": caption, "parse_mode": "Markdown",
                "reply_markup": json.loads(kb)})
        if res.get("ok"):
            if use_copy:
                _copy_text_supported = True
            return True
        logger.warning(f"[CARD-PAY] ارسال پیام کارت ناموفق (copy_text={use_copy}): {res}")
        if use_copy:
            _copy_text_supported = False
    return False


# ═════════════════════════════════════════════════════════════════════════
# ۴) دکمه‌های کاربر — کپی شماره کارت / مبلغ / ارسال رسید
# ═════════════════════════════════════════════════════════════════════════
@card_router.callback_query(F.data.startswith("cpay:cc:"))
async def cb_copy_card(callback: CallbackQuery):
    await callback.answer(f"شماره کارت: {CARD_PAY_NUMBER}", show_alert=True)
    # پیام جداگانه فقط با شماره — با لمس/نگه‌داشتن در بله کپی می‌شود
    await callback.message.answer(f"`{CARD_PAY_NUMBER}`", parse_mode="Markdown")


@card_router.callback_query(F.data.startswith("cpay:ca:"))
async def cb_copy_amount(callback: CallbackQuery):
    entry = _store.get(callback.data.split(":", 2)[2])
    if not entry:
        await callback.answer("این فاکتور دیگر معتبر نیست.", show_alert=True)
        return
    rial = _due_rial(entry)
    await callback.answer(f"مبلغ: {rial // 10:,} تومان = {rial:,} ریال", show_alert=True)
    await callback.message.answer(
        f"`{rial}`\n☝️ مبلغ به *ریال* ({rial // 10:,} تومان)", parse_mode="Markdown")


@card_router.callback_query(F.data.startswith("cpay:up:"))
async def cb_arm_upload(callback: CallbackQuery):
    entry = _store.get(callback.data.split(":", 2)[2])
    if not entry or entry.get("status") not in (S_CARD_SENT, S_REVIEW, S_SHORTFALL):
        await callback.answer("این فاکتور دیگر در انتظار رسید نیست.", show_alert=True)
        return
    if entry["status"] == S_REVIEW:
        await callback.answer("رسید شما قبلاً ارسال شده و در حال بررسی است.", show_alert=True)
        return
    entry["armed_until"] = _now() + _ARM_SECONDS
    _mark_dirty()
    await callback.answer()
    await callback.message.answer(
        "📸 لطفاً *تصویر رسید واریز* را همین حالا ارسال کنید (عکس یا فایل تصویر/PDF).",
        parse_mode="Markdown")


# ═════════════════════════════════════════════════════════════════════════
# ۵) دریافت تصویر رسید از کاربر
# ═════════════════════════════════════════════════════════════════════════
async def _receipt_target(message: Message, state: FSMContext) -> dict | None:
    """ورودی کارت‌به‌کارتی که این عکس باید رسیدش باشد، یا None."""
    uid = message.from_user.id if message.from_user else None
    if uid is None:
        return None
    candidates = [e for e in _entries_for_user(uid, (S_CARD_SENT, S_SHORTFALL))]
    if not candidates:
        return None
    cur = await state.get_state()
    now = _now()
    for e in candidates:
        if e.get("armed_until", 0) > now:
            return e
    for e in candidates:
        if cur is not None and cur == e.get("state_snapshot"):
            return e
    return None


def _is_receipt_media(message: Message) -> bool:
    if message.photo:
        return True
    doc = message.document
    if doc:
        mime = (doc.mime_type or "").lower()
        name = (doc.file_name or "").lower()
        return mime.startswith("image/") or mime == "application/pdf" or name.endswith(
            (".jpg", ".jpeg", ".png", ".webp", ".pdf", ".heic"))
    return False


class _HasCardReceiptTarget(Filter):
    """فیلتر روتر — فقط وقتی پیام را می‌گیرد که رسید کارت‌به‌کارت منتظر باشد."""

    async def __call__(self, message: Message, state: FSMContext) -> bool | dict:
        if not _is_receipt_media(message):
            return False
        entry = await _receipt_target(message, state)
        return {"card_entry": entry} if entry else False


@card_router.message(_HasCardReceiptTarget())
async def on_receipt(message: Message, state: FSMContext, bot: Bot, card_entry: dict):
    entry = card_entry
    async with _lock:
        if entry.get("status") not in (S_CARD_SENT, S_SHORTFALL):
            await message.answer("ℹ️ این فاکتور دیگر در انتظار رسید نیست.")
            return
        is_shortfall = entry["status"] == S_SHORTFALL
        if message.photo:
            file_id, kind = message.photo[-1].file_id, "photo"
        else:
            file_id, kind = message.document.file_id, "document"
        if is_shortfall and entry.get("receipt"):
            # رسید(های) قبلی نگه داشته می‌شود؛ رسید جدید = رسید باقی‌ماندهٔ مبلغ
            entry.setdefault("prev_receipts", []).append(entry["receipt"])
        entry["shortfall_receipt"] = is_shortfall
        entry.update({
            "status": S_REVIEW,
            "receipt": {"file_id": file_id, "kind": kind, "msg_id": message.message_id, "at": _now()},
            "full_name": message.from_user.full_name,
            "username": message.from_user.username or "",
            "armed_until": 0,
            "updated_at": _now(),
        })
        # اگر state هنوز همان state انتظار پرداخت است، snapshot را تازه کن
        cur = await state.get_state()
        if cur and cur == entry.get("state_snapshot"):
            entry["data_snapshot"] = json.loads(
                json.dumps(await state.get_data(), default=str, ensure_ascii=False))
        _mark_dirty()
    _save_store()

    await message.answer(
        ("✅ رسید باقی‌ماندهٔ مبلغ دریافت شد و برای بررسی به پشتیبانی ارسال گردید.\n"
         if is_shortfall else
         "✅ رسید شما دریافت شد و برای بررسی به پشتیبانی ارسال گردید.\n")
        + "⏳ پس از تایید، درخواست شما به‌صورت خودکار ادامه پیدا می‌کند.")
    await _send_to_admin(bot, entry)
    asyncio.create_task(_upload_receipt_and_sync(bot, entry))


def _admin_caption(entry: dict, header: str = "🧾 رسید کارت‌به‌کارت جدید") -> str:
    rial = entry["amount_rial"]
    pl = entry.get("payload_obj") or {}
    tracking = pl.get("tracking_code") or ""
    uname = f"@{entry['username']}" if entry.get("username") else "—"
    return (
        f"{header}\n\n"
        f"📄 نوع درخواست: {_service_label(entry)}\n"
        f"🏷 عنوان فاکتور: {entry.get('title') or '—'}\n"
        f"💰 مبلغ فاکتور: {rial // 10:,} تومان ({rial:,} ریال)\n"
        + _deduction_line(entry)
        + _shortfall_line(entry)
        + (f"🔹 کد رهگیری: {tracking}\n" if tracking else "")
        + f"\n👤 کاربر: {entry.get('full_name') or '—'} ({uname})\n"
        f"🆔 شناسه بله: {entry['uid']}\n"
        f"🕒 فاکتور: {_fmt_dt(entry.get('invoice_at'))} | رسید: "
        f"{_fmt_dt((entry.get('receipt') or {}).get('at'))}\n"
        f"🔖 کد پیگیری کارت‌به‌کارت: {entry['id']}\n\n"
        f"لطفاً مبلغ واریزی رسید را با مبلغ فاکتور تطبیق دهید."
    )


def _deduction_line(entry: dict) -> str:
    ded = entry.get("deduction") or {}
    d = int(ded.get("deducted_rial") or 0)
    if d <= 0:
        return ""
    total = int(ded.get("total_rial") or 0)
    return (f"➖ کسر از فاکتور: {d // 10:,} تومان"
            + (f" ({ded['detail']})" if ded.get("detail") else "")
            + (f" — مبلغ اصلی {total // 10:,} تومان" if total > 0 else "")
            + "\n")


def _shortfall_line(entry: dict) -> str:
    sf = int(entry.get("shortfall_rial") or 0)
    if sf <= 0:
        return ""
    if entry.get("shortfall_receipt"):
        return f"💸 این رسید «باقی‌ماندهٔ مبلغ» است — کسری اعلام‌شده: {sf // 10:,} تومان\n"
    return f"💸 کسری اعلام‌شده به کاربر: {sf // 10:,} تومان\n"


def _admin_kb(eid: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ تایید پرداخت", callback_data=f"cpay:ok:{eid}"),
            InlineKeyboardButton(text="❌ رد رسید", callback_data=f"cpay:rj:{eid}"),
        ],
        [InlineKeyboardButton(text="💸 مبلغ واریزی کمتر از فاکتور است (کسری)",
                              callback_data=f"cpay:sf:{eid}")],
    ])


async def _send_receipt_to_admin(bot: Bot, rc: dict, caption: str, eid: str, extra: dict):
    if rc.get("kind") == "photo":
        return await bot.send_photo(ADMIN_ID, rc["file_id"], caption=caption,
                                    reply_markup=_admin_kb(eid), **extra)
    return await bot.send_document(ADMIN_ID, rc["file_id"], caption=caption,
                                   reply_markup=_admin_kb(eid), **extra)


async def _send_to_admin(bot: Bot, entry: dict) -> None:
    rc = entry.get("receipt") or {}
    if entry.get("shortfall_receipt"):
        caption = _admin_caption(entry, "🧾 رسید باقی‌ماندهٔ مبلغ (کسری) کارت‌به‌کارت")
        # پاسخ به پیام رسید اول تا مدیر هر دو رسید را کنار هم ببیند
        extra = {"reply_to_message_id": entry["admin_msg_id"]} if entry.get("admin_msg_id") else {}
    else:
        caption = _admin_caption(entry)
        extra = {}
    try:
        try:
            msg = await _send_receipt_to_admin(bot, rc, caption, entry["id"], extra)
        except Exception:
            if not extra:
                raise
            msg = await _send_receipt_to_admin(bot, rc, caption, entry["id"], {})
        entry["admin_msg_id"] = msg.message_id
        _mark_dirty()
    except Exception as e:
        logger.error(f"[CARD-PAY] ارسال رسید به مدیر ناموفق: {e}", exc_info=True)
        try:
            await bot.send_message(ADMIN_ID, caption + "\n\n⚠️ ارسال تصویر رسید ناموفق بود.",
                                   reply_markup=_admin_kb(entry["id"]))
        except Exception:
            pass


# ═════════════════════════════════════════════════════════════════════════
# ۶) تصمیم مدیر — تایید / رد
# ═════════════════════════════════════════════════════════════════════════
async def _edit_admin_caption(callback: CallbackQuery, text: str, kb=None) -> None:
    try:
        if callback.message.photo or callback.message.document:
            await callback.message.edit_caption(caption=text, reply_markup=kb)
        else:
            await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        pass


@card_router.callback_query(F.data.startswith("cpay:rj:"))
async def cb_reject_menu(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ فقط مدیر", show_alert=True)
        return
    eid = callback.data.split(":", 2)[2]
    entry = _store.get(eid)
    if not entry or entry.get("status") != S_REVIEW:
        await callback.answer("این رسید دیگر در انتظار بررسی نیست.", show_alert=True)
        return
    rows = [[InlineKeyboardButton(text=t, callback_data=f"cpay:rr:{eid}:{k}")]
            for k, t in _REJECT_REASONS.items()]
    rows.append([InlineKeyboardButton(text="↩️ بازگشت", callback_data=f"cpay:bk:{eid}")])
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@card_router.callback_query(F.data.startswith("cpay:bk:"))
async def cb_back(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return await callback.answer()
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=_admin_kb(callback.data.split(":", 2)[2]))


@card_router.callback_query(F.data.startswith("cpay:rr:"))
async def cb_reject(callback: CallbackQuery, bot: Bot):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ فقط مدیر", show_alert=True)
        return
    _, _, eid, code = callback.data.split(":", 3)
    async with _lock:
        entry = _store.get(eid)
        if not entry or entry.get("status") != S_REVIEW:
            await callback.answer("این رسید دیگر در انتظار بررسی نیست.", show_alert=True)
            return
        reason = _REJECT_REASONS.get(code, _REJECT_REASONS["oth"])
        entry.setdefault("rejections", []).append({"at": _now(), "reason": reason})
        entry["reject_reason"] = reason
        # کاربر می‌تواند رسید صحیح را دوباره بفرستد (اگر رسید باقی‌ماندهٔ
        # کسری رد شد، همچنان فقط همان کسری را باید بفرستد)
        entry["status"] = S_SHORTFALL if entry.get("shortfall_receipt") else S_CARD_SENT
        entry["armed_until"] = _now() + 24 * 3600
        entry["updated_at"] = _now()
        _mark_dirty()
    _save_store()
    await callback.answer("رسید رد شد")
    await _edit_admin_caption(callback, _admin_caption(entry, f"❌ رد شد — {reason}"))
    try:
        await bot.send_message(
            entry["uid"],
            f"❌ رسید کارت‌به‌کارت شما تایید نشد.\n\nعلت: {reason}\n\n"
            "در صورت واریز صحیح، لطفاً تصویر رسید درست را دوباره همین‌جا ارسال کنید "
            "یا با پشتیبانی تماس بگیرید.")
    except Exception:
        pass
    _sync_panel(entry, status_override="REJECTED")


@card_router.callback_query(F.data.startswith("cpay:ok:") | F.data.startswith("cpay:fo:"))
async def cb_approve(callback: CallbackQuery, bot: Bot):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ فقط مدیر", show_alert=True)
        return
    action, eid = callback.data.split(":")[1], callback.data.split(":", 2)[2]
    force = action == "fo"
    entry = _store.get(eid)
    if not entry:
        await callback.answer("رسید پیدا نشد.", show_alert=True)
        return
    if entry.get("status") == S_PAID_GATEWAY:
        await callback.answer("⛔ کاربر از درگاه پرداخت کرده — تایید مجاز نیست.", show_alert=True)
        await _edit_admin_caption(callback, _admin_caption(entry, "⚠️ لغو شد — پرداخت از درگاه انجام شده"))
        return
    if entry.get("status") != S_REVIEW:
        await callback.answer("این رسید قبلاً بررسی شده است.", show_alert=True)
        return

    uid = entry["uid"]
    ptype = (entry.get("payload_obj") or {}).get("type", "")
    raw_state, _ = await _get_state(bot, uid)
    snapshot = entry.get("state_snapshot")
    state_ok = ptype in _PAYLOAD_ROUTED_TYPES or raw_state == snapshot
    if not state_ok and not force:
        await callback.answer()
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="♻️ بازگردانی وضعیت و تایید", callback_data=f"cpay:fo:{eid}")],
            [InlineKeyboardButton(text="❌ رد رسید", callback_data=f"cpay:rj:{eid}")],
        ])
        await _edit_admin_caption(
            callback,
            _admin_caption(entry, "⚠️ وضعیت کاربر تغییر کرده است") +
            f"\n\nوضعیت هنگام فاکتور: {snapshot}\nوضعیت فعلی: {raw_state}\n"
            "با «بازگردانی وضعیت و تایید»، کاربر به مرحلهٔ انتظار پرداخت برگردانده "
            "شده و پرداخت تایید می‌شود (فرایند فعلی او لغو می‌شود).",
            kb)
        return

    async with _lock:
        if entry.get("status") != S_REVIEW:
            await callback.answer("این رسید قبلاً بررسی شده است.", show_alert=True)
            return
        entry["status"] = S_APPROVED
        entry["approved_at"] = _now()
        entry["updated_at"] = _now()
        _mark_dirty()
    _save_store()
    await callback.answer("در حال اعمال پرداخت…")

    if force and not state_ok:
        await _restore_state(bot, entry)

    ok, err = await _replay_successful_payment(bot, entry)
    if ok:
        await _edit_admin_caption(callback, _admin_caption(entry, "✅ تایید شد — پرداخت اعمال گردید"))
    else:
        await _edit_admin_caption(
            callback,
            _admin_caption(entry, "⚠️ تایید شد ولی اعمال خودکار با خطا مواجه شد") +
            f"\n\nخطا: {err}\nلطفاً ادامهٔ درخواست را دستی پیگیری کنید.")
    _sync_panel(entry)


# ── کسری مبلغ: مدیر مبلغ کمبود را وارد می‌کند → فقط همان کسری از کاربر خواسته می‌شود
_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def _parse_toman(text: str) -> int | None:
    t = (text or "").translate(_FA_DIGITS)
    for ch in (",", "،", "٬", " ", "\u200c", "تومان", "ریال"):
        t = t.replace(ch, "")
    return int(t) if t.isdigit() else None


class _AwaitingShortfallAmount(Filter):
    """فقط پیام متنی مدیر را وقتی منتظر مبلغ کسری هستیم می‌گیرد (دستورها رد می‌شوند)."""

    async def __call__(self, message: Message) -> bool:
        global _shortfall_wait
        if not _shortfall_wait or not message.from_user or message.from_user.id != ADMIN_ID:
            return False
        if not message.text:
            return False
        if _now() > _shortfall_wait.get("until", 0) or message.text.startswith("/"):
            # مهلت تمام شده یا مدیر دستور دیگری زد — انتظار لغو، پیام به مسیر عادی برود
            _shortfall_wait = None
            return False
        return True


@card_router.callback_query(F.data.startswith("cpay:sf:"))
async def cb_shortfall_start(callback: CallbackQuery):
    global _shortfall_wait
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ فقط مدیر", show_alert=True)
        return
    eid = callback.data.split(":", 2)[2]
    entry = _store.get(eid)
    if not entry or entry.get("status") != S_REVIEW:
        await callback.answer("این رسید دیگر در انتظار بررسی نیست.", show_alert=True)
        return
    _shortfall_wait = {
        "eid": eid,
        "until": _now() + _SHORTFALL_INPUT_SECONDS,
        "chat_id": callback.message.chat.id,
        "msg_id": callback.message.message_id,
        "is_media": bool(callback.message.photo or callback.message.document),
    }
    await callback.answer()
    rial = entry["amount_rial"]
    await callback.message.answer(
        f"💸 کسری مبلغ — کد {eid}\n\n"
        f"مبلغ فاکتور: {rial // 10:,} تومان\n"
        + _deduction_line(entry)
        + "\nچه مقدار از مبلغ کم واریز شده است؟\n"
        "لطفاً مبلغ کسری را به *تومان* و فقط به‌صورت عدد بفرستید (مثلاً 25000).",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="↩️ انصراف", callback_data=f"cpay:sx:{eid}")]]))


@card_router.callback_query(F.data.startswith("cpay:sx:"))
async def cb_shortfall_cancel(callback: CallbackQuery):
    global _shortfall_wait
    if callback.from_user.id != ADMIN_ID:
        return await callback.answer()
    _shortfall_wait = None
    await callback.answer("لغو شد")
    try:
        await callback.message.edit_text("↩️ ثبت کسری لغو شد؛ رسید همچنان منتظر تصمیم شماست.")
    except Exception:
        pass


@card_router.message(_AwaitingShortfallAmount())
async def on_shortfall_amount(message: Message, bot: Bot):
    global _shortfall_wait
    wait = _shortfall_wait or {}
    eid = wait.get("eid")
    toman = _parse_toman(message.text)
    async with _lock:
        entry = _store.get(eid)
        if not entry or entry.get("status") != S_REVIEW:
            _shortfall_wait = None
            await message.answer("ℹ️ این رسید دیگر در انتظار بررسی نیست؛ کسری ثبت نشد.")
            return
        invoice_toman = entry["amount_rial"] // 10
        if toman is None or toman <= 0 or toman >= invoice_toman:
            await message.answer(
                f"⚠️ مبلغ نامعتبر است. یک عدد بزرگ‌تر از صفر و کمتر از مبلغ فاکتور "
                f"({invoice_toman:,} تومان) به تومان بفرستید، یا «انصراف» را بزنید.")
            return
        _shortfall_wait = None
        entry.update({
            "status": S_SHORTFALL,
            "shortfall_rial": toman * 10,
            "shortfall_at": _now(),
            "armed_until": _now() + 24 * 3600,
            "updated_at": _now(),
        })
        entry.setdefault("shortfalls", []).append({"at": _now(), "rial": toman * 10})
        _mark_dirty()
    _save_store()

    sent = await _send_shortfall_offer(entry)
    await message.answer(
        f"✅ کسری {toman:,} تومان ثبت شد"
        + (" و برای کاربر ارسال گردید. پس از ارسال رسید باقی‌مانده، دوباره برای تایید "
           "به شما نمایش داده می‌شود." if sent else
           "، ولی ارسال پیام به کاربر ناموفق بود (شاید ربات را مسدود کرده باشد)."))
    header = f"💸 کسری {toman:,} تومان اعلام شد — منتظر رسید باقی‌مانده"
    try:
        if wait.get("is_media"):
            await bot.edit_message_caption(chat_id=wait["chat_id"], message_id=wait["msg_id"],
                                           caption=_admin_caption(entry, header), reply_markup=None)
        else:
            await bot.edit_message_text(_admin_caption(entry, header), chat_id=wait["chat_id"],
                                        message_id=wait["msg_id"], reply_markup=None)
    except Exception:
        pass
    _sync_panel(entry)


async def _send_shortfall_offer(entry: dict) -> bool:
    sf_rial = int(entry["shortfall_rial"])
    sf_toman = sf_rial // 10
    caption = (
        "💸 *کسری مبلغ واریزی*\n\n"
        f"مبلغ واریزی شما برای فاکتور «{entry.get('title') or _service_label(entry)}» "
        f"با مبلغ فاکتور مطابقت نداشت و *{sf_toman:,} تومان* کمتر واریز شده است.\n\n"
        "لطفاً باقی‌ماندهٔ مبلغ را به شماره کارت زیر واریز نمایید و *عکس رسید باقی‌مانده "
        "مبلغ* را همین‌جا ارسال کنید:\n\n"
        f"🔢 شماره کارت:\n`{CARD_PAY_NUMBER}`\n"
        f"👤 به نام: *{CARD_PAY_HOLDER}*\n"
        + (f"🏦 {CARD_PAY_BANK}\n" if CARD_PAY_BANK else "")
        + f"\n💰 مبلغ باقی‌مانده: *{sf_toman:,} تومان*  (`{sf_rial}` ریال)\n\n"
        "⏳ پس از تایید پشتیبانی، درخواست شما برای ثبت در سامانه ادامه پیدا می‌کند."
    )
    try:
        from card_payment_image import render_card_image
        image = await asyncio.to_thread(
            render_card_image, CARD_PAY_NUMBER, CARD_PAY_HOLDER, sf_toman,
            CARD_PAY_BANK or None, CARD_PAY_BRAND)
    except Exception as e:
        logger.error(f"[CARD-PAY] ساخت تصویر کارت (کسری) ناموفق: {e}", exc_info=True)
        image = None
    ok = await _send_offer_message(entry["uid"], entry, caption, image, amount_rial=sf_rial)
    logger.info(f"[CARD-PAY] کسری {sf_toman:,} تومان برای id={entry['id']} "
                f"uid={entry['uid']} اعلام شد (ارسال={'موفق' if ok else 'ناموفق'})")
    return ok


async def _restore_state(bot: Bot, entry: dict) -> None:
    dp = getattr(runtime_state, "dp", None)
    if dp is None or not entry.get("state_snapshot"):
        return
    uid = entry["uid"]
    key = StorageKey(bot_id=bot.id, chat_id=uid, user_id=uid)
    await dp.storage.set_state(key, state=entry["state_snapshot"])
    await dp.storage.set_data(key, entry.get("data_snapshot") or {})
    logger.info(f"[CARD-PAY] state کاربر {uid} به {entry['state_snapshot']} بازگردانده شد")


async def _replay_successful_payment(bot: Bot, entry: dict) -> tuple[bool, str]:
    """ساخت رویداد successful_payment معادل فاکتور اصلی و عبور از Dispatcher.

    همهٔ هندلرهای پرداخت پروژه (global_successful_payment_handler و هندلرهای
    state-محور سرویس‌ها) دقیقاً مثل پرداخت واقعی کیف پول بله اجرا می‌شوند.
    """
    dp = getattr(runtime_state, "dp", None)
    if dp is None:
        return False, "Dispatcher در دسترس نیست"
    uid = entry["uid"]
    full_name = entry.get("full_name") or ""
    first, _, last = full_name.partition(" ")
    rc = entry.get("receipt") or {}
    try:
        msg = Message(
            message_id=int(rc.get("msg_id") or 1),
            date=datetime.datetime.now(datetime.timezone.utc),
            chat=Chat(id=uid, type="private"),
            from_user=User(id=uid, is_bot=False, first_name=first or "کاربر",
                           last_name=last or None, username=entry.get("username") or None),
            successful_payment=SuccessfulPayment(
                currency="IRR",
                total_amount=int(entry["amount_rial"]),
                invoice_payload=entry["payload"],
                telegram_payment_charge_id=f"{_FAKE_CHARGE_PREFIX}{entry['id']}",
                provider_payment_charge_id=f"{_FAKE_CHARGE_PREFIX}{entry['id']}",
            ),
        )
        update = Update(update_id=int(time.time() * 1000) % 2_000_000_000, message=msg)
        await dp.feed_update(bot, update)
        logger.info(f"[CARD-PAY] پرداخت کارت‌به‌کارت id={entry['id']} برای uid={uid} بازپخش شد")
        return True, ""
    except Exception as e:
        logger.error(f"[CARD-PAY] بازپخش پرداخت id={entry['id']} ناموفق: {e}", exc_info=True)
        return False, repr(e)[:300]


# ═════════════════════════════════════════════════════════════════════════
# ۷) همگام‌سازی با پنل ادمین (CardPayment)
# ═════════════════════════════════════════════════════════════════════════
_PANEL_STATUS = {
    S_REVIEW: "PENDING_REVIEW", S_APPROVED: "APPROVED", S_CARD_SENT: "AWAITING_RECEIPT",
    S_PAID_GATEWAY: "PAID_VIA_GATEWAY", S_EXPIRED: "EXPIRED",
    S_SHORTFALL: "AWAITING_RECEIPT",
}

# نوع پرداخت برای محاسبهٔ سود در پنل (src/lib/profit.ts → computeCardPaymentProfit)
_PREPAY_TYPES = {"reg_prepay", "bulk_prepay"}
_FINAL_TYPES = {"lavayeh", "tajdid_nazar", "bulk_settlement", "admin_fee", "clearance"}


def _payment_kind(entry: dict) -> str:
    ptype = (entry.get("payload_obj") or {}).get("type", "")
    if ptype in _PREPAY_TYPES:
        return "PREPAY"     # کل مبلغ پیش‌پرداخت = سود
    if ptype in _FINAL_TYPES:
        return "FINAL"      # سود = مبلغ − هزینهٔ سامانه
    return "DIRECT"         # استعلام/ارزش منطقه‌ای/اشتراک/پیام — بدون هزینهٔ سامانه


def _sync_panel(entry: dict, status_override: str | None = None) -> None:
    # فقط ورودی‌هایی که رسید داشته‌اند در پنل ثبت می‌شوند
    if not entry.get("receipt"):
        return
    payload = {
        "externalId": entry["id"],
        "baleUserId": str(entry["uid"]),
        "fullName": entry.get("full_name") or None,
        "serviceType": _panel_service_type(entry),
        "serviceLabel": _service_label(entry),
        "invoiceTitle": entry.get("title") or None,
        "trackingCode": (entry.get("payload_obj") or {}).get("tracking_code") or None,
        "amount": entry["amount_rial"] // 10,   # تومان — مطابق سایر مبالغ پنل
        "paymentKind": _payment_kind(entry),
        "status": status_override or _PANEL_STATUS.get(entry.get("status"), "PENDING_REVIEW"),
        "receiptUrl": entry.get("receipt_url") or None,
        "rejectReason": entry.get("reject_reason") if status_override == "REJECTED" else None,
        "approvedAt": (datetime.datetime.fromtimestamp(entry["approved_at"], datetime.timezone.utc).isoformat()
                       if entry.get("approved_at") else None),
    }
    try:
        from panel_sync import _panel_request, _schedule_panel_job
        _schedule_panel_job(_panel_request("POST", f"{ADMIN_API_BASE}/admin/card-payments", json=payload))
    except Exception as e:
        logger.warning(f"[CARD-PAY] همگام‌سازی پنل ناموفق: {e}")


async def _upload_receipt_and_sync(bot: Bot, entry: dict) -> None:
    """دانلود رسید از بله و آپلود در پنل (public/uploads) — سپس ثبت رکورد."""
    rc = entry.get("receipt") or {}
    try:
        f = await bot.get_file(rc["file_id"])
        buf = io.BytesIO()
        await bot.download_file(f.file_path, destination=buf)
        ext = os.path.splitext(f.file_path or "")[1] or (".jpg" if rc.get("kind") == "photo" else ".bin")
        form = aiohttp.FormData()
        form.add_field("files", buf.getvalue(), filename=f"receipt-{entry['id']}{ext}")
        async with aiohttp.ClientSession(headers=PANEL_AUTH_HEADERS) as s:
            async with s.post(f"{ADMIN_API_BASE}/admin/upload", data=form,
                              timeout=aiohttp.ClientTimeout(total=30)) as resp:
                data = await resp.json(content_type=None)
        files = (data or {}).get("files") or []
        if files:
            entry["receipt_url"] = files[0].get("url")
            _mark_dirty()
    except Exception as e:
        logger.warning(f"[CARD-PAY] آپلود رسید در پنل ناموفق (رکورد بدون تصویر ثبت می‌شود): {e}")
    _sync_panel(entry)


# ═════════════════════════════════════════════════════════════════════════
# ۸) راه‌اندازی
# ═════════════════════════════════════════════════════════════════════════
def setup_card_payment(dp) -> None:
    """در bot.py — *قبل از* dp.include_router(router) صدا زده شود:

        import card_payment
        card_payment.setup_card_payment(dp)          # قبل از include_router(router)
        ...
        asyncio.create_task(card_payment.card_payment_loop(bot))   # در main()
    """
    _load_store()
    dp.include_router(card_router)
    dp.message.outer_middleware(GatewayPaymentObserver())


def save_now() -> None:
    """برای فراخوانی در shutdown (اختیاری)."""
    if _dirty:
        _save_store()
