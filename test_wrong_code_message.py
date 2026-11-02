"""تست ۱۴۰۵/۰۸ — دستور کارفرما: پاپ‌آپ «رمز موقت نادرست» همیشه باید به کاربر
اعلام شود که *کد امضا اشتباه است* و روند امضا ۲۰ دقیقه بعد مجدداً فعال می‌شود؛
حتی اگر پیش از آن لاگین مجدد مدیر (ورود همزمان) انجام شده باشد.
قبلاً در همین حالت به‌اشتباه «sana_session_expired» (اختلال/لاگین مجدد) برگردانده
می‌شد. اجرا: BOT_TOKEN=x ADMIN_ID=1 ADMIN_API_SECRET=x python -m pytest test_wrong_code_message.py"""
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("ADMIN_API_SECRET", "x")

import ezhharnameh_sign_scenario as ess
import lavayeh_sign_handlers as lsh
import lavayeh_sign_scenario as lss


class _FakePage:
    """صفحهٔ ساختگی — evaluate برای پر کردن کد/کلیک دکمه True برمی‌گرداند."""

    async def evaluate(self, *args, **kwargs):
        return True


def _bot():
    bot = MagicMock()
    bot.send_message = AsyncMock()
    return bot


def _patch_popups(monkeypatch, mod, sequence):
    """_wait_for_sign_popup به‌ترتیب مقادیر sequence برمی‌گرداند."""
    calls = {"i": 0}

    async def fake_popup(page, bot=None, user_id=None, timeout_sec=55):
        idx = min(calls["i"], len(sequence) - 1)
        calls["i"] += 1
        return sequence[idx]

    async def fake_close(page):
        return True

    monkeypatch.setattr(mod, "_wait_for_sign_popup", fake_popup)
    monkeypatch.setattr(mod, "_close_any_popup", fake_close)
    return calls


def test_lavayeh_wrong_code_after_relogin_reports_wrong_code(monkeypatch):
    """لایحه: پس از لاگین مجدد مدیر، «رمز موقت نادرست» → wrong_code (نه نشست)."""
    monkeypatch.setattr(lss, "active_sign_page", lambda: _FakePage())
    # ۱) ورود همزمان → لاگین مجدد مدیر  ۲) کد اشتباه
    _patch_popups(monkeypatch, lss, ["session_expired_handled", "wrong_code"])

    result = asyncio.run(lss.submit_sign_code_for_person(_bot(), 42, 0, "12345"))
    assert result == {"success": False, "error": "wrong_code"}


def test_lavayeh_wrong_code_without_relogin_reports_wrong_code(monkeypatch):
    """لایحه: بدون لاگین مجدد هم «رمز موقت نادرست» → wrong_code."""
    monkeypatch.setattr(lss, "active_sign_page", lambda: _FakePage())
    _patch_popups(monkeypatch, lss, ["wrong_code"])

    result = asyncio.run(lss.submit_sign_code_for_person(_bot(), 42, 0, "0000"))
    assert result == {"success": False, "error": "wrong_code"}


def test_ezhhar_wrong_code_after_relogin_reports_wrong_code(monkeypatch):
    """اظهارنامه: پس از لاگین مجدد مدیر، «رمز موقت نادرست» → wrong_code (نه نشست)."""
    _patch_popups(monkeypatch, ess, ["session_expired_handled", "wrong_code"])

    result = asyncio.run(ess._enter_code_and_sign(_FakePage(), 0, "12345", _bot(), 42))
    assert result == {"success": False, "error": "wrong_code"}


def test_ezhhar_wrong_code_without_relogin_reports_wrong_code(monkeypatch):
    """اظهارنامه: بدون لاگین مجدد هم «رمز موقت نادرست» → wrong_code."""
    _patch_popups(monkeypatch, ess, ["wrong_code"])

    result = asyncio.run(ess._enter_code_and_sign(_FakePage(), 0, "0000", _bot(), 42))
    assert result == {"success": False, "error": "wrong_code"}


def test_wrong_code_message_tells_user_20_minutes():
    """پیام «رمز موقت اشتباه» باید اعلام کند روند امضا ۲۰ دقیقه بعد فعال می‌شود."""
    import inspect
    src = inspect.getsource(lsh.on_lavayeh_sign_wrong_code)
    assert "رمز موقت اشتباه" in src
    assert "۲۰ دقیقه" in src


def test_sign_failure_texts_point_to_pending_cases():
    """پیام‌های امضای ناموفق: بدون ارجاع به پشتیبان + معرفی «پرونده‌های در انتظار»."""
    for text in (lsh.SIGN_FAILED_RETRY_TEXT, lsh.SIGN_SANA_DISRUPTED_TEXT,
                 lsh.SIGN_PENDING_CASES_GUIDE):
        assert "پرونده‌های در انتظار" in text
        assert "کد رهگیری" in text
        assert "09306186888" not in text
        assert "واتساپ" not in text
    # جملهٔ فعال‌شدن مجدد ۲۰ دقیقه بعد هم حفظ شده است
    assert "۲۰ دقیقه" in lsh.SIGN_FAILED_RETRY_TEXT
    assert "۲۰ دقیقه" in lsh.SIGN_SANA_DISRUPTED_TEXT
