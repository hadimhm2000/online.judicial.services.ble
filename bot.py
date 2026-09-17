import asyncio
import datetime
import logging
import platform
import signal
import sys
import traceback

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from config import BOT_TOKEN, BALE_API_BASE, ADMIN_ID
from bug_reporter import init_file_logging, report_bug, upload_logs
from handlers import router, fallback_router
from scenarios import browser_worker
from admin_relay import admin_relay_router

# فعال‌سازی لاگ فایل چرخشی در اولین فرصت (قابل آپلود مستمر خطاها)
init_file_logging()
import runtime_state
from persistence import (
    load_into_runtime_state, save_runtime_state, was_crash,
    cleanup_expired_disrupted, cleanup_expired_inquiry_attempts,
    mark_crash_and_save)

dp = Dispatcher(storage=MemoryStorage())
dp.include_router(router)
dp.include_router(admin_relay_router)
# ⭐ اصلاحیه: fallback_router باید همیشه *آخرین* روتر ثبت‌شده باشد تا فقط
# وقتی پیامی توسط هیچ‌کدام از روترهای بالا (اصلی/زیرمنوها/ادمین) گرفته
# نشد، اجرا شود — نه زودتر.
dp.include_router(fallback_router)
runtime_state.dp = dp


# ══════════════════════════════════════════════════════════════════════════════
# سیستم نوتیفیکیشن پیش از کرش / اقدام بحرانی
# ══════════════════════════════════════════════════════════════════════════════

async def notify_admin_critical(bot: Bot, title: str, details: str):
    """ارسال پیام بحرانی به مدیر — بدون فرمت Markdown"""
    try:
        await bot.send_message(
            ADMIN_ID,
            f"🚨 {title}\n\n{details}")
    except Exception as e:
        logging.error(f"[NOTIFY] خطا در ارسال به مدیر: {e}", exc_info=True)


async def notify_user_critical(bot: Bot, user_id: int, message: str):
    """ارسال پیام بحرانی به کاربر."""
    try:
        await bot.send_message(user_id, message)
    except Exception as e:
        logging.error(f"[NOTIFY] خطا در ارسال به کاربر {user_id}: {e}")


async def notify_crash_imminent(bot: Bot, reason: str):
    """اعلام به مدیر و کاربران فعال قبل از وقوع کرش یا توقف بحرانی.

    این تابع باید پیش از هر اقدام بحرانی (کرش، توقف اضطراری و ...) فراخوانی شود.
    """
    logging.critical(f"[CRASH-IMMINENT] دلیل: {reason}")

    # اطلاع به مدیر
    await notify_admin_critical(
        bot,
        "⚠️ ربات در حال توقف اضطراری",
        f"دلیل: {reason[:300]}\n\n"
        f"🔄 حالت ذخیره شده. پس از رفع مشکل ربات را ری‌استارت کنید."
    )

    # اطلاع به تمام کاربران فعال
    active_uids = set()
    active_uids.update(runtime_state.disrupted_users.keys())
    active_uids.update(runtime_state.active_lavayeh_users)
    active_uids.update(runtime_state.pending_lavayeh_sign.keys())
    active_uids.update(runtime_state.pending_ezhhar_sign.keys())
    active_uids.update(runtime_state.pending_lavayeh_payments.keys())
    active_uids.update(runtime_state.pending_ezhhar_sana_fix.keys())

    for uid in active_uids:
        await notify_user_critical(
            bot, uid,
            "🤖 *بابت اختلال پیش‌آمده در سامانه صمیمانه پوزش می‌طلبیم.*\n\n"
            "ربات موقتاً با مشکل فنی مواجه شده است."
            "در صورت ثبت درخواست، مطمئن باشید موارد شما در روند ثبت قرار گرفته است.\n\n"
            "لطفاً چند دقیقه دیگر مجدداً اقدام فرمایید."
        )


def _global_exception_handler(exc_type, exc_value, exc_traceback):
    """هدلر سراسری خطا — ذخیره‌ی فوری حالت و لاگ بحرانی."""
    logging.critical(f"FATAL EXCEPTION: {exc_type.__name__}: {exc_value}")
    try:
        mark_crash_and_save()
    except Exception:
        pass
    # فراخوانی هندلر پیش‌فرض
    sys.__excepthook__(exc_type, exc_value, exc_traceback)


# ⭐ TTL صف‌های امضا/پرداخت/اصلاح — ریشهٔ تکرار پیام: ماندگاری ابدی entryها
_PENDING_TTL_HOURS = 24
_PENDING_TS_FIELDS = (
    "sign_sent_time", "code_sent_time", "created_at", "timestamp",
    "granted_at", "payment_time", "invoice_time", "started_at",
    "last_activity_at", "code_sent_announce_time", "total_no_action_start",
)


def cleanup_expired_pending_entries():
    """پاکسازی entryهای منقضی صف‌های امضا/پرداخت (بیش از _PENDING_TTL_HOURS ساعت عدم فعالیت).

    ⭐ پیشنهاد تکمیلی: ریشهٔ اصلی تکرار ماه‌ها پیام بازیابی، ماندن کاربر
    برای همیشه در pending_lavayeh_sign / pending_ezhhar_sign / ... بود.
    این تابع هر entry که از هر فیلد datetime موجود در آن قدیمی‌تر از
    ۲۴ ساعت باشد را حذف می‌کند (entry بدون timestamp محافظت می‌شود) و
    پرچم recovery_notified کاربر را هم پاک می‌کند. با این کار، فقط
    پرونده‌های واقعاً جاری باقی می‌مانند و دیگر هیچ‌وقت برای پروندهٔ
    ماه‌ها-گذشته پیامی نمی‌رود — حتی بدون نیاز به dedupe.
    """
    now = datetime.datetime.now()
    stores = (
        ("pending_lavayeh_sign", getattr(runtime_state, "pending_lavayeh_sign", None)),
        ("pending_ezhhar_sign", getattr(runtime_state, "pending_ezhhar_sign", None)),
        ("pending_tn_sign", getattr(runtime_state, "pending_tn_sign", None)),
        ("pending_ezhhar_sana_fix", getattr(runtime_state, "pending_ezhhar_sana_fix", None)),
        ("pending_lavayeh_payments", getattr(runtime_state, "pending_lavayeh_payments", None)),
        ("invalid_tracking_retry", getattr(runtime_state, "invalid_tracking_retry", None)),
    )
    removed = 0
    for store_name, store in stores:
        if not isinstance(store, dict):
            continue
        for uid in list(store.keys()):
            info = store.get(uid)
            ts = None
            if isinstance(info, dict):
                for field in _PENDING_TS_FIELDS:
                    v = info.get(field)
                    if isinstance(v, datetime.datetime):
                        ts = v if ts is None or v > ts else ts
            if ts is None:
                continue  # تاریخ نامشخص — محافظت می‌شود
            if (now - ts).total_seconds() > _PENDING_TTL_HOURS * 3600:
                store.pop(uid, None)
                getattr(runtime_state, "recovery_notified", {}).pop(uid, None)
                removed += 1
                logging.info(f"[CLEANUP] {store_name}: entry کاربر {uid} پس از {_PENDING_TTL_HOURS} ساعت عدم فعالیت حذف شد.")
    if removed:
        logging.info(f"[CLEANUP] مجموع {removed} entry منقضی از صف‌ها حذف شد.")


async def state_persister(bot: Bot):
    """تسک پس‌زمینه: ذخیره‌سازی دوره‌ی حالت (هر ۶۰ ثانیه) و پاکسازی رکوردهای منقضی."""
    while True:
        try:
            await asyncio.sleep(60)
            save_runtime_state()
            cleanup_expired_disrupted()
            cleanup_expired_inquiry_attempts()
            cleanup_expired_pending_entries()
            logging.debug("[PERSIST] ذخیره‌ی دوره‌ی انجام شد.")
        except asyncio.CancelledError:
            logging.info("[PERSIST] state_persister لغو شد.")
            break
        except Exception as e:
            logging.error(f"[PERSIST] خطا در ذخیره‌ی دوره‌ی: {e}")


def _recovery_case_fingerprint(uid: int) -> str:
    """اثر انگشت پرونده/رویداد فعال کاربر — برای ارسال فقط یک‌بار پیام بازیابی.

    تا وقتی پرونده همان است (همان کد رهگیری/همان رویداد قطع)، اثر انگشت
    ثابت می‌ماند و پیام عذرخواهی تکرار نمی‌شود. پرونده جدید یا رویداد جدید
    (کد رهگیری/زمان جدید) → اثر انگشت جدید → اطلاع‌رسانی دوباره.
    """
    parts = []
    info = runtime_state.pending_lavayeh_sign.get(uid)
    if info:
        parts.append(f"lav:{info.get('tracking_code', '')}")
    info = runtime_state.pending_ezhhar_sign.get(uid)
    if info:
        parts.append(f"ezr:{info.get('tracking_code', '')}")
    info = getattr(runtime_state, "pending_tn_sign", {}).get(uid)
    if info:
        parts.append(f"tn:{info.get('tracking_code', '')}")
    info = runtime_state.pending_ezhhar_sana_fix.get(uid)
    if info:
        td = info.get("task_data") or {}
        parts.append(f"fix:{td.get('tracking_code', '') or info.get('created_at', '')}")
    info = runtime_state.disrupted_users.get(uid)
    if info:
        jd = info.get("job_data") or {}
        parts.append(f"dis:{jd.get('tracking_code', '') or info.get('timestamp', '')}")
    return "|".join(parts) if parts else f"uid:{uid}"


async def notify_crash_recovery(bot: Bot, submitted_users: list, unsubmitted_users: list):
    """ارسال پیام عذرخواهی به کاربرانی که در میان فرآیند بودند.

    - submitted_users: کاربرانی که درخواستشان قبلاً ثبت شده (در روند پردازش)
    - unsubmitted_users: کاربرانی که هنوز ثبت نکرده‌اند (قطع قبل از ثبت)

    ⭐ اصلاحیه: هر کاربر فقط یک‌بار برای هر پرونده/رویداد اطلاع‌رسانی
    می‌شود (recovery_notified + اثر انگشت). تکرار ماه‌ها ادامه‌دار قبلی —
    به‌علت ماندن entry قدیمی در pending_* — متوقف می‌شود و فقط پرونده/
    رویداد جدید پیام تازه می‌گیرد.
    """
    if not submitted_users and not unsubmitted_users:
        return

    # ذخیره در runtime_state برای ارسال به هندلر /start
    runtime_state._crash_recovered_users = {}
    runtime_state._crash_recovered_submitted = set()
    runtime_state._crash_recovered_unsubmitted = set()

    # ⭐ شمارنده‌های ارسال/رد (برای گزارش دقیق به مدیر)
    sent_sub = skipped_sub = sent_unsub = skipped_unsub = 0

    # ── پیام به کاربرانی که درخواستشان ثبت شده ──
    for uid in submitted_users:
        # ⭐ ارسال فقط یک‌بار برای هر پرونده — پرونده/رویداد جدید دوباره پیام می‌گیرد
        fp = _recovery_case_fingerprint(uid)
        if runtime_state.recovery_notified.get(uid) == fp:
            logging.info(f"[CRASH_RECOVERY] کاربر {uid} قبلاً برای همین پرونده اطلاع‌رسانی شده — رد شد.")
            skipped_sub += 1
            continue
        try:
            await bot.send_message(
                uid,
                "🤖 *بابت اختلال پیش‌آمده در سامانه صمیمانه پوزش می‌طلبیم.*\n\n"
                "درخواست شما قبلاً در سامانه ثبت شده و در حال پردازش/ثبت نهایی است.\n"
                "مطمئن باشید که موارد شما در روند ثبت قرار گرفته است.\n\n"
                "در صورتی که تا ۴۵ دقیقه دیگر موارد شما ارسال نشد، لطفاً به شماره "
                "09306186888 در بله یا واتس‌اپ پیام ارسال فرمایید.")
            runtime_state.recovery_notified[uid] = fp
            runtime_state._crash_recovered_users[uid] = "submitted"
            runtime_state._crash_recovered_submitted.add(uid)
            sent_sub += 1
        except Exception as e:
            logging.warning(f"[CRASH_RECOVERY] خطا در ارسال پیام به {uid}: {e}")

    # ── پیام به کاربرانی که هنوز ثبت نشده ──
    for uid in unsubmitted_users:
        # ⭐ ارسال فقط یک‌بار برای هر رویداد قطع — رویداد جدید دوباره پیام می‌گیرد
        fp = _recovery_case_fingerprint(uid)
        if runtime_state.recovery_notified.get(uid) == fp:
            logging.info(f"[CRASH_RECOVERY] کاربر {uid} قبلاً برای همین رویداد اطلاع‌رسانی شده — رد شد.")
            skipped_unsub += 1
            continue
        try:
            await bot.send_message(
                uid,
                "🤖 *بابت اختلال پیش‌آمده در سامانه صمیمانه پوزش می‌طلبیم.*\n\n"
                "متاسفانه فرآیند شما پیش از ثبت نهایی قطع شد.\n"
                "لطفاً مجدداً از ابتدا اقدام فرمایید.\n\n"
                "اگر قبلاً پرداخت کرده‌اید، نگران نباشید — "
                "پس از شروع مجدد، فرصت تکرار بدون پرداخت به شما داده می‌شود.")
            runtime_state.recovery_notified[uid] = fp
            runtime_state._crash_recovered_users[uid] = "unsubmitted"
            runtime_state._crash_recovered_unsubmitted.add(uid)
            sent_unsub += 1
        except Exception as e:
            logging.warning(f"[CRASH_RECOVERY] خطا در ارسال پیام به {uid}: {e}")

    # ── اطلاع به مدیر — بدون فرمت Markdown ──
    try:
        await bot.send_message(
            ADMIN_ID,
            f"🔄 ربات ری‌استارت شد (بازیابی از کرش)\n\n"
            f"✅ ثبت‌شده (در روند پردازش): {len(submitted_users)} کاربر"
            f" — پیام ارسال شد: {sent_sub} | رد شد (قبلاً اطلاع‌رسانی شده): {skipped_sub}\n"
            f"⚠️ ثبت‌نشده (نیاز به اقدام مجدد): {len(unsubmitted_users)} کاربر"
            f" — پیام ارسال شد: {sent_unsub} | رد شد (قبلاً اطلاع‌رسانی شده): {skipped_unsub}\n\n"
            f"📋 IDs ثبت‌شده: {', '.join(str(u) for u in submitted_users[:20])}\n\n"
            f"📋 IDs ثبت‌نشده: {', '.join(str(u) for u in unsubmitted_users[:20])}\n\n"
            f"✅ حالت ذخیره‌شده بارگذاری شد.")
        logging.info("[RECOVERY] اطلاع به مدیر ارسال شد.")
    except Exception as e:
        logging.error(f"[RECOVERY] خطا در ارسال به مدیر: {e}", exc_info=True)


async def shutdown_handler(bot: Bot, signal_name: str):
    """مدیریت خاموشی نرم — ذخیره‌ی حالت و اطلاع‌رسانی."""
    logging.warning(f"[SHUTDOWN] سیگنال {signal_name} دریافت شد — شروع خاموشی نرم...")

    # اطلاع به کاربران فعال
    await notify_crash_imminent(bot, f"خاموشی نرم ({signal_name})")

    # ذخیره‌ی فوری حالت
    try:
        save_runtime_state()
        logging.info("[SHUTDOWN] حالت با موفقیت ذخیره شد.")
    except Exception as e:
        logging.error(f"[SHUTDOWN] خطا در ذخیره‌ی حالت: {e}")

    # اطلاع نهایی به مدیر — بدون فرمت Markdown
    try:
        await bot.send_message(
            ADMIN_ID,
            f"🔴 ربات در حال خاموش شدن است ({signal_name})\n\n"
            f"✅ حالت ذخیره شد. ری‌استارت بعدی از حالت ذخیره‌شده ادامه می‌یابد.")
        logging.info(f"[SHUTDOWN] اطلاع خاموشی به مدیر ارسال شد.")
    except Exception as e:
        logging.error(f"[SHUTDOWN] خطا در ارسال به مدیر: {e}", exc_info=True)


async def main():
    # ── بررسی کرش قبلی و بارگذاری حالت ──
    crashed, crash_data = was_crash()
    active_submitted, active_unsubmitted = load_into_runtime_state()
    # ⭐ پیشنهاد تکمیلی: پاکسازی entryهای منقضی (TTL) بلافاصله پس از بارگذاری،
    # تا پرونده‌های ماه‌ها-گذشته نه تنها پیام نگیرند، بلکه از صف‌ها هم پاک شوند.
    cleanup_expired_pending_entries()
    _tn_store = getattr(runtime_state, "pending_tn_sign", {})
    active_submitted = [
        u for u in active_submitted
        if (u in runtime_state.pending_lavayeh_sign
            or u in runtime_state.pending_ezhhar_sign
            or u in _tn_store
            or u in runtime_state.pending_ezhhar_sana_fix)
    ]
    active_unsubmitted = [
        u for u in active_unsubmitted
        if u in runtime_state.disrupted_users
    ]
    runtime_state._load_persisted_subscriptions()
    logging.info(
        f"[START] کرش قبلی: {crashed} | "
        f"کاربران ثبت‌شده: {len(active_submitted)} | "
        f"کاربران ثبت‌نشده: {len(active_unsubmitted)}"
    )

    # ── هندلر سراسری خطا ──
    sys.excepthook = _global_exception_handler

    # ── اتصال به بله ──
    logging.info(f"🔌 اتصال از طریق سرور API بله: {BALE_API_BASE}")
    logging.info(f"👤 ADMIN_ID={ADMIN_ID} (نوع: {type(ADMIN_ID).__name__})")
    custom_api_server = TelegramAPIServer.from_base(BALE_API_BASE)
    session = AiohttpSession(api=custom_api_server)

    bot = Bot(token=BOT_TOKEN, session=session)

    # ارسال پیام تستی به ادمین برای اطمینان از صحت ADMIN_ID
    try:
        test_result = await bot.send_message(ADMIN_ID, "🟢 ربات راه‌اندازی شد.")
        logging.info(f"[START] پیام تستی به ادمین ارسال شد. message_id={test_result.message_id}")
    except Exception as e:
        logging.error(f"[START] خطا در ارسال پیام تستی به ادمین (ADMIN_ID={ADMIN_ID}): {e}", exc_info=True)
        logging.error(f"[START] ⚠️ اگر این خطا رخ داد، احتمالاً ADMIN_ID در فایل .env صحیح نیست یا ادمین ربات را استارت نکرده است.")

    # تنظیم منوی دستورات (بله ممکن است پشتیبانی نکند)
    try:
        await bot.set_my_commands([BotCommand(command="start", description="شروع مجدد ربات / ثبت استعلام جدید")])
    except Exception as e:
        logging.warning(f"set_my_commands پشتیبانی نشد: {e}")

    # حذف webhook قبلی
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception as e:
        logging.warning(f"delete_webhook خطا: {e}")

    # ── اگر کرش شده بود، به کاربران اطلاع بده (با تفکیک ثبت‌شده/ثبت‌نشده) ──
    if crashed and (active_submitted or active_unsubmitted):
        await notify_crash_recovery(bot, active_submitted, active_unsubmitted)
    elif crashed:
        try:
            await bot.send_message(
                ADMIN_ID,
                "🔄 ربات ری‌استارت شد (احتمالاً پس از کرش)\n\n"
                "هیچ کاربر فعالی در حافظه نبود.")
            logging.info("[RECOVERY] اطلاع به مدیر (بدون کاربر فعال) ارسال شد.")
        except Exception as e:
            logging.error(f"[RECOVERY] خطا در ارسال به مدیر: {e}", exc_info=True)

    # ── شروع تسک‌های پس‌زمینه ──
    asyncio.create_task(browser_worker(bot))

    from lavayeh_handlers import lavayeh_payment_reminder_loop
    asyncio.create_task(lavayeh_payment_reminder_loop(bot))

    from subscription_handlers import subscription_expiry_checker
    asyncio.create_task(subscription_expiry_checker(bot))

    # ⭐ گرم کردن پنل ادمین — جلوگیری از Timeout اولین sync پس از استارت
    # (در حالت dev پنل، اولین درخواست هر مسیر باعث کامپایل ۱۰-۳۰ ثانیه‌ای می‌شود)
    from panel_sync import warmup_panel
    asyncio.create_task(warmup_panel())

    # ── تسک ذخیره‌سازی دوره‌ی ──
    persister_task = asyncio.create_task(state_persister(bot))

    # ── مدیریت سیگنال‌های خاموشی (فقط لینوکس/مک — ویندوز پشتیبانی نمی‌کند) ──
    if platform.system() != "Windows":
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown_handler(bot, sig.name)))

    # ── شروع polling (با Timeout 8 ثانیه برای جلوگیری از ارور Vercel) ──
    try:
        await dp.start_polling(bot, timeout=8)
    except Exception as e:
        logging.critical(f"[MAIN] خطای بحرانی در start_polling: {e}", exc_info=True)
        # اطلاع به مدیر و کاربران
        await notify_crash_imminent(bot, f"خطای بحرانی در start_polling: {str(e)[:300]}")
    finally:
        # ذخیره‌ی نهایی حالت
        try:
            save_runtime_state()
        except Exception:
            pass
        # لغو تسک ذخیره‌سازی
        persister_task.cancel()
        logging.info("[MAIN] ربات متوقف شد.")


if __name__ == "__main__":
    asyncio.run(main())