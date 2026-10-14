"""تست بخش «درخواست گواهی عدم سوءپیشینه» (clearance_handlers / clearance_scenario) —
اجرا: BOT_TOKEN=1:x ADMIN_ID=1 ADMIN_API_SECRET=x python -m pytest test_clearance.py"""
import asyncio
import glob
import json
import os
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("ADMIN_API_SECRET", "x")

import pytest

import clearance_handlers as ch
import clearance_scenario as cs
import runtime_state
import wallet
from states import Form

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "test_fixtures", "sana_clearance_mock.html")


def run(coro):
    return asyncio.run(coro)


def _chromium():
    for pattern in ("/opt/pw-browsers/chromium", "/opt/pw-browsers/chromium-*/chrome-linux/chrome"):
        found = sorted(glob.glob(pattern))
        if found and os.path.exists(found[-1]):
            return found[-1]
    return None


def _bot():
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=1))
    return bot


def _texts(bot) -> str:
    return "\n".join(str(c.args[1]) if len(c.args) > 1 else str(c.kwargs.get("text"))
                     for c in bot.send_message.call_args_list)


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(ch, "STORE_FILE", str(tmp_path / "clearance.json"))
    ch._store = {}
    ch._loaded = True
    monkeypatch.setattr(wallet, "STORE_FILE", str(tmp_path / "wallet.json"))
    wallet._store = {"users": {}, "offers": {}, "holds": {}, "autopaid": {}}
    wallet._lock = asyncio.Lock()
    monkeypatch.setattr(ch, "_panel_update", AsyncMock())
    monkeypatch.setattr(ch, "_panel_register", AsyncMock())
    monkeypatch.setattr(ch, "_set_user_state", AsyncMock())
    q = asyncio.Queue()
    monkeypatch.setattr(runtime_state, "job_queue", q)
    cs._tabs.clear()
    cs._locks.clear()
    yield


def _new_request(uid=500, paid=True, status=ch.ST_QUEUED, **extra):
    rid = f"CLR{uid}"
    ch._store[rid] = {"rid": rid, "uid": uid, "full_name": "تست", "nid": "0012345679",
                      "birth": "1370/05/12", "desc": "ارائه به اداره", "status": status,
                      "paid": paid, "paid_toman": ch.FEE_TOMAN if paid else 0,
                      "created_at": time.time(), "updated_at": time.time(), **extra}
    return rid


# ── تشخیص پاپ‌آپ‌ها (متن دقیق سامانه) ─────────────────────────────────────

def test_classify_send_code_popups():
    assert cs.classify_send_code_popup("رمز موقت به شماره همراه ارسال شد") == cs.OK
    assert cs.classify_send_code_popup(
        "رمز موقت درخواست گواهی عدم سوء پیشینه طی 10 دقیقه گذشته ارسال شده است") == cs.OK
    assert cs.classify_send_code_popup("اطلاعاتی بااین شماره ملی وتاریخ تولد پیدا نشد.") == cs.WRONG_ID
    assert cs.classify_send_code_popup("اطلاعاتي بااين شماره ملي وتاريخ تولد پيدا نشد.") == cs.WRONG_ID
    assert cs.classify_send_code_popup("خطای داخلی سرور") == cs.FAILED
    assert cs.classify_send_code_popup("") == cs.FAILED


def test_classify_code_and_final_popups():
    assert cs.classify_code_popup("") == cs.OK
    assert cs.classify_code_popup("زمان اعتبار رمز موقت منقضی شده است. باید رمز جدید اخذ شود") == cs.CODE_EXPIRED
    assert cs.classify_code_popup("رمز وارد شده صحیح نیست") == cs.FAILED
    assert cs.is_search_success("بازیابی اطلاعات با موفقیت انجام شد.")
    assert cs.is_final_success("گواهی عدم سوءپیشینه توسط واحد مربوطه مورد بررسی قرار گرفت و در وضعیت "
                               "سابقه یابی خودکار می‌باشد، بعد از صدور ابلاغیه امکان دریافت نسخه‌ی چاپی آن وجود دارد.")
    assert not cs.is_final_success("هزینه پرداخت نشده است")


def test_code_expired_popup_is_not_concurrent_login():
    from browser_helpers import is_concurrent_login_text
    assert not is_concurrent_login_text("زمان اعتبار رمز موقت منقضی شده است. باید رمز جدید اخذ شود")
    assert is_concurrent_login_text(
        "با این شناسه «2281365549»، در ساعت 15:32 ورود به سامانه در صفحه یا رایانه ای دیگر انجام شده "
        "و اعتبار ورود قبلی ( ساعت 15:06 ) منقضی شده است")


def test_menu_has_clearance_button_and_states():
    import keyboards as kb
    rows = [[b.text for b in r] for r in kb.get_flow_type_kb(99).keyboard]
    assert [kb.CLEARANCE_MENU_TEXT] in rows
    # ⭐ جای «ابزار فایل» و «گواهی عدم سوءپیشینه» جابه‌جا شد
    assert rows.index([kb.CLEARANCE_MENU_TEXT]) < rows.index(["🔧 ابزار فایل"])
    assert Form.clr_waiting_code.state == "Form:clr_waiting_code"


def test_birth_and_nid_parsing():
    assert ch._parse_birth("۱۳۷۰/۵/۱۲") == "1370/05/12"
    assert ch._parse_birth("1370/5/12") == "1370/05/12"
    assert ch._parse_birth("12/05/1370") is None
    assert ch._parse_nid("0012345679") is None or len(ch._parse_nid("0012345679")) == 10
    assert ch._parse_nid("1111111111") is None


# ── نتیجهٔ فازها ──────────────────────────────────────────────────────────

def test_payment_starts_send_code_in_queue():
    rid = _new_request(paid=False, status=ch.ST_AWAIT_PAY)
    bot = _bot()
    run(ch._start_after_payment(bot, rid, paid_toman=150_000, exempt=False))
    req = ch.get_request(rid)
    assert req["paid"] and req["status"] == ch.ST_QUEUED
    job = runtime_state.job_queue.get_nowait()
    assert job == {"task_type": "CLEARANCE_SEND_CODE", "user_id": 500, "rid": rid}
    assert "رمز موقت" in _texts(bot)


def test_send_code_ok_asks_for_code_with_7_minutes():
    rid = _new_request(status=ch.ST_SENDING)
    bot = _bot()
    run(ch.on_send_code_result(bot, rid, cs.OK, "رمز موقت به شماره همراه ارسال شد"))
    assert ch.get_request(rid)["status"] == ch.ST_WAIT_CODE
    assert "7 دقیقه" in _texts(bot)
    ch._set_user_state.assert_awaited()
    assert ch._set_user_state.await_args.args[2] == Form.clr_waiting_code


def test_wrong_id_gives_45_minute_window_then_refunds_half():
    rid = _new_request(status=ch.ST_SENDING)
    bot = _bot()
    run(ch.on_send_code_result(bot, rid, cs.WRONG_ID, "اطلاعاتی بااین شماره ملی وتاریخ تولد پیدا نشد."))
    req = ch.get_request(rid)
    assert req["status"] == ch.ST_FIX
    assert 179 * 60 < req["fix_deadline"] - time.time() <= 180 * 60
    assert "کدملی و تاریخ تولد اشتباه است" in _texts(bot) and "۳ ساعت" in _texts(bot)

    # پایان مهلت → لغو + ۵۰٪ به کیف پول
    req["fix_deadline"] = time.time() - 1
    run(ch._tick(bot))
    assert ch.get_request(rid)["status"] == ch.ST_CANCELLED
    assert wallet.balance(500) == 75_000
    ch._panel_update.assert_awaited()
    assert ch._panel_update.await_args.kwargs["fee"] == 75_000


def test_fix_nid_and_birth_requeues_send_code():
    rid = _new_request(status=ch.ST_FIX, fix_deadline=time.time() + 600)
    state = MagicMock()
    state.get_data = AsyncMock(return_value={"clr_fix_nid": "0499370899"})
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    state.clear = AsyncMock()
    msg = MagicMock()
    msg.text = "1365/01/02"
    msg.from_user.id = 500
    msg.answer = AsyncMock()
    run(ch.clr_fix_birth(msg, state, _bot()))
    req = ch.get_request(rid)
    assert req["nid"] == "0499370899" and req["birth"] == "1365/01/02" and req["status"] == ch.ST_QUEUED
    assert runtime_state.job_queue.get_nowait()["task_type"] == "CLEARANCE_SEND_CODE"


def test_code_expired_resends_after_30_minutes():
    rid = _new_request(status=ch.ST_CHECK_CODE)
    bot = _bot()
    run(ch.on_code_result(bot, rid, cs.CODE_EXPIRED, "زمان اعتبار رمز موقت منقضی شده است"))
    req = ch.get_request(rid)
    assert req["status"] == ch.ST_RESEND and "30 دقیقه" in _texts(bot)
    run(ch._tick(bot))
    assert runtime_state.job_queue.empty()          # هنوز ۳۰ دقیقه نگذشته
    req["resend_at"] = time.time() - 1
    run(ch._tick(bot))
    assert runtime_state.job_queue.get_nowait()["task_type"] == "CLEARANCE_SEND_CODE"


def test_payment_id_goes_only_to_admin_with_paid_button():
    rid = _new_request(status=ch.ST_REGISTER)
    bot = _bot()
    run(ch.on_register_result(bot, rid, cs.OK, "140520260393634930"))
    calls = bot.send_message.call_args_list
    admin_calls = [c for c in calls if c.args[0] == ch.ADMIN_ID]
    user_calls = [c for c in calls if c.args[0] == 500]
    assert any("140520260393634930" in c.args[1] for c in admin_calls)
    assert not any("140520260393634930" in c.args[1] for c in user_calls)
    kb = admin_calls[-1].kwargs["reply_markup"]
    assert kb.inline_keyboard[0][0].callback_data == f"clr:paid:{rid}"

    # مدیر «پرداخت کردم» → تسک تایید نهایی در نوبت
    cb = MagicMock()
    cb.data = f"clr:paid:{rid}"
    cb.from_user = SimpleNamespace(id=ch.ADMIN_ID)
    cb.answer = AsyncMock()
    cb.message.text = "x"
    cb.message.edit_text = AsyncMock()
    run(ch.clr_admin_callback(cb, bot))
    job = runtime_state.job_queue.get_nowait()
    assert job["task_type"] == "CLEARANCE_FINALIZE" and job["admin_forced"]
    assert ch.get_request(rid)["status"] == ch.ST_FINALIZE

    # کاربر عادی نمی‌تواند دکمه را بزند
    cb.from_user = SimpleNamespace(id=12345)
    run(ch.clr_admin_callback(cb, bot))
    assert runtime_state.job_queue.empty()


def test_send_code_failure_offers_admin_retry():
    rid = _new_request(status=ch.ST_SENDING)
    bot = _bot()
    run(ch.on_send_code_result(bot, rid, cs.FAILED, "خطای داخلی سرور"))
    req = ch.get_request(rid)
    assert req["status"] == ch.ST_ERROR and req["failed_phase"] == "send_code"
    admin_call = [c for c in bot.send_message.call_args_list if c.args[0] == ch.ADMIN_ID][-1]
    assert admin_call.kwargs["reply_markup"].inline_keyboard[0][0].callback_data == f"clr:retry:{rid}"


def test_clearance_payment_payload_is_routed_without_state():
    import card_payment
    assert "clearance" in card_payment._PAYLOAD_ROUTED_TYPES
    assert "clearance" in wallet._PAYLOAD_ROUTED_TYPES
    msg = MagicMock()
    msg.successful_payment = SimpleNamespace(invoice_payload=json.dumps({"type": "clearance", "rid": "X"}))
    assert ch._is_clearance_payment(msg)
    msg.successful_payment = SimpleNamespace(invoice_payload=json.dumps({"type": "single_use"}))
    assert not ch._is_clearance_payment(msg)


# ── اجرای کامل روی صفحهٔ شبیه‌سازی‌شدهٔ سامانه ────────────────────────────

async def _with_browser(fn, query: str):
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=_chromium())
        ctx = await browser.new_context()
        old_ctx = runtime_state.browser_context
        runtime_state.browser_context = ctx
        old_url = cs.OFFICES_URL
        cs.OFFICES_URL = "file://" + FIXTURE + query
        try:
            return await fn()
        finally:
            cs.OFFICES_URL = old_url
            runtime_state.browser_context = old_ctx
            await browser.close()


@pytest.mark.skipif(_chromium() is None, reason="chromium not available")
def test_full_flow_on_mock_site(monkeypatch):
    rid = _new_request()
    req = ch.get_request(rid)
    bot = _bot()

    async def flow():
        kind, txt = await cs.send_code(rid, req, bot)
        assert kind == cs.OK, txt
        page = cs._tabs[rid]
        assert await page.evaluate("window.__stepRegisterClicked") is True
        assert await page.evaluate("window.__nid") == "0012345679"
        assert await page.evaluate("window.__birth") == "1370/05/12"
        kind, txt = await cs.submit_code(rid, req, "12345", bot)
        assert kind == cs.OK, txt
        assert await page.evaluate("window.__code") == "12345"
        kind, pay_id = await cs.register(rid, req, bot)
        assert kind == cs.OK and pay_id == "140520260393634930"
        assert await page.evaluate("window.__lastDesc") == "ارائه به اداره"
        kind, path = await cs.finalize(rid, req, bot)
        assert kind == cs.OK, path
        assert os.path.exists(path) and os.path.getsize(path) > 1024
        os.remove(path)
        calls = await page.evaluate("window.__calls")
        assert calls["search"] == 1 and calls["final"] == 1 and calls["print"] == 1

    run(_with_browser(flow, "?send=ok"))


@pytest.mark.skipif(_chromium() is None, reason="chromium not available")
def test_send_code_retries_once_and_handles_recent_and_wrong():
    rid = _new_request()
    req = ch.get_request(rid)
    bot = _bot()

    async def retry_then_ok():
        kind, _ = await cs.send_code(rid, req, bot)
        assert kind == cs.OK
        assert await cs._tabs[rid].evaluate("window.__calls.send") == 1  # تب جدید در تلاش دوم

    run(_with_browser(retry_then_ok, "?send=error_once"))

    async def recent():
        kind, txt = await cs.send_code(rid, req, bot)
        assert kind == cs.OK and "10 دقیقه" in txt

    run(_with_browser(recent, "?send=recent"))

    async def wrong():
        kind, txt = await cs.send_code(rid, req, bot)
        assert kind == cs.WRONG_ID and "پیدا نشد" in txt

    run(_with_browser(wrong, "?send=wrong"))


@pytest.mark.skipif(_chromium() is None, reason="chromium not available")
def test_concurrent_login_popup_alerts_admin_and_retries(monkeypatch):
    rid = _new_request()
    req = ch.get_request(rid)
    bot = _bot()

    async def fake_relogin(_bot, _uid, page=None, **_):
        await page.evaluate("closePopup()")

    relogin = AsyncMock(side_effect=fake_relogin)
    monkeypatch.setattr(cs, "handle_session_expired", relogin)

    async def flow():
        kind, txt = await cs.send_code(rid, req, bot)
        assert kind == cs.OK, txt
        relogin.assert_awaited_once()

    run(_with_browser(flow, "?send=concurrent_once"))


@pytest.mark.skipif(_chromium() is None, reason="chromium not available")
def test_code_expired_and_payment_id_via_calculate_button():
    rid = _new_request()
    req = ch.get_request(rid)
    bot = _bot()

    async def expired():
        assert (await cs.send_code(rid, req, bot))[0] == cs.OK
        kind, txt = await cs.submit_code(rid, req, "12345", bot)
        assert kind == cs.CODE_EXPIRED and "منقضی" in txt

    run(_with_browser(expired, "?code=expired"))

    async def calc_button():
        assert (await cs.send_code(rid, req, bot))[0] == cs.OK
        assert (await cs.submit_code(rid, req, "12345", bot))[0] == cs.OK
        kind, pay_id = await cs.register(rid, req, bot)
        assert kind == cs.OK and pay_id == "140520260393634930"
        assert await cs._tabs[rid].evaluate("window.__calls.calc") == 1

    run(_with_browser(calc_button, "?payid=calc_once"))
