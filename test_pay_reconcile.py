"""تست pay_reconcile — هشدار پرداخت بدون پیگیری (لاگ ۱۴۰۵/۰۸/۰۶).

سناریوهای لاگ ۱۴۰۵/۰۸/۰۶: پرداخت انجام می‌شود اما به‌دلیل گم‌شدن FSM/
ری‌استارت، هیچ فرآیند فعالی برای کاربر شروع نمی‌شود. حلقهٔ آشتی‌سازی باید
۱۰ تا ۱۲۰ دقیقه پس از پرداخت، فقط یک بار به مدیر هشدار دهد.
"""
import asyncio
import datetime
import os
from unittest.mock import AsyncMock

import pytest

# config.py در زمان import به BOT_TOKEN/ADMIN_ID نیاز دارد (مثل سایر تست‌ها)
os.environ.setdefault("BOT_TOKEN", "1:test")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("BALE_API_BASE", "https://tapi.bale.ai")

import pay_reconcile
import runtime_state


class _FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, **kw):
        self.sent.append((chat_id, text))


def _set_prepaid(uid, minutes_ago, amount_rial=100_000, svc="lavayeh"):
    runtime_state.prepaid_registrations[uid] = {
        "amount_rial": amount_rial,
        "amount_toman": amount_rial // 10,
        "prepay_paid_rial": amount_rial,
        "service": svc,
        "service_label": "لایحه",
        "charge_id": "BALE-test",
        "paid_at": datetime.datetime.now() - datetime.timedelta(minutes=minutes_ago),
    }


@pytest.fixture(autouse=True)
def _clean():
    runtime_state.prepaid_registrations.pop(1, None)
    runtime_state.prepaid_registrations.pop(2, None)
    runtime_state.prepaid_registrations.pop(3, None)
    pay_reconcile._alerted.clear()
    yield
    runtime_state.prepaid_registrations.pop(1, None)
    runtime_state.prepaid_registrations.pop(2, None)
    runtime_state.prepaid_registrations.pop(3, None)
    pay_reconcile._alerted.clear()


@pytest.mark.asyncio
async def test_paid_without_followup_alerts_admin_once(monkeypatch):
    """پرداخت ۳۰ دقیقه پیش، بدون هیچ فرآیند فعال → فقط یک بار هشدار."""
    _set_prepaid(1, minutes_ago=30)
    # هیچ نشانهٔ فعالیتی نیست (pending_jobs / is_busy / pending_cases خالی‌اند)
    import pending_jobs
    monkeypatch.setattr(pending_jobs, "user_ids", lambda: set())
    import user_activity
    monkeypatch.setattr(user_activity, "is_busy", lambda uid: False)

    bot = _FakeBot()
    sent = await pay_reconcile.run_once(bot)
    assert sent == 1 and len(bot.sent) == 1
    assert "[PAY-RECONCILE]" in bot.sent[0][1]
    # چرخهٔ بعدی همان وضعیت → تکرار نمی‌شود
    assert await pay_reconcile.run_once(bot) == 0
    assert len(bot.sent) == 1


@pytest.mark.asyncio
async def test_paid_with_followup_no_alert(monkeypatch):
    """کاربر در صف ثبت است → هشدار داده نمی‌شود."""
    _set_prepaid(2, minutes_ago=30)
    import pending_jobs
    monkeypatch.setattr(pending_jobs, "user_ids", lambda: {2})

    bot = _FakeBot()
    assert await pay_reconcile.run_once(bot) == 0
    assert bot.sent == []


@pytest.mark.asyncio
async def test_too_fresh_and_too_old_ignored(monkeypatch):
    """پرداخت تازه (۲ دقیقه) و قدیمی (۳ ساعت) → نادیده."""
    import pending_jobs
    monkeypatch.setattr(pending_jobs, "user_ids", lambda: set())
    import user_activity
    monkeypatch.setattr(user_activity, "is_busy", lambda uid: False)

    _set_prepaid(3, minutes_ago=2)
    _set_prepaid(1, minutes_ago=200)
    bot = _FakeBot()
    assert await pay_reconcile.run_once(bot) == 0
    assert bot.sent == []


@pytest.mark.asyncio
async def test_active_lavayeh_user_counts_as_followup(monkeypatch):
    _set_prepaid(3, minutes_ago=30)
    import pending_jobs
    monkeypatch.setattr(pending_jobs, "user_ids", lambda: set())
    import user_activity
    monkeypatch.setattr(user_activity, "is_busy", lambda uid: False)
    runtime_state.active_lavayeh_users.add(3)
    try:
        bot = _FakeBot()
        assert await pay_reconcile.run_once(bot) == 0
        assert bot.sent == []
    finally:
        runtime_state.active_lavayeh_users.discard(3)
