"""
wallet.py — کیف پول (اعتبار پیش‌خرید) برای کاربران پرکار
══════════════════════════════════════════════════════════════════════════════

جریان:
  ۱) شارژ: منوی «👛 کیف پول» → انتخاب مبلغ → فاکتور بله با payload
     {"type": "wallet_topup"} → پس از پرداخت موفق، موجودی افزایش می‌یابد.
     (رسید کارت‌به‌کارت همین فاکتور هم از مسیر card_payment بازپخش و شارژ می‌شود.)
  ۲) خرج: هر جا ربات فاکتور می‌فرستد، card_payment.track_invoice صدا زده
     می‌شود؛ اگر موجودی کیف پول کاربر کافی باشد، زیر فاکتور یک پیام با دکمهٔ
     «پرداخت از کیف پول» ارسال می‌شود (on_invoice).
  ۳) با زدن دکمه، مبلغ از کیف پول کسر و دقیقاً همان رویداد successful_payment
     فاکتور اصلی (با شناسهٔ WALLET-…) از Dispatcher بازپخش می‌شود — همان روشی
     که card_payment برای رسیدهای تاییدشده استفاده می‌کند — پس همهٔ هندلرهای
     پرداخت سرویس‌ها بدون تغییر کار می‌کنند. اگر بازپخش خطا بدهد، مبلغ
     خودکار برگردانده می‌شود.
  ۴) ⭐ کسر خودکار (۱۴۰۵/۰۷): همهٔ فاکتورها (استعلام، پیش‌پرداخت، فاکتور نهایی،
     اشتراک، …) پیش از sendInvoice از prepare_invoice عبور می‌کنند:
       - موجودی کمتر از فاکتور → مبلغ فاکتور به اندازهٔ موجودی کم می‌شود (حداقل
         ۱۰,۰۰۰ ریال فاکتور می‌ماند) و همان مقدار برای این فاکتور «رزرو» می‌شود.
         پس از پرداخت، رزرو از کیف پول کسر و total_amount رویداد پرداخت به مبلغ
         اصلی فاکتور برگردانده می‌شود (WalletPaymentMiddleware) تا هندلرهای
         سرویس‌ها همان مبلغ کامل را ببینند. رزرو پرداخت‌نشده پس از ۲۴ ساعت آزاد
         می‌شود.
       - موجودی کافی → on_invoice فاکتور را به‌صورت خودکار از کیف پول پرداخت
         می‌کند (همان بازپخش بند ۳). پرداخت تکراری همان فاکتور از درگاه/کارت به
         کیف پول برمی‌گردد.
  ۵) همهٔ مبالغی که باید به کاربر برگردد (مازاد پیش‌پرداخت، نصف پیش‌پرداخت
     جریمهٔ کدملی، بازگشت خطای فوت، مازاد دسته‌جمعی، مانده‌های قبلی) به همین
     کیف پول واریز می‌شوند (credit / credit_nowait).

دستورات مدیر:
  /wallet <آیدی>                       موجودی و آخرین تراکنش‌ها
  /wallet_add <آیدی> <تومان> [توضیح]   افزایش/کاهش دستی (عدد منفی = کسر)
  /owed                                همهٔ مبالغی که الان به کاربران بدهکاریم

مبالغ کیف پول به «تومان» نگهداری می‌شوند (مثل پنل)؛ فاکتورهای بله به ریال‌اند.
ذخیره: wallet.json (ماندگار در ری‌استارت).
"""
import asyncio
import datetime
import json
import logging
import os
import secrets
import time

import aiohttp
from aiogram import BaseMiddleware, Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import (
    CallbackQuery, Chat, InlineKeyboardButton, InlineKeyboardMarkup, Message,
    SuccessfulPayment, Update, User)

import runtime_state
from config import ADMIN_ID, BALE_API_BASE, BALE_SSL_CONTEXT, BALE_WALLET_TOKEN, BOT_TOKEN
from keyboards import WALLET_MENU_TEXT

logger = logging.getLogger(__name__)

STORE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wallet.json")
TOPUP_TYPE = "wallet_topup"
CHARGE_PREFIX = "WALLET-"
TOPUP_OPTIONS_TOMAN = (100_000, 200_000, 500_000, 1_000_000)
OFFER_TTL_SECONDS = 2 * 3600
MAX_TX_PER_USER = 50
# حداقل مبلغ فاکتور در API بله (۱۰,۰۰۰ ریال) — کسر کیف پول فاکتور را زیر این نمی‌برد
MIN_INVOICE_RIAL = 10_000
HOLD_ACTIVE_SECONDS = 24 * 3600      # رزرو فاکتور پرداخت‌نشده پس از این مدت آزاد می‌شود
HOLD_KEEP_SECONDS = 7 * 24 * 3600    # پرداخت دیرهنگام تا این مدت هنوز با رزرو تطبیق داده می‌شود
AUTOPAID_KEEP_SECONDS = 24 * 3600    # تشخیص پرداخت تکراری فاکتوری که خودکار پرداخت شد
AUTOPAY_FIRST_DELAY = 3.0            # صبر تا هندلر فرستندهٔ فاکتور state انتظار پرداخت را بگذارد
AUTOPAY_STABLE_DELAY = 2.0

# payloadهایی که هندلرشان مستقل از state کاربر مسیریابی می‌شود (مثل card_payment)
_PAYLOAD_ROUTED_TYPES = {"admin_fee", "panel_message", "reg_prepay", "clearance"}

_store: dict = {"users": {}, "offers": {}, "holds": {}, "autopaid": {}}
_lock = asyncio.Lock()
_bot: Bot | None = None

wallet_router = Router()


# ── ذخیره‌سازی ───────────────────────────────────────────────────────────

def _load():
    global _store
    if not os.path.exists(STORE_FILE):
        return
    try:
        with open(STORE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        _store = {"users": data.get("users", {}), "offers": data.get("offers", {}),
                  "holds": data.get("holds", {}), "autopaid": data.get("autopaid", {})}
    except Exception as e:
        logger.error(f"[WALLET] خطا در خواندن کیف پول: {e}")


def _save():
    tmp = STORE_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_store, f, ensure_ascii=False, indent=1)
        os.replace(tmp, STORE_FILE)
    except Exception as e:
        logger.error(f"[WALLET] خطا در ذخیرهٔ کیف پول: {e}")


def _user(uid) -> dict:
    return _store["users"].setdefault(str(uid), {"balance": 0, "tx": []})


def balance(uid) -> int:
    """موجودی کیف پول (تومان)."""
    return int(_store["users"].get(str(uid), {}).get("balance", 0))


def _apply(uid, amount_toman: int, kind: str, note: str = ""):
    """تغییر موجودی + ثبت تراکنش. فراخوان باید _lock را گرفته باشد."""
    u = _user(uid)
    u["balance"] = int(u["balance"]) + int(amount_toman)
    u["tx"].append({
        "at": datetime.datetime.now().isoformat(timespec="seconds"),
        "amount": int(amount_toman),
        "kind": kind,
        "note": note[:120],
        "balance": u["balance"],
    })
    u["tx"] = u["tx"][-MAX_TX_PER_USER:]
    _save()


async def credit(uid, amount_toman: int, kind: str = "refund", note: str = ""):
    """واریز (یا کسر با عدد منفی) به کیف پول کاربر از سایر ماژول‌ها."""
    async with _lock:
        _apply(uid, int(amount_toman), kind, note)


def credit_nowait(uid, amount_toman: int, kind: str = "refund", note: str = ""):
    """نسخهٔ هم‌زمان credit برای توابع sync (بدون await، پس در حلقهٔ asyncio اتمیک است)."""
    if int(amount_toman) == 0:
        return
    _apply(uid, int(amount_toman), kind, note)


def _cleanup_offers():
    now = time.time()
    for oid in [k for k, v in _store["offers"].items() if now - v.get("at", 0) > OFFER_TTL_SECONDS]:
        _store["offers"].pop(oid, None)
    for k in [k for k, v in _store.setdefault("holds", {}).items() if now - v.get("at", 0) > HOLD_KEEP_SECONDS]:
        _store.setdefault("holds", {}).pop(k, None)
    for k in [k for k, v in _store.setdefault("autopaid", {}).items() if now - v.get("at", 0) > AUTOPAID_KEEP_SECONDS]:
        _store.setdefault("autopaid", {}).pop(k, None)


# ── رزرو و کسر خودکار از فاکتورها ────────────────────────────────────────

def _key(uid, payload: str) -> str:
    return f"{int(uid)}|{payload}"


def _ptype_of(payload: str) -> str:
    try:
        return str(json.loads(payload).get("type", "") or "")
    except Exception:
        return ""


def _amount_of(invoice_data: dict) -> int:
    return int(sum(int(p.get("amount", 0)) for p in invoice_data.get("prices") or []))


def reserved(uid) -> int:
    """مبلغ (تومان) رزروشده برای فاکتورهای پرداخت‌نشدهٔ کاربر."""
    now = time.time()
    return sum(int(h.get("wallet_toman", 0)) for h in _store.setdefault("holds", {}).values()
               if h.get("uid") == int(uid) and now - h.get("at", 0) <= HOLD_ACTIVE_SECONDS)


def available(uid) -> int:
    """موجودی قابل خرج (تومان) = موجودی − رزرو فاکتورهای باز."""
    return max(0, balance(uid) - reserved(uid))


def _note_card_deduction(uid: int, ptype: str, total_rial: int, used_rial: int):
    """کسر کیف پول در رسید کارت‌به‌کارت مدیر (کنار کسر پیش‌پرداخت/مانده، اگر بود)."""
    try:
        import card_payment
        prev = card_payment._pending_deductions.get(uid)
        if prev and ptype in prev.get("types", []) and card_payment._now() - prev.get("at", 0) < 60:
            prev["deducted_rial"] = int(prev["deducted_rial"]) + used_rial
            prev["detail"] = f"{prev.get('detail', '')} + کیف پول"
            return
        card_payment.note_invoice_deduction(uid, (ptype,), total_rial, used_rial, "کیف پول")
    except Exception:
        pass


def prepare_invoice(invoice_data: dict) -> dict:
    """⭐ پیش از هر sendInvoice صدا زده می‌شود و invoice_data (احتمالاً کاهش‌یافته) را برمی‌گرداند.

    - موجودی قابل خرج < مبلغ فاکتور → مبلغ فاکتور به اندازهٔ موجودی کم می‌شود
      (حداقل MIN_INVOICE_RIAL می‌ماند) و همان مقدار برای این فاکتور رزرو می‌شود.
    - موجودی کافی → فاکتور دست‌نخورده؛ on_invoice آن را خودکار پرداخت می‌کند.
    هرگز استثنا نمی‌دهد؛ در خطا همان فاکتور اصلی برمی‌گردد.
    """
    # ⭐ تخفیف اختصاصی کاربر روی فاکتورهای استعلام — پیش از کسر کیف پول
    try:
        import user_discounts
        invoice_data = user_discounts.apply_to_invoice(invoice_data)
    except Exception as e:
        logger.error(f"[WALLET] اعمال تخفیف اختصاصی ناموفق: {e}")
    try:
        payload = str(invoice_data.get("payload") or "")
        ptype = _ptype_of(payload)
        if ptype == TOPUP_TYPE:
            return invoice_data
        uid = int(invoice_data.get("chat_id"))
        key = _key(uid, payload)
        # فاکتور جدید با همان payload → رزرو/پرداخت خودکار قبلی دیگر به این فاکتور مربوط نیست
        prev_hold = _store.setdefault("holds", {}).pop(key, None)
        changed = prev_hold is not None
        changed = (_store.setdefault("autopaid", {}).pop(key, None) is not None) or changed
        amount_rial = _amount_of(invoice_data)
        avail_rial = available(uid) * 10
        use_rial = min(avail_rial, amount_rial - MIN_INVOICE_RIAL)
        if amount_rial <= 0 or avail_rial >= amount_rial or use_rial <= 0:
            if changed:
                _save()
            return invoice_data
        new_rial = amount_rial - use_rial
        new_data = dict(invoice_data)
        prices = invoice_data.get("prices") or []
        label = str((prices[0] if prices else {}).get("label") or invoice_data.get("title") or "فاکتور")
        new_data["prices"] = [{"label": label, "amount": new_rial}]
        line = (f"\n👛 کسر از کیف پول: {use_rial // 10:,} تومان — "
                f"قابل پرداخت: {new_rial // 10:,} تومان")
        desc = str(invoice_data.get("description") or "")
        if len(desc) + len(line) <= 255:
            new_data["description"] = desc + line
        _store.setdefault("holds", {})[key] = {
            "uid": uid, "payload": payload, "ptype": ptype,
            "title": str(invoice_data.get("title") or ""),
            "orig_rial": amount_rial, "invoice_rial": new_rial,
            "wallet_toman": use_rial // 10, "at": time.time(),
            # یادآوری همان فاکتور با همان کسر → اطلاع دوباره به کاربر لازم نیست
            "notified": bool(prev_hold and prev_hold.get("notified")
                             and prev_hold.get("orig_rial") == amount_rial
                             and prev_hold.get("invoice_rial") == new_rial),
        }
        _save()
        _note_card_deduction(uid, ptype, amount_rial, use_rial)
        logger.info(f"[WALLET] فاکتور {ptype or '-'} کاربر {uid}: {use_rial:,} ریال از کیف پول "
                    f"رزرو شد؛ {amount_rial:,} → {new_rial:,} ریال")
        return new_data
    except Exception as e:
        logger.error(f"[WALLET] prepare_invoice ناموفق: {e}", exc_info=True)
        return invoice_data


# ── پیشنهاد پرداخت از کیف پول زیر هر فاکتور ───────────────────────────────

def on_invoice(invoice_data: dict):
    """از card_payment.track_invoice (پس از sendInvoice موفق) صدا زده می‌شود. هرگز استثنا نمی‌دهد.

    - اگر prepare_invoice برای این فاکتور مبلغی رزرو کرده → اطلاع به کاربر.
    - اگر موجودی قابل خرج کل فاکتور را بپوشاند → پرداخت خودکار از کیف پول.
    """
    try:
        payload = str(invoice_data.get("payload") or "")
        ptype = _ptype_of(payload)
        if ptype == TOPUP_TYPE or _bot is None:
            return
        uid = int(invoice_data.get("chat_id"))
        amount_rial = _amount_of(invoice_data)
        title = str(invoice_data.get("title") or "")
        hold = _store.setdefault("holds", {}).get(_key(uid, payload))
        if hold and not hold.get("notified") and int(hold.get("invoice_rial", 0)) == amount_rial:
            hold["notified"] = True
            asyncio.get_running_loop().create_task(_send_hold_notice(uid, hold))
            return
        if amount_rial <= 0 or available(uid) * 10 < amount_rial:
            return
        asyncio.get_running_loop().create_task(_auto_pay(uid, payload, ptype, amount_rial, title))
    except Exception as e:
        logger.error(f"[WALLET] on_invoice ناموفق: {e}", exc_info=True)


async def _send_hold_notice(uid: int, hold: dict):
    await asyncio.sleep(1)
    try:
        await _bot.send_message(
            uid,
            f"👛 {hold['wallet_toman']:,} تومان از موجودی کیف پول شما به‌صورت خودکار از فاکتور "
            f"«{hold.get('title', '')}» کسر شد.\n"
            f"💰 مبلغ اصلی: {hold['orig_rial'] // 10:,} تومان — "
            f"قابل پرداخت: {hold['invoice_rial'] // 10:,} تومان")
    except Exception as e:
        logger.warning(f"[WALLET] اطلاع کسر کیف پول به {uid} ناموفق: {e}")


async def _wait_stable_state(uid: int) -> str | None:
    """صبر تا state کاربر پس از ارسال فاکتور ثابت شود (هندلر فرستنده state انتظار پرداخت را می‌گذارد)."""
    await asyncio.sleep(AUTOPAY_FIRST_DELAY)
    prev = await _current_state(uid)
    for _ in range(5):
        await asyncio.sleep(AUTOPAY_STABLE_DELAY)
        cur = await _current_state(uid)
        if cur == prev:
            return cur
        prev = cur
    return prev


async def _auto_pay(uid: int, payload: str, ptype: str, amount_rial: int, title: str):
    """پرداخت خودکار کل فاکتور از کیف پول (بازپخش successful_payment)."""
    try:
        st = await _wait_stable_state(uid)
        if st is None and ptype not in _PAYLOAD_ROUTED_TYPES:
            # مسیر پرداخت به state وابسته است و state در دسترس نیست → دکمهٔ دستی
            await _send_offer(uid, payload, ptype, amount_rial, title)
            return
        amount_toman = amount_rial // 10
        key = _key(uid, payload)
        async with _lock:
            if available(uid) < amount_toman or key in _store.setdefault("autopaid", {}):
                return
            oid = secrets.token_hex(4)
            _store["offers"][oid] = {
                "uid": uid, "payload": payload, "ptype": ptype, "amount_rial": amount_rial,
                "title": title, "at": time.time(), "state": st, "used": True, "auto": True,
            }
            _store.setdefault("autopaid", {})[key] = {"at": time.time(), "amount_rial": amount_rial, "oid": oid}
            _apply(uid, -amount_toman, "pay", title)
        ok, err = await _replay_payment(_bot, uid, User(id=uid, is_bot=False, first_name="کاربر"),
                                        payload, amount_rial, oid)
        if ok:
            await _bot.send_message(
                uid,
                f"✅ فاکتور «{title}» ({amount_toman:,} تومان) به‌صورت خودکار از کیف پول پرداخت شد؛ "
                f"نیازی به پرداخت فاکتور نیست.\n👛 موجودی فعلی: {balance(uid):,} تومان")
            return
        async with _lock:
            _store.setdefault("autopaid", {}).pop(key, None)
            _apply(uid, amount_toman, "refund", f"بازگشت پرداخت خودکار ناموفق {oid}")
        await _bot.send_message(uid, "⚠️ پرداخت خودکار از کیف پول انجام نشد و مبلغ به کیف پول برگشت. "
                                     "لطفاً فاکتور را از درگاه پرداخت کنید.")
        await _bot.send_message(ADMIN_ID, f"⚠️ پرداخت خودکار کیف پول کاربر {uid} ناموفق ماند و برگشت داده شد: {err}")
    except Exception as e:
        logger.error(f"[WALLET] پرداخت خودکار کاربر {uid} ناموفق: {e}", exc_info=True)


async def _current_state(uid: int) -> str | None:
    dp = getattr(runtime_state, "dp", None)
    if dp is None or _bot is None:
        return None
    key = StorageKey(bot_id=_bot.id, chat_id=uid, user_id=uid)
    return await dp.storage.get_state(key)


async def _send_offer(uid: int, payload: str, ptype: str, amount_rial: int, title: str):
    # کمی صبر تا هندلرِ ارسال‌کنندهٔ فاکتور state انتظار پرداخت را تنظیم کند
    await asyncio.sleep(1.5)
    async with _lock:
        _cleanup_offers()
        oid = secrets.token_hex(4)
        _store["offers"][oid] = {
            "uid": uid, "payload": payload, "ptype": ptype, "amount_rial": amount_rial,
            "title": title, "at": time.time(), "state": await _current_state(uid), "used": False,
        }
        _save()
    amount_toman = amount_rial // 10
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"👛 پرداخت {amount_toman:,} تومان از کیف پول",
                             callback_data=f"wal:pay:{oid}")]])
    try:
        await _bot.send_message(
            uid,
            f"👛 موجودی کیف پول شما *{balance(uid):,} تومان* است.\n"
            f"می‌توانید فاکتور «{title}» را به‌جای درگاه، از کیف پول پرداخت کنید:",
            reply_markup=kb)
    except Exception as e:
        logger.warning(f"[WALLET] ارسال پیشنهاد کیف پول به {uid} ناموفق: {e}")


async def _replay_payment(bot: Bot, uid: int, user: User, payload: str, amount_rial: int, oid: str) -> tuple[bool, str]:
    dp = getattr(runtime_state, "dp", None)
    if dp is None:
        return False, "Dispatcher در دسترس نیست"
    try:
        msg = Message(
            message_id=1,
            date=datetime.datetime.now(datetime.timezone.utc),
            chat=Chat(id=uid, type="private"),
            from_user=User(id=uid, is_bot=False, first_name=user.first_name or "کاربر",
                           last_name=user.last_name, username=user.username),
            successful_payment=SuccessfulPayment(
                currency="IRR",
                total_amount=amount_rial,
                invoice_payload=payload,
                telegram_payment_charge_id=f"{CHARGE_PREFIX}{oid}",
                provider_payment_charge_id=f"{CHARGE_PREFIX}{oid}",
            ),
        )
        await dp.feed_update(bot, Update(update_id=int(time.time() * 1000) % 2_000_000_000, message=msg))
        return True, ""
    except Exception as e:
        logger.error(f"[WALLET] بازپخش پرداخت {oid} ناموفق: {e}", exc_info=True)
        return False, repr(e)[:200]


@wallet_router.callback_query(F.data.startswith("wal:pay:"))
async def cb_wallet_pay(callback: CallbackQuery, bot: Bot):
    oid = callback.data.split(":", 2)[2]
    uid = callback.from_user.id
    async with _lock:
        offer = _store["offers"].get(oid)
        if not offer or offer.get("uid") != uid or offer.get("used"):
            await callback.answer("این فاکتور دیگر قابل پرداخت از کیف پول نیست.", show_alert=True)
            return
        if time.time() - offer.get("at", 0) > OFFER_TTL_SECONDS:
            await callback.answer("مهلت این فاکتور تمام شده است.", show_alert=True)
            return
        if offer["ptype"] not in _PAYLOAD_ROUTED_TYPES and await _current_state(uid) != offer.get("state"):
            await callback.answer(
                "مرحلهٔ درخواست شما تغییر کرده و این فاکتور دیگر معتبر نیست.", show_alert=True)
            return
        amount_toman = offer["amount_rial"] // 10
        if available(uid) < amount_toman:
            await callback.answer("موجودی کیف پول کافی نیست.", show_alert=True)
            return
        offer["used"] = True
        _store.setdefault("autopaid", {})[_key(uid, offer["payload"])] = {
            "at": time.time(), "amount_rial": offer["amount_rial"], "oid": oid}
        _apply(uid, -amount_toman, "pay", offer.get("title", ""))
    await callback.answer("در حال پرداخت…")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    ok, err = await _replay_payment(bot, uid, callback.from_user, offer["payload"], offer["amount_rial"], oid)
    if ok:
        await callback.message.answer(
            f"✅ مبلغ {amount_toman:,} تومان از کیف پول پرداخت شد.\n"
            f"👛 موجودی فعلی: {balance(uid):,} تومان")
        return
    async with _lock:
        _store.setdefault("autopaid", {}).pop(_key(uid, offer["payload"]), None)
        _apply(uid, amount_toman, "refund", f"بازگشت پرداخت ناموفق {oid}")
    await callback.message.answer("⚠️ پرداخت از کیف پول انجام نشد و مبلغ به کیف پول برگشت. لطفاً از درگاه پرداخت کنید.")
    try:
        await bot.send_message(ADMIN_ID, f"⚠️ پرداخت کیف پول کاربر {uid} ناموفق ماند و برگشت داده شد: {err}")
    except Exception:
        pass


# ── منوی کیف پول و شارژ ──────────────────────────────────────────────────

def _menu_kb() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"➕ شارژ {a:,} تومان", callback_data=f"wal:top:{a}")]
            for a in TOPUP_OPTIONS_TOMAN]
    rows.append([InlineKeyboardButton(text="📜 تراکنش‌های اخیر", callback_data="wal:tx")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _pending_prepay_rial(uid) -> int:
    """پیش‌پرداخت/ماندهٔ پروندهٔ در جریان (prepaid_registrations) — در فاکتور نهایی کسر می‌شود."""
    rec = getattr(runtime_state, "prepaid_registrations", {}).get(int(uid))
    return max(0, int((rec or {}).get("amount_rial", 0) or 0))


@wallet_router.message(StateFilter("*"), F.text == WALLET_MENU_TEXT)
async def wallet_menu(message: Message, state: FSMContext):
    uid = message.from_user.id
    extra = ""
    if reserved(uid) > 0:
        extra += f"🔒 رزرو برای فاکتور پرداخت‌نشده: {reserved(uid):,} تومان\n"
    if _pending_prepay_rial(uid) > 0:
        extra += (f"💼 پیش‌پرداخت پروندهٔ در جریان: {_pending_prepay_rial(uid) // 10:,} تومان "
                  "(در فاکتور نهایی همان پرونده کسر می‌شود)\n")
    await message.answer(
        f"👛 *کیف پول*\n\nموجودی شما: *{balance(uid):,} تومان*\n{extra}\n"
        "هر مبلغی که به شما برگردد (مازاد پیش‌پرداخت، بازگشت وجه و ...) به همین کیف پول "
        "واریز می‌شود. موجودی کیف پول به‌صورت خودکار از فاکتورهای بعدی شما (استعلام، "
        "پیش‌پرداخت، هزینهٔ نهایی و ...) کسر می‌گردد.",
        reply_markup=_menu_kb())


@wallet_router.callback_query(F.data == "wal:tx")
async def cb_wallet_tx(callback: CallbackQuery):
    await callback.answer()
    tx = list(reversed(_store["users"].get(str(callback.from_user.id), {}).get("tx", [])))[:10]
    if not tx:
        await callback.message.answer("📭 تراکنشی ثبت نشده است.")
        return
    labels = {"topup": "شارژ", "pay": "پرداخت", "refund": "بازگشت", "admin": "اصلاح مدیر"}
    lines = [f"{'➕' if t['amount'] > 0 else '➖'} {abs(t['amount']):,} تومان — "
             f"{labels.get(t['kind'], t['kind'])}"
             + (f" ({t['note'][:60]})" if t.get("note") and t["kind"] != "topup" else "")
             + f" — {t['at'][:10]}" for t in tx]
    await callback.message.answer("📜 *تراکنش‌های اخیر*\n\n" + "\n".join(lines))


@wallet_router.callback_query(F.data.startswith("wal:top:"))
async def cb_wallet_topup(callback: CallbackQuery):
    try:
        amount_toman = int(callback.data.rsplit(":", 1)[1])
    except ValueError:
        await callback.answer()
        return
    if amount_toman not in TOPUP_OPTIONS_TOMAN:
        await callback.answer()
        return
    await callback.answer()
    uid = callback.from_user.id
    amount_rial = amount_toman * 10
    invoice_data = {
        "chat_id": uid,
        "title": "شارژ کیف پول",
        "description": f"شارژ کیف پول ربات به مبلغ {amount_toman:,} تومان",
        "payload": json.dumps({"type": TOPUP_TYPE, "amt": amount_toman, "uid": uid}),
        "provider_token": BALE_WALLET_TOKEN,
        "currency": "IRR",
        "prices": [{"label": "شارژ کیف پول", "amount": amount_rial}],
    }
    try:
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=BALE_SSL_CONTEXT)) as session:
            async with session.post(f"{BALE_API_BASE}/bot{BOT_TOKEN}/sendInvoice", json=invoice_data) as resp:
                result = await resp.json()
        if not result.get("ok"):
            raise Exception(result.get("description", "sendInvoice failed"))
        from card_payment import track_invoice as _cp_track; _cp_track(invoice_data)  # کارت‌به‌کارت پس از ۲۰ دقیقه
    except Exception as e:
        logger.error(f"[WALLET] ارسال فاکتور شارژ ناموفق: {e}")
        await callback.message.answer("⚠️ ساخت فاکتور شارژ ممکن نشد. لطفاً کمی بعد دوباره تلاش کنید.")


def _is_topup_payment(message: Message) -> bool:
    sp = message.successful_payment
    if sp is None:
        return False
    try:
        return json.loads(sp.invoice_payload or "{}").get("type") == TOPUP_TYPE
    except Exception:
        return False


@wallet_router.message(F.successful_payment, _is_topup_payment)
async def wallet_topup_paid(message: Message):
    sp = message.successful_payment
    uid = message.from_user.id
    amount_toman = int(sp.total_amount) // 10
    charge = sp.telegram_payment_charge_id or ""
    async with _lock:
        u = _user(uid)
        if charge and any(t.get("note") == charge for t in u["tx"]):
            logger.warning(f"[WALLET] پرداخت شارژ تکراری نادیده گرفته شد: {charge}")
            return
        _apply(uid, amount_toman, "topup", charge)
    await message.answer(
        f"✅ کیف پول شما {amount_toman:,} تومان شارژ شد.\n"
        f"👛 موجودی فعلی: *{balance(uid):,} تومان*")
    try:
        await message.bot.send_message(
            ADMIN_ID, f"👛 شارژ کیف پول: کاربر {uid} — {amount_toman:,} تومان (موجودی: {balance(uid):,})")
    except Exception:
        pass


# ── دستورات مدیر ─────────────────────────────────────────────────────────

def _is_admin(message: Message) -> bool:
    return bool(message.from_user and message.from_user.id == ADMIN_ID)


@wallet_router.message(Command("wallet"), _is_admin)
async def admin_wallet(message: Message):
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        total = sum(int(u.get("balance", 0)) for u in _store["users"].values())
        await message.answer(
            f"👛 مجموع موجودی کیف پول کاربران: {total:,} تومان "
            f"({len(_store['users'])} کاربر)\n\nفرمت: /wallet <آیدی>  |  /wallet_add <آیدی> <تومان> [توضیح]")
        return
    uid = parts[1]
    tx = list(reversed(_store["users"].get(uid, {}).get("tx", [])))[:10]
    lines = [f"{t['at'][:16]}  {t['amount']:+,}  {t['kind']}  {t.get('note', '')}" for t in tx]
    await message.answer(f"👛 کاربر {uid}\nموجودی: {balance(uid):,} تومان\n\n" + ("\n".join(lines) or "بدون تراکنش"))


@wallet_router.message(Command("wallet_add"), _is_admin)
async def admin_wallet_add(message: Message, bot: Bot):
    parts = (message.text or "").split(maxsplit=3)
    try:
        uid = int(parts[1])
        amount = int(parts[2].replace(",", ""))
    except (IndexError, ValueError):
        await message.answer("فرمت: /wallet_add <آیدی> <تومان> [توضیح]   (عدد منفی = کسر)")
        return
    note = parts[3] if len(parts) > 3 else "اصلاح مدیر"
    async with _lock:
        if balance(uid) + amount < 0:
            await message.answer(f"⚠️ موجودی کاربر {balance(uid):,} تومان است؛ کسر بیشتر ممکن نیست.")
            return
        _apply(uid, amount, "admin", note)
    await message.answer(f"✅ انجام شد. موجودی جدید کاربر {uid}: {balance(uid):,} تومان")
    try:
        await bot.send_message(uid, f"👛 کیف پول شما {amount:+,} تومان تغییر کرد ({note}).\nموجودی: {balance(uid):,} تومان")
    except Exception:
        pass


@wallet_router.message(Command("owed"), _is_admin)
async def admin_owed(message: Message):
    """همهٔ مبالغی که الان به کاربران بدهکاریم (موجودی کیف پول + پیش‌پرداخت‌های در جریان)."""
    _cleanup_offers()
    bal = sorted(((uid, int(u.get("balance", 0))) for uid, u in _store["users"].items()
                  if int(u.get("balance", 0)) > 0), key=lambda x: -x[1])
    total_bal = sum(b for _, b in bal)
    lines = [f"💰 *مبالغ قابل بازگشت به کاربران*\n",
             f"👛 موجودی کیف پول: *{total_bal:,} تومان* ({len(bal)} کاربر)"]
    for uid, b in bal[:40]:
        r = reserved(uid)
        last = next((t for t in reversed(_store["users"][uid].get("tx", [])) if t.get("amount", 0) > 0), None)
        why = f" — آخرین واریز: {last.get('note') or last.get('kind')}"[:70] if last else ""
        lines.append(f"• `{uid}`: {b:,} تومان" + (f" (رزرو {r:,})" if r else "") + why)
    if len(bal) > 40:
        lines.append(f"… و {len(bal) - 40} کاربر دیگر")

    prepaid = getattr(runtime_state, "prepaid_registrations", {}) or {}
    pp = [(uid, int((rec or {}).get("amount_rial", 0) or 0), rec) for uid, rec in prepaid.items()]
    pp = [x for x in pp if x[1] > 0]
    if pp:
        lines.append(f"\n💼 پیش‌پرداخت پرونده‌های در جریان (در فاکتور نهایی کسر می‌شود): "
                     f"*{sum(x[1] for x in pp) // 10:,} تومان* ({len(pp)} کاربر)")
        for uid, amt, rec in pp[:20]:
            lines.append(f"• `{uid}`: {amt // 10:,} تومان — {rec.get('service_label') or rec.get('service', '')}")
    try:
        from bulk_submissions import BULK_TASKS
        bulk = [(tc, td.get("user_id"), int(td.get("surplus_rial", 0) or 0))
                for tc, td in BULK_TASKS.items() if int(td.get("surplus_rial", 0) or 0) > 0]
    except Exception:
        bulk = []
    if bulk:
        lines.append("\n📦 مازاد بچ‌های دسته‌جمعی (منتظر ردیف‌های اصلاحی):")
        for tc, uid, sr in bulk[:20]:
            lines.append(f"• `{uid}` بچ {tc}: {sr // 10:,} تومان")
    lines.append("\nجزئیات یک کاربر: `/wallet <آیدی>` | اصلاح: `/wallet_add <آیدی> <تومان> [توضیح]`")
    text = "\n".join(lines)
    try:
        await message.answer(text, parse_mode="Markdown")
    except Exception:
        await message.answer(text.replace("*", "").replace("`", ""))


# ── میان‌افزار پرداخت: اعمال رزرو کیف پول / برگشت پرداخت تکراری ───────────

async def _on_successful_payment(event: Message, bot: Bot | None) -> tuple[Message, bool]:
    """(رویداد برای هندلرها، توقف؟) — رزرو تطبیق‌یافته کسر و total_amount به مبلغ اصلی برمی‌گردد."""
    sp = event.successful_payment
    payload = str(sp.invoice_payload or "")
    charge = str(sp.telegram_payment_charge_id or "")
    if _ptype_of(payload) == TOPUP_TYPE or charge.startswith(CHARGE_PREFIX) or not event.from_user:
        return event, False
    uid = event.from_user.id
    key = _key(uid, payload)
    total = int(sp.total_amount or 0)
    hold = _store.setdefault("holds", {}).get(key)
    if hold and int(hold.get("invoice_rial", -1)) == total and time.time() - hold.get("at", 0) <= HOLD_KEEP_SECONDS:
        async with _lock:
            hold = _store.setdefault("holds", {}).pop(key, None) or hold
            take = max(0, min(int(hold.get("wallet_toman", 0)), balance(uid)))
            if take > 0:
                _apply(uid, -take, "pay", f"{hold.get('title', '')} (کسر خودکار از فاکتور)")
            else:
                _save()
        logger.info(f"[WALLET] رزرو فاکتور کاربر {uid} اعمال شد: {take:,} تومان از کیف پول؛ "
                    f"مبلغ پرداخت {total:,} → {total + take * 10:,} ریال")
        if take <= 0:
            return event, False
        new_sp = sp.model_copy(update={"total_amount": total + take * 10})
        new_event = event.model_copy(update={"successful_payment": new_sp})
        if bot is not None:
            try:
                new_event = new_event.as_(bot)
            except Exception:
                pass
        return new_event, False
    auto = _store.setdefault("autopaid", {}).get(key)
    if auto and time.time() - auto.get("at", 0) <= AUTOPAID_KEEP_SECONDS and total > 0:
        # این فاکتور قبلاً خودکار از کیف پول پرداخت شده بود → پرداخت دوم به کیف پول برمی‌گردد
        async with _lock:
            _store.setdefault("autopaid", {}).pop(key, None)
            _apply(uid, total // 10, "refund", f"پرداخت تکراری فاکتور {charge[:30]}")
        logger.warning(f"[WALLET] پرداخت تکراری فاکتور خودکار‌پرداخت‌شده کاربر {uid} به کیف پول برگشت ({total:,} ریال)")
        if bot is not None:
            try:
                await bot.send_message(uid, f"ℹ️ این فاکتور قبلاً از کیف پول پرداخت شده بود؛ مبلغ "
                                            f"{total // 10:,} تومان به کیف پول شما برگشت.\n"
                                            f"👛 موجودی: {balance(uid):,} تومان")
                await bot.send_message(ADMIN_ID, f"👛 پرداخت تکراری کاربر {uid} ({total // 10:,} تومان) "
                                                 f"برای فاکتوری که خودکار از کیف پول پرداخت شده بود، به کیف پول او برگشت.")
            except Exception:
                pass
        return event, True
    return event, False


class WalletPaymentMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data: dict):
        if getattr(event, "successful_payment", None) is not None:
            try:
                event, stop = await _on_successful_payment(event, data.get("bot"))
                if stop:
                    return None
            except Exception as e:
                logger.error(f"[WALLET] میان‌افزار پرداخت ناموفق: {e}", exc_info=True)
        return await handler(event, data)


# ── انتقال مبالغ قدیمی به کیف پول ────────────────────────────────────────

def migrate_legacy_credits() -> int:
    """یک‌بار در شروع ربات (پس از load_into_runtime_state): مانده/بستانکاری‌های
    قدیمیِ prepaid_registrations و مازاد بچ‌های دسته‌جمعیِ تمام‌شده به کیف پول
    منتقل می‌شوند. خروجی: تعداد موارد منتقل‌شده (۰ = چیزی نبود؛ تکرار بی‌اثر است)."""
    moved = 0
    try:
        from prepay_registration import _split_record
        prepaid = getattr(runtime_state, "prepaid_registrations", {})
        for uid, rec in list(prepaid.items()):
            paid, credit_rial = _split_record(rec)
            if credit_rial < 10:
                continue
            _apply(uid, credit_rial // 10, "refund", "انتقال مانده/بستانکاری قبلی به کیف پول")
            if paid > 0:
                rec.update({"amount_rial": paid, "amount_toman": paid // 10, "prepay_paid_rial": paid})
                rec.pop("manual", None)
            else:
                prepaid.pop(uid, None)
            moved += 1
    except Exception as e:
        logger.error(f"[WALLET] انتقال مانده‌های قبلی ناموفق: {e}", exc_info=True)
    try:
        from bulk_submissions import BULK_TASKS
        for tc, td in BULK_TASKS.items():
            sr = int(td.get("surplus_rial", 0) or 0)
            if td.get("finalized") and sr >= 10 and td.get("user_id"):
                _apply(td["user_id"], sr // 10, "refund", f"مازاد پیش‌پرداخت دسته‌جمعی {tc}")
                td["surplus_rial"] = 0
                moved += 1
    except Exception as e:
        logger.error(f"[WALLET] انتقال مازاد دسته‌جمعی ناموفق: {e}", exc_info=True)
    if moved:
        logger.info(f"[WALLET] {moved} مبلغ قدیمی به کیف پول کاربران منتقل شد")
    return moved


# ── راه‌اندازی ───────────────────────────────────────────────────────────

def setup_wallet(dp, bot: Bot | None = None):
    """در bot.py: قبل از dp.include_router(router) صدا زده شود."""
    _load()
    dp.include_router(wallet_router)
    dp.message.outer_middleware(WalletPaymentMiddleware())


def set_bot(bot: Bot):
    global _bot
    _bot = bot
