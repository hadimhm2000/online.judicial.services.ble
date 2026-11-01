"""
refund_approvals.py — صف «بازگشت وجه با تایید مدیر»
══════════════════════════════════════════════════════════════════════════════

هر مبلغی که قرار است به‌خاطر جریمه/لغو/مازاد/ثبت ناموفق یا ناقص به کیف پول
کاربر برگردد، به‌جای واریز مستقیم اینجا «درخواست» می‌شود:

  1) request_refund_nowait(...)  → درخواست در refund_approvals.json ذخیره می‌شود
     (ماندگار در ری‌استارت) و برای مدیر پیام با دکمهٔ «✅ تایید / ❌ رد» می‌رود.
  2) فقط پس از زدن «تایید» توسط مدیر، wallet.credit مبلغ را واریز می‌کند.
     تایید idempotent است (وضعیت پیش از واریز تغییر می‌کند؛ کلیک دوم اثری ندارد).
  3) «رد» چیزی واریز نمی‌کند و کاربر مطلع می‌شود.

موارد زیر عمداً خودکار می‌مانند و از این صف عبور نمی‌کنند:
  - پرداخت تکراری/نامربوط/فاکتور منقضی که به کیف پول برمی‌گردد (invoice_guard،
    WalletPaymentMiddleware، پرداخت تکراری گواهی)
  - برگشت پرداخت ناموفق «از خودِ کیف پول» (wallet._auto_pay / cb_wallet_pay)

دستورات مدیر:
  /refunds    فهرست درخواست‌های در انتظار تایید (هر کدام با دکمه)
"""
import asyncio
import datetime
import json
import logging
import os
import secrets
import shutil
import time

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import ADMIN_ID

logger = logging.getLogger(__name__)

STORE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "refund_approvals.json")

ST_PENDING = "pending"
ST_APPROVED = "approved"
ST_REJECTED = "rejected"
ST_CANCELLED = "cancelled"   # دیگر لازم نیست (مثلاً ثبت ناموفق بعداً با موفقیت انجام شد)

MAX_KEEP_DECIDED = 500       # سقف رکوردهای تصمیم‌گرفته‌شده در فایل

_store: dict = {"items": {}}
_lock = asyncio.Lock()
_bot: Bot | None = None

refund_router = Router()


# ── ذخیره‌سازی ───────────────────────────────────────────────────────────

def _load():
    global _store
    for path in (STORE_FILE, STORE_FILE + ".bak"):
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            _store = {"items": dict(data.get("items", {}))}
            return
        except Exception as e:
            logger.error(f"[REFUND] خواندن {os.path.basename(path)} ناموفق: {e}")


def _save():
    tmp = STORE_FILE + ".tmp"
    try:
        decided = [k for k, v in _store["items"].items() if v.get("status") != ST_PENDING]
        if len(decided) > MAX_KEEP_DECIDED:
            decided.sort(key=lambda k: _store["items"][k].get("decided_at", 0))
            for k in decided[:len(decided) - MAX_KEEP_DECIDED]:
                _store["items"].pop(k, None)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_store, f, ensure_ascii=False, indent=1)
            f.flush()
            os.fsync(f.fileno())
        if os.path.exists(STORE_FILE):
            shutil.copyfile(STORE_FILE, STORE_FILE + ".bak")
        os.replace(tmp, STORE_FILE)
    except Exception as e:
        logger.error(f"[REFUND] ذخیرهٔ درخواست‌های بازگشت ناموفق: {e}")


def pending() -> list[dict]:
    return sorted((v for v in _store["items"].values() if v.get("status") == ST_PENDING),
                  key=lambda v: v.get("created_at", 0))


def pending_total_toman(uid=None) -> int:
    return sum(int(v.get("toman", 0)) for v in pending()
               if uid is None or str(v.get("uid")) == str(uid))


# ── ثبت درخواست ─────────────────────────────────────────────────────────

def request_refund_nowait(uid, toman: int, note: str, source: str = "",
                          dedupe_key: str = "") -> str | None:
    """ثبت درخواست بازگشت وجه (بدون واریز). هم‌زمان؛ در حلقهٔ asyncio اتمیک است.

    dedupe_key: اگر درخواست در انتظار/تاییدشده‌ای با همین کلید باشد، درخواست
    تازه ساخته نمی‌شود و شناسهٔ قبلی برمی‌گردد. خروجی: شناسه یا None (مبلغ ≤ ۰).
    """
    toman = int(toman)
    if toman <= 0:
        return None
    if dedupe_key:
        for v in _store["items"].values():
            if v.get("dedupe_key") == dedupe_key and v.get("status") in (ST_PENDING, ST_APPROVED):
                return v["id"]
    rid = secrets.token_hex(4)
    _store["items"][rid] = {
        "id": rid, "uid": int(uid), "toman": toman, "note": (note or "")[:200],
        "source": source, "dedupe_key": dedupe_key, "status": ST_PENDING,
        "created_at": time.time(), "notified": False,
    }
    _save()
    logger.info(f"[REFUND] درخواست بازگشت {rid}: کاربر {uid}، {toman:,} تومان، {note} ({source})")
    try:
        asyncio.get_running_loop().create_task(_notify_admin(rid))
    except RuntimeError:
        pass   # بدون حلقه (مثلاً تست) — notify_pending بعداً می‌فرستد
    return rid


def cancel_pending(dedupe_key: str) -> int:
    """لغو درخواست‌های در انتظارِ یک کلید (مثلاً ثبت ناموفق بعداً موفق شد). خروجی: تعداد."""
    n = 0
    for v in _store["items"].values():
        if v.get("dedupe_key") == dedupe_key and v.get("status") == ST_PENDING:
            v["status"] = ST_CANCELLED
            v["decided_at"] = time.time()
            n += 1
    if n:
        _save()
    return n


# ── اطلاع به مدیر ───────────────────────────────────────────────────────

def _kb(rid: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ تایید و واریز", callback_data=f"rfd:ok:{rid}"),
        InlineKeyboardButton(text="❌ رد", callback_data=f"rfd:no:{rid}"),
    ]])


def _admin_text(it: dict) -> str:
    when = datetime.datetime.fromtimestamp(it.get("created_at", 0)).strftime("%Y/%m/%d %H:%M")
    return (f"💰 درخواست بازگشت وجه — نیازمند تایید شما\n\n"
            f"👤 کاربر: {it['uid']}\n"
            f"💵 مبلغ: {int(it['toman']):,} تومان\n"
            f"📝 دلیل: {it.get('note') or '—'}\n"
            f"🔖 منبع: {it.get('source') or '—'}\n"
            f"🕒 {when}\n🆔 {it['id']}")


async def _notify_admin(rid: str, bot: Bot | None = None):
    bot = bot or _bot
    it = _store["items"].get(rid)
    if bot is None or not it or it.get("status") != ST_PENDING or it.get("notified"):
        return
    try:
        await bot.send_message(ADMIN_ID, _admin_text(it), reply_markup=_kb(rid))
        it["notified"] = True
        _save()
    except Exception as e:
        logger.warning(f"[REFUND] اطلاع به مدیر برای {rid} ناموفق (بعداً تکرار می‌شود): {e}")


async def notify_pending(bot: Bot):
    """اطلاع درخواست‌هایی که هنوز به مدیر نرسیده‌اند (از state_persister صدا زده می‌شود)."""
    for it in pending():
        if not it.get("notified"):
            await _notify_admin(it["id"], bot)


# ── تصمیم مدیر ──────────────────────────────────────────────────────────

async def decide(rid: str, approve: bool, by: int = 0) -> tuple[str, dict | None]:
    """هستهٔ تصمیم مدیر. خروجی: (نتیجه، رکورد) با نتیجه یکی از:
    "done" (انجام شد) | "missing" | "closed" (قبلاً بسته شده) | "failed" (واریز ناموفق؛ هنوز pending).
    وضعیت پیش از واریز تغییر می‌کند، پس کلیک/فراخوانی دوباره هرگز دوبار واریز نمی‌کند."""
    import wallet
    async with _lock:
        it = _store["items"].get(rid)
        if not it:
            return "missing", None
        if it["status"] != ST_PENDING:
            return "closed", it
        it["status"] = ST_APPROVED if approve else ST_REJECTED
        it["decided_at"] = time.time()
        it["decided_by"] = by
        _save()
        if approve:
            try:
                await wallet.credit(it["uid"], int(it["toman"]), "refund", it.get("note", "")[:100])
            except Exception as e:
                # واریز نشد → به حالت انتظار برمی‌گردد تا مدیر دوباره بزند
                it["status"] = ST_PENDING
                it.pop("decided_at", None)
                it.pop("decided_by", None)
                _save()
                logger.error(f"[REFUND] واریز {rid} ناموفق: {e}", exc_info=True)
                return "failed", it
    return "done", it


async def _decide(callback: CallbackQuery, approve: bool):
    if not callback.from_user or callback.from_user.id != ADMIN_ID:
        await callback.answer("فقط مدیر می‌تواند تصمیم بگیرد.", show_alert=True)
        return
    rid = callback.data.split(":", 2)[2]
    import wallet
    result, it = await decide(rid, approve, callback.from_user.id)
    if result == "missing":
        await callback.answer("این درخواست پیدا نشد.", show_alert=True)
        return
    if result == "closed":
        await callback.answer(f"این درخواست قبلاً بسته شده ({it['status']}).", show_alert=True)
        _strip(callback)
        return
    if result == "failed":
        await callback.answer("واریز ناموفق بود؛ دوباره تلاش کنید.", show_alert=True)
        return
    await callback.answer("واریز شد." if approve else "رد شد.")
    verdict = "✅ تایید و واریز شد" if approve else "❌ رد شد"
    try:
        await callback.message.edit_text(f"{_admin_text(it)}\n\n{verdict}", reply_markup=None)
    except Exception:
        pass
    bot = callback.bot or _bot
    if bot is None:
        return
    try:
        if approve:
            await bot.send_message(
                it["uid"],
                f"✅ بازگشت وجه شما ({int(it['toman']):,} تومان) توسط مدیریت تایید و به کیف پول "
                f"شما واریز شد.\n👛 موجودی فعلی: {wallet.balance(it['uid']):,} تومان")
        else:
            await bot.send_message(
                it["uid"],
                f"ℹ️ درخواست بازگشت وجه شما ({int(it['toman']):,} تومان) توسط مدیریت تایید نشد. "
                "برای پیگیری با پشتیبانی تماس بگیرید.")
    except Exception as e:
        logger.warning(f"[REFUND] اطلاع به کاربر {it['uid']} ناموفق: {e}")


def _strip(callback: CallbackQuery):
    try:
        asyncio.get_running_loop().create_task(callback.message.edit_reply_markup(reply_markup=None))
    except Exception:
        pass


@refund_router.callback_query(F.data.startswith("rfd:ok:"))
async def cb_refund_ok(callback: CallbackQuery):
    await _decide(callback, True)


@refund_router.callback_query(F.data.startswith("rfd:no:"))
async def cb_refund_no(callback: CallbackQuery):
    await _decide(callback, False)


@refund_router.message(Command("refunds"), F.from_user.id == ADMIN_ID)
async def admin_refunds(message: Message):
    items = pending()
    if not items:
        await message.answer("✅ هیچ درخواست بازگشت وجهی در انتظار تایید نیست.")
        return
    await message.answer(f"💰 {len(items)} درخواست در انتظار تایید "
                         f"(جمع {pending_total_toman():,} تومان):")
    for it in items[:20]:
        await message.answer(_admin_text(it), reply_markup=_kb(it["id"]))
    if len(items) > 20:
        await message.answer(f"… و {len(items) - 20} درخواست دیگر (پس از رسیدگی دوباره /refunds بزنید).")


# ── راه‌اندازی ───────────────────────────────────────────────────────────

def setup_refunds(dp):
    """در bot.py پس از wallet.setup_wallet(dp)، قبل از روتر اصلی."""
    _load()
    dp.include_router(refund_router)


def set_bot(bot: Bot):
    global _bot
    _bot = bot
