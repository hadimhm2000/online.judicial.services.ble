"""
stale_requests.py — پاک‌سازی درخواست‌های بی‌پیشرفت پس از ۲۴ ساعت
══════════════════════════════════════════════════════════════════════════════

دستور کارفرما (۱۴۰۵/۰۷):
  ۱) موارد «گیرکرده» گزارش روزانه پس از ۲۴ ساعت از حافظه پاک شوند.
  ۲) درخواست‌هایی که منتظر اقدام کاربرند (پرداخت فاکتور، امضا، اصلاح و ...)
     اگر ۲۴ ساعت اقدامی نشد حذف شوند؛ اگر کاربر مبلغی پرداخت کرده بود به او
     گفته شود برای ادامه به پشتیبانی مراجعه کند.

روش کار (هر ساعت، در stale_requests_loop):
  - پنل (POST /api/admin/cases/expire-stale) پرونده‌های باز
    (PENDING_PAYMENT / INCOMPLETE / PROCESSING) را که ۲۴ ساعت هیچ به‌روزرسانی
    نداشته‌اند «لغو شده» می‌کند. کاربرانی که ربات هنوز فرآیند زنده‌ای برایشان
    دارد (پنجرهٔ امضا/پرداخت/اصلاح تازه‌تر از ۲۴ ساعت، صف خارج از ساعت کاری،
    رسید کارت‌به‌کارت در بررسی مدیر) کنار گذاشته می‌شوند.
  - حافظهٔ ربات برای همان کاربران پاک می‌شود (فاکتور/امضا/اصلاح/تسک ناقص و
    state گفتگو اگر کاربر ۲۴ ساعت بی‌کار بوده).
  - به کاربرانی که پرونده‌شان تازه (≤۴۸ ساعت) از مرز ۲۴ ساعت گذشته و مبلغی
    پرداخت کرده‌اند پیام پشتیبانی می‌رود؛ پرونده‌های قدیمی‌تر (مثلاً اولین اجرا)
    بی‌صدا بسته می‌شوند. خلاصه برای مدیر ارسال می‌شود.
  - هنگام «قطعی سامانه» (/outage_on) اجرا نمی‌شود، و اگر ربات تازه پس از یک
    خاموشی طولانی بالا آمده، مدت خاموشی به مهلت ۲۴ ساعت اضافه می‌شود.
"""
import asyncio
import datetime
import json
import logging
import os
import time

from aiogram import Bot
from aiogram.fsm.storage.base import StorageKey

import runtime_state
from config import ADMIN_ID

logger = logging.getLogger(__name__)

STALE_HOURS = 24
NOTIFY_WINDOW_HOURS = 48
SWEEP_INTERVAL_SECONDS = 3600
SUPPORT_TEXT = ("جهت ادامه به پشتیبانی به شماره 09306186888 در بله یا واتس‌اپ "
                "مراجعه بفرمائید.")

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stale_requests_state.json")

# مخازنی که entry آن‌ها «انتظار اقدام کاربر» است و فیلد زمان datetime دارند
_TIMED_STORES = (
    "pending_lavayeh_payments", "pending_tn_payments", "pending_admin_fee_payments",
    "pending_lavayeh_sign", "pending_ezhhar_sign", "pending_tn_sign",
    "pending_ezhhar_sana_fix", "invalid_tracking_retry", "disrupted_users",
)
_TS_FIELDS = (
    "sign_sent_time", "code_sent_time", "created_at", "timestamp",
    "granted_at", "payment_time", "invoice_time", "started_at",
    "last_activity_at", "code_sent_announce_time", "total_no_action_start",
    "wrong_code_time", "expires_at",
)
# پنجره‌های مهلت‌دار (جریمه/اطلاع‌رسانی‌شان با nid_fix_window است) — تا وقتی
# مهلتشان باقی است کاربر کنار گذاشته می‌شود
_DEADLINE_STORES = ("pending_nid_fix_windows", "pending_tn_retrieve_fix", "pending_contract_fix",
                    "pending_lavayeh_case_fix")
# مخازنی که هنگام لغو پرونده برای کاربر پاک می‌شوند
_CLEAR_STORES = (
    "pending_lavayeh_payments", "pending_tn_payments", "pending_admin_fee_payments",
    "pending_lavayeh_sign", "pending_ezhhar_sign", "pending_tn_sign",
    "pending_ezhhar_sana_fix", "pending_tn_sana_fix", "pending_lavayeh_sana_fix",
    "invalid_tracking_retry", "tn_queried_persons", "recovery_notified",
)

_process_start = time.time()


def _latest_ts(info):
    ts = None
    if isinstance(info, dict):
        for f in _TS_FIELDS:
            v = info.get(f)
            if isinstance(v, datetime.datetime):
                v = v.replace(tzinfo=None) if v.tzinfo else v
                ts = v if ts is None or v > ts else ts
    return ts


def _entry_user_id(name: str, key, info) -> str | None:
    """شناسهٔ کاربرِ یک رکورد مخزن — pending_admin_fee_payments با fid یکتای
    فاکتور کلید می‌خورد (اصلاحیه ۱۴۰۵/۰۸)؛ کاربر داخل خود رکورد است."""
    if isinstance(info, dict) and name == "pending_admin_fee_payments":
        uid = info.get("uid")
        return str(uid) if uid else None
    return str(key) if key is not None else None


def _excluded_users() -> set:
    """کاربرانی که هنوز فرآیند زنده (تازه‌تر از ۲۴ ساعت) دارند."""
    now = datetime.datetime.now()
    limit = datetime.timedelta(hours=STALE_HOURS)
    out = set()
    for name in _TIMED_STORES:
        for uid, info in list((getattr(runtime_state, name, None) or {}).items()):
            ts = _latest_ts(info)
            if ts is not None and now - ts < limit:
                u = _entry_user_id(name, uid, info)
                if u:
                    out.add(u)
    for name in _DEADLINE_STORES:
        for uid, info in list((getattr(runtime_state, name, None) or {}).items()):
            dl = info.get("deadline") if isinstance(info, dict) else None
            if isinstance(dl, datetime.datetime):
                dl = dl.replace(tzinfo=None) if dl.tzinfo else dl
                if dl > now:
                    out.add(str(uid))
    try:
        import sana_gate
        out.update(str(u) for u in sana_gate.deferred_by_user() if u)
    except Exception as e:
        logger.warning(f"[STALE] خواندن صف خارج از ساعت کاری ناموفق: {e}")
    try:
        import pending_jobs
        out.update(pending_jobs.user_ids())
    except Exception as e:
        logger.warning(f"[STALE] خواندن دفتر درخواست‌های ثبت ناموفق: {e}")
    try:
        import card_payment
        for e in list(getattr(card_payment, "_store", {}).values()):
            if e.get("status") == getattr(card_payment, "S_REVIEW", "review") and e.get("uid"):
                out.add(str(e["uid"]))
    except Exception as e:
        logger.warning(f"[STALE] خواندن رسیدهای کارت‌به‌کارت ناموفق: {e}")
    for uid in list(getattr(runtime_state, "pending_admin_payment_review", {}) or {}):
        out.add(str(uid))
    return out


def _load_state() -> dict:
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(data: dict):
    try:
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, STATE_FILE)
    except Exception as e:
        logger.error(f"[STALE] خطا در ذخیرهٔ وضعیت: {e}")


def _effective_hours(downtime_seconds: float) -> int:
    """۲۴ ساعت + مدت خاموشی اخیر ربات (تا وقتی ۲۴ ساعت از راه‌اندازی نگذشته)."""
    if time.time() - _process_start < STALE_HOURS * 3600 and downtime_seconds > 600:
        return STALE_HOURS + int(downtime_seconds // 3600) + 1
    return STALE_HOURS


async def _clear_user_memory(bot: Bot, uid_str: str):
    try:
        uid = int(uid_str)
    except (TypeError, ValueError):
        return
    for name in _CLEAR_STORES:
        store = getattr(runtime_state, name, None)
        if isinstance(store, dict):
            if name == "pending_admin_fee_payments":
                # ⭐ کلید = fid یکتای فاکتور؛ همهٔ فاکتورهای «همین کاربر» پاک شوند
                for key, info in list(store.items()):
                    if isinstance(info, dict) and str(info.get("uid")) == uid_str:
                        store.pop(key, None)
            else:
                store.pop(uid, None)
    runtime_state.active_lavayeh_users.discard(uid)
    for key, info in list(runtime_state.incomplete_tasks.items()):
        if isinstance(info, dict) and str(info.get("user_id")) == uid_str:
            runtime_state.incomplete_tasks.pop(key, None)
    # state گفتگو فقط اگر کاربر ۲۴ ساعت هیچ اقدامی نکرده (درخواست تازه‌اش دست نخورد)
    try:
        import user_activity
        idle = user_activity.seconds_idle(uid)
        dp = getattr(runtime_state, "dp", None)
        if dp is not None and getattr(bot, "id", None) and (idle is None or idle > STALE_HOURS * 3600):
            key = StorageKey(bot_id=bot.id, chat_id=uid, user_id=uid)
            if await dp.storage.get_state(key):
                await dp.storage.set_state(key, state=None)
                await dp.storage.set_data(key, {})
    except Exception as e:
        logger.warning(f"[STALE] پاک‌کردن state کاربر {uid}: {e}")


def _label(c: dict) -> str:
    from daily_report import SERVICE_LABELS
    svc = SERVICE_LABELS.get(c.get("serviceType"), c.get("serviceType") or "درخواست")
    tc = c.get("trackingCode")
    return f"{svc} (کد رهگیری {tc})" if tc else svc


async def sweep(bot: Bot, downtime_seconds: float = 0) -> dict | None:
    """یک دور پاک‌سازی؛ خروجی پنل یا None."""
    try:
        import sana_gate
        if sana_gate.is_outage():
            logger.info("[STALE] سامانه در حالت قطعی است — پاک‌سازی انجام نشد.")
            return None
    except Exception:
        pass

    from panel_sync import expire_stale_cases
    hours = _effective_hours(downtime_seconds)
    data = await expire_stale_cases(hours, max(NOTIFY_WINDOW_HOURS, hours * 2), sorted(_excluded_users()))
    if not data or not data.get("expired"):
        return data

    for uid_str in data.get("userIds") or []:
        await _clear_user_memory(bot, uid_str)

    recent = data.get("recent") or []
    by_user: dict = {}
    for c in recent:
        if c.get("paid"):
            by_user.setdefault(str(c.get("baleUserId")), []).append(c)
    notified = 0
    for uid_str, items in by_user.items():
        names = "، ".join(_label(c) for c in items)
        text = (f"⏳ درخواست {names} شما پس از ۲۴ ساعت بدون تکمیل، از ربات حذف شد.\n\n"
                f"با توجه به پرداختی که انجام داده‌اید، {SUPPORT_TEXT}")
        try:
            await bot.send_message(int(uid_str), text)
            notified += 1
        except Exception as e:
            logger.warning(f"[STALE] ارسال پیام به کاربر {uid_str} ناموفق: {e}")

    expired = int(data.get("expired") or 0)
    logger.info(f"[STALE] {expired} پرونده لغو شد ({len(recent)} تازه، {notified} کاربر مطلع شد).")
    if recent:
        lines = [f"🧹 لغو خودکار درخواست‌های بی‌پیشرفت (بیش از {hours} ساعت): {len(recent)}"]
        for c in recent[:10]:
            mark = " — 💵 پرداخت‌شده" if c.get("paid") else ""
            lines.append(f"   • {_label(c)} — کاربر {c.get('baleUserId')}{mark}")
        if len(recent) > 10:
            lines.append(f"   … و {len(recent) - 10} مورد دیگر")
        if notified:
            lines.append(f"✉️ پیام مراجعه به پشتیبانی برای {notified} کاربر پرداخت‌کننده ارسال شد.")
        if expired > len(recent):
            lines.append(f"🗂 {expired - len(recent)} پروندهٔ قدیمی‌تر هم بی‌صدا بسته شد.")
        try:
            await bot.send_message(ADMIN_ID, "\n".join(lines))
        except Exception as e:
            logger.warning(f"[STALE] ارسال خلاصه به مدیر ناموفق: {e}")
    return data


async def stale_requests_loop(bot: Bot, first_delay_seconds: int = 180):
    """هر ساعت یک دور پاک‌سازی؛ ضربان قلب روی دیسک برای محاسبهٔ مدت خاموشی."""
    prev = _load_state().get("heartbeat")
    downtime = max(0.0, _process_start - prev) if isinstance(prev, (int, float)) else 0.0
    await asyncio.sleep(first_delay_seconds)   # پس از گرم شدن پنل
    while True:
        try:
            await sweep(bot, downtime)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[STALE] خطا در پاک‌سازی: {e}", exc_info=True)
        try:
            for _ in range(SWEEP_INTERVAL_SECONDS // 300):
                _save_state({"heartbeat": time.time()})
                await asyncio.sleep(300)
        except asyncio.CancelledError:
            break
