# -*- coding: utf-8 -*-
"""
چک سلامت ماژول ارزش منطقه‌ای — فقط ادمین دسترسی داره.

کامند: /rv_check  (یا دکمه 🔍 چک ارزش منطقه‌ای در پنل ادمین)

تست‌ها:
  ۱. NESHAN_API_KEY تنظیم شده؟
  ۲. اتصال به API نشان (Geocoding)
  ۳. اتصال به tax.gov.ir (استعلام واقعی)
  ۴. ساخت PDF
  ۵. فایل هدر وجود دارد؟
  ۶. وابستگی‌ها نصب هستند؟
"""

import asyncio
import logging
import os
import sys
import time
import traceback

logger = logging.getLogger(__name__)

# ═══ توابع تست (بدون وابستگی به aiogram) ═══
# این توابع هم در بات و هم خط فرمان کار می‌کنند




# ══════════════════════════════════════════════════════════════
# تابع اصلی تست — هم در تلگرام/بله و هم خط فرمان قابل اجراست
# ══════════════════════════════════════════════════════════════

def run_all_checks() -> list[dict]:
    """
    تمام تست‌ها را اجرا می‌کند و لیست نتایج برمی‌گرداند.
    هر آیتم: {"name": str, "ok": bool, "detail": str, "time_ms": int}
    """
    results = []

    # ═══ تست ۱: وابستگی‌ها ═══
    t0 = time.time()
    missing_deps = []
    for mod_name in ["requests", "bs4", "weasyprint"]:
        try:
            __import__(mod_name)
        except ImportError:
            missing_deps.append(mod_name)
    results.append({
        "name": "کتابخانه‌های موردنیاز",
        "ok": len(missing_deps) == 0,
        "detail": "نصب هستند" if not missing_deps else f"نصب نشده: {', '.join(missing_deps)}",
        "time_ms": int((time.time() - t0) * 1000),
    })

    # ═══ تست ۲: NESHAN_API_KEY ═══
    t0 = time.time()
    from config import NESHAN_API_KEY
    api_key_ok = bool(NESHAN_API_KEY and len(NESHAN_API_KEY) > 5)
    results.append({
        "name": "NESHAN_API_KEY",
        "ok": api_key_ok,
        "detail": "تنظیم شده" + (f" ({NESHAN_API_KEY[:6]}...{NESHAN_API_KEY[-4:]})" if api_key_ok else "❌ تنظیم نشده!") ,
        "time_ms": int((time.time() - t0) * 1000),
    })

    # ═══ تست ۳: عکس هدر ═══
    t0 = time.time()
    header_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tax_header.jpg")
    header_exists = os.path.exists(header_path)
    header_size = os.path.getsize(header_path) if header_exists else 0
    results.append({
        "name": "عکس هدر (tax_header.jpg)",
        "ok": header_exists and header_size > 10000,
        "detail": f"وجود دارد ({header_size:,} بایت)" if header_exists else "❌ فایل یافت نشد!",
        "time_ms": int((time.time() - t0) * 1000),
    })

    # ═══ تست ۴: اتصال به API نشان ═══
    t0 = time.time()
    try:
        import requests
        test_addr = "تهران، میدان ونک"
        resp = requests.get(
            "https://api.neshan.org/geocoding/v1/plus",
            params={"json": '{"address": "' + test_addr + '"}'},
            headers={"Api-Key": NESHAN_API_KEY},
            timeout=10,
        )
        neshan_ok = resp.status_code == 200
        data = resp.json() if neshan_ok else {}
        items = data.get("items", [])
        detail = f"موفق — {len(items)} نتیجه"
        if items:
            loc = items[0].get("location", {})
            detail += f" (lat={loc.get('latitude','?')}, lng={loc.get('longitude','?')})"
        if not neshan_ok:
            detail = f"❌ خطای HTTP {resp.status_code}: {resp.text[:200]}"
    except Exception as e:
        neshan_ok = False
        detail = f"❌ خطا: {e}"
    results.append({
        "name": "اتصال به API نشان (Geocoding)",
        "ok": neshan_ok,
        "detail": detail,
        "time_ms": int((time.time() - t0) * 1000),
    })

    # ═══ تست ۵: اتصال به tax.gov.ir ═══
    t0 = time.time()
    try:
        from tax_geolocation_query import get_form_state, get_province_id
        import requests as req_lib

        pid = get_province_id("تهران")
        session = req_lib.Session()
        state = get_form_state(session, pid)
        tax_ok = bool(state.get("__VIEWSTATE"))
        detail = f"موفق — province_id={pid}, VIEWSTATE طول={len(state.get('__VIEWSTATE',''))}"
    except Exception as e:
        tax_ok = False
        detail = f"❌ خطا: {e}"
    results.append({
        "name": "اتصال به tax.gov.ir",
        "ok": tax_ok,
        "detail": detail,
        "time_ms": int((time.time() - t0) * 1000),
    })

    # ═══ تست ۶: استعلام واقعی (کوئری POST) ═══
    t0 = time.time()
    try:
        from tax_geolocation_query import query_location_value
        import requests as req_lib

        # مختصات نمونه: تهران، منطقه ۱
        test_lat, test_lng = 35.735280, 51.376876
        pid = get_province_id("تهران")
        session = req_lib.Session()
        tax_result = query_location_value(session, pid, test_lat, test_lng)

        structured = tax_result.get("فیلدهای_ساختاریافته", {})
        missing = tax_result.get("فیلدهای_پیدا_نشده", [])
        found_count = sum(1 for v in structured.values() if v is not None)
        total_count = len(structured)

        query_ok = found_count >= 3  # حداقل ۳ فیلد پیدا شده
        detail = f"موفق — {found_count}/{total_count} فیلد پیدا شد"
        if missing:
            detail += f" | پیدانشده: {', '.join(missing[:5])}"
    except Exception as e:
        query_ok = False
        detail = f"❌ خطا: {e}"
    results.append({
        "name": "استعلام واقعی tax.gov.ir (POST)",
        "ok": query_ok,
        "detail": detail,
        "time_ms": int((time.time() - t0) * 1000),
    })

    # ═══ تست ۷: ساخت PDF ═══
    t0 = time.time()
    try:
        from regional_value_pdf import build_regional_value_pdf
        import tempfile

        # داده‌های نمونه
        sample_tax_result = {
            "سال": "1405",
            "فیلدهای_ساختاریافته": {
                "اداره کل امور مالیاتی": "اداره کل امور مالیاتی استان تهران (تست)",
                "واحد مرتبط مالیاتی سنیم املاک": "واحد تست",
                "واحد مرتبط مالیاتی سنیم حقوقی": "واحد تست",
                "واحد مرتبط مالیاتی سنیم حقیقی": "واحد تست",
                "واحد مرتبط مالیاتی حقوقی": "واحد تست",
                "واحد مرتبط مالیاتی حقیقی": "واحد تست",
                "واحد مرتبط مالیاتی ارث": "واحد تست",
                "شماره بلوک بر اساس دفترچه ارزش معاملاتی ملک": "-",
                "شماره ردیف بر اساس دفترچه ارزش معاملاتی ملک": "-",
                "ارزش معاملاتی مسکونی": "86,500,000 ریال",
                "ارزش معاملاتی اداری": "120,000,000 ریال",
                "ارزش معاملاتی تجاری": "180,000,000 ریال",
            },
            "همه_فیلدهای_خام_صفحه": {},
            "فیلدهای_پیدا_نشده": [],
        }

        pdf_fd, pdf_path = tempfile.mkstemp(suffix=".pdf")
        os.close(pdf_fd)

        pdf_ok = build_regional_value_pdf(
            tax_result=sample_tax_result,
            province="تهران",
            address="آدرس تست",
            area=100,
            land_use="مسکونی",
            total_value=86500000 * 100,
            output_path=pdf_path,
        )
        pdf_size = os.path.getsize(pdf_path) if pdf_ok else 0

        if not pdf_ok:
            detail = "❌ ساخت PDF ناموفق"
        elif pdf_size < 5000:
            detail = f"⚠️ PDF ساخت ولی خیلی کوچک ({pdf_size:,} بایت)"
            pdf_ok = False
        else:
            detail = f"موفق ({pdf_size:,} بایت)"

        # حذف فایل تست
        try:
            os.remove(pdf_path)
        except Exception:
            pass

    except Exception as e:
        pdf_ok = False
        detail = f"❌ خطا: {e}"
    results.append({
        "name": "ساخت PDF گزارش",
        "ok": pdf_ok,
        "detail": detail,
        "time_ms": int((time.time() - t0) * 1000),
    })

    return results


def format_check_report(results: list[dict]) -> str:
    """فرمت‌بندی نتایج برای ارسال به ادمین."""
    lines = ["🔍 *گزارش چک سلامت ماژول ارزش منطقه‌ای*\n"]

    all_ok = True
    for r in results:
        icon = "✅" if r["ok"] else "❌"
        if not r["ok"]:
            all_ok = False
        lines.append(f"{icon} *{r['name']}*")
        lines.append(f"   {r['detail']}  ({r['time_ms']}ms)")

    total_time = sum(r["time_ms"] for r in results)
    lines.append(f"\n⏱ زمان کل تست: {total_time:,}ms")

    if all_ok:
        lines.append("\n🎉 *همه چیز سالم است!*")
    else:
        failed = [r['name'] for r in results if not r['ok']]
        lines.append(f"\n⚠️ *موارد مشکل‌دار:* {', '.join(failed)}")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════
# هندلر کامند ادمین — /rv_check
# ══════════════════════════════════════════════════════════════

try:
    from aiogram import Bot, Router
    from aiogram.types import Message

    admin_rv_check_router = Router()

    @admin_rv_check_router.message(lambda msg: msg.text == "/rv_check")
    async def rv_check_command(message: Message, bot: Bot):
        """کامند چک سلامت — فقط ادمین."""
        from config import ADMIN_ID

        if message.from_user.id != ADMIN_ID:
            await message.answer("⛔ فقط ادمین دسترسی دارد.")
            return

        await message.answer("🔍 در حال بررسی ماژول ارزش منطقه‌ای...\nلطفاً چند لحظه صبر کنید.")

        try:
            loop = asyncio.get_running_loop()
            results = await loop.run_in_executor(None, run_all_checks)
            report = format_check_report(results)
            await message.answer(report)
        except Exception as e:
            logger.error(f"[ADMIN-CHECK] خطا: {e}", exc_info=True)
            await message.answer(f"❌ خطا در اجرای تست:\n{e}")

except ImportError:
    # aiogram نصب نیست — فقط خط فرمان
    admin_rv_check_router = None
    rv_check_command = None


# ══════════════════════════════════════════════════════════════
# اجرای مستقل خط فرمان: python admin_rv_check.py
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("🔍 چک سلامت ماژول ارزش منطقه‌ای...\n")
    results = run_all_checks()
    for r in results:
        icon = "✅" if r["ok"] else "❌"
        print(f"  {icon} {r['name']}: {r['detail']}  ({r['time_ms']}ms)")

    all_ok = all(r["ok"] for r in results)
    print(f"\n{'🎉 همه چیز سالم است!' if all_ok else '⚠️ موارد مشکل‌دار وجود دارد.'}")
    sys.exit(0 if all_ok else 1)
