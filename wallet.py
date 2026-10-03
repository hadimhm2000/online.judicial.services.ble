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

دستورات مدیر:
  /wallet <آیدی>                       موجودی و آخرین تراکنش‌ها
  /wallet_add <آیدی> <تومان> [توضیح]   افزایش/کاهش دستی (عدد منفی = کسر)

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
from aiogram import Bot, F, Router
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

# payloadهایی که هندلرشان مستقل از state کاربر مسیریابی می‌شود (مثل card_payment)
_PAYLOAD_ROUTED_TYPES = {"admin_fee", "panel_message", "reg_prepay"}

_store: dict = {"users": {}, "offers": {}}
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
        _store = {"users": data.get("users", {}), "offers": data.get("offers", {})}
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


def credit(uid, amount_toman: int, kind: str, note: str = "") -> int:
    """افزودن مبلغ به کیف پول کاربر (مثلاً بازگشت وجه). همگام و بدون await،
    پس در حلقهٔ asyncio اتمیک است. خروجی: موجودی جدید (تومان)."""
    if int(amount_toman) <= 0:
        return balance(uid)
    _apply(uid, int(amount_toman), kind, note)
    return balance(uid)


def _cleanup_offers():
    now = time.time()
    for oid in [k for k, v in _store["offers"].items() if now - v.get("at", 0) > OFFER_TTL_SECONDS]:
        _store["offers"].pop(oid, None)


# ── پیشنهاد پرداخت از کیف پول زیر هر فاکتور ───────────────────────────────

def on_invoice(invoice_data: dict):
    """از card_payment.track_invoice صدا زده می‌شود (هم‌زمان). هرگز استثنا نمی‌دهد."""
    try:
        payload = str(invoice_data.get("payload") or "")
        try:
            ptype = json.loads(payload).get("type", "")
        except Exception:
            ptype = ""
        if ptype == TOPUP_TYPE or _bot is None:
            return
        uid = int(invoice_data.get("chat_id"))
        amount_rial = int(sum(int(p.get("amount", 0)) for p in invoice_data.get("prices") or []))
        if amount_rial <= 0 or balance(uid) * 10 < amount_rial:
            return
        asyncio.get_running_loop().create_task(_send_offer(uid, payload, ptype, amount_rial,
                                                           str(invoice_data.get("title") or "")))
    except Exception as e:
        logger.error(f"[WALLET] on_invoice ناموفق: {e}", exc_info=True)


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
        if balance(uid) < amount_toman:
            await callback.answer("موجودی کیف پول کافی نیست.", show_alert=True)
            return
        offer["used"] = True
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


@wallet_router.message(StateFilter("*"), F.text == WALLET_MENU_TEXT)
async def wallet_menu(message: Message, state: FSMContext):
    await message.answer(
        f"👛 *کیف پول*\n\nموجودی شما: *{balance(message.from_user.id):,} تومان*\n\n"
        "با شارژ کیف پول، فاکتورهای ربات (پیش‌پرداخت، هزینهٔ ثبت، استعلام و ...) "
        "با یک دکمه و بدون رفتن به درگاه پرداخت می‌شوند.",
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
             f"{labels.get(t['kind'], t['kind'])} — {t['at'][:10]}" for t in tx]
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


# ── راه‌اندازی ───────────────────────────────────────────────────────────

def setup_wallet(dp, bot: Bot | None = None):
    """در bot.py: قبل از dp.include_router(router) صدا زده شود."""
    _load()
    dp.include_router(wallet_router)


def set_bot(bot: Bot):
    global _bot
    _bot = bot
