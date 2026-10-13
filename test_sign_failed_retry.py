"""تست ۱۴۰۵/۰۷: امضای ناموفق → ۲۰ دقیقه بعد درخواست امضای مجدد.
اجرا: BOT_TOKEN=x ADMIN_ID=1 ADMIN_API_SECRET=x python -m pytest test_sign_failed_retry.py"""
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("ADMIN_API_SECRET", "x")

import pytest

import lavayeh_sign_handlers as lsh
import runtime_state
import tajdid_nazar_handlers as tnh
from states import Form

UID = 4242


def _bot():
    bot = MagicMock()
    bot.send_message = AsyncMock()
    return bot


def _state():
    st = MagicMock()
    st.set_state = AsyncMock()
    st.clear = AsyncMock()
    return st


@pytest.mark.parametrize("handler, store, waiter, wait_state", [
    ("on_lavayeh_sign_submit_failure", "pending_lavayeh_sign", "_lavayeh_wrong_code_waiter", Form.lavayeh_sign_wrong_code_wait),
    ("on_lavayeh_sign_code_sent_failure", "pending_lavayeh_sign", "_lavayeh_wrong_code_waiter", Form.lavayeh_sign_wrong_code_wait),
    ("on_ezhhar_sign_submit_failure", "pending_ezhhar_sign", "_ezhhar_wrong_code_waiter", Form.ezhhar_sign_wrong_code_wait),
    ("on_ezhhar_sign_code_sent_failure", "pending_ezhhar_sign", "_ezhhar_wrong_code_waiter", Form.ezhhar_sign_wrong_code_wait),
])
def test_lavayeh_ezhhar_failure_waits_20min(monkeypatch, handler, store, waiter, wait_state):
    started = []
    monkeypatch.setattr(lsh, waiter, lambda bot, uid, st: started.append(uid) or asyncio.sleep(0))
    getattr(runtime_state, store)[UID] = {"tracking_code": "1"}
    bot, st = _bot(), _state()
    try:
        asyncio.run(getattr(lsh, handler)(bot, UID, st))
    finally:
        getattr(runtime_state, store).pop(UID, None)
    assert bot.send_message.await_args.args[1] == lsh.SIGN_FAILED_RETRY_TEXT
    st.set_state.assert_awaited_with(wait_state)
    assert started == [UID]


@pytest.mark.parametrize("handler", ["on_tn_sign_submit_failure", "on_tn_sign_code_sent_failure"])
def test_tn_failure_waits_20min(monkeypatch, handler):
    started = []
    monkeypatch.setattr(tnh, "_tn_wrong_code_waiter", lambda bot, uid, st: started.append(uid) or asyncio.sleep(0))
    runtime_state.pending_tn_sign[UID] = {"tracking_code": "1"}
    bot, st = _bot(), _state()
    try:
        asyncio.run(getattr(tnh, handler)(bot, UID, st))
    finally:
        runtime_state.pending_tn_sign.pop(UID, None)
    assert "۲۰ دقیقه" in bot.send_message.await_args.args[1]
    st.set_state.assert_awaited_with(Form.tn_sign_wrong_code_wait)
    assert started == [UID]
