"""تست پویا پیدا کردن سطر «شماره پرونده استنادي» در مرحلهٔ «دلايل» — اجرا:
BOT_TOKEN=1:x ADMIN_ID=1 ADMIN_API_SECRET=x python -m pytest test_aasar_refered_case.py

⭐ باگ رفع‌شده: قبلاً تیک #chk3 و درج شماره پرونده در #ReferedCaseNo3
هاردکد بود؛ اما ایندکس سطر «شماره پرونده استنادي» در جدول «تحقیقات و
اقدامات مورد تقاضا» بسته به نوع دادخواست متفاوت است (در عناوین اعسار
#chk4/#ReferedCaseNo4 — طبق لاگ/HTML ارسالی کارفرما: «درج شماره پرونده در
#ReferedCaseNo3 ناموفق»). حالا سطر از روی متن عنوان به‌صورت پویا پیدا
می‌شود، تیک چک‌باکس همان سطر زده و شماره در فیلد ReferedCaseNo همان سطر
درج می‌گردد.
"""
import asyncio
import glob
import os

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("ADMIN_API_SECRET", "x")

from pathlib import Path

import check_scenario

FIXTURE = Path(__file__).parent / "test_fixtures" / "sana_dalael_aasar.html"
CASE_NO = "140547420000463695"


def _run(coro):
    return asyncio.run(coro)


def _chromium():
    """مسیر کرومِ محیط اجرا (مثل سایر تست‌های مرورگری پروژه)."""
    for pattern in ("/opt/pw-browsers/chromium",
                    "/opt/pw-browsers/chromium-*/chrome-linux/chrome"):
        found = sorted(glob.glob(pattern))
        if found and os.path.exists(found[-1]):
            return found[-1]
    return None


async def _with_page(fn):
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        exe = _chromium()
        browser = await p.chromium.launch(
            headless=True, executable_path=exe) if exe \
            else await p.chromium.launch(headless=True)
        try:
            ctx = await browser.new_context()
            page = await ctx.new_page()
            await page.goto(FIXTURE.as_uri())
            return await fn(page)
        finally:
            await browser.close()


def test_finds_row_by_label_ticks_and_fills():
    """سطر «شماره پرونده استنادي» با ایندکس ۴ (chk4/ReferedCaseNo4) — عناوین اعسار."""
    async def scenario(page):
        res = await check_scenario._fill_aasar_refered_case_no(page, CASE_NO)
        assert res["ok"] is True
        assert res["chk_id"] == "chk4"
        assert res["input_id"] == "ReferedCaseNo4"
        # تیک واقعاً خورده و مقدار واقعاً در فیلد مانده است
        assert await page.eval_on_selector("#chk4", "el => el.checked") is True
        assert await page.eval_on_selector(
            "#ReferedCaseNo4", "el => el.value") == CASE_NO
        # تیک هیچ سطر دیگری نخورده است
        for i in range(4):
            assert await page.eval_on_selector(f"#chk{i}", "el => el.checked") is False
        return True
    assert _run(_with_page(scenario))


def test_works_when_row_index_is_3():
    """عناوین دیگر — سطر «شماره پرونده استنادي» ایندکس ۳ (chk3/ReferedCaseNo3)."""
    async def scenario(page):
        await page.evaluate('''() => {
            // سطر «تحقيقات محلي» (chk3 اصلی) حذف می‌شود
            const rows = Array.from(document.querySelectorAll('tr'));
            const mohali = rows.find(
                r => r.textContent.indexOf('محلي') !== -1);
            if (mohali) mohali.remove();
            // سطر «شماره پرونده استنادي» به ایندکس ۳ تغییر می‌کند
            const lbl4 = document.querySelector('label[for="chk4"]');
            const tr = lbl4.closest('tr');
            const chk = tr.querySelector('input#chk4');
            chk.id = 'chk3'; chk.setAttribute('name', 'chk3');
            lbl4.setAttribute('for', 'chk3');
            const inp = tr.querySelector('input#ReferedCaseNo4');
            inp.id = 'ReferedCaseNo3';
            inp.setAttribute('name', 'ReferedCaseNo3');
        }''')
        res = await check_scenario._fill_aasar_refered_case_no(page, CASE_NO)
        assert res["ok"] is True
        assert res["chk_id"] == "chk3"
        assert res["input_id"] == "ReferedCaseNo3"
        assert await page.eval_on_selector(
            "#ReferedCaseNo3", "el => el.value") == CASE_NO
        return True
    assert _run(_with_page(scenario))


def test_fallback_when_label_text_changes():
    """فال‌بک — اگر متن عنوان فرق کند، سطر از روی فیلد ReferedCaseNo پیدا می‌شود."""
    async def scenario(page):
        await page.evaluate('''() => {
            const lbl = document.querySelector('label[for="chk4"]');
            lbl.textContent = 'عنوان متفاوت';
        }''')
        res = await check_scenario._fill_aasar_refered_case_no(page, CASE_NO)
        assert res["ok"] is True
        assert res["input_id"] == "ReferedCaseNo4"
        return True
    assert _run(_with_page(scenario))


def test_row_not_found():
    """بدون سطر «شماره پرونده استنادي» → شکست کنترل‌شده با reason مشخص."""
    async def scenario(page):
        await page.evaluate('''() => {
            const lbl = document.querySelector('label[for="chk4"]');
            lbl.closest('tr').remove();
        }''')
        res = await check_scenario._fill_aasar_refered_case_no(page, CASE_NO)
        assert res["ok"] is False
        assert res["reason"] == "row_not_found"
        return True
    assert _run(_with_page(scenario))
