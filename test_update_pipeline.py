"""تست update_pipeline — سریال‌سازی آپدیت‌های هر کاربر + لاگ کندی‌ها (۱۴۰۵/۰۸).

مهم‌ترین سناریوها:
  ۱) دو آپدیت هم‌زمانِ یک کاربر، به ترتیب و پشت‌سرهم پردازش می‌شوند.
  ۲) بازپخش مصنوعی (dp.feed_update درون هندلر — الگوی wallet/card_payment)
     برای همان کاربر، بدون بن‌بست عبور می‌کند (re-entrant).
  ۳) کاربران مختلف مانع هم نمی‌شوند (موازی می‌مانند).
"""
import asyncio
import datetime

import pytest

import update_pipeline
from update_pipeline import SlowUpdateLogMiddleware, UserSerialMiddleware


def _make_update(uid: int, update_id: int, text: str = "hi"):
    from aiogram.types import Chat, Message, Update, User

    msg = Message(
        message_id=update_id,
        date=datetime.datetime.now(datetime.timezone.utc),
        chat=Chat(id=uid, type="private"),
        from_user=User(id=uid, is_bot=False, first_name="u"),
        text=text,
    )
    return Update(update_id=update_id, message=msg)


@pytest.mark.asyncio
async def test_same_user_updates_run_in_order():
    """دو آپدیت یک کاربر که هم‌زمان می‌رسند → ترتیب حفظ می‌شود."""
    mw = UserSerialMiddleware()
    order = []

    async def handler_1(event, data):
        order.append("start-1")
        await asyncio.sleep(0.05)   # اگر سریال نباشد، آپدیت ۲ وسط این می‌آید
        order.append("end-1")
        return 1

    async def handler_2(event, data):
        order.append("start-2")
        order.append("end-2")
        return 2

    u1, u2 = _make_update(10, 1), _make_update(10, 2)
    await asyncio.gather(
        mw(handler_1, u1, {}),
        mw(handler_2, u2, {}),
    )
    assert order == ["start-1", "end-1", "start-2", "end-2"]


@pytest.mark.asyncio
async def test_different_users_run_in_parallel():
    """کاربران مختلف منتظر هم نمی‌مانند."""
    mw = UserSerialMiddleware()
    both_inside = asyncio.Event()

    async def slow(event, data):
        # تا وقتی کاربر دوم هم وارد شده، منتظر می‌ماند (حداکثر ۲ ثانیه)
        try:
            await asyncio.wait_for(both_inside.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            pass
        return "a"

    async def fast(event, data):
        both_inside.set()
        return "b"

    r = await asyncio.gather(
        mw(slow, _make_update(10, 1), {}),
        mw(fast, _make_update(20, 2), {}),
    )
    assert r == ["a", "b"]   # fast داخلِ slow اجرا شده → موازی بودند


@pytest.mark.asyncio
async def test_reentrant_replay_does_not_deadlock():
    """بازپخش مصنوعی برای همان کاربر درون همان تسک (الگوی wallet/CARD-) →
    بدون قفل دوباره عبور می‌کند و بن‌بست نمی‌سازد."""
    mw = UserSerialMiddleware()
    inner_ran = []

    async def inner_handler(event, data):
        inner_ran.append(event.update_id)
        return "inner"

    async def outer_handler(event, data):
        # هندلر جاری (کاربر ۱۰) یک آپدیت مصنوعی برای «همان کاربر» بازپخش می‌کند
        await mw(inner_handler, _make_update(10, 99), {})
        return "outer"

    res = await asyncio.wait_for(mw(outer_handler, _make_update(10, 1), {}), timeout=3)
    assert res == "outer" and inner_ran == [99]


@pytest.mark.asyncio
async def test_slow_update_logged(caplog):
    """هندلر کند → لاگ [UPDATE-TIMING] با هشدار مناسب."""
    import logging

    mw = SlowUpdateLogMiddleware()

    async def slow_handler(event, data):
        await asyncio.sleep(0.12)
        return "ok"

    with caplog.at_level(logging.INFO, logger="update_pipeline"):
        # آستانه را موقتاً پایین می‌آوریم تا در تست عملی شود
        update_pipeline.SLOW_INFO_SECONDS = 0.05
        try:
            await mw(slow_handler, _make_update(7, 3), {})
        finally:
            update_pipeline.SLOW_INFO_SECONDS = 5.0
    assert any("[UPDATE-TIMING]" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_fast_update_not_logged(caplog):
    import logging

    mw = SlowUpdateLogMiddleware()

    async def fast_handler(event, data):
        return "ok"

    with caplog.at_level(logging.INFO, logger="update_pipeline"):
        await mw(fast_handler, _make_update(7, 4), {})
    assert not any("[UPDATE-TIMING]" in r.message for r in caplog.records)


def _user_of_update_covers_all_event_types():
    from aiogram.types import CallbackQuery, PreCheckoutQuery

    cb = _make_update(5, 1).model_copy(deep=True)
    assert update_pipeline._user_of_update(cb) == 5

    u = _make_update(6, 2)
    u.message.text = None
    assert update_pipeline._user_of_update(u) == 6

    # آپدیت بدون کاربر → None (نباید خطا بدهد)
    empty = _make_update(1, 3).model_copy(update={"message": None})
    assert update_pipeline._user_of_update(empty) is None
