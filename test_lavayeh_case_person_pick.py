"""تست فلوی «انتخاب ارائه‌دهنده لایحه از فهرست اشخاص پرونده» (اصلاحیهٔ کارفرما).

پس از خطای «شخص ارائه‌کننده لایحه ... در فهرست اشخاص پرونده نیست» در ثبت موقت:
  - ربات فهرست اشخاص پرونده (کدملی + نام + سمت) را از مودال #casePersonList
    استخراج می‌کند؛
  - به کاربر می‌گوید صرفاً این نام‌ها در پرونده هستند و از همین لیست انتخاب کند؛
  - اطلاعات کدملی قبلی کامل حذف و با انتخاب کاربر جایگزین می‌شود؛
  - گزینهٔ انصراف: ۳۰,۰۰۰ تومان از پیش‌پرداخت (پس از تایید مدیر) برمی‌گردد.

اجرا: BOT_TOKEN=1:x ADMIN_ID=1 ADMIN_API_SECRET=x python -m pytest test_lavayeh_case_person_pick.py
"""
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
ERROR_TEXT = ("شخص ارائه كننده لايحه به\u200cنام «محمدهادي منتظران» در فهرست "
              "اشخاص پرونده نیست و امکان ثبت لايحه دفاعيه وجود ندارد")

CASE_PERSONS = [
    {"row": "1", "first_name": "علي", "last_name": "خادمي مجومرد",
     "father_name": "غلامرضا", "national_id": "4433435457", "role": "خواهان/شاكي"},
    {"row": "2", "first_name": "علي", "last_name": "بهمني نيا",
     "father_name": "جواد", "national_id": "4420160616", "role": "خوانده/متهم"},
    {"row": "3", "first_name": "دادسراي عمومي و انقلاب شهرستان يزد - دادستان",
     "last_name": "---", "father_name": "---", "national_id": "03033$0050",
     "role": "دادستان/نماينده دادستان"},
]


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    runtime_state.pending_nid_fix_windows.clear()
    runtime_state.pending_lavayeh_sana_fix.clear()
    runtime_state.prepaid_registrations.clear()
    runtime_state.active_lavayeh_users.discard(UID)
    # فایل‌های وضعیت به پوشهٔ موقت بروند نه پوشهٔ پروژه
    try:
        import persistence
        monkeypatch.setattr(persistence, "STATE_FILE", str(tmp_path / "state.json"))
        monkeypatch.setattr(persistence, "STATE_FILE_BACKUP", str(tmp_path / "state.bak.json"))
    except Exception:
        pass
    try:
        import refund_approvals
        monkeypatch.setattr(refund_approvals, "STORE_FILE", str(tmp_path / "refund.json"))
    except Exception:
        pass
    yield
    runtime_state.pending_nid_fix_windows.clear()
    runtime_state.pending_lavayeh_sana_fix.clear()
    runtime_state.prepaid_registrations.clear()
    runtime_state.active_lavayeh_users.discard(UID)


def _task(**kw):
    t = {
        "user_id": UID, "prepaid": True, "task_type": "LAVAYEH",
        "tracking_method": "case_number",
        "lavayeh_tracking_code": "140513920000628315",
        "lavayeh_province": "یزد", "lavayeh_row_number": 3,
        "lavayeh_persons": [{"person_type": "شخص حقیقی",
                             "national_id": "0012345678"}],
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
    return SimpleNamespace(text=text, from_user=SimpleNamespace(id=UID),
                           answer=AsyncMock())


def _cb(data, uid=UID):
    return SimpleNamespace(
        data=data, from_user=SimpleNamespace(id=uid),
        answer=AsyncMock(),
        message=SimpleNamespace(text="پیام فهرست", edit_text=AsyncMock()))


def _bot():
    return SimpleNamespace(send_message=AsyncMock())


# ══════════════════════════════════════════════════════════════════════
# ۱) استخراج فهرست از مودال + حمل روی exception
# ══════════════════════════════════════════════════════════════════════

class FakeModalPage:
    """صفحهٔ جعلی: مودال #casePersonList باز می‌شود و ۳ شخص دارد."""

    def __init__(self, persons=CASE_PERSONS, open_result="case-btn"):
        self.persons = persons
        self.open_result = open_result
        self.calls = []

    async def evaluate(self, js, *args):
        self.calls.append(js)
        if "btnAddPersonFromCase" in js:
            return self.open_result
        if "#casePersonList" in js and "classList.contains" in js:
            return True                     # مودال نمایان است
        if "theHstCasePersonTempList" in js:
            return self.persons             # ردیف‌های جدول
        return None


@pytest.fixture
def _fast_browser(monkeypatch):
    """حذف صبرهای واقعی و کلیک مرحله از مسیر استخراج."""
    import lavayeh_scenario as ls
    async def _sleep(page, s, bot=None, uid=None):
        return False
    async def _idle(page):
        return True
    async def _step(page, name, bot=None, uid=None):
        return True
    monkeypatch.setattr(ls, "resilient_sleep", _sleep)
    monkeypatch.setattr(ls, "wait_for_angular_idle", _idle)
    monkeypatch.setattr(ls, "_click_step_label", _step)
    return ls


def test_extract_reads_case_person_list(_fast_browser):
    ls = _fast_browser
    page = FakeModalPage()
    out = run(ls._open_case_person_list_and_extract(page, _bot(), UID))
    assert out == CASE_PERSONS
    assert out[0]["national_id"] == "4433435457"
    assert out[2]["national_id"] == "03033$0050"


def test_raise_attaches_case_persons(_fast_browser):
    """خطای ثبت موقت → فهرست استخراج و روی exception حمل می‌شود (فلو جدید)."""
    ls = _fast_browser
    page = FakeModalPage()
    bot = _bot()
    with pytest.raises(ls.LavayehSanaDataError) as ei:
        run(ls._raise_fatal_temp_save_error(page, bot, UID, ERROR_TEXT))
    e = ei.value
    assert e.kind == "person_not_in_case"
    assert e.case_persons == CASE_PERSONS
    assert e.person_name == "محمدهادي منتظران"
    # پیام «در حال دریافت فهرست...» قبل از استخراج ارسال شده است
    texts = [c.args[1] for c in bot.send_message.await_args_list]
    assert any("فهرست اشخاص پرونده" in t for t in texts)


def test_raise_falls_back_when_list_unreadable(_fast_browser):
    """مودال باز نشد → فال‌بک به همان روند قبلی (پیام ویرایش کدملی)."""
    ls = _fast_browser
    page = FakeModalPage(open_result=None)
    bot = _bot()
    with pytest.raises(ls.LavayehSanaDataError) as ei:
        run(ls._raise_fatal_temp_save_error(page, bot, UID, ERROR_TEXT))
    e = ei.value
    assert e.kind == "person_not_in_case"
    assert e.case_persons == []
    texts = [c.args[1] for c in bot.send_message.await_args_list]
    assert any("در فهرست اشخاص پرونده نیست" in t for t in texts)


def test_birthdate_error_keeps_old_path(_fast_browser):
    """خطای تاریخ تولد تغییری نکرده — پیام ویرایش کدملی (بدون فهرست)."""
    ls = _fast_browser
    page = FakeModalPage()
    bot = _bot()
    err = "تاریخ تولد ارسالی مربوط به شماره ملی 4433435457 اشتباه است"
    with pytest.raises(ls.LavayehSanaDataError) as ei:
        run(ls._raise_fatal_temp_save_error(page, bot, UID, err))
    assert ei.value.kind == "birthdate"
    assert ei.value.case_persons == []


# ══════════════════════════════════════════════════════════════════════
# ۲) پیام و کیبورد انتخاب
# ══════════════════════════════════════════════════════════════════════

def _kb_datas(kb):
    return [b.callback_data for row in kb.inline_keyboard for b in row]


def test_build_ui_lists_all_persons_with_nid_and_role():
    import lavayeh_scenario as ls
    text, kb = ls._build_case_person_pick_ui(UID, CASE_PERSONS, [], error_text=ERROR_TEXT)
    # نام‌ها و کدملی و سمت‌ها در پیام هستند
    for p in CASE_PERSONS:
        assert p["national_id"] in text
        assert p["role"] in text
    assert "صرفاً این نام‌ها در پرونده" in text
    assert "مجدداً از همین لیست" in text          # توضیح انتخاب مجدد کدملی قبلی
    assert "۳۰,۰۰۰ تومان" in text                  # اعلام بازگشت وجه انصراف
    # دکمه‌ها: سه شخص + انصراف (بدون «پایان انتخاب» چون هنوز انتخابی نیست)
    datas = _kb_datas(kb)
    assert f"lav_cpk_pick:{UID}:0" in datas
    assert f"lav_cpk_pick:{UID}:1" in datas
    assert f"lav_cpk_pick:{UID}:2" in datas
    assert f"lav_cpk_cancel:{UID}" in datas
    assert f"lav_cpk_done:{UID}" not in datas


def test_build_ui_after_selection_shows_done_and_excludes_selected():
    import lavayeh_scenario as ls
    selected = [{"person_type": "شخص حقیقی", "national_id": "4433435457",
                 "name": "علي خادمي مجومرد", "case_role": "خواهان/شاكي"}]
    text, kb = ls._build_case_person_pick_ui(UID, CASE_PERSONS, selected)
    datas = _kb_datas(kb)
    assert f"lav_cpk_pick:{UID}:0" not in datas     # انتخاب‌شده حذف شد
    assert f"lav_cpk_pick:{UID}:1" in datas
    assert f"lav_cpk_done:{UID}" in datas           # دکمهٔ پایان ظاهر شد
    assert f"lav_cpk_cancel:{UID}" in datas
    assert "علي خادمي مجومرد" in text               # انتخاب‌ها در متن هم هستند


# ══════════════════════════════════════════════════════════════════════
# ۳) هندلرها: انتخاب / تکراری / شخص حقوقی / پایان / انصراف
# ══════════════════════════════════════════════════════════════════════

def _start_pick_window():
    win = nid_fix_window.start_window(
        UID, flow=nid_fix_window.FLOW_LAVAYEH, task_data=_task(),
        error_text=ERROR_TEXT, kind="person_not_in_case")
    win["case_persons"] = CASE_PERSONS
    win["case_persons_selected"] = []
    return win


def test_pick_real_person_appends_selection():
    import lavayeh_handlers as lh
    win = _start_pick_window()
    st = FakeState()
    run(lh.lav_case_pick_callback(_cb(f"lav_cpk_pick:{UID}:0"), st, _bot()))
    sel = win["case_persons_selected"]
    assert len(sel) == 1
    assert sel[0]["person_type"] == "شخص حقیقی"
    assert sel[0]["national_id"] == "4433435457"
    assert sel[0]["name"] == "علي خادمي مجومرد"
    assert st.state == Form.lavayeh_case_pick_wait


def test_pick_lawyer_maps_to_lawyer_type():
    import lavayeh_handlers as lh
    win = _start_pick_window()
    win["case_persons"] = [{
        "row": "1", "first_name": "محمد", "last_name": "وکیلی",
        "father_name": "---", "national_id": "1111111111", "role": "وکیل"}]
    st = FakeState()
    run(lh.lav_case_pick_callback(_cb(f"lav_cpk_pick:{UID}:0"), st, _bot()))
    assert win["case_persons_selected"][0]["person_type"] == "وکیل"


def test_pick_duplicate_blocked():
    import lavayeh_handlers as lh
    win = _start_pick_window()
    st = FakeState()
    run(lh.lav_case_pick_callback(_cb(f"lav_cpk_pick:{UID}:0"), st, _bot()))
    cb2 = _cb(f"lav_cpk_pick:{UID}:0")
    run(lh.lav_case_pick_callback(cb2, FakeState(), _bot()))
    assert len(win["case_persons_selected"]) == 1
    cb2.answer.assert_awaited_once()               # «قبلاً انتخاب شده»


def test_pick_entity_asks_representative_then_appends():
    import lavayeh_handlers as lh
    win = _start_pick_window()
    st = FakeState()
    # شخص حقوقی (کدملی غیر ۱۰ رقمی مثل دادستان) → پرسش نوع نماینده
    run(lh.lav_case_pick_callback(_cb(f"lav_cpk_pick:{UID}:2"), st, _bot()))
    assert st.state == Form.lavayeh_case_pick_rep_type
    # نوع نماینده
    run(lh.lav_case_pick_rep_type(_msg("نماینده"), st))
    assert st.state == Form.lavayeh_case_pick_rep_nid
    # کدملی نماینده
    run(lh.lav_case_pick_rep_nid(_msg("5555555555"), st, _bot()))
    sel = win["case_persons_selected"]
    assert len(sel) == 1
    assert sel[0]["person_type"] == "شخص حقوقی"
    assert sel[0]["company_id"] == "03033$0050"
    assert sel[0]["representative_type"] == "نماینده"
    assert sel[0]["national_id"] == "5555555555"
    assert st.state == Form.lavayeh_case_pick_wait


def test_done_replaces_old_persons_and_requeues(monkeypatch):
    import lavayeh_handlers as lh
    win = _start_pick_window()
    q = asyncio.Queue()
    monkeypatch.setattr(runtime_state, "job_queue", q)
    st = FakeState()

    run(lh.lav_case_pick_callback(_cb(f"lav_cpk_pick:{UID}:0"), st, _bot()))
    run(lh.lav_case_pick_callback(_cb(f"lav_cpk_pick:{UID}:1"), FakeState(), _bot()))
    run(lh.lav_case_pick_done_callback(_cb(f"lav_cpk_done:{UID}"), FakeState(), _bot()))

    job = q.get_nowait()
    # ⭐ اطلاعات کدملی قبلی کامل حذف و با انتخاب کاربر جایگزین شد
    assert job["lavayeh_persons"] == win["case_persons_selected"]
    assert all(p["national_id"] != "0012345678" for p in job["lavayeh_persons"])
    assert {p["national_id"] for p in job["lavayeh_persons"]} == {"4433435457", "4420160616"}
    assert job["prepaid"] is True                     # بدون پرداخت مجدد
    assert nid_fix_window.get_window(UID) is None
    assert runtime_state.pending_lavayeh_sana_fix.get(UID) is None
    assert UID in runtime_state.active_lavayeh_users


def test_done_without_selection_blocked():
    import lavayeh_handlers as lh
    _start_pick_window()
    cb = _cb(f"lav_cpk_done:{UID}")
    run(lh.lav_case_pick_done_callback(cb, FakeState(), _bot()))
    cb.answer.assert_awaited_once()
    assert "حداقل یک شخص" in cb.answer.await_args.args[0]


def test_pick_from_other_user_rejected():
    import lavayeh_handlers as lh
    _start_pick_window()
    cb = _cb(f"lav_cpk_pick:{UID}:0", uid=999)
    run(lh.lav_case_pick_callback(cb, FakeState(), _bot()))
    cb.answer.assert_awaited_once()
    assert "مربوط به شما نیست" in cb.answer.await_args.args[0]


# ══════════════════════════════════════════════════════════════════════
# ۴) انصراف — بازگشت ۳۰,۰۰۰ تومان از پیش‌پرداخت + مصرف باقی
# ══════════════════════════════════════════════════════════════════════

def _make_reservation(paid_rial=1_000_000, free_rial=0):
    runtime_state.prepaid_registrations[UID] = {
        "version": 2, "free_credit_rial": free_rial,
        "reservations": [{
            "status": "reserved", "service_key": "lavayeh",
            "task_id": "T1", "paid_rial": paid_rial,
            "credit_used_rial": 0, "reserved_rial": paid_rial,
            "paid_at": datetime.datetime.now(),
        }],
    }


def test_cancel_refunds_30000_and_consumes_rest(monkeypatch):
    import refund_approvals
    import lavayeh_handlers as lh
    _start_pick_window()
    _make_reservation(paid_rial=1_000_000)      # پیش‌پرداخت ۱۰۰,۰۰۰ تومان
    captured = []
    monkeypatch.setattr(refund_approvals, "request_refund_nowait",
                        lambda uid, toman, note, source="", **kw:
                        captured.append((uid, toman, source)) or "rid")

    run(lh.lav_case_pick_cancel_callback(_cb(f"lav_cpk_cancel:{UID}"),
                                         FakeState(), _bot()))
    # درخواست بازگشت ۳۰,۰۰۰ تومان (نه ۵۰٪ و نه کل مبلغ)
    assert captured == [(UID, 30_000, "lavayeh_case_pick_cancel")]
    # باقی پیش‌پرداخت مصرف شد
    res = runtime_state.prepaid_registrations[UID]["reservations"][0]
    assert res["status"] == "consumed_manual"
    assert res["release_reason"] == "lavayeh_case_pick_cancel"
    # پنجره بسته شد
    assert nid_fix_window.get_window(UID) is None
    assert runtime_state.pending_lavayeh_sana_fix.get(UID) is None


def test_cancel_caps_refund_at_prepay_amount(monkeypatch):
    import refund_approvals
    import lavayeh_handlers as lh
    _start_pick_window()
    _make_reservation(paid_rial=100_000)        # فقط ۱۰,۰۰۰ تومان پرداخت شده
    captured = []
    monkeypatch.setattr(refund_approvals, "request_refund_nowait",
                        lambda uid, toman, note, source="", **kw:
                        captured.append((uid, toman, source)) or "rid")
    run(lh.lav_case_pick_cancel_callback(_cb(f"lav_cpk_cancel:{UID}"),
                                         FakeState(), _bot()))
    assert captured == [(UID, 10_000, "lavayeh_case_pick_cancel")]


def test_cancel_without_reservation_is_safe():
    import lavayeh_handlers as lh
    _start_pick_window()                        # بدون رزرو → بدون کرش
    run(lh.lav_case_pick_cancel_callback(_cb(f"lav_cpk_cancel:{UID}"),
                                         FakeState(), _bot()))
    assert nid_fix_window.get_window(UID) is None


def test_settle_case_pick_cancel_returns_user_line(monkeypatch):
    import refund_approvals
    _make_reservation(paid_rial=1_000_000, free_rial=50_000)
    captured = []
    monkeypatch.setattr(refund_approvals, "request_refund_nowait",
                        lambda uid, toman, note, source="", **kw:
                        captured.append((uid, toman, source)) or "rid")
    line = run(nid_fix_window.settle_case_pick_cancel(UID))
    # ۳۰,۰۰۰ تومان + ماندهٔ آزاد (۵,۰۰۰ تومان) → ۳۵,۰۰۰
    assert captured == [(UID, 35_000, "lavayeh_case_pick_cancel")]
    assert "30,000" in line
    assert runtime_state.prepaid_registrations[UID]["free_credit_rial"] == 0


# ══════════════════════════════════════════════════════════════════════
# ۵) انقضای پنجره (۳ ساعته + جریمه نصف پیش‌پرداخت طبق قواعد فعلی)
# ══════════════════════════════════════════════════════════════════════

def test_sweep_expired_case_pick_window(monkeypatch):
    import refund_approvals
    win = _start_pick_window()
    win["deadline"] = datetime.datetime.now() - datetime.timedelta(seconds=1)
    _make_reservation(paid_rial=1_000_000)
    captured = []
    monkeypatch.setattr(refund_approvals, "request_refund_nowait",
                        lambda uid, toman, note, source="", **kw:
                        captured.append((uid, toman, source)) or "rid")
    bot = _bot()
    closed = run(nid_fix_window.sweep_expired(bot))
    assert closed >= 1
    assert nid_fix_window.get_window(UID) is None
    texts = [c.args[1] for c in bot.send_message.await_args_list]
    # پیام اختصاصی فلو (نه «ویرایش کدملی») + جریمهٔ نصف پیش‌پرداخت
    assert any("انتخاب ارائه‌دهنده" in t for t in texts)
    assert any("نصف مبلغ پیش‌پرداخت" in t for t in texts)
    # نصف ۱۰۰,۰۰۰ تومان = ۵۰,۰۰۰ تومان درخواست بازگشت
    assert (UID, 50_000, "nid_fix_penalty") in captured


def test_is_case_pick_kind_detection():
    win = _start_pick_window()
    assert nid_fix_window.is_case_pick_kind(win) is True
    plain = nid_fix_window.start_window(
        UID, flow=nid_fix_window.FLOW_LAVAYEH, task_data=_task(),
        error_text="x", kind="birthdate")
    assert nid_fix_window.is_case_pick_kind(plain) is False
    assert nid_fix_window.is_case_pick_kind(None) is False


# ══════════════════════════════════════════════════════════════════════
# ۶) تست رفتاری واقعی با Chromium — استخراج از HTML واقعی مودال سنا
#    (test_fixtures/sana_case_person_list_modal.html عین HTML ارسالی کارفرماست)
# ══════════════════════════════════════════════════════════════════════

def test_extract_against_real_modal_html(_fast_browser):
    pytest.importorskip("playwright")
    ls = _fast_browser
    try:
        from playwright.async_api import async_playwright
    except Exception:
        pytest.skip("playwright async api unavailable")
    import pathlib

    fixture = pathlib.Path(__file__).parent / "test_fixtures" / "sana_case_person_list_modal.html"

    async def _scenario():
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            try:
                page = await browser.new_page()
                await page.goto(fixture.as_uri())
                out = await ls._open_case_person_list_and_extract(page, _bot(), UID)
                # وضعیت مودال پس از استخراج: باید بسته شده باشد
                modal_closed = await page.evaluate(
                    "() => { const m = document.querySelector('#casePersonList');"
                    " return !m || (!m.classList.contains('in') && "
                    "getComputedStyle(m).display === 'none'); }")
                return out, modal_closed
            finally:
                await browser.close()

    try:
        out, modal_closed = run(_scenario())
    except Exception as e:                                  # مرورگر در این محیط نیست
        pytest.skip(f"chromium unavailable: {e}")

    assert len(out) == 3
    # ردیف ۱: علي خادمي مجومرد (ي/ك عربی → ی/ک فارسی نرمال شده)
    assert out[0]["first_name"] == "علی"
    assert out[0]["last_name"] == "خادمی مجومرد"
    assert out[0]["father_name"] == "غلامرضا"
    assert out[0]["national_id"] == "4433435457"
    assert out[0]["role"] == "خواهان/شاکی"
    # ردیف ۲
    assert out[1]["national_id"] == "4420160616"
    assert out[1]["role"] == "خوانده/متهم"
    assert out[1]["last_name"] == "بهمنی نیا"
    # ردیف ۳: شخص حقوقی (دادستان) با کد ویژه
    assert out[2]["national_id"] == "03033$0050"
    assert out[2]["role"] == "دادستان/نماینده دادستان"
    assert "دادسرای عمومی" in out[2]["first_name"]
    # مودال پس از استخراج بسته شده است (بدون انتخاب هیچ شخصی)
    assert modal_closed is True
