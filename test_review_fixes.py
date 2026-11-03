"""تست اصلاحات بازبینی ۱۴۰۵/۰۸/۱۲:
  - کیف پول: فاکتور reg_prepay فقط در همان state زمان صدور قابل پرداخت است
  - credit_orphan_prepay_payment: ثبت اعتبار بدون پاک کردن state

اجرا: BOT_TOKEN=1:x ADMIN_ID=1 ADMIN_API_SECRET=x python -m pytest test_review_fixes.py
"""
import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("ADMIN_API_SECRET", "x")

import runtime_state
import wallet


def test_wallet_reg_prepay_requires_state():
    assert "reg_prepay" in wallet._PAYLOAD_ROUTED_TYPES
    assert "reg_prepay" not in wallet._STATE_CHECK_EXEMPT
    assert "admin_fee" in wallet._STATE_CHECK_EXEMPT


async def test_credit_orphan_prepay_keeps_state_and_credits(monkeypatch):
    import prepay_registration
    runtime_state.prepaid_registrations.pop(99, None)
    msg = SimpleNamespace(
        from_user=SimpleNamespace(id=99),
        successful_payment=SimpleNamespace(total_amount=1_000_000,
                                           telegram_payment_charge_id="CARD-x"),
        answer=AsyncMock())
    bot = SimpleNamespace(send_message=AsyncMock())
    await prepay_registration.credit_orphan_prepay_payment(msg, bot, "lavayeh")
    rec = runtime_state.prepaid_registrations.pop(99)
    assert rec["amount_rial"] == 1_000_000
    assert rec["service"] == "lavayeh"
    msg.answer.assert_awaited()
    bot.send_message.assert_awaited()


async def test_aasar_notice_back_without_images_returns_to_notice_no():
    """«🔙 بازگشت» در مرحلهٔ تصویر ابلاغیه بدون هیچ تصویری → بازگشت به شماره
    ابلاغیه (قبلاً کاربر در حلقهٔ «ارسال تصویر» گیر می‌کرد)."""
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.storage.base import StorageKey
    from aiogram.fsm.storage.memory import MemoryStorage
    import check_handlers
    from states import Form

    storage = MemoryStorage()
    state = FSMContext(storage, StorageKey(bot_id=1, chat_id=5, user_id=5))
    await state.set_state(Form.check_aasar_notice_more)
    await state.update_data(check_aasar_notice_images=[])
    msg = SimpleNamespace(text="🔙 بازگشت", photo=None, answer=AsyncMock())
    await check_handlers.check_aasar_notice_more_handler(msg, state)
    assert await state.get_state() == Form.check_aasar_notice_no.state

    # با یک تصویر: فقط تصویر آخر حذف و دوباره تصویر خواسته می‌شود
    await state.set_state(Form.check_aasar_notice_more)
    await state.update_data(check_aasar_notice_images=["f1"])
    await check_handlers.check_aasar_notice_more_handler(msg, state)
    assert await state.get_state() == Form.check_aasar_notice_image.state
    assert (await state.get_data())["check_aasar_notice_images"] == []
