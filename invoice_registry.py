"""
invoice_registry.py — دفتر فاکتورهای پرونده‌محور (۱۴۰۵/۰۸)
═══════════════════════════════════════════════════════════════

مسئله (لاگ ۱۴۰۵/۰۸/۲۵): پرداخت فاکتور لایحه/اظهارنامه از روی «state فعلی کاربر»
و payload مشترک {"type": "lavayeh", "uid": ...} مسیریابی می‌شد؛ در نتیجه
  • اگر کاربر در لحظهٔ پرداخت state دیگری داشت (چند پرونده، شروع فلوی دیگر،
    کندی ربات)، پرداخت به شاخهٔ عمومی می‌افتاد و پول به کیف پول برمی‌گشت؛
  • فاکتور قدیمی/تکراری را می‌شد چند بار پرداخت کرد؛
  • فاکتور هرگز منقضی نمی‌شد.

راه‌حل: هر فاکتور نهایی پرونده یک شناسهٔ یکتا (inv) دارد و در payload
{"type": "pending_case", "uid", "tc", "st", "inv"} می‌آید. پرداخت دقیقاً به
همان پرونده (tc = کد رهگیری) می‌رسد و امضای همان پرونده شروع می‌شود — مستقل از
state، و برای هر تعداد لایحه/اظهارنامه‌ای که کاربر هم‌زمان ثبت کرده.

قواعد:
  ۱) انقضا: هر فاکتور ۲۴ ساعت پس از صدور منقضی می‌شود (EXPIRE_SECONDS).
  ۲) فقط «آخرین» فاکتور هر پرونده معتبر است؛ صدور فاکتور جدید، قبلی را
     جایگزین‌شده (superseded) می‌کند.
  ۳) قفل پرداخت هم‌زمان: pre_checkout فاکتور را «claim» می‌کند؛ تا CLAIM_SECONDS
     کسی نمی‌تواند همان فاکتور را هم‌زمان بپردازد.
  ۴) یک‌بارمصرف: پس از پرداخت، فاکتور (و کل پرونده) paid می‌شود؛ پرداخت دوم
     رد می‌شود (pre_checkout) یا — اگر بله بدون pre_checkout پرداخت را کامل کرد —
     مبلغ به کیف پول برمی‌گردد.
  ۵) پرداخت‌های بازپخش‌شده (کارت‌به‌کارت تاییدشدهٔ مدیر / کیف پول) چون پول واقعاً
     دریافت شده، حتی برای فاکتور منقضی پذیرفته می‌شوند، مگر پرونده قبلاً پرداخت
     شده باشد.

داده روی دیسک (data/invoice_registry.json) نگه‌داری می‌شود تا ری‌استارت چیزی
را گم نکند. هیچ تماس شبکه‌ای ندارد (سریع و بدون timeout).
"""
import json
import logging
import os
import secrets
import threading
import time

logger = logging.getLogger(__name__)

STORE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "invoice_registry.json")

PAYLOAD_TYPE = "pending_case"
EXPIRE_SECONDS = 24 * 3600        # اعتبار هر فاکتور
CLAIM_SECONDS = 3 * 60            # مدت قفل پس از pre_checkout (پرداخت هم‌زمان)
KEEP_SECONDS = 30 * 24 * 3600     # نگه‌داری رکورد برای تشخیص پرداخت دیرهنگام

OPEN = "open"
CLAIMED = "claimed"
PAID = "paid"
SUPERSEDED = "superseded"
EXPIRED = "expired"
_LIVE = (OPEN, CLAIMED)

REPLAY_PREFIXES = ("WALLET-", "CARD-")

# پیام‌های کاربر (ریز دلیل رد)
MESSAGES = {
    "expired": ("⏰ این فاکتور منقضی شده است (اعتبار هر فاکتور ۲۴ ساعت است).\n"
                "از منوی «پرونده‌های در انتظار امضا و پرداخت» فاکتور جدید همین پرونده را دریافت کنید."),
    "superseded": ("این فاکتور جایگزین شده است و فقط آخرین فاکتور هر پرونده قابل پرداخت است.\n"
                   "لطفاً آخرین فاکتور ارسالی را پرداخت کنید."),
    "paid": "هزینهٔ این پرونده قبلاً پرداخت شده است.",
    "busy": "پرداخت این فاکتور هم‌اکنون در حال انجام است. لطفاً چند دقیقه صبر کنید.",
    "owner": "این فاکتور متعلق به حساب شما نیست.",
}

_lock = threading.RLock()
_store: dict = {}
_loaded = False


# ───────────────────────── ذخیره‌سازی ─────────────────────────

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
        logger.error(f"[INVOICE-REG] خطا در خواندن {STORE_FILE}: {e}")


def _save() -> None:
    try:
        os.makedirs(os.path.dirname(STORE_FILE), exist_ok=True)
        tmp = STORE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_store, f, ensure_ascii=False)
        os.replace(tmp, STORE_FILE)
    except Exception as e:
        logger.error(f"[INVOICE-REG] خطا در ذخیرهٔ {STORE_FILE}: {e}")


def _ensure() -> None:
    if not _loaded:
        _load()


def _purge(now: float) -> None:
    for k in [k for k, v in _store.items() if now - float(v.get("created_at", 0)) > KEEP_SECONDS]:
        _store.pop(k, None)


def reset_for_tests() -> None:
    global _store, _loaded
    with _lock:
        _store = {}
        _loaded = True


# ───────────────────────── payload ─────────────────────────

def build_payload(uid: int, tc: str, st: str, inv: str) -> str:
    return json.dumps({"type": PAYLOAD_TYPE, "uid": int(uid), "tc": str(tc),
                       "st": st or "", "inv": inv})


def inv_of(payload) -> str:
    """شناسهٔ فاکتور از payload؛ "" اگر نداشت (فاکتورهای قدیمی/غیرپرونده‌ای)."""
    try:
        obj = json.loads(payload or "{}")
        if isinstance(obj, dict):
            return str(obj.get("inv") or "")
    except Exception:
        pass
    return ""


# ───────────────────────── وضعیت ─────────────────────────

def _effective(rec: dict, now: float) -> str:
    """وضعیت واقعی با اعمال انقضا و آزادشدن قفل‌های کهنه (بدون تغییر رکورد)."""
    st = rec.get("status")
    if st in _LIVE:
        if now > float(rec.get("expires_at", 0)):
            return EXPIRED
        if st == CLAIMED and now - float(rec.get("claimed_at", 0)) > CLAIM_SECONDS:
            return OPEN
    return st


def _case_records(uid: int, tc: str):
    return [r for r in _store.values() if r.get("uid") == int(uid) and r.get("tc") == str(tc)]


def case_paid(uid: int, tc: str) -> bool:
    with _lock:
        _ensure()
        return any(r.get("status") == PAID for r in _case_records(uid, tc))


def active_claim(uid: int, tc: str) -> bool:
    """آیا همین حالا پرداختی روی فاکتورهای این پرونده در جریان است؟"""
    now = time.time()
    with _lock:
        _ensure()
        return any(_effective(r, now) == CLAIMED for r in _case_records(uid, tc))


def get(inv: str) -> dict | None:
    with _lock:
        _ensure()
        rec = _store.get(inv)
        return dict(rec) if rec else None


# ───────────────────────── صدور فاکتور ─────────────────────────

def issue(uid: int, tc: str, st: str, amount_rial: int) -> tuple[str, str] | None:
    """فاکتور جدید برای پرونده؛ (inv, payload) یا None اگر پرداختی هم‌زمان در جریان است
    یا پرونده قبلاً پرداخت شده. فاکتورهای باز قبلی همین پرونده جایگزین‌شده می‌شوند."""
    now = time.time()
    released = []
    with _lock:
        _ensure()
        recs = _case_records(uid, tc)
        if any(r.get("status") == PAID for r in recs):
            return None
        if any(_effective(r, now) == CLAIMED for r in recs):
            return None
        for r in recs:
            if r.get("status") in _LIVE:
                r["status"] = SUPERSEDED
                r["closed_at"] = now
                released.append(r.get("payload"))
        inv = secrets.token_hex(5)
        payload = build_payload(uid, tc, st, inv)
        _store[inv] = {
            "inv": inv, "uid": int(uid), "tc": str(tc), "st": st or "",
            "amount_rial": int(amount_rial or 0), "payload": payload,
            "created_at": now, "expires_at": now + EXPIRE_SECONDS, "status": OPEN,
        }
        _purge(now)
        _save()
    _release_wallet_holds(uid, released)
    logger.info(f"[INVOICE-REG] فاکتور صادر شد inv={inv} uid={uid} tc={tc} مبلغ={int(amount_rial or 0):,} ریال "
                f"(انقضا ۲۴ ساعت){' — قبلی‌ها جایگزین شدند' if released else ''}")
    return inv, payload


def _release_wallet_holds(uid: int, payloads) -> None:
    """رزرو کیف پولِ فاکتورهای جایگزین‌شده آزاد شود تا از فاکتور جدید کسر شود."""
    for p in payloads:
        if not p:
            continue
        try:
            import wallet
            wallet.release_hold(uid, p)
        except Exception as e:
            logger.debug(f"[INVOICE-REG] آزادسازی رزرو ناموفق: {e}")


# ───────────────────────── pre_checkout ─────────────────────────

def claim(inv: str, uid: int) -> tuple[bool, str]:
    """تایید/رد pre_checkout. (True, "") یا (False, کلید پیام).
    فاکتور ناشناخته (مثلاً فایل دفتر از بین رفته) اجازه داده می‌شود و لاگ می‌شود."""
    now = time.time()
    with _lock:
        _ensure()
        rec = _store.get(inv)
        if rec is None:
            logger.warning(f"[INVOICE-REG] فاکتور ناشناخته در pre_checkout (مجاز شد): inv={inv} uid={uid}")
            return True, ""
        if rec.get("uid") != int(uid):
            return False, "owner"
        if any(r.get("status") == PAID for r in _case_records(rec["uid"], rec["tc"])):
            return False, "paid"
        st = _effective(rec, now)
        if st == EXPIRED:
            if rec.get("status") in _LIVE:
                rec["status"] = EXPIRED
                rec["closed_at"] = now
                _save()
            return False, "expired"
        if st in (SUPERSEDED, PAID, EXPIRED):
            return False, "superseded" if st == SUPERSEDED else ("paid" if st == PAID else "expired")
        if st == CLAIMED:
            return False, "busy"
        rec["status"] = CLAIMED
        rec["claimed_at"] = now
        _save()
        return True, ""


def unclaim(inv: str) -> None:
    """آزادکردن قفل (پرداخت انجام نشد)."""
    with _lock:
        _ensure()
        rec = _store.get(inv)
        if rec and rec.get("status") == CLAIMED:
            rec["status"] = OPEN
            _save()


# ───────────────────────── successful_payment ─────────────────────────

def settle(inv: str, uid: int, charge: str = "") -> tuple[bool, str]:
    """ثبت پرداخت موفق. (True, "") یا (False, کلید پیام) → فراخوان باید پول را به کیف پول برگرداند."""
    now = time.time()
    replay = str(charge or "").startswith(REPLAY_PREFIXES)
    with _lock:
        _ensure()
        rec = _store.get(inv)
        if rec is None:
            logger.warning(f"[INVOICE-REG] پرداخت فاکتور ناشناخته (پذیرفته شد): inv={inv} uid={uid}")
            return True, ""
        if rec.get("uid") != int(uid):
            return False, "owner"
        if any(r.get("status") == PAID for r in _case_records(rec["uid"], rec["tc"])):
            return False, "paid"
        st = _effective(rec, now)
        if not replay and st in (EXPIRED, SUPERSEDED):
            return False, "expired" if st == EXPIRED else "superseded"
        rec["status"] = PAID
        rec["paid_at"] = now
        rec["charge"] = str(charge or "")
        # فاکتورهای دیگر همین پرونده بسته می‌شوند
        for r in _case_records(rec["uid"], rec["tc"]):
            if r is not rec and r.get("status") in _LIVE:
                r["status"] = SUPERSEDED
                r["closed_at"] = now
        _save()
        return True, ""


def close_case(uid: int, tc: str) -> None:
    """پرونده از راه دیگری پرداخت شد (تایید مدیر/پنل/معافیت): فاکتورهای باز بسته شوند."""
    now = time.time()
    released = []
    with _lock:
        _ensure()
        changed = False
        for r in _case_records(uid, tc):
            if r.get("status") in _LIVE:
                r["status"] = SUPERSEDED
                r["closed_at"] = now
                released.append(r.get("payload"))
                changed = True
        if changed:
            _save()
    _release_wallet_holds(uid, released)


# ═════════════════════════════════════════════════════════════════════════
# میان‌افزارهای aiogram
# ═════════════════════════════════════════════════════════════════════════
from aiogram.dispatcher.middlewares.base import BaseMiddleware  # noqa: E402


class RegistryPreCheckoutMiddleware(BaseMiddleware):
    """pre_checkout_query: فاکتور منقضی/جایگزین‌شده/پرداخت‌شده/در حال پرداخت رد می‌شود
    (پیش از کسر پول) و در غیر این صورت فاکتور claim می‌شود (قفل پرداخت هم‌زمان)."""

    async def __call__(self, handler, event, data: dict):
        inv = inv_of(getattr(event, "invoice_payload", ""))
        if not inv:
            return await handler(event, data)
        try:
            ok, why = claim(inv, event.from_user.id)
        except Exception as e:
            logger.error(f"[INVOICE-REG] claim ناموفق (مجاز شد): {e}", exc_info=True)
            return await handler(event, data)
        if ok:
            return await handler(event, data)
        logger.warning(f"[INVOICE-REG] pre_checkout رد شد inv={inv} user={event.from_user.id}: {why}")
        bot = data.get("bot")
        try:
            await bot.answer_pre_checkout_query(event.id, ok=False, error_message=MESSAGES.get(why, MESSAGES["expired"])[:200])
        except Exception:
            try:
                await bot.answer_pre_checkout_query(event.id, ok=False)
            except Exception as e:
                logger.error(f"[INVOICE-REG] رد pre_checkout ناموفق: {e}")
        return None


class RegistryPaymentMiddleware(BaseMiddleware):
    """successful_payment: فاکتور «یک‌بارمصرف» ثبت می‌شود. اگر بله پرداخت را بدون
    pre_checkout کامل کرده باشد و فاکتور منقضی/تکراری باشد، مبلغ به کیف پول برمی‌گردد
    و پرداخت به هیچ پرونده‌ای اعمال نمی‌شود. باید پیش از میان‌افزار کیف پول ثبت شود."""

    async def __call__(self, handler, event, data: dict):
        sp = getattr(event, "successful_payment", None)
        if sp is None or not getattr(event, "from_user", None):
            return await handler(event, data)
        inv = inv_of(getattr(sp, "invoice_payload", ""))
        if not inv:
            return await handler(event, data)
        uid = event.from_user.id
        charge = str(getattr(sp, "telegram_payment_charge_id", "") or "")
        try:
            ok, why = settle(inv, uid, charge)
        except Exception as e:
            logger.error(f"[INVOICE-REG] settle ناموفق (پرداخت ادامه یافت): {e}", exc_info=True)
            return await handler(event, data)
        if ok:
            return await handler(event, data)

        total = int(getattr(sp, "total_amount", 0) or 0)
        logger.error(f"[INVOICE-REG] پرداخت رد شد و به کیف پول برگشت: user={uid} inv={inv} "
                     f"دلیل={why} charge={charge} مبلغ={total:,} ریال")
        bot = data.get("bot")
        balance_line = ""
        try:
            import wallet
            await wallet.credit(uid, total // 10, "refund", f"فاکتور {why} {inv} {charge[:30]}")
            balance_line = f"\n👛 موجودی کیف پول: {wallet.balance(uid):,} تومان"
        except Exception as e:
            logger.error(f"[INVOICE-REG] برگشت به کیف پول ناموفق: {e}", exc_info=True)
        if bot is not None:
            try:
                await bot.send_message(
                    uid, f"⚠️ {MESSAGES.get(why, MESSAGES['expired'])}\n\n"
                         f"مبلغ {total // 10:,} تومان به کیف پول شما برگشت و از فاکتورهای بعدی کسر می‌شود."
                         f"{balance_line}")
            except Exception:
                pass
            try:
                from config import ADMIN_ID
                await bot.send_message(
                    ADMIN_ID, f"⚠️ پرداخت فاکتور نامعتبر ({why}) — کاربر {uid}\ninv={inv}\n"
                              f"{total // 10:,} تومان به کیف پول کاربر برگشت.\ncharge: {charge}")
            except Exception:
                pass
        return None
