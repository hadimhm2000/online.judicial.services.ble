"""تست نمایش جدول هزینه دادرسی با کلیک #btnCalculateCash — اجرا:
BOT_TOKEN=1:x ADMIN_ID=1 ADMIN_API_SECRET=x python -m pytest test_cost_table_retry.py

⭐ باگ رفع‌شده (لاگ کارفرما): در بخش هزینه‌ها، جدول هزینه دادرسی نمایش
داده نشد (و/یا پاپ‌آپ «خطا: تاخیر در اجرای سرویس» صادر شد) → ربات مبلغ
صفر ریال محاسبه کرد («[LAVAYEH] مبلغی در جدول پیدا نشد» × ۳ →
court_total: 0).

دستور کارفرما: در چنین حالتی دکمهٔ «محاسبه هزینه ی دادرسی و تعرفه خدمات»
(#btnCalculateCash) زده شود تا جدول هزینه دادرسی نمایش داده شود؛ سپس
استخراج مبلغ تکرار گردد.

پوشش:
  · LAVAYEH (_calculate_cost_with_retry) — با پاپ‌آپ خطا و بدون پاپ‌آپ
  · CHECK (_extract_cost_data_with_retry) — جدول نبود → کلیک → استخراج
"""
import asyncio
import glob
import os

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("ADMIN_API_SECRET", "x")

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import check_scenario
import lavayeh_scenario

FIXTURE = Path(__file__).parent / "test_fixtures" / "sana_cost_delay_mock.html"
USER_ID = 272660549


def _run(coro):
    return asyncio.run(coro)


def _bot():
    bot = MagicMock()
    bot.send_message = AsyncMock()
    return bot


def _chromium():
    """مسیر کرومِ محیط اجرا (مثل سایر تست‌های مرورگری پروژه)."""
    for pattern in ("/opt/pw-browsers/chromium",
                    "/opt/pw-browsers/chromium-*/chrome-linux/chrome"):
        found = sorted(glob.glob(pattern))
        if found and os.path.exists(found[-1]):
            return found[-1]
    return None


async def _with_page(fn, popup_visible=True, table_hidden=True):
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        exe = _chromium()
        browser = await (p.chromium.launch(executable_path=exe, headless=True)
                         if exe else p.chromium.launch(headless=True))
        try:
            ctx = await browser.new_context()
            page = await ctx.new_page()
            await page.goto(FIXTURE.as_uri())
            if not popup_visible:
                await page.evaluate(
                    "() => { const p = document.querySelector('.sweet-alert');"
                    " if (p) p.style.display = 'none'; }")
            if not table_hidden:
                await page.evaluate(
                    "() => showFeeTable()")
            return await fn(page)
        finally:
            await browser.close()


# ── LAVAYEH ────────────────────────────────────────────────────────────────

def test_lavayeh_service_delay_popup_then_table():
    """پاپ‌آپ «تاخیر در اجرای سرویس» + جدول مخفی → بستن پاپ‌آپ + کلیک
    #btnCalculateCash → جدول نمایش → مبلغ درست استخراج می‌شود (نه صفر)."""
    async def scenario(page):
        amount = await lavayeh_scenario._calculate_cost_with_retry(
            page, _bot(), USER_ID)
        assert amount == 1_500_000
        # پاپ‌آپ بسته شده و جدول در DOM render شده است
        assert await page.evaluate(
            "() => getComputedStyle(document.querySelector('.sweet-alert')).display") == "none"
        assert await page.evaluate(
            "() => !!document.querySelector('td.font-yekan-number.color-green.font-size-18')")
        return True
    assert _run(_with_page(scenario))


def test_lavayeh_no_popup_table_not_shown():
    """سناریوی دقیق لاگ کارفرما: بدون پاپ‌آپِ شناخته‌شده، فقط جدول نمایش
    داده نشده → مسیر «مبلغی در جدول پیدا نشد» اکنون #btnCalculateCash را
    کلیک می‌کند و مبلغ صفر نمی‌شود."""
    async def scenario(page):
        # دکمه فقط از طریق مسیر not-found کلیک شود؛ اولین استخراج null است
        amount = await lavayeh_scenario._calculate_cost_with_retry(
            page, _bot(), USER_ID)
        assert amount == 1_500_000
        assert await page.evaluate(
            "() => !!document.querySelector('td.font-yekan-number.color-green.font-size-18')")
        return True
    assert _run(_with_page(scenario, popup_visible=False))


def test_lavayeh_table_already_visible():
    """جدول از قبل نمایش داده شده → مبلغ بدون کلیک اضافه استخراج می‌شود."""
    async def scenario(page):
        amount = await lavayeh_scenario._calculate_cost_with_retry(
            page, _bot(), USER_ID)
        assert amount == 1_500_000
        return True
    assert _run(_with_page(scenario, popup_visible=False, table_hidden=False))


# ── CHECK ──────────────────────────────────────────────────────────────────

def test_check_cost_table_retry():
    """CHECK: جدول هزینه نمایش داده نشد → کلیک #btnCalculateCash →
    costSum/ردیف‌ها استخراج می‌شوند (نه costSum=0)."""
    async def scenario(page):
        cost_data = await check_scenario._extract_cost_data_with_retry(
            page, _bot(), USER_ID)
        assert int(cost_data["costSum"]) == 1_500_000
        assert int(cost_data["rowSum"]) == 500_000
        # ۴ ردیف خاص باید منطبق شده باشند
        assert len(cost_data["matched_rows_debug"]) == 4
        # فرمول: ۱٬۵۰۰٬۰۰۰ + ۵۰۰٬۰۰۰ + ۵۵۰٬۰۰۰ = ۲٬۵۵۰٬۰۰۰ (مضرب ۱۰k)
        assert int(cost_data["final_total"]) == 2_550_000
        return True
    assert _run(_with_page(scenario, popup_visible=False))
