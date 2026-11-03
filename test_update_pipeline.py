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


def _make_pre_checkout_update(uid: int, update_id: int):
    from aiogram.types import PreCheckoutQuery, Update, User

    return Update(
        update_id=update_id,
        pre_checkout_query=PreCheckoutQuery(
            id=str(update_id),
            from_user=User(id=uid, is_bot=False, first_name="u"),
            currency="IRR",
            total_amount=10000,
            invoice_payload="{}",
        ),
    )


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
async def test_pre_checkout_query_bypasses_user_lock():
    """⭐ اصلاحیه ۱۴۰۵/۰۸: pre_checkout_query بدون انتظار برای قفل کاربر عبور
    می‌کند — مهلت ~۱۰ ثانیه‌ای پاسخ بله پشت هندلر کندِ همان کاربر نمی‌گذرد."""
    mw = UserSerialMiddleware()
    slow_started = asyncio.Event()
    release_slow = asyncio.Event()

    async def slow_handler(event, data):
        slow_started.set()
        # هندلر کند همان کاربر (مثل آپدیت ۴۶ ثانیه‌ای لاگ ۱۴۰۵/۰۸/۰۶)
        try:
            await asyncio.wait_for(release_slow.wait(), timeout=3)
        except asyncio.TimeoutError:
            pass
        return "slow"

    async def checkout_handler(event, data):
        return "checkout-ok"

    async def run_slow():
        return await mw(slow_handler, _make_update(10, 1), {})

    task = asyncio.create_task(run_slow())
    await asyncio.wait_for(slow_started.wait(), timeout=2)
    try:
        # کاربر ۱۰ هنوز در هندلر کند قفل است؛ pre_checkout همان کاربر
        # نباید منتظر قفل بماند (در مهلت ~۱۰ ثانیه‌ای بله جواب داده می‌شود)
        res = await asyncio.wait_for(
            mw(checkout_handler, _make_pre_checkout_update(10, 2), {}), timeout=1.0)
        assert res == "checkout-ok"
    finally:
        release_slow.set()
    assert await asyncio.wait_for(task, timeout=2) == "slow"


@pytest.mark.asyncio
async def test_normal_message_waits_for_busy_user_lock():
    """پیام عادی همان کاربرِ مشغول، همچنان صف می‌شود (سریال‌سازی حفظ می‌شود)."""
    mw = UserSerialMiddleware()
    slow_started = asyncio.Event()
    release_slow = asyncio.Event()
    order = []

    async def slow_handler(event, data):
        slow_started.set()
        order.append("slow-start")
        try:
            await asyncio.wait_for(release_slow.wait(), timeout=3)
        except asyncio.TimeoutError:
            pass
        order.append("slow-end")
        return "slow"

    async def queued_handler(event, data):
        order.append("queued")
        return "queued"

    async def run_slow():
        return await mw(slow_handler, _make_update(10, 1), {})

    task = asyncio.create_task(run_slow())
    await asyncio.wait_for(slow_started.wait(), timeout=2)
    # پیام عادی همان کاربر: هنوز شروع نشده چون قفل در اختیار هندلر کند است
    inner = asyncio.create_task(mw(queued_handler, _make_update(10, 2), {}))
    await asyncio.sleep(0.15)
    assert order == ["slow-start"]
    release_slow.set()
    assert await asyncio.wait_for(task, timeout=2) == "slow"
    assert await asyncio.wait_for(inner, timeout=2) == "queued"
    assert order == ["slow-start", "slow-end", "queued"]


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


def test_user_of_update_covers_all_event_types():
    """⭐ اصلاحیه ۱۴۰۵/۰۸: این تابع پیشوند test_ نداشت و هرگز اجرا نمی‌شد."""
    from aiogram.types import CallbackQuery, Chat, Message, Update, User

    u = _make_update(5, 1)
    assert update_pipeline._user_of_update(u) == 5

    # callback_query
    cb = CallbackQuery(id="1", from_user=User(id=7, is_bot=False, first_name="u"),
                       chat_instance="ci", data="x",
                       message=Message(message_id=1, date=datetime.datetime.now(datetime.timezone.utc),
                                       chat=Chat(id=7, type="private")))
    assert update_pipeline._user_of_update(
        Update(update_id=2, callback_query=cb)) == 7

    # pre_checkout_query (مهم برای عبور بدون قفل)
    assert update_pipeline._user_of_update(_make_pre_checkout_update(8, 3)) == 8

    # پیام بدون متن (مثلاً فقط عکس) — مدل‌های aiogram فروزن‌اند؛ مستقیم ساخته می‌شود
    from aiogram.types import Chat as _Chat, Message as _Message, Update as _Update, User as _User
    plain = _Update(update_id=4, message=_Message(
        message_id=4, date=datetime.datetime.now(datetime.timezone.utc),
        chat=_Chat(id=6, type="private"),
        from_user=_User(id=6, is_bot=False, first_name="u")))
    assert update_pipeline._user_of_update(plain) == 6

    # آپدیت بدون کاربر → None (نباید خطا بدهد)
    empty = _make_update(1, 5).model_copy(update={"message": None})
    assert update_pipeline._user_of_update(empty) is None
