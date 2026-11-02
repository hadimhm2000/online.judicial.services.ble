"""
pay_reconcile.py — آشتی‌سازی پرداخت‌های بی‌پیگیری (۱۴۰۵/۰۸)
══════════════════════════════════════════════════════════════════════════════

ریشهٔ مسئله (لاگ ۱۴۰۵/۰۸/۰۶ — کاربر ۲۷۲۶۶۰۵۴۹): پرداخت انجام می‌شود ولی به
دلایلی (ری‌استارت ربات بین پرداخت و انبار شدن تسک، خطای هندلر و ...) هیچ
پیگیری‌ای برایش شروع نمی‌شود و تا وقتی کاربر یا مدیر متوجه شوند، پولِ کاربر
تعلق‌کرده است.

این حلقهٔ پس‌زمینه هر ۱۰ دقیقه یکبار وضعیت «پیش‌پرداخت‌های ثبت‌شده» را با
نشانه‌های واقعی فعالیت (صف ثبت، امضا، اصلاح، اعلان قطعی، پروندهٔ باز و …)
مقایسه می‌کند و اگر پرداختی ۱۰ تا ۱۲۰ دقیقه دیرتر هنوز هیچ پیگیری ندارد،
فقط یک بار برای همان پرداخت به مدیر هشدار می‌دهد (بدون هیچ اقدام خودکار —
تصمیم و اقدام با مدیر است).

ایمنی‌ها:
  - فقط «هشدار» — هیچ state، صف یا پرداختی را تغییر نمی‌دهد.
  - هر پرداخت (user + زمان ثبت + مبلغ) فقط یک بار گزارش می‌شود.
  - اگر نشانهٔ فعال بودن پیدا شود (حتی دیرهنگام) دیگر گزارش نمی‌شود؛
    رکوردهای قدیمی‌تر از ۲ ساعت (که فرآیندشان تمام/تعیین‌تکلیف شده) نادیده
    گرفته می‌شوند تا هشدار بی‌مورد برای پرونده‌های درست‌امان تکرار نشود.
"""
import asyncio
import datetime
import logging

from aiogram import Bot

import runtime_state
from config import ADMIN_ID

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 10 * 60      # هر ۱۰ دقیقه
MIN_AGE_MINUTES = 10                  # حداقل سن پرداخت برای گزارش
MAX_AGE_MINUTES = 120                 # پرداخت‌های قدیمی‌تر گزارش نمی‌شوند

# (uid, paid_at_iso, amount_rial) های گزارش‌شده — فقط برای جلوگیری از تکرار
_alerted: set = set()


def _user_has_followup(uid: int) -> bool:
    """آیا برای این کاربر نشانه‌ای از پیگیریِ پرداختش وجود دارد؟

    نشانه‌ها: وجود در صف ثبت (pending_jobs)، مخازن فرآیند فعال
    (امضا/اصلاح/پرداخت/قطعی — user_activity.is_busy)، کاربران فعال لایحه،
    یا پروندهٔ بازِ قابل پرداخت در دفتر pending_cases.
    """
    try:
        import pending_jobs
        if uid in pending_jobs.user_ids():
            return True
    except Exception:
        pass
    try:
        import user_activity
        if user_activity.is_busy(uid):
            return True
    except Exception:
        pass
    try:
        active = getattr(runtime_state, "active_lavayeh_users", None) or set()
        if uid in active:
            return True
    except Exception:
        pass
    try:
        import pending_cases
        now = datetime.datetime.now(datetime.timezone.utc)
        with pending_cases._lock:
            items = [dict(it) for it in pending_cases._load()["items"]]
        for it in items:
            if it.get("user_id") == uid and pending_cases._is_visible(it, now):
                return True
    except Exception:
        pass
    return False


async def run_once(bot: Bot, now: datetime.datetime | None = None) -> int:
    """یک دور بررسی؛ خروجی: تعداد هشدارهای ارسال‌شده."""
    now = now or datetime.datetime.now()
    prepaid = getattr(runtime_state, "prepaid_registrations", None) or {}
    sent = 0
    for uid, rec in list(prepaid.items()):
        try:
            if not isinstance(rec, dict):
                continue
            paid_at = rec.get("paid_at")
            if not isinstance(paid_at, datetime.datetime):
                continue
            age_min = (now - paid_at).total_seconds() / 60
            if age_min < MIN_AGE_MINUTES or age_min > MAX_AGE_MINUTES:
                continue
            if _user_has_followup(int(uid)):
                continue
            amount_rial = int(rec.get("amount_rial", 0) or 0)
            key = (int(uid), paid_at.isoformat(), amount_rial)
            if key in _alerted:
                continue
            _alerted.add(key)
            logger.warning(
                f"[PAY-RECONCILE] پرداخت بدون پیگیری: user={uid} "
                f"مبلغ={amount_rial:,} ریال svc={rec.get('service')} "
                f"charge={rec.get('charge_id') or '—'} سن={int(age_min)} دقیقه")
            try:
                await bot.send_message(
                    ADMIN_ID,
                    "🔎 [PAY-RECONCILE] پرداخت ثبت‌شده بدون پیگیری\n\n"
                    f"👤 کاربر: {uid}\n"
                    f"💰 مبلغ: {amount_rial // 10:,} تومان"
                    f" ({amount_rial:,} ریال)\n"
                    f"🧾 سرویس: {rec.get('service_label') or rec.get('service') or '—'}\n"
                    f"🎫 charge: {rec.get('charge_id') or '—'}\n"
                    f"⏱ زمان پرداخت: {paid_at.strftime('%Y/%m/%d %H:%M')}"
                    f" (حدود {int(age_min)} دقیقه پیش)\n\n"
                    "این کاربر پیش‌پرداخت پرداخته اما هیچ فرآیند فعالی (صف ثبت، "
                    "امضا، اصلاح یا پروندهٔ باز) برایش یافت نشد. لطفاً بررسی کنید؛"
                    " مبلغ به‌عنوان اعتبار کاربر ثبت است و در فاکتور بعدی او کسر می‌شود.")
                sent += 1
            except Exception as e:
                logger.warning(f"[PAY-RECONCILE] ارسال هشدار به مدیر ناموفق: {e}")
        except Exception as e:
            logger.warning(f"[PAY-RECONCILE] بررسی کاربر {uid} ناموفق: {e}")

    # پاکسازی کلیدهای گزارش‌شدهٔ قدیمی (بیش از یک روز) — جلوگیری از رشد بی‌نهایت
    if len(_alerted) > 500:
        cutoff = (now - datetime.timedelta(days=1)).isoformat()
        _alerted.symmetric_difference_update(
            {k for k in _alerted if k[1] < cutoff})
    return sent


async def pay_reconcile_loop(bot: Bot, first_delay_seconds: int = 600):
    """حلقهٔ دائمی؛ در main() با asyncio.create_task اجرا می‌شود."""
    logger.info("[PAY-RECONCILE] حلقهٔ آشتی‌سازی پرداخت فعال شد (هر ۱۰ دقیقه)")
    while True:
        try:
            await run_once(bot)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[PAY-RECONCILE] خطا در حلقه: {e}", exc_info=True)
        try:
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            break
