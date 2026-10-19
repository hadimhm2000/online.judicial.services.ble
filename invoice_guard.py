"""
invoice_guard.py — جلوگیری از پرداخت «فاکتور قدیمی/نامربوط»
═══════════════════════════════════════════════════════════════

مشکل: فاکتورهای بله تا وقتی پرداخت نشده‌اند در چت قابل پرداخت می‌مانند و
مسیر پردازش پرداخت (global_successful_payment_handler) برای بیشتر سرویس‌ها از
روی «state فعلی کاربر» انتخاب می‌شود، نه از روی فاکتوری که پرداخت شده. کاربر
می‌توانست در مرحلهٔ پرداخت یک سرویس گران (مثلاً هزینهٔ نهایی لایحه) یک فاکتور
ارزان و قدیمی (استعلام، پیش‌پرداخت، …) را پرداخت کند و سرویس گران «پرداخت‌شده»
ثبت شود.

این ماژول فقط دو حالت مشخصاً اشتباه را رد می‌کند و بقیهٔ پرداخت‌ها را
دست‌نخورده عبور می‌دهد:

  ۱) فاکتور از نوع سرویس دیگری است و کاربر در state انتظار پرداختِ یک سرویس
     state-محور است (مسیر پردازش، پرداخت را اشتباهی به آن سرویس می‌داد).
  ۲) مبلغ فاکتور پرداخت‌شده «کمتر» از آخرین فاکتوری است که ربات با همان
     payload برای همان کاربر فرستاده (فاکتور قدیمی‌تر و ارزان‌تر).

بررسی در دو جا انجام می‌شود:
  - pre_checkout_query (handlers.py): پیش از کسر پول؛ فاکتور رد می‌شود.
  - successful_payment (InvoiceGuardMiddleware): اگر بله بدون منتظر ماندن
    برای pre_checkout پرداخت را انجام داد، مبلغ به کیف پول کاربر برمی‌گردد،
    به کاربر و مدیر اطلاع داده می‌شود و پرداخت به هیچ سرویسی اعمال نمی‌شود.

پرداخت‌های بازپخش‌شدهٔ کیف پول (WALLET-…) و کارت‌به‌کارت تاییدشدهٔ مدیر (CARD-…)
بررسی نمی‌شوند؛ آن‌ها قبلاً state و مبلغ را خودشان تطبیق داده‌اند.
"""
import json
import logging
import os
import time

from aiogram.dispatcher.middlewares.base import BaseMiddleware

from states import Form

logger = logging.getLogger(__name__)

STORE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "invoice_guard.json")
KEEP_SECONDS = 30 * 24 * 3600

# نوع payload → state انتظار پرداختی که global_successful_payment_handler پرداخت
# این نوع را در آن به سرویس درست می‌رساند.
STATE_FOR_TYPE = {
    "cart": Form.waiting_for_payment_receipt.state,
    "single": Form.waiting_for_payment_receipt.state,
    "bulk_inquiry": Form.waiting_for_payment_receipt.state,
    "lavayeh": Form.waiting_for_lavayeh_payment_receipt.state,
    "regional_value": Form.rv_waiting_payment.state,
    "tajdid_nazar": Form.waiting_for_tn_payment_receipt.state,
    "subscription": Form.subscription_waiting_payment.state,
}
GUARDED_STATES = set(STATE_FOR_TYPE.values())

# انواعی که پیش از هر بررسی state، از روی payload به هندلر خودشان می‌رسند
# (روترهای جدا یا ابتدای global_successful_payment_handler) — در هر state مجازند.
SAFE_ANYWHERE_TYPES = {
    "wallet_topup", "pending_case", "clearance", "panel_message", "single_use", "admin_fee",
}

# انواع شناخته‌شده‌ای که مسیرشان در زنجیرهٔ state قرار دارد (بعد از بررسی state)
OTHER_KNOWN_TYPES = {"reg_prepay", "bulk_prepay", "bulk_settlement"}

# انواعی که برای هر کاربر در هر لحظه فقط «آخرین» فاکتورشان معتبر است.
# (admin_fee و … عمداً نیستند: مدیر ممکن است چند فاکتور هم‌زمان بفرستد.)
LATEST_ONLY_TYPES = set(STATE_FOR_TYPE) | OTHER_KNOWN_TYPES

_REPLAY_PREFIXES = ("WALLET-", "CARD-")

_store: dict = {}
_loaded = False


def _load() -> None:
    global _store, _loaded
    _loaded = True
    try:
        if os.path.exists(STORE_FILE):
            with open(STORE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                _store = data
    except Exception as e:
        logger.error(f"[INVOICE-GUARD] خطا در خواندن {STORE_FILE}: {e}")


def _save() -> None:
    try:
        os.makedirs(os.path.dirname(STORE_FILE), exist_ok=True)
        tmp = STORE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_store, f, ensure_ascii=False)
        os.replace(tmp, STORE_FILE)
    except Exception as e:
        logger.error(f"[INVOICE-GUARD] خطا در ذخیرهٔ {STORE_FILE}: {e}")


def _key(uid, payload: str) -> str:
    return f"{int(uid)}|{payload}"


def payload_type(payload) -> str:
    try:
        obj = json.loads(payload or "{}")
        return str(obj.get("type") or "") if isinstance(obj, dict) else ""
    except Exception:
        return ""


def record(invoice_data: dict) -> None:
    """پس از هر فاکتور ارسالی (از card_payment.track_invoice) صدا زده می‌شود. هرگز استثنا نمی‌دهد."""
    try:
        if not _loaded:
            _load()
        payload = str(invoice_data.get("payload") or "")
        if payload_type(payload) not in LATEST_ONLY_TYPES:
            return
        uid = int(invoice_data.get("chat_id"))
        amount = int(sum(int(p.get("amount", 0)) for p in (invoice_data.get("prices") or [])))
        if amount <= 0:
            return
        now = time.time()
        _store[_key(uid, payload)] = {"amount": amount, "at": now}
        for k in [k for k, v in _store.items() if now - float(v.get("at", 0)) > KEEP_SECONDS]:
            _store.pop(k, None)
        _save()
    except Exception as e:
        logger.error(f"[INVOICE-GUARD] ثبت فاکتور ناموفق: {e}")


def check(uid, payload: str, total_amount: int, current_state) -> str | None:
    """None = پرداخت مجاز است؛ در غیر این صورت علت رد (برای لاگ)."""
    try:
        if not _loaded:
            _load()
        ptype = payload_type(payload)
        if current_state in GUARDED_STATES and ptype not in SAFE_ANYWHERE_TYPES \
                and (ptype in STATE_FOR_TYPE or ptype in OTHER_KNOWN_TYPES) \
                and STATE_FOR_TYPE.get(ptype) != current_state:
            return f"نوع فاکتور «{ptype}» با مرحلهٔ فعلی کاربر ({current_state}) نمی‌خواند"
        if ptype in LATEST_ONLY_TYPES:
            rec = _store.get(_key(uid, payload))
            if rec and int(total_amount or 0) < int(rec.get("amount", 0)):
                return (f"مبلغ فاکتور ({int(total_amount or 0):,} ریال) کمتر از آخرین فاکتور "
                        f"صادرشده ({int(rec['amount']):,} ریال) است — فاکتور قدیمی")
    except Exception as e:
        logger.error(f"[INVOICE-GUARD] بررسی ناموفق (پرداخت مجاز شد): {e}")
    return None


STALE_INVOICE_TEXT = (
    "⚠️ این فاکتور منقضی شده یا مربوط به مرحلهٔ فعلی شما نیست.\n"
    "لطفاً فقط آخرین فاکتوری را که ربات برایتان فرستاده پرداخت کنید.")


class InvoiceGuardMiddleware(BaseMiddleware):
    """پشتیبان pre_checkout: پرداخت نامعتبر به کیف پول برمی‌گردد و به سرویسی اعمال نمی‌شود."""

    async def __call__(self, handler, event, data: dict):
        sp = getattr(event, "successful_payment", None)
        if sp is None or not getattr(event, "from_user", None):
            return await handler(event, data)
        charge = str(getattr(sp, "telegram_payment_charge_id", "") or "")
        if charge.startswith(_REPLAY_PREFIXES):
            return await handler(event, data)
        try:
            state = data.get("state")
            current_state = await state.get_state() if state is not None else None
        except Exception:
            current_state = None
        uid = event.from_user.id
        total = int(sp.total_amount or 0)
        reason = check(uid, str(sp.invoice_payload or ""), total, current_state)
        if reason is None:
            return await handler(event, data)

        logger.error(f"[INVOICE-GUARD] پرداخت نامعتبر کاربر {uid} به کیف پول برگشت: {reason} "
                     f"| charge={charge}")
        bot = data.get("bot")
        try:
            import wallet
            await wallet.credit(uid, total // 10, "refund", f"فاکتور منقضی/نامربوط {charge[:30]}")
            balance_line = f"\n👛 موجودی کیف پول: {wallet.balance(uid):,} تومان"
        except Exception as e:
            logger.error(f"[INVOICE-GUARD] برگشت به کیف پول ناموفق: {e}", exc_info=True)
            balance_line = ""
        if bot is not None:
            try:
                await bot.send_message(
                    uid,
                    f"{STALE_INVOICE_TEXT}\n\nمبلغ {total // 10:,} تومان به کیف پول شما برگشت و از "
                    f"فاکتورهای بعدی کسر می‌شود.{balance_line}")
            except Exception:
                pass
            try:
                from config import ADMIN_ID
                await bot.send_message(
                    ADMIN_ID,
                    f"⚠️ پرداخت فاکتور نامعتبر — کاربر {uid}\n{reason}\n"
                    f"مبلغ {total // 10:,} تومان به کیف پول کاربر برگشت.\ncharge: {charge}")
            except Exception:
                pass
        return None
