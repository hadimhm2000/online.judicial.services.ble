"""تست تشخیص صفحهٔ چاپِ «ورود در صفحه یا رایانه‌ای دیگر … منقضی شده» پیش از گرفتن PDF —
اجرا: BOT_TOKEN=1:x ADMIN_ID=1 ADMIN_API_SECRET=x python -m pytest test_print_session_expired.py"""
import asyncio
import glob
import os
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("ADMIN_API_SECRET", "x")

import pytest

import browser_helpers as bh
import runtime_state

EXPIRED_PRINT_HTML = """<html><head><title>چاپ دادخواست</title></head>
<body style="font-family: Nazanin,Tahoma; font-size: 15px;">
<form method="post" action="./PetitionPrint.aspx?petitionNo=1405220984016986" id="frmJSSPetition">
<div class="aspNetHidden"><input type="hidden" name="__VIEWSTATE" value="x"></div>
<div style="padding:10px;background:#fed1d1;color:#821717;">با این شناسه «2281365549»، در ساعت 19:31 ورود به سامانه در صفحه یا رایانه ای دیگر انجام شده و اعتبار ورود قبلی ( ساعت 19:28 ) منقضی شده است</div>
</form></body></html>"""

EXPIRED_TEXT = ("با این شناسه «2281365549»، در ساعت 19:31 ورود به سامانه در صفحه یا رایانه ای دیگر "
                "انجام شده و اعتبار ورود قبلی ( ساعت 19:28 ) منقضی شده است")


def test_detects_expired_notice_text():
    assert bh.is_print_session_expired_text(EXPIRED_TEXT)
    # املای عربی ی/ک
    assert bh.is_print_session_expired_text(EXPIRED_TEXT.replace("ی", "ي"))


def test_real_document_is_not_flagged():
    # سند واقعی طولانی که به‌طور اتفاقی همین عبارت‌ها را دارد نباید غلط‌مثبت شود
    doc = "متن دادخواست خواهان. " * 80 + EXPIRED_TEXT
    assert not bh.is_print_session_expired_text(doc)
    assert not bh.is_print_session_expired_text("چاپ دادخواست — اعتبار ورود")
    assert not bh.is_print_session_expired_text("")


def _chromium():
    for pattern in ("/opt/pw-browsers/chromium", "/opt/pw-browsers/chromium-*/chrome-linux/chrome"):
        found = sorted(glob.glob(pattern))
        if found and os.path.exists(found[-1]):
            return found[-1]
    return None


@pytest.mark.skipif(_chromium() is None, reason="chromium not available")
def test_check_and_handle_expiry_closes_print_page_and_relogs(monkeypatch):
    relogin = AsyncMock()
    monkeypatch.setattr(bh, "handle_session_expired", relogin)

    async def go():
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(executable_path=_chromium())
            ctx = await browser.new_context()
            main = await ctx.new_page()
            monkeypatch.setattr(runtime_state, "sana_page", main)
            print_page = await ctx.new_page()
            await print_page.set_content(EXPIRED_PRINT_HTML)
            expired = await bh.check_and_handle_expiry(print_page, MagicMock(), 42, check_body_text=False)
            closed = print_page.is_closed()

            # صفحهٔ چاپ سالم نباید تشخیص داده شود
            ok_page = await ctx.new_page()
            await ok_page.set_content("<html><body>" + "متن کامل سند حقوقی. " * 60 + "</body></html>")
            ok_expired = await bh.check_and_handle_expiry(ok_page, MagicMock(), 42, check_body_text=False)
            await browser.close()
            return expired, closed, ok_expired

    expired, closed, ok_expired = asyncio.run(go())
    assert expired is True
    assert closed is True
    relogin.assert_awaited_once()
    assert ok_expired is False
