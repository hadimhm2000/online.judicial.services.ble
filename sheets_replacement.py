"""
فایل جایگزین sheets.py برای اتصال به داشبورد Next.js

این فایل را به جای sheets.py فعلی ربات بله استفاده کنید.
ربات به جای ارسال مستقیم به گوگل شیت، رویدادها را از طریق
وبهوک به داشبورد ارسال می‌کند و داشبورد آن‌ها را هم در
دیتابیس و هم در گوگل شیت ثبت می‌کند.

مزایا:
  - اگر اتصال گوگل شیت قطع شود، داده‌ها در دیتابیس باقی می‌مانند
  - رویدادهای سینک نشده بعداً قابل سینک مجدد هستند
  - رکوردهای ناقص (خطای سیستمی) به صورت خودکار شناسایی و به مدیر اطلاع داده می‌شوند
  - کد رهگیری (txtBillNo) حتی در صورت خطا استخراج و ثبت می‌شود

تنظیم:
  WEBHOOK_URL را به آدرس داشبورد خود تغییر دهید
"""

import asyncio
import datetime
import logging

try:
    import aiohttp
except ImportError:
    import subprocess
    subprocess.check_call(["pip", "install", "aiohttp"])
    import aiohttp

# آدرس داشبورد — تغییر دهید
WEBHOOK_URL = "https://YOUR_DASHBOARD_URL/api/webhook/log"


async def append_to_sheet(row_data):
    """سازگاری با کد قبلی — حالا از طریق وبهوک کار می‌کند"""
    if len(row_data) >= 9:
        await log_event(
            event_type=row_data[1] if len(row_data) > 1 else "",
            query_type=row_data[2] if len(row_data) > 2 else "",
            full_name=row_data[3] if len(row_data) > 3 else "",
            user_id=row_data[4] if len(row_data) > 4 else "",
            tracking_code=row_data[5] if len(row_data) > 5 else "",
            doc_name=row_data[6] if len(row_data) > 6 else "",
            payment_status=row_data[7] if len(row_data) > 7 else "-",
            note=row_data[8] if len(row_data) > 8 else "")


async def log_event(
    event_type: str,
    query_type: str,
    full_name: str,
    user_id,
    tracking_code: str = "",
    national_id: str = "",
    doc_name: str = "",
    payment_status: str = "-",
    note: str = "",
    bill_no: str = ""):
    """
    لاگ رویداد از طریق وبهوک داشبورد.
    
    اگر event_type برابر 'خطای سامانه' باشد، به صورت خودکار:
    - در گوگل شیت با وضعیت 'ناقص به علت خطای سیستمی' ثبت می‌شود
    - به مدیر اطلاع‌رسانی می‌شود
    - اگر bill_no (از txtBillNo) وجود داشته باشد، استخراج و ثبت می‌شود
    """
    payload = {
        "event_type": event_type,
        "query_type": query_type,
        "full_name": full_name,
        "user_id": str(user_id),
        "tracking_code": tracking_code,
        "national_id": national_id,
        "doc_name": doc_name,
        "payment_status": payment_status,
        "note": note,
        "bill_no": bill_no,
        "is_incomplete": event_type == "خطای سامانه",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                WEBHOOK_URL,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    logging.info(
                        f"✅ Event logged (id={data.get('event_id')}, "
                        f"sheet={'✅' if data.get('synced_to_sheet') else '❌'})"
                    )
                else:
                    text = await resp.text()
                    logging.error(f"❌ Webhook error ({resp.status}): {text}")
    except Exception as e:
        logging.error(f"❌ Webhook connection error: {e}")
        # فال‌بک: تلاش مجدد در آینده — داده در حافظه ذخیره شود
        _pending_events.append(payload)
        logging.info(f"📦 Event queued for retry ({len(_pending_events)} pending)")


# صف رویدادهای ارسال‌نشده
_pending_events = []


async def retry_pending_events():
    """ارسال مجدد رویدادهای ارسال‌نشده"""
    global _pending_events
    if not _pending_events:
        return

    remaining = []
    for payload in _pending_events:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    WEBHOOK_URL,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        remaining.append(payload)
        except Exception:
            remaining.append(payload)

    _pending_events = remaining
    if remaining:
        logging.warning(f"⚠️ {len(remaining)} events still pending")
