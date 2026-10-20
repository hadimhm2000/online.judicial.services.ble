"""تست ورود همزمان هنگام ثبت کد امضا و کلیک باکس «اخذ امضاي الكترونيك» —
اجرا: BOT_TOKEN=1:x ADMIN_ID=1 ADMIN_API_SECRET=x python -m pytest test_sign_session_expired.py"""
import asyncio
import glob
import os
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("ADMIN_API_SECRET", "x")

import pytest

import ezhharnameh_sign_scenario as ess
import lavayeh_sign_handlers as lsh
import lavayeh_sign_scenario as lss

SWEET_ALERT = """<html><head><style>.sa-icon{display:none}</style></head><body>
<div class="sweet-alert showSweetAlert visible" style="display:block;">
<div class="sa-icon sa-error animateErrorIcon" style="display: block;"></div>
<div class="sa-icon sa-success" style="display: none;"></div>
<div class="sa-icon sa-warning" style="display: none;"></div>
<h2></h2><p style="display: block;">با این شناسه «2281365549»، در ساعت 15:32 ورود به سامانه در صفحه یا رایانه ای دیگر انجام شده و اعتبار ورود قبلی ( ساعت 15:06 ) منقضی شده است</p>
<button class="confirm">بستن</button></div></body></html>"""

SIGN_BOX_LATE = """<html><body><div id="root"></div><script>
window.clickedSign = false;
setTimeout(() => {
  document.getElementById('root').innerHTML =
    '<div class="box" id="b"><div class="heading"><h5 class="font-yekan ng-binding">اخذ امضاي الكترونيك</h5></div>' +
    '<div class="body"><p class="ng-binding">اين مرحله در دفاتر خدمات انجام مي شود.</p></div></div>';
  document.getElementById('b').addEventListener('click', () => { window.clickedSign = true; });
}, 2500);
</script></body></html>"""


def _chromium():
    for pattern in ("/opt/pw-browsers/chromium", "/opt/pw-browsers/chromium-*/chrome-linux/chrome"):
        found = sorted(glob.glob(pattern))
        if found and os.path.exists(found[-1]):
            return found[-1]
    return None


async def _with_page(html, fn):
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=_chromium())
        page = await browser.new_page()
        await page.set_content(html)
        try:
            return await fn(page)
        finally:
            await browser.close()


@pytest.mark.skipif(_chromium() is None, reason="chromium not available")
@pytest.mark.parametrize("mod", [lss, ess])
def test_concurrent_login_popup_on_submit_starts_relogin(monkeypatch, mod):
    # از PR #48: پس از پاپ‌آپ ورود همزمان، منتظر لاگین مجدد مدیر می‌ماند و
    # «session_expired_handled» برمی‌گرداند تا امضا دوباره کلیک شود.
    relogin = AsyncMock()
    monkeypatch.setattr(mod, "handle_session_expired", relogin)

    async def fn(page):
        return await mod._wait_for_sign_popup(page, MagicMock(), 42, timeout_sec=3)

    assert asyncio.run(_with_page(SWEET_ALERT, fn)) == "session_expired_handled"
    relogin.assert_awaited_once()


@pytest.mark.skipif(_chromium() is None, reason="chromium not available")
def test_sign_box_clicked_when_rendered_late():
    async def fn(page):
        ok = await lss._click_sign_box(page, wait_sec=8)
        return ok, await page.evaluate("window.clickedSign")

    assert asyncio.run(_with_page(SIGN_BOX_LATE, fn)) == (True, True)


def test_disrupted_message_and_retry_wait(monkeypatch):
    bot = MagicMock()
    bot.send_message = AsyncMock()
    state = MagicMock()
    state.set_state = AsyncMock()
    waiter = AsyncMock()
    monkeypatch.setattr(lsh, "_lavayeh_wrong_code_waiter", waiter)

    async def go():
        await lsh.on_lavayeh_sign_submit_failure(bot, 42, state, sana_disrupted=True)
        await asyncio.sleep(0)

    asyncio.run(go())
    text = bot.send_message.await_args.args[1]
    assert "اختلال" in text and "۲۰ دقیقه" in text
    state.set_state.assert_awaited_once()
    waiter.assert_called_once()
