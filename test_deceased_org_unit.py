"""تست خطای «فوت کرده است» و انتخاب «واحد زیر مجموعه شخص حقوقی» —
اجرا: BOT_TOKEN=1:x ADMIN_ID=1 ADMIN_API_SECRET=x python -m pytest test_deceased_org_unit.py"""
import asyncio
import datetime
import glob
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("ADMIN_API_SECRET", "x")

import pytest

import error_catalog
import nid_fix_window
import org_unit_picker
import runtime_state
import wallet

DECEASED_POPUP = "طبق اطلاعات ثبت احوال فلان  فلاني فوت کرده است و قابل انتخاب نمی باشد."
FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "test_fixtures", "sana_org_unit_modal.html")


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(wallet, "STORE_FILE", str(tmp_path / "wallet.json"))
    wallet._store = {"users": {}, "offers": {}}
    wallet._lock = asyncio.Lock()
    runtime_state.prepaid_registrations.clear()
    runtime_state.pending_nid_fix_windows.clear()
    yield
    runtime_state.prepaid_registrations.clear()
    runtime_state.pending_nid_fix_windows.clear()


# ── ۱) خطای «فوت کرده است» ─────────────────────────────────────────────

def test_deceased_popup_classified():
    assert error_catalog.is_deceased_error(DECEASED_POPUP)
    assert error_catalog.classify_sana_popup(DECEASED_POPUP) == "deceased"
    assert not error_catalog.is_deceased_error("تاریخ تولد ارسالی مربوط به شماره ملی 1234567890 اشتباه است")


def test_deceased_message_has_error_text_and_deadline():
    msg = nid_fix_window.deceased_message(DECEASED_POPUP)
    assert "فوت کرده است" in msg
    assert "کدملی جدید" in msg
    assert "45 دقیقه" in msg
    assert "۵۰ درصد" in msg


def _prepay(uid, paid_rial, credit_rial=0):
    runtime_state.prepaid_registrations[uid] = {
        "amount_rial": paid_rial + credit_rial,
        "amount_toman": (paid_rial + credit_rial) // 10,
        "prepay_paid_rial": paid_rial,
    }


def test_cancel_deceased_refunds_half_prepay_to_wallet():
    _prepay(7, 2_000_000)  # ۲۰۰,۰۰۰ تومان
    win = nid_fix_window.start_window(7, flow="check", task_data={}, error_text=DECEASED_POPUP,
                                      kind="deceased")
    line = run(nid_fix_window.settle_cancel(7, win))
    assert wallet.balance(7) == 100_000
    assert 7 not in runtime_state.prepaid_registrations
    assert "100,000" in line


def test_cancel_deceased_keeps_previous_credit():
    _prepay(8, 2_000_000, credit_rial=300_000)
    run(nid_fix_window.settle_cancel(8, {"kind": "deceased"}))
    assert wallet.balance(8) == 100_000
    assert runtime_state.prepaid_registrations[8]["amount_rial"] == 300_000
    assert runtime_state.prepaid_registrations[8]["prepay_paid_rial"] == 0


def test_cancel_other_errors_keep_old_behavior():
    _prepay(9, 2_000_000)
    line = run(nid_fix_window.settle_cancel(9, {"kind": "birthdate"}))
    assert wallet.balance(9) == 0
    assert runtime_state.prepaid_registrations[9]["amount_rial"] == 1_000_000
    assert "100,000" in line


def test_sweep_expired_deceased_and_normal_windows():
    _prepay(10, 2_000_000)
    _prepay(11, 2_000_000)
    past = datetime.datetime.now() - datetime.timedelta(minutes=1)
    for uid, kind in ((10, "deceased"), (11, "birthdate")):
        win = nid_fix_window.start_window(uid, flow="lavayeh", task_data={}, error_text="x", kind=kind)
        win["deadline"] = past
    bot = MagicMock()
    bot.send_message = AsyncMock()
    closed = run(nid_fix_window.sweep_expired(bot))
    assert closed == 2
    assert wallet.balance(10) == 100_000
    assert runtime_state.prepaid_registrations[11]["amount_rial"] == 1_000_000
    user_texts = [c.args[1] for c in bot.send_message.call_args_list if c.args[0] in (10, 11)]
    assert len(user_texts) == 2


# ── ۲) اجرای قابل جداشدن تسک اصلی ───────────────────────────────────────

def test_run_detachable_behaves_like_await():
    async def ok():
        return 5

    async def boom():
        raise ValueError("x")

    assert run(org_unit_picker.run_detachable(ok())) == 5
    with pytest.raises(ValueError):
        run(org_unit_picker.run_detachable(boom()))


def test_release_main_worker_swaps_tab(monkeypatch):
    async def scenario():
        old_page, new_page = MagicMock(name="old"), MagicMock(name="new")
        new_page.goto = AsyncMock()
        old_page.is_closed = MagicMock(return_value=False)
        old_page.close = AsyncMock()
        ctx = MagicMock()
        ctx.new_page = AsyncMock(return_value=new_page)
        monkeypatch.setattr(runtime_state, "browser_context", ctx, raising=False)
        monkeypatch.setattr(runtime_state, "sana_page", old_page, raising=False)
        gate = asyncio.Event()
        finished = asyncio.Event()

        async def task():
            await org_unit_picker.release_main_worker(old_page, MagicMock())
            await gate.wait()           # منتظر انتخاب کاربر
            finished.set()

        result = await asyncio.wait_for(org_unit_picker.run_detachable(task()), 5)
        assert result is None                       # حلقهٔ اصلی آزاد شد
        assert runtime_state.sana_page is new_page  # تسک‌های بعدی در تب جدید
        assert org_unit_picker.is_parked_page(old_page)
        gate.set()
        await asyncio.wait_for(finished.wait(), 5)
        await asyncio.sleep(0.1)
        old_page.close.assert_awaited()             # تب قبلی پس از پایان بسته شد
        assert not org_unit_picker.is_parked_page(old_page)

    run(scenario())


# ── ۳) انتخاب واحد روی HTML واقعی سامانه ثنا ───────────────────────────

def _chromium():
    for pat in ("/opt/pw-browsers/chromium-*/chrome-linux/chrome",):
        found = sorted(glob.glob(pat))
        if found:
            return found[-1]
    return None


def _callback(user_id, data):
    cb = MagicMock()
    cb.data = data
    cb.from_user = SimpleNamespace(id=user_id)
    cb.answer = AsyncMock()
    return cb


@pytest.mark.skipif(_chromium() is None, reason="chromium not available")
def test_org_unit_pick_nested_on_real_sana_html():
    from playwright.async_api import async_playwright

    async def scenario():
        async with async_playwright() as p:
            browser = await p.chromium.launch(executable_path=_chromium())
            page = await browser.new_page()
            await page.goto("file://" + FIXTURE)
            bot = MagicMock()
            bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=1))
            bot.edit_message_text = AsyncMock()
            org_unit_picker._choice_cache.clear()

            pick = asyncio.create_task(org_unit_picker.handle_if_present(
                page, bot, 42, company_id="10100000000", fatal_exc=RuntimeError))
            for _ in range(100):
                if org_unit_picker._sessions:
                    break
                await asyncio.sleep(0.1)
            sess = next(iter(org_unit_picker._sessions.values()))
            sid = sess["sid"]
            assert len(sess["items"]) == 31
            tehran = next(i for i, it in enumerate(sess["items"]) if it["expandable"])

            # کاربر دیگری نمی‌تواند انتخاب کند
            other = _callback(99, f"orgu:{sid}:i0")
            await org_unit_picker.org_unit_callback(other, bot)
            assert not sess["future"].done()

            await org_unit_picker.org_unit_callback(_callback(42, f"orgu:{sid}:i{tehran}"), bot)
            for _ in range(100):
                if sess["crumbs"] and not sess["busy"]:
                    break
                await asyncio.sleep(0.1)
            assert len(sess["items"]) == 19
            await org_unit_picker.org_unit_callback(_callback(42, f"orgu:{sid}:i1"), bot)
            assert await asyncio.wait_for(pick, 20) is True

            state = await org_unit_picker._field_state(page)
            assert state["title"] == "بانك كارگشايي مركز"
            assert state["code"] == "53"
            assert not await page.evaluate(org_unit_picker._JS_MODAL_OPEN)
            assert org_unit_picker._choice_cache[(42, "10100000000")][0][-1] == "بانك كارگشايي مركز"

            # تلاش مجدد همان تسک: انتخاب قبلی بدون پرسش دوباره درج می‌شود
            await page.reload()
            sent_before = bot.send_message.await_count
            assert await org_unit_picker.handle_if_present(
                page, bot, 42, company_id="10100000000", fatal_exc=RuntimeError) is True
            assert bot.send_message.await_count == sent_before
            assert (await org_unit_picker._field_state(page))["code"] == "53"
            await browser.close()

    run(scenario())


@pytest.mark.skipif(_chromium() is None, reason="chromium not available")
def test_org_unit_absent_field_is_noop():
    from playwright.async_api import async_playwright

    async def scenario():
        async with async_playwright() as p:
            browser = await p.chromium.launch(executable_path=_chromium())
            page = await browser.new_page()
            await page.set_content("<html><body><input id='x'></body></html>")
            assert await org_unit_picker.handle_if_present(page, MagicMock(), 1) is False
            await browser.close()

    run(scenario())
