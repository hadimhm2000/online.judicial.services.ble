"""تست پنجرهٔ اصلاح اطلاعات پرونده لایحه (پس از «با اطلاعات ارسالی پرونده یافت نشد») —
اجرا: BOT_TOKEN=1:x ADMIN_ID=1 ADMIN_API_SECRET=x python -m pytest test_lavayeh_case_fix.py"""
import asyncio
import datetime
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("ADMIN_API_SECRET", "x")

import pytest

import nid_fix_window
import runtime_state
from states import Form

UID = 4242
NOT_FOUND = "با اطلاعات ارسالی پرونده یافت نشد."


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _isolate():
    runtime_state.pending_lavayeh_case_fix.clear()
    runtime_state.prepaid_registrations.clear()
    yield
    runtime_state.pending_lavayeh_case_fix.clear()
    runtime_state.prepaid_registrations.clear()


def _task(**kw):
    t = {
        "user_id": UID, "prepaid": True, "task_type": "LAVAYEH",
        "tracking_method": "case_number",
        "lavayeh_tracking_code": "140513920000628315",
        "lavayeh_province": "یزد", "lavayeh_row_number": 3,
        "lavayeh_persons": [{"person_type": "شخص حقیقی", "national_id": "0012345678"}],
        "lavayeh_text": "متن",
    }
    t.update(kw)
    return t


class FakeState:
    def __init__(self):
        self.data, self.state = {}, None

    async def get_data(self):
        return dict(self.data)

    async def update_data(self, **kw):
        self.data.update(kw)

    async def set_data(self, d):
        self.data = dict(d)

    async def set_state(self, s):
        self.state = s

    async def clear(self):
        self.data, self.state = {}, None


def _msg(text):
    return SimpleNamespace(text=text, from_user=SimpleNamespace(id=UID), answer=AsyncMock())


# ── سناریو: پیشنهاد پنجرهٔ اصلاح ────────────────────────────────────────

def test_offer_opens_window_and_keeps_task():
    import lavayeh_scenario
    bot = SimpleNamespace(send_message=AsyncMock())
    ok = run(lavayeh_scenario._offer_case_info_fix(_task(), bot, UID, NOT_FOUND))
    assert ok
    win = nid_fix_window.get_lavayeh_case_fix(UID)
    assert win["task_data"]["prepaid"] is True
    assert win["deadline"] > datetime.datetime.now()
    text = bot.send_message.await_args.args[1]
    assert "یافت نشد" in text and "140513920000628315" in text and "بدون پرداخت مجدد" in text
    kb = bot.send_message.await_args.kwargs["reply_markup"]
    datas = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert datas == [f"lav_case_fix:{UID}", f"lav_case_cancel:{UID}"]


def test_offer_refused_after_max_rounds():
    import lavayeh_scenario
    bot = SimpleNamespace(send_message=AsyncMock())
    t = _task(_case_fix_rounds=nid_fix_window.LAVAYEH_CASE_FIX_MAX_ROUNDS)
    assert not run(lavayeh_scenario._offer_case_info_fix(t, bot, UID, NOT_FOUND))
    assert nid_fix_window.get_lavayeh_case_fix(UID) is None
    bot.send_message.assert_not_awaited()


def test_archive_failure_is_fatal_subclass():
    # دسته‌جمعی همچنان از مسیر LavayehFatalError (ثبت شکست ردیف) عبور می‌کند
    import lavayeh_scenario as ls
    assert issubclass(ls.LavayehCaseNotFoundError, ls.LavayehFatalError)
    e = ls.LavayehCaseNotFoundError("x", sana_text=NOT_FOUND)
    assert e.sana_text == NOT_FOUND


# ── هندلرها: تغییر روش ورود و ارسال مجدد به صف ──────────────────────────

def _drive(*steps):
    import lavayeh_handlers as lh
    st = FakeState()
    for handler, text in steps:
        m = _msg(text)
        if handler is lh.lav_case_fix_confirm:
            run(handler(m, st, SimpleNamespace(send_message=AsyncMock())))
        else:
            run(handler(m, st))
    return st


def test_switch_case_number_to_archive_and_requeue(monkeypatch):
    import lavayeh_handlers as lh
    nid_fix_window.start_lavayeh_case_fix(UID, _task(), NOT_FOUND)
    q = asyncio.Queue()
    monkeypatch.setattr(runtime_state, "job_queue", q)

    st = _drive((lh.lav_case_fix_method, "2️⃣ شعبه رسیدگی کننده و شماره بایگانی"))
    assert st.state == Form.lavayeh_case_fix_archive_number
    run(lh.lav_case_fix_archive_number(_msg("0312345"), st))
    assert st.state == Form.lavayeh_case_fix_branch
    run(lh.lavayeh_case_fix_branch_selected(_msg(""), st, "شعبه ۱ دادگاه", "12345", "p"))
    assert st.state == Form.lavayeh_case_fix_confirm
    run(lh.lav_case_fix_confirm(_msg("✅ تایید و ثبت مجدد"), st,
                                SimpleNamespace(send_message=AsyncMock())))

    job = q.get_nowait()
    assert job["tracking_method"] == "archive_number"
    assert job["lavayeh_archive_number"] == "0312345"
    assert job["lavayeh_branch_code"] == "12345"
    assert job["prepaid"] is True                       # پرداخت مجدد لازم نیست
    assert job["lavayeh_persons"][0]["national_id"] == "0012345678"
    assert job["_case_fix_rounds"] == 1
    assert nid_fix_window.get_lavayeh_case_fix(UID) is None
    assert UID in runtime_state.active_lavayeh_users


def test_fix_province_only_with_keep_buttons(monkeypatch):
    import lavayeh_handlers as lh
    nid_fix_window.start_lavayeh_case_fix(UID, _task(), NOT_FOUND)
    q = asyncio.Queue()
    monkeypatch.setattr(runtime_state, "job_queue", q)
    keep = lh.LAVAYEH_CASE_FIX_KEEP

    st = FakeState()
    run(lh.lav_case_fix_method(_msg("1️⃣ شماره پرونده و ردیف فرعی"), st))
    run(lh.lav_case_fix_tracking_code(_msg(keep), st))
    assert st.state == Form.lavayeh_case_fix_province
    run(lh.lav_case_fix_province(_msg("تهران" if "تهران" in lh.PROVINCES else lh.PROVINCES[0]), st))
    run(lh.lav_case_fix_row_number(_msg(keep), st))
    assert st.state == Form.lavayeh_case_fix_confirm
    run(lh.lav_case_fix_confirm(_msg("✅ تایید و ثبت مجدد"), st,
                                SimpleNamespace(send_message=AsyncMock())))
    job = q.get_nowait()
    assert job["lavayeh_tracking_code"] == "140513920000628315"
    assert job["lavayeh_row_number"] == 3
    assert job["lavayeh_province"] != "یزد"


def test_invalid_tracking_code_rejected():
    import lavayeh_handlers as lh
    nid_fix_window.start_lavayeh_case_fix(UID, _task(), NOT_FOUND)
    st = FakeState()
    run(lh.lav_case_fix_method(_msg("1️⃣ شماره پرونده و ردیف فرعی"), st))
    m = _msg("123")
    run(lh.lav_case_fix_tracking_code(m, st))
    assert st.state == Form.lavayeh_case_fix_tracking_code
    assert "_cf_tracking_code" not in st.data


def test_expired_window_blocks_steps():
    import lavayeh_handlers as lh
    st = FakeState()
    m = _msg("1️⃣ شماره پرونده و ردیف فرعی")
    run(lh.lav_case_fix_method(m, st))
    assert st.state is None
    assert "مهلت" in m.answer.await_args.args[0]


# ── اسوئپر: انقضا بدون جریمه ────────────────────────────────────────────

def test_sweep_expires_without_touching_prepay():
    runtime_state.prepaid_registrations[UID] = {"amount_rial": 10000, "prepay_paid_rial": 10000}
    win = nid_fix_window.start_lavayeh_case_fix(UID, _task(), NOT_FOUND)
    win["deadline"] = datetime.datetime.now() - datetime.timedelta(seconds=1)
    bot = SimpleNamespace(send_message=AsyncMock())
    closed = run(nid_fix_window.sweep_expired(bot))
    assert closed >= 1
    assert nid_fix_window.get_lavayeh_case_fix(UID) is None
    assert runtime_state.prepaid_registrations[UID]["amount_rial"] == 10000
    user_text = bot.send_message.await_args_list[0].args[1]
    assert "پیش‌پرداخت شما حفظ شده" in user_text
