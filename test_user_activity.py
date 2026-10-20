"""تست بازگشت خودکار به منوی اصلی پس از بی‌کاری (user_activity) —
اجرا: BOT_TOKEN=1:x ADMIN_ID=1 ADMIN_API_SECRET=x python -m pytest test_user_activity.py"""
import asyncio
import os
import time
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("ADMIN_API_SECRET", "x")

import pytest
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

import bot_settings
import runtime_state
import user_activity
from states import Form

UID = 4242


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    user_activity._last_activity.clear()
    monkeypatch.setattr(bot_settings, "_values", {})
    for name in user_activity._BUSY_STORE_NAMES:
        store = getattr(runtime_state, name, None)
        if hasattr(store, "clear"):
            store.clear()
    dp = MagicMock()
    dp.storage = MemoryStorage()
    monkeypatch.setattr(runtime_state, "dp", dp, raising=False)
    yield


def _bot():
    bot = MagicMock()
    bot.id = 1
    bot.send_message = AsyncMock()
    return bot


def _key(bot):
    return StorageKey(bot_id=bot.id, chat_id=UID, user_id=UID)


def _idle(minutes):
    user_activity._last_activity[UID] = time.monotonic() - minutes * 60


def _run(bot, state, data=None):
    async def go():
        storage = runtime_state.dp.storage
        await storage.set_state(_key(bot), state)
        await storage.set_data(_key(bot), data or {})
        await user_activity.sweep_inactive_users(bot)
        return await storage.get_state(_key(bot)), await storage.get_data(_key(bot))
    return asyncio.run(go())


def test_idle_user_returned_to_main_menu_with_message():
    bot = _bot()
    _idle(61)
    st, data = _run(bot, Form.main_menu.state, {"cart": [1]})
    assert st == Form.waiting_for_flow_type.state
    assert data == {}
    bot.send_message.assert_awaited_once()
    assert "عدم فعالیت" in bot.send_message.await_args.args[1]


def test_not_yet_idle_untouched():
    bot = _bot()
    _idle(59)
    st, _ = _run(bot, Form.main_menu.state)
    assert st == Form.main_menu.state
    bot.send_message.assert_not_awaited()


def test_already_on_main_menu_gets_no_message():
    bot = _bot()
    _idle(120)
    st, _ = _run(bot, Form.waiting_for_flow_type.state)
    assert st == Form.waiting_for_flow_type.state
    bot.send_message.assert_not_awaited()


def test_payment_wait_state_kept():
    bot = _bot()
    _idle(120)
    st, _ = _run(bot, Form.waiting_for_payment_receipt.state)
    assert st == Form.waiting_for_payment_receipt.state
    bot.send_message.assert_not_awaited()


def test_busy_user_kept():
    bot = _bot()
    _idle(120)
    runtime_state.active_lavayeh_users.add(UID)
    st, _ = _run(bot, Form.main_menu.state)
    assert st == Form.main_menu.state
    bot.send_message.assert_not_awaited()


def test_minutes_and_notify_from_panel(monkeypatch):
    bot = _bot()
    monkeypatch.setattr(bot_settings, "_values", {"inactivity.minutes": "10", "inactivity.notify": "false"})
    _idle(11)
    st, _ = _run(bot, Form.main_menu.state)
    assert st == Form.waiting_for_flow_type.state
    bot.send_message.assert_not_awaited()


def test_custom_text(monkeypatch):
    bot = _bot()
    monkeypatch.setattr(bot_settings, "_values", {"inactivity.text": "برگشتید"})
    _idle(61)
    _run(bot, Form.main_menu.state)
    assert bot.send_message.await_args.args[1].startswith("برگشتید")


def test_send_failure_still_resets():
    bot = _bot()
    bot.send_message = AsyncMock(side_effect=RuntimeError("blocked"))
    _idle(61)
    st, _ = _run(bot, Form.main_menu.state)
    assert st == Form.waiting_for_flow_type.state
