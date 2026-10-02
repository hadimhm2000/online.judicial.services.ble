"""
daily_report.py — گزارش شبانهٔ مدیر در بله
══════════════════════════════════════════════════════════════════════════════

هر شب ساعت report.hour (پیش‌فرض ۲۳ به وقت تهران، قابل تغییر از تنظیمات پنل)
خلاصهٔ آن روز از پنل خوانده و برای مدیر فرستاده می‌شود:
  تعداد درخواست‌ها به تفکیک خدمت، انجام‌شده/ناموفق، پرونده‌های گیرکرده
  (بیش از ۳ ساعت در حال ثبت)، مبلغ دریافتی، میانگین امتیاز کاربران و
  امتیازهای پایین. اگر ربات در ساعت گزارش خاموش بوده، گزارش همان روز پس از
  راه‌اندازی (تا پایان روز) ارسال می‌شود.

ارسال دستی در هر لحظه: /report  (یا /report 2026-10-01)
"""
import asyncio
import datetime
import json
import logging
import os

from aiogram import Bot, Router, types
from aiogram.filters import Command

import bot_settings
from config import ADMIN_ID

logger = logging.getLogger(__name__)

TEHRAN = datetime.timezone(datetime.timedelta(hours=3, minutes=30))
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "daily_report_state.json")

report_router = Router()

SERVICE_LABELS = {
    "INQUIRY": "استعلام", "LAVAYEH": "لایحه", "EZHHARNAMEH": "اظهارنامه",
    "EALAM_VAKALAHT": "اعلام وکالت", "TAJDID_NAZAR": "دعاوی اعتراضی", "CHECK": "دادخواست",
    "STAMP_CALC": "محاسبه تمبر", "REGIONAL_VALUE": "ارزش منطقه‌ای",
}


def format_report(r: dict) -> str:
    lines = [f"📊 *گزارش روز {r.get('date', '')}*", ""]
    total = r.get("totalCases", 0)
    lines.append(f"📥 درخواست‌ها: {total}")
    for svc, n in sorted((r.get("byService") or {}).items(), key=lambda x: -x[1]):
        lines.append(f"   • {SERVICE_LABELS.get(svc, svc)}: {n}")
    lines.append(f"✅ انجام‌شده: {r.get('completed', 0)}   ❌ ناموفق: {r.get('failed', 0)}")
    stuck = r.get("stuck") or []
    lines.append(f"⏳ گیرکرده (بیش از ۳ ساعت در حال ثبت): {len(stuck)}")
    for c in stuck[:5]:
        lines.append(f"   • {SERVICE_LABELS.get(c.get('serviceType'), c.get('serviceType'))} — "
                     f"{c.get('trackingCode') or c.get('baleUserId')}")
    lines.append(f"💰 دریافتی امروز: {int(r.get('revenueToman', 0)):,} تومان")
    fb = r.get("feedback") or {}
    if fb.get("count"):
        lines.append(f"⭐ امتیاز کاربران: میانگین {fb.get('average', 0):.1f} از ۵ ({fb['count']} نظر)"
                     f" — امتیاز پایین: {fb.get('low', 0)}")
    else:
        lines.append("⭐ امروز نظری ثبت نشده است.")
    return "\n".join(lines)


def _last_sent() -> str:
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("last_sent", "")
    except Exception:
        return ""


def _mark_sent(day: str):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"last_sent": day}, f)
    except Exception as e:
        logger.error(f"[REPORT] خطا در ذخیرهٔ وضعیت: {e}")


async def send_report(bot: Bot, day: datetime.date) -> bool:
    from panel_sync import get_daily_report
    data = await get_daily_report(day.isoformat())
    if data is None:
        return False
    await bot.send_message(ADMIN_ID, format_report(data))
    return True


async def daily_report_loop(bot: Bot, check_every_seconds: int = 300):
    while True:
        try:
            await asyncio.sleep(check_every_seconds)
            now = datetime.datetime.now(TEHRAN)
            hour = bot_settings.get_int("report.hour", 23)
            if now.hour < hour or _last_sent() == now.date().isoformat():
                continue
            if await send_report(bot, now.date()):
                _mark_sent(now.date().isoformat())
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[REPORT] خطا در گزارش شبانه: {e}")


@report_router.message(Command("report"), lambda m: m.from_user and m.from_user.id == ADMIN_ID)
async def report_cmd(message: types.Message, bot: Bot):
    parts = (message.text or "").split()
    try:
        day = datetime.date.fromisoformat(parts[1]) if len(parts) > 1 else datetime.datetime.now(TEHRAN).date()
    except ValueError:
        await message.answer("فرمت: /report  یا  /report 2026-10-01")
        return
    if not await send_report(bot, day):
        await message.answer("⚠️ دریافت گزارش از پنل ممکن نشد.")
