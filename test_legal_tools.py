"""تست بخش «محاسبه دیه و ارث» منوی اصلی (legal_tools_handlers.py) —
اجرا: BOT_TOKEN=x ADMIN_ID=1 ADMIN_API_SECRET=x python -m pytest test_legal_tools.py"""
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("ADMIN_API_SECRET", "x")

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

import keyboards as kb
import legal_tools_handlers as lt
import runtime_state
import single_pay_handlers as sp
from states import Form

UID = 4242


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    runtime_state.user_free_usage.clear()
    runtime_state.user_subscriptions.clear()
    monkeypatch.setattr(lt, "send_document_direct", AsyncMock(return_value=True))


def _state():
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=UID, user_id=UID))


def _msg(text):
    m = MagicMock()
    m.text = text
    m.from_user.id = UID
    m.chat.id = UID
    m.message_id = 1
    m.answer = AsyncMock()
    m.edit_text = AsyncMock()
    return m


def _last_text(m):
    return m.answer.call_args_list[-1].args[0]


def run(coro):
    return asyncio.run(coro)


def test_menu_position_between_clearance_and_file_tools():
    rows = [[b.text for b in r] for r in kb.get_flow_type_kb(999).keyboard]
    i = rows.index([kb.LEGAL_MENU_TEXT])
    assert rows[i - 1] == [kb.CLEARANCE_MENU_TEXT]
    assert rows[i + 1] == ["🔧 ابزار فایل"]
    rows = [[b.text for b in r] for r in kb.flow_type_kb.keyboard]
    assert rows.index([kb.LEGAL_MENU_TEXT]) < rows.index(["🔧 ابزار فایل"])


def test_same_payment_rules_as_damages():
    assert runtime_state.SINGLE_USE_FEES["legal"] == runtime_state.SINGLE_USE_FEES["damages"]
    assert "legal" in sp.SERVICE_LABELS
    assert "دیه" in runtime_state.SUBSCRIPTION_FEATURES_TEXT


def test_diyeh_homicide_flow_counts_one_use_and_sends_pdf():
    async def scenario():
        state = _state()
        await lt.legal_menu_entry(_msg(kb.LEGAL_MENU_TEXT), state)
        assert await state.get_state() == lt.LegalForm.menu.state
        await lt.legal_menu_choice(_msg(lt.DIYEH_TEXT), state)
        assert await state.get_state() == lt.LegalForm.dy_year.state
        await lt.dy_year(_msg("1405"), state)
        await lt.dy_method(_msg(lt.DY_METHOD_BUTTONS[lt.dyc.METHOD_HOMICIDE]), state)
        await lt.dy_sex(_msg("👩 زن"), state)
        m = _msg(lt.NO)
        await lt.dy_holy(m, state)
        assert any("10,500,000,000" in str(c.args[0]) or "۱۰٬۵۰۰" in str(c.args[0])
                   or "10,500" in str(c.args[0]) for c in m.answer.call_args_list)
        assert lt.send_document_direct.await_count == 1
        assert runtime_state.get_user_usage(UID)["legal"] == 1
        assert await state.get_state() == lt.LegalForm.dy_method.state
    run(scenario())


def test_inheritance_flow_with_board_callbacks():
    async def scenario():
        state = _state()
        await lt.legal_menu_choice(_msg(lt.INHERITANCE_TEXT), state)
        await lt.inh_marital(_msg("👨 متوفی مرد بود و همسر داشت"), state)
        await lt.inh_wives(_msg("۱"), state)
        assert await state.get_state() == lt.LegalForm.inh_board.state
        for data in ("inh:inc:pesar", "inh:inc:dokhtar", "inh:next"):
            cb = MagicMock()
            cb.data = data
            cb.answer = AsyncMock()
            cb.message = _msg("")
            await lt.inh_callback(cb, state)
        assert await state.get_state() == lt.LegalForm.inh_estate.state
        m = _msg("240000000")
        await lt.inh_estate(m, state)
        text = "\n".join(str(c.args[0]) for c in m.answer.call_args_list)
        assert "همسر" in text or "زوجه" in text
        assert lt.send_document_direct.await_count == 1
        assert runtime_state.get_user_usage(UID)["legal"] == 1
    run(scenario())


def test_after_two_free_uses_offers_subscription_or_single(monkeypatch):
    async def scenario():
        runtime_state.increment_usage(UID, "legal")
        runtime_state.increment_usage(UID, "legal")
        # سهمیهٔ خسارت تأخیر/مهریه جداست
        assert runtime_state.can_use_service(UID, "damages")
        state = _state()
        m = _msg(kb.LEGAL_MENU_TEXT)
        await lt.legal_menu_entry(m, state)
        assert await state.get_state() == Form.single_pay_choice.state
        assert (await state.get_data())["single_pay_service"] == "legal"
        assert "۴۵,۰۰۰" in _last_text(m) or "45,000" in _last_text(m)

        # پرداخت تکی → یک اعتبار و ورود مستقیم به همین بخش
        pay = _msg("")
        await sp.single_use_successful_payment(pay, state, MagicMock(), {"type": "single_use", "svc": "legal"})
        assert runtime_state.get_single_use_credits(UID, "legal") == 1
        assert await state.get_state() == lt.LegalForm.menu.state
        await lt.legal_menu_choice(_msg(lt.DIYEH_TEXT), state)
        await lt.dy_year(_msg("1405"), state)
        await lt.dy_method(_msg(lt.DY_METHOD_BUTTONS[lt.dyc.METHOD_PERCENT]), state)
        await lt.dy_value(_msg("2.5"), state)
        assert runtime_state.get_single_use_credits(UID, "legal") == 0
        assert not runtime_state.can_use_service(UID, "legal")
    run(scenario())


def test_back_and_main_menu():
    async def scenario():
        state = _state()
        await lt.legal_menu_choice(_msg(lt.DIYEH_TEXT), state)
        await lt.dy_year(_msg(lt.BACK_TEXT), state)
        assert await state.get_state() == lt.LegalForm.menu.state
        await lt.legal_menu_choice(_msg(kb.BACK_TO_MAIN_TEXT), state)
        assert await state.get_state() == Form.waiting_for_flow_type.state
    run(scenario())


def test_diyeh_rate_file_outside_git(tmp_path, monkeypatch):
    monkeypatch.setattr(lt.dyc, "RATES_FILE", str(tmp_path / "diyeh_rates.json"))
    lt.dyc.set_full_diyeh(1406, 27_000_000_000)
    assert lt.dyc.full_diyeh(1406) == 27_000_000_000
    assert lt.dyc.DATA_FILE.endswith(os.path.join("data", "diyeh_data.json"))
